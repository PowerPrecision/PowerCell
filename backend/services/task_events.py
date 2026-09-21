"""
Emissão de eventos de tarefa para o canal Redis (`task_started`/`progress`/…).

ÉPICO "Refatorização para Event-Driven" (Eixo 3): os serviços que correm
trabalho pesado deixam de apenas escrever na base de dados e passam a
**emitir eventos**, que o ``websocket_manager`` entrega em tempo real ao
utilizador dono da tarefa.

PORQUÊ ESTE MÓDULO EXISTE:
    O PowerCell tem dois sistemas de tarefas com formas diferentes —
    ``task_logs`` (``TaskLogService``) e ``background_jobs``
    (``BackgroundJobService`` + as importações IA em
    ``routes/ai_bulk/jobs.py``). Sem uma camada comum, cada um emitiria o
    seu formato e o frontend teria de conhecer três contratos. Aqui os três
    convergem num **payload único** que o cliente sabe ler.

    Igualmente importante: instrumentar os 12 pontos de escrita destes três
    sistemas cobre TODAS as tarefas pesadas do produto (importação Excel,
    análise IA em massa, envio de emails, extracção de documentos, motor de
    simulação financeira) sem tocar num único chamador.

CONTRATO DO PAYLOAD (o que o frontend recebe em `data`):
    ``{task_id, source, status, progress, message, title, task_type,
    process_id, error, result, updated_at}``

TENANT-SAFETY:
    Cada emissão exige o ``user_id`` **dono da tarefa** — é o destinatário
    do evento. Uma tarefa sem dono conhecido não gera evento (em vez de
    gerar um evento difundido): ver ``redis_pubsub.publish_event``.

NUNCA QUEBRA A TAREFA:
    Todas as funções aqui engolem as suas excepções. Emitir um evento é um
    efeito secundário de observabilidade: se falhar, a tarefa continua e o
    frontend cai para polling. A escrita na BD é que é a fonte de verdade.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from services.redis_pubsub import (
    TASK_COMPLETED,
    TASK_FAILED,
    TASK_PROGRESS,
    TASK_STARTED,
    publish_event,
)

logger = logging.getLogger(__name__)

# Origem da tarefa — permite ao cliente saber que lista invalidar.
SOURCE_TASK_LOG = "task_log"          # colecção `task_logs`
SOURCE_BACKGROUND_JOB = "background_job"  # colecção `background_jobs`

# Estados terminais → evento correspondente.
_TERMINAL_SUCCESS = {"completed", "success"}
_TERMINAL_FAILURE = {"failed", "error", "cancelled", "canceled"}
_RUNNING = {"processing", "running", "in_progress"}
_PENDING = {"pending", "queued", "paused"}


def _enum_value(value: Any) -> Any:
    """Desembrulha um Enum no seu valor (``TaskStatus.COMPLETED`` → ``"completed"``).

    ``TaskStatus``/``TaskType`` são ``str``-Enums, mas ``model_dump()`` em
    modo python devolve o membro do Enum, não a string. Sem esta
    normalização, ``str(TaskStatus.COMPLETED)`` daria
    ``"taskstatus.completed"`` e o mapeamento de estados falharia em
    silêncio — a tarefa ficaria eternamente "em progresso" na UI.
    """
    return getattr(value, "value", value)


def resolve_event_type(status: Optional[str], *, is_creation: bool = False) -> str:
    """Traduz o estado de uma tarefa no tipo de evento a emitir.

    Args:
        status: Estado da tarefa (``pending``/``processing``/``completed``/…).
        is_creation: ``True`` quando a tarefa acabou de ser criada — nesse
            caso o evento é sempre ``task_started``, mesmo que o estado
            inicial seja ``pending`` (para o cliente, a tarefa nasceu agora).

    Returns:
        Um de ``task_started`` / ``task_progress`` / ``task_completed`` /
        ``task_failed``. Estados desconhecidos degradam para
        ``task_progress`` — nunca se perde o sinal de que algo mudou.
    """
    normalized = str(_enum_value(status) or "").strip().lower()

    if normalized in _TERMINAL_SUCCESS:
        return TASK_COMPLETED
    if normalized in _TERMINAL_FAILURE:
        return TASK_FAILED
    if is_creation:
        return TASK_STARTED
    if normalized in _PENDING:
        return TASK_STARTED
    if normalized in _RUNNING:
        return TASK_PROGRESS
    return TASK_PROGRESS


def build_task_payload(
    *,
    task_id: str,
    source: str,
    status: Optional[str] = None,
    progress: Optional[int] = None,
    message: Optional[str] = None,
    title: Optional[str] = None,
    task_type: Optional[str] = None,
    process_id: Optional[str] = None,
    error: Optional[str] = None,
    result: Optional[dict] = None,
    updated_at: Optional[str] = None,
) -> dict:
    """Monta o payload canónico de um evento de tarefa.

    Campos a ``None`` são omitidos: o cliente faz merge sobre o estado que
    já tem, pelo que um evento de progresso não precisa de reenviar o
    título nem o tipo da tarefa.
    """
    payload: dict[str, Any] = {"task_id": task_id, "source": source}

    status_value = _enum_value(status)
    optional = {
        "status": str(status_value).lower() if status_value else None,
        "progress": (
            max(0, min(100, int(progress))) if progress is not None else None
        ),
        "message": message,
        "title": title,
        "task_type": _enum_value(task_type),
        "process_id": process_id,
        "error": error,
        "result": result,
        "updated_at": updated_at,
    }
    for key, value in optional.items():
        if value is not None:
            payload[key] = value

    return payload


async def emit_task_event(
    *,
    task_id: str,
    user_id: Optional[str],
    source: str,
    status: Optional[str] = None,
    is_creation: bool = False,
    company_id: Optional[str] = None,
    **payload_fields,
) -> bool:
    """Emite um evento de tarefa para o dono da tarefa.

    Returns:
        ``True`` se o evento seguiu pelo Redis. ``False`` quando degradou
        (sem dono conhecido, Redis em baixo, ou entrega apenas in-process).
        O chamador **não** deve reagir ao resultado — a tarefa segue na
        mesma; o frontend cai para polling se o tempo real falhar.
    """
    if not task_id:
        return False
    if not user_id:
        # Sem destinatário não há evento. Nunca difundir "para todos".
        logger.debug(
            f"[TASK-EVENT] Tarefa {task_id} sem user_id — evento não emitido"
        )
        return False

    try:
        event_type = resolve_event_type(status, is_creation=is_creation)
        payload = build_task_payload(
            task_id=task_id, source=source, status=status, **payload_fields
        )
        return await publish_event(
            event_type, payload, user_id=user_id, company_id=company_id
        )
    except Exception as e:
        # Observabilidade nunca quebra a tarefa que a originou.
        logger.warning(
            f"[TASK-EVENT] Falha ao emitir evento de {task_id}: "
            f"{type(e).__name__}: {e}"
        )
        return False


async def emit_task_log_event(
    task_doc: Any,
    *,
    is_creation: bool = False,
) -> bool:
    """Emite o evento correspondente a um documento de ``task_logs``.

    Aceita o ``TaskLogResponse`` devolvido por ``TaskLogService`` ou o dict
    equivalente — o serviço trabalha com ambos consoante o caminho.
    """
    doc = _as_dict(task_doc)
    if not doc:
        return False

    return await emit_task_event(
        task_id=doc.get("task_id") or doc.get("id"),
        user_id=doc.get("user_id"),
        source=SOURCE_TASK_LOG,
        status=doc.get("status"),
        is_creation=is_creation,
        title=doc.get("title"),
        task_type=doc.get("task_type"),
        progress=doc.get("progress"),
        message=doc.get("progress_message"),
        process_id=doc.get("process_id"),
        error=doc.get("error_message"),
        result=doc.get("result_data"),
        updated_at=doc.get("completed_at") or doc.get("started_at"),
    )


def _as_dict(value: Any) -> dict:
    """Normaliza modelo Pydantic / dict / None num dict simples."""
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    # Pydantic v2 e v1, por esta ordem
    for method in ("model_dump", "dict"):
        dumper = getattr(value, method, None)
        if callable(dumper):
            try:
                dumped = dumper()
                if isinstance(dumped, dict):
                    return dumped
            except Exception:  # pragma: no cover
                continue
    return {}

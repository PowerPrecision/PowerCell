"""
Orquestração da nota de voz do consultor — Épico 7, Eixo 3.

O FLUXO
-------
    áudio (S3, opcional)
        → transcrição            (`voice_transcription`)
        → extracção              (`voice_extraction`)
        → resumo na timeline     (`db.activities` + histórico do processo)
        → tarefas                (`task_api_crud.run_create_task`)
        → eventos em tempo real  (TaskLog → Redis → WebSocket)

PORQUE NÃO HÁ UM EVENTO NOVO
----------------------------
O Épico 4 já publica ``task_started``/``task_progress``/``task_completed``/
``task_failed`` no canal ``powercell_system_events``, entregues **apenas ao
dono da tarefa**, e o frontend já os escuta em ``hooks/useTaskEvents.js``.
Esta corrida usa um ``TaskLog`` do tipo ``VOICE_NOTE``, pelo que ganha o
tempo real de graça. Inventar um ``voice_note_ready`` obrigaria os dois
lados a conhecer dois contratos — o mesmo erro que o Épico 5 evitou ao
manter o nome ``new_email``. O que o cliente precisa de saber para se
actualizar viaja no ``result_data`` do evento terminal.

PORQUE NÃO SE ESCREVE `db.tasks` DIRECTAMENTE
---------------------------------------------
``run_create_task`` já prefixa o título com a referência do processo
(``[PROC-012]``), regista no histórico e notifica os atribuídos. Duplicar
esse ``insert_one`` aqui criaria tarefas com forma diferente das criadas à
mão — e a notificação desapareceria sem ninguém reparar.

DEGRADAÇÃO GRACIOSA
-------------------
A transcrição tem valor por si. Se o LLM falhar depois de o áudio já estar
transcrito, o resumo entra na timeline com o texto transcrito e a tarefa
termina com um aviso, em vez de o consultor perder o que gravou. Só uma
falha de transcrição termina em ``FAILED`` — aí não há mesmo nada a dizer.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from database import db

logger = logging.getLogger(__name__)

# Origem gravada na atividade e nos metadados das tarefas. É por este valor
# que se identifica (e se desfaz em bloco) o que a IA criou.
ORIGEM = "voice_note"

# Estados da nota em `db.voice_notes`.
ESTADO_PROCESSANDO = "processing"
ESTADO_CONCLUIDO = "completed"
ESTADO_FALHADO = "failed"
ESTADO_PARCIAL = "partial"  # transcreveu, mas a extracção falhou


# ====================================================================
# PERSISTÊNCIA DA NOTA
# ====================================================================


async def registar_nota(
    *,
    nota_id: str,
    process_id: str,
    user: dict,
    filename: str,
    mime_type: str,
    tamanho: int,
    s3_path: Optional[str],
    task_id: Optional[str],
) -> None:
    """Cria o registo da nota antes de a processar.

    Existe para que uma nota cuja corrida morra a meio (restart do worker,
    excepção não prevista) deixe rasto em vez de desaparecer.
    """
    try:
        await db.voice_notes.insert_one(
            {
                "id": nota_id,
                "process_id": process_id,
                "user_id": user.get("id"),
                "user_name": user.get("name"),
                "filename": filename,
                "mime_type": mime_type,
                "size_bytes": tamanho,
                "s3_path": s3_path,
                "task_id": task_id,
                "status": ESTADO_PROCESSANDO,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        )
    except Exception as e:  # pragma: no cover — Mongo em baixo
        logger.warning(f"[NOTA-VOZ] Registo da nota {nota_id} não criado: {e}")


async def _actualizar_nota(nota_id: str, campos: dict) -> None:
    try:
        await db.voice_notes.update_one(
            {"id": nota_id},
            {"$set": {**campos, "updated_at": datetime.now(timezone.utc).isoformat()}},
        )
    except Exception as e:  # pragma: no cover
        logger.warning(f"[NOTA-VOZ] Nota {nota_id} não actualizada: {e}")


# ====================================================================
# ESCRITA NA TIMELINE
# ====================================================================


async def registar_resumo_na_timeline(
    *,
    process_id: str,
    user: dict,
    resumo: str,
    nota_id: str,
) -> Optional[str]:
    """Grava o resumo como nota do consultor no histórico do processo.

    O autor é o consultor, não "Sistema": foi ele que falou. A proveniência
    fica em ``origin`` para a timeline poder distinguir visualmente uma nota
    ditada de um comentário escrito.

    Returns:
        O id da atividade criada, ou ``None`` se a escrita falhar.
    """
    activity_id = str(uuid.uuid4())
    try:
        await db.activities.insert_one(
            {
                "id": activity_id,
                "process_id": process_id,
                "user_id": user.get("id") or "system",
                "user_name": user.get("name") or "Consultor",
                "user_role": user.get("role") or "consultor",
                "comment": resumo,
                "origin": ORIGEM,
                "voice_note_id": nota_id,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        )
    except Exception as e:
        logger.warning(
            f"[NOTA-VOZ] Resumo da nota {nota_id} não gravado em {process_id}: {e}"
        )
        return None

    try:
        from services.history import log_history

        await log_history(process_id, user, "Registou nota de voz")
    except Exception as e:  # pragma: no cover — histórico é acessório
        logger.debug(f"[NOTA-VOZ] Histórico não registado: {e}")

    return activity_id


# ====================================================================
# CRIAÇÃO DAS TAREFAS
# ====================================================================


async def criar_tarefas(
    *,
    process_id: str,
    user: dict,
    tarefas: list,
    nota_id: str,
) -> list:
    """Cria em ``db.tasks`` as tarefas extraídas, atribuídas a quem gravou.

    Uma tarefa que falhe não trava as seguintes: melhor três das quatro do
    que nenhuma por causa de um título que o sanitizador recusou.

    Returns:
        Lista de ``{"id", "titulo", "due_date"}`` das tarefas criadas.
    """
    from models.task import TaskCreate
    from services.task_api_crud import run_create_task

    criadas = []
    for tarefa in tarefas:
        try:
            descricao = tarefa.get("descricao") or ""
            # O rasto da origem vive na descrição porque `TaskCreate` não
            # tem campo de metadados; sem ele, ninguém distingue mais tarde
            # uma tarefa ditada de uma escrita à mão.
            assinatura = f"[Nota de voz {nota_id}]"
            if assinatura not in descricao:
                descricao = f"{descricao}\n\n{assinatura}".strip()

            resposta = await run_create_task(
                TaskCreate(
                    title=tarefa["titulo"],
                    description=descricao,
                    assigned_to=[user["id"]],
                    process_id=process_id,
                    due_date=tarefa.get("due_date"),
                    priority=tarefa.get("prioridade"),
                ),
                user,
            )
            criadas.append(
                {
                    "id": getattr(resposta, "id", None),
                    "titulo": getattr(resposta, "title", tarefa["titulo"]),
                    "due_date": tarefa.get("due_date"),
                }
            )
        except Exception as e:
            logger.warning(
                f"[NOTA-VOZ] Tarefa '{tarefa.get('titulo')}' não criada "
                f"(nota {nota_id}): {type(e).__name__}: {e}"
            )

    return criadas


# ====================================================================
# PROGRESSO DA TAREFA
# ====================================================================


async def _progresso(task_id: Optional[str], valor: int, mensagem: str) -> None:
    """Actualiza o TaskLog (e, por consequência, emite o evento).

    O estado vai explicitamente a ``PROCESSING``. Sem isso a tarefa ficava
    em ``pending`` durante toda a corrida e ``resolve_event_type`` traduzia
    cada actualização num ``task_started`` — o cliente recebia meia dúzia de
    "começou" e nenhuma barra de progresso a andar.
    """
    if not task_id:
        return
    try:
        from models.task_log import TaskStatus
        from services.task_log_service import TaskLogService

        await TaskLogService.update_task(
            task_id,
            status=TaskStatus.PROCESSING,
            progress=valor,
            progress_message=mensagem,
        )
    except Exception as e:  # pragma: no cover — observabilidade nunca trava
        logger.debug(f"[NOTA-VOZ] Progresso não actualizado: {e}")


async def _concluir(task_id: Optional[str], resultado: dict) -> None:
    if not task_id:
        return
    try:
        from services.task_log_service import TaskLogService

        await TaskLogService.mark_completed(task_id, result_data=resultado)
    except Exception as e:  # pragma: no cover
        logger.warning(f"[NOTA-VOZ] Tarefa {task_id} não marcada como concluída: {e}")


async def _falhar(task_id: Optional[str], motivo: str) -> None:
    if not task_id:
        return
    try:
        from services.task_log_service import TaskLogService

        await TaskLogService.mark_failed(task_id, motivo)
    except Exception as e:  # pragma: no cover
        logger.warning(f"[NOTA-VOZ] Tarefa {task_id} não marcada como falhada: {e}")


# ====================================================================
# CONTEXTO DO PROCESSO
# ====================================================================


async def montar_contexto(process_id: str, user: dict) -> dict:
    """Contexto textual que ajuda o modelo a resolver datas e nomes."""
    contexto = {
        "consultor_name": user.get("name"),
        "hoje": datetime.now(timezone.utc).strftime("%Y-%m-%d (%A)"),
    }
    try:
        processo = await db.processes.find_one(
            {"id": process_id},
            {"_id": 0, "client_name": 1, "process_ref": 1},
        )
        if processo:
            contexto["client_name"] = processo.get("client_name")
            contexto["process_ref"] = processo.get("process_ref")
    except Exception as e:  # pragma: no cover
        logger.debug(f"[NOTA-VOZ] Contexto do processo indisponível: {e}")
    return contexto


# ====================================================================
# CORRIDA PRINCIPAL
# ====================================================================


async def run_voice_note_pipeline(
    *,
    nota_id: str,
    process_id: str,
    user: dict,
    audio: bytes,
    filename: str = "",
    mime_type: str = "",
    task_id: Optional[str] = None,
) -> dict:
    """Executa a nota de voz do princípio ao fim.

    Corre em background (``spawn_background_task``): a resposta do endpoint
    de upload não espera por ela.

    Returns:
        ``{"success", "activity_id", "task_ids", "tarefas", "aviso"}`` — o
        mesmo dicionário que segue no ``result_data`` do evento terminal.
    """
    from services.voice_extraction import extrair_accoes
    from services.voice_transcription import ErroDeTranscricao, transcrever_audio

    # ── Passo A: transcrever ──────────────────────────────────────────
    await _progresso(task_id, 15, "A transcrever o áudio...")
    try:
        transcricao = await transcrever_audio(
            audio, filename=filename, mime_type=mime_type
        )
    except ErroDeTranscricao as e:
        motivo = f"Não foi possível transcrever o áudio: {e}"
        logger.warning(f"[NOTA-VOZ] {motivo} (nota {nota_id})")
        await _actualizar_nota(nota_id, {"status": ESTADO_FALHADO, "error": str(e)})
        await _falhar(task_id, motivo)
        return {"success": False, "reason": "transcricao_falhou", "erro": str(e)}
    except Exception as e:  # defesa: um provider pode levantar o que quiser
        motivo = f"Erro inesperado na transcrição: {type(e).__name__}: {e}"
        logger.error(f"[NOTA-VOZ] {motivo} (nota {nota_id})", exc_info=True)
        await _actualizar_nota(nota_id, {"status": ESTADO_FALHADO, "error": str(e)})
        await _falhar(task_id, motivo)
        return {"success": False, "reason": "transcricao_falhou", "erro": str(e)}

    await _actualizar_nota(
        nota_id,
        {"transcription": transcricao.texto, "asr_provider": transcricao.provider},
    )

    # ── Passo B: extrair resumo e tarefas ─────────────────────────────
    await _progresso(task_id, 50, "A analisar com Inteligência Artificial...")
    aviso = None
    try:
        extraccao = await extrair_accoes(
            transcricao.texto, contexto=await montar_contexto(process_id, user)
        )
    except Exception as e:
        # Degradação graciosa: a transcrição não se perde. O resumo passa a
        # ser o texto transcrito e não se criam tarefas.
        aviso = f"A análise por IA falhou ({type(e).__name__}); ficou a transcrição."
        logger.warning(f"[NOTA-VOZ] {aviso} (nota {nota_id}): {e}")
        extraccao = {"resumo_timeline": transcricao.texto, "tarefas_extraidas": []}

    resumo = (extraccao.get("resumo_timeline") or "").strip() or transcricao.texto

    # ── Passo C: resumo na timeline ───────────────────────────────────
    await _progresso(task_id, 75, "A registar no histórico do processo...")
    activity_id = await registar_resumo_na_timeline(
        process_id=process_id, user=user, resumo=resumo, nota_id=nota_id
    )

    # ── Passo D: tarefas ──────────────────────────────────────────────
    tarefas_extraidas = extraccao.get("tarefas_extraidas") or []
    if tarefas_extraidas:
        await _progresso(task_id, 90, "A agendar as tarefas identificadas...")
    criadas = await criar_tarefas(
        process_id=process_id,
        user=user,
        tarefas=tarefas_extraidas,
        nota_id=nota_id,
    )

    resultado = {
        "success": True,
        "voice_note_id": nota_id,
        "process_id": process_id,
        "activity_id": activity_id,
        "task_ids": [t["id"] for t in criadas if t.get("id")],
        "tarefas": criadas,
        "resumo": resumo,
        "aviso": aviso,
    }

    await _actualizar_nota(
        nota_id,
        {
            "status": ESTADO_PARCIAL if aviso else ESTADO_CONCLUIDO,
            "activity_id": activity_id,
            "task_ids": resultado["task_ids"],
            "summary": resumo,
            "warning": aviso,
        },
    )
    await _concluir(task_id, resultado)

    logger.info(
        f"[NOTA-VOZ] Nota {nota_id} concluída no processo {process_id}: "
        f"{len(criadas)} tarefa(s), atividade {activity_id}"
        + (f" — AVISO: {aviso}" if aviso else "")
    )
    return resultado

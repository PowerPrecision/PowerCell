"""
Orquestração do Motor de Simulação Financeira (hook pós-indexação).

ÉPICO "Motor de Simulação Financeira" (Eixos 1 e 3): quando um consultor
valida a indexação de um processo de Crédito Habitação, este módulo:

    1. detecta os documentos financeiros indexados (IRS, recibos de
       vencimento, notas de liquidação);
    2. garante que têm dados extraídos — reaproveitando o OCR já guardado
       em ``document_metadata.extracted_data`` e, só quando falta, voltando
       a correr a extracção (``ai_document.analyze_document_from_base64``,
       o mesmo motor de ``document_ai_analyze``/``document_auto_categorize``);
    3. consolida rendimentos com o ``ClientDataAggregator`` e persiste-os
       no ``financial_data`` do processo;
    4. chama ``financial_simulator`` (DSTI + Euribor + 3 cenários);
    5. gera o PDF (``financial_proposal_pdf``), guarda-o no S3
       (``s3_storage``) e anexa-o ao separador Documentos do processo com
       o tipo **Proposta Financeira**.

PORQUÊ UM MÓDULO SEPARADO:
    ``financial_simulator`` é puro (testável sem Mongo) e
    ``financial_proposal_pdf`` só desenha. Todo o I/O e todos os efeitos
    colaterais concentram-se aqui, atrás de uma única fronteira.

NUNCA ENCRAVA O PROCESSO:
    O motor corre em *fire-and-forget* (``asyncio.create_task``) — a
    resposta do endpoint de indexação não espera por ele. Qualquer falha
    (IRS ilegível, OCR sem rendimentos, S3 em baixo, Euribor inacessível)
    termina em ``flag_manual_review``: tarefa marcada como falhada com
    motivo legível, aviso na timeline do processo e estado
    ``needs_manual_review`` gravado em ``process.financial_simulation``.
    A indexação em si nunca é revertida nem bloqueada.
"""
from __future__ import annotations

import asyncio
import io
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from database import db
from services.document_ai_analyze import DOCUMENT_TYPE_FOLDERS
from services.document_constants import DEFAULT_CLIENT_NAME, MIME_TYPE_PDF

logger = logging.getLogger(__name__)


# ====================================================================
# TAXONOMIA DE DOCUMENTOS FINANCEIROS
# (derivada do mapa canónico da análise IA — sem lista paralela)
# ====================================================================

# Pasta S3 dos documentos financeiros, tal como a IA a classifica.
FINANCIAL_FOLDER = DOCUMENT_TYPE_FOLDERS["irs"]

# Tipos de documento que a IA arruma na pasta financeira
# ({"irs", "declaracao_irs", "nota_liquidacao", "recibo_vencimento"}).
FINANCIAL_DOC_TYPES = frozenset(
    doc_type
    for doc_type, folder in DOCUMENT_TYPE_FOLDERS.items()
    if folder == FINANCIAL_FOLDER and doc_type != "default"
)

# Categorias (pasta) aceites como financeiras nos metadados já existentes.
# "Fiscal"/"Financiamento" aparecem em documentos categorizados por
# versões anteriores do categorizador (ver `_OCR_CATEGORIES`).
FINANCIAL_CATEGORIES = frozenset(
    {FINANCIAL_FOLDER.lower(), "financeiro", "fiscal", "financiamento"}
)

# Tipo financeiro → tipo entendido pelo ClientDataAggregator.
AGGREGATOR_DOC_TYPES = {
    "irs": "irs",
    "declaracao_irs": "irs",
    "nota_liquidacao": "irs",
    "recibo_vencimento": "recibo_vencimento",
}

# Categoria/subcategoria com que a proposta é anexada aos Documentos.
PROPOSAL_CATEGORY = DOCUMENT_TYPE_FOLDERS["proposta"]  # "Propostas"
PROPOSAL_SUBCATEGORY = "Proposta Financeira"
PROPOSAL_DOC_TYPE = "proposta_financeira"

# Estados persistidos em `process.financial_simulation.status`
STATUS_RUNNING = "running"
STATUS_COMPLETED = "completed"
STATUS_NEEDS_REVIEW = "needs_manual_review"

# Motivos de não-disparo (contrato com a resposta do mark-indexed)
SKIP_DISABLED = "motor_desativado"
SKIP_NOT_CREDIT = "processo_nao_credito"
SKIP_NO_DOCUMENTS = "sem_documentos_financeiros"

# Mensagens de revisão manual (uma fonte de verdade para log/timeline/UI)
REVIEW_MESSAGES = {
    "sem_rendimento": (
        "Não foi possível apurar rendimentos a partir dos documentos "
        "financeiros indexados (IRS/recibos ilegíveis ou sem valores). "
        "É necessária revisão manual dos dados financeiros."
    ),
    "sem_capital": (
        "Não foi possível determinar o montante ou o prazo do financiamento. "
        "Preencher os dados de crédito do processo e repetir a simulação."
    ),
    "extracao_falhou": (
        "A extracção automática dos documentos financeiros falhou. "
        "É necessária revisão manual dos dados financeiros."
    ),
    "pdf_falhou": (
        "Os cenários foram calculados mas a proposta em PDF não pôde ser "
        "gerada ou arquivada. É necessária intervenção manual."
    ),
    "erro_inesperado": (
        "O motor de simulação financeira terminou com erro inesperado. "
        "É necessária revisão manual do processo."
    ),
}

# Referências fortes às tasks em curso (impede o GC de as cancelar).
_BACKGROUND_TASKS: set = set()


# ====================================================================
# DETECÇÃO
# ====================================================================


def _normalize_doc_token(value: Any) -> str:
    """Normaliza subcategoria/nome de ficheiro para comparar com os tipos."""
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_")


def classify_financial_document(doc: dict) -> Optional[str]:
    """Tipo financeiro canónico de um registo de ``document_metadata``.

    Ordem de decisão: subcategoria IA (o tipo detectado, ex.: "Recibo
    Vencimento") → categoria/pasta financeira → palavras do nome do
    ficheiro. Devolve ``None`` quando o documento não é financeiro.
    """
    if not isinstance(doc, dict):
        return None

    subcategory = _normalize_doc_token(doc.get("ai_subcategory"))
    if subcategory in FINANCIAL_DOC_TYPES:
        return subcategory

    filename_token = _normalize_doc_token(doc.get("filename"))
    category = _normalize_doc_token(doc.get("ai_category"))
    is_financial_category = category in FINANCIAL_CATEGORIES

    for doc_type in sorted(FINANCIAL_DOC_TYPES, key=len, reverse=True):
        if doc_type in filename_token:
            return doc_type

    if is_financial_category:
        # Pasta financeira sem tipo reconhecível: trata-se como IRS
        # (o extractor de IRS é o mais abrangente para rendimentos).
        return "irs"

    return None


async def collect_financial_documents(process_id: str) -> list[dict]:
    """Documentos financeiros indexados de um processo (mais recentes 1º)."""
    docs = await db.document_metadata.find(
        {"process_id": process_id},
        {"_id": 0, "extracted_text": 0},
    ).to_list(500)

    financial = []
    for doc in docs:
        doc_type = classify_financial_document(doc)
        if not doc_type:
            continue
        financial.append({**doc, "financial_doc_type": doc_type})
    return financial


def decide_trigger(
    process: dict,
    financial_documents: list,
    *,
    enabled: bool,
) -> dict:
    """Decide se o motor deve disparar para este processo.

    Returns:
        ``{"triggered": bool, "reason": str|None, "documents": int}``.
        ``reason`` só está preenchido quando **não** dispara.
    """
    if not enabled:
        return {"triggered": False, "reason": SKIP_DISABLED, "documents": 0}

    from services.finance_helpers import _is_credito

    if not _is_credito(process.get("process_type") or ""):
        return {"triggered": False, "reason": SKIP_NOT_CREDIT, "documents": 0}

    count = len(financial_documents or [])
    if count == 0:
        return {"triggered": False, "reason": SKIP_NO_DOCUMENTS, "documents": 0}

    return {"triggered": True, "reason": None, "documents": count}


# ====================================================================
# EXTRACÇÃO E CONSOLIDAÇÃO DE RENDIMENTOS
# ====================================================================


async def _extract_document_data(doc: dict) -> Optional[dict]:
    """Dados extraídos de um documento (cache do OCR ou nova extracção).

    Reaproveita ``extracted_data`` guardado pela categorização automática.
    Só quando não existe é que o ficheiro é descarregado do S3 e reanalisado
    — evita gastar chamadas de IA por cada validação de indexação.
    """
    cached = doc.get("extracted_data")
    if isinstance(cached, dict) and cached:
        return cached

    s3_path = doc.get("s3_path")
    if not s3_path:
        return None

    from services.s3_storage import s3_service

    if not s3_service.is_configured():
        logger.warning("[MOTOR-FIN] S3 não configurado — extracção impossível")
        return None

    try:
        loop = asyncio.get_event_loop()
        content = await loop.run_in_executor(
            None, lambda: s3_service.get_file_content(s3_path)
        )
        if not content:
            return None

        import base64

        from services.ai_document import analyze_document_from_base64

        filename = str(doc.get("filename") or "")
        mime_type = (
            MIME_TYPE_PDF if filename.lower().endswith(".pdf") else "image/jpeg"
        )
        aggregator_type = AGGREGATOR_DOC_TYPES.get(
            doc.get("financial_doc_type") or "", "irs"
        )
        result = await analyze_document_from_base64(
            base64.b64encode(content).decode("utf-8"), mime_type, aggregator_type
        )
        extracted = (result or {}).get("extracted_data")
        if not extracted:
            logger.info(
                f"[MOTOR-FIN] Extracção sem dados para '{filename}': "
                f"{(result or {}).get('error') or 'sem extracted_data'}"
            )
            return None

        # Persistir para que a próxima corrida não repita a análise
        try:
            await db.document_metadata.update_one(
                {"id": doc.get("id")},
                {
                    "$set": {
                        "extracted_data": extracted,
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    }
                },
            )
        except Exception as persist_err:  # pragma: no cover
            logger.debug(f"[MOTOR-FIN] extracted_data não persistido: {persist_err}")

        return extracted
    except Exception as e:
        logger.warning(
            f"[MOTOR-FIN] Falha ao extrair '{doc.get('filename')}': "
            f"{type(e).__name__}: {e}"
        )
        return None


async def consolidate_financial_data(
    process: dict,
    financial_documents: list,
) -> dict:
    """Consolida os rendimentos dos documentos financeiros do processo.

    Returns:
        ``{"financial_data": dict, "processed": [filenames],
        "failed": [filenames]}``. ``financial_data`` vem vazio quando
        nenhum documento produziu dados legíveis.
    """
    from services.documents.data_aggregator import ClientDataAggregator

    aggregator = ClientDataAggregator(
        process.get("id") or "",
        process.get("client_name") or DEFAULT_CLIENT_NAME,
    )
    processed: list[str] = []
    failed: list[str] = []

    for doc in financial_documents:
        filename = str(doc.get("filename") or doc.get("s3_path") or "documento")
        extracted = await _extract_document_data(doc)
        if not extracted:
            failed.append(filename)
            continue
        aggregator_type = AGGREGATOR_DOC_TYPES.get(
            doc.get("financial_doc_type") or "", "irs"
        )
        try:
            aggregator.add_extraction(aggregator_type, extracted, filename)
            processed.append(filename)
        except Exception as e:  # pragma: no cover — extracção malformada
            logger.warning(f"[MOTOR-FIN] Agregação falhou para '{filename}': {e}")
            failed.append(filename)

    consolidated = aggregator.get_consolidated_data() if processed else {}
    return {
        "financial_data": consolidated.get("financial_data") or {},
        "processed": processed,
        "failed": failed,
    }


async def persist_financial_data(process_id: str, financial_data: dict) -> None:
    """Grava os rendimentos consolidados em ``processes.financial_data``.

    Escrita por campo (dot-notation) para não apagar dados introduzidos
    manualmente pelo consultor que o motor não calcula.
    """
    if not financial_data:
        return
    update = {
        f"financial_data.{key}": value
        for key, value in financial_data.items()
        if value is not None
    }
    if not update:
        return
    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    try:
        await db.processes.update_one({"id": process_id}, {"$set": update})
    except Exception as e:  # pragma: no cover
        logger.warning(f"[MOTOR-FIN] financial_data não persistido: {e}")


# ====================================================================
# ARQUIVO DA PROPOSTA (S3 + separador Documentos)
# ====================================================================


async def archive_proposal(
    process: dict,
    pdf_bytes: bytes,
    filename: str,
) -> dict:
    """Guarda a proposta no S3 e anexa-a aos Documentos do processo.

    Returns:
        ``{"s3_path": str, "document_id": str}``.

    Raises:
        RuntimeError: S3 indisponível ou upload falhado — o chamador
            converte em pedido de revisão manual.
    """
    from services.document_process_resolve import extract_second_client_name
    from services.s3_storage import s3_service

    if not s3_service.is_configured():
        raise RuntimeError("S3 não configurado — proposta não arquivada")

    process_id = process.get("id") or ""
    client_name = process.get("client_name") or DEFAULT_CLIENT_NAME
    second_client_name = extract_second_client_name(process)

    loop = asyncio.get_event_loop()
    s3_path = await loop.run_in_executor(
        None,
        lambda: s3_service.upload_file(
            io.BytesIO(pdf_bytes),
            process_id,
            client_name,
            PROPOSAL_CATEGORY,
            filename,
            MIME_TYPE_PDF,
            second_client_name,
            process.get("s3_folder"),
        ),
    )
    if not s3_path:
        raise RuntimeError("Upload da proposta para o S3 falhou")

    now = datetime.now(timezone.utc).isoformat()
    document_id = str(uuid.uuid4())
    await db.document_metadata.insert_one(
        {
            "id": document_id,
            "process_id": process_id,
            "client_name": client_name,
            "s3_path": s3_path,
            "filename": filename,
            "ai_category": PROPOSAL_CATEGORY,
            "ai_subcategory": PROPOSAL_SUBCATEGORY,
            "document_type": PROPOSAL_DOC_TYPE,
            "file_size": len(pdf_bytes),
            "mime_type": MIME_TYPE_PDF,
            "is_categorized": True,
            "generated_by": "financial_simulator",
            "categorized_at": now,
            "created_at": now,
            "updated_at": now,
        }
    )
    return {"s3_path": s3_path, "document_id": document_id}


# ====================================================================
# REGISTO NO PROCESSO (sucesso e revisão manual)
# ====================================================================


async def _add_system_activity(
    process_id: str,
    action: str,
    details: str,
    *,
    user: Optional[dict] = None,
) -> None:
    """Regista uma atividade de sistema na timeline do processo."""
    try:
        await db.processes.update_one(
            {"id": process_id},
            {
                "$push": {
                    "activities": {
                        "id": str(uuid.uuid4()),
                        "user_id": (user or {}).get("id") or "system",
                        "user_name": "Motor Financeiro",
                        "action": action,
                        "details": details,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "type": "system",
                    }
                }
            },
        )
    except Exception as e:  # pragma: no cover
        logger.warning(f"[MOTOR-FIN] Atividade não registada em {process_id}: {e}")


async def _set_simulation_state(process_id: str, state: dict) -> None:
    """Persiste ``process.financial_simulation`` (estado do motor)."""
    try:
        await db.processes.update_one(
            {"id": process_id},
            {"$set": {"financial_simulation": state}},
        )
    except Exception as e:  # pragma: no cover
        logger.warning(f"[MOTOR-FIN] Estado não persistido em {process_id}: {e}")


async def flag_manual_review(
    process_id: str,
    *,
    reason: str,
    task_id: Optional[str],
    user: Optional[dict] = None,
    details: Optional[str] = None,
    missing: Optional[list] = None,
) -> None:
    """Marca o processo como "requer revisão manual" sem o bloquear.

    Três registos complementares, porque cada um serve um público:
    ``financial_simulation`` (API/UI), atividade de sistema (timeline do
    consultor) e tarefa falhada (monitor de tarefas em background).
    """
    message = details or REVIEW_MESSAGES.get(reason) or REVIEW_MESSAGES[
        "erro_inesperado"
    ]
    now = datetime.now(timezone.utc).isoformat()

    await _set_simulation_state(
        process_id,
        {
            "status": STATUS_NEEDS_REVIEW,
            "reason": reason,
            "message": message,
            "missing": missing or [],
            "task_id": task_id,
            "updated_at": now,
        },
    )
    await _add_system_activity(
        process_id,
        "SIMULACAO_FINANCEIRA_REVISAO_MANUAL",
        message,
        user=user,
    )

    if task_id:
        try:
            from models.task_log import TaskStatus
            from services.task_log_service import TaskLogService

            await TaskLogService.update_task(
                task_id,
                status=TaskStatus.FAILED,
                progress=100,
                progress_message="Requer revisão manual",
                error_message=message,
            )
        except Exception as e:  # pragma: no cover
            logger.warning(f"[MOTOR-FIN] Tarefa {task_id} não actualizada: {e}")

    logger.warning(
        f"[MOTOR-FIN] Processo {process_id} marcado para revisão manual "
        f"({reason}): {message}"
    )


def summarize_scenarios(simulation: dict) -> list[dict]:
    """Resumo compacto dos cenários para guardar no processo/API."""
    return [
        {
            "key": cenario.get("key"),
            "label": cenario.get("label"),
            "taxa_pct": cenario.get("taxa_inicial_pct"),
            "prestacao_mensal": cenario.get("prestacao_total_mensal"),
            "taeg_pct": cenario.get("taeg_pct"),
            "dsti_pct": (cenario.get("dsti") or {}).get("dsti_pct"),
            "dentro_limite": (cenario.get("dsti") or {}).get("dentro_limite"),
        }
        for cenario in (simulation.get("cenarios") or [])
    ]


# ====================================================================
# EXECUÇÃO DO MOTOR
# ====================================================================


async def _update_task(task_id: Optional[str], **kwargs) -> None:
    """Actualiza a tarefa de background (silencioso se indisponível)."""
    if not task_id:
        return
    try:
        from services.task_log_service import TaskLogService

        await TaskLogService.update_task(task_id, **kwargs)
    except Exception as e:  # pragma: no cover
        logger.debug(f"[MOTOR-FIN] Tarefa {task_id} não actualizada: {e}")


async def run_financial_engine(
    process_id: str,
    *,
    user: Optional[dict] = None,
    task_id: Optional[str] = None,
) -> dict:
    """Corre o motor de ponta a ponta para um processo.

    Pensado para ser chamado em background. **Nunca levanta excepção**:
    qualquer falha resulta em ``{"success": False, "reason": ...}`` e no
    respectivo pedido de revisão manual.
    """
    from models.task_log import TaskStatus

    try:
        process = await db.processes.find_one(
            {"id": process_id, "is_deleted": {"$ne": True}}, {"_id": 0}
        )
        if not process:
            logger.warning(f"[MOTOR-FIN] Processo {process_id} não encontrado")
            await _update_task(
                task_id,
                status=TaskStatus.FAILED,
                error_message="Processo não encontrado",
            )
            return {"success": False, "reason": "processo_inexistente"}

        await _set_simulation_state(
            process_id,
            {
                "status": STATUS_RUNNING,
                "task_id": task_id,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        await _update_task(
            task_id,
            status=TaskStatus.PROCESSING,
            progress=10,
            progress_message="A extrair dados dos documentos financeiros...",
        )

        # 1) Extracção + consolidação dos rendimentos
        financial_documents = await collect_financial_documents(process_id)
        extraction = await consolidate_financial_data(process, financial_documents)

        if not extraction["processed"]:
            await flag_manual_review(
                process_id,
                reason="extracao_falhou",
                task_id=task_id,
                user=user,
                details=(
                    f"{REVIEW_MESSAGES['extracao_falhou']} Documentos sem "
                    f"leitura: {', '.join(extraction['failed']) or 'nenhum'}."
                ),
            )
            return {"success": False, "reason": "extracao_falhou"}

        await persist_financial_data(process_id, extraction["financial_data"])
        # Recarregar para simular com os rendimentos já consolidados
        process = await db.processes.find_one({"id": process_id}, {"_id": 0}) or process

        # 2) Simulação (DSTI + Euribor + 3 cenários)
        await _update_task(
            task_id,
            progress=45,
            progress_message="A calcular cenários de crédito...",
        )
        from services.financial_simulator import run_financial_simulation

        simulation = await run_financial_simulation(process)
        if not simulation.get("success"):
            await flag_manual_review(
                process_id,
                reason=simulation.get("reason") or "sem_rendimento",
                task_id=task_id,
                user=user,
                missing=simulation.get("missing"),
            )
            return {"success": False, "reason": simulation.get("reason")}

        # 3) PDF + arquivo
        await _update_task(
            task_id,
            progress=75,
            progress_message="A gerar a proposta em PDF...",
        )
        try:
            from services.financial_proposal_pdf import (
                generate_financial_proposal_pdf,
            )

            pdf_bytes, filename = await generate_financial_proposal_pdf(
                process, simulation
            )
            archived = await archive_proposal(process, pdf_bytes, filename)
        except Exception as pdf_err:
            logger.error(
                f"[MOTOR-FIN] Proposta não gerada/arquivada para {process_id}: "
                f"{type(pdf_err).__name__}: {pdf_err}",
                exc_info=True,
            )
            await flag_manual_review(
                process_id,
                reason="pdf_falhou",
                task_id=task_id,
                user=user,
            )
            return {"success": False, "reason": "pdf_falhou"}

        # 4) Estado final + timeline
        now = datetime.now(timezone.utc).isoformat()
        resumo = summarize_scenarios(simulation)
        await _set_simulation_state(
            process_id,
            {
                "status": STATUS_COMPLETED,
                "task_id": task_id,
                "document_id": archived["document_id"],
                "s3_path": archived["s3_path"],
                "filename": filename,
                "cenarios": resumo,
                "euribor": simulation.get("taxa_indexante"),
                "avisos": simulation.get("avisos") or [],
                "documentos_lidos": extraction["processed"],
                "documentos_sem_leitura": extraction["failed"],
                "generated_at": now,
                "updated_at": now,
            },
        )
        melhor = min(
            resumo, key=lambda c: c.get("prestacao_mensal") or float("inf")
        ) if resumo else {}
        await _add_system_activity(
            process_id,
            "SIMULACAO_FINANCEIRA_GERADA",
            (
                f"Proposta financeira gerada automaticamente com 3 cenários "
                f"({', '.join(c['label'] for c in resumo)}). "
                f"Prestação mais baixa: {melhor.get('label') or 'N/D'} — "
                f"{melhor.get('prestacao_mensal') or 0:.2f} €/mês."
            ),
            user=user,
        )
        if extraction["failed"]:
            await _add_system_activity(
                process_id,
                "SIMULACAO_FINANCEIRA_AVISO",
                (
                    "Documentos financeiros sem leitura automática (não "
                    f"entraram no cálculo): {', '.join(extraction['failed'])}. "
                    "Confirmar manualmente."
                ),
                user=user,
            )

        await _update_task(
            task_id,
            status=TaskStatus.COMPLETED,
            progress=100,
            progress_message="Proposta financeira pronta",
            result_data={
                "process_id": process_id,
                "document_id": archived["document_id"],
                "filename": filename,
                "cenarios": resumo,
            },
        )
        logger.info(
            f"[MOTOR-FIN] Proposta gerada para o processo {process_id}: "
            f"{filename} ({len(resumo)} cenários)"
        )
        return {
            "success": True,
            "process_id": process_id,
            "document_id": archived["document_id"],
            "filename": filename,
            "cenarios": resumo,
        }

    except Exception as e:  # pragma: no cover — rede de segurança final
        logger.error(
            f"[MOTOR-FIN] Erro inesperado no processo {process_id}: "
            f"{type(e).__name__}: {e}",
            exc_info=True,
        )
        try:
            await flag_manual_review(
                process_id,
                reason="erro_inesperado",
                task_id=task_id,
                user=user,
            )
        except Exception:
            pass
        return {"success": False, "reason": "erro_inesperado"}


# ====================================================================
# HOOK DE INDEXAÇÃO (Eixo 1)
# ====================================================================


def _schedule(coro) -> None:
    """Agenda a corrida em background mantendo referência forte à task."""
    task = asyncio.create_task(coro)
    _BACKGROUND_TASKS.add(task)
    task.add_done_callback(_BACKGROUND_TASKS.discard)


async def trigger_financial_engine_after_indexing(
    process: dict,
    user: dict,
) -> dict:
    """Dispara o motor quando a indexação de um processo é validada.

    Chamado pelos efeitos colaterais do ``mark-indexed``/``set-indexed``.
    Só a decisão + o registo da tarefa são aguardados (milissegundos); o
    trabalho pesado corre em *fire-and-forget*.

    Returns:
        ``{"triggered": bool, "reason": str|None, "task_id": str|None,
        "documents": int}`` — devolvido na resposta do endpoint para que o
        frontend mostre o toast "Motor financeiro a processar cenários...".
    """
    process_id = process.get("id") or ""
    try:
        from services.system_config import get_system_config

        config = await get_system_config(
            process.get("company_id") or process.get("company") or "default"
        )
        enabled = bool(config.financial_simulator.enabled)
    except Exception as e:  # pragma: no cover — config indisponível
        logger.warning(f"[MOTOR-FIN] Configuração indisponível: {e}")
        enabled = False

    try:
        financial_documents = (
            await collect_financial_documents(process_id) if enabled else []
        )
    except Exception as e:  # pragma: no cover
        logger.warning(f"[MOTOR-FIN] Documentos não consultados: {e}")
        financial_documents = []

    decision = decide_trigger(process, financial_documents, enabled=enabled)
    if not decision["triggered"]:
        logger.info(
            f"[MOTOR-FIN] Motor não disparado para {process_id}: "
            f"{decision['reason']}"
        )
        return {**decision, "task_id": None}

    task_id = None
    try:
        from models.task_log import TaskType
        from services.task_log_service import TaskLogService

        task = await TaskLogService.create_task(
            TaskType.PDF_GEN,
            user.get("id") or "system",
            "Motor financeiro — cenários de crédito",
            description=(
                "Extracção de rendimentos, cálculo de DSTI e geração da "
                "proposta com 3 cenários de Crédito Habitação."
            ),
            process_id=process_id,
            metadata={
                "engine": "financial_simulator",
                "financial_documents": decision["documents"],
            },
        )
        task_id = task.task_id
    except Exception as e:  # pragma: no cover — TaskLog indisponível
        logger.warning(
            f"[MOTOR-FIN] Tarefa de background não registada para "
            f"{process_id}: {e}"
        )

    _schedule(run_financial_engine(process_id, user=user, task_id=task_id))
    logger.info(
        f"[MOTOR-FIN] Motor disparado para o processo {process_id} "
        f"({decision['documents']} documentos financeiros, tarefa {task_id})"
    )
    return {**decision, "task_id": task_id}

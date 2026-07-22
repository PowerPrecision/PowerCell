"""Async document analysis API + background worker.

Extraído de `routes/ai.py`. Prefer `ai_api_*` — do **not** overwrite
`ai_document.py` / `task_log_service.py`.
"""
from __future__ import annotations

import logging

from fastapi import BackgroundTasks, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from models.task_log import TaskType
from services.ai_document import (
    analyze_document_from_url,
    map_cc_to_personal_data,
    map_recibo_to_financial_data,
    map_irs_to_financial_data,
)
from services.ai_api_helpers import VALID_DOCUMENT_TYPES
from services.task_log_service import task_log_service

logger = logging.getLogger(__name__)


class AsyncAnalyzeDocumentRequest(BaseModel):
    """Request for async document analysis."""
    process_id: str
    document_url: str
    document_type: str
    auto_apply: bool = False


async def analyze_document_background(
    task_id: str,
    process_id: str,
    document_url: str,
    document_type: str,
    auto_apply: bool,
    user_id: str,
):
    """Background worker for async document analysis (after 202)."""
    from database import db

    try:
        await task_log_service.mark_processing(task_id)
        await task_log_service.update_progress(task_id, 10, "A iniciar análise...")

        result = await analyze_document_from_url(document_url, document_type)

        if not result.get("success", False):
            await task_log_service.mark_failed(
                task_id,
                result.get("error", "Erro ao analisar documento"),
            )
            return

        await task_log_service.update_progress(task_id, 60, "Análise concluída, a processar dados...")

        extracted_data = result.get("extracted_data", {})
        mapped_data = {}

        if document_type == "cc":
            mapped_data["personal_data"] = map_cc_to_personal_data(extracted_data)
        elif document_type == "recibo_vencimento":
            mapped_data["financial_data"] = map_recibo_to_financial_data(extracted_data)
        elif document_type == "irs":
            mapped_data["financial_data"] = map_irs_to_financial_data(extracted_data)

        await task_log_service.update_progress(task_id, 80, "A guardar resultados...")

        if auto_apply and mapped_data:
            for field, data in mapped_data.items():
                if data:
                    await db.processes.update_one(
                        {"id": process_id},
                        {"$set": {field: data}},
                    )

        await task_log_service.mark_completed(
            task_id,
            result_data={
                "document_type": document_type,
                "extracted_data": extracted_data,
                "mapped_data": mapped_data,
                "auto_applied": auto_apply,
            },
        )

        logger.info(f"[AsyncAI] Análise concluída: {task_id}")

    except Exception as e:
        logger.error(f"[AsyncAI] Erro na análise: {e}")
        await task_log_service.mark_failed(task_id, str(e))


# Keep private alias for callers that used the route-local name
_analyze_document_background = analyze_document_background


async def run_analyze_document_async(
    request: AsyncAnalyzeDocumentRequest,
    background_tasks: BackgroundTasks,
    user: dict,
):
    """Start async document analysis; returns 202 with task_id."""
    if request.document_type not in VALID_DOCUMENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"document_type inválido. Tipos suportados: {VALID_DOCUMENT_TYPES}",
        )

    from database import db
    process = await db.processes.find_one({"id": request.process_id})
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")

    task = await task_log_service.create_task(
        task_type=TaskType.AI_ANALYSIS,
        user_id=user.get("id"),
        title=f"Análise IA: {request.document_type}",
        description=f"A analisar documento do tipo '{request.document_type}' com IA",
        process_id=request.process_id,
        metadata={
            "document_url": (
                request.document_url[:100] + "..."
                if len(request.document_url) > 100
                else request.document_url
            ),
            "document_type": request.document_type,
            "auto_apply": request.auto_apply,
        },
    )

    background_tasks.add_task(
        analyze_document_background,
        task.task_id,
        request.process_id,
        request.document_url,
        request.document_type,
        request.auto_apply,
        user.get("id"),
    )

    return JSONResponse(
        status_code=202,
        content={
            "success": True,
            "message": "Análise iniciada em background",
            "task_id": task.task_id,
            "process_id": request.process_id,
        },
    )

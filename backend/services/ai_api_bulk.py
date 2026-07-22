"""Bulk async AI analysis API + background worker.

Extraído de `routes/ai.py`. Prefer `ai_api_*` — do **not** overwrite
`ai_document_analyzer.py` / `task_log_service.py`.
"""
from __future__ import annotations

import logging
from typing import List

from fastapi import BackgroundTasks, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from models.task_log import TaskType
from services.task_log_service import task_log_service

logger = logging.getLogger(__name__)


class BulkAnalysisRequest(BaseModel):
    """Request for bulk document analysis."""
    process_ids: List[str]
    analysis_type: str  # 'full', 'documents_only', 'financial_only'


async def bulk_analysis_background(
    task_id: str,
    process_ids: List[str],
    analysis_type: str,
    user_id: str,
):
    """Executa análise em massa em background."""
    from services.ai_document_analyzer import analyze_process_documents

    try:
        await task_log_service.mark_processing(task_id)

        total = len(process_ids)
        results = []

        for i, process_id in enumerate(process_ids, 1):
            try:
                progress = int((i / total) * 100)
                await task_log_service.update_progress(
                    task_id,
                    progress,
                    f"A processar {i}/{total} processos...",
                )

                if analysis_type == "documents_only":
                    result = await analyze_process_documents(process_id)
                else:
                    result = {"process_id": process_id, "analyzed": True}

                results.append({
                    "process_id": process_id,
                    "success": True,
                    "result": result,
                })

            except Exception as e:
                results.append({
                    "process_id": process_id,
                    "success": False,
                    "error": str(e),
                })

        successful = sum(1 for r in results if r["success"])
        await task_log_service.mark_completed(
            task_id,
            result_data={
                "total": total,
                "successful": successful,
                "failed": total - successful,
                "results": results,
            },
        )

    except Exception as e:
        logger.error(f"[BulkAnalysis] Erro: {e}")
        await task_log_service.mark_failed(task_id, str(e))


_bulk_analysis_background = bulk_analysis_background


async def run_bulk_analysis_async(
    request: BulkAnalysisRequest,
    background_tasks: BackgroundTasks,
    user: dict,
):
    """Start bulk async analysis; returns 202 with task_id (admin only)."""
    if len(request.process_ids) == 0:
        raise HTTPException(status_code=400, detail="Lista de process_ids vazia")

    if len(request.process_ids) > 50:
        raise HTTPException(status_code=400, detail="Máximo de 50 processos por análise em massa")

    task = await task_log_service.create_task(
        task_type=TaskType.AI_ANALYSIS,
        user_id=user.get("id"),
        title=f"Análise em massa: {len(request.process_ids)} processos",
        description=f"Análise {request.analysis_type} de {len(request.process_ids)} processos",
        metadata={
            "analysis_type": request.analysis_type,
            "process_count": len(request.process_ids),
        },
    )

    background_tasks.add_task(
        bulk_analysis_background,
        task.task_id,
        request.process_ids,
        request.analysis_type,
        user.get("id"),
    )

    return JSONResponse(
        status_code=202,
        content={
            "success": True,
            "message": "Análise em massa iniciada",
            "task_id": task.task_id,
            "process_count": len(request.process_ids),
        },
    )

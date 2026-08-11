"""Enqueue analysis + job status handlers.

Extraído de `routes/async_jobs.py`.
"""
from __future__ import annotations

import logging

from fastapi import HTTPException

from services.async_jobs_api_models import (
    ARQ_AVAILABLE,
    AnalyzeJobRequest,
    AnalyzeJobResponse,
    JobStatusResponse,
    enqueue_document_analysis,
    get_job_status,
)

logger = logging.getLogger(__name__)


async def run_enqueue_analysis(data: AnalyzeJobRequest, user: dict):
    """Enfileirar análise de documento para processamento assíncrono."""
    if not ARQ_AVAILABLE:
        return AnalyzeJobResponse(
            job_id=None,
            status="fallback",
            message="Processamento assíncrono não disponível - usar endpoint síncrono",
            queue_available=False,
        )

    try:
        job_id = await enqueue_document_analysis(
            content_base64=data.content_base64,
            mime_type=data.mime_type,
            document_type=data.document_type,
            process_id=data.process_id,
            client_name=data.client_name,
            filename=data.filename,
            session_id=data.session_id,
        )

        if job_id:
            logger.info(
                f"[JOB] Analysis enqueued: job_id={job_id}, file={data.filename}"
            )
            return AnalyzeJobResponse(
                job_id=job_id,
                status="queued",
                message=(
                    f"Análise enfileirada com sucesso. "
                    f"Use GET /jobs/{job_id} para verificar status."
                ),
                queue_available=True,
            )

        return AnalyzeJobResponse(
            job_id=None,
            status="error",
            message="Falha ao enfileirar análise",
            queue_available=True,
        )

    except Exception as e:
        logger.error(f"[JOB] Error enqueueing analysis: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao enfileirar análise: {str(e)}",
        )


async def run_get_job_status(job_id: str, user: dict):
    """Obter status de um job de análise."""
    if not ARQ_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="Serviço de processamento assíncrono não disponível",
        )

    try:
        job_info = await get_job_status(job_id)

        if not job_info:
            raise HTTPException(
                status_code=404,
                detail=f"Job não encontrado: {job_id}",
            )

        return JobStatusResponse(
            job_id=job_info.get("job_id", job_id),
            status=job_info.get("status", "unknown"),
            result=job_info.get("result"),
            error=(
                str(job_info.get("exc_info"))
                if job_info.get("exc_info")
                else None
            ),
            start_time=(
                str(job_info.get("start_time"))
                if job_info.get("start_time")
                else None
            ),
            finish_time=(
                str(job_info.get("finish_time"))
                if job_info.get("finish_time")
                else None
            ),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[JOB] Error getting job status: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao obter status do job: {str(e)}",
        )

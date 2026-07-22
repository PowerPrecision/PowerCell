"""
====================================================================
ASYNC JOB ROUTES — thin FastAPI stubs
====================================================================
Logic in services/async_jobs_api_*.py.
Preserve rate limits on stubs. Keep static paths (/health, /session/*,
/analyze) before /{job_id}.
====================================================================
"""
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile

from middleware.rate_limit import limiter
from services.auth import get_current_user
from services.async_jobs_api_models import (
    AnalyzeJobRequest,
    AnalyzeJobResponse,
    JobStatusResponse,
    SessionStatusResponse,
)
from services.async_jobs_api_analyze import (
    run_enqueue_analysis,
    run_get_job_status,
)
from services.async_jobs_api_session import (
    run_enqueue_session_analysis,
    run_finish_async_session,
    run_get_session_status,
    run_start_async_session,
)
from services.async_jobs_api_health import run_jobs_health_check

router = APIRouter(prefix="/jobs", tags=["Async Job Management"])


@router.post("/analyze", response_model=AnalyzeJobResponse)
@limiter.limit("100/minute")
async def enqueue_analysis(
    request: Request,
    data: AnalyzeJobRequest,
    user: dict = Depends(get_current_user),
):
    """Enfileirar análise de documento para processamento assíncrono."""
    return await run_enqueue_analysis(data, user)


@router.get("/health")
async def jobs_health_check():
    """Verificar saúde do sistema de jobs assíncronos."""
    return await run_jobs_health_check()


@router.post("/session/start")
async def start_async_session(
    request: Request,
    total_files: int = Form(...),
    client_id: Optional[str] = Form(None),
    client_name: Optional[str] = Form(None),
    user: dict = Depends(get_current_user),
):
    """Iniciar uma sessão de importação assíncrona."""
    return await run_start_async_session(
        total_files, client_id, client_name, user,
    )


@router.post("/session/{session_id}/analyze")
@limiter.limit("60/minute")
async def enqueue_session_analysis(
    request: Request,
    session_id: str,
    file: UploadFile = File(...),
    document_type: str = Form(...),
    process_id: str = Form(...),
    client_name: str = Form(...),
    user: dict = Depends(get_current_user),
):
    """Enfileirar análise de documento numa sessão existente."""
    return await run_enqueue_session_analysis(
        session_id, file, document_type, process_id, client_name, user,
    )


@router.get("/session/{session_id}/status", response_model=SessionStatusResponse)
async def get_session_status(
    session_id: str,
    user: dict = Depends(get_current_user),
):
    """Obter status de uma sessão de importação assíncrona."""
    return await run_get_session_status(session_id, user)


@router.post("/session/{session_id}/finish")
async def finish_async_session(
    session_id: str,
    user: dict = Depends(get_current_user),
):
    """Finalizar sessão de importação assíncrona."""
    return await run_finish_async_session(session_id, user)


@router.get("/{job_id}", response_model=JobStatusResponse)
async def get_job_status_endpoint(
    job_id: str,
    user: dict = Depends(get_current_user),
):
    """Obter status de um job de análise."""
    return await run_get_job_status(job_id, user)

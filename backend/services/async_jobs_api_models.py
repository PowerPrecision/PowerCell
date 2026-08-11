"""Pydantic models + ARQ availability for async job routes.

Extraído de `routes/async_jobs.py`.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from pydantic import BaseModel

logger = logging.getLogger(__name__)

try:
    from worker.tasks import (  # noqa: F401
        enqueue_document_analysis,
        get_job_status,
        ARQ_AVAILABLE,
    )
except ImportError:
    ARQ_AVAILABLE = False
    enqueue_document_analysis = None  # type: ignore[assignment]
    get_job_status = None  # type: ignore[assignment]
    logger.warning("Worker module not available - async processing disabled")


class AnalyzeJobRequest(BaseModel):
    """Request para enfileirar análise de documento."""

    content_base64: str
    mime_type: str
    document_type: str
    process_id: str
    client_name: str
    filename: str
    session_id: Optional[str] = None


class AnalyzeJobResponse(BaseModel):
    """Response após enfileirar análise."""

    job_id: Optional[str]
    status: str
    message: str
    queue_available: bool


class JobStatusResponse(BaseModel):
    """Response com status de um job."""

    job_id: str
    status: str
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    start_time: Optional[str] = None
    finish_time: Optional[str] = None


class SessionStatusResponse(BaseModel):
    """Response com status de uma sessão."""

    session_id: str
    status: str
    total_files: int
    processed: int
    errors: int
    jobs_pending: int
    jobs_completed: int
    message: Optional[str] = None

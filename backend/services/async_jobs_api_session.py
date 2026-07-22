"""Async import session handlers.

Extraído de `routes/async_jobs.py`.
"""
from __future__ import annotations

import base64
from typing import Optional

from fastapi import HTTPException, UploadFile
from fastapi.responses import JSONResponse

from database import db
from services.async_jobs_api_models import (
    ARQ_AVAILABLE,
    SessionStatusResponse,
    enqueue_document_analysis,
)


async def run_start_async_session(
    total_files: int,
    client_id: Optional[str],
    client_name: Optional[str],
    user: dict,
):
    """Iniciar uma sessão de importação assíncrona."""
    from routes.ai_bulk.jobs import create_background_job_db

    details = {
        "async_mode": ARQ_AVAILABLE,
        "client_id": client_id,
        "client_name": client_name,
    }

    session_id = await create_background_job_db(
        job_type="async_import" if ARQ_AVAILABLE else "sync_import",
        user_email=user.get("email"),
        details=details,
        total_files=total_files,
    )

    return {
        "session_id": session_id,
        "async_mode": ARQ_AVAILABLE,
        "message": (
            f"Sessão iniciada. Use POST /jobs/session/{session_id}/analyze "
            f"para enfileirar documentos."
        ),
        "total_files": total_files,
    }


async def run_enqueue_session_analysis(
    session_id: str,
    file: UploadFile,
    document_type: str,
    process_id: str,
    client_name: str,
    user: dict,
):
    """Enfileirar análise de documento numa sessão existente."""
    from services.file_validation import validate_file_content

    filename = file.filename or "documento.pdf"
    content = await file.read()

    try:
        validate_file_content(content, filename)
    except HTTPException as e:
        raise HTTPException(
            status_code=400, detail=f"Ficheiro rejeitado: {e.detail}",
        )

    content_base64 = base64.b64encode(content).decode("utf-8")

    import magic
    mime_type = magic.from_buffer(content, mime=True)

    if not ARQ_AVAILABLE:
        from services.ai_document import analyze_document_from_base64

        result = await analyze_document_from_base64(
            base64_content=content_base64,
            mime_type=mime_type,
            document_type=document_type,
        )

        return JSONResponse(
            status_code=200,
            content={
                "status": "sync_completed",
                "session_id": session_id,
                "filename": filename,
                "result": result,
                "async_mode": False,
            },
        )

    job_id = await enqueue_document_analysis(
        content_base64=content_base64,
        mime_type=mime_type,
        document_type=document_type,
        process_id=process_id,
        client_name=client_name,
        filename=filename,
        session_id=session_id,
    )

    if job_id:
        return JSONResponse(
            status_code=200,
            content={
                "status": "queued",
                "job_id": job_id,
                "session_id": session_id,
                "filename": filename,
                "async_mode": True,
                "message": f"Análise enfileirada. Use GET /jobs/{job_id} para status.",
            },
        )

    raise HTTPException(
        status_code=500,
        detail="Falha ao enfileirar análise",
    )


async def run_get_session_status(session_id: str, user: dict):
    """Obter status de uma sessão de importação assíncrona."""
    job = await db.background_jobs.find_one({"id": session_id}, {"_id": 0})

    if not job:
        raise HTTPException(
            status_code=404,
            detail=f"Sessão não encontrada: {session_id}",
        )

    return SessionStatusResponse(
        session_id=session_id,
        status=job.get("status", "unknown"),
        total_files=job.get("total_files", 0),
        processed=job.get("processed", 0),
        errors=job.get("errors", 0),
        jobs_pending=0,
        jobs_completed=job.get("processed", 0),
        message=job.get("message"),
    )


async def run_finish_async_session(session_id: str, user: dict):
    """Finalizar sessão de importação assíncrona."""
    from routes.ai_bulk.jobs import finish_background_job_db

    await finish_background_job_db(
        session_id,
        success=True,
        message="Sessão finalizada",
    )

    return {
        "session_id": session_id,
        "status": "completed",
        "message": "Sessão finalizada com sucesso",
    }

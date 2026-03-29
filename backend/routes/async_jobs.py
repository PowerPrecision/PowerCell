"""
====================================================================
ASYNC JOB ROUTES - BACKGROUND PROCESSING API
====================================================================
Rotas para gerir tarefas assíncronas de processamento de documentos.

Endpoints:
- POST /jobs/analyze: Enfileirar análise de documento
- GET /jobs/{job_id}: Obter status de um job
- POST /jobs/session/start: Iniciar sessão de importação assíncrona
- POST /jobs/session/{session_id}/analyze: Enfileirar análise em sessão
- GET /jobs/session/{session_id}/status: Status da sessão

Vantagens do processamento assíncrono:
- API responde instantaneamente com job_id
- Processamento acontece em background workers
- Não bloqueia threads do servidor
- Escalável com múltiplos workers
====================================================================
"""
import os
import base64
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel

from database import db
from models.auth import UserRole
from services.auth import get_current_user
from middleware.rate_limit import limiter
from fastapi import Request

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/jobs", tags=["Async Job Management"])

# Verificar se ARQ está disponível
try:
    from worker.tasks import (
        enqueue_document_analysis,
        get_job_status,
        ARQ_AVAILABLE,
    )
except ImportError:
    ARQ_AVAILABLE = False
    logger.warning("Worker module not available - async processing disabled")


# ====================================================================
# MODELOS PYDANTIC
# ====================================================================

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


# ====================================================================
# ENDPOINTS
# ====================================================================

@router.post("/analyze", response_model=AnalyzeJobResponse)
@limiter.limit("100/minute")
async def enqueue_analysis(
    request: Request,
    data: AnalyzeJobRequest,
    user: dict = Depends(get_current_user)
):
    """
    Enfileirar análise de documento para processamento assíncrono.
    
    Este endpoint responde instantaneamente com um job_id.
    O processamento acontece em background pelo worker ARQ.
    
    Se o worker não estiver disponível, retorna status indicando
    que processamento síncrono deve ser usado como fallback.
    """
    if not ARQ_AVAILABLE:
        return AnalyzeJobResponse(
            job_id=None,
            status="fallback",
            message="Processamento assíncrono não disponível - usar endpoint síncrono",
            queue_available=False
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
            logger.info(f"[JOB] Analysis enqueued: job_id={job_id}, file={data.filename}")
            return AnalyzeJobResponse(
                job_id=job_id,
                status="queued",
                message=f"Análise enfileirada com sucesso. Use GET /jobs/{job_id} para verificar status.",
                queue_available=True
            )
        else:
            return AnalyzeJobResponse(
                job_id=None,
                status="error",
                message="Falha ao enfileirar análise",
                queue_available=True
            )
            
    except Exception as e:
        logger.error(f"[JOB] Error enqueueing analysis: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao enfileirar análise: {str(e)}"
        )


@router.get("/{job_id}", response_model=JobStatusResponse)
async def get_job_status_endpoint(
    job_id: str,
    user: dict = Depends(get_current_user)
):
    """
    Obter status de um job de análise.
    
    Status possíveis:
    - pending: Job na fila, aguardando processamento
    - in_progress: Job em execução
    - complete: Job concluído com sucesso
    - failed: Job falhou
    
    O campo 'result' contém os dados extraídos quando o job está completo.
    """
    if not ARQ_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="Serviço de processamento assíncrono não disponível"
        )
    
    try:
        job_info = await get_job_status(job_id)
        
        if not job_info:
            raise HTTPException(
                status_code=404,
                detail=f"Job não encontrado: {job_id}"
            )
        
        return JobStatusResponse(
            job_id=job_info.get("job_id", job_id),
            status=job_info.get("status", "unknown"),
            result=job_info.get("result"),
            error=str(job_info.get("exc_info")) if job_info.get("exc_info") else None,
            start_time=str(job_info.get("start_time")) if job_info.get("start_time") else None,
            finish_time=str(job_info.get("finish_time")) if job_info.get("finish_time") else None,
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[JOB] Error getting job status: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao obter status do job: {str(e)}"
        )


@router.post("/session/start")
async def start_async_session(
    request: Request,
    total_files: int = Form(...),
    client_id: Optional[str] = Form(None),
    client_name: Optional[str] = Form(None),
    user: dict = Depends(get_current_user)
):
    """
    Iniciar uma sessão de importação assíncrona.
    
    Retorna session_id para acompanhar o progresso.
    """
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
        total_files=total_files
    )
    
    return {
        "session_id": session_id,
        "async_mode": ARQ_AVAILABLE,
        "message": f"Sessão iniciada. Use POST /jobs/session/{session_id}/analyze para enfileirar documentos.",
        "total_files": total_files,
    }


@router.post("/session/{session_id}/analyze")
@limiter.limit("60/minute")
async def enqueue_session_analysis(
    request: Request,
    session_id: str,
    file: UploadFile = File(...),
    document_type: str = Form(...),
    process_id: str = Form(...),
    client_name: str = Form(...),
    user: dict = Depends(get_current_user)
):
    """
    Enfileirar análise de documento numa sessão existente.
    
    Se o worker não estiver disponível, executa análise síncrona como fallback.
    """
    from services.file_validation import validate_file_content
    
    filename = file.filename or "documento.pdf"
    
    # Ler e validar ficheiro
    content = await file.read()
    
    try:
        validate_file_content(content, filename)
    except HTTPException as e:
        raise HTTPException(status_code=400, detail=f"Ficheiro rejeitado: {e.detail}")
    
    # Converter para base64
    content_base64 = base64.b64encode(content).decode('utf-8')
    
    # Detectar MIME type
    import magic
    mime_type = magic.from_buffer(content, mime=True)
    
    if not ARQ_AVAILABLE:
        # Fallback: processamento síncrono
        from services.ai_document import analyze_document_from_base64
        
        result = await analyze_document_from_base64(
            base64_content=content_base64,
            mime_type=mime_type,
            document_type=document_type
        )
        
        return {
            "status": "sync_completed",
            "session_id": session_id,
            "filename": filename,
            "result": result,
            "async_mode": False,
        }
    
    # Enfileirar para processamento assíncrono
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
        return {
            "status": "queued",
            "job_id": job_id,
            "session_id": session_id,
            "filename": filename,
            "async_mode": True,
            "message": f"Análise enfileirada. Use GET /jobs/{job_id} para status.",
        }
    else:
        raise HTTPException(
            status_code=500,
            detail="Falha ao enfileirar análise"
        )


@router.get("/session/{session_id}/status", response_model=SessionStatusResponse)
async def get_session_status(
    session_id: str,
    user: dict = Depends(get_current_user)
):
    """
    Obter status de uma sessão de importação assíncrona.
    
    Retorna informações sobre o progresso da sessão:
    - total_files: Total de ficheiros esperados
    - processed: Ficheiros processados
    - errors: Erros encontrados
    - status: Estado atual da sessão
    """
    job = await db.background_jobs.find_one({"id": session_id}, {"_id": 0})
    
    if not job:
        raise HTTPException(
            status_code=404,
            detail=f"Sessão não encontrada: {session_id}"
        )
    
    return SessionStatusResponse(
        session_id=session_id,
        status=job.get("status", "unknown"),
        total_files=job.get("total_files", 0),
        processed=job.get("processed", 0),
        errors=job.get("errors", 0),
        jobs_pending=0,  # TODO: implementar tracking de jobs
        jobs_completed=job.get("processed", 0),
        message=job.get("message"),
    )


@router.post("/session/{session_id}/finish")
async def finish_async_session(
    session_id: str,
    user: dict = Depends(get_current_user)
):
    """
    Finalizar sessão de importação assíncrona.
    
    Agrega resultados e persiste na base de dados.
    """
    from routes.ai_bulk.jobs import finish_background_job_db
    
    # TODO: Implementar agregação de resultados de jobs
    
    await finish_background_job_db(
        session_id,
        success=True,
        message="Sessão finalizada"
    )
    
    return {
        "session_id": session_id,
        "status": "completed",
        "message": "Sessão finalizada com sucesso",
    }


@router.get("/health")
async def jobs_health_check():
    """
    Verificar saúde do sistema de jobs assíncronos.
    """
    return {
        "async_available": ARQ_AVAILABLE,
        "redis_configured": bool(os.environ.get("REDIS_URL")),
        "status": "healthy" if ARQ_AVAILABLE else "fallback_mode",
    }

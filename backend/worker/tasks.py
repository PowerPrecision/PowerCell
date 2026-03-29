"""
====================================================================
DOCUMENT ANALYSIS TASKS - ASYNC WORKER JOBS
====================================================================
Tarefas assíncronas para processamento de documentos com IA.

Estas tarefas são executadas pelo worker ARQ em background,
libertando as rotas da API para responder rapidamente.

Tarefas disponíveis:
- analyze_document_task: Análise de documento individual
- bulk_analyze_task: Análise em massa de documentos
- aggregate_and_save_task: Agregação e persistência de dados
====================================================================
"""
import os
import base64
import logging
import asyncio
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Importação condicional para evitar erros se ARQ não estiver disponível
try:
    from arq import create_pool
    from arq.connections import RedisSettings
    ARQ_AVAILABLE = True
except ImportError:
    ARQ_AVAILABLE = False
    logger.warning("ARQ não instalado - processamento síncrono será usado")

# Redis connection URL
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")


def parse_redis_url(url: str) -> RedisSettings:
    """
    Parse Redis URL para RedisSettings do ARQ.
    
    Suporta formatos:
    - redis://localhost:6379
    - redis://:password@host:port/db
    """
    from urllib.parse import urlparse
    
    parsed = urlparse(url)
    
    return RedisSettings(
        host=parsed.hostname or "localhost",
        port=parsed.port or 6379,
        password=parsed.password,
        database=int(parsed.path.lstrip("/")) if parsed.path and parsed.path != "/" else 0,
    )


async def get_redis_pool():
    """
    Obter ou criar pool de conexão Redis para ARQ.
    """
    if not ARQ_AVAILABLE:
        return None
    
    settings = parse_redis_url(REDIS_URL)
    return await create_pool(settings)


async def analyze_document_task(
    ctx: Dict,
    *,
    content_base64: str,
    mime_type: str,
    document_type: str,
    process_id: str,
    client_name: str,
    filename: str,
    session_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Analisar documento com IA em background.
    
    Esta tarefa é executada pelo worker ARQ e não bloqueia a API.
    
    Args:
        ctx: Contexto do worker (injetado pelo ARQ)
        content_base64: Conteúdo do documento em base64
        mime_type: Tipo MIME do documento
        document_type: Tipo de documento (cc, recibo_vencimento, etc.)
        process_id: ID do processo/cliente
        client_name: Nome do cliente
        filename: Nome do ficheiro
        session_id: ID da sessão de importação (opcional)
    
    Returns:
        Resultado da análise com dados extraídos
    """
    from services.ai_document import analyze_document_from_base64
    from database import db
    
    job_id = ctx.get("job_id", "unknown")
    logger.info(f"[TASK] analyze_document_task started: job_id={job_id}, file={filename}")
    
    start_time = datetime.now(timezone.utc)
    
    try:
        # Validar entrada
        if not content_base64:
            return {
                "success": False,
                "error": "Conteúdo vazio",
                "process_id": process_id,
                "filename": filename,
            }
        
        # Executar análise (esta é a parte demorada)
        result = await analyze_document_from_base64(
            base64_content=content_base64,
            mime_type=mime_type,
            document_type=document_type
        )
        
        extracted_data = result.get("extracted_data", {})
        
        # Atualizar job na base de dados se tiver session_id
        if session_id:
            try:
                await db.background_jobs.update_one(
                    {"id": session_id},
                    {
                        "$inc": {"processed": 1},
                        "$set": {
                            "updated_at": datetime.now(timezone.utc).isoformat(),
                            "last_file": filename,
                        }
                    }
                )
            except Exception as db_error:
                logger.warning(f"[TASK] Failed to update job progress: {db_error}")
        
        # Calcular duração
        duration_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)
        
        logger.info(f"[TASK] analyze_document_task completed: job_id={job_id}, duration={duration_ms}ms")
        
        return {
            "success": result.get("success", True),
            "process_id": process_id,
            "client_name": client_name,
            "filename": filename,
            "document_type": document_type,
            "extracted_data": extracted_data,
            "analysis_method": result.get("analysis_method"),
            "duration_ms": duration_ms,
            "error": result.get("error"),
        }
        
    except asyncio.TimeoutError:
        logger.error(f"[TASK] analyze_document_task timeout: job_id={job_id}")
        return {
            "success": False,
            "error": "Timeout na análise do documento",
            "process_id": process_id,
            "filename": filename,
        }
        
    except Exception as e:
        logger.error(f"[TASK] analyze_document_task error: job_id={job_id}, error={e}", exc_info=True)
        
        # Incrementar contador de erros na sessão
        if session_id:
            try:
                await db.background_jobs.update_one(
                    {"id": session_id},
                    {
                        "$inc": {"errors": 1},
                        "$set": {"updated_at": datetime.now(timezone.utc).isoformat()},
                        "$push": {"error_messages": f"{filename}: {str(e)}"}
                    }
                )
            except Exception:
                pass
        
        return {
            "success": False,
            "error": str(e),
            "process_id": process_id,
            "filename": filename,
        }


async def aggregate_and_save_task(
    ctx: Dict,
    *,
    process_id: str,
    session_id: str,
    aggregated_data: Dict[str, Any],
    document_history: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Agregar dados extraídos e persistir na base de dados.
    
    Esta tarefa é executada quando uma sessão de importação termina,
    consolidando todos os dados extraídos e atualizando o processo.
    
    Args:
        ctx: Contexto do worker (injetado pelo ARQ)
        process_id: ID do processo/cliente
        session_id: ID da sessão de importação
        aggregated_data: Dados agregados de todos os documentos
        document_history: Histórico de documentos processados
    
    Returns:
        Resultado da operação
    """
    from database import db
    from services.ai_document import build_update_data_from_extraction
    
    job_id = ctx.get("job_id", "unknown")
    logger.info(f"[TASK] aggregate_and_save_task started: job_id={job_id}, process_id={process_id}")
    
    try:
        # Obter processo existente
        existing_process = await db.processes.find_one({"id": process_id}, {"_id": 0})
        if not existing_process:
            return {
                "success": False,
                "error": "Processo não encontrado",
                "process_id": process_id,
            }
        
        # Preparar dados de atualização
        update_data = {}
        
        # Agregar dados pessoais
        if aggregated_data.get("personal_data"):
            existing_personal = existing_process.get("personal_data") or {}
            existing_personal.update(aggregated_data["personal_data"])
            update_data["personal_data"] = existing_personal
        
        # Agregar dados financeiros
        if aggregated_data.get("financial_data"):
            existing_financial = existing_process.get("financial_data") or {}
            existing_financial.update(aggregated_data["financial_data"])
            update_data["financial_data"] = existing_financial
        
        # Agregar dados do imóvel
        if aggregated_data.get("real_estate_data"):
            existing_real_estate = existing_process.get("real_estate_data") or {}
            existing_real_estate.update(aggregated_data["real_estate_data"])
            update_data["real_estate_data"] = existing_real_estate
        
        # Compradores conjuntos
        if aggregated_data.get("co_buyers"):
            update_data["co_buyers"] = aggregated_data["co_buyers"]
        if aggregated_data.get("co_applicants"):
            update_data["co_applicants"] = aggregated_data["co_applicants"]
        
        # Metadados de importação
        update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
        update_data["ai_import_aggregated"] = True
        update_data["ai_import_timestamp"] = datetime.now(timezone.utc).isoformat()
        update_data["ai_documents_count"] = len(document_history)
        
        # Executar atualização
        if update_data:
            await db.processes.update_one(
                {"id": process_id},
                {
                    "$set": update_data,
                    "$push": {
                        "ai_extraction_history": {
                            "$each": document_history
                        }
                    }
                }
            )
        
        logger.info(f"[TASK] aggregate_and_save_task completed: process_id={process_id}")
        
        return {
            "success": True,
            "process_id": process_id,
            "fields_updated": list(update_data.keys()),
            "documents_processed": len(document_history),
        }
        
    except Exception as e:
        logger.error(f"[TASK] aggregate_and_save_task error: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
            "process_id": process_id,
        }


async def cleanup_expired_sessions_task(
    ctx: Dict,
) -> Dict[str, Any]:
    """
    Limpar sessões expiradas da base de dados.
    
    Esta tarefa deve ser executada periodicamente (cron job).
    Remove sessões inativas há mais de 24 horas.
    
    Args:
        ctx: Contexto do worker (injetado pelo ARQ)
    
    Returns:
        Número de sessões limpas
    """
    from database import db
    
    logger.info("[TASK] cleanup_expired_sessions_task started")
    
    try:
        # Calcular threshold (24 horas atrás)
        threshold = datetime.now(timezone.utc) - __import__('datetime').timedelta(hours=24)
        threshold_iso = threshold.isoformat()
        
        # Remover sessões antigas
        result = await db.aggregated_sessions.delete_many({
            "is_active": False,
            "finished_at": {"$lt": threshold_iso}
        })
        
        # Limpar jobs antigos
        jobs_result = await db.background_jobs.delete_many({
            "status": {"$in": ["completed", "failed"]},
            "updated_at": {"$lt": threshold_iso}
        })
        
        logger.info(f"[TASK] cleanup_expired_sessions_task completed: sessions={result.deleted_count}, jobs={jobs_result.deleted_count}")
        
        return {
            "success": True,
            "sessions_deleted": result.deleted_count,
            "jobs_deleted": jobs_result.deleted_count,
        }
        
    except Exception as e:
        logger.error(f"[TASK] cleanup_expired_sessions_task error: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
        }


# ====================================================================
# FUNÇÕES UTILITÁRIAS PARA ENFILEIRAR TAREFAS
# ====================================================================

async def enqueue_document_analysis(
    content_base64: str,
    mime_type: str,
    document_type: str,
    process_id: str,
    client_name: str,
    filename: str,
    session_id: Optional[str] = None,
) -> Optional[str]:
    """
    Enfileirar tarefa de análise de documento.
    
    Retorna o job_id se sucesso, None se falhar.
    """
    if not ARQ_AVAILABLE:
        logger.warning("ARQ não disponível - usando processamento síncrono")
        return None
    
    try:
        redis = await get_redis_pool()
        job = await redis.enqueue_job(
            "analyze_document_task",
            content_base64=content_base64,
            mime_type=mime_type,
            document_type=document_type,
            process_id=process_id,
            client_name=client_name,
            filename=filename,
            session_id=session_id,
        )
        logger.info(f"[ENQUEUE] Job enqueued: {job.job_id}")
        return job.job_id
    except Exception as e:
        logger.error(f"[ENQUEUE] Failed to enqueue job: {e}")
        return None


async def get_job_status(job_id: str) -> Optional[Dict[str, Any]]:
    """
    Obter status de um job.
    
    Retorna informações sobre o job ou None se não encontrado.
    """
    if not ARQ_AVAILABLE:
        return None
    
    try:
        redis = await get_redis_pool()
        job = await redis.get_job(job_id)
        
        if not job:
            return None
        
        return {
            "job_id": job.job_id,
            "status": job.status,
            "result": job.result,
            "start_time": job.start_time,
            "finish_time": job.finish_time,
            "exc_info": job.exc_info,
        }
    except Exception as e:
        logger.error(f"[JOB_STATUS] Failed to get job status: {e}")
        return None


# ====================================================================
# REGISTAR TAREFAS NO WORKER
# ====================================================================

# Lista de tarefas a registar no worker
TASK_FUNCTIONS = [
    analyze_document_task,
    aggregate_and_save_task,
    cleanup_expired_sessions_task,
]

"""
====================================================================
ARQ WORKER CONFIGURATION - ASYNC DOCUMENT PROCESSING
====================================================================
Configuração do worker ARQ para processamento assíncrono de documentos.

ARQ é uma alternativa leve ao Celery que:
- Funciona nativamente com asyncio/FastAPI
- Usa Redis como broker (já instalado no projeto)
- É mais simples de configurar e manter

Variáveis de ambiente necessárias:
- REDIS_URL: URL de conexão Redis (default: redis://localhost:6379)

Para iniciar o worker:
    cd backend && arq worker.config.WorkerSettings
====================================================================
"""
import os
import logging
from typing import Dict, Any, Optional
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Redis connection URL
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")

# Job timeout in seconds (5 minutes for document processing)
JOB_TIMEOUT = int(os.environ.get("ARQ_JOB_TIMEOUT", "300"))

# Keep job results for 24 hours
KEEP_RESULT = int(os.environ.get("ARQ_KEEP_RESULT", "86400"))

# Maximum concurrent jobs
MAX_CONCURRENT_JOBS = int(os.environ.get("ARQ_MAX_CONCURRENT", "10"))


async def startup(ctx: Dict) -> None:
    """
    Executado quando o worker inicia.
    Inicializa conexões e recursos partilhados.
    """
    logger.info("[ARQ WORKER] Starting up...")
    
    # Importar database aqui para evitar import circular
    from database import db
    
    ctx["db"] = db
    ctx["startup_time"] = datetime.now(timezone.utc)
    
    logger.info("[ARQ WORKER] Startup complete - ready to process jobs")


async def shutdown(ctx: Dict) -> None:
    """
    Executado quando o worker para.
    Limpa recursos e fecha conexões.
    """
    logger.info("[ARQ WORKER] Shutting down...")
    
    # Limpar recursos se necessário
    ctx.clear()
    
    logger.info("[ARQ WORKER] Shutdown complete")


async def on_job_start(ctx: Dict) -> None:
    """
    Executado antes de cada job.
    """
    job_id = ctx.get("job_id", "unknown")
    logger.info(f"[ARQ WORKER] Starting job: {job_id}")


async def on_job_end(ctx: Dict) -> None:
    """
    Executado após cada job terminar.
    """
    job_id = ctx.get("job_id", "unknown")
    logger.info(f"[ARQ WORKER] Finished job: {job_id}")


async def on_job_failed(ctx: Dict) -> None:
    """
    Executado quando um job falha.
    """
    job_id = ctx.get("job_id", "unknown")
    error = ctx.get("error", "Unknown error")
    logger.error(f"[ARQ WORKER] Job failed: {job_id} - {error}")


# Importar tarefas
from worker.tasks import (
    analyze_document_task,
    aggregate_and_save_task,
    cleanup_expired_sessions_task,
)


class WorkerSettings:
    """
    Configurações do worker ARQ.
    
    Esta classe é usada pelo comando `arq worker.config.WorkerSettings`
    para iniciar o worker.
    """
    # Redis connection
    redis_dsn = REDIS_URL
    
    # Functions to register as tasks
    functions = [
        analyze_document_task,
        aggregate_and_save_task,
        cleanup_expired_sessions_task,
    ]
    
    # Lifecycle hooks
    on_startup = startup
    on_shutdown = shutdown
    on_job_start = on_job_start
    on_job_end = on_job_end
    
    # Job settings
    job_timeout = JOB_TIMEOUT
    keep_result = KEEP_RESULT
    max_tries = 3  # Retry failed jobs up to 3 times
    
    # Concurrency
    max_jobs = MAX_CONCURRENT_JOBS
    
    # Polling interval (seconds)
    poll_delay = 0.5
    
    # Retry settings
    retry_jobs = True
    retry_on_timeout = True
    
    # Cron jobs for periodic tasks
    cron_jobs = [
        # Executar limpeza de sessões expiradas a cada hora
        # Nota: Para ativar, descomente a linha abaixo
        # cron(cleanup_expired_sessions_task, hour="*", minute=0),
    ]

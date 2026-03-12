"""
Background Jobs Service
=======================
Sistema para processar tarefas longas em background (importações, análises, etc.)
Permite ao utilizador acompanhar o progresso em tempo real.
"""
import asyncio
import uuid
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Callable, List
from enum import Enum

from database import db

logger = logging.getLogger(__name__)


class JobStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class JobType(str, Enum):
    EXCEL_IMPORT = "excel_import"
    BULK_ANALYSIS = "bulk_analysis"
    DATA_EXPORT = "data_export"


class BackgroundJobService:
    """
    Serviço para gerir jobs em background.
    Armazena progresso no MongoDB para persistência e acompanhamento.
    """
    
    def __init__(self):
        self._running_jobs: Dict[str, asyncio.Task] = {}
    
    async def create_job(
        self,
        job_type: JobType,
        user_id: str,
        user_email: str,
        metadata: Dict[str, Any] = None
    ) -> str:
        """
        Cria um novo job e retorna o ID.
        """
        job_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        
        job_doc = {
            "id": job_id,
            "type": job_type.value,
            "status": JobStatus.PENDING.value,
            "user_id": user_id,
            "user_email": user_email,
            "metadata": metadata or {},
            "progress": {
                "current": 0,
                "total": 0,
                "percentage": 0,
                "message": "A iniciar..."
            },
            "result": None,
            "error": None,
            "created_at": now,
            "started_at": None,
            "completed_at": None
        }
        
        await db.background_jobs.insert_one(job_doc)
        logger.info(f"Job criado: {job_id} ({job_type.value}) por {user_email}")
        
        return job_id
    
    async def update_progress(
        self,
        job_id: str,
        current: int,
        total: int,
        message: str = None
    ):
        """
        Atualiza o progresso de um job.
        """
        percentage = int((current / total * 100)) if total > 0 else 0
        
        update = {
            "$set": {
                "progress.current": current,
                "progress.total": total,
                "progress.percentage": percentage
            }
        }
        
        if message:
            update["$set"]["progress.message"] = message
        
        await db.background_jobs.update_one({"id": job_id}, update)
    
    async def set_status(self, job_id: str, status: JobStatus):
        """
        Define o status de um job.
        """
        now = datetime.now(timezone.utc).isoformat()
        
        update = {"$set": {"status": status.value}}
        
        if status == JobStatus.PROCESSING:
            update["$set"]["started_at"] = now
        elif status in [JobStatus.COMPLETED, JobStatus.FAILED]:
            update["$set"]["completed_at"] = now
        
        await db.background_jobs.update_one({"id": job_id}, update)
    
    async def set_result(self, job_id: str, result: Dict[str, Any]):
        """
        Define o resultado de um job concluído.
        """
        await db.background_jobs.update_one(
            {"id": job_id},
            {"$set": {
                "result": result,
                "status": JobStatus.COMPLETED.value,
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "progress.percentage": 100,
                "progress.message": "Concluído"
            }}
        )
    
    async def set_error(self, job_id: str, error: str):
        """
        Define o erro de um job falhado.
        """
        await db.background_jobs.update_one(
            {"id": job_id},
            {"$set": {
                "error": error,
                "status": JobStatus.FAILED.value,
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "progress.message": f"Erro: {error}"
            }}
        )
    
    async def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """
        Obtém um job pelo ID.
        """
        job = await db.background_jobs.find_one({"id": job_id}, {"_id": 0})
        return job
    
    async def get_user_jobs(
        self,
        user_id: str,
        job_type: JobType = None,
        status: JobStatus = None,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Obtém os jobs de um utilizador.
        """
        query = {"user_id": user_id}
        
        if job_type:
            query["type"] = job_type.value
        if status:
            query["status"] = status.value
        
        jobs = await db.background_jobs.find(
            query,
            {"_id": 0}
        ).sort("created_at", -1).limit(limit).to_list(limit)
        
        return jobs
    
    async def cleanup_old_jobs(self, days: int = 7) -> int:
        """
        Remove jobs antigos.
        """
        from datetime import timedelta
        
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        
        result = await db.background_jobs.delete_many({
            "completed_at": {"$lt": cutoff},
            "status": {"$in": [JobStatus.COMPLETED.value, JobStatus.FAILED.value]}
        })
        
        return result.deleted_count
    
    def run_in_background(self, job_id: str, coroutine):
        """
        Executa uma coroutine em background.
        """
        async def wrapper():
            try:
                await coroutine
            except Exception as e:
                logger.error(f"Job {job_id} falhou: {e}")
                await self.set_error(job_id, str(e))
            finally:
                if job_id in self._running_jobs:
                    del self._running_jobs[job_id]
        
        task = asyncio.create_task(wrapper())
        self._running_jobs[job_id] = task
        return task


# Instância global
background_jobs = BackgroundJobService()

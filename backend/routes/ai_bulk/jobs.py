"""
Gestão de Background Jobs.
Extraído de ai_bulk.py para melhor organização (SonarQube).

Este módulo contém:
- Tracking de processos em background
- Persistência de jobs na DB
- Funções para criar, atualizar, finalizar jobs
"""
import uuid
import logging
import re
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional, Any

from database import db
from .constants import (
    ERROR_JOB_NOT_FOUND,
    ERROR_ONLY_RUNNING_JOBS_CAN_CANCEL,
    ERROR_ONLY_RUNNING_JOBS_CAN_PAUSE,
    ERROR_ONLY_PAUSED_JOBS_CAN_RESUME
)

logger = logging.getLogger(__name__)


def _sanitize_for_log(value: str, max_length: int = 50) -> str:
    """
    Sanitiza dados controlados pelo utilizador antes de logar.
    Remove carateres potencialmente perigosos e limita o tamanho.
    """
    if not value:
        return "[empty]"
    # Truncar e remover quebras de linha/carateres perigosos
    sanitized = str(value)[:max_length].replace('\n', ' ').replace('\r', '')
    # Remover carateres de controlo
    sanitized = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', sanitized)
    return sanitized if sanitized else "[sanitized]"

# Cache em memória para performance (a DB é a fonte de verdade)
background_processes: Dict[str, dict] = {}  # job_id -> status


async def create_background_job_db(
    job_type: str, 
    user_email: str, 
    details: dict = None, 
    total_files: int = 0
) -> str:
    """Criar registo de job em background (persistido na DB)."""
    job_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    
    job = {
        "id": job_id,
        "type": job_type,
        "status": "running",
        "started_at": now.isoformat(),
        "user_email": user_email,
        "progress": 0,
        "total": total_files,
        "processed": 0,
        "errors": 0,
        "details": details or {},
        "error_messages": [],
        "finished_at": None
    }
    
    # Guardar em memória e na DB
    background_processes[job_id] = job
    await db.background_jobs.insert_one({**job, "_id": job_id})
    
    # Log sem dados controlados pelo utilizador
    logger.info(f"[BG JOB] Criado: tipo={_sanitize_for_log(job_type)} ficheiros={total_files}")
    return job_id


async def update_background_job_db(job_id: str, **kwargs):
    """Atualizar estado de um job em background (persistido na DB)."""
    update_data = {**kwargs, "updated_at": datetime.now(timezone.utc).isoformat()}
    
    # Actualizar cache em memória
    if job_id in background_processes:
        background_processes[job_id].update(update_data)
        if background_processes[job_id].get("total", 0) > 0:
            processed = background_processes[job_id].get("processed", 0)
            total = background_processes[job_id]["total"]
            update_data["progress"] = int((processed / total) * 100)
            background_processes[job_id]["progress"] = update_data["progress"]
    
    # Actualizar na DB
    await db.background_jobs.update_one(
        {"id": job_id},
        {"$set": update_data}
    )


async def finish_background_job_db(
    job_id: str, 
    success: bool, 
    message: str = None
):
    """Marcar job como terminado (persistido na DB)."""
    status = "success" if success else "failed"
    finished_at = datetime.now(timezone.utc).isoformat()
    
    update_data = {
        "status": status,
        "finished_at": finished_at
    }
    if message:
        update_data["message"] = message
    
    # Actualizar cache em memória
    if job_id in background_processes:
        background_processes[job_id].update(update_data)
    
    # Actualizar na DB
    await db.background_jobs.update_one(
        {"id": job_id},
        {"$set": update_data}
    )
    
    logger.info(f"[BG JOB] Terminado: status={status}")


async def load_background_jobs_from_db():
    """Carregar jobs da DB para memória (chamado no startup)."""
    try:
        # Carregar apenas jobs recentes (últimos 7 dias)
        cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
        jobs = await db.background_jobs.find(
            {"started_at": {"$gte": cutoff}},
            {"_id": 0}
        ).to_list(100)
        
        for job in jobs:
            background_processes[job["id"]] = job
        
        logger.info(f"[BG JOB] {len(jobs)} jobs carregados da DB")
    except (IOError, OSError, ValueError, KeyError, TypeError, ConnectionError, TimeoutError) as e:
        logger.error(f"[BG JOB] Erro ao carregar da DB: {e}")


# ====================================================================
# FUNÇÕES LEGADAS PARA COMPATIBILIDADE
# ====================================================================

def create_background_job(job_type: str, user_email: str, details: dict = None) -> str:
    """[LEGACY] Criar registo de job em background (apenas memória)."""
    job_id = str(uuid.uuid4())
    background_processes[job_id] = {
        "id": job_id,
        "type": job_type,
        "status": "running",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "user_email": user_email,
        "progress": 0,
        "total": 0,
        "processed": 0,
        "errors": 0,
        "details": details or {},
        "error_messages": [],
        "finished_at": None
    }
    logger.info(f"[BG JOB] Criado (legacy): tipo={_sanitize_for_log(job_type)}")
    return job_id


def update_background_job(job_id: str, **kwargs):
    """[LEGACY] Atualizar estado de um job em background (apenas memória)."""
    if job_id in background_processes:
        background_processes[job_id].update(kwargs)
        
        # Calcular progresso percentual
        if background_processes[job_id].get("total", 0) > 0:
            processed = background_processes[job_id].get("processed", 0)
            total = background_processes[job_id]["total"]
            background_processes[job_id]["progress"] = int((processed / total) * 100)


def finish_background_job(job_id: str, success: bool, message: str = None):
    """[LEGACY] Marcar job como terminado (apenas memória)."""
    if job_id in background_processes:
        background_processes[job_id]["status"] = "success" if success else "failed"
        background_processes[job_id]["finished_at"] = datetime.now(timezone.utc).isoformat()
        if message:
            background_processes[job_id]["message"] = message
        logger.info(f"[BG JOB] Terminado (legacy): status={background_processes[job_id]['status']}")


# ====================================================================
# FUNÇÕES DE CONSULTA
# ====================================================================

async def get_job_status(job_id: str) -> Optional[dict]:
    """Obter estado de um job (memória primeiro, depois DB)."""
    # Tentar memória primeiro (mais rápido)
    if job_id in background_processes:
        return background_processes[job_id]
    
    # Buscar na DB
    job = await db.background_jobs.find_one({"id": job_id}, {"_id": 0})
    return job


async def get_all_jobs(status: str = None, limit: int = 20) -> list:
    """Obter lista de jobs (com filtro opcional por status)."""
    # Carregar jobs recentes da DB (última semana)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    query = {"started_at": {"$gte": cutoff}}
    
    if status:
        query["status"] = status
    
    # Buscar da DB
    db_jobs = await db.background_jobs.find(
        query,
        {"_id": 0}
    ).sort("started_at", -1).limit(limit).to_list(limit)
    
    # Juntar com jobs em memória (podem existir jobs novos ainda não na DB)
    all_jobs = {job["id"]: job for job in db_jobs}
    for jid, job in background_processes.items():
        if jid not in all_jobs:
            if not status or job.get("status") == status:
                all_jobs[jid] = job
    
    jobs = list(all_jobs.values())
    jobs.sort(key=lambda x: x.get("started_at", ""), reverse=True)
    return jobs[:limit]


async def get_job_counts() -> Dict[str, int]:
    """Obter contagem de jobs por status."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    
    running_count = await db.background_jobs.count_documents({"status": "running"})
    paused_count = await db.background_jobs.count_documents({"status": "paused"})
    success_count = await db.background_jobs.count_documents({"status": "success", "started_at": {"$gte": cutoff}})
    failed_count = await db.background_jobs.count_documents({"status": "failed", "started_at": {"$gte": cutoff}})
    total_count = await db.background_jobs.count_documents({"started_at": {"$gte": cutoff}})
    
    return {
        "running": running_count,
        "paused": paused_count,
        "success": success_count,
        "failed": failed_count,
        "total": total_count
    }


# ====================================================================
# FUNÇÕES DE MANIPULAÇÃO
# ====================================================================

async def cancel_job(job_id: str) -> dict:
    """Cancelar um job em execução."""
    job = await get_job_status(job_id)
    
    if not job:
        raise ValueError(ERROR_JOB_NOT_FOUND)
    
    if job.get("status") != "running":
        raise ValueError(ERROR_ONLY_RUNNING_JOBS_CAN_CANCEL)
    
    # Marcar como cancelado
    update_data = {
        "status": "cancelled",
        "message": "Cancelado pelo utilizador",
        "finished_at": datetime.now(timezone.utc).isoformat()
    }
    
    # Actualizar na memória
    if job_id in background_processes:
        background_processes[job_id].update(update_data)
    
    # Actualizar na DB
    await db.background_jobs.update_one(
        {"id": job_id},
        {"$set": update_data}
    )
    
    return {"success": True, "status": "cancelled"}


async def pause_job(job_id: str) -> dict:
    """Pausar um job em execução."""
    job = await get_job_status(job_id)
    
    if not job:
        raise ValueError(ERROR_JOB_NOT_FOUND)
    
    if job.get("status") != "running":
        raise ValueError(ERROR_ONLY_RUNNING_JOBS_CAN_PAUSE)
    
    # Marcar como pausado
    update_data = {
        "status": "paused",
        "paused_at": datetime.now(timezone.utc).isoformat()
    }
    
    # Actualizar na memória
    if job_id in background_processes:
        background_processes[job_id].update(update_data)
    
    # Actualizar na DB
    await db.background_jobs.update_one(
        {"id": job_id},
        {"$set": update_data}
    )
    
    return {"success": True, "status": "paused"}


async def resume_job(job_id: str) -> dict:
    """Retomar um job pausado."""
    job = await get_job_status(job_id)
    
    if not job:
        raise ValueError(ERROR_JOB_NOT_FOUND)
    
    if job.get("status") != "paused":
        raise ValueError(ERROR_ONLY_PAUSED_JOBS_CAN_RESUME)
    
    # Marcar como running novamente
    update_data = {
        "status": "running",
        "resumed_at": datetime.now(timezone.utc).isoformat()
    }
    
    # Actualizar na memória
    if job_id in background_processes:
        background_processes[job_id].update(update_data)
    
    # Actualizar na DB
    await db.background_jobs.update_one(
        {"id": job_id},
        {"$set": update_data}
    )
    
    return {"success": True, "status": "running"}


async def delete_job(job_id: str) -> bool:
    """Remover um job do histórico."""
    # Remover da memória
    job = background_processes.pop(job_id, None)
    
    # Remover da DB
    result = await db.background_jobs.delete_one({"id": job_id})
    
    return bool(job or result.deleted_count > 0)


async def cleanup_stuck_jobs(max_age_hours: int = 2) -> dict:
    """Limpar jobs que estão "stuck" (running/pending há muito tempo)."""
    cutoff_time = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
    
    stuck_jobs = []
    cleaned_ids = []
    
    # Verificar jobs na memória
    for jid, job in list(background_processes.items()):
        if job.get("status") in ["running", "pending"]:
            updated_at_str = job.get("updated_at") or job.get("created_at")
            if updated_at_str:
                try:
                    if isinstance(updated_at_str, str):
                        updated_at = datetime.fromisoformat(updated_at_str.replace('Z', '+00:00'))
                    else:
                        updated_at = updated_at_str
                    
                    if updated_at < cutoff_time:
                        stuck_jobs.append({
                            "id": jid,
                            "type": job.get("type"),
                            "status": job.get("status"),
                            "hours_stuck": round((datetime.now(timezone.utc) - updated_at).total_seconds() / 3600, 1)
                        })
                        
                        # Marcar como failed
                        background_processes[jid]["status"] = "failed"
                        background_processes[jid]["error"] = f"Job marcado como stuck após {max_age_hours}h"
                        cleaned_ids.append(jid)
                except (ValueError, TypeError):
                    pass
    
    # Actualizar jobs stuck na DB
    if cleaned_ids:
        await db.background_jobs.update_many(
            {"id": {"$in": cleaned_ids}},
            {"$set": {
                "status": "failed",
                "error": f"Job marcado como stuck após {max_age_hours}h"
            }}
        )
    
    return {
        "stuck_found": len(stuck_jobs),
        "cleaned": len(cleaned_ids),
        "details": stuck_jobs
    }

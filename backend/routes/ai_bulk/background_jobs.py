"""
Background Jobs Management
==========================
Gestão de jobs em background para importação em massa.
Inclui criação, actualização, tracking e métricas.
"""
import uuid
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional, List, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from database import db
from models.auth import UserRole
from services.auth import require_roles

logger = logging.getLogger(__name__)
router = APIRouter()

# Cache em memória para performance (a DB é a fonte de verdade)
background_processes: Dict[str, dict] = {}


# ====================================================================
# FUNÇÕES DE GESTÃO DE JOBS
# ====================================================================

async def create_background_job_db(job_type: str, user_email: str, details: dict = None, total_files: int = 0) -> str:
    """Criar registo de job em background (persistido na DB)."""
    job_id = str(uuid.uuid4())
    job = {
        "id": job_id,
        "type": job_type,
        "status": "running",
        "started_at": datetime.now(timezone.utc).isoformat(),
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
    
    logger.info(f"Job background criado: {job_id} ({job_type}) com {total_files} ficheiros")
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


async def finish_background_job_db(job_id: str, success: bool, message: str = None):
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
    
    logger.info(f"Job background terminado: {job_id} ({status})")


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
        
        logger.info(f"[BACKGROUND JOBS] {len(jobs)} jobs carregados da DB")
    except Exception as e:
        logger.error(f"[BACKGROUND JOBS] Erro ao carregar da DB: {e}")


# Funções legadas para compatibilidade
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
    return job_id


def update_background_job(job_id: str, **kwargs):
    """[LEGACY] Atualizar estado de um job em background (apenas memória)."""
    if job_id in background_processes:
        background_processes[job_id].update(kwargs)
        
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


def _format_duration(seconds: float) -> str:
    """Formatar duração em string legível."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        minutes = seconds / 60
        return f"{minutes:.1f}m"
    else:
        hours = seconds / 3600
        return f"{hours:.1f}h"


# ====================================================================
# ENDPOINTS DE BACKGROUND JOBS
# ====================================================================

@router.get("/background-jobs")
async def get_background_jobs(
    status: Optional[str] = None,
    limit: int = Query(50, le=200),
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """Lista jobs em background com filtros opcionais."""
    query = {}
    if status:
        query["status"] = status
    
    jobs = await db.background_jobs.find(
        query,
        {"_id": 0}
    ).sort("started_at", -1).limit(limit).to_list(limit)
    
    # Adicionar informação sobre jobs em memória
    memory_jobs = []
    for job_id, job in background_processes.items():
        if status and job.get("status") != status:
            continue
        
        # Verificar se já está na lista da DB
        if not any(j.get("id") == job_id for j in jobs):
            memory_jobs.append(job)
    
    all_jobs = jobs + memory_jobs[:limit - len(jobs)]
    
    return {
        "jobs": all_jobs,
        "total": len(all_jobs),
        "from_db": len(jobs),
        "from_memory": len(memory_jobs)
    }


@router.get("/background-jobs/metrics")
async def get_job_metrics(
    days: int = Query(7, ge=1, le=30),
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """Obtém métricas agregadas de jobs em background."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    
    jobs = await db.background_jobs.find(
        {"started_at": {"$gte": cutoff}},
        {"_id": 0}
    ).to_list(1000)
    
    if not jobs:
        return {
            "period_days": days,
            "total_jobs": 0,
            "success_rate": 0,
            "avg_duration_seconds": 0,
            "by_status": {},
            "by_type": {},
            "trend": [],
            "stuck_count": 0
        }
    
    # Calcular métricas
    total = len(jobs)
    by_status = {}
    by_type = {}
    durations = []
    stuck_count = 0
    
    for job in jobs:
        # Por status
        status = job.get("status", "unknown")
        by_status[status] = by_status.get(status, 0) + 1
        
        # Por tipo
        jtype = job.get("type", "unknown")
        by_type[jtype] = by_type.get(jtype, 0) + 1
        
        # Duração
        if job.get("started_at") and job.get("finished_at"):
            try:
                start = datetime.fromisoformat(job["started_at"].replace("Z", "+00:00"))
                end = datetime.fromisoformat(job["finished_at"].replace("Z", "+00:00"))
                duration = (end - start).total_seconds()
                durations.append(duration)
            except:
                pass
        
        # Jobs stuck
        if status in ["running", "pending"]:
            updated = job.get("updated_at") or job.get("started_at")
            if updated:
                try:
                    updated_dt = datetime.fromisoformat(updated.replace("Z", "+00:00"))
                    if (datetime.now(timezone.utc) - updated_dt).total_seconds() > 7200:  # 2 horas
                        stuck_count += 1
                except:
                    pass
    
    success_count = by_status.get("success", 0)
    success_rate = (success_count / total * 100) if total > 0 else 0
    avg_duration = sum(durations) / len(durations) if durations else 0
    
    # Trend por dia
    trend = {}
    for job in jobs:
        try:
            date = job.get("started_at", "")[:10]
            if date:
                trend[date] = trend.get(date, 0) + 1
        except:
            pass
    
    trend_list = [{"date": d, "count": c} for d, c in sorted(trend.items())]
    
    return {
        "period_days": days,
        "total_jobs": total,
        "success_rate": round(success_rate, 1),
        "avg_duration_seconds": round(avg_duration, 1),
        "avg_duration_formatted": _format_duration(avg_duration),
        "by_status": by_status,
        "by_type": by_type,
        "trend": trend_list,
        "stuck_count": stuck_count
    }


@router.get("/background-jobs/notifications")
async def get_job_notifications(
    unread_only: bool = True,
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """Obtém notificações de jobs (ex: jobs stuck)."""
    try:
        query = {"type": "stuck_job"}
        if unread_only:
            query["is_read"] = False
        
        notifications = await db.job_notifications.find(
            query,
            {"_id": 0}
        ).sort("created_at", -1).limit(50).to_list(50)
        
        return {"notifications": notifications}
    except Exception as e:
        logger.warning(f"Erro ao obter notificações de jobs: {e}")
        # Retornar lista vazia se a coleção não existir
        return {"notifications": []}


@router.put("/background-jobs/notifications/{notification_id}/read")
async def mark_notification_read(
    notification_id: str,
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """Marca notificação como lida."""
    result = await db.job_notifications.update_one(
        {"id": notification_id},
        {"$set": {"is_read": True, "read_at": datetime.now(timezone.utc).isoformat()}}
    )
    
    return {"success": result.modified_count > 0}


@router.delete("/background-jobs/notifications/clear")
async def clear_job_notifications(
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """Limpa todas as notificações de jobs."""
    result = await db.job_notifications.delete_many({})
    return {"deleted": result.deleted_count}


@router.get("/background-jobs/{job_id}")
async def get_background_job_status(
    job_id: str,
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """Obtém estado de um job específico."""
    # Primeiro tentar memória (mais rápido)
    if job_id in background_processes:
        return background_processes[job_id]
    
    # Depois tentar DB
    job = await db.background_jobs.find_one({"id": job_id}, {"_id": 0})
    
    if not job:
        raise HTTPException(status_code=404, detail="Job não encontrado")
    
    return job


@router.delete("/background-jobs/{job_id}")
async def delete_background_job(
    job_id: str,
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """Remove um job em background."""
    # Remover de memória
    if job_id in background_processes:
        del background_processes[job_id]
    
    # Remover da DB
    result = await db.background_jobs.delete_one({"id": job_id})
    
    return {"success": result.deleted_count > 0}


@router.post("/background-jobs/{job_id}/cancel")
async def cancel_background_job(
    job_id: str,
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """Cancela um job em execução."""
    job = background_processes.get(job_id)
    if not job:
        job = await db.background_jobs.find_one({"id": job_id}, {"_id": 0})
    
    if not job:
        raise HTTPException(status_code=404, detail="Job não encontrado")
    
    if job.get("status") not in ["running", "pending"]:
        raise HTTPException(status_code=400, detail="Job não pode ser cancelado (não está em execução)")
    
    await finish_background_job_db(job_id, False, "Cancelado pelo utilizador")
    
    return {"success": True, "message": "Job cancelado"}


@router.post("/background-jobs/cleanup-stuck")
async def cleanup_stuck_jobs(
    hours: int = Query(2, ge=1, le=24),
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """Limpa jobs que estão stuck há mais de X horas."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    
    stuck_jobs = await db.background_jobs.find({
        "status": {"$in": ["running", "pending"]},
        "$or": [
            {"updated_at": {"$lt": cutoff.isoformat()}},
            {"updated_at": None, "started_at": {"$lt": cutoff.isoformat()}}
        ]
    }, {"_id": 0, "id": 1}).to_list(100)
    
    cleaned = 0
    for job in stuck_jobs:
        await finish_background_job_db(job["id"], False, f"Limpo automaticamente (stuck > {hours}h)")
        cleaned += 1
    
    return {"cleaned": cleaned}


@router.delete("/background-jobs")
async def clear_finished_jobs(
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """Remove jobs terminados (success ou failed)."""
    result = await db.background_jobs.delete_many({
        "status": {"$in": ["success", "failed", "cancelled"]}
    })
    
    # Limpar também da memória
    to_remove = [k for k, v in background_processes.items() 
                 if v.get("status") in ["success", "failed", "cancelled"]]
    for k in to_remove:
        del background_processes[k]
    
    return {"deleted": result.deleted_count + len(to_remove)}


@router.post("/background-jobs/clear-all")
async def clear_all_jobs(
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """Remove TODOS os jobs (usar com cuidado)."""
    result = await db.background_jobs.delete_many({})
    
    count = len(background_processes)
    background_processes.clear()
    
    return {"deleted_db": result.deleted_count, "deleted_memory": count}


# ====================================================================
# MODELOS PYDANTIC
# ====================================================================

class ProgressUpdateRequest(BaseModel):
    """Request para actualizar progresso de um job."""
    processed: Optional[int] = None
    errors: Optional[int] = None
    message: Optional[str] = None


@router.post("/background-job/{job_id}/progress")
async def update_background_job_progress(
    job_id: str,
    request: ProgressUpdateRequest,
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """
    Actualizar progresso de um job em background.
    Usado pelo frontend para reportar progresso de uploads.
    """
    update_fields = {}
    
    if request.processed is not None:
        update_fields["processed"] = request.processed
    if request.errors is not None:
        update_fields["errors"] = request.errors
    if request.message:
        update_fields["message"] = request.message
    
    if update_fields:
        await update_background_job_db(job_id, **update_fields)
    
    job = background_processes.get(job_id)
    if not job:
        job = await db.background_jobs.find_one({"id": job_id}, {"_id": 0})
    
    return job or {"error": "Job não encontrado", "updated": bool(update_fields)}

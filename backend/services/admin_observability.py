"""System logs, jobs health, client registrations, audit, stale processes, team performance.

Extraído de `routes/admin.py`.
"""
from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone, timedelta
from typing import List, Optional

from fastapi import HTTPException, Query, Request, BackgroundTasks
from pydantic import BaseModel

from database import db
from models.auth import UserRole, UserCreate, UserUpdate, UserResponse
from models.workflow import WorkflowStatusCreate, WorkflowStatusUpdate, WorkflowStatusResponse
from models.email_config import EmailConfigCreate, EmailConfigResponse
from services.auth import hash_password, require_roles, get_current_user
from services.process_status import INACTIVE_STATUSES
from services.admin_helpers import _safe_float, _audit_log
from services.permissions import (
    get_default_permissions_for_role,
    get_all_available_permissions,
    get_role_display_info,
    validate_permissions,
    DEFAULT_PERMISSIONS_BY_ROLE,
    get_user_capabilities,
    build_permissions_document,
)
from models.permissions import (
    CAPABILITIES,
    CATEGORIES,
    SUPER_ADMIN_ROLES,
    ROLE_CAPABILITY_DEFAULTS,
    get_all_capabilities,
    get_capabilities_by_category,
    get_role_defaults,
    resolve_capability,
    validate_capabilities,
)

logger = logging.getLogger(__name__)



async def run_get_system_error_logs(user: dict, page: int = 1, limit: int = 50, severity: str = None, component: str = None, error_type: str = None, resolved: bool = None, days: int = 7):
    """
    Obtém logs de erros do sistema com filtros e paginação.
    
    Query params:
    - page: Página (default 1)
    - limit: Items por página (default 50)
    - severity: Filtrar por severidade (info, warning, error, critical)
    - component: Filtrar por componente (scraper, auth, processes, etc.)
    - error_type: Filtrar por tipo de erro
    - resolved: True/False para filtrar resolvidos/não resolvidos
    - days: Últimos N dias (default 7)
    """
    from services.system_error_logger import system_error_logger
    return await system_error_logger.get_errors(
        page=page,
        limit=limit,
        severity=severity,
        component=component,
        error_type=error_type,
        resolved=resolved,
        days=days
    )


async def run_get_system_logs_stats(user: dict, days: int = 7):
    """Obtém estatísticas de erros dos últimos N dias."""
    from services.system_error_logger import system_error_logger
    return await system_error_logger.get_stats(days)


async def run_get_system_log_detail(error_id: str, user: dict):
    """Obtém detalhes de um erro específico."""
    from services.system_error_logger import system_error_logger
    error = await system_error_logger.get_error_by_id(error_id)
    if not error:
        raise HTTPException(status_code=404, detail="Erro não encontrado")
    return error


async def run_mark_errors_as_read(data: dict, user: dict):
    """
    Marca erros como lidos.
    
    Body: {"error_ids": ["id1", "id2"]}
    """
    error_ids = data.get("error_ids", [])
    if not error_ids:
        raise HTTPException(status_code=400, detail="error_ids é obrigatório")
    
    from services.system_error_logger import system_error_logger
    count = await system_error_logger.mark_as_read(error_ids)
    return {"success": True, "marked_count": count}


async def run_resolve_system_error(error_id: str, user: dict, data: dict = None):
    """
    Marca um erro como resolvido.
    
    Body (opcional): {"notes": "Corrigido em versão X"}
    """
    data = data or {}
    notes = data.get("notes")
    
    from services.system_error_logger import system_error_logger
    success = await system_error_logger.mark_as_resolved(
        error_id=error_id,
        resolved_by=user.get("email", "admin"),
        notes=notes
    )
    
    if not success:
        raise HTTPException(status_code=404, detail="Erro não encontrado")
    
    return {"success": True, "message": "Erro marcado como resolvido"}


async def run_bulk_resolve_system_errors(data: dict, user: dict):
    """
    Marca múltiplos erros como resolvidos em massa.
    
    Body: {"error_ids": ["id1", "id2", ...]}
    """
    error_ids = data.get("error_ids", [])
    
    if not error_ids:
        raise HTTPException(status_code=400, detail="Nenhum ID fornecido")
    
    from services.system_error_logger import system_error_logger
    resolved_count = await system_error_logger.bulk_mark_as_resolved(
        error_ids=error_ids,
        resolved_by=user.get("email", "admin")
    )
    
    return {
        "success": True, 
        "resolved_count": resolved_count,
        "message": f"{resolved_count} erros marcados como resolvidos"
    }


async def run_resolve_all_system_errors(user: dict):
    """
    Marca TODOS os erros não resolvidos como resolvidos.
    Útil para limpar o painel de erros depois de uma manutenção.
    """
    from services.system_error_logger import system_error_logger
    resolved_count = await system_error_logger.resolve_all_unresolved(
        resolved_by=user.get("email", "admin")
    )
    
    return {
        "success": True,
        "resolved_count": resolved_count,
        "message": f"Todos os {resolved_count} erros foram marcados como resolvidos"
    }


async def run_cleanup_old_system_logs(user: dict, days: int = 90):
    """Remove logs antigos (mais de N dias)."""
    from services.system_error_logger import system_error_logger
    count = await system_error_logger.cleanup_old_errors(days)
    return {"success": True, "deleted_count": count}


async def run_cleanup_old_jobs(days: int, user: dict):
    """
    Remove jobs de background antigos (concluídos ou falhados).
    """
    from datetime import timedelta
    
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    
    result = await db.background_jobs.delete_many({
        "completed_at": {"$lt": cutoff},
        "status": {"$in": ["completed", "failed"]}
    })
    
    return {"success": True, "deleted_count": result.deleted_count}


async def run_cleanup_old_error_logs(days: int, user: dict):
    """
    Remove logs de erro antigos.
    """
    from datetime import timedelta
    
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    
    result = await db.system_error_logs.delete_many({
        "timestamp": {"$lt": cutoff}
    })
    
    return {"success": True, "deleted_count": result.deleted_count}


async def run_get_jobs_health(user: dict):
    """
    Verifica o estado dos jobs em background.
    Detecta jobs travados (em execução há muito tempo).
    """
    from datetime import timedelta
    
    # Definir thresholds
    stuck_threshold_minutes = 30  # Job é considerado travado após 30 minutos
    
    # Buscar jobs recentes
    now = datetime.now(timezone.utc)
    cutoff_time = now - timedelta(hours=24)  # Últimas 24 horas
    
    # Buscar AI import logs (jobs de importação)
    ai_import_logs = await db.ai_import_logs.find(
        {"start_time": {"$gte": cutoff_time.isoformat()}},
        {"_id": 0}
    ).sort("start_time", -1).to_list(100)
    
    # Analisar jobs
    running_jobs = []
    stuck_jobs = []
    completed_jobs = []
    failed_jobs = []
    
    for log in ai_import_logs:
        status = log.get("status", "").lower()
        start_time_str = log.get("start_time")
        
        if status in ["completed", "success", "done"]:
            completed_jobs.append(log)
        elif status in ["failed", "error"]:
            failed_jobs.append(log)
        elif status in ["processing", "running", "in_progress"]:
            # Verificar se está travado
            if start_time_str:
                try:
                    start_time = datetime.fromisoformat(start_time_str.replace('Z', '+00:00'))
                    duration_minutes = (now - start_time).total_seconds() / 60
                    
                    if duration_minutes > stuck_threshold_minutes:
                        stuck_jobs.append({
                            **log,
                            "duration_minutes": round(duration_minutes, 1)
                        })
                    else:
                        running_jobs.append({
                            **log,
                            "duration_minutes": round(duration_minutes, 1)
                        })
                except Exception:
                    running_jobs.append(log)
            else:
                running_jobs.append(log)
    
    # Calcular estatísticas
    total_jobs = len(ai_import_logs)
    success_rate = (len(completed_jobs) / total_jobs * 100) if total_jobs > 0 else 0
    
    return {
        "timestamp": now.isoformat(),
        "healthy": len(stuck_jobs) == 0,
        "stats": {
            "total_24h": total_jobs,
            "running": len(running_jobs),
            "stuck": len(stuck_jobs),
            "completed": len(completed_jobs),
            "failed": len(failed_jobs),
            "success_rate": round(success_rate, 1)
        },
        "stuck_jobs": stuck_jobs,
        "running_jobs": running_jobs,
        "alerts": [
            {
                "type": "stuck_job",
                "message": f"Job travado há {job.get('duration_minutes', 0)} minutos: {job.get('job_id', 'N/A')}",
                "job_id": job.get("job_id"),
                "severity": "warning"
            }
            for job in stuck_jobs
        ]
    }


async def run_cancel_stuck_job(job_id: str, user: dict):
    """
    Cancela/marca um job travado como falhado.
    """
    # Actualizar log para failed
    result = await db.ai_import_logs.update_one(
        {"job_id": job_id},
        {"$set": {
            "status": "cancelled",
            "end_time": datetime.now(timezone.utc).isoformat(),
            "cancelled_by": user.get("id"),
            "cancelled_at": datetime.now(timezone.utc).isoformat()
        }}
    )
    
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Job não encontrado")
    
    return {
        "success": True,
        "job_id": job_id,
        "message": "Job cancelado com sucesso"
    }


async def run_list_client_registrations(user: dict, page: int = 1, limit: int = 20, search: str = None, status: str = None, source: str = None):
    """
    Lista registos de clientes do formulário público.
    
    Query params:
    - page: Página (default 1)
    - limit: Items por página (default 20)
    - search: Pesquisar por nome, email ou NIF
    - status: Filtrar por estado do processo
    - source: Filtrar por origem (public_form, manual, etc.)
    """
    query = {}
    
    if search:
        query["$or"] = [
            {"client_name": {"$regex": search, "$options": "i"}},
            {"client_email": {"$regex": search, "$options": "i"}},
            {"personal_data.nif": {"$regex": search, "$options": "i"}}
        ]
    
    if status:
        query["status"] = status
    
    if source:
        query["source"] = source
    
    skip = (page - 1) * limit
    
    total = await db.processes.count_documents(query)
    
    processes = await db.processes.find(
        query,
        {"_id": 0}
    ).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    
    return {
        "registrations": processes,
        "total": total,
        "page": page,
        "limit": limit,
        "pages": (total + limit - 1) // limit
    }


async def run_get_client_registration(process_id: str, user: dict):
    """
    Obtém detalhes de um registo de cliente.
    """
    process = await db.processes.find_one(
        {"id": process_id},
        {"_id": 0}
    )
    
    if not process:
        raise HTTPException(status_code=404, detail="Registo não encontrado")
    
    return {"registration": process}


async def run_update_client_registration(process_id: str, data: dict, user: dict):
    """
    Atualiza dados de um registo de cliente.
    
    Permite editar:
    - Dados pessoais (personal_data)
    - Dados do 2º titular (titular2_data)
    - Dados do imóvel (real_estate_data)
    - Dados financeiros (financial_data)
    - Informações de contacto (client_name, client_email, client_phone)
    """
    process = await db.processes.find_one({"id": process_id})
    
    if not process:
        raise HTTPException(status_code=404, detail="Registo não encontrado")
    
    update_data = {}
    
    # Campos simples
    if "client_name" in data:
        update_data["client_name"] = data["client_name"]
    if "client_email" in data:
        update_data["client_email"] = data["client_email"]
    if "client_phone" in data:
        update_data["client_phone"] = data["client_phone"]
    if "second_client_name" in data:
        update_data["second_client_name"] = data["second_client_name"]
    
    # Campos aninhados
    if "personal_data" in data:
        # Manter dados existentes e actualizar apenas os fornecidos
        existing_personal = process.get("personal_data", {})
        existing_personal.update(data["personal_data"])
        update_data["personal_data"] = existing_personal
    
    if "titular2_data" in data:
        existing_titular2 = process.get("titular2_data", {}) or {}
        existing_titular2.update(data["titular2_data"])
        update_data["titular2_data"] = existing_titular2
    
    if "real_estate_data" in data:
        existing_realestate = process.get("real_estate_data", {}) or {}
        existing_realestate.update(data["real_estate_data"])
        update_data["real_estate_data"] = existing_realestate
    
    if "financial_data" in data:
        existing_financial = process.get("financial_data", {}) or {}
        existing_financial.update(data["financial_data"])
        update_data["financial_data"] = existing_financial
    
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    update_data["updated_by"] = user.get("email", "admin")
    
    await db.processes.update_one(
        {"id": process_id},
        {"$set": update_data}
    )
    
    # Log da alteração
    await db.history.insert_one({
        "id": str(uuid.uuid4()),
        "process_id": process_id,
        "user_id": user["id"],
        "user_name": user.get("name", "Admin"),
        "action": "Dados do registo editados pelo admin",
        "field": "registration_edit",
        "old_value": None,
        "new_value": list(update_data.keys()),
        "created_at": datetime.now(timezone.utc).isoformat()
    })
    
    updated = await db.processes.find_one({"id": process_id}, {"_id": 0})
    
    return {
        "success": True,
        "message": "Registo atualizado com sucesso",
        "registration": updated
    }


async def run_delete_client_registration(process_id: str, user: dict):
    """
    Elimina um registo de cliente.
    
    NOTA: Esta ação agora faz soft delete em vez de hard delete.
    O processo é marcado como eliminado mas permanece na base de dados.
    """
    process = await db.processes.find_one({"id": process_id})
    
    if not process:
        raise HTTPException(status_code=404, detail="Registo não encontrado")
    
    # Guardar log antes de eliminar
    await db.history.insert_one({
        "id": str(uuid.uuid4()),
        "process_id": process_id,
        "user_id": user["id"],
        "user_name": user.get("name", "Admin"),
        "action": f"Registo eliminado (soft delete): {process.get('client_name', 'N/A')} ({process.get('client_email', 'N/A')})",
        "field": "registration_delete",
        "old_value": process.get("client_name"),
        "new_value": None,
        "created_at": datetime.now(timezone.utc).isoformat()
    })
    
    # Soft delete: marcar processo como eliminado em vez de remover permanentemente
    await db.processes.update_one(
        {"id": process_id},
        {"$set": {"is_deleted": True, "status": "eliminado", "is_active": False, "deleted_at": datetime.now(timezone.utc), "deleted_by": user.get("id", "")}}
    )
    
    return {
        "success": True,
        "message": "Registo eliminado com sucesso"
    }


async def run_get_client_registrations_stats(user: dict):
    """
    Obtém estatísticas de registos de clientes.
    """
    # Total de registos
    total = await db.processes.count_documents({})
    
    # Registos por origem
    by_source = await db.processes.aggregate([
        {"$group": {"_id": "$source", "count": {"$sum": 1}}}
    ]).to_list(10)
    
    # Registos por estado
    by_status = await db.processes.aggregate([
        {"$group": {"_id": "$status", "count": {"$sum": 1}}}
    ]).to_list(50)
    
    # Registos hoje
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    today_count = await db.processes.count_documents({
        "created_at": {"$gte": today.isoformat()}
    })
    
    # Registos esta semana
    week_start = today - timedelta(days=today.weekday())
    week_count = await db.processes.count_documents({
        "created_at": {"$gte": week_start.isoformat()}
    })
    
    # Registos este mês
    month_start = today.replace(day=1)
    month_count = await db.processes.count_documents({
        "created_at": {"$gte": month_start.isoformat()}
    })
    
    return {
        "total": total,
        "today": today_count,
        "this_week": week_count,
        "this_month": month_count,
        "by_source": {item["_id"] or "unknown": item["count"] for item in by_source},
        "by_status": {item["_id"] or "unknown": item["count"] for item in by_status}
    }


async def run_get_audit_logs(user: dict, limit: int = 100, skip: int = 0, action: Optional[str] = None, entity: Optional[str] = None):
    """O18 - Lista de audit logs para acções críticas do sistema."""
    query = {}
    if action:
        query["action"] = action
    if entity:
        query["entity"] = entity
    
    logs = await db.audit_logs.find(query, {"_id": 0}).sort("timestamp", -1).skip(skip).limit(limit).to_list(length=limit)
    total = await db.audit_logs.count_documents(query)
    
    return {"logs": logs, "total": total, "limit": limit, "skip": skip}


async def run_get_stale_processes(user: dict, days: int = 14):
    """
    Obter estatísticas de processos sem atualização.
    Retorna processos agrupados por nível de urgência.
    """
    now = datetime.now(timezone.utc)
    # Fix: Normalize process status filters — combina a constante central
    # (todas as variações legadas singular/plural) com os termos extra
    # específicos deste relatório (recusado, escritura_feita, etc.).
    final_statuses = list(set(INACTIVE_STATUSES) | {
        "recusado", "desistiu", "desistência",
        "escritura_feita", "arquivado",
    })
    
    cutoff = (now - timedelta(days=days)).isoformat()
    
    stale = await db.processes.find({
        "status": {"$nin": final_statuses},
        "$or": [
            {"updated_at": {"$lte": cutoff}},
            {"updated_at": {"$exists": False}, "created_at": {"$lte": cutoff}}
        ]
    }, {"_id": 0, "id": 1, "client_name": 1, "status": 1, "consultor_name": 1, 
        "mediador_name": 1, "updated_at": 1, "created_at": 1}).to_list(500)
    
    # Calcular dias desde última actualização
    results = []
    for p in stale:
        last = p.get("updated_at") or p.get("created_at", "")
        try:
            last_date = datetime.fromisoformat(last.replace('Z', '+00:00'))
            days_since = (now - last_date).days
        except (ValueError, TypeError, AttributeError):
            days_since = days
        
        results.append({
            "id": p["id"],
            "client_name": p.get("client_name", ""),
            "status": p.get("status", ""),
            "consultor_name": p.get("consultor_name", ""),
            "mediador_name": p.get("mediador_name", ""),
            "days_since_update": days_since,
            "urgency": "critical" if days_since > 21 else "high" if days_since > 14 else "medium"
        })
    
    results.sort(key=lambda x: x["days_since_update"], reverse=True)
    
    return {
        "total": len(results),
        "critical": len([r for r in results if r["urgency"] == "critical"]),
        "high": len([r for r in results if r["urgency"] == "high"]),
        "medium": len([r for r in results if r["urgency"] == "medium"]),
        "processes": results[:100]
    }


async def run_get_team_performance(user: dict, start_date: Optional[str] = None, end_date: Optional[str] = None):
    """
    Obter estatísticas de desempenho da equipa para um dado período.
    Retorna a lista de colaboradores com: processos avançados,
    tarefas concluídas, tarefas atrasadas e tarefas pendentes.

    Reutiliza a lógica de agregação do analytics_service.
    """
    from services.analytics_service import generate_weekly_team_report

    now = datetime.now(timezone.utc)

    # Parse dates with defaults
    if end_date:
        try:
            end_dt = datetime.strptime(end_date, "%Y-%m-%d").replace(
                hour=23, minute=59, second=59, tzinfo=timezone.utc
            )
        except ValueError:
            raise HTTPException(status_code=422, detail="end_date inválido. Use YYYY-MM-DD")
    else:
        end_dt = now

    if start_date:
        try:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d").replace(
                hour=0, minute=0, second=0, tzinfo=timezone.utc
            )
        except ValueError:
            raise HTTPException(status_code=422, detail="start_date inválido. Use YYYY-MM-DD")
    else:
        start_dt = end_dt - timedelta(days=7)

    if start_dt >= end_dt:
        raise HTTPException(status_code=422, detail="start_date deve ser anterior a end_date")

    report = await generate_weekly_team_report(db, period_start=start_dt, period_end=end_dt)

    return {
        "period_start": report["period_start"],
        "period_end": report["period_end"],
        "summary": report["summary"],
        "users": report["users"],
    }



"""System-level diagnostics endpoints.

Extraído de `routes/diagnostics.py`.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from database import db
from services.diagnostics_helpers import ServiceStatus, SystemDiagnostics
from services.diagnostics_checks import (
    check_email_service,
    check_storage_service,
    check_ai_service,
    check_backup_service,
    check_notifications_service,
)

logger = logging.getLogger(__name__)


async def run_get_system_diagnostics() -> SystemDiagnostics:
    """
    Obtém diagnóstico completo do sistema.

    Retorna o estado de todos os serviços e últimos erros.
    """
    services = {}

    # Verificar cada serviço com tratamento de erros
    try:
        services["email"] = await check_email_service()
    except Exception as e:
        logger.error(f"Erro ao verificar email: {e}")
        services["email"] = ServiceStatus(
            name="Email (SMTP)",
            configured=False,
            status="error",
            message=f"Erro ao verificar: {str(e)}"
        )

    try:
        services["storage"] = await check_storage_service()
    except Exception as e:
        logger.error(f"Erro ao verificar storage: {e}")
        services["storage"] = ServiceStatus(
            name="Armazenamento",
            configured=False,
            status="error",
            message=f"Erro ao verificar: {str(e)}"
        )

    try:
        services["ai"] = await check_ai_service()
    except Exception as e:
        logger.error(f"Erro ao verificar AI: {e}")
        services["ai"] = ServiceStatus(
            name="Inteligência Artificial",
            configured=False,
            status="error",
            message=f"Erro ao verificar: {str(e)}"
        )

    try:
        services["backup"] = await check_backup_service()
    except Exception as e:
        logger.error(f"Erro ao verificar Backup: {e}")
        services["backup"] = ServiceStatus(
            name="Sistema de Backup",
            configured=False,
            status="error",
            message=f"Erro ao verificar: {str(e)}"
        )

    try:
        services["notifications"] = await check_notifications_service()
    except Exception as e:
        logger.error(f"Erro ao verificar Notifications: {e}")
        services["notifications"] = ServiceStatus(
            name="Notificações",
            configured=False,
            status="error",
            message=f"Erro ao verificar: {str(e)}"
        )

    # Buscar erros recentes
    recent_errors = []
    try:
        collections = await db.list_collection_names()
        if "system_error_logs" in collections:
            errors = await db.system_error_logs.find(
                {},
                {"_id": 0}
            ).sort("timestamp", -1).limit(10).to_list(10)
            recent_errors = errors
    except Exception as e:
        logger.error(f"Erro ao buscar logs de erros: {e}")

    # Resumo - não contar serviços desativados intencionalmente
    summary = {
        "ok": sum(1 for s in services.values() if s.status == "ok"),
        "warning": sum(1 for s in services.values() if s.status == "warning"),
        "error": sum(1 for s in services.values() if s.status == "error"),
        "not_configured": sum(1 for s in services.values() if s.status == "not_configured"),
        "disabled": sum(1 for s in services.values() if s.status == "disabled")
    }

    return SystemDiagnostics(
        timestamp=datetime.now(timezone.utc).isoformat(),
        services=services,
        recent_errors=recent_errors,
        summary=summary
    )


async def run_get_service_diagnostics(service_name: str):
    """
    Obtém diagnóstico detalhado de um serviço específico.
    """
    checkers = {
        "email": check_email_service,
        "storage": check_storage_service,
        "ai": check_ai_service,
        "backup": check_backup_service,
        "notifications": check_notifications_service
    }

    if service_name not in checkers:
        return {"error": f"Serviço '{service_name}' não encontrado", "available": list(checkers.keys())}

    status = await checkers[service_name]()

    # Adicionar informação extra dependendo do serviço
    extra_info = {}

    if service_name == "email":
        # Últimos 5 emails
        emails = await db.emails.find(
            {},
            {"_id": 0, "id": 1, "subject": 1, "to_address": 1, "created_at": 1, "status": 1}
        ).sort("created_at", -1).limit(5).to_list(5)
        extra_info["recent_emails"] = emails

    elif service_name == "backup":
        # Últimos 5 backups
        backups = await db.backup_history.find(
            {},
            {"_id": 0, "id": 1, "status": 1, "started_at": 1, "completed_at": 1, "trigger_type": 1}
        ).sort("started_at", -1).limit(5).to_list(5)
        extra_info["recent_backups"] = backups

    # Trello integration removed (deprecated)

    return {
        "service": status.dict(),
        "extra": extra_info,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


async def run_quick_system_check():
    """
    Verificação rápida do sistema (para qualquer utilizador staff).

    Retorna apenas o resumo sem detalhes sensíveis.
    Ignora serviços desativados intencionalmente.
    """
    services = {}

    # Verificar cada serviço (apenas status básico)
    services["email"] = (await check_email_service()).status
    services["storage"] = (await check_storage_service()).status
    services["ai"] = (await check_ai_service()).status
    # Todos os serviços activos verificados
    services["backup"] = (await check_backup_service()).status

    # Contagens básicas
    stats = {
        "processes": await db.processes.count_documents({}),
        "users": await db.users.count_documents({}),
        "documents": await db.documents.count_documents({}) if "documents" in await db.list_collection_names() else 0
    }

    return {
        "status": "healthy" if all(s in ["ok", "warning"] for s in services.values()) else "issues",
        "services": services,
        "stats": stats,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

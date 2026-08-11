"""Service health checkers for diagnostics.

Extraído de `routes/diagnostics.py`.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta

from database import db
from services.diagnostics_helpers import ServiceStatus, datetime_to_str

logger = logging.getLogger(__name__)


async def check_email_service() -> ServiceStatus:
    """Verificar estado do serviço de email."""
    config = await db.system_config.find_one({}, {"_id": 0, "email": 1})
    email_config = config.get("email", {}) if config else {}

    # Verificar campos obrigatórios (usar nomes corretos do modelo)
    # Nota: smtp_server é o nome correto (não smtp_host)
    required = ["smtp_server", "smtp_port", "smtp_user", "smtp_password"]
    missing = [f for f in required if not email_config.get(f)]

    # Se não tem configuração completa, verificar se tem pelo menos uma conta secundária
    if missing:
        # Verificar conta secundária (smtp_server_2, etc.)
        required_2 = ["smtp_server_2", "smtp_port_2", "smtp_user_2", "smtp_password_2"]
        has_secondary = all(email_config.get(f) for f in required_2)

        if not has_secondary:
            return ServiceStatus(
                name="Email (SMTP)",
                configured=False,
                status="not_configured",
                message=f"Campos em falta: {', '.join(missing)}",
                config_fields=missing
            )

    # Contar emails enviados
    total_emails = await db.emails.count_documents({})
    last_email = await db.emails.find_one(
        {},
        {"_id": 0, "created_at": 1, "subject": 1},
        sort=[("created_at", -1)]
    )

    return ServiceStatus(
        name="Email (SMTP)",
        configured=True,
        status="ok",
        message="Serviço configurado",
        last_activity=datetime_to_str(last_email.get("created_at")) if last_email else None,
        stats={
            "total_emails": total_emails,
            "last_email_subject": last_email.get("subject", "N/A") if last_email else None
        }
    )


async def check_storage_service() -> ServiceStatus:
    """Verificar estado do serviço de armazenamento (S3 ou OneDrive)."""
    config = await db.system_config.find_one({}, {"_id": 0, "storage": 1})
    storage_config = config.get("storage", {}) if config else {}

    provider = storage_config.get("provider", "")

    if provider == "aws_s3":
        required = ["aws_access_key_id", "aws_secret_access_key", "aws_bucket_name"]
        missing = [f for f in required if not storage_config.get(f)]

        if missing:
            return ServiceStatus(
                name="Armazenamento (AWS S3)",
                configured=False,
                status="not_configured",
                message=f"Campos em falta: {', '.join(missing)}",
                config_fields=missing
            )

        # Contar documentos
        total_docs = await db.documents.count_documents({})

        return ServiceStatus(
            name="Armazenamento (AWS S3)",
            configured=True,
            status="ok",
            message=f"Bucket: {storage_config.get('aws_bucket_name', 'N/A')}",
            stats={"total_documents": total_docs}
        )

    elif provider == "onedrive":
        # OneDrive é opcional - apenas mostrar status informativo
        if not storage_config.get("onedrive_shared_url"):
            return ServiceStatus(
                name="Armazenamento (OneDrive)",
                configured=False,
                status="not_configured",
                message="OneDrive não configurado (opcional - use AWS S3 como principal)",
                config_fields=["onedrive_shared_url"]
            )

        return ServiceStatus(
            name="Armazenamento (OneDrive)",
            configured=True,
            status="ok",
            message="OneDrive configurado"
        )

    elif provider == "none" or not provider:
        # Nenhum provider configurado - mostrar como informação
        return ServiceStatus(
            name="Armazenamento",
            configured=False,
            status="not_configured",
            message="Configure AWS S3 para armazenamento de documentos",
            config_fields=["provider"]
        )

    # Outros providers
    return ServiceStatus(
        name=f"Armazenamento ({provider})",
        configured=True,
        status="ok",
        message=f"Provider: {provider}"
    )


async def check_ai_service() -> ServiceStatus:
    """Verificar estado do serviço de IA."""
    config = await db.system_config.find_one({}, {"_id": 0, "ai": 1})
    ai_config = config.get("ai", {}) if config else {}

    if not ai_config.get("api_key"):
        return ServiceStatus(
            name="Inteligência Artificial",
            configured=False,
            status="not_configured",
            message="Chave API não configurada",
            config_fields=["api_key"]
        )

    provider = ai_config.get("provider", "openai")
    model = ai_config.get("model", "gpt-4o-mini")

    # Contar análises feitas
    total_analyses = await db.ai_analyses.count_documents({}) if "ai_analyses" in await db.list_collection_names() else 0

    return ServiceStatus(
        name="Inteligência Artificial",
        configured=True,
        status="ok",
        message=f"Provider: {provider}, Modelo: {model}",
        stats={"total_analyses": total_analyses}
    )


async def check_backup_service() -> ServiceStatus:
    """Verificar estado do serviço de backup."""
    # Verificar último backup
    last_backup = await db.backup_history.find_one(
        {"status": "completed"},
        {"_id": 0, "completed_at": 1, "result": 1},
        sort=[("completed_at", -1)]
    )

    total_backups = await db.backup_history.count_documents({"status": "completed"})

    if not last_backup:
        return ServiceStatus(
            name="Sistema de Backup",
            configured=True,
            status="warning",
            message="Nenhum backup realizado ainda",
            stats={"total_backups": 0}
        )

    # Verificar se o último backup foi há mais de 2 dias
    last_date_raw = last_backup.get("completed_at")
    last_date_str = None

    if last_date_raw:
        # Converter datetime para string se necessário
        if isinstance(last_date_raw, datetime):
            last_date_str = last_date_raw.isoformat()
        else:
            last_date_str = str(last_date_raw)

        try:
            # Parse para calcular dias
            if isinstance(last_date_raw, datetime):
                last_dt = last_date_raw
            else:
                last_dt = datetime.fromisoformat(str(last_date_raw).replace("Z", "+00:00"))

            # Garantir timezone awareness
            if last_dt.tzinfo is None:
                last_dt = last_dt.replace(tzinfo=timezone.utc)

            days_ago = (datetime.now(timezone.utc) - last_dt).days

            if days_ago > 2:
                return ServiceStatus(
                    name="Sistema de Backup",
                    configured=True,
                    status="warning",
                    message=f"Último backup há {days_ago} dias",
                    last_activity=last_date_str,
                    stats={"total_backups": total_backups, "days_since_last": days_ago}
                )
        except Exception as e:
            logger.warning(f"Erro ao processar data do backup: {e}")

    return ServiceStatus(
        name="Sistema de Backup",
        configured=True,
        status="ok",
        message="Backup automático activo (03:00 UTC)",
        last_activity=last_date_str,
        stats={
            "total_backups": total_backups,
            "s3_uploaded": last_backup.get("result", {}).get("uploaded", False)
        }
    )


async def check_notifications_service() -> ServiceStatus:
    """Verificar estado do serviço de notificações."""
    # Verificar notificações recentes
    recent_count = await db.notifications.count_documents({
        "created_at": {"$gte": (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()}
    }) if "notifications" in await db.list_collection_names() else 0

    total_count = await db.notifications.count_documents({}) if "notifications" in await db.list_collection_names() else 0

    return ServiceStatus(
        name="Notificações",
        configured=True,
        status="ok",
        message="Sistema de notificações activo",
        stats={
            "total": total_count,
            "last_7_days": recent_count
        }
    )

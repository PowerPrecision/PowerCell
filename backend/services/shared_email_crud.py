"""CRUD handlers for admin shared-email configs.

Extraído de `routes/shared_email.py`.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import HTTPException

from database import db
from services.encryption import encryption_service
from models.shared_email_config import (
    SharedEmailConfigCreate,
    SharedEmailConfigResponse,
    SharedEmailConfigListResponse,
)
from services.shared_email_helpers import ALLOWED_ROLES, _require_admin

logger = logging.getLogger(__name__)


async def run_list_shared_email_configs(current_user: dict) -> SharedEmailConfigListResponse:
    """Listar todas as configurações de email partilhado."""
    _require_admin(current_user)

    configs = await db.shared_role_email_configs.find({}, {"_id": 0}).to_list(50)

    response_list = []
    for cfg in configs:
        response_list.append(SharedEmailConfigResponse(
            role=cfg.get("role", ""),
            email_address=cfg.get("email_address"),
            display_name=cfg.get("display_name"),
            is_configured=cfg.get("is_configured", False),
            auth_method=cfg.get("auth_method", "none"),
            has_google_oauth=bool(cfg.get("google_refresh_token")),
            google_email=cfg.get("google_email"),
            has_imap_password=bool(cfg.get("encrypted_password")),
            oauth_connected_at=cfg.get("oauth_connected_at"),
            last_sync_at=cfg.get("last_sync_at"),
            total_emails_synced=cfg.get("total_emails_synced", 0),
            updated_at=cfg.get("updated_at"),
        ))

    return SharedEmailConfigListResponse(configs=response_list, total=len(response_list))


async def run_get_shared_email_config(role: str, current_user: dict) -> SharedEmailConfigResponse:
    """Obter configuração de email partilhado para um role."""
    _require_admin(current_user)

    if role not in ALLOWED_ROLES:
        raise HTTPException(status_code=400, detail=f"Role '{role}' não permitido. Roles: {ALLOWED_ROLES}")

    cfg = await db.shared_role_email_configs.find_one({"role": role}, {"_id": 0})
    if not cfg:
        return SharedEmailConfigResponse(role=role)

    return SharedEmailConfigResponse(
        role=cfg.get("role", role),
        email_address=cfg.get("email_address"),
        display_name=cfg.get("display_name"),
        is_configured=cfg.get("is_configured", False),
        auth_method=cfg.get("auth_method", "none"),
        has_google_oauth=bool(cfg.get("google_refresh_token")),
        google_email=cfg.get("google_email"),
        has_imap_password=bool(cfg.get("encrypted_password")),
        oauth_connected_at=cfg.get("oauth_connected_at"),
        last_sync_at=cfg.get("last_sync_at"),
        total_emails_synced=cfg.get("total_emails_synced", 0),
        updated_at=cfg.get("updated_at"),
    )


async def run_upsert_shared_email_config(
    role: str,
    payload: SharedEmailConfigCreate,
    current_user: dict,
) -> SharedEmailConfigResponse:
    """Criar ou atualizar configuração de email partilhado (IMAP/SMTP)."""
    _require_admin(current_user)

    if role not in ALLOWED_ROLES:
        raise HTTPException(status_code=400, detail=f"Role '{role}' não permitido. Roles: {ALLOWED_ROLES}")

    existing = await db.shared_role_email_configs.find_one({"role": role}, {"_id": 0})

    now = datetime.now(timezone.utc).isoformat()

    update_data = {
        "role": role,
        "email_address": payload.email_address,
        "display_name": payload.display_name or f"Email {role}",
        "imap_server": payload.imap_server,
        "imap_port": payload.imap_port,
        "smtp_server": payload.smtp_server,
        "smtp_port": payload.smtp_port,
        "updated_at": now,
    }

    # Encriptar password se fornecida (não apaga a existente se vazio)
    if payload.encrypted_password:
        if not payload.encrypted_password.startswith("ENC:"):
            update_data["encrypted_password"] = encryption_service.encrypt(payload.encrypted_password)
        else:
            update_data["encrypted_password"] = payload.encrypted_password

    # Se já existe, preservar campos OAuth
    if existing:
        update_data.setdefault("google_refresh_token", existing.get("google_refresh_token", ""))
        update_data.setdefault("google_email", existing.get("google_email", ""))
        update_data.setdefault("auth_method", existing.get("auth_method", "none"))
        update_data.setdefault("oauth_connected_at", existing.get("oauth_connected_at", ""))
        update_data.setdefault("total_emails_synced", existing.get("total_emails_synced", 0))

    # Determinar se está configurado
    has_oauth = bool(update_data.get("google_refresh_token"))
    has_imap = bool(update_data.get("encrypted_password"))
    update_data["is_configured"] = has_oauth or has_imap
    if has_oauth:
        update_data["auth_method"] = "google_oauth"
    elif has_imap:
        update_data["auth_method"] = "imap_smtp"

    await db.shared_role_email_configs.update_one(
        {"role": role},
        {"$set": update_data},
        upsert=True,
    )

    # Audit log
    await db.audit_logs.insert_one({
        "action": "shared_email_config_updated",
        "user_id": current_user["id"],
        "details": {"role": role, "auth_method": update_data["auth_method"]},
        "created_at": now,
    })

    logger.info(f"[Shared Email] Config atualizada para role '{role}' por {current_user['id']}")

    return SharedEmailConfigResponse(
        **update_data,
        has_google_oauth=has_oauth,
        has_imap_password=has_imap,
    )


async def run_delete_shared_email_config(role: str, current_user: dict) -> dict:
    """Remover configuração de email partilhado."""
    _require_admin(current_user)

    result = await db.shared_role_email_configs.delete_one({"role": role})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail=f"Config para role '{role}' não encontrada")

    logger.info(f"[Shared Email] Config removida para role '{role}' por {current_user['id']}")

    return {"success": True, "message": f"Config para role '{role}' removida"}

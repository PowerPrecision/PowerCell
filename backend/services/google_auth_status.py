"""Google OAuth status + disconnect handlers (user Gmail).

Extraído de `routes/google_auth.py`. Prefer `google_auth_*` — do **not**
overwrite existing `gmail_oauth.py` / `gmail_api_service.py`.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import HTTPException, Request

from database import db

logger = logging.getLogger(__name__)


def _resolve_storage_key(request: Request, user_role: str) -> str:
    """Prefer company:<id> when X-Company-Id is set; else role/default."""
    company_id = (request.headers.get("X-Company-Id") or "").strip()
    if company_id and company_id != "default":
        return f"company:{company_id}"
    active_role_header = request.headers.get("X-Active-Role", "")
    if active_role_header and active_role_header != user_role:
        return active_role_header
    return "default"


async def run_google_oauth_status(request: Request, current_user: dict) -> dict:
    """
    Verifica o estado da ligação Google OAuth do utilizador.

    Prefers company key when X-Company-Id is present; falls back to role.
    """
    from services.email_config_resolver import (
        _extract_role_email_config,
    )

    user_id = current_user["id"]
    user_role = current_user.get("role", "")
    user = await db.users.find_one(
        {"id": user_id},
        {"_id": 0, "email_config": 1},
    )

    if not user or not user.get("email_config"):
        return {
            "connected": False,
            "auth_method": "none",
            "google_email": None,
            "has_refresh_token": False,
        }

    storage_key = _resolve_storage_key(request, user_role)
    raw_config = user["email_config"]

    # Prefer explicit company key when nested
    if storage_key.startswith("company:") and isinstance(raw_config.get(storage_key), dict):
        config = raw_config[storage_key]
    else:
        active_role = storage_key if storage_key != "default" else None
        config = _extract_role_email_config(raw_config, active_role)

    refresh_token_enc = config.get("google_refresh_token", "")

    return {
        "connected": bool(refresh_token_enc),
        "auth_method": config.get("auth_method", "none"),
        "google_email": config.get("google_email"),
        "email_address": config.get("email_address"),
        "has_refresh_token": bool(refresh_token_enc),
        "oauth_connected_at": config.get("oauth_connected_at"),
    }


async def run_google_oauth_disconnect(request: Request, current_user: dict) -> dict:
    """
    Remove os tokens Google OAuth do utilizador.
    Mantém a configuração IMAP/SMTP existente (para fallback).

    Prefers company key when X-Company-Id is present.
    """
    from services.email_config_resolver import (
        _is_nested_email_config,
    )

    user_id = current_user["id"]
    user_role = current_user.get("role", "")
    storage_role = _resolve_storage_key(request, user_role)

    # Load existing config
    existing_user = await db.users.find_one(
        {"id": user_id}, {"_id": 0, "email_config": 1}
    )
    raw_config = (existing_user or {}).get("email_config", {})

    if not raw_config:
        raise HTTPException(status_code=400, detail="Sem configuração de email")

    # Normalize
    if _is_nested_email_config(raw_config):
        nested_config = raw_config
    else:
        nested_config = {"default": raw_config}

    # Clear OAuth fields from the company/role-specific sub-config
    role_config = nested_config.get(storage_role)
    if role_config and isinstance(role_config, dict):
        role_config["google_refresh_token"] = ""
        role_config["google_access_token"] = ""
        role_config["google_email"] = ""
        role_config["oauth_connected_at"] = ""
        role_config["updated_at"] = datetime.now(timezone.utc).isoformat()
        # Remove auth_method if it was google_oauth
        if role_config.get("auth_method", "").startswith("google_oauth"):
            role_config["auth_method"] = role_config.get("auth_method", "").replace("google_oauth", "none") or "none"

        await db.users.update_one(
            {"id": user_id},
            {"$set": {"email_config": nested_config}},
        )
    else:
        # Fallback: use dot notation for flat config
        await db.users.update_one(
            {"id": user_id},
            {
                "$set": {
                    "email_config.google_refresh_token": "",
                    "email_config.google_access_token": "",
                    "email_config.google_email": "",
                    "email_config.auth_method": "none",
                    "email_config.oauth_connected_at": "",
                    "email_config.updated_at": datetime.now(timezone.utc).isoformat(),
                }
            },
        )

    # Audit log
    await db.audit_logs.insert_one({
        "action": "google_oauth_disconnected",
        "user_id": user_id,
        "details": {"storage_key": storage_role},
        "created_at": datetime.now(timezone.utc).isoformat(),
    })

    logger.info(f"[Google OAuth] Utilizador {user_id} desconectou Google OAuth")

    return {"success": True, "message": "Google OAuth desconectado"}

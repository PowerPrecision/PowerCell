"""User email-config get / save / test handlers.

Extraído de `routes/users.py`.
Preserves multi-empresa resolution, dual-write, and FORCED_SHARED_ROLES blocks.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException, Request

from database import db
from models.email_config import EmailConfigCreate
from services.users_api_helpers import FORCED_SHARED_ROLES


def _resolve_active_role(request: Request, user_role: str) -> Optional[str]:
    active_role_header = request.headers.get("X-Active-Role", "")
    if active_role_header and active_role_header != user_role:
        return active_role_header
    return None


async def run_get_my_email_config(
    request: Request,
    company_id: Optional[str],
    current_user: dict,
):
    """Obter configuração de email do utilizador logado (sem secrets)."""
    from services.email_config_resolver import resolve_email_config
    from services.auth import get_active_company_id_async, get_effective_role
    from services.user_email_config_service import get_user_companies_with_config

    user_id = current_user["id"]
    user_role = current_user.get("role", "")
    # Prefer effective role (X-Active-Role) for FORCED_SHARED and nested resolution
    effective_role = get_effective_role(request, current_user)
    active_role = _resolve_active_role(request, user_role) or (
        effective_role if effective_role != user_role else None
    )

    header_company_id = await get_active_company_id_async(request, current_user)
    active_company_id = company_id or header_company_id

    if effective_role in FORCED_SHARED_ROLES:
        resolved = await resolve_email_config(
            user_id, active_role=effective_role, active_company_id=active_company_id,
        )
        return {
            "config_source": resolved.get("config_source", "none"),
            "is_configured": (
                resolved.get("has_password") or resolved.get("has_google_oauth")
            ),
            "email_address": resolved.get("email_address"),
            "imap_server": resolved.get("imap_server"),
            "imap_port": resolved.get("imap_port", 993),
            "smtp_server": resolved.get("smtp_server"),
            "smtp_port": resolved.get("smtp_port", 465),
            "has_password": resolved.get("has_password", False),
            "has_google_oauth": resolved.get("has_google_oauth", False),
            "auth_method": resolved.get("auth_method", "none"),
            "google_email": resolved.get("google_email"),
            "oauth_connected_at": resolved.get("oauth_connected_at"),
            "shared_role": effective_role,
            "managed_centralized": True,
            "company_name": resolved.get("company_name"),
            "display_name": resolved.get("display_name"),
            "company_id": resolved.get("resolved_company_id", active_company_id),
        }

    resolved = await resolve_email_config(
        user_id, active_role=active_role, active_company_id=active_company_id,
    )
    source = resolved.get("config_source", "none")

    available_companies = await get_user_companies_with_config(user_id)

    if not available_companies:
        existing_user_doc = await db.users.find_one(
            {"id": user_id},
            {"_id": 0, "email_config": 1},
        )
        raw_ec = (existing_user_doc or {}).get("email_config", {})
        if isinstance(raw_ec, dict):
            for key in raw_ec.keys():
                if key.startswith("company:"):
                    cid = key.replace("company:", "")
                    if cid not in available_companies:
                        available_companies.append(cid)
                elif key == "default":
                    if "default" not in available_companies:
                        available_companies.append("default")

    resolved_company_id = (
        resolved.get("resolved_company_id", active_company_id) or "default"
    )

    return {
        "config_source": source,
        "is_configured": (
            resolved.get("has_password") or resolved.get("has_google_oauth")
        ),
        "email_address": resolved.get("email_address"),
        "imap_server": resolved.get("imap_server"),
        "imap_port": resolved.get("imap_port", 993),
        "smtp_server": resolved.get("smtp_server"),
        "smtp_port": resolved.get("smtp_port", 465),
        "has_password": resolved.get("has_password", False),
        "has_google_oauth": resolved.get("has_google_oauth", False),
        "auth_method": resolved.get("auth_method", "none"),
        "google_email": resolved.get("google_email"),
        "oauth_connected_at": resolved.get("oauth_connected_at"),
        "company_name": resolved.get("company_name"),
        "company_id": resolved_company_id,
        "available_companies": available_companies or ["default"],
    }


async def run_save_my_email_config(
    request: Request,
    config: EmailConfigCreate,
    current_user: dict,
):
    """Guardar configuração de email (dual-write + encryption)."""
    from services.encryption import encryption_service
    from services.email_config_resolver import (
        _is_nested_email_config,
        _extract_role_email_config,
    )
    from services.user_email_config_service import upsert_user_email_config
    from services.auth import get_active_company_id_async, get_effective_role

    user_id = current_user["id"]
    user_role = current_user.get("role", "")
    effective_role = get_effective_role(request, current_user)

    if effective_role in FORCED_SHARED_ROLES:
        raise HTTPException(
            status_code=403,
            detail=(
                "O seu acesso ao email é gerido centralmente pelo departamento. "
                "Contacte o Administrador para alterações na configuração de email."
            ),
        )

    company_id = config.company_id or "default"
    if company_id == "default":
        try:
            header_company = await get_active_company_id_async(request, current_user)
            if header_company:
                company_id = header_company
        except Exception:
            pass

    active_role_header = request.headers.get("X-Active-Role", "")
    if active_role_header and active_role_header != user_role:
        storage_role = active_role_header
    else:
        storage_role = "default"

    # Canonical key is (user_id, company_id) — prefer company over role when set
    if company_id != "default":
        storage_key = f"company:{company_id}"
    else:
        storage_key = storage_role

    existing_user = await db.users.find_one(
        {"id": user_id},
        {"_id": 0, "email_config": 1},
    )
    raw_existing = (existing_user or {}).get("email_config", {})

    if raw_existing and not _is_nested_email_config(raw_existing):
        nested_existing = {"default": raw_existing}
    elif raw_existing:
        nested_existing = raw_existing
    else:
        nested_existing = {}

    existing_role_config = (
        _extract_role_email_config(nested_existing, storage_key)
        if storage_key != "default"
        else nested_existing.get("default", {})
    )

    if config.password:
        encrypted_password = encryption_service.encrypt(config.password)
    elif existing_role_config.get("encrypted_password"):
        encrypted_password = existing_role_config["encrypted_password"]
    else:
        encrypted_password = ""

    await upsert_user_email_config(
        user_id=user_id,
        company_id=company_id,
        email_address=config.email_address.strip().lower(),
        imap_server=config.imap_server.strip(),
        imap_port=config.imap_port,
        smtp_server=config.smtp_server.strip(),
        smtp_port=config.smtp_port,
        encrypted_password=encrypted_password,
        google_refresh_token=existing_role_config.get("google_refresh_token"),
        google_access_token=existing_role_config.get("google_access_token"),
        google_email=existing_role_config.get("google_email"),
        auth_method=existing_role_config.get("auth_method", "none"),
        oauth_connected_at=existing_role_config.get("oauth_connected_at"),
        is_configured=True,
    )

    new_role_config = {
        "email_address": config.email_address.strip().lower(),
        "imap_server": config.imap_server.strip(),
        "imap_port": config.imap_port,
        "smtp_server": config.smtp_server.strip(),
        "smtp_port": config.smtp_port,
        "encrypted_password": encrypted_password,
        "company_id": company_id,
        "is_configured": True,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    for oauth_key in (
        "google_refresh_token",
        "google_access_token",
        "google_email",
        "auth_method",
        "oauth_connected_at",
    ):
        if existing_role_config.get(oauth_key):
            new_role_config[oauth_key] = existing_role_config[oauth_key]

    nested_existing[storage_key] = new_role_config

    await db.users.update_one(
        {"id": user_id},
        {"$set": {"email_config": nested_existing}},
    )

    return {
        "success": True,
        "message": "Configuração guardada com sucesso",
        "is_configured": True,
        "company_id": company_id,
    }


async def run_test_my_email_config(
    request: Request,
    company_id: Optional[str],
    current_user: dict,
):
    """Testar ligação de email (Gmail OAuth ou IMAP/SMTP)."""
    from services.gmail_oauth import test_connection_smart
    from services.email_config_resolver import resolve_email_config_for_sync
    from services.auth import get_active_company_id_async, get_effective_role

    user_id = current_user["id"]
    user_role = current_user.get("role", "")
    effective_role = get_effective_role(request, current_user)
    active_role = _resolve_active_role(request, user_role) or (
        effective_role if effective_role != user_role else None
    )

    header_company_id = await get_active_company_id_async(request, current_user)
    active_company_id = company_id or header_company_id

    if effective_role in FORCED_SHARED_ROLES:
        resolved = await resolve_email_config_for_sync(
            user_id, active_role=effective_role, active_company_id=active_company_id,
        )
        if not resolved:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Configuração de email do departamento não disponível. "
                    "Contacte o Administrador."
                ),
            )
        test_config = {
            "email_address": resolved.get("email_address"),
            "imap_server": resolved.get("imap_server"),
            "imap_port": resolved.get("imap_port", 993),
            "smtp_server": resolved.get("smtp_server"),
            "smtp_port": resolved.get("smtp_port", 465),
            "encrypted_password": resolved.get("encrypted_password", ""),
            "google_refresh_token": resolved.get("google_refresh_token"),
        }
        return await test_connection_smart(test_config, user_id)

    resolved = await resolve_email_config_for_sync(
        user_id, active_role=active_role, active_company_id=active_company_id,
    )
    if not resolved:
        raise HTTPException(
            status_code=400, detail="Configuração de email não encontrada",
        )

    test_config = {
        "email_address": resolved.get("email_address"),
        "imap_server": resolved.get("imap_server"),
        "imap_port": resolved.get("imap_port", 993),
        "smtp_server": resolved.get("smtp_server"),
        "smtp_port": resolved.get("smtp_port", 465),
        "encrypted_password": resolved.get("encrypted_password", ""),
        "google_refresh_token": resolved.get("google_refresh_token"),
    }
    return await test_connection_smart(test_config, user_id)

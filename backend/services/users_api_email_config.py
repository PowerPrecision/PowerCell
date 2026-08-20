"""User email-config get / save / test handlers.

Extraído de `routes/users.py`.
Preserves multi-empresa resolution, dual-write, and FORCED_SHARED_ROLES blocks.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException, Request

from database import db
from models.email_config import EmailConfigCreate
from services.users_api_helpers import FORCED_SHARED_ROLES

logger = logging.getLogger(__name__)


def _non_default_company_id(*candidates: Optional[str]) -> Optional[str]:
    """Primeiro company_id útil (não vazio e diferente de 'default')."""
    for value in candidates:
        if not value:
            continue
        cleaned = str(value).strip()
        if cleaned and cleaned != "default":
            return cleaned
    return None


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
    from services.user_email_config_service import (
        get_user_companies_with_config,
        get_user_email_config,
        list_company_email_configs,
        publicize_email_account,
    )

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

    account_docs = await list_company_email_configs(user_id, resolved_company_id)
    accounts = [publicize_email_account(doc) for doc in account_docs]
    primary_doc = await get_user_email_config(user_id, resolved_company_id)

    return {
        "config_source": source,
        "is_configured": (
            resolved.get("has_password") or resolved.get("has_google_oauth")
        ),
        "id": (primary_doc or {}).get("id"),
        "is_primary": bool((primary_doc or {}).get("is_primary", True)),
        "label": (primary_doc or {}).get("label"),
        "accounts": accounts,
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
    query_company_id: Optional[str] = None,
):
    """Guardar configuração de email (dual-write + encryption).

    PACOTE DM: o company_id é resolvido por ordem isolada do UCR da tab:
      1) body.company_id  2) query ?company_id=  3) header X-Company-Id
    """
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

    header_company = None
    try:
        header_company = await get_active_company_id_async(request, current_user)
    except Exception as exc:
        logger.warning(
            "[email-config] Falha a ler X-Company-Id para user=%s: %s",
            user_id, exc,
        )

    company_id = _non_default_company_id(
        getattr(config, "company_id", None),
        query_company_id,
        header_company,
    ) or "default"

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

    try:
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
            config_id=getattr(config, "account_id", None),
            label=getattr(config, "label", None),
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

        logger.info(
            "[email-config] Guardado para user=%s company_id=%s storage_key=%s",
            user_id, company_id, storage_key,
        )
        return {
            "success": True,
            "message": "Configuração guardada com sucesso",
            "is_configured": True,
            "company_id": company_id,
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception(
            "[email-config] Erro a guardar config de email user=%s company_id=%s: %s",
            user_id, company_id, exc,
        )
        raise HTTPException(
            status_code=500,
            detail="Não foi possível guardar a configuração de email. Tente novamente.",
        )


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


def _assert_not_forced_shared(effective_role: str):
    if effective_role in FORCED_SHARED_ROLES:
        raise HTTPException(
            status_code=403,
            detail=(
                "O seu acesso ao email é gerido centralmente pelo departamento. "
                "Contacte o Administrador para alterações na configuração de email."
            ),
        )


def _assert_not_caixa_geral(account_id: str):
    from services.email_config_resolver import CAIXA_GERAL_ACCOUNT_ID
    if account_id == CAIXA_GERAL_ACCOUNT_ID:
        raise HTTPException(
            status_code=403,
            detail="A Caixa Geral é gerida centralmente. Não é possível editar ou remover esta conta.",
        )


async def run_list_my_email_accounts(
    request: Request,
    company_id: Optional[str],
    current_user: dict,
):
    """Listar contas de email do perfil activo (Pacote DN.4 + DO.3)."""
    from services.auth import get_active_company_id_async, get_effective_role
    from services.user_email_config_service import (
        list_company_email_configs,
        publicize_email_account,
    )
    from services.email_config_resolver import (
        CAIXA_GERAL_INJECT_ROLES,
        load_caixa_geral_config,
        publicize_caixa_geral_account,
        resolve_active_ucr_role,
    )

    effective_role = get_effective_role(request, current_user)
    if effective_role in FORCED_SHARED_ROLES:
        return {"accounts": [], "managed_centralized": True}

    header_company = await get_active_company_id_async(request, current_user)
    active_company_id = _non_default_company_id(company_id, header_company) or "default"
    docs = await list_company_email_configs(current_user["id"], active_company_id)
    accounts = [publicize_email_account(doc) for doc in docs]

    ucr_role = await resolve_active_ucr_role(
        request, current_user, active_company_id,
    )
    caixa_injected = False
    if ucr_role in CAIXA_GERAL_INJECT_ROLES or effective_role in CAIXA_GERAL_INJECT_ROLES:
        caixa = await load_caixa_geral_config(active_company_id)
        if caixa and caixa.get("email_address"):
            existing = {
                (a.get("email_address") or "").strip().lower() for a in accounts
            }
            caixa_email = caixa["email_address"].strip().lower()
            if caixa_email not in existing:
                accounts.insert(0, publicize_caixa_geral_account(caixa, active_company_id))
                caixa_injected = True
            else:
                for account in accounts:
                    if (account.get("email_address") or "").strip().lower() == caixa_email:
                        account["is_caixa_geral"] = True
                        account["is_shared"] = True
                        account["managed_centralized"] = True
                        account["label"] = account.get("label") or "Caixa Geral"
                        caixa_injected = True
                        break
            logger.info(
                "[email-accounts] Caixa Geral disponível para diretor user=%s company=%s email=%s",
                current_user.get("id"), active_company_id, caixa.get("email_address"),
            )

    return {
        "company_id": active_company_id,
        "accounts": accounts,
        "caixa_geral_injected": caixa_injected,
    }


async def run_add_my_email_account(
    request: Request,
    config: EmailConfigCreate,
    current_user: dict,
    query_company_id: Optional[str] = None,
):
    """Adicionar uma conta extra (IMAP/SMTP) ao perfil activo."""
    from services.encryption import encryption_service
    from services.user_email_config_service import (
        upsert_user_email_config,
        publicize_email_account,
    )
    from services.auth import get_active_company_id_async, get_effective_role

    effective_role = get_effective_role(request, current_user)
    _assert_not_forced_shared(effective_role)

    header_company = None
    try:
        header_company = await get_active_company_id_async(request, current_user)
    except Exception:
        header_company = None

    company_id = _non_default_company_id(
        getattr(config, "company_id", None),
        query_company_id,
        header_company,
    ) or "default"

    encrypted_password = ""
    if config.password:
        encrypted_password = encryption_service.encrypt(config.password)

    doc = await upsert_user_email_config(
        user_id=current_user["id"],
        company_id=company_id,
        email_address=config.email_address.strip().lower(),
        imap_server=config.imap_server.strip(),
        imap_port=config.imap_port,
        smtp_server=config.smtp_server.strip(),
        smtp_port=config.smtp_port,
        encrypted_password=encrypted_password,
        is_configured=True,
        create_new=True,
        label=getattr(config, "label", None),
        is_primary=False,
    )
    return {
        "success": True,
        "message": "Conta de email adicionada",
        "account": publicize_email_account(doc),
        "company_id": company_id,
    }


async def run_update_my_email_account(
    request: Request,
    account_id: str,
    config: EmailConfigCreate,
    current_user: dict,
):
    """Actualizar uma conta existente do perfil."""
    from services.encryption import encryption_service
    from services.user_email_config_service import (
        get_user_email_config,
        upsert_user_email_config,
        publicize_email_account,
    )
    from services.auth import get_effective_role

    effective_role = get_effective_role(request, current_user)
    _assert_not_forced_shared(effective_role)
    _assert_not_caixa_geral(account_id)

    existing = await get_user_email_config(
        current_user["id"], config.company_id or "default", account_id=account_id,
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Conta de email não encontrada")

    encrypted_password = existing.get("encrypted_password") or ""
    if config.password:
        encrypted_password = encryption_service.encrypt(config.password)

    doc = await upsert_user_email_config(
        user_id=current_user["id"],
        company_id=existing.get("company_id") or config.company_id or "default",
        email_address=config.email_address.strip().lower(),
        imap_server=config.imap_server.strip(),
        imap_port=config.imap_port,
        smtp_server=config.smtp_server.strip(),
        smtp_port=config.smtp_port,
        encrypted_password=encrypted_password,
        google_refresh_token=existing.get("google_refresh_token"),
        google_access_token=existing.get("google_access_token"),
        google_email=existing.get("google_email"),
        auth_method=existing.get("auth_method", "none"),
        oauth_connected_at=existing.get("oauth_connected_at"),
        is_configured=True,
        config_id=account_id,
        label=getattr(config, "label", None) or existing.get("label"),
    )
    return {"success": True, "account": publicize_email_account(doc)}


async def run_delete_my_email_account(
    request: Request,
    account_id: str,
    current_user: dict,
):
    """Remover uma conta de email do perfil."""
    from services.user_email_config_service import (
        get_user_email_config,
        delete_user_email_config,
    )
    from services.auth import get_effective_role

    effective_role = get_effective_role(request, current_user)
    _assert_not_forced_shared(effective_role)
    _assert_not_caixa_geral(account_id)

    existing = await get_user_email_config(
        current_user["id"], "default", account_id=account_id,
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Conta de email não encontrada")

    ok = await delete_user_email_config(
        current_user["id"],
        existing.get("company_id") or "default",
        account_id=account_id,
    )
    if not ok:
        raise HTTPException(status_code=404, detail="Conta de email não encontrada")
    return {"success": True, "message": "Conta de email removida"}


async def run_set_primary_email_account(
    request: Request,
    account_id: str,
    current_user: dict,
):
    """Definir a conta por omissão do perfil activo."""
    from services.user_email_config_service import (
        get_user_email_config,
        set_primary_email_config,
        publicize_email_account,
    )
    from services.auth import get_effective_role

    effective_role = get_effective_role(request, current_user)
    _assert_not_forced_shared(effective_role)
    _assert_not_caixa_geral(account_id)

    existing = await get_user_email_config(
        current_user["id"], "default", account_id=account_id,
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Conta de email não encontrada")

    updated = await set_primary_email_config(
        current_user["id"],
        existing.get("company_id") or "default",
        account_id,
    )
    return {"success": True, "account": publicize_email_account(updated)}

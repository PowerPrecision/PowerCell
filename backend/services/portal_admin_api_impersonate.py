"""Portal admin impersonation handler.

Extraído de `routes/portal_admin.py`.
Use portal_admin_api_* (careful vs portal_* services).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import HTTPException, Request

from database import db
from services.portal_security import PORTAL_TOKEN_VALIDITY_DAYS
from services.portal_magic_link import issue_portal_magic_link
from services.history import log_history
from services.audit_trail_service import log_audit_event

logger = logging.getLogger(__name__)


async def run_impersonate_client_portal(process_id: str, request: Request, user: dict):
    process = await db.processes.find_one({"id": process_id}, {"_id": 0})
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")

    if process.get("is_deleted"):
        raise HTTPException(
            status_code=404,
            detail="Este processo foi eliminado. Restaure-o antes de usar Ver como Cliente."
        )

    client_name = process.get("client_name", "Cliente")
    client_email = process.get("client_email", "")
    client_id = process.get("client_id", "")

    now = datetime.now(timezone.utc)
    issued = await issue_portal_magic_link(
        process_id=process_id,
        process=process,
        user=user,
        request=request,
        token_filter={"process_id": process_id, "impersonated_by": user.get("id")},
        extra_token_fields={
            "impersonated_by": user.get("id"),
            "impersonated_by_email": user.get("email"),
            "impersonated_by_name": user.get("name"),
            "impersonated_by_role": user.get("role"),
            "impersonated_at": now,
            "token_type": "staff_impersonate",
        },
    )
    short_id = issued["short_id"]
    impersonate_url = issued["magic_link"]

    audit_msg = (
        f"O utilizador {user.get('email')} assumiu a identidade do "
        f"cliente no processo {process_id}"
    )
    logger.info(f"[IMPERSONATE] {audit_msg} (cliente: {client_name})")

    try:
        await log_audit_event(
            process_id=process_id,
            user=user,
            action="Impersonate — Ver como Cliente no Portal",
            field="portal_impersonate",
            new_value=short_id,
            request=request,
            source="web",
            audit_reason="Suporte ao cliente (ver portal como cliente)",
            metadata={
                "impersonate": True,
                "impersonated_by_email": user.get("email"),
                "impersonated_by_role": user.get("role"),
                "short_id": short_id,
                "client_id": client_id,
                "client_name": client_name,
            },
        )
    except Exception as e:
        logger.warning(f"[IMPERSONATE] Não foi possível registar audit_trail: {e}")

    try:
        await log_history(
            process_id=process_id,
            user=user,
            action=(
                f"Impersonate — {user.get('name', 'Staff')} assumiu a "
                f"identidade do cliente no Portal (suporte)"
            ),
            field="portal_impersonate",
            new_value=short_id,
        )
    except Exception as e:
        logger.warning(f"[IMPERSONATE] Não foi possível registar history: {e}")

    return {
        "url": impersonate_url,
        "short_id": short_id,
        "process_id": process_id,
        "client_name": client_name,
        "client_email": client_email,
        "expires_in_days": PORTAL_TOKEN_VALIDITY_DAYS,
        "impersonated_by": user.get("email"),
        "impersonated_by_name": user.get("name"),
    }

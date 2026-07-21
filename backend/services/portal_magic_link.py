"""
Helpers para emitir magic links do Portal do Cliente.

Centraliza a geração de JWT + short_id + upsert em `portal_tokens` e a
resolução/criação do `portal_access_code` do cliente — lógica que estava
duplicada em `routes/processes.py` (generate/send) e parcialmente em
`routes/portal_admin.py` (impersonate).
"""
from __future__ import annotations

import logging
import secrets
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import Request

from database import db
from services.portal_security import create_client_magic_token
from utils.frontend_url import get_frontend_url

logger = logging.getLogger(__name__)


async def ensure_portal_access_code(client_id: str) -> Optional[str]:
    """
    Devolve o portal_access_code do cliente, gerando e persistindo um novo
    se ainda não existir. Sem client_id devolve None.
    """
    if not client_id:
        return None

    client_doc = await db.clients.find_one(
        {"id": client_id},
        {"_id": 0, "portal_access_code": 1},
    )
    portal_access_code = (client_doc or {}).get("portal_access_code")
    if portal_access_code:
        return portal_access_code

    from models.client import generate_portal_access_code

    portal_access_code = generate_portal_access_code()
    await db.clients.update_one(
        {"id": client_id},
        {"$set": {"portal_access_code": portal_access_code}},
    )
    return portal_access_code


async def issue_portal_magic_link(
    *,
    process_id: str,
    process: dict,
    user: dict,
    request: Request,
    extra_token_fields: Optional[dict[str, Any]] = None,
    token_filter: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """
    Gera JWT + short_id, faz upsert em portal_tokens e devolve a URL pública.

    Args:
        process_id: ID do processo.
        process: Documento do processo (precisa de client_id / client_name…).
        user: Utilizador staff que emite o link.
        request: Request FastAPI (Referer/Origin → frontend URL).
        extra_token_fields: Campos extra a gravar no documento portal_tokens
            (ex.: metadados de impersonate).
        token_filter: Filtro do upsert. Por defeito `{"process_id": process_id}`.
            Impersonate usa filtro por process_id + impersonated_by.

    Returns:
        dict com short_id, token, magic_link, frontend_url, process_id,
        client_id, client_name, client_email.
    """
    token = create_client_magic_token(process_id)
    short_id = secrets.token_urlsafe(6)[:8]
    now = datetime.now(timezone.utc)

    set_fields: dict[str, Any] = {
        "short_id": short_id,
        "jwt_token": token,
        "process_id": process_id,
        "client_id": process.get("client_id", ""),
        "created_by": user.get("email", ""),
        "updated_at": now,
    }
    if extra_token_fields:
        set_fields.update(extra_token_fields)

    filt = token_filter or {"process_id": process_id}
    await db.portal_tokens.update_one(
        filt,
        {
            "$set": set_fields,
            "$setOnInsert": {"created_at": now},
        },
        upsert=True,
    )

    frontend_url = get_frontend_url(request)
    magic_link = f"{frontend_url}/portal/{short_id}" if frontend_url else f"/portal/{short_id}"

    return {
        "short_id": short_id,
        "token": token,
        "magic_link": magic_link,
        "frontend_url": frontend_url,
        "process_id": process_id,
        "client_id": process.get("client_id", ""),
        "client_name": process.get("client_name", ""),
        "client_email": process.get("client_email", ""),
    }


def build_magic_link_email_bodies(
    *,
    client_name: str,
    client_email: str,
    magic_link: str,
    portal_access_code: Optional[str],
) -> tuple[str, str]:
    """Constrói (text_body, html_body) do email de magic link ao cliente."""
    portal_credentials_html = f"""
            <div style="background: #f0fdfa; border: 1px solid #0d9488; border-radius: 8px; padding: 20px; margin: 20px 0;">
                <p style="font-size: 14px; color: #1e293b; margin: 0 0 10px 0;">Se o link não funcionar, aceda a <strong>www.powercell.pt/portal</strong> e insira o seguinte Código de Acesso:</p>
                <h3 style="text-align: center; margin: 10px 0;"><strong style="font-family: 'Courier New', monospace; font-size: 22px; color: #0f766e; letter-spacing: 3px;">{portal_access_code or '—'}</strong></h3>
                <p style="margin: 5px 0; color: #1e293b; font-size: 13px;"><strong>Email:</strong> {client_email}</p>
            </div>
    """
    portal_credentials_text = (
        f"\nSe o link não funcionar, aceda a www.powercell.pt/portal e "
        f"insira o seguinte Código de Acesso: {portal_access_code or '—'}\n"
        f"Email: {client_email}\n"
    )

    html_body = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
        <div style="background: #0F766E; color: white; padding: 20px; border-radius: 8px 8px 0 0;">
            <h1 style="margin: 0; font-size: 20px;">Power Precision · Crédito Habitação</h1>
        </div>
        <div style="padding: 30px; border: 1px solid #e2e8f0; border-top: none; border-radius: 0 0 8px 8px;">
            <p style="font-size: 16px; color: #1e293b;">Olá {client_name},</p>
            <p style="font-size: 14px; color: #475569;">
                O seu consultor preparou o seu portal pessoal para acompanhar o seu processo de crédito habitação.
            </p>
            <div style="text-align: center; margin: 30px 0;">
                <a href="{magic_link}" style="display: inline-block; background: #0F766E; color: white; padding: 14px 28px; border-radius: 8px; text-decoration: none; font-weight: bold; font-size: 16px;">
                    Aceder ao meu Portal
                </a>
            </div>
            <p style="font-size: 12px; color: #94a3b8; text-align: center;">
                Ou copie este link no seu navegador:<br>
                <span style="color: #64748b;">{magic_link}</span>
            </p>
            {portal_credentials_html}
            <p style="font-size: 12px; color: #94a3b8; margin-top: 20px;">
                Este link é válido por 90 dias. Se precisar de um novo link, contacte o seu consultor.
            </p>
        </div>
    </div>
    """

    text_body = (
        f"Olá {client_name},\n\n"
        f"O seu consultor preparou o seu portal pessoal para acompanhar o seu processo de crédito habitação.\n\n"
        f"Aceda ao portal através deste link:\n{magic_link}\n"
        f"{portal_credentials_text}\n"
        f"Este link é válido por 90 dias.\n"
        f"Se precisar de um novo link, contacte o seu consultor.\n\n"
        f"Power Precision · Crédito Habitação"
    )
    return text_body, html_body

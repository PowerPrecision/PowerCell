"""
====================================================================
SERVIÇO DE MAGIC LINKS DO PORTAL - CREDITOIMO
====================================================================
Geração de magic links curtos, envio por email e email de
boas-vindas do portal após criação de processo.

Extraído de routes/processes.py.
====================================================================
"""
import os
import secrets
import logging
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse

from fastapi import HTTPException

from database import db
from services.portal_security import create_client_magic_token, PORTAL_TOKEN_VALIDITY_DAYS

logger = logging.getLogger(__name__)


def get_frontend_url(request) -> str:
    """
    Obtém a URL base do frontend para construir links públicos.

    Prioridade:
    1. Header Referer (vem do browser do staff — é sempre o domínio correto)
    2. Env var FRONTEND_URL (configurada no deploy)
    3. Sem fallback hardcoded — devolve string vazia se não for possível determinar
    """
    referer = request.headers.get("referer") or request.headers.get("origin")
    if referer:
        parsed = urlparse(referer)
        if parsed.scheme and parsed.netloc:
            return f"{parsed.scheme}://{parsed.netloc}"

    frontend_url = os.environ.get("FRONTEND_URL")
    if frontend_url:
        return frontend_url.rstrip("/")

    logger.warning(
        "[MAGIC LINK] FRONTEND_URL não configurada e sem Referer header. "
        "Configure a env var FRONTEND_URL no backend."
    )
    return ""


async def send_portal_welcome_email_from_process(
    client_id: str,
    client_email: str,
    client_name: str,
) -> None:
    """Envia email de boas-vindas do Portal após criar um processo.

    Fire-and-forget: falhas são LOGADAS mas não propagadas.
    """
    try:
        portal_access_code = None
        try:
            client_doc = await db.clients.find_one(
                {"id": client_id}, {"portal_access_code": 1, "_id": 0}
            )
            if client_doc:
                portal_access_code = client_doc.get("portal_access_code")
                if not portal_access_code:
                    from models.client import generate_portal_access_code as _gen_code
                    portal_access_code = _gen_code()
                    await db.clients.update_one(
                        {"id": client_id},
                        {"$set": {"portal_access_code": portal_access_code}}
                    )
        except Exception as e:
            logger.warning(
                f"[PORTAL-EMAIL] Erro ao obter/gerar portal_access_code para {client_id}: {e}"
            )

        from services.task_queue import task_queue
        from services.email import send_registration_confirmation

        job_id = None
        try:
            job_id = await task_queue.send_registration_email(
                client_email=client_email,
                client_name=client_name,
                portal_access_code=portal_access_code,
            )
        except Exception as tq_err:
            logger.warning(
                f"[PORTAL-EMAIL] Task Queue indisponível para cliente {client_id}: {tq_err}"
            )

        if not job_id:
            logger.info(
                f"[PORTAL-EMAIL] A enviar email diretamente para {client_email} "
                f"(client_id={client_id})"
            )
            try:
                await send_registration_confirmation(
                    client_email=client_email,
                    client_name=client_name,
                    portal_access_code=portal_access_code,
                )
                logger.info(
                    f"[PORTAL-EMAIL] Email enviado com sucesso para {client_email} "
                    f"(client_id={client_id})"
                )
            except Exception as direct_err:
                logger.error(
                    f"[PORTAL-EMAIL] Falha ao enviar email diretamente para {client_email} "
                    f"(client_id={client_id}): {direct_err}",
                    exc_info=True,
                )
    except Exception as e:
        logger.error(
            f"[PORTAL-EMAIL] Erro inesperado no envio do email de boas-vindas "
            f"para {client_email} (client_id={client_id}): {e}",
            exc_info=True,
        )


async def _ensure_portal_access_code(client_id: str) -> Optional[str]:
    """Busca ou gera portal_access_code para o cliente."""
    if not client_id:
        return None

    portal_access_code = None
    client_doc = await db.clients.find_one(
        {"id": client_id},
        {"_id": 0, "portal_access_code": 1}
    )
    if client_doc:
        portal_access_code = client_doc.get("portal_access_code")

    if not portal_access_code:
        from models.client import generate_portal_access_code
        portal_access_code = generate_portal_access_code()
        await db.clients.update_one(
            {"id": client_id},
            {"$set": {"portal_access_code": portal_access_code}}
        )
    return portal_access_code


async def _persist_magic_link_token(
    process: dict,
    process_id: str,
    user: dict,
) -> tuple[str, str, str]:
    """Gera JWT + short_id e persiste em portal_tokens.

    Returns:
        (token, short_id, magic_link_path_suffix) — magic_link precisa do frontend_url.
    """
    token = create_client_magic_token(process_id)
    short_id = secrets.token_urlsafe(6)[:8]

    await db.portal_tokens.update_one(
        {"process_id": process_id},
        {
            "$set": {
                "short_id": short_id,
                "jwt_token": token,
                "process_id": process_id,
                "client_id": process.get("client_id", ""),
                "created_by": user.get("email", ""),
                "updated_at": datetime.now(timezone.utc),
            },
            "$setOnInsert": {
                "created_at": datetime.now(timezone.utc),
            },
        },
        upsert=True,
    )
    return token, short_id, f"/portal/{short_id}"


async def create_magic_link(process_id: str, request, user: dict) -> dict:
    """
    Gera um Magic Link para o Portal do Cliente e devolve o payload da API.
    """
    process = await db.processes.find_one(
        {"id": process_id, "is_deleted": {"$ne": True}},
        {"_id": 0}
    )
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")

    token, short_id, path = await _persist_magic_link_token(process, process_id, user)
    frontend_url = get_frontend_url(request)
    magic_link = f"{frontend_url}{path}"

    logger.info(
        f"Magic link gerado por {user.get('email')} para processo {process_id} "
        f"(cliente: {process.get('client_name', 'N/A')}, short_id: {short_id})"
    )

    return {
        "magic_link": magic_link,
        "short_id": short_id,
        "token": token,
        "process_id": process_id,
        "client_name": process.get("client_name", ""),
        "client_email": process.get("client_email", ""),
        "expires_in_days": PORTAL_TOKEN_VALIDITY_DAYS,
    }


async def send_magic_link_email_to_client(process_id: str, request, user: dict) -> dict:
    """
    Gera um Magic Link e envia-o por email ao cliente.
    """
    from services.email_service import send_email

    process = await db.processes.find_one(
        {"id": process_id, "is_deleted": {"$ne": True}},
        {"_id": 0}
    )
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")

    client_email = process.get("client_email", "")
    client_name = process.get("client_name", "Cliente")
    client_id = process.get("client_id", "")

    if not client_email:
        raise HTTPException(status_code=400, detail="Cliente não tem email associado")

    portal_access_code = await _ensure_portal_access_code(client_id)
    _token, short_id, path = await _persist_magic_link_token(process, process_id, user)
    frontend_url = get_frontend_url(request)
    magic_link = f"{frontend_url}{path}"

    # PACOTE DC — Bloco "Código de Acesso" SEMPRE presente (incondicional).
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

    try:
        await send_email(
            account_name="power",
            to_emails=[client_email],
            subject=f"Portal do Cliente — Acompanhe o seu processo ({client_name})",
            body=text_body,
            body_html=html_body,
            force_system=True,
            system_purpose="NOTIFICATIONS",
        )
    except Exception as e:
        logger.error(f"Erro ao enviar magic link email: {e}")
        raise HTTPException(
            status_code=500,
            detail="Erro ao enviar email. Tente copiar o link manualmente.",
        )

    logger.info(
        f"Magic link enviado por email para {client_email} "
        f"(processo {process_id}, short_id: {short_id})"
    )

    return {
        "success": True,
        "message": f"Email enviado para {client_email}",
        "magic_link": magic_link,
        "short_id": short_id,
        "portal_access_code": portal_access_code,
    }

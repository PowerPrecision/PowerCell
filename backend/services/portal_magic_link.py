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
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import Request

from database import db
from services.portal_security import create_client_magic_token
from utils.frontend_url import get_frontend_url

logger = logging.getLogger(__name__)

#: Códigos de falha do ``send_email`` que são CONFIGURAÇÃO da conta (e não
#: infraestrutura): quem os recebe tem de os corrigir, repetir não adianta.
CODIGOS_DE_CONFIGURACAO_DO_REMETENTE = frozenset({"smtp_auth", "smtp_password_unreadable"})


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
    logo_html: str = "",
    company_name: Optional[str] = None,
    portal_login_url: Optional[str] = None,
) -> tuple[str, str]:
    """Constrói (text_body, html_body) do email de magic link ao cliente.

    PACOTE 11 (Eixo 2): ``logo_html`` (fragmento ``<img>`` do logo da
    empresa, resolvido pelo caller async via email_branding) é injectado
    no header. String vazia → header só com texto (comportamento antigo).

    REDE: ``company_name`` e ``portal_login_url`` vêm do contexto da rede do
    cliente (``portal_email_context``) — o nome da empresa e o endereço da
    página de entrada do Portal. Já não há marca nem domínio fixos no texto.
    """
    nome_da_empresa = (company_name or "").strip() or "Portal do Cliente"
    destino_de_entrada = (portal_login_url or "").strip() or "ao Portal do Cliente"
    portal_credentials_html = f"""
            <div style="background: #f0fdfa; border: 1px solid #0d9488; border-radius: 8px; padding: 20px; margin: 20px 0;">
                <p style="font-size: 14px; color: #1e293b; margin: 0 0 10px 0;">Se o link não funcionar, aceda a <strong>{destino_de_entrada}</strong> e insira o seguinte Código de Acesso:</p>
                <h3 style="text-align: center; margin: 10px 0;"><strong style="font-family: 'Courier New', monospace; font-size: 22px; color: #0f766e; letter-spacing: 3px;">{portal_access_code or '—'}</strong></h3>
                <p style="margin: 5px 0; color: #1e293b; font-size: 13px;"><strong>Email:</strong> {client_email}</p>
            </div>
    """
    portal_credentials_text = (
        f"\nSe o link não funcionar, aceda a {destino_de_entrada} e "
        f"insira o seguinte Código de Acesso: {portal_access_code or '—'}\n"
        f"Email: {client_email}\n"
    )

    html_body = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
        <div style="background: #0F766E; color: white; padding: 20px; border-radius: 8px 8px 0 0; text-align: center;">
            {logo_html}<h1 style="margin: 0; font-size: 20px;">{nome_da_empresa} · Crédito Habitação</h1>
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
        f"{nome_da_empresa} · Crédito Habitação"
    )
    return text_body, html_body


async def load_active_process_or_404(process_id: str) -> dict:
    """Processo não eliminado ou HTTP 404."""
    from fastapi import HTTPException
    process = await db.processes.find_one(
        {"id": process_id, "is_deleted": {"$ne": True}},
        {"_id": 0},
    )
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")
    return process


def build_generate_magic_link_response(
    *,
    process_id: str,
    process: dict,
    issued: dict,
    expires_in_days: int,
) -> dict[str, Any]:
    return {
        "magic_link": issued["magic_link"],
        "short_id": issued["short_id"],
        "token": issued["token"],
        "process_id": process_id,
        "client_name": process.get("client_name", ""),
        "client_email": process.get("client_email", ""),
        "expires_in_days": expires_in_days,
    }


def build_send_magic_link_response(
    *,
    client_email: str,
    magic_link: str,
    short_id: str,
    portal_access_code: Optional[str],
) -> dict[str, Any]:
    return {
        "success": True,
        "message": f"A enviar o email para {client_email}. Será avisado se não sair.",
        "queued": True,
        "magic_link": magic_link,
        "short_id": short_id,
        "portal_access_code": portal_access_code,
    }


#: O serviço de email não entregou (rede, timeout, relay recusado…).
DETALHE_FALHA_DE_ENTREGA = (
    "Não foi possível enviar o e-mail: o servidor de e-mail da empresa não respondeu ou "
    "recusou o envio. Verifique as definições em Contas de Email ou copie o link manualmente."
)

#: Mensagem de uma falha NOSSA (não do serviço de email) antes ou depois do envio.
DETALHE_FALHA_INTERNA = (
    "Não foi possível preparar o envio do link de acesso. Tente de novo; se persistir, "
    "gere o link e copie-o manualmente."
)


async def send_magic_link_to_client(
    *,
    process_id: str,
    process: dict,
    user: dict,
    request: Request,
) -> dict[str, Any]:
    """
    Garante access code, emite link e envia email.

    Raises HTTPException — e SÓ HTTPException:
      400 configuração do remetente (sem caixa, credenciais, ValueError de config);
      502 o serviço de email não entregou (rede, timeout, relay recusado, excepção);
      500 falha interna nossa (base de dados, emissão do link), com detalhe.

    Nenhuma excepção do serviço de email chega ao FastAPI sem tradução: o
    `try/except` à volta do envio protegia só a chamada final, e a resolução do
    remetente (que corre antes) estava fora dele.
    """
    from fastapi import HTTPException

    try:
        return await _send_magic_link_to_client(
            process_id=process_id, process=process, user=user, request=request,
        )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 - nada escapa sem tradução
        logger.error(
            "[MAGIC-LINK] Falha inesperada no envio (processo %s): %s: %s",
            process_id, type(exc).__name__, exc, exc_info=True,
        )
        raise HTTPException(status_code=500, detail=DETALHE_FALHA_INTERNA)


async def _send_magic_link_to_client(
    *,
    process_id: str,
    process: dict,
    user: dict,
    request: Request,
) -> dict[str, Any]:
    from fastapi import HTTPException

    client_email = process.get("client_email", "")
    client_name = process.get("client_name", "Cliente")
    client_id = process.get("client_id", "")

    if not client_email:
        raise HTTPException(
            status_code=400,
            detail="Cliente não tem email associado",
        )

    # Contexto de REDE do cliente: nome, logótipo, remetente e endereço do
    # Portal vêm do carimbo do processo/cliente, nunca de uma constante.
    from services.email_branding import build_email_header_logo_html
    from services.portal_email_context import (
        resolver_contexto,
        verificar_remetente,
    )

    def _contexto(frontend_url):
        return resolver_contexto(
            company_id=process.get("company_id"),
            company_name=process.get("company_name"),
            network_id=process.get("network_id"),
            client_id=client_id or None,
            user=user,
            frontend_url=frontend_url,
        )

    # FAIL FAST: sem remetente não há o que emitir, gravar ou repetir. Antes de
    # emitir o link (um token novo por tentativa) e de escrever «Enviou o link»
    # no histórico de um email que nunca sairá. O remetente depende da rede e
    # não do endereço do Portal, que só se conhece depois de emitir o link.
    contexto = await _contexto(None)
    sem_remetente = await verificar_remetente(contexto)
    if sem_remetente:
        logger.warning(
            "[MAGIC-LINK] Processo %s (rede %s): %s", process_id, contexto.network_id, sem_remetente,
        )
        raise HTTPException(status_code=400, detail=sem_remetente)

    portal_access_code = await ensure_portal_access_code(client_id)
    issued = await issue_portal_magic_link(
        process_id=process_id,
        process=process,
        user=user,
        request=request,
    )
    magic_link = issued["magic_link"]
    short_id = issued["short_id"]
    contexto = await _contexto(issued.get("frontend_url"))

    text_body, html_body = build_magic_link_email_bodies(
        client_name=client_name,
        client_email=client_email,
        magic_link=magic_link,
        portal_access_code=portal_access_code,
        logo_html=build_email_header_logo_html(contexto.logo_url, alt=contexto.nome),
        company_name=contexto.nome,
        portal_login_url=contexto.portal_url,
    )

    # O envio SMTP já NÃO bloqueia o pedido (Lote 2, Out 2026): um servidor de
    # email pendurado fazia o pedido esperar o timeout SMTP e o proxy do Render
    # cortava-o com um 502 que não diz nada ao utilizador. Tudo o que se pode
    # recusar de imediato (cliente sem email, remetente em falta) foi recusado
    # acima, com 400. Daqui para a frente a entrega corre em segundo plano e uma
    # falha chega ao utilizador como NOTIFICAÇÃO — nunca em silêncio.
    from services.background_tasks import spawn_background_task

    spawn_background_task(
        _entregar_magic_link(
            contexto=contexto,
            process_id=process_id,
            user=user,
            client_email=client_email,
            client_name=client_name,
            text_body=text_body,
            html_body=html_body,
            short_id=short_id,
        ),
        name=f"magic-link-email-{process_id}",
    )
    return build_send_magic_link_response(
        client_email=client_email,
        magic_link=magic_link,
        short_id=short_id,
        portal_access_code=portal_access_code,
    )


async def _avisar_falha_do_envio(user: dict, process_id: str, client_name: str, motivo: str) -> None:
    """Notifica quem pediu o envio de que o email NÃO saiu. Nunca levanta."""
    try:
        user_id = (user or {}).get("id")
        if not user_id:
            return
        await db.notifications.insert_one({
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "message": (
                f"O email com o link do Portal para {client_name} não foi enviado: {motivo}"
            ),
            "type": "email_failed",
            "process_id": process_id,
            "client_name": client_name,
            "link": f"/processo/{process_id}",
            "read": False,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        from services.telegram_notifications import agendar as agendar_telegram

        await agendar_telegram(user_id, "email_failed", process_id=process_id, link=f"/processo/{process_id}")
    except Exception as exc:  # noqa: BLE001 - o aviso é o último recurso
        logger.error("[MAGIC-LINK] Nem a notificação da falha foi gravada (processo %s): %s", process_id, exc)


async def _entregar_magic_link(
    *,
    contexto,
    process_id: str,
    user: dict,
    client_email: str,
    client_name: str,
    text_body: str,
    html_body: str,
    short_id: str,
) -> None:
    """Entrega o email do link do Portal, fora do ciclo pedido/resposta.

    Nunca levanta (é uma task sem ninguém à espera): qualquer falha fica no log
    e numa notificação para quem pediu o envio.
    """
    from services.portal_email_context import enviar_email_do_portal, mensagem_sem_remetente

    try:
        send_result = await enviar_email_do_portal(
            contexto,
            to_emails=[client_email],
            subject=f"Portal do Cliente — Acompanhe o seu processo ({client_name})",
            body=text_body,
            body_html=html_body,
        )
    except ValueError as e:
        logger.error(f"Erro de configuração ao enviar magic link email: {e}")
        await _avisar_falha_do_envio(user, process_id, client_name, f"SMTP não está configurado ({e}).")
        return
    except Exception as e:  # noqa: BLE001
        logger.error(f"Erro ao enviar magic link email: {e}", exc_info=True)
        await _avisar_falha_do_envio(user, process_id, client_name, DETALHE_FALHA_DE_ENTREGA)
        return

    # `send_email` NÃO levanta quando o envio falha — devolve {"success": False}.
    if not send_result or not send_result.get("success"):
        error_detail = (send_result or {}).get("error") or "Falha desconhecida ao enviar o email."
        error_code = (send_result or {}).get("error_code")
        logger.error(f"Erro ao enviar magic link email para {client_email}: {error_detail}")
        if error_code == "SMTP_NOT_CONFIGURED":
            motivo = mensagem_sem_remetente(contexto)
        elif error_code in CODIGOS_DE_CONFIGURACAO_DO_REMETENTE:
            motivo = (
                f"A conta de e-mail da empresa não está a funcionar ({error_detail}). "
                "Verifique as credenciais em Contas de Email."
            )
        else:
            motivo = f"{DETALHE_FALHA_DE_ENTREGA} ({error_detail})"
        await _avisar_falha_do_envio(user, process_id, client_name, motivo)
        return

    # O acesso SAIU: o alerta «Email de acesso não entregue» deixa de valer (QA-6).
    from services.email_delivery_status import registar_acesso_entregue_do_processo

    await registar_acesso_entregue_do_processo(process_id)

    # Bloco 3 (ponto 21): enviar acesso ao Portal fica no histórico (sem o link)
    # — só DEPOIS de o email ter saído: um registo de «enviou» não pode
    # descrever um envio que falhou.
    from services.history import log_history

    try:
        await log_history(
            process_id, user, "Enviou o link de acesso ao Portal ao cliente",
            "portal_access", None, "email",
        )
    except Exception as exc:  # noqa: BLE001 - o email JÁ saiu; o rasto não o desfaz
        logger.warning("[MAGIC-LINK] Email enviado mas o histórico falhou (processo %s): %s", process_id, exc)

    logger.info(
        f"Magic link enviado por email para {client_email} "
        f"(processo {process_id}, short_id: {short_id})"
    )

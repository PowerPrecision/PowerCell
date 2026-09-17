"""RGPD request + resend email orchestration.

Extraído de `routes/rgpd.py`. Reuses `create_rgpd_request` / `send_rgpd_email`
from existing `services/rgpd_service.py` (do not duplicate).
"""
from __future__ import annotations

import logging
import smtplib
import uuid
from datetime import datetime, timezone, timedelta

from fastapi import HTTPException

from database import db
from models.rgpd import RGPDCreate, RGPDResponse, RGPDStatusEnum
from services.rgpd_service import (
    create_rgpd_request,
    send_rgpd_email,
    resolve_second_titular_for_rgpd,
    RGPD_REQUESTS_COLLECTION,
    TOKEN_EXPIRY_HOURS,
)
from services.rgpd_helpers import (
    _add_process_activity,
    _get_rgpd_or_404,
    _frontend_base_url_from_request,
)

logger = logging.getLogger(__name__)


async def run_request_rgpd(data: RGPDCreate, request, user: dict):
    """
    Solicita consentimento RGPD para um processo, enviando um email
    com link temporário (24h) para o cliente assinar digitalmente.

    PACOTE 5 (RGPD por titular — 2 documentos independentes): o texto legal
    do RGPD/Minuta é redigido no SINGULAR — cada titular assina o SEU
    documento. Se o processo tiver um 2º titular com NOME e EMAIL válidos
    (`second_client_id` ligado, `second_client_data` ou `titular2_data`),
    o sistema cria um pedido INDEPENDENTE para o 2º titular e envia 2
    emails separados (um para cada titular, cada um com o seu token de
    assinatura). Os PDFs gerados na assinatura de cada um são preenchidos
    exclusivamente com os dados dessa pessoa.
    """
    try:
        process = await db.processes.find_one({"id": data.process_id})
        if not process:
            raise HTTPException(status_code=404, detail="Processo não encontrado")

        # ── 1º titular (pedido principal — compatível com o fluxo clássico) ──
        result = await create_rgpd_request(
            process_id=data.process_id,
            client_name=data.client_name,
            client_email=data.client_email,
            user=user,
            titular="first",
        )

        if not result.get("success"):
            logger.error(f"Erro ao criar pedido RGPD: {result}")
            raise HTTPException(status_code=500, detail="Erro ao criar pedido de RGPD")

        if result.get("existing"):
            if result.get("status") == "signed":
                return RGPDResponse(
                    id=result["request_id"],
                    process_id=data.process_id,
                    client_name=data.client_name,
                    client_email=data.client_email,
                    status=RGPDStatusEnum.SIGNED,
                    signed_at=result.get("signed_at"),
                    created_at="",
                    created_by_name=user.get("name", ""),
                )
            elif result.get("status") == "pending":
                return RGPDResponse(
                    id=result["request_id"],
                    process_id=data.process_id,
                    client_name=data.client_name,
                    client_email=data.client_email,
                    status=RGPDStatusEnum.PENDING,
                    token_expires_at=result.get("expires_at"),
                    created_at="",
                    created_by_name=user.get("name", ""),
                )

        frontend_base_url = _frontend_base_url_from_request(request)

        email_sent = await send_rgpd_email(
            client_email=data.client_email,
            client_name=data.client_name,
            token=result["token"],
            request_id=result["request_id"],
            user_email=user["email"],
            custom_message=data.custom_message,
            base_url=frontend_base_url,
            process_id=data.process_id,
            user_id=user.get("id"),
        )

        if not email_sent:
            logger.warning("RGPD created but email failed to send")

        email_status = "enviado" if email_sent else "falhou"
        await _add_process_activity(
            process_id=data.process_id,
            user_id=user.get("id", "system"),
            user_name=user.get("name", "Sistema"),
            action=f"RGPD solicitado — email {email_status} para {data.client_email}",
            details=f"Link de assinatura enviado para o cliente. Expira em {TOKEN_EXPIRY_HOURS}h.",
        )

        # ── PACOTE 5 — 2º titular: pedido + email INDEPENDENTES ──
        # Verifica se existe um 2º titular com nome e email válidos no
        # processo; se existir, cria o pedido dele e envia o 2º email.
        second_titular = await resolve_second_titular_for_rgpd(process)
        second_titular_name = None
        second_email_sent = None

        if second_titular:
            second_titular_name = second_titular["nome"]
            second_email_sent = False

            # Evitar duplicar o envio quando o 2º titular partilha o email
            # do 1º (mesma caixa) — nesse caso um único pedido chega.
            same_email = (
                second_titular["email"].strip().lower()
                == str(data.client_email).strip().lower()
            )

            if not same_email:
                result_second = await create_rgpd_request(
                    process_id=data.process_id,
                    client_name=second_titular["nome"],
                    client_email=second_titular["email"],
                    user=user,
                    titular="second",
                )

                if result_second.get("success") and not result_second.get("existing"):
                    second_email_sent = await send_rgpd_email(
                        client_email=second_titular["email"],
                        client_name=second_titular["nome"],
                        token=result_second["token"],
                        request_id=result_second["request_id"],
                        user_email=user["email"],
                        custom_message=data.custom_message,
                        base_url=frontend_base_url,
                        process_id=data.process_id,
                        user_id=user.get("id"),
                    )
                    second_status_txt = "enviado" if second_email_sent else "falhou"
                    await _add_process_activity(
                        process_id=data.process_id,
                        user_id=user.get("id", "system"),
                        user_name=user.get("name", "Sistema"),
                        action=(
                            f"RGPD do 2º titular solicitado — email "
                            f"{second_status_txt} para {second_titular['email']}"
                        ),
                        details=(
                            "Link de assinatura independente para o 2º titular "
                            f"({second_titular['nome']}). Expira em {TOKEN_EXPIRY_HOURS}h."
                        ),
                    )
                    if not second_email_sent:
                        logger.warning(
                            f"RGPD 2º titular criado mas email falhou: "
                            f"{second_titular['email']}"
                        )
                elif result_second.get("existing"):
                    # Já existe pedido ativo para o 2º titular — não reenviar.
                    second_email_sent = True
                    logger.info(
                        f"[RGPD-TITULAR2] Pedido já existente para "
                        f"{second_titular['email']} (status={result_second.get('status')})"
                    )
            else:
                logger.info(
                    "[RGPD-TITULAR2] 2º titular partilha o email do 1º — "
                    "um único pedido cobre ambos os titulares."
                )

        return RGPDResponse(
            id=result["request_id"],
            process_id=data.process_id,
            client_name=data.client_name,
            client_email=data.client_email,
            status=RGPDStatusEnum.PENDING,
            token_expires_at=result["expires_at"],
            created_at="",
            created_by_name=user.get("name", ""),
            second_titular_name=second_titular_name,
            second_email_sent=second_email_sent,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro inesperado em request_rgpd: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")


async def run_resend_rgpd_email(request_id: str, request, user: dict):
    """Reenviar email de RGPD para o cliente (novo token)."""
    rgpd = await _get_rgpd_or_404(request_id)

    if rgpd["status"] == "signed":
        raise HTTPException(status_code=400, detail="Este RGPD já foi assinado")

    new_token = f"{uuid.uuid4().hex}{uuid.uuid4().hex}"
    new_expires = datetime.now(timezone.utc) + timedelta(hours=TOKEN_EXPIRY_HOURS)

    await db[RGPD_REQUESTS_COLLECTION].update_one(
        {"id": request_id},
        {
            "$set": {
                "token": new_token,
                "token_expires_at": new_expires.isoformat(),
                "status": "pending",
            }
        },
    )

    frontend_base_url = _frontend_base_url_from_request(request, log_prefix="[RGPD-RESEND]")

    # Pacote FQ-4 — envolver o envio de email num try/except dedicado para
    # devolver um erro elegante (400) quando as credenciais SMTP do sistema
    # estão inválidas, em vez de rebentar com um Erro 500 genérico.
    try:
        email_sent = await send_rgpd_email(
            client_email=rgpd["client_email"],
            client_name=rgpd["client_name"],
            token=new_token,
            request_id=request_id,
            user_email=user["email"],
            base_url=frontend_base_url,
            raise_on_error=True,
            process_id=rgpd.get("process_id"),
            user_id=user.get("id"),
        )
    except (smtplib.SMTPAuthenticationError, smtplib.SMTPException) as smtp_err:
        logger.error(
            f"[RGPD-RESEND] Falha SMTP ao reenviar email para {rgpd.get('client_email')}: {smtp_err}"
        )
        raise HTTPException(
            status_code=400,
            detail="Falha de autenticação SMTP no email do sistema. Verifique as credenciais.",
        )

    if not email_sent:
        raise HTTPException(status_code=500, detail="Erro ao enviar email")

    logger.info("RGPD email resent by user")

    return {
        "success": True,
        "message": "Email reenviado com sucesso",
        "expires_at": new_expires.isoformat(),
    }

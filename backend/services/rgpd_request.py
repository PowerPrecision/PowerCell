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
    """
    try:
        process = await db.processes.find_one({"id": data.process_id})
        if not process:
            raise HTTPException(status_code=404, detail="Processo não encontrado")

        result = await create_rgpd_request(
            process_id=data.process_id,
            client_name=data.client_name,
            client_email=data.client_email,
            user=user,
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

        return RGPDResponse(
            id=result["request_id"],
            process_id=data.process_id,
            client_name=data.client_name,
            client_email=data.client_email,
            status=RGPDStatusEnum.PENDING,
            token_expires_at=result["expires_at"],
            created_at="",
            created_by_name=user.get("name", ""),
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

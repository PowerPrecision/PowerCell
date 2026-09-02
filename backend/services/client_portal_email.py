"""Helper para enviar email de boas-vindas do Portal (fire-and-forget).

Extraído de `routes/clients.py`.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

async def _send_portal_welcome_email_safe(
    client_email: str,
    client_name: str,
    portal_access_code: str = None,
    client_id: str = None
) -> None:
    """Envia email de boas-vindas do Portal em background, com logs de erro."""
    try:
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
            logger.warning(f"[PORTAL-EMAIL] Task Queue indisponível para cliente {client_id}: {tq_err}")

        if not job_id:
            logger.info(f"[PORTAL-EMAIL] A enviar email diretamente para {client_email} (client_id={client_id})")
            try:
                sent = await send_registration_confirmation(
                    client_email=client_email,
                    client_name=client_name,
                    portal_access_code=portal_access_code,
                )
                if sent:
                    logger.info(f"[PORTAL-EMAIL] Email enviado com sucesso para {client_email} (client_id={client_id})")
                else:
                    logger.error(
                        f"[PORTAL-EMAIL] Falha ao enviar email de boas-vindas para {client_email} "
                        f"(client_id={client_id}) — ver logs de [EMAIL] acima para a razão."
                    )
            except Exception as direct_err:
                logger.error(f"[PORTAL-EMAIL] Falha ao enviar email diretamente para {client_email} "
                             f"(client_id={client_id}): {direct_err}", exc_info=True)
    except Exception as e:
        logger.error(f"[PORTAL-EMAIL] Erro inesperado no envio do email de boas-vindas "
                     f"para {client_email} (client_id={client_id}): {e}", exc_info=True)

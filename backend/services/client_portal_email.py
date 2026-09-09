"""Helper para enviar email de boas-vindas do Portal (fire-and-forget).

Extraído de `routes/clients.py`.

BUGFIX (E2E, Set 2026 — email de boas-vindas ausente no pré-registo):
a função era enfileirada no ARQ/Redis (`task_queue.send_registration_email`
→ job `send_registration_email_task`), mas NENHUM consumidor processa jobs
ARQ nesta base de código: o worker de produção arranca com `python
worker.py` (loop próprio que processa a fila Mongo por `task_type`), e o
worker ARQ (`arq worker.config.WorkerSettings`) não só nunca é lançado
como não tem a função registada. Com o Redis (Upstash) disponível, o
`enqueue()` devolvia um `job_id` — logo o fallback de envio directo
(`if not job_id:`) NUNCA executava e o email morria silenciosamente na
fila para sempre.

A entrega canónica passa a ser: (1) ENVIO DIRECTO primeiro — é o caminho
que funciona com ou sem worker; (2) em caso de falha real de envio
(SMP temporário, rede), enfileirar na task queue como retry de última
esperança (a task ARQ passa a estar registada em `worker/config.py`).
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


async def deliver_registration_email(
    client_email: str,
    client_name: str,
    portal_access_code: str = None,
    client_id: str = None,
) -> bool:
    """
    Entrega o email de boas-vindas/acesso ao Portal do Cliente.

    Ordem canónica (PACOTE BH):
    1. Envio DIRECTO (`send_registration_confirmation`) — funciona mesmo
       sem Redis/worker; é o caminho crítico do onboarding (pré-registo).
    2. Se o envio directo falhar, enfileira na task queue (ARQ) para
       retry posterior pelo worker — best-effort, nunca bloqueia.

    Returns:
        True se o email foi enviado com sucesso nesta chamada.
    """
    from services.email import send_registration_confirmation

    sent_direct = False
    try:
        sent_direct = await send_registration_confirmation(
            client_email=client_email,
            client_name=client_name,
            portal_access_code=portal_access_code,
        )
        if sent_direct:
            logger.info(
                f"[PORTAL-EMAIL] Email de boas-vindas enviado com sucesso "
                f"para {client_email} (client_id={client_id})"
            )
        else:
            logger.error(
                f"[PORTAL-EMAIL] Falha ao enviar email de boas-vindas para "
                f"{client_email} (client_id={client_id}) — ver logs de "
                f"[EMAIL] acima para a razão."
            )
    except Exception as direct_err:
        logger.error(
            f"[PORTAL-EMAIL] Erro no envio directo para {client_email} "
            f"(client_id={client_id}): {direct_err}",
            exc_info=True,
        )

    if sent_direct:
        return True

    # ── Retry de última esperança: enfileirar na task queue ──────────
    # A task `send_registration_email_task` está registada no worker ARQ
    # (worker/config.py) desde o PACOTE BH — quando o ARQ worker estiver
    # activo, o retry será processado; sem Redis, o enqueue devolve None
    # e ficamos apenas com o log de erro acima.
    try:
        from services.task_queue import task_queue

        job_id = await task_queue.send_registration_email(
            client_email=client_email,
            client_name=client_name,
            portal_access_code=portal_access_code,
        )
        if job_id:
            logger.info(
                f"[PORTAL-EMAIL] Email de boas-vindas para {client_email} "
                f"(client_id={client_id}) enfileirado para retry "
                f"(job={job_id}) após falha de envio directo."
            )
    except Exception as tq_err:
        logger.warning(
            f"[PORTAL-EMAIL] Task Queue indisponível para retry do cliente "
            f"{client_id}: {tq_err}"
        )
    return False


async def _send_portal_welcome_email_safe(
    client_email: str,
    client_name: str,
    portal_access_code: str = None,
    client_id: str = None
) -> None:
    """Envia email de boas-vindas do Portal em background, com logs de erro.

    Delega em `deliver_registration_email` (PACOTE BH — envio directo
    prioritário; fila ARQ apenas como retry).
    """
    try:
        await deliver_registration_email(
            client_email=client_email,
            client_name=client_name,
            portal_access_code=portal_access_code,
            client_id=client_id,
        )
    except Exception as e:
        logger.error(f"[PORTAL-EMAIL] Erro inesperado no envio do email de boas-vindas "
                     f"para {client_email} (client_id={client_id}): {e}", exc_info=True)

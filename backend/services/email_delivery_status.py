"""
====================================================================
PACOTE 10 — ESTADO DE ENTREGA DO EMAIL DE ACESSO AO PORTAL
====================================================================

PORQUÊ: antes do Pacote 10, a falha total do envio do email de boas-
vindas/acesso ao Portal (envio directo SMTP/Resend falhou E o retry
na fila também não confirmou entrega) ficava registada APENAS nos
logs do servidor. O staff nunca tomava conhecimento de que o cliente
não recebeu o código de acesso — o cliente ficava "preso" fora do
Portal sem que ninguém soubesse.

Este módulo resolve o problema em DUAS camadas complementares:

1. **Registo persistente no Cliente** (campo ``portal_email_delivery``):
   o doc do cliente passa a manter o último estado de entrega
   (``sent`` / ``failed`` / ``retry_scheduled``), com timestamps e
   o erro. Fonte de verdade para o alerta crítico do processo
   (services/alerts.py → "Email de acesso não entregue") e para o
   indicador visual na lista de clientes.

2. **Task log no monitor global** (colecção ``task_logs``, colecção
   que alimenta o widget "Processos em Segundo Plano" via
   GET /tasks/active): ciclo de vida pending → processing →
   completed/failed, visível na topbar de qualquer ecrã.

Toda a escrita é best-effort (degradação graciosa): uma falha a
gravar o estado NUNCA rebenta o fluxo de envio — apenas loga.

Convenções do repo: entrypoints prefixados com run_*, logs com
tags [PORTAL-EMAIL-DELIVERY], sem hardcode de config externa.
"""
from __future__ import annotations

import logging
from typing import Optional

from database import db
from models.task_log import TaskType
from services.task_log_service import task_log_service

logger = logging.getLogger(__name__)

# Estados possíveis de portal_email_delivery.status
DELIVERY_SENT = "sent"                # entregue com sucesso (envio directo)
DELIVERY_FAILED = "failed"            # falha definitiva (fallback também falhou)
DELIVERY_RETRY_SCHEDULED = "retry_scheduled"  # enfileirado no ARQ para retry

PORTAL_EMAIL_TASK_TITLE = "Email de acesso ao Portal"
PORTAL_EMAIL_TASK_DESCRIPTION = "Envio do email de boas-vindas com o código de acesso ao Portal do Cliente."


async def _set_client_delivery_status(
    client_id: Optional[str],
    status: str,
    error: Optional[str] = None,
) -> None:
    """Grava o estado de entrega no doc do cliente (best-effort)."""
    if not client_id:
        return
    from datetime import datetime, timezone

    update = {
        "status": status,
        "last_attempt_at": datetime.now(timezone.utc).isoformat(),
    }
    if error:
        update["error"] = str(error)[:500]
    try:
        await db.clients.update_one(
            {"id": client_id},
            {"$set": {"portal_email_delivery": update}},
        )
    except Exception as exc:  # pragma: no cover — degradação graciosa
        logger.warning(
            "[PORTAL-EMAIL-DELIVERY] Falha ao gravar estado '%s' no cliente %s: %s",
            status, client_id, exc,
        )


async def resolve_client_creator_user_id(
    client_id: Optional[str],
    fallback_user_id: Optional[str] = None,
) -> Optional[str]:
    """
    Resolve o user_id a associar ao task_log do email de acesso.

    Ordem: user_id explícito do chamador (fluxos staff) → lookup do
    criador do cliente (``clients.created_by`` guarda o EMAIL; a
    colecção users resolve email → id). Best-effort.
    """
    if fallback_user_id:
        return fallback_user_id
    if not client_id:
        return None
    try:
        client = await db.clients.find_one(
            {"id": client_id}, {"created_by": 1, "_id": 0}
        )
        creator_email = (client or {}).get("created_by")
        if not creator_email:
            return None
        creator = await db.users.find_one(
            {"email": creator_email}, {"id": 1, "_id": 0}
        )
        return (creator or {}).get("id")
    except Exception as exc:  # pragma: no cover — degradação graciosa
        logger.warning(
            "[PORTAL-EMAIL-DELIVERY] Falha ao resolver criador do cliente %s: %s",
            client_id, exc,
        )
        return None


async def begin_portal_email_task(
    client_id: Optional[str],
    client_email: Optional[str],
    *,
    user_id: Optional[str] = None,
    process_id: Optional[str] = None,
) -> Optional[str]:
    """
    Cria o task_log (pending) do envio do email de acesso.

    Devolve o task_id para o chamador completar/falhar, ou None quando
    não foi possível criar (sem user_id resolvível ou BD indisponível —
    o envio do email em si NÃO é afectado).
    """
    try:
        resolved_user_id = await resolve_client_creator_user_id(client_id, user_id)
        if not resolved_user_id:
            logger.info(
                "[PORTAL-EMAIL-DELIVERY] Task log omitido (user não resolvível) "
                "para cliente %s", client_id,
            )
            return None
        task = await task_log_service.create_task(
            task_type=TaskType.EMAIL_SEND,
            user_id=resolved_user_id,
            title=PORTAL_EMAIL_TASK_TITLE,
            description=(
                f"Destinatário: {client_email}" if client_email
                else PORTAL_EMAIL_TASK_DESCRIPTION
            ),
            process_id=process_id,
            metadata={"client_id": client_id, "kind": "portal_access_email"},
        )
        return task.task_id if task else None
    except Exception as exc:  # pragma: no cover — degradação graciosa
        logger.warning(
            "[PORTAL-EMAIL-DELIVERY] Falha ao criar task log para cliente %s: %s",
            client_id, exc,
        )
        return None


async def _update_task(
    task_id: Optional[str],
    **updates,
) -> None:
    if not task_id:
        return
    try:
        await task_log_service.update_task(task_id, **updates)
    except Exception as exc:  # pragma: no cover — degradação graciosa
        logger.warning(
            "[PORTAL-EMAIL-DELIVERY] Falha ao actualizar task log %s: %s",
            task_id, exc,
        )


async def complete_portal_email_task(
    task_id: Optional[str],
    client_id: Optional[str],
) -> None:
    """Entrega confirmada: task_log completed + estado 'sent' no cliente."""
    await _update_task(
        task_id,
        status="completed",
        progress=100,
        progress_message="Email de acesso entregue com sucesso.",
    )
    await _set_client_delivery_status(client_id, DELIVERY_SENT)


async def mark_portal_email_retry_scheduled(
    task_id: Optional[str],
    client_id: Optional[str],
) -> None:
    """
    Envio directo falhou mas o retry foi enfileirado (ARQ) — a entrega
    ainda pode acontecer. Estado 'retry_scheduled' (NÃO gera alerta
    crítico) e task_log continua em processamento.
    """
    await _update_task(
        task_id,
        status="processing",
        progress_message="Envio directo falhou — retry agendado na fila.",
    )
    await _set_client_delivery_status(client_id, DELIVERY_RETRY_SCHEDULED)


async def fail_portal_email_task(
    task_id: Optional[str],
    client_id: Optional[str],
    error: str,
) -> None:
    """
    Falha DEFINITIVA (fallback síncrono também falhou): task_log failed
    + estado 'failed' no cliente — dispara o alerta crítico
    "Email de acesso não entregue" nos Detalhes do Processo e o
    indicador vermelho na lista de clientes.
    """
    await _update_task(
        task_id,
        status="failed",
        error_message=str(error)[:500],
        progress_message="Email de acesso não entregue.",
    )
    await _set_client_delivery_status(client_id, DELIVERY_FAILED, error=error)

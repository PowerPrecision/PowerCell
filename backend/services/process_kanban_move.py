"""
Helpers para PUT /processes/kanban/{id}/move.

Extraído de `routes/processes.py` — flags dinâmicas do workflow (PACOTE BR)
e side-effects pós-persist (Trello, alerts, finance, waitlist, WS).

Nota: `process_kanban.move_process` é um helper mais antigo/simplificado
(VALID_STATUSES fixos); este módulo cobre o endpoint HTTP actual.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from database import db

logger = logging.getLogger(__name__)

# Fallbacks retrocompatíveis quando flags ainda não existem no workflow_status
_PROPERTY_CHECK_FALLBACK = ("ch_aprovado", "fase_escritura", "escritura_agendada")
_INACTIVE_FALLBACK = ("desistencias", "concluidos")


def resolve_workflow_purpose_flags(status_doc: dict, new_status: str) -> dict[str, bool]:
    """
    Lê flags de comportamento do workflow_status com fallback hardcoded.

    Returns:
        trigger_finance, trigger_countdown, trigger_property_check,
        trigger_deed_reminder, is_active
    """
    trigger_finance = status_doc.get("trigger_finance")
    if trigger_finance is None:
        trigger_finance = new_status == "concluidos"

    trigger_countdown = status_doc.get("trigger_countdown")
    if trigger_countdown is None:
        trigger_countdown = new_status == "fase_bancaria"

    trigger_property_check = status_doc.get("trigger_property_check")
    if trigger_property_check is None:
        trigger_property_check = new_status in _PROPERTY_CHECK_FALLBACK

    trigger_deed_reminder = status_doc.get("trigger_deed_reminder")
    if trigger_deed_reminder is None:
        trigger_deed_reminder = new_status == "escritura_agendada"

    is_active = status_doc.get("is_active")
    if is_active is None:
        is_active = new_status not in _INACTIVE_FALLBACK

    return {
        "trigger_finance": bool(trigger_finance),
        "trigger_countdown": bool(trigger_countdown),
        "trigger_property_check": bool(trigger_property_check),
        "trigger_deed_reminder": bool(trigger_deed_reminder),
        "is_active": bool(is_active),
    }


def build_kanban_move_update(new_status: str, is_active: bool) -> dict[str, Any]:
    """Campos $set do movimento Kanban (sem CDC)."""
    return {
        "status": new_status,
        "is_active": is_active,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


async def run_kanban_move_alerts(
    *,
    process: dict,
    process_id: str,
    user: dict,
    old_status: str,
    new_status: str,
    flags: dict[str, bool],
    deed_date: Optional[str],
    inject_cdc_fn,
) -> list[dict]:
    """Alertas automáticos baseados nas flags dinâmicas (PACOTE BR)."""
    from services.alerts import (
        check_property_documents,
        create_deed_reminder,
        notify_pre_approval_countdown,
        notify_cpcv_or_deed_document_check,
    )
    from services.audit_cdc import inject_cdc_context as _inject

    inject = inject_cdc_fn or _inject
    alerts: list[dict] = []

    if flags["trigger_property_check"]:
        property_check = await check_property_documents(process)
        if property_check.get("active"):
            alerts.append({
                "type": "property_docs",
                "message": property_check.get("message"),
                "details": property_check.get("details"),
            })
        await notify_cpcv_or_deed_document_check(process, new_status)
        alerts.append({
            "type": "document_verification_alert",
            "message": "Alerta enviado aos envolvidos para verificação de documentos",
        })

    if flags["trigger_countdown"] and old_status != new_status:
        if not process.get("credit_data", {}).get("bank_approval_date"):
            bank_approval_data = {
                "credit_data.bank_approval_date": datetime.now().strftime("%Y-%m-%d"),
            }
            inject(bank_approval_data, user)
            await db.processes.update_one(
                {"id": process_id},
                {"$set": bank_approval_data},
            )
        updated_process = await db.processes.find_one({"id": process_id}, {"_id": 0})
        await notify_pre_approval_countdown(updated_process)
        alerts.append({
            "type": "countdown_started",
            "message": "Countdown de 90 dias iniciado para pré-aprovação",
        })

    if flags["trigger_deed_reminder"]:
        if deed_date:
            deadline_id = await create_deed_reminder(process, deed_date, user)
            if deadline_id:
                alerts.append({
                    "type": "deed_reminder",
                    "message": (
                        f"Lembrete de escritura criado para 15 dias antes de {deed_date}"
                    ),
                })
        else:
            alerts.append({
                "type": "deed_date_needed",
                "message": (
                    "Escritura agendada sem data. Defina a data para criar "
                    "lembrete automático."
                ),
            })

    return alerts


async def notify_client_and_staff_status_change(
    process: dict,
    old_status: str,
    new_status: str,
    user: dict,
) -> None:
    """Email ao cliente + notificação in-app staff."""
    from services.notification_service import send_notification_with_preference_check
    from services.realtime_notifications import notify_process_status_change

    status_doc = await db.workflow_statuses.find_one({"name": new_status}, {"_id": 0})
    status_label = status_doc.get("label", new_status) if status_doc else new_status

    if process.get("client_email"):
        await send_notification_with_preference_check(
            process["client_email"],
            "Atualização do seu processo",
            f"O estado do seu processo foi atualizado para: {status_label}",
            notification_type="status_change",
        )

    await notify_process_status_change(
        process=process,
        old_status=old_status,
        new_status=new_status,
        new_status_label=status_label,
        changed_by=user,
    )


async def trigger_waitlist_on_inactive_move(
    process: dict,
    process_id: str,
    new_status: str,
    is_active: bool,
) -> None:
    """Se moveu para estado inativo com indexador, processa fila."""
    if is_active:
        return
    try:
        from services.process_assignment import check_waitlist_for_indexer
        assigned_indexer_id = process.get("assigned_indexacao_id")
        if assigned_indexer_id:
            asyncio.create_task(check_waitlist_for_indexer(assigned_indexer_id))
            logger.info(
                f"[KANBAN-MOVE-BR] Gatilho de fila de espera disparado para "
                f"indexador {assigned_indexer_id} (processo {process_id} → "
                f"{new_status}, is_active=False dinâmico)"
            )
    except Exception as waitlist_err:
        logger.warning(f"[KANBAN-MOVE] Erro ao verificar fila de espera: {waitlist_err}")


async def run_kanban_move_side_effects(
    *,
    process: dict,
    process_id: str,
    user: dict,
    old_status: str,
    new_status: str,
    flags: dict[str, bool],
    deed_date: Optional[str],
    broadcast_fn,
    create_finance_snapshot_fn,
    inject_cdc_fn,
) -> dict[str, Any]:
    """
    Pós-persist: Trello, cache, history, WS, finance, alerts, email, waitlist.

    Returns:
        Response dict do endpoint.
    """
    from services.history import log_history
    from services.trello_service import sync_process_to_trello
    from services.redis_cache import invalidate_stats_cache
    from services.websocket_manager import manager, WSEventType, create_ws_message

    _trello_move_proc = {
        **process,
        "status": new_status,
        "trello_card_id": process.get("trello_card_id"),
    }
    asyncio.create_task(
        sync_process_to_trello(_trello_move_proc, action="move", new_status=new_status)
    )

    await invalidate_stats_cache(user_id=user.get("id"))
    await log_history(process_id, user, "Moveu processo", "status", old_status, new_status)

    await broadcast_fn(
        event_type=WSEventType.PROCESS_STATUS_CHANGED,
        process_id=process_id,
        process_number=process.get("process_number"),
        client_name=process.get("client_name"),
        status=new_status,
        old_status=old_status,
        updated_at=datetime.now(timezone.utc).isoformat(),
    )

    moved_message = create_ws_message(
        WSEventType.PROCESS_MOVED,
        {
            "process_id": str(process_id),
            "process_number": process.get("process_number"),
            "client_name": process.get("client_name"),
            "new_status": new_status,
            "old_status": old_status,
            "user_id": str(user.get("id", "")),
            "user_name": user.get("name", "Unknown"),
        },
    )
    await manager.broadcast(moved_message, exclude_user=str(user.get("id", "")))

    if flags["trigger_finance"]:
        try:
            await create_finance_snapshot_fn(process, user)
        except Exception as snap_err:
            logger.warning(
                f"Falha ao criar snapshot financeiro para processo "
                f"{process_id}: {snap_err}"
            )

    alerts_generated = await run_kanban_move_alerts(
        process=process,
        process_id=process_id,
        user=user,
        old_status=old_status,
        new_status=new_status,
        flags=flags,
        deed_date=deed_date,
        inject_cdc_fn=inject_cdc_fn,
    )

    await notify_client_and_staff_status_change(
        process, old_status, new_status, user,
    )
    await trigger_waitlist_on_inactive_move(
        process, process_id, new_status, flags["is_active"],
    )

    return {
        "message": "Processo movido com sucesso",
        "new_status": new_status,
        "alerts": alerts_generated,
    }

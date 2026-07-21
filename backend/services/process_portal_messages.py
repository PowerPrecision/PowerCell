"""
Helpers de mensagens do portal (vista staff) em /processes/{id}/portal-messages.

Extraído de `routes/processes.py`.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Optional

from fastapi import HTTPException

from database import db

logger = logging.getLogger(__name__)


async def load_process_for_portal_or_404(process_id: str) -> dict:
    process = await db.processes.find_one(
        {"id": process_id, "is_deleted": {"$ne": True}},
        {"_id": 0},
    )
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")
    return process


def validate_staff_portal_message_content(content: Any) -> str:
    text = (content or "").strip() if isinstance(content, str) else str(content or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="A mensagem não pode estar vazia.")
    if len(text) > 5000:
        raise HTTPException(
            status_code=400,
            detail="A mensagem não pode exceder 5000 caracteres.",
        )
    return text


def build_staff_portal_message_doc(
    *,
    process_id: str,
    user: dict,
    content: str,
    now: str,
    message_id: Optional[str] = None,
) -> dict[str, Any]:
    mid = message_id or str(uuid.uuid4())
    return {
        "id": mid,
        "process_id": process_id,
        "sender_type": "staff",
        "sender_id": user.get("id", ""),
        "sender_name": user.get("name", "Staff"),
        "content": content,
        "created_at": now,
        "read_by_client": False,
        "read_by_staff": True,
    }


def staff_portal_message_response(message_doc: dict) -> dict[str, Any]:
    """Resposta sem `_id` Mongo."""
    return {
        "id": message_doc["id"],
        "process_id": message_doc["process_id"],
        "sender_type": message_doc["sender_type"],
        "sender_id": message_doc["sender_id"],
        "sender_name": message_doc["sender_name"],
        "content": message_doc["content"],
        "created_at": message_doc["created_at"],
        "read_by_client": message_doc.get("read_by_client", False),
        "read_by_staff": message_doc.get("read_by_staff", True),
    }


async def count_unread_client_portal_messages(process_id: str) -> int:
    try:
        return await db.portal_messages.count_documents({
            "process_id": process_id,
            "sender_type": "client",
            "read_by_staff": False,
        })
    except Exception as e:
        logger.error(f"[PROCESS] Erro ao contar mensagens não lidas do portal: {e}")
        return 0


async def list_portal_messages_for_staff(process_id: str) -> dict[str, Any]:
    """Lista até 100 msgs e marca as do cliente como lidas pelo staff."""
    try:
        messages = await db.portal_messages.find(
            {"process_id": process_id},
            {"_id": 0},
        ).sort("created_at", 1).limit(100).to_list(100)

        try:
            await db.portal_messages.update_many(
                {
                    "process_id": process_id,
                    "sender_type": "client",
                    "read_by_staff": False,
                },
                {"$set": {"read_by_staff": True}},
            )
        except Exception as e:
            logger.warning(
                f"[PROCESS] Erro ao marcar mensagens do portal como lidas: {e}"
            )

        return {
            "messages": messages,
            "total": len(messages),
            "process_id": process_id,
        }
    except Exception as e:
        logger.error(f"[PROCESS] Erro ao listar mensagens do portal: {e}")
        raise HTTPException(
            status_code=500,
            detail="Erro ao carregar mensagens do portal.",
        )


async def insert_staff_portal_message(message_doc: dict, *, user_email: str) -> None:
    try:
        await db.portal_messages.insert_one(message_doc)
        logger.info(
            f"[PROCESS] Mensagem do portal enviada por {user_email} "
            f"para processo {message_doc.get('process_id')}"
        )
    except Exception as e:
        logger.error(f"[PROCESS] Erro ao enviar mensagem do portal: {e}")
        raise HTTPException(
            status_code=500,
            detail="Erro ao enviar mensagem. Tente novamente.",
        )


def collect_assigned_user_ids(process: dict) -> list:
    """Delega a portal._get_all_assigned_user_ids (fonte de verdade)."""
    from routes.portal import _get_all_assigned_user_ids
    return _get_all_assigned_user_ids(process)


async def notify_team_email_portal_message(
    process: dict,
    sender: dict,
    process_id: str,
) -> None:
    """Email/preferências aos outros membros atribuídos (exclui remetente)."""
    from services.notification_service import send_notification_with_preference_check

    assigned_ids = collect_assigned_user_ids(process)
    sender_id = sender.get("id", "")
    process_ref = process.get("process_number", process_id)
    sender_name = sender.get("name", "Membro da equipa")
    client_name = process.get("client_name", "Cliente")

    for uid in assigned_ids:
        if uid == sender_id:
            continue
        try:
            team_user = await db.users.find_one(
                {"id": uid}, {"name": 1, "email": 1},
            )
            if team_user and team_user.get("email"):
                await send_notification_with_preference_check(
                    team_user["email"],
                    "Nova Mensagem no Processo",
                    (
                        f"{sender_name} enviou uma mensagem ao cliente "
                        f"{client_name} no processo #{process_ref}."
                    ),
                    notification_type="portal_message",
                )
        except Exception as e:
            logger.warning(
                f"Erro ao notificar membro {uid} sobre mensagem do portal: {e}"
            )


async def notify_assigned_realtime_portal_message(
    process: dict,
    sender: dict,
    process_id: str,
) -> None:
    """Notificações in-app realtime aos atribuídos (exclui remetente)."""
    try:
        assigned_ids = collect_assigned_user_ids(process)
        sender_id = sender.get("id", "")
        process_number = process.get("process_number", "")
        process_ref = (
            f"#{process_number}" if process_number else process_id[:8]
        )

        for uid in assigned_ids:
            if uid == sender_id:
                continue
            try:
                from services.realtime_notifications import send_realtime_notification
                await send_realtime_notification(
                    user_id=uid,
                    title="Nova Mensagem Interna",
                    message=(
                        f"{sender.get('name', 'Staff')} enviou uma mensagem "
                        f"no processo {process_ref}."
                    ),
                    notification_type="portal_message",
                    link=f"/processes/{process_id}",
                    process_id=process_id,
                )
            except Exception as notif_err:
                logger.debug(
                    f"Erro ao notificar membro {uid} sobre mensagem interna: "
                    f"{notif_err}"
                )
    except Exception as e:
        logger.warning(
            f"Erro ao notificar equipa sobre mensagem do portal: {e}"
        )


async def broadcast_staff_portal_message_ws(
    *,
    process_id: str,
    message_doc: dict,
    content: str,
    exclude_user_id: Optional[str],
) -> None:
    try:
        from services.websocket_manager import manager, WSEventType, create_ws_message
        ws_message = create_ws_message(WSEventType.PORTAL_MESSAGE, {
            "id": message_doc["id"],
            "process_id": process_id,
            "sender_type": "staff",
            "sender_id": message_doc.get("sender_id", ""),
            "sender_name": message_doc.get("sender_name", "Staff"),
            "content": content[:200],
            "created_at": message_doc.get("created_at"),
        })
        await manager.broadcast_to_room(
            f"process_{process_id}",
            ws_message,
            exclude_user=exclude_user_id,
        )
    except Exception as ws_err:
        logger.debug(
            f"Erro ao broadcast mensagem staff via WebSocket: {ws_err}"
        )

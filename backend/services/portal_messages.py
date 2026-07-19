"""
====================================================================
SERVIÇO DE MENSAGENS DO PORTAL (STAFF) - CREDITOIMO
====================================================================
Operações do lado staff sobre portal_messages: contagem de não lidas,
listagem (com mark-as-read), envio e notificações à equipa.

Extraído de routes/processes.py.
====================================================================
"""
import uuid
import logging
from datetime import datetime, timezone
from fastapi import HTTPException

from database import db
from services.process_assignment import get_all_assigned_user_ids
from services.notification_service import send_notification_with_preference_check
from services.websocket_manager import manager, WSEventType, create_ws_message

logger = logging.getLogger(__name__)


async def _get_active_process(process_id: str) -> dict:
    process = await db.processes.find_one(
        {"id": process_id, "is_deleted": {"$ne": True}},
        {"_id": 0}
    )
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")
    return process


async def count_unread_for_staff(process_id: str) -> dict:
    """Conta mensagens do cliente ainda não lidas pelo staff."""
    await _get_active_process(process_id)

    try:
        count = await db.portal_messages.count_documents({
            "process_id": process_id,
            "sender_type": "client",
            "read_by_staff": False,
        })
        return {"unread_count": count}
    except Exception as e:
        logger.error(f"[PROCESS] Erro ao contar mensagens não lidas do portal: {e}")
        return {"unread_count": 0}


async def list_messages_for_staff(process_id: str) -> dict:
    """Lista mensagens do portal e marca as do cliente como lidas pelo staff."""
    await _get_active_process(process_id)

    try:
        messages = await db.portal_messages.find(
            {"process_id": process_id},
            {"_id": 0}
        ).sort("created_at", 1).limit(100).to_list(100)

        try:
            await db.portal_messages.update_many(
                {
                    "process_id": process_id,
                    "sender_type": "client",
                    "read_by_staff": False,
                },
                {"$set": {"read_by_staff": True}}
            )
        except Exception as e:
            logger.warning(f"[PROCESS] Erro ao marcar mensagens do portal como lidas: {e}")

        return {
            "messages": messages,
            "total": len(messages),
            "process_id": process_id,
        }
    except Exception as e:
        logger.error(f"[PROCESS] Erro ao listar mensagens do portal: {e}")
        raise HTTPException(
            status_code=500,
            detail="Erro ao carregar mensagens do portal."
        )


async def notify_team_portal_message(process: dict, sender: dict, process_id: str):
    """Notifica outros membros da equipa atribuída (email/preferências).

    O remetente NÃO recebe notificação.
    """
    assigned_ids = get_all_assigned_user_ids(process)
    sender_id = sender.get("id", "")
    process_ref = process.get("process_number", process_id)
    sender_name = sender.get("name", "Membro da equipa")
    client_name = process.get("client_name", "Cliente")

    for uid in assigned_ids:
        if uid == sender_id:
            continue
        try:
            team_user = await db.users.find_one({"id": uid}, {"name": 1, "email": 1})
            if team_user and team_user.get("email"):
                await send_notification_with_preference_check(
                    team_user["email"],
                    "Nova Mensagem no Processo",
                    f"{sender_name} enviou uma mensagem ao cliente {client_name} "
                    f"no processo #{process_ref}.",
                    notification_type="portal_message"
                )
        except Exception as e:
            logger.warning(f"Erro ao notificar membro {uid} sobre mensagem do portal: {e}")


async def send_staff_message(process_id: str, content: str, user: dict) -> dict:
    """Envia mensagem do staff para o cliente via portal + notificações."""
    process = await _get_active_process(process_id)

    content = (content or "").strip()
    if not content:
        raise HTTPException(status_code=400, detail="A mensagem não pode estar vazia.")
    if len(content) > 5000:
        raise HTTPException(
            status_code=400,
            detail="A mensagem não pode exceder 5000 caracteres.",
        )

    now = datetime.now(timezone.utc).isoformat()
    message_id = str(uuid.uuid4())

    message_doc = {
        "id": message_id,
        "process_id": process_id,
        "sender_type": "staff",
        "sender_id": user.get("id", ""),
        "sender_name": user.get("name", "Staff"),
        "content": content,
        "created_at": now,
        "read_by_client": False,
        "read_by_staff": True,
    }

    try:
        await db.portal_messages.insert_one(message_doc)
        logger.info(
            f"[PROCESS] Mensagem do portal enviada por {user.get('email')} "
            f"para processo {process_id}"
        )
    except Exception as e:
        logger.error(f"[PROCESS] Erro ao enviar mensagem do portal: {e}")
        raise HTTPException(
            status_code=500,
            detail="Erro ao enviar mensagem. Tente novamente."
        )

    await notify_team_portal_message(process, user, process_id)

    try:
        from services.realtime_notifications import send_realtime_notification
        assigned_ids = get_all_assigned_user_ids(process)
        sender_id = user.get("id", "")
        process_number = process.get("process_number", "")
        process_ref = f"#{process_number}" if process_number else process_id[:8]

        for uid in assigned_ids:
            if uid == sender_id:
                continue
            try:
                await send_realtime_notification(
                    user_id=uid,
                    title="Nova Mensagem Interna",
                    message=(
                        f"{user.get('name', 'Staff')} enviou uma mensagem "
                        f"no processo {process_ref}."
                    ),
                    notification_type="portal_message",
                    link=f"/processes/{process_id}",
                    process_id=process_id,
                )
            except Exception as notif_err:
                logger.debug(
                    f"Erro ao notificar membro {uid} sobre mensagem interna: {notif_err}"
                )
    except Exception as e:
        logger.warning(f"Erro ao notificar equipa sobre mensagem do portal: {e}")

    try:
        ws_message = create_ws_message(WSEventType.PORTAL_MESSAGE, {
            "id": message_id,
            "process_id": process_id,
            "sender_type": "staff",
            "sender_id": user.get("id", ""),
            "sender_name": user.get("name", "Staff"),
            "content": content[:200],
            "created_at": now,
        })
        await manager.broadcast_to_room(
            f"process_{process_id}", ws_message, exclude_user=user.get("id")
        )
    except Exception as ws_err:
        logger.debug(f"Erro ao broadcast mensagem staff via WebSocket: {ws_err}")

    return {
        "id": message_id,
        "process_id": process_id,
        "sender_type": "staff",
        "sender_id": user.get("id", ""),
        "sender_name": user.get("name", "Staff"),
        "content": content,
        "created_at": now,
        "read_by_client": False,
        "read_by_staff": True,
    }

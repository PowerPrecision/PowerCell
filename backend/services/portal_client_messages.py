"""Mensagens do cliente no Portal (não confundir com process_portal_messages).

Extraído de `routes/portal.py`.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException

from database import db
from services.portal_assigned_users import get_all_assigned_user_ids as _get_all_assigned_user_ids
from services.notification_service import send_notification_with_preference_check
from services.websocket_manager import manager, WSEventType, create_ws_message

logger = logging.getLogger(__name__)


async def _notify_assigned_team_message(process: dict, process_id: str, client_name: str, message_doc: dict):
    """Notifica TODOS os utilizadores atribuídos ao processo sobre uma nova mensagem do cliente.
    
    Também faz broadcast da mensagem para a sala WebSocket do processo (process_{process_id})
    para que qualquer membro da equipa com o processo aberto veja a mensagem em tempo real.
    """
    # ── Recolher TODOS os IDs de utilizadores atribuídos ──
    assigned_ids = _get_all_assigned_user_ids(process)
    if not assigned_ids:
        return

    process_number = process.get("process_number", "")
    process_ref = f"#{process_number}" if process_number else process_id[:8]
    
    # ── Notificar cada utilizador atribuído (email + in-app notification) ──
    for uid in assigned_ids:
        try:
            user = await db.users.find_one({"id": uid}, {"name": 1, "email": 1})
            if not user:
                continue
            
            # Email notification (com verificação de preferências)
            await send_notification_with_preference_check(
                user.get("email"),
                "Nova Mensagem do Cliente",
                f"O cliente {client_name} enviou uma mensagem no processo {process_ref}.",
                notification_type="portal_message"
            )
            
            # In-app notification (em tempo real via WebSocket)
            try:
                from services.realtime_notifications import send_realtime_notification
                await send_realtime_notification(
                    user_id=uid,
                    title="Nova Mensagem do Cliente",
                    message=f"O cliente {client_name} enviou uma mensagem no processo {process_ref}.",
                    notification_type="portal_message",
                    link=f"/processes/{process_id}",
                    process_id=process_id,
                )
            except Exception as notif_err:
                logger.debug(f"Erro ao enviar notificação in-app para {uid}: {notif_err}")
                
        except Exception as e:
            logger.warning(f"Erro ao notificar utilizador {uid} sobre mensagem do portal: {e}")
    
    # ── Broadcast para a sala WebSocket do processo ──
    try:
        ws_message = create_ws_message(WSEventType.PORTAL_MESSAGE, {
            "id": message_doc.get("id"),
            "process_id": process_id,
            "sender_type": "client",
            "sender_id": "client",
            "sender_name": client_name,
            "content": message_doc.get("content", "")[:200],
            "created_at": message_doc.get("created_at"),
        })
        await manager.broadcast_to_room(f"process_{process_id}", ws_message)
    except Exception as ws_err:
        logger.debug(f"Erro ao broadcast mensagem do portal via WebSocket: {ws_err}")
    
    logger.info(
        f"[PORTAL] Notificados {len(assigned_ids)} utilizadores sobre mensagem "
        f"do cliente {client_name} no processo {process_ref}"
    )


async def run_get_unread_messages_count(client_data: dict):
    """
    Conta mensagens não lidas do staff para este cliente.

    Retorna o número de mensagens enviadas pelo staff que o cliente
    ainda não leu (read_by_client=False).
    """
    process_id = client_data["process_id"]

    try:
        count = await db.portal_messages.count_documents({
            "process_id": process_id,
            "sender_type": "staff",
            "read_by_client": False,
        })
        return {"unread_count": count}
    except Exception as e:
        logger.error(f"[PORTAL] Erro ao contar mensagens não lidas: {e}")
        return {"unread_count": 0}


async def run_get_portal_messages(client_data: dict):
    """
    Lista mensagens do processo para o cliente.

    Retorna as últimas 100 mensagens ordenadas por data de criação
    ascendente (mais antigas primeiro). Ao listar, marca automaticamente
    as mensagens do staff como lidas pelo cliente (read_by_client=True).
    """
    process_id = client_data["process_id"]

    try:
        # Buscar últimas 100 mensagens
        messages = await db.portal_messages.find(
            {"process_id": process_id},
            {"_id": 0}
        ).sort("created_at", 1).limit(100).to_list(100)

        # Marcar mensagens do staff como lidas pelo cliente
        try:
            await db.portal_messages.update_many(
                {
                    "process_id": process_id,
                    "sender_type": "staff",
                    "read_by_client": False,
                },
                {"$set": {"read_by_client": True}}
            )
        except Exception as e:
            logger.warning(f"[PORTAL] Erro ao marcar mensagens como lidas: {e}")

        return {
            "messages": messages,
            "total": len(messages),
        }
    except Exception as e:
        logger.error(f"[PORTAL] Erro ao listar mensagens: {e}")
        raise HTTPException(
            status_code=500,
            detail="Erro ao carregar mensagens. Tente novamente."
        )


async def run_send_portal_message(data: dict, client_data: dict):
    """
    Envia uma mensagem do cliente para o staff.

    Body:
    - content: Texto da mensagem (obrigatório)
    """
    process = client_data["process"]
    process_id = client_data["process_id"]

    content = data.get("content", "").strip()
    if not content:
        raise HTTPException(status_code=400, detail="A mensagem não pode estar vazia.")
    if len(content) > 5000:
        raise HTTPException(status_code=400, detail="A mensagem não pode exceder 5000 caracteres.")

    now = datetime.now(timezone.utc).isoformat()
    message_id = str(uuid.uuid4())
    client_name = process.get("client_name", "Cliente")

    message_doc = {
        "id": message_id,
        "process_id": process_id,
        "sender_type": "client",
        "sender_id": "client",
        "sender_name": client_name,
        "content": content,
        "created_at": now,
        "read_by_client": True,
        "read_by_staff": False,
    }

    try:
        await db.portal_messages.insert_one(message_doc)
        logger.info(f"[PORTAL] Mensagem enviada pelo cliente para processo {process_id}")
    except Exception as e:
        logger.error(f"[PORTAL] Erro ao enviar mensagem: {e}")
        raise HTTPException(
            status_code=500,
            detail="Erro ao enviar mensagem. Tente novamente."
        )

    # Notificar TODOS os utilizadores atribuídos sobre a nova mensagem do cliente
    await _notify_assigned_team_message(process, process_id, client_name, message_doc)

    # Return without MongoDB _id
    return {
        "id": message_id,
        "process_id": process_id,
        "sender_type": "client",
        "sender_id": "client",
        "sender_name": client_name,
        "content": content,
        "created_at": now,
        "read_by_client": True,
        "read_by_staff": False,
    }



"""Typing, unread, online users, chat directory.

Extraído de `routes/chat.py`.
"""
from __future__ import annotations

from typing import Optional

from fastapi import HTTPException

from database import db
from models.chat import TypingIndicator
from services.websocket_manager import manager, create_ws_message
from services.chat_helpers import _block_parceiro


async def run_send_typing_indicator(typing: TypingIndicator, user: dict):
    """
    Enviar indicador de digitação.
    """
    user_id = user["id"]

    if typing.group_id:
        # Verificar acesso ao grupo
        is_member = await db.chat_groups.find_one(
            {"id": typing.group_id, "members.user_id": user_id}
        )
        if not is_member:
            raise HTTPException(status_code=403, detail="Sem acesso a este grupo")

        # Notificar membros do grupo
        for member in is_member.get("members", []):
            member_id = member.get("user_id")
            if member_id and member_id != user_id:
                await manager.send_personal_message(
                    create_ws_message("chat_typing", {
                        "user_id": user_id,
                        "user_name": user.get("name", ""),
                        "group_id": typing.group_id,
                        "is_typing": typing.is_typing
                    }),
                    member_id
                )

    elif typing.receiver_id:
        await manager.send_personal_message(
            create_ws_message("chat_typing", {
                "user_id": user_id,
                "user_name": user.get("name", ""),
                "receiver_id": typing.receiver_id,
                "is_typing": typing.is_typing
            }),
            typing.receiver_id
        )

    return {"success": True}


async def run_get_unread_count(user: dict):
    """
    Obter contagem total de mensagens não lidas.
    """
    _block_parceiro(user)
    user_id = user["id"]

    # Mensagens diretas não lidas
    direct_unread = await db.chat_messages.count_documents({
        "receiver_id": user_id,
        "read": False,
        "group_id": None
    })

    # Mensagens de grupos não lidas
    groups = await db.chat_groups.find(
        {"members.user_id": user_id},
        {"id": 1, "members": 1}
    ).to_list(50)

    group_unread = 0
    for group in groups:
        last_read = None
        for member in group.get("members", []):
            if member.get("user_id") == user_id:
                last_read = member.get("last_read")
                break

        query = {"group_id": group["id"]}
        if last_read:
            query["created_at"] = {"$gt": last_read}

        group_unread += await db.chat_messages.count_documents(query)

    return {
        "unread_count": direct_unread + group_unread,
        "direct_unread": direct_unread,
        "group_unread": group_unread
    }


async def run_get_online_users(user: dict):
    """
    Obter lista de utilizadores online.
    """
    _block_parceiro(user)
    connected_ids = manager.get_connected_users()

    if not connected_ids:
        return {"users": []}

    users = await db.users.find(
        {"id": {"$in": connected_ids}, "is_active": {"$ne": False}},
        {"_id": 0, "id": 1, "name": 1, "role": 1}
    ).to_list(100)

    return {"users": users}


async def run_get_chat_users(user: dict, search: Optional[str] = None):
    """
    Obter lista de utilizadores disponíveis para chat.
    """
    _block_parceiro(user)
    user_id = user["id"]

    query = {
        "id": {"$ne": user_id},
        "is_active": {"$ne": False}
    }

    if search:
        query["$or"] = [
            {"name": {"$regex": search, "$options": "i"}},
            {"email": {"$regex": search, "$options": "i"}}
        ]

    users = await db.users.find(
        query,
        {"_id": 0, "id": 1, "name": 1, "role": 1, "email": 1}
    ).sort("name", 1).limit(50).to_list(50)

    # Adicionar status online
    for u in users:
        u["is_online"] = manager.is_user_connected(u["id"])

    return {"users": users}

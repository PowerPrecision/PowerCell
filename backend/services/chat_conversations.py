"""Conversation list endpoint.

Extraído de `routes/chat.py`.
"""
from __future__ import annotations

from database import db
from services.websocket_manager import manager
from services.chat_helpers import _block_parceiro


async def run_get_conversations(user: dict):
    """
    Obter lista de conversas do utilizador.
    Inclui conversas diretas e grupos.
    """
    _block_parceiro(user)
    user_id = user["id"]

    # Pipeline para conversas diretas
    direct_pipeline = [
        {
            "$match": {
                "sender_id": {"$exists": True},
                "receiver_id": {"$exists": True},
                "$or": [
                    {"sender_id": user_id},
                    {"receiver_id": user_id}
                ],
                "group_id": None
            }
        },
        {"$sort": {"created_at": -1}},
        {
            "$group": {
                "_id": {
                    "$cond": [
                        {"$eq": ["$sender_id", user_id]},
                        "$receiver_id",
                        "$sender_id"
                    ]
                },
                "last_message": {"$first": "$content"},
                "last_message_time": {"$first": "$created_at"},
                "unread_count": {
                    "$sum": {
                        "$cond": [
                            {"$and": [
                                {"$eq": ["$receiver_id", user_id]},
                                {"$eq": ["$read", False]}
                            ]},
                            1, 0
                        ]
                    }
                }
            }
        },
        {"$sort": {"last_message_time": -1}}
    ]

    direct_conversations = await db.chat_messages.aggregate(direct_pipeline).to_list(100)

    conversations = []

    # Processar conversas diretas
    for conv in direct_conversations:
        other_user_id = conv["_id"]
        other_user = await db.users.find_one(
            {"id": other_user_id},
            {"_id": 0, "id": 1, "name": 1, "role": 1}
        )

        if other_user:
            conversations.append({
                "user_id": other_user["id"],
                "user_name": other_user.get("name", "Utilizador"),
                "user_role": other_user.get("role", ""),
                "last_message": conv["last_message"][:50] + "..." if len(conv["last_message"]) > 50 else conv["last_message"],
                "last_message_time": conv["last_message_time"],
                "unread_count": conv["unread_count"],
                "is_online": manager.is_user_connected(other_user_id),
                "is_group": False
            })

    # Buscar grupos do utilizador
    groups = await db.chat_groups.find(
        {"members.user_id": user_id},
        {"_id": 0}
    ).to_list(50)

    for group in groups:
        # Última mensagem do grupo
        last_msg = await db.chat_messages.find_one(
            {"group_id": group["id"]},
            sort=[("created_at", -1)]
        )

        # Contar não lidas
        last_read = None
        for member in group.get("members", []):
            if member.get("user_id") == user_id:
                last_read = member.get("last_read")
                break

        unread_query = {"group_id": group["id"]}
        if last_read:
            unread_query["created_at"] = {"$gt": last_read}

        unread_count = await db.chat_messages.count_documents(unread_query)

        conversations.append({
            "group_id": group["id"],
            "group_name": group["name"],
            "last_message": last_msg["content"][:50] + "..." if last_msg and last_msg.get("content") else "Sem mensagens",
            "last_message_time": last_msg["created_at"] if last_msg else group.get("created_at", ""),
            "unread_count": unread_count,
            "is_group": True,
            "members": group.get("members", [])[:3]  # Primeiros 3 membros para preview
        })

    # Ordenar por última mensagem
    conversations.sort(key=lambda x: x.get("last_message_time", ""), reverse=True)

    return {"conversations": conversations}

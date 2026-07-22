"""Message CRUD, upload, reactions, search.

Extraído de `routes/chat.py`.
"""
from __future__ import annotations

import base64
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4
from mimetypes import guess_type

from fastapi import HTTPException, UploadFile

from database import db
from models.chat import (
    ChatMessageCreate, ChatMessageReaction, ChatMessageEdit, ChatSearchQuery
)
from services.websocket_manager import manager, create_ws_message
from utils.input_sanitization import sanitize_string
from services.chat_helpers import (
    _block_parceiro, MAX_ATTACHMENT_SIZE, ALLOWED_ATTACHMENT_TYPES
)


async def run_get_messages(
    conversation_id: str,
    user: dict,
    limit: int = 50,
    before: Optional[str] = None,
    is_group: bool = False,
):
    """
    Obter mensagens de uma conversa.
    conversation_id pode ser user_id (direto) ou group_id (grupo).
    """
    _block_parceiro(user)
    user_id = user["id"]

    if is_group:
        # Verificar se é membro do grupo
        group = await db.chat_groups.find_one(
            {"id": conversation_id, "members.user_id": user_id},
            {"_id": 0}
        )
        if not group:
            raise HTTPException(status_code=403, detail="Não tem acesso a este grupo")

        query = {"group_id": conversation_id}

        # Actualizar último lido
        await db.chat_groups.update_one(
            {"id": conversation_id, "members.user_id": user_id},
            {"$set": {"members.$[elem].last_read": datetime.now(timezone.utc).isoformat()}},
            array_filters=[{"elem.user_id": user_id}]
        )
    else:
        # Chat direto
        other_user = await db.users.find_one({"id": conversation_id}, {"_id": 0, "id": 1, "name": 1})
        if not other_user:
            raise HTTPException(status_code=404, detail="Utilizador não encontrado")

        query = {
            "$or": [
                {"sender_id": user_id, "receiver_id": conversation_id},
                {"sender_id": conversation_id, "receiver_id": user_id}
            ],
            "group_id": None
        }

    if before:
        query["created_at"] = {"$lt": before}

    messages = await db.chat_messages.find(
        query,
        {"_id": 0}
    ).sort("created_at", -1).limit(limit).to_list(limit)

    # Marcar mensagens como lidas (só para chat direto)
    if not is_group:
        await db.chat_messages.update_many(
            {
                "sender_id": conversation_id,
                "receiver_id": user_id,
                "read": False
            },
            {"$set": {"read": True, "read_at": datetime.now(timezone.utc).isoformat()}}
        )

        # Notificar via WebSocket
        await manager.send_personal_message(
            create_ws_message("chat_messages_read", {
                "reader_id": user_id,
                "conversation_with": conversation_id
            }),
            conversation_id
        )

    # Enriquecer mensagens com dados de reply_to
    enriched_messages = []
    for msg in reversed(messages):
        if msg.get("reply_to"):
            reply_msg = await db.chat_messages.find_one(
                {"id": msg["reply_to"]},
                {"_id": 0, "id": 1, "content": 1, "sender_name": 1, "created_at": 1}
            )
            msg["reply_to_data"] = reply_msg
        enriched_messages.append(msg)

    return {
        "messages": enriched_messages,
        "other_user": None if is_group else {"id": conversation_id, "name": other_user.get("name")} if not is_group else None,
        "group": group if is_group else None
    }


async def run_send_message(message: ChatMessageCreate, user: dict):
    """
    Enviar uma nova mensagem (direta ou para grupo).
    """
    _block_parceiro(user)
    user_id = user["id"]

    # Sanitizar conteúdo da mensagem antes de guardar
    sanitized_content = sanitize_string(message.content, max_length=5000) if message.content else message.content

    if message.group_id:
        # Mensagem para grupo
        group = await db.chat_groups.find_one(
            {"id": message.group_id, "members.user_id": user_id},
            {"_id": 0, "name": 1, "members": 1}
        )
        if not group:
            raise HTTPException(status_code=403, detail="Não tem acesso a este grupo")

        msg_doc = {
            "id": str(uuid4()),
            "sender_id": user_id,
            "sender_name": user.get("name", ""),
            "group_id": message.group_id,
            "group_name": group["name"],
            "content": sanitized_content,
            "reply_to": message.reply_to,
            "reactions": [],
            "attachments": [],
            "edited": False,
            "read": True,  # Grupos não têm read individual
            "created_at": datetime.now(timezone.utc).isoformat()
        }

        await db.chat_messages.insert_one(msg_doc)

        # Notificar todos os membros do grupo
        for member in group.get("members", []):
            member_id = member.get("user_id")
            if member_id and member_id != user_id:
                await manager.send_personal_message(
                    create_ws_message("new_chat_message", {
                        "id": msg_doc["id"],
                        "sender_id": user_id,
                        "sender_name": user.get("name", ""),
                        "group_id": message.group_id,
                        "group_name": group["name"],
                        "content": message.content[:100],
                        "created_at": msg_doc["created_at"]
                    }),
                    member_id
                )

    elif message.receiver_id:
        # Mensagem direta
        receiver = await db.users.find_one({"id": message.receiver_id}, {"_id": 0, "id": 1, "name": 1})
        if not receiver:
            raise HTTPException(status_code=404, detail="Destinatário não encontrado")

        msg_doc = {
            "id": str(uuid4()),
            "sender_id": user_id,
            "sender_name": user.get("name", ""),
            "receiver_id": message.receiver_id,
            "receiver_name": receiver.get("name", ""),
            "content": sanitized_content,
            "process_id": message.process_id,
            "reply_to": message.reply_to,
            "reactions": [],
            "attachments": [],
            "edited": False,
            "read": False,
            "created_at": datetime.now(timezone.utc).isoformat()
        }

        await db.chat_messages.insert_one(msg_doc)

        # Notificar destinatário
        await manager.send_personal_message(
            create_ws_message("new_chat_message", {
                "id": msg_doc["id"],
                "sender_id": user_id,
                "sender_name": user.get("name", ""),
                "receiver_id": message.receiver_id,
                "content": message.content[:100],
                "process_id": message.process_id,
                "created_at": msg_doc["created_at"]
            }),
            message.receiver_id
        )
    else:
        raise HTTPException(status_code=400, detail="Deve especificar receiver_id ou group_id")

    msg_doc.pop("_id", None)
    return {"success": True, "message": msg_doc}


async def run_upload_message_with_attachment(
    user: dict,
    file: UploadFile,
    receiver_id: Optional[str] = None,
    group_id: Optional[str] = None,
    content: Optional[str] = "",
):
    """
    Enviar mensagem com anexo.
    """
    _block_parceiro(user)
    user_id = user["id"]

    # Validar ficheiro
    if file.size > MAX_ATTACHMENT_SIZE:
        raise HTTPException(status_code=400, detail="Ficheiro demasiado grande (máx 10MB)")

    content_type = file.content_type or guess_type(file.filename)[0] or "application/octet-stream"
    if content_type not in ALLOWED_ATTACHMENT_TYPES:
        raise HTTPException(status_code=400, detail=f"Tipo de ficheiro não permitido: {content_type}")

    # Ler e codificar ficheiro
    file_content = await file.read()
    file_base64 = base64.b64encode(file_content).decode('utf-8')

    attachment = {
        "id": str(uuid4()),
        "filename": file.filename,
        "content_type": content_type,
        "size": len(file_content),
        "data": file_base64
    }

    # Sanitizar conteúdo da mensagem antes de guardar
    sanitized_content = sanitize_string(content, max_length=5000) if content else content

    if group_id:
        group = await db.chat_groups.find_one(
            {"id": group_id, "members.user_id": user_id},
            {"_id": 0, "name": 1, "members": 1}
        )
        if not group:
            raise HTTPException(status_code=403, detail="Não tem acesso a este grupo")

        msg_doc = {
            "id": str(uuid4()),
            "sender_id": user_id,
            "sender_name": user.get("name", ""),
            "group_id": group_id,
            "group_name": group["name"],
            "content": sanitized_content,
            "attachments": [attachment],
            "reactions": [],
            "edited": False,
            "read": True,
            "created_at": datetime.now(timezone.utc).isoformat()
        }

        await db.chat_messages.insert_one(msg_doc)

        # Notificar membros
        for member in group.get("members", []):
            member_id = member.get("user_id")
            if member_id and member_id != user_id:
                await manager.send_personal_message(
                    create_ws_message("new_chat_message", {
                        "id": msg_doc["id"],
                        "sender_id": user_id,
                        "sender_name": user.get("name", ""),
                        "group_id": group_id,
                        "has_attachment": True,
                        "content": sanitized_content[:100] if sanitized_content else f"📎 {file.filename}",
                        "created_at": msg_doc["created_at"]
                    }),
                    member_id
                )

    elif receiver_id:
        receiver = await db.users.find_one({"id": receiver_id}, {"_id": 0, "id": 1, "name": 1})
        if not receiver:
            raise HTTPException(status_code=404, detail="Destinatário não encontrado")

        msg_doc = {
            "id": str(uuid4()),
            "sender_id": user_id,
            "sender_name": user.get("name", ""),
            "receiver_id": receiver_id,
            "receiver_name": receiver.get("name", ""),
            "content": sanitized_content,
            "attachments": [attachment],
            "reactions": [],
            "edited": False,
            "read": False,
            "created_at": datetime.now(timezone.utc).isoformat()
        }

        await db.chat_messages.insert_one(msg_doc)

        await manager.send_personal_message(
            create_ws_message("new_chat_message", {
                "id": msg_doc["id"],
                "sender_id": user_id,
                "sender_name": user.get("name", ""),
                "receiver_id": receiver_id,
                "has_attachment": True,
                "content": sanitized_content[:100] if sanitized_content else f"📎 {file.filename}",
                "created_at": msg_doc["created_at"]
            }),
            receiver_id
        )
    else:
        raise HTTPException(status_code=400, detail="Deve especificar receiver_id ou group_id")

    # Remover dados do anexo da resposta (para reduzir tamanho)
    response_msg = {**msg_doc}
    if response_msg.get("attachments"):
        response_msg["attachments"] = [{k: v for k, v in a.items() if k != "data"} for a in response_msg["attachments"]]

    response_msg.pop("_id", None)
    return {"success": True, "message": response_msg}


async def run_react_to_message(reaction: ChatMessageReaction, user: dict):
    """
    Adicionar ou remover reação a uma mensagem.
    """
    user_id = user["id"]

    msg = await db.chat_messages.find_one({"id": reaction.message_id})
    if not msg:
        raise HTTPException(status_code=404, detail="Mensagem não encontrada")

    # Verificar acesso
    if msg.get("group_id"):
        group = await db.chat_groups.find_one(
            {"id": msg["group_id"], "members.user_id": user_id}
        )
        if not group:
            raise HTTPException(status_code=403, detail="Sem acesso a esta mensagem")
    elif msg.get("receiver_id") != user_id and msg.get("sender_id") != user_id:
        raise HTTPException(status_code=403, detail="Sem acesso a esta mensagem")

    reactions = msg.get("reactions", [])

    # Verificar se já tem esta reação
    existing_idx = None
    for i, r in enumerate(reactions):
        if r.get("user_id") == user_id and r.get("reaction") == reaction.reaction:
            existing_idx = i
            break

    if existing_idx is not None:
        # Remover reação
        reactions.pop(existing_idx)
    else:
        # Adicionar reação
        reactions.append({
            "user_id": user_id,
            "user_name": user.get("name", ""),
            "reaction": reaction.reaction,
            "created_at": datetime.now(timezone.utc).isoformat()
        })

    await db.chat_messages.update_one(
        {"id": reaction.message_id},
        {"$set": {"reactions": reactions}}
    )

    # Notificar outros participantes
    notify_user_id = msg.get("sender_id")
    if notify_user_id and notify_user_id != user_id:
        await manager.send_personal_message(
            create_ws_message("chat_message_reaction", {
                "message_id": reaction.message_id,
                "reactions": reactions
            }),
            notify_user_id
        )

    return {"success": True, "reactions": reactions}


async def run_edit_message(edit_data: ChatMessageEdit, user: dict):
    """
    Editar uma mensagem (apenas próprio remetente).
    """
    user_id = user["id"]

    msg = await db.chat_messages.find_one({"id": edit_data.message_id})
    if not msg:
        raise HTTPException(status_code=404, detail="Mensagem não encontrada")

    if msg.get("sender_id") != user_id:
        raise HTTPException(status_code=403, detail="Só pode editar as suas próprias mensagens")

    # Sanitizar conteúdo editado antes de guardar
    sanitized_edit_content = sanitize_string(edit_data.content, max_length=5000) if edit_data.content else edit_data.content

    await db.chat_messages.update_one(
        {"id": edit_data.message_id},
        {
            "$set": {
                "content": sanitized_edit_content,
                "edited": True,
                "edited_at": datetime.now(timezone.utc).isoformat()
            }
        }
    )

    # Notificar destinatários
    if msg.get("group_id"):
        group = await db.chat_groups.find_one({"id": msg["group_id"]}, {"members": 1})
        for member in group.get("members", []):
            member_id = member.get("user_id")
            if member_id and member_id != user_id:
                await manager.send_personal_message(
                    create_ws_message("chat_message_edited", {
                        "message_id": edit_data.message_id,
                        "content": sanitized_edit_content,
                        "edited": True
                    }),
                    member_id
                )
    elif msg.get("receiver_id"):
        await manager.send_personal_message(
            create_ws_message("chat_message_edited", {
                "message_id": edit_data.message_id,
                "content": sanitized_edit_content,
                "edited": True
            }),
            msg["receiver_id"]
        )

    return {"success": True}


async def run_delete_message(message_id: str, user: dict):
    """
    Apagar uma mensagem (apenas próprio remetente).
    """
    user_id = user["id"]

    msg = await db.chat_messages.find_one({"id": message_id})
    if not msg:
        raise HTTPException(status_code=404, detail="Mensagem não encontrada")

    if msg.get("sender_id") != user_id:
        raise HTTPException(status_code=403, detail="Só pode apagar as suas próprias mensagens")

    await db.chat_messages.delete_one({"id": message_id})

    # Notificar destinatários
    if msg.get("group_id"):
        group = await db.chat_groups.find_one({"id": msg["group_id"]}, {"members": 1})
        for member in group.get("members", []):
            member_id = member.get("user_id")
            if member_id and member_id != user_id:
                await manager.send_personal_message(
                    create_ws_message("chat_message_deleted", {"message_id": message_id}),
                    member_id
                )
    elif msg.get("receiver_id"):
        await manager.send_personal_message(
            create_ws_message("chat_message_deleted", {"message_id": message_id}),
            msg["receiver_id"]
        )

    return {"success": True}


async def run_search_messages(search: ChatSearchQuery, user: dict):
    """
    Pesquisar mensagens.
    """
    user_id = user["id"]

    query = {
        "$text": {"$search": search.query}
    }

    # Filtros de acesso
    access_conditions = [
        {"receiver_id": user_id},
        {"sender_id": user_id},
        {"group_id": {"$in": []}}  # Será preenchido com grupos do utilizador
    ]

    # Buscar grupos do utilizador
    groups = await db.chat_groups.find(
        {"members.user_id": user_id},
        {"id": 1}
    ).to_list(50)
    group_ids = [g["id"] for g in groups]

    access_conditions[2]["group_id"]["$in"] = group_ids

    query["$or"] = access_conditions

    # Filtros adicionais
    if search.user_id:
        query["sender_id"] = search.user_id

    if search.group_id:
        query["group_id"] = search.group_id

    if search.date_from or search.date_to:
        date_filter = {}
        if search.date_from:
            date_filter["$gte"] = search.date_from
        if search.date_to:
            date_filter["$lte"] = search.date_to
        query["created_at"] = date_filter

    messages = await db.chat_messages.find(
        query,
        {"score": {"$meta": "textScore"}, "_id": 0}
    ).sort([("score", {"$meta": "textScore"}), ("created_at", -1)]).limit(search.limit).to_list(search.limit)

    return {"results": messages, "total": len(messages)}

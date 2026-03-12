"""
====================================================================
ROTAS DE CHAT INTERNO - CREDITOIMO
====================================================================
Sistema completo de mensagens internas entre utilizadores.

Funcionalidades:
- Chat direto (1-para-1)
- Chat em grupo
- Anexos/ficheiros
- Typing indicators
- Reações a mensagens
- Notificações push
- Pesquisa de mensagens
- Citação/resposta a mensagens
====================================================================
"""

import logging
import base64
import os
from datetime import datetime, timezone
from typing import List, Optional
from uuid import uuid4
from mimetypes import guess_type

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form
from pydantic import BaseModel

from database import db
from services.auth import get_current_user, require_roles
from models.auth import UserRole
from models.chat import (
    ChatMessageCreate, ChatMessageReaction, ChatMessageEdit,
    ChatGroupCreate, ChatGroupUpdate, ChatSearchQuery, TypingIndicator
)
from services.websocket_manager import manager, WSEventType, create_ws_message

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["Chat Interno"])

# Tamanho máximo de anexo: 10MB
MAX_ATTACHMENT_SIZE = 10 * 1024 * 1024
ALLOWED_ATTACHMENT_TYPES = [
    "image/jpeg", "image/png", "image/gif", "image/webp",
    "application/pdf",
    "application/msword", "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "text/plain", "text/csv"
]


# ============= ENDPOINTS DE MENSAGENS =============

@router.get("/conversations")
async def get_conversations(
    user: dict = Depends(get_current_user)
):
    """
    Obter lista de conversas do utilizador.
    Inclui conversas diretas e grupos.
    """
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


@router.get("/messages/{conversation_id}")
async def get_messages(
    conversation_id: str,
    limit: int = Query(50, ge=1, le=200),
    before: Optional[str] = None,
    is_group: bool = Query(False),
    user: dict = Depends(get_current_user)
):
    """
    Obter mensagens de uma conversa.
    conversation_id pode ser user_id (direto) ou group_id (grupo).
    """
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

        # Atualizar último lido
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


@router.post("/messages")
async def send_message(
    message: ChatMessageCreate,
    user: dict = Depends(get_current_user)
):
    """
    Enviar uma nova mensagem (direta ou para grupo).
    """
    user_id = user["id"]

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
            "content": message.content.strip(),
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
            "content": message.content.strip(),
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


@router.post("/messages/upload")
async def upload_message_with_attachment(
    receiver_id: Optional[str] = Form(None),
    group_id: Optional[str] = Form(None),
    content: Optional[str] = Form(""),
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user)
):
    """
    Enviar mensagem com anexo.
    """
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
            "content": content.strip(),
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
                        "content": content[:100] if content else f"📎 {file.filename}",
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
            "content": content.strip(),
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
                "content": content[:100] if content else f"📎 {file.filename}",
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


@router.post("/messages/react")
async def react_to_message(
    reaction: ChatMessageReaction,
    user: dict = Depends(get_current_user)
):
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


@router.put("/messages/edit")
async def edit_message(
    edit_data: ChatMessageEdit,
    user: dict = Depends(get_current_user)
):
    """
    Editar uma mensagem (apenas próprio remetente).
    """
    user_id = user["id"]

    msg = await db.chat_messages.find_one({"id": edit_data.message_id})
    if not msg:
        raise HTTPException(status_code=404, detail="Mensagem não encontrada")

    if msg.get("sender_id") != user_id:
        raise HTTPException(status_code=403, detail="Só pode editar as suas próprias mensagens")

    await db.chat_messages.update_one(
        {"id": edit_data.message_id},
        {
            "$set": {
                "content": edit_data.content.strip(),
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
                        "content": edit_data.content,
                        "edited": True
                    }),
                    member_id
                )
    elif msg.get("receiver_id"):
        await manager.send_personal_message(
            create_ws_message("chat_message_edited", {
                "message_id": edit_data.message_id,
                "content": edit_data.content,
                "edited": True
            }),
            msg["receiver_id"]
        )

    return {"success": True}


@router.delete("/messages/{message_id}")
async def delete_message(
    message_id: str,
    user: dict = Depends(get_current_user)
):
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


# ============= ENDPOINTS DE GRUPOS =============

@router.post("/groups")
async def create_group(
    group_data: ChatGroupCreate,
    user: dict = Depends(get_current_user)
):
    """
    Criar um novo grupo de chat.
    """
    user_id = user["id"]

    # Validar membros
    if group_data.members:
        valid_members = await db.users.find(
            {"id": {"$in": group_data.members}, "is_active": {"$ne": False}},
            {"_id": 0, "id": 1, "name": 1}
        ).to_list(100)
        member_ids = [m["id"] for m in valid_members]
    else:
        member_ids = []

    # Adicionar criador aos membros se não estiver
    if user_id not in member_ids:
        member_ids.append(user_id)

    members = []
    for mid in member_ids:
        member_info = await db.users.find_one({"id": mid}, {"_id": 0, "id": 1, "name": 1, "role": 1})
        if member_info:
            members.append({
                "user_id": mid,
                "user_name": member_info.get("name", ""),
                "user_role": member_info.get("role", ""),
                "joined_at": datetime.now(timezone.utc).isoformat(),
                "last_read": None
            })

    group_doc = {
        "id": str(uuid4()),
        "name": group_data.name.strip(),
        "description": group_data.description,
        "created_by": user_id,
        "created_by_name": user.get("name", ""),
        "members": members,
        "created_at": datetime.now(timezone.utc).isoformat()
    }

    await db.chat_groups.insert_one(group_doc)

    # Notificar membros adicionados
    for member in members:
        if member["user_id"] != user_id:
            await manager.send_personal_message(
                create_ws_message("chat_group_created", {
                    "group_id": group_doc["id"],
                    "group_name": group_doc["name"],
                    "created_by": user.get("name", "")
                }),
                member["user_id"]
            )

    group_doc.pop("_id", None)
    return {"success": True, "group": group_doc}


@router.get("/groups")
async def get_groups(
    user: dict = Depends(get_current_user)
):
    """
    Obter grupos do utilizador.
    """
    user_id = user["id"]

    groups = await db.chat_groups.find(
        {"members.user_id": user_id},
        {"_id": 0}
    ).to_list(50)

    return {"groups": groups}


@router.get("/groups/{group_id}")
async def get_group(
    group_id: str,
    user: dict = Depends(get_current_user)
):
    """
    Obter detalhes de um grupo.
    """
    user_id = user["id"]

    group = await db.chat_groups.find_one(
        {"id": group_id, "members.user_id": user_id},
        {"_id": 0}
    )

    if not group:
        raise HTTPException(status_code=404, detail="Grupo não encontrado ou sem acesso")

    return {"group": group}


@router.put("/groups/{group_id}")
async def update_group(
    group_id: str,
    update_data: ChatGroupUpdate,
    user: dict = Depends(get_current_user)
):
    """
    Atualizar grupo (nome, descrição, membros).
    """
    user_id = user["id"]

    group = await db.chat_groups.find_one({"id": group_id})
    if not group:
        raise HTTPException(status_code=404, detail="Grupo não encontrado")

    # Apenas criador pode atualizar
    if group.get("created_by") != user_id:
        raise HTTPException(status_code=403, detail="Apenas o criador pode atualizar o grupo")

    update_fields = {}

    if update_data.name:
        update_fields["name"] = update_data.name.strip()

    if update_data.description is not None:
        update_fields["description"] = update_data.description

    if update_fields:
        await db.chat_groups.update_one(
            {"id": group_id},
            {"$set": update_fields}
        )

    # Adicionar membros
    if update_data.add_members:
        for mid in update_data.add_members:
            member_info = await db.users.find_one(
                {"id": mid, "is_active": {"$ne": False}},
                {"_id": 0, "id": 1, "name": 1, "role": 1}
            )
            if member_info and not any(m.get("user_id") == mid for m in group.get("members", [])):
                new_member = {
                    "user_id": mid,
                    "user_name": member_info.get("name", ""),
                    "user_role": member_info.get("role", ""),
                    "joined_at": datetime.now(timezone.utc).isoformat(),
                    "last_read": None
                }
                await db.chat_groups.update_one(
                    {"id": group_id},
                    {"$push": {"members": new_member}}
                )
                # Notificar novo membro
                await manager.send_personal_message(
                    create_ws_message("chat_group_created", {
                        "group_id": group_id,
                        "group_name": group.get("name", ""),
                        "added_by": user.get("name", "")
                    }),
                    mid
                )

    # Remover membros
    if update_data.remove_members:
        await db.chat_groups.update_one(
            {"id": group_id},
            {"$pull": {"members": {"user_id": {"$in": update_data.remove_members}}}}
        )

        for mid in update_data.remove_members:
            await manager.send_personal_message(
                create_ws_message("chat_group_removed", {
                    "group_id": group_id,
                    "group_name": group.get("name", "")
                }),
                mid
            )

    updated_group = await db.chat_groups.find_one({"id": group_id}, {"_id": 0})
    return {"success": True, "group": updated_group}


@router.delete("/groups/{group_id}")
async def delete_group(
    group_id: str,
    user: dict = Depends(get_current_user)
):
    """
    Apagar grupo (apenas criador).
    """
    user_id = user["id"]

    group = await db.chat_groups.find_one({"id": group_id})
    if not group:
        raise HTTPException(status_code=404, detail="Grupo não encontrado")

    if group.get("created_by") != user_id:
        raise HTTPException(status_code=403, detail="Apenas o criador pode apagar o grupo")

    # Notificar membros
    for member in group.get("members", []):
        if member.get("user_id") != user_id:
            await manager.send_personal_message(
                create_ws_message("chat_group_deleted", {
                    "group_id": group_id,
                    "group_name": group.get("name", "")
                }),
                member["user_id"]
            )

    # Apagar grupo e mensagens
    await db.chat_groups.delete_one({"id": group_id})
    await db.chat_messages.delete_many({"group_id": group_id})

    return {"success": True}


@router.post("/groups/{group_id}/leave")
async def leave_group(
    group_id: str,
    user: dict = Depends(get_current_user)
):
    """
    Sair de um grupo.
    """
    user_id = user["id"]

    result = await db.chat_groups.update_one(
        {"id": group_id, "members.user_id": user_id},
        {"$pull": {"members": {"user_id": user_id}}}
    )

    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Não é membro deste grupo")

    return {"success": True}


# ============= ENDPOINTS DE PESQUISA =============

@router.post("/search")
async def search_messages(
    search: ChatSearchQuery,
    user: dict = Depends(get_current_user)
):
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


# ============= ENDPOINTS DE TYPING =============

@router.post("/typing")
async def send_typing_indicator(
    typing: TypingIndicator,
    user: dict = Depends(get_current_user)
):
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


# ============= ENDPOINTS AUXILIARES =============

@router.get("/unread-count")
async def get_unread_count(user: dict = Depends(get_current_user)):
    """
    Obter contagem total de mensagens não lidas.
    """
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


@router.get("/online-users")
async def get_online_users(user: dict = Depends(get_current_user)):
    """
    Obter lista de utilizadores online.
    """
    connected_ids = manager.get_connected_users()

    if not connected_ids:
        return {"users": []}

    users = await db.users.find(
        {"id": {"$in": connected_ids}, "is_active": {"$ne": False}},
        {"_id": 0, "id": 1, "name": 1, "role": 1}
    ).to_list(100)

    return {"users": users}


@router.get("/users")
async def get_chat_users(
    search: Optional[str] = None,
    user: dict = Depends(get_current_user)
):
    """
    Obter lista de utilizadores disponíveis para chat.
    """
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

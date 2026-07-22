"""Chat group CRUD.

Extraído de `routes/chat.py`.
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import HTTPException

from database import db
from models.chat import ChatGroupCreate, ChatGroupUpdate
from services.websocket_manager import manager, create_ws_message
from utils.input_sanitization import sanitize_string
from services.chat_helpers import _block_parceiro


async def run_create_group(group_data: ChatGroupCreate, user: dict):
    """
    Criar um novo grupo de chat.
    """
    _block_parceiro(user)
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

    # Sanitizar nome e descrição do grupo antes de guardar
    sanitized_group_name = sanitize_string(group_data.name.strip(), max_length=200) if group_data.name else group_data.name
    sanitized_group_desc = sanitize_string(group_data.description, max_length=500) if group_data.description else group_data.description

    group_doc = {
        "id": str(uuid4()),
        "name": sanitized_group_name,
        "description": sanitized_group_desc,
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


async def run_get_groups(user: dict):
    """
    Obter grupos do utilizador.
    """
    _block_parceiro(user)
    user_id = user["id"]

    groups = await db.chat_groups.find(
        {"members.user_id": user_id},
        {"_id": 0}
    ).to_list(50)

    return {"groups": groups}


async def run_get_group(group_id: str, user: dict):
    """
    Obter detalhes de um grupo.
    """
    _block_parceiro(user)
    user_id = user["id"]

    group = await db.chat_groups.find_one(
        {"id": group_id, "members.user_id": user_id},
        {"_id": 0}
    )

    if not group:
        raise HTTPException(status_code=404, detail="Grupo não encontrado ou sem acesso")

    return {"group": group}


async def run_update_group(group_id: str, update_data: ChatGroupUpdate, user: dict):
    """
    Atualizar grupo (nome, descrição, membros).
    """
    user_id = user["id"]

    group = await db.chat_groups.find_one({"id": group_id})
    if not group:
        raise HTTPException(status_code=404, detail="Grupo não encontrado")

    # Apenas criador pode actualizar
    if group.get("created_by") != user_id:
        raise HTTPException(status_code=403, detail="Apenas o criador pode atualizar o grupo")

    update_fields = {}

    if update_data.name:
        update_fields["name"] = sanitize_string(update_data.name.strip(), max_length=200)

    if update_data.description is not None:
        update_fields["description"] = sanitize_string(update_data.description, max_length=500) if update_data.description else update_data.description

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


async def run_delete_group(group_id: str, user: dict):
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


async def run_leave_group(group_id: str, user: dict):
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

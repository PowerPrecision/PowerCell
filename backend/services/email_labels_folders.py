"""
CRUD de labels e pastas de email (nível utilizador).

Extraído de `routes/emails.py`.
"""
from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException

from database import db
from utils.input_sanitization import sanitize_string

logger = logging.getLogger(__name__)

DEFAULT_LABELS = [
    {"name": "Urgente", "color": "#ef4444"},
    {"name": "A Aguardar", "color": "#f59e0b"},
    {"name": "Concluído", "color": "#22c55e"},
    {"name": "Follow-up", "color": "#3b82f6"},
    {"name": "Reunião", "color": "#8b5cf6"},
]

DEFAULT_FOLDER_COLORS = [
    "#6b7280", "#ef4444", "#f59e0b", "#22c55e", "#3b82f6",
    "#8b5cf6", "#ec4899", "#14b8a6", "#f97316", "#6366f1"
]


def validate_hex_color(color: str) -> bool:
    """Validate hex color format like #e74c3c or #fff."""
    return bool(re.match(r'^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$', color))


async def run_list_labels(current_user: dict) -> dict:
    """Listar todas as labels do utilizador. Cria labels predefinidas na primeira chamada."""
    user_id = current_user["id"]
    existing = await db.email_labels.find(
        {"user_id": user_id}, {"_id": 0}
    ).sort("created_at", 1).to_list(100)

    if not existing:
        now = datetime.now(timezone.utc).isoformat()
        for label_def in DEFAULT_LABELS:
            await db.email_labels.insert_one({
                "id": str(uuid.uuid4()),
                "name": label_def["name"],
                "color": label_def["color"],
                "user_id": user_id,
                "created_at": now,
            })
        existing = await db.email_labels.find(
            {"user_id": user_id}, {"_id": 0}
        ).sort("created_at", 1).to_list(100)

    return {"labels": existing}


async def run_create_label(payload: Any, current_user: dict) -> dict:
    """Criar uma nova label."""
    user_id = current_user["id"]
    name = sanitize_string(payload.name.strip(), max_length=30)
    color = payload.color.strip()

    if not name:
        raise HTTPException(status_code=400, detail="Nome da label é obrigatório")
    if not validate_hex_color(color):
        raise HTTPException(status_code=400, detail="Cor inválida. Use formato hexadecimal (ex: #ef4444)")

    dup = await db.email_labels.find_one({"user_id": user_id, "name": name})
    if dup:
        raise HTTPException(status_code=409, detail="Já existe uma label com esse nome")

    label_doc = {
        "id": str(uuid.uuid4()),
        "name": name,
        "color": color,
        "user_id": user_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.email_labels.insert_one(label_doc)
    label_doc.pop("_id", None)

    logger.info(f"Label criada: {name} ({color}) por {current_user['email']}")
    return label_doc


async def run_update_label(label_id: str, payload: Any, current_user: dict) -> dict:
    """Atualizar nome e/ou cor de uma label."""
    user_id = current_user["id"]
    label = await db.email_labels.find_one({"id": label_id, "user_id": user_id})
    if not label:
        raise HTTPException(status_code=404, detail="Label não encontrada")

    update_data = {}
    if payload.name is not None:
        new_name = sanitize_string(payload.name.strip(), max_length=30)
        if not new_name:
            raise HTTPException(status_code=400, detail="Nome da label é obrigatório")
        dup = await db.email_labels.find_one({"user_id": user_id, "name": new_name, "id": {"$ne": label_id}})
        if dup:
            raise HTTPException(status_code=409, detail="Já existe uma label com esse nome")
        update_data["name"] = new_name
    if payload.color is not None:
        color = payload.color.strip()
        if not validate_hex_color(color):
            raise HTTPException(status_code=400, detail="Cor inválida. Use formato hexadecimal (ex: #ef4444)")
        update_data["color"] = color

    if update_data:
        await db.email_labels.update_one({"id": label_id}, {"$set": update_data})

    updated = await db.email_labels.find_one({"id": label_id}, {"_id": 0})
    logger.info(f"Label {label_id} atualizada por {current_user['email']}")
    return updated


async def run_delete_label(label_id: str, current_user: dict) -> dict:
    """Eliminar label e remover de todos os emails do utilizador."""
    user_id = current_user["id"]
    label = await db.email_labels.find_one({"id": label_id, "user_id": user_id})
    if not label:
        raise HTTPException(status_code=404, detail="Label não encontrada")

    label_name = label["name"]

    await db.emails.update_many(
        {"labels": label_name},
        {"$pull": {"labels": label_name}}
    )

    await db.email_labels.delete_one({"id": label_id})

    logger.info(f"Label '{label_name}' ({label_id}) eliminada por {current_user['email']}")
    return {"success": True, "message": f"Label '{label_name}' eliminada"}


async def run_list_folders(current_user: dict) -> dict:
    """Listar todas as pastas personalizadas do utilizador."""
    user_id = current_user["id"]
    folders = await db.email_folders.find(
        {"user_id": user_id}, {"_id": 0}
    ).sort("created_at", 1).to_list(100)

    folder_ids = [f["id"] for f in folders]
    counts = {}
    if folder_ids:
        pipeline = [
            {"$match": {"folder_id": {"$in": folder_ids}, "is_archived": False}},
            {"$group": {"_id": "$folder_id", "count": {"$sum": 1}}}
        ]
        async for doc in db.emails.aggregate(pipeline):
            counts[doc["_id"]] = doc["count"]

    result = []
    for f in folders:
        f_copy = dict(f)
        f_copy["email_count"] = counts.get(f["id"], 0)
        result.append(f_copy)

    return {"folders": result}


async def run_create_folder(payload: Any, current_user: dict) -> dict:
    """Criar uma nova pasta personalizada."""
    user_id = current_user["id"]
    name = sanitize_string(payload.name.strip(), max_length=40)

    if not name:
        raise HTTPException(status_code=400, detail="Nome da pasta é obrigatório")

    dup = await db.email_folders.find_one({"user_id": user_id, "name": name})
    if dup:
        raise HTTPException(status_code=409, detail="Já existe uma pasta com esse nome")

    color = payload.color.strip() if payload.color else "#6b7280"
    if not validate_hex_color(color):
        color = "#6b7280"

    folder_doc = {
        "id": str(uuid.uuid4()),
        "name": name,
        "color": color,
        "user_id": user_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.email_folders.insert_one(folder_doc)
    folder_doc.pop("_id", None)
    folder_doc["email_count"] = 0

    logger.info(f"Pasta criada: {name} ({color}) por {current_user['email']}")
    return folder_doc


async def run_update_folder(folder_id: str, payload: Any, current_user: dict) -> dict:
    """Atualizar nome e/ou cor de uma pasta."""
    user_id = current_user["id"]
    folder = await db.email_folders.find_one({"id": folder_id, "user_id": user_id})
    if not folder:
        raise HTTPException(status_code=404, detail="Pasta não encontrada")

    update_data = {}
    if payload.name is not None:
        new_name = sanitize_string(payload.name.strip(), max_length=40)
        if not new_name:
            raise HTTPException(status_code=400, detail="Nome da pasta é obrigatório")
        dup = await db.email_folders.find_one({"user_id": user_id, "name": new_name, "id": {"$ne": folder_id}})
        if dup:
            raise HTTPException(status_code=409, detail="Já existe uma pasta com esse nome")
        update_data["name"] = new_name
    if payload.color is not None:
        color = payload.color.strip()
        if not validate_hex_color(color):
            color = "#6b7280"
        update_data["color"] = color

    if update_data:
        await db.email_folders.update_one({"id": folder_id}, {"$set": update_data})

    updated = await db.email_folders.find_one({"id": folder_id}, {"_id": 0})
    logger.info(f"Pasta {folder_id} atualizada por {current_user['email']}")
    return updated


async def run_delete_folder(folder_id: str, current_user: dict) -> dict:
    """Eliminar pasta e remover referência dos emails (emails voltam à pasta de origem)."""
    user_id = current_user["id"]
    folder = await db.email_folders.find_one({"id": folder_id, "user_id": user_id})
    if not folder:
        raise HTTPException(status_code=404, detail="Pasta não encontrada")

    folder_name = folder["name"]

    await db.emails.update_many(
        {"folder_id": folder_id},
        {"$unset": {"folder_id": ""}}
    )

    await db.email_folders.delete_one({"id": folder_id})

    logger.info(f"Pasta '{folder_name}' ({folder_id}) eliminada por {current_user['email']}")
    return {"success": True, "message": f"Pasta '{folder_name}' eliminada"}


async def run_move_emails_to_folder(data: dict, current_user: dict) -> dict:
    """Mover um ou mais emails para uma pasta personalizada."""
    email_ids = data.get("email_ids", [])
    folder_id = data.get("folder_id")  # None/empty = remove from folder

    if not email_ids:
        raise HTTPException(status_code=400, detail="Selecione pelo menos um email")

    if folder_id:
        folder = await db.email_folders.find_one({"id": folder_id})
        if not folder:
            raise HTTPException(status_code=404, detail="Pasta não encontrada")

    update = {"$set": {"folder_id": folder_id}} if folder_id else {"$unset": {"folder_id": ""}}

    result = await db.emails.update_many(
        {"id": {"$in": email_ids}},
        update
    )

    return {
        "success": True,
        "modified_count": result.modified_count,
        "folder_id": folder_id
    }

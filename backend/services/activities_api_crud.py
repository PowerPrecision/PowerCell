"""Activities CRUD handlers.

Extraído de `routes/activities.py`.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException

from database import db
from models.auth import UserRole
from models.activity import ActivityCreate, ActivityResponse
from services.history import log_history, _is_stealth_user
from utils.input_sanitization import sanitize_string


async def run_create_activity(data: ActivityCreate, user: dict):
    process = await db.processes.find_one({"id": data.process_id})
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")

    if user["role"] == UserRole.CLIENTE and process["client_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="Acesso negado")

    if _is_stealth_user(user):
        raise HTTPException(
            status_code=403,
            detail="O seu perfil está em modo de indexação silenciosa e não pode adicionar comentários ao histórico do processo."
        )

    activity_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    activity_doc = {
        "id": activity_id,
        "process_id": data.process_id,
        "user_id": user["id"],
        "user_name": user["name"],
        "user_role": user["role"],
        "comment": sanitize_string(data.comment, max_length=1000),
        "created_at": now
    }

    await db.activities.insert_one(activity_doc)
    await log_history(data.process_id, user, "Adicionou comentário")

    return ActivityResponse(**{k: v for k, v in activity_doc.items() if k != "_id"})


async def run_get_activities(
    process_id: Optional[str],
    limit: int,
    user: dict,
):
    if process_id:
        process = await db.processes.find_one({"id": process_id})
        if not process:
            raise HTTPException(status_code=404, detail="Processo não encontrado")

        if user["role"] == UserRole.CLIENTE and process.get("client_id") != user["id"]:
            raise HTTPException(status_code=403, detail="Acesso negado")

        activities = await db.activities.find(
            {"process_id": process_id}, {"_id": 0}
        ).sort("created_at", -1).to_list(1000)
    else:
        if user["role"] == UserRole.CLIENTE:
            raise HTTPException(status_code=403, detail="Acesso negado")

        activities = await db.activities.find({}, {"_id": 0}).sort(
            "created_at", -1
        ).to_list(limit)

    valid_activities = []
    for a in activities:
        if all(k in a for k in ["id", "user_id", "user_name", "user_role", "comment", "created_at"]):
            valid_activities.append(ActivityResponse(**a))
        elif "comment" in a:
            a.setdefault("user_id", "system")
            a.setdefault("user_name", "Sistema")
            a.setdefault("user_role", "admin")
            valid_activities.append(ActivityResponse(**a))

    return valid_activities


async def run_delete_activity(activity_id: str, user: dict):
    activity = await db.activities.find_one({"id": activity_id})
    if not activity:
        raise HTTPException(status_code=404, detail="Comentário não encontrado")

    if activity["user_id"] != user["id"] and user["role"] != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Só pode eliminar os seus próprios comentários")

    await db.activities.delete_one({"id": activity_id})
    return {"message": "Comentário eliminado"}

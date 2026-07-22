"""Activities history handler.

Extraído de `routes/activities.py`.
"""
from __future__ import annotations

from fastapi import HTTPException

from database import db
from models.auth import UserRole
from models.activity import HistoryResponse


async def run_get_history(process_id: str, user: dict):
    process = await db.processes.find_one({"id": process_id})
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")

    if user["role"] == UserRole.CLIENTE and process["client_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="Acesso negado")

    history = await db.history.find(
        {"process_id": process_id}, {"_id": 0}
    ).sort("created_at", -1).to_list(1000)
    return [HistoryResponse(**h) for h in history]

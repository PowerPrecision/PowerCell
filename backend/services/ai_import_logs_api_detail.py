"""AI import logs detail/delete handlers.

Extraído de `routes/ai_import_logs.py`.
Do **not** overwrite services/admin_ai_data.py.
"""
from __future__ import annotations

from fastapi import HTTPException

from database import db


async def run_get_ai_import_log(log_id: str):
    log = await db.ai_import_logs.find_one({"id": log_id}, {"_id": 0})

    if not log:
        raise HTTPException(status_code=404, detail="Log não encontrado")

    return log


async def run_delete_ai_import_log(log_id: str, user: dict):
    if user.get("role") not in ["admin", "ceo"]:
        raise HTTPException(status_code=403, detail="Apenas administradores podem eliminar logs")

    result = await db.ai_import_logs.delete_one({"id": log_id})

    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Log não encontrado")

    return {"success": True, "message": "Log eliminado com sucesso"}

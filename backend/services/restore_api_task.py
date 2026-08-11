"""Restore task handler.

Extraído de `routes/restore.py`.
Do **not** overwrite services/backup_restore.py.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException

from database import db


async def run_restore_task(task_id: str, user: dict):
    """Restaura uma tarefa eliminada."""
    task = await db.tasks.find_one({"id": task_id})

    if task:
        if not task.get("deleted", False):
            raise HTTPException(
                status_code=400,
                detail="Tarefa não está eliminada"
            )

        await db.tasks.update_one(
            {"id": task_id},
            {"$set": {
                "deleted": False,
                "deleted_at": None,
                "restored_at": datetime.now(timezone.utc).isoformat(),
                "restored_by": user["id"]
            }}
        )

        updated = await db.tasks.find_one({"id": task_id}, {"_id": 0})

        return {
            "success": True,
            "message": "Tarefa restaurada com sucesso",
            "task": updated
        }

    raise HTTPException(status_code=404, detail="Tarefa não encontrada")

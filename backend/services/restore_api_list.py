"""List deleted items handler.

Extraído de `routes/restore.py`.
Do **not** overwrite services/backup_restore.py.
"""
from __future__ import annotations

from database import db


async def run_list_deleted_items(item_type: str, limit: int, user: dict):
    """Lista itens eliminados recentemente que podem ser restaurados."""
    items = []

    if item_type in ["all", "processes"]:
        # Processos eliminados
        deleted_processes = await db.processes.find(
            {"status": "eliminado", "is_active": False},
            {"_id": 0}
        ).sort("updated_at", -1).limit(limit).to_list(limit)

        for p in deleted_processes:
            items.append({
                "type": "process",
                "id": p["id"],
                "name": p.get("client_name", "Sem nome"),
                "deleted_at": p.get("updated_at"),
                "can_restore": True
            })

    if item_type in ["all", "documents"]:
        # Documentos eliminados
        deleted_docs = await db.documents.find(
            {"deleted": True},
            {"_id": 0}
        ).sort("deleted_at", -1).limit(limit).to_list(limit)

        for d in deleted_docs:
            items.append({
                "type": "document",
                "id": d["id"],
                "name": d.get("filename", "Sem nome"),
                "deleted_at": d.get("deleted_at"),
                "can_restore": True
            })

    if item_type in ["all", "tasks"]:
        # Tarefas eliminadas
        deleted_tasks = await db.tasks.find(
            {"deleted": True},
            {"_id": 0}
        ).sort("deleted_at", -1).limit(limit).to_list(limit)

        for t in deleted_tasks:
            items.append({
                "type": "task",
                "id": t["id"],
                "name": t.get("title", "Sem título"),
                "deleted_at": t.get("deleted_at"),
                "can_restore": True
            })

    return {
        "items": items,
        "total": len(items)
    }

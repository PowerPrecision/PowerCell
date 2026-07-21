"""
Soft delete de processos (cascade documentos/tarefas + activity).

Extraído de `routes/processes.py` — DELETE /processes/{id}.
Não toca no documento do cliente.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException

from database import db


def build_soft_delete_process_set(
    process: dict,
    user: dict,
    now: datetime,
) -> dict[str, Any]:
    """
    Campos `$set` do soft delete.

    FIX (Pacote K): `previous_status` permite restore com o status original
    em vez de forçar ``clientes_espera``.
    """
    return {
        "is_deleted": True,
        "status": "eliminado",
        "is_active": False,
        "previous_status": process.get("status"),
        "deleted_at": now,
        "deleted_by": user.get("id", ""),
        "updated_at": now,
    }


def build_cascade_soft_delete_set(now: datetime) -> dict[str, Any]:
    """Campos `$set` para cascade em documents/tasks."""
    return {
        "deleted": True,
        "is_deleted": True,
        "deleted_at": now,
    }


def build_process_deleted_activity(
    process_id: str,
    user: dict,
    now: datetime,
) -> dict[str, Any]:
    return {
        "id": str(uuid.uuid4()),
        "process_id": process_id,
        "type": "process_deleted",
        "description": (
            f"Processo eliminado (soft delete) por "
            f"{user.get('name', 'Utilizador')}"
        ),
        "created_at": now,
        "user_id": user.get("id", ""),
        "user_name": user.get("name", ""),
    }


async def soft_delete_process(process_id: str, user: dict) -> dict[str, Any]:
    """
    Soft-delete processo + cascade documents/tasks + activity.

    Raises:
        HTTPException(404): processo inexistente ou já eliminado.
    """
    process = await db.processes.find_one(
        {"id": process_id, "is_deleted": {"$ne": True}},
        {"_id": 0},
    )
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")

    now = datetime.now(timezone.utc)
    await db.processes.update_one(
        {"id": process_id},
        {"$set": build_soft_delete_process_set(process, user, now)},
    )

    cascade = build_cascade_soft_delete_set(now)
    await db.documents.update_many(
        {"process_id": process_id, "is_deleted": {"$ne": True}},
        {"$set": cascade},
    )
    await db.tasks.update_many(
        {"process_id": process_id, "is_deleted": {"$ne": True}},
        {"$set": cascade},
    )

    await db.process_activities.insert_one(
        build_process_deleted_activity(process_id, user, now),
    )

    return {"message": "Processo eliminado com sucesso", "id": process_id}

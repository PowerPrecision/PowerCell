"""Restore process handler.

Extraído de `routes/restore.py`.
Do **not** overwrite services/backup_restore.py.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import HTTPException

from database import db
from services.restore_api_helpers import TERMINAL_STATUSES


async def run_restore_process(process_id: str, user: dict):
    """Restaura um processo que foi eliminado (soft delete)."""
    # Procurar o processo (inclui eliminados — NÃO filtrar is_deleted aqui)
    process = await db.processes.find_one({"id": process_id})

    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")

    # Só restaurar se o processo está realmente eliminado
    is_deleted = process.get("is_deleted", False)
    status = process.get("status", "")
    if not is_deleted and status != "eliminado":
        raise HTTPException(
            status_code=400,
            detail="Processo não está eliminado — não precisa de restauração"
        )

    now = datetime.now(timezone.utc)

    # Restaurar o status anterior se guardado, senão usar clientes_espera
    previous_status = process.get("previous_status") or "clientes_espera"
    # Se o previous_status era "eliminado" (caso de double-delete), usar fallback
    if previous_status == "eliminado":
        previous_status = "clientes_espera"

    restored_is_active = previous_status not in TERMINAL_STATUSES

    await db.processes.update_one(
        {"id": process_id},
        {"$set": {
            "is_deleted": False,
            "status": previous_status,
            "is_active": restored_is_active,
            "restored_at": now.isoformat(),
            "restored_by": user.get("id", ""),
            "updated_at": now.isoformat(),
        }}
    )

    # Cascade: restaurar documentos e tarefas que foram soft-deletados
    # juntamente com o processo (o delete faz cascade com is_deleted=True).
    await db.documents.update_many(
        {"process_id": process_id, "is_deleted": True},
        {"$set": {
            "deleted": False,
            "is_deleted": False,
            "deleted_at": None,
        }}
    )
    await db.tasks.update_many(
        {"process_id": process_id, "is_deleted": True},
        {"$set": {
            "deleted": False,
            "is_deleted": False,
            "deleted_at": None,
        }}
    )

    # Log de atividade (simétrico ao process_deleted do delete endpoint)
    await db.process_activities.insert_one({
        "id": str(uuid.uuid4()),
        "process_id": process_id,
        "type": "process_restored",
        "description": f"Processo restaurado por {user.get('name', 'Utilizador')}",
        "created_at": now.isoformat(),
        "user_id": user.get("id", ""),
        "user_name": user.get("name", ""),
    })

    updated = await db.processes.find_one({"id": process_id}, {"_id": 0})

    return {
        "success": True,
        "message": "Processo restaurado com sucesso",
        "process": updated
    }

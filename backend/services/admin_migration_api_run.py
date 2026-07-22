"""Start migration + single-client migration handlers.

Extraído de `routes/admin_migration.py`.
"""
from __future__ import annotations

import logging

from fastapi import BackgroundTasks, HTTPException

from database import db
from services.admin_migration_api_helpers import build_client_encryption_updates
from services.admin_migration_api_task import run_migration_task

logger = logging.getLogger(__name__)


async def run_start_migration(background_tasks: BackgroundTasks, user: dict):
    """Enfileira a migração de encriptação em background."""
    background_tasks.add_task(run_migration_task)

    logger.info(f"Migração iniciada por {user.get('email')}")

    return {
        "success": True,
        "message": (
            "Migração iniciada em background. Verifique os logs do servidor "
            "para acompanhar o progresso."
        ),
        "started_by": user.get("email"),
        "note": (
            "A migração pode demorar alguns minutos dependendo do número "
            "de clientes."
        ),
    }


async def run_migration_single(client_id: str, user: dict):
    """Executa a migração para um único cliente (útil para testes)."""
    client = await db.clients.find_one({"id": client_id})
    if not client:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")

    updates, changes = build_client_encryption_updates(
        client, track_changes=True,
    )

    if updates:
        await db.clients.update_one({"id": client_id}, {"$set": updates})
        return {
            "success": True,
            "message": f"Cliente {client_id} migrado com sucesso",
            "client_name": client.get("nome"),
            "changes": changes,
        }

    return {
        "success": True,
        "message": f"Cliente {client_id} já estava migrado",
        "client_name": client.get("nome"),
        "changes": [],
    }

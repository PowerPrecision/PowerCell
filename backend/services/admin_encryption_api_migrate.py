"""Admin encryption migrate handlers.

Extraído de `routes/admin_encryption.py`.
Never create services/admin_encryption.py — use admin_encryption_api_*.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import BackgroundTasks, HTTPException

from database import db
from services.encryption import encryption_service

logger = logging.getLogger(__name__)


async def run_migrate_encryption(
    background_tasks: BackgroundTasks,
    dry_run: bool,
    user: dict,
):
    if not encryption_service.is_available():
        raise HTTPException(
            status_code=503,
            detail="Serviço de encriptação não disponível. Configure ENCRYPTION_KEY."
        )

    from services.migrate_encryption import migrate_processes_encryption

    async def run_migration():
        try:
            stats = await migrate_processes_encryption(dry_run=dry_run, batch_size=50)
            logger.info(f"Migração concluída: {stats}")

            await db.activity_logs.insert_one({
                "type": "encryption_migration",
                "user_id": user["id"],
                "user_name": user.get("name"),
                "stats": stats,
                "dry_run": dry_run,
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
        except Exception as e:
            logger.error(f"Erro na migração: {e}")

    background_tasks.add_task(run_migration)

    return {
        "message": "Migração iniciada em background",
        "dry_run": dry_run,
        "check_status_at": "/api/admin/encryption/status"
    }


async def run_migrate_encryption_sync(dry_run: bool, batch_size: int):
    if not encryption_service.is_available():
        raise HTTPException(
            status_code=503,
            detail="Serviço de encriptação não disponível. Configure ENCRYPTION_KEY."
        )

    from services.migrate_encryption import migrate_processes_encryption

    return await migrate_processes_encryption(dry_run=dry_run, batch_size=batch_size)

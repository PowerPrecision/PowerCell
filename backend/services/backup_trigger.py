"""Backup trigger — manual / run-now endpoints.

Extracted from `routes/backup.py`. Reuses `services.backup.full_backup_workflow`.
Does **not** overwrite `services/backup.py`.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from fastapi import BackgroundTasks
from pydantic import BaseModel

from database import db
from services.backup import full_backup_workflow

logger = logging.getLogger(__name__)


class BackupRequest(BaseModel):
    """Request para backup manual."""

    upload_to_cloud: bool = True
    cleanup_after: bool = True


async def _execute_manual_backup(
    backup_id: str,
    *,
    upload_to_cloud: bool,
    cleanup_after: bool,
) -> None:
    """Executa o workflow completo de backup em background.

    Inclui: exportação de todas as coleções MongoDB, compressão
    em ZIP, e opcionalmente upload para S3. Atualiza o registo
    em backup_history com o resultado (completed/failed).
    """
    try:
        result = await full_backup_workflow(
            upload_to_cloud=upload_to_cloud,
            cleanup_after=cleanup_after,
        )

        await db.backup_history.update_one(
            {"id": backup_id},
            {"$set": {
                "status": "completed" if result["success"] else "failed",
                "result": result,
                "completed_at": datetime.now(timezone.utc),
            }},
        )
        logger.info(
            f"[BACKUP] Backup {backup_id} concluído com status: "
            f"{'completed' if result['success'] else 'failed'}"
        )
    except Exception as e:
        logger.error(f"[BACKUP] Erro no backup {backup_id}: {e}")
        await db.backup_history.update_one(
            {"id": backup_id},
            {"$set": {
                "status": "failed",
                "error": str(e),
                "completed_at": datetime.now(timezone.utc),
            }},
        )


async def _execute_immediate_backup(backup_id: str) -> None:
    """Executa backup imediato com upload obrigatório para S3.

    Semelhante a ``_execute_manual_backup``, mas com
    upload_to_cloud=True e cleanup_after=True forçados.
    """
    try:
        result = await full_backup_workflow(
            upload_to_cloud=True,
            cleanup_after=True,
        )

        await db.backup_history.update_one(
            {"id": backup_id},
            {"$set": {
                "status": "completed" if result["success"] else "failed",
                "result": result,
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }},
        )
    except Exception as e:
        await db.backup_history.update_one(
            {"id": backup_id},
            {"$set": {
                "status": "failed",
                "error": str(e),
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }},
        )


async def run_trigger_backup(
    request: BackupRequest,
    background_tasks: BackgroundTasks,
    user: dict,
) -> dict:
    """Triggera um backup manual em background."""
    logger.info(f"[BACKUP] Backup manual triggered por {user.get('email')}")

    backup_id = str(uuid.uuid4())
    started_at = datetime.now(timezone.utc)

    await db.backup_history.insert_one({
        "id": backup_id,
        "triggered_by": user.get("id"),
        "triggered_by_email": user.get("email"),
        "trigger_type": "manual",
        "started_at": started_at,
        "status": "running",
    })

    background_tasks.add_task(
        _execute_manual_backup,
        backup_id,
        upload_to_cloud=request.upload_to_cloud,
        cleanup_after=request.cleanup_after,
    )

    return {
        "success": True,
        "message": "Backup iniciado em background",
        "backup_id": backup_id,
        "check_status_at": f"/api/backup/status/{backup_id}",
    }


async def run_backup_now(
    background_tasks: BackgroundTasks,
    user: dict,
) -> dict:
    """Executa backup imediato com upload para S3."""
    logger.info(f"[BACKUP] Backup imediato triggered por {user.get('email')}")

    backup_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    await db.backup_history.insert_one({
        "id": backup_id,
        "triggered_by": user.get("id"),
        "triggered_by_email": user.get("email"),
        "trigger_type": "manual_immediate",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "status": "running",
    })

    background_tasks.add_task(_execute_immediate_backup, backup_id)

    return {
        "success": True,
        "message": "Backup iniciado com upload para S3",
        "backup_id": backup_id,
        "check_status_at": f"/api/backup/status/{backup_id}",
    }

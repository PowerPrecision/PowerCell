"""
Backup routes — thin FastAPI stubs.

Logic in services/backup_ops.py, backup_trigger.py, backup_restore.py.
Core backup engine remains in services/backup.py (do **not** overwrite).
"""
from fastapi import APIRouter, BackgroundTasks, Depends

from models.auth import UserRole
from services.auth import require_roles
from services.backup_ops import (
    run_get_backup_config,
    run_get_backup_status,
    run_get_history,
    run_get_statistics,
    run_verify_backups,
)
from services.backup_restore import (
    run_emergency_restore,
    run_restore_from_s3,
)
from services.backup_trigger import (
    BackupRequest,
    run_backup_now as run_backup_now_svc,
    run_trigger_backup,
)

router = APIRouter(prefix="/backup", tags=["Backup"])


@router.get("/statistics")
async def get_statistics(
    current_user: dict = Depends(require_roles([UserRole.ADMIN])),
):
    return await run_get_statistics(current_user)


@router.post("/trigger")
async def trigger_backup(
    request: BackupRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(require_roles([UserRole.ADMIN])),
):
    return await run_trigger_backup(request, background_tasks, current_user)


@router.get("/history")
async def get_history(
    limit: int = 20,
    current_user: dict = Depends(require_roles([UserRole.ADMIN])),
):
    return await run_get_history(current_user, limit=limit)


@router.post("/verify")
async def verify_backups(
    current_user: dict = Depends(require_roles([UserRole.ADMIN])),
):
    return await run_verify_backups(current_user)


@router.get("/config")
async def get_backup_config(
    current_user: dict = Depends(require_roles([UserRole.ADMIN])),
):
    return await run_get_backup_config(current_user)


@router.post("/run-now")
async def run_backup_now(
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(require_roles([UserRole.ADMIN])),
):
    return await run_backup_now_svc(background_tasks, current_user)


@router.get("/status/{backup_id}")
async def get_backup_status(
    backup_id: str,
    current_user: dict = Depends(require_roles([UserRole.ADMIN])),
):
    return await run_get_backup_status(backup_id, current_user)


@router.post("/restore-from-s3")
async def restore_from_s3(
    data: dict,
    current_user: dict = Depends(require_roles([UserRole.ADMIN])),
):
    return await run_restore_from_s3(data, current_user)


@router.post("/restore")
async def emergency_restore(
    data: dict,
    current_user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO])),
):
    return await run_emergency_restore(data, current_user)

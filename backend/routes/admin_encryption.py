"""
====================================================================
ROTAS DE ADMINISTRAÇÃO - ENCRIPTAÇÃO — thin FastAPI stubs
====================================================================
Logic in services/admin_encryption_api_*.py.
Never create services/admin_encryption.py.
====================================================================
"""
from fastapi import APIRouter, Depends, BackgroundTasks

from models.auth import UserRole
from services.auth import require_roles
from services.admin_encryption_api_status import run_get_encryption_status
from services.admin_encryption_api_migrate import (
    run_migrate_encryption,
    run_migrate_encryption_sync,
)
from services.admin_encryption_api_verify import (
    run_verify_process_encryption,
    run_encrypt_single_process,
)

router = APIRouter(prefix="/admin/encryption", tags=["Admin - Encryption"])


@router.get("/status")
async def get_encryption_status(
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """Obtém o status atual da encriptação."""
    return await run_get_encryption_status()


@router.post("/migrate")
async def migrate_encryption(
    background_tasks: BackgroundTasks,
    dry_run: bool = False,
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """Executa a migração de encriptação em background."""
    return await run_migrate_encryption(background_tasks, dry_run, user)


@router.post("/migrate-sync")
async def migrate_encryption_sync(
    dry_run: bool = False,
    batch_size: int = 50,
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """Executa a migração de encriptação síncrona (para conjuntos pequenos)."""
    return await run_migrate_encryption_sync(dry_run, batch_size)


@router.post("/verify/{process_id}")
async def verify_process_encryption(
    process_id: str,
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """Verifica se um processo específico tem dados encriptados."""
    return await run_verify_process_encryption(process_id)


@router.post("/encrypt-process/{process_id}")
async def encrypt_single_process(
    process_id: str,
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """Encripta os dados sensíveis de um processo específico."""
    return await run_encrypt_single_process(process_id)

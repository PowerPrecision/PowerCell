"""
====================================================================
ROTAS DE ADMINISTRAÇÃO - MIGRAÇÃO RGPD — thin FastAPI stubs
====================================================================
Logic in services/admin_migration_api_*.py.
Do **not** create services/admin_migration.py (route name collision).
ACESSO: Apenas Admin, CEO ou Diretor
====================================================================
"""
from fastapi import APIRouter, BackgroundTasks, Depends

from models.auth import UserRole
from services.auth import require_roles
from services.admin_migration_api_status import run_get_migration_status
from services.admin_migration_api_run import (
    run_start_migration,
    run_migration_single,
)
# Re-export for BackgroundTasks / tests that import the task from the route
from services.admin_migration_api_task import run_migration_task  # noqa: F401
from services.admin_migration_api_helpers import is_encrypted  # noqa: F401

router = APIRouter(prefix="/admin/migration", tags=["Admin Migration"])


@router.get("/status")
async def get_migration_status(
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO, UserRole.DIRETOR]))
):
    """Verifica o estado atual da migração de encriptação."""
    return await run_get_migration_status(user)


@router.post("/run")
async def run_migration(
    background_tasks: BackgroundTasks,
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO, UserRole.DIRETOR]))
):
    """Executa a migração de encriptação de dados de clientes."""
    return await run_start_migration(background_tasks, user)


@router.post("/run-single/{client_id}")
async def run_migration_single_endpoint(
    client_id: str,
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO, UserRole.DIRETOR]))
):
    """Executa a migração para um único cliente (útil para testes)."""
    return await run_migration_single(client_id, user)

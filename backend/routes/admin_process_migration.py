"""
====================================================================
ROTAS DE ADMINISTRAÇÃO - MIGRAÇÃO FASE 1: Separação Cliente ↔ Processo
====================================================================
Thin FastAPI stubs. Logic in services/admin_proc_migration_*.py.

NOTE: Do NOT create services/admin_process_migration.py (route name collision).

ENDPOINTS:
  GET  /admin/process-migration/status    — Estado actual da migração
  POST /admin/process-migration/dry-run   — Simulação (não modifica a BD)
  POST /admin/process-migration/run       — Executar migração
  POST /admin/process-migration/reset     — Reset forçado do estado (quando preso)
  POST /admin/process-migration/rollback  — Reverter migração
====================================================================
"""
from fastapi import APIRouter, Depends, BackgroundTasks

from services.auth import require_roles
from models.auth import UserRole
from services.admin_proc_migration_api import (
    run_get_migration_status,
    run_dry_run_migration,
    run_run_migration,
    run_rollback_migration,
    run_reset_migration_state,
)

router = APIRouter(prefix="/admin/process-migration", tags=["Admin Process Migration"])


@router.get("/status")
async def get_migration_status(
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO, UserRole.DIRETOR]))
):
    """Verificar o estado actual da migração Fase 1 (Separação Cliente ↔ Processo)."""
    return await run_get_migration_status(user)


@router.post("/dry-run")
async def dry_run_migration(
    background_tasks: BackgroundTasks,
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO, UserRole.DIRETOR]))
):
    """Executar simulação da migração Fase 1 (não modifica a BD)."""
    return await run_dry_run_migration(background_tasks, user)


@router.post("/run")
async def run_migration(
    background_tasks: BackgroundTasks,
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO, UserRole.DIRETOR]))
):
    """Executar a migração Fase 1 (modifica a BD)."""
    return await run_run_migration(background_tasks, user)


@router.post("/rollback")
async def rollback_migration(
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO, UserRole.DIRETOR]))
):
    """Reverter a migração restaurando as colecções originais a partir dos backups."""
    return await run_rollback_migration(user)


@router.post("/reset")
async def reset_migration_state(
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO, UserRole.DIRETOR]))
):
    """Reset forçado do estado da migração para 'idle'."""
    return await run_reset_migration_state(user)

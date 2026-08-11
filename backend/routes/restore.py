"""
====================================================================
ROTAS DE RESTAURAÇÃO (UNDO) — thin FastAPI stubs
====================================================================
Logic in services/restore_api_*.py.
Do **not** overwrite services/backup_restore.py.
====================================================================
"""
from fastapi import APIRouter, Depends

from models.auth import UserRole
from services.auth import require_roles
from services.restore_api_process import run_restore_process
from services.restore_api_document import run_restore_document
from services.restore_api_task import run_restore_task
from services.restore_api_list import run_list_deleted_items

router = APIRouter(tags=["Restore"])


@router.post("/processes/{process_id}/restore")
async def restore_process(
    process_id: str,
    user: dict = Depends(require_roles([
        UserRole.ADMIN, UserRole.CEO, UserRole.CONSULTOR,
        UserRole.INTERMEDIARIO, UserRole.DIRETOR,
    ]))
):
    """Restaura um processo que foi eliminado (soft delete)."""
    return await run_restore_process(process_id, user)


@router.post("/documents/{document_id}/restore")
async def restore_document(
    document_id: str,
    user: dict = Depends(require_roles([
        UserRole.ADMIN, UserRole.CEO, UserRole.CONSULTOR,
        UserRole.INTERMEDIARIO, UserRole.INDEXACAO,
    ]))
):
    """Restaura um documento que foi eliminado."""
    return await run_restore_document(document_id, user)


@router.post("/tasks/{task_id}/restore")
async def restore_task(
    task_id: str,
    user: dict = Depends(require_roles([
        UserRole.ADMIN, UserRole.CEO, UserRole.CONSULTOR,
        UserRole.INTERMEDIARIO,
    ]))
):
    """Restaura uma tarefa eliminada."""
    return await run_restore_task(task_id, user)


@router.get("/deleted/items")
async def list_deleted_items(
    item_type: str = "all",  # all, processes, documents, tasks
    limit: int = 50,
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
):
    """Lista itens eliminados recentemente que podem ser restaurados."""
    return await run_list_deleted_items(item_type, limit, user)

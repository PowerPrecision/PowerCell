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
from services.by_id_scope import exigir_cliente_no_ambito, exigir_tarefa_no_ambito
from services.process_scope_guard import exigir_processo_no_ambito
from services.restore_api_process import run_restore_process
from services.restore_api_client import run_restore_client
from services.restore_api_document import run_restore_document
from services.restore_api_task import run_restore_task
from services.restore_api_list import run_list_deleted_items

# D-31: restaurar é um PEDIDO POR ID — `require_roles` autoriza o verbo, não o
# objecto. Cada dependência só actua na rota que tem o seu id no caminho.
router = APIRouter(
    tags=["Restore"],
    dependencies=[
        Depends(exigir_processo_no_ambito),
        Depends(exigir_cliente_no_ambito),
        Depends(exigir_tarefa_no_ambito),
    ],
)


@router.post("/processes/{process_id}/restore")
async def restore_process(
    process_id: str,
    user: dict = Depends(require_roles([
        UserRole.MASTER, UserRole.ADMIN, UserRole.CEO, UserRole.CONSULTOR,
        UserRole.INTERMEDIARIO, UserRole.DIRETOR,
    ]))
):
    """Restaura um processo que foi eliminado (soft delete)."""
    return await run_restore_process(process_id, user)


@router.post("/clients/{client_id}/restore")
async def restore_client(
    client_id: str,
    user: dict = Depends(require_roles([
        UserRole.MASTER, UserRole.ADMIN, UserRole.CEO, UserRole.DIRETOR,
        UserRole.ADMINISTRATIVO,
    ]))
):
    """PACOTE 11 (Eixo 4) — restaura um cliente eliminado (soft delete).

    Fecha a assimetria do DELETE /clients/{id}: o client_delete.py já
    anunciava este endpoint, mas a rota não existia. Espelho das permissões
    de eliminação (admin/ceo/diretor/administrativo). Cascata simétrica:
    processos + documentos + tarefas + pedidos RGPD do 1º titular.
    """
    return await run_restore_client(client_id, user)


@router.post("/documents/{document_id}/restore")
async def restore_document(
    document_id: str,
    user: dict = Depends(require_roles([
        UserRole.MASTER, UserRole.ADMIN, UserRole.CEO, UserRole.CONSULTOR,
        UserRole.INTERMEDIARIO, UserRole.INDEXACAO,
    ]))
):
    """Restaura um documento que foi eliminado."""
    return await run_restore_document(document_id, user)


@router.post("/tasks/{task_id}/restore")
async def restore_task(
    task_id: str,
    user: dict = Depends(require_roles([
        UserRole.MASTER, UserRole.ADMIN, UserRole.CEO, UserRole.CONSULTOR,
        UserRole.INTERMEDIARIO,
    ]))
):
    """Restaura uma tarefa eliminada."""
    return await run_restore_task(task_id, user)


@router.get("/deleted/items")
async def list_deleted_items(
    item_type: str = "all",  # all, processes, documents, tasks
    limit: int = 50,
    user: dict = Depends(require_roles([UserRole.MASTER, UserRole.ADMIN, UserRole.CEO]))
):
    """Lista itens eliminados recentemente que podem ser restaurados."""
    return await run_list_deleted_items(item_type, limit, user)

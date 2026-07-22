"""
====================================================================
ROTAS DE LOGS DE IMPORTAÇÃO IA — thin FastAPI stubs
====================================================================
Logic in services/ai_import_logs_api_*.py.
Do **not** overwrite services/admin_ai_data.py (admin AI import logs).
Keep /stats before /{log_id}. Helpers re-exported for back-compat.
====================================================================
"""
from typing import Optional

from fastapi import APIRouter, Depends, Query

from services.auth import get_current_user
from services.ai_import_logs_api_list import (
    run_list_ai_import_logs,
    run_get_ai_import_stats,
)
from services.ai_import_logs_api_detail import (
    run_get_ai_import_log,
    run_delete_ai_import_log,
)
# Re-export helpers used by ai_bulk_sessions / document_ai_analyze / etc.
from services.ai_import_logs_api_helpers import (  # noqa: F401
    create_ai_import_log,
    update_ai_import_log,
    finalize_ai_import_log,
)

router = APIRouter(prefix="/ai-import-logs", tags=["AI Import Logs"])


@router.get("")
async def list_ai_import_logs(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    status: Optional[str] = None,
    process_id: Optional[str] = None,
    search: Optional[str] = None,
    user: dict = Depends(get_current_user)
):
    """Lista logs de importações IA com paginação e filtros."""
    return await run_list_ai_import_logs(page, limit, status, process_id, search)


@router.get("/stats")
async def get_ai_import_stats(
    days: int = Query(30, ge=1, le=365),
    user: dict = Depends(get_current_user)
):
    """Estatísticas gerais de importações IA."""
    return await run_get_ai_import_stats(days)


@router.get("/{log_id}")
async def get_ai_import_log(
    log_id: str,
    user: dict = Depends(get_current_user)
):
    """Obtém detalhes completos de um log de importação."""
    return await run_get_ai_import_log(log_id)


@router.delete("/{log_id}")
async def delete_ai_import_log(
    log_id: str,
    user: dict = Depends(get_current_user)
):
    """Elimina um log de importação (apenas admin/ceo)."""
    return await run_delete_ai_import_log(log_id, user)

"""
====================================================================
SEARCH ROUTES — thin FastAPI stubs
====================================================================
Logic in services/search_api_*.py.
Do **not** overwrite utils/search_filters.py (shared filters).
====================================================================
"""
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, Depends, Query

from services.auth import get_current_user
from services.search_api_helpers import normalize_text  # noqa: F401
from services.search_api_global import run_global_search
from services.search_api_processes import run_search_processes
from services.search_api_suggestions import run_get_search_suggestions

router = APIRouter(prefix="/search", tags=["Search"])


@router.get("/global")
async def global_search(
    q: str = Query(..., min_length=1, description="Termo de pesquisa"),
    limit: int = Query(5, ge=1, le=20, description="Limite de resultados por tipo"),
    user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Pesquisa global em processos, clientes e tarefas.

    Usado pelo modal de pesquisa rápida (Ctrl+K).
    """
    return await run_global_search(q, limit, user)


@router.get("/processes")
async def search_processes(
    q: str = Query(..., min_length=2),
    status: Optional[str] = None,
    process_type: Optional[str] = None,
    limit: int = Query(20, ge=1, le=100),
    user: dict = Depends(get_current_user)
) -> List[Dict[str, Any]]:
    """Pesquisa avançada em processos."""
    return await run_search_processes(q, status, process_type, limit, user)


@router.get("/suggestions")
async def get_search_suggestions(
    q: str = Query(..., min_length=1),
    user: dict = Depends(get_current_user)
) -> List[str]:
    """Obter sugestões de pesquisa baseadas no histórico e dados existentes."""
    return await run_get_search_suggestions(q, user)

"""
====================================================================
Rotas do Agente de Melhoria com IA — thin FastAPI stubs
====================================================================
Logic in services/ai_agent_api.py.
Do **not** overwrite services/ai_improvement_agent.py.
====================================================================
"""
from fastapi import APIRouter, Depends
from typing import Dict, Any

from services.auth import get_current_user
from services.ai_agent_api import (
    run_analyze_all,
    run_analyze_single,
    run_get_suggestions,
    run_get_alerts,
    run_get_stats,
)

router = APIRouter(prefix="/ai-agent", tags=["AI Agent"])


@router.get("/analyze")
async def analyze_all(user: dict = Depends(get_current_user)) -> Dict[str, Any]:
    """Executa análise completa de todos os processos ativos."""
    return await run_analyze_all(user)


@router.get("/analyze/{process_id}")
async def analyze_single(
    process_id: str,
    user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    """Análise detalhada de um processo específico."""
    return await run_analyze_single(process_id)


@router.get("/suggestions")
async def get_suggestions(user: dict = Depends(get_current_user)) -> Dict[str, Any]:
    """Obtém apenas as sugestões de melhoria."""
    return await run_get_suggestions()


@router.get("/alerts")
async def get_alerts(
    severity: str = None,
    limit: int = 20,
    user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    """Obtém alertas de processos problemáticos."""
    return await run_get_alerts(severity, limit)


@router.get("/stats")
async def get_stats(user: dict = Depends(get_current_user)) -> Dict[str, Any]:
    """Obtém estatísticas resumidas dos processos."""
    return await run_get_stats()

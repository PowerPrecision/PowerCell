"""Stats / dashboard routes — thin FastAPI stubs.

Logic in services/stats_*.py.
Do **not** collide with existing `services/analytics_service.py`.
"""
from fastapi import APIRouter, Depends

from services.auth import get_current_user, require_staff

from services.stats_overview import run_get_stats
from services.stats_leads import run_get_leads_stats
from services.stats_conversion import run_get_conversion_stats
from services.stats_communications import run_get_communications_feed
from services.stats_health import run_health_check
from services.stats_branches import run_get_branch_performance
from services.stats_funnel import run_get_funnel
from services.stats_sla import run_get_sla
from services.stats_networks import run_get_network_comparison

router = APIRouter(tags=["Stats"])


@router.get("/stats")
async def get_stats(user: dict = Depends(get_current_user)):
    return await run_get_stats(user)


@router.get("/stats/leads")
async def get_leads_stats(user: dict = Depends(require_staff())):
    return await run_get_leads_stats(user)


@router.get("/stats/conversion")
async def get_conversion_stats(user: dict = Depends(require_staff())):
    return await run_get_conversion_stats(user)


@router.get("/stats/communications")
async def get_communications_feed(user: dict = Depends(get_current_user)):
    return await run_get_communications_feed(user)


@router.get("/health")
async def health_check():
    return await run_health_check()


@router.get("/stats/branches")
async def get_branch_performance(user: dict = Depends(require_staff())):
    return await run_get_branch_performance(user)


# ====================================================================
# BI POR MACRO-FASE (Dashboard, Camada 2)
# ====================================================================
# Estes três substituem a agregação que o `StatisticsPage` fazia no
# BROWSER, sobre os 12.450 processos crus e com listas de nomes de fases
# cravadas. Aqui a agregação corre no servidor, com a fronteira de rede no
# primeiro `$match` e a ponte com o motor a garantir que uma barra conta o
# mesmo que a coluna do quadro.


@router.get("/stats/funil")
async def get_funnel(
    consultor_id: str | None = None,
    user: dict = Depends(require_staff()),
):
    return await run_get_funnel(user, consultor_id=consultor_id)


@router.get("/stats/sla")
async def get_sla(user: dict = Depends(require_staff())):
    return await run_get_sla(user)


@router.get("/stats/redes")
async def get_network_comparison(user: dict = Depends(require_staff())):
    return await run_get_network_comparison(user)

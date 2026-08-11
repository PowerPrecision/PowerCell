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

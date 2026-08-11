"""
====================================================================
Activities / History — thin FastAPI stubs
====================================================================
Logic in services/activities_api_*.py.
====================================================================
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, Query

from models.activity import ActivityCreate, ActivityResponse, HistoryResponse
from services.auth import get_current_user
from services.activities_api_crud import (
    run_create_activity,
    run_get_activities,
    run_delete_activity,
)
from services.activities_api_history import run_get_history

router = APIRouter(tags=["Activities"])


@router.post("/activities", response_model=ActivityResponse)
async def create_activity(data: ActivityCreate, user: dict = Depends(get_current_user)):
    """Create a new activity/comment on a process"""
    return await run_create_activity(data, user)


@router.get("/activities", response_model=List[ActivityResponse])
async def get_activities(
    process_id: Optional[str] = Query(None, description="If provided, filter by process. If omitted, return recent global activities."),
    limit: int = Query(50, ge=1, le=200, description="Max number of activities to return"),
    user: dict = Depends(get_current_user)
):
    """Get activities for a process or recent global activities"""
    return await run_get_activities(process_id, limit, user)


@router.delete("/activities/{activity_id}")
async def delete_activity(activity_id: str, user: dict = Depends(get_current_user)):
    """Delete an activity (only owner or admin)"""
    return await run_delete_activity(activity_id, user)


@router.get("/history", response_model=List[HistoryResponse])
async def get_history(process_id: str, user: dict = Depends(get_current_user)):
    """Get history for a process"""
    return await run_get_history(process_id, user)

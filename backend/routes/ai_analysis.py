"""
AI Executive Summary routes — thin FastAPI stubs.

Logic in services/ai_analysis_api_*.py.
Do **not** overwrite ai_document_analyzer.py / ai_page_analyzer.py /
ai_document.py (analyzers).
"""
from typing import Any, Dict

from fastapi import APIRouter, Depends, Query

from models.auth import UserRole
from services.auth import require_roles
from services.ai_analysis_api_get import run_get_analysis
from services.ai_analysis_api_generate import run_generate_analysis

router = APIRouter(tags=["AI Executive Summary"])

_ANALYSIS_ROLES = [
    UserRole.ADMIN,
    UserRole.CEO,
    UserRole.CONSULTOR,
    UserRole.DIRETOR,
    UserRole.ADMINISTRATIVO,
]


@router.get(
    "/processes/{process_id}/analyze",
    summary="Retrieve existing AI executive summary",
)
async def get_analysis(
    process_id: str,
    user: dict = Depends(require_roles(_ANALYSIS_ROLES)),
) -> Dict[str, Any]:
    return await run_get_analysis(process_id, user)


@router.post(
    "/processes/{process_id}/analyze",
    summary="Generate AI executive summary with cross-reference audit",
)
async def generate_analysis(
    process_id: str,
    force: bool = Query(
        default=False,
        description="Force re-analysis even if a summary already exists",
    ),
    user: dict = Depends(require_roles(_ANALYSIS_ROLES)),
) -> Dict[str, Any]:
    return await run_generate_analysis(process_id, force, user)

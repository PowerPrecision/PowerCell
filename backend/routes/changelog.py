"""
====================================================================
System Changelog — thin FastAPI stubs
====================================================================
Logic in services/changelog_api_*.py.
Do **not** overwrite changelog_service.py.
Keep /diagnose and /generate-ai before colliding paths.
====================================================================
"""
from fastapi import APIRouter, Depends, Query

from services.auth import get_current_user, require_roles
from models.auth import UserRole
from models.changelog import ChangelogGenerateRequest
from services.changelog_api_list import run_list_changelogs
from services.changelog_api_diagnose import run_diagnose_changelog_generation
from services.changelog_api_generate import run_generate_changelog

router = APIRouter(prefix="/system", tags=["System Changelog"])


@router.get("/changelog")
async def list_changelogs(
    limit: int = Query(default=5, ge=1, le=20, description="Número de changelogs a devolver"),
    user: dict = Depends(get_current_user)
):
    """Obter os últimos changelogs publicados."""
    return await run_list_changelogs(limit)


@router.get("/changelog/diagnose")
async def diagnose_changelog_generation(
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
):
    """Diagnosticar problemas na geração de changelog por IA."""
    return await run_diagnose_changelog_generation()


@router.post("/changelog/generate-ai")
async def generate_changelog(
    payload: ChangelogGenerateRequest = ChangelogGenerateRequest(),
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
):
    """Gerar notas de atualização por IA a partir de logs técnicos."""
    return await run_generate_changelog(payload, user)

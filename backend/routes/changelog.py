"""
Rotas para System Changelog (Mural de Atualizações gerado por IA)

Endpoints:
- GET  /api/system/changelog          → Obter últimos changelogs (público, qualquer utilizador autenticado)
- POST /api/system/changelog/generate-ai → Gerar changelog por IA (restrito a admin/ceo)
"""
import logging
from typing import List, Dict, Any
from fastapi import APIRouter, HTTPException, Depends, Query

from services.auth import get_current_user, require_roles
from models.auth import UserRole
from models.changelog import ChangelogGenerateRequest, ChangelogGenerateResponse
from services.changelog_service import get_changelogs, generate_changelog_ai

router = APIRouter(prefix="/system", tags=["System Changelog"])
logger = logging.getLogger(__name__)


@router.get("/changelog")
async def list_changelogs(
    limit: int = Query(default=5, ge=1, le=20, description="Número de changelogs a devolver"),
    user: dict = Depends(get_current_user)
):
    """
    Obter os últimos changelogs publicados.
    Qualquer utilizador autenticado pode consultar.
    """
    try:
        changelogs = await get_changelogs(limit=limit)
        return changelogs
    except Exception as e:
        logger.error("Erro ao listar changelogs: %s", e)
        raise HTTPException(status_code=500, detail="Erro ao carregar atualizações")


@router.post("/changelog/generate-ai")
async def generate_changelog(
    payload: ChangelogGenerateRequest = ChangelogGenerateRequest(),
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
):
    """
    Gerar notas de atualização por IA a partir de logs técnicos.
    Restrito a administradores e CEO.
    
    Fontes disponíveis:
    - 'git': Histórico de commits (padrão)
    - 'changelog_file': Ficheiro CHANGELOG.md
    - 'worklog': Ficheiro worklog.md
    """
    try:
        result = await generate_changelog_ai(
            source_type=payload.source_type,
            max_source_lines=payload.max_source_lines,
            custom_prompt_suffix=payload.custom_prompt_suffix
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        logger.error("Erro inesperado ao gerar changelog: %s", e)
        raise HTTPException(status_code=500, detail="Erro ao gerar notas de atualização")

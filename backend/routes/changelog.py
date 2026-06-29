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
        error_msg = str(e)
        logger.warning("[CHANGELOG] ValueError ao gerar: %s | source_type=%s | user=%s", error_msg, payload.source_type, user.get("email"))
        # Mensagens mais amigáveis para os erros mais comuns
        if "EMERGENT_LLM_KEY" in error_msg or "OpenAI" in error_msg:
            friendly = "A chave da API da IA (EMERGENT_LLM_KEY) não está configurada no servidor. Contacte o administrador para configurar a integração com OpenAI."
        elif "Não foi possível obter dados da fonte" in error_msg:
            friendly = (f"Não foi possível obter dados da fonte '{payload.source_type}'. "
                        "No Render, o histórico Git pode não estar disponível. "
                        "Tente selecionar 'Ficheiro CHANGELOG.md' ou 'worklog.md' como fonte.")
        elif "Fonte não suportada" in error_msg:
            friendly = error_msg
        else:
            friendly = error_msg
        raise HTTPException(status_code=400, detail=friendly)
    except RuntimeError as e:
        logger.error("[CHANGELOG] RuntimeError ao gerar: %s", e)
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        logger.exception("[CHANGELOG] Erro inesperado ao gerar changelog: %s", e)
        raise HTTPException(status_code=500, detail=f"Erro ao gerar notas de atualização: {type(e).__name__}: {e}")

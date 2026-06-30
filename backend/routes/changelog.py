"""
Rotas para System Changelog (Mural de Atualizações gerado por IA)

Endpoints:
- GET  /api/system/changelog          → Obter últimos changelogs (público, qualquer utilizador autenticado)
- GET  /api/system/changelog/diagnose → Diagnosticar problemas na geração (admin/ceo)
- POST /api/system/changelog/generate-ai → Gerar changelog por IA (restrito a admin/ceo)
"""
import os
import logging
from typing import List, Dict, Any
from fastapi import APIRouter, HTTPException, Depends, Query

from services.auth import get_current_user, require_roles
from models.auth import UserRole
from models.changelog import ChangelogGenerateRequest, ChangelogGenerateResponse
from services.changelog_service import (
    get_changelogs, generate_changelog_ai,
    _resolve_project_file, read_worklog_file, read_changelog_file,
    get_ai_client_and_model,
)

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


@router.get("/changelog/diagnose")
async def diagnose_changelog_generation(
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
):
    """
    Diagnosticar problemas na geração de changelog por IA.

    Verifica:
    1. Acessibilidade dos ficheiros (local + GitHub fallback)
    2. Configuração de credenciais de IA (BD + env vars)
    3. Capacidade de ler conteúdo de cada fonte

    Retorna um relatório detalhado para diagnóstico.
    """
    report = {
        "checks": {},
        "can_generate": False,
        "blocking_issue": None,
    }

    # ── 1. Verificar ficheiros de fonte ──
    worklog_local = _resolve_project_file("worklog.md")
    changelog_local = _resolve_project_file("CHANGELOG.md")

    report["checks"]["files"] = {
        "worklog_md_local_path": worklog_local,
        "changelog_md_local_path": changelog_local,
        "worklog_md_local_exists": worklog_local is not None,
        "changelog_md_local_exists": changelog_local is not None,
    }

    # Testar leitura de worklog (async — inclui fallback GitHub)
    try:
        worklog_content = await read_worklog_file(10)
        report["checks"]["files"]["worklog_md_readable"] = bool(worklog_content)
        report["checks"]["files"]["worklog_md_sample"] = worklog_content[:100] if worklog_content else None
    except Exception as e:
        report["checks"]["files"]["worklog_md_readable"] = False
        report["checks"]["files"]["worklog_md_error"] = str(e)

    # Testar leitura de CHANGELOG (async — inclui fallback GitHub)
    try:
        changelog_content = await read_changelog_file(10)
        report["checks"]["files"]["changelog_md_readable"] = bool(changelog_content)
        report["checks"]["files"]["changelog_md_sample"] = changelog_content[:100] if changelog_content else None
    except Exception as e:
        report["checks"]["files"]["changelog_md_readable"] = False
        report["checks"]["files"]["changelog_md_error"] = str(e)

    # ── 2. Verificar credenciais de IA ──
    try:
        client, model = await get_ai_client_and_model()
        report["checks"]["ai_credentials"] = {
            "configured": client is not None,
            "model": model,
            "has_openai_env_key": bool(os.environ.get("OPENAI_API_KEY")),
            "has_emergent_env_key": bool(os.environ.get("EMERGENT_LLM_KEY")),
        }
    except Exception as e:
        report["checks"]["ai_credentials"] = {
            "configured": False,
            "error": str(e),
        }

    # ── 3. Verificar git ──
    from services.changelog_service import read_git_log
    try:
        git_log = read_git_log(5)
        report["checks"]["git"] = {
            "available": bool(git_log),
            "sample": git_log[:100] if git_log else None,
        }
    except Exception as e:
        report["checks"]["git"] = {"available": False, "error": str(e)}

    # ── 4. Determinar blockers ──
    has_source = (
        report["checks"]["files"].get("worklog_md_readable") or
        report["checks"]["files"].get("changelog_md_readable") or
        report["checks"]["git"].get("available")
    )
    has_credentials = report["checks"]["ai_credentials"].get("configured", False)

    if not has_credentials:
        report["blocking_issue"] = (
            "Credenciais de IA não configuradas. Configure no painel de administração "
            "(Configurações → IA) ou defina OPENAI_API_KEY / EMERGENT_LLM_KEY nas env vars."
        )
    elif not has_source:
        report["blocking_issue"] = (
            "Nenhuma fonte de dados disponível (worklog.md, CHANGELOG.md e git log todos vazios). "
            "Verifique se o fallback do GitHub está a funcionar."
        )
    else:
        report["can_generate"] = True
        report["blocking_issue"] = None

    return report


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
        if "Nenhuma credencial de IA configurada" in error_msg:
            friendly = ("Nenhuma credencial de IA configurada. Configure o provider e a API key "
                        "no painel de administração (Configurações → IA) ou defina OPENAI_API_KEY / "
                        "EMERGENT_LLM_KEY nas variáveis de ambiente do servidor.")
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

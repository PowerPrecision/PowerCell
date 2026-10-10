"""
====================================================================
System Changelog — thin FastAPI stubs
====================================================================
Logic in services/changelog_api_*.py.
Do **not** overwrite changelog_service.py.
Keep /diagnose and /generate-ai before colliding paths.

AS ATUALIZAÇÕES SÃO DO CRM, E GLOBAIS
  * Só a equipa do CRM as lê (`require_staff`): o cliente e o parceiro —
    contas fantasma ou tokens dos portais — nunca. Os tokens dos Portais do
    Cliente e do Parceiro nem chegam aqui: o `get_current_user` recusa-os (401).
  * Não têm fronteira de rede: são as MESMAS para todas as redes e empresas.
  * `is_premium` é um rótulo de venda posto pelo Master (upsell).
====================================================================
"""
from fastapi import APIRouter, Depends, HTTPException, Query

from services.auth import require_roles, require_staff
from services.role_scope import utilizador_e_global
from models.auth import UserRole
from models.changelog import ChangelogGenerateRequest, ChangelogPremiumRequest
from services.changelog_api_list import run_list_changelogs
from services.changelog_api_diagnose import run_diagnose_changelog_generation
from services.changelog_api_generate import run_generate_changelog
from services.changelog_api_premium import MENSAGEM_SO_MASTER, run_set_changelog_premium

router = APIRouter(prefix="/system", tags=["System Changelog"])


@router.get("/changelog")
async def list_changelogs(
    limit: int = Query(default=5, ge=1, le=20, description="Número de changelogs a devolver"),
    user: dict = Depends(require_staff())
):
    """Obter os últimos changelogs publicados (globais; só a equipa do CRM)."""
    return await run_list_changelogs(limit)


@router.get("/changelog/diagnose")
async def diagnose_changelog_generation(
    user: dict = Depends(require_roles([UserRole.MASTER, UserRole.ADMIN, UserRole.CEO]))
):
    """Diagnosticar problemas na geração de changelog por IA."""
    return await run_diagnose_changelog_generation()


@router.post("/changelog/generate-ai")
async def generate_changelog(
    payload: ChangelogGenerateRequest = ChangelogGenerateRequest(),
    user: dict = Depends(require_roles([UserRole.MASTER, UserRole.ADMIN, UserRole.CEO]))
):
    """Gerar notas de atualização por IA a partir de logs técnicos."""
    # Marcar como Premium é decisão comercial da plataforma: só o Master.
    if payload.is_premium and not utilizador_e_global(user):
        raise HTTPException(status_code=403, detail=MENSAGEM_SO_MASTER)
    return await run_generate_changelog(payload, user)


@router.patch("/changelog/{changelog_id}/premium")
async def set_changelog_premium(
    changelog_id: str,
    payload: ChangelogPremiumRequest,
    user: dict = Depends(require_roles([UserRole.MASTER]))
):
    """Marcar/desmarcar uma atualização como Premium (só o Master)."""
    return await run_set_changelog_premium(changelog_id, payload, user)

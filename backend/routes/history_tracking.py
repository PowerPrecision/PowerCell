"""
====================================================================
CONTROLO DE HISTÓRICO — thin stubs (Bloco 1, ponto 4)
====================================================================
Lógica em `services/history_tracking.py`. Só o ADMIN (master): nem o CEO
liga ou desliga o registo de outras pessoas.
====================================================================
"""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from models.auth import UserRole
from services.auth import require_roles
from services.history_tracking import (
    run_get_history_tracking,
    run_list_users_history,
    run_set_role_history,
    run_set_user_history,
)

router = APIRouter(prefix="/admin/history-tracking", tags=["Admin — Histórico"])


class RoleHistoryBody(BaseModel):
    enabled: bool


class UserHistoryBody(BaseModel):
    # `null` remove o override pessoal: a pessoa volta a seguir o perfil.
    enabled: Optional[bool] = None


@router.get("")
async def get_history_tracking(user: dict = Depends(require_roles([UserRole.MASTER]))):
    """Os perfis e se cada um deixa rasto no histórico."""
    return await run_get_history_tracking(user)


@router.put("/roles/{role}")
async def set_role_history(
    role: str,
    body: RoleHistoryBody,
    user: dict = Depends(require_roles([UserRole.MASTER])),
):
    """Liga/desliga o registo de um perfil. `indexacao` é sempre recusado."""
    return await run_set_role_history(role, body.enabled, user)


@router.get("/users")
async def list_users_history(
    search: Optional[str] = Query(None, description="Nome ou email"),
    page: int = Query(1, ge=1),
    size: int = Query(25, ge=1, le=100),
    user: dict = Depends(require_roles([UserRole.MASTER])),
):
    """Utilizadores com o override pessoal e o estado efectivo."""
    return await run_list_users_history(search=search, page=page, size=size)


@router.put("/users/{user_id}")
async def set_user_history(
    user_id: str,
    body: UserHistoryBody,
    user: dict = Depends(require_roles([UserRole.MASTER])),
):
    """Liga/desliga o registo de uma pessoa (`enabled: null` remove o override)."""
    return await run_set_user_history(user_id, body.enabled, user)

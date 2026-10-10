"""
====================================================================
ROTAS: UserCompanyRole — thin FastAPI stubs
====================================================================
Logic in services/user_company_roles_api_*.py.
Keep static /migrate* before /{role_id}.
PREFIX: /admin/user-company-roles

Pacote FH / C6: POST set-active-company vive em /auth/active-company
(get_current_user, sem require_admin).
====================================================================
"""
from typing import Optional

from fastapi import APIRouter, Depends

from models.user_company_role import (
    UserCompanyRoleCreate,
    UserCompanyRoleUpdate,
)
from services.auth import get_current_user, require_admin, require_master
from services.user_company_roles_api_crud import (
    run_list_user_company_roles,
    run_get_user_company_role,
    run_create_user_company_role,
    run_update_user_company_role,
    run_delete_user_company_role,
)
from services.user_company_roles_api_migrate import (
    run_migrate_company_field,
    run_migrate_email_configs,
)

router = APIRouter(
    prefix="/admin/user-company-roles",
    tags=["User Company Roles"],
    dependencies=[Depends(require_admin())],
)


@router.get("")
async def list_user_company_roles(
    user_id: Optional[str] = None,
    company_id: Optional[str] = None,
    actor: dict = Depends(get_current_user),
):
    """Lista associações user-company-role (só as do âmbito de quem pede)."""
    return await run_list_user_company_roles(user_id, company_id, actor=actor)


@router.post("")
async def create_user_company_role(
    payload: UserCompanyRoleCreate,
    actor: dict = Depends(get_current_user),
):
    """Associa um utilizador a uma empresa com um role específico."""
    return await run_create_user_company_role(payload, actor=actor)


@router.post("/migrate", dependencies=[Depends(require_master())])
async def migrate_company_field():
    """Migração: popula user_company_roles a partir do campo `company`."""
    return await run_migrate_company_field()


@router.post("/migrate-email-configs", dependencies=[Depends(require_master())])
async def migrate_email_configs():
    """Migração: move configs de email embebidas para user_email_configs."""
    return await run_migrate_email_configs()


@router.get("/{role_id}")
async def get_user_company_role(role_id: str, actor: dict = Depends(get_current_user)):
    """Obtém uma associação específica pelo ID."""
    return await run_get_user_company_role(role_id, actor=actor)


@router.put("/{role_id}")
async def update_user_company_role(
    role_id: str,
    payload: UserCompanyRoleUpdate,
    actor: dict = Depends(get_current_user),
):
    """Atualiza o role ou is_default de uma associação existente."""
    return await run_update_user_company_role(role_id, payload, actor=actor)


@router.delete("/{role_id}")
async def delete_user_company_role(role_id: str, actor: dict = Depends(get_current_user)):
    """Remove uma associação user-company-role."""
    return await run_delete_user_company_role(role_id, actor=actor)

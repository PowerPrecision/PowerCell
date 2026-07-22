"""
====================================================================
ROTAS: UserCompanyRole — thin FastAPI stubs
====================================================================
Logic in services/user_company_roles_api_*.py.
Keep static /migrate*, /set-active-company before /{role_id}.
PREFIX: /admin/user-company-roles
====================================================================
"""
from typing import Optional

from fastapi import APIRouter, Depends

from models.user_company_role import (
    UserCompanyRoleCreate,
    UserCompanyRoleUpdate,
)
from services.auth import require_admin, get_current_user
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
from services.user_company_roles_api_active import run_set_active_company

router = APIRouter(
    prefix="/admin/user-company-roles",
    tags=["User Company Roles"],
    dependencies=[Depends(require_admin())],
)


@router.get("")
async def list_user_company_roles(
    user_id: Optional[str] = None,
    company_id: Optional[str] = None,
):
    """Lista associações user-company-role."""
    return await run_list_user_company_roles(user_id, company_id)


@router.post("")
async def create_user_company_role(payload: UserCompanyRoleCreate):
    """Associa um utilizador a uma empresa com um role específico."""
    return await run_create_user_company_role(payload)


@router.post("/migrate")
async def migrate_company_field():
    """Migração: popula user_company_roles a partir do campo `company`."""
    return await run_migrate_company_field()


@router.post("/set-active-company")
async def set_active_company(
    data: dict,
    user: dict = Depends(get_current_user),
):
    """Define a empresa ativa para o utilizador autenticado."""
    return await run_set_active_company(data, user)


@router.post("/migrate-email-configs")
async def migrate_email_configs():
    """Migração: move configs de email embebidas para user_email_configs."""
    return await run_migrate_email_configs()


@router.get("/{role_id}")
async def get_user_company_role(role_id: str):
    """Obtém uma associação específica pelo ID."""
    return await run_get_user_company_role(role_id)


@router.put("/{role_id}")
async def update_user_company_role(role_id: str, payload: UserCompanyRoleUpdate):
    """Atualiza o role ou is_default de uma associação existente."""
    return await run_update_user_company_role(role_id, payload)


@router.delete("/{role_id}")
async def delete_user_company_role(role_id: str):
    """Remove uma associação user-company-role."""
    return await run_delete_user_company_role(role_id)

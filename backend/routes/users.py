"""
====================================================================
ROTAS DE UTILIZADORES - CREDITOIMO — thin FastAPI stubs
====================================================================
Logic in services/users_api_*.py.
Do **not** overwrite services/auth.py; admin CRUD stays in admin routes.
Keep static `/me/email-config*` before any future `/{user_id}/...` collisions.
====================================================================
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, Query, Request

from models.auth import UserResponse
from models.email_config import EmailConfigCreate
from services.auth import get_current_user, require_staff
from services.users_api_list import run_get_staff_users, run_get_user, run_get_users
from services.users_api_email_config import (
    run_get_my_email_config,
    run_save_my_email_config,
    run_test_my_email_config,
    run_list_my_email_accounts,
    run_add_my_email_account,
    run_update_my_email_account,
    run_delete_my_email_account,
    run_set_primary_email_account,
)

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("", response_model=List[UserResponse])
async def get_users(
    role: str = None,
    for_assignment: bool = Query(
        False,
        description="Se true, devolve só staff elegível para atribuições "
        "(exclui admin e indexação).",
    ),
    user: dict = Depends(require_staff()),
):
    """Listar utilizadores do sistema."""
    return await run_get_users(role, user, for_assignment=for_assignment)


@router.get("/me/email-config")
async def get_my_email_config(
    request: Request,
    company_id: Optional[str] = Query(
        None, description="ID da empresa (fallback para X-Company-Id header)",
    ),
    current_user: dict = Depends(get_current_user),
):
    """Obter configuração de email do utilizador logado."""
    return await run_get_my_email_config(request, company_id, current_user)


@router.post("/me/email-config")
async def save_my_email_config(
    request: Request,
    config: EmailConfigCreate,
    company_id: Optional[str] = Query(
        None, description="ID da empresa (fallback para body.company_id / X-Company-Id)",
    ),
    current_user: dict = Depends(get_current_user),
):
    """Guardar configuração de email do utilizador, isolada por company_id."""
    return await run_save_my_email_config(
        request, config, current_user, query_company_id=company_id,
    )


@router.post("/me/email-config/test")
async def test_my_email_config(
    request: Request,
    company_id: Optional[str] = Query(
        None, description="ID da empresa (fallback para X-Company-Id header)",
    ),
    current_user: dict = Depends(get_current_user),
):
    """Testar ligação de email do utilizador."""
    return await run_test_my_email_config(request, company_id, current_user)


@router.get("/me/email-accounts")
async def list_my_email_accounts(
    request: Request,
    company_id: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
):
    """Listar contas de email do perfil activo (Pacote DN.4)."""
    return await run_list_my_email_accounts(request, company_id, current_user)


@router.post("/me/email-accounts")
async def add_my_email_account(
    request: Request,
    config: EmailConfigCreate,
    company_id: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
):
    """Adicionar uma conta IMAP/SMTP extra ao perfil activo."""
    return await run_add_my_email_account(
        request, config, current_user, query_company_id=company_id,
    )


@router.put("/me/email-accounts/{account_id}")
async def update_my_email_account(
    request: Request,
    account_id: str,
    config: EmailConfigCreate,
    current_user: dict = Depends(get_current_user),
):
    """Actualizar uma conta de email do perfil."""
    return await run_update_my_email_account(request, account_id, config, current_user)


@router.delete("/me/email-accounts/{account_id}")
async def delete_my_email_account(
    request: Request,
    account_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Remover uma conta de email do perfil."""
    return await run_delete_my_email_account(request, account_id, current_user)


@router.post("/me/email-accounts/{account_id}/set-primary")
async def set_primary_email_account(
    request: Request,
    account_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Definir a conta por omissão do perfil activo."""
    return await run_set_primary_email_account(request, account_id, current_user)


@router.get("/staff", response_model=List[UserResponse])
async def get_staff_users(user: dict = Depends(require_staff())):
    """Staff para dropdowns de atribuição (sem admin/indexação)."""
    return await run_get_staff_users(user)


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(user_id: str, user: dict = Depends(require_staff())):
    """Obter utilizador por ID."""
    return await run_get_user(user_id, user)

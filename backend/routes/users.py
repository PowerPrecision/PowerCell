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
from services.users_api_list import run_get_user, run_get_users
from services.users_api_email_config import (
    run_get_my_email_config,
    run_save_my_email_config,
    run_test_my_email_config,
)

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("", response_model=List[UserResponse])
async def get_users(role: str = None, user: dict = Depends(require_staff())):
    """Listar utilizadores do sistema."""
    return await run_get_users(role, user)


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
    current_user: dict = Depends(get_current_user),
):
    """Guardar configuração de email do utilizador."""
    return await run_save_my_email_config(request, config, current_user)


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


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(user_id: str, user: dict = Depends(require_staff())):
    """Obter utilizador por ID."""
    return await run_get_user(user_id, user)

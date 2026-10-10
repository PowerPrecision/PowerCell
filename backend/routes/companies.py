"""
====================================================================
ROTAS: Company Email Config — thin FastAPI stubs
====================================================================
Logic in services/companies_api_*.py (not companies_crud_api_*).
Keep /available-companies before /{company_name}.
====================================================================
"""
from fastapi import APIRouter, Depends

from models.company_email_config import (
    CompanyEmailConfigCreate,
    CompanyEmailConfigListResponse,
)
from services.auth import get_current_user, require_admin
from services.companies_api_list import (
    run_list_company_configs,
    run_get_available_companies,
    run_get_company_config,
)
from services.companies_api_mutate import (
    run_create_company_config,
    run_update_company_config,
    run_delete_company_config,
)

router = APIRouter(
    prefix="/admin/company-email-configs",
    tags=["Company Email Configs"],
    dependencies=[Depends(require_admin())]
)


@router.get("", response_model=CompanyEmailConfigListResponse)
async def list_company_configs(user: dict = Depends(get_current_user)):
    """Lista as configurações de email por empresa (do âmbito de quem pede)."""
    return await run_list_company_configs(actor=user)


@router.get("/available-companies")
async def get_available_companies(user: dict = Depends(get_current_user)):
    """Lista empresas registadas com indicação de config de email."""
    return await run_get_available_companies(actor=user)


@router.get("/{company_name}")
async def get_company_config(company_name: str, user: dict = Depends(get_current_user)):
    """Obtém a config de email de uma empresa específica."""
    return await run_get_company_config(company_name, actor=user)


@router.post("")
async def create_company_config(
    payload: CompanyEmailConfigCreate, user: dict = Depends(get_current_user),
):
    """Cria uma nova config de email por empresa."""
    return await run_create_company_config(payload, actor=user)


@router.put("/{company_name}")
async def update_company_config(
    company_name: str,
    payload: CompanyEmailConfigCreate,
    user: dict = Depends(get_current_user),
):
    """Atualiza a config de email de uma empresa."""
    return await run_update_company_config(company_name, payload, actor=user)


@router.delete("/{company_name}")
async def delete_company_config(company_name: str, user: dict = Depends(get_current_user)):
    """Remove a config de email de uma empresa."""
    return await run_delete_company_config(company_name, actor=user)

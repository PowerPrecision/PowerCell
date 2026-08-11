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
from services.auth import require_admin
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
async def list_company_configs():
    """Lista todas as configurações de email por empresa."""
    return await run_list_company_configs()


@router.get("/available-companies")
async def get_available_companies():
    """Lista empresas registadas com indicação de config de email."""
    return await run_get_available_companies()


@router.get("/{company_name}")
async def get_company_config(company_name: str):
    """Obtém a config de email de uma empresa específica."""
    return await run_get_company_config(company_name)


@router.post("")
async def create_company_config(payload: CompanyEmailConfigCreate):
    """Cria uma nova config de email por empresa."""
    return await run_create_company_config(payload)


@router.put("/{company_name}")
async def update_company_config(company_name: str, payload: CompanyEmailConfigCreate):
    """Atualiza a config de email de uma empresa."""
    return await run_update_company_config(company_name, payload)


@router.delete("/{company_name}")
async def delete_company_config(company_name: str):
    """Remove a config de email de uma empresa."""
    return await run_delete_company_config(company_name)

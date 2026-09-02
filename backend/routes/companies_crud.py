"""
====================================================================
ROTAS: Companies — CRUD de Empresas (Multi-Tenant) — thin stubs
====================================================================
Logic in services/companies_crud_api_*.py.
Prefer companies_crud_api_* / company_crud_* naming.

PREFIX: /admin/companies
====================================================================
"""
from typing import Optional

from fastapi import APIRouter, Depends, File, Query, UploadFile

from models.company import (
    CompanyCreate,
    CompanyUpdate,
    CompanyResponse,
    CompanyListResponse,
    CompanyEmailConnectionTest,
)
from services.auth import require_admin
from services.companies_crud_api_list import (
    run_list_companies,
    run_list_available_companies,
    run_get_company,
)
from services.companies_crud_api_mutate import (
    run_create_company,
    run_update_company,
    run_delete_company,
)
from services.companies_crud_api_logo import run_upload_company_logo
from services.companies_crud_api_test_connection import run_test_email_connection

router = APIRouter(
    prefix="/admin/companies",
    tags=["Companies"],
    dependencies=[Depends(require_admin())],
)


@router.get("", response_model=CompanyListResponse)
async def list_companies(
    search: Optional[str] = Query(None, description="Pesquisa por nome ou NIF"),
):
    """Lista todas as empresas configuradas no sistema."""
    return await run_list_companies(search)


@router.get("/available", response_model=list)
async def list_available_companies():
    """Lista nomes das empresas disponíveis (para selects/dropdowns)."""
    return await run_list_available_companies()


@router.get("/{company_id}", response_model=CompanyResponse)
async def get_company(company_id: str):
    """Obtém uma empresa pelo ID (ou por nome como fallback)."""
    return await run_get_company(company_id)


@router.post("", response_model=CompanyResponse, status_code=201)
async def create_company(data: CompanyCreate):
    """Cria uma nova empresa."""
    return await run_create_company(data)


@router.post("/test-email-connection")
async def test_email_connection(data: CompanyEmailConnectionTest):
    """Testa a ligação SMTP e/ou IMAP com os valores atuais do formulário, sem gravar."""
    return await run_test_email_connection(data)


@router.put("/{company_id}", response_model=CompanyResponse)
async def update_company(company_id: str, data: CompanyUpdate):
    """Atualiza os dados de uma empresa."""
    return await run_update_company(company_id, data)


@router.delete("/{company_id}")
async def delete_company(company_id: str):
    """Remove uma empresa e gere utilizadores associados."""
    return await run_delete_company(company_id)


@router.post("/{company_id}/logo")
async def upload_company_logo(
    company_id: str,
    file: UploadFile = File(...),
):
    """Faz upload do logótipo da empresa para o S3."""
    return await run_upload_company_logo(company_id, file)

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
from services.auth import get_current_user, require_admin, require_master
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
    page: int = Query(1, ge=1),
    size: int = Query(25, ge=1, le=100),
    user: dict = Depends(get_current_user),
):
    """Empresas que o utilizador pode administrar.

    Isolamento por Rede (ponto 11) e paginação: o `.to_list(200)` que
    aqui estava truncava em silêncio.
    """
    return await run_list_companies(search, user=user, page=page, size=size)


@router.get("/available", response_model=list)
async def list_available_companies(user: dict = Depends(get_current_user)):
    """Lista nomes das empresas disponíveis (para selects/dropdowns)."""
    return await run_list_available_companies(actor=user)


@router.get("/{company_id}", response_model=CompanyResponse)
async def get_company(company_id: str, user: dict = Depends(get_current_user)):
    """Obtém uma empresa pelo ID (ou por nome como fallback)."""
    return await run_get_company(company_id, actor=user)


@router.post(
    "", response_model=CompanyResponse, status_code=201,
    dependencies=[Depends(require_master())],
)
async def create_company(data: CompanyCreate):
    """Cria uma nova empresa (um novo inquilino: só o Master)."""
    return await run_create_company(data)


@router.post("/test-email-connection")
async def test_email_connection(data: CompanyEmailConnectionTest):
    """Testa a ligação SMTP e/ou IMAP com os valores atuais do formulário, sem gravar."""
    return await run_test_email_connection(data)


@router.put("/{company_id}", response_model=CompanyResponse)
async def update_company(
    company_id: str, data: CompanyUpdate, user: dict = Depends(get_current_user),
):
    """Atualiza os dados de uma empresa (a própria; a rede só o Master)."""
    return await run_update_company(company_id, data, actor=user)


@router.delete("/{company_id}", dependencies=[Depends(require_master())])
async def delete_company(company_id: str):
    """Remove uma empresa e gere utilizadores associados."""
    return await run_delete_company(company_id)


@router.post("/{company_id}/logo")
async def upload_company_logo(
    company_id: str,
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
):
    """Faz upload do logótipo da empresa para o S3."""
    return await run_upload_company_logo(company_id, file, actor=user)

"""
Rotas de Finanças - PowerCell — thin FastAPI stubs.

Logic in services/finance_*.py.
Do not confuse with services/process_finance.py (process snapshots).

Dashboard Financeiro acessível a toda a equipa interna.
Calcula receitas, despesas e lucro líquido com base nos dados dos processos,
separados por área de negócio (Imobiliária e Crédito) com configurações dinâmicas.

Permissões:
- GET (leitura): todos os roles de staff (excepto cliente e parceiro)
- PUT /finance/config (escrita): apenas Admin e CEO
"""
from typing import Optional

from fastapi import APIRouter, Depends, Query

from models.auth import UserRole
from models.finance import (
    FinanceConfigCreate as FinanceConfigCreateSchema,
    FinanceConfigUpdate as FinanceConfigUpdateSchema,
    ProcessFinanceCreate,
    ProcessFinanceUpdate,
)
from services.auth import require_roles
from services.finance_helpers import (
    FINANCE_READ_ROLES,
    DashboardFinanceConfigUpdate,
)
from services.finance_dashboard import (
    run_get_finance_config,
    run_update_finance_config,
    run_get_finance_summary,
    run_get_finance_monthly,
    run_get_finance_performance,
)
from services.finance_commissions import (
    run_get_finance_commissions,
    run_export_commissions_csv,
)
from services.finance_configs import (
    run_create_finance_config,
    run_list_finance_configs,
    run_get_finance_config_by_id,
    run_update_finance_config_by_id,
    run_delete_finance_config,
)
from services.finance_pool import (
    run_get_pool_distribution,
    run_export_pool_distribution_csv,
)
from services.finance_process_records import (
    run_get_process_finance_summary,
    run_create_process_finance,
    run_list_process_finances,
    run_get_process_finance_by_id,
    run_update_process_finance,
    run_update_process_finance_status,
    run_delete_process_finance,
)

router = APIRouter(tags=["Finance"])


# ====================================================================
# CONFIG ENDPOINTS
# ====================================================================

@router.get("/finance/config")
async def get_finance_config(
    user: dict = Depends(require_roles(FINANCE_READ_ROLES))
):
    return await run_get_finance_config(user)


@router.put("/finance/config")
async def update_finance_config(
    body: DashboardFinanceConfigUpdate,
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
):
    return await run_update_finance_config(body, user)


# ====================================================================
# SUMMARY ENDPOINT (separado por área)
# ====================================================================

@router.get("/finance/summary")
async def get_finance_summary(
    year: Optional[int] = Query(None, description="Ano para filtrar (ex: 2025)"),
    user: dict = Depends(require_roles(FINANCE_READ_ROLES))
):
    return await run_get_finance_summary(year, user)


# ====================================================================
# MONTHLY ENDPOINT
# ====================================================================

@router.get("/finance/monthly")
async def get_finance_monthly(
    year: Optional[int] = Query(None, description="Ano para filtrar"),
    user: dict = Depends(require_roles(FINANCE_READ_ROLES))
):
    return await run_get_finance_monthly(year, user)


# ====================================================================
# COMMISSIONS ENDPOINT
# ====================================================================

@router.get("/finance/commissions")
async def get_finance_commissions(
    year: Optional[int] = Query(None, description="Ano para filtrar"),
    company_id: Optional[str] = Query(None, description="Empresa para filtrar (multi-tenant)"),
    user: dict = Depends(require_roles(FINANCE_READ_ROLES))
):
    return await run_get_finance_commissions(year, company_id, user)


@router.get("/finance/commissions/export")
async def export_commissions_csv(
    year: Optional[int] = Query(None, description="Ano para filtrar"),
    company_id: str = Query(..., description="Empresa para filtrar (obrigatório)"),
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
):
    return await run_export_commissions_csv(year, company_id, user)


# ====================================================================
# PERFORMANCE ENDPOINT
# ====================================================================

@router.get("/finance/performance")
async def get_finance_performance(
    year: Optional[int] = Query(None, description="Ano para filtrar"),
    user: dict = Depends(require_roles(FINANCE_READ_ROLES))
):
    return await run_get_finance_performance(year, user)


# ====================================================================
# NEW CRUD: FinanceConfig (collection: finance_configs)
# ====================================================================

@router.post("/finance/configs")
async def create_finance_config(
    body: FinanceConfigCreateSchema,
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
):
    return await run_create_finance_config(body, user)


@router.get("/finance/configs")
async def list_finance_configs(
    company_id: Optional[str] = Query(None, description="Filtrar por company_id"),
    user: dict = Depends(require_roles(FINANCE_READ_ROLES))
):
    return await run_list_finance_configs(company_id, user)


@router.get("/finance/configs/{config_id}")
async def get_finance_config_by_id(
    config_id: str,
    user: dict = Depends(require_roles(FINANCE_READ_ROLES))
):
    return await run_get_finance_config_by_id(config_id, user)


@router.put("/finance/configs/{config_id}")
async def update_finance_config_by_id(
    config_id: str,
    body: FinanceConfigUpdateSchema,
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
):
    return await run_update_finance_config_by_id(config_id, body, user)


@router.delete("/finance/configs/{config_id}")
async def delete_finance_config(
    config_id: str,
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
):
    return await run_delete_finance_config(config_id, user)


# ====================================================================
# POOL DISTRIBUTION — Fecho de Mês (Modelo Global Pool)
# ====================================================================

@router.get("/finance/pool-distribution")
async def get_pool_distribution(
    month: int = Query(..., ge=1, le=12, description="Mês (1-12)"),
    year: int = Query(..., ge=2020, le=2100, description="Ano (ex: 2025)"),
    company_id: str = Query(..., description="Empresa para filtrar (obrigatório)"),
    user: dict = Depends(require_roles(FINANCE_READ_ROLES))
):
    return await run_get_pool_distribution(month, year, company_id, user)


@router.get("/finance/pool-distribution/export")
async def export_pool_distribution_csv(
    month: int = Query(..., ge=1, le=12, description="Mês (1-12)"),
    year: int = Query(..., ge=2020, le=2100, description="Ano (ex: 2025)"),
    company_id: str = Query(..., description="Empresa para filtrar (obrigatório)"),
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
):
    return await run_export_pool_distribution_csv(month, year, company_id, user)


# ====================================================================
# NEW CRUD: ProcessFinance (collection: process_finances)
# ====================================================================
# NOTA: /finance/processes/summary deve ser definido ANTES de
# /finance/processes/{finance_id} para evitar que "summary" seja
# interpretado como um finance_id pelo FastAPI.

@router.get("/finance/processes/summary")
async def get_process_finance_summary(
    company_id: str = Query(..., description="Empresa para filtrar (obrigatório)"),
    user: dict = Depends(require_roles(FINANCE_READ_ROLES))
):
    return await run_get_process_finance_summary(company_id, user)


@router.post("/finance/processes")
async def create_process_finance(
    body: ProcessFinanceCreate,
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO, UserRole.DIRETOR]))
):
    return await run_create_process_finance(body, user)


@router.get("/finance/processes")
async def list_process_finances(
    company_id: Optional[str] = Query(None, description="Filtrar por company_id"),
    process_id: Optional[str] = Query(None, description="Filtrar por process_id"),
    client_id: Optional[str] = Query(None, description="Filtrar por client_id"),
    status: Optional[str] = Query(None, description="Filtrar por status (pending|invoiced|paid|cancelled)"),
    user: dict = Depends(require_roles(FINANCE_READ_ROLES))
):
    return await run_list_process_finances(company_id, process_id, client_id, status, user)


@router.get("/finance/processes/{finance_id}")
async def get_process_finance_by_id(
    finance_id: str,
    user: dict = Depends(require_roles(FINANCE_READ_ROLES))
):
    return await run_get_process_finance_by_id(finance_id, user)


@router.put("/finance/processes/{finance_id}")
async def update_process_finance(
    finance_id: str,
    body: ProcessFinanceUpdate,
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO, UserRole.DIRETOR]))
):
    return await run_update_process_finance(finance_id, body, user)


@router.patch("/finance/processes/{finance_id}/status")
async def update_process_finance_status(
    finance_id: str,
    status: str = Query(..., description="Novo status: pending|invoiced|paid|cancelled"),
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO, UserRole.DIRETOR]))
):
    return await run_update_process_finance_status(finance_id, status, user)


@router.delete("/finance/processes/{finance_id}")
async def delete_process_finance(
    finance_id: str,
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
):
    return await run_delete_process_finance(finance_id, user)

"""
====================================================================
GDPR ROUTES — thin FastAPI stubs
====================================================================
Logic in services/gdpr_api_*.py.
Do **not** overwrite services/gdpr.py (core compliance service).
====================================================================
"""
from typing import Optional

from fastapi import APIRouter, Depends, Query

from models.auth import UserRole
from services.auth import require_roles
from services.gdpr_api_models import AnonymizeRequest, BatchAnonymizeRequest
from services.gdpr_api_read import (
    run_get_statistics,
    run_get_eligible_processes,
    run_get_audit_log,
    run_get_gdpr_config,
)
from services.gdpr_api_mutate import (
    run_anonymize_single,
    run_anonymize_batch,
    run_export_data,
)

router = APIRouter(prefix="/gdpr", tags=["GDPR Compliance"])


@router.get("/statistics")
async def get_statistics(
    current_user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
):
    """Obtém estatísticas de conformidade GDPR."""
    return await run_get_statistics()


@router.get("/eligible")
async def get_eligible_processes(
    retention_days: int = Query(default=None, description="Dias de retenção"),
    limit: int = Query(default=50, le=200),
    current_user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
):
    """Lista processos elegíveis para anonimização."""
    return await run_get_eligible_processes(retention_days, limit)


@router.post("/anonymize")
async def anonymize_single(
    request: AnonymizeRequest,
    current_user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
):
    """Anonimiza dados de um processo ou utilizador específico."""
    return await run_anonymize_single(request, current_user)


@router.post("/batch")
async def anonymize_batch(
    request: BatchAnonymizeRequest,
    current_user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
):
    """Executa anonimização em lote."""
    return await run_anonymize_batch(request, current_user)


@router.get("/export/{process_id}")
async def export_data(
    process_id: str,
    current_user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
):
    """Exporta dados pessoais de um processo (RGPD Art. 20)."""
    return await run_export_data(process_id)


@router.get("/audit")
async def get_audit_log(
    days: int = Query(default=30, le=365),
    action: Optional[str] = Query(default=None),
    limit: int = Query(default=100, le=500),
    current_user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
):
    """Consulta o log de auditoria GDPR."""
    return await run_get_audit_log(days, action, limit)


@router.get("/config")
async def get_gdpr_config(
    current_user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
):
    """Obtém configuração actual do GDPR."""
    return await run_get_gdpr_config()

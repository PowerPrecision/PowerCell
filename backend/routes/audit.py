"""
====================================================================
Rotas de Auditoria — thin FastAPI stubs
====================================================================
Logic in services/audit_api_*.py.
Do **not** overwrite audit_trail_service.py.
====================================================================
"""
from fastapi import APIRouter, Depends, Query, Request

from models.auth import UserRole
from services.auth import require_roles
from services.audit_api_trail import (
    run_list_audit_trail,
    run_audit_statistics,
)
from services.audit_api_export import run_export_audit
from services.audit_api_cleanup import run_trigger_cleanup

router = APIRouter(prefix="/audit", tags=["Audit Trail"])


@router.get("/trail")
async def list_audit_trail(
    request: Request,
    process_id: str = Query(None, description="Filtrar por ID do processo"),
    user_id: str = Query(None, description="Filtrar por ID do utilizador"),
    action_type: str = Query(None, description="Filtrar por tipo de acção (texto parcial)"),
    source: str = Query(None, description="Filtrar por origem (web, api, ai_automation, email)"),
    date_from: str = Query(None, description="Data inicial (ISO 8601)"),
    date_to: str = Query(None, description="Data final (ISO 8601)"),
    ai_suggested: bool = Query(None, description="Filtrar apenas sugestões de IA"),
    page: int = Query(1, ge=1, description="Número da página"),
    page_size: int = Query(50, ge=1, le=200, description="Itens por página"),
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO])),
):
    """Listar registos de auditoria com paginação e filtros."""
    return await run_list_audit_trail(
        process_id=process_id,
        user_id=user_id,
        action_type=action_type,
        source=source,
        date_from=date_from,
        date_to=date_to,
        ai_suggested=ai_suggested,
        page=page,
        page_size=page_size,
    )


@router.get("/stats")
async def audit_statistics(
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO])),
):
    """Obter estatísticas de auditoria para o dashboard."""
    return await run_audit_statistics()


@router.get("/export")
async def export_audit(
    process_id: str = Query(None, description="Filtrar por ID do processo"),
    user_id: str = Query(None, description="Filtrar por ID do utilizador"),
    source: str = Query(None, description="Filtrar por origem"),
    date_from: str = Query(None, description="Data inicial (ISO 8601)"),
    date_to: str = Query(None, description="Data final (ISO 8601)"),
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO])),
):
    """Exportar registos de auditoria como ficheiro CSV."""
    return await run_export_audit(
        process_id=process_id,
        user_id=user_id,
        source=source,
        date_from=date_from,
        date_to=date_to,
    )


@router.post("/cleanup")
async def trigger_cleanup(
    days: int = Query(None, description="Dias de retenção (usa config se omitido)"),
    user: dict = Depends(require_roles([UserRole.ADMIN])),
):
    """Limpar registos de auditoria antigos (apenas admin)."""
    return await run_trigger_cleanup(days, user)

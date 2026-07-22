"""
====================================================================
ROTAS DE ADMIN DO PORTAL — IMPERSONATION — thin FastAPI stubs
====================================================================
Logic in services/portal_admin_api_*.py.
====================================================================
"""
from fastapi import APIRouter, Depends, Request

from services.auth import require_staff
from services.portal_admin_api_impersonate import run_impersonate_client_portal

router = APIRouter(prefix="/portal", tags=["Portal Admin (Impersonation)"])


@router.post("/impersonate/{process_id}")
async def impersonate_client_portal(
    process_id: str,
    request: Request,
    user: dict = Depends(require_staff()),
):
    """Gera um link do Portal do Cliente autenticado para staff (impersonation)."""
    return await run_impersonate_client_portal(process_id, request, user)

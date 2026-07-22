"""
Rotas para Gestão de Visitas (Quadro de Visitas) — thin FastAPI stubs.

Logic in services/visit_*.py (do **not** collide with portal_client_visits.py).

ENDPOINTS:
- GET  /visits           → Lista visitas (filtros: status, consultor, imóvel, data, process_id)
- POST /visits           → Criar nova visita (com scraper opcional)
- GET  /visits/kanban    → Visitas organizadas por estado
- GET  /visits/{id}      → Detalhe de visita
- PATCH /visits/{id}     → Actualizar visita (status, data, notas) + sync calendário/portal
- DELETE /visits/{id}    → Cancelar visita (soft delete → status cancelada)
"""
from typing import Optional

from fastapi import APIRouter, Depends, Query

from services.auth import get_current_user
from services.visit_list_create import run_list_visits, run_create_visit
from services.visit_kanban_get import run_get_visits_kanban, run_get_visit
from services.visit_update_cancel import run_update_visit, run_cancel_visit

router = APIRouter(prefix="/visits", tags=["Visits"])


@router.get("")
async def list_visits(
    status: Optional[str] = Query(None, description="Filtrar por estado: agendada, concluida, cancelada"),
    consultor_id: Optional[str] = Query(None, description="Filtrar por consultor"),
    property_id: Optional[str] = Query(None, description="Filtrar por imóvel"),
    client_id: Optional[str] = Query(None, description="Filtrar por cliente (process_id)"),
    process_id: Optional[str] = Query(None, description="Filtrar por process_id"),
    date_from: Optional[str] = Query(None, description="Data início (ISO)"),
    date_to: Optional[str] = Query(None, description="Data fim (ISO)"),
    user: dict = Depends(get_current_user)
):
    return await run_list_visits(
        user,
        status=status,
        consultor_id=consultor_id,
        property_id=property_id,
        client_id=client_id,
        process_id=process_id,
        date_from=date_from,
        date_to=date_to,
    )


@router.post("")
async def create_visit(
    data: dict,
    user: dict = Depends(get_current_user)
):
    return await run_create_visit(data, user)


# Static path before /{visit_id}
@router.get("/kanban")
async def get_visits_kanban(
    consultor_id: Optional[str] = Query(None),
    user: dict = Depends(get_current_user)
):
    return await run_get_visits_kanban(user, consultor_id=consultor_id)


@router.get("/{visit_id}")
async def get_visit(
    visit_id: str,
    user: dict = Depends(get_current_user)
):
    return await run_get_visit(visit_id, user)


@router.patch("/{visit_id}")
async def update_visit(
    visit_id: str,
    data: dict,
    user: dict = Depends(get_current_user)
):
    return await run_update_visit(visit_id, data, user)


@router.delete("/{visit_id}")
async def cancel_visit(
    visit_id: str,
    user: dict = Depends(get_current_user)
):
    return await run_cancel_visit(visit_id, user)

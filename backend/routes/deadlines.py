"""
====================================================================
DEADLINES ROUTES — thin FastAPI stubs
====================================================================
Logic in services/deadlines_api_*.py.
Keep static /my-deadlines, /calendar and /dashboard-calendar before /{deadline_id}.
====================================================================
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, Query, Request

from models.auth import UserRole
from models.deadline import DeadlineCreate, DeadlineUpdate, DeadlineResponse
from services.auth import get_current_user, require_roles
from services.deadlines_api_crud import (
    run_create_deadline,
    run_update_deadline,
    run_delete_deadline,
)
from services.deadlines_api_list import (
    run_get_deadlines,
    run_get_my_deadlines,
)
from services.deadlines_api_calendar import run_get_calendar_deadlines
from services.dashboard_calendar import run_dashboard_calendar

router = APIRouter(prefix="/deadlines", tags=["Deadlines"])


@router.post("", response_model=DeadlineResponse)
async def create_deadline(
    data: DeadlineCreate,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Criar um novo evento/prazo no calendário."""
    return await run_create_deadline(data, user, request)


@router.get("", response_model=List[DeadlineResponse])
async def get_deadlines(
    request: Request,
    process_id: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    """Obter prazos/eventos do utilizador (âmbito pelo cargo EFECTIVO)."""
    return await run_get_deadlines(process_id, user, request)


@router.get("/my-deadlines", response_model=List[DeadlineResponse])
async def get_my_deadlines(
    request: Request, user: dict = Depends(get_current_user),
):
    """Obter APENAS prazos onde o utilizador tem acesso ao processo."""
    return await run_get_my_deadlines(user, request)


@router.get("/calendar")
async def get_calendar_deadlines(
    request: Request,
    consultor_id: Optional[str] = None,
    mediador_id: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    """Obter eventos para o calendário (scoped por cargo efectivo e empresa)."""
    return await run_get_calendar_deadlines(
        consultor_id, mediador_id, user, request,
    )


@router.get("/dashboard-calendar")
async def get_dashboard_calendar(
    request: Request, month: Optional[str] = Query(None),
    user: dict = Depends(get_current_user),
):
    """Marcações, escrituras, CPCVs e ausências de um mês (AAAA-MM)."""
    return await run_dashboard_calendar(user, request, month)


@router.put("/{deadline_id}", response_model=DeadlineResponse)
async def update_deadline(
    deadline_id: str,
    data: DeadlineUpdate,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Atualiza um prazo existente.

    O `request` é obrigatório: só ele traz o `X-Active-Role` de que a
    guarda de posse precisa (o papel EFECTIVO, nunca o do JWT).
    """
    return await run_update_deadline(deadline_id, data, user, request)


@router.delete("/{deadline_id}")
async def delete_deadline(
    deadline_id: str,
    request: Request,
    user: dict = Depends(
        require_roles([
            UserRole.CONSULTOR, UserRole.INTERMEDIARIO,
            UserRole.ADMIN, UserRole.CEO, UserRole.DIRETOR,
            UserRole.ADMINISTRATIVO,
        ])
    ),
):
    """Elimina um prazo existente (com guarda de posse — ver o serviço)."""
    return await run_delete_deadline(deadline_id, user, request)

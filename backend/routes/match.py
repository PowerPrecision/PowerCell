"""
====================================================================
MATCH ROUTES — thin FastAPI stubs
====================================================================
Logic in services/match_api_*.py.
Do **not** overwrite services/client_match.py (core matcher).
Keep /process/{id} before /client/... /property/... /lead/...
====================================================================
"""
from fastapi import APIRouter, Depends

from services.auth import get_current_user
from services.match_api_smart import run_smart_match_for_process
from services.match_api_client import (
    run_get_all_matches_for_client,
    run_get_matching_properties,
    run_get_matching_leads,
    run_get_client_match_summary,
)
from services.match_api_property import (
    run_get_matching_clients_for_property,
    run_get_matching_clients_for_lead,
)

router = APIRouter(prefix="/match", tags=["Client-Property Match"])


@router.get("/process/{process_id}")
async def smart_match_for_process(
    process_id: str,
    user: dict = Depends(get_current_user)
):
    """Smart Match: imóveis angariados compatíveis com critérios de compra."""
    return await run_smart_match_for_process(process_id, user)


@router.get("/client/{process_id}/all")
async def get_all_matches_for_client(
    process_id: str,
    user: dict = Depends(get_current_user)
):
    """Encontrar TODOS os imóveis compatíveis (angariados + leads) para um cliente."""
    return await run_get_all_matches_for_client(process_id, user)


@router.get("/client/{process_id}/properties")
async def get_matching_properties(
    process_id: str,
    user: dict = Depends(get_current_user)
):
    """Encontrar imóveis ANGARIADOS compatíveis com o perfil do cliente."""
    return await run_get_matching_properties(process_id, user)


@router.get("/client/{process_id}/leads")
async def get_matching_leads(
    process_id: str,
    user: dict = Depends(get_current_user)
):
    """Encontrar leads de imóveis compatíveis com o perfil do cliente."""
    return await run_get_matching_leads(process_id, user)


@router.get("/property/{property_id}/clients")
async def get_matching_clients_for_property_route(
    property_id: str,
    user: dict = Depends(get_current_user)
):
    """Encontrar clientes que podem ter interesse num imóvel ANGARIADO."""
    return await run_get_matching_clients_for_property(property_id, user)


@router.get("/lead/{lead_id}/clients")
async def get_matching_clients(
    lead_id: str,
    user: dict = Depends(get_current_user)
):
    """Encontrar clientes que podem ter interesse num imóvel específico (lead)."""
    return await run_get_matching_clients_for_lead(lead_id, user)


@router.get("/client/{process_id}/summary")
async def get_client_match_summary(
    process_id: str,
    user: dict = Depends(get_current_user)
):
    """Obter resumo de correspondências para um cliente."""
    return await run_get_client_match_summary(process_id, user)

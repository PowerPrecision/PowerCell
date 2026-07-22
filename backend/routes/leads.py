"""
Rotas para gestão de Leads de Imóveis — thin FastAPI stubs.

Logic in services/lead_*.py.
"""
from typing import List, Optional, Dict

from fastapi import APIRouter, Depends

from models.lead import (
    PropertyLead, PropertyLeadCreate, PropertyLeadUpdate, LeadStatus,
)
from services.auth import get_current_user

from services.lead_list import (
    run_list_leads,
    run_get_leads_by_status,
    run_get_consultores_for_filter,
)
from services.lead_extract import (
    run_extract_url_data,
    run_extract_html_data,
    run_create_lead_from_url,
)
from services.lead_crud import (
    run_create_lead,
    run_update_lead,
    run_update_lead_status,
    run_refresh_lead_price,
    run_delete_lead,
)
from services.lead_associate import run_associate_client

router = APIRouter(prefix="/leads", tags=["Property Leads"])


# Static paths before /{lead_id}
@router.get("", response_model=List[PropertyLead])
async def list_leads(
    status: Optional[LeadStatus] = None,
    client_id: Optional[str] = None,
    consultor_id: Optional[str] = None,
    user: dict = Depends(get_current_user)
):
    return await run_list_leads(
        user, status=status, client_id=client_id, consultor_id=consultor_id,
    )


@router.get("/by-status")
async def get_leads_by_status(
    consultor_id: Optional[str] = None,
    status_filter: Optional[str] = None,
    user: dict = Depends(get_current_user)
):
    return await run_get_leads_by_status(
        user, consultor_id=consultor_id, status_filter=status_filter,
    )


@router.get("/consultores")
async def get_consultores_for_filter(user: dict = Depends(get_current_user)):
    return await run_get_consultores_for_filter(user)


@router.post("/extract-url")
async def extract_url_data(
    payload: Dict[str, str],
    user: dict = Depends(get_current_user)
):
    return await run_extract_url_data(payload, user)


@router.post("/extract-html")
async def extract_html_data(
    payload: Dict[str, str],
    user: dict = Depends(get_current_user)
):
    return await run_extract_html_data(payload, user)


@router.post("/from-url")
async def create_lead_from_url(
    payload: Dict[str, str],
    user: dict = Depends(get_current_user)
):
    return await run_create_lead_from_url(payload, user)


@router.post("", response_model=PropertyLead)
async def create_lead(
    lead_data: PropertyLeadCreate,
    user: dict = Depends(get_current_user)
):
    return await run_create_lead(lead_data, user)


@router.patch("/{lead_id}", response_model=PropertyLead)
async def update_lead(
    lead_id: str,
    update_data: PropertyLeadUpdate,
    user: dict = Depends(get_current_user)
):
    return await run_update_lead(lead_id, update_data, user)


@router.patch("/{lead_id}/status")
async def update_lead_status(
    lead_id: str,
    status: str,
    user: dict = Depends(get_current_user)
):
    return await run_update_lead_status(lead_id, status, user)


@router.post("/{lead_id}/refresh")
async def refresh_lead_price(
    lead_id: str,
    user: dict = Depends(get_current_user)
):
    return await run_refresh_lead_price(lead_id, user)


@router.delete("/{lead_id}")
async def delete_lead(lead_id: str, user: dict = Depends(get_current_user)):
    return await run_delete_lead(lead_id, user)


@router.post("/{lead_id}/associate-client")
async def associate_client(
    lead_id: str,
    client_id: str,
    user: dict = Depends(get_current_user)
):
    return await run_associate_client(lead_id, client_id, user)

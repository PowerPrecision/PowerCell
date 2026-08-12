"""
CLIENT PORTAL - Routes
======================
Thin FastAPI stubs — logic lives in services/portal_*.py

SEGURANÇA:
- Endpoints de cliente usam get_current_client (role="client_portal")
- NUNCA devolvem dados sensíveis (notas internas, NIF, dados financeiros)
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Request
from fastapi.responses import JSONResponse

from services.portal_security import get_current_client
from services.auth import get_current_user, require_staff

from services.portal_doc_categories import (
    DOCUMENT_CATEGORY_MAP,
    PORTAL_HIDDEN_CATEGORIES,
    DEFAULT_PENDING_CATEGORIES,
)
from services.portal_assigned_users import get_all_assigned_user_ids as _get_all_assigned_user_ids
from services.portal_profile import (
    ClientProfileUpdate,
    run_get_client_profile,
    run_update_client_profile,
)
from services.portal_auth import (
    PortalLoginRequest,
    run_portal_login,
    run_verify_portal_login,
    run_resolve_portal_token,
    run_impersonate_client_portal,
    run_authenticate_portal,
)
from services.portal_status import run_get_portal_status
from services.portal_upload_ops import (
    run_generate_portal_upload_url,
    run_confirm_portal_upload,
    run_get_portal_download_url,
)
from services.portal_client_messages import (
    run_get_unread_messages_count,
    run_get_portal_messages,
    run_send_portal_message,
)
from services.portal_gov_fetch import (
    run_check_scraper_status,
    run_fetch_financas_documents,
    run_fetch_seguranca_social_documents,
    run_submit_mfa_code,
    run_get_scraper_job_status,
)
from services.portal_recommendations import (
    run_create_recommendations,
    run_get_recommendations_for_client,
)
from services.portal_client_visits import (
    run_request_portal_visit,
    run_get_portal_visits,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/portal", tags=["Client Portal"])


@router.post("/auth/login")
async def portal_login(data: PortalLoginRequest):
    return await run_portal_login(data)


@router.post("/{client_id}/verify")
async def verify_portal_login(client_id: str, data: dict):
    return await run_verify_portal_login(client_id, data)


@router.get("/resolve/{short_id}")
async def resolve_portal_token(short_id: str):
    return await run_resolve_portal_token(short_id)


@router.get("/impersonate/{process_id}")
async def impersonate_client_portal(
    process_id: str,
    request: Request,
    user: dict = Depends(require_staff()),
):
    return await run_impersonate_client_portal(process_id, request, user)


@router.post("/authenticate")
async def authenticate_portal(client_data: dict = Depends(get_current_client)):
    return await run_authenticate_portal(client_data)


@router.get("/me")
async def get_client_profile(client_data: dict = Depends(get_current_client)):
    return await run_get_client_profile(client_data)


@router.put("/me")
async def update_client_profile(
    data: ClientProfileUpdate,
    client_data: dict = Depends(get_current_client),
):
    return await run_update_client_profile(data, client_data)


@router.get("/status")
async def get_portal_status(client_data: dict = Depends(get_current_client)):
    return await run_get_portal_status(client_data)


@router.post("/upload-url")
async def generate_portal_upload_url(
    data: dict,
    client_data: dict = Depends(get_current_client),
):
    return await run_generate_portal_upload_url(data, client_data)


@router.post("/confirm-upload")
async def confirm_portal_upload(
    data: dict,
    client_data: dict = Depends(get_current_client),
):
    return await run_confirm_portal_upload(data, client_data)


@router.get("/download-url")
async def get_portal_download_url(
    file_key: str,
    client_data: dict = Depends(get_current_client),
):
    return await run_get_portal_download_url(file_key, client_data)


@router.get("/messages/unread")
async def get_unread_messages_count(client_data: dict = Depends(get_current_client)):
    return await run_get_unread_messages_count(client_data)


@router.get("/messages")
async def get_portal_messages(client_data: dict = Depends(get_current_client)):
    return await run_get_portal_messages(client_data)


@router.post("/messages")
async def send_portal_message(
    data: dict,
    client_data: dict = Depends(get_current_client),
):
    return await run_send_portal_message(data, client_data)


@router.get("/scraper-status")
async def check_scraper_status(client_data: dict = Depends(get_current_client)):
    return await run_check_scraper_status(client_data)


@router.post("/fetch-financas")
async def fetch_financas_documents(
    data: dict,
    background_tasks: BackgroundTasks,
    client_data: dict = Depends(get_current_client),
):
    return await run_fetch_financas_documents(data, background_tasks, client_data)


@router.post("/fetch-seguranca-social")
async def fetch_seguranca_social_documents(
    data: dict,
    background_tasks: BackgroundTasks,
    client_data: dict = Depends(get_current_client),
):
    return await run_fetch_seguranca_social_documents(data, background_tasks, client_data)


@router.post("/submit-mfa")
async def submit_mfa_code(
    data: dict,
    client_data: dict = Depends(get_current_client),
):
    return await run_submit_mfa_code(data, client_data)


@router.get("/scraper-job/{job_id}")
async def get_scraper_job_status(job_id: str):
    return await run_get_scraper_job_status(job_id)


@router.post("/recommendations")
async def create_recommendations(
    data: dict,
    user: dict = Depends(get_current_user),
):
    return await run_create_recommendations(data, user)


@router.get("/recommendations")
async def get_recommendations_for_client(
    client_data: dict = Depends(get_current_client),
):
    return await run_get_recommendations_for_client(client_data)


@router.post("/visits/request")
async def request_portal_visit(
    data: dict,
    background_tasks: BackgroundTasks,
    client_data: dict = Depends(get_current_client),
):
    return await run_request_portal_visit(data, background_tasks, client_data)


@router.get("/visits")
async def get_portal_visits(client_data: dict = Depends(get_current_client)):
    return await run_get_portal_visits(client_data)


@router.get("/events")
async def get_portal_events(client_data: dict = Depends(get_current_client)):
    """PACOTE DH — Eventos/prazos visíveis ao cliente no Portal."""
    from services.portal_events import run_get_portal_events
    return await run_get_portal_events(client_data)

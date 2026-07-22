"""
Rotas — configuração de email partilhado por role (thin stubs).

Logic in services/shared_email_*.py.

NOTA: /google/callback DEVE ficar antes de /{role} para evitar que
FastAPI faça match de "google" ao path parameter {role}.
"""
from typing import Optional

from fastapi import APIRouter, Depends, Request, Query

from services.auth import get_current_user
from models.shared_email_config import (
    SharedEmailConfigCreate,
    SharedEmailConfigResponse,
    SharedEmailConfigListResponse,
    SharedEmailOAuthLoginResponse,
)
from services.shared_email_crud import (
    run_list_shared_email_configs,
    run_get_shared_email_config,
    run_upsert_shared_email_config,
    run_delete_shared_email_config,
)
from services.shared_email_google import (
    run_shared_email_google_callback,
    run_shared_email_google_login,
    run_shared_email_google_disconnect,
)
from services.shared_email_sync import run_shared_email_manual_sync

router = APIRouter(prefix="/admin/shared-email", tags=["Shared Email Config"])


@router.get("", response_model=SharedEmailConfigListResponse)
async def list_shared_email_configs(
    current_user: dict = Depends(get_current_user),
):
    return await run_list_shared_email_configs(current_user)


# Static /google/callback BEFORE /{role}
@router.get("/google/callback")
async def shared_email_google_callback(
    request: Request,
    code: str,
    state: Optional[str] = None,
    error: Optional[str] = None,
    error_description: Optional[str] = None,
):
    return await run_shared_email_google_callback(
        request, code, state=state, error=error, error_description=error_description
    )


@router.get("/{role}", response_model=SharedEmailConfigResponse)
async def get_shared_email_config(
    role: str,
    current_user: dict = Depends(get_current_user),
):
    return await run_get_shared_email_config(role, current_user)


@router.put("/{role}", response_model=SharedEmailConfigResponse)
async def upsert_shared_email_config(
    role: str,
    payload: SharedEmailConfigCreate,
    current_user: dict = Depends(get_current_user),
):
    return await run_upsert_shared_email_config(role, payload, current_user)


@router.delete("/{role}")
async def delete_shared_email_config(
    role: str,
    current_user: dict = Depends(get_current_user),
):
    return await run_delete_shared_email_config(role, current_user)


@router.get("/{role}/google/login", response_model=SharedEmailOAuthLoginResponse)
async def shared_email_google_login(
    role: str,
    request: Request,
    current_user: dict = Depends(get_current_user),
    email_address: Optional[str] = Query(None),
):
    return await run_shared_email_google_login(
        role, request, current_user, email_address=email_address
    )


@router.delete("/{role}/google")
async def shared_email_google_disconnect(
    role: str,
    current_user: dict = Depends(get_current_user),
):
    return await run_shared_email_google_disconnect(role, current_user)


@router.post("/{role}/sync")
async def shared_email_manual_sync(
    role: str,
    current_user: dict = Depends(get_current_user),
    days: int = Query(3, ge=1, le=30),
):
    return await run_shared_email_manual_sync(role, current_user, days=days)

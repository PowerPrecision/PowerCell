"""
Rotas Google OAuth 2.0 (Gmail) — thin FastAPI stubs.

Logic in services/google_auth_*.py (do **not** overwrite gmail_oauth.py /
gmail_api_service.py).
"""
from typing import Optional

from fastapi import APIRouter, Depends, Request, Query

from services.auth import get_current_user
from services.google_auth_oauth import (
    run_google_login,
    run_google_callback,
)
from services.google_auth_status import (
    run_google_oauth_status,
    run_google_oauth_disconnect,
)

router = APIRouter(prefix="/auth/google", tags=["Google OAuth"])


@router.get("/login")
async def google_login(
    request: Request,
    token: Optional[str] = Query(None, description="JWT token (fallback when Authorization header is unavailable)"),
    email_address: Optional[str] = None,
):
    return await run_google_login(request, token=token, email_address=email_address)


@router.get("/callback")
async def google_callback(
    request: Request,
    code: str,
    state: Optional[str] = None,
    error: Optional[str] = None,
    error_description: Optional[str] = None,
):
    return await run_google_callback(
        request, code, state=state, error=error, error_description=error_description
    )


@router.get("/status")
async def google_oauth_status(
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    return await run_google_oauth_status(request, current_user)


@router.delete("/disconnect")
async def google_oauth_disconnect(
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    return await run_google_oauth_disconnect(request, current_user)

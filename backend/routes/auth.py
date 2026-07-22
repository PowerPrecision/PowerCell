"""
Rotas de autenticação — thin FastAPI stubs.

Logic in services/auth_*_handlers.py.
Do **not** overwrite existing `services/auth.py` (hashing, JWT, get_current_user).

Preserves:
- deprecated POST /login (410)
- POST /login-v2 (refresh tokens)
- register/request Response params (cookie-ready signatures)
"""
from fastapi import APIRouter, Depends, Request, Response

from models.auth import UserRegister, UserLogin, TokenResponse
from services.auth import get_current_user
from middleware.rate_limit import limiter

from services.auth_register_handlers import run_register
from services.auth_login_handlers import run_login, run_login_v2
from services.auth_profile_handlers import (
    run_get_me,
    run_update_preferences,
    run_get_preferences,
    run_update_profile,
)
from services.auth_password_handlers import (
    run_change_password,
    run_validate_password,
)
from services.auth_sessions_handlers import (
    run_refresh_tokens,
    run_logout,
    run_list_sessions,
    run_revoke_session,
)

router = APIRouter(prefix="/auth", tags=["Auth"])

# Re-export for back-compat (e.g. routes.storage imports get_current_user from here)
__all__ = ["router", "get_current_user"]


@router.post("/register", response_model=TokenResponse)
@limiter.limit("3/hour")
async def register(request: Request, response: Response, data: UserRegister):
    return await run_register(request, response, data)


@router.post("/login", deprecated=True)
@limiter.limit("10/minute")
async def login(request: Request, data: UserLogin, response: Response):
    return await run_login(request, data, response)


@router.get("/me")
async def get_me(request: Request, user: dict = Depends(get_current_user)):
    return await run_get_me(request, user)


@router.put("/preferences")
async def update_preferences(
    data: dict,
    user: dict = Depends(get_current_user)
):
    return await run_update_preferences(data, user)


@router.get("/preferences")
async def get_preferences(user: dict = Depends(get_current_user)):
    return await run_get_preferences(user)


@router.put("/profile")
async def update_profile(
    data: dict,
    request: Request,
    user: dict = Depends(get_current_user)
):
    return await run_update_profile(data, request, user)


@router.post("/change-password")
async def change_password(
    data: dict,
    user: dict = Depends(get_current_user)
):
    return await run_change_password(data, user)


# ====================================================================
# REFRESH TOKENS ENDPOINTS
# ====================================================================

@router.post("/login-v2")
@limiter.limit("10/minute")
async def login_v2(request: Request, data: UserLogin, response: Response):
    return await run_login_v2(request, data, response)


@router.post("/refresh")
async def refresh_tokens(request: Request, data: dict):
    return await run_refresh_tokens(request, data)


@router.post("/logout")
async def logout(data: dict, user: dict = Depends(get_current_user)):
    return await run_logout(data, user)


@router.get("/sessions")
async def list_sessions(user: dict = Depends(get_current_user)):
    return await run_list_sessions(user)


@router.delete("/sessions/{session_id}")
async def revoke_session(session_id: str, user: dict = Depends(get_current_user)):
    return await run_revoke_session(session_id, user)


@router.post("/validate-password")
async def validate_password_endpoint(data: dict):
    return await run_validate_password(data)

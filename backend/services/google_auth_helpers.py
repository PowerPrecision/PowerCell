"""Shared helpers for Google OAuth user Gmail routes.

Extraído de `routes/google_auth.py`. Prefer `google_auth_*` — do **not**
overwrite existing `gmail_oauth.py` / `gmail_api_service.py`.
"""
from __future__ import annotations

import logging
from typing import Optional

import jwt
from fastapi import HTTPException, Request

from database import db
from config import JWT_SECRET, JWT_ALGORITHM

logger = logging.getLogger(__name__)


def get_google_config() -> dict:
    """Valida e devolve a config do Google OAuth. Levanta HTTPException se não configurado."""
    from config import GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REDIRECT_URI, GOOGLE_GMAIL_SCOPES

    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        raise HTTPException(
            status_code=503,
            detail=(
                "Google OAuth não configurado. Defina GOOGLE_CLIENT_ID e "
                "GOOGLE_CLIENT_SECRET nas variáveis de ambiente."
            ),
        )

    return {
        "client_id": GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "scopes": GOOGLE_GMAIL_SCOPES,
    }


_get_google_config = get_google_config


def build_redirect_uri(request: Request, configured_uri: str) -> str:
    """
    Constrói a redirect URI.
    Se GOOGLE_REDIRECT_URI está definido, usa-o (prioridade).
    Caso contrário, infere a partir do Host header do request.
    """
    if configured_uri:
        return configured_uri

    # Inferir a partir do request
    scheme = request.headers.get("x-forwarded-proto", "https")
    host = request.headers.get("host", "localhost:8000")
    base_url = f"{scheme}://{host}"
    return f"{base_url}/api/auth/google/callback"


_build_redirect_uri = build_redirect_uri


async def resolve_user(request: Request, token: Optional[str] = None) -> dict:
    """Resolve the authenticated user from the Authorization header or a ?token= query param.

    Primary: ``Authorization: Bearer <jwt>`` header (standard API calls via axios/fetch).
    Fallback: ``?token=<jwt>`` query parameter (direct browser navigation).

    The fallback exists because ``window.location.href`` does NOT send headers,
    which causes the default ``get_current_user`` dependency to return 401 and
    the SPA to redirect to the login page — a frustrating loop for the user.
    """
    # --- 1. Try the standard Authorization header ---
    auth_header = request.headers.get("authorization")
    if auth_header and auth_header.lower().startswith("bearer "):
        jwt_token = auth_header[7:].strip()
        try:
            payload = jwt.decode(jwt_token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
            user = await db.users.find_one({"id": payload["sub"]}, {"_id": 0})
            if user and user.get("is_active", True):
                return user
        except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
            pass  # fall through to ?token=

    # --- 2. Fallback: ?token= query parameter ---
    if token:
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
            user = await db.users.find_one({"id": payload["sub"]}, {"_id": 0})
            if not user or not user.get("is_active", True):
                raise HTTPException(status_code=401, detail="Token inválido ou conta desativada")
            logger.info(f"[Google OAuth] User resolved via ?token= fallback: {user['id']}")
            return user
        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="Token expirado")
        except jwt.InvalidTokenError:
            raise HTTPException(status_code=401, detail="Token inválido")

    raise HTTPException(
        status_code=401,
        detail="Autenticação necessária. Envie o token JWT via Authorization header ou query param ?token=...",
    )


_resolve_user = resolve_user

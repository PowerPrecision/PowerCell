"""Shared helpers for admin shared-email routes.

Extraído de `routes/shared_email.py`. Prefer `shared_email_*` (no prior collision).
"""
from __future__ import annotations

from fastapi import HTTPException, Request

# Roles permitidos para email partilhado
ALLOWED_ROLES = ["indexacao", "suporte", "comercial", "admin"]


def require_admin(current_user: dict) -> None:
    """Verifica se o cargo efetivo (UCR) ou, em fallback, o JWT, é admin/CEO."""
    from models.auth import UserRole
    role = authorization_role_from_user(current_user)
    if role not in (UserRole.ADMIN, UserRole.CEO):
        raise HTTPException(status_code=403, detail="Acesso restrito a administradores")


def authorization_role_from_user(current_user: dict) -> str:
    """Prefere ``effective_role`` já resolvido; fallback JWT primário."""
    role = (current_user.get("effective_role") or current_user.get("role") or "")
    if role == "__all_roles__":
        role = current_user.get("role") or ""
    return (role or "").strip().lower()


# Alias matching original private name
_require_admin = require_admin


def get_google_config() -> dict:
    """Valida e devolve a config do Google OAuth."""
    from config import GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REDIRECT_URI, GOOGLE_GMAIL_SCOPES

    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        raise HTTPException(
            status_code=503,
            detail="Google OAuth não configurado. Defina GOOGLE_CLIENT_ID e GOOGLE_CLIENT_SECRET.",
        )

    return {
        "client_id": GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "scopes": GOOGLE_GMAIL_SCOPES,
    }


_get_google_config = get_google_config


def build_redirect_uri(request: Request) -> str:
    """Constrói a redirect URI para o callback do shared email.

    IMPORTANTE: Ignora o GOOGLE_REDIRECT_URI genérico porque esse aponta
    para /api/auth/google/callback (autenticação de utilizadores).
    O shared email tem o seu próprio callback dedicado para garantir que
    os tokens são guardados na config partilhada (shared_role_email_configs)
    e não no perfil individual do utilizador.
    """
    scheme = request.headers.get("x-forwarded-proto", "https")
    host = request.headers.get("host", "localhost:8000")
    return f"{scheme}://{host}/api/admin/shared-email/google/callback"


_build_redirect_uri = build_redirect_uri

"""Auth sessions / refresh-token orchestration — extracted from `routes/auth.py`.

Refresh, logout, list/revoke sessions.
Do **not** overwrite existing `services/auth.py`.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException

from database import db
from utils.input_sanitization import sanitize_string
from services.refresh_token_service import (
    create_access_token,
    rotate_refresh_token,
    revoke_refresh_token,
    revoke_all_user_tokens,
    get_active_sessions,
    ACCESS_TOKEN_EXPIRE_MINUTES,
)


async def run_refresh_tokens(request, data: dict):
    """
    Renova tokens usando refresh token.
    Implementa rotação segura: token antigo é invalidado, novo é criado.
    Preserva metadados de impersonate do token anterior, se existirem.
    """
    import jwt as pyjwt

    refresh_token = data.get("refresh_token")
    if not refresh_token:
        raise HTTPException(status_code=400, detail="refresh_token é obrigatório")

    device_info = sanitize_string(request.headers.get("User-Agent", ""), max_length=200)
    ip_address = sanitize_string(request.headers.get("X-Forwarded-For", request.client.host if request.client else ""), max_length=45)

    result = await rotate_refresh_token(
        refresh_token,
        device_info=device_info,
        ip_address=ip_address
    )

    if not result:
        raise HTTPException(status_code=401, detail="Refresh token inválido ou expirado")

    _, new_refresh_token, user = result

    # Preservar metadados de impersonate do token anterior (se existirem)
    additional_data = None
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        old_token = auth_header[7:]
        try:
            old_payload = pyjwt.decode(old_token, options={"verify_signature": False, "verify_exp": False})
            if old_payload.get("is_impersonated"):
                additional_data = {
                    "impersonated_by": old_payload.get("impersonated_by"),
                    "impersonated_by_name": old_payload.get("impersonated_by_name"),
                    "is_impersonated": True,
                }
        except Exception:
            pass  # Token ilegível — continuar sem metadados de impersonate

    # Criar novo access token
    access_token = create_access_token(
        user["id"],
        user["email"],
        user["role"],
        additional_data=additional_data
    )

    return {
        "access_token": access_token,
        "refresh_token": new_refresh_token,
        "token_type": "bearer",
        "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    }


async def run_logout(data: dict, user: dict):
    """
    Logout - revoga refresh token.
    Se refresh_token não fornecido, revoga todos os tokens do utilizador.
    """
    refresh_token = data.get("refresh_token")

    if refresh_token:
        # Revogar token específico
        revoked = await revoke_refresh_token(refresh_token)
        return {
            "success": revoked,
            "message": "Token revogado" if revoked else "Token não encontrado ou já revogado"
        }
    else:
        # Revogar todos os tokens do utilizador
        count = await revoke_all_user_tokens(user["id"])
        return {
            "success": True,
            "message": f"{count} sessão(ões) terminada(s)",
            "revoked_count": count
        }


async def run_list_sessions(user: dict):
    """
    Lista sessões activas do utilizador.
    """
    sessions = await get_active_sessions(user["id"])
    return {
        "sessions": sessions,
        "total": len(sessions)
    }


async def run_revoke_session(session_id: str, user: dict):
    """
    Revoga uma sessão específica pelo ID.
    """
    # Buscar token pelo ID e verificar se pertence ao utilizador
    token_doc = await db.refresh_tokens.find_one(
        {"id": session_id, "user_id": user["id"]},
        {"_id": 0}
    )

    if not token_doc:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")

    if token_doc.get("revoked"):
        raise HTTPException(status_code=400, detail="Sessão já terminada")

    await db.refresh_tokens.update_one(
        {"id": session_id},
        {
            "$set": {
                "revoked": True,
                "revoked_at": datetime.now(timezone.utc).isoformat()
            }
        }
    )

    return {"success": True, "message": "Sessão terminada"}

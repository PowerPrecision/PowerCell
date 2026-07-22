"""Auth login orchestration — extracted from `routes/auth.py`.

Covers deprecated `/login` (410) and `/login-v2` (refresh tokens).
Do **not** overwrite existing `services/auth.py`.
"""
from __future__ import annotations

import logging

from fastapi import HTTPException
from fastapi.responses import JSONResponse

from database import db
from models.auth import UserLogin
from services.auth import (
    hash_password,
    verify_password,
    needs_rehash,
)
from services.refresh_token_service import (
    create_access_token,
    create_refresh_token_db,
    ACCESS_TOKEN_EXPIRE_MINUTES,
)

logger = logging.getLogger(__name__)


async def run_login(request, data: UserLogin, response):
    """
    DEPRECATED: Esta rota foi descontinuada.
    Utilize /auth/login-v2 para autenticação segura com refresh tokens.

    Esta rota será removida em futuras versões.
    """
    raise HTTPException(
        status_code=410,
        detail="Esta rota de login foi descontinuada. Utilize /auth/login-v2 para autenticação segura com refresh tokens."
    )


async def run_login_v2(request, data: UserLogin, response):
    """
    Login com suporte a refresh tokens.
    Retorna access_token (2h) + refresh_token (7 dias).
    """
    try:
        # Normalizar email (sem bleach/sanitize_email — simples e seguro)
        clean_email = str(data.email).strip().lower() if data.email else ""
        if not clean_email or "@" not in clean_email:
            logger.warning(f"Login falhou: email vazio ou sem @")
            raise HTTPException(status_code=401, detail="Credenciais inválidas")

        # Case-insensitive query (MongoDB é case-sensitive por default)
        user = await db.users.find_one(
            {"email": {"$regex": f"^{clean_email}$", "$options": "i"}},
            {"_id": 0}
        )
        if not user:
            logger.warning(f"Login falhou: utilizador não encontrado para email={clean_email}")
            raise HTTPException(status_code=401, detail="Credenciais inválidas")

        password_field = user.get("password") or user.get("hashed_password", "")
        if not password_field:
            logger.error(f"Login falhou: utilizador {user['id']} sem password")
            raise HTTPException(status_code=401, detail="Credenciais inválidas")

        if not verify_password(data.password, password_field):
            logger.warning(f"Login falhou: password incorrecta para user={user['id']}")
            raise HTTPException(status_code=401, detail="Credenciais inválidas")

        # Re-hash automático: se a password está em formato legacy (SHA-256),
        # re-hashar para bcrypt de forma transparente após login bem-sucedido
        if needs_rehash(password_field):
            try:
                new_hash = hash_password(data.password)
                pw_field_name = "password" if user.get("password") else "hashed_password"
                await db.users.update_one(
                    {"id": user["id"]},
                    {"$set": {pw_field_name: new_hash}}
                )
                logger.info(f"Auto-rehash: user={user['id']} password migrada para bcrypt")
            except Exception as e:
                logger.error(f"Auto-rehash falhou para user={user['id']}: {e}")
                # Não bloquear o login — o utilizador consegue entrar de qualquer forma

        if not user.get("is_active", True):
            logger.warning(f"Login falhou: conta desactivada user={user['id']}")
            raise HTTPException(status_code=401, detail="Conta desativada")

        logger.info(f"Login bem-sucedido: user={user['id']} email={clean_email} role={user['role']}")

        # Sincronizar permissões com defaults do role (resolve permissões legacy)
        from services.permissions import sync_permissions_with_role_defaults
        user_perms = user.get("permissions")
        user_role = user.get("role", "cliente")
        synced_perms = sync_permissions_with_role_defaults(user_perms, user_role)
        if user_perms is not None and synced_perms != user_perms:
            await db.users.update_one(
                {"id": user["id"]},
                {"$set": {"permissions": synced_perms}}
            )

        # Criar access token
        access_token = create_access_token(
            user["id"],
            user["email"],
            user["role"]
        )

        # Criar refresh token
        device_info = str(request.headers.get("User-Agent", ""))[:200]
        client_host = ""
        try:
            client_host = request.client.host if request.client else ""
        except Exception:
            pass
        ip_address = str(request.headers.get("X-Forwarded-For", client_host))[:45]

        _, refresh_token = await create_refresh_token_db(
            user["id"],
            device_info=device_info,
            ip_address=ip_address
        )

        return JSONResponse(
            status_code=200,
            content={
                "access_token": access_token,
                "refresh_token": refresh_token,
                "token_type": "bearer",
                "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60,
                "user": {
                    "id": user["id"],
                    "email": user["email"],
                    "name": user["name"],
                    "phone": user.get("phone"),
                    "role": user["role"],
                    "created_at": user["created_at"],
                    "onedrive_folder": user.get("onedrive_folder"),
                    "additional_roles": user.get("additional_roles", []),
                    "permissions": synced_perms,
                }
            }
        )
    except HTTPException:
        raise  # Re-lançar HTTPExceptions (401, 403, etc.)
    except Exception as e:
        logger.exception(f"Login crash inesperado: {type(e).__name__}: {e}")
        raise HTTPException(status_code=500, detail=f"Erro interno: {type(e).__name__}")

"""Manual Gmail sync for admin shared-email configs.

Extraído de `routes/shared_email.py`.
"""
from __future__ import annotations

import logging
import traceback

from fastapi import HTTPException

from database import db
from services.shared_email_helpers import ALLOWED_ROLES, _require_admin

logger = logging.getLogger(__name__)


async def run_shared_email_manual_sync(
    role: str,
    current_user: dict,
    days: int = 3,
) -> dict:
    """Sincronização manual via Gmail API para a caixa partilhada de um role.

    Retorna códigos HTTP diferenciados para facilitar o diagnóstico:
    - 400: Role não permitido
    - 404: Config não encontrada para o role
    - 422: Google OAuth não configurado (sem refresh_token)
    - 500: Erro na sincronização (API, rede, token expirado, etc.)
    """
    _require_admin(current_user)

    if role not in ALLOWED_ROLES:
        raise HTTPException(status_code=400, detail=f"Role '{role}' não permitido. Roles: {ALLOWED_ROLES}")

    # Pré-validar configuração antes de tentar sync (erros mais claros)
    config = await db.shared_role_email_configs.find_one({"role": role}, {"_id": 0})
    if not config:
        raise HTTPException(
            status_code=404,
            detail=f"Configuração de email partilhado não encontrada para '{role}'. "
                   f"Configure primeiro o endereço de email e conecte o Google OAuth."
        )

    encrypted_rt = config.get("google_refresh_token", "")
    if not encrypted_rt:
        raise HTTPException(
            status_code=422,
            detail=f"Google OAuth não configurado para '{role}'. "
                   f"Conecte a conta Google antes de sincronizar."
        )

    auth_method = config.get("auth_method", "none")
    if auth_method != "google_oauth":
        raise HTTPException(
            status_code=422,
            detail=f"Método de autenticação é '{auth_method}', não 'google_oauth'. "
                   f"A sincronização via Gmail API requer OAuth conectado."
        )

    try:
        from services.gmail_api_service import gmail_api_sync_to_db
    except ImportError:
        raise HTTPException(
            status_code=503,
            detail="Bibliotecas Google OAuth não instaladas no servidor. "
                   "Contacte o administrador: pip install google-auth-oauthlib google-api-python-client"
        )

    try:
        result = await gmail_api_sync_to_db(role=role, days=days, max_emails=200)
    except Exception as e:
        logger.error(f"[Shared Email Sync] Erro inesperado para role '{role}': {e}\n{traceback.format_exc()}")
        raise HTTPException(
            status_code=500,
            detail=f"Erro na sincronização Gmail para '{role}': {str(e)}"
        )

    if not result.get("success"):
        error_msg = result.get("error", "Erro desconhecido na sincronização")
        logger.warning(f"[Shared Email Sync] Falha para role '{role}': {error_msg}")

        # Diferenciar tipos de erro para status code adequado
        if "não configurado" in error_msg.lower() or "oauth" in error_msg.lower():
            raise HTTPException(status_code=422, detail=error_msg)
        elif "não encontrada" in error_msg.lower():
            raise HTTPException(status_code=404, detail=error_msg)
        elif "desencriptar" in error_msg.lower():
            raise HTTPException(
                status_code=500,
                detail=f"Erro de desencriptação — o refresh_token pode estar corrompido. "
                       f"Tente desconectar e reconectar o Google OAuth para '{role}'."
            )
        else:
            raise HTTPException(status_code=500, detail=error_msg)

    return result

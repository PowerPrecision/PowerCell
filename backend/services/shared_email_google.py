"""Google OAuth handlers for admin shared-email (login / callback / disconnect).

Extraído de `routes/shared_email.py`.
Static `/google/callback` must stay registered BEFORE `/{role}` in the route file.
"""
from __future__ import annotations

import logging
import secrets
import traceback
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException, Request
from fastapi.responses import HTMLResponse

from database import db
from services.encryption import encryption_service
from models.shared_email_config import SharedEmailOAuthLoginResponse
from services.shared_email_helpers import (
    ALLOWED_ROLES,
    _require_admin,
    _get_google_config,
    _build_redirect_uri,
)

logger = logging.getLogger(__name__)


async def run_shared_email_google_callback(
    request: Request,
    code: str,
    state: Optional[str] = None,
    error: Optional[str] = None,
    error_description: Optional[str] = None,
):
    """
    Callback OAuth para email partilhado por role.

    Quando o state contém `shared_role`, os tokens são guardados na
    coleção `shared_role_email_configs` em vez do perfil do utilizador.
    """
    if error:
        logger.warning(f"[Shared Email OAuth] Autorização negada: {error}")
        return HTMLResponse(
            content=f"""
            <html><head><title>Autenticação Google Cancelada</title></head>
            <body style="font-family: Arial, sans-serif; text-align: center; padding: 50px;">
                <h2 style="color: #e74c3c;">Autenticação Cancelada</h2>
                <p>Acesso ao Gmail cancelado: {error_description or error}</p>
                <p id="status" style="color: #888;">A comunicar com a aplicação...</p>
                <script>
                    try {{
                        if (window.opener && window.opener !== window) {{
                            window.opener.postMessage({{ type: 'shared_google_oauth_error', error: '{error}' }}, '*');
                            document.getElementById('status').textContent = 'Pode fechar esta janela.';
                        }} else {{
                            document.getElementById('status').textContent = 'Autenticação processada. Por favor, feche esta janela e atualize a página principal.';
                        }}
                    }} catch (e) {{
                        document.getElementById('status').textContent = 'Autenticação processada. Por favor, feche esta janela e atualize a página principal.';
                    }}
                    try {{ window.close(); }} catch(e) {{}}
                </script>
            </body></html>
            """,
            status_code=400,
        )

    if not code:
        raise HTTPException(status_code=400, detail="Código de autorização não fornecido")

    try:
        google_cfg = _get_google_config()
    except HTTPException:
        raise

    try:
        from google_auth_oauthlib.flow import Flow
        from googleapiclient.discovery import build

        # Verificar state
        shared_role = None
        redirect_uri = None
        email_address = None
        admin_user_id = None

        if state:
            stored_state = await db.oauth_states.find_one({"state": state})
            if stored_state:
                shared_role = stored_state.get("shared_role")
                admin_user_id = stored_state.get("user_id")
                redirect_uri = stored_state.get("redirect_uri")
                email_address = stored_state.get("email_address")
                await db.oauth_states.delete_one({"_id": stored_state["_id"]})

        if not shared_role:
            logger.warning("[Shared Email OAuth] Callback sem shared_role no state — ignorar")
            return HTMLResponse(
                content="<html><body><p>Erro: Estado de autenticação inválido.</p></body></html>",
                status_code=400,
            )

        if not redirect_uri:
            redirect_uri = _build_redirect_uri(request)

        # Trocar code por tokens
        flow = Flow.from_client_config(
            client_config={
                "web": {
                    "client_id": google_cfg["client_id"],
                    "client_secret": google_cfg["client_secret"],
                    "auth_uri": "https://accounts.google.com/o/oauth2/v2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": [redirect_uri],
                }
            },
            scopes=google_cfg["scopes"],
            redirect_uri=redirect_uri,
        )

        flow.fetch_token(code=code)
        credentials = flow.credentials

        refresh_token = credentials.refresh_token

        if not refresh_token:
            logger.warning("[Shared Email OAuth] Refresh token NÃO recebido!")

        # Verificar email do Google
        google_email = None
        try:
            service = build("gmail", "v1", credentials=credentials)
            profile = service.users().getProfile(userId="me").execute()
            google_email = profile.get("emailAddress")
        except Exception as e:
            logger.warning(f"[Shared Email OAuth] Não foi possível verificar email: {e}")

        # Encriptar tokens
        encrypted_refresh = encryption_service.encrypt(refresh_token) if refresh_token else ""

        # Guardar na config partilhada do role
        now = datetime.now(timezone.utc).isoformat()

        existing = await db.shared_role_email_configs.find_one({"role": shared_role}, {"_id": 0})

        update_data = {
            "role": shared_role,
            "email_address": email_address or google_email or (existing or {}).get("email_address", ""),
            "google_refresh_token": encrypted_refresh,
            "google_email": google_email or "",
            "auth_method": "google_oauth" if refresh_token else "google_oauth_temp",
            "is_configured": True,
            "oauth_connected_at": now,
            "updated_at": now,
        }

        await db.shared_role_email_configs.update_one(
            {"role": shared_role},
            {"$set": update_data},
            upsert=True,
        )

        # Audit log
        await db.audit_logs.insert_one({
            "action": "shared_google_oauth_connected",
            "user_id": admin_user_id,
            "details": {
                "role": shared_role,
                "email": google_email,
                "has_refresh_token": bool(refresh_token),
            },
            "created_at": now,
        })

        logger.info(
            f"[Shared Email OAuth] Tokens guardados para role '{shared_role}' "
            f"(email={google_email}, has_refresh={bool(refresh_token)})"
        )

        has_refresh_text = "sim" if refresh_token else "NÃO"
        return HTMLResponse(
            content=f"""
            <html><head><title>Google OAuth - Conectado</title></head>
            <body style="font-family: Arial, sans-serif; text-align: center; padding: 50px;">
                <h2 style="color: #27ae60;">Gmail Conectado com Sucesso!</h2>
                <p>Email Partilhado: <strong>{google_email or email_address or 'N/A'}</strong></p>
                <p>Departamento (role): <strong>{shared_role}</strong></p>
                <p>Refresh Token: <strong>{has_refresh_text}</strong></p>
                <p id="status">A comunicar com a aplicação...</p>
                <script>
                    try {{
                        if (window.opener && window.opener !== window) {{
                            window.opener.postMessage({{
                                type: 'shared_google_oauth_success',
                                role: '{shared_role}',
                                email: '{google_email or email_address or ""}',
                                has_refresh_token: {str(bool(refresh_token)).lower()}
                            }}, '*');
                            document.getElementById('status').textContent = 'Pode fechar esta janela.';
                        }} else {{
                            document.getElementById('status').textContent = 'Autenticação concluída! Por favor, feche esta janela e atualize a página principal.';
                        }}
                    }} catch (e) {{
                        document.getElementById('status').textContent = 'Autenticação concluída! Por favor, feche esta janela e atualize a página principal.';
                    }}
                    try {{ window.close(); }} catch(e) {{}}
                </script>
            </body></html>
            """,
            status_code=200,
        )

    except HTTPException:
        raise
    except ImportError:
        raise HTTPException(status_code=503, detail="Bibliotecas Google OAuth não instaladas.")
    except Exception as e:
        logger.error(f"[Shared Email OAuth] Erro no callback: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Erro ao processar callback: {e}")


async def run_shared_email_google_login(
    role: str,
    request: Request,
    current_user: dict,
    email_address: Optional[str] = None,
) -> SharedEmailOAuthLoginResponse:
    """
    Iniciar o fluxo Google OAuth para a caixa de email partilhada de um role.

    CRÍTICO: Inclui access_type='offline' e prompt='consent' para obter
    o refresh_token (necessário para sync periódico pelo worker).
    """
    _require_admin(current_user)

    if role not in ALLOWED_ROLES:
        raise HTTPException(status_code=400, detail=f"Role '{role}' não permitido. Roles: {ALLOWED_ROLES}")

    try:
        google_cfg = _get_google_config()

        from google_auth_oauthlib.flow import Flow

        redirect_uri = _build_redirect_uri(request)

        flow = Flow.from_client_config(
            client_config={
                "web": {
                    "client_id": google_cfg["client_id"],
                    "client_secret": google_cfg["client_secret"],
                    "auth_uri": "https://accounts.google.com/o/oauth2/v2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": [redirect_uri],
                }
            },
            scopes=google_cfg["scopes"],
            redirect_uri=redirect_uri,
        )

        state_token = secrets.token_urlsafe(32)

        # Guardar state com metadata do role
        await db.oauth_states.insert_one({
            "state": state_token,
            "user_id": current_user["id"],
            "shared_role": role,  # Chave para identificar como shared email
            "redirect_uri": redirect_uri,
            "email_address": email_address,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })

        authorization_url, _ = flow.authorization_url(
            access_type="offline",
            prompt="consent",
            state=state_token,
            login_hint=email_address if email_address else None,
        )

        logger.info(
            f"[Shared Email OAuth] Login iniciado para role '{role}' "
            f"por admin {current_user['id']} (email_hint={email_address or 'auto'})"
        )

        return SharedEmailOAuthLoginResponse(
            authorization_url=authorization_url,
            state=state_token,
            redirect_uri=redirect_uri,
            role=role,
        )

    except HTTPException:
        raise
    except ImportError as e:
        logger.error(f"[Shared Email OAuth] Biblioteca não instalada: {e}\n{traceback.format_exc()}")
        raise HTTPException(
            status_code=503,
            detail="Bibliotecas Google OAuth não instaladas. pip install google-auth-oauthlib",
        )
    except Exception as e:
        logger.error(f"[Shared Email OAuth] Erro ao gerar URL: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Erro ao gerar URL de autorização: {e}")


async def run_shared_email_google_disconnect(role: str, current_user: dict) -> dict:
    """Remove os tokens Google OAuth da config partilhada de um role."""
    _require_admin(current_user)

    if role not in ALLOWED_ROLES:
        raise HTTPException(status_code=400, detail=f"Role '{role}' não permitido")

    now = datetime.now(timezone.utc).isoformat()

    result = await db.shared_role_email_configs.update_one(
        {"role": role},
        {"$set": {
            "google_refresh_token": "",
            "google_email": "",
            "oauth_connected_at": "",
            "updated_at": now,
        }},
    )

    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail=f"Config para role '{role}' não encontrada")

    # Atualizar auth_method
    existing = await db.shared_role_email_configs.find_one({"role": role}, {"_id": 0})
    if existing:
        has_imap = bool(existing.get("encrypted_password"))
        new_method = "imap_smtp" if has_imap else "none"
        new_configured = has_imap
        await db.shared_role_email_configs.update_one(
            {"role": role},
            {"$set": {"auth_method": new_method, "is_configured": new_configured}},
        )

    logger.info(f"[Shared Email OAuth] Desconectado Google OAuth para role '{role}'")

    return {"success": True, "message": f"Google OAuth desconectado para role '{role}'"}

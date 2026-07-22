"""Google OAuth login + callback handlers (user Gmail).

Extraído de `routes/google_auth.py`. Prefer `google_auth_*` — do **not**
overwrite existing `gmail_oauth.py` / `gmail_api_service.py`.
"""
from __future__ import annotations

import logging
import secrets
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException, Request
from fastapi.responses import HTMLResponse

from database import db
from services.encryption import encryption_service
from services.google_auth_helpers import (
    _get_google_config,
    _build_redirect_uri,
    _resolve_user,
)

logger = logging.getLogger(__name__)


async def run_google_login(
    request: Request,
    token: Optional[str] = None,
    email_address: Optional[str] = None,
) -> dict:
    """
    Gera e devolve o URL de autorização da Google.

    Authentication:
    - Primary: Authorization: Bearer <jwt> header
    - Fallback: ?token=<jwt> query parameter (for direct browser navigation)

    CRÍTICO: Inclui access_type='offline' e prompt='consent' para
    forçar a Google a devolver um refresh_token.
    """
    # Resolve user — try Bearer header first, then ?token= fallback
    user = await _resolve_user(request, token=token)

    google_cfg = _get_google_config()

    try:
        from google_auth_oauthlib.flow import Flow

        # Construir redirect URI dinâmica
        redirect_uri = _build_redirect_uri(request, google_cfg["redirect_uri"])

        # Criar flow
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

        # Gerar state CSRF
        state_token = secrets.token_urlsafe(32)

        # Guardar state na DB para verificação posterior
        # TTL de 10 minutos para o state
        # Persist active role + company for per-company OAuth storage
        active_role = request.headers.get("X-Active-Role", "")
        company_id = request.headers.get("X-Company-Id", "")
        await db.oauth_states.insert_one(
            {
                "state": state_token,
                "user_id": user["id"],
                "redirect_uri": redirect_uri,
                "email_address": email_address,
                "active_role": active_role or None,
                "company_id": company_id or None,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "expires_at": (
                    datetime.now(timezone.utc).isoformat()
                ),
            }
        )

        # Configurar parâmetros de autorização
        authorization_url, _ = flow.authorization_url(
            access_type="offline",
            prompt="consent",
            state=state_token,
            login_hint=email_address if email_address else None,
        )

        logger.info(
            f"[Google OAuth] Login iniciado para user {user['id']} "
            f"(email_hint={email_address or 'auto'})"
        )

        return {
            "authorization_url": authorization_url,
            "state": state_token,
            "redirect_uri": redirect_uri,
        }

    except HTTPException:
        raise
    except ImportError:
        raise HTTPException(
            status_code=503,
            detail="Bibliotecas Google OAuth não instaladas. Execute: pip install google-auth-oauthlib",
        )
    except Exception as e:
        logger.error(f"[Google OAuth] Erro ao gerar URL de autorização: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao gerar URL de autorização: {str(e)}",
        )


async def run_google_callback(
    request: Request,
    code: str,
    state: Optional[str] = None,
    error: Optional[str] = None,
    error_description: Optional[str] = None,
):
    """
    Callback OAuth 2.0 da Google.

    Recebe o código de autorização e troca-o por tokens.
    Guarda o refresh_token de forma segura (encriptado) no perfil do utilizador.
    """
    # Se o utilizador negou o consentimento
    if error:
        logger.warning(f"[Google OAuth] Autorização negada: {error} - {error_description}")
        return HTMLResponse(
            content=f"""
            <html>
            <head><title>Autenticação Google Cancelada</title></head>
            <body style="font-family: Arial, sans-serif; text-align: center; padding: 50px;">
                <h2 style="color: #e74c3c;">Autenticação Cancelada</h2>
                <p>O acesso ao Gmail foi cancelado: {error_description or error}</p>
                <p id="status" style="color: #888;">A comunicar com a aplicação...</p>
                <script>
                    try {{
                        if (window.opener && window.opener !== window) {{
                            window.opener.postMessage({{ type: 'google_oauth_error', error: '{error}' }}, '*');
                            document.getElementById('status').textContent = 'Pode fechar esta janela e tentar novamente.';
                        }} else {{
                            document.getElementById('status').textContent = 'Autenticação cancelada. Por favor, feche esta janela e atualize a página principal.';
                        }}
                    }} catch (e) {{
                        document.getElementById('status').textContent = 'Autenticação cancelada. Por favor, feche esta janela e atualize a página principal.';
                    }}
                    try {{ window.close(); }} catch(e) {{}}
                </script>
            </body>
            </html>
            """,
            status_code=400,
        )

    if not code:
        raise HTTPException(status_code=400, detail="Código de autorização não fornecido")

    google_cfg = _get_google_config()

    try:
        from google_auth_oauthlib.flow import Flow

        # Determinar user_id e redirect_uri
        user_id = None
        redirect_uri = google_cfg["redirect_uri"]
        email_address = None
        stored_state = None

        # Verificar state (se fornecido)
        if state:
            stored_state = await db.oauth_states.find_one({"state": state})
            if stored_state:
                user_id = stored_state.get("user_id")
                redirect_uri = stored_state.get("redirect_uri") or google_cfg["redirect_uri"]
                email_address = stored_state.get("email_address")
                # Limpar state usado
                await db.oauth_states.delete_one({"_id": stored_state["_id"]})

                logger.info(f"[Google OAuth] State verificado para user {user_id}")
            else:
                logger.warning(f"[Google OAuth] State não encontrado: {state}")

        # Se não temos redirect_uri, inferir do request
        if not redirect_uri:
            redirect_uri = _build_redirect_uri(request, "")

        # Criar flow para trocar code por tokens
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

        # Trocar code por tokens
        flow.fetch_token(code=code)
        credentials = flow.credentials

        refresh_token = credentials.refresh_token
        access_token = credentials.token

        if not refresh_token:
            logger.warning(
                "[Google OAuth] Refresh token NÃO recebido. "
                "A Google não devolve refresh_token quando o utilizador já autorizou "
                "sem prompt='consent'. O access_token vai expirar em ~1 hora."
            )
            # Mesmo sem refresh_token, podemos usar o access_token temporariamente
            # Mas aviso: o utilizador terá de re-autenticar quando expirar

        # Verificar o email do utilizador Google
        google_email = None
        try:
            from googleapiclient.discovery import build
            service = build("gmail", "v1", credentials=credentials)
            profile = service.users().getProfile(userId="me").execute()
            google_email = profile.get("emailAddress")
            logger.info(f"[Google OAuth] Email Google verificado: {google_email}")
        except Exception as e:
            logger.warning(f"[Google OAuth] Não foi possível verificar email Google: {e}")

        # Encriptar o refresh_token (e access_token se existir)
        encrypted_refresh = encryption_service.encrypt(refresh_token) if refresh_token else ""
        encrypted_access = encryption_service.encrypt(access_token) if access_token else ""

        # Guardar tokens
        if user_id:
            # Prefer company key when company_id is known (canonical multi-empresa).
            # Fall back to role key only when no company context.
            oauth_company_id = stored_state.get("company_id") if stored_state else None
            oauth_active_role = stored_state.get("active_role") if stored_state else None

            # Get user's primary role for comparison
            user_doc = await db.users.find_one(
                {"id": user_id}, {"_id": 0, "role": 1}
            )
            user_primary_role = (user_doc or {}).get("role", "")

            if oauth_company_id and oauth_company_id != "default":
                storage_key = f"company:{oauth_company_id}"
            elif oauth_active_role and oauth_active_role != user_primary_role:
                storage_key = oauth_active_role
            else:
                storage_key = "default"

            # Load and normalize existing email_config
            from services.email_config_resolver import (
                _is_nested_email_config, _extract_role_email_config,
            )
            existing_user = await db.users.find_one(
                {"id": user_id}, {"_id": 0, "email_config": 1}
            )
            raw_existing = (existing_user or {}).get("email_config", {})

            # Normalize: if flat, wrap as {"default": ...}
            if raw_existing and not _is_nested_email_config(raw_existing):
                nested_existing = {"default": raw_existing}
            elif raw_existing:
                nested_existing = raw_existing
            else:
                nested_existing = {}

            # Get existing config for this storage key
            existing_role_config = _extract_role_email_config(
                nested_existing, storage_key
            )

            email_addr = email_address or google_email or existing_role_config.get("email_address", "")

            # Build config preserving IMAP/SMTP settings
            new_role_config = {
                "email_address": email_addr,
                "imap_server": existing_role_config.get("imap_server", ""),
                "imap_port": existing_role_config.get("imap_port", 993),
                "smtp_server": existing_role_config.get("smtp_server", ""),
                "smtp_port": existing_role_config.get("smtp_port", 465),
                "encrypted_password": existing_role_config.get("encrypted_password", ""),
                "google_refresh_token": encrypted_refresh,
                "google_access_token": encrypted_access,
                "google_email": google_email or "",
                "auth_method": "google_oauth" if refresh_token else "google_oauth_temp",
                "is_configured": True,
                "oauth_connected_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            if oauth_company_id:
                new_role_config["company_id"] = oauth_company_id

            # Store under company key when known, else role/default
            nested_existing[storage_key] = new_role_config

            await db.users.update_one(
                {"id": user_id},
                {"$set": {"email_config": nested_existing}},
            )

            # Dual-write to canonical user_email_configs when company known
            if oauth_company_id and oauth_company_id != "default":
                try:
                    from services.user_email_config_service import upsert_user_email_config
                    await upsert_user_email_config(
                        user_id=user_id,
                        company_id=oauth_company_id,
                        email_address=email_addr,
                        imap_server=new_role_config.get("imap_server", ""),
                        imap_port=new_role_config.get("imap_port", 993),
                        smtp_server=new_role_config.get("smtp_server", ""),
                        smtp_port=new_role_config.get("smtp_port", 465),
                        encrypted_password=new_role_config.get("encrypted_password", ""),
                        google_refresh_token=encrypted_refresh,
                        google_access_token=encrypted_access,
                        google_email=google_email or "",
                        auth_method=new_role_config.get("auth_method", "google_oauth"),
                        oauth_connected_at=new_role_config.get("oauth_connected_at"),
                        is_configured=True,
                    )
                except Exception as e:
                    logger.warning(
                        f"[Google OAuth] Dual-write user_email_configs falhou: {e}"
                    )

            logger.info(
                f"[Google OAuth] Tokens guardados para user {user_id} "
                f"(key={storage_key}, email={email_addr}, has_refresh={bool(refresh_token)})"
            )

            # Log de auditoria
            await db.audit_logs.insert_one({
                "action": "google_oauth_connected",
                "user_id": user_id,
                "details": {
                    "email": email_addr,
                    "google_email": google_email,
                    "has_refresh_token": bool(refresh_token),
                    "storage_key": storage_key,
                    "company_id": oauth_company_id,
                },
                "created_at": datetime.now(timezone.utc).isoformat(),
            })

        else:
            # Sem user_id — tentar guardar em system_config (conta partilhada)
            logger.warning(
                "[Google OAuth] Sem user_id — guardar tokens em system_config "
                "(conta partilhada do departamento de indexação)"
            )
            await db.system_config.update_one(
                {"_id": "shared_gmail_oauth"},
                {
                    "$set": {
                        "google_refresh_token": encrypted_refresh,
                        "google_access_token": encrypted_access,
                        "google_email": google_email or "",
                        "email_address": email_address or google_email or "",
                        "auth_method": "google_oauth" if refresh_token else "google_oauth_temp",
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    }
                },
                upsert=True,
            )

        # Sucesso — devolver HTML que fecha a popup
        has_refresh_text = "sim" if refresh_token else "NÃO (o access token expira em ~1h)"
        return HTMLResponse(
            content=f"""
            <html>
            <head><title>Google OAuth - Conectado</title></head>
            <body style="font-family: Arial, sans-serif; text-align: center; padding: 50px;">
                <h2 style="color: #27ae60;">Gmail Conectado com Sucesso!</h2>
                <p>Email: <strong>{google_email or email_address or 'N/A'}</strong></p>
                <p>Refresh Token: <strong>{has_refresh_text}</strong></p>
                <p id="status">A comunicar com a aplicação...</p>
                <script>
                    try {{
                        if (window.opener && window.opener !== window) {{
                            window.opener.postMessage({{
                                type: 'google_oauth_success',
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
            </body>
            </html>
            """,
            status_code=200,
        )

    except HTTPException:
        raise
    except ImportError as e:
        logger.error(f"[Google OAuth] Biblioteca não instalada: {e}")
        raise HTTPException(
            status_code=503,
            detail="Bibliotecas Google OAuth não instaladas.",
        )
    except Exception as e:
        logger.error(f"[Google OAuth] Erro no callback: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao processar callback OAuth: {str(e)}",
        )

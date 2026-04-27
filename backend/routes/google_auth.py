"""
====================================================================
ROTAS GOOGLE OAUTH 2.0 - GMAIL API
====================================================================
Endpoints para autenticação OAuth 2.0 da Google (Gmail).

Fluxo:
1. Frontend chama GET /api/auth/google/login → recebe authorization_url
2. Utilizador autoriza na página da Google
3. Google redireciona para GET /api/auth/google/callback?code=...
4. Backend troca code por tokens, guarda refresh_token encriptado

O refresh_token é guardado no campo email_config.google_refresh_token
do utilizador (encriptado com Fernet via encryption_service).

CRÍTICO: access_type='offline' + prompt='consent' garantem que a
Google devolve um refresh_token (mesmo se já autorizou antes).
====================================================================
"""
import logging
import secrets
from datetime import datetime, timezone
from typing import Optional

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from fastapi.responses import RedirectResponse, HTMLResponse

from database import db
from services.auth import get_current_user
from config import JWT_SECRET, JWT_ALGORITHM
from services.encryption import encryption_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth/google", tags=["Google OAuth"])


def _get_google_config():
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


def _build_redirect_uri(request: Request, configured_uri: str) -> str:
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




async def _resolve_user(request: Request, token: Optional[str] = None) -> dict:
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


@router.get("/login")
async def google_login(
    request: Request,
    token: Optional[str] = Query(None, description="JWT token (fallback when Authorization header is unavailable)"),
    email_address: Optional[str] = None,
):
    """
    Gera e devolve o URL de autorização da Google.

    Authentication:
    - Primary: Authorization: Bearer <jwt> header
    - Fallback: ?token=<jwt> query parameter (for direct browser navigation)

    Query params (opcionais):
    - email_address: se fornecido, usa este email como login_hint (pré-preenche)

    CRÍTICO: Inclui access_type='offline' e prompt='consent' para
    forçar a Google a devolver um refresh_token.

    Returns:
        JSON com authorization_url e state (para verificação CSRF).
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
        # Also persist active role for per-role OAuth
        active_role = request.headers.get("X-Active-Role", "")
        await db.oauth_states.insert_one(
            {
                "state": state_token,
                "user_id": user["id"],
                "redirect_uri": redirect_uri,
                "email_address": email_address,
                "active_role": active_role or None,
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


@router.get("/callback")
async def google_callback(
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

    Se o state for fornecido, verifica-o contra o guardado na DB (CSRF protection).
    Se não houver state (ex: configuração de conta partilhada por admin),
    guarda os tokens numa localização genérica do sistema.
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
            # Determine which role sub-config to store OAuth tokens in
            oauth_active_role = stored_state.get("active_role") if stored_state else None

            # Get user's primary role for comparison
            user_doc = await db.users.find_one(
                {"id": user_id}, {"_id": 0, "role": 1}
            )
            user_primary_role = (user_doc or {}).get("role", "")

            if oauth_active_role and oauth_active_role != user_primary_role:
                storage_role = oauth_active_role
            else:
                storage_role = "default"

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

            # Get existing config for this role
            existing_role_config = _extract_role_email_config(
                nested_existing, storage_role
            )

            email_addr = email_address or google_email or existing_role_config.get("email_address", "")

            # Build role config preserving IMAP/SMTP settings
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

            # Store under the role key
            nested_existing[storage_role] = new_role_config

            await db.users.update_one(
                {"id": user_id},
                {"$set": {"email_config": nested_existing}},
            )

            logger.info(
                f"[Google OAuth] Tokens guardados para user {user_id} "
                f"(email={email_addr}, has_refresh={bool(refresh_token)})"
            )

            audit_msg = "Google OAuth conectado com refresh_token"
            if not refresh_token:
                audit_msg = "Google OAuth conectado (SEM refresh_token — access_token temporário)"

            # Log de auditoria
            await db.audit_logs.insert_one({
                "action": "google_oauth_connected",
                "user_id": user_id,
                "details": {
                    "email": email_addr,
                    "google_email": google_email,
                    "has_refresh_token": bool(refresh_token),
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


@router.get("/status")
async def google_oauth_status(
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """
    Verifica o estado da ligação Google OAuth do utilizador.

    Suporta per-role configs: lê X-Active-Role header.

    Returns:
        Informações sobre se o refresh_token existe e se a ligação está ativa.
    """
    from services.email_config_resolver import (
        _is_nested_email_config, _extract_role_email_config,
    )

    user_id = current_user["id"]
    user_role = current_user.get("role", "")
    user = await db.users.find_one(
        {"id": user_id},
        {"_id": 0, "email_config": 1},
    )

    if not user or not user.get("email_config"):
        return {
            "connected": False,
            "auth_method": "none",
            "google_email": None,
            "has_refresh_token": False,
        }

    # Determine active role and extract config
    active_role_header = request.headers.get("X-Active-Role", "")
    active_role = active_role_header if active_role_header and active_role_header != user_role else None
    raw_config = user["email_config"]
    config = _extract_role_email_config(raw_config, active_role)

    refresh_token_enc = config.get("google_refresh_token", "")

    return {
        "connected": bool(refresh_token_enc),
        "auth_method": config.get("auth_method", "none"),
        "google_email": config.get("google_email"),
        "email_address": config.get("email_address"),
        "has_refresh_token": bool(refresh_token_enc),
        "oauth_connected_at": config.get("oauth_connected_at"),
    }


@router.delete("/disconnect")
async def google_oauth_disconnect(
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """
    Remove os tokens Google OAuth do utilizador.
    Mantém a configuração IMAP/SMTP existente (para fallback).

    Suporta per-role configs: limpa OAuth tokens apenas da sub-config do role ativo.
    """
    from datetime import datetime, timezone
    from services.email_config_resolver import (
        _is_nested_email_config, _extract_role_email_config,
    )

    user_id = current_user["id"]
    user_role = current_user.get("role", "")

    # Determine active role
    active_role_header = request.headers.get("X-Active-Role", "")
    if active_role_header and active_role_header != user_role:
        storage_role = active_role_header
    else:
        storage_role = "default"

    # Load existing config
    existing_user = await db.users.find_one(
        {"id": user_id}, {"_id": 0, "email_config": 1}
    )
    raw_config = (existing_user or {}).get("email_config", {})

    if not raw_config:
        raise HTTPException(status_code=400, detail="Sem configuração de email")

    # Normalize
    if _is_nested_email_config(raw_config):
        nested_config = raw_config
    else:
        nested_config = {"default": raw_config}

    # Clear OAuth fields from the role-specific sub-config
    role_config = nested_config.get(storage_role)
    if role_config and isinstance(role_config, dict):
        role_config["google_refresh_token"] = ""
        role_config["google_access_token"] = ""
        role_config["google_email"] = ""
        role_config["oauth_connected_at"] = ""
        role_config["updated_at"] = datetime.now(timezone.utc).isoformat()
        # Remove auth_method if it was google_oauth
        if role_config.get("auth_method", "").startswith("google_oauth"):
            role_config["auth_method"] = role_config.get("auth_method", "").replace("google_oauth", "none") or "none"

        await db.users.update_one(
            {"id": user_id},
            {"$set": {"email_config": nested_config}},
        )
    else:
        # Fallback: use dot notation for flat config
        await db.users.update_one(
            {"id": user_id},
            {
                "$set": {
                    "email_config.google_refresh_token": "",
                    "email_config.google_access_token": "",
                    "email_config.google_email": "",
                    "email_config.auth_method": "none",
                    "email_config.oauth_connected_at": "",
                    "email_config.updated_at": datetime.now(timezone.utc).isoformat(),
                }
            },
        )

    # Audit log
    await db.audit_logs.insert_one({
        "action": "google_oauth_disconnected",
        "user_id": user_id,
        "details": {},
        "created_at": datetime.now(timezone.utc).isoformat(),
    })

    logger.info(f"[Google OAuth] Utilizador {user_id} desconectou Google OAuth")

    return {"success": True, "message": "Google OAuth desconectado"}

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

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse, HTMLResponse

from database import db
from services.auth import get_current_user
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


@router.get("/login")
async def google_login(
    request: Request,
    current_user: dict = Depends(get_current_user),
    email_address: Optional[str] = None,
):
    """
    Gera e devolve o URL de autorização da Google.

    Query params (opcionais):
    - email_address: se fornecido, usa este email como login_hint (pré-preenche)

    CRÍTICO: Inclui access_type='offline' e prompt='consent' para
    forçar a Google a devolver um refresh_token.

    Returns:
        JSON com authorization_url e state (para verificação CSRF).
    """
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
        await db.oauth_states.insert_one(
            {
                "state": state_token,
                "user_id": current_user["id"],
                "redirect_uri": redirect_uri,
                "email_address": email_address,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "expires_at": (
                    datetime.now(timezone.utc).isoformat()
                ),
            }
        )

        # Configurar parâmetros de autorização
        flow.params["access_type"] = "offline"
        flow.params["prompt"] = "consent"
        flow.params["state"] = state_token
        if email_address:
            flow.params["login_hint"] = email_address

        authorization_url, _ = flow.authorization_url(
            access_type="offline",
            prompt="consent",
            state=state_token,
        )

        logger.info(
            f"[Google OAuth] Login iniciado para user {current_user['id']} "
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
                <p>Pode fechar esta janela e tentar novamente.</p>
                <script>
                    if (window.opener) {{
                        window.opener.postMessage({{ type: 'google_oauth_error', error: '{error}' }}, '*');
                    }}
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
            # Guardar no email_config do utilizador
            existing_user = await db.users.find_one(
                {"id": user_id}, {"_id": 0, "email_config": 1}
            )
            existing_config = (existing_user or {}).get("email_config", {})

            email_addr = email_address or google_email or existing_config.get("email_address", "")

            # Preservar config IMAP existente (para fallback)
            email_config = {
                "email_address": email_addr,
                "imap_server": existing_config.get("imap_server", ""),
                "imap_port": existing_config.get("imap_port", 993),
                "smtp_server": existing_config.get("smtp_server", ""),
                "smtp_port": existing_config.get("smtp_port", 465),
                "encrypted_password": existing_config.get("encrypted_password", ""),
                "google_refresh_token": encrypted_refresh,
                "google_access_token": encrypted_access,
                "google_email": google_email or "",
                "auth_method": "google_oauth" if refresh_token else "google_oauth_temp",
                "is_configured": True,
                "oauth_connected_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }

            await db.users.update_one(
                {"id": user_id},
                {"$set": {"email_config": email_config}},
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
                <p>Pode fechar esta janela.</p>
                <script>
                    if (window.opener) {{
                        window.opener.postMessage({{
                            type: 'google_oauth_success',
                            email: '{google_email or email_address or ""}',
                            has_refresh_token: {str(bool(refresh_token)).lower()}
                        }}, '*');
                    }}
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
async def google_oauth_status(current_user: dict = Depends(get_current_user)):
    """
    Verifica o estado da ligação Google OAuth do utilizador.

    Returns:
        Informações sobre se o refresh_token existe e se a ligação está ativa.
    """
    user_id = current_user["id"]
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

    config = user["email_config"]
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
async def google_oauth_disconnect(current_user: dict = Depends(get_current_user)):
    """
    Remove os tokens Google OAuth do utilizador.
    Mantém a configuração IMAP/SMTP existente (para fallback).
    """
    from datetime import datetime, timezone

    user_id = current_user["id"]

    # Limpar apenas os campos OAuth, preservar o resto
    await db.users.update_one(
        {"id": user_id},
        {
            "$set": {
                "email_config.google_refresh_token": "",
                "email_config.google_access_token": "",
                "email_config.google_email": "",
                "email_config.auth_method": (
                    "$$REMOVE"  # MongoDB operator to remove field
                ),
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

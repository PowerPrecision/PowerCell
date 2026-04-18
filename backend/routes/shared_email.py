"""
====================================================================
ROTAS - CONFIGURAÇÃO DE EMAIL PARTILHADO POR ROLE
====================================================================
Endpoints para o Administrador gerir caixas de email partilhadas
por departamento/role (ex: 'indexacao', 'suporte').

AUTHORIZAÇÃO: Apenas admin e CEO podem aceder.
ARMAZENAMENTO: Coleção `shared_role_email_configs` no MongoDB.

ENDPOINTS:
- GET    /api/admin/shared-email              → Listar todas as configs
- GET    /api/admin/shared-email/google/callback      → Callback OAuth
- GET    /api/admin/shared-email/{role}       → Obter config de um role
- PUT    /api/admin/shared-email/{role}       → Criar/atualizar config (IMAP)
- DELETE /api/admin/shared-email/{role}       → Remover config
- GET    /api/admin/shared-email/{role}/google/login  → Iniciar OAuth
- POST   /api/admin/shared-email/{role}/sync         → Sync manual via Gmail API
- DELETE /api/admin/shared-email/{role}/google       → Desconectar OAuth

NOTA: /google/callback DEVE ficar antes de /{role} para evitar que
FastAPI faça match de "google" ao path parameter {role}.

O fluxo OAuth é idêntico ao fluxo por utilizador, mas guarda os
tokens na coleção `shared_role_email_configs` em vez do perfil
individual do utilizador.
====================================================================
"""

import logging
import secrets
import traceback
from datetime import datetime, timezone
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Request, Query
from fastapi.responses import HTMLResponse

from database import db
from services.auth import get_current_user
from services.encryption import encryption_service
from models.shared_email_config import (
    SharedEmailConfigCreate,
    SharedEmailConfigResponse,
    SharedEmailConfigListResponse,
    SharedEmailOAuthLoginResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/shared-email", tags=["Shared Email Config"])

# Roles permitidos para email partilhado
ALLOWED_ROLES = ["indexacao", "suporte", "comercial", "admin"]


def _require_admin(current_user: dict):
    """Verifica se o utilizador é admin ou CEO."""
    from models.auth import UserRole
    if current_user.get("role") not in (UserRole.ADMIN, UserRole.CEO):
        raise HTTPException(status_code=403, detail="Acesso restrito a administradores")


def _get_google_config():
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


def _build_redirect_uri(request: Request, configured_uri: str) -> str:
    """Constrói a redirect URI para o callback."""
    if configured_uri:
        return configured_uri
    scheme = request.headers.get("x-forwarded-proto", "https")
    host = request.headers.get("host", "localhost:8000")
    return f"{scheme}://{host}/api/admin/shared-email/google/callback"


# ====================================================================
# CRUD ENDPOINTS
# ====================================================================

@router.get("", response_model=SharedEmailConfigListResponse)
async def list_shared_email_configs(
    current_user: dict = Depends(get_current_user),
):
    """Listar todas as configurações de email partilhado."""
    _require_admin(current_user)

    configs = await db.shared_role_email_configs.find({}, {"_id": 0}).to_list(50)

    response_list = []
    for cfg in configs:
        response_list.append(SharedEmailConfigResponse(
            role=cfg.get("role", ""),
            email_address=cfg.get("email_address"),
            display_name=cfg.get("display_name"),
            is_configured=cfg.get("is_configured", False),
            auth_method=cfg.get("auth_method", "none"),
            has_google_oauth=bool(cfg.get("google_refresh_token")),
            google_email=cfg.get("google_email"),
            has_imap_password=bool(cfg.get("encrypted_password")),
            oauth_connected_at=cfg.get("oauth_connected_at"),
            last_sync_at=cfg.get("last_sync_at"),
            total_emails_synced=cfg.get("total_emails_synced", 0),
            updated_at=cfg.get("updated_at"),
        ))

    return SharedEmailConfigListResponse(configs=response_list, total=len(response_list))


# ====================================================================
# GOOGLE OAUTH CALLBACK — ANTES de /{role} para evitar conflito de rotas
# ====================================================================

@router.get("/google/callback")
async def shared_email_google_callback(
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
                <script>
                    if (window.opener) {{
                        window.opener.postMessage({{ type: 'shared_google_oauth_error', error: '{error}' }}, '*');
                    }}
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
        redirect_uri = google_cfg["redirect_uri"]
        email_address = None
        admin_user_id = None

        if state:
            stored_state = await db.oauth_states.find_one({"state": state})
            if stored_state:
                shared_role = stored_state.get("shared_role")
                admin_user_id = stored_state.get("user_id")
                redirect_uri = stored_state.get("redirect_uri") or google_cfg["redirect_uri"]
                email_address = stored_state.get("email_address")
                await db.oauth_states.delete_one({"_id": stored_state["_id"]})

        if not shared_role:
            logger.warning("[Shared Email OAuth] Callback sem shared_role no state — ignorar")
            return HTMLResponse(
                content="<html><body><p>Erro: Estado de autenticação inválido.</p></body></html>",
                status_code=400,
            )

        if not redirect_uri:
            redirect_uri = _build_redirect_uri(request, "")

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
                <p>Pode fechar esta janela.</p>
                <script>
                    if (window.opener) {{
                        window.opener.postMessage({{
                            type: 'shared_google_oauth_success',
                            role: '{shared_role}',
                            email: '{google_email or email_address or ""}',
                            has_refresh_token: {str(bool(refresh_token)).lower()}
                        }}, '*');
                    }}
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


# ====================================================================
# ENDPOINTS POR ROLE (depois de /google/callback para evitar conflito)
# ====================================================================

@router.get("/{role}", response_model=SharedEmailConfigResponse)
async def get_shared_email_config(
    role: str,
    current_user: dict = Depends(get_current_user),
):
    """Obter configuração de email partilhado para um role."""
    _require_admin(current_user)

    if role not in ALLOWED_ROLES:
        raise HTTPException(status_code=400, detail=f"Role '{role}' não permitido. Roles: {ALLOWED_ROLES}")

    cfg = await db.shared_role_email_configs.find_one({"role": role}, {"_id": 0})
    if not cfg:
        return SharedEmailConfigResponse(role=role)

    return SharedEmailConfigResponse(
        role=cfg.get("role", role),
        email_address=cfg.get("email_address"),
        display_name=cfg.get("display_name"),
        is_configured=cfg.get("is_configured", False),
        auth_method=cfg.get("auth_method", "none"),
        has_google_oauth=bool(cfg.get("google_refresh_token")),
        google_email=cfg.get("google_email"),
        has_imap_password=bool(cfg.get("encrypted_password")),
        oauth_connected_at=cfg.get("oauth_connected_at"),
        last_sync_at=cfg.get("last_sync_at"),
        total_emails_synced=cfg.get("total_emails_synced", 0),
        updated_at=cfg.get("updated_at"),
    )


@router.put("/{role}", response_model=SharedEmailConfigResponse)
async def upsert_shared_email_config(
    role: str,
    payload: SharedEmailConfigCreate,
    current_user: dict = Depends(get_current_user),
):
    """Criar ou atualizar configuração de email partilhado (IMAP/SMTP)."""
    _require_admin(current_user)

    if role not in ALLOWED_ROLES:
        raise HTTPException(status_code=400, detail=f"Role '{role}' não permitido. Roles: {ALLOWED_ROLES}")

    existing = await db.shared_role_email_configs.find_one({"role": role}, {"_id": 0})

    now = datetime.now(timezone.utc).isoformat()

    update_data = {
        "role": role,
        "email_address": payload.email_address,
        "display_name": payload.display_name or f"Email {role}",
        "imap_server": payload.imap_server,
        "imap_port": payload.imap_port,
        "smtp_server": payload.smtp_server,
        "smtp_port": payload.smtp_port,
        "updated_at": now,
    }

    # Encriptar password se fornecida (não apaga a existente se vazio)
    if payload.encrypted_password:
        if not payload.encrypted_password.startswith("ENC:"):
            update_data["encrypted_password"] = encryption_service.encrypt(payload.encrypted_password)
        else:
            update_data["encrypted_password"] = payload.encrypted_password

    # Se já existe, preservar campos OAuth
    if existing:
        update_data.setdefault("google_refresh_token", existing.get("google_refresh_token", ""))
        update_data.setdefault("google_email", existing.get("google_email", ""))
        update_data.setdefault("auth_method", existing.get("auth_method", "none"))
        update_data.setdefault("oauth_connected_at", existing.get("oauth_connected_at", ""))
        update_data.setdefault("total_emails_synced", existing.get("total_emails_synced", 0))

    # Determinar se está configurado
    has_oauth = bool(update_data.get("google_refresh_token"))
    has_imap = bool(update_data.get("encrypted_password"))
    update_data["is_configured"] = has_oauth or has_imap
    if has_oauth:
        update_data["auth_method"] = "google_oauth"
    elif has_imap:
        update_data["auth_method"] = "imap_smtp"

    await db.shared_role_email_configs.update_one(
        {"role": role},
        {"$set": update_data},
        upsert=True,
    )

    # Audit log
    await db.audit_logs.insert_one({
        "action": "shared_email_config_updated",
        "user_id": current_user["id"],
        "details": {"role": role, "auth_method": update_data["auth_method"]},
        "created_at": now,
    })

    logger.info(f"[Shared Email] Config atualizada para role '{role}' por {current_user['id']}")

    return SharedEmailConfigResponse(
        **update_data,
        has_google_oauth=has_oauth,
        has_imap_password=has_imap,
    )


@router.delete("/{role}")
async def delete_shared_email_config(
    role: str,
    current_user: dict = Depends(get_current_user),
):
    """Remover configuração de email partilhado."""
    _require_admin(current_user)

    result = await db.shared_role_email_configs.delete_one({"role": role})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail=f"Config para role '{role}' não encontrada")

    logger.info(f"[Shared Email] Config removida para role '{role}' por {current_user['id']}")

    return {"success": True, "message": f"Config para role '{role}' removida"}


# ====================================================================
# GOOGLE OAUTH ENDPOINTS
# ====================================================================

@router.get("/{role}/google/login", response_model=SharedEmailOAuthLoginResponse)
async def shared_email_google_login(
    role: str,
    request: Request,
    current_user: dict = Depends(get_current_user),
    email_address: Optional[str] = Query(None),
):
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

        redirect_uri = _build_redirect_uri(request, google_cfg["redirect_uri"])

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


@router.delete("/{role}/google")
async def shared_email_google_disconnect(
    role: str,
    current_user: dict = Depends(get_current_user),
):
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


@router.post("/{role}/sync")
async def shared_email_manual_sync(
    role: str,
    current_user: dict = Depends(get_current_user),
    days: int = Query(3, ge=1, le=30),
):
    """Sincronização manual via Gmail API para a caixa partilhada de um role."""
    _require_admin(current_user)

    if role not in ALLOWED_ROLES:
        raise HTTPException(status_code=400, detail=f"Role '{role}' não permitido")

    from services.gmail_api_service import gmail_api_sync_to_db

    result = await gmail_api_sync_to_db(role=role, days=days, max_emails=200)

    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error", "Erro na sincronização"))

    return result

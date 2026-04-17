"""
====================================================================
ROTAS DE UTILIZADORES - CREDITOIMO
====================================================================
Endpoints de leitura para utilizadores do sistema.
CRUD de admin está em admin.py
====================================================================
"""
from typing import List
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException

from database import db
from models.auth import UserRole, UserResponse
from models.email_config import EmailConfigCreate, EmailConfigResponse, EmailConfigTestResult
from services.auth import require_staff, get_current_user


router = APIRouter(prefix="/users", tags=["Users"])

# Roles que usam exclusivamente config partilhada do departamento
FORCED_SHARED_ROLES = {"indexacao", "suporte"}


@router.get("", response_model=List[UserResponse])
async def get_users(role: str = None, user: dict = Depends(require_staff())):
    """
    Listar utilizadores do sistema.
    Filtro opcional por papel (role).
    """
    query = {}
    if role:
        query["role"] = role
    
    users = await db.users.find(query, {"_id": 0, "password": 0}).to_list(500)
    return users


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(user_id: str, user: dict = Depends(require_staff())):
    """Obter utilizador por ID."""
    found_user = await db.users.find_one({"id": user_id}, {"_id": 0, "password": 0})
    if not found_user:
        raise HTTPException(status_code=404, detail="Utilizador não encontrado")
    return found_user


@router.get("/me/email-config")
async def get_my_email_config(current_user: dict = Depends(get_current_user)):
    """
    Obter configuração de email do utilizador logado.
    NUNCA devolve a password real nem o refresh_token — apenas flags booleanas.

    HERANÇA (Caminho da Configuração):
      1. User Config (email_config embedded no user)
      2. Company Config (company_email_configs — servidores padrão)
      3. System Config (system_config.email — globals)

    BLOQUEIO:
      - Utilizadores com role 'indexacao' usam SEMPRE o SharedRoleEmailConfig
        do departamento. Qualquer config individual é ignorada.
    """
    from services.email_config_resolver import resolve_email_config

    user_id = current_user["id"]
    user_role = current_user.get("role", "")

    # Para roles forçados, retornar info do shared role config
    if user_role in FORCED_SHARED_ROLES:
        resolved = await resolve_email_config(user_id)
        return {
            "config_source": resolved.get("config_source", "none"),
            "is_configured": resolved.get("has_password") or resolved.get("has_google_oauth"),
            "email_address": resolved.get("email_address"),
            "imap_server": resolved.get("imap_server"),
            "imap_port": resolved.get("imap_port", 993),
            "smtp_server": resolved.get("smtp_server"),
            "smtp_port": resolved.get("smtp_port", 465),
            "has_password": resolved.get("has_password", False),
            "has_google_oauth": resolved.get("has_google_oauth", False),
            "auth_method": resolved.get("auth_method", "none"),
            "google_email": resolved.get("google_email"),
            "oauth_connected_at": resolved.get("oauth_connected_at"),
            "shared_role": user_role,
            "managed_centralized": True,
            "company_name": resolved.get("company_name"),
            "display_name": resolved.get("display_name"),
        }

    # Usar o resolver para seguir o caminho de herança
    resolved = await resolve_email_config(user_id)
    source = resolved.get("config_source", "none")

    return {
        "config_source": source,
        "is_configured": resolved.get("has_password") or resolved.get("has_google_oauth"),
        "email_address": resolved.get("email_address"),
        "imap_server": resolved.get("imap_server"),
        "imap_port": resolved.get("imap_port", 993),
        "smtp_server": resolved.get("smtp_server"),
        "smtp_port": resolved.get("smtp_port", 465),
        "has_password": resolved.get("has_password", False),
        "has_google_oauth": resolved.get("has_google_oauth", False),
        "auth_method": resolved.get("auth_method", "none"),
        "google_email": resolved.get("google_email"),
        "oauth_connected_at": resolved.get("oauth_connected_at"),
        "company_name": resolved.get("company_name"),
    }


@router.post("/me/email-config")
async def save_my_email_config(
    config: EmailConfigCreate,
    current_user: dict = Depends(get_current_user)
):
    """
    Guardar configuração de email do utilizador.
    A password é encriptada ANTES de ser guardada.
    Se a password não for fornecida, mantém a existente (se houver).

    BLOQUEIO:
      - Utilizadores com role 'indexacao' não podem guardar config individual.
        A config é gerida centralmente pelo administrador.
    """
    from services.encryption import encryption_service

    user_id = current_user["id"]
    user_role = current_user.get("role", "")

    # ==================================================================
    # BLOQUEIO: Roles com config gerida centralmente
    # ==================================================================
    if user_role in FORCED_SHARED_ROLES:
        raise HTTPException(
            status_code=403,
            detail=(
                f"O seu acesso ao email é gerido centralmente pelo departamento. "
                f"Contacte o Administrador para alterações na configuração de email."
            ),
        )

    # Buscar config existente para preservar password se não fornecida
    existing_user = await db.users.find_one(
        {"id": user_id},
        {"_id": 0, "email_config": 1}
    )
    existing_config = (existing_user or {}).get("email_config", {})

    # Encriptar a password (ou manter a existente)
    if config.password:
        encrypted_password = encryption_service.encrypt(config.password)
    elif existing_config.get("encrypted_password"):
        encrypted_password = existing_config["encrypted_password"]
    else:
        encrypted_password = ""

    email_config = {
        "email_address": config.email_address.strip().lower(),
        "imap_server": config.imap_server.strip(),
        "imap_port": config.imap_port,
        "smtp_server": config.smtp_server.strip(),
        "smtp_port": config.smtp_port,
        "encrypted_password": encrypted_password,
        "is_configured": True,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    
    # Preservar campos Google OAuth existentes (não os apagar ao guardar IMAP)
    if existing_config.get("google_refresh_token"):
        email_config["google_refresh_token"] = existing_config["google_refresh_token"]
    if existing_config.get("google_access_token"):
        email_config["google_access_token"] = existing_config["google_access_token"]
    if existing_config.get("google_email"):
        email_config["google_email"] = existing_config["google_email"]
    if existing_config.get("auth_method"):
        email_config["auth_method"] = existing_config["auth_method"]
    if existing_config.get("oauth_connected_at"):
        email_config["oauth_connected_at"] = existing_config["oauth_connected_at"]

    result = await db.users.update_one(
        {"id": user_id},
        {"$set": {"email_config": email_config}}
    )

    if result.modified_count == 0:
        raise HTTPException(status_code=500, detail="Erro ao guardar configuração")

    return {
        "success": True,
        "message": "Configuração guardada com sucesso",
        "is_configured": True,
    }


@router.post("/me/email-config/test")
async def test_my_email_config(
    current_user: dict = Depends(get_current_user)
):
    """
    Testar ligação de email do utilizador (Smart).
    Se tem Google OAuth → testa Gmail API.
    Se tem password IMAP/SMTP → testa IMAP/SMTP.

    Para roles 'indexacao', testa a config partilhada do departamento.
    """
    from services.gmail_oauth import test_connection_smart
    from services.email_config_resolver import resolve_email_config_for_sync

    user_id = current_user["id"]
    user_role = current_user.get("role", "")

    # Para roles com config partilhada, usar a config resolvida
    if user_role in FORCED_SHARED_ROLES:
        resolved = await resolve_email_config_for_sync(user_id)
        if not resolved:
            raise HTTPException(
                status_code=400,
                detail="Configuração de email do departamento não disponível. Contacte o Administrador."
            )
        # Construir config no formato esperado por test_connection_smart
        test_config = {
            "email_address": resolved.get("email_address"),
            "imap_server": resolved.get("imap_server"),
            "imap_port": resolved.get("imap_port", 993),
            "smtp_server": resolved.get("smtp_server"),
            "smtp_port": resolved.get("smtp_port", 465),
            "encrypted_password": resolved.get("encrypted_password", ""),
            "google_refresh_token": resolved.get("google_refresh_token"),
        }
        return await test_connection_smart(test_config, user_id)

    # Para utilizadores normais, usar config individual
    user = await db.users.find_one(
        {"id": user_id},
        {"_id": 0, "email_config": 1}
    )

    if not user or not user.get("email_config"):
        raise HTTPException(status_code=400, detail="Configuração de email não encontrada")

    config = user["email_config"]
    return await test_connection_smart(config, user_id)

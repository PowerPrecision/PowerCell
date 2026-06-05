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
from fastapi import APIRouter, Depends, HTTPException, Request

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
    from services.role_query import build_deep_role_query
    query = {}
    if role:
        query = build_deep_role_query(query, role=role)
    
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
async def get_my_email_config(
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """
    Obter configuração de email do utilizador logado.
    NUNCA devolve a password real nem o refresh_token — apenas flags booleanas.

    Suporta per-role configs: lê X-Active-Role header para determinar
    qual sub-config retornar (fallback para "default" ou config flat).

    HERANÇA (Caminho da Configuração):
      1. User Config (email_config embedded no user)
      2. Company Config (company_email_configs — servidores padrão)
      3. System Config (system_config.email — globals)

    BLOQUEIO:
      - Utilizadores com role 'indexacao' usam SEMPRE o SharedRoleEmailConfig
        do departamento. Qualquer config individual é ignorada.
    """
    from services.email_config_resolver import resolve_email_config
    from services.auth import get_active_company_id_async

    user_id = current_user["id"]
    user_role = current_user.get("role", "")

    # Determine the active role for per-role email config lookup
    active_role_header = request.headers.get("X-Active-Role", "")
    # If active role matches the user's primary role, use "default"
    if active_role_header and active_role_header != user_role:
        active_role = active_role_header
    else:
        active_role = None  # Resolver will use "default" / flat fallback

    # Determinar empresa ativa (X-Company-Id header ou fallback)
    active_company_id = await get_active_company_id_async(request, current_user)

    # Para roles forçados, retornar info do shared role config
    if user_role in FORCED_SHARED_ROLES:
        resolved = await resolve_email_config(user_id, active_role=active_role, active_company_id=active_company_id)
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
    resolved = await resolve_email_config(user_id, active_role=active_role, active_company_id=active_company_id)
    source = resolved.get("config_source", "none")

    # MULTI-EMPRESA: listar company_ids disponíveis na config do user
    existing_user_doc = await db.users.find_one(
        {"id": user_id},
        {"_id": 0, "email_config": 1}
    )
    raw_ec = (existing_user_doc or {}).get("email_config", {})
    available_companies = []
    if isinstance(raw_ec, dict):
        for key in raw_ec.keys():
            if key.startswith("company:"):
                available_companies.append(key.replace("company:", ""))
            elif key == "default":
                available_companies.append("default")

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
        "company_id": "default",
        "available_companies": available_companies,
    }


@router.post("/me/email-config")
async def save_my_email_config(
    request: Request,
    config: EmailConfigCreate,
    current_user: dict = Depends(get_current_user),
):
    """
    Guardar configuração de email do utilizador.
    A password é encriptada ANTES de ser guardada.
    Se a password não for fornecida, mantém a existente (se houver).

    Suporta per-role configs: lê X-Active-Role header para determinar
    sob qual chave guardar (e.g. email_config.consultor).

    BLOQUEIO:
      - Utilizadores com role 'indexacao' não podem guardar config individual.
        A config é gerida centralmente pelo administrador.
    """
    from services.encryption import encryption_service
    from services.email_config_resolver import (
        _is_nested_email_config, _extract_role_email_config,
    )

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

    # Determine the role key for storage
    active_role_header = request.headers.get("X-Active-Role", "")
    if active_role_header and active_role_header != user_role:
        storage_role = active_role_header
    else:
        storage_role = "default"

    # MULTI-EMPRESA: Incorporar company_id na chave de armazenamento.
    # Se company_id for fornecido e não for "default", a chave passa a ser
    # "company:<company_id>" em vez de "default" ou do role.
    # Isto permite que um utilizador tenha configs diferentes por empresa.
    company_id = config.company_id or "default"
    if company_id != "default":
        storage_key = f"company:{company_id}"
    else:
        storage_key = storage_role

    # Buscar config existente para preservar password se não fornecida
    existing_user = await db.users.find_one(
        {"id": user_id},
        {"_id": 0, "email_config": 1}
    )
    raw_existing = (existing_user or {}).get("email_config", {})

    # Normalize existing config: if flat, wrap as {"default": ...}
    if raw_existing and not _is_nested_email_config(raw_existing):
        nested_existing = {"default": raw_existing}
    elif raw_existing:
        nested_existing = raw_existing
    else:
        nested_existing = {}

    # Get existing config for THIS key (to preserve password / OAuth tokens)
    existing_role_config = _extract_role_email_config(
        nested_existing, storage_key
    ) if storage_key != "default" else nested_existing.get("default", {})

    # Encriptar a password (ou manter a existente do role)
    if config.password:
        encrypted_password = encryption_service.encrypt(config.password)
    elif existing_role_config.get("encrypted_password"):
        encrypted_password = existing_role_config["encrypted_password"]
    else:
        encrypted_password = ""

    new_role_config = {
        "email_address": config.email_address.strip().lower(),
        "imap_server": config.imap_server.strip(),
        "imap_port": config.imap_port,
        "smtp_server": config.smtp_server.strip(),
        "smtp_port": config.smtp_port,
        "encrypted_password": encrypted_password,
        "company_id": company_id,  # MULTI-EMPRESA: associação à empresa
        "is_configured": True,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    # Preservar campos Google OAuth existentes do role (não os apagar ao guardar IMAP)
    if existing_role_config.get("google_refresh_token"):
        new_role_config["google_refresh_token"] = existing_role_config["google_refresh_token"]
    if existing_role_config.get("google_access_token"):
        new_role_config["google_access_token"] = existing_role_config["google_access_token"]
    if existing_role_config.get("google_email"):
        new_role_config["google_email"] = existing_role_config["google_email"]
    if existing_role_config.get("auth_method"):
        new_role_config["auth_method"] = existing_role_config["auth_method"]
    if existing_role_config.get("oauth_connected_at"):
        new_role_config["oauth_connected_at"] = existing_role_config["oauth_connected_at"]

    # Store under the storage key in the nested structure
    nested_existing[storage_key] = new_role_config

    result = await db.users.update_one(
        {"id": user_id},
        {"$set": {"email_config": nested_existing}}
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
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """
    Testar ligação de email do utilizador (Smart).
    Se tem Google OAuth → testa Gmail API.
    Se tem password IMAP/SMTP → testa IMAP/SMTP.

    Suporta per-role configs: lê X-Active-Role header para determinar
    qual sub-config testar.

    Para roles 'indexacao', testa a config partilhada do departamento.
    """
    from services.gmail_oauth import test_connection_smart
    from services.email_config_resolver import (
        resolve_email_config_for_sync,
        _is_nested_email_config,
        _extract_role_email_config,
    )
    from services.auth import get_active_company_id_async

    user_id = current_user["id"]
    user_role = current_user.get("role", "")

    # Determine the active role for per-role email config lookup
    active_role_header = request.headers.get("X-Active-Role", "")
    if active_role_header and active_role_header != user_role:
        active_role = active_role_header
    else:
        active_role = None

    # Determinar empresa ativa
    active_company_id = await get_active_company_id_async(request, current_user)

    # Para roles com config partilhada, usar a config resolvida
    if user_role in FORCED_SHARED_ROLES:
        resolved = await resolve_email_config_for_sync(user_id, active_role=active_role, active_company_id=active_company_id)
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

    # Para utilizadores normais, usar config individual (role-aware)
    resolved = await resolve_email_config_for_sync(user_id, active_role=active_role, active_company_id=active_company_id)
    if not resolved:
        raise HTTPException(status_code=400, detail="Configuração de email não encontrada")

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

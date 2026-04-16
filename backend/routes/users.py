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
    Inclui has_google_oauth para indicar se a conta está ligada via Google OAuth.
    """
    user_id = current_user["id"]
    user = await db.users.find_one(
        {"id": user_id},
        {"_id": 0, "email_config": 1}
    )
    if not user or not user.get("email_config"):
        return {
            "is_configured": False,
            "email_address": None,
            "imap_server": None,
            "imap_port": None,
            "smtp_server": None,
            "smtp_port": None,
            "has_password": False,
            "has_google_oauth": False,
            "auth_method": "none",
            "google_email": None,
        }
    
    config = user["email_config"]
    has_oauth = bool(config.get("google_refresh_token"))
    has_password = bool(config.get("encrypted_password"))
    
    # Determinar auth_method
    if has_oauth:
        auth_method = "google_oauth"
    elif has_password:
        auth_method = "imap_smtp"
    else:
        auth_method = "none"
    
    return {
        "is_configured": config.get("is_configured", False) or has_oauth or has_password,
        "email_address": config.get("email_address"),
        "imap_server": config.get("imap_server"),
        "imap_port": config.get("imap_port", 993),
        "smtp_server": config.get("smtp_server"),
        "smtp_port": config.get("smtp_port", 465),
        "has_password": has_password,
        "has_google_oauth": has_oauth,
        "auth_method": auth_method,
        "google_email": config.get("google_email"),
        "oauth_connected_at": config.get("oauth_connected_at"),
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
    """
    from services.encryption import encryption_service

    user_id = current_user["id"]

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
    """
    from services.gmail_oauth import test_connection_smart

    user_id = current_user["id"]
    user = await db.users.find_one(
        {"id": user_id},
        {"_id": 0, "email_config": 1}
    )

    if not user or not user.get("email_config"):
        raise HTTPException(status_code=400, detail="Configuração de email não encontrada")

    config = user["email_config"]
    return await test_connection_smart(config, user_id)

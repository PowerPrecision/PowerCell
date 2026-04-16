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
    NUNCA devolve a password — apenas has_password: true.
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
        }
    
    config = user["email_config"]
    return {
        "is_configured": config.get("is_configured", False),
        "email_address": config.get("email_address"),
        "imap_server": config.get("imap_server"),
        "imap_port": config.get("imap_port", 993),
        "smtp_server": config.get("smtp_server"),
        "smtp_port": config.get("smtp_port", 465),
        "has_password": bool(config.get("encrypted_password")),
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
    Testar ligação IMAP/SMTP do utilizador.
    Usa as credenciais encriptadas guardadas.
    """
    import imaplib
    import smtplib
    import ssl
    import certifi
    from services.encryption import encryption_service
    
    user_id = current_user["id"]
    user = await db.users.find_one(
        {"id": user_id},
        {"_id": 0, "email_config": 1}
    )
    
    if not user or not user.get("email_config"):
        raise HTTPException(status_code=400, detail="Configuração de email não encontrada")
    
    config = user["email_config"]
    encrypted_password = config.get("encrypted_password", "")
    
    if not encrypted_password:
        raise HTTPException(status_code=400, detail="Password não configurada. Guarda a configuração com password primeiro.")
    
    # Desencriptar a password
    password = encryption_service.decrypt(encrypted_password)
    
    # Verificar se a desencriptação falhou (password ainda está encriptada)
    if password.startswith("ENC:"):
        raise HTTPException(
            status_code=400,
            detail="Erro ao desencriptar a password. A chave de encriptação pode ter mudado. Guarda a password novamente."
        )
    
    if not password:
        raise HTTPException(status_code=400, detail="Password desencriptada está vazia. Guarda a password novamente.")
    
    # SSL context com certifi para certificados atualizados (Render)
    ssl_context = ssl.create_default_context(cafile=certifi.where())
    
    # Test IMAP
    imap_ok = False
    smtp_ok = False
    error = None
    
    try:
        imap_port = config.get("imap_port", 993)
        if not imap_port:
            imap_port = 993
        mail = imaplib.IMAP4_SSL(
            config["imap_server"],
            int(imap_port),
            ssl_context=ssl_context
        )
        mail.login(config["email_address"], password)
        mail.logout()
        imap_ok = True
    except Exception as e:
        error = f"IMAP: {str(e)}"
    
    # Test SMTP
    try:
        smtp_port = config.get("smtp_port", 465)
        if not smtp_port:
            smtp_port = 465
        with smtplib.SMTP_SSL(
            config["smtp_server"],
            int(smtp_port),
            context=ssl_context,
            timeout=15
        ) as server:
            server.login(config["email_address"], password)
        smtp_ok = True
    except Exception as e:
        if error:
            error += f" | SMTP: {str(e)}"
        else:
            error = f"SMTP: {str(e)}"
    
    return {
        "success": imap_ok and smtp_ok,
        "imap_connected": imap_ok,
        "smtp_connected": smtp_ok,
        "error": error,
    }

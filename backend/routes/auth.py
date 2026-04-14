import uuid
import re
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Request, Response, HTTPException
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

from database import db
from models.auth import (
    UserRole, UserRegister, UserLogin, UserResponse, TokenResponse
)
from services.auth import (
    hash_password, verify_password, create_token, get_current_user,
    validate_password_strength
)
from utils.input_sanitization import (
    sanitize_string, log_sanitization_rejection
)
from middleware.rate_limit import limiter
from services.refresh_token_service import (
    create_access_token,
    create_refresh_token_db,
    rotate_refresh_token,
    revoke_refresh_token,
    revoke_all_user_tokens,
    get_active_sessions,
    ACCESS_TOKEN_EXPIRE_MINUTES,
)


router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/register", response_model=TokenResponse)
@limiter.limit("3/hour")
async def register(request: Request, response: Response, data: UserRegister):
    """Regista um novo utilizador a partir do formulário público.

    Este endpoint é acessível sem autenticação e permite que novos
    utilizadores se registem no sistema. O role padrão é CLIENTE.

    Porquê sem autenticação: este é o ponto de entrada para novos
    utilizadores que ainda não têm conta. A validação é feita via
    campos obrigatórios (email, nome) e verificação de unicidade.

    Args:
        request: Objeto Request do FastAPI (para definir cookies).
        response: Objeto Response do FastAPI (para definir cookies).
        data: Dados de registo (UserRegister com email, name, phone, password).

    Returns:
        dict: Dados do utilizador registado com access_token.

    Raises:
        HTTPException(400): Se email em falta, já existe, ou dados inválidos.
    """
    # Normalizar inputs (sem validação de formato)
    clean_email = (data.email or "").strip().lower()
    if not clean_email:
        raise HTTPException(status_code=400, detail="Email é obrigatório")
    
    clean_name = (data.name or "").strip()
    clean_phone = (data.phone or "").strip() if data.phone else None
    
    existing = await db.users.find_one({"email": clean_email})
    if existing:
        raise HTTPException(status_code=400, detail="Email já registado")
    
    # Validar força da password
    is_valid, error_msg = validate_password_strength(data.password)
    if not is_valid:
        raise HTTPException(status_code=400, detail=error_msg)
    
    user_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    
    user_doc = {
        "id": user_id,
        "email": clean_email,
        "password": hash_password(data.password),
        "name": clean_name,
        "phone": clean_phone,
        "role": UserRole.CLIENTE,
        "is_active": True,
        "onedrive_folder": clean_name,
        "created_at": now
    }
    
    await db.users.insert_one(user_doc)
    token = create_token(user_id, clean_email, UserRole.CLIENTE)
    
    return TokenResponse(
        access_token=token,
        user=UserResponse(
            id=user_id,
            email=clean_email,
            name=clean_name,
            phone=clean_phone,
            role=UserRole.CLIENTE,
            created_at=now,
            onedrive_folder=clean_name
        )
    )


@router.post("/login", deprecated=True)
@limiter.limit("10/minute")
async def login(request: Request, data: UserLogin, response: Response):
    """
    DEPRECATED: Esta rota foi descontinuada.
    Utilize /auth/login-v2 para autenticação segura com refresh tokens.
    
    Esta rota será removida em futuras versões.
    """
    raise HTTPException(
        status_code=410, 
        detail="Esta rota de login foi descontinuada. Utilize /auth/login-v2 para autenticação segura com refresh tokens."
    )


@router.get("/me")
async def get_me(user: dict = Depends(get_current_user)):
    """Retorna o utilizador atual incluindo info de impersonate e permissões se aplicável.
    
    Sincroniza as permissões com as defaults do role em cada request,
    garantindo que alterações a DEFAULT_PERMISSIONS_BY_ROLE são refletidas
    imediatamente para todos os utilizadores (resolve permissões legacy).
    """
    from services.permissions import get_default_permissions_for_role, sync_permissions_with_role_defaults
    
    # Sincronizar permissões: garantir que actions novas no role são adicionadas
    user_perms = user.get("permissions")
    role = user.get("role", "cliente")
    synced_perms = sync_permissions_with_role_defaults(user_perms, role)
    
    # Verificar se houve alterações (nova action adicionada) e persistir
    if user_perms is not None and synced_perms != user_perms:
        try:
            await db.users.update_one(
                {"id": user["id"]},
                {"$set": {"permissions": synced_perms}}
            )
        except Exception:
            pass  # Falha silenciosa — não bloqueia o request
    
    response = {
        "id": user["id"],
        "email": user["email"],
        "name": user["name"],
        "phone": user.get("phone"),
        "role": user["role"],
        "created_at": user["created_at"],
        "onedrive_folder": user.get("onedrive_folder"),
        "is_active": user.get("is_active", True),
        "permissions": synced_perms,
        "additional_roles": user.get("additional_roles", [])
    }
    
    # Incluir informação de impersonate se presente
    if user.get("is_impersonated"):
        response["is_impersonated"] = True
        response["impersonated_by"] = user.get("impersonated_by")
        response["impersonated_by_name"] = user.get("impersonated_by_name")
    
    return response



@router.put("/preferences")
async def update_preferences(
    data: dict,
    user: dict = Depends(get_current_user)
):
    """
    Atualiza as preferências de notificação do utilizador.
    Sanitiza todas as chaves e valores string para prevenir stored XSS.
    """
    user_id = user["id"]
    
    # Extrair preferências de notificação
    notifications = data.get("notifications", {})
    
    # Sanitizar: apenas permitir chaves esperadas e limpar valores
    ALLOWED_NOTIFICATION_KEYS = {
        "email_new_process", "email_status_change", "email_document_upload",
        "email_task_assigned", "email_deadline_reminder", "email_urgent_only",
        "email_daily_summary", "email_weekly_report",
        "inapp_new_process", "inapp_status_change", "inapp_document_upload",
        "inapp_task_assigned", "inapp_comments",
        "is_test_user"
    }
    
    sanitized_notifications = {}
    for key, value in notifications.items():
        # Rejeitar chaves não esperadas (previne injection de campos arbitrários)
        if key not in ALLOWED_NOTIFICATION_KEYS:
            log_sanitization_rejection(f"preferences.{key}", str(key), "chave de notificação não permitida")
            continue
        # Valores devem ser booleanos
        if isinstance(value, bool):
            sanitized_notifications[key] = value
        elif isinstance(value, str):
            # Strings: aceitar apenas "true"/"false"
            sanitized_notifications[key] = value.lower() in ("true", "1", "yes")
        else:
            sanitized_notifications[key] = bool(value)
    
    update_data = {
        "notification_preferences": sanitized_notifications,
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    
    result = await db.users.update_one(
        {"id": user_id},
        {"$set": update_data}
    )
    
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Utilizador não encontrado")
    
    return {"success": True, "message": "Preferências atualizadas"}


@router.get("/preferences")
async def get_preferences(user: dict = Depends(get_current_user)):
    """
    Retorna as preferências de notificação do utilizador atual.
    """
    user_data = await db.users.find_one({"id": user["id"]}, {"_id": 0, "notification_preferences": 1})
    
    notifications = user_data.get("notification_preferences", {}) if user_data else {}
    
    return {"notifications": notifications}


@router.put("/profile")
async def update_profile(
    data: dict,
    user: dict = Depends(get_current_user)
):
    """
    Permite ao utilizador atualizar o seu próprio perfil (nome e telefone).
    """
    user_id = user["id"]
    
    # Campos permitidos para actualização pelo próprio utilizador
    allowed_fields = ["name", "phone"]
    update_data = {}
    
    for field in allowed_fields:
        if field in data and data[field] is not None:
            # Aceitar qualquer valor — sem validação de formato
            update_data[field] = str(data[field]).strip()
    
    if not update_data:
        raise HTTPException(status_code=400, detail="Nenhum campo válido para atualizar")
    
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    
    result = await db.users.update_one(
        {"id": user_id},
        {"$set": update_data}
    )
    
    if result.modified_count == 0 and result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Utilizador não encontrado")
    
    # Retornar o utilizador actualizado
    updated_user = await db.users.find_one({"id": user_id}, {"_id": 0, "password": 0})
    
    return {
        "success": True,
        "message": "Perfil atualizado com sucesso",
        "user": updated_user
    }


@router.post("/change-password")
async def change_password(
    data: dict,
    user: dict = Depends(get_current_user)
):
    """
    Permite ao utilizador alterar a sua própria password.
    """
    current_password = data.get("current_password")
    new_password = data.get("new_password")
    
    if not current_password or not new_password:
        raise HTTPException(status_code=400, detail="Password atual e nova password são obrigatórias")
    
    # Validar força da nova password
    is_valid, error_msg = validate_password_strength(new_password)
    if not is_valid:
        raise HTTPException(status_code=400, detail=error_msg)
    
    # Buscar utilizador com password
    user_data = await db.users.find_one({"id": user["id"]})
    if not user_data:
        raise HTTPException(status_code=404, detail="Utilizador não encontrado")
    
    # Verificar password atual
    password_field = user_data.get("password") or user_data.get("hashed_password", "")
    if not verify_password(current_password, password_field):
        raise HTTPException(status_code=400, detail="Password atual incorreta")
    
    # Actualizar password
    new_hashed = hash_password(new_password)
    await db.users.update_one(
        {"id": user["id"]},
        {"$set": {
            "password": new_hashed,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }}
    )
    
    return {"success": True, "message": "Password alterada com sucesso"}


# ====================================================================
# REFRESH TOKENS ENDPOINTS
# ====================================================================

@router.post("/login-v2")
@limiter.limit("10/minute")
async def login_v2(request: Request, data: UserLogin, response: Response):
    """
    Login com suporte a refresh tokens.
    Retorna access_token (2h) + refresh_token (7 dias).
    """
    try:
        # Normalizar email (sem bleach/sanitize_email — simples e seguro)
        clean_email = str(data.email).strip().lower() if data.email else ""
        if not clean_email or "@" not in clean_email:
            logger.warning(f"Login falhou: email vazio ou sem @")
            raise HTTPException(status_code=401, detail="Credenciais inválidas")
        
        # Case-insensitive query (MongoDB é case-sensitive por default)
        user = await db.users.find_one(
            {"email": {"$regex": f"^{clean_email}$", "$options": "i"}},
            {"_id": 0}
        )
        if not user:
            logger.warning(f"Login falhou: utilizador não encontrado para email={clean_email}")
            raise HTTPException(status_code=401, detail="Credenciais inválidas")
        
        password_field = user.get("password") or user.get("hashed_password", "")
        if not password_field:
            logger.error(f"Login falhou: utilizador {user['id']} sem password")
            raise HTTPException(status_code=401, detail="Credenciais inválidas")
        
        if not verify_password(data.password, password_field):
            logger.warning(f"Login falhou: password incorrecta para user={user['id']}")
            raise HTTPException(status_code=401, detail="Credenciais inválidas")
        
        if not user.get("is_active", True):
            logger.warning(f"Login falhou: conta desactivada user={user['id']}")
            raise HTTPException(status_code=401, detail="Conta desativada")
        
        logger.info(f"Login bem-sucedido: user={user['id']} email={clean_email} role={user['role']}")
        
        # Sincronizar permissões com defaults do role (resolve permissões legacy)
        from services.permissions import sync_permissions_with_role_defaults
        user_perms = user.get("permissions")
        user_role = user.get("role", "cliente")
        synced_perms = sync_permissions_with_role_defaults(user_perms, user_role)
        if user_perms is not None and synced_perms != user_perms:
            await db.users.update_one(
                {"id": user["id"]},
                {"$set": {"permissions": synced_perms}}
            )
        
        # Criar access token
        access_token = create_access_token(
            user["id"],
            user["email"],
            user["role"]
        )
        
        # Criar refresh token
        device_info = str(request.headers.get("User-Agent", ""))[:200]
        client_host = ""
        try:
            client_host = request.client.host if request.client else ""
        except Exception:
            pass
        ip_address = str(request.headers.get("X-Forwarded-For", client_host))[:45]
        
        _, refresh_token = await create_refresh_token_db(
            user["id"],
            device_info=device_info,
            ip_address=ip_address
        )
        
        return JSONResponse(
            status_code=200,
            content={
                "access_token": access_token,
                "refresh_token": refresh_token,
                "token_type": "bearer",
                "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60,
                "user": {
                    "id": user["id"],
                    "email": user["email"],
                    "name": user["name"],
                    "phone": user.get("phone"),
                    "role": user["role"],
                    "created_at": user["created_at"],
                    "onedrive_folder": user.get("onedrive_folder"),
                    "additional_roles": user.get("additional_roles", [])
                }
            }
        )
    except HTTPException:
        raise  # Re-lançar HTTPExceptions (401, 403, etc.)
    except Exception as e:
        logger.exception(f"Login crash inesperado: {type(e).__name__}: {e}")
        raise HTTPException(status_code=500, detail=f"Erro interno: {type(e).__name__}")


@router.post("/refresh")
async def refresh_tokens(request: Request, data: dict):
    """
    Renova tokens usando refresh token.
    Implementa rotação segura: token antigo é invalidado, novo é criado.
    """
    refresh_token = data.get("refresh_token")
    if not refresh_token:
        raise HTTPException(status_code=400, detail="refresh_token é obrigatório")
    
    device_info = sanitize_string(request.headers.get("User-Agent", ""), max_length=200)
    ip_address = sanitize_string(request.headers.get("X-Forwarded-For", request.client.host if request.client else ""), max_length=45)
    
    result = await rotate_refresh_token(
        refresh_token,
        device_info=device_info,
        ip_address=ip_address
    )
    
    if not result:
        raise HTTPException(status_code=401, detail="Refresh token inválido ou expirado")
    
    _, new_refresh_token, user = result
    
    # Criar novo access token
    access_token = create_access_token(
        user["id"],
        user["email"],
        user["role"]
    )
    
    return {
        "access_token": access_token,
        "refresh_token": new_refresh_token,
        "token_type": "bearer",
        "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    }


@router.post("/logout")
async def logout(data: dict, user: dict = Depends(get_current_user)):
    """
    Logout - revoga refresh token.
    Se refresh_token não fornecido, revoga todos os tokens do utilizador.
    """
    refresh_token = data.get("refresh_token")
    
    if refresh_token:
        # Revogar token específico
        revoked = await revoke_refresh_token(refresh_token)
        return {
            "success": revoked,
            "message": "Token revogado" if revoked else "Token não encontrado ou já revogado"
        }
    else:
        # Revogar todos os tokens do utilizador
        count = await revoke_all_user_tokens(user["id"])
        return {
            "success": True,
            "message": f"{count} sessão(ões) terminada(s)",
            "revoked_count": count
        }


@router.get("/sessions")
async def list_sessions(user: dict = Depends(get_current_user)):
    """
    Lista sessões activas do utilizador.
    """
    sessions = await get_active_sessions(user["id"])
    return {
        "sessions": sessions,
        "total": len(sessions)
    }


@router.delete("/sessions/{session_id}")
async def revoke_session(session_id: str, user: dict = Depends(get_current_user)):
    """
    Revoga uma sessão específica pelo ID.
    """
    # Buscar token pelo ID e verificar se pertence ao utilizador
    token_doc = await db.refresh_tokens.find_one(
        {"id": session_id, "user_id": user["id"]},
        {"_id": 0}
    )
    
    if not token_doc:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")
    
    if token_doc.get("revoked"):
        raise HTTPException(status_code=400, detail="Sessão já terminada")
    
    await db.refresh_tokens.update_one(
        {"id": session_id},
        {
            "$set": {
                "revoked": True,
                "revoked_at": datetime.now(timezone.utc).isoformat()
            }
        }
    )
    
    return {"success": True, "message": "Sessão terminada"}


@router.post("/validate-password")
async def validate_password_endpoint(data: dict):
    """
    Endpoint público para validar a força de uma password.
    Usado pelo frontend para feedback em tempo real.
    """
    password = data.get("password", "")
    
    is_valid, error_msg = validate_password_strength(password)
    
    # Calcular pontuação de força
    score = 0
    feedback = []
    
    if len(password) >= 8:
        score += 20
    else:
        feedback.append("Pelo menos 8 caracteres")
    
    if len(password) >= 12:
        score += 10
    
    if re.search(r'[a-z]', password):
        score += 15
    else:
        feedback.append("Pelo menos uma letra minúscula")
    
    if re.search(r'[A-Z]', password):
        score += 15
    else:
        feedback.append("Pelo menos uma letra maiúscula")
    
    if re.search(r'\d', password):
        score += 15
    else:
        feedback.append("Pelo menos um dígito")
    
    if re.search(r'[@$!%*?&#^()\-_=+\[\]{}|;:,.<>~`]', password):
        score += 25
    else:
        feedback.append("Pelo menos um carácter especial")
    
    # Determinar nível de força
    if score < 40:
        strength = "muito_fraca"
    elif score < 60:
        strength = "fraca"
    elif score < 80:
        strength = "media"
    elif score < 95:
        strength = "forte"
    else:
        strength = "muito_forte"
    
    return {
        "valid": is_valid,
        "error": error_msg if not is_valid else None,
        "score": min(score, 100),
        "strength": strength,
        "feedback": feedback
    }


# ====================================================================
# ENDPOINTS DE DIAGNÓSTICO DE PASSWORDS
# ====================================================================

def _detect_hash_format(hash_value: str) -> str:
    """Detecta o formato de um hash de password."""
    if not hash_value:
        return "empty"
    if hash_value.startswith("$2b$") or hash_value.startswith("$2a$"):
        return "bcrypt"
    if len(hash_value) == 64:
        try:
            int(hash_value, 16)
            return "sha256_broken"
        except ValueError:
            pass
    if len(hash_value) == 32:
        try:
            int(hash_value, 16)
            return "md5"
        except ValueError:
            pass
    return "unknown"


@router.get("/diagnose")
@limiter.limit("5/minute")
async def diagnose_login(request: Request, email: str):
    """
    Diagnóstico público para verificar porque o login falha.
    Diz se o utilizador existe, se está activo, e o formato do hash.

    NÃO revela o hash em si — apenas o formato.
    """
    clean_email = str(email).strip().lower()
    if not clean_email or "@" not in clean_email:
        raise HTTPException(status_code=400, detail="Email inválido")

    user = await db.users.find_one(
        {"email": {"$regex": f"^{clean_email}$", "$options": "i"}},
        {"_id": 0, "id": 1, "email": 1, "name": 1, "role": 1, "password": 1, "hashed_password": 1, "is_active": 1, "created_at": 1}
    )

    if not user:
        return {
            "found": False,
            "email": clean_email,
            "message": "Nenhum utilizador encontrado com este email"
        }

    pw = user.get("password") or user.get("hashed_password", "")
    hash_format = _detect_hash_format(pw)

    return {
        "found": True,
        "email": user.get("email"),
        "name": user.get("name"),
        "role": user.get("role"),
        "is_active": user.get("is_active", True),
        "password_hash_format": hash_format,
        "has_password": bool(pw),
        "diagnosis": {
            "bcrypt": "✅ Formato correcto — o login deve funcionar",
            "sha256_broken": "❌ HASH QUEBRADO — seed_database.py gravou SHA-256 em vez de bcrypt. Usar /auth/fix-passwords para corrigir.",
            "empty": "❌ Utilizador sem password definida",
            "unknown": "⚠️ Formato de hash não reconhecido",
            "md5": "⚠️ Hash MD5 — formato inseguro e incompatível com bcrypt"
        }.get(hash_format, "Formato desconhecido")
    }


@router.post("/fix-passwords")
@limiter.limit("1/minute")
async def fix_broken_passwords(request: Request, data: dict):
    """
    Corrige passwords com hash SHA-256 para bcrypt.
    Como SHA-256 não é reversível, reseta a password para um valor default.
    """
    admin_key = data.get("admin_key")
    if not admin_key or admin_key != "PowerCellFix2025":
        raise HTTPException(status_code=403, detail="Chave de admin inválida")

    target_email = data.get("email")
    if not target_email or "@" not in target_email:
        raise HTTPException(status_code=400, detail="Email obrigatório")

    clean_email = target_email.strip().lower()

    user = await db.users.find_one(
        {"email": {"$regex": f"^{clean_email}$", "$options": "i"}},
        {"_id": 0}
    )
    if not user:
        raise HTTPException(status_code=404, detail="Utilizador não encontrado")

    pw = user.get("password") or user.get("hashed_password", "")
    hash_format = _detect_hash_format(pw)

    if hash_format != "sha256_broken":
        raise HTTPException(
            status_code=400,
            detail=f"Password não está em formato SHA-256 (formato actual: {hash_format}). Não é necessário corrigir."
        )

    # Resetar para password default
    new_password = "PowerCell2025"
    new_hash = hash_password(new_password)

    field = "password" if user.get("password") else "hashed_password"
    await db.users.update_one(
        {"id": user.get("id")},
        {"$set": {
            field: new_hash,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }}
    )

    logger.warning(f"PASSWORD FIX: Utilizador {user.get('id')} ({clean_email}) — SHA-256 → bcrypt (password resetada)")

    return {
        "success": True,
        "email": clean_email,
        "message": f"Password corrigida. Password temporária: {new_password} — alterar imediatamente após login."
    }


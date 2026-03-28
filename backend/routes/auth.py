import uuid
import re
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Request, Response, HTTPException

from database import db
from models.auth import (
    UserRole, UserRegister, UserLogin, UserResponse, TokenResponse
)
from services.auth import (
    hash_password, verify_password, create_token, get_current_user,
    validate_password_strength
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
    existing = await db.users.find_one({"email": data.email})
    if existing:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="Email já registado")
    
    # Validar força da password
    is_valid, error_msg = validate_password_strength(data.password)
    if not is_valid:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=error_msg)
    
    user_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    
    user_doc = {
        "id": user_id,
        "email": data.email,
        "password": hash_password(data.password),
        "name": data.name,
        "phone": data.phone,
        "role": UserRole.CLIENTE,
        "is_active": True,
        "onedrive_folder": data.name,
        "created_at": now
    }
    
    await db.users.insert_one(user_doc)
    token = create_token(user_id, data.email, UserRole.CLIENTE)
    
    return TokenResponse(
        access_token=token,
        user=UserResponse(
            id=user_id,
            email=data.email,
            name=data.name,
            phone=data.phone,
            role=UserRole.CLIENTE,
            created_at=now,
            onedrive_folder=data.name
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
    from fastapi import HTTPException
    raise HTTPException(
        status_code=410, 
        detail="Esta rota de login foi descontinuada. Utilize /auth/login-v2 para autenticação segura com refresh tokens."
    )


@router.get("/me")
async def get_me(user: dict = Depends(get_current_user)):
    """Retorna o utilizador atual incluindo info de impersonate se aplicável."""
    response = {
        "id": user["id"],
        "email": user["email"],
        "name": user["name"],
        "phone": user.get("phone"),
        "role": user["role"],
        "created_at": user["created_at"],
        "onedrive_folder": user.get("onedrive_folder"),
        "is_active": user.get("is_active", True)
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
    """
    user_id = user["id"]
    
    # Extrair preferências de notificação
    notifications = data.get("notifications", {})
    
    update_data = {
        "notification_preferences": notifications,
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    
    result = await db.users.update_one(
        {"id": user_id},
        {"$set": update_data}
    )
    
    if result.modified_count == 0:
        from fastapi import HTTPException
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
    from fastapi import HTTPException
    
    user_id = user["id"]
    
    # Campos permitidos para atualização pelo próprio utilizador
    allowed_fields = ["name", "phone"]
    update_data = {}
    
    for field in allowed_fields:
        if field in data and data[field] is not None:
            update_data[field] = data[field]
    
    if not update_data:
        raise HTTPException(status_code=400, detail="Nenhum campo válido para atualizar")
    
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    
    result = await db.users.update_one(
        {"id": user_id},
        {"$set": update_data}
    )
    
    if result.modified_count == 0 and result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Utilizador não encontrado")
    
    # Retornar o utilizador atualizado
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
    from fastapi import HTTPException
    
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
    
    # Atualizar password
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
    Retorna access_token (15 min) + refresh_token (7 dias).
    """
    user = await db.users.find_one({"email": data.email}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=401, detail="Credenciais inválidas")
    
    password_field = user.get("password") or user.get("hashed_password", "")
    if not verify_password(data.password, password_field):
        raise HTTPException(status_code=401, detail="Credenciais inválidas")
    
    if not user.get("is_active", True):
        raise HTTPException(status_code=401, detail="Conta desativada")
    
    # Criar access token (curto)
    access_token = create_access_token(
        user["id"], 
        user["email"], 
        user["role"]
    )
    
    # Criar refresh token (longo)
    device_info = request.headers.get("User-Agent", "")[:200]
    ip_address = request.headers.get("X-Forwarded-For", request.client.host if request.client else "")
    
    _, refresh_token = await create_refresh_token_db(
        user["id"],
        device_info=device_info,
        ip_address=ip_address
    )
    
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        "user": UserResponse(
            id=user["id"],
            email=user["email"],
            name=user["name"],
            phone=user.get("phone"),
            role=user["role"],
            created_at=user["created_at"],
            onedrive_folder=user.get("onedrive_folder")
        )
    }


@router.post("/refresh")
async def refresh_tokens(request: Request, data: dict):
    """
    Renova tokens usando refresh token.
    Implementa rotação segura: token antigo é invalidado, novo é criado.
    """
    refresh_token = data.get("refresh_token")
    if not refresh_token:
        raise HTTPException(status_code=400, detail="refresh_token é obrigatório")
    
    device_info = request.headers.get("User-Agent", "")[:200]
    ip_address = request.headers.get("X-Forwarded-For", request.client.host if request.client else "")
    
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


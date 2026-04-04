from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Tuple
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
import re
from passlib.context import CryptContext

from config import JWT_SECRET, JWT_ALGORITHM, JWT_EXPIRATION_HOURS
from database import db
from models.auth import UserRole


security = HTTPBearer()

# Password hashing context — unificado com seed.py (passlib)
# Isto resolve incompatibilidade entre bcrypt directo e passlib
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def validate_password_strength(password: str) -> Tuple[bool, str]:
    """
    Valida a força da password.
    
    Requisitos mínimos:
    - Pelo menos 8 caracteres
    - Pelo menos uma letra minúscula
    - Pelo menos uma letra maiúscula
    - Pelo menos um dígito
    - Pelo menos um carácter especial (@$!%*?&)
    
    Returns:
        Tuple[bool, str]: (válido, mensagem de erro)
    """
    if len(password) < 8:
        return False, "Password deve ter pelo menos 8 caracteres"
    
    if len(password) > 128:
        return False, "Password não pode exceder 128 caracteres"
    
    if not re.search(r'[a-z]', password):
        return False, "Password deve conter pelo menos uma letra minúscula"
    
    if not re.search(r'[A-Z]', password):
        return False, "Password deve conter pelo menos uma letra maiúscula"
    
    if not re.search(r'\d', password):
        return False, "Password deve conter pelo menos um dígito"
    
    if not re.search(r'[@$!%*?&#^()\-_=+\[\]{}|;:,.<>~`]', password):
        return False, "Password deve conter pelo menos um carácter especial (@$!%*?& etc.)"
    
    # Verificar passwords comuns fracas
    common_passwords = [
        'password', 'Password1!', '12345678', 'qwerty123', 'admin123',
        'letmein1!', 'welcome1!', 'Password123!', 'Admin123!'
    ]
    if password.lower() in [p.lower() for p in common_passwords]:
        return False, "Password é demasiado comum. Escolha uma password mais segura."
    
    return True, ""


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    return pwd_context.verify(password, hashed)


def create_token(user_id: str, email: str, role: str) -> str:
    payload = {
        "sub": user_id,
        "email": email,
        "role": role,
        "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRATION_HOURS)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def create_access_token(data: Dict[str, Any]) -> str:
    """
    Criar token JWT com dados personalizados.
    Usado para impersonate e outros cenários especiais.
    """
    payload = {
        **data,
        "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRATION_HOURS)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user = await db.users.find_one({"id": payload["sub"]}, {"_id": 0})
        if not user:
            raise HTTPException(status_code=401, detail="Utilizador não encontrado")
        if not user.get("is_active", True):
            raise HTTPException(status_code=401, detail="Conta desativada")
        
        # Adicionar informação de impersonate se presente no token
        if payload.get("is_impersonated"):
            user["is_impersonated"] = True
            user["impersonated_by"] = payload.get("impersonated_by")
            user["impersonated_by_name"] = payload.get("impersonated_by_name")
        
        return user
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expirado")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Token inválido")


def require_roles(allowed_roles: List[str]):
    """Check if user has one of the allowed roles"""
    async def role_checker(user: dict = Depends(get_current_user)):
        user_role = user["role"]
        
        # Admin and CEO have access to most things
        if user_role == UserRole.ADMIN:
            return user
        
        # CEO has access to consultor and mediador routes
        if user_role == UserRole.CEO:
            if any(r in allowed_roles for r in [UserRole.CONSULTOR, UserRole.MEDIADOR, UserRole.CEO]):
                return user
        
        # Diretor has access to both consultor and mediador routes
        if user_role == UserRole.DIRETOR:
            if any(r in allowed_roles for r in [UserRole.CONSULTOR, UserRole.MEDIADOR, UserRole.DIRETOR]):
                return user
        
        # Administrativo has general access to most routes
        if user_role == UserRole.ADMINISTRATIVO:
            if any(r in allowed_roles for r in [UserRole.CONSULTOR, UserRole.MEDIADOR, UserRole.ADMINISTRATIVO]):
                return user
        
        # Standard role check
        if user_role not in allowed_roles:
            raise HTTPException(status_code=403, detail="Permissão negada")
        return user
    return role_checker


def require_staff():
    """Require any staff role (not cliente)"""
    async def staff_checker(user: dict = Depends(get_current_user)):
        if not UserRole.is_staff(user["role"]):
            raise HTTPException(status_code=403, detail="Permissão negada")
        return user
    return staff_checker

"""
====================================================================
SERVIÇO DE REFRESH TOKENS - AUTENTICAÇÃO SEGURA
====================================================================
Implementa rotação segura de tokens:
- Access tokens: 15 minutos
- Refresh tokens: 7 dias
- Rotação automática: novo refresh token em cada refresh
- Revogação de tokens antigos
====================================================================
"""
import uuid
import hashlib
import secrets
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, Tuple
import jwt

from config import JWT_SECRET, JWT_ALGORITHM
from database import db

# Configurações de expiração
ACCESS_TOKEN_EXPIRE_MINUTES = 120  # Access token 2 horas (para operações longas)
REFRESH_TOKEN_EXPIRE_DAYS = 7  # Refresh token longo


def generate_refresh_token() -> str:
    """
    Gera um refresh token seguro (256 bits de entropia).
    Usa secrets para geração criptograficamente segura.
    """
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """
    Cria hash do token para armazenamento seguro.
    Não guardamos o token em claro na BD.
    """
    return hashlib.sha256(token.encode()).hexdigest()


def create_access_token(
    user_id: str, 
    email: str, 
    role: str,
    additional_data: Optional[Dict[str, Any]] = None
) -> str:
    """
    Cria access token JWT com duração de 2 horas.
    """
    payload = {
        "sub": user_id,
        "email": email,
        "role": role,
        "type": "access",
        "exp": datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
        "iat": datetime.now(timezone.utc),
    }
    
    if additional_data:
        payload.update(additional_data)
    
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


async def create_refresh_token_db(
    user_id: str,
    device_info: Optional[str] = None,
    ip_address: Optional[str] = None
) -> Tuple[str, str]:
    """
    Cria e armazena novo refresh token na BD.
    Retorna (token_id, token_raw).
    """
    token_id = str(uuid.uuid4())
    token_raw = generate_refresh_token()
    token_hash = hash_token(token_raw)
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    
    token_doc = {
        "id": token_id,
        "user_id": user_id,
        "token_hash": token_hash,
        "device_info": device_info,
        "ip_address": ip_address,
        "created_at": now.isoformat(),
        "expires_at": expires_at.isoformat(),
        "revoked": False,
        "revoked_at": None,
        "replaced_by": None,
    }
    
    await db.refresh_tokens.insert_one(token_doc)
    
    return token_id, token_raw


async def validate_refresh_token(token_raw: str) -> Optional[Dict[str, Any]]:
    """
    Valida refresh token.
    Retorna documento do token se válido, None se inválido.
    """
    token_hash = hash_token(token_raw)
    now = datetime.now(timezone.utc)
    
    token_doc = await db.refresh_tokens.find_one(
        {"token_hash": token_hash},
        {"_id": 0}
    )
    
    if not token_doc:
        return None
    
    # Verificar se não está revogado
    if token_doc.get("revoked"):
        return None
    
    # Verificar se não expirou
    expires_at = datetime.fromisoformat(token_doc["expires_at"].replace("Z", "+00:00"))
    if now > expires_at:
        return None
    
    return token_doc


async def rotate_refresh_token(
    old_token_raw: str,
    device_info: Optional[str] = None,
    ip_address: Optional[str] = None
) -> Optional[Tuple[str, str, Dict[str, Any]]]:
    """
    Implementa rotação segura de refresh tokens.
    1. Valida o token antigo
    2. Revoga o token antigo
    3. Cria novo token
    
    Retorna (new_token_id, new_token_raw, user_doc) ou None se inválido.
    """
    # Validar token antigo
    old_token_doc = await validate_refresh_token(old_token_raw)
    if not old_token_doc:
        return None
    
    user_id = old_token_doc["user_id"]
    
    # Buscar utilizador
    user = await db.users.find_one({"id": user_id}, {"_id": 0})
    if not user or not user.get("is_active", True):
        return None
    
    # Criar novo token
    new_token_id, new_token_raw = await create_refresh_token_db(
        user_id,
        device_info=device_info,
        ip_address=ip_address
    )
    
    # Revogar token antigo (marcando qual o substituiu)
    old_token_hash = hash_token(old_token_raw)
    await db.refresh_tokens.update_one(
        {"token_hash": old_token_hash},
        {
            "$set": {
                "revoked": True,
                "revoked_at": datetime.now(timezone.utc).isoformat(),
                "replaced_by": new_token_id,
            }
        }
    )
    
    return new_token_id, new_token_raw, user


async def revoke_refresh_token(token_raw: str) -> bool:
    """
    Revoga um refresh token específico.
    Retorna True se revogado com sucesso.
    """
    token_hash = hash_token(token_raw)
    
    result = await db.refresh_tokens.update_one(
        {"token_hash": token_hash, "revoked": False},
        {
            "$set": {
                "revoked": True,
                "revoked_at": datetime.now(timezone.utc).isoformat(),
            }
        }
    )
    
    return result.modified_count > 0


async def revoke_all_user_tokens(user_id: str) -> int:
    """
    Revoga todos os refresh tokens de um utilizador.
    Útil para logout de todos os dispositivos.
    Retorna número de tokens revogados.
    """
    now = datetime.now(timezone.utc).isoformat()
    
    result = await db.refresh_tokens.update_many(
        {"user_id": user_id, "revoked": False},
        {
            "$set": {
                "revoked": True,
                "revoked_at": now,
            }
        }
    )
    
    return result.modified_count


async def cleanup_expired_tokens() -> int:
    """
    Remove tokens expirados da BD.
    Deve ser executado periodicamente (ex: diariamente).
    Retorna número de tokens removidos.
    """
    now = datetime.now(timezone.utc)
    # Remover tokens expirados há mais de 7 dias
    cutoff = now - timedelta(days=7)
    
    result = await db.refresh_tokens.delete_many({
        "expires_at": {"$lt": cutoff.isoformat()}
    })
    
    return result.deleted_count


async def get_active_sessions(user_id: str) -> list:
    """
    Lista sessões activas de um utilizador.
    Útil para mostrar onde está logado.
    """
    now = datetime.now(timezone.utc).isoformat()
    
    cursor = db.refresh_tokens.find(
        {
            "user_id": user_id,
            "revoked": False,
            "expires_at": {"$gt": now}
        },
        {"_id": 0, "token_hash": 0}
    ).sort("created_at", -1)
    
    sessions = []
    async for token in cursor:
        sessions.append({
            "id": token["id"],
            "device_info": token.get("device_info"),
            "ip_address": token.get("ip_address"),
            "created_at": token["created_at"],
            "expires_at": token["expires_at"],
        })
    
    return sessions


# Constantes exportadas para uso externo
__all__ = [
    "ACCESS_TOKEN_EXPIRE_MINUTES",
    "REFRESH_TOKEN_EXPIRE_DAYS",
    "create_access_token",
    "create_refresh_token_db",
    "validate_refresh_token",
    "rotate_refresh_token",
    "revoke_refresh_token",
    "revoke_all_user_tokens",
    "cleanup_expired_tokens",
    "get_active_sessions",
]

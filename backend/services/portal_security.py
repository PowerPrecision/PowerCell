"""
CLIENT PORTAL - Security Module
================================
Geração e validação de Magic Link JWTs para o Portal do Cliente.

SEGURANÇA:
- JWT com claim role="client_portal" isolado de staff
- Validade longa (90 dias) configurável
- Token contém process_id para escopo restrito
- Sem acesso a endpoints de staff/admin
"""
import jwt
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from database import db
from config import JWT_SECRET, JWT_ALGORITHM

logger = logging.getLogger(__name__)

# ====================================================================
# CONFIGURAÇÃO
# ====================================================================

PORTAL_ROLE = "client_portal"
PORTAL_TOKEN_VALIDITY_DAYS = 90  # 90 dias

# Security scheme (igual ao staff, mas validado separadamente)
_portal_security = HTTPBearer(auto_error=False)


# ====================================================================
# GERAÇÃO DE MAGIC LINK JWT
# ====================================================================

def create_client_magic_token(process_id: str) -> str:
    """
    Gera um JWT específico para o Portal do Cliente.

    Claims:
    - sub: process_id (o ID do processo)
    - role: "client_portal" (isolado de roles de staff)
    - type: "magic_link" (identifica o tipo de token)
    - exp: 90 dias a partir de agora

    Args:
        process_id: ID do processo (UUID)

    Returns:
        JWT string codificado
    """
    payload = {
        "sub": process_id,
        "role": PORTAL_ROLE,
        "type": "magic_link",
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(days=PORTAL_TOKEN_VALIDITY_DAYS),
    }
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    logger.info(f"Magic link gerado para processo {process_id} (expira em {PORTAL_TOKEN_VALIDITY_DAYS}d)")
    return token


# ====================================================================
# VALIDAÇÃO E DEPENDÊNCIA DE SEGURANÇA
# ====================================================================

async def get_current_client(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_portal_security)
) -> Dict[str, Any]:
    """
    Depends de segurança para o Portal do Cliente.

    Validações:
    1. Token existe (Authorization: Bearer <token>)
    2. JWT é válido e não expirou
    3. role == "client_portal" (bloqueia tokens de staff)
    4. Processo existe e não está eliminado

    Returns:
        Dict com {process_id, process, token_payload}

    Raises:
        HTTPException 401: Token inválido, expirado ou role incorreta
        HTTPException 404: Processo não encontrado
    """
    if not credentials:
        raise HTTPException(
            status_code=401,
            detail="Token de acesso ao portal é obrigatório. Use o link enviado por email."
        )

    try:
        payload = jwt.decode(
            credentials.credentials,
            JWT_SECRET,
            algorithms=[JWT_ALGORITHM]
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=401,
            detail="Este link expirou. Contacte o seu consultor para receber um novo link."
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=401,
            detail="Link de acesso inválido."
        )

    # Verificar role — bloquear tokens de staff que tentem aceder ao portal
    if payload.get("role") != PORTAL_ROLE:
        logger.warning(
            f"Tentativa de acesso ao portal com role={payload.get('role')} "
            f"(esperado: {PORTAL_ROLE})"
        )
        raise HTTPException(
            status_code=403,
            detail="Este token não tem permissão para aceder ao portal."
        )

    # Verificar que é um magic_link (não um access_token de staff)
    if payload.get("type") != "magic_link":
        raise HTTPException(
            status_code=403,
            detail="Token de tipo incorreto para o portal."
        )

    process_id = payload.get("sub")
    if not process_id:
        raise HTTPException(status_code=401, detail="Token inválido: sem processo associado.")

    # Buscar processo e validar
    process = await db.processes.find_one(
        {"id": process_id},
        {"_id": 0}
    )

    if not process:
        raise HTTPException(
            status_code=404,
            detail="Processo não encontrado. O link pode ter sido desactivado."
        )

    # Processos eliminados não são acessíveis pelo portal
    if process.get("is_deleted"):
        raise HTTPException(
            status_code=404,
            detail="Este processo foi removido. Contacte o seu consultor."
        )

    return {
        "process_id": process_id,
        "process": process,
        "token_payload": payload,
    }


async def get_portal_client_process(
    client_data: Dict[str, Any] = Depends(get_current_client)
) -> Dict[str, Any]:
    """
    Shorthand dependency que retorna apenas o processo (sem token_payload).

    Returns:
        Dict do processo MongoDB
    """
    return client_data["process"]

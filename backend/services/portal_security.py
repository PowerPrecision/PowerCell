"""
CLIENT PORTAL - Security Module
================================
Geração e validação de JWTs para o Portal do Cliente.

SEGURANÇA:
- JWT com claim role="client_portal" isolado de staff
- Validade longa (90 dias) configurável para magic links
- Sessões verificadas: 4 horas (mais curtas que magic links)
- Token contém process_id para escopo restrito
- Sem acesso a endpoints de staff/admin

FLUXOS DE AUTENTICAÇÃO:
1. Magic Link (legado): short_id → resolve → JWT type=magic_link
2. Verificação NIF + Nº Processo: POST /portal/{client_id}/verify → JWT type=verified_session
3. Código de Acesso Fixo: POST /portal/auth/login → JWT type=access_code_session

Todos os tipos de token são aceites pelo get_current_client.
"""
import jwt
import logging
import re
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
PORTAL_SESSION_VALIDITY_HOURS = 4  # Sessão verificada: 4 horas (mais curta que magic link)

# Tentativas máximas de verificação por client_id (prevenção de brute-force)
MAX_VERIFY_ATTEMPTS = 5
VERIFY_LOCKOUT_MINUTES = 15

# Security scheme (igual ao staff, mas validado separadamente)
_portal_security = HTTPBearer(auto_error=False)


# ====================================================================
# GERAÇÃO DE MAGIC LINK JWT
# ====================================================================

def create_client_magic_token(process_id: str) -> str:
    """
    Gera um JWT específico para o Portal do Cliente (Magic Link).

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


def create_verified_session_token(process_id: str, client_id: str) -> str:
    """
    Gera um JWT de sessão verificada para o Portal do Cliente.

    Este token é emitido após verificação bem-sucedida de NIF + Nº Processo.
    Tem validade mais curta que o magic link (4h vs 90d) por ser uma
    sessão interactiva.

    Claims:
    - sub: process_id (o ID do processo)
    - role: "client_portal" (isolado de roles de staff)
    - type: "verified_session" (obtido por verificação NIF + processo)
    - client_id: ID do cliente verificado
    - iat: timestamp de emissão
    - exp: 4 horas a partir de agora

    Args:
        process_id: ID do processo (UUID)
        client_id: ID do cliente verificado (UUID)

    Returns:
        JWT string codificado
    """
    payload = {
        "sub": process_id,
        "role": PORTAL_ROLE,
        "type": "verified_session",
        "client_id": client_id,
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(hours=PORTAL_SESSION_VALIDITY_HOURS),
    }
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    logger.info(
        f"Sessão verificada gerada para processo {process_id}, "
        f"cliente {client_id} (expira em {PORTAL_SESSION_VALIDITY_HOURS}h)"
    )
    return token


def create_access_code_session_token(process_id: str, client_id: str) -> str:
    """
    Gera um JWT de sessão para login com Código de Acesso Fixo.

    Este token é emitido após login bem-sucedido com Email + Código de Acesso.
    Tem validade de 4 horas (sessão interactiva).

    Claims:
    - sub: process_id (o ID do processo, ou "no_process" se sem processo)
    - role: "client_portal" (isolado de roles de staff)
    - type: "access_code_session" (obtido por código de acesso)
    - client_id: ID do cliente autenticado
    - iat: timestamp de emissão
    - exp: 4 horas a partir de agora

    Args:
        process_id: ID do processo (UUID) ou "no_process"
        client_id: ID do cliente autenticado (UUID)

    Returns:
        JWT string codificado
    """
    payload = {
        "sub": process_id,
        "role": PORTAL_ROLE,
        "type": "access_code_session",
        "client_id": client_id,
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(hours=PORTAL_SESSION_VALIDITY_HOURS),
    }
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    logger.info(
        f"Sessão access_code gerada para cliente {client_id}, "
        f"processo {process_id} (expira em {PORTAL_SESSION_VALIDITY_HOURS}h)"
    )
    return token


async def verify_client_credentials(client_id: str, nif: str, process_number: int) -> Dict[str, Any]:
    """
    Verifica as credenciais do cliente (NIF + Nº Processo) para acesso ao portal.

    Fluxo de verificação:
    1. Validar formato do NIF (9 dígitos)
    2. Verificar lockout por tentativas falhadas
    3. Buscar cliente por ID e cruzar NIF (via blind index ou texto limpo)
    4. Buscar processo por process_number que pertença ao cliente
    5. Se ambos baterem, registar sucesso e retornar dados
    6. Se falhar, incrementar contador de tentativas

    SEGURANÇA:
    - NIF é verificado via blind index (SHA-256) quando encriptado
    - Fallback para texto limpo quando encriptação não está activa
    - Protecção contra brute-force: 5 tentativas, lockout de 15 min
    - Log de tentativas falhadas para auditoria

    Args:
        client_id: ID do cliente (UUID)
        nif: NIF do cliente (9 dígitos)
        process_number: Número do processo

    Returns:
        Dict com {client_id, process_id, client_name} se verificação bem-sucedida

    Raises:
        HTTPException 400: Dados inválidos
        HTTPException 401: Credenciais incorrectas
        HTTPException 429: Muitas tentativas (lockout)
    """
    # ── 1. Validar formato do NIF ──
    nif_clean = re.sub(r'[^\d]', '', str(nif))
    if len(nif_clean) != 9 or not nif_clean.isdigit():
        raise HTTPException(
            status_code=400,
            detail="NIF inválido. Deve conter 9 dígitos."
        )

    # ── 2. Verificar lockout por tentativas falhadas ──
    lockout_key = f"portal_verify:{client_id}"
    lockout_doc = await db.portal_verify_attempts.find_one({"_id": lockout_key})

    if lockout_doc:
        attempts = lockout_doc.get("attempts", 0)
        locked_until = lockout_doc.get("locked_until")

        if locked_until:
            try:
                locked_until_dt = datetime.fromisoformat(
                    locked_until.replace('Z', '+00:00') if isinstance(locked_until, str) else locked_until
                )
                if datetime.now(timezone.utc) < locked_until_dt:
                    remaining = int((locked_until_dt - datetime.now(timezone.utc)).total_seconds() / 60)
                    logger.warning(
                        f"[PORTAL VERIFY] Conta bloqueada para client_id={client_id}. "
                        f"Tenta novamente em {remaining} min."
                    )
                    raise HTTPException(
                        status_code=429,
                        detail=f"Muitas tentativas falhadas. Tente novamente em {remaining} minutos."
                    )
            except (ValueError, TypeError):
                pass  # Data inválida, ignorar lockout

        if attempts >= MAX_VERIFY_ATTEMPTS:
            # Aplicar lockout
            locked_until_str = (
                datetime.now(timezone.utc) + timedelta(minutes=VERIFY_LOCKOUT_MINUTES)
            ).isoformat()
            await db.portal_verify_attempts.update_one(
                {"_id": lockout_key},
                {"$set": {"locked_until": locked_until_str}}
            )
            logger.warning(
                f"[PORTAL VERIFY] Lockout aplicado para client_id={client_id} "
                f"após {attempts} tentativas falhadas"
            )
            raise HTTPException(
                status_code=429,
                detail=f"Muitas tentativas falhadas. Conta bloqueada por {VERIFY_LOCKOUT_MINUTES} minutos."
            )

    # ── 3. Buscar cliente e cruzar NIF ──
    client = await db.clients.find_one({"id": client_id})

    if not client:
        await _record_failed_attempt(lockout_key)
        logger.warning(f"[PORTAL VERIFY] Cliente não encontrado: {client_id}")
        raise HTTPException(
            status_code=401,
            detail="Credenciais inválidas. Verifique o seu NIF e Número de Processo."
        )

    # Cruzar NIF — tentar via blind index primeiro (dados encriptados)
    from services.encryption import generate_nif_hash
    nif_hash = generate_nif_hash(nif_clean)
    nif_matches = False

    # Verificar blind index (dados encriptados)
    if nif_hash:
        stored_nif_hash = (
            client.get("dados_pessoais", {}).get("nif_hash")
        )
        if stored_nif_hash and stored_nif_hash == nif_hash:
            nif_matches = True

    # Fallback: verificar NIF em texto limpo (dados não encriptados)
    if not nif_matches:
        stored_nif = client.get("dados_pessoais", {}).get("nif") or client.get("nif")
        if stored_nif:
            # Se está encriptado, desencriptar para comparar
            if isinstance(stored_nif, str) and stored_nif.startswith("ENC:"):
                from services.encryption import decrypt_value
                stored_nif = decrypt_value(stored_nif)
            stored_nif_clean = re.sub(r'[^\d]', '', str(stored_nif))
            if stored_nif_clean == nif_clean:
                nif_matches = True

    if not nif_matches:
        await _record_failed_attempt(lockout_key)
        logger.warning(
            f"[PORTAL VERIFY] NIF não corresponde para client_id={client_id}"
        )
        raise HTTPException(
            status_code=401,
            detail="Credenciais inválidas. Verifique o seu NIF e Número de Processo."
        )

    # ── 4. Buscar processo por process_number que pertença ao cliente ──
    process = None
    client_process_ids = client.get("process_ids", [])

    # Converter process_number para int (pode vir como string do frontend)
    try:
        process_number_int = int(process_number)
    except (ValueError, TypeError):
        await _record_failed_attempt(lockout_key)
        raise HTTPException(
            status_code=400,
            detail="Número de processo inválido."
        )

    # Procurar processo pelo número que pertença ao cliente
    # Critério: process_number == process_number_int E client_id no processo
    query = {
        "process_number": process_number_int,
        "$or": [
            {"client_id": client_id},
            {"client_ids": client_id},
        ],
    }
    process = await db.processes.find_one(query, {"_id": 0})

    if not process:
        # Fallback: verificar por ID directo se o process_number for na verdade o UUID
        if client_process_ids:
            process = await db.processes.find_one(
                {"id": str(process_number), "client_id": client_id},
                {"_id": 0}
            )

    if not process:
        await _record_failed_attempt(lockout_key)
        logger.warning(
            f"[PORTAL VERIFY] Processo nº{process_number} não encontrado "
            f"para client_id={client_id}"
        )
        raise HTTPException(
            status_code=401,
            detail="Credenciais inválidas. Verifique o seu NIF e Número de Processo."
        )

    # ── 5. Verificação bem-sucedida — limpar tentativas falhadas ──
    await db.portal_verify_attempts.delete_one({"_id": lockout_key})

    client_name = client.get("nome", "Cliente")
    process_id = process.get("id")

    logger.info(
        f"[PORTAL VERIFY] Verificação bem-sucedida: client_id={client_id}, "
        f"process_id={process_id}, process_number={process_number_int}"
    )

    return {
        "client_id": client_id,
        "process_id": process_id,
        "client_name": client_name,
        "process_number": process_number_int,
    }


async def _record_failed_attempt(lockout_key: str) -> None:
    """
    Regista uma tentativa falhada de verificação e aplica lockout se necessário.

    Incrementa o contador de tentativas. Se atingir o limite, aplica lockout.
    """
    now = datetime.now(timezone.utc).isoformat()

    result = await db.portal_verify_attempts.update_one(
        {"_id": lockout_key},
        {
            "$inc": {"attempts": 1},
            "$set": {"last_attempt_at": now},
        },
        upsert=True,
    )

    # Verificar se atingiu o limite
    doc = await db.portal_verify_attempts.find_one({"_id": lockout_key})
    if doc and doc.get("attempts", 0) >= MAX_VERIFY_ATTEMPTS:
        locked_until_str = (
            datetime.now(timezone.utc) + timedelta(minutes=VERIFY_LOCKOUT_MINUTES)
        ).isoformat()
        await db.portal_verify_attempts.update_one(
            {"_id": lockout_key},
            {"$set": {"locked_until": locked_until_str}}
        )
        logger.warning(
            f"[PORTAL VERIFY] Lockout aplicado para {lockout_key} "
            f"após {MAX_VERIFY_ATTEMPTS} tentativas"
        )


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
    except jwt.PyJWTError as jwt_err:
        # Outros erros JWT (InvalidKeyError, etc.)
        logger.warning(
            f"[PORTAL_AUTH] PyJWTError ao decodificar token portal: "
            f"{type(jwt_err).__name__}: {jwt_err}"
        )
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

    # Verificar que é um tipo de token válido para o portal
    # Tipos aceites: "magic_link" (legado), "verified_session" (NIF + processo)
    # e "access_code_session" (Email + código de acesso)
    token_type = payload.get("type")
    if token_type not in ("magic_link", "verified_session", "access_code_session"):
        raise HTTPException(
            status_code=403,
            detail="Token de tipo incorreto para o portal."
        )

    process_id = payload.get("sub")
    if not process_id:
        raise HTTPException(status_code=401, detail="Token inválido: sem processo associado.")

    # Para tokens access_code_session com "no_process", permitir sem processo
    # Se o cliente já tiver processo (criado após docs), anexá-lo automaticamente.
    if token_type == "access_code_session" and process_id == "no_process":
        client_id = payload.get("client_id")
        client = await db.clients.find_one({"id": client_id}, {"_id": 0})
        resolved_process = None
        process_ids = (client or {}).get("process_ids") or []
        if process_ids:
            resolved_process = await db.processes.find_one(
                {
                    "id": {"$in": process_ids},
                    "is_deleted": {"$ne": True},
                },
                {"_id": 0},
            )
        if resolved_process:
            return {
                "process_id": resolved_process["id"],
                "process": resolved_process,
                "client_id": client_id,
                "client": client,
                "token_payload": payload,
            }
        return {
            "process_id": None,
            "process": None,
            "client_id": client_id,
            "client": client,
            "token_payload": payload,
        }

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

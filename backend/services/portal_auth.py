"""Auth do Portal do Cliente (login, verify, resolve, impersonate, authenticate).

Extraído de `routes/portal.py`.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, field_validator

from database import db
from utils.frontend_url import get_frontend_url
from services.portal_security import (
    create_verified_session_token,
    create_access_code_session_token,
    verify_client_credentials,
    create_client_magic_token,
    PORTAL_TOKEN_VALIDITY_DAYS,
)
from services.auth import require_staff

logger = logging.getLogger(__name__)

class PortalLoginRequest(BaseModel):
    """Pedido de login no Portal do Cliente.
    
    O cliente fornece o seu Email e o Código de Acesso fixo
    que foi gerado automaticamente quando o seu registo foi criado.
    """
    email: str
    access_code: str

    @field_validator('email', mode='before')
    @classmethod
    def validate_email_field(cls, v):
        if v is None or v == '':
            raise ValueError('Email é obrigatório.')
        return str(v).strip().lower()

    @field_validator('access_code', mode='before')
    @classmethod
    def validate_access_code_field(cls, v):
        if v is None or v == '':
            raise ValueError('Código de acesso é obrigatório.')
        code = str(v).strip().upper()
        # Aceitar com ou sem hífen (A4B9X2 ou A4B-9X2)
        code = re.sub(r'[^A-Z0-9]', '', code)
        if len(code) != 6:
            raise ValueError('Código de acesso deve conter 6 caracteres.')
        return code


MAX_LOGIN_ATTEMPTS = 8
LOGIN_LOCKOUT_MINUTES = 10


async def _record_login_attempt(lockout_key: str):
    """
    Regista uma tentativa falhada de login e aplica lockout se necessário.
    """
    now = datetime.now(timezone.utc).isoformat()

    result = await db.portal_login_attempts.update_one(
        {"_id": lockout_key},
        {
            "$inc": {"attempts": 1},
            "$set": {"last_attempt_at": now},
        },
        upsert=True,
    )

    doc = await db.portal_login_attempts.find_one({"_id": lockout_key})
    if doc and doc.get("attempts", 0) >= MAX_LOGIN_ATTEMPTS:
        locked_until_str = (
            datetime.now(timezone.utc) + timedelta(minutes=LOGIN_LOCKOUT_MINUTES)
        ).isoformat()
        await db.portal_login_attempts.update_one(
            {"_id": lockout_key},
            {"$set": {"locked_until": locked_until_str}}
        )
        logger.warning(
            f"[PORTAL LOGIN] Lockout aplicado para {lockout_key} "
            f"após {MAX_LOGIN_ATTEMPTS} tentativas"
        )


async def run_portal_login(data: PortalLoginRequest):
    """
    Login do Portal do Cliente com Email + Código de Acesso.

    Fluxo:
    1. Recebe email e código de acesso
    2. Verifica rate limiting (5 tentativas, lockout de 15 min)
    3. Pesquisa o cliente pelo email (case-insensitive, suporta blind index)
    4. Compara o código de acesso com o armazenado na BD
    5. Se válido, gera JWT de sessão (type=access_code_session, 4h)
    6. Retorna {"token": token, "client_id": client_id, "client_name": nome}

    SEGURANÇA:
    - Pesquisa por email suporta dados encriptados (blind index) e plaintext
    - Código de acesso é comparado com timing-safe comparison quando possível
    - Rate limiting: 5 tentativas por email, lockout de 15 minutos
    - Mensagens de erro genéricas (não revelam se o email existe)
    - JWT tem validade de 4 horas (sessão interactiva)
    """
    email = data.email
    access_code = data.access_code

    # ── 1. Verificar rate limiting por email ──
    lockout_key = f"portal_login:{email}"
    lockout_doc = await db.portal_login_attempts.find_one({"_id": lockout_key})

    if lockout_doc:
        attempts = lockout_doc.get("attempts", 0)
        locked_until = lockout_doc.get("locked_until")

        if locked_until:
            try:
                locked_until_dt = datetime.fromisoformat(
                    locked_until.replace('Z', '+00:00') if isinstance(locked_until, str) else locked_until
                )
                if datetime.now(timezone.utc) < locked_until_dt:
                    remaining_seconds = int((locked_until_dt - datetime.now(timezone.utc)).total_seconds())
                    remaining_minutes = max(1, remaining_seconds // 60)
                    logger.warning(
                        f"[PORTAL LOGIN] Conta bloqueada para email={email}. "
                        f"Tenta novamente em {remaining_minutes} min."
                    )
                    raise HTTPException(
                        status_code=429,
                        detail={
                            "error": "Conta temporariamente bloqueada",
                            "message": f"Muitas tentativas falhadas. Tente novamente em {remaining_minutes} minutos.",
                            "retry_after": remaining_seconds,
                            "retry_after_minutes": remaining_minutes,
                        },
                        headers={
                            "Retry-After": str(remaining_seconds),
                        }
                    )
            except (ValueError, TypeError):
                pass  # Data inválida, ignorar lockout

        if attempts >= MAX_LOGIN_ATTEMPTS:
            locked_until_str = (
                datetime.now(timezone.utc) + timedelta(minutes=LOGIN_LOCKOUT_MINUTES)
            ).isoformat()
            await db.portal_login_attempts.update_one(
                {"_id": lockout_key},
                {"$set": {"locked_until": locked_until_str}}
            )
            retry_after_seconds = LOGIN_LOCKOUT_MINUTES * 60
            raise HTTPException(
                status_code=429,
                detail={
                    "error": "Conta temporariamente bloqueada",
                    "message": f"Muitas tentativas falhadas. Conta bloqueada por {LOGIN_LOCKOUT_MINUTES} minutos.",
                    "retry_after": retry_after_seconds,
                    "retry_after_minutes": LOGIN_LOCKOUT_MINUTES,
                },
                headers={
                    "Retry-After": str(retry_after_seconds),
                }
            )

    # ── 2. Pesquisar cliente pelo email ──
    # Tentar via blind index primeiro (dados encriptados)
    client = None
    try:
        from services.encryption import generate_email_hash
        email_hash = generate_email_hash(email)
        if email_hash:
            client = await db.clients.find_one(
                {"contacto.email_hash": email_hash},
                {"_id": 0, "id": 1, "nome": 1, "portal_access_code": 1, "process_ids": 1}
            )
    except Exception:
        logger.debug("[PORTAL LOGIN] Erro ao pesquisar por email_hash, a tentar texto limpo")

    # Fallback: pesquisar por email em texto limpo (case-insensitive)
    if not client:
        client = await db.clients.find_one(
            {"contacto.email": email.lower()},
            {"_id": 0, "id": 1, "nome": 1, "portal_access_code": 1, "process_ids": 1}
        )

    # Fallback adicional: email encriptado (desencriptar e comparar)
    if not client:
        try:
            from services.encryption import decrypt_value
            async for c in db.clients.find(
                {"contacto.email": {"$exists": True}},
                {"_id": 0, "id": 1, "nome": 1, "portal_access_code": 1, "process_ids": 1, "contacto.email": 1}
            ).limit(500):
                stored_email = c.get("contacto", {}).get("email")
                if stored_email and isinstance(stored_email, str) and stored_email.startswith("ENC:"):
                    try:
                        decrypted = decrypt_value(stored_email)
                        if decrypted and decrypted.lower().strip() == email:
                            client = c
                            break
                    except Exception:
                        continue
        except Exception:
            logger.debug("[PORTAL LOGIN] Fallback de desencriptação não disponível")

    # ── 3. Validar credenciais ──
    if not client:
        # Segurança: não revelar que o email não existe — mensagem genérica
        logger.info(f"[PORTAL LOGIN] Email não encontrado: {email[:3]}***@***")
        # Registar tentativa falhada (mesmo sem cliente, para rate limiting)
        await _record_login_attempt(lockout_key)
        raise HTTPException(
            status_code=401,
            detail="Credenciais inválidas. Verifique o seu email e código de acesso."
        )

    stored_code = client.get("portal_access_code")

    if not stored_code:
        # Cliente sem código de acesso — pode ser um cliente antigo antes da migração
        logger.warning(f"[PORTAL LOGIN] Cliente {client.get('id')} sem portal_access_code")
        await _record_login_attempt(lockout_key)
        raise HTTPException(
            status_code=401,
            detail="Credenciais inválidas. Verifique o seu email e código de acesso."
        )

    # Normalizar código armazenado para comparação (remover hífen)
    stored_code_clean = re.sub(r'[^A-Z0-9]', '', stored_code.upper())

    # Comparação de códigos (usando hmac para timing-safe comparison quando possível)
    import hmac
    if not hmac.compare_digest(stored_code_clean, access_code):
        logger.info(f"[PORTAL LOGIN] Código incorrecto para email={email[:3]}***@***")
        await _record_login_attempt(lockout_key)
        raise HTTPException(
            status_code=401,
            detail="Credenciais inválidas. Verifique o seu email e código de acesso."
        )

    # ── 4. Login bem-sucedido — limpar tentativas falhadas ──
    await db.portal_login_attempts.delete_one({"_id": lockout_key})

    client_id = client.get("id")
    client_name = client.get("nome", "Cliente")

    # ── 5. Buscar o primeiro processo do cliente para o token ──
    # O JWT do portal precisa de um process_id. Para clientes com código de acesso,
    # usamos o primeiro processo associado ou None se ainda não tiver processo.
    process_id = None
    process_ids = client.get("process_ids", [])
    if process_ids:
        # Buscar o primeiro processo activo
        process = await db.processes.find_one(
            {"id": {"$in": process_ids}, "is_deleted": {"$ne": True}},
            {"_id": 0, "id": 1}
        )
        if process:
            process_id = process.get("id")
        else:
            # Fallback: usar o primeiro ID da lista
            process_id = process_ids[0]

    # ── 6. Gerar JWT de sessão ──
    if process_id:
        token = create_access_code_session_token(
            process_id=process_id,
            client_id=client_id,
        )
    else:
        # Cliente sem processo — gerar token com process_id placeholder
        # O frontend deve lidar com este caso (mostrar mensagem "sem processo")
        token = create_access_code_session_token(
            process_id="no_process",
            client_id=client_id,
        )

    logger.info(
        f"[PORTAL LOGIN] Login bem-sucedido: client_id={client_id}, "
        f"email={email[:3]}***@***"
    )

    return JSONResponse(content={
        "token": token,
        "client_id": client_id,
        "client_name": client_name,
        "process_id": process_id,
        "token_type": "access_code_session",
        "expires_in": 4 * 60 * 60,  # 4 horas em segundos
    })


async def run_verify_portal_login(client_id: str, data: dict):
    """
    Verifica as credenciais do cliente para acesso ao Portal.

    Este endpoint é o novo ecrã de login do Portal do Cliente. O cliente
    deve inserir o seu NIF e o Número do Processo para desbloquear o acesso.

    Se as credenciais forem válidas, devolve um token de sessão (JWT)
    que pode ser usado para aceder aos restantes endpoints do portal.

    SEGURANÇA:
    - NIF é cruzado via blind index (SHA-256) — nunca exposto em plain text na query
    - Protecção contra brute-force: 5 tentativas, lockout de 15 min
    - Token de sessão tem validade de 4 horas (mais curto que magic link de 90 dias)
    - Mensagens de erro genéricas (não revelam qual campo está errado)

    Path:
    - client_id: ID do cliente (UUID) — obtido a partir do link do portal

    Body:
    - nif: NIF do cliente (9 dígitos, obrigatório)
    - process_number: Número do processo (inteiro, obrigatório)

    Returns:
    - token: JWT de sessão verificada (type=verified_session)
    - process_id: ID do processo associado
    - client_name: Nome do cliente
    - expires_in: Validade do token em segundos
    """
    nif = data.get("nif", "").strip()
    process_number = data.get("process_number")

    if not nif:
        raise HTTPException(status_code=400, detail="NIF é obrigatório.")
    if process_number is None:
        raise HTTPException(status_code=400, detail="Número de processo é obrigatório.")

    # Verificar credenciais (NIF + process_number)
    try:
        result = await verify_client_credentials(
            client_id=client_id,
            nif=nif,
            process_number=process_number,
        )
    except HTTPException as e:
        # Log detalhado do motivo da falha (para diagnóstico no Render)
        # Mas a mensagem para o cliente continua genérica (segurança)
        logger.info(
            f"[PORTAL VERIFY] Falha na verificação para client_id={client_id}: "
            f"status={e.status_code}, detail={e.detail}"
        )
        raise

    # Gerar token de sessão verificada
    session_token = create_verified_session_token(
        process_id=result["process_id"],
        client_id=result["client_id"],
    )

    return JSONResponse(content={
        "token": session_token,
        "process_id": result["process_id"],
        "client_name": result["client_name"],
        "process_number": result["process_number"],
        "token_type": "verified_session",
        "expires_in": 4 * 60 * 60,  # 4 horas em segundos
    })


async def run_resolve_portal_token(short_id: str):
    """
    Resolve um short_id (8 chars) para o JWT completo do portal.

    O frontend detecta que o token não é um JWT (não contém '.')
    e chama este endpoint para obter o JWT real antes de
    autenticar nas restantes rotas do portal.

    Returns:
    - token: JWT completo
    - process_id: ID do processo
    """
    import re

    # Validar formato do short_id (apenas alfanumérico + -_)
    if not re.match(r'^[A-Za-z0-9_-]+$', short_id) or len(short_id) > 20:
        raise HTTPException(status_code=400, detail="Token inválido")

    # Buscar na BD
    token_doc = await db.portal_tokens.find_one(
        {"short_id": short_id},
        {"_id": 0}
    )

    if not token_doc:
        raise HTTPException(
            status_code=404,
            detail="Link não encontrado. Pode ter expirado ou sido desactivado."
        )

    # Validar JWT internamente (verificar se ainda é válido / não expirou)
    try:
        import jwt as jwt_lib
        from config import JWT_SECRET, JWT_ALGORITHM
        jwt_lib.decode(
            token_doc["jwt_token"],
            JWT_SECRET,
            algorithms=[JWT_ALGORITHM]
        )
    except jwt_lib.ExpiredSignatureError:
        raise HTTPException(
            status_code=410,
            detail="Este link expirou. Contacte o seu consultor para receber um novo link."
        )
    except Exception:
        raise HTTPException(status_code=401, detail="Link inválido.")

    # Obter client_id (pode não existir em tokens antigos)
    client_id = token_doc.get("client_id")

    # Fallback: buscar client_id do processo se não estiver no token
    if not client_id and token_doc.get("process_id"):
        process = await db.processes.find_one(
            {"id": token_doc["process_id"]},
            {"client_id": 1, "_id": 0}
        )
        if process:
            client_id = process.get("client_id")
            # Atualizar o token doc para futuras resoluções
            await db.portal_tokens.update_one(
                {"short_id": short_id},
                {"$set": {"client_id": client_id or ""}}
            )

    return {
        "token": token_doc["jwt_token"],
        "process_id": token_doc.get("process_id"),
        "client_id": client_id,
    }


async def run_impersonate_client_portal(process_id: str, request: Request, user: dict):
    """
    Gera um URL de auto-login para o Portal do Cliente (uso interno do staff).

    Devolve um URL com o JWT na query string (?token=...) que o frontend
    do Portal intercepta e usa para autenticar automaticamente, saltando
    o ecrã de login. Isto resolve o bug "Ver como Cliente" em que o
    utilizador ficava retido no login.

    Returns:
    - magic_link: URL completa com ?token=JWT
    - token: JWT completo (também útil para debug / chamadas diretas)
    - process_id, client_id, client_name
    - expires_in_days
    """
    # Procurar o processo (mesmo filtrando eliminados — não permitir impersonate de eliminado)
    process = await db.processes.find_one(
        {"id": process_id, "is_deleted": {"$ne": True}},
        {"_id": 0}
    )
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")

    # Tentar obter email do processo ou do cliente associado
    client_email = process.get("client_email", "")
    client_name = process.get("client_name", "")
    client_id = process.get("client_id", "")

    if not client_email and client_id:
        client_doc = await db.clients.find_one(
            {"id": client_id, "is_deleted": {"$ne": True}},
            {"email": 1, "nome": 1, "_id": 0}
        )
        if client_doc:
            client_email = client_doc.get("email", "")
            if not client_name:
                client_name = client_doc.get("nome", "")

    # Sem email — devolver 400 amigável em vez de gerar link que
    # poderá ter funcionalidades limitadas no portal.
    if not client_email:
        logger.warning(
            f"[IMPERSONATE] Processo {process_id} sem email associado "
            f"(client_id: {client_id or 'N/A'}). Bloqueado — 400 retornado."
        )
        raise HTTPException(
            status_code=400,
            detail="Para usar esta função, o cliente precisa de ter um e-mail configurado."
        )

    # Gerar JWT magic token (mesma função usada pelo generate-magic-link)
    token = create_client_magic_token(process_id)

    # Construir URL com o token na query string
    frontend_url = get_frontend_url(request)
    from urllib.parse import urlencode
    magic_link = f"{frontend_url}/portal?{urlencode({'token': token})}"

    logger.info(
        f"[IMPERSONATE] Staff {user.get('email')} gerou auto-login para "
        f"processo {process_id} (cliente: {client_name or 'N/A'})"
    )

    return {
        "magic_link": magic_link,
        "token": token,
        "process_id": process_id,
        "client_id": client_id,
        "client_name": client_name,
        "client_email": client_email,
        "expires_in_days": PORTAL_TOKEN_VALIDITY_DAYS,
    }


async def run_authenticate_portal(client_data: dict):
    """
    Valida o JWT e retorna informações básicas do processo/cliente.
    """
    process = client_data.get("process")
    token_payload = client_data["token_payload"]
    client_id = client_data.get("client_id")

    # Para access_code_session sem processo, retornar dados mínimos
    if not process:
        return JSONResponse(content={
            "valid": True,
            "process_id": None,
            "client_name": "",
            "process_type": None,
            "token_expires": token_payload.get("exp"),
            "client_id": client_id,
            "has_process": False,
        })

    return JSONResponse(content={
        "valid": True,
        "process_id": process["id"],
        "client_name": process.get("client_name", ""),
        "process_type": process.get("process_type", "credito_habitacao"),
        "token_expires": token_payload.get("exp"),
    })



"""
====================================================================
MFA CACHE — Ponte Redis para códigos MFA em tempo real
====================================================================
Utilitário leve para armazenar e recuperar códigos MFA via Redis,
usado como ponte de comunicação entre o endpoint da API
(POST /submit-mfa) e o scraper (loop de espera MFA).

Fluxo:
1. Scraper detecta MFA → atualiza job MongoDB para "awaiting_mfa"
2. Frontend faz polling → vê "awaiting_mfa" → mostra input de código
3. Cliente submete código → POST /submit-mfa → guarda no Redis (TTL 300s)
4. Scraper lê código do Redis → preenche no browser → continua extração

Se Redis não estiver disponível, faz fallback para MongoDB
(campo mfa_code na portal_scraper_jobs).

Chaves Redis:
  mfa_code:{process_id}  → código MFA (string, TTL 300s)
====================================================================
"""
import logging
import os
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# ── Cliente Redis singleton (lazy init) ──
_redis_client = None
_redis_available = None


async def _get_redis():
    """
    Obtém o cliente Redis (lazy initialization).
    Retorna None se Redis não estiver disponível.
    """
    global _redis_client, _redis_available

    if _redis_available is False:
        return None

    if _redis_client is not None:
        return _redis_client

    try:
        import redis.asyncio as aioredis

        redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379")
        redis_db = int(os.environ.get("REDIS_DB", "0"))

        # Se é localhost e não estamos em produção, pode não haver Redis
        if "localhost" in redis_url and os.environ.get("ENVIRONMENT") != "production":
            # Tentar conectar, mas não falhar se não houver
            _redis_client = aioredis.from_url(
                redis_url,
                db=redis_db,
                decode_responses=True,
                socket_timeout=5,
                socket_connect_timeout=5,
            )
            # Testar a conexão
            await _redis_client.ping()
            _redis_available = True
            logger.info("[MFA_CACHE] Redis conectado para cache MFA")
            return _redis_client
        else:
            _redis_client = aioredis.from_url(
                redis_url,
                db=redis_db,
                decode_responses=True,
                socket_timeout=5,
                socket_connect_timeout=5,
            )
            await _redis_client.ping()
            _redis_available = True
            logger.info("[MFA_CACHE] Redis conectado para cache MFA")
            return _redis_client

    except Exception as e:
        logger.warning(f"[MFA_CACHE] Redis não disponível: {e}")
        _redis_available = False
        _redis_client = None
        return None


async def set_mfa_code(process_id: str, mfa_code: str, ttl: int = 300) -> bool:
    """
    Guarda o código MFA no Redis com TTL.

    Args:
        process_id: ID do processo (chave Redis = mfa_code:{process_id})
        mfa_code: Código MFA recebido por SMS
        ttl: Time-to-live em segundos (default 300 = 5 minutos)

    Returns:
        True se guardou com sucesso, False caso contrário
    """
    key = f"mfa_code:{process_id}"

    # Tentar Redis primeiro
    r = await _get_redis()
    if r:
        try:
            await r.set(key, mfa_code, ex=ttl)
            logger.info(
                f"[MFA_CACHE] Código MFA guardado no Redis para "
                f"processo {process_id} (TTL {ttl}s)"
            )
            return True
        except Exception as e:
            logger.warning(f"[MFA_CACHE] Erro ao guardar no Redis: {e}")

    # Fallback: guardar no MongoDB (portal_scraper_jobs)
    try:
        from config import db as get_db
        db = get_db() if callable(get_db) else get_db
        if db is not None:
            from datetime import datetime, timezone
            await db.portal_scraper_jobs.update_one(
                {"process_id": process_id, "status": "awaiting_mfa"},
                {"$set": {
                    "mfa_code": mfa_code,
                    "mfa_submitted_at": datetime.now(timezone.utc).isoformat(),
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }}
            )
            logger.info(
                f"[MFA_CACHE] Código MFA guardado no MongoDB (fallback) "
                f"para processo {process_id}"
            )
            return True
    except Exception as e:
        logger.warning(f"[MFA_CACHE] Erro ao guardar no MongoDB (fallback): {e}")

    logger.error(f"[MFA_CACHE] Falha total ao guardar código MFA para {process_id}")
    return False


async def get_mfa_code(process_id: str) -> Optional[str]:
    """
    Lê o código MFA do Redis (ou MongoDB como fallback).

    Args:
        process_id: ID do processo

    Returns:
        Código MFA ou None se não existir/expirou
    """
    key = f"mfa_code:{process_id}"

    # Tentar Redis primeiro
    r = await _get_redis()
    if r:
        try:
            code = await r.get(key)
            if code:
                logger.info(
                    f"[MFA_CACHE] Código MFA obtido do Redis para "
                    f"processo {process_id}"
                )
                return code
        except Exception as e:
            logger.warning(f"[MFA_CACHE] Erro ao ler do Redis: {e}")

    # Fallback: ler do MongoDB
    try:
        from config import db as get_db
        db = get_db() if callable(get_db) else get_db
        if db is not None:
            job = await db.portal_scraper_jobs.find_one(
                {"process_id": process_id, "status": "awaiting_mfa"},
                {"mfa_code": 1, "_id": 0}
            )
            if job and job.get("mfa_code"):
                logger.info(
                    f"[MFA_CACHE] Código MFA obtido do MongoDB (fallback) "
                    f"para processo {process_id}"
                )
                return job["mfa_code"]
    except Exception as e:
        logger.warning(f"[MFA_CACHE] Erro ao ler do MongoDB (fallback): {e}")

    return None


async def delete_mfa_code(process_id: str) -> None:
    """
    Remove o código MFA após uso (limpeza de segurança).

    Args:
        process_id: ID do processo
    """
    key = f"mfa_code:{process_id}"

    # Remover do Redis
    r = await _get_redis()
    if r:
        try:
            await r.delete(key)
        except Exception:
            pass

    # Remover do MongoDB
    try:
        from config import db as get_db
        db = get_db() if callable(get_db) else get_db
        if db is not None:
            await db.portal_scraper_jobs.update_one(
                {"process_id": process_id},
                {"$unset": {"mfa_code": ""}}
            )
    except Exception:
        pass


async def set_mfa_status(process_id: str, status: str, db=None) -> None:
    """
    Atualiza o status do job no MongoDB (para o frontend fazer polling).

    Args:
        process_id: ID do processo
        status: Novo status (ex: "awaiting_mfa", "processing")
        db: Instância da BD (opcional, para evitar import circular)
    """
    try:
        if db is None:
            from config import db as get_db
            db = get_db() if callable(get_db) else get_db

        if db is not None:
            update_data = {
                "status": status,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            if status == "awaiting_mfa":
                update_data["message"] = (
                    "A Segurança Social pediu um código de verificação por SMS. "
                    "Introduza o código que recebeu no seu telemóvel."
                )

            await db.portal_scraper_jobs.update_one(
                {"process_id": process_id},
                {"$set": update_data}
            )
            logger.info(f"[MFA_CACHE] Job {process_id} atualizado para status '{status}'")
    except Exception as e:
        logger.warning(f"[MFA_CACHE] Erro ao atualizar job: {e}")

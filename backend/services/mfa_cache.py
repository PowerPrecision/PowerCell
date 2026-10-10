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


def _get_db():
    """Obtém a instância da BD (lazy import para evitar import circular)."""
    try:
        from database import db
        return db
    except Exception:
        return None


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
        db = _get_db()
        if db is not None:
            resultado = await db.portal_scraper_jobs.update_one(
                {"process_id": process_id, "status": "awaiting_mfa"},
                {"$set": {
                    "mfa_code": mfa_code,
                    "mfa_submitted_at": datetime.now(timezone.utc).isoformat(),
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }}
            )
            if getattr(resultado, "matched_count", 1) == 0:
                # Ninguém está à espera do código (o scraper expirou entre a
                # verificação e a gravação): dizer «guardado» seria mentir.
                logger.warning(
                    f"[MFA_CACHE] Sem job em awaiting_mfa para {process_id}; código descartado."
                )
                return False
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
        db = _get_db()
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

    # Remover do MongoDB. `update_many` e não `update_one`: um processo tem
    # vários jobs ao longo da vida e o `update_one` sem ordenação limpava o
    # PRIMEIRO que o Mongo devolvesse — muitas vezes um job antigo — e deixava
    # o código em claro no job que acabou de correr.
    try:
        db = _get_db()
        if db is not None:
            await db.portal_scraper_jobs.update_many(
                {"process_id": process_id, "mfa_code": {"$exists": True}},
                {"$unset": {"mfa_code": ""}}
            )
    except Exception as e:
        logger.warning(f"[MFA_CACHE] Erro ao limpar o código MFA no MongoDB: {type(e).__name__}")


ESTADOS_ACTIVOS = ("processing", "awaiting_mfa")

MENSAGEM_A_AGUARDAR_MFA = (
    "O portal pediu um código de verificação. "
    "Introduza o código que recebeu no seu telemóvel."
)
MENSAGEM_A_PROCESSAR = "A obter os documentos. Isto pode demorar alguns minutos."


async def set_mfa_status(process_id: str, status: str, db=None) -> None:
    """
    Atualiza o estado do job ACTIVO do processo (o ecrã faz polling a ele).

    O filtro é «job activo mais recente» e não «um job deste processo»: o
    `update_one({"process_id": ...})` anterior actuava no primeiro documento
    que o Mongo devolvesse, e um processo tem um job por cada pedido já feito.
    Num segundo pedido a mudança caía no job ANTIGO — o ecrã, a fazer polling
    ao novo, ficava em «a processar» e nunca mostrava o campo do código — e
    ainda ressuscitava como `awaiting_mfa` um job que já tinha terminado.

    Args:
        process_id: ID do processo
        status: Novo estado (`awaiting_mfa` | `processing`)
        db: Instância da BD (opcional, para evitar import circular)
    """
    try:
        if db is None:
            db = _get_db()
        if db is None:
            return

        update_data = {
            "status": status,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "message": MENSAGEM_A_AGUARDAR_MFA if status == "awaiting_mfa" else MENSAGEM_A_PROCESSAR,
        }
        operacao: dict = {"$set": update_data}
        if status != "awaiting_mfa":
            # Código consumido: não fica em claro na colecção.
            operacao["$unset"] = {"mfa_code": ""}

        job = await db.portal_scraper_jobs.find_one_and_update(
            {"process_id": process_id, "status": {"$in": list(ESTADOS_ACTIVOS)}},
            operacao,
            sort=[("created_at", -1)],
        )
        if job is None:
            logger.warning(
                f"[MFA_CACHE] Nenhum job activo para o processo {process_id}; "
                f"estado '{status}' não registado."
            )
            return
        logger.info(f"[MFA_CACHE] Job {job.get('id')} (processo {process_id}) -> '{status}'")
    except Exception as e:
        logger.warning(f"[MFA_CACHE] Erro ao atualizar job: {type(e).__name__}: {e}")


async def aguardar_codigo_mfa(
    process_id: str,
    *,
    timeout_s: int = 120,
    intervalo_s: float = 2,
    dormir=None,
) -> Optional[str]:
    """Pede o código ao cliente e espera por ele. Devolve o código ou `None`.

    Os dois scrapers tinham este ciclo copiado à mão. Três coisas que a cópia
    não fazia:

    * **Limpa antes de esperar.** Um código deixado por uma execução anterior
      (excepção entre receber e apagar) era lido ao fim de 2 s como se fosse
      deste pedido: o scraper escrevia no portal um SMS velho, falhava com
      «código incorrecto» e o cliente nunca chegava a ver o campo.
    * **Regista que houve MFA** para que a política de tentativas não repita o
      login (um segundo login pede um SMS novo).
    * **Volta a `processing` ao receber.** Ficar em `awaiting_mfa` até ao fim
      fazia o ecrã mostrar outra vez o campo do código logo após o envio.
    """
    import asyncio

    from services.gov_fetch_policy import marcar_mfa_pedido

    sleep = dormir or asyncio.sleep
    marcar_mfa_pedido()
    await delete_mfa_code(process_id)
    await set_mfa_status(process_id, "awaiting_mfa")

    esperado = 0.0
    while esperado < timeout_s:
        await sleep(intervalo_s)
        esperado += intervalo_s
        codigo = await get_mfa_code(process_id)
        if codigo:
            logger.info(f"[MFA_CACHE] Código MFA recebido para {process_id} após {esperado:.0f}s")
            await set_mfa_status(process_id, "processing")
            return codigo
    return None

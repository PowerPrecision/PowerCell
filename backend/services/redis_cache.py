"""
O13 - Redis Cache Service (Upstash REST API)
Cache para rotas de estatísticas pesadas usando Upstash Redis.

ARQUITECTURA DE KEYS (hierárquica e previsível):
  stats:global:kpis              → KPIs globais (admin/CEO dashboard)
  stats:global:leads             → Estatísticas de leads
  stats:global:conversion        → Tempo médio de conversão
  stats:user:{user_id}:kpis      → KPIs individuais de um utilizador
  stats:user:{user_id}:leads     → Leads stats individuais

INVALIDAÇÃO CIRÚRGICA:
  invalidate_stats_cache(user_id) apaga:
  1. stats:user:{user_id}:*      (cache individual)
  2. stats:global:*               (cache global — ação individual afeta totais)

CIRCUIT BREAKER:
  Se Redis estiver offline, TODAS as operações falham silenciosamente.
  A aplicação funciona sem cache (cache-miss → DB query).

DEV MODE (ENVIRONMENT=dev|development|local|preview):
  Em ambientes de dev (sem Redis configurado), usa um fallback em memória
  (dicionário simples) para evitar erros de DNS "Name or service not known"
  e logs repetidos. O cache em memória NÃO partilha entre workers/processos,
  mas em dev só há 1 processo, pelo que é suficiente.
"""
import os
import json
import time
import logging
import fnmatch
from typing import Optional, List

logger = logging.getLogger(__name__)

# ====================================================================
# DEV MODE DETECTION
# ====================================================================

def _is_dev_mode() -> bool:
    """Verifica se estamos em ambiente NÃO-produção.
    
    REGRA ABSOLUTA: Só ENVIRONMENT=production usa Redis real.
    Qualquer outro valor (dev, development, local, preview, vazio)
    usa o fallback em memória para evitar DNS errors e log spam.
    Default: 'dev' se ENVIRONMENT não estiver definido.
    """
    return os.environ.get('ENVIRONMENT', 'dev') != 'production'


# ====================================================================
# IN-MEMORY CACHE FALLBACK (para DEV / sem Redis)
# ====================================================================

class InMemoryCache:
    """
    Cache em memória simples para ambientes de DEV.
    
    Substitui o Redis quando:
    1. ENVIRONMENT=dev (ambientes de desenvolvimento sem Redis)
    2. As credenciais Redis não estão configuradas
    
    NOTA: Este cache NÃO é partilhado entre processos/workers.
    Em dev (1 processo no Render free tier), isto é aceitável.
    """
    
    def __init__(self):
        self._store: dict = {}  # key → {"value": str, "expires_at": float}
        logger.info("[IN-MEMORY CACHE] Inicializado — fallback para DEV (sem Redis)")
    
    def _cleanup_expired(self):
        """Remove entradas expiradas (lazy cleanup)."""
        now = time.time()
        expired_keys = [k for k, v in self._store.items() if v["expires_at"] < now]
        for k in expired_keys:
            del self._store[k]
    
    async def get(self, key: str) -> Optional[str]:
        self._cleanup_expired()
        entry = self._store.get(key)
        if entry is None:
            return None
        if entry["expires_at"] < time.time():
            del self._store[key]
            return None
        return entry["value"]
    
    async def setex(self, key: str, ttl: int, value: str) -> bool:
        self._store[key] = {
            "value": value,
            "expires_at": time.time() + ttl,
        }
        return True
    
    async def delete(self, *keys) -> int:
        deleted = 0
        for k in keys:
            if k in self._store:
                del self._store[k]
                deleted += 1
        return deleted
    
    async def keys(self, pattern: str) -> List[str]:
        """Suporta patterns tipo 'stats:user:abc:*' usando fnmatch."""
        self._cleanup_expired()
        return [k for k in self._store.keys() if fnmatch.fnmatch(k, pattern)]
    
    async def ping(self) -> str:
        return "PONG (in-memory)"


# ====================================================================
# SINGLETON STATE
# ====================================================================

_redis = None  # Upstash Redis client (produção)
_redis_available: Optional[bool] = None
_memory_cache: Optional[InMemoryCache] = None  # Fallback para DEV


def _get_memory_cache() -> InMemoryCache:
    """Get or create the in-memory cache singleton."""
    global _memory_cache
    if _memory_cache is None:
        _memory_cache = InMemoryCache()
    return _memory_cache


# ====================================================================
# KEY PATTERNS (padrão hierárquico)
# ====================================================================

# Global keys — afectados por QUALQUER mutação de processo
STATS_GLOBAL_KPI_KEY = "stats:global:kpis"
STATS_GLOBAL_LEADS_KEY = "stats:global:leads"
STATS_GLOBAL_CONVERSION_KEY = "stats:global:conversion"

ALL_GLOBAL_KEYS: List[str] = [
    STATS_GLOBAL_KPI_KEY,
    STATS_GLOBAL_LEADS_KEY,
    STATS_GLOBAL_CONVERSION_KEY,
]


def build_user_kpi_key(user_id: str) -> str:
    """Build cache key for user-level KPIs."""
    return f"stats:user:{user_id}:kpis"


def build_user_leads_key(user_id: str) -> str:
    """Build cache key for user-level leads stats."""
    return f"stats:user:{user_id}:leads"


# ====================================================================
# REDIS CONNECTION (singleton + circuit breaker)
# ====================================================================

def get_redis():
    """Get or create Redis client singleton.

    In DEV mode, returns the InMemoryCache instead of Upstash Redis.
    This avoids DNS resolution errors ("Name or service not known")
    and prevents log spam from failed Redis connections.

    Returns None if credentials are missing in production.
    Sets _redis_available flag for circuit breaker pattern.
    """
    global _redis, _redis_available

    # DEV MODE: Usar cache em memória em vez de Redis
    if _is_dev_mode():
        return _get_memory_cache()

    if _redis_available is False:
        return None
    if _redis is None:
        url = os.environ.get("UPSTASH_REDIS_REST_URL")
        token = os.environ.get("UPSTASH_REDIS_REST_TOKEN")
        if url and token:
            try:
                from upstash_redis.asyncio import Redis as UpstashRedis
                _redis = UpstashRedis(url=url, token=token)
                _redis_available = True
                logger.info("Redis (Upstash) conectado com sucesso")
            except Exception as e:
                logger.warning(f"Falha ao conectar ao Redis: {e}")
                _redis_available = False
        else:
            logger.info("Redis credentials not configured — cache disabled")
            _redis_available = False
    return _redis


async def check_redis_available() -> bool:
    """Verify Redis connectivity. Updates the circuit breaker flag."""
    global _redis_available
    
    # DEV MODE: Cache em memória está sempre disponível
    if _is_dev_mode():
        return True
    
    redis = get_redis()
    if not redis:
        _redis_available = False
        return False
    try:
        await redis.ping()
        _redis_available = True
        return True
    except Exception as e:
        logger.warning(f"Redis health check failed: {e}")
        _redis_available = False
        return False


# ====================================================================
# CORE CACHE OPERATIONS (with circuit breaker)
# ====================================================================

async def cache_get(key: str) -> Optional[dict]:
    """
    Obtém um valor do cache Redis por chave, com desserialização JSON
    automática e circuit breaker integrado.

    Se o Redis estiver offline (circuit breaker), retorna None silenciosamente.
    Isto permite que a aplicação funcione sem cache (cache-miss → query
    à base de dados) sem degradar a experiência do utilizador.

    Args:
        key: Chave do cache a consultar (ex: "stats:global:kpis").

    Returns:
        Optional[dict]: Valor em cache desserializado, ou None se não
            encontrado, erro ou Redis offline.
    """
    redis = get_redis()
    if not redis:
        return None
    try:
        cached = await redis.get(key)
        if cached:
            return json.loads(cached) if isinstance(cached, str) else cached
    except Exception as e:
        if not _is_dev_mode():
            logger.warning(f"Redis GET error for key={key}: {e}")
            _redis_available = False
    return None


async def cache_set(key: str, value: dict, ttl: int = 300) -> bool:
    """
    Armazena um valor no cache Redis com TTL (Time-To-Live) e
    serialização JSON automática.

    Porquê TTL curto (5 min por defeito): os dashboards de KPIs mostram
    dados que mudam ao longo do dia. Um TTL longo causaria dados
    desatualizados visíveis aos consultores e direção.

    Args:
        key: Chave do cache (ex: "stats:user:{user_id}:kpis").
        value: Dicionário a armazenar (será serializado em JSON).
        ttl: Tempo de vida em segundos (default: 300 = 5 minutos).

    Returns:
        bool: True se armazenado com sucesso, False se Redis offline.
    """
    redis = get_redis()
    if not redis:
        return False
    try:
        await redis.setex(key, ttl, json.dumps(value, default=str))
        return True
    except Exception as e:
        if not _is_dev_mode():
            logger.warning(f"Redis SET error for key={key}: {e}")
            _redis_available = False
        return False


async def cache_delete(key: str) -> bool:
    """Delete a single cache key. Silent if Redis is offline."""
    redis = get_redis()
    if not redis:
        return False
    try:
        await redis.delete(key)
        return True
    except Exception as e:
        if not _is_dev_mode():
            logger.warning(f"Redis DELETE error for key={key}: {e}")
            _redis_available = False
        return False


async def cache_delete_pattern(pattern: str) -> int:
    """Delete all keys matching a pattern. Returns number deleted."""
    redis = get_redis()
    if not redis:
        return 0
    try:
        keys = await redis.keys(pattern)
        if keys:
            await redis.delete(*keys)
            return len(keys)
    except Exception as e:
        if not _is_dev_mode():
            logger.warning(f"Redis DELETE pattern error for {pattern}: {e}")
            _redis_available = False
    return 0


# ====================================================================
# SURGICAL CACHE INVALIDATION
# ====================================================================

async def invalidate_stats_cache(user_id: str = None) -> int:
    """Invalida caches de estatísticas após mutação de dados.

    Lógica de invalidação cirúrgica:
    1. Sempre apaga as chaves GLOBAIS (stats:global:*),
       porque qualquer ação individual (criar/mover/eliminar processo)
       afecta os totais da empresa.
    2. Se user_id for fornecido, apaga também as chaves desse utilizador
       (stats:user:{user_id}:*) para garantir que o seu dashboard
       reflicta imediatamente a alteração.

    Circuit Breaker:
      Se Redis estiver offline (REDIS_AVAILABLE=False), retorna 0
      silenciosamente — a app funciona sem cache (cache-miss → DB).

    Args:
        user_id: ID do utilizador cujo cache individual deve ser invalidado.
                 Se None, apenas invalida o cache global.

    Returns:
        Número total de chaves apagadas (0 se Redis offline).
    """
    redis = get_redis()
    if not redis:
        return 0

    total_deleted = 0

    # 1. Invalidar sempre o cache GLOBAL
    # Qualquer mutação afecta os KPIs da direcção
    for key in ALL_GLOBAL_KEYS:
        try:
            deleted = await redis.delete(key)
            total_deleted += (deleted or 0)
        except Exception as e:
            if not _is_dev_mode():
                logger.warning(f"Redis DELETE error for global key={key}: {e}")
                _redis_available = False
            break

    # 2. Invalidar cache individual do utilizador (se fornecido)
    if user_id:
        user_pattern = f"stats:user:{user_id}:*"
        try:
            user_keys = await redis.keys(user_pattern)
            if user_keys:
                await redis.delete(*user_keys)
                total_deleted += len(user_keys)
                logger.debug(
                    f"Cache invalidado: {len(user_keys)} keys de user={user_id}"
                )
        except Exception as e:
            if not _is_dev_mode():
                logger.warning(
                    f"Redis DELETE pattern error for {user_pattern}: {e}"
                )
                _redis_available = False

    if total_deleted > 0:
        logger.info(
            f"Cache invalidation: {total_deleted} keys "
            f"(user={user_id or 'global_only'})"
        )

    return total_deleted


# ====================================================================
# HEALTH CHECK
# ====================================================================

async def health_check() -> dict:
    """
    Verifica o estado da ligação ao Redis, retornando um diagnóstico
    detalhado para monitorização e troubleshooting.

    Porquê existir: o Redis é opcional (a app funciona sem ele), pelo
    que é importante distinguir entre "não configurado" (credenciais
    em falta) e "erro de ligação" (problema de rede ou serviço).

    Returns:
        dict: Estado da ligação:
            - status (str): "connected", "disconnected" ou "error".
            - ping (str, opcional): Resposta do PING se conectado.
            - reason (str, opcional): Motivo da desconexão.
    """
    # DEV MODE: Reportar uso do cache em memória
    if _is_dev_mode():
        cache = _get_memory_cache()
        cache_size = len(cache._store)
        return {
            "status": "connected",
            "mode": "in-memory (DEV)",
            "ping": "PONG (in-memory)",
            "keys_cached": cache_size,
        }
    
    redis = get_redis()
    if not redis:
        return {
            "status": "disconnected",
            "reason": "No credentials configured or previous failure"
        }
    try:
        result = await redis.ping()
        return {"status": "connected", "ping": result}
    except Exception as e:
        return {"status": "error", "reason": str(e)}

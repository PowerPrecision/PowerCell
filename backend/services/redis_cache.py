"""
O13 - Redis Cache Service (Upstash REST API)
Cache para rotas de estatísticas pesadas usando Upstash Redis.
"""
import os
import json
import logging
from typing import Optional
from upstash_redis.asyncio import Redis

logger = logging.getLogger(__name__)

_redis: Optional[Redis] = None


def get_redis() -> Optional[Redis]:
    """Get or create Redis client singleton."""
    global _redis
    if _redis is None:
        url = os.environ.get("UPSTASH_REDIS_REST_URL")
        token = os.environ.get("UPSTASH_REDIS_REST_TOKEN")
        if url and token:
            try:
                _redis = Redis(url=url, token=token)
                logger.info("Redis (Upstash) conectado com sucesso")
            except Exception as e:
                logger.warning(f"Falha ao conectar ao Redis: {e}")
                return None
    return _redis


async def cache_get(key: str) -> Optional[dict]:
    """Get cached value by key. Returns None if not found or error."""
    redis = get_redis()
    if not redis:
        return None
    try:
        cached = await redis.get(key)
        if cached:
            return json.loads(cached) if isinstance(cached, str) else cached
    except Exception as e:
        logger.warning(f"Redis GET error for key={key}: {e}")
    return None


async def cache_set(key: str, value: dict, ttl: int = 300) -> bool:
    """Set cache value with TTL (default 5 minutes). Returns True on success."""
    redis = get_redis()
    if not redis:
        return False
    try:
        await redis.setex(key, ttl, json.dumps(value, default=str))
        return True
    except Exception as e:
        logger.warning(f"Redis SET error for key={key}: {e}")
        return False


async def cache_delete(key: str) -> bool:
    """Delete a cache key."""
    redis = get_redis()
    if not redis:
        return False
    try:
        await redis.delete(key)
        return True
    except Exception as e:
        logger.warning(f"Redis DELETE error for key={key}: {e}")
        return False


async def cache_delete_pattern(pattern: str) -> int:
    """Delete all keys matching a pattern. Returns number deleted."""
    redis = get_redis()
    if not redis:
        return 0
    try:
        keys = await redis.keys(pattern)
        if keys:
            for key in keys:
                await redis.delete(key)
            return len(keys)
    except Exception as e:
        logger.warning(f"Redis DELETE pattern error for {pattern}: {e}")
    return 0


async def health_check() -> dict:
    """Check Redis connection health."""
    redis = get_redis()
    if not redis:
        return {"status": "disconnected", "reason": "No credentials configured"}
    try:
        result = await redis.ping()
        return {"status": "connected", "ping": result}
    except Exception as e:
        return {"status": "error", "reason": str(e)}

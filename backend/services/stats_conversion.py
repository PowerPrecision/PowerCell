"""Lead conversion time statistics.

Extraído de `routes/stats.py`.
"""
from __future__ import annotations

from datetime import datetime

from database import db
from services.redis_cache import (
    cache_get, cache_set,
    STATS_GLOBAL_CONVERSION_KEY,
)

async def run_get_conversion_stats(user: dict):
    """
    Estatísticas de tempo de conversão de leads.
    Calcula o tempo médio desde criação até proposta.
    """
    # O13 - Redis cache: chave global hierárquica
    # TTL longo (24h) porque invalidação cirúrgica garante fresh data
    cache_key = STATS_GLOBAL_CONVERSION_KEY
    cached = await cache_get(cache_key)
    if cached:
        return cached
    
    pipeline = [
        {"$match": {"status": {"$in": ["proposta", "reservado"]}}},
        {"$project": {
            "created_at": 1,
            "updated_at": 1,
            "status": 1
        }}
    ]
    
    cursor = db.property_leads.aggregate(pipeline)
    conversion_times = []
    
    async for lead in cursor:
        if lead.get("created_at") and lead.get("updated_at"):
            try:
                created = datetime.fromisoformat(lead["created_at"].replace('Z', '+00:00'))
                updated = datetime.fromisoformat(lead["updated_at"].replace('Z', '+00:00'))
                days = (updated - created).days
                if days >= 0:
                    conversion_times.append(days)
            except:
                pass
    
    avg_conversion_days = sum(conversion_times) / len(conversion_times) if conversion_times else 0
    
    result = {
        "avg_conversion_days": round(avg_conversion_days, 1),
        "total_converted": len(conversion_times),
        "min_days": min(conversion_times) if conversion_times else 0,
        "max_days": max(conversion_times) if conversion_times else 0
    }
    
    # O13 - Cache result for 24 hours (invalidação cirúrgica substitui TTL curto)
    await cache_set(cache_key, result, ttl=86400)
    return result


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
from services.stats_scope import com_ambito, resolver_ambito

async def run_get_conversion_stats(user: dict):
    """
    Estatísticas de tempo de conversão de leads.
    Calcula o tempo médio desde criação até proposta.
    """
    # ISOLAMENTO DE REDE (Dashboard, ponto 1)
    # ====================================================================
    # A chave era `stats:global:conversion` — GLOBAL. Mesmo depois de
    # filtrar, o primeiro pedido semeava a cache para todos e quem
    # pedisse a seguir recebia o tempo de conversão da outra rede vindo
    # do Redis, com o filtro a funcionar perfeitamente.
    ambito = await resolver_ambito(user)

    # O13 - Redis cache: chave global hierárquica, agora por âmbito
    # TTL longo (24h) porque invalidação cirúrgica garante fresh data
    cache_key = ambito.chave(STATS_GLOBAL_CONVERSION_KEY)
    cached = await cache_get(cache_key)
    if cached:
        return cached

    pipeline = [
        {"$match": com_ambito({"status": {"$in": ["proposta", "reservado"]}}, ambito)},
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
            except Exception:
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


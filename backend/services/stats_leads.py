"""Leads statistics for the stats page.

Extraído de `routes/stats.py`.
"""
from __future__ import annotations

import asyncio
import logging

from database import db
from services.redis_cache import (
    cache_get, cache_set,
    build_user_leads_key,
)

logger = logging.getLogger(__name__)

async def run_get_leads_stats(user: dict):
    """
    Estatísticas de leads para a página de Estatísticas.
    
    OTIMIZAÇÃO: Contagens por status executadas em paralelo com asyncio.gather().
    N+1 de nomes de consultores substituído por $in batch lookup.
    """
    # O13 - Redis cache: chave hierárquica por user
    # TTL longo (24h) porque invalidação cirúrgica garante fresh data
    cache_key = build_user_leads_key(user['id'])
    cached = await cache_get(cache_key)
    if cached:
        return cached
    
    lead_statuses = ["novo", "contactado", "visita_agendada", "proposta", "reservado", "descartado"]
    
    # ── BUSCA PARALELA: 6 contagens por status + agregação por source + top consultores ──
    status_coros = [db.property_leads.count_documents({"status": s}) for s in lead_statuses]
    source_cursor = db.property_leads.aggregate([
        {"$group": {"_id": "$source", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}}
    ])
    consultor_cursor = db.property_leads.aggregate([
        {"$match": {"created_by_id": {"$ne": None}}},
        {"$group": {"_id": "$created_by_id", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 5}
    ])
    
    # Executar todas as contagens em paralelo
    status_counts = await asyncio.gather(*status_coros)
    leads_by_status = dict(zip(lead_statuses, status_counts))
    total_leads = sum(status_counts)
    
    # Aggregate por source (consumir cursor)
    leads_by_source = []
    async for doc in source_cursor:
        leads_by_source.append({
            "source": doc["_id"] or "Desconhecido",
            "count": doc["count"]
        })
    
    # Top consultores (consumir cursor + batch lookup de nomes)
    top_consultors_raw = []
    async for doc in consultor_cursor:
        top_consultors_raw.append({"user_id": doc["_id"], "leads_count": doc["count"]})
    
    # ── BATCH LOOKUP: buscar todos os nomes de uma vez com $in ──
    top_consultors = []
    if top_consultors_raw:
        user_ids = [item["user_id"] for item in top_consultors_raw if item["user_id"]]
        if user_ids:
            users_cursor = db.users.find(
                {"id": {"$in": user_ids}}, 
                {"name": 1, "email": 1, "id": 1, "_id": 0}
            )
            users_map = {}
            async for u in users_cursor:
                users_map[u["id"]] = u
            
            for item in top_consultors_raw:
                u = users_map.get(item["user_id"])
                if u:
                    top_consultors.append({
                        "name": u.get("name") or u.get("email"),
                        "leads_count": item["leads_count"]
                    })
    
    result = {
        "total_leads": total_leads,
        "leads_by_status": leads_by_status,
        "leads_by_source": leads_by_source,
        "top_consultors": top_consultors,
        "funnel_data": [
            {"stage": "Novo", "count": leads_by_status.get("novo", 0)},
            {"stage": "Contactado", "count": leads_by_status.get("contactado", 0)},
            {"stage": "Visita Agendada", "count": leads_by_status.get("visita_agendada", 0)},
            {"stage": "Proposta", "count": leads_by_status.get("proposta", 0)},
            {"stage": "Reservado", "count": leads_by_status.get("reservado", 0)},
        ]
    }
    
    # O13 - Cache result for 24 hours (invalidação cirúrgica substitui TTL curto)
    await cache_set(cache_key, result, ttl=86400)
    return result


"""Branch/bank performance dashboard (Pacote S).

Extraído de `routes/stats.py`.
"""
from __future__ import annotations

import logging

from fastapi import HTTPException

from database import db
from services.redis_cache import cache_get, cache_set

logger = logging.getLogger(__name__)

# PACOTE S — DASHBOARD DE PERFORMANCE DE BALCÕES E BANCOS
# ====================================================================

# Status que indicam aprovação (processo passou a barreira do crédito)
_APPROVED_STATUSES = [
    "credito_aprovado", "pedido_avaliacao", "avaliacao",
    "cpcv", "minuta", "escritura", "concluido", "arquivo",
]

# Status que indicam processo concluído (para cálculo de tempo de fecho)
_COMPLETED_STATUSES = ["concluido", "arquivo"]

# Status que indicam processo ativo
_ACTIVE_STATUSES = [
    "clientes_espera", "documentacao", "analise", "pre_aprovacao",
    "credito_aprovado", "pedido_avaliacao", "avaliacao",
    "cpcv", "minuta", "escritura", "fila_espera", "pre_registo",
]

# Conversão ms → dias
_MS_PER_DAY = 1000 * 60 * 60 * 24


async def run_get_branch_performance(user: dict):
    """
    Dashboard de Performance de Balcões e Bancos (Pacote S).

    Utiliza MongoDB Aggregation Pipeline na coleção `processes` para
    agrupar por `credit_data.bank_name` e `credit_data.bank_branch`.

    Métricas calculadas por balcão/banco:
    - total_processes: total de processos associados
    - active_processes: processos em fases ativas do workflow
    - approval_rate (%): processos que atingiram aprovação ou fase posterior
    - avg_closing_time_days: tempo médio de fecho (concluídos/arquivados)
    - total_volume (€): soma do montante financiado (requested_amount)

    Top Cards (summary):
    - Banco mais rápido: menor tempo médio de fecho
    - Balcão com Maior Volume: maior volume financiado
    - Taxa de Aprovação Global: média ponderada global

    Acesso: Staff com capability STATS_VIEW.
    Cache: Redis com TTL de 1 hora.
    """
    from models.permissions import resolve_capability

    if not resolve_capability(user, "STATS_VIEW"):
        raise HTTPException(status_code=403, detail="Sem permissão para ver estatísticas")

    # Cache: TTL de 1h (métricas de balcões são menos voláteis que KPIs)
    cache_key = "stats:branches:v1"
    cached = await cache_get(cache_key)
    if cached:
        return cached

    pipeline = [
        # ── Stage 1: Filtrar processos com banco preenchido (excluir eliminados) ──
        {
            "$match": {
                "is_deleted": {"$ne": True},
                "credit_data.bank_name": {"$nin": [None, ""]},
            }
        },
        # ── Stage 2: Projetar campos + bandeiras computadas ──
        {
            "$project": {
                "bank_name": "$credit_data.bank_name",
                "bank_branch": {"$ifNull": ["$credit_data.bank_branch", "Geral"]},
                "requested_amount": {"$ifNull": ["$credit_data.requested_amount", 0]},
                "status": 1,
                "created_at": 1,
                "updated_at": 1,
                # Booleanos para contagens condicionais no $group
                "is_approved": {"$in": ["$status", _APPROVED_STATUSES]},
                "is_completed": {"$in": ["$status", _COMPLETED_STATUSES]},
                "is_active": {"$in": ["$status", _ACTIVE_STATUSES]},
                # Tempo de fecho em dias (só para concluídos; null para os restantes)
                "closing_time_days": {
                    "$cond": {
                        "if": {"$in": ["$status", _COMPLETED_STATUSES]},
                        "then": {
                            "$divide": [
                                {"$subtract": [
                                    {"$toDate": "$updated_at"},
                                    {"$toDate": "$created_at"},
                                ]},
                                _MS_PER_DAY,
                            ]
                        },
                        "else": None,
                    }
                },
            }
        },
        # ── Stage 3: Agrupar por banco + balcão ──
        {
            "$group": {
                "_id": {
                    "bank_name": "$bank_name",
                    "bank_branch": "$bank_branch",
                },
                "total_processes": {"$sum": 1},
                "active_processes": {
                    "$sum": {"$cond": [{"$eq": ["$is_active", True]}, 1, 0]}
                },
                "approved_processes": {
                    "$sum": {"$cond": [{"$eq": ["$is_approved", True]}, 1, 0]}
                },
                "completed_processes": {
                    "$sum": {"$cond": [{"$eq": ["$is_completed", True]}, 1, 0]}
                },
                "total_volume": {"$sum": "$requested_amount"},
                "closing_times": {"$push": "$closing_time_days"},
            }
        },
        # ── Stage 4: Calcular approval_rate ──
        {
            "$project": {
                "bank_name": "$_id.bank_name",
                "bank_branch": "$_id.bank_branch",
                "total_processes": 1,
                "active_processes": 1,
                "approved_processes": 1,
                "completed_processes": 1,
                "total_volume": {"$round": ["$total_volume", 2]},
                "approval_rate": {
                    "$round": [
                        {"$multiply": [
                            {"$cond": [
                                {"$eq": ["$total_processes", 0]},
                                0,
                                {"$divide": ["$approved_processes", "$total_processes"]},
                            ]},
                            100,
                        ]},
                        1,
                    ]
                },
                # Closing times para calcular média em Python (filtrar nulls)
                "closing_times": 1,
                "_id": 0,
            }
        },
        # ── Stage 5: Ordenar por volume decrescente ──
        {"$sort": {"total_volume": -1}},
    ]

    try:
        cursor = db.processes.aggregate(pipeline, allowDiskUse=True)
    except Exception as e:
        logger.error(f"[Pacote S] Erro na aggregation pipeline: {e}")
        # Fallback: retorna dados vazios em vez de 500
        return {"branches": [], "summary": {"global_approval_rate": 0, "fastest_bank": None, "highest_volume_branch": None}}

    branches = []
    async for doc in cursor:
        # Calcular tempo médio de fecho (excluir valores null/negativos)
        closing_times = [
            t for t in (doc.get("closing_times") or [])
            if t is not None and t >= 0
        ]
        avg_closing_days = round(sum(closing_times) / len(closing_times), 1) if closing_times else 0

        branches.append({
            "bank_name": doc["bank_name"],
            "bank_branch": doc["bank_branch"],
            "total_processes": doc["total_processes"],
            "active_processes": doc["active_processes"],
            "approved_processes": doc["approved_processes"],
            "completed_processes": doc["completed_processes"],
            "approval_rate": doc["approval_rate"],
            "avg_closing_time_days": avg_closing_days,
            "total_volume": doc["total_volume"],
        })

    # ── KPI Summary (Top Cards) ──
    global_approval_rate = 0.0
    fastest_bank = None
    highest_volume_branch = None

    if branches:
        total_all = sum(b["total_processes"] for b in branches)
        approved_all = sum(b["approved_processes"] for b in branches)
        global_approval_rate = round((approved_all / total_all * 100), 1) if total_all > 0 else 0.0

        # Banco mais rápido (menor tempo médio de fecho, com pelo menos 1 concluído)
        with_closing = [b for b in branches if b["avg_closing_time_days"] > 0]
        if with_closing:
            fastest_bank = min(with_closing, key=lambda x: x["avg_closing_time_days"])

        # Balcão com Maior Volume (ignorar se volume = 0)
        with_volume = [b for b in branches if b["total_volume"] > 0]
        if with_volume:
            highest_volume_branch = max(with_volume, key=lambda x: x["total_volume"])

    result = {
        "branches": branches,
        "summary": {
            "global_approval_rate": global_approval_rate,
            "fastest_bank": {
                "bank_name": fastest_bank["bank_name"],
                "bank_branch": fastest_bank["bank_branch"],
                "avg_closing_time_days": fastest_bank["avg_closing_time_days"],
            } if fastest_bank else None,
            "highest_volume_branch": {
                "bank_name": highest_volume_branch["bank_name"],
                "bank_branch": highest_volume_branch["bank_branch"],
                "total_volume": highest_volume_branch["total_volume"],
            } if highest_volume_branch else None,
        },
    }

    # Cache por 1 hora
    await cache_set(cache_key, result, ttl=3600)
    return result


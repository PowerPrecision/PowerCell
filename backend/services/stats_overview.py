"""Dashboard KPI overview stats.

Extraído de `routes/stats.py`.
"""
from __future__ import annotations

import asyncio
import logging

from database import db
from models.auth import UserRole
from services.redis_cache import (
    cache_get, cache_set,
    build_user_kpi_key,
)

logger = logging.getLogger(__name__)

async def run_get_stats(user: dict):
    """Get statistics based on user role. Staff see only their assigned processes.
    
    OTIMIZAÇÃO: Todas as queries count_documents são executadas em paralelo
    com asyncio.gather(), reduzindo o tempo total de ~12 chamadas sequenciais
    para 2-3 chamadas paralelas.
    """
    # O13 - Redis cache: chave hierárquica por user
    # TTL longo (24h) porque invalidação cirúrgica garante fresh data
    cache_key = build_user_kpi_key(user['id'])
    cached = await cache_get(cache_key)
    if cached:
        return cached
    
    stats = {}
    role = user["role"]
    user_id = user["id"]
    
    # Build query based on role
    process_query = {}
    
    # ====================================================================
    # FILTRO DE INTEGRIDADE: is_deleted
    # Processos eliminados NUNCA entram nas estatísticas
    # ====================================================================
    process_query["is_deleted"] = {"$ne": True}

    if role == UserRole.CLIENTE:
        process_query["client_id"] = user_id
    elif role == UserRole.CONSULTOR:
        process_query["assigned_consultor_id"] = user_id
    elif role == UserRole.INDEXACAO:
        # INDEXACAO vê apenas os processos atribuídos a ele
        process_query["assigned_indexacao_id"] = user_id
    elif role == UserRole.INTERMEDIARIO:
        process_query["assigned_mediador_id"] = user_id
    # Admin, CEO, Administrativo e Diretor see all (no additional filter)
    
    # Process status breakdown
    # NOTA: Estatísticas DEVEM incluir concluídos e desistências para métricas precisas
    concluded_statuses = ["concluidos"]
    dropped_statuses = ["desistencias"]  # NOTA: "eliminados" não conta como desistência para estatísticas

    # Queries para contagens separadas (todas excluem is_deleted via process_query base)
    concluded_query = {**process_query, "status": {"$in": concluded_statuses}}
    dropped_query = {**process_query, "status": {"$in": dropped_statuses}}
    active_query = {**process_query, "status": {"$nin": concluded_statuses + dropped_statuses + ["eliminados"]}}
    no_indexacao_query = {**active_query, "assigned_indexacao_id": None}
    
    # ── BUSCA PARALELA: 4 contagens de processos + 1 contagem de tarefas ──
    (
        total_processes,
        concluded_processes,
        dropped_processes,
        no_indexacao_processes,
        pending_tasks_count,
    ) = await asyncio.gather(
        db.processes.count_documents(active_query),
        db.processes.count_documents(concluded_query),
        db.processes.count_documents(dropped_query),
        db.processes.count_documents(no_indexacao_query),
        db.tasks.count_documents({"completed": False, "assigned_to": user_id}),
    )
    
    stats["total_processes"] = total_processes
    stats["active_processes"] = total_processes
    stats["concluded_processes"] = concluded_processes
    stats["dropped_processes"] = dropped_processes
    stats["no_indexacao_processes"] = no_indexacao_processes
    stats["pending_tasks"] = pending_tasks_count
    
    # ── DEADLINES: depende do role ──
    if role in [UserRole.ADMIN, UserRole.CEO, UserRole.ADMINISTRATIVO, UserRole.DIRETOR]:
        # Admin vê todos os prazos — query simples em paralelo com user counts
        pending_deadlines_coro = db.deadlines.count_documents({"completed": False})
    elif role == UserRole.CLIENTE:
        # Clientes: buscar IDs dos processos primeiro
        my_process_docs = await db.processes.find(
            {"client_id": user_id}, {"id": 1, "_id": 0}
        ).to_list(1000)
        my_process_ids = [p["id"] for p in my_process_docs]
        if my_process_ids:
            pending_deadlines_coro = db.deadlines.count_documents({
                "process_id": {"$in": my_process_ids}, "completed": False
            })
        else:
            pending_deadlines_coro = asyncio.sleep(0, result=0)
    else:
        # Consultores/Intermediários: buscar IDs dos processos atribuídos
        my_process_docs = await db.processes.find(
            {"$or": [
                {"assigned_consultor_id": user_id},
                {"consultor_id": user_id},
                {"assigned_mediador_id": user_id},
                {"intermediario_id": user_id}
            ]},
            {"id": 1, "_id": 0}
        ).to_list(1000)
        my_process_ids = [p["id"] for p in my_process_docs]
        if my_process_ids:
            pending_deadlines_coro = db.deadlines.count_documents({
                "$or": [
                    {"process_id": {"$in": my_process_ids}, "completed": False},
                    {"created_by": user_id, "process_id": None, "completed": False}
                ]
            })
        else:
            pending_deadlines_coro = db.deadlines.count_documents({
                "created_by": user_id, "process_id": None, "completed": False
            })
    
    # ── USER STATS (Admin/CEO): executar em paralelo com deadlines ──
    if role in [UserRole.ADMIN, UserRole.CEO]:
        from services.role_query import deep_role_filter, deep_role_in_filter

        (
            pending_deadlines_count,
            total_users,
            active_users,
            inactive_users,
            clients_count,
            consultors_count,
            intermediarios_count,
        ) = await asyncio.gather(
            pending_deadlines_coro,
            db.users.count_documents({}),
            db.users.count_documents({"is_active": {"$ne": False}}),
            db.users.count_documents({"is_active": False}),
            db.users.count_documents(deep_role_filter(UserRole.CLIENTE)),
            db.users.count_documents(deep_role_in_filter([UserRole.CONSULTOR, UserRole.DIRETOR])),
            db.users.count_documents(deep_role_in_filter([UserRole.INTERMEDIARIO, UserRole.DIRETOR])),
        )
        
        stats["total_users"] = total_users
        stats["active_users"] = active_users
        stats["inactive_users"] = inactive_users
        stats["clients"] = clients_count
        stats["consultors"] = consultors_count
        stats["intermediarios"] = intermediarios_count
    else:
        pending_deadlines_count = await pending_deadlines_coro
    
    stats["pending_deadlines"] = pending_deadlines_count
    stats["total_pending"] = pending_deadlines_count + pending_tasks_count
    
    # O13 - Cache result for 24 hours (invalidação cirúrgica substitui TTL curto)
    await cache_set(cache_key, stats, ttl=86400)
    return stats


from datetime import datetime, timezone
import asyncio
from fastapi import APIRouter, Depends

from database import db
from models.auth import UserRole
from services.auth import get_current_user, require_staff
from services.redis_cache import cache_get, cache_set


router = APIRouter(tags=["Stats"])


@router.get("/stats")
async def get_stats(user: dict = Depends(get_current_user)):
    """Get statistics based on user role. Staff see only their assigned processes.
    
    OTIMIZAÇÃO: Todas as queries count_documents são executadas em paralelo
    com asyncio.gather(), reduzindo o tempo total de ~12 chamadas sequenciais
    para 2-3 chamadas paralelas.
    """
    # O13 - Redis cache: TTL 60s por role+user
    cache_key = f"stats:{user['role']}:{user['id']}"
    cached = await cache_get(cache_key)
    if cached:
        return cached
    
    stats = {}
    role = user["role"]
    user_id = user["id"]
    
    # Build query based on role
    process_query = {}
    
    if role == UserRole.CLIENTE:
        process_query = {"client_id": user_id}
    elif role == UserRole.CONSULTOR:
        process_query = {"assigned_consultor_id": user_id}
    elif role in [UserRole.MEDIADOR, UserRole.INTERMEDIARIO]:
        process_query = {"assigned_mediador_id": user_id}
    # Admin, CEO, Administrativo e Diretor see all (no filter)
    
    # Process status breakdown
    concluded_statuses = ["concluidos"]
    dropped_statuses = ["desistencias", "eliminados"]

    concluded_query = {**process_query, "status": {"$in": concluded_statuses}} if process_query else {"status": {"$in": concluded_statuses}}
    dropped_query = {**process_query, "status": {"$in": dropped_statuses}} if process_query else {"status": {"$in": dropped_statuses}}
    active_query = {**process_query, "status": {"$nin": concluded_statuses + dropped_statuses}} if process_query else {"status": {"$nin": concluded_statuses + dropped_statuses}}
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
            db.users.count_documents({"role": UserRole.CLIENTE}),
            db.users.count_documents({"role": {"$in": [UserRole.CONSULTOR, UserRole.DIRETOR]}}),
            db.users.count_documents({"role": {"$in": [UserRole.MEDIADOR, UserRole.INTERMEDIARIO, UserRole.DIRETOR]}}),
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
    
    # O13 - Cache result for 60 seconds
    await cache_set(cache_key, stats, ttl=60)
    return stats


@router.get("/stats/leads")
async def get_leads_stats(user: dict = Depends(require_staff())):
    """
    Estatísticas de leads para a página de Estatísticas.
    
    OTIMIZAÇÃO: Contagens por status executadas em paralelo com asyncio.gather().
    N+1 de nomes de consultores substituído por $in batch lookup.
    """
    # O13 - Redis cache: TTL 120s
    cache_key = f"stats:leads:{user['id']}"
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
    
    # O13 - Cache result for 120 seconds
    await cache_set(cache_key, result, ttl=120)
    return result


@router.get("/stats/conversion")
async def get_conversion_stats(user: dict = Depends(require_staff())):
    """
    Estatísticas de tempo de conversão de leads.
    Calcula o tempo médio desde criação até proposta.
    """
    # O13 - Redis cache: TTL 300s (conversion stats change slowly)
    cache_key = "stats:conversion"
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
    
    # O13 - Cache result for 300 seconds
    await cache_set(cache_key, result, ttl=300)
    return result


@router.get("/health")
async def health_check():
    from services.redis_cache import health_check as redis_health
    redis_status = await redis_health()
    return {
        "status": "healthy", 
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "redis": redis_status
    }

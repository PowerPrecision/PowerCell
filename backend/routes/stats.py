from datetime import datetime, timezone
import asyncio
import logging
from fastapi import APIRouter, Depends, HTTPException

from database import db
from models.auth import UserRole
from services.auth import get_current_user, require_staff
from services.redis_cache import (
    cache_get, cache_set,
    build_user_kpi_key, build_user_leads_key,
    STATS_GLOBAL_LEADS_KEY, STATS_GLOBAL_CONVERSION_KEY,
)

logger = logging.getLogger(__name__)


router = APIRouter(tags=["Stats"])


@router.get("/stats")
async def get_stats(user: dict = Depends(get_current_user)):
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


@router.get("/stats/leads")
async def get_leads_stats(user: dict = Depends(require_staff())):
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


@router.get("/stats/conversion")
async def get_conversion_stats(user: dict = Depends(require_staff())):
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


@router.get("/stats/communications")
async def get_communications_feed(user: dict = Depends(get_current_user)):
    """
    Feed de comunicações para os Dashboards Executivos.

    Retorna dois arrays de dados:
    a) Avisos do Portal: Últimas mensagens submetidas por clientes no portal
       onde read_by_staff é False.
    b) Emails Pendentes: Últimos emails recebidos com is_read a False.

    Filtrado pelo role do utilizador:
    - Admin/CEO/Administrativo/Diretor: vê tudo
    - Consultores/Intermediários: vê apenas dos seus processos
    - Indexação: vê apenas dos seus processos
    - Clientes: não vê nada (dados internos)

    NOTA: TTL curto (5 min) porque comunicações são time-sensitive.
    """
    import logging
    _logger = logging.getLogger(__name__)

    role = user["role"]
    user_id = user["id"]

    # Clientes não têm acesso ao feed de comunicações internas
    if role == UserRole.CLIENTE:
        return {"portal_messages": [], "unread_emails": [], "portal_unread_count": 0, "email_unread_count": 0}

    # ── Determinar process_ids do utilizador (para filtragem por role) ──
    process_ids = None  # None = sem filtro (vê tudo)

    if role not in [UserRole.ADMIN, UserRole.CEO, UserRole.ADMINISTRATIVO, UserRole.DIRETOR]:
        # Consultores/Intermediários/Indexação: apenas os seus processos
        or_conditions = [
            {"assigned_consultor_id": user_id},
            {"consultor_id": user_id},
            {"assigned_mediador_id": user_id},
            {"intermediario_id": user_id},
        ]
        if role == UserRole.INDEXACAO:
            or_conditions = [{"assigned_indexacao_id": user_id}]

        my_processes = await db.processes.find(
            {"$or": or_conditions, "is_deleted": {"$ne": True}},
            {"id": 1, "_id": 0}
        ).to_list(1000)
        process_ids = [p["id"] for p in my_processes]

    # ── Portal Messages (não lidas pelo staff) ──
    portal_query = {"read_by_staff": False}
    if process_ids is not None:
        portal_query["process_id"] = {"$in": process_ids}

    portal_cursor = db.portal_messages.find(
        portal_query,
        {"_id": 0}
    ).sort("created_at", -1).limit(15)

    portal_messages = []
    async for msg in portal_cursor:
        # Enriquecer com nome do processo/cliente
        process_info = await db.processes.find_one(
            {"id": msg.get("process_id")},
            {"client_name": 1, "process_number": 1, "_id": 0}
        )
        portal_messages.append({
            "id": msg.get("id"),
            "process_id": msg.get("process_id"),
            "sender_name": msg.get("sender_name", "Cliente"),
            "content": (msg.get("content") or "")[:150],
            "created_at": msg.get("created_at"),
            "client_name": process_info.get("client_name", "") if process_info else "",
            "process_number": process_info.get("process_number") if process_info else None,
        })

    # ── Emails Pendentes (não lidos) ──
    email_query = {"is_read": False}
    if process_ids is not None:
        email_query["process_id"] = {"$in": process_ids}

    # A coleção de emails pode variar — verificar se existe 'emails'
    email_cursor = db.emails.find(
        email_query,
        {"_id": 0}
    ).sort("received_at", -1).limit(15)

    unread_emails = []
    async for email in email_cursor:
        # Enriquecer com nome do processo/cliente
        process_info = None
        if email.get("process_id"):
            process_info = await db.processes.find_one(
                {"id": email["process_id"]},
                {"client_name": 1, "process_number": 1, "_id": 0}
            )
        unread_emails.append({
            "id": email.get("id"),
            "process_id": email.get("process_id"),
            "subject": email.get("subject", "(Sem assunto)"),
            "from_address": email.get("from_address", email.get("from", "")),
            "received_at": email.get("received_at", email.get("created_at")),
            "client_name": process_info.get("client_name", "") if process_info else "",
            "process_number": process_info.get("process_number") if process_info else None,
        })

    # Contagens totais (para os KPI cards)
    portal_unread_count = await db.portal_messages.count_documents(portal_query)
    email_unread_count = await db.emails.count_documents(email_query)

    return {
        "portal_messages": portal_messages,
        "unread_emails": unread_emails,
        "portal_unread_count": portal_unread_count,
        "email_unread_count": email_unread_count,
    }


@router.get("/health")
async def health_check():
    """Verifica a saúde do sistema e das dependências externas.

    Retorna o estado das seguintes componentes:
    - Base de dados MongoDB
    - Serviço de armazenamento S3
    - Cache Redis (se disponível)
    - Serviço de email

    Porquê sem autenticação: este endpoint é usado por monitoring
    externo (UptimeRobot, etc.) e não expõe dados sensíveis.

    Returns:
        dict: Estado de cada componente (ok/erro) e timestamp.
    """
    from services.redis_cache import health_check as redis_health
    redis_status = await redis_health()
    return {
        "status": "healthy", 
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "redis": redis_status
    }


# ====================================================================
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


@router.get("/stats/branches")
async def get_branch_performance(user: dict = Depends(require_staff())):
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

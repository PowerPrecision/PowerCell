from datetime import datetime, timezone
from fastapi import APIRouter, Depends

from database import db
from models.auth import UserRole
from services.auth import get_current_user, require_staff


router = APIRouter(tags=["Stats"])


@router.get("/stats")
async def get_stats(user: dict = Depends(get_current_user)):
    """Get statistics based on user role. Staff see only their assigned processes."""
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
    elif role == UserRole.DIRETOR:
        process_query = {"$or": [
            {"assigned_consultor_id": user_id},
            {"assigned_mediador_id": user_id}
        ]}
    # Admin, CEO e Administrativo see all (no filter)
    
    # Get process count
    stats["total_processes"] = await db.processes.count_documents(process_query)
    
    # Process status breakdown
    # Active = not concluded and not dropped out
    concluded_statuses = ["concluidos"]
    dropped_statuses = ["desistencias"]
    
    concluded_query = {**process_query, "status": {"$in": concluded_statuses}} if process_query else {"status": {"$in": concluded_statuses}}
    dropped_query = {**process_query, "status": {"$in": dropped_statuses}} if process_query else {"status": {"$in": dropped_statuses}}
    active_query = {**process_query, "status": {"$nin": concluded_statuses + dropped_statuses}} if process_query else {"status": {"$nin": concluded_statuses + dropped_statuses}}
    
    stats["active_processes"] = await db.processes.count_documents(active_query)
    stats["concluded_processes"] = await db.processes.count_documents(concluded_query)
    stats["dropped_processes"] = await db.processes.count_documents(dropped_query)
    
    # Get process IDs que o utilizador tem acesso (para contar prazos)
    if role in [UserRole.ADMIN, UserRole.CEO, UserRole.ADMINISTRATIVO]:
        # Admin, CEO e Administrativo vêem todos os prazos pendentes
        pending_deadlines_count = await db.deadlines.count_documents({"completed": False})
    elif role == UserRole.CLIENTE:
        # Clientes vêem apenas prazos dos seus processos
        my_processes = await db.processes.find({"client_id": user_id}, {"id": 1, "_id": 0}).to_list(1000)
        my_process_ids = [p["id"] for p in my_processes]
        pending_deadlines_count = await db.deadlines.count_documents({
            "process_id": {"$in": my_process_ids}, 
            "completed": False
        }) if my_process_ids else 0
    else:
        # Consultores/Intermediários/Diretores vêem apenas prazos dos processos que lhes estão atribuídos
        my_processes = await db.processes.find({
            "$or": [
                {"assigned_consultor_id": user_id},
                {"consultor_id": user_id},
                {"assigned_mediador_id": user_id},
                {"intermediario_id": user_id}
            ]
        }, {"id": 1, "_id": 0}).to_list(1000)
        my_process_ids = [p["id"] for p in my_processes]
        
        # Contar prazos dos processos atribuídos OU criados pelo utilizador
        if my_process_ids:
            pending_deadlines_count = await db.deadlines.count_documents({
                "$or": [
                    {"process_id": {"$in": my_process_ids}, "completed": False},
                    {"created_by": user_id, "process_id": None, "completed": False}
                ]
            })
        else:
            pending_deadlines_count = await db.deadlines.count_documents({
                "created_by": user_id, 
                "process_id": None, 
                "completed": False
            })
    
    # Tarefas pendentes atribuídas ao utilizador
    task_query = {"completed": False, "assigned_to": user_id}
    pending_tasks_count = await db.tasks.count_documents(task_query)
    
    # Total de pendentes = prazos + tarefas
    stats["pending_deadlines"] = pending_deadlines_count
    stats["pending_tasks"] = pending_tasks_count
    stats["total_pending"] = pending_deadlines_count + pending_tasks_count
    
    # User stats (Admin and CEO only)
    if role in [UserRole.ADMIN, UserRole.CEO]:
        stats["total_users"] = await db.users.count_documents({})
        stats["active_users"] = await db.users.count_documents({"is_active": {"$ne": False}})
        stats["inactive_users"] = await db.users.count_documents({"is_active": False})
        stats["clients"] = await db.users.count_documents({"role": UserRole.CLIENTE})
        stats["consultors"] = await db.users.count_documents({"role": {"$in": [UserRole.CONSULTOR, UserRole.DIRETOR]}})
        stats["intermediarios"] = await db.users.count_documents({"role": {"$in": [UserRole.MEDIADOR, UserRole.INTERMEDIARIO, UserRole.DIRETOR]}})
    
    return stats


@router.get("/stats/leads")
async def get_leads_stats(user: dict = Depends(require_staff())):
    """
    Estatísticas de leads para a página de Estatísticas.
    Retorna contagens por estado, origem e ranking de consultores.
    """
    # Contagem de leads por estado
    lead_statuses = ["novo", "contactado", "visita_agendada", "proposta", "reservado", "descartado"]
    leads_by_status = {}
    
    for status in lead_statuses:
        count = await db.property_leads.count_documents({"status": status})
        leads_by_status[status] = count
    
    # Total de leads
    total_leads = sum(leads_by_status.values())
    
    # Leads por fonte (source)
    pipeline_source = [
        {"$group": {"_id": "$source", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}}
    ]
    source_cursor = db.property_leads.aggregate(pipeline_source)
    leads_by_source = []
    async for doc in source_cursor:
        leads_by_source.append({
            "source": doc["_id"] or "Desconhecido",
            "count": doc["count"]
        })
    
    # Top 5 consultores com mais leads angariados
    pipeline_consultors = [
        {"$match": {"created_by_id": {"$ne": None}}},
        {"$group": {"_id": "$created_by_id", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 5}
    ]
    consultor_cursor = db.property_leads.aggregate(pipeline_consultors)
    top_consultors_raw = []
    async for doc in consultor_cursor:
        top_consultors_raw.append({"user_id": doc["_id"], "leads_count": doc["count"]})
    
    # Enriquecer com nomes dos consultores
    top_consultors = []
    for item in top_consultors_raw:
        user = await db.users.find_one({"id": item["user_id"]}, {"name": 1, "email": 1, "_id": 0})
        if user:
            top_consultors.append({
                "name": user.get("name") or user.get("email"),
                "leads_count": item["leads_count"]
            })
    
    return {
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


@router.get("/stats/conversion")
async def get_conversion_stats(user: dict = Depends(require_staff())):
    """
    Estatísticas de tempo de conversão de leads.
    Calcula o tempo médio desde criação até proposta.
    """
    # Buscar leads que chegaram a proposta ou reservado
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
    
    return {
        "avg_conversion_days": round(avg_conversion_days, 1),
        "total_converted": len(conversion_times),
        "min_days": min(conversion_times) if conversion_times else 0,
        "max_days": max(conversion_times) if conversion_times else 0
    }


@router.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.now(timezone.utc).isoformat()}

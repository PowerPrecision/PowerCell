"""
====================================================================
ROTAS DE CLIENTES DO UTILIZADOR - CREDITOIMO
====================================================================
Endpoints para gestão de "Os Meus Clientes" - clientes atribuídos
ao utilizador actual.

SINCRONIZAÇÃO COM "Os Meus Processos":
A query de my-clients deve usar EXATAMENTE o mesmo critério base que
my-processes (assigned_consultor_ids + is_active + status), para que
os clientes listados correspondam aos processos visíveis.
A estes somam-se os Leads (clientes sem processo) criados pelo utilizador.
====================================================================
"""
import logging
from typing import List, Optional
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query, Request

from database import db
from models.auth import UserRole
from services.auth import get_current_user, require_roles, get_effective_role

logger = logging.getLogger(__name__)

# Mesmos status inactivos que processes.py
INACTIVE_STATUSES = ["concluidos", "desistencias", "eliminados"]

router = APIRouter(prefix="/my-clients", tags=["My Clients"])


@router.get("")
async def get_my_clients(request: Request, user: dict = Depends(require_roles([
    UserRole.CONSULTOR, UserRole.INTERMEDIARIO, 
    UserRole.ADMIN, UserRole.CEO, UserRole.INDEXACAO,
    UserRole.DIRETOR, UserRole.ADMINISTRATIVO
]))):
    """
    Obter lista de clientes atribuídos ao utilizador actual.
    
    Retorna uma lista com:
    - Nome do cliente
    - Fase do processo
    - Ações pendentes (tarefas, documentos a atualizar)
    
    Permissões:
    - Consultor: Apenas os seus clientes (assigned_consultor_id/ids) — apenas processos activos
    - Intermediário/Mediador: Apenas os seus clientes (assigned_mediador_id/ids ou criados por eles) — apenas processos activos
    - Indexacao: Todos os processos (para poder atribuir a consultores/intermediários)
    - Admin/CEO/Diretor: Todos os clientes (para supervisão)
    
    SINCRONIZAÇÃO:
    - Consultores e Intermediários: query sincronizada com my-processes
      (is_active=True, status ∉ INACTIVE_STATUSES, is_deleted≠True)
    - Leads (clientes sem processo) criados pelo utilizador são adicionados à lista
    """
    user_id = user["id"]
    user_email = user.get("email", "")
    role = get_effective_role(request, user)
    
    # Construir query baseada no papel do utilizador
    #
    # SINCRONIZAÇÃO COM "Os Meus Processos":
    # A query de my-clients deve usar EXATAMENTE o mesmo critério base que
    # my-processes (assigned_consultor_ids + is_active + status), para que
    # os clientes listados correspondam aos processos visíveis.
    # A estes somam-se os Leads (clientes sem processo) criados pelo utilizador.
    if role == UserRole.CONSULTOR:
        query = {
            "$and": [
                {"$or": [
                    {"assigned_consultor_ids": user_id},
                    {"assigned_consultor_id": user_id}
                ]},
                {"is_active": {"$ne": False}},
                {"status": {"$nin": INACTIVE_STATUSES}},
                {"is_deleted": {"$ne": True}}
            ]
        }
    elif role == UserRole.INTERMEDIARIO:
        query = {
            "$and": [
                {"$or": [
                    {"assigned_mediador_ids": user_id},
                    {"assigned_mediador_id": user_id},
                    {"created_by": user_email}
                ]},
                {"is_active": {"$ne": False}},
                {"status": {"$nin": INACTIVE_STATUSES}},
                {"is_deleted": {"$ne": True}}
            ]
        }
    elif role == UserRole.INDEXACAO:
        query = {
            "$or": [
                {"assigned_indexacao_id": user_id},
                {"created_by": user_email}
            ]
        }
    elif role in [UserRole.ADMIN, UserRole.CEO, UserRole.DIRETOR, UserRole.ADMINISTRATIVO]:
        # Admin/CEO/Diretor/Administrativo veem todos os ativos
        query = {
            "status": {"$nin": ["concluidos", "desistencias", "eliminado"]},
            "is_active": {"$ne": False}
        }
    else:
        # Outros roles não têm acesso
        query = {"_id": None}  # Query que não retorna nada
    
    # Buscar processos
    processes = await db.processes.find(
        query,
        {
            "_id": 0,
            "id": 1,
            "process_number": 1,
            "client_name": 1,
            "client_email": 1,
            "client_phone": 1,
            "status": 1,
            "created_at": 1,
            "updated_at": 1,
            "assigned_consultor_id": 1,
            "assigned_consultor_ids": 1,
            "assigned_mediador_id": 1,
            "assigned_mediador_ids": 1,
            "next_action": 1,
            "is_active": 1
        }
    ).sort("client_name", 1).limit(100).to_list(100)
    
    # Desencriptar dados sensíveis (client_phone, client_nif)
    from services.process_service import decrypt_processes_list
    processes = decrypt_processes_list(processes)
    
    # ── BUSCAR LEADS (clientes sem processo) criados pelo utilizador ──
    leads = []
    if role in [UserRole.CONSULTOR, UserRole.INTERMEDIARIO]:
        leads_query = {
            "$and": [
                {"created_by": user_id},
                {"is_deleted": {"$ne": True}},
                # Sem processo associado (Lead puro)
                {"$or": [
                    {"process_ids": {"$exists": False}},
                    {"process_ids": []},
                    {"process_ids": None}
                ]},
                # Apenas leads pendentes (não convertidos)
                {"$or": [
                    {"lead_status": {"$exists": False}},
                    {"lead_status": "new"}
                ]}
            ]
        }
        leads_cursor = await db.clients.find(
            leads_query,
            {
                "_id": 0, "id": 1, "nome": 1, "contacto": 1,
                "created_at": 1, "updated_at": 1, "fonte": 1,
                "assigned_to": 1, "lead_status": 1
            }
        ).to_list(500)
        
        # Desencriptar dados sensíveis dos leads
        from services.encryption import decrypt_clients_list
        leads_cursor = decrypt_clients_list(leads_cursor)
        
        # Converter leads para o mesmo formato dos clientes de processo
        for lead in leads_cursor:
            contacto = lead.get("contacto", {})
            leads.append({
                "id": lead.get("id"),
                "process_number": None,
                "client_name": lead.get("nome", "Sem nome"),
                "client_email": contacto.get("email", ""),
                "client_phone": contacto.get("telefone", ""),
                "status": "lead",
                "status_label": "Lead",
                "status_color": "#8B5CF6",
                "pending_tasks": 0,
                "pending_actions": [],
                "created_at": lead.get("created_at"),
                "updated_at": lead.get("updated_at"),
                "is_lead": True
            })
    
    # Enriquecer processos com status_label do workflow
    if processes:
        statuses = await db.workflow_statuses.find({}, {"_id": 0}).to_list(100)
        status_map = {s["name"]: s for s in statuses}
        for p in processes:
            status_info = status_map.get(p.get("status"), {})
            p["status_label"] = status_info.get("label", p.get("status", ""))
            p["status_color"] = status_info.get("color", "#6B7280")
    
    # Para cada processo, buscar tarefas pendentes detalhadas
    for process in processes:
        pending_tasks = await db.tasks.find(
            {
                "process_id": process["id"],
                "status": {"$ne": "completed"}
            },
            {"_id": 0, "id": 1, "title": 1, "priority": 1, "due_date": 1}
        ).sort("due_date", 1).limit(5).to_list(5)

        process["pending_tasks"] = len(pending_tasks)
        process["pending_actions"] = [
            {
                "type": "task",
                "title": t.get("title", "Tarefa sem título"),
                "priority": t.get("priority", "medium"),
                "due_date": t.get("due_date")
            }
            for t in pending_tasks
        ]

    # ====================================================================
    # PACOTE BI: BATCH ENRIQUECIMENTO — has_unread_messages & has_new_documents
    # Pistas visuais silenciosas (bolinhas) para interações do cliente no portal.
    # Mesma lógica do Kanban (processes.py linhas 2122-2155). Leads não têm
    # mensagens/documentos do portal, pelo que ficam com False por defeito.
    # ====================================================================
    _bi_process_ids = [p["id"] for p in processes if p.get("id")]
    _bi_unread_map = {}
    _bi_new_docs_map = {}
    if _bi_process_ids:
        _bi_unread = await db.portal_messages.aggregate([
            {"$match": {
                "process_id": {"$in": _bi_process_ids},
                "sender_type": "client",
                "read_by_staff": False
            }},
            {"$group": {"_id": "$process_id", "unread_count": {"$sum": 1}}}
        ]).to_list(1000)
        _bi_unread_map = {r["_id"]: r["unread_count"] > 0 for r in _bi_unread}

        _bi_new_docs = await db.documents.aggregate([
            {"$match": {
                "process_id": {"$in": _bi_process_ids},
                "status": "uploaded"
            }},
            {"$group": {"_id": "$process_id", "new_count": {"$sum": 1}}}
        ]).to_list(1000)
        _bi_new_docs_map = {r["_id"]: r["new_count"] > 0 for r in _bi_new_docs}

    for p in processes:
        p["has_unread_messages"] = _bi_unread_map.get(p.get("id"), False)
        p["has_new_documents"] = _bi_new_docs_map.get(p.get("id"), False)

    # Combinar processos + leads
    all_clients = leads + processes

    return {"clients": all_clients, "total": len(all_clients), "leads_count": len(leads)}


@router.get("/stats")
async def get_my_clients_stats(user: dict = Depends(require_roles([
    UserRole.CONSULTOR, UserRole.INTERMEDIARIO, 
    UserRole.ADMIN, UserRole.CEO, UserRole.INDEXACAO,
    UserRole.DIRETOR, UserRole.ADMINISTRATIVO
]))):
    """
    Obter estatísticas dos clientes do utilizador.
    """
    user_id = user["id"]
    user_email = user.get("email", "")
    role = user["role"]
    
    # Construir query baseada no papel do utilizador (sincronizada com get_my_clients)
    if role == UserRole.CONSULTOR:
        query = {
            "$and": [
                {"$or": [
                    {"assigned_consultor_ids": user_id},
                    {"assigned_consultor_id": user_id}
                ]},
                {"is_active": {"$ne": False}},
                {"status": {"$nin": INACTIVE_STATUSES}},
                {"is_deleted": {"$ne": True}}
            ]
        }
    elif role == UserRole.INTERMEDIARIO:
        query = {
            "$and": [
                {"$or": [
                    {"assigned_mediador_ids": user_id},
                    {"assigned_mediador_id": user_id},
                    {"created_by": user_email}
                ]},
                {"is_active": {"$ne": False}},
                {"status": {"$nin": INACTIVE_STATUSES}},
                {"is_deleted": {"$ne": True}}
            ]
        }
    elif role == UserRole.INDEXACAO:
        query = {
            "$or": [
                {"assigned_indexacao_id": user_id},
                {"created_by": user_email}
            ]
        }
    elif role in [UserRole.ADMIN, UserRole.CEO, UserRole.DIRETOR, UserRole.ADMINISTRATIVO]:
        query = {
            "status": {"$nin": ["concluidos", "desistencias", "eliminado"]},
            "is_active": {"$ne": False}
        }
    else:
        query = {"_id": None}
    
    # Contar por status
    pipeline = [
        {"$match": query},
        {"$group": {"_id": "$status", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}}
    ]
    
    status_counts = await db.processes.aggregate(pipeline).to_list(20)
    
    # Total de clientes
    total = sum(s["count"] for s in status_counts)
    
    # Tarefas pendentes
    process_ids = [p["id"] async for p in db.processes.find(query, {"_id": 0, "id": 1})]
    pending_tasks = await db.tasks.count_documents({
        "process_id": {"$in": process_ids},
        "status": {"$ne": "completed"}
    }) if process_ids else 0
    
    return {
        "total_clients": total,
        "by_status": {s["_id"]: s["count"] for s in status_counts},
        "pending_tasks": pending_tasks
    }

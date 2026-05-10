"""
====================================================================
ROTAS DE CLIENTES DO UTILIZADOR - CREDITOIMO
====================================================================
Endpoints para gestão de "Os Meus Clientes" - clientes atribuídos
ao utilizador actual.
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
    - Consultor: Apenas os seus clientes (assigned_consultor_id)
    - Intermediário/Mediador: Apenas os seus clientes (assigned_mediador_id ou criados por eles)
    - Indexacao: Todos os processos (para poder atribuir a consultores/intermediários)
    - Admin/CEO/Diretor: Todos os clientes (para supervisão)
    """
    user_id = user["id"]
    user_email = user.get("email", "")
    role = get_effective_role(request, user)
    
    # Construir query baseada no papel do utilizador
    if role == UserRole.CONSULTOR:
        query = {"assigned_consultor_id": user_id}
    elif role == UserRole.INTERMEDIARIO:
        # Intermediários vêem processos atribuídos a eles OU criados por eles
        query = {
            "$or": [
                {"assigned_mediador_id": user_id},
                {"created_by": user_email}
            ]
        }
    elif role == UserRole.INDEXACAO:
        # Indexacao vê apenas os processos atribuídos a si (assigned_indexacao_id)
        # ou processos criados por si (created_by)
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
            "assigned_mediador_id": 1,
            "next_action": 1
        }
    ).sort("client_name", 1).limit(100).to_list(100)
    
    # Desencriptar dados sensíveis (client_phone, client_nif)
    from services.process_service import decrypt_processes_list
    processes = decrypt_processes_list(processes)
    
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
    
    return {"clients": processes, "total": len(processes)}


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
    
    # Construir query baseada no papel do utilizador
    if role == UserRole.CONSULTOR:
        query = {"assigned_consultor_id": user_id}
    elif role == UserRole.INTERMEDIARIO:
        query = {
            "$or": [
                {"assigned_mediador_id": user_id},
                {"created_by": user_email}
            ]
        }
    elif role == UserRole.INDEXACAO:
        # Indexacao vê apenas os processos atribuídos a si
        query = {
            "$or": [
                {"assigned_indexacao_id": user_id},
                {"created_by": user_email}
            ]
        }
    elif role in [UserRole.ADMIN, UserRole.CEO, UserRole.DIRETOR, UserRole.ADMINISTRATIVO]:
        # Admin/CEO/Diretor/Administrativo veem todos (ativos)
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

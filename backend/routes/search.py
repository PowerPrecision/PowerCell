"""
Search Routes - Pesquisa Global
Endpoint para pesquisa unificada em processos, clientes e tarefas
"""
import logging
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, Query
import re

from database import db
from services.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/search", tags=["Search"])


@router.get("/global")
async def global_search(
    q: str = Query(..., min_length=2, description="Termo de pesquisa"),
    limit: int = Query(5, ge=1, le=20, description="Limite de resultados por tipo"),
    user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Pesquisa global em processos, clientes e tarefas.
    
    Usado pelo modal de pesquisa rápida (Ctrl+K).
    
    Returns:
        {
            "processes": [...],
            "clients": [...],
            "tasks": [...]
        }
    """
    search_term = q.strip()
    
    # Criar regex para pesquisa case-insensitive
    regex_pattern = {"$regex": search_term, "$options": "i"}
    
    results = {
        "processes": [],
        "clients": [],
        "tasks": []
    }
    
    try:
        # Pesquisar processos
        process_query = {
            "$or": [
                {"client_name": regex_pattern},
                {"personal_data.nif": regex_pattern},
                {"personal_data.email": regex_pattern},
                {"process_type": regex_pattern},
            ]
        }
        
        processes = await db.processes.find(
            process_query,
            {
                "_id": 0,
                "id": 1,
                "client_name": 1,
                "process_type": 1,
                "status": 1,
                "personal_data.nif": 1
            }
        ).limit(limit).to_list(limit)
        
        results["processes"] = processes
        
        # Pesquisar tarefas
        task_query = {
            "$or": [
                {"title": regex_pattern},
                {"description": regex_pattern},
                {"client_name": regex_pattern},
            ]
        }
        
        tasks = await db.tasks.find(
            task_query,
            {
                "_id": 0,
                "id": 1,
                "title": 1,
                "status": 1,
                "priority": 1,
                "client_name": 1
            }
        ).limit(limit).to_list(limit)
        
        results["tasks"] = tasks
        
        # Clientes são os mesmos processos mas com filtro diferente
        # (mantemos separado para compatibilidade com o frontend)
        results["clients"] = []
        
        logger.info(f"Pesquisa global '{search_term}': {len(processes)} processos, {len(tasks)} tarefas")
        
    except Exception as e:
        logger.error(f"Erro na pesquisa global: {e}")
    
    return results


@router.get("/processes")
async def search_processes(
    q: str = Query(..., min_length=2),
    status: Optional[str] = None,
    process_type: Optional[str] = None,
    limit: int = Query(20, ge=1, le=100),
    user: dict = Depends(get_current_user)
) -> List[Dict[str, Any]]:
    """
    Pesquisa avançada em processos.
    
    Args:
        q: Termo de pesquisa
        status: Filtrar por status
        process_type: Filtrar por tipo de processo
        limit: Limite de resultados
    """
    search_term = q.strip()
    regex_pattern = {"$regex": search_term, "$options": "i"}
    
    query = {
        "$or": [
            {"client_name": regex_pattern},
            {"personal_data.nif": regex_pattern},
            {"personal_data.email": regex_pattern},
            {"personal_data.telefone": regex_pattern},
        ]
    }
    
    if status:
        query["status"] = status
    
    if process_type:
        query["process_type"] = process_type
    
    processes = await db.processes.find(
        query,
        {"_id": 0}
    ).sort("updated_at", -1).limit(limit).to_list(limit)
    
    return processes


@router.get("/suggestions")
async def get_search_suggestions(
    q: str = Query(..., min_length=1),
    user: dict = Depends(get_current_user)
) -> List[str]:
    """
    Obter sugestões de pesquisa baseadas no histórico e dados existentes.
    """
    search_term = q.strip().lower()
    suggestions = set()
    
    # Buscar nomes de clientes que começam com o termo
    clients = await db.processes.find(
        {"client_name": {"$regex": f"^{search_term}", "$options": "i"}},
        {"_id": 0, "client_name": 1}
    ).limit(5).to_list(5)
    
    for client in clients:
        suggestions.add(client.get("client_name", ""))
    
    # Buscar títulos de tarefas
    tasks = await db.tasks.find(
        {"title": {"$regex": f"^{search_term}", "$options": "i"}},
        {"_id": 0, "title": 1}
    ).limit(3).to_list(3)
    
    for task in tasks:
        suggestions.add(task.get("title", ""))
    
    return list(suggestions)[:10]

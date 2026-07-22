"""AI training data + AI import logs (admin) — não confundir com routes/admin_ai.py.

Extraído de `routes/admin.py`.
"""
from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone, timedelta
from typing import List, Optional

from fastapi import HTTPException, Query, Request, BackgroundTasks
from pydantic import BaseModel

from database import db
from models.auth import UserRole, UserCreate, UserUpdate, UserResponse
from models.workflow import WorkflowStatusCreate, WorkflowStatusUpdate, WorkflowStatusResponse
from models.email_config import EmailConfigCreate, EmailConfigResponse
from services.auth import hash_password, require_roles, get_current_user
from services.admin_helpers import _safe_float, _audit_log
from services.permissions import (
    get_default_permissions_for_role,
    get_all_available_permissions,
    get_role_display_info,
    validate_permissions,
    DEFAULT_PERMISSIONS_BY_ROLE,
    get_user_capabilities,
    build_permissions_document,
)
from models.permissions import (
    CAPABILITIES,
    CATEGORIES,
    SUPER_ADMIN_ROLES,
    ROLE_CAPABILITY_DEFAULTS,
    get_all_capabilities,
    get_capabilities_by_category,
    get_role_defaults,
    resolve_capability,
    validate_capabilities,
)

logger = logging.getLogger(__name__)


async def run_get_ai_training_data(user: dict, category: str = None):
    """
    Obtém os dados de treino personalizados do agente IA.
    
    Categorias:
    - document_types: Tipos de documentos e como classificá-los
    - field_mappings: Mapeamento de campos para extração
    - client_patterns: Padrões de nomes de clientes
    - custom_rules: Regras personalizadas
    """
    query = {"type": "ai_training"}
    if category:
        query["category"] = category
    
    entries = await db.ai_training.find(query, {"_id": 0}).to_list(100)
    
    # Agrupar por categoria
    by_category = {}
    for entry in entries:
        cat = entry.get("category", "other")
        if cat not in by_category:
            by_category[cat] = []
        by_category[cat].append(entry)
    
    return {
        "total": len(entries),
        "categories": list(by_category.keys()),
        "data": by_category
    }


async def run_add_ai_training_entry(data: dict, user: dict):
    """
    Adiciona uma nova entrada de treino para o agente IA.
    
    Body:
    {
        "category": "document_types",  // ou field_mappings, client_patterns, custom_rules
        "title": "Título descritivo",
        "content": "Conteúdo de treino / instruções para a IA",
        "examples": ["exemplo1", "exemplo2"],  // Opcional
        "is_active": true  // Se deve ser usado pelo agente
    }
    """
    required_fields = ["category", "title", "content"]
    for field in required_fields:
        if field not in data:
            raise HTTPException(status_code=400, detail=f"Campo '{field}' é obrigatório")
    
    valid_categories = ["document_types", "field_mappings", "client_patterns", "custom_rules", "extraction_tips"]
    if data["category"] not in valid_categories:
        raise HTTPException(status_code=400, detail=f"Categoria inválida. Use: {valid_categories}")
    
    entry = {
        "id": str(uuid.uuid4()),
        "type": "ai_training",
        "category": data["category"],
        "title": data["title"],
        "content": data["content"],
        "examples": data.get("examples", []),
        "is_active": data.get("is_active", True),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": user.get("email", "admin"),
        "updated_at": None
    }
    
    await db.ai_training.insert_one(entry)
    
    return {
        "success": True,
        "entry": {k: v for k, v in entry.items() if k != "_id"}
    }


async def run_update_ai_training_entry(entry_id: str, data: dict, user: dict):
    """
    Actualiza uma entrada de treino existente.
    """
    existing = await db.ai_training.find_one({"id": entry_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Entrada não encontrada")
    
    update_data = {}
    if "title" in data:
        update_data["title"] = data["title"]
    if "content" in data:
        update_data["content"] = data["content"]
    if "examples" in data:
        update_data["examples"] = data["examples"]
    if "is_active" in data:
        update_data["is_active"] = data["is_active"]
    if "category" in data:
        valid_categories = ["document_types", "field_mappings", "client_patterns", "custom_rules", "extraction_tips"]
        if data["category"] not in valid_categories:
            raise HTTPException(status_code=400, detail=f"Categoria inválida. Use: {valid_categories}")
        update_data["category"] = data["category"]
    
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    update_data["updated_by"] = user.get("email", "admin")
    
    await db.ai_training.update_one(
        {"id": entry_id},
        {"$set": update_data}
    )
    
    updated = await db.ai_training.find_one({"id": entry_id}, {"_id": 0})
    return {"success": True, "entry": updated}


async def run_delete_ai_training_entry(entry_id: str, user: dict):
    """
    Remove uma entrada de treino.
    """
    result = await db.ai_training.delete_one({"id": entry_id})
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Entrada não encontrada")
    
    return {"success": True, "message": "Entrada removida"}


async def run_get_ai_training_prompt(user: dict, category: str = None):
    """
    Gera o prompt de treino consolidado a partir das entradas activas.
    Este prompt é usado pelo agente IA durante a análise de documentos.
    """
    query = {"type": "ai_training", "is_active": True}
    if category:
        query["category"] = category
    
    entries = await db.ai_training.find(query, {"_id": 0}).sort("category", 1).to_list(100)
    
    # Construir prompt por categoria
    prompt_sections = []
    
    # Agrupar por categoria
    by_category = {}
    for entry in entries:
        cat = entry.get("category", "other")
        if cat not in by_category:
            by_category[cat] = []
        by_category[cat].append(entry)
    
    category_titles = {
        "document_types": "## Tipos de Documentos",
        "field_mappings": "## Mapeamento de Campos",
        "client_patterns": "## Padrões de Nomes de Clientes",
        "custom_rules": "## Regras Personalizadas",
        "extraction_tips": "## Dicas de Extracção"
    }
    
    for cat, cat_entries in by_category.items():
        section = category_titles.get(cat, f"## {cat.title()}")
        section += "\n"
        
        for entry in cat_entries:
            section += f"\n### {entry['title']}\n"
            section += entry["content"] + "\n"
            
            if entry.get("examples"):
                section += "\nExemplos:\n"
                for ex in entry["examples"]:
                    section += f"- {ex}\n"
        
        prompt_sections.append(section)
    
    full_prompt = "\n\n".join(prompt_sections)
    
    return {
        "prompt": full_prompt,
        "entries_count": len(entries),
        "categories": list(by_category.keys())
    }


async def run_record_ai_prompt_execution(user: dict):
    """
    O23 - Regista uma execução do prompt de treino de IA.
    Incrementa o contador de execuções.
    """
    now = datetime.now(timezone.utc).isoformat()
    
    # Incrementar contador global de execuções
    await db.ai_config.update_one(
        {"type": "execution_stats"},
        {
            "$inc": {"total_executions": 1},
            "$set": {"last_executed_at": now, "last_executed_by": user.get("name", "unknown")},
            "$setOnInsert": {"type": "execution_stats", "created_at": now}
        },
        upsert=True
    )
    
    # Retornar stats actualizadas
    stats = await db.ai_config.find_one({"type": "execution_stats"}, {"_id": 0})
    return {
        "success": True,
        "total_executions": stats.get("total_executions", 1),
        "last_executed_at": stats.get("last_executed_at"),
        "last_executed_by": stats.get("last_executed_by")
    }


async def run_get_ai_training_stats(user: dict):
    """O23 - Obtém estatísticas de uso do AI Training."""
    stats = await db.ai_config.find_one({"type": "execution_stats"}, {"_id": 0}) or {}
    entries_count = await db.ai_training.count_documents({"type": "ai_training", "is_active": True})
    
    return {
        "total_executions": stats.get("total_executions", 0),
        "last_executed_at": stats.get("last_executed_at"),
        "last_executed_by": stats.get("last_executed_by"),
        "active_entries": entries_count
    }


async def run_get_ai_import_logs(user: dict, page: int = 1, limit: int = 50, status: str = None, days: int = 7, client_name: str = None):
    """
    Obtém logs de importação massiva IA para integração no menu de Logs do sistema.
    
    Query params:
    - page: Página (default 1)
    - limit: Items por página (default 50)
    - status: Filtrar por estado (success, error, warning)
    - days: Últimos N dias (default 7)
    - client_name: Filtrar por nome de cliente
    """
    skip = (page - 1) * limit
    cutoff_date = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    
    # Query base
    query = {"timestamp": {"$gte": cutoff_date}}
    
    if status == "error":
        query["resolved"] = False
    elif status == "success":
        query["resolved"] = True
    
    if client_name:
        query["client_name"] = {"$regex": client_name, "$options": "i"}
    
    # Buscar erros de importação
    errors = await db.import_errors.find(
        query,
        {"_id": 0}
    ).sort("timestamp", -1).skip(skip).limit(limit).to_list(None)
    
    # Contagem total
    total = await db.import_errors.count_documents(query)
    
    # Estatísticas rápidas
    stats = {
        "total_errors": await db.import_errors.count_documents({"timestamp": {"$gte": cutoff_date}}),
        "unresolved": await db.import_errors.count_documents({"timestamp": {"$gte": cutoff_date}, "resolved": False}),
        "resolved": await db.import_errors.count_documents({"timestamp": {"$gte": cutoff_date}, "resolved": True}),
    }
    
    # Formatar logs para UI
    formatted_logs = []
    for error in errors:
        formatted_logs.append({
            "id": error.get("id"),
            "timestamp": error.get("timestamp"),
            "severity": "error" if not error.get("resolved") else "info",
            "component": "ai_bulk_import",
            "error_type": error.get("document_type", "import_error"),
            "message": error.get("error", ""),
            "details": {
                "client_name": error.get("client_name"),
                "filename": error.get("filename"),
                "folder_name": error.get("folder_name"),
                "matching_details": error.get("matching_details")
            },
            "resolved": error.get("resolved", False),
            "user_email": error.get("user_email")
        })
    
    return {
        "logs": formatted_logs,
        "pagination": {
            "page": page,
            "limit": limit,
            "total": total,
            "total_pages": (total + limit - 1) // limit
        },
        "stats": stats
    }


async def run_resolve_ai_import_log(log_id: str, user: dict):
    """
    Marca um log de importação como resolvido.
    """
    result = await db.import_errors.update_one(
        {"id": log_id},
        {
            "$set": {
                "resolved": True,
                "resolved_at": datetime.now(timezone.utc).isoformat(),
                "resolved_by": user.get("email", "admin")
            }
        }
    )
    
    # Também actualizar na colecção ai_import_logs
    await db.ai_import_logs.update_one(
        {"id": log_id},
        {
            "$set": {
                "resolved": True,
                "resolved_at": datetime.now(timezone.utc).isoformat(),
                "resolved_by": user.get("email", "admin")
            }
        }
    )
    
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Log não encontrado")
    
    return {"success": True, "message": "Log marcado como resolvido"}


async def run_bulk_resolve_ai_import_logs(data: dict, user: dict):
    """
    Marca múltiplos logs de importação como resolvidos em massa.
    
    Body:
    - log_ids: Lista de IDs a resolver
    """
    log_ids = data.get("log_ids", [])
    if not log_ids:
        raise HTTPException(status_code=400, detail="Nenhum ID fornecido")
    
    now = datetime.now(timezone.utc).isoformat()
    resolved_by = user.get("email", "admin")
    
    # Actualizar na colecção ai_import_logs
    result = await db.ai_import_logs.update_many(
        {"id": {"$in": log_ids}, "resolved": {"$ne": True}},
        {
            "$set": {
                "resolved": True,
                "resolved_at": now,
                "resolved_by": resolved_by
            }
        }
    )
    
    # Também actualizar na colecção import_errors (legacy)
    await db.import_errors.update_many(
        {"id": {"$in": log_ids}},
        {
            "$set": {
                "resolved": True,
                "resolved_at": now,
                "resolved_by": resolved_by
            }
        }
    )
    
    return {
        "success": True,
        "resolved_count": result.modified_count,
        "message": f"{result.modified_count} logs marcados como resolvidos"
    }


async def run_get_ai_import_logs_grouped(user: dict, days: int = 7, status: str = None):
    """
    Obtém logs de importação IA agrupados por cliente.
    Mostra resumo de sucesso/erro por cliente.
    
    Query params:
    - days: Últimos N dias (default 7)
    - status: Filtrar por estado (success, error, all)
    """
    cutoff_date = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    
    # Query base
    match_stage = {"timestamp": {"$gte": cutoff_date}}
    if status == "error":
        match_stage["status"] = "error"
    elif status == "success":
        match_stage["status"] = "success"
    
    # Agregar por cliente
    pipeline = [
        {"$match": match_stage},
        {"$sort": {"timestamp": -1}},
        {"$group": {
            "_id": "$client_name",
            "total_docs": {"$sum": 1},
            "success_count": {"$sum": {"$cond": [{"$eq": ["$status", "success"]}, 1, 0]}},
            "error_count": {"$sum": {"$cond": [{"$eq": ["$status", "error"]}, 1, 0]}},
            "fields_updated": {"$sum": "$fields_count"},
            "last_import": {"$first": "$timestamp"},
            "logs": {"$push": {
                "id": "$id",
                "status": "$status",
                "filename": "$filename",
                "document_type": "$document_type",
                "timestamp": "$timestamp",
                "fields_count": "$fields_count",
                "error": "$error",
                "resolved": "$resolved"
            }}
        }},
        {"$sort": {"last_import": -1}},
        {"$project": {
            "client_name": "$_id",
            "total_docs": 1,
            "success_count": 1,
            "error_count": 1,
            "fields_updated": 1,
            "last_import": 1,
            "logs": {"$slice": ["$logs", 50]},  # Limitar a 50 logs por cliente
            "_id": 0
        }}
    ]
    
    groups = await db.ai_import_logs.aggregate(pipeline).to_list(100)
    
    # Estatísticas gerais
    stats = {
        "total_clients": len(groups),
        "total_docs": sum(g["total_docs"] for g in groups),
        "total_success": sum(g["success_count"] for g in groups),
        "total_errors": sum(g["error_count"] for g in groups),
        "total_fields": sum(g["fields_updated"] for g in groups)
    }
    
    return {
        "groups": groups,
        "stats": stats
    }


async def run_get_ai_import_logs_v2(user: dict, page: int = 1, limit: int = 50, status: str = None, days: int = 7, client_name: str = None, document_type: str = None):
    """
    Obtém logs de importação IA com dados categorizados.
    
    Query params:
    - page: Página (default 1)
    - limit: Items por página (default 50)
    - status: Filtrar por estado (success, error, partial, all)
    - days: Últimos N dias (default 7)
    - client_name: Filtrar por nome de cliente
    - document_type: Filtrar por tipo de documento (cc, irs, recibo_vencimento, etc.)
    
    Returns:
    - logs: Lista de logs com dados categorizados
    - stats: Estatísticas de sucesso/erro
    - pagination: Info de paginação
    """
    skip = (page - 1) * limit
    cutoff_date = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    
    # Query base
    query = {"created_at": {"$gte": cutoff_date}}
    
    if status == "error":
        query["status"] = "error"
    elif status == "success":
        query["status"] = "success"
    elif status == "partial":
        query["status"] = "partial"
    
    if client_name:
        query["client_name"] = {"$regex": client_name, "$options": "i"}
    
    if document_type:
        query["documents.document_type"] = document_type
    
    # Buscar logs
    logs = await db.ai_import_logs.find(
        query,
        {"_id": 0}
    ).sort("created_at", -1).skip(skip).limit(limit).to_list(None)
    
    # Contagem total
    total = await db.ai_import_logs.count_documents(query)
    
    # Estatísticas
    base_query = {"created_at": {"$gte": cutoff_date}}
    stats = {
        "total": await db.ai_import_logs.count_documents(base_query),
        "success": await db.ai_import_logs.count_documents({**base_query, "status": "success"}),
        "error": await db.ai_import_logs.count_documents({**base_query, "status": "error"}),
        "partial": await db.ai_import_logs.count_documents({**base_query, "status": "partial"}),
        "total_documents": 0,
        "success_documents": 0,
        "error_documents": 0,
    }
    
    # Contar documentos processados
    pipeline = [
        {"$match": base_query},
        {"$group": {
            "_id": None, 
            "total_docs": {"$sum": "$total_documents"},
            "success_docs": {"$sum": "$success_count"},
            "error_docs": {"$sum": "$error_count"}
        }}
    ]
    agg_result = await db.ai_import_logs.aggregate(pipeline).to_list(1)
    if agg_result:
        stats["total_documents"] = agg_result[0].get("total_docs", 0)
        stats["success_documents"] = agg_result[0].get("success_docs", 0)
        stats["error_documents"] = agg_result[0].get("error_docs", 0)
    
    # Taxa de sucesso
    if stats["total_documents"] > 0:
        stats["success_rate"] = round(stats["success_documents"] / stats["total_documents"] * 100, 1)
    else:
        stats["success_rate"] = 0
    
    return {
        "logs": logs,
        "pagination": {
            "page": page,
            "limit": limit,
            "total": total,
            "total_pages": (total + limit - 1) // limit if total > 0 else 1
        },
        "stats": stats
    }


async def run_get_ai_import_log_detail(log_id: str, user: dict):
    """
    Obtém detalhes de um log de importação específico.
    Inclui dados categorizados por tabs.
    """
    log = await db.ai_import_logs.find_one(
        {"id": log_id},
        {"_id": 0}
    )
    
    if not log:
        raise HTTPException(status_code=404, detail="Log não encontrado")
    
    return log



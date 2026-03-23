"""
====================================================================
ROTAS DE LOGS DE IMPORTAÇÃO IA - CREDITOIMO
====================================================================
Endpoints para gestão e visualização de logs de importações IA.
====================================================================
"""

import logging
from typing import Optional, List
from datetime import datetime, timezone
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query

from database import db
from services.auth import get_current_user
from models.ai_import_log import (
    AIImportLog, 
    AIImportLogCreate, 
    AIImportLogSummary,
    ImportStatus,
    DocumentImportResult
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ai-import-logs", tags=["AI Import Logs"])


@router.get("")
async def list_ai_import_logs(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    status: Optional[str] = None,
    process_id: Optional[str] = None,
    search: Optional[str] = None,
    user: dict = Depends(get_current_user)
):
    """
    Lista logs de importações IA com paginação e filtros.
    
    Args:
        page: Página atual
        limit: Itens por página
        status: Filtrar por status (success, partial, error)
        process_id: Filtrar por processo específico
        search: Pesquisar por nome de cliente
    """
    # Construir query
    query = {}
    
    if status:
        query["status"] = status
    
    if process_id:
        query["process_id"] = process_id
    
    if search:
        query["client_name"] = {"$regex": search, "$options": "i"}
    
    # Contar total
    total = await db.ai_import_logs.count_documents(query)
    
    # Buscar logs com paginação
    skip = (page - 1) * limit
    logs = await db.ai_import_logs.find(
        query,
        {
            "_id": 0,
            "id": 1,
            "process_id": 1,
            "client_name": 1,
            "created_at": 1,
            "created_by_name": 1,
            "status": 1,
            "total_documents": 1,
            "success_count": 1,
            "error_count": 1,
            "partial_count": 1,
            "duration_ms": 1
        }
    ).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    
    return {
        "logs": logs,
        "total": total,
        "page": page,
        "limit": limit,
        "total_pages": (total + limit - 1) // limit
    }


@router.get("/stats")
async def get_ai_import_stats(
    days: int = Query(30, ge=1, le=365),
    user: dict = Depends(get_current_user)
):
    """
    Estatísticas gerais de importações IA.
    """
    from datetime import timedelta
    
    since_date = datetime.now(timezone.utc) - timedelta(days=days)
    
    pipeline = [
        {"$match": {"created_at": {"$gte": since_date.isoformat()}}},
        {"$group": {
            "_id": None,
            "total_imports": {"$sum": 1},
            "total_documents": {"$sum": "$total_documents"},
            "total_success": {"$sum": "$success_count"},
            "total_errors": {"$sum": "$error_count"},
            "avg_duration_ms": {"$avg": "$duration_ms"}
        }}
    ]
    
    result = await db.ai_import_logs.aggregate(pipeline).to_list(1)
    
    if result:
        stats = result[0]
        del stats["_id"]
        stats["success_rate"] = (
            round(stats["total_success"] / stats["total_documents"] * 100, 1)
            if stats["total_documents"] > 0 else 0
        )
        return stats
    
    return {
        "total_imports": 0,
        "total_documents": 0,
        "total_success": 0,
        "total_errors": 0,
        "avg_duration_ms": 0,
        "success_rate": 0
    }


@router.get("/{log_id}")
async def get_ai_import_log(
    log_id: str,
    user: dict = Depends(get_current_user)
):
    """
    Obtém detalhes completos de um log de importação.
    """
    log = await db.ai_import_logs.find_one({"id": log_id}, {"_id": 0})
    
    if not log:
        raise HTTPException(status_code=404, detail="Log não encontrado")
    
    return log


@router.delete("/{log_id}")
async def delete_ai_import_log(
    log_id: str,
    user: dict = Depends(get_current_user)
):
    """
    Elimina um log de importação (apenas admin/ceo).
    """
    if user.get("role") not in ["admin", "ceo"]:
        raise HTTPException(status_code=403, detail="Apenas administradores podem eliminar logs")
    
    result = await db.ai_import_logs.delete_one({"id": log_id})
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Log não encontrado")
    
    return {"success": True, "message": "Log eliminado com sucesso"}


# Função auxiliar para criar log (usada pelo serviço de análise)
async def create_ai_import_log(
    process_id: str,
    client_name: str,
    created_by: str = None,
    created_by_name: str = None
) -> str:
    """
    Cria um novo log de importação IA.
    
    Returns:
        ID do log criado
    """
    log_id = str(uuid.uuid4())
    
    log = {
        "id": log_id,
        "process_id": process_id,
        "client_name": client_name,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": created_by,
        "created_by_name": created_by_name,
        "status": ImportStatus.PENDING.value,
        "total_documents": 0,
        "success_count": 0,
        "error_count": 0,
        "partial_count": 0,
        "duration_ms": None,
        "documents": [],
        "auto_filled_fields": {},
        "conflict_resolutions": [],
        "notes": None
    }
    
    await db.ai_import_logs.insert_one(log)
    logger.info(f"Log de importação IA criado: {log_id} para cliente {client_name}")
    
    return log_id


async def update_ai_import_log(
    log_id: str,
    document_result: dict = None,
    status: str = None,
    auto_filled_fields: dict = None,
    duration_ms: int = None,
    notes: str = None
):
    """
    Actualiza um log de importação IA.
    """
    update = {"$set": {}}
    
    if document_result:
        # Adicionar resultado de documento
        await db.ai_import_logs.update_one(
            {"id": log_id},
            {
                "$push": {"documents": document_result},
                "$inc": {
                    "total_documents": 1,
                    "success_count": 1 if document_result.get("status") == "success" else 0,
                    "error_count": 1 if document_result.get("status") == "error" else 0,
                    "partial_count": 1 if document_result.get("status") == "partial" else 0
                }
            }
        )
    
    if status:
        update["$set"]["status"] = status
    
    if auto_filled_fields:
        update["$set"]["auto_filled_fields"] = auto_filled_fields
    
    if duration_ms is not None:
        update["$set"]["duration_ms"] = duration_ms
    
    if notes:
        update["$set"]["notes"] = notes
    
    if update["$set"]:
        await db.ai_import_logs.update_one({"id": log_id}, update)


async def finalize_ai_import_log(log_id: str, duration_ms: int):
    """
    Finaliza um log de importação calculando o status final.
    """
    log = await db.ai_import_logs.find_one({"id": log_id})
    
    if not log:
        return
    
    # Determinar status final
    if log["error_count"] == log["total_documents"]:
        final_status = ImportStatus.ERROR.value
    elif log["error_count"] > 0:
        final_status = ImportStatus.PARTIAL.value
    else:
        final_status = ImportStatus.SUCCESS.value
    
    await db.ai_import_logs.update_one(
        {"id": log_id},
        {"$set": {
            "status": final_status,
            "duration_ms": duration_ms
        }}
    )
    
    logger.info(f"Log de importação IA finalizado: {log_id} - Status: {final_status}")

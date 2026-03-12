"""
Import Errors Module
====================
Gestão de erros de importação para análise e correcção.
"""
import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from enum import Enum

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from database import db
from models.auth import UserRole
from services.auth import require_roles

logger = logging.getLogger(__name__)
router = APIRouter()


class ErrorSeverity(str, Enum):
    """Níveis de severidade de erros."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ErrorCategory(str, Enum):
    """Categorias de erros de importação."""
    FILE_READ = "file_read"
    FILE_FORMAT = "file_format"
    AI_ANALYSIS = "ai_analysis"
    CLIENT_MATCH = "client_match"
    DATA_VALIDATION = "data_validation"
    DUPLICATE = "duplicate"
    PERMISSION = "permission"
    UNKNOWN = "unknown"


# ====================================================================
# MODELOS PYDANTIC
# ====================================================================

class ImportError(BaseModel):
    """Modelo de erro de importação."""
    id: str
    session_id: Optional[str] = None
    job_id: Optional[str] = None
    filename: str
    s3_path: Optional[str] = None
    category: ErrorCategory
    severity: ErrorSeverity
    message: str
    details: Optional[Dict[str, Any]] = None
    stack_trace: Optional[str] = None
    created_at: str
    resolved: bool = False
    resolved_at: Optional[str] = None
    resolved_by: Optional[str] = None


class ErrorResolutionRequest(BaseModel):
    """Request para resolver erro."""
    resolution_notes: Optional[str] = None


# ====================================================================
# FUNÇÕES DE GESTÃO DE ERROS
# ====================================================================

async def log_import_error(
    filename: str,
    category: ErrorCategory,
    message: str,
    severity: ErrorSeverity = ErrorSeverity.MEDIUM,
    session_id: str = None,
    job_id: str = None,
    s3_path: str = None,
    details: dict = None,
    stack_trace: str = None
) -> str:
    """
    Registar erro de importação na base de dados.
    
    Returns:
        ID do erro criado
    """
    import uuid
    
    error_id = str(uuid.uuid4())
    
    error_doc = {
        "id": error_id,
        "session_id": session_id,
        "job_id": job_id,
        "filename": filename,
        "s3_path": s3_path,
        "category": category.value,
        "severity": severity.value,
        "message": message,
        "details": details or {},
        "stack_trace": stack_trace,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "resolved": False,
        "resolved_at": None,
        "resolved_by": None
    }
    
    await db.import_errors.insert_one(error_doc)
    
    logger.error(f"[IMPORT ERROR] {category.value}: {message} (file: {filename})")
    
    return error_id


async def get_import_errors(
    session_id: str = None,
    job_id: str = None,
    category: str = None,
    severity: str = None,
    resolved: bool = None,
    limit: int = 100
) -> List[dict]:
    """Obter lista de erros de importação com filtros."""
    query = {}
    
    if session_id:
        query["session_id"] = session_id
    if job_id:
        query["job_id"] = job_id
    if category:
        query["category"] = category
    if severity:
        query["severity"] = severity
    if resolved is not None:
        query["resolved"] = resolved
    
    errors = await db.import_errors.find(
        query,
        {"_id": 0}
    ).sort("created_at", -1).limit(limit).to_list(limit)
    
    return errors


async def resolve_import_error(error_id: str, user_email: str, notes: str = None) -> bool:
    """Marcar erro como resolvido."""
    result = await db.import_errors.update_one(
        {"id": error_id, "resolved": False},
        {"$set": {
            "resolved": True,
            "resolved_at": datetime.now(timezone.utc).isoformat(),
            "resolved_by": user_email,
            "resolution_notes": notes
        }}
    )
    
    return result.modified_count > 0


async def get_error_statistics(days: int = 7) -> dict:
    """Obter estatísticas de erros."""
    from datetime import timedelta
    
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    
    errors = await db.import_errors.find(
        {"created_at": {"$gte": cutoff}},
        {"_id": 0}
    ).to_list(1000)
    
    if not errors:
        return {
            "total": 0,
            "resolved": 0,
            "unresolved": 0,
            "by_category": {},
            "by_severity": {},
            "resolution_rate": 0
        }
    
    total = len(errors)
    resolved = len([e for e in errors if e.get("resolved")])
    unresolved = total - resolved
    
    by_category = {}
    by_severity = {}
    
    for e in errors:
        cat = e.get("category", "unknown")
        sev = e.get("severity", "medium")
        
        by_category[cat] = by_category.get(cat, 0) + 1
        by_severity[sev] = by_severity.get(sev, 0) + 1
    
    return {
        "period_days": days,
        "total": total,
        "resolved": resolved,
        "unresolved": unresolved,
        "by_category": by_category,
        "by_severity": by_severity,
        "resolution_rate": round((resolved / total) * 100, 1) if total > 0 else 0
    }


# ====================================================================
# ENDPOINTS
# ====================================================================

@router.get("/import-errors")
async def list_import_errors(
    session_id: Optional[str] = None,
    job_id: Optional[str] = None,
    category: Optional[str] = None,
    severity: Optional[str] = None,
    resolved: Optional[bool] = None,
    limit: int = Query(100, le=500),
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """Lista erros de importação com filtros."""
    errors = await get_import_errors(
        session_id=session_id,
        job_id=job_id,
        category=category,
        severity=severity,
        resolved=resolved,
        limit=limit
    )
    
    return {"errors": errors, "total": len(errors)}


@router.get("/import-errors/stats")
async def get_error_stats(
    days: int = Query(7, ge=1, le=90),
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """Obtém estatísticas de erros de importação."""
    return await get_error_statistics(days)


@router.get("/import-errors/{error_id}")
async def get_import_error(
    error_id: str,
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """Obtém detalhes de um erro específico."""
    error = await db.import_errors.find_one({"id": error_id}, {"_id": 0})
    
    if not error:
        raise HTTPException(status_code=404, detail="Erro não encontrado")
    
    return error


@router.post("/import-errors/{error_id}/resolve")
async def resolve_error(
    error_id: str,
    request: ErrorResolutionRequest,
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """Marca erro como resolvido."""
    success = await resolve_import_error(
        error_id,
        user.get("email", "unknown"),
        request.resolution_notes
    )
    
    if not success:
        raise HTTPException(status_code=404, detail="Erro não encontrado ou já resolvido")
    
    return {"success": True, "message": "Erro marcado como resolvido"}


@router.delete("/import-errors/{error_id}")
async def delete_import_error(
    error_id: str,
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """Remove um erro de importação."""
    result = await db.import_errors.delete_one({"id": error_id})
    
    return {"success": result.deleted_count > 0}


@router.post("/import-errors/clear-resolved")
async def clear_resolved_errors(
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """Remove todos os erros resolvidos."""
    result = await db.import_errors.delete_many({"resolved": True})
    
    return {"deleted": result.deleted_count}


@router.post("/import-errors/bulk-resolve")
async def bulk_resolve_errors(
    error_ids: List[str],
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """Resolve múltiplos erros de uma vez."""
    resolved_count = 0
    
    for error_id in error_ids:
        if await resolve_import_error(error_id, user.get("email", "unknown")):
            resolved_count += 1
    
    return {"resolved": resolved_count, "total": len(error_ids)}

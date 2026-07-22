"""Import-error list/resolve handlers for AI bulk import.

Extraído de `routes/ai_bulk.py`. Named `ai_bulk_import_errors` to avoid
colliding with `routes.ai_bulk.import_errors`.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from database import db


async def run_get_import_errors(
    user: dict,
    limit: int = 100,
    document_type: Optional[str] = None,
    resolved: Optional[bool] = None,
):
    """Obter lista de erros de importação."""
    query = {}
    
    if document_type:
        query["document_type"] = document_type
    if resolved is not None:
        query["resolved"] = resolved
    
    errors = await db.import_errors.find(
        query,
        {"_id": 0}
    ).sort("timestamp", -1).to_list(length=limit)
    
    error_summary = {}
    for err in errors:
        error_key = err.get("error", "Desconhecido")[:100]
        if error_key not in error_summary:
            error_summary[error_key] = {
                "count": 0,
                "document_types": set(),
                "clients": set()
            }
        error_summary[error_key]["count"] += 1
        error_summary[error_key]["document_types"].add(err.get("document_type", "?"))
        error_summary[error_key]["clients"].add(err.get("client_name", "?"))
    
    for key in error_summary:
        error_summary[key]["document_types"] = list(error_summary[key]["document_types"])
        error_summary[key]["clients"] = list(error_summary[key]["clients"])[:5]
    
    return {
        "total_errors": len(errors),
        "errors": errors,
        "summary": error_summary
    }



async def run_resolve_import_error(
    error_id: str,
    user: dict,
):
    """Marcar um erro de importação como resolvido."""
    result = await db.import_errors.update_one(
        {"id": error_id},
        {"$set": {"resolved": True, "resolved_by": user.get("email"), "resolved_at": datetime.now(timezone.utc).isoformat()}}
    )
    
    if result.modified_count > 0:
        return {"success": True, "message": "Erro marcado como resolvido"}
    else:
        return {"success": False, "message": "Erro não encontrado"}


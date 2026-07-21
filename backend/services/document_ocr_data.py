"""
OCR status + resolução de conflitos de dados do processo.

Extraído de `routes/documents.py` (ocr-status / data-suggestions /
resolve-conflict / confirm-data).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import HTTPException

from database import db
from services.document_constants import ERROR_PROCESS_NOT_FOUND

logger = logging.getLogger(__name__)


async def run_get_document_ocr_status(process_id: str) -> dict:
    """Estado OCR (extracted_data) dos documentos de um processo."""
    process = await db.processes.find_one({"id": process_id})
    if not process:
        raise HTTPException(status_code=404, detail=ERROR_PROCESS_NOT_FOUND)

    docs = await db.document_metadata.find(
        {"process_id": process_id},
        {
            "_id": 0,
            "id": 1,
            "filename": 1,
            "ai_category": 1,
            "extracted_data": 1,
            "is_categorized": 1,
            "categorized_at": 1,
        },
    ).to_list(100)

    docs_with_ocr = [d for d in docs if d.get("extracted_data")]
    return {
        "success": True,
        "total_documents": len(docs),
        "documents_with_ocr": len(docs_with_ocr),
        "documents": docs_with_ocr,
    }


async def run_get_data_suggestions(process_id: str) -> dict:
    """Sugestões de conflito pendentes (DataConflictResolver)."""
    from services.data_conflict import get_pending_suggestions

    process = await db.processes.find_one({"id": process_id})
    if not process:
        raise HTTPException(status_code=404, detail=ERROR_PROCESS_NOT_FOUND)

    suggestions = await get_pending_suggestions(process_id)
    return {
        "success": True,
        "process_id": process_id,
        "is_data_confirmed": process.get("is_data_confirmed", False),
        "suggestions": suggestions,
        "count": len(suggestions),
    }


async def run_resolve_data_conflict(
    process_id: str,
    data: dict,
    *,
    user: dict,
) -> dict:
    """Resolve um conflito individual (choice: current|ai)."""
    from services.data_conflict import resolve_suggestion

    suggestion_id = data.get("suggestion_id")
    field = data.get("field")
    choice = data.get("choice", "current")

    if not suggestion_id and not field:
        raise HTTPException(
            status_code=400, detail="suggestion_id ou field é obrigatório"
        )
    if choice not in ("current", "ai"):
        raise HTTPException(
            status_code=400, detail="choice deve ser 'current' ou 'ai'"
        )

    if not suggestion_id:
        suggestion = await db.data_suggestions.find_one(
            {"process_id": process_id, "field": field, "resolved": False}
        )
        if not suggestion:
            raise HTTPException(
                status_code=404, detail="Sugestão não encontrada para este campo"
            )
        suggestion_id = suggestion["id"]

    result = await resolve_suggestion(suggestion_id, choice, user.get("id"))
    if not result["success"]:
        raise HTTPException(status_code=404, detail=result["message"])
    return result


async def run_confirm_process_data(
    process_id: str,
    data: dict,
    *,
    user: dict,
) -> dict:
    """Confirma ou desbloqueia dados do processo (is_data_confirmed)."""
    confirmed = data.get("confirmed", True)

    process = await db.processes.find_one({"id": process_id})
    if not process:
        raise HTTPException(status_code=404, detail=ERROR_PROCESS_NOT_FOUND)

    now = datetime.now(timezone.utc).isoformat()
    await db.processes.update_one(
        {"id": process_id},
        {
            "$set": {
                "is_data_confirmed": confirmed,
                "data_confirmed_at": now if confirmed else None,
                "data_confirmed_by": user.get("id") if confirmed else None,
                "updated_at": now,
            }
        },
    )
    return {
        "success": True,
        "message": (
            "Dados confirmados com sucesso" if confirmed else "Dados desbloqueados"
        ),
        "is_data_confirmed": confirmed,
    }

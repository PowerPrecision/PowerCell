"""Reset client AI-extracted data API handler.

Extraído de `routes/ai.py`. Prefer `ai_api_*` — do **not** overwrite
`ai_document.py` / analyzers.
"""
from __future__ import annotations

import logging

from fastapi import HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class ResetClientDataRequest(BaseModel):
    """Request to reset client extracted data."""
    process_id: str
    reset_personal: bool = True
    reset_financial: bool = True
    reset_real_estate: bool = True


async def run_reset_client_data(request: ResetClientDataRequest, user: dict) -> dict:
    """Reset/clear extracted AI data for a specific client (admin only)."""
    from database import db

    update_fields = {}

    if request.reset_personal:
        update_fields["personal_data"] = {}
    if request.reset_financial:
        update_fields["financial_data"] = {}
    if request.reset_real_estate:
        update_fields["real_estate_data"] = {}

    if not update_fields:
        raise HTTPException(status_code=400, detail="Nenhum campo selecionado para limpar")

    process = await db.processes.find_one({"id": request.process_id})
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")

    result = await db.processes.update_one(
        {"id": request.process_id},
        {"$set": update_fields},
    )

    if result.modified_count > 0:
        logger.info(f"Dados do cliente {request.process_id} limpos por {user.get('email')}")
        return {
            "success": True,
            "message": f"Dados limpos com sucesso para o processo {request.process_id}",
            "fields_reset": list(update_fields.keys()),
        }
    return {
        "success": True,
        "message": "Nenhuma alteração necessária (dados já estavam vazios)",
        "fields_reset": [],
    }

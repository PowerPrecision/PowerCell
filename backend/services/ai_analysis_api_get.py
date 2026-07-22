"""GET existing AI executive summary handler.

Extraído de `routes/ai_analysis.py`. Prefer `ai_analysis_api_*` —
do **not** overwrite analyzer core services.
"""
from __future__ import annotations

from typing import Any, Dict

from fastapi import HTTPException

from database import db


async def run_get_analysis(process_id: str, user: dict) -> Dict[str, Any]:
    """Return existing ``ai_executive_summary`` / ``ai_analysis_date`` (no AI call)."""
    process = await db.processes.find_one(
        {"id": process_id},
        {"_id": 0, "ai_executive_summary": 1, "ai_analysis_date": 1, "id": 1},
    )
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")

    return {
        "process_id": process_id,
        "ai_executive_summary": process.get("ai_executive_summary"),
        "ai_analysis_date": process.get("ai_analysis_date"),
    }

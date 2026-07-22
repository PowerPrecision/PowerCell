"""Audit trail list / stats handlers.

Extraído de `routes/audit.py`.
Do **not** overwrite audit_trail_service.py — use audit_api_*.
"""
from __future__ import annotations

import logging

from fastapi import HTTPException

from services.audit_trail_service import get_audit_trail, get_audit_stats

logger = logging.getLogger(__name__)


async def run_list_audit_trail(
    process_id=None,
    user_id=None,
    action_type=None,
    source=None,
    date_from=None,
    date_to=None,
    ai_suggested=None,
    page: int = 1,
    page_size: int = 50,
):
    try:
        return await get_audit_trail(
            process_id=process_id,
            user_id=user_id,
            action_type=action_type,
            source=source,
            date_from=date_from,
            date_to=date_to,
            ai_suggested=ai_suggested,
            page=page,
            page_size=page_size,
        )
    except Exception as e:
        logger.error(f"Erro ao consultar audit trail: {e}")
        raise HTTPException(status_code=500, detail="Erro ao consultar registos de auditoria")


async def run_audit_statistics():
    try:
        return await get_audit_stats()
    except Exception as e:
        logger.error(f"Erro ao obter estatísticas de auditoria: {e}")
        raise HTTPException(status_code=500, detail="Erro ao obter estatísticas")

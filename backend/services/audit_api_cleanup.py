"""Audit trail cleanup handler.

Extraído de `routes/audit.py`.
Do **not** overwrite audit_trail_service.py — use audit_api_*.
"""
from __future__ import annotations

import logging

from fastapi import HTTPException

from services.audit_trail_service import cleanup_old_records

logger = logging.getLogger(__name__)


async def run_trigger_cleanup(days, user: dict):
    try:
        deleted_count = await cleanup_old_records(days=days)
        logger.info(
            f"Cleanup de audit trail executado por {user.get('email')}: "
            f"{deleted_count} registos eliminados"
        )
        return {
            "success": True,
            "deleted_count": deleted_count,
            "message": f"{deleted_count} registos eliminados com sucesso",
        }
    except Exception as e:
        logger.error(f"Erro no cleanup de audit trail: {e}")
        raise HTTPException(status_code=500, detail="Erro ao limpar registos de auditoria")

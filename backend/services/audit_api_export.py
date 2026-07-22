"""Audit trail export handler.

Extraído de `routes/audit.py`.
Do **not** overwrite audit_trail_service.py — use audit_api_*.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import HTTPException
from fastapi.responses import StreamingResponse

from services.audit_trail_service import export_audit_trail

logger = logging.getLogger(__name__)


async def run_export_audit(
    process_id=None,
    user_id=None,
    source=None,
    date_from=None,
    date_to=None,
):
    try:
        csv_content = await export_audit_trail(
            process_id=process_id,
            user_id=user_id,
            source=source,
            date_from=date_from,
            date_to=date_to,
        )

        filename = f"audit_trail_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"

        return StreamingResponse(
            iter([csv_content]),
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename={filename}",
            },
        )
    except Exception as e:
        logger.error(f"Erro ao exportar audit trail: {e}")
        raise HTTPException(status_code=500, detail="Erro ao exportar registos de auditoria")

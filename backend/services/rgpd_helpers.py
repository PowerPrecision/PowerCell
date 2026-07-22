"""Shared helpers for RGPD route thinning.

Extraído de `routes/rgpd.py`. Do **not** collide with existing
`services/rgpd_service.py` / `services/gdpr.py`.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from urllib.parse import urlparse

from fastapi import HTTPException

from database import db
from services.rgpd_service import RGPD_REQUESTS_COLLECTION

logger = logging.getLogger(__name__)


async def _add_process_activity(
    process_id: str,
    user_id: str,
    user_name: str,
    action: str,
    details: str = "",
):
    """Insere uma atividade/comentário automático na timeline do processo."""
    try:
        activity = {
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "user_name": user_name,
            "action": action,
            "details": details,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "type": "system",
        }
        await db.processes.update_one(
            {"id": process_id},
            {"$push": {"activities": activity}},
        )
    except Exception as e:
        logger.warning(
            f"Não foi possível registar atividade RGPD no processo {process_id}: {e}"
        )


async def _get_rgpd_or_404(request_id: str):
    """
    Função auxiliar para obter um RGPD ou lançar erro 404.

    Args:
        request_id: ID do pedido RGPD

    Returns:
        Documento do RGPD

    Raises:
        HTTPException: Se o RGPD não for encontrado
    """
    rgpd = await db[RGPD_REQUESTS_COLLECTION].find_one({"id": request_id})
    if not rgpd:
        raise HTTPException(status_code=404, detail="RGPD não encontrado")
    return rgpd


def _frontend_base_url_from_request(request, *, log_prefix: str = "[RGPD]") -> str | None:
    """Determina URL base do frontend a partir do Referer/Origin do staff."""
    frontend_base_url = None
    try:
        referer = request.headers.get("referer") or request.headers.get("origin")
        if referer:
            parsed = urlparse(referer)
            if parsed.scheme and parsed.netloc:
                frontend_base_url = f"{parsed.scheme}://{parsed.netloc}"
    except Exception as _err:
        logger.warning(f"{log_prefix} Não foi possível determinar base_url do Referer: {_err}")
    return frontend_base_url

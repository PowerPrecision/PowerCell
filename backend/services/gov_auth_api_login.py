"""Gov-auth login handler.

Extraído de `routes/gov_auth.py`.
"""
from __future__ import annotations

import base64
import logging
from typing import Optional

from fastapi.responses import RedirectResponse

from services.gov_auth_api_helpers import FRONTEND_URL, IS_MOCK

logger = logging.getLogger(__name__)


async def run_gov_auth_login(redirect: Optional[str] = None):
    """Inicia o fluxo de autenticação via Autenticação.gov (Chave Móvel Digital)."""
    frontend_base = redirect or FRONTEND_URL

    if IS_MOCK:
        logger.info("[GOV_AUTH] Modo MOCK — a redirecionar para callback de teste")
        callback_url = (
            f"/api/gov-auth/callback"
            f"?code=mock123"
            f"&state={base64.urlsafe_b64encode(frontend_base.encode()).decode()}"
        )
        return RedirectResponse(url=callback_url)

    # ── MODO PRODUÇÃO (futuro) ──
    logger.warning("[GOV_AUTH] Modo PRODUÇÃO não implementado — a usar mock")
    callback_url = (
        f"/api/gov-auth/callback"
        f"?code=mock123"
        f"&state={base64.urlsafe_b64encode(frontend_base.encode()).decode()}"
    )
    return RedirectResponse(url=callback_url)

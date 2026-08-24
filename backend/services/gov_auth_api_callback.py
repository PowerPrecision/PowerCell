"""Gov-auth OAuth callback handler.

Extraído de `routes/gov_auth.py`.
"""
from __future__ import annotations

import base64
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi.responses import RedirectResponse

from services.gov_auth_api_helpers import (
    FRONTEND_URL,
    IS_MOCK,
    MOCK_CITIZEN,
    create_gov_jwt,
    resolve_safe_redirect_base,
)

logger = logging.getLogger(__name__)


async def run_gov_auth_callback(code: str, state: Optional[str] = None):
    """Recebe o código de autorização da AMA e devolve os dados do cidadão."""
    frontend_base = FRONTEND_URL
    if state:
        try:
            decoded_state = base64.urlsafe_b64decode(state.encode()).decode()
        except Exception:
            decoded_state = None

        # Mitigação Open Redirect: só aceita o destino decodificado do
        # `state` se pertencer a um domínio permitido (evita reenviar o
        # gov_token, ainda que mock, para um domínio arbitrário).
        if decoded_state:
            frontend_base = resolve_safe_redirect_base(decoded_state)
            if frontend_base != decoded_state:
                logger.warning(
                    "[GOV_AUTH] 'state' recusado (domínio de redirecionamento "
                    f"não permitido): {decoded_state!r}"
                )

    if IS_MOCK or code == "mock123":
        logger.info(
            f"[GOV_AUTH] Modo MOCK — a gerar dados fictícios do cidadão "
            f"(code={code})"
        )
        citizen_data = {**MOCK_CITIZEN, "verified_at": datetime.now(timezone.utc).isoformat()}
    else:
        logger.warning("[GOV_AUTH] Modo PRODUÇÃO não implementado — a usar mock")
        citizen_data = {**MOCK_CITIZEN, "verified_at": datetime.now(timezone.utc).isoformat()}

    gov_token = create_gov_jwt(citizen_data)
    redirect_url = f"{frontend_base}/public-form?gov_token={gov_token}"

    logger.info(
        f"[GOV_AUTH] A redirecionar para o frontend com dados verificados "
        f"(nome={citizen_data.get('nome', '?')}, nif={citizen_data.get('nif', '?')})"
    )

    return RedirectResponse(url=redirect_url)

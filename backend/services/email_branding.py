"""Resolução do logótipo da empresa para emails transaccionais.

PACOTE 11 (Eixo 2 — "Logo no Email Base"): os emails transaccionais base
(welcome, convites, confirmações) saíam SEM a imagem/logo da empresa no
header — apenas texto hardcoded. Este helper injecta o ``company.logo_url``
nos templates HTML do backend.

Fontes de resolução (por ordem de prioridade):
1. ``db.system_config`` (documento ``_id: "main"``, secção ``settings``,
   campo ``logo_url``) — configuração global do sistema;
2. ``db.companies`` (campo ``logo_url`` da primeira empresa activa) —
   multi-tenant.

Valores relativos (chaves S3) são resolvidos para URL pré-assinado via
``services.companies_crud_api_helpers.resolve_logo_url`` (7 dias de
validade — suficiente para emails transaccionais).

Degradação graciosa: BD indisponível / logo ausente → ``None`` (o template
renderiza apenas o texto do header, como antes). Nunca levanta excepção.
"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)


async def resolve_company_logo_url() -> Optional[str]:
    """URL absoluto (ou pré-assinado S3) do logo da empresa, ou None."""
    from database import db
    from services.companies_crud_api_helpers import resolve_logo_url

    # 1) SystemConfig global (settings.logo_url)
    try:
        config = await db.system_config.find_one({"_id": "main"}, {"_id": 0})
        if config:
            settings = config.get("settings") or {}
            logo = resolve_logo_url(settings.get("logo_url"))
            if logo:
                return logo
    except Exception as e:
        logger.debug(f"[EMAIL-BRANDING] system_config indisponível: {e}")

    # 2) Primeira empresa activa com logo (multi-tenant)
    try:
        company = await db.companies.find_one(
            {"is_active": {"$ne": False}, "logo_url": {"$nin": [None, ""]}},
            {"_id": 0, "logo_url": 1},
        )
        if company:
            logo = resolve_logo_url(company.get("logo_url"))
            if logo:
                return logo
    except Exception as e:
        logger.debug(f"[EMAIL-BRANDING] companies indisponível: {e}")

    return None


def build_email_header_logo_html(logo_url: Optional[str], *, alt: str = "") -> str:
    """Fragmento HTML ``<img>`` do logo para o header de emails.

    Devolve string vazia quando não há logo — os templates inserem o
    fragmento tal qual, sem condicionais no f-string caller.
    """
    if not logo_url:
        return ""
    alt_attr = (alt or "Logótipo da empresa").replace('"', "'")
    return (
        f'<img src="{logo_url}" alt="{alt_attr}" '
        f'style="max-height: 56px; max-width: 180px; width: auto; '
        f'display: block; margin: 0 auto 10px auto; border-radius: 6px;" />'
    )

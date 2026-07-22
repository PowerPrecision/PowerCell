"""Logo URL resolution helper for companies CRUD.

Extraído de `routes/companies_crud.py`.
Prefer companies_crud_api_* / company_crud_* — avoid colliding with existing
company services.
"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)


def resolve_logo_url(logo_value) -> Optional[str]:
    """
    Resolve o campo ``logo_url`` para um URL carregável pelo browser.

    O campo ``logo_url`` pode conter:
    - ``None`` / vazio → devolve ``None``.
    - Um URL absoluto (``http://`` / ``https://``) → devolve como está.
    - Uma chave S3 → gera um URL pré-assinado com validade de 7 dias.
    """
    if not logo_value or not isinstance(logo_value, str):
        return None
    if logo_value.startswith(("http://", "https://")):
        return logo_value
    try:
        from services.s3_storage import s3_service
        if s3_service.is_configured():
            url = s3_service.get_presigned_url(
                logo_value, expiration=7 * 24 * 3600,
            )
            if url:
                return url
    except Exception as e:
        logger.warning(
            f"[COMPANIES] Erro ao gerar pre-signed URL para logo "
            f"'{logo_value}': {e}"
        )
    return None

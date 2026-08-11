"""
Helper partilhado para determinar a URL base do frontend.

Usado para construir links públicos (magic links do portal, impersonate, etc.).
Extraído para eliminar a duplicação entre `routes/processes.py` e
`routes/portal_admin.py`.
"""
import os
import logging
from urllib.parse import urlparse

from fastapi import Request

logger = logging.getLogger(__name__)


def get_frontend_url(request: Request) -> str:
    """
    Obtém a URL base do frontend para construir links públicos.

    Prioridade:
    1. Header Referer/Origin (vem do browser do staff — domínio correto).
    2. Env var FRONTEND_URL (configurada no deploy).
    3. String vazia (sem fallback hardcoded; o chamador decide o que fazer).

    Garante que os links funcionam independentemente do domínio de deploy
    (Vercel, Netlify, domínio custom).
    """
    referer = request.headers.get("referer") or request.headers.get("origin")
    if referer:
        parsed = urlparse(referer)
        if parsed.scheme and parsed.netloc:
            return f"{parsed.scheme}://{parsed.netloc}"

    frontend_url = os.environ.get("FRONTEND_URL")
    if frontend_url:
        return frontend_url.rstrip("/")

    logger.warning(
        "FRONTEND_URL não configurada e sem Referer/Origin header — "
        "não é possível determinar a URL do frontend. Configure FRONTEND_URL."
    )
    return ""

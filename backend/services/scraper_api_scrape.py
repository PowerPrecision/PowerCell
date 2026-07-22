"""Scrape / crawl handlers for scraper routes.

Extraído de `routes/scraper.py`.
Do **not** overwrite `services/scraper.py` / `gov_scraper.py` / `property_scraper.py`.
"""
from __future__ import annotations

import logging

from fastapi import HTTPException

from services.scraper import crawl_properties, property_scraper
from services.scraper_api_models import (
    FRIENDLY_SCRAPE_ERRORS,
    CrawlRequest,
    ScrapeRequest,
    ScrapeResponse,
)

logger = logging.getLogger(__name__)


async def run_scrape_single_url(request: ScrapeRequest, user: dict) -> ScrapeResponse:
    """Extrai dados de uma única URL de imóvel (com cache)."""
    try:
        logger.info(
            f"Scraping URL: {request.url} "
            f"(user: {user.get('email')}, cache: {request.use_cache})"
        )

        result = await property_scraper.scrape_url(
            request.url, use_cache=request.use_cache,
        )

        if result.get("error"):
            error_code = result.get("error_code", "unknown")
            error_msg = result.get("error", "Erro desconhecido")
            friendly_error = FRIENDLY_SCRAPE_ERRORS.get(error_code, error_msg)

            return ScrapeResponse(
                success=False,
                error=friendly_error,
                data={
                    **result,
                    "error_code": error_code,
                    "can_retry": error_code in ["blocked", "timeout", "ssl_error"],
                    "suggest_manual": True,
                    "partial_data": {
                        k: v
                        for k, v in result.items()
                        if v and k not in ["error", "error_code"]
                    },
                },
            )

        return ScrapeResponse(success=True, data=result)

    except Exception as e:
        logger.error(f"Erro no scraping: {e}")
        return ScrapeResponse(
            success=False,
            error=(
                "Ocorreu um erro ao extrair os dados. Por favor, "
                "insira os dados manualmente ou tente novamente."
            ),
            data={
                "error_code": "system_error",
                "can_retry": True,
                "suggest_manual": True,
                "url": request.url,
            },
        )


async def run_scrape_url(request: ScrapeRequest, user: dict) -> ScrapeResponse:
    """Alias simples para /single."""
    return await run_scrape_single_url(request, user)


async def run_crawl_website(request: CrawlRequest, user: dict):
    """Crawler recursivo para extrair múltiplos imóveis de um site."""
    max_pages = min(request.max_pages, 50)
    max_depth = min(request.max_depth, 3)

    try:
        logger.info(
            f"Iniciando crawl: {request.url} "
            f"(max_pages={max_pages}, max_depth={max_depth}, user={user.get('email')})"
        )
        return await crawl_properties(
            start_url=request.url,
            max_pages=max_pages,
            max_depth=max_depth,
        )
    except Exception as e:
        logger.error(f"Erro no crawling: {e}")
        raise HTTPException(status_code=500, detail=str(e))

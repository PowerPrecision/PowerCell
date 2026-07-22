"""Supported sites + AI/HTML extraction for scraper routes.

Extraído de `routes/scraper.py`.
Do **not** overwrite `services/scraper.py` / `gov_scraper.py` / `property_scraper.py`.
"""
from __future__ import annotations

import logging

import httpx
from fastapi import HTTPException

from services.scraper_api_models import (
    SUPPORTED_SITES,
    ExtractHtmlRequest,
    ScrapeRequest,
    detect_html_source,
)

logger = logging.getLogger(__name__)


async def run_get_supported_sites(user: dict):
    """Lista os sites imobiliários suportados pelo scraper."""
    return {
        "supported_sites": SUPPORTED_SITES,
        "generic_support": True,
        "ai_analysis": {
            "available": True,
            "model": "gemini-1.5-flash (configurable)",
            "description": (
                "Análise IA disponível para sites não suportados "
                "(Gemini por defeito)"
            ),
        },
        "notes": "Sites não listados são processados com extração genérica ou IA",
    }


async def run_analyze_page_with_ai(request: ScrapeRequest, user: dict):
    """Analisa uma página usando IA configurada (Gemini por defeito)."""
    try:
        from services.scraper import analyze_page_with_ai
        from services.ai_page_analyzer import get_ai_config

        logger.info(f"Análise IA solicitada para: {request.url}")

        config = await get_ai_config()
        model = config.get("scraper_extraction", "gemini-1.5-flash")

        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            response = await client.get(
                request.url,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36"
                    ),
                },
            )

            if response.status_code != 200:
                return {
                    "success": False,
                    "error": (
                        f"Não foi possível aceder à página "
                        f"(HTTP {response.status_code})"
                    ),
                }

            html_content = response.text

        result = await analyze_page_with_ai(request.url, html_content)

        return {
            "success": True,
            "url": request.url,
            "ai_model": model,
            "data": result,
        }

    except Exception as e:
        logger.error(f"Erro na análise IA: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def run_extract_from_html(request: ExtractHtmlRequest, user: dict):
    """Extrai dados de imóvel a partir de HTML colado."""
    try:
        from services.scraper import analyze_page_with_ai

        html_content = request.html

        if len(html_content) < 500:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Conteúdo muito curto. Certifique-se que copiou a "
                    "página inteira (Ctrl+A, Ctrl+C)."
                ),
            )

        source = detect_html_source(html_content)
        logger.info(
            f"Extracção HTML: source detectado = {source}, "
            f"tamanho = {len(html_content)}"
        )

        url = request.url or f"html-import-{source}"
        result = await analyze_page_with_ai(url, html_content)

        if result:
            result["_source"] = source
            result["_extracted_from"] = "html_paste"
            return result

        raise HTTPException(
            status_code=422,
            detail=(
                "Não foi possível extrair dados do conteúdo fornecido. "
                "Tente copiar a página novamente."
            ),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao extrair HTML: {e}")
        raise HTTPException(status_code=500, detail=f"Erro ao processar: {str(e)}")

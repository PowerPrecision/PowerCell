"""
Rotas para Web Scraping de Imóveis — thin FastAPI stubs.

Logic in services/scraper_api_*.py.
Do **not** overwrite services/scraper.py, gov_scraper.py, or property_scraper.py.
"""
from typing import Optional

from fastapi import APIRouter, Depends

from services.auth import get_current_user, require_roles, UserRole
from services.scraper_api_models import (
    CrawlRequest,
    ExtractHtmlRequest,
    ScrapeRequest,
    ScrapeResponse,
)
from services.scraper_api_scrape import (
    run_crawl_website,
    run_scrape_single_url,
    run_scrape_url,
)
from services.scraper_api_ai import (
    run_analyze_page_with_ai,
    run_extract_from_html,
    run_get_supported_sites,
)
from services.scraper_api_cache import (
    run_clear_scraper_cache,
    run_get_cache_stats,
    run_refresh_url_cache,
)

router = APIRouter(prefix="/scraper", tags=["Scraper"])


@router.post("/single", response_model=ScrapeResponse)
async def scrape_single_url(
    request: ScrapeRequest,
    user: dict = Depends(get_current_user),
):
    """Extrai dados de uma única URL de imóvel (cache 7 dias)."""
    return await run_scrape_single_url(request, user)


@router.post("/scrape")
async def scrape_url(
    request: ScrapeRequest,
    user: dict = Depends(get_current_user),
):
    """Alias simples para /single."""
    return await run_scrape_url(request, user)


@router.post("/crawl")
async def crawl_website(
    request: CrawlRequest,
    user: dict = Depends(require_roles([
        UserRole.ADMIN, UserRole.CEO, UserRole.DIRETOR, UserRole.CONSULTOR,
    ])),
):
    """Crawler recursivo para extrair múltiplos imóveis de um site."""
    return await run_crawl_website(request, user)


@router.get("/supported-sites")
async def get_supported_sites(user: dict = Depends(get_current_user)):
    """Lista os sites imobiliários suportados pelo scraper."""
    return await run_get_supported_sites(user)


@router.post("/analyze-with-ai")
async def analyze_page_with_ai_endpoint(
    request: ScrapeRequest,
    user: dict = Depends(require_roles([
        UserRole.ADMIN, UserRole.CEO, UserRole.DIRETOR,
    ])),
):
    """Analisa uma página usando IA configurada (Gemini por defeito)."""
    return await run_analyze_page_with_ai(request, user)


@router.post("/extract-html")
async def extract_from_html(
    request: ExtractHtmlRequest,
    user: dict = Depends(get_current_user),
):
    """Extrai dados de imóvel a partir de HTML colado."""
    return await run_extract_from_html(request, user)


@router.get("/cache/stats")
async def get_cache_stats(
    user: dict = Depends(require_roles([UserRole.ADMIN])),
):
    """Retorna estatísticas do cache de scraping."""
    return await run_get_cache_stats(user)


@router.delete("/cache/clear")
async def clear_scraper_cache(
    url: Optional[str] = None,
    user: dict = Depends(require_roles([UserRole.ADMIN])),
):
    """Limpa o cache de scraping."""
    return await run_clear_scraper_cache(url, user)


@router.post("/cache/refresh")
async def refresh_url_cache(
    request: ScrapeRequest,
    user: dict = Depends(require_roles([
        UserRole.ADMIN, UserRole.CEO, UserRole.DIRETOR,
    ])),
):
    """Força o refresh do cache para uma URL específica."""
    return await run_refresh_url_cache(request, user)

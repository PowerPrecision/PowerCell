"""Pydantic models for scraper API routes.

Extraído de `routes/scraper.py`.
Do **not** overwrite `services/scraper.py` / `gov_scraper.py` / `property_scraper.py`.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class ScrapeRequest(BaseModel):
    """Request para scraping de uma única URL."""

    url: str
    use_cache: bool = True


class CrawlRequest(BaseModel):
    """Request para crawling recursivo."""

    url: str
    max_pages: int = 10
    max_depth: int = 2


class ScrapeResponse(BaseModel):
    """Response do scraping."""

    success: bool
    data: Optional[dict] = None
    error: Optional[str] = None


class ExtractHtmlRequest(BaseModel):
    """Request para extrair dados de HTML colado."""

    html: str
    url: Optional[str] = None


FRIENDLY_SCRAPE_ERRORS = {
    "blocked": (
        "O site bloqueou o acesso. Tente novamente mais tarde ou "
        "insira os dados manualmente."
    ),
    "timeout": (
        "O site demorou muito a responder. Verifique se o link esta "
        "correcto ou insira os dados manualmente."
    ),
    "not_found": (
        "Pagina nao encontrada. O imovel pode ter sido removido. "
        "Insira os dados manualmente."
    ),
    "quota_exceeded": (
        "Limite de IA excedido. Os dados basicos foram extraidos. "
        "Pode complementar manualmente."
    ),
    "parse_error": (
        "Nao foi possivel extrair todos os dados. Verifique e complete manualmente."
    ),
    "ssl_error": (
        "Erro de seguranca ao aceder ao site. Tente novamente ou insira manualmente."
    ),
}

SUPPORTED_SITES = [
    {
        "name": "Idealista",
        "domain": "idealista.pt",
        "quality": "alta",
        "notes": "Pode necessitar de múltiplas tentativas",
    },
    {
        "name": "Imovirtual",
        "domain": "imovirtual.com",
        "quality": "alta",
        "notes": None,
    },
    {
        "name": "Casa Sapo",
        "domain": "casa.sapo.pt",
        "quality": "média",
        "notes": None,
    },
    {
        "name": "SuperCasa",
        "domain": "supercasa.pt",
        "quality": "média",
        "notes": None,
    },
    {
        "name": "ERA",
        "domain": "era.pt",
        "quality": "alta",
        "notes": None,
    },
    {
        "name": "Remax",
        "domain": "remax.pt",
        "quality": "média",
        "notes": None,
    },
    {
        "name": "Keller Williams",
        "domain": "kwportugal.pt",
        "quality": "média",
        "notes": None,
    },
]


def detect_html_source(html_content: str) -> str:
    """Detect portal source from pasted HTML content."""
    html_lower = html_content.lower()
    if "idealista.pt" in html_lower or "idealista" in html_lower:
        return "idealista"
    if "imovirtual" in html_lower:
        return "imovirtual"
    if "casasapo" in html_lower or "casa.sapo" in html_lower:
        return "casasapo"
    if "supercasa" in html_lower:
        return "supercasa"
    if "powerealestate" in html_lower or "power real estate" in html_lower:
        return "powerealestate"
    if "remax" in html_lower or "re/max" in html_lower:
        return "remax"
    if "era.pt" in html_lower or "eraimobiliaria" in html_lower:
        return "era"
    if "century21" in html_lower:
        return "century21"
    if "kw.com" in html_lower or "kellerwilliams" in html_lower:
        return "kellerwilliams"
    if "olx" in html_lower:
        return "olx"
    if "bpiexpressoimobiliario" in html_lower:
        return "bpi"
    return "desconhecido"

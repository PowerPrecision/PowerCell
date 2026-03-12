"""
Serviço para extração de dados de anúncios de imóveis
Ponto de entrada que usa EXCLUSIVAMENTE o DeepScraper (scraper.py)
para extracção avançada com navegação para sites de agências.

IMPORTANTE: NÃO usa httpx directo - todo o scraping passa pelo DeepScraper
que utiliza curl_cffi para bypass anti-bot (Cloudflare, Akamai).
"""
import logging
from typing import Optional, Dict, Any
from urllib.parse import urlparse

from models.lead import ScrapedData, ConsultantInfo
from services.scraper import property_scraper as deep_scraper

logger = logging.getLogger(__name__)


async def extract_property_data(url: str, use_deep_scraping: bool = True) -> ScrapedData:
    """
    Extrai dados de um anúncio de imóvel a partir do URL.
    Usa EXCLUSIVAMENTE o DeepScraper (curl_cffi) para evitar bloqueios anti-bot.
    
    Args:
        url: URL do anúncio
        use_deep_scraping: Ignorado - sempre usa deep scraping
    """
    if not url:
        return ScrapedData(url="", source="manual", raw_data={"error": "URL vazia"})
    
    try:
        return await extract_with_deep_scraper(url)
    except Exception as e:
        logger.error(f"Erro ao extrair dados de {url}: {e}")
        return ScrapedData(
            url=url, 
            source="error",
            raw_data={"error": str(e)}
        )


async def extract_with_deep_scraper(url: str) -> ScrapedData:
    """
    Usa o DeepScraper avançado (curl_cffi) para extração completa.
    Inclui navegação para sites de agências para encontrar contactos.
    
    O DeepScraper:
    - Usa curl_cffi com impersonate="chrome120" para bypass anti-bot
    - Faz deep scraping seguindo links para agências (Remax, EasyGest, etc.)
    - Usa Gemini como fallback para extracção de dados
    - Tem cache local para evitar chamadas repetidas
    """
    try:
        # Chamar o scraper robusto
        result = await deep_scraper.scrape_url(url, use_cache=True)
        
        # Verificar se houve erro
        if result.get("error"):
            logger.warning(f"DeepScraper retornou erro: {result.get('error')}")
            return ScrapedData(
                url=url,
                source="error",
                raw_data={"error": result.get("error")}
            )
        
        # Construir informação do consultor
        consultant = None
        if result.get("agente_nome") or result.get("agente_telefone") or result.get("agente_email"):
            consultant = ConsultantInfo(
                name=result.get("agente_nome"),
                phone=result.get("agente_telefone"),
                email=result.get("agente_email"),
                agency_name=result.get("agencia_nome"),
                source_url=result.get("_deep_source") or result.get("_url")
            )
        
        # Converter para o modelo ScrapedData
        return ScrapedData(
            url=url,
            title=result.get("titulo"),
            price=result.get("preco"),
            location=result.get("localizacao"),
            typology=result.get("tipologia"),
            area=result.get("area") or result.get("area_util"),
            photo_url=result.get("foto_principal"),
            consultant=consultant,
            source=result.get("_source") or _detect_source(url),
            raw_data={
                "descricao": result.get("descricao"),
                "caracteristicas": result.get("caracteristicas"),
                "referencia": result.get("referencia"),
                "quartos": result.get("quartos"),
                "casas_banho": result.get("casas_banho"),
                "certificado_energetico": result.get("certificado_energetico"),
                "ano_construcao": result.get("ano_construcao"),
                "deep_scraped": result.get("_deep_scraped", False),
                "deep_source": result.get("_deep_source"),
                "deep_agency": result.get("_deep_agency"),
                "extracted_by": result.get("_extracted_by"),
                "from_cache": result.get("_from_cache", False),
            }
        )
        
    except Exception as e:
        logger.error(f"Erro no Deep Scraper para {url}: {e}")
        return ScrapedData(
            url=url,
            source="error",
            raw_data={"error": str(e)}
        )


def _detect_source(url: str) -> str:
    """Detecta a fonte baseada na URL."""
    url_lower = url.lower()
    
    if "idealista" in url_lower:
        return "idealista"
    elif "imovirtual" in url_lower:
        return "imovirtual"
    elif "supercasa" in url_lower:
        return "supercasa"
    elif "casasapo" in url_lower or "casa.sapo" in url_lower:
        return "casasapo"
    elif "remax" in url_lower:
        return "remax"
    elif "era.pt" in url_lower:
        return "era"
    elif "century21" in url_lower:
        return "century21"
    elif "easygest" in url_lower:
        return "easygest"
    elif "quatru" in url_lower:
        return "quatru"
    elif "zome" in url_lower:
        return "zome"
    elif "kw" in url_lower:
        return "kw"
    else:
        return "manual"

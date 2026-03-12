"""
Rotas para Web Scraping de Imóveis
==================================
Endpoints para extrair dados de portais imobiliários.
Inclui sistema de cache para evitar chamadas repetidas.
"""
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, HttpUrl

from services.auth import get_current_user, require_roles, UserRole
from services.scraper import scrape_property_url, crawl_properties, property_scraper

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/scraper", tags=["Scraper"])


class ScrapeRequest(BaseModel):
    """Request para scraping de uma única URL."""
    url: str
    use_cache: bool = True  # Se deve usar cache


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


@router.post("/single", response_model=ScrapeResponse)
async def scrape_single_url(
    request: ScrapeRequest,
    user: dict = Depends(get_current_user)
):
    """
    Extrai dados de uma única URL de imóvel.
    
    Suporta: Idealista, Imovirtual, Casa Sapo, SuperCasa, ERA, Remax, KW, etc.
    
    O sistema usa cache por 7 dias - URLs já processadas retornam
    resultado em cache para economizar recursos.
    """
    try:
        logger.info(f"Scraping URL: {request.url} (user: {user.get('email')}, cache: {request.use_cache})")
        
        result = await property_scraper.scrape_url(request.url, use_cache=request.use_cache)
        
        if result.get("error"):
            # Mensagens de erro amigáveis
            error_code = result.get("error_code", "unknown")
            error_msg = result.get("error", "Erro desconhecido")
            
            friendly_messages = {
                "blocked": "O site bloqueou o acesso. Tente novamente mais tarde ou insira os dados manualmente.",
                "timeout": "O site demorou muito a responder. Verifique se o link esta correcto ou insira os dados manualmente.",
                "not_found": "Pagina nao encontrada. O imovel pode ter sido removido. Insira os dados manualmente.",
                "quota_exceeded": "Limite de IA excedido. Os dados basicos foram extraidos. Pode complementar manualmente.",
                "parse_error": "Nao foi possivel extrair todos os dados. Verifique e complete manualmente.",
                "ssl_error": "Erro de seguranca ao aceder ao site. Tente novamente ou insira manualmente.",
            }
            
            friendly_error = friendly_messages.get(error_code, error_msg)
            
            return ScrapeResponse(
                success=False,
                error=friendly_error,
                data={
                    **result,
                    "error_code": error_code,
                    "can_retry": error_code in ["blocked", "timeout", "ssl_error"],
                    "suggest_manual": True,
                    "partial_data": {k: v for k, v in result.items() if v and k not in ["error", "error_code"]}
                }
            )
        
        return ScrapeResponse(
            success=True,
            data=result
        )
        
    except Exception as e:
        logger.error(f"Erro no scraping: {e}")
        # Erro generico - sempre sugerir insercao manual
        return ScrapeResponse(
            success=False,
            error="Ocorreu um erro ao extrair os dados. Por favor, insira os dados manualmente ou tente novamente.",
            data={
                "error_code": "system_error",
                "can_retry": True,
                "suggest_manual": True,
                "url": request.url
            }
        )


@router.post("/scrape")
async def scrape_url(
    request: ScrapeRequest,
    user: dict = Depends(get_current_user)
):
    """
    Alias simples para /single - extrai dados de uma URL.
    Usado pelo modal de importação HTML para deep scraping.
    """
    return await scrape_single_url(request, user)


@router.post("/crawl")
async def crawl_website(
    request: CrawlRequest,
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO, UserRole.DIRETOR, UserRole.CONSULTOR]))
):
    """
    Crawler recursivo para extrair múltiplos imóveis de um site.
    
    Navega pelo site a partir da URL inicial, seguindo links de imóveis
    até atingir o limite de páginas ou profundidade.
    
    Args:
        url: URL inicial (ex: página de listagem de imóveis)
        max_pages: Número máximo de páginas a visitar (default: 10, max: 50)
        max_depth: Profundidade máxima de navegação (default: 2, max: 3)
        
    Returns:
        Lista de imóveis encontrados com seus dados extraídos
    """
    # Limitar parâmetros para evitar abusos
    max_pages = min(request.max_pages, 50)
    max_depth = min(request.max_depth, 3)
    
    try:
        logger.info(
            f"Iniciando crawl: {request.url} "
            f"(max_pages={max_pages}, max_depth={max_depth}, user={user.get('email')})"
        )
        
        result = await crawl_properties(
            start_url=request.url,
            max_pages=max_pages,
            max_depth=max_depth
        )
        
        return result
        
    except Exception as e:
        logger.error(f"Erro no crawling: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/supported-sites")
async def get_supported_sites(user: dict = Depends(get_current_user)):
    """
    Lista os sites imobiliários suportados pelo scraper.
    """
    return {
        "supported_sites": [
            {
                "name": "Idealista",
                "domain": "idealista.pt",
                "quality": "alta",
                "notes": "Pode necessitar de múltiplas tentativas"
            },
            {
                "name": "Imovirtual",
                "domain": "imovirtual.com",
                "quality": "alta",
                "notes": None
            },
            {
                "name": "Casa Sapo",
                "domain": "casa.sapo.pt",
                "quality": "média",
                "notes": None
            },
            {
                "name": "SuperCasa",
                "domain": "supercasa.pt",
                "quality": "média",
                "notes": None
            },
            {
                "name": "ERA",
                "domain": "era.pt",
                "quality": "alta",
                "notes": None
            },
            {
                "name": "Remax",
                "domain": "remax.pt",
                "quality": "média",
                "notes": None
            },
            {
                "name": "Keller Williams",
                "domain": "kwportugal.pt",
                "quality": "média",
                "notes": None
            }
        ],
        "generic_support": True,
        "ai_analysis": {
            "available": True,
            "model": "gemini-1.5-flash (configurable)",
            "description": "Análise IA disponível para sites não suportados (Gemini por defeito)"
        },
        "notes": "Sites não listados são processados com extração genérica ou IA"
    }


@router.post("/analyze-with-ai")
async def analyze_page_with_ai_endpoint(
    request: ScrapeRequest,
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO, UserRole.DIRETOR]))
):
    """
    Analisa uma página usando IA configurada (Gemini por defeito).
    
    Útil para sites que bloqueiam scraping ou têm estrutura complexa.
    A IA extrai automaticamente informações de imóveis do HTML.
    
    Custo: Usa créditos da API configurada (Gemini é muito económico)
    """
    try:
        from services.scraper import analyze_page_with_ai
        from services.ai_page_analyzer import get_ai_config
        import httpx
        
        logger.info(f"Análise IA solicitada para: {request.url}")
        
        # Obter modelo configurado
        config = await get_ai_config()
        model = config.get("scraper_extraction", "gemini-1.5-flash")
        
        # Primeiro, obter o HTML da página
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            response = await client.get(request.url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            })
            
            if response.status_code != 200:
                return {
                    "success": False,
                    "error": f"Não foi possível aceder à página (HTTP {response.status_code})"
                }
            
            html_content = response.text
        
        # Analisar com IA
        result = await analyze_page_with_ai(request.url, html_content)
        
        return {
            "success": True,
            "url": request.url,
            "ai_model": model,
            "data": result
        }
        
    except Exception as e:
        logger.error(f"Erro na análise IA: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# EXTRAÇÃO DE HTML (COLAR DO IDEALISTA)
# ============================================================

class ExtractHtmlRequest(BaseModel):
    """Request para extrair dados de HTML colado."""
    html: str
    url: Optional[str] = None


@router.post("/extract-html")
async def extract_from_html(
    request: ExtractHtmlRequest,
    user: dict = Depends(get_current_user)
):
    """
    Extrai dados de imóvel a partir de HTML colado.
    
    Útil quando o scraping directo é bloqueado (ex: Idealista).
    O utilizador copia a página e cola aqui, a IA extrai os dados.
    
    Passos:
    1. Utilizador abre página do Idealista no browser
    2. Faz Ctrl+A, Ctrl+C
    3. Cola no frontend
    4. Este endpoint processa com IA
    """
    try:
        from services.scraper import analyze_page_with_ai
        
        html_content = request.html
        
        # Validar que tem conteúdo mínimo
        if len(html_content) < 500:
            raise HTTPException(
                status_code=400, 
                detail="Conteúdo muito curto. Certifique-se que copiou a página inteira (Ctrl+A, Ctrl+C)."
            )
        
        # Detectar source pelo conteúdo
        source = "desconhecido"
        html_lower = html_content.lower()
        if "idealista.pt" in html_lower or "idealista" in html_lower:
            source = "idealista"
        elif "imovirtual" in html_lower:
            source = "imovirtual"
        elif "casasapo" in html_lower or "casa.sapo" in html_lower:
            source = "casasapo"
        elif "supercasa" in html_lower:
            source = "supercasa"
        elif "powerealestate" in html_lower or "power real estate" in html_lower:
            source = "powerealestate"
        elif "remax" in html_lower or "re/max" in html_lower:
            source = "remax"
        elif "era.pt" in html_lower or "eraimobiliaria" in html_lower:
            source = "era"
        elif "century21" in html_lower:
            source = "century21"
        elif "kw.com" in html_lower or "kellerwilliams" in html_lower:
            source = "kellerwilliams"
        elif "olx" in html_lower:
            source = "olx"
        elif "bpiexpressoimobiliario" in html_lower:
            source = "bpi"
        
        logger.info(f"Extracção HTML: source detectado = {source}, tamanho = {len(html_content)}")
        
        # Analisar com IA
        url = request.url or f"html-import-{source}"
        result = await analyze_page_with_ai(url, html_content)
        
        if result:
            result["_source"] = source
            result["_extracted_from"] = "html_paste"
            return result
        else:
            raise HTTPException(
                status_code=422,
                detail="Não foi possível extrair dados do conteúdo fornecido. Tente copiar a página novamente."
            )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao extrair HTML: {e}")
        raise HTTPException(status_code=500, detail=f"Erro ao processar: {str(e)}")


# ============================================================
# CACHE MANAGEMENT ENDPOINTS
# ============================================================

@router.get("/cache/stats")
async def get_cache_stats(
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
):
    """
    Retorna estatísticas do cache de scraping.
    
    Inclui verificação de limite e notificações.
    
    Returns:
        - total_entries: Total de URLs em cache
        - valid_entries: URLs ainda válidas (não expiradas)
        - expired_entries: URLs expiradas
        - cache_expiry_days: Dias de validade do cache
        - limit_status: Informação sobre limite do cache
    """
    from database import db
    
    stats = await property_scraper.get_cache_stats()
    
    # Obter configurações de limite
    cache_config = await db.system_config.find_one({"type": "cache_settings"}, {"_id": 0})
    cache_limit = cache_config.get("cache_limit", 1000) if cache_config else 1000
    notify_percentage = cache_config.get("notify_at_percentage", 80) if cache_config else 80
    
    total = stats.get("total_entries", 0)
    percentage_used = (total / cache_limit * 100) if cache_limit > 0 else 0
    
    # Verificar se deve notificar
    should_notify = percentage_used >= notify_percentage
    notification = None
    
    if should_notify:
        notification = {
            "type": "warning",
            "message": f"Cache de scraping está a {percentage_used:.0f}% da capacidade ({total}/{cache_limit})",
            "action": "Considere limpar o cache ou aumentar o limite"
        }
        
        # Guardar notificação na DB
        await db.notifications.update_one(
            {"type": "cache_limit_warning", "dismissed": False},
            {
                "$set": {
                    "type": "cache_limit_warning",
                    "message": notification["message"],
                    "percentage": percentage_used,
                    "created_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
                    "dismissed": False
                }
            },
            upsert=True
        )
    
    return {
        **stats,
        "cache_limit": cache_limit,
        "percentage_used": round(percentage_used, 1),
        "should_notify": should_notify,
        "notification": notification
    }


@router.delete("/cache/clear")
async def clear_scraper_cache(
    url: Optional[str] = None,
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """
    Limpa o cache de scraping.
    
    Args:
        url: URL específica a limpar. Se não fornecida, limpa todo o cache.
        
    Returns:
        Número de registos eliminados
    """
    deleted = await property_scraper.clear_cache(url)
    
    return {
        "success": True,
        "deleted_count": deleted,
        "message": f"Cache {'da URL' if url else 'completo'} limpo"
    }


@router.post("/cache/refresh")
async def refresh_url_cache(
    request: ScrapeRequest,
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO, UserRole.DIRETOR]))
):
    """
    Força o refresh do cache para uma URL específica.
    
    Remove o cache existente e faz novo scraping.
    """
    try:
        # Limpar cache da URL
        await property_scraper.clear_cache(request.url)
        
        # Fazer novo scraping
        result = await property_scraper.scrape_url(request.url, use_cache=True)
        
        return {
            "success": True,
            "message": "Cache actualizado",
            "data": result
        }
        
    except Exception as e:
        logger.error(f"Erro ao refrescar cache: {e}")
        raise HTTPException(status_code=500, detail=str(e))

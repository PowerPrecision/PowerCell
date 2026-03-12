"""
====================================================================
SCRAPER SERVICE - EXTRAÇÃO HÍBRIDA (curl_cffi + Gemini + Deep Scraping)
====================================================================
Este serviço extrai dados de portais imobiliários usando:
1. curl_cffi com impersonate para bypass anti-bot (Cloudflare, Akamai)
2. Parsers específicos (BeautifulSoup) para sites conhecidos
3. Gemini 2.0 Flash como fallback para sites desconhecidos
4. "Deep Scraping" - Segue links para sites de agências para dados completos
5. Cache local - Guarda resultados para evitar chamadas repetidas

Deep Scraping Logic:
- Se a página for de um agregador (Idealista, Supercasa, Imovirtual)
- Detecta links para sites de agências (Remax, Century21, Quatru, etc.)
- Navega automaticamente para a página da agência
- Extrai dados completos do consultor (telefone direto, email)
- Faz merge inteligente dos dados

Suporta: Idealista, Supercasa, Imovirtual, Remax, Century21, ERA, 
         Quatru, Mais Consultores, Zome, KW, IAD, SAFTI, EXP, etc.
====================================================================
"""
import logging
import re
import json
import random
import hashlib
from bs4 import BeautifulSoup
from typing import Optional, Dict, Any, List
from fake_useragent import UserAgent
from urllib.parse import urlparse, urljoin, quote_plus
import asyncio
import os
from datetime import datetime, timezone, timedelta

# curl_cffi para bypass anti-bot
try:
    from curl_cffi.requests import AsyncSession
    CURL_CFFI_AVAILABLE = True
except ImportError:
    CURL_CFFI_AVAILABLE = False
    import httpx

from config import GEMINI_API_KEY

logger = logging.getLogger(__name__)

# ================================================================
# CONFIGURAÇÃO ANTI-BOT
# ================================================================

# API Key do ScraperAPI (fallback)
SCRAPERAPI_KEY = os.environ.get("SCRAPERAPI_API_KEY")

# Profiles para rotação - evita fingerprint consistente
# CRÍTICO: Rodar entre diferentes browsers evita detecção
IMPERSONATE_PROFILES = [
    "chrome120",
    "chrome119", 
    "chrome116",
    "safari17_0",
    "safari15_5",
]

# Tentativas e delays
MAX_RETRIES = 3
RETRY_DELAY = 2.0
BLOCKED_DELAY_MIN = 5   # Delay mínimo após 403 (segundos)
BLOCKED_DELAY_MAX = 10  # Delay máximo após 403 (segundos)

# Sites agregadores (devemos procurar deep links)
AGGREGATOR_SITES = [
    "idealista.pt", "idealista.com", 
    "supercasa.pt", 
    "imovirtual.com",
    "casasapo.pt", "casa.sapo.pt",
    "bfrancisco.pt"
]

# Sites que requerem medidas especiais de anti-bot
PROTECTED_SITES = ["idealista.pt", "idealista.com"]

# Domínios de agências imobiliárias (expandido)
AGENCY_DOMAINS = [
    # Grandes redes internacionais
    "remax", "century21", "era.pt", "coldwellbanker", 
    "engel", "sothebys", "christies", "savills", "cbre", "jll",
    # Redes portuguesas
    "quatru", "maisconsultores", "zome", "kwportugal", "kw.com",
    "iadportugal", "iad-", "safti", "exp-portugal", "expportugal",
    "predimed", "ds-imobiliaria", "comprarcasa", "casasdobarlavento",
    "lusobroker", "coldwellbanker", "primusalgarve", "keller",
    # Agências com sistemas próprios
    "easygest.com.pt", "easygest", "gerimax", "casafari",
    # Outras
    "chaves-chaves", "casayes", "real-estate", "imobiliaria"
]

# Textos que indicam links para agências
AGENCY_LINK_TEXTS = [
    "ver no site", "link externo", "página da agência", "website",
    "site do anunciante", "ver anúncio", "contactar agência",
    "visitar site", "ir para o site", "ver original",
    "ver detalhes", "mais informação", "contacto direto"
]

# Padrões regex para contactos - formato português
PHONE_PATTERNS = [
    # Links tel: - maior prioridade
    r'tel:\+?351?(9[1236]\d{7})',
    r'tel:\+?351?(2[1-9]\d{7})',
    # Telemóveis portugueses com +351
    r'\+351[\s.-]?(9[1236])[\s.-]?(\d{3})[\s.-]?(\d{4})',
    r'\+351\s*9[1236]\d{7}',
    # Telemóveis sem código país
    r'\b(9[1236])[\s.-]?(\d{3})[\s.-]?(\d{4})\b',
    r'\b9[1236]\d{7}\b',
    # Fixos portugueses
    r'\+351[\s.-]?(2[1-9])[\s.-]?(\d{3})[\s.-]?(\d{4})',
    r'\b(2[1-9])[\s.-]?(\d{3})[\s.-]?(\d{4})\b',
    r'\b2[1-9]\d{7}\b',
    # Formato genérico XXX XXX XXX
    r'\b(\d{3})[\s.-](\d{3})[\s.-](\d{3})\b',
]

# Selectores específicos por agência
AGENCY_PHONE_SELECTORS = {
    "remax": ['.agent-phone', 'a[href^="tel:"]', '.contact-phone', '.consultant-phone'],
    "era": ['.phone', '.contact-info a[href*="tel"]', '.agent-details .phone'],
    "century21": ['.agent-contact a', '.phone-number', '.consultant-info .phone'],
    "zome": ['.contact-phone', '.agent-phone', 'a[href^="tel:"]'],
    "iad": ['.conseiller-tel', '.phone', 'a[href*="tel"]'],
    "kw": ['.agent-phone', '.contact-phone', 'a.phone-link'],
    "quatru": ['.agent-phone', '.contact-phone', 'a[href^="tel:"]', '.phone'],
    "maisconsultores": ['.consultant-phone', '.phone', 'a[href*="tel"]'],
    "safti": ['.agent-phone', '.phone', 'a[href^="tel:"]'],
    "easygest": ['.phone', '.tel', 'a[href^="tel:"]', '.contact-phone', '.agent-phone'],
}

EMAIL_PATTERN = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'

# Cache settings
CACHE_EXPIRY_DAYS = 7

# Configurações de retry
MAX_RETRIES = 3
RETRY_DELAY = 1.5


class PropertyScraper:
    """
    Scraper de propriedades com bypass anti-bot e deep scraping.
    
    Usa curl_cffi para imitar browser real (Chrome 120) e contornar
    protecções Cloudflare/Akamai. Implementa deep scraping para seguir
    links de agregadores até sites de agências.
    """
    
    def __init__(self):
        self.ua = UserAgent()
        self.timeout = 45.0
        self._db = None
        self._session = None
        self._current_profile = None
    
    def _get_random_profile(self) -> str:
        """Escolhe um profile aleatório para rotação."""
        return random.choice(IMPERSONATE_PROFILES)
    
    async def _get_session(self, force_new: bool = False):
        """
        Obtém sessão curl_cffi com impersonate rotativo.
        
        CRÍTICO: Não reusar a mesma sessão/profile após 403.
        A rotação de profiles evita detecção de fingerprint.
        """
        if CURL_CFFI_AVAILABLE:
            # Criar nova sessão se forçado ou se não existe
            if force_new or self._session is None:
                if self._session:
                    try:
                        await self._session.close()
                    except Exception:
                        pass
                
                self._current_profile = self._get_random_profile()
                self._session = AsyncSession(impersonate=self._current_profile)
                logger.debug(f"[SCRAPER] Nova sessão criada com profile: {self._current_profile}")
            
            return self._session
        return None
    
    async def _close_session(self):
        """Fecha sessão curl_cffi."""
        if self._session:
            await self._session.close()
            self._session = None
    
    def _get_headers(self) -> Dict[str, str]:
        """Retorna headers que imitam browser real."""
        return {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "pt-PT,pt;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Cache-Control": "max-age=0",
        }
    
    async def _get_db(self):
        """Lazy load database connection."""
        if self._db is None:
            from database import db
            self._db = db
        return self._db
    
    # ================================================================
    # FETCH COM CURL_CFFI (ANTI-BOT BYPASS)
    # ================================================================
    
    async def _fetch_url(self, url: str, retries: int = MAX_RETRIES) -> Optional[str]:
        """
        Obtém HTML de uma URL usando curl_cffi com impersonate.
        
        CRÍTICO para bypass anti-bot:
        - NÃO passar headers manuais - curl_cffi gera os corretos para o profile
        - Usar rotação de profiles após 403
        - Delay aleatório após bloqueio
        
        Args:
            url: URL a aceder
            retries: Número de tentativas
            
        Returns:
            HTML content ou None se falhar
        """
        last_error = None
        got_403 = False
        
        for attempt in range(retries):
            try:
                if CURL_CFFI_AVAILABLE:
                    # Após 403, forçar nova sessão com profile diferente
                    session = await self._get_session(force_new=got_403)
                    
                    # CRÍTICO: NÃO passar headers - curl_cffi gera automaticamente
                    # Passar headers manuais cria fingerprint inconsistente que é detectado
                    response = await session.get(
                        url,
                        timeout=self.timeout,
                        allow_redirects=True
                    )
                    
                    if response.status_code == 200:
                        logger.info(f"[SCRAPER] curl_cffi sucesso (profile={self._current_profile}) para {url[:60]}...")
                        got_403 = False
                        return response.text
                    elif response.status_code == 403:
                        logger.warning(f"[SCRAPER] 403 Forbidden (profile={self._current_profile}) - tentativa {attempt + 1}/{retries}")
                        last_error = "403 Forbidden"
                        got_403 = True
                        
                        # Delay aleatório após bloqueio para não "martelar"
                        delay = random.uniform(BLOCKED_DELAY_MIN, BLOCKED_DELAY_MAX)
                        logger.info(f"[SCRAPER] Aguardando {delay:.1f}s após 403...")
                        await asyncio.sleep(delay)
                        continue
                        
                    elif response.status_code == 404:
                        return None
                    else:
                        last_error = f"HTTP {response.status_code}"
                        logger.warning(f"[SCRAPER] {last_error} em {url}")
                else:
                    # Fallback para httpx se curl_cffi não disponível
                    import httpx
                    async with httpx.AsyncClient(
                        timeout=self.timeout,
                        follow_redirects=True,
                        http2=True
                    ) as client:
                        response = await client.get(url, headers=self._get_headers())
                        
                        if response.status_code == 200:
                            return response.text
                        elif response.status_code == 403:
                            last_error = "403 Forbidden"
                            got_403 = True
                        else:
                            last_error = f"HTTP {response.status_code}"
                
            except Exception as e:
                last_error = str(e)
                logger.warning(f"[SCRAPER] Erro na tentativa {attempt + 1}: {e}")
            
            # Esperar antes de retry (crescente)
            if attempt < retries - 1 and not got_403:  # 403 já tem delay próprio
                await asyncio.sleep(RETRY_DELAY * (attempt + 1))
        
        logger.error(f"[SCRAPER] Falha após {retries} tentativas: {last_error}")
        return None
    
    async def _fetch_with_scraperapi(self, url: str) -> Optional[str]:
        """
        Fallback: Usa ScraperAPI para sites muito protegidos.
        
        IMPORTANTE: Ordem de tentativas optimizada para Idealista:
        1. Premium SEM render (mais rápido, menos timeouts)
        2. Básico (simples, funciona em alguns casos)
        3. Premium COM render (último recurso, mais lento)
        
        Adiciona delay de 2s antes de cada chamada para evitar rate limits.
        """
        if not SCRAPERAPI_KEY:
            return None
        
        try:
            import httpx
            
            encoded_url = quote_plus(url)
            
            # ORDEM CORRIGIDA: Premium sem render primeiro (mais estável)
            configs = [
                # 1. Premium sem render - mais rápido e estável
                (f"http://api.scraperapi.com?api_key={SCRAPERAPI_KEY}&url={encoded_url}&premium=true", "premium"),
                # 2. Básico - simples
                (f"http://api.scraperapi.com?api_key={SCRAPERAPI_KEY}&url={encoded_url}", "basic"),
                # 3. Premium com render - último recurso (pode dar timeout/500)
                (f"http://api.scraperapi.com?api_key={SCRAPERAPI_KEY}&url={encoded_url}&premium=true&render=true", "premium+render"),
            ]
            
            for scraper_url, config_name in configs:
                logger.info(f"[SCRAPER] Tentando ScraperAPI ({config_name}) para: {url[:50]}...")
                
                # Delay antes de chamar API para evitar burst limits
                await asyncio.sleep(2.0)
                
                try:
                    async with httpx.AsyncClient(timeout=90.0) as client:
                        response = await client.get(scraper_url)
                        
                        if response.status_code == 200:
                            # Verificar se a resposta não é uma página de erro
                            content = response.text
                            content_lower = content.lower()
                            
                            # Verificar se é HTML válido e não página de erro/captcha
                            if len(content) > 1000 and "<!doctype html" in content_lower:
                                # Verificar se não é página de captcha/bloqueio
                                if "captcha" in content_lower or "blocked" in content_lower or "access denied" in content_lower:
                                    logger.warning(f"[SCRAPER] ScraperAPI ({config_name}) retornou página de bloqueio/captcha")
                                    continue
                                    
                                logger.info(f"[SCRAPER] ScraperAPI sucesso ({config_name}) - {len(content)} chars")
                                return content
                            elif len(content) < 500:
                                logger.warning(f"[SCRAPER] Resposta muito curta ({len(content)} chars)")
                                continue
                            else:
                                # Pode ser JSON de erro ou conteúdo inválido
                                logger.warning(f"[SCRAPER] Resposta sem HTML válido ({config_name})")
                                continue
                                
                        elif response.status_code == 404:
                            logger.warning(f"[SCRAPER] ScraperAPI ({config_name}) retornou 404 - página não existe?")
                            # 404 pode ser real - não tentar mais configs
                            return None
                            
                        elif response.status_code == 500:
                            logger.warning(f"[SCRAPER] ScraperAPI ({config_name}) erro interno 500 - tentando próxima config")
                            await asyncio.sleep(3.0)  # Delay extra após erro
                            continue
                            
                        elif response.status_code == 429:
                            logger.warning("[SCRAPER] ScraperAPI rate limit - aguardando 10s")
                            await asyncio.sleep(10.0)
                            continue
                            
                        else:
                            logger.warning(f"[SCRAPER] ScraperAPI ({config_name}) retornou {response.status_code}")
                            continue
                            
                except asyncio.TimeoutError:
                    logger.warning(f"[SCRAPER] ScraperAPI ({config_name}) timeout")
                    continue
                except Exception as e:
                    logger.warning(f"[SCRAPER] Erro na config {config_name}: {e}")
                    continue
            
            logger.warning("[SCRAPER] Todas as configurações ScraperAPI falharam")
            return None
            
        except Exception as e:
            logger.error(f"[SCRAPER] Erro ScraperAPI: {e}")
            return None
    
    # ================================================================
    # CACHE SYSTEM
    # ================================================================
    
    def _get_url_hash(self, url: str) -> str:
        """Gera hash único para uma URL usando SHA-256 (seguro)."""
        return hashlib.sha256(url.lower().strip().encode()).hexdigest()
    
    async def _get_cached_result(self, url: str) -> Optional[Dict[str, Any]]:
        """
        Verifica se existe resultado em cache para esta URL.
        
        Returns:
            Resultado em cache ou None
        """
        try:
            db = await self._get_db()
            url_hash = self._get_url_hash(url)
            
            # Buscar cache não expirado
            expiry_date = datetime.now(timezone.utc) - timedelta(days=CACHE_EXPIRY_DAYS)
            
            cached = await db.scraper_cache.find_one(
                {
                    "url_hash": url_hash,
                    "created_at": {"$gte": expiry_date.isoformat()}
                },
                {"_id": 0}
            )
            
            if cached:
                logger.info(f"✓ Cache hit para {url[:50]}...")
                cached["_from_cache"] = True
                return cached.get("result")
            
            return None
            
        except Exception as e:
            logger.debug(f"Erro ao verificar cache: {e}")
            return None
    
    async def _save_to_cache(self, url: str, result: Dict[str, Any]) -> None:
        """
        Guarda resultado no cache.
        
        Args:
            url: URL processada
            result: Resultado da extracção
        """
        try:
            db = await self._get_db()
            url_hash = self._get_url_hash(url)
            
            cache_doc = {
                "url_hash": url_hash,
                "url": url,
                "result": result,
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            
            # Upsert (actualizar se existir)
            await db.scraper_cache.update_one(
                {"url_hash": url_hash},
                {"$set": cache_doc},
                upsert=True
            )
            
            logger.debug(f"Resultado guardado em cache para {url[:50]}...")
            
        except Exception as e:
            logger.debug(f"Erro ao guardar cache: {e}")
    
    async def clear_cache(self, url: Optional[str] = None) -> int:
        """
        Limpa cache de scraping.
        
        Args:
            url: URL específica para limpar, ou None para limpar tudo
            
        Returns:
            Número de registos eliminados
        """
        try:
            db = await self._get_db()
            
            if url:
                url_hash = self._get_url_hash(url)
                result = await db.scraper_cache.delete_one({"url_hash": url_hash})
            else:
                result = await db.scraper_cache.delete_many({})
            
            return result.deleted_count
            
        except Exception as e:
            logger.error(f"Erro ao limpar cache: {e}")
            return 0
    
    async def get_cache_stats(self) -> Dict[str, Any]:
        """Retorna estatísticas do cache."""
        try:
            db = await self._get_db()
            
            total = await db.scraper_cache.count_documents({})
            
            expiry_date = datetime.now(timezone.utc) - timedelta(days=CACHE_EXPIRY_DAYS)
            valid = await db.scraper_cache.count_documents({
                "created_at": {"$gte": expiry_date.isoformat()}
            })
            
            return {
                "total_entries": total,
                "valid_entries": valid,
                "expired_entries": total - valid,
                "cache_expiry_days": CACHE_EXPIRY_DAYS
            }
            
        except Exception as e:
            return {"error": str(e)}
    
    def _clean_text(self, text: str) -> str:
        """Limpa texto HTML removendo scripts, estilos e whitespace extra."""
        if not text:
            return ""
        # Remover tags script e style
        text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
        # Remover tags HTML
        text = re.sub(r'<[^>]+>', ' ', text)
        # Normalizar whitespace
        text = re.sub(r'\s+', ' ', text)
        return text.strip()
    
    # ================================================================
    # DEEP SCRAPING - EXTRAÇÃO DE DADOS DE SITES DE AGÊNCIAS
    # ================================================================
    
    def _is_aggregator_site(self, url: str) -> bool:
        """Verifica se a URL é de um site agregador."""
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        return any(agg in domain for agg in AGGREGATOR_SITES)
    
    def _find_agency_links(self, soup: BeautifulSoup, current_domain: str) -> List[Dict[str, str]]:
        """
        Encontra links para sites de agências imobiliárias na página.
        
        Procura:
        1. Links externos para domínios de agências conhecidas
        2. Botões/links com textos como "Ver no site", "Link externo", etc.
        3. Links que saem do domínio atual para agências
        
        Returns:
            Lista de dicts com {url, text, agency} para cada link encontrado
        """
        agency_links = []
        seen_urls = set()
        
        for a_tag in soup.find_all('a', href=True):
            href = a_tag.get('href', '')
            if not href or href.startswith('#') or href.startswith('javascript:'):
                continue
            
            # Ignorar links relativos
            if not href.startswith('http'):
                continue
            
            parsed = urlparse(href)
            link_domain = parsed.netloc.lower()
            
            # Ignorar links para o mesmo domínio
            if current_domain in link_domain or link_domain in current_domain:
                continue
            
            # Verificar se é um domínio de agência
            matched_agency = None
            for agency_pattern in AGENCY_DOMAINS:
                if agency_pattern in link_domain:
                    matched_agency = agency_pattern
                    break
            
            # Também verificar pelo texto do link
            link_text = a_tag.get_text(strip=True).lower()
            is_agency_link_text = any(text in link_text for text in AGENCY_LINK_TEXTS)
            
            # Adicionar se for domínio de agência OU tiver texto indicativo
            if (matched_agency or is_agency_link_text) and href not in seen_urls:
                agency_links.append({
                    "url": href,
                    "text": link_text[:100],
                    "agency": matched_agency or "unknown",
                    "domain": link_domain
                })
                seen_urls.add(href)
        
        # Ordenar por prioridade (agências conhecidas primeiro)
        agency_links.sort(key=lambda x: 0 if x["agency"] != "unknown" else 1)
        
        return agency_links[:5]  # Max 5 links
    
    async def _deep_scrape_agency(self, agency_url: str, agency_name: str) -> Dict[str, Any]:
        """
        Faz scraping da página de uma agência para extrair dados do consultor.
        
        Args:
            agency_url: URL da página da agência
            agency_name: Nome da agência (remax, quatru, etc.)
            
        Returns:
            Dict com dados extraídos (telefone, email, nome do consultor, referência)
        """
        logger.info(f"[DEEP SCRAPE] Navegando para {agency_url[:60]}...")
        
        result = {
            "deep_scraped": True,
            "source_url": agency_url,
            "source_agency": agency_name
        }
        
        try:
            html = await self._fetch_url(agency_url)
            if not html:
                logger.warning(f"[DEEP SCRAPE] Não foi possível aceder {agency_url}")
                return result
            
            soup = BeautifulSoup(html, 'html.parser')
            
            # 1. Tentar selectores específicos da agência
            if agency_name in AGENCY_PHONE_SELECTORS:
                for selector in AGENCY_PHONE_SELECTORS[agency_name]:
                    elements = soup.select(selector)
                    for el in elements:
                        text = el.get_text(strip=True)
                        # Limpar e validar telefone
                        phone = self._extract_phone_from_text(text)
                        if phone:
                            result["agente_telefone"] = phone
                            break
                    if result.get("agente_telefone"):
                        break
            
            # 2. Extrair contactos do texto completo
            clean_text = self._clean_text(html)
            contacts = self._extract_contacts_from_text(clean_text)
            
            if contacts.get("telefones") and not result.get("agente_telefone"):
                # Priorizar telemóveis sobre fixos
                phones = contacts["telefones"]
                mobile = next((p for p in phones if p.startswith("9")), None)
                result["agente_telefone"] = mobile or phones[0]
            
            if contacts.get("emails"):
                # Filtrar emails genéricos
                valid_emails = [e for e in contacts["emails"] 
                              if not any(x in e.lower() for x in ["noreply", "info@", "geral@", "admin@"])]
                if valid_emails:
                    result["agente_email"] = valid_emails[0]
            
            # 3. Extrair nome do consultor
            agent_name_selectors = [
                '.agent-name', '.consultant-name', '.broker-name',
                '.contact-name', 'h1.name', 'h2.name', '.profile-name',
                '[class*="agent"] [class*="name"]', '[class*="consultant"] [class*="name"]'
            ]
            for selector in agent_name_selectors:
                el = soup.select_one(selector)
                if el:
                    name = el.get_text(strip=True)
                    if name and len(name) > 3 and len(name) < 100:
                        result["agente_nome"] = name
                        break
            
            # 4. Extrair referência da agência
            ref_patterns = [
                r'Ref[.:]?\s*([A-Z0-9-]{5,20})',
                r'Referência[:]?\s*([A-Z0-9-]{5,20})',
                r'ID[:]?\s*([A-Z0-9-]{5,20})',
            ]
            for pattern in ref_patterns:
                match = re.search(pattern, html, re.IGNORECASE)
                if match:
                    result["referencia_agencia"] = match.group(1)
                    break
            
            logger.info(f"[DEEP SCRAPE] Extraídos: tel={result.get('agente_telefone')}, email={result.get('agente_email')}, nome={result.get('agente_nome')}")
            
        except Exception as e:
            logger.error(f"[DEEP SCRAPE] Erro: {e}")
        
        return result
    
    def _extract_phone_from_text(self, text: str) -> Optional[str]:
        """Extrai e limpa um número de telefone de texto."""
        if not text:
            return None
        
        # Remover espaços e caracteres especiais
        clean = re.sub(r'[\s\-\.\(\)]', '', text)
        
        # Remover prefixo +351
        clean = re.sub(r'^\+?351', '', clean)
        
        # Verificar se é telefone português válido
        if re.match(r'^[92]\d{8}$', clean):
            return clean
        
        return None
    
    def _merge_deep_scrape_data(self, main_data: Dict[str, Any], deep_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Faz merge inteligente dos dados do agregador com dados da agência.
        
        A agência tem prioridade para:
        - Telefone do consultor (geralmente é o direto)
        - Email do consultor
        - Nome do consultor
        - Referência da agência
        
        Args:
            main_data: Dados extraídos do agregador (Idealista, etc.)
            deep_data: Dados extraídos da página da agência
            
        Returns:
            Dados fundidos
        """
        result = main_data.copy()
        
        # Campos onde a agência tem prioridade
        priority_fields = ["agente_telefone", "agente_email", "agente_nome", "referencia_agencia"]
        
        for field in priority_fields:
            if deep_data.get(field):
                # Se o agregador não tem o dado, ou se a agência tem telefone móvel vs fixo
                if not result.get(field):
                    result[field] = deep_data[field]
                elif field == "agente_telefone":
                    # Preferir telemóvel sobre fixo
                    current = result[field]
                    new = deep_data[field]
                    if new.startswith("9") and not current.startswith("9"):
                        result[field] = new
        
        # Marcar que houve deep scraping
        if deep_data.get("deep_scraped"):
            result["_deep_scraped"] = True
            result["_deep_source"] = deep_data.get("source_url")
            result["_deep_agency"] = deep_data.get("source_agency")
        
        return result
    
    def _extract_contacts_from_text(self, text: str) -> Dict[str, Any]:
        """
        Extrai telefones e emails de texto usando regex.
        Prioriza telemóveis (9X) sobre fixos (2X).
        
        Returns:
            Dict com telefones e emails encontrados
        """
        contacts = {
            "telefones": [],
            "emails": []
        }
        
        # Extrair telefones com priorização
        mobile_phones = []  # 9X - telemóveis
        landline_phones = []  # 2X - fixos
        
        for pattern in PHONE_PATTERNS:
            matches = re.findall(pattern, text)
            for match in matches:
                # match pode ser string ou tuple (de grupos de captura)
                if isinstance(match, tuple):
                    phone = ''.join(match)
                else:
                    phone = match
                
                # Normalizar telefone - remover espaços, pontos, hífens
                phone = re.sub(r'[\s.\-]', '', phone)
                
                # Remover prefixo tel: se presente
                if phone.startswith('tel:'):
                    phone = phone[4:]
                
                # Remover +351 se presente para normalização
                if phone.startswith('+351'):
                    phone = phone[4:]
                elif phone.startswith('351') and len(phone) == 12:
                    phone = phone[3:]
                
                # Validar que tem 9 dígitos
                if len(phone) != 9 or not phone.isdigit():
                    continue
                
                # Classificar por tipo
                if phone.startswith('9') and phone[1] in '1236':
                    if phone not in mobile_phones:
                        mobile_phones.append(phone)
                elif phone.startswith('2'):
                    if phone not in landline_phones:
                        landline_phones.append(phone)
        
        # Priorizar telemóveis, depois fixos
        contacts["telefones"] = mobile_phones[:3] + landline_phones[:2]
        
        # Extrair emails
        email_matches = re.findall(EMAIL_PATTERN, text, re.IGNORECASE)
        for email in email_matches:
            email_lower = email.lower()
            # Filtrar emails genéricos/inválidos
            generic_patterns = [
                '@example', '@test', 'noreply', 'no-reply',
                'info@', 'geral@', 'contacto@', 'admin@',
                'suporte@', 'support@', 'privacy@'
            ]
            if any(x in email_lower for x in generic_patterns):
                continue
            if email_lower not in contacts["emails"]:
                contacts["emails"].append(email_lower)
        
        return contacts
    
    def _extract_contacts_from_soup(self, soup: BeautifulSoup, agency_type: str = None) -> Dict[str, Any]:
        """
        Extrai contactos usando selectores específicos por agência.
        
        Args:
            soup: BeautifulSoup object
            agency_type: Tipo de agência (remax, era, century21, etc.)
        
        Returns:
            Dict com telefones e emails encontrados
        """
        contacts = {"telefones": [], "emails": []}
        
        # Selectores genéricos
        phone_selectors = [
            'a[href^="tel:"]',
            '.phone', '.tel', '.telefone',
            '.agent-phone', '.consultant-phone',
            '[itemprop="telephone"]',
        ]
        
        email_selectors = [
            'a[href^="mailto:"]',
            '.email', '.mail',
            '.agent-email', '.consultant-email',
            '[itemprop="email"]',
        ]
        
        # Adicionar selectores específicos da agência
        if agency_type and agency_type in AGENCY_PHONE_SELECTORS:
            phone_selectors = AGENCY_PHONE_SELECTORS[agency_type] + phone_selectors
        
        # Extrair telefones
        for selector in phone_selectors:
            try:
                elements = soup.select(selector)
                for elem in elements:
                    # Tentar href primeiro (para links tel:)
                    href = elem.get('href', '')
                    if href.startswith('tel:'):
                        phone = href.replace('tel:', '').replace('+351', '').replace(' ', '')
                        if len(phone) == 9 and phone.isdigit():
                            if phone not in contacts["telefones"]:
                                contacts["telefones"].append(phone)
                    else:
                        # Extrair do texto
                        text = elem.get_text(strip=True)
                        phone = re.sub(r'[^\d]', '', text)
                        if len(phone) >= 9:
                            phone = phone[-9:]  # Últimos 9 dígitos
                            if phone not in contacts["telefones"]:
                                contacts["telefones"].append(phone)
            except Exception:
                continue
        
        # Extrair emails
        for selector in email_selectors:
            try:
                elements = soup.select(selector)
                for elem in elements:
                    href = elem.get('href', '')
                    if href.startswith('mailto:'):
                        email = href.replace('mailto:', '').lower().strip()
                        if '@' in email and email not in contacts["emails"]:
                            contacts["emails"].append(email)
                    else:
                        text = elem.get_text(strip=True).lower()
                        if '@' in text and '.' in text:
                            if text not in contacts["emails"]:
                                contacts["emails"].append(text)
            except Exception:
                continue
        
        return contacts
    
    def _extract_agent_name(self, soup: BeautifulSoup, text: str) -> Optional[str]:
        """
        Tenta extrair o nome do agente/consultor imobiliário da página.
        
        Estratégias:
        1. Procura elementos com classes típicas (agent-name, consultant, etc.)
        2. Procura headers com nomes próprios portugueses
        3. Procura padrões de texto comuns (Consultor: X, Agente: X)
        
        Returns:
            Nome do agente ou None
        """
        # Selectores comuns para nome de agente
        agent_selectors = [
            '.agent-name', '.agente-nome', '.consultant-name', '.consultor-nome',
            '.realtor-name', '.team-member-name', '.employee-name',
            '[data-agent-name]', '[itemprop="name"]',
            'h1.nome', 'h2.nome', 'h1.name', 'h2.name',
            '.card-title', '.profile-name'
        ]
        
        for selector in agent_selectors:
            try:
                element = soup.select_one(selector)
                if element:
                    name = element.get_text(strip=True)
                    # Validar que parece um nome próprio (2-4 palavras, com maiúsculas)
                    if self._is_valid_name(name):
                        return name
            except Exception:
                continue
        
        # Procurar padrões no texto
        name_patterns = [
            r'(?:Consultor|Agente|Responsável|Contacto)\s*[:\-]\s*([A-Z][a-záàâãéêíóôõúç]+(?:\s+[A-Z][a-záàâãéêíóôõúç]+){1,3})',
            r'(?:Fale com|Contacte)\s+([A-Z][a-záàâãéêíóôõúç]+(?:\s+[A-Z][a-záàâãéêíóôõúç]+){1,3})',
        ]
        
        for pattern in name_patterns:
            match = re.search(pattern, text)
            if match:
                name = match.group(1).strip()
                if self._is_valid_name(name):
                    return name
        
        return None
    
    def _extract_agency_name(self, soup: BeautifulSoup, url: str) -> Optional[str]:
        """
        Tenta extrair o nome da agência imobiliária.
        
        Returns:
            Nome da agência ou None
        """
        # Tentar extrair do título da página
        title_tag = soup.find('title')
        if title_tag:
            title = title_tag.get_text(strip=True)
            # Remover partes comuns
            for remove in ['| Imóveis', '- Imóveis', 'Home', 'Início']:
                title = title.replace(remove, '').strip()
            if title and len(title) > 3 and len(title) < 100:
                return title.split('|')[0].split('-')[0].strip()
        
        # Tentar extrair de meta tags
        meta_site = soup.find('meta', {'property': 'og:site_name'})
        if meta_site and meta_site.get('content'):
            return meta_site['content']
        
        # Extrair do domínio como fallback
        parsed = urlparse(url)
        domain_parts = parsed.netloc.replace('www.', '').split('.')
        if domain_parts:
            agency = domain_parts[0].replace('-', ' ').replace('_', ' ').title()
            if len(agency) > 2:
                return agency
        
        return None
    
    def _is_valid_name(self, name: str) -> bool:
        """
        Verifica se uma string parece ser um nome próprio válido.
        
        Returns:
            True se parecer um nome válido
        """
        if not name or len(name) < 4 or len(name) > 60:
            return False
        
        # Deve ter 2-4 palavras
        words = name.split()
        if len(words) < 2 or len(words) > 4:
            return False
        
        # Cada palavra deve começar com maiúscula
        for word in words:
            if not word[0].isupper():
                return False
        
        # Não deve conter números ou caracteres especiais (exceto acentos)
        if re.search(r'[0-9@#$%^&*()+=\[\]{}|\\/<>]', name):
            return False
        
        return True
    
    async def _fetch_page_content(self, url: str, use_proxy: bool = True) -> Optional[str]:
        """
        Faz download do conteúdo HTML de uma URL.
        
        Args:
            url: URL para fazer download
            use_proxy: Se True, usa rotação de proxies (se disponíveis)
        
        Returns:
            Conteúdo HTML ou None se falhar
        """
        proxy = self._get_next_proxy() if use_proxy else None
        
        for verify_ssl in [True, False]:
            try:
                await asyncio.sleep(0.5)  # Delay para evitar bloqueios
                
                client_kwargs = {
                    "timeout": self.timeout,
                    "follow_redirects": True,
                    "verify": verify_ssl,
                    "http2": not proxy  # HTTP2 pode não funcionar com proxies
                }
                
                if proxy:
                    client_kwargs["proxy"] = proxy
                    logger.debug(f"Usando proxy: {proxy[:30]}...")
                
                async with httpx.AsyncClient(**client_kwargs) as client:
                    response = await client.get(url, headers=self._get_headers())
                    
                    if response.status_code == 200:
                        return response.text
                    elif response.status_code in [403, 429]:
                        # Se bloqueado e temos proxies, tenta com próxima
                        if proxy and self._proxies:
                            logger.warning(f"Proxy bloqueada ({response.status_code}), tentando próxima...")
                            continue
                    
            except Exception as e:
                if verify_ssl:
                    continue
                logger.debug(f"Erro ao buscar {url}: {e}")
        
        return None
    
    async def _deep_link_contacts(self, soup: BeautifulSoup, current_url: str) -> Dict[str, Any]:
        """
        Segue links externos para encontrar dados de contacto.
        
        Este método implementa a lógica "Deep Link":
        1. Procura links para sites de agências na página actual
        2. Visita cada link encontrado
        3. Extrai telefones, emails E NOME DO CONSULTOR dessas páginas
        
        Returns:
            Dict com contactos encontrados via deep link
        """
        parsed_url = urlparse(current_url)
        current_domain = parsed_url.netloc.lower()
        
        # Encontrar links de agências
        agency_links = self._find_agency_links(soup, current_domain)
        
        if not agency_links:
            logger.debug(f"Nenhum link de agência encontrado em {current_url}")
            return {}
        
        logger.info(f"Deep Link: Encontrados {len(agency_links)} links de agência em {current_url}")
        
        all_contacts = {
            "telefones": [],
            "emails": [],
            "agente_nome": None,
            "agencia_nome": None,
            "deep_link_sources": []
        }
        
        for link in agency_links[:3]:  # Limitar a 3 para não sobrecarregar
            try:
                html_content = await self._fetch_page_content(link)
                
                if not html_content:
                    continue
                
                # Parse HTML
                link_soup = BeautifulSoup(html_content, 'html.parser')
                
                # Extrair contactos do texto limpo
                clean_text = self._clean_text(html_content)
                contacts = self._extract_contacts_from_text(clean_text)
                
                # Tentar extrair nome do consultor
                agent_name = self._extract_agent_name(link_soup, clean_text)
                if agent_name and not all_contacts["agente_nome"]:
                    all_contacts["agente_nome"] = agent_name
                    logger.info(f"Deep Link: Nome do agente encontrado: {agent_name}")
                
                # Tentar extrair nome da agência
                agency_name = self._extract_agency_name(link_soup, link)
                if agency_name and not all_contacts["agencia_nome"]:
                    all_contacts["agencia_nome"] = agency_name
                
                if contacts["telefones"] or contacts["emails"]:
                    logger.info(f"Deep Link: Encontrados contactos em {link}")
                    all_contacts["telefones"].extend(contacts["telefones"])
                    all_contacts["emails"].extend(contacts["emails"])
                    all_contacts["deep_link_sources"].append(link)
                
            except Exception as e:
                logger.debug(f"Deep Link erro em {link}: {e}")
                continue
        
        # Remover duplicados
        all_contacts["telefones"] = list(set(all_contacts["telefones"]))[:3]
        all_contacts["emails"] = list(set(all_contacts["emails"]))[:3]
        
        return all_contacts
    
    async def _get_ai_model_for_scraping(self) -> str:
        """
        Obtém o modelo de IA configurado para scraping.
        Por defeito usa gemini-2.0-flash.
        
        Returns:
            Nome do modelo a usar (ex: "gemini-2.0-flash", "gpt-4o-mini")
        """
        try:
            # Tentar obter configuração do admin via MongoDB
            from motor.motor_asyncio import AsyncIOMotorClient
            import os
            
            mongo_url = os.environ.get("MONGO_URL", "")
            if mongo_url:
                client = AsyncIOMotorClient(mongo_url)
                db = client.get_default_database()
                config = await db.system_config.find_one({"key": "ai_config"})
                if config and config.get("value", {}).get("scraping_model"):
                    return config["value"]["scraping_model"]
        except Exception as e:
            logger.debug(f"Erro ao obter config de IA: {e}")
        
        # Default: Gemini 2.0 Flash
        return "gemini-2.0-flash"
    
    # ================================================================
    # EXTRAÇÃO COM GEMINI (FALLBACK IA)
    # ================================================================
    
    async def _extract_with_gemini(self, html_content: str, url: str) -> Dict[str, Any]:
        """
        Usa Gemini 2.0 Flash para extrair dados de imóveis quando 
        os parsers específicos falham.
        
        O modelo usado é determinado pela configuração do admin em
        /api/admin/ai-config.
        
        Args:
            html_content: Conteúdo HTML da página
            url: URL da página (para contexto)
            
        Returns:
            Dict com dados extraídos ou erro
        """
        # Obter modelo configurado
        configured_model = await self._get_ai_model_for_scraping()
        logger.info(f"Usando modelo configurado: {configured_model}")
        
        # Verificar se é Gemini ou OpenAI
        if configured_model.startswith("gpt"):
            return await self._extract_with_openai(html_content, url, configured_model)
        
        # Gemini (default)
        if not GEMINI_API_KEY:
            logger.warning("GEMINI_API_KEY não configurada - fallback IA desactivado")
            return {}
        
        import time
        start_time = time.time()
        input_tokens = 0
        output_tokens = 0
        
        try:
            import google.generativeai as genai
            
            # Configurar API
            genai.configure(api_key=GEMINI_API_KEY)
            
            # Limitar HTML para poupar tokens (15k chars ~= 3-4k tokens)
            clean_html = self._clean_text(html_content)[:15000]
            input_tokens = len(clean_html) // 4  # Estimativa: ~4 chars por token
            
            prompt = f"""Analisa este conteúdo de uma página imobiliária portuguesa e extrai TODOS os dados disponíveis em formato JSON estrito.

URL: {url}

Extrai os seguintes campos (usa null se não encontrares):

DADOS DO IMÓVEL:
- titulo: título/nome completo do imóvel
- preco: preço em número (sem €, sem pontos de milhar)
- preco_m2: preço por m² se disponível
- localizacao: localização completa (rua, freguesia, concelho, distrito)
- codigo_postal: código postal se visível
- tipologia: tipo (T0, T1, T2, T3, T4, T5+, moradia V1-V5+, terreno, loja, armazém)
- area: área útil em m² (apenas número)
- area_bruta: área bruta em m² se disponível
- area_terreno: área do terreno em m²
- quartos: número de quartos
- suites: número de suites
- casas_banho: número de casas de banho
- garagem: número de lugares de garagem
- piso: andar/piso do imóvel
- elevador: true/false se tem elevador
- varanda: true/false se tem varanda/terraço
- vista: tipo de vista (mar, rio, cidade, jardim)

CARACTERÍSTICAS:
- descricao: descrição do imóvel (texto completo)
- caracteristicas: lista de características (piscina, ar condicionado, lareira, etc)
- certificacao_energetica: certificado energético (A+, A, B, B-, C, D, E, F, G)
- ano_construcao: ano de construção
- estado: estado do imóvel (novo, usado, remodelado, para renovar, em construção)
- orientacao_solar: orientação (norte, sul, este, oeste)
- condominio: valor do condomínio mensal se aplicável

CONTACTO:
- agente_nome: nome do agente/consultor imobiliário
- agente_telefone: telefone do agente (formato +351 XXX XXX XXX)
- agente_email: email do agente
- agencia_nome: nome da agência/imobiliária
- agencia_telefone: telefone da agência
- referencia: código de referência do anúncio

LINKS:
- foto_principal: URL da foto principal
- url_planta: URL da planta do imóvel se disponível
- url_video: URL do vídeo se disponível

IMPORTANTE: 
1. Responde APENAS com o JSON, sem explicações ou markdown
2. Extrai o máximo de informação possível
3. Para preços, remove símbolos e converte para número
4. Para áreas, extrai apenas o número

Conteúdo:
{clean_html}"""
            
            # Usar Gemini 2.0 Flash
            model = genai.GenerativeModel("gemini-2.0-flash")
            response = model.generate_content(prompt)
            
            result_text = response.text.strip()
            
            # Limpar possíveis markdown code blocks
            if result_text.startswith("```json"):
                result_text = result_text[7:]
            if result_text.startswith("```"):
                result_text = result_text[3:]
            if result_text.endswith("```"):
                result_text = result_text[:-3]
            
            # Parsear JSON
            data = json.loads(result_text.strip())
            output_tokens = len(result_text) // 4  # Estimativa
            
            # Registar uso de IA
            response_time = int((time.time() - start_time) * 1000)
            try:
                from services.ai_usage_tracker import ai_usage_tracker, estimate_cost
                cost = estimate_cost("gemini-2.0-flash", input_tokens, output_tokens)
                await ai_usage_tracker.log_usage(
                    task="scraper_extraction",
                    model="gemini-2.0-flash",
                    provider="gemini",
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cost=cost,
                    response_time_ms=response_time,
                    success=True,
                    metadata={"url": url[:100]}
                )
            except Exception as track_err:
                logger.debug(f"Erro ao registar uso: {track_err}")
            
            logger.info(f"✓ Gemini extraiu dados de {url}: {data.get('titulo', 'N/A')}")
            
            # Retornar todos os campos extraídos
            return {
                # Dados principais
                "titulo": data.get("titulo"),
                "preco": data.get("preco"),
                "preco_m2": data.get("preco_m2"),
                "localizacao": data.get("localizacao"),
                "codigo_postal": data.get("codigo_postal"),
                "tipologia": data.get("tipologia"),
                "area": data.get("area"),
                "area_bruta": data.get("area_bruta"),
                "area_terreno": data.get("area_terreno"),
                "quartos": data.get("quartos"),
                "suites": data.get("suites"),
                "casas_banho": data.get("casas_banho"),
                "garagem": data.get("garagem"),
                "piso": data.get("piso"),
                "elevador": data.get("elevador"),
                "varanda": data.get("varanda"),
                "vista": data.get("vista"),
                # Características
                "descricao": data.get("descricao"),
                "caracteristicas": data.get("caracteristicas"),
                "certificado_energetico": data.get("certificacao_energetica"),
                "ano_construcao": data.get("ano_construcao"),
                "estado": data.get("estado"),
                "orientacao_solar": data.get("orientacao_solar"),
                "condominio": data.get("condominio"),
                # Contacto
                "agente_nome": data.get("agente_nome"),
                "agente_telefone": data.get("agente_telefone"),
                "agente_email": data.get("agente_email"),
                "agencia_nome": data.get("agencia_nome"),
                "agencia_telefone": data.get("agencia_telefone"),
                "referencia": data.get("referencia"),
                # Links
                "foto_principal": data.get("foto_principal"),
                "url_planta": data.get("url_planta"),
                "url_video": data.get("url_video"),
                "_extracted_by": "gemini-2.0-flash"
            }
            
        except json.JSONDecodeError as e:
            logger.error(f"Gemini retornou JSON inválido: {e}")
            # Registar erro
            try:
                from services.ai_usage_tracker import ai_usage_tracker, estimate_cost
                response_time = int((time.time() - start_time) * 1000)
                cost = estimate_cost("gemini-2.0-flash", input_tokens, 0)
                await ai_usage_tracker.log_usage(
                    task="scraper_extraction",
                    model="gemini-2.0-flash",
                    provider="gemini",
                    input_tokens=input_tokens,
                    cost=cost,
                    response_time_ms=response_time,
                    success=False,
                    error_message="JSON inválido"
                )
            except Exception:
                pass
            return {"_error": "JSON inválido da IA"}
        except Exception as e:
            error_str = str(e).lower()
            # Tratamento específico para quota excedida
            if "quota" in error_str or "rate" in error_str or "resource" in error_str or "exhausted" in error_str:
                logger.warning(f"Gemini quota excedida - continuando sem IA: {e}")
                # Registar erro de quota
                try:
                    from services.ai_usage_tracker import ai_usage_tracker
                    await ai_usage_tracker.log_usage(
                        task="scraper_extraction",
                        model="gemini-2.0-flash",
                        provider="gemini",
                        success=False,
                        error_message="quota_exceeded"
                    )
                except Exception:
                    pass
                return {"_error": "quota_exceeded", "_fallback": True}
            logger.error(f"Erro Gemini: {type(e).__name__}: {e}")
            return {"_error": str(e)}
    
    async def _extract_with_openai(self, html_content: str, url: str, model: str) -> Dict[str, Any]:
        """
        Usa OpenAI como alternativa ao Gemini para extracção.
        
        Args:
            html_content: Conteúdo HTML da página
            url: URL da página
            model: Modelo OpenAI a usar (ex: 'gpt-4o-mini')
            
        Returns:
            Dict com dados extraídos ou erro
        """
        from config import EMERGENT_LLM_KEY
        
        if not EMERGENT_LLM_KEY:
            logger.warning("EMERGENT_LLM_KEY não configurada - OpenAI desactivado")
            return {"_error": "EMERGENT_LLM_KEY não configurada"}
        
        try:
            from emergentintegrations.llm.chat import LlmChat, UserMessage
            
            clean_html = self._clean_text(html_content)[:20000]
            
            prompt = f"""Analisa este conteúdo de uma página imobiliária portuguesa e extrai TODOS os dados disponíveis em formato JSON.

URL: {url}

Extrai os seguintes campos (usa null se não encontrares):

DADOS DO IMÓVEL:
- titulo, preco (número), preco_m2, localizacao, codigo_postal
- tipologia (T0-T5+, V1-V5+, moradia, terreno, loja)
- area (m²), area_bruta, area_terreno, quartos, suites, casas_banho
- garagem, piso, elevador, varanda, vista

CARACTERÍSTICAS:
- descricao (texto completo), caracteristicas (lista)
- certificacao_energetica, ano_construcao, estado, orientacao_solar, condominio

CONTACTO:
- agente_nome, agente_telefone (+351 XXX XXX XXX), agente_email
- agencia_nome, agencia_telefone, referencia

LINKS:
- foto_principal, url_planta, url_video

Responde APENAS com JSON válido. Extrai o máximo de informação.

Conteúdo:
{clean_html}"""
            
            chat = LlmChat(
                api_key=EMERGENT_LLM_KEY,
                session_id="scraper-extraction",
                system_message="Extrais dados de páginas imobiliárias. Respondes sempre em JSON válido."
            ).with_model("openai", model)
            
            response = await chat.send_message(UserMessage(text=prompt))
            
            result_text = response.strip()
            if result_text.startswith("```json"):
                result_text = result_text[7:]
            if result_text.startswith("```"):
                result_text = result_text[3:]
            if result_text.endswith("```"):
                result_text = result_text[:-3]
            
            data = json.loads(result_text.strip())
            
            logger.info(f"✓ OpenAI ({model}) extraiu dados de {url}")
            
            # Normalizar resposta - aplanar categorias aninhadas se existirem
            normalized = {}
            for key, value in data.items():
                if isinstance(value, dict):
                    # Aplanar categorias como DADOS_DO_IMOVEL, CARACTERISTICAS, etc.
                    for sub_key, sub_value in value.items():
                        normalized[sub_key] = sub_value
                else:
                    normalized[key] = value
            
            return {
                **normalized,
                "_extracted_by": f"openai-{model}"
            }
            
        except Exception as e:
            logger.error(f"Erro OpenAI: {e}")
            return {"_error": str(e)}
    
    # ================================================================
    # SCRAPING PRINCIPAL (HÍBRIDO COM DEEP LINK E CACHE)
    # ================================================================
    
    async def scrape_url(self, url: str, use_cache: bool = True) -> Dict[str, Any]:
        """
        Extrai dados de uma URL imobiliária usando abordagem híbrida com Deep Scraping.
        
        Fluxo:
        1. Verifica cache local
        2. Obtém HTML usando curl_cffi (bypass anti-bot)
        3. Usa parser específico ou genérico
        4. Se for agregador, faz Deep Scraping para sites de agências
        5. Faz merge inteligente dos dados
        6. Guarda resultado em cache
        
        Args:
            url: URL a processar
            use_cache: Se deve usar/guardar cache (default: True)
            
        Returns:
            Dict com dados do imóvel
        """
        if not url:
            return {"error": "URL vazia"}
        
        # Normalizar URL
        if not url.startswith("http"):
            url = "https://" + url
        
        # ============================================================
        # VERIFICAR CACHE
        # ============================================================
        if use_cache:
            cached = await self._get_cached_result(url)
            if cached:
                return cached
        
        parsed_url = urlparse(url)
        current_domain = parsed_url.netloc.lower()
        is_aggregator = self._is_aggregator_site(url)
        is_protected = any(site in current_domain for site in PROTECTED_SITES)
        
        logger.info(f"[SCRAPER] Processando: {url[:80]}... (agregador={is_aggregator}, protegido={is_protected})")
        
        # ============================================================
        # OBTER HTML COM CURL_CFFI (ANTI-BOT BYPASS)
        # ============================================================
        html_content = None
        
        # Primeiro tentar curl_cffi (funciona na maioria dos casos)
        html_content = await self._fetch_url(url)
        
        # Se falhou, tentar ScraperAPI (para sites protegidos ou agregadores)
        if not html_content and SCRAPERAPI_KEY:
            logger.info("[SCRAPER] curl_cffi falhou, tentando ScraperAPI...")
            html_content = await self._fetch_with_scraperapi(url)
        
        if not html_content:
            return {"error": "Não foi possível obter o conteúdo da página. O site pode estar bloqueando acessos automáticos."}
        
        # ============================================================
        # PARSEAR HTML
        # ============================================================
        soup = BeautifulSoup(html_content, 'html.parser')
        url_lower = url.lower()
        result = {}
        parser_used = None
        
        if "idealista" in url_lower:
            result = self._parse_idealista(soup, html_content)
            parser_used = "idealista"
        elif "imovirtual" in url_lower:
            result = self._parse_imovirtual(soup)
            parser_used = "imovirtual"
        elif "supercasa" in url_lower:
            result = self._parse_supercasa(soup)
            parser_used = "supercasa"
        elif "casasapo" in url_lower or "casa.sapo" in url_lower:
            result = self._parse_casasapo(soup)
            parser_used = "casasapo"
        elif "remax" in url_lower:
            result = self._parse_remax(soup)
            parser_used = "remax"
        elif "era.pt" in url_lower:
            result = self._parse_era(soup, html_content)
            parser_used = "era"
        elif "kw.com" in url_lower or "kwportugal" in url_lower:
            result = self._parse_kw(soup)
            parser_used = "kw"
        elif "easygest" in url_lower:
            result = self._parse_easygest(soup, html_content, url)
            parser_used = "easygest"
        else:
            result = self._parse_generic(soup)
            parser_used = "generic"
        
        # ============================================================
        # FALLBACK GEMINI: Se dados essenciais estiverem em falta
        # ============================================================
        needs_gemini = False
        
        if not result.get("titulo") and not result.get("preco"):
            needs_gemini = True
            logger.info(f"Parser {parser_used} falhou - título e preço em falta")
        elif parser_used == "generic":
            needs_gemini = True
            logger.info("Site genérico - usando Gemini para melhor extração")
        
        if needs_gemini:
            gemini_result = await self._extract_with_gemini(html_content, url)
            
            if gemini_result and not gemini_result.get("_error"):
                for key, value in gemini_result.items():
                    if key.startswith("_"):
                        continue
                    if value is not None and (not result.get(key) or result.get(key) == "N/A"):
                        result[key] = value
                
                result["_extracted_by"] = "hybrid (parser + gemini)"
            else:
                result["_extracted_by"] = parser_used
        else:
            result["_extracted_by"] = parser_used
        
        # ============================================================
        # DEEP SCRAPING: Se for agregador, procurar dados na agência
        # ============================================================
        if is_aggregator:
            logger.info("[DEEP SCRAPING] Site agregador detectado, procurando links de agências...")
            
            agency_links = self._find_agency_links(soup, current_domain)
            
            if agency_links:
                logger.info(f"[DEEP SCRAPING] Encontrados {len(agency_links)} links de agências: {[link['agency'] for link in agency_links]}")
                
                # Tentar o primeiro link de agência
                for link_info in agency_links:
                    deep_data = await self._deep_scrape_agency(
                        link_info["url"], 
                        link_info["agency"]
                    )
                    
                    # Se obtivemos dados úteis, fazer merge e parar
                    if deep_data.get("agente_telefone") or deep_data.get("agente_email"):
                        result = self._merge_deep_scrape_data(result, deep_data)
                        logger.info(f"[DEEP SCRAPING] Dados da agência {link_info['agency']} incorporados com sucesso")
                        break
            else:
                logger.info("[DEEP SCRAPING] Nenhum link de agência encontrado")
        
        # Se ainda não temos contacto, extrair do texto da página original
        if not result.get("agente_telefone") and not result.get("agente_email"):
            clean_text = self._clean_text(html_content)
            contacts = self._extract_contacts_from_text(clean_text)
            
            if contacts.get("telefones"):
                phones = contacts["telefones"]
                mobile = next((p for p in phones if p.startswith("9")), None)
                result["agente_telefone"] = mobile or phones[0]
            
            if contacts.get("emails"):
                valid_emails = [e for e in contacts["emails"] 
                              if not any(x in e.lower() for x in ["noreply", "info@", "geral@"])]
                if valid_emails:
                    result["agente_email"] = valid_emails[0]
        
        # ============================================================
        # GUARDAR EM CACHE E RETORNAR
        # ============================================================
        result["_url"] = url
        result["_source"] = current_domain
        
        if use_cache and not result.get("error"):
            await self._save_to_cache(url, result)
        
        return result
    
    # ================================================================
    # PARSERS ESPECÍFICOS
    # ================================================================
    
    def _parse_idealista(self, soup: BeautifulSoup, raw_html: str = "") -> Dict[str, Any]:
        """
        Parser melhorado para Idealista.pt
        
        Extrai:
        - Dados básicos: título, preço, localização, tipologia, área
        - Referência do anúncio
        - Link da agência (para deep link) - incluindo EasyGest
        - Nome do consultor/agente
        - Certificado energético
        """
        data = {}
        
        # Título
        title = soup.find('h1', class_='main-info__title')
        if title:
            data["titulo"] = title.get_text(strip=True)
        
        # Preço
        price = soup.find('span', class_='info-data-price')
        if not price:
            price = soup.find('span', {'class': lambda x: x and 'price' in x.lower()})
        if price:
            price_text = re.sub(r'[^\d]', '', price.get_text())
            if price_text:
                data["preco"] = int(price_text)
        
        # Localização
        location = soup.find('span', class_='main-info__title-minor')
        if location:
            data["localizacao"] = location.get_text(strip=True)
        
        # === Referência do anúncio ===
        # Procurar em múltiplos locais possíveis
        ref_patterns = [
            r'Ref[.:]?\s*(\w+)',
            r'Referência[.:]?\s*(\w+)',
            r'reference[.:]?\s*(\w+)',
        ]
        
        # Procurar na classe .reference
        ref_elem = soup.find(class_='reference')
        if ref_elem:
            data["referencia"] = ref_elem.get_text(strip=True)
        else:
            # Procurar em atributos data-*
            ref_attr = soup.find(attrs={'data-reference': True})
            if ref_attr:
                data["referencia"] = ref_attr.get('data-reference')
            else:
                # Procurar no texto via regex
                text_content = soup.get_text()
                for pattern in ref_patterns:
                    match = re.search(pattern, text_content, re.IGNORECASE)
                    if match:
                        data["referencia"] = match.group(1)
                        break
        
        # === Link da agência (MELHORADO para EasyGest e outros) ===
        # 1. Procurar links directos em botões/links de agência
        agency_selectors = [
            'a[data-link="agency"]',
            'a.agency-link',
            '.advertiser-info a[href*="remax"]',
            '.advertiser-info a[href*="era"]',
            '.advertiser-info a[href*="century21"]',
            '.advertiser-info a[href*="kwportugal"]',
            '.advertiser-info a[href*="zome"]',
            '.advertiser-info a[href*="iad"]',
            '.advertiser-info a[href*="easygest"]',
            '.advertiser-info a[href*="quatru"]',
            'a[href*="agencia"]',
            'a[href*="imobiliaria"]',
            # Selectores específicos do Idealista
            '.professional-name a',
            '.advertiser-data a',
            '.contact-action a[target="_blank"]',
            'a.advertiser-logo',
        ]
        
        for selector in agency_selectors:
            try:
                agency_link = soup.select_one(selector)
                if agency_link and agency_link.get('href'):
                    href = agency_link.get('href')
                    if href.startswith('http') and 'idealista' not in href.lower():
                        data["agency_link"] = href
                        logger.info(f"[IDEALISTA] Link de agência encontrado via selector: {href[:60]}...")
                        break
            except Exception:
                continue
        
        # 2. Procurar em scripts JavaScript por URLs de redirecionamento
        if 'agency_link' not in data:
            scripts = soup.find_all('script')
            agency_url_patterns = [
                r'easygest\.com\.pt[^\s"\'<>]*',
                r'remax\.pt[^\s"\'<>]*',
                r'century21\.pt[^\s"\'<>]*',
                r'quatru\.pt[^\s"\'<>]*',
                r'zome\.pt[^\s"\'<>]*',
                r'era\.pt[^\s"\'<>]*',
                r'https?://[^\s"\'<>]+imobiliaria[^\s"\'<>]*',
                r'https?://[^\s"\'<>]+imovel[^\s"\'<>]*\d{6,}',  # URLs com IDs de imóveis
            ]
            
            for script in scripts:
                script_text = script.string or ""
                for pattern in agency_url_patterns:
                    match = re.search(pattern, script_text, re.IGNORECASE)
                    if match:
                        url = match.group(0)
                        if not url.startswith('http'):
                            url = 'https://' + url
                        data["agency_link"] = url
                        logger.info(f"[IDEALISTA] Link de agência encontrado em script: {url[:60]}...")
                        break
                if 'agency_link' in data:
                    break
        
        # 3. Procurar no raw HTML por padrões de URL de agências
        if 'agency_link' not in data and raw_html:
            # Padrões específicos para EasyGest e outras agências
            html_patterns = [
                r'href=["\']?(https?://[^\s"\'<>]*easygest[^\s"\'<>]*)["\']?',
                r'href=["\']?(https?://[^\s"\'<>]*remax[^\s"\'<>]*)["\']?',
                r'href=["\']?(https?://[^\s"\'<>]*quatru[^\s"\'<>]*)["\']?',
                r'href=["\']?(https?://[^\s"\'<>]*century21[^\s"\'<>]*)["\']?',
                r'href=["\']?(https?://[^\s"\'<>]*zome[^\s"\'<>]*)["\']?',
                r'data-url=["\']?(https?://[^\s"\'<>]*imobiliaria[^\s"\'<>]*)["\']?',
            ]
            
            for pattern in html_patterns:
                match = re.search(pattern, raw_html, re.IGNORECASE)
                if match:
                    url = match.group(1)
                    if 'idealista' not in url.lower():
                        data["agency_link"] = url
                        logger.info(f"[IDEALISTA] Link de agência encontrado via regex HTML: {url[:60]}...")
                        break
        
        # 4. Procurar texto "Ver no site da agência" ou similar
        agency_buttons = soup.find_all('a', string=re.compile(r'(site da agência|agência|agency|ver anúncio|ver original)', re.IGNORECASE))
        for btn in agency_buttons:
            href = btn.get('href', '')
            if href.startswith('http') and 'idealista' not in href.lower() and 'agency_link' not in data:
                data["agency_link"] = href
                logger.info(f"[IDEALISTA] Link de agência encontrado via botão: {href[:60]}...")
                break
        
        # === Nome do consultor/agente ===
        agent_selectors = [
            '.professional-name',
            '.advertiser-data-name',
            '.agent-name',
            '.contact-name',
            '[itemprop="name"]',
        ]
        
        for selector in agent_selectors:
            try:
                agent_elem = soup.select_one(selector)
                if agent_elem:
                    agent_name = agent_elem.get_text(strip=True)
                    if agent_name and self._is_valid_name(agent_name):
                        data["agente_nome"] = agent_name
                        break
            except Exception:
                continue
        
        # === Nome da agência/imobiliária ===
        agency_name_selectors = [
            '.advertiser-name',
            '.agency-name',
            '.professional-agency',
            '.advertiser-data .name',
            'span[class*="agency"]',
            'span[class*="professional"]',
            '[data-testid="advertiser-name"]',
        ]
        
        for selector in agency_name_selectors:
            try:
                agency_elem = soup.select_one(selector)
                if agency_elem:
                    agency_name = agency_elem.get_text(strip=True)
                    if agency_name and len(agency_name) > 2 and len(agency_name) < 100:
                        data["agencia_nome"] = agency_name
                        break
            except Exception:
                continue
        
        # Fallback: tentar extrair nome da agência do link
        if 'agencia_nome' not in data and data.get('agency_link'):
            # Extrair nome do domínio
            agency_url = data['agency_link']
            domain_match = re.search(r'https?://(?:www\.)?([^/]+)', agency_url)
            if domain_match:
                domain = domain_match.group(1)
                # Mapear domínios conhecidos
                agency_mapping = {
                    'remax': 'RE/MAX',
                    'century21': 'Century 21',
                    'era.pt': 'ERA',
                    'zome': 'Zome',
                    'easygest': 'EasyGest',
                    'quatru': 'Quatru',
                    'kw': 'Keller Williams',
                    'kwportugal': 'Keller Williams',
                    'iad': 'IAD',
                    'safti': 'SAFTI',
                }
                for key, name in agency_mapping.items():
                    if key in domain.lower():
                        data["agencia_nome"] = name
                        break
        
        # Características
        features = soup.find_all('li', class_='info-features-item')
        for feat in features:
            text = feat.get_text(strip=True).lower()
            if 'm²' in text or 'm2' in text:
                area = re.search(r'(\d+)', text)
                if area:
                    data["area"] = int(area.group(1))
            elif 'quarto' in text or 'hab' in text:
                rooms = re.search(r'(\d+)', text)
                if rooms:
                    data["quartos"] = int(rooms.group(1))
            elif 'wc' in text or 'banho' in text:
                baths = re.search(r'(\d+)', text)
                if baths:
                    data["casas_banho"] = int(baths.group(1))
        
        # Tipologia
        if data.get("quartos"):
            data["tipologia"] = f"T{data['quartos']}"
        
        # Descrição
        desc = soup.find('div', class_='comment')
        if desc:
            data["descricao"] = desc.get_text(strip=True)[:500]
        
        # === Certificado energético ===
        energy_patterns = [
            r'[Cc]ertificado\s+[Ee]nerg[ée]tico[:\s]+([A-Ga-g][+]?)',
            r'[Cc]lasse\s+[Ee]nerg[ée]tica[:\s]+([A-Ga-g][+]?)',
            r'[Ee]nergy\s+[Cc]ertificate[:\s]+([A-Ga-g][+]?)',
            r'\b([A-G])\s*[-–]\s*[Cc]ertificado',
        ]
        
        # Procurar na secção de características
        details_section = soup.find('div', class_='details-property')
        if details_section:
            details_text = details_section.get_text()
            for pattern in energy_patterns:
                match = re.search(pattern, details_text)
                if match:
                    data["certificado_energetico"] = match.group(1).upper()
                    break
        
        # Fallback: procurar em todo o documento
        if 'certificado_energetico' not in data:
            full_text = soup.get_text()
            for pattern in energy_patterns:
                match = re.search(pattern, full_text)
                if match:
                    data["certificado_energetico"] = match.group(1).upper()
                    break
        
        # === 5. TAREFA 4: Procurar URLs de agências na descrição ===
        # Se ainda não encontramos agency_link, procurar no texto da descrição
        if 'agency_link' not in data:
            desc_text = data.get("descricao", "") or ""
            
            # Padrões de URLs de agências comuns no texto
            desc_url_patterns = [
                # Encurtadores (frequentemente usados em descrições)
                r'(https?://dez\.pt/[a-zA-Z0-9]+)',
                r'(https?://bit\.ly/[a-zA-Z0-9]+)',
                r'(https?://tinyurl\.com/[a-zA-Z0-9]+)',
                r'(https?://t\.co/[a-zA-Z0-9]+)',
                # Domínios simples sem https (comuns em descrições)
                r'(?:visite|veja|mais info(?:rmações)?|site)[:\s]+([a-z0-9-]+\.(?:pt|com)[^\s<>"\']{0,50})',
                # URLs completas de agências
                r'(https?://(?:www\.)?easygest[^\s<>"\']+)',
                r'(https?://(?:www\.)?remax[^\s<>"\']+)',
                r'(https?://(?:www\.)?century21[^\s<>"\']+)',
                r'(https?://(?:www\.)?era\.pt[^\s<>"\']+)',
                r'(https?://(?:www\.)?zome[^\s<>"\']+)',
                r'(https?://(?:www\.)?quatru[^\s<>"\']+)',
                r'(https?://(?:www\.)?kw(?:portugal)?[^\s<>"\']+)',
                r'(https?://(?:www\.)?iad[^\s<>"\']+)',
                r'(https?://(?:www\.)?safti[^\s<>"\']+)',
                # Qualquer URL com padrão de imobiliária
                r'(https?://[^\s<>"\']+/(?:imovel|property|listing)/[^\s<>"\']+)',
            ]
            
            # Procurar primeiro na descrição
            for pattern in desc_url_patterns:
                match = re.search(pattern, desc_text, re.IGNORECASE)
                if match:
                    url_found = match.group(1)
                    # Adicionar https se não tiver
                    if not url_found.startswith('http'):
                        url_found = 'https://' + url_found
                    # Validar que não é do idealista
                    if 'idealista' not in url_found.lower():
                        data["agency_link"] = url_found
                        logger.info(f"[IDEALISTA] Link de agência encontrado na descrição: {url_found[:60]}...")
                        break
            
            # Se não encontrou na descrição, procurar no HTML todo
            if 'agency_link' not in data and raw_html:
                # Procurar padrões no texto completo
                full_text = soup.get_text(' ', strip=True)
                for pattern in desc_url_patterns[:5]:  # Apenas encurtadores e padrões simples
                    match = re.search(pattern, full_text, re.IGNORECASE)
                    if match:
                        url_found = match.group(1)
                        if not url_found.startswith('http'):
                            url_found = 'https://' + url_found
                        if 'idealista' not in url_found.lower():
                            data["agency_link"] = url_found
                            logger.info(f"[IDEALISTA] Link de agência encontrado no texto completo: {url_found[:60]}...")
                            break
        
        return data
    
    def _parse_imovirtual(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Parser para Imovirtual.com"""
        data = {}
        
        # Título
        title = soup.find('h1', {'data-cy': 'adPageAdTitle'})
        if not title:
            title = soup.find('h1')
        if title:
            data["titulo"] = title.get_text(strip=True)
        
        # Preço
        price = soup.find('strong', {'data-cy': 'adPageHeaderPrice'})
        if not price:
            price = soup.find('strong', class_=lambda x: x and 'price' in str(x).lower())
        if price:
            price_text = re.sub(r'[^\d]', '', price.get_text())
            if price_text:
                data["preco"] = int(price_text)
        
        # Localização
        location = soup.find('a', {'data-cy': 'adPageHeaderBreadcrumb'})
        if location:
            data["localizacao"] = location.get_text(strip=True)
        
        # Área
        area_elem = soup.find('div', {'data-testid': 'table-value-area'})
        if area_elem:
            area = re.search(r'(\d+)', area_elem.get_text())
            if area:
                data["area"] = int(area.group(1))
        
        # Quartos
        rooms_elem = soup.find('div', {'data-testid': 'table-value-rooms_num'})
        if rooms_elem:
            rooms = re.search(r'(\d+)', rooms_elem.get_text())
            if rooms:
                data["quartos"] = int(rooms.group(1))
                data["tipologia"] = f"T{data['quartos']}"
        
        return data
    
    def _parse_casasapo(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Parser para Casa.sapo.pt"""
        data = {}
        
        title = soup.find('h1')
        if title:
            data["titulo"] = title.get_text(strip=True)
        
        price = soup.find('span', class_='priceValue')
        if not price:
            price = soup.find(class_=lambda x: x and 'price' in str(x).lower())
        if price:
            price_text = re.sub(r'[^\d]', '', price.get_text())
            if price_text:
                data["preco"] = int(price_text)
        
        return data
    
    def _parse_remax(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Parser para Remax.pt"""
        data = {}
        
        title = soup.find('h1', class_='details-title')
        if not title:
            title = soup.find('h1')
        if title:
            data["titulo"] = title.get_text(strip=True)
        
        price = soup.find('div', class_='details-price')
        if price:
            price_text = re.sub(r'[^\d]', '', price.get_text())
            if price_text:
                data["preco"] = int(price_text)
        
        return data
    
    def _parse_era(self, soup: BeautifulSoup, raw_html: str = "") -> Dict[str, Any]:
        """Parser para ERA.pt"""
        data = {}
        
        # Tentar JSON-LD primeiro
        scripts = soup.find_all('script', type='application/ld+json')
        for script in scripts:
            try:
                json_data = json.loads(script.string)
                if isinstance(json_data, dict):
                    if json_data.get('@type') == 'Product' or json_data.get('@type') == 'RealEstateListing':
                        if json_data.get('name'):
                            data["titulo"] = json_data['name']
                        if json_data.get('offers', {}).get('price'):
                            data["preco"] = int(float(json_data['offers']['price']))
            except (json.JSONDecodeError, TypeError, ValueError):
                continue
        
        # Fallback para HTML
        if not data.get("titulo"):
            title = soup.find('h1')
            if title:
                data["titulo"] = title.get_text(strip=True)
        
        return data
    
    def _parse_kw(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Parser para KW Portugal"""
        data = {}
        
        title = soup.find('h1')
        if title:
            data["titulo"] = title.get_text(strip=True)
        
        price = soup.find(class_=lambda x: x and 'price' in str(x).lower())
        if price:
            price_text = re.sub(r'[^\d]', '', price.get_text())
            if price_text:
                data["preco"] = int(price_text)
        
        return data
    
    def _parse_easygest(self, soup: BeautifulSoup, raw_html: str = "", url: str = "") -> Dict[str, Any]:
        """
        Parser para EasyGest (easygest.com.pt) - Powered by eGO Real Estate
        
        EasyGest usa o sistema eGO Real Estate que inclui dados estruturados
        em JSON-LD (Schema.org). Este parser prioriza:
        1. JSON-LD (RealEstateListing, RealEstateAgent)
        2. Meta tags OpenGraph
        3. Extracção da URL (referência)
        4. Fallback para selectores HTML
        
        URLs típicas: https://www.easygest.com.pt/imovel/titulo-slug/24001265
        """
        data = {}
        
        logger.info(f"[EASYGEST] A fazer parse de: {url[:60] if url else 'N/A'}...")
        
        # === 1. Extrair dados do JSON-LD (mais fiável) ===
        json_ld_scripts = soup.find_all('script', type='application/ld+json')
        
        for script in json_ld_scripts:
            try:
                json_data = json.loads(script.string) if script.string else {}
                schema_type = json_data.get('@type', '')
                
                # RealEstateListing - dados do imóvel
                if schema_type == 'RealEstateListing':
                    if json_data.get('name'):
                        data["titulo"] = json_data['name']
                    
                    if json_data.get('description'):
                        data["descricao"] = json_data['description'][:1500]
                    
                    # Preço está em offers
                    offers = json_data.get('offers', {})
                    if offers.get('price'):
                        try:
                            data["preco"] = int(float(offers['price']))
                        except (ValueError, TypeError):
                            pass
                    
                    # URL canónica
                    if json_data.get('url'):
                        data["_canonical_url"] = json_data['url']
                    
                    # Imagem
                    if json_data.get('image'):
                        data["foto_principal"] = json_data['image']
                    elif json_data.get('primaryImageOfPage'):
                        data["foto_principal"] = json_data['primaryImageOfPage']
                    
                    logger.info(f"[EASYGEST] JSON-LD RealEstateListing: titulo={data.get('titulo', 'N/A')[:30]}, preco={data.get('preco')}")
                
                # RealEstateAgent - dados da agência
                elif schema_type == 'RealEstateAgent':
                    if json_data.get('telephone'):
                        phone = re.sub(r'[^\d+]', '', json_data['telephone'])
                        if phone:
                            data["agente_telefone"] = phone
                    
                    if json_data.get('name'):
                        data["agencia_nome"] = json_data['name']
                    
                    # Endereço
                    address = json_data.get('address', {})
                    if address.get('addressLocality'):
                        data["localizacao"] = address['addressLocality']
                    
                    logger.info(f"[EASYGEST] JSON-LD RealEstateAgent: tel={data.get('agente_telefone')}, agencia={data.get('agencia_nome', 'N/A')[:20]}")
                    
            except (json.JSONDecodeError, TypeError, AttributeError) as e:
                logger.debug(f"[EASYGEST] Erro ao processar JSON-LD: {e}")
                continue
        
        # === 2. Referência da URL ===
        # URLs do EasyGest terminam com o ID: /imovel/slug/24001265
        if url:
            ref_match = re.search(r'/(\d{6,})(?:[/?#]|$)', url)
            if ref_match:
                data["referencia"] = ref_match.group(1)
                logger.info(f"[EASYGEST] Referência extraída da URL: {data['referencia']}")
        
        # Fallback: procurar na canonical URL
        if 'referencia' not in data:
            canonical = soup.find('link', rel='canonical')
            if canonical and canonical.get('href'):
                ref_match = re.search(r'/(\d{6,})(?:[/?#]|$)', canonical['href'])
                if ref_match:
                    data["referencia"] = ref_match.group(1)
        
        # === 3. Meta tags OpenGraph (fallback) ===
        if not data.get("titulo"):
            og_title = soup.find('meta', property='og:title')
            if og_title:
                data["titulo"] = og_title.get('content', '').strip()
        
        if not data.get("descricao"):
            og_desc = soup.find('meta', property='og:description')
            if og_desc:
                data["descricao"] = og_desc.get('content', '').strip()[:1500]
            else:
                meta_desc = soup.find('meta', attrs={'name': 'description'})
                if meta_desc:
                    data["descricao"] = meta_desc.get('content', '').strip()[:1500]
        
        if not data.get("foto_principal"):
            og_image = soup.find('meta', property='og:image')
            if og_image:
                data["foto_principal"] = og_image.get('content', '')
        
        # === 4. Localização do breadcrumb ou URL ===
        if not data.get("localizacao"):
            # Tentar extrair do título ou breadcrumb
            # URLs: /imovel/apartamento-t2-em-queluz-.../ID
            if url:
                # Extrair cidade do slug
                slug_match = re.search(r'/imovel/[^/]*-em-([^/]+)/', url.lower())
                if slug_match:
                    location = slug_match.group(1).replace('-', ' ').title()
                    data["localizacao"] = location
        
        # === 5. Características do texto ===
        text_content = soup.get_text().lower()
        
        # Tipologia (T1, T2, T3...)
        tipologia_match = re.search(r'\bt(\d)\b', text_content)
        if tipologia_match:
            data["tipologia"] = f"T{tipologia_match.group(1)}"
            data["quartos"] = int(tipologia_match.group(1))
        
        # Área
        area_match = re.search(r'(\d+)\s*m[²2]', text_content)
        if area_match:
            data["area"] = int(area_match.group(1))
        
        # Casas de banho
        wc_match = re.search(r'(\d+)\s*(?:casas?\s*de\s*banho|wc|banhos?)', text_content)
        if wc_match:
            data["casas_banho"] = int(wc_match.group(1))
        
        # === 6. Contactos do texto (fallback) ===
        if not data.get("agente_telefone"):
            clean_text = self._clean_text(raw_html if raw_html else str(soup))
            contacts = self._extract_contacts_from_text(clean_text)
            
            if contacts.get("telefones"):
                phones = contacts["telefones"]
                # Preferir telemóvel (começa com 9)
                mobile = next((p for p in phones if p.startswith("9")), None)
                data["agente_telefone"] = mobile or phones[0]
            
            if contacts.get("emails"):
                # Filtrar emails genéricos
                valid_emails = [e for e in contacts["emails"] 
                              if not any(x in e.lower() for x in ["noreply", "info@", "geral@", "admin@", "no-reply"])]
                if valid_emails:
                    data["agente_email"] = valid_emails[0]
        
        logger.info(f"[EASYGEST] Extracção completa: titulo={data.get('titulo', 'N/A')[:30]}..., ref={data.get('referencia')}, preco={data.get('preco')}")
        
        return data
    
    def _parse_supercasa(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Parser para SuperCasa.pt"""
        data = {}
        
        title = soup.find('h1')
        if title:
            data["titulo"] = title.get_text(strip=True)
        
        price = soup.find(class_=lambda x: x and 'price' in str(x).lower())
        if price:
            price_text = re.sub(r'[^\d]', '', price.get_text())
            if price_text:
                data["preco"] = int(price_text)
        
        return data
    
    def _parse_generic(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Parser genérico usando meta tags OpenGraph e Schema.org"""
        data = {}
        
        # OpenGraph
        og_title = soup.find('meta', property='og:title')
        if og_title:
            data["titulo"] = og_title.get('content', '')
        
        og_desc = soup.find('meta', property='og:description')
        if og_desc:
            data["descricao"] = og_desc.get('content', '')[:500]
        
        # Schema.org
        for script in soup.find_all('script', type='application/ld+json'):
            try:
                json_data = json.loads(script.string)
                if isinstance(json_data, dict):
                    if json_data.get('name'):
                        data["titulo"] = json_data['name']
                    if json_data.get('offers', {}).get('price'):
                        data["preco"] = int(float(json_data['offers']['price']))
            except (json.JSONDecodeError, TypeError, ValueError):
                continue
        
        # Fallback: H1
        if not data.get("titulo"):
            h1 = soup.find('h1')
            if h1:
                data["titulo"] = h1.get_text(strip=True)
        
        # Tentar encontrar preço no texto
        if not data.get("preco"):
            text = soup.get_text()
            prices = re.findall(r'(\d{1,3}(?:\.\d{3})*(?:,\d{2})?)\s*€', text)
            if prices:
                price_text = prices[0].replace('.', '').replace(',', '.')
                try:
                    data["preco"] = int(float(price_text))
                except ValueError:
                    pass
        
        return data
    
    # ================================================================
    # CRAWLING RECURSIVO
    # ================================================================
    
    async def crawl_recursive(
        self, 
        start_url: str, 
        max_pages: int = 10,
        max_depth: int = 2
    ) -> Dict[str, Any]:
        """
        Crawler recursivo que navega por várias páginas do mesmo domínio.
        """
        if not start_url.startswith("http"):
            start_url = "https://" + start_url
        
        parsed_start = urlparse(start_url)
        base_domain = parsed_start.netloc
        
        # Verificar se o site requer medidas especiais
        is_protected = any(site in base_domain.lower() for site in PROTECTED_SITES)
        
        from collections import deque
        queue = deque([(start_url, 0)])
        visited = set()
        properties = []
        errors = []
        
        logger.info(f"Iniciando crawl em {base_domain} (max_pages={max_pages}, protegido={'sim' if is_protected else 'não'})")
        
        while queue and len(visited) < max_pages:
            current_url, depth = queue.popleft()
            
            if current_url in visited:
                continue
            
            visited.add(current_url)
            
            try:
                import random
                await asyncio.sleep(random.uniform(0.5, 1.5))
                
                html_content = None
                
                # Usar curl_cffi para obter página
                html_content = await self._fetch_url(current_url)
                
                # Se falhou e é site protegido, tentar ScraperAPI
                if not html_content and is_protected and SCRAPERAPI_KEY:
                    html_content = await self._fetch_with_scraperapi(current_url)
                
                if not html_content:
                    errors.append({"url": current_url, "error": "Não foi possível obter página"})
                    continue
                
                soup = BeautifulSoup(html_content, 'html.parser')
                
                # Extrair dados usando o scrape_url (que já tem toda a lógica)
                property_data = await self.scrape_url(current_url)
                
                if property_data and not property_data.get("error"):
                    if property_data.get("titulo") or property_data.get("preco"):
                        property_data["crawl_depth"] = depth
                        properties.append(property_data)
                
                # Encontrar mais links se não atingimos profundidade máxima
                if depth < max_depth:
                    new_links = self._extract_property_links(soup, base_domain, current_url)
                    for link in new_links:
                        if link not in visited:
                            queue.append((link, depth + 1))
                        
            except Exception as e:
                errors.append({"url": current_url, "error": str(e)})
        
        return {
            "success": True,
            "domain": base_domain,
            "pages_visited": len(visited),
            "properties_found": len(properties),
            "properties": properties,
            "errors": errors if errors else None
        }
    
    def _extract_property_links(self, soup: BeautifulSoup, base_domain: str, current_url: str) -> List[str]:
        """Extrai links de imóveis de uma página."""
        links = []
        
        property_patterns = [
            r'/imovel/', r'/property/', r'/anuncio/', r'/listing/',
            r'/detalhe/', r'/ficha/', r'/ad/', r'/casa-', r'/apartamento-',
            r'/moradia-', r'/terreno-', r'/comprar/', r'/venda/'
        ]
        
        skip_patterns = [
            r'page=', r'/login', r'/registo', r'/contacto', r'/sobre',
            r'#', r'javascript:', r'mailto:', r'tel:'
        ]
        
        for a_tag in soup.find_all('a', href=True):
            href = a_tag.get('href', '')
            if not href:
                continue
            
            full_url = urljoin(current_url, href)
            parsed = urlparse(full_url)
            
            if base_domain not in parsed.netloc:
                continue
            
            if any(re.search(p, full_url.lower()) for p in skip_patterns):
                continue
            
            is_property = any(re.search(p, full_url.lower()) for p in property_patterns)
            has_id = re.search(r'/\d{4,}', full_url)
            
            if is_property or has_id:
                clean_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
                if clean_url not in links:
                    links.append(clean_url)
        
        return links[:50]
    
    # ================================================================
    # ANÁLISE DIRECTA COM IA
    # ================================================================
    
    async def analyze_with_ai(self, url: str, html_content: str) -> Dict[str, Any]:
        """
        Usa IA para analisar uma página.
        Tenta Gemini primeiro, depois OpenAI como fallback.
        """
        # Tentar Gemini primeiro
        result = await self._extract_with_gemini(html_content, url)
        
        # Se Gemini falhou (quota ou outro erro), tentar OpenAI
        if result and (result.get("_error") == "quota_exceeded" or result.get("_fallback")):
            logger.info("Gemini com quota excedida, tentando OpenAI como fallback...")
            openai_result = await self._extract_with_openai(html_content, url, "gpt-4o-mini")
            
            if openai_result and not openai_result.get("_error"):
                return openai_result
            
            # Se OpenAI também falhou, retornar erro original
            logger.warning("OpenAI também falhou, retornando erro original")
        
        return result



# Instância global
property_scraper = PropertyScraper()
scrape_property_url = property_scraper.scrape_url
crawl_properties = property_scraper.crawl_recursive
analyze_page_with_ai = property_scraper.analyze_with_ai

"""
Rotas para gestão de Leads de Imóveis
"""
import re
import uuid
import logging
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends

from database import db
from models.lead import (
    PropertyLead, PropertyLeadCreate, PropertyLeadUpdate,
    LeadStatus, LeadHistory, ConsultantInfo
)
# CORREÇÃO: Importar do novo scraper.py
from services.scraper import scrape_property_url
from services.auth import get_current_user, require_roles
from models.auth import UserRole
from utils.input_sanitization import (sanitize_string, sanitize_name, sanitize_email, sanitize_phone, sanitize_url, log_sanitization_rejection)

router = APIRouter(prefix="/leads", tags=["Property Leads"])
logger = logging.getLogger(__name__)


async def _log_system_error(
    error_type: str,
    message: str,
    details: dict = None,
    severity: str = "warning"
):
    """
    Regista um erro no sistema para o admin visualizar.
    
    Args:
        error_type: Tipo de erro (scraper_error, api_error, validation_error, etc.)
        message: Mensagem descritiva do erro
        details: Detalhes adicionais (dict)
        severity: Nível (info, warning, error, critical)
    """
    try:
        error_log = {
            "id": str(uuid.uuid4()),
            "type": error_type,
            "message": message,
            "details": details or {},
            "severity": severity,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "read": False,
            "resolved": False
        }
        await db.system_error_logs.insert_one(error_log)
    except Exception as e:
        logger.error(f"Falha ao registar erro no sistema: {e}")

@router.get("", response_model=List[PropertyLead])
async def list_leads(
    status: Optional[LeadStatus] = None,
    client_id: Optional[str] = None,
    consultor_id: Optional[str] = None,
    user: dict = Depends(get_current_user)
):
    """
    Listar todos os leads de imóveis com filtros opcionais.
    
    Regras de visibilidade:
    - Admin/Director: Vê todos os leads
    - Consultor/Mediador: Só vê os seus leads
    """
    query = {}
    user_role = user.get("role", "")
    user_id = user.get("id")
    
    # Filtrar por utilizador se não for admin/director
    if user_role not in ["admin", "diretor"]:
        query["created_by_id"] = user_id
    elif consultor_id:
        query["created_by_id"] = consultor_id
    
    if status:
        query["status"] = status.value
    if client_id:
        query["client_id"] = client_id
    
    # Busca leads e exclui o _id do mongo
    leads = await db.property_leads.find(query, {"_id": 0}).to_list(length=500)
    
    # Enriquecer com nome do cliente (se existir)
    for lead in leads:
        if lead.get("client_id"):
            process = await db.processes.find_one(
                {"id": lead["client_id"]},
                {"client_name": 1, "_id": 0}
            )
            if process:
                lead["client_name"] = process.get("client_name")
    
    return leads


@router.get("/by-status")
async def get_leads_by_status(
    consultor_id: Optional[str] = None,
    status_filter: Optional[str] = None,
    user: dict = Depends(get_current_user)
):
    """
    Obter leads agrupados por status (para o Kanban).
    Suporta filtros por consultor e por estado.
    
    Regras de visibilidade:
    - Admin/Director: Vê todos os leads (pode filtrar por consultor)
    - Consultor/Mediador: Só vê os seus leads (created_by_id = user_id)
    """
    query = {}
    user_role = user.get("role", "")
    user_id = user.get("id")
    
    # Filtrar por utilizador se não for admin/director
    if user_role not in ["admin", "diretor"]:
        # Consultor/Mediador só vê os seus leads
        query["created_by_id"] = user_id
    elif consultor_id:
        # Admin/Director pode filtrar por consultor específico
        query["created_by_id"] = consultor_id
    
    if status_filter and status_filter != "all":
        query["status"] = status_filter
    
    leads = await db.property_leads.find(query, {"_id": 0}).to_list(length=500)
    
    # Inicializar grupos
    grouped = {status.value: [] for status in LeadStatus}
    
    for lead in leads:
        # Enriquecer nome do cliente
        if lead.get("client_id"):
            process = await db.processes.find_one({"id": lead["client_id"]}, {"client_name": 1})
            if process:
                lead["client_name"] = process.get("client_name")
        
        # Calcular dias desde criação
        if lead.get("created_at"):
            try:
                from datetime import datetime, timezone
                created = datetime.fromisoformat(lead["created_at"].replace('Z', '+00:00'))
                days_old = (datetime.now(timezone.utc) - created).days
                lead["days_old"] = days_old
                lead["is_stale"] = days_old > 7 and lead.get("status") == LeadStatus.NOVO.value
            except:
                lead["days_old"] = 0
                lead["is_stale"] = False
        
        # Agrupar
        lead_status = lead.get("status", LeadStatus.NOVO.value)
        if lead_status in grouped:
            grouped[lead_status].append(lead)
        else:
            grouped[LeadStatus.NOVO.value].append(lead)
    
    return grouped


@router.get("/consultores")
async def get_consultores_for_filter(user: dict = Depends(get_current_user)):
    """
    Obter lista de consultores para os filtros do Kanban.
    Retorna utilizadores com role consultor, diretor ou admin.
    """
    consultores = await db.users.find(
        {"role": {"$in": ["consultor", "diretor", "admin", "administrativo"]}},
        {"_id": 0, "id": 1, "name": 1, "email": 1}
    ).to_list(length=100)
    
    return consultores


@router.post("/extract-url")
async def extract_url_data(
    payload: Dict[str, str], # Recebe JSON { "url": "..." }
    user: dict = Depends(get_current_user)
):
    """
    Extrair dados de um URL usando o Deep Scraper.
    
    Melhorias (Item 6):
    - Navegação automática ao link da agência se não encontrar telefone
    - Extracção de referência do anúncio
    - Mais campos de propriedade (certificado energético, ano construção, estado)
    """
    url = payload.get("url")
    if not url:
        # Tentar ler da query string se falhar no body (compatibilidade)
        raise HTTPException(status_code=400, detail="URL é obrigatório")
    
    # Sanitize URL before use
    url = sanitize_url(url)
    if not url:
        raise HTTPException(status_code=400, detail="URL inválido")
    
    logger.info(f"A iniciar Deep Scraping de: {url}")
    
    try:
        # Usar scraper híbrido
        raw_data = await scrape_property_url(url)
        
        # Verificar se houve erro
        if raw_data.get("error"):
            error_msg = raw_data.get("error", "Erro desconhecido")
            logger.warning(f"Scraper retornou erro: {error_msg}")
            
            # Mensagem mais amigável para o utilizador
            user_message = error_msg
            if "403" in error_msg or "bloqueado" in error_msg.lower():
                user_message = "O site Idealista está a bloquear a extração automática. Por favor, insira os dados manualmente ou tente novamente mais tarde."
            elif "timeout" in error_msg.lower():
                user_message = "O site demorou muito a responder. Por favor, tente novamente."
            
            # Log para admin
            await _log_system_error(
                error_type="scraper_error",
                message=f"Erro ao extrair dados de {url}: {error_msg}",
                details={"url": url, "error": error_msg}
            )
            return {
                "success": False,
                "message": user_message,
                "data": {"url": url}
            }
        
        # Mapear dados do scraper para o formato esperado pelo lead
        consultant_data = None
        if raw_data.get("agente_nome") or raw_data.get("agente_telefone") or raw_data.get("agente_email"):
            consultant_data = {
                "name": sanitize_name(raw_data.get("agente_nome", "")),
                "phone": sanitize_phone(raw_data.get("agente_telefone", "")),
                "email": sanitize_email(raw_data.get("agente_email", "")),
                "agency_name": sanitize_string(raw_data.get("agencia_nome", ""), max_length=200),
                "source_url": raw_data.get("url")
            }
        
        # Também verificar campos antigos do scraper (compatibilidade)
        if not consultant_data and raw_data.get("consultor"):
            raw_consultor = raw_data.get("consultor")
            consultant_data = {
                "name": sanitize_name(raw_consultor.get("nome", "")),
                "phone": sanitize_phone(raw_consultor.get("telefone", "")),
                "email": sanitize_email(raw_consultor.get("email", "")),
                "agency_name": sanitize_string(raw_consultor.get("agencia", ""), max_length=200),
                "source_url": raw_consultor.get("url_origem")
            }

        # === MELHORIAS Item 6 ===
        cleaned_data = {
            "url": url,
            "title": raw_data.get("titulo"),
            "price": raw_data.get("preco"),
            "location": raw_data.get("localizacao"),
            "typology": raw_data.get("tipologia"),
            "area": raw_data.get("area"),
            "bedrooms": raw_data.get("quartos"),
            "bathrooms": raw_data.get("casas_banho"),
            "description": raw_data.get("descricao"),
            "photo_url": raw_data.get("foto_principal"),
            "consultant": consultant_data,
            "source": raw_data.get("fonte", raw_data.get("_parser", "auto")),
            "_extracted_by": raw_data.get("_extracted_by"),
            # Novos campos (Item 6)
            "reference": raw_data.get("referencia") or raw_data.get("reference"),
            "energy_certificate": raw_data.get("certificado_energetico"),
            "year_built": raw_data.get("ano_construcao"),
            "condition": raw_data.get("estado"),
            "agency_link": raw_data.get("agency_link"),
            "_raw_fields": list(raw_data.keys())  # Para debug
        }
        
        # Verificar se extraiu dados úteis
        has_useful_data = cleaned_data.get("title") or cleaned_data.get("price") or cleaned_data.get("location")
        
        if not has_useful_data:
            logger.warning(f"Scraper não extraiu dados úteis de {url}")
            await _log_system_error(
                error_type="scraper_no_data",
                message=f"Não foi possível extrair dados de {url}",
                details={"url": url, "raw_keys": list(raw_data.keys()), "extracted_by": raw_data.get("_extracted_by")}
            )
        
        return {
            "success": has_useful_data,
            "data": cleaned_data,
            "message": "Dados extraídos com sucesso" if has_useful_data else "Poucos dados extraídos - preencha manualmente"
        }
        
    except Exception as e:
        logger.error(f"Erro no scraping: {e}")
        # Log para admin
        await _log_system_error(
            error_type="scraper_exception",
            message=f"Excepção ao extrair dados de {url}",
            details={"url": url, "error": str(e), "error_type": type(e).__name__}
        )
        return {
            "success": False, 
            "message": f"Não foi possível extrair dados automáticos: {str(e)}",
            "data": {"url": url}
        }


def _parse_plain_text(text: str, url: str = "") -> Dict[str, Any]:
    """
    Parser para texto puro (quando não é HTML estruturado).
    Extrai dados usando regex e padrões comuns.
    """
    data = {}
    text_lower = text.lower()
    
    # === Título ===
    # Procurar padrões como "Apartamento T2 à venda"
    title_patterns = [
        r'((?:apartamento|moradia|vivenda|casa|loja|terreno|armazém|escritório|garagem)\s+t?\d?\s*(?:à|a|para)?\s*(?:venda|arrendar|vender)?\s*(?:em|no|na)?\s*[^\n]{0,50})',
        r'(T\d[^\n]{0,80})',
    ]
    
    for pattern in title_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            data["titulo"] = match.group(1).strip()[:100]
            break
    
    # === Preço ===
    price_patterns = [
        r'([\d\s.]+)\s*€',
        r'€\s*([\d\s.]+)',
        r'([\d\s.]+)\s*euros?',
    ]
    
    for pattern in price_patterns:
        match = re.search(pattern, text)
        if match:
            price_str = match.group(1).replace(' ', '').replace('.', '')
            try:
                price = int(price_str)
                if 10000 < price < 50000000:  # Preço razoável para imóveis
                    data["preco"] = price
                    break
            except ValueError:
                continue
    
    # === Localização ===
    # Procurar padrões como "em Lisboa" ou "Queluz e Belas"
    location_patterns = [
        r'(?:em|localizado em|localização)[:\s]+([A-Z][^,\n]{5,40})',
        r'(?:Queluz|Lisboa|Porto|Sintra|Cascais|Oeiras|Almada|Seixal|Amadora|Loures|Setúbal|Braga|Coimbra|Faro)[^,\n]*',
    ]
    
    for pattern in location_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            data["localizacao"] = match.group(0).strip()[:100] if match.lastindex is None else match.group(1).strip()[:100]
            break
    
    # === Tipologia e Quartos ===
    tipo_match = re.search(r'\bT(\d)\b', text, re.IGNORECASE)
    if tipo_match:
        data["tipologia"] = f"T{tipo_match.group(1)}"
        data["quartos"] = int(tipo_match.group(1))
    
    # === Área ===
    area_match = re.search(r'(\d+)\s*m[²2]', text)
    if area_match:
        data["area"] = int(area_match.group(1))
    
    # === Referência ===
    ref_patterns = [
        r'[Rr]ef(?:erência)?[.:\s]*([A-Z0-9-]+)',
        r'([A-Z]{2,}\d{5,})',
    ]
    
    for pattern in ref_patterns:
        match = re.search(pattern, text)
        if match:
            data["referencia"] = match.group(1)
            break
    
    # === Link da agência ===
    # Procurar URLs no texto - encurtadores primeiro
    url_patterns = [
        r'(dez\.pt/[a-zA-Z0-9]+)',  # Encurtador dez.pt
        r'(bit\.ly/[a-zA-Z0-9]+)',  # bit.ly
        r'(tinyurl\.com/[a-zA-Z0-9]+)',
        r'(https?://[^\s<>"]+(?:easygest|remax|century21|era|zome|quatru|kw)[^\s<>"]*)',
    ]
    
    for pattern in url_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            link = match.group(1)
            if not link.startswith('http'):
                link = 'https://' + link
            data["agency_link"] = link
            break
    
    # === Consultor/Agência ===
    # Procurar nomes de agências conhecidas
    agency_patterns = [
        r'(EasyGest[^\n,]*)',
        r'(Easy\s+Lourinhã)',
        r'(Remax[^\n,]*)',
        r'(Century\s*21[^\n,]*)',
        r'(ERA[^\n,]*)',
        r'(Zome[^\n,]*)',
    ]
    
    for pattern in agency_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            data["agencia_nome"] = match.group(1).strip()
            break
    
    # === Descrição ===
    # Usar os primeiros parágrafos que não parecem ser metadados
    lines = [l.strip() for l in text.split('\n') if len(l.strip()) > 50]
    desc_lines = [l for l in lines if not any(x in l.lower() for x in ['€', 'preço', 'partilhar', 'guardar', 'excluir', 'calcular'])]
    if desc_lines:
        data["descricao"] = '\n'.join(desc_lines[:3])[:500]
    
    # === Telefone ===
    phone_patterns = [
        r'(?:\+351|00351)?[\s.-]?(9\d{8})',
        r'(?:\+351|00351)?[\s.-]?(2\d{8})',
    ]
    
    for pattern in phone_patterns:
        match = re.search(pattern, text)
        if match:
            data["agente_telefone"] = match.group(1)
            break
    
    return data


@router.post("/extract-html")
async def extract_html_data(
    payload: Dict[str, str],
    user: dict = Depends(get_current_user)
):
    """
    Extrai dados de HTML colado manualmente.
    
    Endpoint de fallback para quando o scraper automático falha
    (sites com protecção muito forte como Idealista).
    
    O utilizador pode:
    1. Abrir a página no browser
    2. Copiar o HTML (Ctrl+U ou Inspecionar Elemento)
    3. Colar aqui para extração dos dados
    """
    html_content = payload.get("html", "")
    source_url = payload.get("url") or payload.get("source_url", "")
    
    # Sanitize source URL if provided
    if source_url:
        source_url = sanitize_url(source_url)
    
    if not html_content:
        raise HTTPException(status_code=400, detail="HTML é obrigatório")
    
    if len(html_content) < 100:
        raise HTTPException(status_code=400, detail="HTML parece estar incompleto (muito curto)")
    
    logger.info(f"A extrair dados de HTML manual ({len(html_content)} chars)")
    
    try:
        from services.scraper import property_scraper
        from bs4 import BeautifulSoup
        
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Detectar fonte pelo HTML
        result = {}
        parser_used = "manual_html"
        
        html_lower = html_content.lower()
        url_lower = (source_url or "").lower()
        
        # Verificar se é HTML real ou texto puro
        is_html = '<html' in html_lower or '<body' in html_lower or '<div' in html_lower or '<span' in html_lower
        
        if not is_html:
            # É texto puro - usar parser de texto simples
            result = _parse_plain_text(html_content, source_url or "")
            parser_used = "text_manual"
        elif "idealista" in html_lower or "idealista" in url_lower:
            result = property_scraper._parse_idealista(soup, html_content)
            parser_used = "idealista_manual"
        elif "easygest" in html_lower or "easygest" in url_lower:
            result = property_scraper._parse_easygest(soup, html_content, source_url)
            parser_used = "easygest_manual"
        elif "supercasa" in html_lower or "supercasa" in url_lower:
            result = property_scraper._parse_supercasa(soup)
            parser_used = "supercasa_manual"
        elif "imovirtual" in html_lower or "imovirtual" in url_lower:
            result = property_scraper._parse_imovirtual(soup)
            parser_used = "imovirtual_manual"
        elif "remax" in html_lower or "remax" in url_lower:
            result = property_scraper._parse_remax(soup)
            parser_used = "remax_manual"
        elif "era.pt" in html_lower or "era.pt" in url_lower:
            result = property_scraper._parse_era(soup, html_content)
            parser_used = "era_manual"
        elif "kw.com" in html_lower or "kwportugal" in html_lower or "kw" in url_lower:
            result = property_scraper._parse_kw(soup)
            parser_used = "kw_manual"
        else:
            result = property_scraper._parse_generic(soup)
            parser_used = "generic_manual"
        
        # Tentar Gemini se dados insuficientes
        if not result.get("titulo") and not result.get("preco"):
            gemini_result = await property_scraper._extract_with_gemini(html_content, source_url or "manual_import")
            if gemini_result and not gemini_result.get("_error"):
                for key, value in gemini_result.items():
                    if not key.startswith("_") and value:
                        result[key] = value
                parser_used = "gemini_manual"
        
        # Extrair contactos do texto
        clean_text = property_scraper._clean_text(html_content)
        contacts = property_scraper._extract_contacts_from_text(clean_text)
        
        if contacts.get("telefones") and not result.get("agente_telefone"):
            phones = contacts["telefones"]
            mobile = next((p for p in phones if p.startswith("9")), None)
            result["agente_telefone"] = mobile or phones[0]
        
        if contacts.get("emails") and not result.get("agente_email"):
            valid_emails = [e for e in contacts["emails"] 
                          if not any(x in e.lower() for x in ["noreply", "info@", "geral@"])]
            if valid_emails:
                result["agente_email"] = valid_emails[0]
        
        # Formatar resposta - retornar dados de forma plana para o frontend
        cleaned_data = {
            "titulo": result.get("titulo"),
            "title": result.get("titulo"),  # Alias
            "preco": result.get("preco"),
            "price": result.get("preco"),  # Alias
            "localizacao": result.get("localizacao"),
            "location": result.get("localizacao"),  # Alias
            "tipologia": result.get("tipologia") or result.get("tipo"),
            "property_type": result.get("tipologia") or result.get("tipo"),  # Alias
            "area_util": result.get("area"),
            "area": result.get("area"),  # Alias
            "quartos": result.get("quartos"),
            "bedrooms": result.get("quartos"),  # Alias
            "casas_banho": result.get("casas_banho"),
            "bathrooms": result.get("casas_banho"),  # Alias
            "foto_principal": result.get("foto_principal"),
            "photo_url": result.get("foto_principal"),  # Alias
            "descricao": result.get("descricao"),
            "description": result.get("descricao"),  # Alias
            "agente_nome": result.get("agente_nome") or result.get("consultor"),
            "agent_name": result.get("agente_nome") or result.get("consultor"),  # Alias
            "agente_telefone": result.get("agente_telefone"),
            "agent_phone": result.get("agente_telefone"),  # Alias
            "agente_email": result.get("agente_email"),
            "agent_email": result.get("agente_email"),  # Alias
            "agencia_nome": result.get("agencia_nome") or result.get("agencia"),
            "agency_name": result.get("agencia_nome") or result.get("agencia"),  # Alias
            "agency_link": result.get("agency_link"),  # Link para site da agência
            "referencia": result.get("referencia"),
            "reference": result.get("referencia"),  # Alias
            "url": source_url,
            "_source_url": source_url,
            "_import_method": "manual_html",
            "_extracted_by": parser_used,
        }
        
        has_useful_data = cleaned_data.get("titulo") or cleaned_data.get("preco") or cleaned_data.get("localizacao")
        
        # Retornar dados directamente para o frontend usar
        return cleaned_data
        
    except Exception as e:
        logger.error(f"Erro na extração de HTML manual: {e}")
        return {
            "success": False,
            "message": f"Erro ao processar HTML: {str(e)}",
            "data": {}
        }


@router.post("/from-url")
async def create_lead_from_url(
    payload: Dict[str, str],
    user: dict = Depends(get_current_user)
):
    """
    Extrair dados de um URL e criar um lead automaticamente.
    Combina extração de dados e criação do lead num único passo.
    """
    url = payload.get("url")
    if not url:
        raise HTTPException(status_code=400, detail="URL é obrigatório")
    
    # Sanitize URL before use
    url = sanitize_url(url)
    if not url:
        raise HTTPException(status_code=400, detail="URL inválido")
    
    # Verificar duplicados
    existing = await db.property_leads.find_one({"url": url})
    if existing:
        return {
            "success": False,
            "message": "Já existe um lead com este URL",
            "lead": existing
        }
    
    logger.info(f"A criar lead de: {url}")
    
    try:
        # Extrair dados usando o scraper
        raw_data = await scrape_property_url(url)
        
        # Verificar se houve erro no scraper
        if raw_data.get("error"):
            await _log_system_error(
                error_type="scraper_error",
                message=f"Erro ao extrair dados de {url}: {raw_data.get('error')}",
                details={"url": url, "error": raw_data.get("error")},
                severity="warning"
            )
            return {
                "success": False,
                "message": f"Erro ao extrair: {raw_data.get('error')}. Pode criar o lead manualmente.",
                "data": {"url": url}
            }
        
        # Mapear dados do scraper para o formato do lead
        # O scraper retorna: titulo, preco, localizacao, tipologia, area, agente_nome, agente_telefone, agente_email, agencia_nome
        consultant_data = None
        if raw_data.get("agente_nome") or raw_data.get("agente_telefone") or raw_data.get("agente_email"):
            consultant_data = {
                "name": sanitize_name(raw_data.get("agente_nome", "")),
                "phone": sanitize_phone(raw_data.get("agente_telefone", "")),
                "email": sanitize_email(raw_data.get("agente_email", "")),
                "agency_name": sanitize_string(raw_data.get("agencia_nome", ""), max_length=200),
                "source_url": raw_data.get("url")
            }
        
        # Também verificar campos antigos do scraper (compatibilidade)
        if not consultant_data and raw_data.get("consultor"):
            raw_consultor = raw_data.get("consultor")
            consultant_data = {
                "name": sanitize_name(raw_consultor.get("nome", "")),
                "phone": sanitize_phone(raw_consultor.get("telefone", "")),
                "email": sanitize_email(raw_consultor.get("email", "")),
                "agency_name": sanitize_string(raw_consultor.get("agencia", ""), max_length=200),
                "source_url": raw_consultor.get("url_origem")
            }
        
        now = datetime.now(timezone.utc).isoformat()
        
        # Criar o lead com os dados extraídos (sanitized)
        lead_dict = {
            "id": str(uuid.uuid4()),
            "url": url,
            "title": sanitize_string(raw_data.get("titulo", ""), max_length=300),
            "price": raw_data.get("preco"),
            "location": sanitize_string(raw_data.get("localizacao", ""), max_length=200),
            "typology": raw_data.get("tipologia"),
            "area": raw_data.get("area"),
            "bedrooms": raw_data.get("quartos"),
            "bathrooms": raw_data.get("casas_banho"),
            "description": sanitize_string(raw_data.get("descricao", ""), max_length=2000),
            "photo_url": raw_data.get("foto_principal"),
            "consultant": consultant_data,
            "source": raw_data.get("fonte", raw_data.get("_parser", "auto")),
            "status": LeadStatus.NOVO.value,
            "created_at": now,
            "updated_at": now,
            "created_by": user.get("email"),
            "created_by_id": user.get("id"),
            "history": [{
                "timestamp": now,
                "event": "Lead criado automaticamente via URL",
                "user": user.get("email")
            }]
        }
        
        # Inserir na base de dados
        await db.property_leads.insert_one(lead_dict)
        
        # Verificar se extraiu dados úteis
        has_useful_data = lead_dict.get("title") or lead_dict.get("price") or lead_dict.get("location")
        
        if not has_useful_data:
            await _log_system_error(
                error_type="scraper_no_data",
                message=f"Lead criado mas com poucos dados de {url}",
                details={"url": url, "lead_id": lead_dict["id"]},
                severity="info"
            )
        
        # Remover _id do MongoDB antes de retornar
        lead_dict.pop("_id", None)
        
        return {
            "success": True,
            "message": "Lead criado com sucesso" if has_useful_data else "Lead criado mas com poucos dados extraídos - edite manualmente",
            "lead": lead_dict
        }
        
    except Exception as e:
        logger.error(f"Erro ao criar lead de URL: {e}")
        await _log_system_error(
            error_type="scraper_exception",
            message=f"Excepção ao criar lead de {url}",
            details={"url": url, "error": str(e), "error_type": type(e).__name__},
            severity="error"
        )
        raise HTTPException(status_code=500, detail=f"Erro ao criar lead: {str(e)}")


@router.post("", response_model=PropertyLead)
async def create_lead(
    lead_data: PropertyLeadCreate,
    user: dict = Depends(get_current_user)
):
    """Criar um novo lead na base de dados."""
    # Verificar duplicados
    existing = await db.property_leads.find_one({"url": lead_data.url})
    if existing:
        raise HTTPException(status_code=400, detail="Já existe um lead com este URL")
    
    now = datetime.now(timezone.utc).isoformat()
    
    lead_dict = lead_data.model_dump()
    lead_dict["id"] = str(uuid.uuid4())
    lead_dict["status"] = LeadStatus.NOVO.value
    lead_dict["created_at"] = now
    lead_dict["updated_at"] = now
    lead_dict["created_by"] = user.get("email")
    lead_dict["created_by_id"] = user.get("id")  # Para filtros por consultor
    lead_dict["history"] = [{
        "timestamp": now,
        "event": "Lead criado",
        "user": user.get("email")
    }]
    
    # Sanitize user-provided string fields before DB insert
    if lead_dict.get("title"):
        lead_dict["title"] = sanitize_string(lead_dict["title"], max_length=300)
    if lead_dict.get("description"):
        lead_dict["description"] = sanitize_string(lead_dict["description"], max_length=2000)
    if lead_dict.get("location"):
        lead_dict["location"] = sanitize_string(lead_dict["location"], max_length=200)
    if lead_dict.get("notes"):
        lead_dict["notes"] = sanitize_string(lead_dict["notes"], max_length=1000)
    if lead_dict.get("url"):
        lead_dict["url"] = sanitize_url(lead_dict["url"])
    # Sanitize consultant fields if present
    consultant = lead_dict.get("consultant")
    if consultant:
        if consultant.get("name"):
            consultant["name"] = sanitize_name(consultant["name"])
        if consultant.get("phone"):
            consultant["phone"] = sanitize_phone(consultant["phone"])
        if consultant.get("email"):
            consultant["email"] = sanitize_email(consultant["email"])
    
    await db.property_leads.insert_one(lead_dict)
    return lead_dict

@router.patch("/{lead_id}", response_model=PropertyLead)
async def update_lead(
    lead_id: str,
    update_data: PropertyLeadUpdate,
    user: dict = Depends(get_current_user)
):
    """Atualizar dados de um lead."""
    lead = await db.property_leads.find_one({"id": lead_id})
    if not lead:
        raise HTTPException(status_code=404, detail="Lead não encontrado")
    
    now = datetime.now(timezone.utc).isoformat()
    update_dict = update_data.model_dump(exclude_none=True)
    update_dict["updated_at"] = now
    
    # Registar mudança de estado no histórico
    if "status" in update_dict and update_dict["status"] != lead.get("status"):
        # Garantir que o histórico existe
        history = lead.get("history", [])
        history.append({
            "timestamp": now,
            "event": f"Status alterado para {update_dict['status']}",
            "user": user.get("email")
        })
        update_dict["history"] = history

    await db.property_leads.update_one({"id": lead_id}, {"$set": update_dict})
    
    # Retornar objeto atualizado (sem _id)
    return await db.property_leads.find_one({"id": lead_id}, {"_id": 0})

@router.patch("/{lead_id}/status")
async def update_lead_status(
    lead_id: str,
    status: str, 
    user: dict = Depends(get_current_user)
):
    """Endpoint rápido para mudar estado (Drag & Drop)."""
    lead = await db.property_leads.find_one({"id": lead_id})
    if not lead:
        raise HTTPException(status_code=404, detail="Lead não encontrado")
    
    # Validar se o status existe no Enum
    # status vem como query param string, validar contra os valores do enum
    valid_statuses = [s.value for s in LeadStatus]
    if status not in valid_statuses:
         raise HTTPException(status_code=400, detail="Estado inválido")

    now = datetime.now(timezone.utc).isoformat()
    
    # Preparar entrada de histórico
    history_entry = {
        "timestamp": now,
        "event": f"Status alterado para {status}",
        "user": user.get("email")
    }

    await db.property_leads.update_one(
        {"id": lead_id},
        {
            "$set": {"status": status, "updated_at": now},
            "$push": {"history": history_entry}
        }
    )
    return {"success": True, "status": status}


@router.post("/{lead_id}/refresh")
async def refresh_lead_price(
    lead_id: str,
    user: dict = Depends(get_current_user)
):
    """
    Verificar se o preço do lead mudou visitando o URL novamente.
    Se mudou, actualiza a DB e adiciona entrada ao histórico.
    """
    # Buscar lead
    lead = await db.property_leads.find_one({"id": lead_id}, {"_id": 0})
    if not lead:
        raise HTTPException(status_code=404, detail="Lead não encontrado")
    
    url = lead.get("url")
    if not url:
        raise HTTPException(status_code=400, detail="Lead não tem URL associado")
    
    old_price = lead.get("price")
    
    try:
        # Fazer scraping novamente
        scraped_data = await scrape_property_url(url)
        
        if scraped_data.get("error"):
            return {
                "success": False,
                "message": f"Erro ao verificar: {scraped_data.get('error')}",
                "old_price": old_price,
                "new_price": None,
                "price_changed": False
            }
        
        new_price = scraped_data.get("preco")
        now = datetime.now(timezone.utc).isoformat()
        
        # Verificar se o preço mudou
        price_changed = new_price is not None and new_price != old_price
        
        update_fields = {
            "updated_at": now,
            "last_checked_at": now
        }
        
        history_entry = {
            "timestamp": now,
            "event": "Preço verificado",
            "user": user.get("email")
        }
        
        if price_changed:
            update_fields["price"] = new_price
            history_entry["event"] = f"Preço alterado de {old_price or 'N/D'}€ para {new_price}€"
            logger.info(f"Lead {lead_id}: Preço alterado de {old_price} para {new_price}")
        
        # Também actualizar outros campos se disponíveis
        if scraped_data.get("titulo"):
            update_fields["title"] = scraped_data.get("titulo")
        if scraped_data.get("localizacao"):
            update_fields["location"] = scraped_data.get("localizacao")
        
        await db.property_leads.update_one(
            {"id": lead_id},
            {
                "$set": update_fields,
                "$push": {"history": history_entry}
            }
        )
        
        return {
            "success": True,
            "message": "Preço alterado" if price_changed else "Preço sem alteração",
            "old_price": old_price,
            "new_price": new_price,
            "price_changed": price_changed
        }
        
    except Exception as e:
        logger.error(f"Erro ao verificar preço do lead {lead_id}: {str(e)}")
        return {
            "success": False,
            "message": f"Erro ao verificar preço: {str(e)}",
            "old_price": old_price,
            "new_price": None,
            "price_changed": False
        }


@router.delete("/{lead_id}")
async def delete_lead(lead_id: str, user: dict = Depends(get_current_user)):
    """Eliminar lead."""
    result = await db.property_leads.delete_one({"id": lead_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Lead não encontrado")
    return {"success": True}

@router.post("/{lead_id}/associate-client")
async def associate_client(
    lead_id: str,
    client_id: str,
    user: dict = Depends(get_current_user)
):
    """Associar um lead a um cliente/processo."""
    # Verificar se lead existe
    lead = await db.property_leads.find_one({"id": lead_id})
    if not lead:
        raise HTTPException(status_code=404, detail="Lead não encontrado")
    
    # Verificar se cliente existe
    process = await db.processes.find_one({"id": client_id})
    if not process:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    
    now = datetime.now(timezone.utc).isoformat()
    
    # Actualizar lead
    await db.property_leads.update_one(
        {"id": lead_id},
        {
            "$set": {"client_id": client_id, "updated_at": now},
            "$push": {
                "history": {
                    "timestamp": now,
                    "event": f"Associado ao cliente {process.get('client_name')}",
                    "user": user.get("email")
                }
            }
        }
    )
    
    return {
        "success": True,
        "message": f"Lead associado a {process.get('client_name')}"
    }
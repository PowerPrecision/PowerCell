"""URL/HTML extraction + create-from-url lead endpoints.

Extraído de `routes/leads.py`.
"""
from __future__ import annotations

import uuid
import logging
from typing import Dict
from datetime import datetime, timezone

from fastapi import HTTPException

from database import db
from models.lead import LeadStatus
from services.scraper import scrape_property_url
from utils.input_sanitization import (
    sanitize_string, sanitize_name, sanitize_email, sanitize_phone, sanitize_url,
)
from services.lead_helpers import _log_system_error, _parse_plain_text

logger = logging.getLogger(__name__)


async def run_extract_url_data(
    payload: Dict[str, str],
    user: dict,
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


async def run_extract_html_data(
    payload: Dict[str, str],
    user: dict,
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


async def run_create_lead_from_url(
    payload: Dict[str, str],
    user: dict,
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
    existing = await db.property_leads.find_one({"url": url}, {"_id": 0})
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

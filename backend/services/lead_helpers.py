"""Shared helpers for property lead routes.

Extraído de `routes/leads.py`.
"""
from __future__ import annotations

import re
import uuid
import logging
from typing import Dict, Any
from datetime import datetime, timezone

from database import db

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

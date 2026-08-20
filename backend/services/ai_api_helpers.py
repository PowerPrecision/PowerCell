"""Shared mapping helpers for AI document analysis API.

Extraído de `routes/ai.py`. Prefer `ai_api_*` — do **not** overwrite
`ai_document.py` / `ai_document_analyzer.py` / `ai_page_analyzer.py`.
"""
from __future__ import annotations

from typing import Any, Dict

from services.ai_document import (
    map_cc_to_personal_data,
    map_recibo_to_financial_data,
    map_irs_to_financial_data,
)

VALID_DOCUMENT_TYPES = [
    "cc",
    "recibo_vencimento",
    "irs",
    "cpcv",
    "simulacao_credito",
    "caderneta_predial",
    "outro",
]

# Aliases enviados pelo AdminDashboard / selects legado → tipos canónicos.
DOCUMENT_TYPE_ALIASES = {
    "cartao_cidadao": "cc",
    "cartão_cidadão": "cc",
    "passaporte": "outro",
    "contrato_trabalho": "outro",
    "certidao_permanente": "outro",
    "extrato_bancario": "outro",
    "mapa_responsabilidades": "outro",
}


def normalize_document_type(document_type: str | None) -> str:
    """Normaliza document_type do frontend para um valor em VALID_DOCUMENT_TYPES."""
    raw = str(document_type or "").strip().lower()
    mapped = DOCUMENT_TYPE_ALIASES.get(raw, raw)
    if mapped in VALID_DOCUMENT_TYPES:
        return mapped
    return "outro" if raw else ""


def map_extracted_data(document_type: str, extracted_data: Dict[str, Any]) -> Dict[str, Any]:
    """Map AI extracted fields onto process form sections."""
    mapped_data: Dict[str, Any] = {}

    if document_type == "cc":
        mapped_data["personal_data"] = map_cc_to_personal_data(extracted_data)
        mapped_data["name"] = extracted_data.get("nome_completo")
    elif document_type == "recibo_vencimento":
        mapped_data["financial_data"] = map_recibo_to_financial_data(extracted_data)
    elif document_type == "irs":
        mapped_data["financial_data"] = map_irs_to_financial_data(extracted_data)
    elif document_type == "cpcv":
        mapped_data["compradores"] = extracted_data.get("compradores", [])
        mapped_data["vendedor"] = extracted_data.get("vendedor", {})
        mapped_data["imovel"] = extracted_data.get("imovel", {})
        mapped_data["valores"] = extracted_data.get("valores", {})
        mapped_data["datas"] = extracted_data.get("datas", {})
        mapped_data["condicoes"] = extracted_data.get("condicoes", {})
        mapped_data["mediador"] = extracted_data.get("mediador", {})
    elif document_type == "caderneta_predial":
        mapped_data["real_estate_data"] = extracted_data

    return mapped_data

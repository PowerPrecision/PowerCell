"""
Match de documentos IA → titular 1 vs titular 2 no processo.

O 2.º titular fica definido no processo na criação (`second_client_id` /
`titular2_data`). A IA compara identidade extraída (NIF, nome, CC) com
os dois clientes; só pede escolha ao user se o match for ambíguo.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any, Optional


def _norm_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip().lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^a-z0-9\s]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _norm_nif(value: Any) -> str:
    digits = re.sub(r"\D", "", str(value or ""))
    return digits


def _norm_doc_id(value: Any) -> str:
    return re.sub(r"[^a-zA-Z0-9]", "", str(value or "")).upper()


def build_titular_identity_snapshot(
    *,
    label: str,
    client_id: Optional[str],
    name: Optional[str],
    personal: Optional[dict],
    titular2_data: Optional[dict] = None,
) -> dict:
    """Normaliza identidade de um titular (cliente ou snapshot titular2)."""
    personal = personal or {}
    t2 = titular2_data or {}
    nif = (
        personal.get("nif")
        or t2.get("nif")
        or t2.get("NIF")
    )
    doc_id = (
        personal.get("documento_id")
        or personal.get("cc_number")
        or t2.get("documento_id")
        or t2.get("cc_number")
    )
    full_name = (
        name
        or personal.get("nome")
        or personal.get("nome_completo")
        or t2.get("name")
        or t2.get("nome")
    )
    return {
        "label": label,  # "titular1" | "titular2"
        "client_id": client_id,
        "name": full_name or "",
        "name_norm": _norm_text(full_name),
        "nif_norm": _norm_nif(nif),
        "doc_id_norm": _norm_doc_id(doc_id),
    }


def score_extracted_against_titular(extracted: dict, titular: dict) -> int:
    """
    Score simples de identidade.
    +3 NIF exacto, +2 CC exacto, +2 nome forte, +1 nome parcial.
    """
    score = 0
    ext_nif = _norm_nif(
        extracted.get("nif")
        or extracted.get("NIF")
        or extracted.get("numero_contribuinte")
    )
    ext_doc = _norm_doc_id(
        extracted.get("documento_id")
        or extracted.get("cc_number")
        or extracted.get("numero_documento")
    )
    ext_name = _norm_text(
        extracted.get("client_name")
        or extracted.get("nome")
        or extracted.get("nome_completo")
        or extracted.get("name")
    )

    if ext_nif and titular.get("nif_norm") and ext_nif == titular["nif_norm"]:
        score += 3
    if ext_doc and titular.get("doc_id_norm") and ext_doc == titular["doc_id_norm"]:
        score += 2
    if ext_name and titular.get("name_norm"):
        if ext_name == titular["name_norm"]:
            score += 2
        elif ext_name in titular["name_norm"] or titular["name_norm"] in ext_name:
            score += 1
        else:
            # overlap de tokens significativos
            a = set(t for t in ext_name.split() if len(t) > 2)
            b = set(t for t in titular["name_norm"].split() if len(t) > 2)
            if a and b and len(a & b) >= 2:
                score += 1
    return score


def resolve_titular_match(
    extracted: dict,
    titular1: dict,
    titular2: Optional[dict] = None,
    *,
    min_confident_score: int = 2,
) -> dict:
    """
    Decide titular1 / titular2 / ambiguous / titular1 (default se só 1).

    Returns:
      {
        match: "titular1"|"titular2"|"ambiguous"|"unknown",
        confidence: "high"|"low"|"none",
        score_titular1, score_titular2,
        needs_user_choice: bool,
        suggested_client_id, suggested_label
      }
    """
    s1 = score_extracted_against_titular(extracted, titular1)
    s2 = score_extracted_against_titular(extracted, titular2) if titular2 else 0

    result = {
        "score_titular1": s1,
        "score_titular2": s2,
        "needs_user_choice": False,
        "match": "unknown",
        "confidence": "none",
        "suggested_client_id": None,
        "suggested_label": None,
    }

    if not titular2:
        result["match"] = "titular1"
        result["confidence"] = "high" if s1 >= min_confident_score else "low"
        result["suggested_client_id"] = titular1.get("client_id")
        result["suggested_label"] = titular1.get("name") or "Titular 1"
        result["needs_user_choice"] = False
        return result

    # Ambíguo: ambos com score semelhante e >= limiar
    if s1 >= min_confident_score and s2 >= min_confident_score and abs(s1 - s2) <= 1:
        result["match"] = "ambiguous"
        result["confidence"] = "low"
        result["needs_user_choice"] = True
        return result

    if s1 >= min_confident_score and s1 > s2:
        result["match"] = "titular1"
        result["confidence"] = "high"
        result["suggested_client_id"] = titular1.get("client_id")
        result["suggested_label"] = titular1.get("name") or "Titular 1"
        return result

    if s2 >= min_confident_score and s2 > s1:
        result["match"] = "titular2"
        result["confidence"] = "high"
        result["suggested_client_id"] = titular2.get("client_id")
        result["suggested_label"] = titular2.get("name") or "Titular 2"
        return result

    # Sem identidade útil → pedir escolha se há 2 titulares
    if s1 == 0 and s2 == 0:
        result["match"] = "ambiguous"
        result["confidence"] = "none"
        result["needs_user_choice"] = True
        return result

    # Um ligeiramente à frente mas fraco → ainda pedir confirmação
    if s1 != s2:
        winner = titular1 if s1 > s2 else titular2
        result["match"] = "titular1" if s1 > s2 else "titular2"
        result["confidence"] = "low"
        result["suggested_client_id"] = winner.get("client_id")
        result["suggested_label"] = winner.get("name") or result["match"]
        result["needs_user_choice"] = True
        return result

    result["match"] = "ambiguous"
    result["needs_user_choice"] = True
    return result

"""
Helpers para POST /processes/{id}/resolve-conflict (sugestões IA).

Extraído de `routes/processes.py` — localizar sugestão, sanitizar valor
e construir campos `$set`.
"""
from __future__ import annotations

from typing import Any, Optional, Tuple

from fastapi import HTTPException

from utils.input_sanitization import (
    sanitize_email,
    sanitize_name,
    sanitize_nif,
    sanitize_phone,
    sanitize_string,
    log_sanitization_rejection,
)

PERSONAL_FIELDS = {
    "nif", "documento_id", "naturalidade", "nacionalidade", "morada_fiscal",
    "birth_date", "data_nascimento", "estado_civil", "data_validade_cc",
    "sexo", "altura", "nome_pai", "nome_mae",
}
FINANCIAL_FIELDS = {
    "salario_bruto", "salario_liquido", "rendimento_anual",
    "acesso_portal_financas", "capital_proprio",
}


def find_ai_suggestion(
    ai_suggestions: list,
    field: str,
    suggestion_id: Optional[str] = None,
) -> Tuple[dict, int]:
    """
    Localiza sugestão por field (+ suggestion_id opcional).

    Returns:
        (suggestion, index)

    Raises:
        HTTPException(404)
    """
    for i, s in enumerate(ai_suggestions):
        if s.get("field") != field:
            continue
        if suggestion_id and s.get("id") != suggestion_id:
            continue
        return s, i
    raise HTTPException(
        status_code=404,
        detail=f"Nenhuma sugestão encontrada para o campo '{field}'",
    )


def sanitize_ai_suggested_value(field: str, suggested_value: Any) -> Any:
    """Sanitiza valor sugerido pela IA conforme o tipo de campo."""
    if suggested_value is None or not isinstance(suggested_value, str):
        return suggested_value

    if field in ["nif", "documento_id"]:
        sanitized_val = sanitize_nif(suggested_value)
        if sanitized_val is None and suggested_value:
            log_sanitization_rejection(field, str(suggested_value), "NIF inválido")
        return sanitized_val
    if field in ["email", "client_email"]:
        return sanitize_email(suggested_value)
    if field in ["telefone", "phone", "client_phone"]:
        return sanitize_phone(suggested_value)
    if field in ["nome_completo", "nome", "name", "nome_pai", "nome_mae"]:
        return sanitize_name(suggested_value)
    if field in ["morada_fiscal"]:
        return sanitize_string(suggested_value, max_length=500)
    return sanitize_string(suggested_value, max_length=500)


def build_ai_accept_update_fields(
    field: str,
    field_path: str,
    suggested_value: Any,
) -> dict[str, Any]:
    """Monta chaves `$set` ao aceitar sugestão IA."""
    if "." in field_path:
        section, actual_field = field_path.split(".", 1)
        return {f"{section}.{actual_field}": suggested_value}
    if field in PERSONAL_FIELDS:
        return {f"personal_data.{field}": suggested_value}
    if field in FINANCIAL_FIELDS:
        return {f"financial_data.{field}": suggested_value}
    return {field: suggested_value}


def apply_ai_conflict_choice(
    *,
    ai_suggestions: list,
    field: str,
    choice: str,
    suggestion_id: Optional[str],
    now: str,
) -> tuple[dict, dict, Any]:
    """
    Resolve conflito: devolve (update_data parcial sem CDC, suggestion, resolved_value).

    `resolved_value` é o valor sanitizado aceite (choice=ai) ou None (choice=current).
    `choice` deve ser 'ai' | 'current'. Caller regista histórico e injecta CDC.
    """
    suggestion, suggestion_index = find_ai_suggestion(
        ai_suggestions, field, suggestion_id,
    )
    update_data: dict[str, Any] = {"updated_at": now}
    resolved_value: Any = None

    if choice == "ai":
        resolved_value = sanitize_ai_suggested_value(
            field, suggestion.get("suggested"),
        )
        field_path = suggestion.get("field_path", field)
        update_data.update(
            build_ai_accept_update_fields(field, field_path, resolved_value),
        )

    remaining = list(ai_suggestions)
    remaining.pop(suggestion_index)
    update_data["ai_suggestions"] = remaining
    return update_data, suggestion, resolved_value

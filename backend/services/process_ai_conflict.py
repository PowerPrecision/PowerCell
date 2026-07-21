"""
Helpers para resolve-conflict / confirm-data (sugestões IA).

Extraído de `routes/processes.py` — localizar sugestão, sanitizar valor,
construir campos `$set` e orquestrar persistência + histórico.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional, Tuple

from fastapi import HTTPException

from database import db
from services.audit_cdc import inject_cdc_context
from utils.input_sanitization import (
    sanitize_email,
    sanitize_name,
    sanitize_nif,
    sanitize_phone,
    sanitize_string,
    log_sanitization_rejection,
)

logger = logging.getLogger(__name__)

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


def parse_resolve_conflict_body(data: Optional[dict]) -> tuple[str, str, Optional[str]]:
    """Valida body do resolve-conflict. Devolve (field, choice, suggestion_id)."""
    data = data or {}
    field = data.get("field")
    choice = data.get("choice")
    suggestion_id = data.get("suggestion_id")
    if not field or choice not in ("ai", "current"):
        raise HTTPException(
            status_code=400,
            detail="field e choice ('ai' ou 'current') são obrigatórios",
        )
    return field, choice, suggestion_id


def assert_can_edit_process_or_403(
    user: dict,
    process: dict,
    process_id: str,
    *,
    action: str,
    can_edit_fn,
) -> None:
    """IDOR guard partilhado por resolve-conflict e confirm-data."""
    can_edit, reason = can_edit_fn(user, process)
    if can_edit:
        return
    logger.warning(
        "IDOR attempt: User %s (%s) tried to %s on process %s: %s",
        user.get("id"),
        user.get("role"),
        action,
        process_id,
        reason,
    )
    raise HTTPException(
        status_code=403,
        detail=f"Não tem permissões para alterar este processo. {reason}",
    )


def build_confirm_data_update(confirmed: bool, user: dict, now: str) -> dict[str, Any]:
    return {
        "is_data_confirmed": confirmed,
        "data_confirmed_at": now if confirmed else None,
        "data_confirmed_by": user["id"] if confirmed else None,
        "updated_at": now,
    }


def assert_no_pending_ai_conflicts(ai_suggestions: list, *, confirmed: bool) -> None:
    if confirmed and len(ai_suggestions) > 0:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Existem {len(ai_suggestions)} conflitos pendentes. "
                "Resolva-os antes de confirmar os dados."
            ),
        )


def build_resolve_conflict_response(field: str, choice: str, remaining: list) -> dict:
    return {
        "success": True,
        "message": (
            f"Conflito resolvido: "
            f"{'valor IA aceite' if choice == 'ai' else 'valor actual mantido'}"
        ),
        "field": field,
        "remaining_conflicts": len(remaining),
    }


def build_confirm_data_response(confirmed: bool) -> dict:
    return {
        "success": True,
        "message": (
            f"Dados do cliente "
            f"{'confirmados e bloqueados' if confirmed else 'desbloqueados'}"
        ),
        "is_data_confirmed": confirmed,
    }


async def resolve_ai_data_conflict(
    process_id: str,
    data: dict,
    user: dict,
    *,
    can_edit_fn,
    log_history_fn,
) -> dict:
    """Orquestra POST /resolve-conflict."""
    field, choice, suggestion_id = parse_resolve_conflict_body(data)

    process = await db.processes.find_one({"id": process_id}, {"_id": 0})
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")

    assert_can_edit_process_or_403(
        user, process, process_id,
        action="resolve conflict",
        can_edit_fn=can_edit_fn,
    )

    now = datetime.now(timezone.utc).isoformat()
    update_data, suggestion, resolved_value = apply_ai_conflict_choice(
        ai_suggestions=process.get("ai_suggestions", []),
        field=field,
        choice=choice,
        suggestion_id=suggestion_id,
        now=now,
    )

    if choice == "ai":
        await log_history_fn(
            process_id, user,
            f"Aceitou sugestão IA para '{field}'",
            field, suggestion.get("current"), resolved_value,
        )
    else:
        await log_history_fn(
            process_id, user,
            f"Manteve valor actual para '{field}'",
            field, suggestion.get("suggested"), suggestion.get("current"),
        )

    inject_cdc_context(update_data, user)
    await db.processes.update_one({"id": process_id}, {"$set": update_data})

    return build_resolve_conflict_response(
        field, choice, update_data.get("ai_suggestions", []),
    )


async def confirm_process_client_data(
    process_id: str,
    data: dict,
    user: dict,
    *,
    can_edit_fn,
    log_history_fn,
) -> dict:
    """Orquestra POST /confirm-data."""
    confirmed = (data or {}).get("confirmed", True)

    process = await db.processes.find_one({"id": process_id}, {"_id": 0})
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")

    assert_can_edit_process_or_403(
        user, process, process_id,
        action="confirm data",
        can_edit_fn=can_edit_fn,
    )

    assert_no_pending_ai_conflicts(
        process.get("ai_suggestions", []),
        confirmed=bool(confirmed),
    )

    now = datetime.now(timezone.utc).isoformat()
    confirm_update_data = build_confirm_data_update(bool(confirmed), user, now)
    inject_cdc_context(confirm_update_data, user)
    await db.processes.update_one(
        {"id": process_id},
        {"$set": confirm_update_data},
    )

    action = "confirmou" if confirmed else "desbloqueou"
    await log_history_fn(
        process_id, user,
        f"{action} os dados do cliente",
        "is_data_confirmed", not confirmed, confirmed,
    )

    return build_confirm_data_response(bool(confirmed))

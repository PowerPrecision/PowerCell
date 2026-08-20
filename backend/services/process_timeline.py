"""PACOTE DO.1 — Timeline compacta do processo (Resumo).

Reutiliza a coleção `history` (já escrita por `services/history.log_history`
em criação, mudanças de fase e edições) e acrescenta um evento sintético de
criação quando o histórico ainda não o contém.

Não substitui o audit_trail de compliance (`audit_trail_service.py`).
"""
from __future__ import annotations

from typing import Any

from services.history import build_history_description, classify_history_event


def _is_created_action(action: str | None) -> bool:
    text = (action or "").strip().lower()
    return text.startswith("criou processo")


def _kind_for_history_item(item: dict) -> str:
    event_type = classify_history_event(item)
    if event_type == "created" or _is_created_action(item.get("action")):
        return "created"
    if event_type == "status_change":
        return "status"
    if event_type == "comment":
        return "comment"
    return "event"


def _description_for_history_item(item: dict) -> str | None:
    description = build_history_description(item)
    action = str(item.get("action") or "").strip()
    if not description or description == action:
        field = item.get("field")
        old_value = item.get("old_value")
        new_value = item.get("new_value")
        if not field and old_value is None and new_value is None:
            return None
    return description or None


def build_summary_timeline(
    process: dict | None,
    history: list[dict] | None,
    *,
    limit: int = 40,
) -> list[dict[str, Any]]:
    """Normaliza histórico + criação do processo para a Timeline do Resumo."""
    process = process or {}
    history = history or []
    events: list[dict[str, Any]] = []

    created_at = process.get("created_at")
    has_created = any(_is_created_action(h.get("action")) for h in history)
    if created_at and not has_created:
        events.append({
            "id": f"created-{process.get('id') or 'process'}",
            "kind": "created",
            "title": "Processo criado",
            "description": None,
            "actor": None,
            "at": created_at,
            "field": None,
            "old_value": None,
            "new_value": None,
        })

    for item in history:
        events.append({
            "id": item.get("id"),
            "kind": _kind_for_history_item(item),
            "title": item.get("action") or "Atualização",
            "description": _description_for_history_item(item),
            "actor": item.get("user_name"),
            "at": item.get("created_at"),
            "field": item.get("field"),
            "old_value": item.get("old_value"),
            "new_value": item.get("new_value"),
        })

    events.sort(key=lambda e: e.get("at") or "", reverse=True)
    return events[: max(int(limit), 1)]


async def run_get_process_timeline(
    process_id: str,
    user: dict,
    *,
    can_view_fn,
    limit: int = 40,
) -> dict:
    """Orquestra GET /processes/{id}/timeline (PACOTE DO.1)."""
    from fastapi import HTTPException

    from database import db

    process = await db.processes.find_one({"id": process_id}, {"_id": 0})
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")
    if not can_view_fn(user, process):
        raise HTTPException(status_code=403, detail="Acesso negado")

    history = await db.history.find(
        {"process_id": process_id}, {"_id": 0}
    ).sort("created_at", -1).to_list(1000)

    events = build_summary_timeline(process, history, limit=limit)
    return {"events": events, "total": len(events)}

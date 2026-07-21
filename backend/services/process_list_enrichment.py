"""
Enriquecimento batch partilhado entre listagens de processos.

Unifica a lógica duplicada em get_processes / get_processes_paginated /
get_kanban_board (flags de portal, últimas notas, nomes de assignees).
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from database import db
from services.process_my_clients import (
    fetch_unread_messages_map,
    fetch_new_documents_map,
    fetch_latest_activity_notes_map,
)

logger = logging.getLogger(__name__)

PRIORITY_MAP = {
    "alta": 3, "high": 3,
    "media": 2, "medium": 2,
    "baixa": 1, "low": 1,
}


def get_priority_weight(process: dict) -> int:
    """Peso de prioridade (suporta prioridade PT + priority EN)."""
    return PRIORITY_MAP.get(process.get("prioridade") or process.get("priority"), 0)


def collect_assignee_user_ids(processes: list[dict]) -> set[str]:
    """IDs únicos de consultor/mediador/indexação/parceiro nos processos."""
    user_ids: set[str] = set()
    for p in processes:
        if p.get("assigned_consultor_id"):
            user_ids.add(p["assigned_consultor_id"])
        if p.get("assigned_mediador_id"):
            user_ids.add(p["assigned_mediador_id"])
        if p.get("assigned_indexacao_id"):
            user_ids.add(p["assigned_indexacao_id"])
        if p.get("assigned_parceiro_id"):
            user_ids.add(p["assigned_parceiro_id"])
        for cid in (p.get("assigned_consultor_ids") or []):
            user_ids.add(cid)
        for mid in (p.get("assigned_mediador_ids") or []):
            user_ids.add(mid)
    return user_ids


def apply_assignee_names(processes: list[dict], user_map: dict[str, str]) -> None:
    """
    Preenche consultor_name / mediador_name / indexacao_name / parceiro_name.

    `user_map` é id → name (string).
    """
    for p in processes:
        if not p.get("consultor_name"):
            c_ids = list(set(
                ([p["assigned_consultor_id"]] if p.get("assigned_consultor_id") else []) +
                (p.get("assigned_consultor_ids") or [])
            ))
            names = [user_map[cid] for cid in c_ids if user_map.get(cid)]
            if names:
                p["consultor_name"] = ", ".join(names)

        if not p.get("mediador_name"):
            m_ids = list(set(
                ([p["assigned_mediador_id"]] if p.get("assigned_mediador_id") else []) +
                (p.get("assigned_mediador_ids") or [])
            ))
            names = [user_map[mid] for mid in m_ids if user_map.get(mid)]
            if names:
                p["mediador_name"] = ", ".join(names)

        if not p.get("indexacao_name") and p.get("assigned_indexacao_id"):
            p["indexacao_name"] = user_map.get(p["assigned_indexacao_id"], "")

        if not p.get("parceiro_name") and p.get("assigned_parceiro_id"):
            p["parceiro_name"] = user_map.get(p["assigned_parceiro_id"], "")


async def load_assignee_name_map(processes: list[dict]) -> dict[str, str]:
    """Resolve nomes dos assignees presentes na lista."""
    user_ids = collect_assignee_user_ids(processes)
    if not user_ids:
        return {}
    user_docs = await db.users.find(
        {"id": {"$in": list(user_ids)}},
        {"_id": 0, "id": 1, "name": 1},
    ).to_list(len(user_ids))
    return {u["id"]: u.get("name", "") for u in user_docs}


async def enrich_processes_assignee_names(processes: list[dict]) -> None:
    """Carrega mapa de nomes e aplica aos processos (mutação in-place)."""
    if not processes:
        return
    user_map = await load_assignee_name_map(processes)
    if user_map:
        apply_assignee_names(processes, user_map)


async def enrich_processes_portal_flags(processes: list[dict]) -> None:
    """Injeta has_unread_messages / has_new_documents (PACOTE BI)."""
    if not processes:
        return
    process_ids = [p["id"] for p in processes if p.get("id")]
    unread_map = await fetch_unread_messages_map(db, process_ids)
    new_docs_map = await fetch_new_documents_map(db, process_ids)
    for p in processes:
        pid = p.get("id")
        p["has_unread_messages"] = unread_map.get(pid, False)
        p["has_new_documents"] = new_docs_map.get(pid, False)


async def enrich_processes_latest_notes(processes: list[dict]) -> None:
    """
    Injeta latest_note + latest_activity_preview (PACOTE BT/CZ — listagens).
    """
    if not processes:
        return
    process_ids = [p["id"] for p in processes if p.get("id")]
    notes_map = await fetch_latest_activity_notes_map(db, process_ids)
    for p in processes:
        note = notes_map.get(p.get("id"), {})
        p["latest_note"] = note.get("latest_activity_note")
        p["latest_note_at"] = note.get("latest_activity_note_at")
        p["latest_note_by"] = note.get("latest_activity_note_by")
        p["latest_activity_preview"] = p.get("latest_note")


async def enrich_processes_latest_activity(processes: list[dict]) -> None:
    """
    Injeta latest_activity (objeto) para o Kanban / ProcessDetailsModal (PACOTE DA).
    """
    if not processes:
        return
    process_ids = [p["id"] for p in processes if p.get("id")]
    try:
        rows = await db.activities.aggregate([
            {"$match": {
                "process_id": {"$in": process_ids},
                "comment": {"$exists": True, "$ne": ""},
            }},
            {"$sort": {"created_at": -1}},
            {"$group": {
                "_id": "$process_id",
                "comment": {"$first": "$comment"},
                "user_name": {"$first": "$user_name"},
                "user_role": {"$first": "$user_role"},
                "created_at": {"$first": "$created_at"},
            }},
        ]).to_list(1000)
        acts_map = {r["_id"]: r for r in rows}
        for p in processes:
            act = acts_map.get(p.get("id"))
            if act:
                p["latest_activity"] = {k: v for k, v in act.items() if k != "_id"}
            else:
                p["latest_activity"] = None
    except Exception as e:
        logger.warning(f"[ENRICH] Erro no batch enrichment latest_activity: {e}")
        for p in processes:
            p.setdefault("latest_activity", None)


def sort_process_list(
    processes: list[dict],
    *,
    sort_field: Optional[str] = None,
    sort_order: str = "asc",
    status_order: Optional[dict[str, int]] = None,
) -> None:
    """
    Ordenação da listagem tabular (get_processes).

    Com sort_field explícito: campo + prioridade estável.
    Sem sort_field: prioridade → fase workflow → nome.
    """
    status_order = status_order or {}

    if sort_field and sort_field in (
        "client_name", "status", "created_at", "updated_at",
        "priority", "property_value", "property_location", "contacto",
    ):
        reverse = sort_order.lower() == "desc"

        if sort_field == "priority":
            try:
                processes.sort(key=get_priority_weight, reverse=reverse)
            except TypeError:
                processes.sort(key=lambda p: str(get_priority_weight(p)), reverse=reverse)
            return

        def _primary_key(p: dict) -> Any:
            if sort_field == "client_name":
                return (p.get("client_name") or "").lower()
            if sort_field == "status":
                return (p.get("status") or "").lower()
            if sort_field in ("created_at", "updated_at"):
                return p.get(sort_field) or ""
            if sort_field == "contacto":
                return (p.get("client_email") or p.get("client_phone") or "").lower()
            return p.get(sort_field) or ""

        try:
            processes.sort(key=_primary_key, reverse=reverse)
        except TypeError:
            processes.sort(key=lambda p: str(_primary_key(p)), reverse=reverse)
        processes.sort(key=lambda p: -get_priority_weight(p))
        return

    processes.sort(key=lambda p: (
        -get_priority_weight(p),
        status_order.get(p.get("status"), 999),
        (p.get("client_name") or "").lower(),
    ))


def compute_page_slice(total: int, page: int, size: int) -> tuple[int, int, int]:
    """Returns (skip, pages, size_safe)."""
    size_safe = size if size > 0 else 0
    skip = (page - 1) * size if size_safe else 0
    pages = (total + size_safe - 1) // size_safe if size_safe else 0
    return skip, pages, size_safe


def slice_page(items: list, page: int, size: int) -> tuple[list, int, int]:
    """Paginação Python-side: (page_items, total, pages)."""
    total = len(items)
    skip, pages, size_safe = compute_page_slice(total, page, size)
    if not size_safe:
        return [], total, 0
    return items[skip:skip + size_safe], total, pages


def build_process_list_response(
    *,
    items: list,
    total: int,
    page: int,
    size: int,
    pages: int,
    view_mode: Optional[str],
) -> dict:
    return {
        "items": items,
        "total": total,
        "page": page,
        "size": size,
        "pages": pages,
        "view_mode": view_mode,
    }


def build_process_cursor_list_response(
    *,
    result: dict,
    view_mode: Optional[str],
) -> dict:
    return {
        "processes": result["items"],
        "next_cursor": result["next_cursor"],
        "has_more": result["has_more"],
        "limit": result["limit"],
        "view_mode": view_mode,
    }


async def load_workflow_status_order() -> dict[str, int]:
    """name → índice de ordem no workflow."""
    from database import db
    statuses = await db.workflow_statuses.find(
        {}, {"_id": 0},
    ).sort("order", 1).to_list(100)
    return {s["name"]: idx for idx, s in enumerate(statuses)}


async def load_workflow_status_map() -> dict[str, dict]:
    """name → doc workflow_status completo."""
    from database import db
    statuses = await db.workflow_statuses.find(
        {}, {"_id": 0},
    ).sort("order", 1).to_list(100)
    return {s["name"]: s for s in statuses}
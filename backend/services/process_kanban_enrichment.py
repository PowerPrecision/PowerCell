"""
Helpers de enriquecimento/ordenação do Kanban.

Extraído de `routes/processes.py` (`get_kanban_board`) para isolar
ordenação por prioridade, agrupamento por status e cards enriquecidos.
"""
from __future__ import annotations

from typing import Any, Optional

PRIORITY_WEIGHT = {"alta": 3, "media": 2, "baixa": 1}


def group_processes_by_status(processes: list[dict]) -> dict[str, list[dict]]:
    """Agrupa processos por status (lookup O(1) por coluna)."""
    processes_by_status: dict[str, list[dict]] = {}
    for p in processes:
        s = p.get("status", "")
        processes_by_status.setdefault(s, []).append(p)
    return processes_by_status


def sort_kanban_column_processes(processes: list[dict]) -> list[dict]:
    """
    Ordena in-place: 1º prioridade (Alta>Média>Baixa), 2º updated_at DESC.

    Two-step stable sort: first by updated_at DESC, then by priority DESC.
    """
    processes.sort(key=lambda p: p.get("updated_at") or "", reverse=True)
    processes.sort(
        key=lambda p: -PRIORITY_WEIGHT.get(p.get("prioridade") or p.get("priority"), 0)
    )
    return processes


def sort_all_kanban_columns(processes_by_status: dict[str, list[dict]]) -> None:
    """Aplica sort_kanban_column_processes a cada coluna."""
    for status_key in processes_by_status:
        sort_kanban_column_processes(processes_by_status[status_key])


def enrich_kanban_process_card(
    process: dict,
    user_map: dict[str, dict],
    current_user_id: str,
) -> dict:
    """
    Card Kanban com nomes de assignees + flags is_assigned_to_me.

    `user_map` é id → {id, name, role}.
    """
    p = process
    consultor_ids = p.get("assigned_consultor_ids") or []
    if not isinstance(consultor_ids, list):
        consultor_ids = []
    primary_consultor = p.get("assigned_consultor_id")
    if primary_consultor and primary_consultor not in consultor_ids:
        consultor_ids = list(consultor_ids) + [primary_consultor]
    consultor_names = [
        user_map.get(cid, {}).get("name", "")
        for cid in consultor_ids
        if cid and isinstance(cid, str) and user_map.get(cid)
    ]

    mediador_ids = p.get("assigned_mediador_ids") or []
    if not isinstance(mediador_ids, list):
        mediador_ids = []
    primary_mediador = p.get("assigned_mediador_id")
    if primary_mediador and primary_mediador not in mediador_ids:
        mediador_ids = list(mediador_ids) + [primary_mediador]
    mediador_names = [
        user_map.get(mid, {}).get("name", "")
        for mid in mediador_ids
        if mid and isinstance(mid, str) and user_map.get(mid)
    ]

    idx_id = p.get("assigned_indexacao_id")
    indexacao_name = p.get("indexacao_name") or ""
    if not indexacao_name and idx_id and isinstance(idx_id, str):
        indexacao_name = user_map.get(idx_id, {}).get("name", "")

    par_id = p.get("assigned_parceiro_id")
    parceiro_name = p.get("parceiro_name") or ""
    if not parceiro_name and par_id and isinstance(par_id, str):
        parceiro_name = user_map.get(par_id, {}).get("name", "")

    assigned_consultor_ids_list = p.get("assigned_consultor_ids") or []
    if not isinstance(assigned_consultor_ids_list, list):
        assigned_consultor_ids_list = []
    assigned_mediador_ids_list = p.get("assigned_mediador_ids") or []
    if not isinstance(assigned_mediador_ids_list, list):
        assigned_mediador_ids_list = []

    is_my_consultor = (
        p.get("assigned_consultor_id") == current_user_id
        or current_user_id in assigned_consultor_ids_list
    )
    is_my_mediador = (
        p.get("assigned_mediador_id") == current_user_id
        or current_user_id in assigned_mediador_ids_list
    )

    return {
        **p,
        "consultor_name": ", ".join(consultor_names) if consultor_names else (p.get("consultor_name") or ""),
        "mediador_name": ", ".join(mediador_names) if mediador_names else (p.get("mediador_name") or ""),
        "indexacao_name": indexacao_name,
        "parceiro_name": parceiro_name,
        "is_assigned_to_me": is_my_consultor or is_my_mediador,
        "my_role_in_process": (
            "consultor" if is_my_consultor
            else ("intermediario" if is_my_mediador else None)
        ),
    }


def build_kanban_columns(
    statuses: list[dict],
    processes_by_status: dict[str, list[dict]],
    user_map: dict[str, dict],
    current_user_id: str,
) -> list[dict]:
    """Monta a lista de colunas do Kanban com cards enriquecidos."""
    kanban: list[dict] = []
    for status in statuses:
        if not isinstance(status, dict):
            continue
        status_name = status.get("name") or ""
        status_processes = processes_by_status.get(status_name, [])
        enriched_processes = []
        for p in status_processes:
            if not isinstance(p, dict):
                continue
            enriched_processes.append(
                enrich_kanban_process_card(p, user_map, current_user_id)
            )
        kanban.append({
            "id": status.get("id") or status_name,
            "name": status_name,
            "label": status.get("label") or status_name.replace("_", " ").title(),
            "color": status.get("color") or "#6B7280",
            "order": status.get("order", 0),
            "processes": enriched_processes,
            "count": len(enriched_processes),
        })
    return kanban

"""
Helpers de enriquecimento/ordenação do Kanban.

Extraído de `routes/processes.py` (`get_kanban_board`) para isolar
ordenação por prioridade e agrupamento por status.
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

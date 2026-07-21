"""
Helpers puros para mark-indexed / salto dinâmico de workflow.

Extraído de `routes/processes.py` (`mark_process_indexed`) para testes
unitários isolados da progressão de estado e limpeza do indexador.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


def compute_next_workflow_status(
    current_status: Optional[str],
    status_pipeline: list[str],
) -> Optional[str]:
    """
    Calcula o próximo estado na pipeline de workflow_statuses.

    - Se current está na pipeline e não é o último → seguinte
    - Se current está na pipeline e é o último → None
    - Se current NÃO está na pipeline → 1º estado (fallback) ou None se vazia
    """
    if current_status in status_pipeline:
        current_idx = status_pipeline.index(current_status)
        if current_idx < len(status_pipeline) - 1:
            next_status = status_pipeline[current_idx + 1]
            logger.info(
                f"[INDEXACAO-DYNAMIC] Salto dinâmico: '{current_status}' (pos {current_idx}) "
                f"→ '{next_status}' (pos {current_idx + 1})"
            )
            return next_status
        logger.info(
            f"[INDEXACAO-DYNAMIC] Processo já está no último estado da pipeline "
            f"('{current_status}'). Sem salto automático."
        )
        return None

    if status_pipeline:
        next_status = status_pipeline[0]
        logger.warning(
            f"[INDEXACAO-DYNAMIC] Status actual '{current_status}' não encontrado "
            f"na pipeline. Fallback para o 1º estado: '{next_status}'"
        )
        return next_status
    return None


def build_indexacao_update_set(
    user: dict,
    now: str,
    next_status: Optional[str] = None,
) -> dict[str, Any]:
    """Campos $set ao marcar indexação concluída (+ opcional salto de status)."""
    update_set: dict[str, Any] = {
        "is_indexed": True,
        "indexed_at": now,
        "indexed_by": user.get("id"),
        "indexed_by_name": user.get("name", ""),
        "assigned_indexacao_id": None,
        "indexacao_name": None,
        "updated_at": now,
        "is_data_confirmed": True,
        "data_confirmed_at": now,
        "data_confirmed_by": user.get("id"),
        "data_confirmed_by_name": user.get("name", ""),
    }
    if next_status:
        update_set["status"] = next_status
    return update_set


def collect_assigned_user_ids(process: dict) -> list[str]:
    """IDs únicos de consultores/mediadores/indexação atribuídos ao processo."""
    return list(set(filter(None, (
        (process.get("assigned_consultor_ids") or []) +
        ([process["assigned_consultor_id"]] if process.get("assigned_consultor_id") else []) +
        (process.get("assigned_mediador_ids") or []) +
        ([process["assigned_mediador_id"]] if process.get("assigned_mediador_id") else []) +
        ([process["assigned_indexacao_id"]] if process.get("assigned_indexacao_id") else [])
    ))))

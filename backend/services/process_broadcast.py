"""
Broadcast WebSocket de deltas de processo (Kanban / realtime).

Extraído de `routes/processes.py`.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from services.websocket_manager import manager, create_ws_message

logger = logging.getLogger(__name__)


def build_process_delta_payload(
    *,
    process_id: str,
    process_number: Any = None,
    client_name: Optional[str] = None,
    status: Optional[str] = None,
    old_status: Optional[str] = None,
    assigned_consultor_ids: Optional[list] = None,
    assigned_mediador_ids: Optional[list] = None,
    consultor_names: Optional[list] = None,
    mediador_names: Optional[list] = None,
    priority: Optional[str] = None,
    prioridade: Optional[str] = None,
    process_type: Optional[str] = None,
    updated_at: Optional[str] = None,
) -> dict[str, Any]:
    """Monta o payload leve (só campos non-None)."""
    delta: dict[str, Any] = {"process_id": process_id}
    optional = {
        "process_number": process_number,
        "client_name": client_name,
        "status": status,
        "old_status": old_status,
        "assigned_consultor_ids": assigned_consultor_ids,
        "assigned_mediador_ids": assigned_mediador_ids,
        "consultor_names": consultor_names,
        "mediador_names": mediador_names,
        "priority": priority,
        "prioridade": prioridade,
        "process_type": process_type,
        "updated_at": updated_at,
    }
    for key, value in optional.items():
        if value is not None:
            delta[key] = value
    return delta


async def broadcast_process_delta(
    event_type: str,
    process_id: str,
    process_number: int = None,
    client_name: str = None,
    status: str = None,
    old_status: str = None,
    assigned_consultor_ids: list = None,
    assigned_mediador_ids: list = None,
    consultor_names: list = None,
    mediador_names: list = None,
    priority: str = None,
    prioridade: str = None,
    process_type: str = None,
    updated_at: str = None,
) -> None:
    """Broadcast a lightweight process delta to all connected WebSocket clients."""
    try:
        delta = build_process_delta_payload(
            process_id=process_id,
            process_number=process_number,
            client_name=client_name,
            status=status,
            old_status=old_status,
            assigned_consultor_ids=assigned_consultor_ids,
            assigned_mediador_ids=assigned_mediador_ids,
            consultor_names=consultor_names,
            mediador_names=mediador_names,
            priority=priority,
            prioridade=prioridade,
            process_type=process_type,
            updated_at=updated_at,
        )
        message = create_ws_message(event_type, delta)
        await manager.broadcast(message)
        logger.debug(f"Broadcast {event_type} for process {process_id}")
    except Exception as e:
        logger.error(f"Error broadcasting process delta: {e}")

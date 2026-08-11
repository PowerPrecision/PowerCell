"""WebSocket status endpoint handler.

Extraído de `routes/websocket.py`.
Do **not** overwrite services/websocket_manager.py.
"""
from __future__ import annotations

from services.websocket_manager import manager


async def run_websocket_status():
    """Retorna o estado atual das ligações WebSocket ativas."""
    return {
        "total_connections": manager.get_total_connections(),
        "connected_users": len(manager.get_connected_users()),
        "user_ids": manager.get_connected_users()
    }

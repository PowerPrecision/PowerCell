"""
====================================================================
ROTAS WEBSOCKET — thin FastAPI stubs
====================================================================
Logic in services/websocket_api_*.py.
Do **not** overwrite services/websocket_manager.py.
====================================================================
"""
from fastapi import APIRouter, WebSocket, Query

from services.websocket_api_notifications import run_websocket_notifications
from services.websocket_api_status import run_websocket_status

router = APIRouter(tags=["WebSocket"])


@router.websocket("/ws/notifications")
async def websocket_notifications(
    websocket: WebSocket,
    token: str = Query(...)
):
    """Endpoint WebSocket para receber notificações em tempo real."""
    await run_websocket_notifications(websocket, token)


@router.get("/ws/status")
async def websocket_status():
    """Retorna o estado atual das ligações WebSocket ativas."""
    return await run_websocket_status()

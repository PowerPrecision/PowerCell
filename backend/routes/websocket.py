"""
====================================================================
ROTAS WEBSOCKET — thin FastAPI stubs
====================================================================
Logic in services/websocket_api_*.py.
Do **not** overwrite services/websocket_manager.py.
====================================================================
"""
from fastapi import APIRouter, Depends, WebSocket, Query

from services.auth import require_admin
from services.websocket_api_notifications import run_websocket_notifications
from services.websocket_api_portal import run_portal_websocket
from services.websocket_api_status import run_websocket_status

router = APIRouter(tags=["WebSocket"])


@router.websocket("/ws/notifications")
async def websocket_notifications(
    websocket: WebSocket,
    token: str = Query(...)
):
    """Endpoint WebSocket para receber notificações em tempo real."""
    await run_websocket_notifications(websocket, token)


@router.websocket("/ws/portal")
async def websocket_portal(
    websocket: WebSocket,
    token: str = Query(...)
):
    """WebSocket do CLIENTE do Portal — endpoint SEPARADO do de staff.

    Separado de propósito: o laço do staff trata seis tipos de mensagem e meter
    um cliente externo lá dentro faria a segurança depender de nenhum ramo novo
    se esquecer da guarda. Aqui só existe `ping`.
    """
    await run_portal_websocket(websocket, token)


@router.get("/ws/status")
async def websocket_status(user: dict = Depends(require_admin())):
    """Retorna o estado atual das ligações WebSocket ativas (apenas admin/CEO)."""
    return await run_websocket_status()

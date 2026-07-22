"""
====================================================================
ROTAS PUSH NOTIFICATIONS — thin FastAPI stubs
====================================================================
Logic in services/push_notifications_api_*.py.
Do **not** overwrite services/push_notifications.py (VAPID send engine).
====================================================================
"""
from fastapi import APIRouter, Depends

from services.auth import get_current_user
from services.push_notifications_api_subscribe import (
    PushSubscriptionRequest,
    run_subscribe_push,
    run_unsubscribe_push,
    run_unsubscribe_all_push,
)
from services.push_notifications_api_status import run_get_push_status

router = APIRouter(prefix="/notifications/push", tags=["Push Notifications"])


@router.post("/subscribe")
async def subscribe_push(
    subscription: PushSubscriptionRequest,
    current_user: dict = Depends(get_current_user)
):
    """Registar subscrição push para o utilizador atual."""
    return await run_subscribe_push(subscription, current_user)


@router.post("/unsubscribe")
async def unsubscribe_push(
    subscription: PushSubscriptionRequest,
    current_user: dict = Depends(get_current_user)
):
    """Cancelar subscrição push."""
    return await run_unsubscribe_push(subscription, current_user)


@router.delete("/unsubscribe-all")
async def unsubscribe_all_push(
    current_user: dict = Depends(get_current_user)
):
    """Cancelar todas as subscrições push do utilizador atual."""
    return await run_unsubscribe_all_push(current_user)


@router.get("/status")
async def get_push_status(
    current_user: dict = Depends(get_current_user)
):
    """Verificar estado das subscrições push do utilizador."""
    return await run_get_push_status(current_user)

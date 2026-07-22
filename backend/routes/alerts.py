"""
====================================================================
ROTAS DE ALERTAS E NOTIFICAÇÕES — thin FastAPI stubs
====================================================================
Logic in services/alerts_api_*.py.
Do **not** overwrite services/alerts.py (core alert engine).
====================================================================
"""
from fastapi import APIRouter, Depends

from services.auth import get_current_user
from services.alerts_api_process import (
    run_get_alerts_for_process,
    run_check_age_eligibility,
    run_get_pre_approval_countdown,
    run_get_document_alerts,
    run_check_property_docs,
    run_create_deed_reminder,
)
from services.alerts_api_notifications import (
    run_get_notifications,
    run_mark_notification_read,
)

router = APIRouter(prefix="/alerts", tags=["Alerts"])


@router.get("/process/{process_id}")
async def get_alerts_for_process(
    process_id: str,
    user: dict = Depends(get_current_user)
):
    """Obter todos os alertas para um processo específico."""
    return await run_get_alerts_for_process(process_id)


@router.get("/age-check/{process_id}")
async def check_age_eligibility(
    process_id: str,
    user: dict = Depends(get_current_user)
):
    """Verificar se o cliente é elegível para apoio ao estado (< 35 anos)."""
    return await run_check_age_eligibility(process_id)


@router.get("/pre-approval/{process_id}")
async def get_pre_approval_countdown(
    process_id: str,
    user: dict = Depends(get_current_user)
):
    """Obter o countdown de 90 dias da pré-aprovação."""
    return await run_get_pre_approval_countdown(process_id)


@router.get("/documents/{process_id}")
async def get_document_alerts(
    process_id: str,
    user: dict = Depends(get_current_user)
):
    """Obter alertas de documentos a expirar (15 dias)."""
    return await run_get_document_alerts(process_id)


@router.get("/property-docs/{process_id}")
async def check_property_docs(
    process_id: str,
    user: dict = Depends(get_current_user)
):
    """Verificar se os documentos do imóvel estão completos."""
    return await run_check_property_docs(process_id)


@router.post("/deed-reminder/{process_id}")
async def create_deed_reminder_endpoint(
    process_id: str,
    deed_date: str,
    user: dict = Depends(get_current_user)
):
    """Criar um lembrete de escritura 15 dias antes da data."""
    return await run_create_deed_reminder(process_id, deed_date, user)


@router.get("/notifications")
async def get_notifications(
    unread_only: bool = False,
    user: dict = Depends(get_current_user)
):
    """Obter notificações do sistema."""
    return await run_get_notifications(unread_only, user)


@router.put("/notifications/{notification_id}/read")
async def mark_notification_read(
    notification_id: str,
    user: dict = Depends(get_current_user)
):
    """Marcar notificação como lida."""
    return await run_mark_notification_read(notification_id)

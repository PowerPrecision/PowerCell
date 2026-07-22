"""
====================================================================
ROTAS: Portal Settings — thin FastAPI stubs
====================================================================
Logic in services/portal_settings_api_*.py.
Helpers re-exported for back-compat (portal_status imports).
====================================================================
"""
from fastapi import APIRouter, Depends

from services.auth import require_admin
from services.portal_settings_api_helpers import (  # noqa: F401
    PortalSettingsUpdate,
    DEFAULT_WELCOME_TEMPLATE,
    render_welcome_message,
    get_portal_settings_doc,
    _get_portal_settings_doc,
)
from services.portal_settings_api_crud import (
    run_get_portal_settings,
    run_update_portal_settings,
    run_reset_welcome_template,
)
from services.portal_settings_api_preview import run_preview_welcome_message

router = APIRouter(
    prefix="/admin/portal-settings",
    tags=["Portal Settings"],
    dependencies=[Depends(require_admin())]
)


@router.get("")
async def get_portal_settings():
    """Obtém as definições do portal do cliente."""
    return await run_get_portal_settings()


@router.put("")
async def update_portal_settings(payload: PortalSettingsUpdate):
    """Atualiza as definições do portal do cliente."""
    return await run_update_portal_settings(payload)


@router.post("/reset-welcome")
async def reset_welcome_template():
    """Repõe o template da mensagem de boas-vindas para o padrão."""
    return await run_reset_welcome_template()


@router.post("/preview")
async def preview_welcome_message(payload: PortalSettingsUpdate):
    """Pré-visualiza a mensagem de boas-vindas com dados de exemplo."""
    return await run_preview_welcome_message(payload)

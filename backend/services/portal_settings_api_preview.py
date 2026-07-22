"""Portal settings preview handler.

Extraído de `routes/portal_settings.py`.
"""
from __future__ import annotations

from services.portal_settings_api_helpers import (
    DEFAULT_WELCOME_TEMPLATE,
    PortalSettingsUpdate,
    render_welcome_message,
)


async def run_preview_welcome_message(payload: PortalSettingsUpdate):
    template = payload.welcome_message_template or DEFAULT_WELCOME_TEMPLATE
    preview = render_welcome_message(
        template=template,
        client_name="João Silva",
        consultor_name="Ana Rodrigues",
        empresa_name="Power Precision",
    )
    return {
        "template": template,
        "preview": preview,
    }

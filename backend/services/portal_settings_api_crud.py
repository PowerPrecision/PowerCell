"""Portal settings get / update / reset handlers.

Extraído de `routes/portal_settings.py`.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import HTTPException

from database import db
from services.portal_settings_api_helpers import (
    DEFAULT_WELCOME_TEMPLATE,
    PortalSettingsUpdate,
    get_portal_settings_doc,
)

logger = logging.getLogger(__name__)


async def run_get_portal_settings():
    doc = await get_portal_settings_doc()
    return {
        "welcome_message_template": doc.get("welcome_message_template", DEFAULT_WELCOME_TEMPLATE),
        "available_variables": [
            {"key": "{{cliente}}", "description": "Nome do cliente"},
            {"key": "{{consultor}}", "description": "Nome do consultor atribuído"},
            {"key": "{{empresa}}", "description": "Nome da empresa"},
        ],
        "updated_at": doc.get("updated_at"),
    }


async def run_update_portal_settings(payload: PortalSettingsUpdate):
    update_data = {"updated_at": datetime.now(timezone.utc).isoformat()}

    if payload.welcome_message_template is not None:
        if not payload.welcome_message_template.strip():
            raise HTTPException(
                status_code=400,
                detail="O template da mensagem de boas-vindas não pode estar vazio."
            )
        update_data["welcome_message_template"] = payload.welcome_message_template

    result = await db.portal_settings.update_one(
        {"_id": "main"},
        {"$set": update_data},
        upsert=True,
    )

    logger.info(
        f"[PortalSettings] Config atualizada — "
        f"matched={result.matched_count}, modified={result.modified_count}"
    )

    return {
        "success": True,
        "message": "Definições do portal atualizadas",
    }


async def run_reset_welcome_template():
    await db.portal_settings.update_one(
        {"_id": "main"},
        {
            "$set": {
                "welcome_message_template": DEFAULT_WELCOME_TEMPLATE,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        },
        upsert=True,
    )

    logger.info("[PortalSettings] Template de boas-vindas reposto para o padrão")

    return {
        "success": True,
        "message": "Template reposto para o padrão",
        "welcome_message_template": DEFAULT_WELCOME_TEMPLATE,
    }

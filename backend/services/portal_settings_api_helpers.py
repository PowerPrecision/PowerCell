"""Portal settings helpers and models.

Extraído de `routes/portal_settings.py`.
Use portal_settings_api_* (careful vs portal_* services).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field

from database import db

logger = logging.getLogger(__name__)


class PortalSettingsUpdate(BaseModel):
    welcome_message_template: Optional[str] = Field(
        None,
        description="Template da mensagem de boas-vindas. Variáveis: {{cliente}}, {{consultor}}, {{empresa}}",
        examples=[
            "Olá, {{cliente}}!\n\nChamo-me {{consultor}}, da equipa da {{empresa}}..."
        ]
    )


DEFAULT_WELCOME_TEMPLATE = (
    "Olá, {{cliente}}!\n\n"
    "Chamo-me {{consultor}}, faço parte da equipa que vai acompanhar todo o seu processo de Crédito "
    "e dou-lhe as boas-vindas. O nosso serviço não tem qualquer custo para si.\n\n"
    "O seu processo vai percorrer 2 fases:\n\n"
    "1ª Fase — Reunião de documentação:\n"
    "• Cartão de Cidadão / Passaporte\n"
    "• IRS e Nota de Liquidação\n"
    "• Recibos de Vencimento\n"
    "• Extratos Bancários\n"
    "• Mapa de Responsabilidades (Banco de Portugal)\n"
    "• Comprovativo de IBAN\n\n"
    "2ª Fase — Análise e submissão bancária:\n"
    "A sua documentação será analisada e submetida às entidades bancárias para aprovação.\n\n"
    "Pode contactar-me por aqui a qualquer momento.\n\n"
    "Obrigado por escolher a {{empresa}}."
)


async def get_portal_settings_doc() -> dict:
    """Obtém o documento de portal_settings (cria com defaults se não existir)."""
    doc = await db.portal_settings.find_one({"_id": "main"})
    if not doc:
        doc = {
            "_id": "main",
            "welcome_message_template": DEFAULT_WELCOME_TEMPLATE,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.portal_settings.insert_one(doc)
        logger.info("[PortalSettings] Documento criado com template padrão")
    return doc


# Back-compat alias used by portal_status / routes.portal_settings re-exports
_get_portal_settings_doc = get_portal_settings_doc


def render_welcome_message(
    template: str,
    client_name: str = "Cliente",
    consultor_name: str = "a sua equipa",
    empresa_name: str = "Power Precision",
) -> str:
    """Faz a substituição das variáveis no template da mensagem."""
    result = template
    result = result.replace("{{cliente}}", client_name)
    result = result.replace("{{consultor}}", consultor_name)
    result = result.replace("{{empresa}}", empresa_name)
    return result

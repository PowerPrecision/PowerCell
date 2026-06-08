"""
====================================================================
ROTAS: Portal Settings — Configuração do Portal do Cliente
====================================================================
Permite ao CEO/Admin personalizar a mensagem de boas-vindas e outras
definições do portal do cliente.

A config é guardada na collection `portal_settings` (1 documento global).
Variáveis disponíveis no template da mensagem:
  {{cliente}}       → Nome do cliente
  {{consultor}}     → Nome do consultor atribuído
  {{empresa}}       → Nome da empresa (do processo)

PREFIX: /admin/portal-settings
====================================================================
"""

import logging
from typing import Optional
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from database import db
from services.auth import require_admin

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/admin/portal-settings",
    tags=["Portal Settings"],
    dependencies=[Depends(require_admin())]
)


# ── Modelos Pydantic ──

class PortalSettingsUpdate(BaseModel):
    welcome_message_template: Optional[str] = Field(
        None,
        description="Template da mensagem de boas-vindas. Variáveis: {{cliente}}, {{consultor}}, {{empresa}}",
        examples=[
            "Olá, {{cliente}}!\n\nChamo-me {{consultor}}, da equipa da {{empresa}}..."
        ]
    )


# ── Default template (caso não exista config na BD) ──

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


# ── Helpers ──

async def _get_portal_settings_doc() -> dict:
    """Obtém o documento de portal_settings (cria com defaults se não existir)."""
    doc = await db.portal_settings.find_one({"_id": "main"})
    if not doc:
        # Criar com defaults
        doc = {
            "_id": "main",
            "welcome_message_template": DEFAULT_WELCOME_TEMPLATE,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.portal_settings.insert_one(doc)
        logger.info("[PortalSettings] Documento criado com template padrão")
    return doc


def render_welcome_message(
    template: str,
    client_name: str = "Cliente",
    consultor_name: str = "a sua equipa",
    empresa_name: str = "Power Precision",
) -> str:
    """
    Faz a substituição das variáveis no template da mensagem.

    Args:
        template: Texto com variáveis {{cliente}}, {{consultor}}, {{empresa}}
        client_name: Nome do cliente
        consultor_name: Nome do consultor
        empresa_name: Nome da empresa

    Returns:
        Mensagem renderizada com as variáveis substituídas
    """
    result = template
    result = result.replace("{{cliente}}", client_name)
    result = result.replace("{{consultor}}", consultor_name)
    result = result.replace("{{empresa}}", empresa_name)
    return result


# ── Rotas ──

@router.get("")
async def get_portal_settings():
    """
    Obtém as definições do portal do cliente.
    Inclui o template da mensagem de boas-vindas e as variáveis disponíveis.
    """
    doc = await _get_portal_settings_doc()

    return {
        "welcome_message_template": doc.get("welcome_message_template", DEFAULT_WELCOME_TEMPLATE),
        "available_variables": [
            {"key": "{{cliente}}", "description": "Nome do cliente"},
            {"key": "{{consultor}}", "description": "Nome do consultor atribuído"},
            {"key": "{{empresa}}", "description": "Nome da empresa"},
        ],
        "updated_at": doc.get("updated_at"),
    }


@router.put("")
async def update_portal_settings(payload: PortalSettingsUpdate):
    """
    Atualiza as definições do portal do cliente.
    Apenas os campos fornecidos no payload são atualizados.
    """
    update_data = {"updated_at": datetime.now(timezone.utc).isoformat()}

    if payload.welcome_message_template is not None:
        # Validar que o template não está vazio (espaços contam como vazio)
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


@router.post("/reset-welcome")
async def reset_welcome_template():
    """
    Repõe o template da mensagem de boas-vindas para o padrão.
    """
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


@router.post("/preview")
async def preview_welcome_message(payload: PortalSettingsUpdate):
    """
    Pré-visualiza a mensagem de boas-vindas com dados de exemplo.
    Não guarda na BD — apenas retorna o renderizado.
    """
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

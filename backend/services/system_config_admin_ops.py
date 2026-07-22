"""
System config admin ops — complete-setup, storage-info, reset-cache, reveal-secrets.

Extraído de `routes/system_config.py`.
Reuses `services.system_config` (mark_setup_completed, invalidate_config_cache, get_system_config).
"""
from __future__ import annotations

from typing import Optional

from fastapi import HTTPException

from services.system_config import (
    get_system_config,
    mark_setup_completed,
    invalidate_config_cache,
)
from services.system_config_api import SENSITIVE_FIELDS


async def run_complete_setup() -> dict:
    """Marcar a configuração inicial como concluída."""
    await mark_setup_completed()
    return {"success": True, "message": "Configuração inicial concluída"}


async def run_get_storage_info() -> dict:
    """Obter informação sobre o sistema de armazenamento configurado."""
    config = await get_system_config()
    storage = config.storage

    # Converter para string para comparação segura
    provider_value = str(storage.provider.value) if hasattr(storage.provider, 'value') else str(storage.provider)

    # Mapear provider para label amigável
    provider_labels = {
        "none": "Não configurado",
        "aws_s3": "Amazon S3",
        "google_drive": "Google Drive",
        "onedrive": "OneDrive",
        "dropbox": "Dropbox"
    }

    result = {
        "provider": provider_value,
        "provider_label": provider_labels.get(provider_value, provider_value),
        "configured": False,
        "base_url": None,
        "can_browse": False  # Se permite navegação de pastas
    }

    if provider_value == "none":
        return result

    elif provider_value == "aws_s3":
        from services.s3_storage import s3_service
        result["configured"] = s3_service.is_configured()
        result["can_browse"] = True  # S3 permite listar ficheiros
        # Não retornar URL s3:// - browsers não suportam este esquema
        # O acesso a ficheiros S3 é feito via URLs pré-assinadas geradas pela API
        result["base_url"] = None

    elif provider_value == "onedrive":
        result["configured"] = bool(storage.onedrive_shared_url)
        result["base_url"] = storage.onedrive_shared_url
        result["can_browse"] = False  # OneDrive usa links externos

    elif provider_value == "google_drive":
        result["configured"] = bool(storage.google_folder_id)
        if storage.google_folder_id:
            result["base_url"] = f"https://drive.google.com/drive/folders/{storage.google_folder_id}"
        result["can_browse"] = False

    elif provider_value == "dropbox":
        result["configured"] = bool(storage.dropbox_access_token)
        result["can_browse"] = False

    return result


async def run_reset_cache() -> dict:
    """Forçar recarga das configurações do sistema."""
    invalidate_config_cache()
    return {"success": True, "message": "Cache de configurações limpo"}


async def run_reveal_secrets(section: Optional[str] = None) -> dict:
    """Revelar valores sensíveis (passwords, API keys) de uma secção de configuração."""
    config = await get_system_config()
    config_dict = config.model_dump()

    sensitive_fields = SENSITIVE_FIELDS

    # Filtrar apenas a secção pedida
    if section:
        section_data = config_dict.get(section, {})
        if not section_data:
            raise HTTPException(status_code=400, detail=f"Secção '{section}' não encontrada")
        result = {k: v for k, v in section_data.items() if k in sensitive_fields and v}
    else:
        # Revelar todos os campos sensíveis de todas as secções
        result = {}
        for sec_name in ["storage", "email", "ai", "credit_services"]:
            sec_data = config_dict.get(sec_name, {})
            sec_secrets = {k: v for k, v in sec_data.items() if k in sensitive_fields and v}
            if sec_secrets:
                result[sec_name] = sec_secrets

    return {"secrets": result}

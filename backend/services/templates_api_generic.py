"""Generic template generate / download / validate / available handlers.

Extraído de `routes/templates.py`.
Do **not** overwrite `services/template_generator.py`.
"""
from __future__ import annotations

from fastapi import HTTPException

from database import db
from services.template_generator import (
    get_available_templates_list,
    get_template_for_process,
    validate_template_requirements,
)
from services.templates_api_helpers import (
    TEMPLATE_DOWNLOAD_TYPE_NAMES,
    client_filename_slug,
    plain_text_download,
    raise_template_error,
)


async def run_get_available_templates(user: dict):
    """Lista todos os tipos de templates disponíveis para geração."""
    return {"templates": get_available_templates_list()}


async def run_generate_template_generic(
    process_id: str,
    template_type: str,
    user: dict,
):
    """Endpoint genérico para gerar qualquer tipo de template."""
    result = await get_template_for_process(process_id, template_type)
    if result.get("error"):
        raise_template_error(result, include_template_type=template_type)
    return result


async def run_download_template_generic(
    process_id: str,
    template_type: str,
    user: dict,
):
    """Download genérico de template como ficheiro de texto."""
    result = await get_template_for_process(process_id, template_type)
    if result.get("error"):
        raise_template_error(result)

    type_name = TEMPLATE_DOWNLOAD_TYPE_NAMES.get(template_type, template_type)
    filename = f"{type_name}_{client_filename_slug(result)}.txt"
    return plain_text_download(result["template"], filename)


async def run_validate_template_fields(
    process_id: str,
    template_type: str,
    user: dict,
):
    """Valida se o processo tem todos os dados necessários para um template."""
    process = await db.processes.find_one({"id": process_id}, {"_id": 0})
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")

    validation = validate_template_requirements(process, template_type)

    return {
        "process_id": process_id,
        "template_type": template_type,
        "is_valid": validation["is_valid"],
        "can_generate": validation["is_valid"],
        "missing_required_fields": validation["missing_fields"],
        "missing_recommended_fields": validation.get("missing_recommended", []),
        "message": validation["message"],
    }

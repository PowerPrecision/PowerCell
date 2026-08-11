"""Webmail + named template generate/download handlers.

Extraído de `routes/templates.py`.
Do **not** overwrite `services/template_generator.py`.
"""
from __future__ import annotations

from services.template_generator import WEBMAIL_URLS, get_template_for_process
from services.templates_api_helpers import (
    DocumentRequestData,
    client_filename_slug,
    plain_text_download,
    raise_template_error,
)


async def run_get_webmail_urls(user: dict):
    """Retorna as URLs dos webmails disponíveis."""
    return {
        "webmails": [
            {
                "id": "precision",
                "name": "Precision Crédito",
                "url": WEBMAIL_URLS["precision"],
            },
            {
                "id": "power",
                "name": "Power Real Estate",
                "url": WEBMAIL_URLS["power"],
            },
        ]
    }


async def run_get_named_template(process_id: str, template_type: str, user: dict):
    """Generate a named template (cpcv, valuation_appeal, etc.)."""
    result = await get_template_for_process(process_id, template_type)
    if result.get("error"):
        raise_template_error(result)
    return result


async def run_download_named_template(
    process_id: str,
    template_type: str,
    filename_prefix: str,
    user: dict,
):
    """Download a named template as a text attachment."""
    result = await get_template_for_process(process_id, template_type)
    if result.get("error"):
        raise_template_error(result)
    filename = f"{filename_prefix}_{client_filename_slug(result)}.txt"
    return plain_text_download(result["template"], filename)


async def run_get_document_request_template(
    process_id: str,
    data: DocumentRequestData,
    user: dict,
):
    """Gera o template de pedido de documentos ao cliente."""
    result = await get_template_for_process(
        process_id,
        "document_request",
        extra_data={"missing_docs": data.missing_docs},
    )
    if result.get("error"):
        raise_template_error(result)
    return result

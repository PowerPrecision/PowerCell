"""Shared helpers for templates API routes.

Extraído de `routes/templates.py`.
Do **not** overwrite `services/template_generator.py`.
"""
from __future__ import annotations

from typing import List, Optional

from fastapi import HTTPException
from pydantic import BaseModel

from models.auth import UserRole

TEMPLATES_ALLOWED_ROLES = [
    UserRole.ADMIN,
    UserRole.CEO,
    UserRole.DIRETOR,
    UserRole.ADMINISTRATIVO,
    UserRole.CONSULTOR,
    UserRole.INTERMEDIARIO,
]

TEMPLATE_DOWNLOAD_TYPE_NAMES = {
    "cpcv": "CPCV",
    "contrato_mediacao": "Contrato_Mediacao",
    "ficha_visita": "Ficha_Visita",
    "valuation_appeal": "Apelacao_Avaliacao",
    "deed_reminder": "Lembrete_Escritura",
    "document_request": "Pedido_Documentos",
}


class DocumentRequestData(BaseModel):
    """Payload para o pedido de geração de documentos."""

    missing_docs: List[str] = []


def raise_template_error(result: dict, *, include_template_type: Optional[str] = None):
    """Raise HTTPException from a template_generator error payload."""
    if result.get("validation_error"):
        detail = {
            "message": result["error"],
            "missing_fields": result.get("missing_fields", []),
            "missing_fields_message": result.get("missing_fields_message", ""),
        }
        if include_template_type is not None:
            detail["template_type"] = include_template_type
        raise HTTPException(status_code=400, detail=detail)
    raise HTTPException(status_code=404, detail=result["error"])


def plain_text_download(content: str, filename: str):
    """Build PlainTextResponse attachment for a generated template."""
    from fastapi.responses import PlainTextResponse

    return PlainTextResponse(
        content=content,
        media_type="text/plain; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


def client_filename_slug(result: dict) -> str:
    return result.get("client_name", "cliente").replace(" ", "_")

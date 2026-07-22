"""Checklist + document-types handlers for templates routes.

Extraído de `routes/templates.py`.
Do **not** overwrite `services/template_generator.py`.
"""
from __future__ import annotations

from fastapi import HTTPException

from database import db
from services.document_checklist import (
    DOCUMENTOS_CREDITO_HABITACAO,
    generate_checklist,
    get_documentos_em_falta,
)
from services.template_generator import WEBMAIL_URLS


async def run_get_document_checklist(process_id: str, user: dict):
    """Retorna a checklist dinâmica de documentos para um processo."""
    process = await db.processes.find_one({"id": process_id}, {"_id": 0})
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")

    uploaded_files = process.get("uploaded_documents", [])
    file_names = [f.get("name", f.get("filename", "")) for f in uploaded_files]

    checklist_result = generate_checklist(file_names, "credito_habitacao")
    missing_docs = get_documentos_em_falta(
        checklist_result, apenas_obrigatorios=False,
    )

    return {
        "process_id": process_id,
        "client_name": process.get("client_name"),
        "checklist": checklist_result,
        "missing_documents": missing_docs,
        "webmail_urls": WEBMAIL_URLS,
    }


async def run_get_document_types(user: dict):
    """Retorna a lista de tipos de documentos disponíveis."""
    return {
        "document_types": [
            {
                "id": doc["id"],
                "name": doc["nome"],
                "required": doc.get("obrigatorio", False),
            }
            for doc in DOCUMENTOS_CREDITO_HABITACAO
        ]
    }

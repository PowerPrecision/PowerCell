"""Storage document checklist handlers.

Extraído de `routes/storage.py`.
Do **not** overwrite s3_storage.py / storage_service.py — use storage_api_*.
"""
from __future__ import annotations

from fastapi import HTTPException

from database import db
from services.document_checklist import generate_checklist


async def run_generate_document_checklist(process_id: str, files: list[str]):
    process = await db.processes.find_one({"id": process_id}, {"_id": 0})
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")

    tipo_processo = "credito_habitacao"
    result = generate_checklist(files, tipo_processo)
    result["client_name"] = process.get("client_name", "")
    result["process_id"] = process_id

    await db.processes.update_one(
        {"id": process_id},
        {"$set": {"document_checklist": result}}
    )

    return result


async def run_get_document_checklist(process_id: str):
    process = await db.processes.find_one(
        {"id": process_id},
        {"document_checklist": 1, "client_name": 1, "_id": 0}
    )
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")

    checklist = process.get("document_checklist")
    if not checklist:
        return {
            "checklist": [],
            "resumo": {
                "total_documentos": 0,
                "percentagem_conclusao": 0,
            },
            "client_name": process.get("client_name", ""),
            "process_id": process_id
        }

    return checklist

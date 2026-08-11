"""Admin encryption verify/encrypt-single handlers.

Extraído de `routes/admin_encryption.py`.
Never create services/admin_encryption.py — use admin_encryption_api_*.
"""
from __future__ import annotations

from fastapi import HTTPException

from database import db
from services.encryption import encryption_service


async def run_verify_process_encryption(process_id: str):
    process = await db.processes.find_one({"id": process_id}, {"_id": 0})
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")

    results = {
        "process_id": process_id,
        "client_name": process.get("client_name"),
        "encrypted_fields": [],
        "unencrypted_fields": []
    }

    fields_to_check = {
        "personal_data.nif": process.get("personal_data", {}).get("nif"),
        "personal_data.documento_id": process.get("personal_data", {}).get("documento_id"),
        "personal_data.morada_fiscal": process.get("personal_data", {}).get("morada_fiscal"),
        "client_phone": process.get("client_phone"),
        "financial_data.portal_financas_senha": process.get("financial_data", {}).get("portal_financas_senha"),
    }

    for field_path, value in fields_to_check.items():
        if value:
            if encryption_service.is_encrypted(str(value)):
                results["encrypted_fields"].append(field_path)
            else:
                results["unencrypted_fields"].append(field_path)

    return results


async def run_encrypt_single_process(process_id: str):
    if not encryption_service.is_available():
        raise HTTPException(
            status_code=503,
            detail="Serviço de encriptação não disponível"
        )

    process = await db.processes.find_one({"id": process_id})
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")

    encrypted_process = encryption_service.encrypt_process(process)

    if "_id" in encrypted_process:
        del encrypted_process["_id"]

    await db.processes.update_one(
        {"id": process_id},
        {"$set": encrypted_process}
    )

    return {
        "success": True,
        "message": f"Processo {process_id} encriptado com sucesso"
    }

"""Admin encryption status handler.

Extraído de `routes/admin_encryption.py`.
Never create services/admin_encryption.py — use admin_encryption_api_*.
"""
from __future__ import annotations

from database import db
from services.encryption import encryption_service


async def run_get_encryption_status():
    total_processes = await db.processes.count_documents({})

    encrypted_count = 0
    sample_processes = await db.processes.find({}, {
        "_id": 0,
        "id": 1,
        "personal_data.nif": 1,
        "personal_data.documento_id": 1
    }).limit(100).to_list(100)

    for proc in sample_processes:
        personal = proc.get("personal_data", {})
        nif = personal.get("nif", "")
        if nif and encryption_service.is_encrypted(nif):
            encrypted_count += 1

    estimated_encrypted = int((encrypted_count / 100) * total_processes) if sample_processes else 0

    return {
        "encryption_available": encryption_service.is_available(),
        "total_processes": total_processes,
        "estimated_encrypted": estimated_encrypted,
        "estimated_pending": total_processes - estimated_encrypted,
        "fields_protected": [
            "NIFs (personal_data.nif, titular2_data.nif, employer_nif)",
            "Documentos de Identidade (documento_id)",
            "Senhas de portais (portal_financas_senha, seg_social_senha)",
            "Moradas fiscais (morada_fiscal)",
            "Telefones (client_phone, titular2_data.phone)"
        ]
    }

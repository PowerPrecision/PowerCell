"""Migration status endpoint handler.

Extraído de `routes/admin_migration.py`.
"""
from __future__ import annotations

from database import db
from services.admin_migration_api_helpers import pct
from services.encryption import encryption_service


async def run_get_migration_status(user: dict):
    """Verifica o estado atual da migração de encriptação."""
    total_clients = await db.clients.count_documents({})

    with_nif_hash = await db.clients.count_documents(
        {"dados_pessoais.nif_hash": {"$exists": True}}
    )
    with_email_hash = await db.clients.count_documents(
        {"contacto.email_hash": {"$exists": True}}
    )
    with_telefone_hash = await db.clients.count_documents(
        {"contacto.telefone_hash": {"$exists": True}}
    )

    with_encrypted_nif = await db.clients.count_documents(
        {"dados_pessoais.nif": {"$regex": "^ENC:"}}
    )
    with_plain_nif = await db.clients.count_documents({
        "dados_pessoais.nif": {
            "$exists": True, "$ne": None, "$not": {"$regex": "^ENC:"},
        }
    })

    with_encrypted_telefone = await db.clients.count_documents(
        {"contacto.telefone": {"$regex": "^ENC:"}}
    )

    encryption_available = encryption_service.is_available()

    return {
        "encryption_service_available": encryption_available,
        "total_clients": total_clients,
        "blind_indexes": {
            "nif_hash": {
                "count": with_nif_hash,
                "percentage": pct(with_nif_hash, total_clients),
            },
            "email_hash": {
                "count": with_email_hash,
                "percentage": pct(with_email_hash, total_clients),
            },
            "telefone_hash": {
                "count": with_telefone_hash,
                "percentage": pct(with_telefone_hash, total_clients),
            },
        },
        "encryption_status": {
            "nif_encrypted": {
                "count": with_encrypted_nif,
                "percentage": pct(with_encrypted_nif, total_clients),
            },
            "nif_plain_text": {
                "count": with_plain_nif,
                "percentage": pct(with_plain_nif, total_clients),
            },
            "telefone_encrypted": {
                "count": with_encrypted_telefone,
                "percentage": pct(with_encrypted_telefone, total_clients),
            },
        },
        "needs_migration": {
            "count": with_plain_nif,
            "percentage": pct(with_plain_nif, total_clients),
        },
    }

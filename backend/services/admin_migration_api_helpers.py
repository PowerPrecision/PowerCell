"""Helpers for RGPD client encryption migration.

Extraído de `routes/admin_migration.py`.
Do **not** create `services/admin_migration.py` (route name collision).
"""
from __future__ import annotations

import re

from services.encryption import (
    encryption_service,
    generate_nif_hash,
    generate_email_hash,
    generate_telefone_hash,
)


def is_encrypted(value: str) -> bool:
    """Verifica se um valor já está encriptado."""
    if not value or not isinstance(value, str):
        return False
    return value.startswith("ENC:")


def pct(count: int, total: int) -> float:
    """Percentagem arredondada de count/total (0 se total for 0)."""
    return round(count / total * 100, 1) if total > 0 else 0


def build_client_encryption_updates(client: dict, *, track_changes: bool = False):
    """Build `$set` updates (and optional change labels) for one client doc.

    Returns:
        (updates, changes) where updates is a dict suitable for Mongo `$set`
        and changes is a list of human-readable labels (empty unless track_changes).
    """
    updates: dict = {}
    changes: list = []

    dados_pessoais = client.get("dados_pessoais", {})
    if isinstance(dados_pessoais, dict):
        dp_updates = {}

        nif = dados_pessoais.get("nif")
        if nif and not is_encrypted(nif):
            nif_clean = re.sub(r"[^\d]", "", str(nif))
            if len(nif_clean) == 9:
                dp_updates["nif_hash"] = generate_nif_hash(nif_clean)
                if track_changes:
                    changes.append(f"nif_hash gerado para {nif_clean[:3]}***")
            if encryption_service.is_available():
                dp_updates["nif"] = encryption_service.encrypt(str(nif))
                if track_changes:
                    changes.append("NIF encriptado")

        doc_id = dados_pessoais.get("documento_id")
        if doc_id and not is_encrypted(doc_id) and encryption_service.is_available():
            dp_updates["documento_id"] = encryption_service.encrypt(str(doc_id))
            if track_changes:
                changes.append("documento_id encriptado")

        morada = dados_pessoais.get("morada_fiscal")
        if morada and not is_encrypted(morada) and encryption_service.is_available():
            dp_updates["morada_fiscal"] = encryption_service.encrypt(str(morada))
            if track_changes:
                changes.append("morada_fiscal encriptada")

        if dp_updates:
            updates["dados_pessoais"] = {**dados_pessoais, **dp_updates}

    contacto = client.get("contacto", {})
    if isinstance(contacto, dict):
        ct_updates = {}

        email = contacto.get("email")
        if email and not contacto.get("email_hash"):
            ct_updates["email_hash"] = generate_email_hash(email)
            if track_changes:
                changes.append(f"email_hash gerado para {email[:3]}***")

        telefone = contacto.get("telefone")
        if telefone and not is_encrypted(telefone):
            telefone_clean = re.sub(r"[^\d]", "", str(telefone))
            if len(telefone_clean) >= 9:
                ct_updates["telefone_hash"] = generate_telefone_hash(telefone_clean)
                if track_changes:
                    changes.append(
                        f"telefone_hash gerado para {telefone_clean[:3]}***"
                    )
            if encryption_service.is_available():
                ct_updates["telefone"] = encryption_service.encrypt(str(telefone))
                if track_changes:
                    changes.append("Telefone encriptado")

        tel_sec = contacto.get("telefone_secundario")
        if tel_sec and not is_encrypted(tel_sec) and encryption_service.is_available():
            ct_updates["telefone_secundario"] = encryption_service.encrypt(str(tel_sec))
            if track_changes:
                changes.append("telefone_secundario encriptado")

        if ct_updates:
            updates["contacto"] = {**contacto, **ct_updates}

    titular2 = client.get("titular2_data", {})
    if isinstance(titular2, dict) and titular2:
        t2_updates = {}

        nif2 = titular2.get("nif")
        if nif2 and not is_encrypted(nif2):
            nif2_clean = re.sub(r"[^\d]", "", str(nif2))
            if len(nif2_clean) == 9:
                t2_updates["nif_hash"] = generate_nif_hash(nif2_clean)
                if track_changes:
                    changes.append(
                        f"titular2.nif_hash gerado para {nif2_clean[:3]}***"
                    )
            if encryption_service.is_available():
                t2_updates["nif"] = encryption_service.encrypt(str(nif2))
                if track_changes:
                    changes.append("NIF titular2 encriptado")

        if t2_updates:
            updates["titular2_data"] = {**titular2, **t2_updates}

    return updates, changes

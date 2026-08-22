"""
Enriquecimento de registos de email (client_name, created_by_name).

Extraído de `routes/emails.py`.
"""
from __future__ import annotations

from typing import Iterable, List, Sequence

from database import db


async def enrich_emails(emails: Sequence[dict]) -> List[dict]:
    """Enriquece uma lista de emails com nomes de processo e criador.

    Substitui o padrão N+1 (``find_one`` por email) por dois ``find`` com
    ``$in``, juntando os resultados em memória.

    Args:
        emails: Documentos de email da MongoDB (mutados in-place).

    Returns:
        list[dict]: Os mesmos dicionários, com ``client_name`` e
            ``created_by_name`` preenchidos quando encontrados.
    """
    if not emails:
        return list(emails)

    process_ids = list({
        email["process_id"]
        for email in emails
        if email.get("process_id")
    })
    creator_ids = list({
        email["created_by"]
        for email in emails
        if email.get("created_by")
    })

    process_names = await _id_name_map(
        db.processes, process_ids, name_field="client_name",
    )
    creator_names = await _id_name_map(
        db.users, creator_ids, name_field="name",
    )

    for email in emails:
        process_id = email.get("process_id")
        if process_id and process_id in process_names:
            email["client_name"] = process_names[process_id]
        created_by = email.get("created_by")
        if created_by and created_by in creator_names:
            email["created_by_name"] = creator_names[created_by]

    return list(emails)


async def enrich_email(email: dict) -> dict:
    """Enriquece um único registo de email (wrapper do batch)."""
    enriched = await enrich_emails([email])
    return enriched[0] if enriched else email


async def _id_name_map(collection, ids: Iterable, name_field: str) -> dict:
    """Busca ``id`` → ``name_field`` numa colecção com um único ``$in``."""
    id_list = [item for item in ids if item]
    if not id_list:
        return {}
    docs = await collection.find(
        {"id": {"$in": id_list}},
        {"_id": 0, "id": 1, name_field: 1},
    ).to_list(len(id_list))
    return {
        doc["id"]: doc.get(name_field, "") or ""
        for doc in docs
        if doc.get("id")
    }

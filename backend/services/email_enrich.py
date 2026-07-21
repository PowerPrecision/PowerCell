"""
Enriquecimento de registos de email (client_name, created_by_name).

Extraído de `routes/emails.py`.
"""
from __future__ import annotations

from database import db


async def enrich_email(email: dict) -> dict:
    """Enriquece um registo de email com nomes de processo e criador.

    Adiciona ``client_name`` (nome do cliente do processo associado)
    e ``created_by_name`` (nome do utilizador que criou o email).

    Porquê este enriquecimento: a lista de emails no frontend precisa
    de mostrar nomes legíveis em vez de apenas IDs.

    Args:
        email: Dicionário do documento de email da MongoDB.

    Returns:
        dict: Mesmo dicionário com campos client_name e
            created_by_name adicionados (se encontrado).
    """
    # Nome do processo/cliente
    if email.get("process_id"):
        process = await db.processes.find_one(
            {"id": email["process_id"]},
            {"_id": 0, "client_name": 1}
        )
        if process:
            email["client_name"] = process.get("client_name", "")
    
    # Nome de quem criou
    if email.get("created_by"):
        user = await db.users.find_one(
            {"id": email["created_by"]},
            {"_id": 0, "name": 1}
        )
        if user:
            email["created_by_name"] = user.get("name", "")
    
    return email

"""User list / get-by-id handlers.

Extraído de `routes/users.py`.
"""
from __future__ import annotations

from fastapi import HTTPException

from database import db


async def run_get_users(role: str | None, user: dict):
    """Listar utilizadores do sistema (filtro opcional por role)."""
    from services.role_query import build_deep_role_query

    query = {}
    if role:
        query = build_deep_role_query(query, role=role)

    return await db.users.find(query, {"_id": 0, "password": 0}).to_list(500)


async def run_get_user(user_id: str, user: dict):
    """Obter utilizador por ID."""
    found_user = await db.users.find_one(
        {"id": user_id}, {"_id": 0, "password": 0},
    )
    if not found_user:
        raise HTTPException(status_code=404, detail="Utilizador não encontrado")
    return found_user

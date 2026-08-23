"""User list / get-by-id handlers.

Extraído de `routes/users.py`.
"""
from __future__ import annotations

from fastapi import HTTPException

from database import db
from services.staff_assignment import (
    apply_assignment_staff_filter,
    filter_assignment_staff,
)

# Pacote EB — lista global sem paginação curta (alinhado com /admin/users).
USERS_LIST_LIMIT = 10000


async def run_get_users(
    role: str | None,
    user: dict,
    for_assignment: bool = False,
):
    """Listar utilizadores do sistema (filtro opcional por role).

    Pacote DT: `for_assignment=True` exclui admin das dropdowns.
    Pacote FL: inclui indexação nas dropdowns de atribuição.
    Pacote EB: por defeito devolve TODOS (admin, indexação, inativos).
    """
    from services.role_query import build_deep_role_query

    query = {}
    if role:
        query = build_deep_role_query(query, role=role)
    query = apply_assignment_staff_filter(query, for_assignment)

    users = await db.users.find(query, {"_id": 0, "password": 0}).to_list(
        USERS_LIST_LIMIT
    )
    if for_assignment:
        return filter_assignment_staff(users)
    return users


async def run_get_staff_users(user: dict):
    """Staff elegível para atribuição (consultor/intermediario/diretor/ceo)."""
    return await run_get_users(role=None, user=user, for_assignment=True)


async def run_get_user(user_id: str, user: dict):
    """Obter utilizador por ID."""
    found_user = await db.users.find_one(
        {"id": user_id}, {"_id": 0, "password": 0},
    )
    if not found_user:
        raise HTTPException(status_code=404, detail="Utilizador não encontrado")
    return found_user

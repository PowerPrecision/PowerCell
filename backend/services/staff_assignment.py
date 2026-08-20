"""Filtro global de staff para dropdowns de atribuição (Pacote DT).

Admins, indexação, clientes e parceiros nunca entram nas listas de
responsáveis. Elegíveis: consultor, intermediario (incl. mediador legado),
diretor e ceo.
"""
from __future__ import annotations

from typing import Any, Iterable, Optional

from services.role_query import deep_role_in_filter

# Cargos que podem aparecer em atribuições de processo / calendário / tarefas.
ASSIGNMENT_ALLOWED_ROLES = (
    "consultor",
    "intermediario",
    "mediador",
    "diretor",
    "ceo",
)

# Cargo actual (role principal) que nunca entra nestas listas.
ASSIGNMENT_EXCLUDED_PRIMARY_ROLES = (
    "admin",
    "indexacao",
    "index",
    "cliente",
    "parceiro",
)


def _norm_role(value: Any) -> str:
    if not value or not isinstance(value, str):
        return ""
    return value.strip().lower()


def assignment_staff_mongo_filter() -> dict:
    """Query Mongo: cargo principal fora da exclusão + pelo menos um cargo elegível."""
    return {
        "$and": [
            {"role": {"$nin": list(ASSIGNMENT_EXCLUDED_PRIMARY_ROLES)}},
            deep_role_in_filter(list(ASSIGNMENT_ALLOWED_ROLES)),
        ]
    }


def apply_assignment_staff_filter(query: Optional[dict], enabled: bool) -> dict:
    """Combina um filtro existente com o filtro obrigatório de atribuição."""
    base = dict(query or {})
    if not enabled:
        return base
    staff = assignment_staff_mongo_filter()
    if not base:
        return staff
    return {"$and": [base, staff]}


def is_assignment_eligible_user(user: Optional[dict]) -> bool:
    """True se o utilizador pode aparecer num Select de responsável."""
    if not user:
        return False
    primary = _norm_role(user.get("role"))
    if primary in ASSIGNMENT_EXCLUDED_PRIMARY_ROLES:
        return False
    roles = {primary}
    extra = user.get("additional_roles") or []
    if isinstance(extra, Iterable):
        for item in extra:
            roles.add(_norm_role(item))
    return bool(roles & set(ASSIGNMENT_ALLOWED_ROLES))


def filter_assignment_staff(users: Optional[list]) -> list:
    """Cinto de segurança em memória (além do filtro Mongo)."""
    return [u for u in (users or []) if is_assignment_eligible_user(u)]

"""Shared helpers for deadline calendar scope (Pacote DQ).

Extraído para testes unitários sem Mongo: papéis de vista de equipa vs
vista pessoal, responsável do evento e filtro de empresa activa.
"""
from __future__ import annotations

from typing import Optional

from models.auth import UserRole
from models.deadline import normalize_deadline_type
from services.auth import get_all_user_roles

# Diretor / CEO / Admin vêem o calendário da empresa activa.
TEAM_CALENDAR_ROLES = {
    UserRole.ADMIN,
    UserRole.CEO,
    UserRole.DIRETOR,
}

# Consultor / intermediário só vêem eventos atribuídos a si.
SELF_CALENDAR_ROLES = {
    UserRole.CONSULTOR,
    UserRole.INTERMEDIARIO,
}


def sees_team_calendar(effective_role: Optional[str], user: Optional[dict] = None) -> bool:
    """True se o cargo efectivo (X-Active-Role) vê a agenda da equipa."""
    role = (effective_role or "").strip().lower()
    if role == "__all_roles__":
        roles = get_all_user_roles(user or {})
        return any(r in TEAM_CALENDAR_ROLES for r in roles)
    if role in TEAM_CALENDAR_ROLES:
        return True
    if not role and user:
        return (user.get("role") or "") in TEAM_CALENDAR_ROLES
    return False


def is_absence_type(value: Optional[str]) -> bool:
    try:
        return normalize_deadline_type(value, default="deadline") == "absence"
    except ValueError:
        return False


def first_name(full_name: Optional[str]) -> str:
    text = (full_name or "").strip()
    if not text:
        return ""
    return text.split()[0]


def pick_responsible(deadline: dict) -> tuple[Optional[str], Optional[str]]:
    """Devolve (user_id, None) do responsável a prefixar no calendário da equipa.

    Prioridade: primeiro assigned_user_ids → assigned_consultor_id → created_by.
    O nome é preenchido depois via mapa de utilizadores.
    """
    assigned = deadline.get("assigned_user_ids") or []
    if assigned:
        return assigned[0], None
    if deadline.get("assigned_consultor_id"):
        return deadline["assigned_consultor_id"], None
    if deadline.get("created_by"):
        return deadline["created_by"], None
    return None, None


def personal_deadline_or_clauses(user_id: str, process_ids: list[str]) -> list[dict]:
    """Cláusulas $or para consultor/intermediário: só o que lhe está atribuído."""
    clauses = [
        {"assigned_user_ids": user_id},
        {"created_by": user_id},
        {"assigned_consultor_id": user_id},
        {"assigned_mediador_id": user_id},
    ]
    if process_ids:
        clauses.append({"process_id": {"$in": process_ids}})
    else:
        clauses.append({"process_id": None})
    return clauses


def company_event_or_clauses(company_id: Optional[str], process_ids: list[str]) -> list[dict]:
    """Cláusulas $or para a vista de equipa da empresa activa."""
    clauses: list[dict] = []
    if company_id and company_id != "default":
        clauses.append({"company_id": company_id})
    if process_ids:
        clauses.append({"process_id": {"$in": process_ids}})
    return clauses


__all__ = [
    "TEAM_CALENDAR_ROLES",
    "SELF_CALENDAR_ROLES",
    "sees_team_calendar",
    "is_absence_type",
    "first_name",
    "pick_responsible",
    "personal_deadline_or_clauses",
    "company_event_or_clauses",
]

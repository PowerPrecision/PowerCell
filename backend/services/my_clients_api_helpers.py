"""Helpers for routes/my_clients.py.

Do **not** overwrite `process_my_clients.py` (used by GET /processes/my-clients).
Constants mirror the my-clients dedicated route behaviour.
"""
from __future__ import annotations

from fastapi import Request

from models.auth import UserRole
from services.auth import get_effective_role
from services.process_list_filters import (
    EMPTY_PORTFOLIO_QUERY,
    role_has_client_portfolio,
)
from services.process_status import (
    DELETED_STATUS_VALUES,
    INACTIVE_STATUSES,
)

# PACOTE BK — Estado pré_registo (cliente ainda a preencher no portal).
PRE_REGISTO_STATUS = "pre_registo"
# PACOTE DB — Valores de status "Lead" (sem fase do Kanban ativo).
LEAD_STATUS_VALUES = ["pre_registo", None]

MY_CLIENTS_ROLES = [
    UserRole.CONSULTOR,
    UserRole.INTERMEDIARIO,
    UserRole.ADMIN,
    UserRole.CEO,
    UserRole.INDEXACAO,
    UserRole.DIRETOR,
    UserRole.ADMINISTRATIVO,
]

PROCESS_LIST_PROJECTION = {
    "_id": 0,
    "id": 1,
    "process_number": 1,
    "client_name": 1,
    "client_email": 1,
    "client_phone": 1,
    "status": 1,
    "created_at": 1,
    "updated_at": 1,
    "assigned_consultor_id": 1,
    "assigned_consultor_ids": 1,
    "assigned_mediador_id": 1,
    "assigned_mediador_ids": 1,
    "next_action": 1,
    "is_active": 1,
}

LEADS_PROJECTION = {
    "_id": 0,
    "id": 1,
    "nome": 1,
    "contacto": 1,
    "created_at": 1,
    "updated_at": 1,
    "fonte": 1,
    "assigned_to": 1,
    "lead_status": 1,
}


def wants_deleted_view(request: Request) -> bool:
    """PACOTE CP — view_mode=deleted / status=eliminado(s)."""
    view_mode = request.query_params.get("view_mode", "active_only")
    status_filter = request.query_params.get("status")
    return status_filter in DELETED_STATUS_VALUES or view_mode == "deleted"


def build_my_clients_process_query(
    *,
    user_id: str,
    user_email: str,
    role: str,
    wants_deleted: bool,
) -> dict:
    """Build Mongo query for processes in GET /my-clients."""
    if not role_has_client_portfolio(role):
        return EMPTY_PORTFOLIO_QUERY

    if wants_deleted:
        if role == UserRole.CONSULTOR:
            return {
                "$and": [
                    {"$or": [
                        {"assigned_consultor_ids": user_id},
                        {"assigned_consultor_id": user_id},
                    ]},
                    {"is_deleted": True},
                ]
            }
        if role == UserRole.INTERMEDIARIO:
            return {
                "$and": [
                    {"$or": [
                        {"assigned_mediador_ids": user_id},
                        {"assigned_mediador_id": user_id},
                        {"created_by": user_email},
                    ]},
                    {"is_deleted": True},
                ]
            }
        if role in [
            UserRole.DIRETOR,
            UserRole.ADMINISTRATIVO,
        ]:
            return {"$or": [
                {"is_deleted": True},
                {"status": {"$in": DELETED_STATUS_VALUES}},
            ]}
        return EMPTY_PORTFOLIO_QUERY

    if role == UserRole.CONSULTOR:
        return {
            "$and": [
                {"$or": [
                    {"assigned_consultor_ids": user_id},
                    {"assigned_consultor_id": user_id},
                ]},
                {"is_active": {"$ne": False}},
                {"status": {"$nin": INACTIVE_STATUSES}},
                {"is_deleted": {"$ne": True}},
            ]
        }
    if role == UserRole.INTERMEDIARIO:
        return {
            "$and": [
                {"$or": [
                    {"assigned_mediador_ids": user_id},
                    {"assigned_mediador_id": user_id},
                    {"created_by": user_email},
                ]},
                {"is_active": {"$ne": False}},
                {"status": {"$nin": INACTIVE_STATUSES}},
                {"is_deleted": {"$ne": True}},
            ]
        }
    if role in [
        UserRole.DIRETOR,
        UserRole.ADMINISTRATIVO,
    ]:
        return {
            "status": {"$nin": INACTIVE_STATUSES},
            "is_active": {"$ne": False},
        }
    return EMPTY_PORTFOLIO_QUERY


def apply_pre_registo_exclusion(query: dict) -> dict:
    """PACOTE BK/DB — exclude pre_registo + None (Lead) from Meus Clientes."""
    if query == EMPTY_PORTFOLIO_QUERY:
        return query
    pre_registo_filter = {"status": {"$nin": LEAD_STATUS_VALUES}}
    if "$and" in query:
        query["$and"].append(pre_registo_filter)
        return query
    if query:
        return {"$and": [query, pre_registo_filter]}
    return pre_registo_filter


def build_my_clients_stats_query(
    *,
    user_id: str,
    user_email: str,
    role: str,
) -> dict:
    """Build Mongo query for GET /my-clients/stats (no deleted / pre_registo variants)."""
    if not role_has_client_portfolio(role):
        return EMPTY_PORTFOLIO_QUERY
    if role == UserRole.CONSULTOR:
        return {
            "$and": [
                {"$or": [
                    {"assigned_consultor_ids": user_id},
                    {"assigned_consultor_id": user_id},
                ]},
                {"is_active": {"$ne": False}},
                {"status": {"$nin": INACTIVE_STATUSES}},
                {"is_deleted": {"$ne": True}},
            ]
        }
    if role == UserRole.INTERMEDIARIO:
        return {
            "$and": [
                {"$or": [
                    {"assigned_mediador_ids": user_id},
                    {"assigned_mediador_id": user_id},
                    {"created_by": user_email},
                ]},
                {"is_active": {"$ne": False}},
                {"status": {"$nin": INACTIVE_STATUSES}},
                {"is_deleted": {"$ne": True}},
            ]
        }
    if role in [
        UserRole.DIRETOR,
        UserRole.ADMINISTRATIVO,
    ]:
        return {
            "status": {"$nin": INACTIVE_STATUSES},
            "is_active": {"$ne": False},
        }
    return EMPTY_PORTFOLIO_QUERY


def resolve_list_context(request: Request, user: dict) -> tuple[str, str, str, bool]:
    """Return (user_id, user_email, role, wants_deleted)."""
    return (
        user["id"],
        user.get("email", ""),
        get_effective_role(request, user),
        wants_deleted_view(request),
    )


def format_lead_row(lead: dict) -> dict:
    """Convert a clients lead doc to the my-clients list row shape."""
    contacto = lead.get("contacto", {})
    return {
        "id": lead.get("id"),
        "process_number": None,
        "client_name": lead.get("nome", "Sem nome"),
        "client_email": contacto.get("email", ""),
        "client_phone": contacto.get("telefone", ""),
        "status": "lead",
        "status_label": "Lead",
        "status_color": "#8B5CF6",
        "pending_tasks": 0,
        "pending_actions": [],
        "created_at": lead.get("created_at"),
        "updated_at": lead.get("updated_at"),
        "is_lead": True,
    }

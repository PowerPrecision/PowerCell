"""
Builders de query MongoDB para listagens de processos.

Extraído de `routes/processes.py` para eliminar a duplicação entre
`get_processes` e `get_processes_paginated`, e permitir testes unitários
isolados das regras de visibilidade / view_mode / pesquisa.
"""
from __future__ import annotations

import re
from typing import Any, Optional

from models.auth import UserRole
from services.process_status import (
    INACTIVE_STATUSES,
    ARCHIVED_STATUSES,
    LEAD_STATUS_VALUES,
    _should_hide_pre_registo,
)
from utils.search_filters import (
    create_accent_insensitive_regex,
    build_multiword_search_filter,
)


def combine_and_conditions(and_conditions: list[dict]) -> dict:
    """Monta a query final a partir de condições $and."""
    if len(and_conditions) == 1:
        return and_conditions[0]
    if len(and_conditions) > 1:
        return {"$and": and_conditions}
    return {}


def build_is_deleted_filter(
    *,
    status: Optional[str],
    view_mode: Optional[str],
) -> dict:
    """
    Filtro de integridade is_deleted.

    status="eliminados" ou view_mode="deleted" → apenas eliminados.
    Caso contrário → excluir eliminados.
    """
    wants_deleted = status == "eliminados" or view_mode == "deleted"
    if wants_deleted:
        return {"is_deleted": True}
    return {"is_deleted": {"$ne": True}}


def build_role_visibility_conditions(
    user: dict,
    role: str,
    *,
    show_all: bool = False,
    all_roles: Optional[list] = None,
) -> list[dict]:
    """
    Condições de visibilidade por role (sem montar $and final).

    Devolve uma lista (0 ou 1 condições) para acrescentar a and_conditions.
    """
    if show_all:
        return []

    if role == "__all_roles__":
        roles = all_roles or []
        role_conditions: list[dict] = []
        for r in roles:
            if r == UserRole.CONSULTOR:
                role_conditions.extend([
                    {"assigned_consultor_ids": user["id"]},
                    {"assigned_consultor_id": user["id"]},
                ])
            elif r == UserRole.INTERMEDIARIO:
                role_conditions.extend([
                    {"assigned_mediador_ids": user["id"]},
                    {"assigned_mediador_id": user["id"]},
                ])
            elif r == UserRole.INDEXACAO:
                role_conditions.extend([
                    {"assigned_indexacao_id": user["id"]},
                    {"created_by": user.get("email", "")},
                ])
            elif r in [UserRole.ADMIN, UserRole.CEO, UserRole.ADMINISTRATIVO, UserRole.DIRETOR]:
                return []
        if role_conditions:
            return [{"$or": role_conditions}]
        return []

    if role == UserRole.CLIENTE:
        return [{"client_id": user["id"]}]

    if role == UserRole.INDEXACAO:
        # PACOTE BQ — scoped global: atribuídos + criados + fila_espera
        return [{"$or": [
            {"assigned_indexacao_id": user["id"]},
            {"created_by": user.get("email", "")},
            {"status": "fila_espera"},
        ]}]

    if role in [UserRole.ADMIN, UserRole.CEO, UserRole.ADMINISTRATIVO, UserRole.DIRETOR]:
        return []

    if role == UserRole.CONSULTOR:
        return [{"$or": [
            {"assigned_consultor_ids": user["id"]},
            {"assigned_consultor_id": user["id"]},
        ]}]

    if role == UserRole.INTERMEDIARIO:
        return [{"$or": [
            {"assigned_mediador_ids": user["id"]},
            {"assigned_mediador_id": user["id"]},
        ]}]

    return []


def build_view_mode_status_conditions(
    *,
    status: Optional[str],
    view_mode: Optional[str],
) -> list[dict]:
    """Filtros de view_mode + status explícito (exceto eliminados)."""
    conditions: list[dict] = []

    if status == "eliminados":
        pass
    elif view_mode == "active_only":
        conditions.append({"status": {"$nin": INACTIVE_STATUSES}})
    elif view_mode == "historical":
        conditions.append({"status": {"$in": ARCHIVED_STATUSES}})

    if status and status != "eliminados":
        conditions.append({"status": status})

    return conditions


def build_is_indexed_conditions(is_indexed: Optional[bool]) -> list[dict]:
    """PACOTE BZ — filtro de estado de indexação."""
    if is_indexed is None:
        return []
    if is_indexed is True:
        return [{"is_indexed": True}]
    return [{"$or": [
        {"is_indexed": {"$ne": True}},
        {"is_indexed": {"$exists": False}},
    ]}]


def build_process_search_condition(
    search: Optional[str],
    *,
    mode: str = "accent",
) -> Optional[dict]:
    """
    Condição de pesquisa de texto.

    mode:
      - "accent": regex accent-insensitive no nome (GET /processes)
      - "multiword": build_multiword_search_filter no nome (cursor paginated)
    """
    if not search:
        return None

    simple_regex = {"$regex": re.escape(search), "$options": "i"}
    search_or_conditions: list[dict] = []

    if mode == "multiword":
        name_filter = build_multiword_search_filter(search, "client_name")
        if name_filter:
            search_or_conditions.append(name_filter)
    else:
        search_or_conditions.append({"client_name": create_accent_insensitive_regex(search)})

    search_or_conditions.extend([
        {"client_email": simple_regex},
        {"client_nif": simple_regex},
        {"client_phone": simple_regex},
        {"process_number": simple_regex},
    ])
    return {"$or": search_or_conditions}


def build_process_list_query(
    user: dict,
    role: str,
    *,
    status: Optional[str] = None,
    search: Optional[str] = None,
    view_mode: Optional[str] = "active_only",
    show_all: bool = False,
    is_indexed: Optional[bool] = None,
    all_roles: Optional[list] = None,
    search_mode: str = "accent",
) -> dict[str, Any]:
    """
    Query MongoDB completa para listagens de processos.

    Combinada com $and — os filtros nunca se anulam mutuamente.
    """
    and_conditions: list[dict] = []

    and_conditions.append(build_is_deleted_filter(status=status, view_mode=view_mode))
    and_conditions.extend(
        build_role_visibility_conditions(
            user, role, show_all=show_all, all_roles=all_roles,
        )
    )
    and_conditions.extend(
        build_view_mode_status_conditions(status=status, view_mode=view_mode)
    )
    and_conditions.extend(build_is_indexed_conditions(is_indexed))

    search_cond = build_process_search_condition(search, mode=search_mode)
    if search_cond:
        and_conditions.append(search_cond)

    if _should_hide_pre_registo(role, status, search):
        and_conditions.append({"status": {"$nin": LEAD_STATUS_VALUES}})

    return combine_and_conditions(and_conditions)


# ====================================================================
# KANBAN QUERY BUILDERS
# ====================================================================

def merge_query_and(query: dict, condition: dict) -> dict:
    """Combina uma condição extra numa query existente via $and."""
    if not condition:
        return query
    if not query:
        return condition
    if "$and" in query:
        query["$and"].append(condition)
        return query
    return {"$and": [query, condition]}


def build_kanban_role_base_query(
    user: dict,
    role: str,
    *,
    show_all: bool = False,
) -> dict:
    """
    Query base do Kanban: is_deleted + visibilidade por role.

    Nota: INDEXACAO tem scope próprio (atribuídos + fila_espera) mesmo com
    show_all=True — é o âmbito natural de trabalho da Indexação.
    """
    query: dict[str, Any] = {"is_deleted": {"$ne": True}}
    user_id = user["id"]

    if role == UserRole.INDEXACAO:
        query["$or"] = [
            {"assigned_indexacao_id": user_id},
            {"status": "fila_espera"},
        ]
    elif not show_all:
        if role == UserRole.CONSULTOR:
            query["$or"] = [
                {"assigned_consultor_ids": user_id},
                {"assigned_consultor_id": user_id},
            ]
        elif role == UserRole.INTERMEDIARIO:
            query["$or"] = [
                {"assigned_mediador_ids": user_id},
                {"assigned_mediador_id": user_id},
            ]
        # Admin/CEO/Administrativo/Diretor — sem filtro extra

    return query


def build_kanban_assignee_filters(
    *,
    consultor_id: Optional[str] = None,
    mediador_id: Optional[str] = None,
    indexacao_id: Optional[str] = None,
    parceiro_id: Optional[str] = None,
) -> list[dict]:
    """Filtros opcionais por atribuição (incl. valor especial \"none\")."""
    filter_conditions: list[dict] = []

    if consultor_id:
        if consultor_id == "none":
            filter_conditions.append({
                "$or": [
                    {"assigned_consultor_ids": {"$in": [None, [], ""]}},
                    {"assigned_consultor_ids": {"$exists": False}},
                    {"assigned_consultor_id": None},
                    {"assigned_consultor_id": ""},
                    {"assigned_consultor_id": {"$exists": False}},
                ]
            })
        else:
            filter_conditions.append({
                "$or": [
                    {"assigned_consultor_ids": consultor_id},
                    {"assigned_consultor_id": consultor_id},
                ]
            })

    if mediador_id:
        if mediador_id == "none":
            filter_conditions.append({
                "$or": [
                    {"assigned_mediador_ids": {"$in": [None, [], ""]}},
                    {"assigned_mediador_ids": {"$exists": False}},
                    {"assigned_mediador_id": None},
                    {"assigned_mediador_id": ""},
                    {"assigned_mediador_id": {"$exists": False}},
                ]
            })
        else:
            filter_conditions.append({
                "$or": [
                    {"assigned_mediador_ids": mediador_id},
                    {"assigned_mediador_id": mediador_id},
                ]
            })

    if indexacao_id:
        if indexacao_id == "none":
            filter_conditions.append({
                "$or": [
                    {"assigned_indexacao_id": {"$in": [None, ""]}},
                    {"assigned_indexacao_id": {"$exists": False}},
                ]
            })
        else:
            filter_conditions.append({"assigned_indexacao_id": indexacao_id})

    if parceiro_id:
        if parceiro_id == "none":
            filter_conditions.append({
                "$or": [
                    {"assigned_parceiro_id": {"$in": [None, ""]}},
                    {"assigned_parceiro_id": {"$exists": False}},
                ]
            })
        else:
            filter_conditions.append({"assigned_parceiro_id": parceiro_id})

    return filter_conditions


def build_kanban_view_mode_filter(
    *,
    view_mode: Optional[str] = "all",
    completed_days: Optional[int] = 30,
    now: Optional[Any] = None,
) -> Optional[dict]:
    """
    Filtro de view_mode do Kanban.

    - active_only: exclui concluídos/desistências
    - all + completed_days > 0: activos OU inactivos recentes
    - all + completed_days == 0: sem filtro extra
    """
    if view_mode == "active_only":
        return {"status": {"$nin": INACTIVE_STATUSES}}

    if completed_days and completed_days > 0:
        from datetime import datetime, timezone, timedelta
        ref = now or datetime.now(timezone.utc)
        cutoff_date = (ref - timedelta(days=completed_days)).isoformat()
        return {
            "$or": [
                {"status": {"$nin": INACTIVE_STATUSES}},
                {
                    "$and": [
                        {"status": {"$in": ARCHIVED_STATUSES}},
                        {"updated_at": {"$gte": cutoff_date}},
                    ]
                },
            ]
        }
    return None


def build_kanban_query(
    user: dict,
    role: str,
    *,
    show_all: bool = False,
    consultor_id: Optional[str] = None,
    mediador_id: Optional[str] = None,
    indexacao_id: Optional[str] = None,
    parceiro_id: Optional[str] = None,
    view_mode: Optional[str] = "all",
    completed_days: Optional[int] = 30,
) -> dict:
    """Query MongoDB completa para o board Kanban."""
    query = build_kanban_role_base_query(user, role, show_all=show_all)

    assignee_filters = build_kanban_assignee_filters(
        consultor_id=consultor_id,
        mediador_id=mediador_id,
        indexacao_id=indexacao_id,
        parceiro_id=parceiro_id,
    )
    if assignee_filters:
        if query:
            query = {"$and": [query] + assignee_filters}
        else:
            query = combine_and_conditions(assignee_filters)

    view_filter = build_kanban_view_mode_filter(
        view_mode=view_mode, completed_days=completed_days,
    )
    if view_filter:
        query = merge_query_and(query, view_filter)

    # Pré-registo sempre excluído do Kanban (todos os roles)
    query = merge_query_and(query, {"status": {"$nin": LEAD_STATUS_VALUES}})
    return query

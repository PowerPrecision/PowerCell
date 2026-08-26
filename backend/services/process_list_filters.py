"""
Builders de query MongoDB para listagens de processos.

Extraído de `routes/processes.py` para eliminar a duplicação entre
`get_processes` e `get_processes_paginated`, e permitir testes unitários
isolados das regras de visibilidade / view_mode / pesquisa.
"""
from __future__ import annotations

import re
from typing import Any, Iterable, Optional, Sequence, Union

from bson import ObjectId
from bson.errors import InvalidId

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


def normalize_id_for_match(value: Any) -> Optional[str]:
    """
    Normaliza um ID de utilizador para comparação robusta com o Mongo.

    O ID do consultor/intermediário extraído do token JWT (``user["id"]``)
    chega sempre como ``str`` quando vem de um payload JSON válido, mas
    documentos legados/seed podem ter o campo equivalente guardado com
    outro tipo Python (``ObjectId``, ``UUID``, ``int``) ou com espaços em
    branco acidentais. Uma comparação directa (``==`` / ``$in``) no Mongo
    falha SILENCIOSAMENTE quando os tipos BSON não coincidem — não há
    erro, apenas zero resultados — o que é exactamente o sintoma de
    "Os Meus Processos" a devolver vazio para Consultores.

    Converte sempre para ``str`` e remove espaços, para garantir que o
    valor usado nas cláusulas ``$or`` / ``$in`` é uma string Mongo pura,
    igual à forma como os IDs são persistidos em ``assigned_*`` pelos
    fluxos de atribuição (``str(uuid.uuid4())``).
    """
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _safe_object_id(value: Optional[str]) -> Optional[ObjectId]:
    """
    Tenta converter ``value`` num ``bson.ObjectId`` de forma segura.

    A base de dados guarda alguns IDs de atribuição como ``ObjectId``
    nativo (seed/migrações antigas), enquanto o ID extraído do token JWT
    chega sempre como ``str``. Uma comparação Mongo entre tipos BSON
    diferentes falha SILENCIOSAMENTE (zero resultados, sem erro) — daí a
    lista "Os Meus Processos" aparecer vazia mesmo com processos
    atribuídos. Fazemos sempre o cast num bloco try/except para nunca
    deixar a query rebentar quando o valor não é um ObjectId válido
    (ex.: UUID legado gerado por ``str(uuid.uuid4())``).
    """
    if not value:
        return None
    try:
        return ObjectId(value)
    except (InvalidId, TypeError, ValueError):
        return None


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

    # Normaliza sempre para str — evita que um tipo BSON inesperado no
    # user["id"] (ObjectId/UUID/int) falhe silenciosamente o match.
    user_id = normalize_id_for_match(user.get("id")) or ""

    if role == "__all_roles__":
        roles = all_roles or []
        role_conditions: list[dict] = []
        for r in roles:
            if r == UserRole.CONSULTOR:
                role_conditions.extend([
                    {"assigned_consultor_ids": user_id},
                    {"assigned_consultor_id": user_id},
                ])
            elif r == UserRole.INTERMEDIARIO:
                role_conditions.extend([
                    {"assigned_mediador_ids": user_id},
                    {"assigned_mediador_id": user_id},
                ])
            elif r == UserRole.INDEXACAO:
                role_conditions.extend([
                    {"assigned_indexacao_id": user_id},
                    {"created_by": user.get("email", "")},
                ])
            elif r in [UserRole.ADMIN, UserRole.CEO, UserRole.ADMINISTRATIVO, UserRole.DIRETOR]:
                return []
        if role_conditions:
            return [{"$or": role_conditions}]
        return []

    if role == UserRole.CLIENTE:
        return [{"client_id": user_id}]

    if role == UserRole.INDEXACAO:
        # PACOTE BQ — scoped global: atribuídos + criados + fila_espera
        return [{"$or": [
            {"assigned_indexacao_id": user_id},
            {"created_by": user.get("email", "")},
            {"status": "fila_espera"},
        ]}]

    if role in [UserRole.ADMIN, UserRole.CEO, UserRole.ADMINISTRATIVO, UserRole.DIRETOR]:
        return []

    if role == UserRole.CONSULTOR:
        return [{"$or": [
            {"assigned_consultor_ids": user_id},
            {"assigned_consultor_id": user_id},
        ]}]

    if role == UserRole.INTERMEDIARIO:
        return [{"$or": [
            {"assigned_mediador_ids": user_id},
            {"assigned_mediador_id": user_id},
        ]}]

    return []


# Campos de atribuição canónicos + aliases legados. Usados tanto em
# GET /processes/me (mine_only) como no filtro "Atribuído a".
ASSIGNMENT_ID_FIELDS: tuple[str, ...] = (
    "assigned_to",
    "assigned_consultor_ids",
    "assigned_consultor_id",
    "assigned_consultant_ids",
    "assigned_consultant_id",
    "assigned_mediador_ids",
    "assigned_mediador_id",
    "assigned_indexacao_id",
    "assigned_parceiro_id",
    "assigned_users",
    "assigned_user_ids",
    "consultant_id",
    "consultor_id",
    "mediador_id",
    "manager_id",
)

_SENTINEL_IDS = frozenset({"", "all", "undefined", "null"})

# Campos legados/canónicos que guardam o(s) ID(s) do utilizador numa array.
# Nestes, a comparação usa ``$in`` explicitamente (em vez de igualdade
# simples) para garantir o match robusto mesmo que o valor guardado não
# seja uma array "pura" do Mongo.
_ARRAY_ASSIGNMENT_FIELDS: frozenset[str] = frozenset({
    "assigned_consultor_ids",
    "assigned_consultant_ids",
    "assigned_mediador_ids",
    "assigned_users",
    "assigned_user_ids",
})


def _assignment_clauses_for_id(user_id: str) -> list[dict]:
    # Normaliza sempre para str antes de montar as cláusulas — o ID pode
    # chegar como ObjectId/UUID/int em documentos legados/seed e uma
    # comparação Mongo entre tipos BSON diferentes falha silenciosamente
    # (zero resultados, sem erro). Tentamos SEMPRE o cast seguro para
    # ObjectId (try/except bson.errors.InvalidId) e procuramos TANTO pela
    # string original COMO pelo ObjectId (quando válido), porque a BD tem
    # documentos com o ID guardado em ambos os formatos.
    normalized_id = normalize_id_for_match(user_id) or ""
    object_id = _safe_object_id(normalized_id)
    match_values: list[Any] = [normalized_id]
    if object_id is not None:
        match_values.append(object_id)

    clauses: list[dict] = []
    for field in ASSIGNMENT_ID_FIELDS:
        if field in _ARRAY_ASSIGNMENT_FIELDS or len(match_values) > 1:
            clauses.append({field: {"$in": match_values}})
        else:
            clauses.append({field: normalized_id})
    return clauses


def build_assigned_to_me_condition(user_id: str) -> dict:
    """
    PACOTE DU / DV / FL / FQ-3 — processos directamente atribuídos ao utilizador.

    GET /processes/me filtra SEMPRE por esta condição, inclusive quando a
    role activa é diretor/admin/ceo (esses roles só vêem tudo em show_all).

    Operador ``$or`` robusto: cobre tanto o ID directo do utilizador nos
    campos escalares canónicos e legados (ex.: ``consultant_id``,
    ``consultor_id``, ``manager_id``, ``assigned_to``) como a presença do
    ID na(s) array(s) de atribuição (``assigned_user_ids``,
    ``assigned_consultor_ids``, ``assigned_mediador_ids``, ``assigned_users``,
    via ``$in``). Sem isto, Consultores com processos atribuídos apenas via
    ``assigned_user_ids`` (ou apenas via ``consultant_id``/``manager_id``
    legados) ficavam sem resultados em "Os Meus Processos".

    O ID é normalizado explicitamente para ``str`` (ver
    ``normalize_id_for_match``) e as cláusulas geradas por
    ``_assignment_clauses_for_id`` procuram tanto pela string como pelo
    ``ObjectId`` equivalente (quando válido) — a causa nº1 de "Os Meus
    Processos" devolver vazio para Consultores é o ID do token não
    coincidir em tipo BSON (``str`` vs ``ObjectId``) com o valor
    persistido em ``assigned_*``.
    """
    return {"$or": _assignment_clauses_for_id(user_id)}


def normalize_assigned_user_ids(
    assigned_user_id: Optional[str] = None,
    assigned_user_ids: Optional[Union[str, Sequence[str]]] = None,
) -> list[str]:
    """Junta ``assigned_user_id`` (legado) e ``assigned_user_ids`` (lista/CSV)."""
    raw: list[Any] = []
    if assigned_user_ids is not None:
        if isinstance(assigned_user_ids, str):
            raw.extend(assigned_user_ids.split(","))
        elif isinstance(assigned_user_ids, Iterable):
            for item in assigned_user_ids:
                if item is None:
                    continue
                raw.extend(str(item).split(","))
    if assigned_user_id:
        raw.extend(str(assigned_user_id).split(","))

    ids: list[str] = []
    seen: set[str] = set()
    for piece in raw:
        uid = str(piece).strip()
        if not uid or uid.lower() in _SENTINEL_IDS or uid in seen:
            continue
        seen.add(uid)
        ids.append(uid)
    return ids


def parse_assigned_logic(assigned_logic: Optional[str]) -> str:
    logic = (assigned_logic or "OR").strip().upper()
    return "AND" if logic == "AND" else "OR"


def match_users_on_assignment_fields(
    user_ids: Sequence[str],
    logic: str = "OR",
) -> Optional[dict]:
    """Filtro de atribuição para 1+ IDs. OR = pelo menos um; AND = todos."""
    ids = [uid for uid in user_ids if uid]
    if not ids:
        return None
    logic_n = parse_assigned_logic(logic)
    if logic_n == "AND":
        if len(ids) == 1:
            return {"$or": _assignment_clauses_for_id(ids[0])}
        return {"$and": [{"$or": _assignment_clauses_for_id(uid)} for uid in ids]}
    if len(ids) == 1:
        return {"$or": _assignment_clauses_for_id(ids[0])}
    return {"$or": [{field: {"$in": ids}} for field in ASSIGNMENT_ID_FIELDS]}


def build_assigned_user_filter(assigned_user_id: Optional[str]) -> Optional[dict]:
    """Compat PACOTE FK — um único ID. Delega no filtro multi-utilizador."""
    return match_users_on_assignment_fields(
        normalize_assigned_user_ids(assigned_user_id=assigned_user_id),
        "OR",
    )


def build_assigned_users_filter(
    assigned_user_ids: Optional[Union[str, Sequence[str]]] = None,
    assigned_logic: Optional[str] = "OR",
    assigned_user_id: Optional[str] = None,
) -> Optional[dict]:
    """PACOTE FL — filtro multi-utilizador com lógica AND/OR."""
    ids = normalize_assigned_user_ids(assigned_user_id, assigned_user_ids)
    return match_users_on_assignment_fields(ids, assigned_logic)


def build_process_type_condition(process_type: Optional[str]) -> Optional[dict]:
    """Filtro opcional por tipo de processo (campo canónico + alias legado)."""
    pt = (process_type or "").strip()
    if not pt:
        return None
    return {"$or": [
        {"process_type": pt},
        {"type": pt},
    ]}


def build_company_scope_condition(company_id: Optional[str]) -> Optional[dict]:
    """
    PACOTE DV — isolamento por empresa activa.

    GET /processes/me exige ``company_id == active_company_id`` (com fallback
    para o campo legado ``company``). Processos sem empresa só entram no
    sentinel ``default``.
    """
    cid = (company_id or "").strip()
    if not cid:
        return None

    clauses: list[dict] = [
        {"company_id": cid},
        {"company": cid},
        {"company_name": cid},
    ]
    if cid == "default":
        clauses.extend([
            {"company_id": {"$in": [None, "", "default"]}},
            {"company_id": {"$exists": False}},
            {"company": {"$in": [None, "", "default"]}},
            {"company": {"$exists": False}},
        ])
    return {"$or": clauses}


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
    mine_only: bool = False,
    company_id: Optional[str] = None,
    assigned_user_id: Optional[str] = None,
    assigned_user_ids: Optional[Union[str, Sequence[str]]] = None,
    assigned_logic: Optional[str] = "OR",
    process_type: Optional[str] = None,
) -> dict[str, Any]:
    """
    Query MongoDB completa para listagens de processos.

    Combinada com $and — os filtros nunca se anulam mutuamente.
    mine_only=True (GET /processes/me) ignora a role e filtra sempre
    por assigned_to / assigned_* / consultant_id / manager_id / assigned_users
    == user_id E company_id da empresa activa.

    PACOTE FL: ``assigned_user_ids`` + ``assigned_logic`` (AND/OR) são
    filtros opcionais da listagem (AND com visibilidade / mine_only /
    view_mode). ``assigned_user_id`` mantém-se como alias legado.
    """
    and_conditions: list[dict] = []

    and_conditions.append(build_is_deleted_filter(status=status, view_mode=view_mode))
    if mine_only:
        # Normaliza explicitamente para str — a causa nº1 de "Os Meus
        # Processos" devolver vazio para Consultores é o ID extraído do
        # token (``user["id"]``) não coincidir em tipo BSON com o valor
        # persistido nos campos ``assigned_*`` (comparação Mongo entre
        # tipos diferentes falha silenciosamente, sem erro).
        user_id = normalize_id_for_match(user.get("id") or user.get("user_id")) or ""
        and_conditions.append(build_assigned_to_me_condition(user_id))
        company_cond = build_company_scope_condition(
            company_id if company_id is not None else user.get("active_company_id") or user.get("company")
        )
        if company_cond:
            and_conditions.append(company_cond)
    else:
        and_conditions.extend(
            build_role_visibility_conditions(
                user, role, show_all=show_all, all_roles=all_roles,
            )
        )
    and_conditions.extend(
        build_view_mode_status_conditions(status=status, view_mode=view_mode)
    )
    and_conditions.extend(build_is_indexed_conditions(is_indexed))

    assigned_cond = build_assigned_users_filter(
        assigned_user_ids=assigned_user_ids,
        assigned_logic=assigned_logic,
        assigned_user_id=assigned_user_id,
    )
    if assigned_cond:
        and_conditions.append(assigned_cond)

    type_cond = build_process_type_condition(process_type)
    if type_cond:
        and_conditions.append(type_cond)

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
    user_id = normalize_id_for_match(user.get("id")) or ""

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


# ====================================================================
# MY-CLIENTS QUERY BUILDERS
# ====================================================================

# Perfis puramente administrativos: não têm carteira própria em
# "Os Meus Clientes". Um admin/CEO/indexação de sistema não deve ver
# todos os clientes da plataforma nesta vista (nem os que eventualmente
# estejam atribuídos a si enquanto cargo operacional).
NO_CLIENT_PORTFOLIO_ROLES = frozenset({
    UserRole.ADMIN,
    UserRole.CEO,
    UserRole.INDEXACAO,
})

# Query que não casa com nenhum documento Mongo (os docs têm sempre _id).
EMPTY_PORTFOLIO_QUERY = {"_id": None}


def role_has_client_portfolio(role: str) -> bool:
    """False para admin / ceo / indexacao (perfil activo sem carteira)."""
    return (role or "") not in NO_CLIENT_PORTFOLIO_ROLES


def build_my_clients_process_query(
    user_id: str,
    user_email: str,
    role: str,
) -> dict:
    """
    Query de processos para GET /processes/my-clients.

    SINCRONIZAÇÃO COM "Os Meus Processos":
    Consultor/intermediário usam o mesmo critério base (assigned_* + is_active
    + status activo). Pré-registo é sempre excluído nesta vista.
    Admin / CEO / Indexação devolvem query vazia (sem carteira).
    """
    if not role_has_client_portfolio(role):
        return EMPTY_PORTFOLIO_QUERY

    # Mesma normalização defensiva usada em "Os Meus Processos" — garante
    # que o ID é sempre uma string Mongo pura.
    user_id = normalize_id_for_match(user_id) or user_id

    if role == UserRole.CONSULTOR:
        query: dict[str, Any] = {
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
    elif role == UserRole.INTERMEDIARIO:
        query = {
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
    else:
        query = {}

    return merge_query_and(query, {"status": {"$nin": LEAD_STATUS_VALUES}})


def build_my_clients_leads_query(user_id: str) -> dict:
    """Leads órfãos (sem processo) criados pelo utilizador, ainda pendentes."""
    return {
        "$and": [
            {"created_by": user_id},
            {"is_deleted": {"$ne": True}},
            {"$or": [
                {"process_ids": {"$exists": False}},
                {"process_ids": []},
                {"process_ids": None},
            ]},
            {"$or": [
                {"lead_status": {"$exists": False}},
                {"lead_status": "new"},
            ]},
        ]
    }

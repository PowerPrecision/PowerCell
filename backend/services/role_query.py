"""
DEEP ROLE SEARCH — Pesquisa Profunda de Cargos

Helper para queries MongoDB que incluem tanto o role principal
quanto o array additional_roles.

Quando um utilizador tem role="consultor" e additional_roles=["mediador"],
uma query por role="mediador" DEVE encontrar este utilizador.

Uso:
    from services.role_query import deep_role_filter, deep_role_in_filter

    # Filtro exacto
    query.update(deep_role_filter("mediador"))

    # Filtro $in
    query.update(deep_role_in_filter(["consultor", "diretor"]))
"""
from typing import Union, List, Optional, Dict


def deep_role_filter(role: str) -> dict:
    """
    Retorna um filtro MongoDB que inclui utilizadores cujo role principal
    OU additional_roles contenha o role solicitado.

    Args:
        role: O role a pesquisar (ex: "consultor", "mediador")

    Returns:
        dict com $or condition
    """
    return {
        "$or": [
            {"role": role},
            {"additional_roles": role}
        ]
    }


def deep_role_in_filter(roles: List[str]) -> dict:
    """
    Retorna um filtro MongoDB equivalente a $in mas que também pesquisa
    em additional_roles.

    Exemplo: deep_role_in_filter(["consultor", "diretor"])
    → {"$or": [{"role": {"$in": [...]}}, {"additional_roles": {"$in": [...]}}]}

    Args:
        roles: Lista de roles a pesquisar

    Returns:
        dict com $or + $in conditions
    """
    if not roles:
        return {}
    if len(roles) == 1:
        return deep_role_filter(roles[0])
    return {
        "$or": [
            {"role": {"$in": roles}},
            {"additional_roles": {"$in": roles}}
        ]
    }


def deep_role_nin_filter(roles: List[str]) -> dict:
    """
    Retorna um filtro MongoDB que EXCLUI utilizadores cujo role principal
    OU additional_roles contenha qualquer um dos roles especificados.

    Args:
        roles: Lista de roles a excluir

    Returns:
        dict com $and + $nin/$not conditions
    """
    if not roles:
        return {}
    return {
        "$and": [
            {"role": {"$nin": roles}},
            {"additional_roles": {"$nin": roles}}
        ]
    }


def build_deep_role_query(base_query: dict, role: Optional[str] = None, roles: Optional[List[str]] = None) -> dict:
    """
    Constroi uma query MongoDB combinando um query base com filtros de deep role.

    Args:
        base_query: Query base existente (ex: {"is_active": True})
        role: Role exacto para pesquisar (mutuamente exclusivo com roles)
        roles: Lista de roles para pesquisa $in (mutuamente exclusivo com role)

    Returns:
        Query MongoDB completa com deep role filtering
    """
    query = dict(base_query)
    if role:
        query.update(deep_role_filter(role))
    elif roles:
        query.update(deep_role_in_filter(roles))
    return query


__all__ = [
    "deep_role_filter",
    "deep_role_in_filter",
    "deep_role_nin_filter",
    "build_deep_role_query",
]

"""Cargos dados POR EMPRESA (UCR) também contam nas listas de atribuição (Nov 2026).

O PROBLEMA
==========
O perfil efectivo de alguém resolve-se pelos UCRs (`user_company_roles`,
`services/auth.py::get_effective_role_async`): é assim que a pessoa ENTRA e
trabalha. Mas as listas de «a quem posso atribuir» e o pool da atribuição
automática do Index perguntavam só ao documento `users` (`role` +
`additional_roles`). Quem tinha o cargo de Index (ou de consultor,
intermediário…) dado na grelha de acessos por empresa trabalhava como tal e
NÃO aparecia na Gestão de Atribuições — nem para o Master —, nem recebia
processos da atribuição automática.

A REGRA
=======
Um cargo vale para as listas se estiver no `role`, nos `additional_roles` OU
num UCR válido (não apagado, não inactivo — o mesmo filtro de
`get_user_companies`). Um UCR sem `role` herda o principal, que já conta.
Os aliases do Index (`indexacao` e o legado `index`) são o mesmo cargo.

Isto só decide QUEM ENTRA na lista. A fronteira de rede continua a ser a de
`assignment_network_guard` (quem grava faz a mesma pergunta).
"""
from __future__ import annotations

import logging
from typing import Iterable

logger = logging.getLogger(__name__)


def _base(base):
    """A BD do CHAMADOR (a referência que o seu módulo tem), como `exigir_atribuidos_da_minha_rede`.

    Um `from database import db` no topo deste módulo dava-lhe uma referência própria: os testes que
    substituem só a do chamador (`patch.object(modulo, "db", fake)`) deixavam aqui falar com o proxy
    real — «Event loop is closed». Sem `base`, lê-se `database.db` na hora (respeita o patch global).
    """
    if base is not None:
        return base
    import database

    return database.db

#: Os papéis do Index (o principal e o alias legado).
PAPEIS_DO_INDEX = ("indexacao", "index")

#: Um UCR conta se não foi apagado nem desactivado (igual a `get_user_companies`).
UCR_VALIDO = {"is_deleted": {"$ne": True}, "is_active": {"$ne": False}}

#: Tecto de leitura (alinhado com `USERS_LIST_LIMIT`).
_LIMITE = 10000


def _norm(valor) -> str:
    return valor.strip().lower() if isinstance(valor, str) else ""


def papeis_equivalentes(roles: Iterable[str]) -> list[str]:
    """Os papéis pedidos, com os aliases do Index juntos. Sem repetidos, ordem estável."""
    saida: list[str] = []
    for r in roles or ():
        n = _norm(r)
        if not n:
            continue
        for p in (PAPEIS_DO_INDEX if n in PAPEIS_DO_INDEX else (n,)):
            if p not in saida:
                saida.append(p)
    return saida


async def _ler_ucrs(base, filtro: dict, projeccao: dict) -> list[dict]:
    """Lê UCRs; se a leitura falhar, nenhum (fica o comportamento antigo: só `users.role`).

    Degradação graciosa: uma lista de atribuição sem os cargos por empresa é a de ontem; uma
    lista que rebenta deixa a Gestão de Atribuições vazia.
    """
    try:
        return await _base(base).user_company_roles.find(filtro, projeccao).to_list(_LIMITE)
    except Exception as exc:
        logger.warning("[role_ucr] Não foi possível ler os acessos por empresa: %s", exc)
        return []


async def ids_com_papel_numa_empresa(roles: Iterable[str], base=None) -> list[str]:
    """Ids de quem tem um destes papéis num UCR válido."""
    papeis = papeis_equivalentes(roles)
    if not papeis:
        return []
    docs = await _ler_ucrs(base, {**UCR_VALIDO, "role": {"$in": papeis}}, {"_id": 0, "user_id": 1})
    return sorted({str(d["user_id"]) for d in docs if d.get("user_id")})


async def filtro_de_papel(roles: Iterable[str], base=None) -> dict:
    """Filtro Mongo de `users`: o papel no `role`, nos `additional_roles` ou num UCR."""
    papeis = papeis_equivalentes(roles)
    if not papeis:
        return {}
    ramos: list[dict] = [
        {"role": {"$in": papeis}},
        {"additional_roles": {"$in": papeis}},
    ]
    ids = await ids_com_papel_numa_empresa(papeis, base)
    if ids:
        ramos.append({"id": {"$in": ids}})
    return {"$or": ramos}


async def filtro_de_atribuicao(base=None) -> dict:
    """O filtro de `staff_assignment.assignment_staff_mongo_filter`, com os cargos dos UCRs.

    O cargo PRINCIPAL excluído (master/admin/cliente/parceiro) continua de fora: é a regra do
    Pacote DT, e não muda aqui.
    """
    from services.staff_assignment import (
        ASSIGNMENT_ALLOWED_ROLES,
        ASSIGNMENT_EXCLUDED_PRIMARY_ROLES,
    )

    return {
        "$and": [
            {"role": {"$nin": list(ASSIGNMENT_EXCLUDED_PRIMARY_ROLES)}},
            await filtro_de_papel(ASSIGNMENT_ALLOWED_ROLES, base),
        ]
    }


async def anexar_papeis_das_empresas(users: list[dict], base=None) -> list[dict]:
    """Junta a cada utilizador `company_roles`: os papéis dos seus UCRs válidos.

    É o que a interface lê para pôr a pessoa no Select certo (consultor,
    intermediário, Index) — o `role` principal sozinho não o diz.
    """
    ids = [str(u.get("id")) for u in users or [] if u.get("id")]
    if not ids:
        return list(users or [])
    docs = await _ler_ucrs(
        base, {**UCR_VALIDO, "user_id": {"$in": ids}}, {"_id": 0, "user_id": 1, "role": 1},
    )
    por_id: dict[str, set[str]] = {}
    for d in docs:
        papel = _norm(d.get("role"))
        if papel and d.get("user_id"):
            por_id.setdefault(str(d["user_id"]), set()).add(papel)
    return [
        {**u, "company_roles": sorted(por_id.get(str(u.get("id")), set()))}
        for u in users
    ]


async def tem_papel(user_id: str, roles: Iterable[str], base=None) -> bool:
    """O utilizador tem um destes papéis (principal, adicional ou num UCR válido)?"""
    papeis = papeis_equivalentes(roles)
    if not user_id or not papeis:
        return False
    bd = _base(base)
    user = await bd.users.find_one(
        {"id": user_id}, {"_id": 0, "role": 1, "additional_roles": 1},
    )
    if not user:
        return False
    proprios = {_norm(user.get("role")), *(_norm(r) for r in user.get("additional_roles") or [])}
    if proprios & set(papeis):
        return True
    ucr = await _ler_ucrs(
        base, {**UCR_VALIDO, "user_id": user_id, "role": {"$in": papeis}}, {"_id": 0, "user_id": 1},
    )
    return bool(ucr)


__all__ = [
    "PAPEIS_DO_INDEX",
    "anexar_papeis_das_empresas",
    "filtro_de_atribuicao",
    "filtro_de_papel",
    "ids_com_papel_numa_empresa",
    "papeis_equivalentes",
    "tem_papel",
]

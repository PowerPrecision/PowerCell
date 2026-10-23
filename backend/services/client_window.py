"""«Janela, não porta» — partilhar um processo abre aquele negócio, não o cliente todo (Lote 6).

A REGRA
=======
Quando a empresa A partilha com a empresa B UM processo de um cliente, B passa a ver
**esse processo** (e, para o trabalhar, os dados do titular que ele precisa). Não passa a
ver os outros processos desse cliente, a actividade deles, nem o acesso do cliente ao Portal.

O DEFEITO QUE ISTO FECHA
========================
`GET /clients/{id}` abria para a rede convidada (a ficha do titular de um processo partilhado
tem de abrir), mas depois de aberto devolvia o cliente INTEIRO: todos os processos dele
(`process_ids` + 2.º titular), a última actividade de qualquer um deles, e o **código de acesso
e o magic link do Portal do cliente** — que dão acesso a tudo o que o cliente vê. A mesma forma
de defeito tinha o `PUT` (propagava a edição para todos os processos do cliente, também os de
fora da janela) e a listagem «Clientes Registados» (as linhas saíam dos processos visíveis, e
um processo partilhado trazia a ficha — com os dados pessoais — de um cliente de outra rede).

DUAS PERGUNTAS, DUAS FUNÇÕES
============================
* `ids_dos_processos_visiveis` — destes processos, quais o utilizador vê? (a JANELA)
* `e_visitante_do_cliente` — o cliente é de outra rede (só o vejo por causa de um processo
  partilhado)? Um visitante não recebe o que é do dono: acesso ao Portal, em particular.

A conta Master atravessa tudo (abrir por id é global para ela; ver `by_id_scope`).
"""
from __future__ import annotations

import logging
from typing import Iterable, Optional

from database import db
from services.role_scope import fronteira_levantada
from services.tenant_network import (
    CAMPO_REDE,
    CAMPO_REDES_PARCEIRAS,
    PROJECCAO_DO_CARIMBO,
    build_network_scope_condition,
    build_process_scope_condition,
    com_isolamento,
    documento_no_ambito,
    resolve_tenant_scope,
)

logger = logging.getLogger(__name__)


def _ids(valores: Iterable) -> list[str]:
    return list(dict.fromkeys(str(v).strip() for v in valores or [] if v and str(v).strip()))


def condicao_do_visitante(redes: Iterable[str]) -> dict:
    """A janela de um VISITANTE: só o que a sua rede recebeu ou lhe pertence, de forma EXPLÍCITA.

    Lote 7.2 (Out 2026). O âmbito de processos tem um ramo para «a pilha por carimbar» (processos
    antigos, sem rede nem empresa), que em dev/QA — ou numa produção sem a rede de omissão definida —
    vale para TODAS as redes. Para o dono é a tolerância do legado; para um VISITANTE era uma porta:
    os processos antigos do cliente, em estados fechados (Desistência, Concluído…) por serem os mais
    velhos e por isso os que nunca foram carimbados, entravam na janela. A regra do visitante é cega
    ao estado e ao legado: só entra um processo cuja rede está entre as redes do visitante
    (carimbo explícito) ou cuja lista de redes convidadas as inclui (partilha explícita).
    """
    lista = sorted({str(r).strip() for r in redes if r and str(r).strip()})
    if not lista:
        return CONDICAO_IMPOSSIVEL_DO_VISITANTE
    return {"$or": [{CAMPO_REDE: {"$in": lista}}, {CAMPO_REDES_PARCEIRAS: {"$in": lista}}]}


#: Sem redes não há janela. `_id: None` não casa com nenhum documento (todos têm `_id`).
CONDICAO_IMPOSSIVEL_DO_VISITANTE = {"_id": None}


async def ids_dos_processos_visiveis(
    user: dict,
    candidatos: Iterable[str],
    *,
    client_id: Optional[str] = None,
    cliente: Optional[dict] = None,
) -> list[str]:
    """Dos processos `candidatos` (e dos que apontam para `client_id`), os que `user` vê.

    A condição é a de PROCESSOS (conta a rede convidada): é exactamente a janela. Falha
    FECHADA: se a base de dados não responde, a janela é vazia e não «tudo».

    Com `cliente` (o documento do cliente) um VISITANTE — cliente de outra rede que só se
    alcança por partilha — recebe a janela ESTRITA (`condicao_do_visitante`): só os processos
    partilhados com a sua rede, ou carimbados com ela, seja qual for o estado de cada um.
    """
    ids = _ids(candidatos)
    master = fronteira_levantada(user, por_conta=True)

    ramos: list[dict] = []
    if ids:
        ramos.append({"id": {"$in": ids}})
    if client_id:
        ramos.append({"client_id": client_id})
        ramos.append({"second_client_id": client_id})
    if not ramos:
        return []

    try:
        base = {"$or": ramos}
        if master:
            consulta = base  # a conta Master não tem janela: tudo o que aponta para o cliente
        else:
            scope = await resolve_tenant_scope(user)
            if cliente is not None and await e_visitante_do_cliente(cliente, user):
                consulta = com_isolamento(condicao_do_visitante(scope.network_ids), base)
            else:
                consulta = com_isolamento(build_process_scope_condition(scope), base)
        encontrados = await db.processes.find(consulta, {"_id": 0, "id": 1}).to_list(500)
    except Exception as exc:  # noqa: BLE001 - numa fronteira, a dúvida fecha
        logger.warning("[JANELA] Não foi possível resolver os processos visíveis (%s): janela vazia.", exc)
        return []
    return _ids(p.get("id") for p in encontrados)


def e_visitante_no_ambito(cliente: Optional[dict], user: dict, scope) -> bool:
    """`e_visitante_do_cliente` SEM I/O: o âmbito já está resolvido (`scope`).

    Existe para as listagens. Resolver o âmbito por cliente (uma ida à base de dados — duas, com as
    empresas) fazia «Clientes Registados» custar trinta mil pedidos a uma lista de quinze mil clientes:
    mais de meio minuto, num servidor local. Quem percorre uma lista resolve o âmbito UMA vez.
    """
    if not cliente or fronteira_levantada(user, por_conta=True):
        return False
    from services.by_id_scope import cliente_e_da_pool

    if cliente_e_da_pool(cliente):
        return False
    return not documento_no_ambito(cliente, scope)


async def e_visitante_do_cliente(cliente: Optional[dict], user: dict) -> bool:
    """O cliente é de OUTRA rede e eu só chego a ele por um processo partilhado?

    A Pool (sem carimbo e sem processos) não é «de outra rede»: é de quem a reivindicar.
    O Master nunca é visitante.
    """
    if not cliente or fronteira_levantada(user, por_conta=True):
        return False
    return e_visitante_no_ambito(cliente, user, await resolve_tenant_scope(user))


def processo_na_janela_do_visitante(processo: Optional[dict], redes: Iterable[str]) -> bool:
    """Gémeo em Python do `condicao_do_visitante`: carimbo explícito ou partilha explícita."""
    minhas = {str(r).strip() for r in redes if r and str(r).strip()}
    if not minhas or not processo:
        return False
    if str(processo.get(CAMPO_REDE) or "").strip() in minhas:
        return True
    convidadas = processo.get(CAMPO_REDES_PARCEIRAS)
    if isinstance(convidadas, (list, tuple, set)):
        return bool({str(r).strip() for r in convidadas if r} & minhas)
    return bool(convidadas) and str(convidadas).strip() in minhas


async def so_o_que_a_janela_deixa_ver(processos: list[dict], user: dict) -> list[dict]:
    """Das linhas de processos de uma listagem, tira as de clientes-visitados que a janela não cobre.

    Para as listagens que partem dos PROCESSOS («Clientes Registados»): um cliente de outra rede só
    aparece pelos processos que a minha rede recebeu ou que lhe pertencem, explicitamente; os outros
    processos desse cliente — antigos, sem carimbo, desistidos — não entram. Os clientes que são
    meus (ou da Pool) não mudam. Falha FECHADA: sem ler os clientes, as linhas de clientes
    desconhecidos saem.
    """
    if not processos or fronteira_levantada(user, por_conta=True):
        return processos
    ids = _ids(p.get("client_id") for p in processos)
    if not ids:
        return processos
    try:
        scope = await resolve_tenant_scope(user)
        # Só interessam os clientes que NÃO estão no meu âmbito: um cliente da minha rede nunca é
        # «visitante» e a linha de um cliente que não se conhece também fica. Pedir todos os documentos
        # (milhares, numa carteira grande) para deitar quase todos fora era o grosso do custo: a condição
        # de rede é a gémea em Mongo do predicado `documento_no_ambito` (afirmada por teste de concordância).
        docs = await db.clients.find(
            {"id": {"$in": ids}, "$nor": [build_network_scope_condition(scope)]},
            {"_id": 0, "id": 1, "process_ids": 1, "lead_status": 1, **PROJECCAO_DO_CARIMBO},
        ).to_list(len(ids))
        # o âmbito resolve-se UMA vez (não por cliente): ver `e_visitante_no_ambito`
        visitados = {
            d["id"] for d in docs if d.get("id") and e_visitante_no_ambito(d, user, scope)
        }
        conhecidos = {d.get("id") for d in docs}
    except Exception as exc:  # noqa: BLE001 - numa fronteira, a dúvida fecha
        logger.warning("[JANELA] Não foi possível ler os clientes da listagem (%s): sem linhas de outras redes.", exc)
        return [p for p in processos if not p.get("client_id")]
    redes = scope.network_ids
    return [
        p for p in processos
        if not p.get("client_id")
        or p.get("client_id") not in conhecidos
        or p.get("client_id") not in visitados
        or processo_na_janela_do_visitante(p, redes)
    ]


__all__ = [
    "processo_na_janela_do_visitante",
    "so_o_que_a_janela_deixa_ver",
    "PROJECCAO_DO_CARIMBO",
    "condicao_do_visitante",
    "e_visitante_do_cliente",
    "e_visitante_no_ambito",
    "ids_dos_processos_visiveis",
]

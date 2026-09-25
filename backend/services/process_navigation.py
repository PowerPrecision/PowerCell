"""
Navegação contígua entre processos (Ponto 17).

PORQUÊ: nos Detalhes de um processo o utilizador não tinha forma de
passar ao processo seguinte da listagem de onde veio — tinha de voltar
atrás, encontrar a linha e clicar. Com filtros aplicados isso é uma
volta completa por cada processo revisto.

O FRONTEND resolve o caso comum SEM pedido nenhum: a listagem leva
consigo os ids já ordenados da página aberta. Este módulo existe só
para a FRONTEIRA DA PÁGINA — o item 40 de 40, cujo seguinte vive na
página a seguir e que o frontend não tem em mão.

DUAS REGRAS QUE NÃO SE PODEM PERDER:

1. A query vem de `build_process_list_query`, a MESMA da listagem. Um
   construtor próprio aqui repetiria o defeito do Kanban (Lote 4/5),
   que tinha o seu e ficou de fora do isolamento por Rede durante meses.
   O isolamento multi-tenant entra por `build_tenant_condition`, como em
   `run_get_processes`.

2. A ordenação vem de `sort_process_list`, a MESMA da listagem. Não é um
   detalhe: a listagem NÃO ordena no Mongo, ordena em Python por peso de
   prioridade + ordem do workflow + nome. Uma seta que devolvesse o
   vizinho por ordem natural do Mongo levaria ao processo errado — e um
   vizinho errado é pior do que não haver seta, porque ninguém desconfia.

A projecção é a mais pequena que preserva essa ordenação (ver
`PROCESS_NAV_PROJECTION`): o endpoint devolve DOIS ids, não processos.
"""
from __future__ import annotations

import logging
from typing import Any, Optional, Sequence, Union

from database import db
from services.workflow_phases import carregar_fases, nomes_terminais
from services.process_list_enrichment import (
    load_workflow_status_order,
    sort_process_list,
)
from services.tenant_network import build_tenant_condition

logger = logging.getLogger(__name__)


# Exactamente os campos que `sort_process_list` (e o `get_priority_weight`
# que ela usa) lê, mais o `id`. Nem um a mais: o objectivo do endpoint é
# não trazer processos. Nem um a menos: um campo em falta muda a ordem em
# silêncio e a seta passa a apontar para o processo errado.
#
# Há um teste que prova a equivalência — ordena a lista completa e a lista
# reduzida a esta projecção e exige a MESMA sequência de ids.
PROCESS_NAV_PROJECTION = {
    "_id": 0,
    "id": 1,
    "client_name": 1,
    "client_email": 1,
    "client_phone": 1,
    "status": 1,
    "priority": 1,
    "prioridade": 1,
    "property_value": 1,
    "property_location": 1,
    "created_at": 1,
    "updated_at": 1,
}


def vizinhos_na_lista(ids: Sequence[str], process_id: str) -> dict:
    """
    Vizinhos de `process_id` numa sequência já ordenada de ids.

    Devolve `previous_id`/`next_id` a `None` nos extremos — é assim que o
    frontend sabe que não deve desenhar a seta. `position` é 1-based (é
    o que se mostra ao utilizador: "12 de 348").

    Um processo que não esteja na sequência devolve tudo a `None`: pode
    ter mudado de estado e saído do filtro entre a listagem e o clique, e
    inventar-lhe uma posição seria mentir.
    """
    lista = [i for i in (ids or []) if i]
    total = len(lista)
    try:
        indice = lista.index(process_id)
    except ValueError:
        return {
            "previous_id": None,
            "next_id": None,
            "position": None,
            "total": total,
        }
    return {
        "previous_id": lista[indice - 1] if indice > 0 else None,
        "next_id": lista[indice + 1] if indice < total - 1 else None,
        "position": indice + 1,
        "total": total,
    }


async def run_get_process_neighbours(
    *,
    user: dict,
    role: str,
    process_id: str,
    decrypt_list_fn,
    status: Optional[str] = None,
    search: Optional[str] = None,
    view_mode: Optional[str] = "active_only",
    sort_field: Optional[str] = None,
    sort_order: Optional[str] = "asc",
    show_all: bool = False,
    is_indexed: Optional[bool] = None,
    all_roles: Optional[list] = None,
    mine_only: bool = False,
    company_id: Optional[str] = None,
    assigned_user_id: Optional[str] = None,
    assigned_user_ids: Optional[Union[str, Sequence[str]]] = None,
    assigned_logic: Optional[str] = "OR",
    process_type: Optional[str] = None,
    labels: Optional[Any] = None,
    labels_logic: Optional[str] = "OR",
) -> dict:
    """
    Orquestra GET /processes/{id}/neighbours.

    Raises:
        HTTPException(404): o processo não existe DENTRO deste âmbito.
            404 e não 403 de propósito — distinguir "não existe" de "não
            é teu" confirmaria a existência de um processo de outra Rede.
    """
    from fastapi import HTTPException
    from services.process_list_filters import build_process_list_query

    tenant_condition = await build_tenant_condition(user)

    query = build_process_list_query(
        user,
        role,
        tenant_condition=tenant_condition,
        status=status,
        search=search,
        view_mode=view_mode,
        show_all=bool(show_all),
        is_indexed=is_indexed,
        all_roles=all_roles,
        search_mode="accent",
        mine_only=mine_only,
        company_id=company_id,
        assigned_user_id=assigned_user_id,
        assigned_user_ids=assigned_user_ids,
        assigned_logic=assigned_logic,
        process_type=process_type,
        labels=labels,
        labels_logic=labels_logic,
        terminais=nomes_terminais(await carregar_fases()),
    )

    status_order = await load_workflow_status_order()
    processos = await db.processes.find(query, PROCESS_NAV_PROJECTION).to_list(5000)

    # A listagem desencripta ANTES de ordenar, e a ordenação por
    # "contacto" lê o telefone. Sem este passo a ordem divergiria
    # exactamente nesse caso — o mais difícil de notar.
    processos = decrypt_list_fn(processos, fields_to_decrypt=["client_phone"])

    sort_process_list(
        processos,
        sort_field=sort_field,
        sort_order=sort_order or "asc",
        status_order=status_order,
    )

    ids = [p.get("id") for p in processos if p.get("id")]
    vizinhos = vizinhos_na_lista(ids, process_id)

    if vizinhos["position"] is None:
        raise HTTPException(status_code=404, detail="Processo não encontrado")

    return vizinhos

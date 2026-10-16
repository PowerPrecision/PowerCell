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
    PROJECCAO_DO_CARIMBO,
    build_process_scope_condition,
    com_isolamento,
    documento_no_ambito,
    resolve_tenant_scope,
)

logger = logging.getLogger(__name__)


def _ids(valores: Iterable) -> list[str]:
    return list(dict.fromkeys(str(v).strip() for v in valores or [] if v and str(v).strip()))


async def ids_dos_processos_visiveis(
    user: dict,
    candidatos: Iterable[str],
    *,
    client_id: Optional[str] = None,
) -> list[str]:
    """Dos processos `candidatos` (e dos que apontam para `client_id`), os que `user` vê.

    A condição é a de PROCESSOS (conta a rede convidada): é exactamente a janela. Falha
    FECHADA: se a base de dados não responde, a janela é vazia e não «tudo».
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
            consulta = com_isolamento(build_process_scope_condition(scope), base)
        encontrados = await db.processes.find(consulta, {"_id": 0, "id": 1}).to_list(500)
    except Exception as exc:  # noqa: BLE001 - numa fronteira, a dúvida fecha
        logger.warning("[JANELA] Não foi possível resolver os processos visíveis (%s): janela vazia.", exc)
        return []
    return _ids(p.get("id") for p in encontrados)


async def e_visitante_do_cliente(cliente: Optional[dict], user: dict) -> bool:
    """O cliente é de OUTRA rede e eu só chego a ele por um processo partilhado?

    A Pool (sem carimbo e sem processos) não é «de outra rede»: é de quem a reivindicar.
    O Master nunca é visitante.
    """
    if not cliente or fronteira_levantada(user, por_conta=True):
        return False
    from services.by_id_scope import cliente_e_da_pool

    if cliente_e_da_pool(cliente):
        return False
    scope = await resolve_tenant_scope(user)
    return not documento_no_ambito(cliente, scope)


__all__ = ["PROJECCAO_DO_CARIMBO", "e_visitante_do_cliente", "ids_dos_processos_visiveis"]

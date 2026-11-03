"""Quem pode mudar a equipa de um processo, e de que empresa (regras do Flavio, Nov 2026).

AS REGRAS (decididas com o Flavio em 2026-11-03)
================================================
1. **Quem altera**: a gestão (Master, Admin, CEO, Diretor) e o Intermediário. O Index altera
   SÓ a atribuição do Index — e essa alteração fica no histórico (excepção ao modo invisível,
   para haver controlo). Os outros perfis não alteram (pedem à chefia).
2. **Pelo perfil seleccionado**: conta o perfil EFECTIVO (`get_effective_role_async`), nunca o
   `role` da conta — quem tem vários perfis segue as regras do que tem activo.
3. **A empresa é a fronteira**: consultores, intermediários e direção só se escolhem da empresa
   com que se está a trabalhar (`X-Company-Id`). Num processo partilhado vê-se quem a outra
   empresa atribuiu, mas não se lhe mexe: esses ficam SEMPRE, mesmo que o pedido os omita.
   O Master na vista «Sistema» (sem empresa escolhida) mexe em tudo.
4. O Index é da REDE (Power, Precision e Sistema): o campo Index segue só a fronteira de rede
   (`assignment_network_guard`), não a de empresa.

A pergunta «esta pessoa é da minha empresa?» é a MESMA da lista de atribuição
(`empresas_da_empresa_activa` + `build_users_scope_query`): o que a lista mostra é o que o
servidor aceita.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import HTTPException

logger = logging.getLogger(__name__)

#: Perfis (efectivos) que mudam a equipa de um processo.
PAPEIS_QUE_ALTERAM = frozenset({"master", "admin", "ceo", "diretor", "intermediario", "mediador"})

#: O Index: só o campo Index.
PAPEIS_DO_INDEX = frozenset({"indexacao", "index"})

MENSAGEM_PERFIL = "O seu perfil não altera atribuições. Peça a alteração à chefia."
MENSAGEM_INDEX = "O perfil Index só altera a atribuição do Index."
MENSAGEM_EMPRESA = (
    "Só pode atribuir pessoas da empresa com que está a trabalhar. "
    "As atribuições de outra empresa não se alteram daqui."
)


def _norm(valor) -> str:
    return str(valor or "").strip().lower()


def exigir_quem_pode_alterar(
    papel_efectivo: Optional[str],
    *,
    consultor_ids: Optional[str] = None,
    mediador_ids: Optional[str] = None,
    direcao_ids: Optional[str] = None,
    indexacao_id: Optional[str] = None,
    parceiro_id: Optional[str] = None,
) -> None:
    """403 se o perfil activo não pode fazer ESTE pedido. PURA."""
    papel = _norm(papel_efectivo)
    if papel in PAPEIS_DO_INDEX:
        outros = (consultor_ids, mediador_ids, direcao_ids, parceiro_id)
        if any(v is not None for v in outros):
            raise HTTPException(status_code=403, detail=MENSAGEM_INDEX)
        return
    if papel not in PAPEIS_QUE_ALTERAM:
        raise HTTPException(status_code=403, detail=MENSAGEM_PERFIL)


def e_o_index(papel_efectivo: Optional[str]) -> bool:
    return _norm(papel_efectivo) in PAPEIS_DO_INDEX


async def _condicao_da_minha_empresa(ator: dict, base) -> Optional[dict]:
    """Condição Mongo de `users` para «da empresa de quem pede». ``None`` = sem limite."""
    from services.admin_users_scope import build_users_scope_query, empresas_da_empresa_activa

    ambito = await empresas_da_empresa_activa(ator or {})
    if ambito.sem_fronteira or not ambito.fechado:
        return None
    condicao = await build_users_scope_query(ambito)
    return condicao or None


async def ids_da_minha_empresa(ator: dict, ids, base) -> Optional[set[str]]:
    """Dos `ids`, os que são da empresa de quem pede. ``None`` = sem limite (Master em Sistema)."""
    lista = sorted({str(i) for i in ids if i})
    condicao = await _condicao_da_minha_empresa(ator, base)
    if condicao is None:
        return None
    if not lista:
        return set()
    docs = await base.users.find(
        {"$and": [{"id": {"$in": lista}}, condicao]}, {"_id": 0, "id": 1},
    ).to_list(len(lista))
    return {str(d["id"]) for d in docs if d.get("id")}


def _csv(valor: Optional[str]) -> Optional[list[str]]:
    if valor is None:
        return None
    return [p.strip() for p in str(valor).split(",") if p.strip() and p.strip() != "null"]


async def aplicar_fronteira_de_empresa(
    ator: dict,
    processo: dict,
    pedido: dict[str, Optional[str]],
    base,
) -> dict[str, Optional[str]]:
    """Ajusta os campos de LISTA do pedido à empresa de quem pede.

    `pedido` mapeia o campo do processo (`assigned_consultor_ids`, …) para o CSV pedido (ou None,
    «não mexer»). Devolve o mesmo mapa já com:

    * 403 se se tenta PÔR alguém de outra empresa;
    * os já atribuídos de outra empresa SEMPRE mantidos (num processo partilhado vêem-se, não se
      tiram) — mesmo com o pedido de «limpar tudo».
    """
    pedidos = {campo: _csv(csv) for campo, csv in pedido.items()}
    todos = set()
    for campo, novos in pedidos.items():
        if novos is None:
            continue
        todos.update(novos)
        todos.update(str(i) for i in (processo.get(campo) or []) if i)
    minha = await ids_da_minha_empresa(ator, todos, base)
    if minha is None:
        return dict(pedido)

    saida: dict[str, Optional[str]] = {}
    for campo, novos in pedidos.items():
        if novos is None:
            saida[campo] = None
            continue
        antigos = [str(i) for i in (processo.get(campo) or []) if i]
        alheios = [i for i in antigos if i not in minha]
        intrusos = [i for i in novos if i not in minha and i not in antigos]
        if intrusos:
            logger.warning(
                "[ATRIBUICAO] %s tentou atribuir %d pessoa(s) de outra empresa em %s; recusado.",
                (ator or {}).get("id") or "?", len(intrusos), campo,
            )
            raise HTTPException(status_code=403, detail=MENSAGEM_EMPRESA)
        final = list(dict.fromkeys([*[i for i in novos if i in minha or i in alheios], *alheios]))
        saida[campo] = ",".join(final)
    return saida


__all__ = [
    "MENSAGEM_EMPRESA",
    "MENSAGEM_INDEX",
    "MENSAGEM_PERFIL",
    "PAPEIS_DO_INDEX",
    "PAPEIS_QUE_ALTERAM",
    "aplicar_fronteira_de_empresa",
    "e_o_index",
    "exigir_quem_pode_alterar",
    "ids_da_minha_empresa",
]

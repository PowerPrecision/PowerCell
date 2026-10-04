"""Quadro de visitas + leitura de uma visita.

Extraído de `routes/visits.py`.

LOTE 9 (D-21) — O KANBAN TEM CONSTRUTOR SEPARADO
================================================
E foi por isso que ficou fora de todos os varrimentos anteriores: a
condição do quadro não passa pelo `run_list_visits`. É a lição do
`build_kanban_query` do Lote 5 — **um ponto único para a CONDIÇÃO não
chega; é preciso inventariar as superfícies que LISTAM**, e esta é uma
delas. Hoje as duas derivam do mesmo contexto de acesso e do mesmo
`com_isolamento`, e há um teste a afirmar que a fronteira é a mesma.

E `run_get_visit` era `find_one({"id": visit_id})` e mais nada — o
`require_roles` da rota autoriza o VERBO, não o OBJECTO (o
`run_delete_deadline` do Lote 7). Responde **404 e nunca 403**:
distinguir «não existe» de «não é tua» confirma o id a quem adivinha, e
o legítimo nunca o vê porque a visita aparece-lhe na lista.
"""
from __future__ import annotations

from typing import Optional

from fastapi import HTTPException, Request

from database import db
from services.tenant_access_context import carregar_contexto_de_acesso
from services.tenant_network import com_isolamento
from services.visit_scope import (
    ERRO_VISITA_NAO_ENCONTRADA,
    build_visit_rbac_condition,
    e_papel_de_equipa_nas_visitas,
    pode_ver_visita,
)


async def run_get_visits_kanban(
    user: dict,
    *,
    consultor_id: Optional[str] = None,
    request: Optional[Request] = None,
):
    """Visitas organizadas por estado, dentro do âmbito do utilizador.

    Colunas: solicitada, agendada, concluida, cancelada (+ recusada).
    """
    contexto = await carregar_contexto_de_acesso(
        user, request, e_equipa=e_papel_de_equipa_nas_visitas,
    )

    filtros: list[dict] = []
    if consultor_id:
        filtros.append({"consultor_id": consultor_id})

    rbac = build_visit_rbac_condition(
        user_id=user.get("id"),
        papel=contexto.papel,
        processos_visiveis=contexto.processos,
    )
    if rbac:
        filtros.append(rbac)

    if not filtros:
        query: dict = {}
    elif len(filtros) == 1:
        query = filtros[0]
    else:
        query = {"$and": filtros}

    final = com_isolamento(contexto.condicao_de_rede, query)
    visits = await db.visits.find(
        final, {"_id": 0, "scraped_data.raw_data": 0}
    ).sort("scheduled_date", 1).to_list(200)

    solicitadas = [v for v in visits if v.get("status") == "solicitada"]
    agendadas = [v for v in visits if v.get("status") == "agendada"]
    concluidas = [v for v in visits if v.get("status") == "concluida"]
    canceladas = [v for v in visits if v.get("status") in ("cancelada", "recusada")]

    return {
        "solicitadas": solicitadas,
        "agendadas": agendadas,
        "concluidas": concluidas,
        "canceladas": canceladas,
        "total": len(visits),
    }


async def exigir_visita_acessivel(
    visit_id: str, user: dict, request: Optional[Request] = None
) -> dict:
    """A visita, se este utilizador a puder ver — ou 404.

    Vive aqui e é usada pela leitura E pelas escritas: três cópias da
    mesma resolução divergem na primeira mudança, e a que divergir deixa
    ver ou deixa escrever.
    """
    visit = await db.visits.find_one({"id": visit_id})
    if not visit:
        raise HTTPException(status_code=404, detail=ERRO_VISITA_NAO_ENCONTRADA)

    contexto = await carregar_contexto_de_acesso(
        user, request, e_equipa=e_papel_de_equipa_nas_visitas,
    )
    if not pode_ver_visita(
        visit,
        user_id=user.get("id"),
        papel=contexto.papel,
        redes=contexto.redes,
        processos_visiveis=contexto.processos,
    ):
        raise HTTPException(status_code=404, detail=ERRO_VISITA_NAO_ENCONTRADA)
    return visit


async def run_get_visit(
    visit_id: str, user: dict, request: Optional[Request] = None
):
    """Obtém detalhe de uma visita — se for do âmbito do utilizador."""
    await exigir_visita_acessivel(visit_id, user, request)
    return await db.visits.find_one(
        {"id": visit_id}, {"_id": 0, "scraped_data.raw_data": 0}
    )

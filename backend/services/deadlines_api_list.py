"""Listagens de prazos/eventos — com âmbito de REDE e pelo papel EFECTIVO.

O QUE A AUDITORIA DO LOTE 7 ENCONTROU AQUI
==========================================
1. **`GET /deadlines?process_id=X` filtrava SÓ por `process_id`.** Sem
   verificar que o utilizador pode ver esse processo: qualquer sessão de
   staff lia os prazos de qualquer processo do sistema sabendo o id — de
   outra rede incluída. Um título de prazo diz mais do que parece
   («Escritura Ana Martins — 2.ª hipoteca»).

2. **ADMIN/CEO recebiam `query = {}`** — *todos* os prazos da base de
   dados, de todas as redes. É a forma do `db.tasks` sem filtro de tenant,
   e aqui com uma diferença: a isenção era pelo papel do **JWT**, logo
   valia mesmo quando o perfil activo era outro.

3. **O ramo restrito escapava por acidente.** Filtrava por atribuição, que
   coincide quase sempre com o âmbito — a forma do `run_get_my_tasks`, e
   foi essa metade a funcionar que escondeu a outra.

4. **O papel era o do JWT.** Quem tem perfil base de consultor e entra COMO
   diretor caía no ramo restrito; ao contrário, quem é admin de base
   mantinha a isenção com outro perfil activo. Quarta ocorrência da forma
   do `history._is_stealth_user`.

A REGRA
=======
O âmbito de rede entra em TODAS as consultas, por `com_isolamento` — nunca
escrito à mão aqui, porque uma condição de isolamento repetida em cada
listagem diverge numa delas, e a que divergir devolve dados a mais.
"""
from __future__ import annotations

from typing import Optional

from fastapi import HTTPException, Request

from database import db
from models.auth import UserRole
from models.deadline import DeadlineResponse
from services.deadline_scope import e_papel_de_equipa, e_papel_sem_fronteira
from services.deadlines_api_scope import (
    carregar_contexto_de_acesso,
    condicao_dos_meus_processos,
)
from services.tenant_network import com_isolamento

#: Os eventos PESSOAIS do utilizador — os que não têm processo e por isso
#: nenhuma condição de rede alcança (uma ausência, um bloco de agenda).
#: Sem este ramo, o autor deixava de ver a sua própria marcação.
def _condicao_pessoal(user_id: str) -> list[dict]:
    return [
        {"assigned_user_ids": user_id},
        {"created_by": user_id},
        {"assigned_consultor_id": user_id},
        {"assigned_mediador_id": user_id},
    ]


def _ramo_dos_processos(process_ids) -> dict:
    """`{"process_id": {"$in": [...]}}`, ou uma cláusula que não casa nada.

    `{"process_id": None}` como "nada" era o padrão antigo e é **errado**:
    casa com todos os eventos GERAIS (os que não têm processo), que é o
    contrário do pretendido. Usa-se `$in: []`.
    """
    ids = [str(p) for p in (process_ids or []) if p]
    return {"process_id": {"$in": ids}}


async def run_get_deadlines(
    process_id: Optional[str],
    user: dict,
    request: Optional[Request] = None,
):
    """Obter prazos/eventos do utilizador, dentro do seu âmbito."""
    contexto = await carregar_contexto_de_acesso(user, request)

    if process_id:
        # Lote 7 — A GUARDA QUE FALTAVA. Antes bastava o id.
        if (
            not e_papel_sem_fronteira(contexto.papel)
            and str(process_id) not in contexto.processos
        ):
            raise HTTPException(status_code=404, detail="Processo não encontrado")
        query: dict = {"process_id": process_id}
    elif user.get("role") == UserRole.CLIENTE:
        processes = await db.processes.find(
            {"client_id": user["id"]}, {"id": 1, "_id": 0}
        ).to_list(1000)
        query = _ramo_dos_processos([p.get("id") for p in processes])
    elif e_papel_sem_fronteira(contexto.papel):
        # ADMIN/CEO reconciliam a pilha inteira. O âmbito continua a ser
        # aplicado pelo `com_isolamento` abaixo: para estes perfis a
        # condição de rede já é larga por construção, e não um `{}` escrito
        # à mão que atravessa redes de propósito.
        query = {}
    elif e_papel_de_equipa(contexto.papel):
        # Agenda da EQUIPA: tudo dentro da rede (o `com_isolamento` abaixo).
        query = {}
    else:
        query = {
            "$or": [
                *_condicao_pessoal(user["id"]),
                _ramo_dos_processos(contexto.processos),
            ]
        }

    final = com_isolamento(contexto.condicao_de_rede, query)
    deadlines = await db.deadlines.find(final, {"_id": 0}).to_list(1000)
    return [DeadlineResponse(**d) for d in deadlines]


async def run_get_my_deadlines(user: dict, request: Optional[Request] = None):
    """Prazos abertos a que o utilizador tem acesso (fases terminais fora).

    ADMIN/CEO/ADMINISTRATIVO recebiam `query = {}` aqui também: todos os
    prazos de todas as redes. O âmbito passa a ser o do utilizador, e o
    papel o EFECTIVO.
    """
    # Fases fechadas ditadas pelo motor (ÉPICO 10, ponto 1). "arquivado"
    # (com D) não é fase nenhuma: é um valor legado que nunca existiu no
    # workflow e mantém-se só para não ressuscitar prazos antigos.
    from services.workflow_phases import carregar_fases, nomes_terminais

    FINISHED_STATUS = nomes_terminais(await carregar_fases()) + ["arquivado"]
    contexto = await carregar_contexto_de_acesso(user, request)

    if user.get("role") == UserRole.CLIENTE:
        processes = await db.processes.find({
            "client_id": user["id"],
            "status": {"$nin": FINISHED_STATUS},
        }, {"id": 1, "_id": 0}).to_list(1000)
        query = _ramo_dos_processos([p.get("id") for p in processes])
        final = com_isolamento(contexto.condicao_de_rede, query)
        deadlines = await db.deadlines.find(final, {"_id": 0}).to_list(1000)
        return [DeadlineResponse(**d) for d in deadlines]

    # Os processos ABERTOS que este utilizador vê. O conjunto do contexto
    # já respeita a rede e a atribuição; aqui tira-se o que está fechado.
    consulta_de_processos: dict = {"status": {"$nin": FINISHED_STATUS}}
    if not e_papel_sem_fronteira(contexto.papel):
        if e_papel_de_equipa(contexto.papel):
            consulta_de_processos = com_isolamento(
                contexto.condicao_de_rede, consulta_de_processos,
            )
        else:
            minha = condicao_dos_meus_processos(user.get("id"))
            consulta_de_processos = com_isolamento(
                contexto.condicao_de_rede,
                {"$and": [consulta_de_processos, minha]} if minha
                else consulta_de_processos,
            )
    abertos = await db.processes.find(
        consulta_de_processos, {"id": 1, "_id": 0},
    ).to_list(20000)
    ids_abertos = [p["id"] for p in abertos if p.get("id")]

    # Um evento sem processo é do seu AUTOR: é a válvula que mantém as
    # ausências e os blocos de agenda na lista de quem os criou.
    query = {
        "$or": [
            _ramo_dos_processos(ids_abertos),
            {"process_id": {"$in": [None, ""]}, "created_by": user.get("id")},
        ]
    }
    final = com_isolamento(contexto.condicao_de_rede, query)
    deadlines = await db.deadlines.find(final, {"_id": 0}).to_list(1000)
    return [DeadlineResponse(**d) for d in deadlines]

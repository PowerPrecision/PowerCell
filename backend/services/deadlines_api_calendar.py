"""Calendário geral — eventos enriquecidos, dentro da REDE.

PACOTE DQ — visibilidade por cargo efectivo (X-Active-Role) e empresa activa.

LOTE 7 — DUAS COISAS QUE A AUDITORIA ENCONTROU
==============================================
1. **«Sem empresa → todos os eventos».** O ramo final dizia, em comentário,
   «comportamento legado admin/CEO»: com `deadline_query` vazio, a consulta
   era `{}` — **todos os eventos da base de dados, de todas as redes**. Um
   diretor sem `X-Company-Id` (um atalho antigo, um pedido sem o header) via
   o calendário da Domus, que é uma ilha. Falha ABERTA no sítio onde não
   pode falhar aberta.

2. **O âmbito era só por EMPRESA, e o ramo de legado aceitava a pilha por
   carimbar.** `company_event_or_clauses` inclui
   `{"company_id": {"$in": [None, "", "default"]}}` — e, até este lote, o
   `run_create_deadline` não carimbava a rede e gravava o **NOME** da
   empresa no campo `company_id` (a confusão de 2026-09-21). A combinação é
   a do `build_company_scope_condition` placebo do Lote 4: uma cláusula que
   admite documentos sem marca mais escritores que não marcam = tudo casa.

Hoje a condição de REDE (`build_network_scope_condition`, o ponto único)
envolve sempre a consulta, e o ramo de empresa continua a existir **dentro**
dela: a rede é a fronteira de segurança, a empresa é uma vista.

O enriquecimento resolve os processos por `{"id": {"$in": ...}}` e devolve
`client_name` e `client_email`. É por isso que um evento a mais não é um
incómodo de UI: é o nome e o email de um cliente de outra rede no ecrã.
"""
from __future__ import annotations

from typing import Optional

from fastapi import Request

from database import db
from services.auth import get_active_company_id_async, get_effective_role
from services.deadlines_api_helpers import (
    company_event_or_clauses,
    personal_deadline_or_clauses,
    pick_responsible,
    sees_team_calendar,
)


def _staff_process_or(user_id: str) -> list[dict]:
    return [
        {"assigned_consultor_id": user_id},
        {"consultor_id": user_id},
        {"assigned_mediador_id": user_id},
        {"intermediario_id": user_id},
    ]


async def _process_ids_for_user(user_id: str) -> list[str]:
    docs = await db.processes.find(
        {"$or": _staff_process_or(user_id)},
        {"id": 1, "_id": 0},
    ).to_list(1000)
    return [p["id"] for p in docs if p.get("id")]


async def _process_ids_for_company(company_id: Optional[str]) -> list[str]:
    if not company_id or company_id == "default":
        return []
    docs = await db.processes.find(
        {"$or": [{"company_id": company_id}, {"company": company_id}]},
        {"id": 1, "_id": 0},
    ).to_list(5000)
    return [p["id"] for p in docs if p.get("id")]


#: Só os campos que o enriquecimento usa. Era `{"_id": 0}` — o processo
#: INTEIRO, com o bloco de dados pessoais já desencriptado, para cada linha
#: do calendário. A regra é a do `diagnose_assignment_drift`: ler o que se
#: precisa, nunca o documento todo.
PROJECCAO_DO_PROCESSO = {
    "_id": 0,
    "id": 1,
    "client_id": 1,
    "client_name": 1,
    "client_email": 1,
    "status": 1,
    "assigned_consultor_id": 1,
    "assigned_mediador_id": 1,
}


async def _enrich_calendar_rows(deadlines: list[dict]) -> list[dict]:
    process_ids = [d.get("process_id") for d in deadlines if d.get("process_id")]
    process_map: dict = {}
    if process_ids:
        processes = await db.processes.find(
            {"id": {"$in": list(set(process_ids))}},
            PROJECCAO_DO_PROCESSO,
        ).to_list(2000)
        process_map = {p["id"]: p for p in processes if p.get("id")}

    user_ids: set[str] = set()
    for d in deadlines:
        rid, _ = pick_responsible(d)
        if rid:
            user_ids.add(rid)
        for uid in d.get("assigned_user_ids") or []:
            if uid:
                user_ids.add(uid)
        created = d.get("created_by")
        if created:
            user_ids.add(created)
        consultor = d.get("assigned_consultor_id")
        if consultor:
            user_ids.add(consultor)

    user_map: dict[str, str] = {}
    if user_ids:
        users = await db.users.find(
            {"id": {"$in": list(user_ids)}},
            {"_id": 0, "id": 1, "name": 1},
        ).to_list(500)
        user_map = {u["id"]: (u.get("name") or "") for u in users if u.get("id")}

    result = []
    for d in deadlines:
        process = process_map.get(d.get("process_id"), {}) or {}
        event_type = d.get("type") or "deadline"
        client_name = process.get("client_name") or ""
        if event_type == "absence":
            client_name = client_name or "Ausência"
        elif not client_name:
            client_name = "Evento Geral"

        responsible_id, _ = pick_responsible(d)
        if not responsible_id:
            responsible_id = (
                d.get("assigned_consultor_id")
                or process.get("assigned_consultor_id")
            )
        responsible_name = user_map.get(responsible_id or "", "") or None

        result.append({
            **d,
            "type": event_type,
            "all_day": bool(d.get("all_day")),
            "end_date": d.get("end_date") or None,
            "client_name": client_name,
            # Lote 7 — o `client_id` vai na linha para o calendário poder
            # LIGAR o evento à ficha. Sem ele, o nome do cliente era texto
            # morto: o ecrã dizia de quem era o evento e não havia como
            # chegar lá (e um evento de um cliente da Pool não tem processo
            # para onde navegar).
            "client_id": process.get("client_id") or "",
            "client_email": process.get("client_email", ""),
            "process_status": process.get("status", ""),
            "assigned_consultor_id": (
                d.get("assigned_consultor_id")
                or process.get("assigned_consultor_id")
            ),
            "assigned_mediador_id": (
                d.get("assigned_mediador_id")
                or process.get("assigned_mediador_id")
            ),
            "responsible_id": responsible_id,
            "responsible_name": responsible_name,
            "assigned_user_name": responsible_name,
        })

    return result


async def run_get_calendar_deadlines(
    consultor_id: Optional[str],
    mediador_id: Optional[str],
    user: dict,
    request: Optional[Request] = None,
):
    """Obter eventos para o calendário (enriched with process + responsável).

    PACOTE DQ:
    - diretor / ceo / admin (cargo efectivo no header) → eventos da empresa activa
    - consultor / intermediário → apenas eventos atribuídos a si
    """
    effective_role = user.get("role") or ""
    company_id = user.get("company")
    if request is not None:
        effective_role = get_effective_role(request, user)
        company_id = await get_active_company_id_async(request, user)

    team_view = sees_team_calendar(effective_role, user)
    deadline_query: dict = {}

    # LOTE 7 — a fronteira de REDE, sempre. Não substitui o filtro de
    # empresa (que é uma vista mais estreita): envolve-o.
    from services.deadline_scope import e_papel_sem_fronteira
    from services.tenant_network import (
        build_network_scope_condition,
        com_isolamento,
        resolve_tenant_scope,
    )

    condicao_de_rede = build_network_scope_condition(
        await resolve_tenant_scope(user)
    )

    if team_view:
        company_pids = await _process_ids_for_company(company_id)
        company_clauses = company_event_or_clauses(company_id, company_pids)

        person_id = consultor_id or mediador_id
        if person_id:
            if consultor_id:
                person_processes = await db.processes.find({
                    "$or": [
                        {"assigned_consultor_id": consultor_id},
                        {"consultor_id": consultor_id},
                    ]
                }, {"id": 1, "_id": 0}).to_list(1000)
            else:
                person_processes = await db.processes.find({
                    "$or": [
                        {"assigned_mediador_id": mediador_id},
                        {"intermediario_id": mediador_id},
                    ]
                }, {"id": 1, "_id": 0}).to_list(1000)
            person_pids = [p["id"] for p in person_processes if p.get("id")]
            person_or = personal_deadline_or_clauses(person_id, person_pids)
            if company_clauses:
                deadline_query = {"$and": [{"$or": company_clauses}, {"$or": person_or}]}
            else:
                deadline_query["$or"] = person_or
        elif company_clauses:
            deadline_query["$or"] = company_clauses
        elif not e_papel_sem_fronteira(effective_role):
            # LOTE 7 — era aqui que o calendário falhava ABERTO. Sem
            # empresa activa, `deadline_query` ficava `{}` e a consulta
            # devolvia TODOS os eventos de TODAS as redes (o comentário
            # chamava-lhe "comportamento legado admin/CEO", mas o ramo
            # alcançava qualquer papel de equipa — um diretor sem o header
            # `X-Company-Id` via o calendário da Domus). Falha FECHADA
            # para a vista da equipa: sem empresa, a agenda da equipa é a
            # do próprio. ADMIN/CEO mantêm a vista global por desenho —
            # são eles que reconciliam a pilha.
            my_process_ids = await _process_ids_for_user(user["id"])
            deadline_query["$or"] = personal_deadline_or_clauses(
                user["id"], my_process_ids,
            )
    else:
        my_process_ids = await _process_ids_for_user(user["id"])
        deadline_query["$or"] = personal_deadline_or_clauses(user["id"], my_process_ids)

    final = com_isolamento(condicao_de_rede, deadline_query)
    deadlines = await db.deadlines.find(final, {"_id": 0}).to_list(1000)
    return await _enrich_calendar_rows(deadlines)

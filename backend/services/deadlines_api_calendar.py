"""Calendar deadlines enrichment handler.

Extraído de `routes/deadlines.py`.
PACOTE DQ — visibilidade por cargo efectivo (X-Active-Role) e empresa activa.
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


async def _enrich_calendar_rows(deadlines: list[dict]) -> list[dict]:
    process_ids = [d.get("process_id") for d in deadlines if d.get("process_id")]
    process_map: dict = {}
    if process_ids:
        processes = await db.processes.find(
            {"id": {"$in": list(set(process_ids))}},
            {"_id": 0},
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
        # else: sem empresa → todos os eventos (comportamento legado admin/CEO)
    else:
        my_process_ids = await _process_ids_for_user(user["id"])
        deadline_query["$or"] = personal_deadline_or_clauses(user["id"], my_process_ids)

    deadlines = await db.deadlines.find(deadline_query, {"_id": 0}).to_list(1000)
    return await _enrich_calendar_rows(deadlines)

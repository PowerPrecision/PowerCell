"""Calendar deadlines enrichment handler.

Extraído de `routes/deadlines.py`.
"""
from __future__ import annotations

from typing import Optional

from database import db
from models.auth import UserRole


async def run_get_calendar_deadlines(
    consultor_id: Optional[str],
    mediador_id: Optional[str],
    user: dict,
):
    """Obter eventos para o calendário (enriched with process info)."""
    deadline_query = {}

    if user["role"] in [UserRole.ADMIN, UserRole.CEO]:
        if consultor_id:
            consultor_processes = await db.processes.find({
                "$or": [
                    {"assigned_consultor_id": consultor_id},
                    {"consultor_id": consultor_id},
                ]
            }, {"id": 1, "_id": 0}).to_list(1000)
            consultor_process_ids = [p["id"] for p in consultor_processes]

            deadline_query["$or"] = [
                {"assigned_user_ids": consultor_id},
                {"created_by": consultor_id},
                {"assigned_consultor_id": consultor_id},
                (
                    {"process_id": {"$in": consultor_process_ids}}
                    if consultor_process_ids
                    else {"process_id": None}
                ),
            ]
        elif mediador_id:
            mediador_processes = await db.processes.find({
                "$or": [
                    {"assigned_mediador_id": mediador_id},
                    {"intermediario_id": mediador_id},
                ]
            }, {"id": 1, "_id": 0}).to_list(1000)
            mediador_process_ids = [p["id"] for p in mediador_processes]

            deadline_query["$or"] = [
                {"assigned_user_ids": mediador_id},
                {"created_by": mediador_id},
                {"assigned_mediador_id": mediador_id},
                (
                    {"process_id": {"$in": mediador_process_ids}}
                    if mediador_process_ids
                    else {"process_id": None}
                ),
            ]
    else:
        my_processes = await db.processes.find({
            "$or": [
                {"assigned_consultor_id": user["id"]},
                {"consultor_id": user["id"]},
                {"assigned_mediador_id": user["id"]},
                {"intermediario_id": user["id"]},
            ]
        }, {"id": 1, "_id": 0}).to_list(1000)
        my_process_ids = [p["id"] for p in my_processes]

        deadline_query["$or"] = [
            {"assigned_user_ids": user["id"]},
            {"created_by": user["id"]},
            {"assigned_consultor_id": user["id"]},
            {"assigned_mediador_id": user["id"]},
            (
                {"process_id": {"$in": my_process_ids}}
                if my_process_ids
                else {"process_id": None}
            ),
        ]

    deadlines = await db.deadlines.find(deadline_query, {"_id": 0}).to_list(1000)

    processes = await db.processes.find({}, {"_id": 0}).to_list(1000)
    process_map = {p["id"]: p for p in processes}

    result = []
    for d in deadlines:
        process = process_map.get(d.get("process_id"), {})
        if not process and d.get("process_id"):
            process = await db.processes.find_one(
                {"id": d["process_id"]}, {"_id": 0}
            ) or {}

        result.append({
            **d,
            "client_name": process.get("client_name", "Evento Geral"),
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
        })

    return result

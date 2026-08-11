"""Deadline list / my-deadlines handlers.

Extraído de `routes/deadlines.py`.
"""
from __future__ import annotations

from typing import Optional

from database import db
from models.auth import UserRole
from models.deadline import DeadlineResponse


async def run_get_deadlines(process_id: Optional[str], user: dict):
    """Obter prazos/eventos do utilizador (scoped by role)."""
    query = {}

    if process_id:
        query["process_id"] = process_id
    elif user["role"] == UserRole.CLIENTE:
        processes = await db.processes.find(
            {"client_id": user["id"]}, {"id": 1, "_id": 0}
        ).to_list(1000)
        process_ids = [p["id"] for p in processes]
        query["process_id"] = {"$in": process_ids}
    elif user["role"] in [UserRole.ADMIN, UserRole.CEO]:
        pass
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

        query["$or"] = [
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

    deadlines = await db.deadlines.find(query, {"_id": 0}).to_list(1000)
    return [DeadlineResponse(**d) for d in deadlines]


async def run_get_my_deadlines(user: dict):
    """Obter prazos onde o utilizador tem acesso ao processo."""
    FINISHED_STATUS = ["concluido", "desistido", "cancelado", "arquivado"]

    if user["role"] in [
        UserRole.ADMIN, UserRole.CEO, UserRole.ADMINISTRATIVO,
    ]:
        finished_processes = await db.processes.find(
            {"status": {"$in": FINISHED_STATUS}},
            {"id": 1, "_id": 0},
        ).to_list(10000)
        finished_ids = [p["id"] for p in finished_processes]

        query = {}
        if finished_ids:
            query["process_id"] = {"$nin": finished_ids}

        deadlines = await db.deadlines.find(query, {"_id": 0}).to_list(1000)
    elif user["role"] == UserRole.CLIENTE:
        processes = await db.processes.find({
            "client_id": user["id"],
            "status": {"$nin": FINISHED_STATUS},
        }, {"id": 1, "_id": 0}).to_list(1000)
        process_ids = [p["id"] for p in processes]
        deadlines = await db.deadlines.find(
            {"process_id": {"$in": process_ids}}, {"_id": 0}
        ).to_list(1000)
    else:
        my_processes = await db.processes.find({
            "$and": [
                {"status": {"$nin": FINISHED_STATUS}},
                {"$or": [
                    {"assigned_consultor_id": user["id"]},
                    {"consultor_id": user["id"]},
                    {"assigned_mediador_id": user["id"]},
                    {"intermediario_id": user["id"]},
                ]},
            ]
        }, {"id": 1, "_id": 0}).to_list(1000)
        my_process_ids = [p["id"] for p in my_processes]

        query = {
            "$or": [
                (
                    {"process_id": {"$in": my_process_ids}}
                    if my_process_ids
                    else {"process_id": None}
                ),
                {"created_by": user["id"]},
            ]
        }

        deadlines = await db.deadlines.find(query, {"_id": 0}).to_list(1000)

        filtered_deadlines = []
        for d in deadlines:
            process_id = d.get("process_id")
            if not process_id:
                if d.get("created_by") == user["id"]:
                    filtered_deadlines.append(d)
            elif process_id in my_process_ids:
                filtered_deadlines.append(d)

        deadlines = filtered_deadlines

    return [DeadlineResponse(**d) for d in deadlines]

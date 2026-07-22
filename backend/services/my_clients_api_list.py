"""GET /my-clients list handler.

Extraído de `routes/my_clients.py`.
Reuses enrichment helpers from `process_my_clients` (do not overwrite that module).
"""
from __future__ import annotations

import logging

from fastapi import Request

from database import db
from models.auth import UserRole
from services.my_clients_api_helpers import (
    LEADS_PROJECTION,
    PROCESS_LIST_PROJECTION,
    apply_pre_registo_exclusion,
    build_my_clients_process_query,
    format_lead_row,
    resolve_list_context,
)
from services.process_my_clients import (
    fetch_latest_activity_notes_map,
    fetch_new_documents_map,
    fetch_unread_messages_map,
)

logger = logging.getLogger(__name__)


async def run_get_my_clients(request: Request, user: dict):
    """
    Obter lista de clientes atribuídos ao utilizador actual.

    SINCRONIZAÇÃO COM "Os Meus Processos":
    A query de my-clients deve usar EXATAMENTE o mesmo critério base que
    my-processes (assigned_consultor_ids + is_active + status), para que
    os clientes listados correspondam aos processos visíveis.
    A estes somam-se os Leads (clientes sem processo) criados pelo utilizador.
    """
    user_id, user_email, role, wants_deleted = resolve_list_context(request, user)

    query = build_my_clients_process_query(
        user_id=user_id,
        user_email=user_email,
        role=role,
        wants_deleted=wants_deleted,
    )
    query = apply_pre_registo_exclusion(query)

    processes = await db.processes.find(
        query,
        PROCESS_LIST_PROJECTION,
    ).sort("client_name", 1).limit(100).to_list(100)

    from services.process_service import decrypt_processes_list
    processes = decrypt_processes_list(processes)

    leads = []
    if role in [UserRole.CONSULTOR, UserRole.INTERMEDIARIO]:
        leads_query = {
            "$and": [
                {"created_by": user_id},
                {"is_deleted": {"$ne": True}},
                {"$or": [
                    {"process_ids": {"$exists": False}},
                    {"process_ids": []},
                    {"process_ids": None},
                ]},
                {"$or": [
                    {"lead_status": {"$exists": False}},
                    {"lead_status": "new"},
                ]},
            ]
        }
        leads_cursor = await db.clients.find(
            leads_query,
            LEADS_PROJECTION,
        ).to_list(500)

        from services.encryption import decrypt_clients_list
        leads_cursor = decrypt_clients_list(leads_cursor)

        for lead in leads_cursor:
            leads.append(format_lead_row(lead))

    if processes:
        statuses = await db.workflow_statuses.find({}, {"_id": 0}).to_list(100)
        status_map = {s["name"]: s for s in statuses}
        for p in processes:
            status_info = status_map.get(p.get("status"), {})
            p["status_label"] = status_info.get("label", p.get("status", ""))
            p["status_color"] = status_info.get("color", "#6B7280")

    for process in processes:
        pending_tasks = await db.tasks.find(
            {
                "process_id": process["id"],
                "status": {"$ne": "completed"},
            },
            {"_id": 0, "id": 1, "title": 1, "priority": 1, "due_date": 1},
        ).sort("due_date", 1).limit(5).to_list(5)

        process["pending_tasks"] = len(pending_tasks)
        process["pending_actions"] = [
            {
                "type": "task",
                "title": t.get("title", "Tarefa sem título"),
                "priority": t.get("priority", "medium"),
                "due_date": t.get("due_date"),
            }
            for t in pending_tasks
        ]

    process_ids = [p["id"] for p in processes if p.get("id")]
    unread_map = await fetch_unread_messages_map(db, process_ids)
    new_docs_map = await fetch_new_documents_map(db, process_ids)
    notes_map = await fetch_latest_activity_notes_map(db, process_ids)

    for p in processes:
        pid = p.get("id")
        p["has_unread_messages"] = unread_map.get(pid, False)
        p["has_new_documents"] = new_docs_map.get(pid, False)
        note_info = notes_map.get(pid, {})
        p["latest_activity_note"] = note_info.get("latest_activity_note")
        p["latest_activity_note_at"] = note_info.get("latest_activity_note_at")
        p["latest_activity_note_by"] = note_info.get("latest_activity_note_by")
        p["latest_activity_preview"] = (
            note_info.get("latest_activity_note") if note_info else None
        )

    all_clients = leads + processes
    return {
        "clients": all_clients,
        "total": len(all_clients),
        "leads_count": len(leads),
    }

"""Shared helpers for staff task routes.

Extraído de `routes/tasks.py`. Uses `task_api_*` prefix to avoid colliding
with existing `task_queue.py` / `task_log_service.py` / `scheduled_tasks.py`.
"""
from __future__ import annotations

from typing import List
from datetime import datetime, timezone

from fastapi import HTTPException

from database import db


def block_parceiro(user: dict) -> None:
    """Bloqueia utilizadores com role 'parceiro' de criar tarefas."""
    if user.get("role") == "parceiro":
        raise HTTPException(
            status_code=403,
            detail="Apenas visualização disponível para parceiros. Não é possível criar tarefas."
        )


# Alias matching original private name for call sites that prefer underscore form.
_block_parceiro = block_parceiro


async def get_user_names(user_ids: List[str]) -> dict:
    """Obter nomes dos utilizadores por ID."""
    users = await db.users.find(
        {"id": {"$in": user_ids}},
        {"_id": 0, "id": 1, "name": 1}
    ).to_list(100)
    return {u["id"]: u["name"] for u in users}


async def enrich_task(task: dict) -> dict:
    """Adicionar nomes de utilizadores, processo e info de prazo à tarefa."""
    # Obter nomes dos utilizadores atribuídos
    if task.get("assigned_to"):
        user_names = await get_user_names(task["assigned_to"])
        task["assigned_to_names"] = [user_names.get(uid, "Desconhecido") for uid in task["assigned_to"]]

    # Obter nome do criador
    if task.get("created_by"):
        creator_names = await get_user_names([task["created_by"]])
        task["created_by_name"] = creator_names.get(task["created_by"], "Desconhecido")

    # Obter nome do processo/cliente
    if task.get("process_id"):
        process = await db.processes.find_one(
            {"id": task["process_id"]},
            {"_id": 0, "client_name": 1}
        )
        if process:
            task["process_name"] = process.get("client_name", "")

    # Calcular se está atrasada e dias até vencer
    if task.get("due_date") and not task.get("completed"):
        try:
            due = datetime.fromisoformat(task["due_date"].replace("Z", "+00:00"))
            now = datetime.now(timezone.utc)
            days_diff = (due - now).days
            task["days_until_due"] = days_diff
            task["is_overdue"] = days_diff < 0
        except (ValueError, TypeError):
            task["days_until_due"] = None
            task["is_overdue"] = None
    else:
        task["days_until_due"] = None
        task["is_overdue"] = None

    return task

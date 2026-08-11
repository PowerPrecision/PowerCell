"""Deadline create / update / delete handlers.

Extraído de `routes/deadlines.py`.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import HTTPException

from database import db
from models.auth import UserRole
from models.deadline import DeadlineCreate, DeadlineUpdate, DeadlineResponse
from services.history import log_history
from services.notification_service import send_notification_with_preference_check
from utils.input_sanitization import sanitize_string


async def run_create_deadline(data: DeadlineCreate, user: dict):
    """Criar um novo evento/prazo no calendário."""
    if user["role"] == UserRole.CLIENTE:
        raise HTTPException(
            status_code=403, detail="Clientes não podem criar prazos"
        )

    if data.process_id:
        process = await db.processes.find_one(
            {"id": data.process_id}, {"_id": 0}
        )
        if not process:
            raise HTTPException(
                status_code=404, detail="Processo não encontrado"
            )

    deadline_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    safe_title = sanitize_string(data.title, max_length=300)
    safe_description = sanitize_string(data.description or "", max_length=1000)

    assigned_users = data.assigned_user_ids or []
    if user["id"] not in assigned_users:
        assigned_users.append(user["id"])

    deadline_doc = {
        "id": deadline_id,
        "process_id": data.process_id,
        "title": safe_title,
        "description": safe_description,
        "due_date": data.due_date,
        "priority": data.priority,
        "completed": False,
        "created_by": user["id"],
        "created_at": now,
        "assigned_user_ids": assigned_users,
        "assigned_consultor_id": data.assigned_consultor_id,
        "assigned_mediador_id": data.assigned_mediador_id,
        # PACOTE DH — Agenda: tipo, visibilidade no portal e lembretes.
        "type": data.type,
        "visible_to_client": data.visible_to_client,
        "reminder_time": data.reminder_time,
    }

    await db.deadlines.insert_one(deadline_doc)

    if data.process_id:
        await log_history(
            data.process_id, user, "Criou prazo", "deadline", None, safe_title
        )

    for assigned_id in assigned_users:
        if assigned_id != user["id"]:
            assigned_user = await db.users.find_one(
                {"id": assigned_id}, {"_id": 0}
            )
            if assigned_user:
                await send_notification_with_preference_check(
                    assigned_user["email"],
                    f"Novo Prazo Atribuído: {safe_title}",
                    f"Foi-lhe atribuído um novo prazo por {user['name']}:\n\n"
                    f"Título: {safe_title}\n"
                    f"Data limite: {data.due_date}\n"
                    f"Prioridade: {data.priority}",
                    notification_type="task_assigned",
                )

    return DeadlineResponse(
        **{k: v for k, v in deadline_doc.items() if k != "_id"}
    )


async def run_update_deadline(
    deadline_id: str, data: DeadlineUpdate, user: dict,
):
    """Atualiza um prazo existente."""
    if user["role"] == UserRole.CLIENTE:
        raise HTTPException(
            status_code=403, detail="Clientes não podem editar prazos"
        )

    deadline = await db.deadlines.find_one({"id": deadline_id}, {"_id": 0})
    if not deadline:
        raise HTTPException(status_code=404, detail="Prazo não encontrado")

    update_data = {}
    if data.title is not None:
        update_data["title"] = sanitize_string(data.title, max_length=300)
    if data.description is not None:
        update_data["description"] = sanitize_string(
            data.description, max_length=1000
        )
    if data.due_date is not None:
        update_data["due_date"] = data.due_date
    if data.priority is not None:
        update_data["priority"] = data.priority
    if data.completed is not None:
        update_data["completed"] = data.completed
        if data.completed and deadline.get("process_id"):
            await log_history(
                deadline["process_id"],
                user,
                "Concluiu prazo",
                "deadline",
                deadline["title"],
                "concluído",
            )
    if data.assigned_consultor_id is not None:
        update_data["assigned_consultor_id"] = data.assigned_consultor_id
    if data.assigned_mediador_id is not None:
        update_data["assigned_mediador_id"] = data.assigned_mediador_id

    # PACOTE DH — Bugfix: assigned_user_ids estava no schema mas nunca era persistido no update.
    if data.assigned_user_ids is not None:
        update_data["assigned_user_ids"] = data.assigned_user_ids

    # PACOTE DH — Agenda: novos campos no update parcial.
    if data.type is not None:
        update_data["type"] = data.type
    if data.visible_to_client is not None:
        update_data["visible_to_client"] = data.visible_to_client
    if data.reminder_time is not None:
        update_data["reminder_time"] = data.reminder_time

    if update_data:
        await db.deadlines.update_one(
            {"id": deadline_id}, {"$set": update_data}
        )

    updated = await db.deadlines.find_one({"id": deadline_id}, {"_id": 0})
    return DeadlineResponse(**updated)


async def run_delete_deadline(deadline_id: str, user: dict):
    """Elimina um prazo existente."""
    result = await db.deadlines.delete_one({"id": deadline_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Prazo não encontrado")
    return {"message": "Prazo eliminado"}

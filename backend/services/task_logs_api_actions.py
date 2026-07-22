"""Task logs detail/action handlers.

Extraído de `routes/task_logs.py`.
Do **not** overwrite services/task_log_service.py.
"""
from __future__ import annotations

from fastapi import HTTPException

from database import db
from models.task_log import TaskStatus
from services.task_log_service import task_log_service


async def run_get_task_details(task_id: str, user: dict):
    task = await task_log_service.get_task(task_id)

    if not task:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada")

    if task.user_id != user.get("id") and user.get("role") not in ["admin", "ceo"]:
        raise HTTPException(status_code=403, detail="Acesso não autorizado a esta tarefa")

    return task


async def run_acknowledge_task(task_id: str, user: dict):
    task = await task_log_service.get_task(task_id)

    if not task:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada")

    if task.user_id != user.get("id"):
        raise HTTPException(status_code=403, detail="Acesso não autorizado a esta tarefa")

    success = await task_log_service.acknowledge_task(task_id, user.get("id"))

    if not success:
        raise HTTPException(
            status_code=400,
            detail="Não foi possível confirmar a tarefa"
        )

    return {
        "success": True,
        "message": "Tarefa confirmada",
        "task_id": task_id
    }


async def run_cancel_task(task_id: str, user: dict):
    task = await task_log_service.get_task(task_id)

    if not task:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada")

    if task.user_id != user.get("id") and user.get("role") not in ["admin", "ceo"]:
        raise HTTPException(status_code=403, detail="Acesso não autorizado a esta tarefa")

    if task.status != TaskStatus.PENDING:
        raise HTTPException(
            status_code=400,
            detail=f"Não é possível cancelar uma tarefa em status '{task.status.value}'"
        )

    success = await task_log_service.cancel_task(task_id, user.get("id"))

    if not success:
        raise HTTPException(
            status_code=400,
            detail="Não foi possível cancelar a tarefa"
        )

    return {
        "success": True,
        "message": "Tarefa cancelada",
        "task_id": task_id
    }


async def run_delete_task(task_id: str, user: dict):
    task = await task_log_service.get_task(task_id)

    if not task:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada")

    if task.user_id != user.get("id") and user.get("role") not in ["admin", "ceo"]:
        raise HTTPException(status_code=403, detail="Acesso não autorizado a esta tarefa")

    if task.status in [TaskStatus.PENDING, TaskStatus.PROCESSING]:
        raise HTTPException(
            status_code=400,
            detail="Não é possível eliminar uma tarefa em execução. Cancele primeiro."
        )

    result = await db.task_logs.delete_one(
        {"$or": [{"task_id": task_id}, {"id": task_id}]}
    )

    if result.deleted_count > 0:
        return {
            "success": True,
            "message": "Tarefa eliminada",
            "task_id": task_id
        }

    raise HTTPException(
        status_code=500,
        detail="Erro ao eliminar tarefa"
    )

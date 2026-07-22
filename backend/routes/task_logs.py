"""
====================================================================
ROTAS DE TAREFAS ASSÍNCRONAS (TASKLOG) — thin FastAPI stubs
====================================================================
Logic in services/task_logs_api_*.py.
Do **not** overwrite services/task_log_service.py.
Keep /active before /{task_id}. Prefix /task-logs avoids /tasks collision.
====================================================================
"""
from typing import Optional

from fastapi import APIRouter, Depends, Query

from models.task_log import TaskStatus, TaskType, TaskLogResponse, TaskLogListResponse
from services.auth import get_current_user
from services.task_logs_api_list import run_get_active_tasks, run_list_user_tasks
from services.task_logs_api_actions import (
    run_get_task_details,
    run_acknowledge_task,
    run_cancel_task,
    run_delete_task,
)

router = APIRouter(prefix="/task-logs", tags=["Async Tasks"])


@router.get("/active", response_model=TaskLogListResponse)
async def get_active_tasks(
    user: dict = Depends(get_current_user)
):
    """Retorna todas as tarefas ativas do utilizador."""
    return await run_get_active_tasks(user)


@router.get("", response_model=TaskLogListResponse)
async def list_user_tasks(
    status: Optional[TaskStatus] = Query(None, description="Filtrar por status"),
    task_type: Optional[TaskType] = Query(None, description="Filtrar por tipo"),
    limit: int = Query(50, ge=1, le=100),
    skip: int = Query(0, ge=0),
    user: dict = Depends(get_current_user)
):
    """Lista todas as tarefas do utilizador com filtros opcionais."""
    return await run_list_user_tasks(status, task_type, limit, skip, user)


@router.get("/{task_id}", response_model=TaskLogResponse)
async def get_task_details(
    task_id: str,
    user: dict = Depends(get_current_user)
):
    """Retorna os detalhes de uma tarefa específica."""
    return await run_get_task_details(task_id, user)


@router.post("/{task_id}/acknowledge")
async def acknowledge_task(
    task_id: str,
    user: dict = Depends(get_current_user)
):
    """Marca uma tarefa como visualizada/confirmada pelo utilizador."""
    return await run_acknowledge_task(task_id, user)


@router.delete("/{task_id}/cancel")
async def cancel_task(
    task_id: str,
    user: dict = Depends(get_current_user)
):
    """Cancela uma tarefa pendente."""
    return await run_cancel_task(task_id, user)


@router.delete("/{task_id}")
async def delete_task(
    task_id: str,
    user: dict = Depends(get_current_user)
):
    """Elimina uma tarefa do histórico."""
    return await run_delete_task(task_id, user)

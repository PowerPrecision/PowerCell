"""
Rotas de Tarefas — thin FastAPI stubs.

Logic in services/task_api_*.py (do **not** overwrite task_queue.py /
task_log_service.py / scheduled_tasks.py).
"""
from typing import Optional, List

from fastapi import APIRouter, Depends, Query

from models.task import TaskCreate, TaskUpdate, TaskResponse
from services.auth import get_current_user
from services.task_api_crud import (
    run_create_task,
    run_get_tasks,
    run_get_my_tasks,
    run_get_task,
    run_update_task,
    run_complete_task,
    run_reopen_task,
    run_delete_task,
)
from services.task_api_background import (
    run_get_active_background_tasks,
    run_acknowledge_background_task,
    run_cancel_background_task,
)

router = APIRouter(prefix="/tasks", tags=["Tasks"])


@router.post("", response_model=TaskResponse)
async def create_task(
    task_data: TaskCreate,
    current_user: dict = Depends(get_current_user)
):
    return await run_create_task(task_data, current_user)


@router.get("", response_model=List[TaskResponse])
async def get_tasks(
    process_id: Optional[str] = Query(None, description="Filtrar por processo"),
    user_id: Optional[str] = Query(None, description="Filtrar por utilizador (admin/ceo: 'all' para todos)"),
    assigned_to_me: bool = Query(False, description="Apenas tarefas atribuídas a mim"),
    created_by_me: bool = Query(False, description="Apenas tarefas criadas por mim"),
    include_completed: bool = Query(False, description="Incluir tarefas concluídas"),
    current_user: dict = Depends(get_current_user)
):
    return await run_get_tasks(
        current_user,
        process_id=process_id,
        user_id=user_id,
        assigned_to_me=assigned_to_me,
        created_by_me=created_by_me,
        include_completed=include_completed,
    )


# Static paths before /{task_id}
@router.get("/active")
async def get_active_background_tasks(
    current_user: dict = Depends(get_current_user)
):
    return await run_get_active_background_tasks(current_user)


@router.get("/my-tasks", response_model=List[TaskResponse])
async def get_my_tasks(
    include_completed: bool = Query(False),
    current_user: dict = Depends(get_current_user)
):
    return await run_get_my_tasks(current_user, include_completed=include_completed)


@router.post("/{task_id}/acknowledge")
async def acknowledge_background_task(
    task_id: str,
    current_user: dict = Depends(get_current_user)
):
    return await run_acknowledge_background_task(task_id, current_user)


@router.delete("/{task_id}/cancel")
async def cancel_background_task(
    task_id: str,
    current_user: dict = Depends(get_current_user)
):
    return await run_cancel_background_task(task_id, current_user)


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(
    task_id: str,
    current_user: dict = Depends(get_current_user)
):
    return await run_get_task(task_id, current_user)


@router.put("/{task_id}", response_model=TaskResponse)
async def update_task(
    task_id: str,
    task_data: TaskUpdate,
    current_user: dict = Depends(get_current_user)
):
    return await run_update_task(task_id, task_data, current_user)


@router.put("/{task_id}/complete", response_model=TaskResponse)
async def complete_task(
    task_id: str,
    current_user: dict = Depends(get_current_user)
):
    return await run_complete_task(task_id, current_user)


@router.put("/{task_id}/reopen", response_model=TaskResponse)
async def reopen_task(
    task_id: str,
    current_user: dict = Depends(get_current_user)
):
    return await run_reopen_task(task_id, current_user)


@router.delete("/{task_id}")
async def delete_task(
    task_id: str,
    current_user: dict = Depends(get_current_user)
):
    return await run_delete_task(task_id, current_user)

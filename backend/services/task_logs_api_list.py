"""Task logs active/list handlers.

Extraído de `routes/task_logs.py`.
Do **not** overwrite services/task_log_service.py.
"""
from __future__ import annotations

from typing import Optional

from models.task_log import TaskStatus, TaskType, TaskLogListResponse
from services.task_log_service import task_log_service


async def run_get_active_tasks(user: dict):
    user_id = user.get("id")

    tasks = await task_log_service.get_active_tasks(user_id)

    active_count = sum(
        1 for t in tasks
        if t.status in [TaskStatus.PENDING, TaskStatus.PROCESSING]
    )
    completed_unacknowledged = sum(
        1 for t in tasks
        if t.status in [TaskStatus.COMPLETED, TaskStatus.FAILED] and not t.acknowledged_at
    )

    return TaskLogListResponse(
        tasks=tasks,
        total=len(tasks),
        active_count=active_count,
        completed_unacknowledged=completed_unacknowledged
    )


async def run_list_user_tasks(
    status: Optional[TaskStatus],
    task_type: Optional[TaskType],
    limit: int,
    skip: int,
    user: dict,
):
    user_id = user.get("id")

    tasks, total = await task_log_service.get_user_tasks(
        user_id,
        status=status,
        task_type=task_type,
        limit=limit,
        skip=skip
    )

    active_count = sum(
        1 for t in tasks
        if t.status in [TaskStatus.PENDING, TaskStatus.PROCESSING]
    )
    completed_unacknowledged = sum(
        1 for t in tasks
        if t.status in [TaskStatus.COMPLETED, TaskStatus.FAILED] and not t.acknowledged_at
    )

    return TaskLogListResponse(
        tasks=tasks,
        total=total,
        active_count=active_count,
        completed_unacknowledged=completed_unacknowledged
    )

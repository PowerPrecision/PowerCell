"""
Admin AI routes — thin FastAPI stubs.

Logic in services/admin_ai_*.py.
Do **not** create services/admin_ai.py (route module name).
Do **not** overwrite admin_ai_data.py (training/import logs).
"""
from fastapi import APIRouter, Depends

from services.auth import require_management
from services.admin_ai_config import (
    run_get_ai_configuration,
    run_update_ai_configuration,
    run_get_ai_report_recipients,
    run_update_ai_report_recipients,
    run_get_ai_report_config,
    run_update_ai_report_config,
)
from services.admin_ai_models import (
    run_list_ai_models,
    run_create_ai_model,
    run_update_ai_model,
    run_delete_ai_model,
)
from services.admin_ai_tasks import (
    run_list_ai_tasks,
    run_create_ai_task,
    run_update_ai_task,
    run_delete_ai_task,
)
from services.admin_ai_cache import (
    run_get_cache_settings,
    run_update_cache_settings,
)
from services.admin_ai_usage import (
    run_get_ai_usage_summary,
    run_get_ai_usage_by_task,
    run_get_ai_usage_by_model,
    run_get_ai_usage_trend,
    run_get_ai_usage_logs,
    run_get_current_ai_weekly_report,
    run_generate_ai_weekly_report,
    run_get_ai_weekly_report_history,
)

router = APIRouter(prefix="/admin", tags=["Admin - AI"])


@router.get("/ai-config")
async def get_ai_configuration(user: dict = Depends(require_management())):
    return await run_get_ai_configuration(user)


@router.put("/ai-config")
async def update_ai_configuration(
    config: dict,
    user: dict = Depends(require_management()),
):
    return await run_update_ai_configuration(config, user)


@router.get("/ai-models")
async def list_ai_models(user: dict = Depends(require_management())):
    return await run_list_ai_models(user)


@router.post("/ai-models")
async def create_ai_model(
    key: str,
    name: str,
    provider: str,
    model_id: str,
    description: str = "",
    cost_per_1k_input: float = 0.0,
    cost_per_1k_output: float = 0.0,
    max_tokens: int = 4096,
    user: dict = Depends(require_management()),
):
    return await run_create_ai_model(
        key, name, provider, model_id,
        description=description,
        cost_per_1k_input=cost_per_1k_input,
        cost_per_1k_output=cost_per_1k_output,
        max_tokens=max_tokens,
        user=user,
    )


@router.put("/ai-models/{model_key}")
async def update_ai_model(
    model_key: str,
    name: str = None,
    description: str = None,
    cost_per_1k_input: float = None,
    cost_per_1k_output: float = None,
    is_active: bool = None,
    user: dict = Depends(require_management()),
):
    return await run_update_ai_model(
        model_key,
        name=name,
        description=description,
        cost_per_1k_input=cost_per_1k_input,
        cost_per_1k_output=cost_per_1k_output,
        is_active=is_active,
        user=user,
    )


@router.delete("/ai-models/{model_key}")
async def delete_ai_model(
    model_key: str,
    user: dict = Depends(require_management()),
):
    return await run_delete_ai_model(model_key, user=user)


@router.get("/ai-tasks")
async def list_ai_tasks(user: dict = Depends(require_management())):
    return await run_list_ai_tasks(user)


@router.post("/ai-tasks")
async def create_ai_task(
    key: str,
    description: str,
    default_model: str,
    user: dict = Depends(require_management()),
):
    return await run_create_ai_task(key, description, default_model, user=user)


@router.put("/ai-tasks/{task_key}")
async def update_ai_task(
    task_key: str,
    description: str = None,
    default_model: str = None,
    user: dict = Depends(require_management()),
):
    return await run_update_ai_task(
        task_key, description=description, default_model=default_model, user=user
    )


@router.delete("/ai-tasks/{task_key}")
async def delete_ai_task(
    task_key: str,
    user: dict = Depends(require_management()),
):
    return await run_delete_ai_task(task_key, user=user)


@router.get("/cache-settings")
async def get_cache_settings(user: dict = Depends(require_management())):
    return await run_get_cache_settings(user)


@router.put("/cache-settings")
async def update_cache_settings(
    cache_limit: int = None,
    notify_at_percentage: int = None,
    user: dict = Depends(require_management()),
):
    return await run_update_cache_settings(
        cache_limit=cache_limit,
        notify_at_percentage=notify_at_percentage,
        user=user,
    )


@router.get("/ai-usage/summary")
async def get_ai_usage_summary(
    period: str = "month",
    task: str = None,
    model: str = None,
    user: dict = Depends(require_management()),
):
    return await run_get_ai_usage_summary(period, task, model, user=user)


@router.get("/ai-usage/by-task")
async def get_ai_usage_by_task(
    period: str = "month",
    user: dict = Depends(require_management()),
):
    return await run_get_ai_usage_by_task(period, user=user)


@router.get("/ai-usage/by-model")
async def get_ai_usage_by_model(
    period: str = "month",
    user: dict = Depends(require_management()),
):
    return await run_get_ai_usage_by_model(period, user=user)


@router.get("/ai-usage/trend")
async def get_ai_usage_trend(
    days: int = 30,
    user: dict = Depends(require_management()),
):
    return await run_get_ai_usage_trend(days, user=user)


@router.get("/ai-usage/logs")
async def get_ai_usage_logs(
    limit: int = 50,
    task: str = None,
    user: dict = Depends(require_management()),
):
    return await run_get_ai_usage_logs(limit, task, user=user)


@router.get("/ai-report-recipients")
async def get_ai_report_recipients(user: dict = Depends(require_management())):
    return await run_get_ai_report_recipients(user)


@router.post("/ai-report-recipients")
async def update_ai_report_recipients(
    data: dict,
    user: dict = Depends(require_management()),
):
    return await run_update_ai_report_recipients(data, user)


@router.get("/ai-report-config")
async def get_ai_report_config(user: dict = Depends(require_management())):
    return await run_get_ai_report_config(user)


@router.put("/ai-report-config")
async def update_ai_report_config(
    data: dict,
    user: dict = Depends(require_management()),
):
    return await run_update_ai_report_config(data, user)


@router.get("/ai-weekly-report")
async def get_current_ai_weekly_report(
    user: dict = Depends(require_management()),
):
    return await run_get_current_ai_weekly_report(user=user)


@router.post("/ai-weekly-report/generate")
async def generate_ai_weekly_report(
    user: dict = Depends(require_management()),
):
    return await run_generate_ai_weekly_report(user=user)


@router.get("/ai-weekly-report/history")
async def get_ai_weekly_report_history(
    limit: int = 10,
    user: dict = Depends(require_management()),
):
    return await run_get_ai_weekly_report_history(limit, user=user)

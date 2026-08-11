"""Admin AI usage tracking + weekly report handlers.

Extraído de `routes/admin_ai.py`. Prefer `admin_ai_usage` / `admin_ai_*` —
do **not** create `services/admin_ai.py` or overwrite `admin_ai_data.py` /
`ai_usage_tracker.py` (core tracker).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from database import db


async def run_get_ai_usage_summary(
    period: str = "month",
    task: Optional[str] = None,
    model: Optional[str] = None,
    user: Optional[dict] = None,
):
    """Obtém resumo de uso de IA."""
    from services.ai_usage_tracker import ai_usage_tracker
    return await ai_usage_tracker.get_usage_summary(period, task, model)


async def run_get_ai_usage_by_task(period: str = "month", user: Optional[dict] = None):
    """Obtém uso agregado por tarefa."""
    from services.ai_usage_tracker import ai_usage_tracker
    return await ai_usage_tracker.get_usage_by_task(period)


async def run_get_ai_usage_by_model(period: str = "month", user: Optional[dict] = None):
    """Obtém uso agregado por modelo."""
    from services.ai_usage_tracker import ai_usage_tracker
    return await ai_usage_tracker.get_usage_by_model(period)


async def run_get_ai_usage_trend(days: int = 30, user: Optional[dict] = None):
    """Obtém tendência diária de uso."""
    from services.ai_usage_tracker import ai_usage_tracker
    return await ai_usage_tracker.get_daily_trend(days)


async def run_get_ai_usage_logs(
    limit: int = 50,
    task: Optional[str] = None,
    user: Optional[dict] = None,
):
    """Obtém logs recentes de chamadas à IA."""
    from services.ai_usage_tracker import ai_usage_tracker
    return await ai_usage_tracker.get_recent_logs(limit, task)


async def run_get_current_ai_weekly_report(user: Optional[dict] = None) -> dict:
    """Obtém o último relatório semanal de IA."""
    from services.ai_usage_tracker import ai_usage_tracker

    try:
        last_report = await db.ai_weekly_reports.find_one(
            {},
            {"_id": 0},
            sort=[("generated_at", -1)],
        )

        if last_report:
            return {"success": True, "report": last_report}

        usage_summary = await ai_usage_tracker.get_usage_summary("week")
        by_task = await ai_usage_tracker.get_usage_by_task("week")
        by_model = await ai_usage_tracker.get_usage_by_model("week")

        report = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "period": "last_7_days",
            "usage_summary": usage_summary,
            "by_task": by_task,
            "by_model": by_model,
        }

        return {"success": True, "report": report}

    except Exception as e:
        return {"success": True, "report": None, "message": str(e)}


async def run_generate_ai_weekly_report(user: Optional[dict] = None) -> dict:
    """Gera relatório semanal de IA manualmente."""
    from services.ai_usage_tracker import ai_usage_tracker

    try:
        usage_summary = await ai_usage_tracker.get_usage_summary("week")
        by_task = await ai_usage_tracker.get_usage_by_task("week")
        by_model = await ai_usage_tracker.get_usage_by_model("week")

        report = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "period": "last_7_days",
            "usage_summary": usage_summary,
            "by_task": by_task,
            "by_model": by_model,
        }

        report["id"] = str(uuid.uuid4())
        await db.ai_weekly_reports.insert_one(report)
        report.pop("_id", None)

        return {"success": True, "report": report}

    except Exception as e:
        return {"success": False, "error": str(e)}


async def run_get_ai_weekly_report_history(
    limit: int = 10,
    user: Optional[dict] = None,
) -> dict:
    """Obtém histórico de relatórios semanais."""
    reports = await db.ai_weekly_reports.find(
        {},
        {"_id": 0},
    ).sort("generated_at", -1).limit(limit).to_list(limit)

    return {"reports": reports, "total": len(reports)}

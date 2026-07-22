"""GDPR read endpoints (statistics, eligible, audit, config).

Extraído de `routes/gdpr.py`.
Do **not** overwrite services/gdpr.py.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Optional

from database import db
from services.gdpr import (
    get_gdpr_statistics,
    find_processes_for_anonymization,
    gdpr_config,
)


async def run_get_statistics():
    stats = await get_gdpr_statistics()
    return {
        "success": True,
        "data": stats
    }


async def run_get_eligible_processes(retention_days: Optional[int], limit: int):
    processes = await find_processes_for_anonymization(retention_days, limit)

    return {
        "success": True,
        "count": len(processes),
        "retention_days": retention_days or gdpr_config.retention_period_days,
        "processes": processes
    }


async def run_get_audit_log(days: int, action: Optional[str], limit: int):
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    query = {"timestamp": {"$gte": cutoff}}
    if action:
        query["action"] = action

    audit_entries = await db.gdpr_audit.find(
        query,
        {"_id": 0}
    ).sort("timestamp", -1).limit(limit).to_list(limit)

    return {
        "success": True,
        "count": len(audit_entries),
        "period_days": days,
        "entries": audit_entries
    }


async def run_get_gdpr_config():
    return {
        "success": True,
        "config": {
            "retention_period_days": gdpr_config.retention_period_days,
            "eligible_statuses": gdpr_config.eligible_statuses,
            "batch_size": gdpr_config.batch_size,
            "dry_run_mode": gdpr_config.dry_run
        }
    }

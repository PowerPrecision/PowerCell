"""AI import logs list/stats handlers.

Extraído de `routes/ai_import_logs.py`.
Do **not** overwrite services/admin_ai_data.py.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Optional

from database import db


async def run_list_ai_import_logs(
    page: int,
    limit: int,
    status: Optional[str],
    process_id: Optional[str],
    search: Optional[str],
):
    query = {}

    if status:
        query["status"] = status

    if process_id:
        query["process_id"] = process_id

    if search:
        query["client_name"] = {"$regex": search, "$options": "i"}

    total = await db.ai_import_logs.count_documents(query)

    skip = (page - 1) * limit
    logs = await db.ai_import_logs.find(
        query,
        {
            "_id": 0,
            "id": 1,
            "process_id": 1,
            "client_name": 1,
            "created_at": 1,
            "created_by_name": 1,
            "status": 1,
            "total_documents": 1,
            "success_count": 1,
            "error_count": 1,
            "partial_count": 1,
            "duration_ms": 1
        }
    ).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)

    return {
        "logs": logs,
        "total": total,
        "page": page,
        "limit": limit,
        "total_pages": (total + limit - 1) // limit
    }


async def run_get_ai_import_stats(days: int):
    since_date = datetime.now(timezone.utc) - timedelta(days=days)

    pipeline = [
        {"$match": {"created_at": {"$gte": since_date.isoformat()}}},
        {"$group": {
            "_id": None,
            "total_imports": {"$sum": 1},
            "total_documents": {"$sum": "$total_documents"},
            "total_success": {"$sum": "$success_count"},
            "total_errors": {"$sum": "$error_count"},
            "avg_duration_ms": {"$avg": "$duration_ms"}
        }}
    ]

    result = await db.ai_import_logs.aggregate(pipeline).to_list(1)

    if result:
        stats = result[0]
        del stats["_id"]
        stats["success_rate"] = (
            round(stats["total_success"] / stats["total_documents"] * 100, 1)
            if stats["total_documents"] > 0 else 0
        )
        return stats

    return {
        "total_imports": 0,
        "total_documents": 0,
        "total_success": 0,
        "total_errors": 0,
        "avg_duration_ms": 0,
        "success_rate": 0
    }

"""GET /my-clients/stats handler.

Extraído de `routes/my_clients.py`.
"""
from __future__ import annotations

from database import db
from services.my_clients_api_helpers import build_my_clients_stats_query


async def run_get_my_clients_stats(user: dict):
    """Obter estatísticas dos clientes do utilizador."""
    user_id = user["id"]
    user_email = user.get("email", "")
    role = user["role"]

    query = build_my_clients_stats_query(
        user_id=user_id,
        user_email=user_email,
        role=role,
    )

    pipeline = [
        {"$match": query},
        {"$group": {"_id": "$status", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]

    status_counts = await db.processes.aggregate(pipeline).to_list(20)
    total = sum(s["count"] for s in status_counts)

    process_ids = [
        p["id"] async for p in db.processes.find(query, {"_id": 0, "id": 1})
    ]
    pending_tasks = await db.tasks.count_documents({
        "process_id": {"$in": process_ids},
        "status": {"$ne": "completed"},
    }) if process_ids else 0

    return {
        "total_clients": total,
        "by_status": {s["_id"]: s["count"] for s in status_counts},
        "pending_tasks": pending_tasks,
    }

"""Alerts notifications handlers.

Extraído de `routes/alerts.py`.
Do **not** overwrite services/alerts.py — use alerts_api_*.
"""
from __future__ import annotations

from fastapi import HTTPException

from database import db
from models.auth import UserRole


async def run_get_notifications(unread_only: bool, user: dict):
    """Obter notificações do sistema com regras de visibilidade por role."""
    query = {}

    if unread_only:
        query["read"] = False

    if user["role"] not in [UserRole.ADMIN, UserRole.CEO, UserRole.DIRETOR]:
        or_conditions = [
            {"assigned_consultor_id": user["id"]},
            {"consultor_id": user["id"]},
            {"assigned_mediador_id": user["id"]},
            {"intermediario_id": user["id"]},
            {"assigned_indexacao_id": user["id"]}
        ]

        processes = await db.processes.find({
            "$or": or_conditions
        }, {"id": 1, "_id": 0}).to_list(1000)
        process_ids = [p["id"] for p in processes]

        query["$and"] = [
            {"$or": [
                {"process_id": {"$in": process_ids}},
                {"process_id": None}
            ]},
            {"type": {"$ne": "new_registration"}}
        ]

    notifications = await db.notifications.find(query, {"_id": 0}).sort("created_at", -1).to_list(100)

    unread_query = {**query, "read": False}
    total_unread = await db.notifications.count_documents(unread_query)

    return {
        "notifications": notifications,
        "total": len(notifications),
        "unread": total_unread
    }


async def run_mark_notification_read(notification_id: str):
    """Marcar notificação como lida (idempotente)."""
    result = await db.notifications.update_one(
        {"id": notification_id},
        {"$set": {"read": True}}
    )

    if result.matched_count == 0:
        result = await db.notifications.update_one(
            {"_id": notification_id},
            {"$set": {"read": True}}
        )

    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Notificação não encontrada")

    return {"success": True}

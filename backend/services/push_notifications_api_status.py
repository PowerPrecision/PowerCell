"""Push notification status handler.

Extraído de `routes/push_notifications.py`.
Do **not** overwrite services/push_notifications.py — use push_notifications_api_*.
"""
from __future__ import annotations

from database import db


async def run_get_push_status(current_user: dict):
    user_id = current_user["id"]

    subscriptions = await db.push_subscriptions.find(
        {"user_id": user_id, "is_active": True},
        {"_id": 0, "keys": 0}
    ).to_list(10)

    return {
        "is_subscribed": len(subscriptions) > 0,
        "subscription_count": len(subscriptions),
        "subscriptions": [
            {
                "id": sub.get("id"),
                "created_at": sub.get("created_at"),
                "is_active": sub.get("is_active", True)
            }
            for sub in subscriptions
        ]
    }

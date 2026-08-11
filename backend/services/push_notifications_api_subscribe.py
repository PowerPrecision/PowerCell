"""Push notification request models and subscribe/unsubscribe handlers.

Extraído de `routes/push_notifications.py`.
Do **not** overwrite services/push_notifications.py — use push_notifications_api_*.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel

from database import db

logger = logging.getLogger(__name__)


class PushSubscriptionRequest(BaseModel):
    """Dados de subscrição push do browser."""
    endpoint: str
    keys: dict  # Contém 'p256dh' e 'auth'
    expirationTime: Optional[int] = None


class PushNotificationPayload(BaseModel):
    """Payload para enviar notificação push."""
    title: str
    body: str
    icon: Optional[str] = "/logo192.png"
    badge: Optional[str] = "/logo192.png"
    tag: Optional[str] = "creditoimo-notification"
    url: Optional[str] = "/"
    data: Optional[dict] = None


async def run_subscribe_push(subscription: PushSubscriptionRequest, current_user: dict):
    user_id = current_user["id"]

    existing = await db.push_subscriptions.find_one({
        "endpoint": subscription.endpoint
    })

    if existing:
        await db.push_subscriptions.update_one(
            {"endpoint": subscription.endpoint},
            {
                "$set": {
                    "user_id": user_id,
                    "keys": subscription.keys,
                    "expiration_time": subscription.expirationTime,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                    "is_active": True
                }
            }
        )
        logger.info(f"Subscrição push atualizada para utilizador {user_id}")
        return {"success": True, "message": "Subscrição atualizada"}

    sub_data = {
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "endpoint": subscription.endpoint,
        "keys": subscription.keys,
        "expiration_time": subscription.expirationTime,
        "is_active": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }

    await db.push_subscriptions.insert_one(sub_data)
    logger.info(f"Nova subscrição push criada para utilizador {user_id}")

    return {"success": True, "message": "Subscrição criada com sucesso"}


async def run_unsubscribe_push(subscription: PushSubscriptionRequest, current_user: dict):
    user_id = current_user["id"]

    result = await db.push_subscriptions.delete_one({
        "endpoint": subscription.endpoint,
        "user_id": user_id
    })

    if result.deleted_count > 0:
        logger.info(f"Subscrição push removida para utilizador {user_id}")
        return {"success": True, "message": "Subscrição removida"}

    await db.push_subscriptions.delete_one({
        "endpoint": subscription.endpoint
    })

    return {"success": True, "message": "Subscrição removida"}


async def run_unsubscribe_all_push(current_user: dict):
    user_id = current_user["id"]
    result = await db.push_subscriptions.delete_many({"user_id": user_id})
    logger.info(f"Removidas {result.deleted_count} subscrições push do utilizador {user_id}")
    return {
        "success": True,
        "message": f"{result.deleted_count} subscrições removidas"
    }

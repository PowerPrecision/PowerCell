"""
====================================================================
ROTAS PUSH NOTIFICATIONS - CREDITOIMO
====================================================================
Endpoints para gestão de subscrições de notificações push.
====================================================================
"""

import logging
from typing import Optional
from datetime import datetime, timezone
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from database import db
from services.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/notifications/push", tags=["Push Notifications"])


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


@router.post("/subscribe")
async def subscribe_push(
    subscription: PushSubscriptionRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Registar subscrição push para o utilizador atual.
    Guarda os dados de subscrição na base de dados.
    """
    user_id = current_user["id"]
    
    # Verificar se já existe subscrição com este endpoint
    existing = await db.push_subscriptions.find_one({
        "endpoint": subscription.endpoint
    })
    
    if existing:
        # Atualizar subscrição existente
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
    
    # Criar nova subscrição
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


@router.post("/unsubscribe")
async def unsubscribe_push(
    subscription: PushSubscriptionRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Cancelar subscrição push.
    """
    user_id = current_user["id"]
    
    result = await db.push_subscriptions.delete_one({
        "endpoint": subscription.endpoint,
        "user_id": user_id
    })
    
    if result.deleted_count > 0:
        logger.info(f"Subscrição push removida para utilizador {user_id}")
        return {"success": True, "message": "Subscrição removida"}
    
    # Se não encontrou pelo user_id, tenta só pelo endpoint
    result = await db.push_subscriptions.delete_one({
        "endpoint": subscription.endpoint
    })
    
    return {"success": True, "message": "Subscrição removida"}


@router.delete("/unsubscribe-all")
async def unsubscribe_all_push(
    current_user: dict = Depends(get_current_user)
):
    """
    Cancelar todas as subscrições push do utilizador atual.
    """
    user_id = current_user["id"]
    
    result = await db.push_subscriptions.delete_many({"user_id": user_id})
    
    logger.info(f"Removidas {result.deleted_count} subscrições push do utilizador {user_id}")
    
    return {
        "success": True,
        "message": f"{result.deleted_count} subscrições removidas"
    }


@router.get("/status")
async def get_push_status(
    current_user: dict = Depends(get_current_user)
):
    """
    Verificar estado das subscrições push do utilizador.
    """
    user_id = current_user["id"]
    
    subscriptions = await db.push_subscriptions.find(
        {"user_id": user_id, "is_active": True},
        {"_id": 0, "keys": 0}  # Não retornar chaves por segurança
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

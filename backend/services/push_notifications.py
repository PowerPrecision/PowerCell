"""
====================================================================
SERVIÇO DE PUSH NOTIFICATIONS - CREDITOIMO
====================================================================
Serviço para enviar notificações push via Web Push API com VAPID.
====================================================================
"""

import logging
import json
import os
from typing import Optional, List
from datetime import datetime, timezone

from pywebpush import webpush, WebPushException

from database import db

logger = logging.getLogger(__name__)

# Configuração VAPID
VAPID_PRIVATE_KEY = os.environ.get("VAPID_PRIVATE_KEY", "")
VAPID_PUBLIC_KEY = os.environ.get("VAPID_PUBLIC_KEY", "")
VAPID_MAILTO = os.environ.get("VAPID_MAILTO", "mailto:admin@creditoimo.pt")


def is_vapid_configured() -> bool:
    """Verificar se as chaves VAPID estão configuradas."""
    return bool(VAPID_PRIVATE_KEY and VAPID_PUBLIC_KEY)


async def get_user_push_subscriptions(user_id: str) -> List[dict]:
    """
    Obter todas as subscrições push activas de um utilizador.
    """
    subscriptions = await db.push_subscriptions.find(
        {"user_id": user_id, "is_active": True}
    ).to_list(10)
    
    return subscriptions


async def send_push_notification(
    user_id: str,
    title: str,
    body: str,
    icon: Optional[str] = "/logo192.png",
    badge: Optional[str] = "/logo192.png",
    tag: Optional[str] = None,
    url: Optional[str] = "/",
    data: Optional[dict] = None
) -> dict:
    """
    Enviar notificação push para um utilizador via Web Push API.
    
    Args:
        user_id: ID do utilizador
        title: Título da notificação
        body: Corpo da notificação
        icon: Ícone da notificação
        badge: Badge (ícone pequeno)
        tag: Tag para agrupar notificações
        url: URL para abrir ao clicar
        data: Dados adicionais
    
    Returns:
        Resultado do envio
    """
    subscriptions = await get_user_push_subscriptions(user_id)
    
    if not subscriptions:
        logger.info(f"Utilizador {user_id} não tem subscrições push activas")
        return {"success": False, "reason": "no_subscriptions"}
    
    if not is_vapid_configured():
        logger.warning("VAPID keys não configuradas - notificação push não enviada")
        return {"success": False, "reason": "vapid_not_configured"}
    
    payload = json.dumps({
        "title": title,
        "body": body,
        "icon": icon,
        "badge": badge,
        "tag": tag or f"creditoimo-{datetime.now(timezone.utc).timestamp()}",
        "data": {
            "url": url,
            **(data or {})
        }
    })
    
    sent_count = 0
    failed_subscriptions = []
    
    for sub in subscriptions:
        try:
            subscription_info = {
                "endpoint": sub["endpoint"],
                "keys": sub["keys"]
            }
            
            webpush(
                subscription_info=subscription_info,
                data=payload,
                vapid_private_key=VAPID_PRIVATE_KEY,
                vapid_claims={"sub": VAPID_MAILTO}
            )
            
            sent_count += 1
            logger.info(f"Push notification enviada para {user_id}")
            
        except WebPushException as e:
            logger.error(f"Erro ao enviar push para {user_id}: {e}")
            
            # Se a subscrição expirou ou é inválida, marcar como inativa
            if e.response and e.response.status_code in [404, 410]:
                failed_subscriptions.append(sub["endpoint"])
                logger.info(f"Subscrição expirada marcada para remoção: {sub['endpoint'][:50]}...")
        
        except ValueError as e:
            # Erro de deserialização da chave VAPID - log e continuar
            logger.error(f"Erro de chave VAPID para {user_id}: {e}")
            
        except Exception as e:
            # Qualquer outro erro - log e continuar
            logger.error(f"Erro inesperado ao enviar push para {user_id}: {e}")
    
    # Desativar subscrições inválidas
    if failed_subscriptions:
        await db.push_subscriptions.update_many(
            {"endpoint": {"$in": failed_subscriptions}},
            {"$set": {"is_active": False, "deactivated_at": datetime.now(timezone.utc).isoformat()}}
        )
        logger.info(f"Desativadas {len(failed_subscriptions)} subscrições inválidas")
    
    return {
        "success": sent_count > 0,
        "sent_count": sent_count,
        "total_subscriptions": len(subscriptions),
        "failed_count": len(failed_subscriptions)
    }


async def send_push_to_multiple_users(
    user_ids: List[str],
    title: str,
    body: str,
    **kwargs
) -> dict:
    """
    Enviar notificação push para múltiplos utilizadores.
    """
    results = {
        "total": len(user_ids),
        "sent": 0,
        "no_subscriptions": 0,
        "failed": 0
    }
    
    for user_id in user_ids:
        result = await send_push_notification(user_id, title, body, **kwargs)
        if result.get("success"):
            results["sent"] += 1
        elif result.get("reason") == "no_subscriptions":
            results["no_subscriptions"] += 1
        else:
            results["failed"] += 1
    
    return results


async def broadcast_push_notification(
    title: str,
    body: str,
    roles: Optional[List[str]] = None,
    exclude_users: Optional[List[str]] = None,
    **kwargs
) -> dict:
    """
    Enviar notificação push para múltiplos utilizadores baseado em roles.
    
    Args:
        title: Título da notificação
        body: Corpo da notificação
        roles: Lista de roles a notificar (None = todos)
        exclude_users: Lista de user_ids a excluir
    """
    exclude_users = exclude_users or []
    
    # Obter utilizadores alvo
    query = {"is_active": {"$ne": False}}
    if roles:
        query["role"] = {"$in": roles}
    
    users = await db.users.find(query, {"id": 1, "_id": 0}).to_list(1000)
    user_ids = [u["id"] for u in users if u["id"] not in exclude_users]
    
    return await send_push_to_multiple_users(user_ids, title, body, **kwargs)


async def cleanup_expired_subscriptions():
    """
    Remover subscrições expiradas.
    """
    # Marcar como inativas subscrições com expiration_time passado
    now = datetime.now(timezone.utc).timestamp() * 1000  # Em milliseconds
    
    result = await db.push_subscriptions.update_many(
        {
            "expiration_time": {"$ne": None, "$lt": now},
            "is_active": True
        },
        {"$set": {"is_active": False}}
    )
    
    if result.modified_count > 0:
        logger.info(f"Desactivadas {result.modified_count} subscrições push expiradas")
    
    return result.modified_count

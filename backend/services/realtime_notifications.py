"""
====================================================================
SERVIÇO DE NOTIFICAÇÕES EM TEMPO REAL - CREDITOIMO
====================================================================
Funções utilitárias para enviar notificações via WebSocket.
====================================================================
"""

import logging
from typing import Optional, List
from datetime import datetime, timezone
import uuid

from database import db
from services.websocket_manager import manager, WSEventType, create_ws_message
from services.push_notifications import send_push_notification

logger = logging.getLogger(__name__)


# Mapeamento de tipo de notificação para chave de preferência inapp
NOTIFICATION_TYPE_TO_PREF_KEY = {
    "process_created": "inapp_new_process",
    "process_updated": "inapp_new_process",
    "process_status_change": "inapp_status_change",
    "process_assigned": "inapp_new_process",
    "document_uploaded": "inapp_document_upload",
    "task_assigned": "inapp_task_assigned",
    "deadline_approaching": "inapp_deadline_reminder",
    "deadline_missed": "inapp_deadline_reminder",
}

# Cache simples de preferências (por user_id)
_pref_cache: dict = {}


async def _get_user_prefs(user_id: str) -> dict:
    """Obter preferências de notificação de um utilizador, com cache."""
    if user_id in _pref_cache:
        return _pref_cache[user_id]
    
    prefs_doc = await db.notification_preferences.find_one({"user_id": user_id})
    prefs = prefs_doc["preferences"] if prefs_doc and prefs_doc.get("preferences") else {}
    _pref_cache[user_id] = prefs
    return prefs


def _invalidate_pref_cache(user_id: Optional[str] = None):
    """Invalidar cache de preferências."""
    if user_id:
        _pref_cache.pop(user_id, None)
    else:
        _pref_cache.clear()


async def _should_send_inapp_notification(user_id: str, notification_type: str) -> bool:
    """
    Verificar se o utilizador tem notificações in-app activadas para este tipo.
    Se não encontrar preferências, assume True (envia por defeito).
    """
    prefs = await _get_user_prefs(user_id)
    
    # Mapear tipo de notificação para chave de preferência
    pref_key = NOTIFICATION_TYPE_TO_PREF_KEY.get(notification_type)
    if pref_key:
        # Se o utilizador definiu explicitamente a preferência, respeitar
        if pref_key in prefs:
            return bool(prefs[pref_key])
    
    # Por defeito, enviar notificação
    return True


async def send_realtime_notification(
    user_id: str,
    title: str,
    message: str,
    notification_type: str = "info",
    link: Optional[str] = None,
    process_id: Optional[str] = None,
    save_to_db: bool = True
) -> dict:
    """
    Enviar notificação em tempo real para um utilizador.
    
    Verifica as preferências de notificação do utilizador antes de enviar.
    
    Args:
        user_id: ID do utilizador destinatário
        title: Título da notificação
        message: Mensagem da notificação
        notification_type: Tipo (info, warning, error, success, process_status_change, etc.)
        link: Link opcional para redireccionamento
        process_id: ID do processo relacionado (opcional)
        save_to_db: Se deve guardar na base de dados
    
    Returns:
        Notificação criada, ou None se o utilizador desactivou este tipo
    """
    # Verificar preferências do utilizador
    if not await _should_send_inapp_notification(user_id, notification_type):
        logger.info(f"Notificação in-app bloqueada para {user_id} (tipo: {notification_type})")
        return None
    
    notification = {
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "title": title,
        "message": message,
        "type": notification_type,
        "link": link,
        "process_id": process_id,
        "read": False,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    # Guardar na base de dados
    if save_to_db:
        await db.notifications.insert_one({**notification, "_id": notification["id"]})
        # Remover _id para resposta
        notification.pop("_id", None)
    
    # Enviar via WebSocket se o utilizador estiver conectado
    if manager.is_user_connected(user_id):
        await manager.send_personal_message(
            create_ws_message(WSEventType.NEW_NOTIFICATION, notification),
            user_id
        )
        logger.info(f"Notificação enviada via WebSocket para {user_id}")
    else:
        logger.info(f"Utilizador {user_id} não conectado. Notificação guardada na DB.")
        # Enviar push notification quando o utilizador não está conectado via WebSocket
        await send_push_notification(
            user_id=user_id,
            title=title,
            body=message,
            url=link or "/",
            data={"process_id": process_id} if process_id else None
        )
    
    return notification


async def broadcast_notification(
    title: str,
    message: str,
    notification_type: str = "info",
    link: Optional[str] = None,
    exclude_users: Optional[List[str]] = None,
    roles: Optional[List[str]] = None,
    save_to_db: bool = True
) -> int:
    """
    Enviar notificação para múltiplos utilizadores.
    
    Args:
        title: Título da notificação
        message: Mensagem da notificação
        notification_type: Tipo (info, warning, error, success)
        link: Link opcional
        exclude_users: Lista de user_ids a excluir
        roles: Lista de papéis a notificar (None = todos)
        save_to_db: Se deve guardar na base de dados
    
    Returns:
        Número de utilizadores notificados
    """
    exclude_users = exclude_users or []
    count = 0
    
    # Obter utilizadores alvo
    query = {"is_active": {"$ne": False}}
    if roles:
        query["role"] = {"$in": roles}
    
    users = await db.users.find(query, {"id": 1, "_id": 0}).to_list(1000)
    
    for user in users:
        user_id = user["id"]
        if user_id not in exclude_users:
            await send_realtime_notification(
                user_id=user_id,
                title=title,
                message=message,
                notification_type=notification_type,
                link=link,
                save_to_db=save_to_db
            )
            count += 1
    
    return count


async def notify_process_update(
    process_id: str,
    action: str,
    actor_name: str,
    details: Optional[str] = None
):
    """
    Notificar utilizadores relevantes sobre uma actualização de processo.
    
    Args:
        process_id: ID do processo
        action: Acção realizada (created, updated, status_changed, assigned)
        actor_name: Nome de quem realizou a acção
        details: Detalhes adicionais
    """
    process = await db.processes.find_one({"id": process_id}, {"_id": 0})
    if not process:
        return
    
    client_name = process.get("client_name", "Cliente")
    
    # Determinar título e mensagem baseado na acção
    if action == "created":
        title = "Novo Processo Criado"
        message = f"{actor_name} criou um novo processo para {client_name}"
        event_type = WSEventType.PROCESS_CREATED
    elif action == "status_changed":
        title = "Estado do Processo Alterado"
        message = f"O processo de {client_name} mudou para {details}"
        event_type = WSEventType.PROCESS_STATUS_CHANGED
    elif action == "assigned":
        title = "Processo Atribuído"
        message = f"Foste atribuído ao processo de {client_name}"
        event_type = WSEventType.PROCESS_ASSIGNED
    else:
        title = "Processo Actualizado"
        message = f"O processo de {client_name} foi actualizado"
        event_type = WSEventType.PROCESS_UPDATED
    
    # Notificar utilizadores atribuídos ao processo
    users_to_notify = set()
    
    if process.get("consultor_id"):
        users_to_notify.add(process["consultor_id"])
    if process.get("mediador_id"):
        users_to_notify.add(process["mediador_id"])
    
    # Também notificar admins e CEOs
    admins = await db.users.find(
        {"role": {"$in": ["admin", "ceo"]}, "is_active": {"$ne": False}},
        {"id": 1, "_id": 0}
    ).to_list(100)
    
    for admin in admins:
        users_to_notify.add(admin["id"])
    
    # Enviar notificações
    for user_id in users_to_notify:
        await send_realtime_notification(
            user_id=user_id,
            title=title,
            message=message,
            notification_type="info",
            link=f"/processos/{process_id}",
            process_id=process_id
        )
    
    # Broadcast evento WebSocket
    await manager.broadcast(create_ws_message(
        event_type,
        {
            "process_id": process_id,
            "client_name": client_name,
            "action": action,
            "actor": actor_name,
            "details": details
        }
    ))


async def notify_deadline_reminder(deadline: dict, minutes_before: int = 30):
    """
    Enviar lembrete de prazo/evento.
    
    Args:
        deadline: Dados do prazo/evento
        minutes_before: Minutos antes do evento
    """
    # Notificar participantes
    participants = deadline.get("participants", [])
    
    if not participants:
        return
    
    title = f"⏰ Lembrete: {deadline.get('title', 'Evento')}"
    message = f"O evento começa em {minutes_before} minutos"
    
    for user_id in participants:
        await send_realtime_notification(
            user_id=user_id,
            title=title,
            message=message,
            notification_type="warning",
            link="/admin?tab=calendar"
        )
        
        # Enviar evento específico via WebSocket
        if manager.is_user_connected(user_id):
            await manager.send_personal_message(
                create_ws_message(
                    WSEventType.DEADLINE_REMINDER,
                    {
                        "deadline_id": deadline.get("id"),
                        "title": deadline.get("title"),
                        "date": deadline.get("date"),
                        "minutes_before": minutes_before
                    }
                ),
                user_id
            )


async def notify_process_status_change(
    process: dict,
    old_status: str,
    new_status: str,
    new_status_label: str,
    changed_by: dict
):
    """
    Notificar utilizadores relevantes sobre mudança de fase de um processo.
    Cria notificação na colecção 'notifications' do MongoDB.
    
    Args:
        process: Dados do processo
        old_status: Estado anterior
        new_status: Novo estado
        new_status_label: Label legível do novo estado
        changed_by: Utilizador que fez a mudança
    """
    client_name = process.get("client_name", "Cliente")
    process_id = process.get("id")
    
    # Construir mensagem
    message = f"O processo de {client_name} avançou para {new_status_label}"
    
    # Determinar quem notificar
    users_to_notify = set()
    
    # Consultor e Mediador atribuídos
    if process.get("consultor_id"):
        users_to_notify.add(process["consultor_id"])
    if process.get("assigned_consultor_id"):
        users_to_notify.add(process["assigned_consultor_id"])
    if process.get("mediador_id"):
        users_to_notify.add(process["mediador_id"])
    if process.get("assigned_mediador_id"):
        users_to_notify.add(process["assigned_mediador_id"])
    
    # Também notificar admins, CEOs e diretores
    admins = await db.users.find(
        {"role": {"$in": ["admin", "ceo", "diretor"]}, "is_active": {"$ne": False}},
        {"id": 1, "_id": 0}
    ).to_list(100)
    
    for admin in admins:
        users_to_notify.add(admin["id"])
    
    # Remover quem fez a mudança (não precisa de notificação)
    users_to_notify.discard(changed_by.get("id"))
    
    # Enviar notificações
    for user_id in users_to_notify:
        await send_realtime_notification(
            user_id=user_id,
            title="📋 Processo Atualizado",
            message=message,
            notification_type="process_status_change",
            link=f"/process/{process_id}",
            process_id=process_id,
            save_to_db=True
        )
    
    logger.info(f"Notificação de mudança de estado enviada para {len(users_to_notify)} utilizadores")

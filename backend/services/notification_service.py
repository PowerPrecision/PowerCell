"""
====================================================================
SERVIÇO DE NOTIFICAÇÕES - CREDITOIMO
====================================================================
Serviço centralizado para envio de notificações com verificação de preferências.
Antes de enviar qualquer email, verifica se o utilizador quer receber esse tipo.
====================================================================
"""

import logging
from typing import Optional, Dict, Any
from database import db
from services.email import send_email_notification

logger = logging.getLogger(__name__)

# Preferências por defeito
DEFAULT_NOTIFICATION_PREFS = {
    "email_new_process": False,
    "email_status_change": False,
    "email_document_upload": False,
    "email_task_assigned": False,
    "email_portal_message": True,
    "email_deadline_reminder": True,
    "email_urgent_only": True,
    "email_daily_summary": True,
    "email_weekly_report": True,
    "inapp_new_process": True,
    "inapp_status_change": True,
    "inapp_document_upload": True,
    "inapp_task_assigned": True,
    "inapp_comments": True,
    "inapp_portal_message": True,
    "is_test_user": False,
}

# Mapeamento de tipo de notificação para chave de preferência
NOTIFICATION_TYPE_MAP = {
    "new_process": "email_new_process",
    "status_change": "email_status_change",
    "document_upload": "email_document_upload",
    "task_assigned": "email_task_assigned",
    "portal_message": "email_portal_message",
    "deadline_reminder": "email_deadline_reminder",
    "urgent": "email_urgent_only",
    "daily_summary": "email_daily_summary",
    "weekly_report": "email_weekly_report",
}


async def get_user_notification_prefs(user_email: str) -> Dict[str, Any]:
    """
    Obtém as preferências de notificação de um utilizador, aplicando merge
    com valores por defeito para garantir compatibilidade retroativa.

    Porquê o merge com defaults: quando novos tipos de notificação são
    adicionados ao sistema, utilizadores existentes não têm essa chave
    nas suas preferências. O merge garante que novos campos assumem o
    valor seguro (normalmente False) sem eliminar preferências antigas.

    Args:
        user_email: Email do utilizador para procurar preferências.

    Returns:
        Dict[str, Any]: Preferências completas (defaults + personalização).
    """
    # Procurar utilizador pelo email
    user = await db.users.find_one({"email": user_email}, {"_id": 0, "id": 1})
    if not user:
        return DEFAULT_NOTIFICATION_PREFS
    
    # Obter preferências
    prefs = await db.notification_preferences.find_one(
        {"user_id": user["id"]}, 
        {"_id": 0}
    )
    
    if not prefs:
        return DEFAULT_NOTIFICATION_PREFS
    
    # Merge com defaults (para campos novos)
    return {**DEFAULT_NOTIFICATION_PREFS, **prefs}


async def should_send_email(
    user_email: str, 
    notification_type: str,
    is_urgent: bool = False
) -> bool:
    """
    Verifica se deve enviar email para um utilizador baseado nas preferências.
    
    Args:
        user_email: Email do destinatário
        notification_type: Tipo de notificação (new_process, status_change, etc.)
        is_urgent: Se é uma notificação urgente
    
    Returns:
        True se deve enviar, False caso contrário
    """
    prefs = await get_user_notification_prefs(user_email)
    
    # Utilizadores de teste nunca recebem emails
    if prefs.get("is_test_user", False):
        logger.debug(f"Email bloqueado para {user_email}: utilizador de teste")
        return False
    
    # Se é urgente e utilizador aceita urgentes, enviar
    if is_urgent and prefs.get("email_urgent_only", True):
        return True
    
    # Verificar preferência específica
    pref_key = NOTIFICATION_TYPE_MAP.get(notification_type)
    if pref_key:
        should_send = prefs.get(pref_key, False)
        if not should_send:
            logger.debug(f"Email bloqueado para {user_email}: {notification_type} desactivado")
        return should_send
    
    # Se não há mapeamento, usar email_urgent_only como fallback
    return prefs.get("email_urgent_only", True)


async def send_notification_with_preference_check(
    to_email: str,
    subject: str,
    body: str,
    notification_type: str = "urgent",
    is_urgent: bool = False,
    html_body: str = None
) -> bool:
    """
    Envia email apenas se o destinatário tem a preferência desse tipo
    de notificação ativada. Esta é a função principal que todas as
    notificações do sistema devem usar como gateway.

    Porquê um gateway centralizado:
    - Evita spam: respeita as preferências de cada utilizador.
    - Protege utilizadores de teste (is_test_user nunca recebe emails).
    - Urgências bypassam preferências normais para garantir entrega.
    - Simplifica auditoria: toda a lógica de filtragem está num só lugar.

    Args:
        to_email: Email do destinatário.
        subject: Assunto do email.
        body: Corpo do email em texto simples.
        notification_type: Tipo de notificação (ver NOTIFICATION_TYPE_MAP).
        is_urgent: Se True, bypass preferências não-urgentes.
        html_body: Corpo do email em HTML (opcional, para emails formatados).

    Returns:
        bool: True se o email foi enviado, False se bloqueado por
            preferências ou erro no envio.
    """
    # Verificar preferências
    if not await should_send_email(to_email, notification_type, is_urgent):
        logger.info(f"Notificação '{notification_type}' não enviada para {to_email} (preferências)")
        return False
    
    # Enviar email
    try:
        await send_email_notification(to_email, subject, body, html_body)
        logger.info(f"Notificação '{notification_type}' enviada para {to_email}")
        return True
    except Exception as e:
        logger.error(f"Erro ao enviar email para {to_email}: {e}")
        return False


async def send_to_admins(
    subject: str,
    body: str,
    notification_type: str = "urgent",
    html_body: str = None
) -> int:
    """
    Envia notificação para todos os administradores (Admin e CEO) que
    aceitam esse tipo de notificação, respeitando preferências individuais.

    Útil para alertas do sistema que requerem atenção da gestão, como
    erros críticos, novos processos ou alertas de segurança.

    Args:
        subject: Assunto do email.
        body: Corpo do email em texto simples.
        notification_type: Tipo de notificação para filtragem.
        html_body: Corpo em HTML (opcional).

    Returns:
        int: Número de emails efetivamente enviados.
    """
    from models.auth import UserRole
    from services.role_query import deep_role_in_filter
    
    admins = await db.users.find(
        deep_role_in_filter([UserRole.ADMIN, UserRole.CEO]),
        {"_id": 0, "email": 1}
    ).to_list(100)
    
    sent_count = 0
    for admin in admins:
        if await send_notification_with_preference_check(
            admin["email"], subject, body, notification_type, html_body=html_body
        ):
            sent_count += 1
    
    return sent_count


async def send_status_change_notification(
    client_email: str,
    client_name: str,
    old_status: str,
    new_status: str,
    new_status_label: str
) -> bool:
    """
    Envia notificação de mudança de estado ao cliente.
    """
    subject = "Atualização do seu processo"
    body = f"""Olá {client_name},

O estado do seu processo foi atualizado de "{old_status}" para "{new_status_label}".

Se tiver dúvidas, não hesite em contactar-nos.

Cumprimentos,
Equipa PowerCell
"""
    
    return await send_notification_with_preference_check(
        client_email, 
        subject, 
        body, 
        notification_type="status_change"
    )


async def send_new_process_notification(
    staff_email: str,
    client_name: str,
    process_type: str,
    process_number: int = None
) -> bool:
    """
    Envia notificação de novo processo ao staff.
    """
    subject = "Novo Processo Criado"
    process_info = f"#{process_number}" if process_number else ""
    body = f"""Novo processo {process_info} criado:

Cliente: {client_name}
Tipo: {process_type}

Aceda à aplicação para mais detalhes.
"""
    
    return await send_notification_with_preference_check(
        staff_email, 
        subject, 
        body, 
        notification_type="new_process"
    )


async def send_deadline_reminder(
    to_email: str,
    client_name: str,
    deadline_title: str,
    due_date: str,
    days_remaining: int
) -> bool:
    """
    Envia lembrete de prazo.
    """
    urgency = "URGENTE: " if days_remaining <= 3 else ""
    subject = f"{urgency}Lembrete de Prazo - {deadline_title}"
    body = f"""Lembrete de prazo:

Cliente: {client_name}
Prazo: {deadline_title}
Data Limite: {due_date}
Dias Restantes: {days_remaining}

{'Este prazo está próximo do fim!' if days_remaining <= 3 else ''}
"""
    
    return await send_notification_with_preference_check(
        to_email, 
        subject, 
        body, 
        notification_type="deadline_reminder",
        is_urgent=(days_remaining <= 3)
    )

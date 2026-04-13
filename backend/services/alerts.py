"""
====================================================================
SERVIÇO DE ALERTAS E NOTIFICAÇÕES - CREDITOIMO
====================================================================
Sistema de alertas automáticos e notificações para processos.

TIPOS DE ALERTAS:
1. Alerta de Idade: Cliente < 35 anos - Apoio ao Estado
2. Alerta de Janela: Countdown 90 dias após pré-aprovação
3. Alerta de Validade: 15 dias antes da expiração de documentos
4. Alerta de Avaliação: Verificar documentos do imóvel
5. Alerta de Escritura: 15 dias antes da data marcada

Autor: PowerCell Development Team
====================================================================
"""

import uuid
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict, Any

from database import db
from services.notification_service import send_notification_with_preference_check, send_deadline_reminder

logger = logging.getLogger(__name__)


# ====================================================================
# CONSTANTES DE CONFIGURAÇÃO
# ====================================================================

ALERT_TYPES = {
    "AGE_UNDER_35": "age_under_35",              # Cliente < 35 anos
    "PRE_APPROVAL_COUNTDOWN": "pre_approval_countdown",  # 90 dias após pré-aprovação
    "DOCUMENT_EXPIRY": "document_expiry",        # 15 dias antes de expirar
    "PROPERTY_DOCS_CHECK": "property_docs_check",  # Verificar docs do imóvel
    "DEED_REMINDER": "deed_reminder",            # 15 dias antes da escritura
    "NEW_CLIENT_REGISTRATION": "new_registration",  # Novo registo de cliente
    "PROPERTY_MATCH": "property_match",          # Match perfeito cliente-imóvel
    "VALUATION_BELOW_PURCHASE": "valuation_below_purchase",  # Avaliação < valor compra
}

# Dias para alertas
DAYS_PRE_APPROVAL_COUNTDOWN = 90
DAYS_DOCUMENT_EXPIRY_WARNING = 15
DAYS_DEED_REMINDER = 15
MATCH_SCORE_THRESHOLD = 50  # Score mínimo para notificação de match


# ====================================================================
# FUNÇÕES DE VERIFICAÇÃO DE IDADE
# ====================================================================

def calculate_age(birth_date_str: str) -> Optional[int]:
    """
    Calcula a idade a partir da data de nascimento.
    
    Args:
        birth_date_str: Data no formato YYYY-MM-DD
    
    Returns:
        Idade em anos ou None se não conseguir calcular
    """
    if not birth_date_str:
        return None
    
    try:
        birth_date = datetime.strptime(birth_date_str, "%Y-%m-%d")
        today = datetime.now()
        age = today.year - birth_date.year
        
        # Ajustar se ainda não fez anos este ano
        if (today.month, today.day) < (birth_date.month, birth_date.day):
            age -= 1
        
        return age
    except (ValueError, TypeError):
        return None


def check_age_alert(process: dict) -> Dict[str, Any]:
    """
    Verifica se o cliente tem menos de 35 anos (elegível para apoio do estado).
    
    Args:
        process: Dados do processo
    
    Returns:
        Dict com informação do alerta ou None
    """
    personal_data = process.get("personal_data", {}) or {}
    birth_date = personal_data.get("birth_date")
    
    # Também verificar o campo idade_menos_35
    if process.get("idade_menos_35"):
        return {
            "type": ALERT_TYPES["AGE_UNDER_35"],
            "active": True,
            "message": "Cliente com menos de 35 anos - Elegível para Apoio ao Estado",
            "details": "Verificar condições do programa de apoio à habitação jovem",
            "priority": "info",
            "icon": "star"
        }
    
    age = calculate_age(birth_date)
    if age is not None and age < 35:
        return {
            "type": ALERT_TYPES["AGE_UNDER_35"],
            "active": True,
            "age": age,
            "message": f"Cliente com {age} anos - Elegível para Apoio ao Estado",
            "details": "Verificar condições do programa de apoio à habitação jovem",
            "priority": "info",
            "icon": "star"
        }
    
    return {"type": ALERT_TYPES["AGE_UNDER_35"], "active": False}


# ====================================================================
# FUNÇÕES DE COUNTDOWN PÓS PRÉ-APROVAÇÃO
# ====================================================================

async def check_pre_approval_countdown(process: dict) -> Dict[str, Any]:
    """
    Verifica o countdown de 90 dias após a pré-aprovação.
    
    Args:
        process: Dados do processo
    
    Returns:
        Dict com informação do countdown
    """
    credit_data = process.get("credit_data", {}) or {}
    approval_date_str = credit_data.get("bank_approval_date")
    
    # Verificar se está em estado de aprovação
    if process.get("status") not in ["ch_aprovado", "fase_escritura", "escritura_agendada"]:
        return {"type": ALERT_TYPES["PRE_APPROVAL_COUNTDOWN"], "active": False}
    
    if not approval_date_str:
        # Se não tem data de aprovação mas está aprovado, usar created_at ou updated_at
        # como fallback
        return {
            "type": ALERT_TYPES["PRE_APPROVAL_COUNTDOWN"],
            "active": True,
            "message": "Pré-aprovação sem data registada",
            "details": "Por favor, registar a data de aprovação bancária",
            "priority": "warning"
        }
    
    try:
        approval_date = datetime.strptime(approval_date_str, "%Y-%m-%d")
        deadline = approval_date + timedelta(days=DAYS_PRE_APPROVAL_COUNTDOWN)
        today = datetime.now()
        days_remaining = (deadline - today).days
        
        if days_remaining <= 0:
            return {
                "type": ALERT_TYPES["PRE_APPROVAL_COUNTDOWN"],
                "active": True,
                "days_remaining": days_remaining,
                "deadline": deadline.strftime("%Y-%m-%d"),
                "message": f"URGENTE: Prazo de 90 dias EXPIRADO há {abs(days_remaining)} dias!",
                "details": "A pré-aprovação pode ter caducado. Contactar o banco.",
                "priority": "critical"
            }
        elif days_remaining <= 15:
            return {
                "type": ALERT_TYPES["PRE_APPROVAL_COUNTDOWN"],
                "active": True,
                "days_remaining": days_remaining,
                "deadline": deadline.strftime("%Y-%m-%d"),
                "message": f"ATENÇÃO: Faltam {days_remaining} dias para o fim do prazo de aprovação",
                "details": "Acelerar o processo de escritura",
                "priority": "high"
            }
        elif days_remaining <= 30:
            return {
                "type": ALERT_TYPES["PRE_APPROVAL_COUNTDOWN"],
                "active": True,
                "days_remaining": days_remaining,
                "deadline": deadline.strftime("%Y-%m-%d"),
                "message": f"Countdown: {days_remaining} dias restantes da pré-aprovação",
                "details": "Prazo limite: " + deadline.strftime("%d/%m/%Y"),
                "priority": "medium"
            }
        else:
            return {
                "type": ALERT_TYPES["PRE_APPROVAL_COUNTDOWN"],
                "active": True,
                "days_remaining": days_remaining,
                "deadline": deadline.strftime("%Y-%m-%d"),
                "message": f"Pré-aprovação válida por mais {days_remaining} dias",
                "details": "Prazo limite: " + deadline.strftime("%d/%m/%Y"),
                "priority": "low"
            }
    except (ValueError, TypeError):
        return {"type": ALERT_TYPES["PRE_APPROVAL_COUNTDOWN"], "active": False}


# ====================================================================
# FUNÇÕES DE ALERTA DE DOCUMENTOS
# ====================================================================

async def check_document_expiry_alerts(process_id: str) -> List[Dict[str, Any]]:
    """
    Verifica documentos que expiram nos próximos 15 dias.
    
    Args:
        process_id: ID do processo
    
    Returns:
        Lista de alertas de documentos
    """
    alerts = []
    today = datetime.now().date()
    warning_date = today + timedelta(days=DAYS_DOCUMENT_EXPIRY_WARNING)
    
    # Buscar documentos do processo
    docs = await db.document_expiries.find({
        "process_id": process_id,
        "expiry_date": {
            "$gte": today.isoformat(),
            "$lte": warning_date.isoformat()
        }
    }, {"_id": 0}).to_list(100)
    
    # Filtrar por tipo de documento crítico (IRS, identificação)
    critical_types = ["cc", "passaporte", "carta_conducao", "declaracao_irs", "irs"]
    
    for doc in docs:
        expiry = datetime.strptime(doc["expiry_date"], "%Y-%m-%d").date()
        days_until = (expiry - today).days
        
        is_critical = doc.get("document_type", "").lower() in critical_types
        
        alerts.append({
            "type": ALERT_TYPES["DOCUMENT_EXPIRY"],
            "active": True,
            "document_id": doc["id"],
            "document_name": doc.get("document_name", "Documento"),
            "document_type": doc.get("document_type"),
            "expiry_date": doc["expiry_date"],
            "days_until": days_until,
            "is_critical": is_critical,
            "message": f"{doc.get('document_name', 'Documento')} expira em {days_until} dias",
            "details": f"Data de expiração: {expiry.strftime('%d/%m/%Y')}",
            "priority": "critical" if days_until <= 7 or is_critical else "high"
        })
    
    return alerts


# ====================================================================
# FUNÇÕES DE VERIFICAÇÃO DE DOCUMENTOS DO IMÓVEL
# ====================================================================

async def check_property_documents(process: dict) -> Dict[str, Any]:
    """
    Verifica se os documentos do imóvel estão completos (para fase de avaliação).
    
    Args:
        process: Dados do processo
    
    Returns:
        Dict com informação sobre documentos do imóvel
    """
    # Documentos necessários do imóvel
    required_property_docs = [
        "certidao_predial",
        "caderneta_predial",
        "licenca_utilizacao",
        "ficha_tecnica"
    ]
    
    # Buscar documentos do processo
    existing_docs = await db.document_expiries.find({
        "process_id": process["id"]
    }, {"document_type": 1, "_id": 0}).to_list(100)
    
    existing_types = [d.get("document_type", "").lower() for d in existing_docs]
    
    missing_docs = []
    for doc_type in required_property_docs:
        if doc_type not in existing_types:
            missing_docs.append(doc_type)
    
    doc_names = {
        "certidao_predial": "Certidão Predial",
        "caderneta_predial": "Caderneta Predial",
        "licenca_utilizacao": "Licença de Utilização",
        "ficha_tecnica": "Ficha Técnica de Habitação"
    }
    
    if missing_docs:
        missing_names = [doc_names.get(d, d) for d in missing_docs]
        return {
            "type": ALERT_TYPES["PROPERTY_DOCS_CHECK"],
            "active": True,
            "missing_documents": missing_docs,
            "missing_names": missing_names,
            "message": f"Faltam {len(missing_docs)} documento(s) do imóvel",
            "details": "Documentos em falta: " + ", ".join(missing_names),
            "priority": "high"
        }
    
    return {
        "type": ALERT_TYPES["PROPERTY_DOCS_CHECK"],
        "active": False,
        "message": "Todos os documentos do imóvel estão presentes",
        "priority": "success"
    }


# ====================================================================
# FUNÇÕES DE CRIAÇÃO DE ALERTAS NO CALENDÁRIO
# ====================================================================

async def create_deed_reminder(process: dict, deed_date: str, user: dict) -> Optional[str]:
    """
    Cria um alerta no calendário 15 dias antes da escritura.
    
    Args:
        process: Dados do processo
        deed_date: Data da escritura (YYYY-MM-DD)
        user: Utilizador que está a criar
    
    Returns:
        ID do deadline criado ou None
    """
    try:
        deed_datetime = datetime.strptime(deed_date, "%Y-%m-%d")
        reminder_date = deed_datetime - timedelta(days=DAYS_DEED_REMINDER)
        
        # Não criar se a data do lembrete já passou
        if reminder_date.date() < datetime.now().date():
            return None
        
        # Obter utilizadores envolvidos no processo
        assigned_users = []
        if process.get("assigned_consultor_id"):
            assigned_users.append(process["assigned_consultor_id"])
        if process.get("consultor_id"):
            assigned_users.append(process["consultor_id"])
        if process.get("assigned_mediador_id"):
            assigned_users.append(process["assigned_mediador_id"])
        if process.get("intermediario_id"):
            assigned_users.append(process["intermediario_id"])
        
        # Remover duplicados
        assigned_users = list(set(assigned_users))
        
        deadline_id = str(uuid.uuid4())
        
        deadline_doc = {
            "id": deadline_id,
            "process_id": process["id"],
            "title": f"📋 Preparar Escritura - {process.get('client_name', 'Cliente')}",
            "description": f"Escritura agendada para {deed_datetime.strftime('%d/%m/%Y')}. Verificar se toda a documentação está pronta.",
            "due_date": reminder_date.strftime("%Y-%m-%d"),
            "priority": "high",
            "completed": False,
            "created_by": user["id"],
            "created_at": datetime.now(timezone.utc).isoformat(),
            "assigned_user_ids": assigned_users,
            "alert_type": ALERT_TYPES["DEED_REMINDER"]
        }
        
        await db.deadlines.insert_one(deadline_doc)
        
        # Notificar utilizadores envolvidos (com verificação de preferências)
        for user_id in assigned_users:
            assigned_user = await db.users.find_one({"id": user_id}, {"_id": 0})
            if assigned_user:
                await send_notification_with_preference_check(
                    assigned_user["email"],
                    f"Lembrete: Escritura em 15 dias - {process.get('client_name')}",
                    f"A escritura do cliente {process.get('client_name')} está agendada para {deed_datetime.strftime('%d/%m/%Y')}.\n\n"
                    f"Por favor, verifique se toda a documentação necessária está pronta.\n\n"
                    f"Este lembrete foi criado automaticamente.",
                    notification_type="deadline_reminder",
                    is_urgent=True
                )
        
        return deadline_id
    except (ValueError, TypeError) as e:
        print(f"Erro ao criar lembrete de escritura: {e}")
        return None


# ====================================================================
# FUNÇÕES DE NOTIFICAÇÃO DE NOVO REGISTO
# ====================================================================

async def notify_new_client_registration(process: dict, has_property: bool = False):
    """
    Notifica administradores sobre novo registo de cliente.
    NOTA: Envia email apenas para o PRIMEIRO admin para evitar spam.
    Os outros recebem notificação via sistema interno.
    
    Args:
        process: Dados do processo (pode ter 'client_name' ou 'nome')
        has_property: Se o cliente já tem imóvel (atribuir só intermediários)
    """
    # Buscar administradores e CEO
    admins = await db.users.find({
        "role": {"$in": ["admin", "ceo"]},
        "is_active": True
    }, {"_id": 0}).to_list(100)
    
    # Obter nome do cliente (compatível com ambos os formatos)
    client_name = process.get("client_name") or process.get("nome") or "Cliente"
    client_email = process.get("client_email") or (process.get("contacto") or {}).get("email") or ""
    client_phone = process.get("client_phone") or (process.get("contacto") or {}).get("telefone") or ""
    
    assignment_note = ""
    if has_property:
        assignment_note = "\n\n⚠️ O cliente indicou que JÁ TEM IMÓVEL - Atribuir apenas a INTERMEDIÁRIO DE CRÉDITO."
    else:
        assignment_note = "\n\nAtribuir consultor imobiliário e/ou intermediário de crédito conforme necessário."
    
    # Enviar email apenas para o PRIMEIRO admin (evitar spam) - com verificação de preferências
    if admins:
        admin = admins[0]
        await send_notification_with_preference_check(
            admin["email"],
            f"Novo Registo de Cliente: {client_name}",
            f"Um novo cliente registou-se no sistema:\n\n"
            f"Nome: {client_name}\n"
            f"Email: {client_email}\n"
            f"Telefone: {client_phone}\n"
            f"Tipo: {process.get('process_type', 'Não especificado')}\n"
            f"{assignment_note}\n\n"
            f"Por favor, aceda ao sistema para atribuir os responsáveis.",
            notification_type="new_process",
            is_urgent=True
        )
    
    # Criar notificação no sistema para TODOS os admins
    notification = {
        "id": str(uuid.uuid4()),
        "type": ALERT_TYPES["NEW_CLIENT_REGISTRATION"],
        "process_id": process.get("id"),
        "client_name": client_name,
        "has_property": has_property,
        "message": f"Novo registo: {client_name}" + (" (Já tem imóvel)" if has_property else ""),
        "read": False,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db.notifications.insert_one(notification)


# ====================================================================
# FUNÇÕES DE NOTIFICAÇÃO DE COUNTDOWN
# ====================================================================

async def notify_cpcv_or_deed_document_check(process: dict, new_status: str):
    """
    Notifica os envolvidos quando um processo atinge CPCV ou Escritura
    para verificar se toda a documentação está em ordem.
    
    Args:
        process: Dados do processo
        new_status: O novo estado do processo (cpcv, fase_escritura, escritura_agendada)
    """
    from services.realtime_notifications import send_realtime_notification
    
    # Determinar mensagem baseada no estado
    status_messages = {
        "fase_escritura": ("📋 CPCV/Escritura", "O processo entrou em fase de escritura"),
        "escritura_agendada": ("📝 Escritura Agendada", "A escritura foi agendada"),
        "ch_aprovado": ("✅ CH Aprovado", "O crédito habitação foi aprovado"),
    }
    
    title, description = status_messages.get(new_status, ("📋 Mudança de Fase", "O processo mudou de fase"))
    
    # Obter utilizadores envolvidos
    user_ids = set()
    if process.get("assigned_consultor_id"):
        user_ids.add(process["assigned_consultor_id"])
    if process.get("consultor_id"):
        user_ids.add(process["consultor_id"])
    if process.get("assigned_mediador_id"):
        user_ids.add(process["assigned_mediador_id"])
    if process.get("intermediario_id"):
        user_ids.add(process["intermediario_id"])
    
    # Adicionar CEO, Diretores e Administrativos
    staff = await db.users.find({
        "role": {"$in": ["ceo", "diretor", "admin"]},
        "is_active": True
    }, {"_id": 0, "id": 1, "email": 1, "name": 1}).to_list(100)
    
    for s in staff:
        user_ids.add(s["id"])
    
    # Verificar documentos do imóvel
    property_check = await check_property_documents(process)
    missing_info = ""
    if property_check.get("active"):
        missing_info = f"\n\n⚠️ Documentos em falta: {property_check.get('details', 'Verificar')}"
    
    # Enviar notificações
    client_name = process.get("client_name", "Cliente")
    
    for user_id in user_ids:
        # Notificação em tempo real (WebSocket + Push)
        await send_realtime_notification(
            user_id=user_id,
            title=f"{title} - {client_name}",
            message=f"{description}. Por favor, verifique se toda a documentação está em ordem.{missing_info}",
            notification_type="document_verification",
            link=f"/process/{process['id']}",
            process_id=process["id"]
        )
        
        # Email (com verificação de preferências)
        user = await db.users.find_one({"id": user_id}, {"_id": 0})
        if user:
            await send_notification_with_preference_check(
                user["email"],
                f"{title} - {client_name}",
                f"Olá {user['name']},\n\n"
                f"{description} para o cliente {client_name}.\n\n"
                f"Por favor, aceda ao sistema para verificar se toda a documentação está em ordem "
                f"antes de prosseguir com o processo.{missing_info}\n\n"
                f"Aceda ao processo: /process/{process['id']}",
                notification_type="document_upload"
            )


async def notify_pre_approval_countdown(process: dict):
    """
    Notifica os envolvidos sobre o countdown da pré-aprovação.
    
    Args:
        process: Dados do processo
    """
    countdown = await check_pre_approval_countdown(process)
    
    if not countdown.get("active") or countdown.get("priority") not in ["high", "critical"]:
        return
    
    # Obter utilizadores envolvidos
    user_ids = []
    if process.get("assigned_consultor_id"):
        user_ids.append(process["assigned_consultor_id"])
    if process.get("consultor_id"):
        user_ids.append(process["consultor_id"])
    if process.get("assigned_mediador_id"):
        user_ids.append(process["assigned_mediador_id"])
    if process.get("intermediario_id"):
        user_ids.append(process["intermediario_id"])
    
    user_ids = list(set(user_ids))
    
    for user_id in user_ids:
        user = await db.users.find_one({"id": user_id}, {"_id": 0})
        if user:
            await send_notification_with_preference_check(
                user["email"],
                f"Alerta de Prazo: {process.get('client_name')}",
                f"{countdown['message']}\n\n"
                f"Cliente: {process.get('client_name')}\n"
                f"{countdown.get('details', '')}\n\n"
                f"Por favor, tome as medidas necessárias.",
                notification_type="deadline_reminder",
                is_urgent=(countdown.get("priority") == "critical")
            )


# ====================================================================
# FUNÇÃO PRINCIPAL DE OBTER TODOS OS ALERTAS
# ====================================================================

async def get_process_alerts(process: dict) -> List[Dict[str, Any]]:
    """
    Obtém todos os alertas activos para um processo.
    
    Args:
        process: Dados do processo
    
    Returns:
        Lista de todos os alertas
    """
    alerts = []
    
    # Verificar se processo é válido
    if not process:
        return alerts
    
    # Processos finalizados não geram alertas
    status = process.get("status", "")
    if status in ["concluido", "desistido", "cancelado", "arquivado"]:
        return alerts
    
    # 1. Alerta de idade
    try:
        age_alert = check_age_alert(process)
        if age_alert and age_alert.get("active"):
            alerts.append(age_alert)
    except Exception as e:
        logger.warning(f"Erro ao verificar alerta de idade: {e}")
    
    # 2. Countdown de pré-aprovação
    try:
        countdown_alert = await check_pre_approval_countdown(process)
        if countdown_alert and countdown_alert.get("active"):
            alerts.append(countdown_alert)
    except Exception as e:
        logger.warning(f"Erro ao verificar countdown: {e}")
    
    # 3. Alertas de documentos a expirar
    try:
        process_id = process.get("id")
        if process_id:
            doc_alerts = await check_document_expiry_alerts(process_id)
            alerts.extend(doc_alerts)
    except Exception as e:
        logger.warning(f"Erro ao verificar documentos: {e}")
    
    # 4. Verificação de documentos do imóvel (se em fase de avaliação)
    try:
        if process.get("status") in ["ch_aprovado", "fase_escritura"]:
            property_alert = await check_property_documents(process)
            if property_alert and property_alert.get("active"):
                alerts.append(property_alert)
    except Exception as e:
        logger.warning(f"Erro ao verificar documentos do imóvel: {e}")
    
    # 5. Alerta de avaliação bancária abaixo do valor de compra
    try:
        valuation_alert = check_valuation_alert(process)
        if valuation_alert and valuation_alert.get("active"):
            alerts.append(valuation_alert)
    except Exception as e:
        logger.warning(f"Erro ao verificar avaliação: {e}")
    
    return alerts


# ====================================================================
# ALERTA DE AVALIAÇÃO BANCÁRIA
# ====================================================================

def check_valuation_alert(process: dict) -> Dict[str, Any]:
    """
    Verifica se o valor da avaliação bancária é inferior ao valor de compra.
    
    Este é um alerta CRÍTICO porque:
    - O banco só financia com base no valor de avaliação
    - Cliente terá que cobrir a diferença com capital próprio
    - Pode inviabilizar o negócio
    
    Args:
        process: Dados do processo
    
    Returns:
        dict: Alerta com detalhes ou inactive se não houver problema
    """
    # Obter dados de crédito e imóvel (usar or {} para evitar NoneType)
    credit_data = process.get("credit_data") or {}
    property_data = process.get("property_data") or {}
    financial_data = process.get("financial_data") or {}
    
    # Valor da avaliação bancária
    valuation_value = credit_data.get("valuation_value")
    if not valuation_value:
        return {"type": ALERT_TYPES["VALUATION_BELOW_PURCHASE"], "active": False}
    
    # Valor de compra/aquisição (pode estar em vários campos)
    purchase_value = (
        property_data.get("valor_imovel") or 
        financial_data.get("valor_pretendido") or
        credit_data.get("requested_amount")
    )
    
    if not purchase_value:
        return {"type": ALERT_TYPES["VALUATION_BELOW_PURCHASE"], "active": False}
    
    # Verificar se avaliação é inferior
    if valuation_value >= purchase_value:
        return {"type": ALERT_TYPES["VALUATION_BELOW_PURCHASE"], "active": False}
    
    # Calcular diferença
    difference = purchase_value - valuation_value
    percentage = ((purchase_value - valuation_value) / purchase_value) * 100
    
    # Determinar prioridade baseada na diferença
    if percentage > 20:
        priority = "critical"
        urgency_msg = "MUITO CRÍTICO - Diferença significativa!"
    elif percentage > 10:
        priority = "high"
        urgency_msg = "Crítico - Diferença relevante"
    else:
        priority = "medium"
        urgency_msg = "Atenção - Pequena diferença"
    
    return {
        "type": ALERT_TYPES["VALUATION_BELOW_PURCHASE"],
        "active": True,
        "valuation_value": valuation_value,
        "purchase_value": purchase_value,
        "difference": difference,
        "difference_percentage": round(percentage, 2),
        "valuation_bank": credit_data.get("valuation_bank"),
        "valuation_date": credit_data.get("valuation_date"),
        "message": f"⚠️ Avaliação bancária ({valuation_value:,.0f}€) abaixo do valor de compra ({purchase_value:,.0f}€)",
        "details": f"{urgency_msg}. Diferença: {difference:,.0f}€ ({percentage:.1f}%). "
                   f"O cliente precisará de capital próprio adicional para cobrir esta diferença.",
        "priority": priority,
        "recommendations": [
            "Informar o cliente imediatamente sobre a diferença",
            "Verificar se o cliente tem capital próprio adicional",
            "Considerar renegociação do preço com o vendedor",
            "Avaliar pedido de segunda avaliação noutro banco",
            "Documentar toda a comunicação com o cliente"
        ]
    }


async def notify_valuation_alert(process: dict):
    """
    Notifica os envolvidos quando há alerta de avaliação bancária.
    
    Args:
        process: Dados do processo
    """
    from services.realtime_notifications import send_realtime_notification
    
    alert = check_valuation_alert(process)
    
    if not alert.get("active"):
        return
    
    # Obter utilizadores envolvidos
    user_ids = set()
    if process.get("assigned_consultor_id"):
        user_ids.add(process["assigned_consultor_id"])
    if process.get("consultor_id"):
        user_ids.add(process["consultor_id"])
    if process.get("assigned_mediador_id"):
        user_ids.add(process["assigned_mediador_id"])
    if process.get("intermediario_id"):
        user_ids.add(process["intermediario_id"])
    
    # Sempre notificar admin/CEO para alertas críticos
    if alert.get("priority") in ["critical", "high"]:
        staff = await db.users.find({
            "role": {"$in": ["admin", "ceo", "diretor"]},
            "is_active": True
        }, {"_id": 0, "id": 1}).to_list(100)
        for s in staff:
            user_ids.add(s["id"])
    
    client_name = process.get("client_name", "Cliente")
    
    for user_id in user_ids:
        # Notificação em tempo real
        await send_realtime_notification(
            user_id=user_id,
            title=f"⚠️ Alerta de Avaliação - {client_name}",
            message=alert["message"],
            notification_type="valuation_alert",
            link=f"/process/{process['id']}",
            process_id=process["id"]
        )
        
        # Email para alertas críticos
        if alert.get("priority") in ["critical", "high"]:
            user = await db.users.find_one({"id": user_id}, {"_id": 0})
            if user:
                recommendations = "\n".join([f"• {r}" for r in alert.get("recommendations", [])])
                await send_notification_with_preference_check(
                    user["email"],
                    f"⚠️ ALERTA CRÍTICO: Avaliação Bancária - {client_name}",
                    f"Olá {user['name']},\n\n"
                    f"{alert['message']}\n\n"
                    f"{alert['details']}\n\n"
                    f"Recomendações:\n{recommendations}\n\n"
                    f"Cliente: {client_name}\n"
                    f"Processo: {process['id']}\n\n"
                    f"Por favor, tome acção imediata.",
                    notification_type="deadline",
                    is_urgent=True
                )


# ====================================================================
# NOTIFICAÇÕES DE MATCH CLIENTE-IMÓVEL
# ====================================================================

async def notify_property_match(
    property_id: str,
    property_title: str,
    matching_clients: list,
    agent_email: str = None
):
    """
    Notifica sobre matches perfeitos entre um imóvel e clientes.
    Chamada quando um novo imóvel é adicionado ou quando há matches de alta pontuação.
    """
    if not matching_clients:
        return
    
    now = datetime.now(timezone.utc).isoformat()
    
    for match in matching_clients:
        if match.get("score", 0) < MATCH_SCORE_THRESHOLD:
            continue
        
        client_name = match.get("process", {}).get("client_name", "Cliente")
        process_id = match.get("process", {}).get("id")
        score = match.get("score", 0)
        reasons = match.get("match_reasons", [])
        
        # Criar notificação no sistema
        notification = {
            "id": str(uuid.uuid4()),
            "type": ALERT_TYPES["PROPERTY_MATCH"],
            "title": f"Match Encontrado: {client_name}",
            "message": f"O cliente {client_name} tem {score}% de compatibilidade com o imóvel '{property_title}'",
            "details": {
                "property_id": property_id,
                "property_title": property_title,
                "process_id": process_id,
                "client_name": client_name,
                "score": score,
                "reasons": reasons
            },
            "process_id": process_id,
            "property_id": property_id,
            "read": False,
            "created_at": now
        }
        
        await db.notifications.insert_one(notification)
    
    # Se há agente responsável, enviar email (com verificação de preferências)
    if agent_email and matching_clients:
        top_matches = [m for m in matching_clients if m.get("score", 0) >= MATCH_SCORE_THRESHOLD][:3]
        if top_matches:
            match_list = "\n".join([
                f"- {m['process']['client_name']}: {m['score']}% compatível"
                for m in top_matches
            ])
            
            try:
                await send_notification_with_preference_check(
                    agent_email,
                    f"Novos Matches para {property_title}",
                    f"Foram encontrados {len(top_matches)} clientes com alta compatibilidade:\n\n{match_list}\n\nAceda ao sistema para ver mais detalhes.",
                    notification_type="task_assigned"
                )
            except Exception:
                pass  # Não falhar se email não enviar


async def check_and_notify_matches_for_new_property(property_id: str):
    """
    Verifica e notifica matches quando um novo imóvel é adicionado.
    Deve ser chamada após criar um imóvel.
    """
    from services.client_match import find_matching_clients_for_property
    
    prop = await db.properties.find_one({"id": property_id}, {"_id": 0})
    if not prop:
        return
    
    matches = await find_matching_clients_for_property(property_id)
    
    if matches:
        agent_email = None
        if prop.get("assigned_agent_id"):
            agent = await db.users.find_one(
                {"id": prop["assigned_agent_id"]}, 
                {"email": 1}
            )
            if agent:
                agent_email = agent.get("email")
        
        await notify_property_match(
            property_id=property_id,
            property_title=prop.get("title", "Imóvel"),
            matching_clients=matches,
            agent_email=agent_email
        )
    
    return {"matches_found": len(matches)}


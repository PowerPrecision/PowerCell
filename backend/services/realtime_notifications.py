"""
====================================================================
SERVIÇO DE NOTIFICAÇÕES EM TEMPO REAL - CREDITOIMO
====================================================================
Funções utilitárias para enviar notificações via WebSocket.
====================================================================
"""

import logging
from typing import Optional
from datetime import datetime, timedelta, timezone
import uuid

from pymongo import ReturnDocument

from database import db
from services.websocket_manager import WSEventType
from services.realtime_delivery import entregar_a_processo, entregar_a_utilizador
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
    # PACOTE DH — Agenda: lembrete de evento reusa a preferência inapp_deadline_reminder.
    "event_reminder": "inapp_deadline_reminder",
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


# Janela FIXA (desde o primeiro aviso) em que os avisos do mesmo processo se juntam.
JANELA_DE_AGRUPAMENTO_NA_APP = timedelta(minutes=10)
MAX_ITENS_DO_GRUPO = 20


def _item_do_grupo(title: str, message: str, tipo: str, quando: datetime) -> dict:
    return {"title": title, "message": message, "type": tipo, "created_at": quando.isoformat()}


def _mensagem_do_grupo(total: int, numero: Optional[str], itens: list) -> str:
    titulos: list[str] = []
    for item in reversed(itens):
        titulo = (item.get("title") or "").strip()
        if titulo and titulo not in titulos:
            titulos.append(titulo)
    resumo = ", ".join(titulos[:3]) + ("…" if len(titulos) > 3 else "")
    onde = f"no processo nº {numero}" if numero else "neste processo"
    return f"{total} novidades {onde}" + (f": {resumo}" if resumo else "")


async def _juntar_ao_aviso_do_processo(
    user_id: str, process_id: str, title: str, message: str, tipo: str, link: Optional[str]
) -> Optional[dict]:
    """Junta o aviso ao aviso por ler do mesmo processo, se a janela ainda estiver aberta."""
    agora = datetime.now(timezone.utc)
    atual = await db.notifications.find_one_and_update(
        {
            "user_id": user_id,
            "process_id": process_id,
            "read": False,
            "agrupar_ate": {"$gte": agora.isoformat()},
        },
        {
            "$inc": {"grupo_total": 1},
            "$push": {"grupo": {"$each": [_item_do_grupo(title, message, tipo, agora)], "$slice": -MAX_ITENS_DO_GRUPO}},
            "$set": {"created_at": agora.isoformat(), "type": tipo, **({"link": link} if link else {})},
        },
        sort=[("created_at", -1)],
        projection={"_id": 0},
        return_document=ReturnDocument.AFTER,
    )
    if not atual:
        return None

    # Só o número: há avisos (os do Index) que por regra não levam o nome do cliente.
    processo = await db.processes.find_one({"id": process_id}, {"_id": 0, "process_number": 1}) or {}
    numero = processo.get("process_number")
    campos = {
        "title": f"{atual.get('grupo_total', 2)} novidades",
        "message": _mensagem_do_grupo(
            int(atual.get("grupo_total") or 2),
            str(numero) if numero not in (None, "") else None,
            atual.get("grupo") or [],
        ),
        "agrupada": True,
    }
    await db.notifications.update_one({"id": atual["id"], "user_id": user_id}, {"$set": campos})
    return {**atual, **campos}


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
    # Telegram: canal à parte, com as suas próprias preferências (por isso
    # antes do filtro in-app). Agrupa por processo e nunca levanta.
    from services.telegram_notifications import agendar as agendar_telegram

    await agendar_telegram(user_id, notification_type, process_id=process_id, link=link)

    # Ruído e avisos de processos de outros ficam de fora (ver `notification_policy`).
    from services.notification_policy import deve_notificar

    if not await deve_notificar(user_id, notification_type, process_id, bd=db):
        return None

    # Verificar preferências do utilizador
    if not await _should_send_inapp_notification(user_id, notification_type):
        logger.info(f"Notificação in-app bloqueada para {user_id} (tipo: {notification_type})")
        return None

    # A rajada do mesmo processo junta-se ao aviso por ler que já lá está: um só
    # aviso no sino, sem som/toast/push repetidos (o id não muda).
    if save_to_db and process_id:
        agrupada = await _juntar_ao_aviso_do_processo(
            user_id, process_id, title, message, notification_type, link
        )
        if agrupada:
            await entregar_a_utilizador(user_id, WSEventType.NEW_NOTIFICATION, agrupada)
            return agrupada

    agora = datetime.now(timezone.utc)
    notification = {
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "title": title,
        "message": message,
        "type": notification_type,
        "link": link,
        "process_id": process_id,
        "read": False,
        "created_at": agora.isoformat()
    }
    if process_id:
        notification.update({
            "grupo_total": 1,
            "grupo": [_item_do_grupo(title, message, notification_type, agora)],
            "agrupar_ate": (agora + JANELA_DE_AGRUPAMENTO_NA_APP).isoformat(),
        })

    # Guardar na base de dados
    if save_to_db:
        await db.notifications.insert_one({**notification, "_id": notification["id"]})
        # Remover _id para resposta
        notification.pop("_id", None)
    
    # ÉPICO 10, FASE 1 — a entrega passa pelo Redis, não pela memória.
    # Este ponto fazia `if manager.is_user_connected(user_id)`, e essa
    # pergunta MENTE com vários workers: um utilizador com o socket no
    # worker B lê como desligado no worker A, o evento morria em silêncio e
    # quem entregava a notificação era, de facto, o polling de 30s do
    # `NotificationsDropdown`. Por isso o polling não era redundância — era
    # suporte de vida, e desligá-lo antes desta migração apagaria metade das
    # notificações em produção.
    await entregar_a_utilizador(user_id, WSEventType.NEW_NOTIFICATION, notification)

    # PRESENÇA GLOBAL (Ponto 2) — era aqui que a mentira custava dinheiro.
    #
    # Esta pergunta era `manager.is_user_connected(user_id)`, memória
    # LOCAL. Com dois workers, um utilizador com o socket no worker B
    # lia-se como desligado no worker A e levava um push no telemóvel
    # **enquanto estava a olhar para a aplicação**.
    #
    # O `is_notified` que se escrevia neste ramo foi REMOVIDO: era
    # escrito e não era lido em lado nenhum. Não prevenia re-emissão
    # nenhuma, ao contrário do que o comentário original afirmava.
    from services.presenca import esta_online

    if not await esta_online(user_id):
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
        tipo = "process_created"
    elif action == "status_changed":
        title = "Estado do Processo Alterado"
        message = f"O processo de {client_name} mudou para {details}"
        event_type = WSEventType.PROCESS_STATUS_CHANGED
        tipo = "process_status_change"
    elif action == "assigned":
        title = "Processo Atribuído"
        message = f"Foste atribuído ao processo de {client_name}"
        event_type = WSEventType.PROCESS_ASSIGNED
        tipo = "process_assigned"
    else:
        title = "Processo Actualizado"
        message = f"O processo de {client_name} foi actualizado"
        event_type = WSEventType.PROCESS_UPDATED
        tipo = "process_updated"  # ruído: a política deixa-o de fora
    
    # BUGFIX (E2E — privacidade das notificações, Set 2026): a notificação
    # (in-app) é enviada ESTRITAMENTE para os utilizadores atribuídos ao
    # processo. Antes expandia para TODOS os admin/CEO — a notificação de
    # atribuição aparecia a todos os admins em vez de apenas a quem o
    # processo foi atribuído. A sincronização do Kanban continua a ser
    # feita pelo delta dedicado (broadcast_process_delta), não por aqui.
    users_to_notify = _collect_process_assignee_ids(process)
    
    # Enviar notificações
    for user_id in users_to_notify:
        await send_realtime_notification(
            user_id=user_id,
            title=title,
            message=message,
            notification_type=tipo,
            link=f"/process/{process_id}",
            process_id=process_id
        )
    
    # ÉPICO 10, FASE 2 — isto era um `manager.broadcast()`, e o comentário
    # que o acompanhava dizia "sem dados sensíveis" apesar de o payload
    # levar o `client_name`. Levava-o para TODOS os sockets ligados,
    # incluindo os de outra rede. Hoje vai para a audiência do processo.
    await entregar_a_processo(
        process,
        event_type,
        {
            "process_id": process_id,
            "client_name": client_name,
            "action": action,
            "actor": actor_name,
            "details": details,
        },
    )


def _collect_process_assignee_ids(process: dict) -> set:
    """
    IDs únicos de TODOS os utilizadores atribuídos ao processo.

    BUGFIX (E2E — privacidade das notificações, Set 2026): centraliza o
    destinatário das notificações de processo — ESTRITAMENTE quem está
    atribuído (consultor/intermediário/indexador, campos singulares e
    plurais). Substitui a expansão indiscriminada para admin/CEO/diretor
    que fazia a notificação de atribuição aparecer a todos os admins.
    """
    raw = []
    # Consultor (singular legado + assign explícito + plural)
    raw.append(process.get("consultor_id"))
    raw.append(process.get("assigned_consultor_id"))
    raw += (process.get("assigned_consultor_ids") or [])
    # Intermediário/mediador (idem)
    raw.append(process.get("mediador_id"))
    raw.append(process.get("assigned_mediador_id"))
    raw += (process.get("assigned_mediador_ids") or [])
    # Indexador atribuído
    raw.append(process.get("assigned_indexacao_id"))
    return {uid for uid in raw if uid}


async def notify_deadline_reminder(deadline: dict, minutes_before: int = 30):
    """
    Enviar lembrete de prazo/evento.
    
    Args:
        deadline: Dados do prazo/evento
        minutes_before: Minutos antes do evento
    """
    # PACOTE DH — Bugfix: ler assigned_user_ids (campo correcto do schema) em vez de participants.
    assigned_user_ids = deadline.get("assigned_user_ids", []) or []
    
    if not assigned_user_ids:
        return
    
    title = f"⏰ Lembrete: {deadline.get('title', 'Evento')}"
    message = f"O evento começa em {minutes_before} minutos"
    
    for user_id in assigned_user_ids:
        await send_realtime_notification(
            user_id=user_id,
            title=title,
            message=message,
            notification_type="warning",
            link="/calendario"
        )
        
        # Dirigido, e por isso atravessa a fronteira do worker (Fase 1):
        # o `is_user_connected` que aqui estava fazia este lembrete morrer
        # sempre que o socket vivesse no outro processo uvicorn.
        await entregar_a_utilizador(
            user_id,
            WSEventType.DEADLINE_REMINDER,
            {
                "deadline_id": deadline.get("id"),
                "title": deadline.get("title"),
                # PACOTE DH — usar due_date (campo correcto) com fallback para date (legacy).
                "date": deadline.get("due_date") or deadline.get("date"),
                "minutes_before": minutes_before,
            },
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
    # BUGFIX (E2E — privacidade das notificações, Set 2026): o payload é
    # enviado ESTRITAMENTE para os user_ids atribuídos ao processo.
    # Antes, além dos atribuídos, TODOS os admin/CEO/diretor recebiam a
    # notificação a CADA mudança de fase — incluindo a notificação de
    # atribuição quando o processo entrava no Index (o sintoma reportado:
    # "a notificação de atribuição está a aparecer a todos os admins").
    # A visão global da gestão continua garantida pelos dashboards/Kanban.
    users_to_notify = _collect_process_assignee_ids(process)
    
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

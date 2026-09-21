"""WebSocket notifications for newly inserted IMAP/Gmail emails.

Pacote EC — when a sync path inserts an email that did not exist before,
emit ``new_email`` to that user's WebSocket room so the Webmail UI can
refetch silently.

ÉPICO 5 — TRANSPORTE VIA REDIS PUB/SUB
--------------------------------------
Esta emissão usava directamente o ``ConnectionManager`` em memória. Isso
funciona num só processo, mas com vários workers Uvicorn (o cenário real
depois do Épico 4) um email sincronizado no worker A nunca chegava a um
socket aberto no worker B: o `is_user_connected` do worker A respondia
`False` e o evento era **descartado em silêncio**.

A emissão passa agora por ``services.redis_pubsub.publish_event``, o mesmo
canal dos eventos de tarefa. O envelope leva o ``user_id`` do destinatário
e o router (`websocket_manager.route_system_event`) entrega-o apenas às
ligações desse utilizador, no worker onde elas viverem.

Degradação graciosa: sem Redis (ou com ele em baixo), `publish_event` cai
para entrega in-process — exactamente o comportamento anterior. A
sincronização IMAP nunca quebra por causa de um socket ou de um Redis.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Iterable, Optional, Sequence, Union

from services.redis_pubsub import publish_event
from services.websocket_manager import WSEventType, create_ws_message, manager

logger = logging.getLogger(__name__)

NEW_EMAIL_EVENT = "new_email"
NEW_EMAIL_MESSAGE = "Novo email recebido"
USER_ROOM_PREFIX = "user_"


def user_email_room(user_id: str) -> str:
    """Stable room name for a staff user's personal WebSocket channel."""
    return f"{USER_ROOM_PREFIX}{user_id}"


def join_user_email_room(user_id: str) -> str:
    """Subscribe the connected user to their personal email room.

    Called on WebSocket connect so later ``broadcast_to_room`` reaches them.
    """
    room = user_email_room(user_id)
    manager.join_room(room, user_id)
    return room


def build_new_email_payload(
    email_doc: Optional[Dict[str, Any]] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> dict:
    """Constrói o ``data`` do evento ``new_email``.

    É um SINAL, não o email: leva o suficiente para a lista inserir uma
    linha sem esperar por um GET (remetente, assunto, pasta, lido). O corpo
    e os anexos vêm depois, quando o utilizador abre a mensagem.

    ``is_read`` vai explícito a ``False`` para o contador de não-lidos do
    Webmail poder incrementar sem consultar o servidor.
    """
    doc = email_doc or {}
    extra = extra or {}
    is_received = doc.get("direction", extra.get("direction", "received")) == "received"
    payload = {
        "email_id": doc.get("id", ""),
        "from_email": doc.get("from_email", ""),
        "subject": doc.get("subject", ""),
        "account": doc.get("account", ""),
        "folder": extra.get("folder") or ("inbox" if is_received else "sent"),
        "direction": doc.get("direction", extra.get("direction", "received")),
        "message": NEW_EMAIL_MESSAGE,
    }
    # Campos que permitem à lista inserir a linha sem refetch.
    for key in ("sent_at", "created_at", "to_emails", "is_read", "process_id"):
        if doc.get(key) is not None:
            payload[key] = doc[key]
    payload.setdefault("is_read", False)

    if extra.get("box"):
        payload["box"] = extra["box"]
    for key, value in extra.items():
        if key not in payload and value is not None:
            payload[key] = value
    return payload


def build_new_email_ws_message(
    email_doc: Optional[Dict[str, Any]] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> dict:
    """Envelope WebSocket completo do ``new_email``.

    Mantido para a entrega in-process e para quem já dependia da forma
    ``type``/``data`` mais ``event``/``message`` no topo (Pacote EC).
    """
    ws_msg = create_ws_message(
        WSEventType.NEW_EMAIL, build_new_email_payload(email_doc, extra)
    )
    ws_msg["event"] = NEW_EMAIL_EVENT
    ws_msg["message"] = NEW_EMAIL_MESSAGE
    return ws_msg


def _normalize_user_ids(user_ids: Union[str, Sequence[str], None]) -> list:
    if not user_ids:
        return []
    if isinstance(user_ids, str):
        return [user_ids] if user_ids else []
    return [uid for uid in user_ids if uid]


async def notify_new_email(
    user_ids: Union[str, Iterable[str], None],
    email_doc: Optional[Dict[str, Any]] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> int:
    """Emite ``new_email`` para cada destinatário, via canal Redis.

    UM ENVELOPE POR DESTINATÁRIO, nunca uma difusão: é o mesmo contrato de
    tenant-safety dos eventos de tarefa. O router a jusante descarta
    qualquer envelope sem ``user_id`` em vez de o mandar para todos, pelo
    que um email do utilizador A não pode aparecer no Webmail do B.

    NÃO filtra por ``is_user_connected``: essa era precisamente a falha de
    multi-worker. O worker que corre a sincronização IMAP raramente é o que
    detém o socket do utilizador, e perguntar-lhe se está ligado *aqui*
    respondia `False` e deitava o evento fora. Quem sabe responder a isso é
    o worker dono da ligação, depois de receber o envelope.

    Falhas são registadas e nunca propagadas — a sincronização de email não
    pode quebrar porque um socket ou o Redis estão em baixo.

    Returns:
        Número de destinatários para os quais o evento foi emitido (não o
        número de sockets que o receberam — isso acontece noutros workers).
    """
    targets = _normalize_user_ids(user_ids)
    if not targets:
        return 0

    payload = build_new_email_payload(email_doc, extra)
    company_id = (email_doc or {}).get("company_id")

    notified = 0
    for uid in targets:
        try:
            await publish_event(
                NEW_EMAIL_EVENT,
                payload,
                user_id=uid,
                company_id=company_id,
            )
            # `publish_event` devolve False quando degrada para entrega
            # in-process. Isso não é um erro nem uma não-entrega: o
            # utilizador ligado a ESTE worker continua a receber. Contamos
            # a emissão, não o transporte.
            notified += 1
        except Exception as ws_err:
            logger.debug(
                "[Email Realtime] WS NEW_EMAIL falhou para %s (non-critical): %s",
                uid,
                ws_err,
            )
    return notified


async def notify_new_email_for_global_mailbox(email_doc: Dict[str, Any]) -> int:
    """Notify staff with access to the shared/global mailbox."""
    try:
        from database import db

        to_set = {str(e).lower() for e in (email_doc.get("to_emails") or []) if e}
        cc_set = {str(e).lower() for e in (email_doc.get("cc_emails") or []) if e}
        all_recipients = to_set | cc_set
        is_received = email_doc.get("direction") == "received"

        user_ids = []
        staff_cursor = db.users.find(
            {"is_active": {"$ne": False}},
            {"_id": 0, "id": 1, "role": 1, "email": 1},
        )
        async for user in staff_cursor:
            uid = user.get("id")
            if not uid:
                continue
            role = user.get("role")
            if role in ("admin", "ceo", "diretor", "administrativo"):
                user_ids.append(uid)
            elif (user.get("email") or "").lower() in all_recipients:
                user_ids.append(uid)
            elif role == "indexacao" and is_received:
                user_ids.append(uid)

        return await notify_new_email(user_ids, email_doc, extra={"box": "general"})
    except Exception as ws_err:
        logger.debug("[Email Realtime] global mailbox NEW_EMAIL falhou (non-critical): %s", ws_err)
        return 0


async def notify_new_email_for_shared_role(role: str, email_doc: Dict[str, Any]) -> int:
    """Notify every connected user that holds the shared mailbox role."""
    if not role:
        return 0
    try:
        from database import db

        user_ids = []
        cursor = db.users.find(
            {"role": role, "is_active": {"$ne": False}},
            {"_id": 0, "id": 1},
        )
        async for user in cursor:
            uid = user.get("id")
            if uid:
                user_ids.append(uid)
        return await notify_new_email(
            user_ids,
            email_doc,
            extra={"box": f"shared_{role}", "shared_role": role},
        )
    except Exception as ws_err:
        logger.debug(
            "[Email Realtime] shared role %s NEW_EMAIL falhou (non-critical): %s",
            role,
            ws_err,
        )
        return 0

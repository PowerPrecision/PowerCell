"""WebSocket notifications for newly inserted IMAP/Gmail emails.

Pacote EC — when a sync path inserts an email that did not exist before,
emit ``new_email`` to that user's WebSocket room so the Webmail UI can
refetch silently.

The in-memory ConnectionManager lives in the API process. Sync that runs
inside uvicorn (``run_email_auto_sync``) can reach connected clients;
a separate worker process cannot.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Iterable, Optional, Sequence, Union

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


def build_new_email_ws_message(
    email_doc: Optional[Dict[str, Any]] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> dict:
    """Build the canonical ``new_email`` payload.

    Keeps the existing ``type`` / ``data`` envelope (frontend dispatcher) and
    also exposes ``event`` + ``message`` at the top level as specified by
    Pacote EC.
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
    if extra.get("box"):
        payload["box"] = extra["box"]
    for key, value in extra.items():
        if key not in payload and value is not None:
            payload[key] = value

    ws_msg = create_ws_message(WSEventType.NEW_EMAIL, payload)
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
    """Emit ``new_email`` to each user's room after a fresh insert.

    Skips users that are not currently connected. Failures are logged and
    never raised — IMAP sync must not break because a socket is down.

    Returns:
        Number of users the event was sent to.
    """
    targets = _normalize_user_ids(user_ids)
    if not targets:
        return 0

    ws_msg = build_new_email_ws_message(email_doc, extra)
    notified = 0
    for uid in targets:
        try:
            if not manager.is_user_connected(uid):
                continue
            room = user_email_room(uid)
            if not manager.is_in_room(room, uid):
                manager.join_room(room, uid)
            await manager.broadcast_to_room(room, ws_msg)
            # Room broadcast is a no-op if the room was empty; personal
            # send covers that without duplicating (broadcast already uses it
            # when the user is a room member).
            if not manager.is_in_room(room, uid):
                await manager.send_personal_message(ws_msg, uid)
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

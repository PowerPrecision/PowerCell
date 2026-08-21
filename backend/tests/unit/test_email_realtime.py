"""Pacote EC — IMAP auto-sync interval + WebSocket new_email helpers."""
import asyncio
from unittest.mock import AsyncMock, MagicMock

from services.email_realtime import (
    NEW_EMAIL_EVENT,
    NEW_EMAIL_MESSAGE,
    build_new_email_ws_message,
    notify_new_email,
    user_email_room,
)
from services.scheduled_tasks import get_email_auto_sync_interval_seconds
from services.websocket_manager import WSEventType


def test_user_email_room_name():
    assert user_email_room("abc-123") == "user_abc-123"


def test_build_new_email_ws_message_shape():
    msg = build_new_email_ws_message(
        {
            "id": "e1",
            "from_email": "ana@cliente.pt",
            "subject": "IRS",
            "direction": "received",
            "account": "geral@x.pt",
        }
    )
    assert msg["type"] == WSEventType.NEW_EMAIL
    assert msg["event"] == NEW_EMAIL_EVENT
    assert msg["message"] == NEW_EMAIL_MESSAGE
    assert msg["data"]["email_id"] == "e1"
    assert msg["data"]["from_email"] == "ana@cliente.pt"
    assert msg["data"]["folder"] == "inbox"
    assert msg["data"]["message"] == NEW_EMAIL_MESSAGE
    assert "timestamp" in msg


def test_get_email_auto_sync_interval_seconds(monkeypatch):
    monkeypatch.delenv("EMAIL_AUTO_SYNC_INTERVAL_SECONDS", raising=False)
    assert get_email_auto_sync_interval_seconds() == 60

    monkeypatch.setenv("EMAIL_AUTO_SYNC_INTERVAL_SECONDS", "90")
    assert get_email_auto_sync_interval_seconds() == 90

    monkeypatch.setenv("EMAIL_AUTO_SYNC_INTERVAL_SECONDS", "5")
    assert get_email_auto_sync_interval_seconds() == 30

    monkeypatch.setenv("EMAIL_AUTO_SYNC_INTERVAL_SECONDS", "9999")
    assert get_email_auto_sync_interval_seconds() == 300

    monkeypatch.setenv("EMAIL_AUTO_SYNC_INTERVAL_SECONDS", "nope")
    assert get_email_auto_sync_interval_seconds() == 60


def test_notify_new_email_skips_disconnected(monkeypatch):
    from services import email_realtime as mod

    monkeypatch.setattr(mod.manager, "is_user_connected", lambda _uid: False)
    broadcast = AsyncMock()
    monkeypatch.setattr(mod.manager, "broadcast_to_room", broadcast)

    count = asyncio.run(notify_new_email("u1", {"id": "e1", "direction": "received"}))
    assert count == 0
    broadcast.assert_not_called()


def test_notify_new_email_broadcasts_to_user_room(monkeypatch):
    from services import email_realtime as mod

    monkeypatch.setattr(mod.manager, "is_user_connected", lambda _uid: True)
    monkeypatch.setattr(mod.manager, "is_in_room", lambda _room, _uid: True)
    monkeypatch.setattr(mod.manager, "join_room", MagicMock())
    broadcast = AsyncMock()
    monkeypatch.setattr(mod.manager, "broadcast_to_room", broadcast)
    monkeypatch.setattr(mod.manager, "send_personal_message", AsyncMock())

    count = asyncio.run(
        notify_new_email(
            "user-1",
            {
                "id": "e1",
                "from_email": "ana@x.pt",
                "subject": "Olá",
                "direction": "received",
                "account": "ana@x.pt",
            },
        )
    )
    assert count == 1
    broadcast.assert_awaited()
    room, msg = broadcast.await_args.args[:2]
    assert room == "user_user-1"
    assert msg["event"] == "new_email"
    assert msg["message"] == "Novo email recebido"
    assert msg["type"] == "new_email"
    assert msg["data"]["from_email"] == "ana@x.pt"


def test_websocket_connect_joins_user_email_room():
    from pathlib import Path

    text = Path(__file__).resolve().parents[2].joinpath(
        "services", "websocket_api_notifications.py"
    ).read_text()
    assert "join_user_email_room" in text
    assert "manager.connect" in text


def test_api_startup_uses_configurable_email_sync_interval():
    from pathlib import Path

    server = Path(__file__).resolve().parents[2].joinpath("server.py").read_text()
    assert "get_email_auto_sync_interval_seconds" in server
    assert "interval_seconds=180" not in server
    tasks = Path(__file__).resolve().parents[2].joinpath(
        "services", "scheduled_tasks.py"
    ).read_text()
    assert "_DEFAULT_EMAIL_AUTO_SYNC_INTERVAL = 60" in tasks
    assert "random.randint(0, 60)" not in tasks

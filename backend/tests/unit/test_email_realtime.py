"""Pacote EC — IMAP auto-sync interval + WebSocket new_email helpers."""
import asyncio
from unittest.mock import AsyncMock

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
    """Cadência do auto-sync IMAP.

    Os valores mudaram no Lote 5 (fecho do ponto 7): o ciclo de 60s com
    clamp 30–300s era o que estava a apanhar rate limit / bloqueio de IP
    no alojamento partilhado. Passou a 5 minutos, com o chão em 2 min
    para que uma variável mal posta não reabra o bloqueio. Ver
    `services/email_sync_cadence.py` e `tests/unit/test_imap_cadencia.py`.
    """
    monkeypatch.delenv("EMAIL_AUTO_SYNC_INTERVAL_SECONDS", raising=False)
    assert get_email_auto_sync_interval_seconds() == 300

    monkeypatch.setenv("EMAIL_AUTO_SYNC_INTERVAL_SECONDS", "600")
    assert get_email_auto_sync_interval_seconds() == 600

    monkeypatch.setenv("EMAIL_AUTO_SYNC_INTERVAL_SECONDS", "5")
    assert get_email_auto_sync_interval_seconds() == 120

    monkeypatch.setenv("EMAIL_AUTO_SYNC_INTERVAL_SECONDS", "9999")
    assert get_email_auto_sync_interval_seconds() == 1800

    monkeypatch.setenv("EMAIL_AUTO_SYNC_INTERVAL_SECONDS", "nope")
    assert get_email_auto_sync_interval_seconds() == 300


# ====================================================================
# ÉPICO 5 — emissão via canal Redis (ver docstring de email_realtime)
# ====================================================================
# Estes dois testes afirmavam o comportamento ANTERIOR: entrega directa
# pelo ConnectionManager deste processo, saltando quem não estivesse
# ligado *aqui*. Isso era o bug de multi-worker — o worker que corre a
# sincronização IMAP quase nunca é o que detém o socket do utilizador.
# Passam a afirmar o contrato novo: um envelope publicado POR
# DESTINATÁRIO, entregue pelo worker que tiver a ligação.


def test_notify_new_email_publishes_even_if_not_connected_here(monkeypatch):
    """Não estar ligado a ESTE worker não pode cancelar o evento.

    Regressão directa do bug: o socket do utilizador pode viver noutro
    processo, e é esse que decide se há a quem entregar.
    """
    from services import email_realtime as mod

    monkeypatch.setattr(mod.manager, "is_user_connected", lambda _uid: False)
    published = AsyncMock(return_value=True)
    monkeypatch.setattr(mod, "publish_event", published)

    count = asyncio.run(notify_new_email("u1", {"id": "e1", "direction": "received"}))

    assert count == 1, "o evento tem de ser emitido à mesma"
    published.assert_awaited_once()
    assert published.await_args.kwargs["user_id"] == "u1"


def test_notify_new_email_publishes_one_envelope_per_recipient(monkeypatch):
    """Tenant-safety: um envelope endereçado a cada um, nunca uma difusão."""
    from services import email_realtime as mod

    published = AsyncMock(return_value=True)
    monkeypatch.setattr(mod, "publish_event", published)

    count = asyncio.run(
        notify_new_email(
            ["user-1", "user-2"],
            {
                "id": "e1",
                "from_email": "ana@x.pt",
                "subject": "Olá",
                "direction": "received",
                "account": "ana@x.pt",
            },
        )
    )

    assert count == 2
    assert published.await_count == 2
    destinatarios = [c.kwargs["user_id"] for c in published.await_args_list]
    assert destinatarios == ["user-1", "user-2"]

    event_type, payload = published.await_args_list[0].args[:2]
    assert event_type == "new_email"
    assert payload["from_email"] == "ana@x.pt"
    assert payload["folder"] == "inbox"
    assert payload["is_read"] is False, "a lista incrementa não-lidos sem ir ao servidor"


def test_notify_new_email_survives_publish_failure(monkeypatch):
    """Um Redis em baixo não pode rebentar a sincronização IMAP."""
    from services import email_realtime as mod

    monkeypatch.setattr(
        mod, "publish_event", AsyncMock(side_effect=RuntimeError("redis morto"))
    )

    count = asyncio.run(notify_new_email("u1", {"id": "e1", "direction": "received"}))
    assert count == 0, "falha de transporte conta como não-emitido, mas não levanta"


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
    # A cadência vive agora em `email_sync_cadence` (ponto único partilhado
    # com o Monitor de Sinais Vitais, que não pode importar o módulo pesado
    # de tarefas agendadas). O `scheduled_tasks` re-exporta-a.
    tasks = Path(__file__).resolve().parents[2].joinpath(
        "services", "scheduled_tasks.py"
    ).read_text()
    assert "from services.email_sync_cadence import" in tasks
    assert "jitter_do_auto_sync(interval_seconds)" in tasks, (
        "o jitter tem de ser proporcional ao ciclo; um tecto fixo de 15s "
        "num ciclo de 5 min não desencontra os workers"
    )
    cadencia = Path(__file__).resolve().parents[2].joinpath(
        "services", "email_sync_cadence.py"
    ).read_text()
    assert "DEFAULT_INTERVAL_SECONDS = 300" in cadencia
    assert "MIN_INTERVAL_SECONDS = 120" in cadencia

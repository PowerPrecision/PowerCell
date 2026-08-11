"""Unit tests for websocket route thinning helpers (websocket_api_*)."""

from pathlib import Path


def test_websocket_api_modules_exist():
    services_dir = Path(__file__).resolve().parents[2] / "services"
    expected = [
        "websocket_api_helpers.py",
        "websocket_api_notifications.py",
        "websocket_api_status.py",
    ]
    for name in expected:
        assert (services_dir / name).exists(), f"missing {name}"
    files = sorted(p.name for p in services_dir.glob("websocket_api_*.py"))
    assert files == expected
    # Do not overwrite websocket_manager.py
    assert (services_dir / "websocket_manager.py").exists()
    assert (services_dir / "websocket_manager.py").read_text().count("\n") > 50
    assert not (services_dir / "websocket.py").exists()


def test_websocket_api_export_run_entrypoints():
    from services import (
        websocket_api_helpers,
        websocket_api_notifications,
        websocket_api_status,
    )

    assert callable(websocket_api_helpers.verify_websocket_token)
    assert callable(websocket_api_helpers.is_disconnect_error)
    assert callable(websocket_api_notifications.run_websocket_notifications)
    assert callable(websocket_api_status.run_websocket_status)


def test_is_disconnect_error_detects_common_cases():
    from services.websocket_api_helpers import is_disconnect_error

    assert is_disconnect_error(RuntimeError("Cannot call receive once a disconnect"))
    assert is_disconnect_error(ConnectionError("connection reset by peer"))
    assert not is_disconnect_error(ValueError("unrelated"))


def test_websocket_router_is_thin_stubs_only():
    routes_path = Path(__file__).resolve().parents[2] / "routes" / "websocket.py"
    text = routes_path.read_text()
    assert "await run_websocket_notifications" in text
    assert "return await run_websocket_status" in text
    assert len(text.splitlines()) < 50
    assert "/ws/notifications" in text
    assert "/ws/status" in text
    assert "mark_notification_read" not in text

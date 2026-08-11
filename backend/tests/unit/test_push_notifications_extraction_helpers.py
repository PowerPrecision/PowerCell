"""Unit tests for push_notifications route thinning (push_notifications_api_*)."""

from pathlib import Path


def test_push_notifications_api_modules_exist():
    services_dir = Path(__file__).resolve().parents[2] / "services"
    expected = [
        "push_notifications_api_status.py",
        "push_notifications_api_subscribe.py",
    ]
    for name in expected:
        assert (services_dir / name).exists(), f"missing {name}"
    files = sorted(p.name for p in services_dir.glob("push_notifications_api_*.py"))
    assert files == expected
    # NEVER overwrite core push_notifications.py
    assert (services_dir / "push_notifications.py").exists()


def test_push_notifications_api_export_run_entrypoints():
    from services import (
        push_notifications_api_subscribe,
        push_notifications_api_status,
    )

    assert callable(push_notifications_api_subscribe.run_subscribe_push)
    assert callable(push_notifications_api_subscribe.run_unsubscribe_push)
    assert callable(push_notifications_api_subscribe.run_unsubscribe_all_push)
    assert callable(push_notifications_api_status.run_get_push_status)
    assert push_notifications_api_subscribe.PushSubscriptionRequest is not None


def test_push_notifications_router_is_thin_stubs_only():
    routes_path = Path(__file__).resolve().parents[2] / "routes" / "push_notifications.py"
    text = routes_path.read_text()
    assert text.count("return await run_") >= 4
    assert len(text.splitlines()) < 80
    assert "push_subscriptions" not in text
    assert "uuid.uuid4" not in text

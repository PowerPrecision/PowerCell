"""Unit tests for alerts route thinning (alerts_api_*)."""

from pathlib import Path


def test_alerts_api_modules_exist():
    services_dir = Path(__file__).resolve().parents[2] / "services"
    expected = [
        "alerts_api_notifications.py",
        "alerts_api_process.py",
    ]
    for name in expected:
        assert (services_dir / name).exists(), f"missing {name}"
    files = sorted(p.name for p in services_dir.glob("alerts_api_*.py"))
    assert files == expected
    # NEVER overwrite services/alerts.py
    assert (services_dir / "alerts.py").exists()


def test_alerts_api_export_run_entrypoints():
    from services import alerts_api_process, alerts_api_notifications

    assert callable(alerts_api_process.run_get_alerts_for_process)
    assert callable(alerts_api_process.run_check_age_eligibility)
    assert callable(alerts_api_process.run_get_pre_approval_countdown)
    assert callable(alerts_api_process.run_get_document_alerts)
    assert callable(alerts_api_process.run_check_property_docs)
    assert callable(alerts_api_process.run_create_deed_reminder)
    assert callable(alerts_api_notifications.run_get_notifications)
    assert callable(alerts_api_notifications.run_mark_notification_read)


def test_alerts_api_uses_core_alerts_service():
    import inspect
    from services import alerts_api_process

    src = inspect.getsource(alerts_api_process)
    assert "from services.alerts import" in src
    assert "get_process_alerts" in src


def test_alerts_router_is_thin_stubs_only():
    routes_path = Path(__file__).resolve().parents[2] / "routes" / "alerts.py"
    text = routes_path.read_text()
    assert text.count("return await run_") >= 8
    assert len(text.splitlines()) < 120
    assert "assigned_consultor_id" not in text
    assert "create_deed_reminder(" not in text or "run_create_deed_reminder" in text

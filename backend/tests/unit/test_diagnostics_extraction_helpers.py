"""Unit tests for diagnostics route thinning helpers."""

from datetime import datetime, timezone


def test_datetime_to_str_helpers():
    from services.diagnostics_helpers import datetime_to_str

    assert datetime_to_str(None) is None
    dt = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
    assert datetime_to_str(dt) == dt.isoformat()
    assert datetime_to_str("already-a-string") == "already-a-string"
    assert datetime_to_str(42) == "42"


def test_diagnostics_models_export():
    from services.diagnostics_helpers import (
        ServiceStatus,
        SystemDiagnostics,
        TTLMigrationResult,
        TTLMigrationResponse,
    )

    status = ServiceStatus(
        name="Test",
        configured=True,
        status="ok",
        message="ok",
    )
    assert status.status == "ok"

    assert SystemDiagnostics.__name__ == "SystemDiagnostics"
    assert TTLMigrationResult.__name__ == "TTLMigrationResult"
    assert TTLMigrationResponse.__name__ == "TTLMigrationResponse"


def test_diagnostics_modules_export_run_entrypoints():
    from services import (
        diagnostics_helpers,
        diagnostics_checks,
        diagnostics_system,
        diagnostics_security,
        diagnostics_ttl,
    )

    assert callable(diagnostics_helpers.datetime_to_str)

    assert callable(diagnostics_checks.check_email_service)
    assert callable(diagnostics_checks.check_storage_service)
    assert callable(diagnostics_checks.check_ai_service)
    assert callable(diagnostics_checks.check_backup_service)
    assert callable(diagnostics_checks.check_notifications_service)

    assert callable(diagnostics_system.run_get_system_diagnostics)
    assert callable(diagnostics_system.run_get_service_diagnostics)
    assert callable(diagnostics_system.run_quick_system_check)

    assert callable(diagnostics_security.run_check_encryption_status)
    assert callable(diagnostics_security.run_check_pii_compliance)
    assert callable(diagnostics_security.run_test_openai_api_privacy)

    assert callable(diagnostics_ttl.run_migrate_ttl_datetime_fields)
    assert callable(diagnostics_ttl.run_get_ttl_index_status)


def test_diagnostics_router_is_thin_stubs_only():
    from pathlib import Path

    routes_path = Path(__file__).resolve().parents[2] / "routes" / "diagnostics.py"
    text = routes_path.read_text()
    assert text.count("return await run_") >= 8
    assert len(text.splitlines()) < 200


def test_diagnostics_no_collision_with_kanban_diagnose():
    """Ensure thinning used diagnostics_* prefix and did not overwrite process_kanban_diagnose."""
    from pathlib import Path
    from services import process_kanban_diagnose

    assert callable(process_kanban_diagnose.check_workflow_statuses)

    services_dir = Path(__file__).resolve().parents[2] / "services"
    diagnostics_files = sorted(p.name for p in services_dir.glob("diagnostics_*.py"))
    assert diagnostics_files == [
        "diagnostics_checks.py",
        "diagnostics_helpers.py",
        "diagnostics_security.py",
        "diagnostics_system.py",
        "diagnostics_ttl.py",
    ]

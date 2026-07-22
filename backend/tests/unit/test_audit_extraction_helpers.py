"""Unit tests for audit route thinning (audit_api_*)."""

from pathlib import Path


def test_audit_api_modules_exist():
    services_dir = Path(__file__).resolve().parents[2] / "services"
    expected = [
        "audit_api_cleanup.py",
        "audit_api_export.py",
        "audit_api_trail.py",
    ]
    for name in expected:
        assert (services_dir / name).exists(), f"missing {name}"
    files = sorted(p.name for p in services_dir.glob("audit_api_*.py"))
    assert files == expected
    assert (services_dir / "audit_trail_service.py").exists()


def test_audit_api_export_run_entrypoints():
    from services import audit_api_trail, audit_api_export, audit_api_cleanup

    assert callable(audit_api_trail.run_list_audit_trail)
    assert callable(audit_api_trail.run_audit_statistics)
    assert callable(audit_api_export.run_export_audit)
    assert callable(audit_api_cleanup.run_trigger_cleanup)


def test_audit_router_is_thin_stubs_only():
    routes_path = Path(__file__).resolve().parents[2] / "routes" / "audit.py"
    text = routes_path.read_text()
    assert text.count("return await run_") >= 4
    assert len(text.splitlines()) < 110
    assert "export_audit_trail" not in text
    assert "cleanup_old_records" not in text

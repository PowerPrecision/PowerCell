"""Unit tests for portal_admin route thinning (portal_admin_api_*)."""

from pathlib import Path


def test_portal_admin_api_modules_exist():
    services_dir = Path(__file__).resolve().parents[2] / "services"
    expected = ["portal_admin_api_impersonate.py"]
    for name in expected:
        assert (services_dir / name).exists(), f"missing {name}"
    files = sorted(p.name for p in services_dir.glob("portal_admin_api_*.py"))
    assert files == expected


def test_portal_admin_api_export_run_entrypoints():
    from services import portal_admin_api_impersonate

    assert callable(portal_admin_api_impersonate.run_impersonate_client_portal)


def test_portal_admin_api_uses_magic_link():
    import inspect
    from services import portal_admin_api_impersonate

    src = inspect.getsource(portal_admin_api_impersonate)
    assert "issue_portal_magic_link" in src
    assert "log_audit_event" in src


def test_portal_admin_router_is_thin_stubs_only():
    routes_path = Path(__file__).resolve().parents[2] / "routes" / "portal_admin.py"
    text = routes_path.read_text()
    assert text.count("return await run_") >= 1
    assert len(text.splitlines()) < 40
    assert "issue_portal_magic_link" not in text
    assert "impersonated_by" not in text

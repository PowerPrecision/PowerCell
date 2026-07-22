"""Unit tests for admin_encryption route thinning (admin_encryption_api_*)."""

from pathlib import Path


def test_admin_encryption_api_modules_exist():
    services_dir = Path(__file__).resolve().parents[2] / "services"
    expected = [
        "admin_encryption_api_migrate.py",
        "admin_encryption_api_status.py",
        "admin_encryption_api_verify.py",
    ]
    for name in expected:
        assert (services_dir / name).exists(), f"missing {name}"
    files = sorted(p.name for p in services_dir.glob("admin_encryption_api_*.py"))
    assert files == expected
    # NEVER create services/admin_encryption.py
    assert not (services_dir / "admin_encryption.py").exists()


def test_admin_encryption_api_export_run_entrypoints():
    from services import (
        admin_encryption_api_status,
        admin_encryption_api_migrate,
        admin_encryption_api_verify,
    )

    assert callable(admin_encryption_api_status.run_get_encryption_status)
    assert callable(admin_encryption_api_migrate.run_migrate_encryption)
    assert callable(admin_encryption_api_migrate.run_migrate_encryption_sync)
    assert callable(admin_encryption_api_verify.run_verify_process_encryption)
    assert callable(admin_encryption_api_verify.run_encrypt_single_process)


def test_admin_encryption_api_uses_encryption_service():
    import inspect

    from services import admin_encryption_api_status, admin_encryption_api_verify

    assert "encryption_service" in inspect.getsource(admin_encryption_api_status)
    assert "encryption_service" in inspect.getsource(admin_encryption_api_verify)


def test_admin_encryption_router_is_thin_stubs_only():
    routes_path = Path(__file__).resolve().parents[2] / "routes" / "admin_encryption.py"
    text = routes_path.read_text()
    assert text.count("return await run_") >= 5
    assert len(text.splitlines()) < 90
    assert "encrypt_process" not in text or "run_encrypt_single_process" in text
    assert "sample_processes" not in text

"""Unit tests for admin_migration route thinning helpers (admin_migration_api_*)."""


def test_admin_migration_api_modules_exist():
    from pathlib import Path

    services_dir = Path(__file__).resolve().parents[2] / "services"
    expected = [
        "admin_migration_api_helpers.py",
        "admin_migration_api_run.py",
        "admin_migration_api_status.py",
        "admin_migration_api_task.py",
    ]
    for name in expected:
        assert (services_dir / name).exists(), f"missing {name}"
    files = sorted(p.name for p in services_dir.glob("admin_migration_api_*.py"))
    assert files == expected
    assert not (services_dir / "admin_migration.py").exists()


def test_admin_migration_api_export_run_entrypoints():
    from services import (
        admin_migration_api_helpers,
        admin_migration_api_task,
        admin_migration_api_status,
        admin_migration_api_run,
    )

    assert callable(admin_migration_api_helpers.is_encrypted)
    assert callable(admin_migration_api_helpers.pct)
    assert callable(admin_migration_api_helpers.build_client_encryption_updates)
    assert callable(admin_migration_api_task.run_migration_task)
    assert callable(admin_migration_api_status.run_get_migration_status)
    assert callable(admin_migration_api_run.run_start_migration)
    assert callable(admin_migration_api_run.run_migration_single)


def test_is_encrypted_detects_enc_prefix():
    from services.admin_migration_api_helpers import is_encrypted, pct

    assert is_encrypted("ENC:abc") is True
    assert is_encrypted("123456789") is False
    assert is_encrypted("") is False
    assert is_encrypted(None) is False  # type: ignore[arg-type]
    assert pct(50, 100) == 50.0
    assert pct(1, 0) == 0


def test_build_updates_skips_already_encrypted():
    from services.admin_migration_api_helpers import build_client_encryption_updates

    client = {
        "dados_pessoais": {"nif": "ENC:already"},
        "contacto": {"email": "a@b.com", "email_hash": "existing"},
        "titular2_data": {},
    }
    updates, changes = build_client_encryption_updates(client, track_changes=True)
    assert "dados_pessoais" not in updates
    assert changes == []


def test_admin_migration_router_is_thin_stubs_only():
    from pathlib import Path

    routes_path = (
        Path(__file__).resolve().parents[2] / "routes" / "admin_migration.py"
    )
    text = routes_path.read_text()
    assert text.count("return await run_") >= 3
    assert len(text.splitlines()) < 80
    assert "generate_nif_hash" not in text
    assert "encryption_service.encrypt" not in text

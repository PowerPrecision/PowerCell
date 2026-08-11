"""Unit tests for admin_process_migration route thinning helpers."""


def test_generate_client_key_prefers_nif():
    from services.admin_proc_migration_helpers import generate_client_key

    assert generate_client_key(nif="123 456 789", email="a@b.com", nome="X") == "nif:123456789"
    assert generate_client_key(nif=None, email=" A@B.COM ", nome="X") == "email:a@b.com"
    assert generate_client_key(nif="bad", email="", nome="José Silva!") == "nome:josé_silva"
    assert generate_client_key() is None


def test_extract_personal_from_process():
    from services.admin_proc_migration_helpers import extract_personal_from_process

    process = {
        "client_name": "Ana",
        "client_email": "ana@ex.com",
        "client_phone": "912",
        "personal_data": {"nif": "123456789", "nacionalidade": "PT"},
    }
    data = extract_personal_from_process(process)
    assert data["nome"] == "Ana"
    assert data["contacto"]["email"] == "ana@ex.com"
    assert data["dados_pessoais"]["nif"] == "123456789"


def test_admin_proc_migration_modules_export_run_entrypoints():
    from services import admin_proc_migration_helpers, admin_proc_migration_api

    assert callable(admin_proc_migration_helpers.generate_client_key)
    assert callable(admin_proc_migration_helpers.extract_personal_from_process)
    assert callable(admin_proc_migration_helpers.now_iso)
    assert callable(admin_proc_migration_helpers._is_stale)
    assert callable(admin_proc_migration_helpers._reset_stale_state)
    assert callable(admin_proc_migration_helpers.run_migration_task)

    assert callable(admin_proc_migration_api.run_get_migration_status)
    assert callable(admin_proc_migration_api.run_dry_run_migration)
    assert callable(admin_proc_migration_api.run_run_migration)
    assert callable(admin_proc_migration_api.run_rollback_migration)
    assert callable(admin_proc_migration_api.run_reset_migration_state)


def test_admin_proc_migration_router_is_thin_stubs_only():
    from pathlib import Path

    routes_path = Path(__file__).resolve().parents[2] / "routes" / "admin_process_migration.py"
    text = routes_path.read_text()
    assert text.count("return await run_") >= 5
    assert len(text.splitlines()) < 100


def test_admin_proc_migration_no_route_name_collision():
    """Never create services/admin_process_migration.py (collides with route module)."""
    from pathlib import Path

    services_dir = Path(__file__).resolve().parents[2] / "services"
    assert not (services_dir / "admin_process_migration.py").exists()
    files = sorted(p.name for p in services_dir.glob("admin_proc_migration_*.py"))
    assert files == [
        "admin_proc_migration_api.py",
        "admin_proc_migration_helpers.py",
    ]

"""Unit tests for companies (email-config) route thinning (companies_api_*)."""

from pathlib import Path


def test_companies_api_modules_exist():
    services_dir = Path(__file__).resolve().parents[2] / "services"
    expected = [
        "companies_api_list.py",
        "companies_api_mutate.py",
    ]
    for name in expected:
        assert (services_dir / name).exists(), f"missing {name}"
    files = sorted(p.name for p in services_dir.glob("companies_api_*.py"))
    assert files == expected
    # Must not collide with companies_crud_api_*
    assert (services_dir / "companies_crud_api_list.py").exists()


def test_companies_api_export_run_entrypoints():
    from services import companies_api_list, companies_api_mutate

    assert callable(companies_api_list.run_list_company_configs)
    assert callable(companies_api_list.run_get_available_companies)
    assert callable(companies_api_list.run_get_company_config)
    assert callable(companies_api_mutate.run_create_company_config)
    assert callable(companies_api_mutate.run_update_company_config)
    assert callable(companies_api_mutate.run_delete_company_config)


def test_companies_router_is_thin_stubs_only():
    routes_path = Path(__file__).resolve().parents[2] / "routes" / "companies.py"
    text = routes_path.read_text()
    assert text.count("return await run_") >= 6
    assert len(text.splitlines()) < 90
    assert "encrypted_password" not in text
    avail_pos = text.index('/available-companies"')
    id_pos = text.index('/{company_name}"')
    assert avail_pos < id_pos

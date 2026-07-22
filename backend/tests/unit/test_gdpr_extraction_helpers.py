"""Unit tests for gdpr route thinning helpers (gdpr_api_*)."""

from pathlib import Path


def test_gdpr_api_modules_exist():
    services_dir = Path(__file__).resolve().parents[2] / "services"
    expected = [
        "gdpr_api_models.py",
        "gdpr_api_mutate.py",
        "gdpr_api_read.py",
    ]
    for name in expected:
        assert (services_dir / name).exists(), f"missing {name}"
    files = sorted(p.name for p in services_dir.glob("gdpr_api_*.py"))
    assert files == expected
    # Do not overwrite core gdpr.py
    assert (services_dir / "gdpr.py").exists()
    assert (services_dir / "gdpr.py").read_text().count("\n") > 50


def test_gdpr_api_export_run_entrypoints():
    from services import gdpr_api_models, gdpr_api_read, gdpr_api_mutate

    assert gdpr_api_models.AnonymizeRequest is not None
    assert gdpr_api_models.BatchAnonymizeRequest is not None
    assert callable(gdpr_api_read.run_get_statistics)
    assert callable(gdpr_api_read.run_get_eligible_processes)
    assert callable(gdpr_api_read.run_get_audit_log)
    assert callable(gdpr_api_read.run_get_gdpr_config)
    assert callable(gdpr_api_mutate.run_anonymize_single)
    assert callable(gdpr_api_mutate.run_anonymize_batch)
    assert callable(gdpr_api_mutate.run_export_data)


def test_gdpr_api_still_imports_core_gdpr():
    import inspect

    from services import gdpr_api_read, gdpr_api_mutate

    assert "from services.gdpr import" in inspect.getsource(gdpr_api_read)
    assert "from services.gdpr import" in inspect.getsource(gdpr_api_mutate)


def test_gdpr_router_is_thin_stubs_only():
    routes_path = Path(__file__).resolve().parents[2] / "routes" / "gdpr.py"
    text = routes_path.read_text()
    assert text.count("return await run_") >= 7
    assert len(text.splitlines()) < 120
    assert "gdpr_audit.insert_one" not in text

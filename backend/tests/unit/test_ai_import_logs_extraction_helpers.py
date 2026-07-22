"""Unit tests for ai_import_logs route thinning (ai_import_logs_api_*)."""

from pathlib import Path


def test_ai_import_logs_api_modules_exist():
    services_dir = Path(__file__).resolve().parents[2] / "services"
    expected = [
        "ai_import_logs_api_detail.py",
        "ai_import_logs_api_helpers.py",
        "ai_import_logs_api_list.py",
    ]
    for name in expected:
        assert (services_dir / name).exists(), f"missing {name}"
    files = sorted(p.name for p in services_dir.glob("ai_import_logs_api_*.py"))
    assert files == expected
    # Do not overwrite admin_ai_data.py
    assert (services_dir / "admin_ai_data.py").exists()
    assert (services_dir / "admin_ai_data.py").read_text().count("\n") > 50
    assert not (services_dir / "ai_import_logs.py").exists()


def test_ai_import_logs_api_export_run_entrypoints():
    from services import (
        ai_import_logs_api_helpers,
        ai_import_logs_api_list,
        ai_import_logs_api_detail,
    )

    assert callable(ai_import_logs_api_helpers.create_ai_import_log)
    assert callable(ai_import_logs_api_helpers.update_ai_import_log)
    assert callable(ai_import_logs_api_helpers.finalize_ai_import_log)
    assert callable(ai_import_logs_api_list.run_list_ai_import_logs)
    assert callable(ai_import_logs_api_list.run_get_ai_import_stats)
    assert callable(ai_import_logs_api_detail.run_get_ai_import_log)
    assert callable(ai_import_logs_api_detail.run_delete_ai_import_log)


def test_ai_import_logs_route_reexports_helpers():
    from routes import ai_import_logs

    assert callable(ai_import_logs.create_ai_import_log)
    assert callable(ai_import_logs.update_ai_import_log)
    assert callable(ai_import_logs.finalize_ai_import_log)


def test_ai_import_logs_router_is_thin_stubs_only():
    routes_path = Path(__file__).resolve().parents[2] / "routes" / "ai_import_logs.py"
    text = routes_path.read_text()
    assert text.count("return await run_") >= 4
    assert len(text.splitlines()) < 90
    assert text.index('@router.get("/stats")') < text.index('@router.get("/{log_id}")')
    assert "aggregate(pipeline)" not in text

"""Unit tests for activities route thinning (activities_api_*)."""

from pathlib import Path


def test_activities_api_modules_exist():
    services_dir = Path(__file__).resolve().parents[2] / "services"
    expected = [
        "activities_api_crud.py",
        "activities_api_history.py",
    ]
    for name in expected:
        assert (services_dir / name).exists(), f"missing {name}"
    files = sorted(p.name for p in services_dir.glob("activities_api_*.py"))
    assert files == expected


def test_activities_api_export_run_entrypoints():
    from services import activities_api_crud, activities_api_history

    assert callable(activities_api_crud.run_create_activity)
    assert callable(activities_api_crud.run_get_activities)
    assert callable(activities_api_crud.run_delete_activity)
    assert callable(activities_api_history.run_get_history)


def test_activities_api_stealth_guard_preserved():
    import inspect
    from services import activities_api_crud

    src = inspect.getsource(activities_api_crud)
    assert "_is_stealth_user" in src
    assert "sanitize_string" in src


def test_activities_api_history_enriches_entries():
    import inspect
    from services import activities_api_history

    src = inspect.getsource(activities_api_history)
    assert "enrich_history_entry" in src
    assert "description" in src or "HistoryResponse" in src


def test_activities_router_is_thin_stubs_only():
    routes_path = Path(__file__).resolve().parents[2] / "routes" / "activities.py"
    text = routes_path.read_text()
    assert text.count("return await run_") >= 4
    assert len(text.splitlines()) < 70
    assert "_is_stealth_user" not in text
    assert "sanitize_string" not in text

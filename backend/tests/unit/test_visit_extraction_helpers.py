"""Unit tests for visit route thinning helpers."""


def test_visit_helpers_exports():
    from services.visit_helpers import (
        _create_calendar_event_for_visit,
        _remove_calendar_event_for_visit,
        _update_portal_visit_status,
        _run_scraper_for_visit,
    )

    assert callable(_create_calendar_event_for_visit)
    assert callable(_remove_calendar_event_for_visit)
    assert callable(_update_portal_visit_status)
    assert callable(_run_scraper_for_visit)


def test_visit_modules_export_run_entrypoints():
    from services import (
        visit_helpers,
        visit_list_create,
        visit_kanban_get,
        visit_update_cancel,
    )

    assert callable(visit_helpers._create_calendar_event_for_visit)
    assert callable(visit_helpers._remove_calendar_event_for_visit)
    assert callable(visit_helpers._update_portal_visit_status)
    assert callable(visit_helpers._run_scraper_for_visit)

    assert callable(visit_list_create.run_list_visits)
    assert callable(visit_list_create.run_create_visit)

    assert callable(visit_kanban_get.run_get_visits_kanban)
    assert callable(visit_kanban_get.run_get_visit)

    assert callable(visit_update_cancel.run_update_visit)
    assert callable(visit_update_cancel.run_cancel_visit)


def test_visit_router_is_thin_stubs_only():
    from pathlib import Path

    routes_path = Path(__file__).resolve().parents[2] / "routes" / "visits.py"
    text = routes_path.read_text()
    assert text.count("return await run_") >= 6
    assert len(text.splitlines()) < 120


def test_visit_no_collision_with_portal_client_visits():
    """Ensure thinning used visit_* and left portal_client_visits intact."""
    from pathlib import Path
    from services import portal_client_visits

    services_dir = Path(__file__).resolve().parents[2] / "services"
    visit_files = sorted(p.name for p in services_dir.glob("visit_*.py"))
    assert visit_files == [
        "visit_helpers.py",
        "visit_kanban_get.py",
        "visit_list_create.py",
        "visit_update_cancel.py",
    ]
    assert (services_dir / "portal_client_visits.py").exists()
    assert hasattr(portal_client_visits, "__file__")

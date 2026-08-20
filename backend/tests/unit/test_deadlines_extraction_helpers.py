"""Unit tests for deadlines route thinning helpers (deadlines_api_*)."""


def test_deadlines_api_modules_exist():
    from pathlib import Path

    services_dir = Path(__file__).resolve().parents[2] / "services"
    expected = [
        "deadlines_api_calendar.py",
        "deadlines_api_crud.py",
        "deadlines_api_helpers.py",
        "deadlines_api_list.py",
    ]
    for name in expected:
        assert (services_dir / name).exists(), f"missing {name}"
    files = sorted(p.name for p in services_dir.glob("deadlines_api_*.py"))
    assert files == expected


def test_deadlines_api_export_run_entrypoints():
    from services import (
        deadlines_api_crud,
        deadlines_api_list,
        deadlines_api_calendar,
        deadlines_api_helpers,
    )

    assert callable(deadlines_api_crud.run_create_deadline)
    assert callable(deadlines_api_crud.run_update_deadline)
    assert callable(deadlines_api_crud.run_delete_deadline)
    assert callable(deadlines_api_list.run_get_deadlines)
    assert callable(deadlines_api_list.run_get_my_deadlines)
    assert callable(deadlines_api_calendar.run_get_calendar_deadlines)
    assert callable(deadlines_api_helpers.sees_team_calendar)


def test_deadlines_router_is_thin_stubs_only():
    from pathlib import Path

    routes_path = Path(__file__).resolve().parents[2] / "routes" / "deadlines.py"
    text = routes_path.read_text()
    assert text.count("return await run_") >= 6
    assert len(text.splitlines()) < 100
    assert "sanitize_string" not in text
    assert "send_notification_with_preference_check" not in text
    # Static paths before /{deadline_id}
    my_pos = text.index('/my-deadlines"')
    cal_pos = text.index('/calendar"')
    id_pos = text.index('/{deadline_id}"')
    assert my_pos < id_pos
    assert cal_pos < id_pos

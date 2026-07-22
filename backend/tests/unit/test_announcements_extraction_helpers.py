"""Unit tests for announcements route thinning (announcements_api_*)."""

from pathlib import Path


def test_announcements_api_modules_exist():
    services_dir = Path(__file__).resolve().parents[2] / "services"
    expected = [
        "announcements_api_crud.py",
        "announcements_api_interactions.py",
    ]
    for name in expected:
        assert (services_dir / name).exists(), f"missing {name}"
    files = sorted(p.name for p in services_dir.glob("announcements_api_*.py"))
    assert files == expected


def test_announcements_api_export_run_entrypoints():
    from services import announcements_api_crud, announcements_api_interactions

    assert callable(announcements_api_crud.run_get_announcements)
    assert callable(announcements_api_crud.run_create_announcement)
    assert callable(announcements_api_crud.run_delete_announcement)
    assert callable(announcements_api_interactions.run_toggle_like)
    assert callable(announcements_api_interactions.run_mark_as_read)
    assert callable(announcements_api_interactions.run_get_readers)


def test_announcements_router_is_thin_stubs_only():
    routes_path = Path(__file__).resolve().parents[2] / "routes" / "announcements.py"
    text = routes_path.read_text()
    assert text.count("return await run_") >= 6
    assert len(text.splitlines()) < 100
    assert "sanitize_string" not in text
    readers_pos = text.index('/readers/{announcement_id}"')
    delete_pos = text.index('delete("/{announcement_id}"')
    assert readers_pos < delete_pos

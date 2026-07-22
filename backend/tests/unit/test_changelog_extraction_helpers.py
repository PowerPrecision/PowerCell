"""Unit tests for changelog route thinning (changelog_api_*)."""

from pathlib import Path


def test_changelog_api_modules_exist():
    services_dir = Path(__file__).resolve().parents[2] / "services"
    expected = [
        "changelog_api_diagnose.py",
        "changelog_api_generate.py",
        "changelog_api_list.py",
    ]
    for name in expected:
        assert (services_dir / name).exists(), f"missing {name}"
    files = sorted(p.name for p in services_dir.glob("changelog_api_*.py"))
    assert files == expected
    # NEVER overwrite core changelog_service
    assert (services_dir / "changelog_service.py").exists()


def test_changelog_api_export_run_entrypoints():
    from services import (
        changelog_api_list,
        changelog_api_diagnose,
        changelog_api_generate,
    )

    assert callable(changelog_api_list.run_list_changelogs)
    assert callable(changelog_api_diagnose.run_diagnose_changelog_generation)
    assert callable(changelog_api_generate.run_generate_changelog)


def test_changelog_api_uses_changelog_service():
    import inspect
    from services import changelog_api_list, changelog_api_diagnose, changelog_api_generate

    assert "changelog_service" in inspect.getsource(changelog_api_list)
    assert "changelog_service" in inspect.getsource(changelog_api_diagnose)
    assert "generate_changelog_ai" in inspect.getsource(changelog_api_generate)


def test_changelog_router_is_thin_stubs_only():
    routes_path = Path(__file__).resolve().parents[2] / "routes" / "changelog.py"
    text = routes_path.read_text()
    assert text.count("return await run_") >= 3
    assert len(text.splitlines()) < 70
    assert "blocking_issue" not in text
    assert "_resolve_project_file" not in text

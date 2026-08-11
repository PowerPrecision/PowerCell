"""Unit tests for user_branches route thinning (user_branches_api_*)."""

from pathlib import Path


def test_user_branches_api_modules_exist():
    services_dir = Path(__file__).resolve().parents[2] / "services"
    expected = ["user_branches_api_crud.py"]
    for name in expected:
        assert (services_dir / name).exists(), f"missing {name}"
    files = sorted(p.name for p in services_dir.glob("user_branches_api_*.py"))
    assert files == expected


def test_user_branches_api_export_run_entrypoints():
    from services import user_branches_api_crud

    assert callable(user_branches_api_crud.run_create_user_branch)
    assert callable(user_branches_api_crud.run_list_user_branches)
    assert callable(user_branches_api_crud.run_delete_user_branch)


def test_user_branches_router_is_thin_stubs_only():
    routes_path = Path(__file__).resolve().parents[2] / "routes" / "user_branches.py"
    text = routes_path.read_text()
    assert text.count("return await run_") >= 3
    assert len(text.splitlines()) < 60
    assert "ObjectId" not in text
    assert "user_custom_branches" not in text

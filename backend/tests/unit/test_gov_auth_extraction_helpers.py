"""Unit tests for gov_auth route thinning (gov_auth_api_*)."""

from pathlib import Path


def test_gov_auth_api_modules_exist():
    services_dir = Path(__file__).resolve().parents[2] / "services"
    expected = [
        "gov_auth_api_callback.py",
        "gov_auth_api_helpers.py",
        "gov_auth_api_login.py",
        "gov_auth_api_verify.py",
    ]
    for name in expected:
        assert (services_dir / name).exists(), f"missing {name}"
    files = sorted(p.name for p in services_dir.glob("gov_auth_api_*.py"))
    assert files == expected


def test_gov_auth_api_export_run_entrypoints():
    from services import (
        gov_auth_api_login,
        gov_auth_api_callback,
        gov_auth_api_verify,
        gov_auth_api_helpers,
    )

    assert callable(gov_auth_api_login.run_gov_auth_login)
    assert callable(gov_auth_api_callback.run_gov_auth_callback)
    assert callable(gov_auth_api_verify.run_verify_gov_token)
    assert callable(gov_auth_api_helpers.create_gov_jwt)
    assert "MOCK_CITIZEN" in dir(gov_auth_api_helpers)


def test_gov_auth_router_is_thin_stubs_only():
    routes_path = Path(__file__).resolve().parents[2] / "routes" / "gov_auth.py"
    text = routes_path.read_text()
    assert text.count("return await run_") >= 3
    assert len(text.splitlines()) < 60
    assert "MOCK_CITIZEN" not in text
    assert "jwt.encode" not in text

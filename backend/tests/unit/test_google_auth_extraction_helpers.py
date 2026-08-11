"""Unit tests for google_auth route thinning helpers (google_auth_*)."""

from pathlib import Path

import pytest
from fastapi import HTTPException


def test_google_auth_helpers_exports():
    from services.google_auth_helpers import (
        get_google_config,
        _get_google_config,
        build_redirect_uri,
        _build_redirect_uri,
        resolve_user,
        _resolve_user,
    )

    assert get_google_config is _get_google_config
    assert build_redirect_uri is _build_redirect_uri
    assert resolve_user is _resolve_user


def test_build_redirect_uri_prefers_configured():
    from services.google_auth_helpers import _build_redirect_uri

    class FakeRequest:
        headers = {"host": "example.com", "x-forwarded-proto": "https"}

    assert _build_redirect_uri(FakeRequest(), "https://app.example/callback") == (
        "https://app.example/callback"
    )
    assert _build_redirect_uri(FakeRequest(), "") == (
        "https://example.com/api/auth/google/callback"
    )


def test_google_auth_modules_export_run_entrypoints():
    from services import google_auth_helpers, google_auth_oauth, google_auth_status

    assert callable(google_auth_helpers._get_google_config)
    assert callable(google_auth_helpers._build_redirect_uri)
    assert callable(google_auth_helpers._resolve_user)

    assert callable(google_auth_oauth.run_google_login)
    assert callable(google_auth_oauth.run_google_callback)

    assert callable(google_auth_status.run_google_oauth_status)
    assert callable(google_auth_status.run_google_oauth_disconnect)


def test_google_auth_router_is_thin_stubs_only():
    routes_path = Path(__file__).resolve().parents[2] / "routes" / "google_auth.py"
    text = routes_path.read_text()
    assert text.count("return await run_") >= 4
    assert "/login" in text
    assert "/callback" in text
    assert len(text.splitlines()) < 100


def test_google_auth_no_collision_with_gmail_oauth():
    """Ensure thinning used google_auth_* and did not overwrite gmail_oauth."""
    from services import gmail_oauth, gmail_api_service

    services_dir = Path(__file__).resolve().parents[2] / "services"
    google_auth_files = sorted(p.name for p in services_dir.glob("google_auth_*.py"))
    assert google_auth_files == [
        "google_auth_helpers.py",
        "google_auth_oauth.py",
        "google_auth_status.py",
    ]
    assert (services_dir / "gmail_oauth.py").exists()
    assert (services_dir / "gmail_api_service.py").exists()
    # Core gmail_oauth should remain substantial
    gmail_lines = (services_dir / "gmail_oauth.py").read_text().count("\n")
    assert gmail_lines > 100
    assert hasattr(gmail_oauth, "__file__")
    assert hasattr(gmail_api_service, "__file__")

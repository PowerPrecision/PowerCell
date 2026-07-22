"""Unit tests for shared_email route thinning helpers (shared_email_*)."""

import pytest
from fastapi import HTTPException


def test_shared_email_helpers_exports():
    from services.shared_email_helpers import (
        ALLOWED_ROLES,
        require_admin,
        _require_admin,
        get_google_config,
        _get_google_config,
        build_redirect_uri,
        _build_redirect_uri,
    )

    assert require_admin is _require_admin
    assert get_google_config is _get_google_config
    assert build_redirect_uri is _build_redirect_uri
    assert "indexacao" in ALLOWED_ROLES
    assert "suporte" in ALLOWED_ROLES


def test_require_admin_raises_for_non_admin():
    from services.shared_email_helpers import _require_admin

    with pytest.raises(HTTPException) as exc:
        _require_admin({"role": "consultor", "id": "u1"})
    assert exc.value.status_code == 403

    _require_admin({"role": "admin", "id": "u1"})
    _require_admin({"role": "ceo", "id": "u1"})


def test_shared_email_modules_export_run_entrypoints():
    from services import (
        shared_email_helpers,
        shared_email_crud,
        shared_email_google,
        shared_email_sync,
    )

    assert callable(shared_email_helpers._require_admin)
    assert callable(shared_email_helpers._get_google_config)
    assert callable(shared_email_helpers._build_redirect_uri)

    assert callable(shared_email_crud.run_list_shared_email_configs)
    assert callable(shared_email_crud.run_get_shared_email_config)
    assert callable(shared_email_crud.run_upsert_shared_email_config)
    assert callable(shared_email_crud.run_delete_shared_email_config)

    assert callable(shared_email_google.run_shared_email_google_callback)
    assert callable(shared_email_google.run_shared_email_google_login)
    assert callable(shared_email_google.run_shared_email_google_disconnect)

    assert callable(shared_email_sync.run_shared_email_manual_sync)


def test_shared_email_router_is_thin_stubs_only():
    from pathlib import Path

    routes_path = Path(__file__).resolve().parents[2] / "routes" / "shared_email.py"
    text = routes_path.read_text()
    assert text.count("return await run_") >= 8
    assert "/google/callback" in text
    # callback must appear before /{role} path registration
    callback_pos = text.find("/google/callback")
    role_pos = text.find('/{role}"')
    assert callback_pos > 0
    assert role_pos > callback_pos
    assert len(text.splitlines()) < 160


def test_shared_email_no_collision_with_email_services():
    """Ensure thinning used shared_email_* and did not overwrite email_* cores."""
    from pathlib import Path
    from services import email_service, email_draft_service, gmail_oauth

    services_dir = Path(__file__).resolve().parents[2] / "services"
    shared_files = sorted(p.name for p in services_dir.glob("shared_email_*.py"))
    assert shared_files == [
        "shared_email_crud.py",
        "shared_email_google.py",
        "shared_email_helpers.py",
        "shared_email_sync.py",
    ]
    assert (services_dir / "email_service.py").exists()
    assert (services_dir / "gmail_oauth.py").exists()
    assert hasattr(email_service, "__file__")
    assert hasattr(email_draft_service, "__file__")
    assert hasattr(gmail_oauth, "__file__")

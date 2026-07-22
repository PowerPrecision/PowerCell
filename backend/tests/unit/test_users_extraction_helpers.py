"""Unit tests for users route thinning helpers (users_api_*)."""

from fastapi import HTTPException
import pytest


def test_users_api_modules_exist():
    from pathlib import Path

    services_dir = Path(__file__).resolve().parents[2] / "services"
    expected = [
        "users_api_email_config.py",
        "users_api_helpers.py",
        "users_api_list.py",
    ]
    for name in expected:
        assert (services_dir / name).exists(), f"missing {name}"
    files = sorted(p.name for p in services_dir.glob("users_api_*.py"))
    assert files == expected


def test_users_api_export_run_entrypoints():
    from services import (
        users_api_helpers,
        users_api_list,
        users_api_email_config,
    )

    assert "indexacao" in users_api_helpers.FORCED_SHARED_ROLES
    assert "suporte" in users_api_helpers.FORCED_SHARED_ROLES
    assert callable(users_api_list.run_get_users)
    assert callable(users_api_list.run_get_user)
    assert callable(users_api_email_config.run_get_my_email_config)
    assert callable(users_api_email_config.run_save_my_email_config)
    assert callable(users_api_email_config.run_test_my_email_config)


def test_auth_core_not_overwritten():
    from pathlib import Path
    from services import auth

    core = Path(__file__).resolve().parents[2] / "services" / "auth.py"
    assert core.exists()
    text = core.read_text()
    assert "run_get_my_email_config" not in text
    assert callable(auth.get_current_user)
    assert callable(auth.require_staff)


def test_users_router_is_thin_stubs_only():
    from pathlib import Path

    routes_path = Path(__file__).resolve().parents[2] / "routes" / "users.py"
    text = routes_path.read_text()
    assert text.count("return await run_") >= 5
    assert len(text.splitlines()) < 100
    assert "encryption_service.encrypt" not in text
    # Static /me paths declared before /{user_id}
    me_pos = text.index('/me/email-config"')
    id_pos = text.index('/{user_id}"')
    assert me_pos < id_pos


def test_forced_shared_roles_block_on_save_constant():
    from services.users_api_helpers import FORCED_SHARED_ROLES

    assert FORCED_SHARED_ROLES == {"indexacao", "suporte"}

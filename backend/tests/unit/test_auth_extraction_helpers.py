"""Unit tests for auth route thinning helpers."""


def test_auth_core_service_not_overwritten():
    """Ensure thinning did not collide with existing services/auth.py."""
    from pathlib import Path
    from services import auth

    assert callable(auth.hash_password)
    assert callable(auth.verify_password)
    assert callable(auth.needs_rehash)
    assert callable(auth.create_token)
    assert callable(auth.get_current_user)
    assert callable(auth.validate_password_strength)
    assert callable(auth.get_user_companies)
    assert callable(auth.get_active_company_id_async)
    assert callable(auth.get_effective_role_async)
    assert callable(auth.effective_role_is_allowed)

    core = Path(__file__).resolve().parents[2] / "services" / "auth.py"
    assert core.exists()
    text = core.read_text()
    assert "CryptContext" in text
    assert "get_current_user" in text
    # Handlers must be separate files — not merged into core auth.py
    assert "run_login_v2" not in text
    assert "run_register" not in text


def test_auth_handler_modules_exist_with_handlers_suffix():
    from pathlib import Path

    services_dir = Path(__file__).resolve().parents[2] / "services"
    expected = [
        "auth_register_handlers.py",
        "auth_login_handlers.py",
        "auth_profile_handlers.py",
        "auth_sessions_handlers.py",
        "auth_password_handlers.py",
    ]
    for name in expected:
        assert (services_dir / name).exists(), f"missing {name}"
    # Must not invent a colliding services/auth.py replacement
    auth_glob = sorted(p.name for p in services_dir.glob("auth*.py"))
    assert "auth.py" in auth_glob
    for name in expected:
        assert name in auth_glob


def test_auth_modules_export_run_entrypoints():
    from services import (
        auth_register_handlers,
        auth_login_handlers,
        auth_profile_handlers,
        auth_sessions_handlers,
        auth_password_handlers,
    )

    assert callable(auth_register_handlers.run_register)

    assert callable(auth_login_handlers.run_login)
    assert callable(auth_login_handlers.run_login_v2)

    assert callable(auth_profile_handlers.run_get_me)
    assert callable(auth_profile_handlers.run_update_preferences)
    assert callable(auth_profile_handlers.run_get_preferences)
    assert callable(auth_profile_handlers.run_update_profile)

    assert callable(auth_sessions_handlers.run_refresh_tokens)
    assert callable(auth_sessions_handlers.run_logout)
    assert callable(auth_sessions_handlers.run_list_sessions)
    assert callable(auth_sessions_handlers.run_revoke_session)

    assert callable(auth_password_handlers.run_change_password)
    assert callable(auth_password_handlers.run_validate_password)


def test_auth_router_is_thin_stubs_only():
    from pathlib import Path

    routes_path = Path(__file__).resolve().parents[2] / "routes" / "auth.py"
    text = routes_path.read_text()
    assert text.count("return await run_") >= 12
    assert len(text.splitlines()) < 200
    # Deprecated login + login-v2 preserved as route stubs
    assert 'deprecated=True' in text or "deprecated=True" in text
    assert "/login-v2" in text
    assert "run_login" in text
    assert "run_login_v2" in text
    assert "/active-company" in text
    assert "run_set_active_company" in text
    assert "require_admin" not in text


def test_auth_routes_reexport_get_current_user():
    """Back-compat: routes.storage imports get_current_user from routes.auth."""
    from routes.auth import get_current_user, router

    assert callable(get_current_user)
    assert router.prefix == "/auth"


def test_deprecated_login_raises_410():
    import asyncio
    import pytest
    from fastapi import HTTPException
    from services.auth_login_handlers import run_login
    from models.auth import UserLogin

    data = UserLogin(email="a@b.com", password="Secret1!")

    with pytest.raises(HTTPException) as exc:
        asyncio.run(run_login(None, data, None))
    assert exc.value.status_code == 410
    assert "login-v2" in exc.value.detail


def test_validate_password_scoring_helpers():
    import asyncio
    from services.auth_password_handlers import run_validate_password

    weak = asyncio.run(run_validate_password({"password": "abc"}))
    strong = asyncio.run(run_validate_password({"password": "Str0ng!Pass#"}))

    assert weak["valid"] is False
    assert weak["score"] < 40
    assert isinstance(weak["feedback"], list)
    assert strong["valid"] is True
    assert strong["score"] >= 80
    assert strong["error"] is None

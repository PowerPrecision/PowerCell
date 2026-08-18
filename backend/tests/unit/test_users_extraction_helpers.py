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
    assert callable(users_api_email_config.run_list_my_email_accounts)
    assert callable(users_api_email_config.run_add_my_email_account)
    assert callable(users_api_email_config.run_delete_my_email_account)
    assert callable(users_api_email_config.run_set_primary_email_account)


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
    assert len(text.splitlines()) < 180
    assert "encryption_service.encrypt" not in text
    # Static /me paths declared before /{user_id}
    me_pos = text.index('/me/email-config"')
    accounts_pos = text.index("/me/email-accounts")
    id_pos = text.index('/{user_id}"')
    assert me_pos < id_pos
    assert accounts_pos < id_pos


def test_forced_shared_roles_block_on_save_constant():
    from services.users_api_helpers import FORCED_SHARED_ROLES

    assert FORCED_SHARED_ROLES == {"indexacao", "suporte"}


def test_forced_shared_uses_effective_role_not_primary():
    """FORCED_SHARED must key off active/effective role, not primary JWT role."""
    import asyncio
    from unittest.mock import AsyncMock, MagicMock, patch

    from models.email_config import EmailConfigCreate
    from services.users_api_email_config import run_save_my_email_config
    from services.email_config_resolver import resolve_email_config

    # ── save: primary=consultor + active=indexacao → 403 ──
    async def _save_blocked():
        request = MagicMock()
        request.headers = {"X-Active-Role": "indexacao"}
        user = {
            "id": "u1",
            "role": "consultor",
            "additional_roles": ["indexacao"],
        }
        config = EmailConfigCreate(
            email_address="a@b.com",
            imap_server="imap.test",
            smtp_server="smtp.test",
            password="secret",
        )
        with pytest.raises(HTTPException) as exc:
            await run_save_my_email_config(request, config, user)
        assert exc.value.status_code == 403

    asyncio.run(_save_blocked())

    # ── save: primary=indexacao + active=consultor → NOT blocked by FORCED_SHARED ──
    async def _save_allowed_when_not_effective_indexacao():
        request = MagicMock()
        request.headers = {"X-Active-Role": "consultor", "X-Company-Id": "acme"}
        user = {
            "id": "u1",
            "role": "indexacao",
            "additional_roles": ["consultor"],
            "company": "acme",
        }
        config = EmailConfigCreate(
            email_address="a@b.com",
            imap_server="imap.test",
            smtp_server="smtp.test",
            password="secret",
            company_id="acme",
        )
        with patch(
            "services.user_email_config_service.upsert_user_email_config",
            new_callable=AsyncMock,
        ), patch(
            "services.encryption.encryption_service.encrypt",
            return_value="enc",
        ), patch(
            "services.users_api_email_config.db"
        ) as mock_db, patch(
            "services.auth.get_active_company_id_async",
            new_callable=AsyncMock,
            return_value="acme",
        ):
            mock_db.users.find_one = AsyncMock(return_value={"email_config": {}})
            mock_db.users.update_one = AsyncMock()
            result = await run_save_my_email_config(request, config, user)
            assert result["success"] is True
            assert result["company_id"] == "acme"

    asyncio.run(_save_allowed_when_not_effective_indexacao())

    # ── resolver: active_role=indexacao forces shared even if primary is consultor ──
    async def _resolver_uses_active_role():
        from services import email_config_resolver as ecr

        user_doc = {
            "role": "consultor",
            "company": "acme",
            "email_config": {},
            "additional_roles": ["indexacao"],
        }
        shared = {
            "config_source": "shared_role",
            "shared_role": "indexacao",
            "email_address": "idx@co.com",
            "imap_server": "imap",
            "imap_port": 993,
            "smtp_server": "smtp",
            "smtp_port": 465,
            "has_password": True,
            "has_google_oauth": False,
            "auth_method": "imap_smtp",
            "encrypted_password": "x",
        }
        with patch.object(ecr.db, "users") as mock_users, patch.object(
            ecr, "_load_shared_role_config", new_callable=AsyncMock
        ) as load_shared, patch.object(
            ecr, "_load_company_config", new_callable=AsyncMock, return_value=None
        ), patch.object(
            ecr, "_load_system_config", new_callable=AsyncMock, return_value=None
        ):
            mock_users.find_one = AsyncMock(return_value=user_doc)
            load_shared.return_value = shared
            result = await resolve_email_config("u1", active_role="indexacao")
            load_shared.assert_awaited_once_with("indexacao")
            assert result["config_source"] == "shared_role"

            load_shared.reset_mock()
            # active consultor → do not force shared
            result2 = await resolve_email_config("u1", active_role="consultor")
            load_shared.assert_not_awaited()
            assert result2["config_source"] != "shared_role"

    asyncio.run(_resolver_uses_active_role())


def test_save_email_config_prefers_body_company_over_header():
    """PACOTE DM: gravar no company_id do body mesmo se o header for outra empresa."""
    import asyncio
    from unittest.mock import AsyncMock, MagicMock, patch

    from models.email_config import EmailConfigCreate
    from services.users_api_email_config import run_save_my_email_config

    async def _run():
        request = MagicMock()
        request.headers = {"X-Active-Role": "consultor", "X-Company-Id": "empresa-global"}
        user = {"id": "u-dm", "role": "consultor", "company": "empresa-global"}
        config = EmailConfigCreate(
            email_address="perfil@empresa-b.pt",
            imap_server="imap.b.pt",
            smtp_server="smtp.b.pt",
            password="secret",
            company_id="empresa-b",
        )
        with patch(
            "services.user_email_config_service.upsert_user_email_config",
            new_callable=AsyncMock,
        ) as upsert, patch(
            "services.encryption.encryption_service.encrypt",
            return_value="enc",
        ), patch(
            "services.users_api_email_config.db"
        ) as mock_db, patch(
            "services.auth.get_active_company_id_async",
            new_callable=AsyncMock,
            return_value="empresa-global",
        ):
            mock_db.users.find_one = AsyncMock(return_value={"email_config": {}})
            mock_db.users.update_one = AsyncMock()
            result = await run_save_my_email_config(
                request, config, user, query_company_id="empresa-b",
            )
            assert result["success"] is True
            assert result["company_id"] == "empresa-b"
            upsert.assert_awaited()
            assert upsert.await_args.kwargs["company_id"] == "empresa-b"
            nested = mock_db.users.update_one.await_args.args[1]["$set"]["email_config"]
            assert "company:empresa-b" in nested

    asyncio.run(_run())


def test_non_default_company_id_helper():
    from services.users_api_email_config import _non_default_company_id

    assert _non_default_company_id("default", None, "acme") == "acme"
    assert _non_default_company_id("  ", "comp-2") == "comp-2"
    assert _non_default_company_id(None, None) is None
    assert _non_default_company_id("tab-company", "header-company") == "tab-company"


def test_publicize_email_account_strips_secrets():
    from services.user_email_config_service import publicize_email_account

    pub = publicize_email_account({
        "id": "acc-1",
        "company_id": "co-1",
        "email_address": "a@b.pt",
        "encrypted_password": "secret",
        "google_refresh_token": "tok",
        "is_primary": True,
        "is_configured": True,
        "auth_method": "none",
    })
    assert pub["id"] == "acc-1"
    assert pub["has_password"] is True
    assert pub["has_google_oauth"] is True
    assert pub["auth_method"] == "google_oauth"
    assert "encrypted_password" not in pub
    assert "google_refresh_token" not in pub


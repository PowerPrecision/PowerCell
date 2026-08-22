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
    assert callable(users_api_list.run_get_staff_users)
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
    staff_pos = text.index('/staff"')
    id_pos = text.index('/{user_id}"')
    assert me_pos < id_pos
    assert accounts_pos < id_pos
    assert staff_pos < id_pos


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
            "effective_role": "indexacao",
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
            "effective_role": "consultor",
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


def test_decrypt_email_secret_passthrough_and_failed_enc():
    from services.email_config_resolver import decrypt_email_secret

    assert decrypt_email_secret("plain-secret") == "plain-secret"
    assert decrypt_email_secret("") == ""
    assert decrypt_email_secret(None) == ""
    leftover = decrypt_email_secret("ENC:not-a-valid-blob", context="unit-test")
    assert leftover == "" or not leftover.startswith("ENC:")


@pytest.mark.asyncio
async def test_run_get_users_includes_admin_index_and_inactive():
    """Pacote EB: GET /users sem for_assignment devolve a lista completa."""
    from unittest.mock import MagicMock, patch

    from services import users_api_list as ual

    docs = [
        {"id": "u-admin", "name": "Admin", "role": "admin", "is_active": True},
        {"id": "u-index", "name": "Index", "role": "indexacao", "is_active": True},
        {"id": "u-off", "name": "Inativo", "role": "consultor", "is_active": False},
        {"id": "u-ceo", "name": "CEO", "role": "ceo", "is_active": True},
    ]
    captured = {}

    class _Cursor:
        async def to_list(self, n):
            captured["limit"] = n
            return docs

    mock_db = MagicMock()
    mock_db.users.find = MagicMock(return_value=_Cursor())

    with patch.object(ual, "db", mock_db):
        result = await ual.run_get_users(None, {"id": "caller", "role": "admin"})

    query = mock_db.users.find.call_args[0][0]
    assert query == {}
    assert captured["limit"] >= 1000
    assert [u["id"] for u in result] == ["u-admin", "u-index", "u-off", "u-ceo"]


@pytest.mark.asyncio
async def test_run_get_staff_users_excludes_admin_and_index():
    from unittest.mock import MagicMock, patch

    from services import users_api_list as ual

    docs = [
        {"id": "u-admin", "name": "Admin", "role": "admin"},
        {"id": "u-index", "name": "Index", "role": "indexacao"},
        {"id": "u-con", "name": "Ana", "role": "consultor"},
    ]

    class _Cursor:
        async def to_list(self, _n):
            return docs

    mock_db = MagicMock()
    mock_db.users.find = MagicMock(return_value=_Cursor())

    with patch.object(ual, "db", mock_db):
        result = await ual.run_get_staff_users({"id": "caller", "role": "admin"})

    ids = [u["id"] for u in result]
    assert ids == ["u-con"]


def test_publicize_caixa_geral_account_strips_password():
    from services.email_config_resolver import (
        CAIXA_GERAL_ACCOUNT_ID,
        publicize_caixa_geral_account,
    )

    pub = publicize_caixa_geral_account(
        {
            "email_address": "geral@empresa.pt",
            "imap_server": "imap.empresa.pt",
            "smtp_server": "smtp.empresa.pt",
            "password": "super-secret",
            "has_password": True,
        },
        company_id="co-1",
    )
    assert pub["id"] == CAIXA_GERAL_ACCOUNT_ID
    assert pub["is_caixa_geral"] is True
    assert pub["read_only"] is True
    assert pub["has_password"] is True
    assert "password" not in pub
    assert "encrypted_password" not in pub


def test_list_email_accounts_injects_caixa_geral_for_diretor():
    import asyncio
    from unittest.mock import AsyncMock, MagicMock, patch

    from services.users_api_email_config import run_list_my_email_accounts

    async def _run():
        request = MagicMock()
        request.headers = {"X-Active-Role": "diretor", "X-Company-Id": "acme"}
        user = {"id": "u-dir", "role": "consultor", "additional_roles": ["diretor"]}
        caixa = {
            "email_address": "geral@acme.pt",
            "imap_server": "imap.acme.pt",
            "smtp_server": "smtp.acme.pt",
            "imap_port": 993,
            "smtp_port": 465,
            "password": "decrypted",
            "has_password": True,
            "label": "Caixa Geral",
        }
        with patch(
            "services.auth.get_effective_role", return_value="diretor",
        ), patch(
            "services.auth.get_active_company_id_async",
            new_callable=AsyncMock, return_value="acme",
        ), patch(
            "services.user_email_config_service.list_company_email_configs",
            new_callable=AsyncMock, return_value=[],
        ), patch(
            "services.email_config_resolver.load_caixa_geral_config",
            new_callable=AsyncMock, return_value=caixa,
        ):
            result = await run_list_my_email_accounts(request, "acme", user)
        assert result["caixa_geral_injected"] is True
        assert len(result["accounts"]) == 1
        assert result["accounts"][0]["is_caixa_geral"] is True
        assert result["accounts"][0]["email_address"] == "geral@acme.pt"
        assert "password" not in result["accounts"][0]

    asyncio.run(_run())


def test_list_email_accounts_skips_caixa_geral_for_consultor():
    import asyncio
    from unittest.mock import AsyncMock, MagicMock, patch

    from services.users_api_email_config import run_list_my_email_accounts

    async def _run():
        request = MagicMock()
        request.headers = {"X-Active-Role": "consultor", "X-Company-Id": "acme"}
        user = {"id": "u-c", "role": "consultor"}
        with patch(
            "services.auth.get_effective_role", return_value="consultor",
        ), patch(
            "services.auth.get_active_company_id_async",
            new_callable=AsyncMock, return_value="acme",
        ), patch(
            "services.user_email_config_service.list_company_email_configs",
            new_callable=AsyncMock, return_value=[],
        ), patch(
            "services.email_config_resolver.load_caixa_geral_config",
            new_callable=AsyncMock,
        ) as load_caixa:
            result = await run_list_my_email_accounts(request, "acme", user)
        load_caixa.assert_not_awaited()
        assert result.get("caixa_geral_injected") is False
        assert result["accounts"] == []

    asyncio.run(_run())


def test_list_email_accounts_skips_caixa_geral_without_email():
    import asyncio
    from unittest.mock import AsyncMock, MagicMock, patch

    from services.users_api_email_config import run_list_my_email_accounts

    async def _run():
        request = MagicMock()
        user = {"id": "u-dir", "role": "diretor"}
        with patch(
            "services.auth.get_effective_role", return_value="diretor",
        ), patch(
            "services.auth.get_active_company_id_async",
            new_callable=AsyncMock, return_value="acme",
        ), patch(
            "services.user_email_config_service.list_company_email_configs",
            new_callable=AsyncMock, return_value=[],
        ), patch(
            "services.email_config_resolver.load_caixa_geral_config",
            new_callable=AsyncMock, return_value={"label": "Caixa Geral"},
        ):
            result = await run_list_my_email_accounts(request, "acme", user)
        assert result.get("caixa_geral_injected") is False
        assert result["accounts"] == []

    asyncio.run(_run())


def test_list_email_accounts_uses_active_role_not_additional_diretor():
    import asyncio
    from unittest.mock import AsyncMock, MagicMock, patch

    from services.users_api_email_config import run_list_my_email_accounts

    async def _run():
        request = MagicMock()
        user = {
            "id": "u-c",
            "role": "consultor",
            "additional_roles": ["diretor"],
        }
        with patch(
            "services.auth.get_effective_role", return_value="consultor",
        ), patch(
            "services.auth.get_active_company_id_async",
            new_callable=AsyncMock, return_value="acme",
        ), patch(
            "services.user_email_config_service.list_company_email_configs",
            new_callable=AsyncMock, return_value=[],
        ), patch(
            "services.email_config_resolver.load_caixa_geral_config",
            new_callable=AsyncMock,
        ) as load_caixa:
            result = await run_list_my_email_accounts(request, "acme", user)
        load_caixa.assert_not_awaited()
        assert result.get("caixa_geral_injected") is False

    asyncio.run(_run())


def test_cannot_mutate_caixa_geral_virtual_account():
    import asyncio
    from unittest.mock import MagicMock, patch

    from fastapi import HTTPException
    from models.email_config import EmailConfigCreate
    from services.users_api_email_config import (
        run_delete_my_email_account,
        run_update_my_email_account,
    )

    async def _run():
        request = MagicMock()
        request.headers = {"X-Active-Role": "diretor"}
        user = {"id": "u-dir", "role": "diretor"}
        config = EmailConfigCreate(
            email_address="geral@acme.pt",
            imap_server="imap",
            smtp_server="smtp",
        )
        with patch("services.auth.get_effective_role", return_value="diretor"):
            with pytest.raises(HTTPException) as exc:
                await run_delete_my_email_account(request, "caixa-geral", user)
            assert exc.value.status_code == 403
            with pytest.raises(HTTPException) as exc2:
                await run_update_my_email_account(
                    request, "caixa-geral", config, user,
                )
            assert exc2.value.status_code == 403

    asyncio.run(_run())


"""Testes unitários do Pacote 8 — 3 fixes de UX e lógica de negócio.

Sem I/O de Mongo (convenção tests/unit — fake_async_db do conftest +
patches do `db` nos módulos do fluxo):

1. Perfis fantasma no ContextSwitcher: queries de UCR filtram
   estritamente is_deleted=True / is_active=False (get_user_companies,
   lista admin, set-active-company) — o frontend só recebe perfis válidos.
2. Webmail unificado: GET /users/me/email-accounts?scope=all devolve a
   vista consolidada (configs de todas as empresas + Caixas Gerais por
   empresa + flag has_shared_indexacao), independentemente do perfil
   activo; permissões de caixa e caixas gerais consideram TODOS os UCRs.
3. Desacoplamento login ↔ webmail: os filtros de conversa (from/to)
   baseiam-se nas contas do UserEmailConfig, não no email de login.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.unit.conftest import FakeAsyncDatabase

pytestmark = pytest.mark.asyncio


def _make_request(headers: dict = None) -> MagicMock:
    request = MagicMock()
    request.headers = headers or {}
    return request


# ====================================================================
# BUG 1 — Perfis fantasma no ContextSwitcher
# ====================================================================
class TestBug1GhostProfiles:
    async def test_get_user_companies_excludes_deleted_and_inactive(self):
        """A fonte do ContextSwitcher (/auth/login + /auth/me) só devolve
        UCRs válidos: is_deleted=True e is_active=False ficam de fora;
        docs legados sem as flags continuam a contar."""
        from services.auth import get_user_companies

        fake = FakeAsyncDatabase()
        fake.user_company_roles.docs = [
            {"user_id": "u1", "company_id": "c1", "role": "consultor",
             "company_name": "Power"},
            {"user_id": "u1", "company_id": "c2", "role": "diretor",
             "company_name": "Precision"},
            {"user_id": "u1", "company_id": "c3", "role": "admin",
             "company_name": "Ghost Deleted", "is_deleted": True},
            {"user_id": "u1", "company_id": "c4", "role": "ceo",
             "company_name": "Ghost Inactive", "is_active": False},
        ]
        with patch("database.db", fake):
            companies = await get_user_companies("u1")
        assert {c["company_id"] for c in companies} == {"c1", "c2"}

    async def test_admin_list_user_company_roles_filters_ghosts(self):
        from services.user_company_roles_api_crud import (
            run_list_user_company_roles,
        )

        fake = FakeAsyncDatabase()
        fake.user_company_roles.docs = [
            {"id": "r1", "user_id": "u1", "company_id": "c1", "role": "consultor",
             "company_name": "Power"},
            {"id": "r2", "user_id": "u1", "company_id": "c2", "role": "diretor",
             "company_name": "Precision", "is_deleted": True},
            {"id": "r3", "user_id": "u1", "company_id": "c3", "role": "admin",
             "company_name": "Ghost", "is_active": False},
        ]
        with patch("services.user_company_roles_api_crud.db", fake):
            result = await run_list_user_company_roles(user_id="u1")
        assert result["total"] == 1
        assert result["roles"][0]["company_id"] == "c1"

    async def test_set_active_company_refuses_deleted_ucr(self):
        """Switch para um perfil apagado/inactivo → 403 (nunca activável)."""
        from fastapi import HTTPException

        from services.user_company_roles_api_active import run_set_active_company

        fake = FakeAsyncDatabase()
        fake.user_company_roles.docs = [
            {"id": "r1", "user_id": "u1", "company_id": "c1", "role": "diretor",
             "company_name": "Ghost", "is_deleted": True},
        ]
        user = {"id": "u1", "email": "u1@x.pt"}
        with patch("services.user_company_roles_api_active.db", fake):
            with pytest.raises(HTTPException) as exc_info:
                await run_set_active_company(
                    {"company_id": "c1", "role": "diretor"}, user,
                )
        assert exc_info.value.status_code == 403

    async def test_set_active_company_allows_valid_ucr(self):
        from services.user_company_roles_api_active import run_set_active_company

        fake = FakeAsyncDatabase()
        fake.user_company_roles.docs = [
            {"id": "r1", "user_id": "u1", "company_id": "c1", "role": "diretor",
             "company_name": "Power", "is_default": False},
        ]
        user = {"id": "u1", "email": "u1@x.pt"}
        with patch("services.user_company_roles_api_active.db", fake):
            result = await run_set_active_company(
                {"company_id": "c1", "role": "diretor"}, user,
            )
        assert result["success"] is True
        assert result["active_company_id"] == "c1"

    async def test_last_ucr_protection_counts_only_valid_ucrs(self):
        """A protecção do último acesso conta apenas UCRs válidos — um
        perfil apagado não é um 'acesso' para efeitos do bloqueio."""
        from fastapi import HTTPException

        from services.user_company_roles_api_crud import (
            run_delete_user_company_role,
        )

        fake = FakeAsyncDatabase()
        fake.user_company_roles.docs = [
            {"id": "r1", "user_id": "u1", "company_id": "c1", "role": "consultor",
             "company_name": "Power"},
            {"id": "r2", "user_id": "u1", "company_id": "c2", "role": "diretor",
             "company_name": "Ghost", "is_deleted": True},
        ]
        with patch("services.user_company_roles_api_crud.db", fake):
            # 1 UCR válido (r1) + 1 apagado (r2) — apagar r1 tem de ser
            # recusado (ficaria sem nenhum acesso VÁLIDO).
            with pytest.raises(HTTPException) as exc_info:
                await run_delete_user_company_role("r1")
        assert exc_info.value.status_code == 400


# ====================================================================
# BUG 2 — Webmail unificado (scope=all + permissões por UCR)
# ====================================================================
class TestBug2UnifiedWebmail:
    async def test_list_my_email_accounts_scope_all_consolidates(self):
        """scope=all devolve configs de TODAS as empresas (com nome),
        injecta a Caixa Geral de cada empresa com cargo de gestão e
        expõe has_shared_indexacao — sem depender do perfil activo."""
        from services.users_api_email_config import run_list_my_email_accounts

        fake = FakeAsyncDatabase()
        fake.user_company_roles.docs = [
            {"user_id": "u1", "company_id": "cA", "role": "consultor",
             "company_name": "Empresa A"},
            {"user_id": "u1", "company_id": "cB", "role": "diretor",
             "company_name": "Empresa B"},
            {"user_id": "u1", "company_id": "cC", "role": "indexacao",
             "company_name": "Empresa C"},
            {"user_id": "u1", "company_id": "cD", "role": "ceo",
             "company_name": "Ghost", "is_deleted": True},
        ]
        fake.user_email_configs.docs = [
            {"id": "e1", "user_id": "u1", "company_id": "cA",
             "email_address": "pessoal@a.pt", "is_configured": True,
             "is_primary": True},
            {"id": "e2", "user_id": "u1", "company_id": "cB",
             "email_address": "diretor@b.pt", "is_configured": True,
             "is_primary": True},
        ]

        async def fake_load_caixa(cid):
            if cid == "cB":
                return {"email_address": "geral@b.pt"}
            return {}

        request = _make_request()
        user = {"id": "u1", "email": "login@x.pt", "role": "consultor"}
        with patch("services.users_api_email_config.db", fake), patch(
            "services.user_email_config_service.db", fake,
        ), patch(
            "services.email_config_resolver.load_caixa_geral_config",
            AsyncMock(side_effect=fake_load_caixa),
        ), patch(
            "services.auth.get_effective_role", MagicMock(return_value="consultor"),
        ):
            result = await run_list_my_email_accounts(
                request, None, user, scope="all",
            )

        assert result["scope"] == "all"
        emails = {a["email_address"] for a in result["accounts"]}
        # config da empresa A + config da empresa B + caixa geral de B
        assert emails == {"pessoal@a.pt", "diretor@b.pt", "geral@b.pt"}
        # nomes de empresa presentes para desambiguação no seletor
        by_email = {a["email_address"]: a for a in result["accounts"]}
        assert by_email["pessoal@a.pt"]["company_name"] == "Empresa A"
        assert by_email["diretor@b.pt"]["company_name"] == "Empresa B"
        assert by_email["geral@b.pt"]["is_caixa_geral"] is True
        # indexacao existe num UCR válido (empresa C) → flag a True
        assert result["has_shared_indexacao"] is True
        # a empresa D (UCR apagado) não contribui com caixa geral
        assert all(a["company_name"] != "Ghost" for a in result["accounts"])

    async def test_scope_all_ignores_forced_shared_empty_return(self):
        """Com scope=all, um utilizador cujo perfil ACTIVO é indexacao
        continua a ver as suas configs pessoais (a caixa partilhada é
        gerida centralmente, mas as pessoais existem)."""
        from services.users_api_email_config import run_list_my_email_accounts

        fake = FakeAsyncDatabase()
        fake.user_company_roles.docs = [
            {"user_id": "u1", "company_id": "cA", "role": "indexacao",
             "company_name": "Empresa A"},
        ]
        fake.user_email_configs.docs = [
            {"id": "e1", "user_id": "u1", "company_id": "cA",
             "email_address": "pessoal@a.pt", "is_configured": True,
             "is_primary": True},
        ]
        request = _make_request()
        user = {"id": "u1", "email": "login@x.pt", "role": "indexacao"}
        with patch("services.users_api_email_config.db", fake), patch(
            "services.user_email_config_service.db", fake,
        ), patch(
            "services.auth.get_effective_role", MagicMock(return_value="indexacao"),
        ):
            result = await run_list_my_email_accounts(
                request, None, user, scope="all",
            )
        assert [a["email_address"] for a in result["accounts"]] == ["pessoal@a.pt"]
        assert result["has_shared_indexacao"] is True

    async def test_scope_active_keeps_legacy_behaviour(self):
        """Sem scope, o comportamento anterior mantém-se: configs da
        empresa activa + FORCED_SHARED devolve managed_centralized."""
        from services.users_api_email_config import run_list_my_email_accounts

        request = _make_request()
        user = {"id": "u1", "email": "login@x.pt", "role": "indexacao"}
        with patch(
            "services.auth.get_effective_role", MagicMock(return_value="indexacao"),
        ):
            result = await run_list_my_email_accounts(request, None, user)
        assert result == {"accounts": [], "managed_centralized": True}

    async def test_user_ucr_roles_considers_all_profiles(self):
        from services.email_webmail import _user_ucr_roles

        fake = FakeAsyncDatabase()
        fake.user_company_roles.docs = [
            {"user_id": "u1", "company_id": "cA", "role": "consultor"},
            {"user_id": "u1", "company_id": "cB", "role": "indexacao"},
            {"user_id": "u1", "company_id": "cC", "role": "diretor",
             "is_active": False},
        ]
        request = _make_request()
        user = {"id": "u1", "role": "consultor"}
        with patch("services.email_webmail.db", fake):
            roles = await _user_ucr_roles(request, user)
        assert roles == {"consultor", "indexacao"}

    async def test_rewrite_box_for_caixa_geral_cross_company(self):
        """Seleccionar a Caixa Geral de OUTRA empresa (não a activa)
        reescreve para box=general — o seletor unificado chega lá sem
        trocar de perfil global."""
        from services.email_webmail import rewrite_box_for_caixa_geral

        fake = FakeAsyncDatabase()
        fake.user_company_roles.docs = [
            {"user_id": "u1", "company_id": "cA", "role": "consultor"},
            {"user_id": "u1", "company_id": "cB", "role": "diretor"},
        ]

        async def fake_load_caixa(cid):
            if cid == "cB":
                return {"email_address": "geral@b.pt"}
            return {}

        request = _make_request()
        user = {"id": "u1", "role": "consultor"}
        with patch("services.email_webmail.db", fake), patch(
            "services.email_config_resolver.load_caixa_geral_config",
            AsyncMock(side_effect=fake_load_caixa),
        ):
            box, mailbox = await rewrite_box_for_caixa_geral(
                request, user, "personal", "geral@b.pt",
            )
        assert box == "general"
        assert mailbox is None

    async def test_resolve_ucr_mailbox_filter_personal_cross_company(self):
        """Uma mailbox pessoal de outra empresa → filtro estrito por
        ``account`` (não injecta a empresa activa na cláusula)."""
        from services.email_webmail import resolve_ucr_mailbox_filter

        fake = FakeAsyncDatabase()
        fake.user_company_roles.docs = [
            {"user_id": "u1", "company_id": "cA", "role": "consultor"},
            {"user_id": "u1", "company_id": "cB", "role": "diretor"},
        ]
        request = _make_request()
        user = {"id": "u1", "role": "consultor"}
        with patch("services.email_webmail.db", fake), patch(
            "services.email_config_resolver.load_caixa_geral_config",
            AsyncMock(return_value={}),
        ):
            result = await resolve_ucr_mailbox_filter(
                request, user, box="personal", mailbox="diretor@b.pt",
            )
        assert result == {
            "account": {"$regex": "^diretor@b\\.pt$", "$options": "i"}
        }

    async def test_webmail_list_allows_general_box_via_ucr_role(self):
        """box=general com perfil activo consultor mas UCR diretor noutro
        perfil → 200 (não 403) — o webmail não depende do perfil activo."""
        from services.email_webmail import run_webmail_list

        fake = FakeAsyncDatabase()
        fake.user_company_roles.docs = [
            {"user_id": "u1", "company_id": "cA", "role": "consultor"},
            {"user_id": "u1", "company_id": "cB", "role": "diretor"},
        ]
        fake.emails.docs = [
            {"id": "em1", "direction": "received", "status": "synced",
             "is_archived": False, "shared_role": "geral", "to_emails": [],
             "from_email": "x@y.pt", "sent_at": "2026-01-01T00:00:00",
             "attachments": []},
        ]
        request = _make_request()
        user = {"id": "u1", "email": "login@x.pt", "role": "consultor"}

        async def fake_conversation(u):
            return ["login@x.pt"]

        with patch("services.email_webmail.db", fake), patch(
            "services.auth.get_effective_role_async",
            AsyncMock(return_value="consultor"),
        ), patch(
            "services.auth.get_active_company_id_async",
            AsyncMock(return_value=None),
        ), patch(
            "services.email_webmail._resolve_conversation_emails",
            AsyncMock(side_effect=fake_conversation),
        ), patch(
            "services.email_webmail.enrich_emails",
            AsyncMock(side_effect=lambda emails: emails),
        ):
            result = await run_webmail_list(
                request, user, folder="inbox", box="general",
            )
        assert result["total"] == 1

    async def test_webmail_list_blocks_general_box_without_any_ucr_role(self):
        from fastapi import HTTPException

        from services.email_webmail import run_webmail_list

        fake = FakeAsyncDatabase()
        fake.user_company_roles.docs = [
            {"user_id": "u1", "company_id": "cA", "role": "consultor"},
        ]
        request = _make_request()
        user = {"id": "u1", "email": "login@x.pt", "role": "consultor"}
        with patch("services.email_webmail.db", fake), patch(
            "services.auth.get_effective_role_async",
            AsyncMock(return_value="consultor"),
        ), patch(
            "services.auth.get_active_company_id_async",
            AsyncMock(return_value=None),
        ), patch(
            "services.email_webmail._resolve_conversation_emails",
            AsyncMock(return_value=["login@x.pt"]),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await run_webmail_list(request, user, folder="inbox", box="general")
        assert exc_info.value.status_code == 403


# ====================================================================
# BUG 3 — Desacoplamento email de login ↔ email configurado (IMAP)
# ====================================================================
class TestBug3DecoupledLoginEmail:
    async def test_get_user_mailbox_addresses_only_configured(self):
        from services.user_email_config_service import get_user_mailbox_addresses

        fake = FakeAsyncDatabase()
        fake.user_email_configs.docs = [
            {"user_id": "u1", "company_id": "cA", "email_address": "Geral@X.pt",
             "is_configured": True, "is_primary": False},
            {"user_id": "u1", "company_id": "cB", "email_address": "diretor@b.pt",
             "is_configured": True, "is_primary": True},
            {"user_id": "u1", "company_id": "cC", "email_address": "inativo@c.pt",
             "is_configured": False},
            {"user_id": "other", "company_id": "cA", "email_address": "outra@x.pt",
             "is_configured": True},
        ]
        with patch("services.user_email_config_service.db", fake):
            addresses = await get_user_mailbox_addresses("u1")
        assert set(addresses) == {"diretor@b.pt", "geral@x.pt"}

    async def test_get_user_mailbox_addresses_degrades_gracefully(self):
        from services.user_email_config_service import get_user_mailbox_addresses

        broken = MagicMock()
        broken.user_email_configs = property(
            lambda self: (_ for _ in ()).throw(RuntimeError("boom"))
        )
        with patch("services.user_email_config_service.db", broken):
            addresses = await get_user_mailbox_addresses("u1")
        assert addresses == []

    async def test_regex_any_builds_clause_per_email(self):
        from services.email_webmail import _regex_any

        clauses = _regex_any("to_emails", ["geral@x.pt", "login@x.pt", ""])
        assert clauses == [
            {"to_emails": {"$regex": "geral@x\\.pt", "$options": "i"}},
            {"to_emails": {"$regex": "login@x\\.pt", "$options": "i"}},
        ]
        assert _regex_any("from_email", []) == []

    async def test_resolve_conversation_emails_prefers_config_over_login(self):
        """Com configs activas, a conversa usa EXCLUSIVAMENTE as contas
        configuradas — o email de login (users.email) é ignorado."""
        from services.email_webmail import _resolve_conversation_emails

        user = {"id": "u1", "email": "login@x.pt"}
        async def fake_addresses(uid):
            assert uid == "u1"
            return ["geral@x.pt"]
        with patch(
            "services.user_email_config_service.get_user_mailbox_addresses",
            AsyncMock(side_effect=fake_addresses),
        ):
            emails = await _resolve_conversation_emails(user)
        assert emails == ["geral@x.pt"]

    async def test_resolve_conversation_emails_falls_back_to_login(self):
        from services.email_webmail import _resolve_conversation_emails

        user = {"id": "u1", "email": "Login@X.pt"}
        with patch(
            "services.user_email_config_service.get_user_mailbox_addresses",
            AsyncMock(return_value=[]),
        ):
            emails = await _resolve_conversation_emails(user)
        assert emails == ["login@x.pt"]

    async def test_get_email_allows_configured_mailbox_conversation(self):
        """Email dirigido à caixa CONFIGURADA (geral@x.pt) é visível para
        o utilizador cujo login é user@x.pt — antes, o 403 disparava
        porque a conversa era avaliada contra o email de login."""
        from services.email_process_crud import run_get_email

        fake = FakeAsyncDatabase()
        fake.emails.docs = [
            {"id": "em1", "to_emails": ["geral@x.pt"], "from_email": "cliente@z.pt",
             "subject": "Docs", "body": "olá", "direction": "received",
             "attachments": []},
        ]
        request = _make_request()
        user = {"id": "u1", "email": "user@x.pt", "role": "consultor"}

        class FakeResponse:
            def __init__(self, **kwargs):
                self.__dict__.update(kwargs)

        with patch("services.email_process_crud.db", fake), patch(
            "services.email_process_crud.get_effective_role",
            MagicMock(return_value="consultor"),
        ), patch(
            "services.user_email_config_service.get_user_mailbox_addresses",
            AsyncMock(return_value=["geral@x.pt"]),
        ), patch(
            "services.email_process_crud.enrich_email",
            AsyncMock(side_effect=lambda email: email),
        ), patch(
            "services.email_process_crud.EmailResponse", FakeResponse,
        ):
            result = await run_get_email("em1", request, user)
        assert result.id == "em1"

    async def test_get_email_still_blocks_unrelated_conversations(self):
        from fastapi import HTTPException

        from services.email_process_crud import run_get_email

        fake = FakeAsyncDatabase()
        fake.emails.docs = [
            {"id": "em1", "to_emails": ["outra@y.pt"], "from_email": "cliente@z.pt",
             "subject": "Docs", "body": "olá", "direction": "received",
             "attachments": []},
        ]
        request = _make_request()
        user = {"id": "u1", "email": "user@x.pt", "role": "consultor"}
        with patch("services.email_process_crud.db", fake), patch(
            "services.email_process_crud.get_effective_role",
            MagicMock(return_value="consultor"),
        ), patch(
            "services.user_email_config_service.get_user_mailbox_addresses",
            AsyncMock(return_value=["geral@x.pt"]),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await run_get_email("em1", request, user)
        assert exc_info.value.status_code == 403

    async def test_attachment_download_uses_configured_mailbox(self):
        """_assert_email_readable: anexo de email dirigido à caixa
        configurada é descarregável pelo utilizador com login diferente."""
        from services.email_mailbox_ops import _assert_email_readable

        email_doc = {
            "to_emails": ["geral@x.pt"],
            "from_email": "cliente@z.pt",
            "created_by": "other-user",
            "synced_for_user": "other-user",
        }
        request = _make_request()
        user = {"id": "u1", "email": "user@x.pt", "role": "consultor"}
        with patch(
            "services.auth.get_effective_role", MagicMock(return_value="consultor"),
        ), patch(
            "services.user_email_config_service.get_user_mailbox_addresses",
            AsyncMock(return_value=["geral@x.pt"]),
        ):
            await _assert_email_readable(email_doc, request, user)  # não levanta

    async def test_sync_user_matches_mailbox_across_companies(self):
        """run_webmail_sync_user: mailbox de OUTRA empresa resolve a config
        dessa empresa (não fica preso à empresa activa)."""
        from services.email_webmail import run_webmail_sync_user

        fake = FakeAsyncDatabase()
        fake.user_company_roles.docs = [
            {"user_id": "u1", "company_id": "cA", "role": "consultor"},
            {"user_id": "u1", "company_id": "cB", "role": "diretor"},
        ]
        fake.user_email_configs.docs = [
            {"id": "eA", "user_id": "u1", "company_id": "cA",
             "email_address": "pessoal@a.pt", "is_configured": True,
             "is_primary": True},
            {"id": "eB", "user_id": "u1", "company_id": "cB",
             "email_address": "diretor@b.pt", "is_configured": True},
        ]
        request = _make_request()
        user = {"id": "u1", "email": "user@x.pt", "role": "consultor"}

        resolved_calls: list = []

        async def fake_resolve(uid, active_role=None, active_company_id=None,
                               account_id=None):
            resolved_calls.append(
                {"company_id": active_company_id, "account_id": account_id}
            )
            if account_id == "eB":
                return {
                    "config_source": "user",
                    "email_address": "diretor@b.pt",
                    "encrypted_password": "x",
                    "resolved_company_id": active_company_id,
                }
            return {
                "config_source": "user",
                "email_address": "pessoal@a.pt",
                "encrypted_password": "x",
                "resolved_company_id": active_company_id,
            }

        async def fake_sync_user(user_id, resolved_config=None):
            return {"success": True, "total_synced": 0, "resolved": resolved_config}

        # O sync real corre em background job — aqui patchamos o job service
        # e o sync para observar apenas a resolução da config.
        job_service = MagicMock()
        job_service.create_job = AsyncMock(return_value="job-1")
        job_service.update_progress = AsyncMock()
        job_service.complete_job = AsyncMock()
        job_service.fail_job = AsyncMock()

        with patch("services.email_webmail.db", fake), patch(
            "services.user_email_config_service.db", fake,
        ), patch(
            "services.auth.get_effective_role_async",
            AsyncMock(return_value="consultor"),
        ), patch(
            "services.auth.get_active_company_id_async",
            AsyncMock(return_value="cA"),
        ), patch(
            "services.email_config_resolver.resolve_email_config_for_sync",
            AsyncMock(side_effect=fake_resolve),
        ), patch(
            "services.email_config_resolver.load_caixa_geral_config",
            AsyncMock(return_value={}),
        ), patch(
            "services.background_jobs.BackgroundJobService",
            MagicMock(return_value=job_service),
        ), patch(
            "services.email_service.sync_user_emails",
            AsyncMock(side_effect=fake_sync_user),
        ):
            result = await run_webmail_sync_user(
                request, user, mailbox="diretor@b.pt",
            )

        assert result["success"] is True
        # A segunda resolução (match da mailbox noutra empresa) usa a
        # company_id da config encontrada e o account_id certo.
        assert resolved_calls[-1] == {"company_id": "cB", "account_id": "eB"}

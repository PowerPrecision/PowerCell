"""Pacote FH — UCR effective-role RBAC (C3) e isolamento Webmail (A5)."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from models.auth import UserRole
from services.auth import (
    authorization_role,
    effective_role_is_allowed,
    get_effective_role,
    get_effective_role_async,
)


class _FakeRequest:
    def __init__(self, headers=None):
        self.headers = headers or {}
        self.state = SimpleNamespace()


def test_effective_role_is_allowed_ignores_jwt_additional_roles():
    """C3: additional_roles do JWT não entram na hierarquia RBAC."""
    assert effective_role_is_allowed("consultor", [UserRole.ADMIN, UserRole.CEO]) is False
    assert effective_role_is_allowed("admin", [UserRole.ADMIN, UserRole.CEO]) is True
    assert effective_role_is_allowed("admin", [UserRole.CONSULTOR]) is True
    assert effective_role_is_allowed("ceo", [UserRole.CONSULTOR]) is True
    assert effective_role_is_allowed("diretor", [UserRole.CONSULTOR]) is True
    assert effective_role_is_allowed("indexacao", [UserRole.ADMIN, UserRole.INDEXACAO]) is True
    assert effective_role_is_allowed("consultor", [UserRole.ADMIN, UserRole.INDEXACAO]) is False


def test_authorization_role_all_sentinel_falls_back_to_jwt():
    user = {"role": "diretor", "additional_roles": ["admin"]}
    assert authorization_role("__all_roles__", user) == "diretor"
    assert authorization_role("consultor", user) == "consultor"


def test_sync_get_effective_role_does_not_honour_additional_roles():
    """Sem cache UCR, additional_roles do JWT não validam X-Active-Role."""
    request = _FakeRequest({"X-Active-Role": "indexacao"})
    user = {"id": "u1", "role": "consultor", "additional_roles": ["indexacao"]}
    assert get_effective_role(request, user) == "consultor"


def test_sync_get_effective_role_uses_request_state_cache():
    request = _FakeRequest({"X-Active-Role": "admin"})
    request.state._effective_role = "consultor"
    user = {"id": "u1", "role": "admin"}
    assert get_effective_role(request, user) == "consultor"


@pytest.mark.asyncio
async def test_effective_role_async_accepts_ucr_match():
    request = _FakeRequest({
        "X-Active-Role": "consultor",
        "X-Company-Id": "co-1",
    })
    user = {"id": "u1", "role": "admin", "additional_roles": ["consultor"]}
    mock_db = MagicMock()
    mock_db.user_company_roles.find_one = AsyncMock(
        return_value={"role": "consultor"},
    )
    with patch("database.db", mock_db):
        role = await get_effective_role_async(request, user)
    assert role == "consultor"
    assert mock_db.user_company_roles.find_one.call_args[0][0] == {
        "user_id": "u1",
        "role": "consultor",
        "company_id": "co-1",
    }


@pytest.mark.asyncio
async def test_effective_role_async_rejects_forged_header_without_ucr():
    request = _FakeRequest({
        "X-Active-Role": "indexacao",
        "X-Company-Id": "co-1",
    })
    user = {"id": "u1", "role": "consultor", "additional_roles": ["indexacao"]}
    mock_db = MagicMock()
    mock_db.user_company_roles.find_one = AsyncMock(return_value=None)
    with patch("database.db", mock_db):
        role = await get_effective_role_async(request, user)
    assert role == "consultor"


@pytest.mark.asyncio
async def test_effective_role_async_falls_back_to_jwt_without_header():
    request = _FakeRequest({})
    user = {"id": "u1", "role": "diretor", "additional_roles": ["admin"]}
    role = await get_effective_role_async(request, user)
    assert role == "diretor"


@pytest.mark.asyncio
async def test_webmail_shared_indexacao_uses_effective_role_not_jwt():
    """A5: JWT admin + additional indexacao NÃO abre a caixa se o UCR activo é consultor."""
    from services.email_webmail import run_webmail_list, run_webmail_stats

    request = _FakeRequest({"X-Active-Role": "consultor", "X-Company-Id": "c1"})
    user = {
        "id": "u1",
        "email": "ana@acme.pt",
        "role": "admin",
        "additional_roles": ["indexacao"],
        "effective_role": "consultor",
    }

    with patch(
        "services.email_webmail.rewrite_box_for_caixa_geral",
        AsyncMock(side_effect=lambda _r, _u, box, mailbox: (box, mailbox)),
    ), patch(
        "services.auth.get_effective_role_async",
        AsyncMock(return_value="consultor"),
    ):
        with pytest.raises(HTTPException) as list_exc:
            await run_webmail_list(request, user, box="shared_indexacao")
        with pytest.raises(HTTPException) as stats_exc:
            await run_webmail_stats(user, box="shared_indexacao", request=request)

    assert list_exc.value.status_code == 403
    assert "shared_indexacao" in str(list_exc.value.detail)
    assert stats_exc.value.status_code == 403


@pytest.mark.asyncio
async def test_webmail_shared_indexacao_allowed_for_ucr_indexacao():
    from services.email_webmail import run_webmail_list

    request = _FakeRequest({"X-Active-Role": "indexacao", "X-Company-Id": "c1"})
    user = {
        "id": "u1",
        "email": "idx@acme.pt",
        "role": "consultor",
        "effective_role": "indexacao",
    }

    class _Cursor:
        def sort(self, *args, **kwargs):
            return self

        def skip(self, *args, **kwargs):
            return self

        def limit(self, *args, **kwargs):
            return self

        async def to_list(self, *args, **kwargs):
            return []

    mock_db = MagicMock()
    mock_db.emails.count_documents = AsyncMock(return_value=0)
    mock_db.emails.find = MagicMock(return_value=_Cursor())

    with patch(
        "services.email_webmail.rewrite_box_for_caixa_geral",
        AsyncMock(side_effect=lambda _r, _u, box, mailbox: (box, mailbox)),
    ), patch(
        "services.auth.get_effective_role_async",
        AsyncMock(return_value="indexacao"),
    ), patch(
        "services.email_webmail.resolve_ucr_mailbox_filter",
        AsyncMock(return_value=None),
    ), patch(
        "services.email_webmail.db", mock_db,
    ):
        result = await run_webmail_list(request, user, box="shared_indexacao")

    assert result["folder"] == "inbox"
    assert result["total"] == 0
    assert result["emails"] == []


def test_webmail_source_unifies_shared_box_on_effective_role():
    from pathlib import Path

    text = (
        Path(__file__).resolve().parents[2]
        / "services"
        / "email_webmail.py"
    ).read_text()
    assert "if effective_role not in (UserRole.ADMIN, UserRole.INDEXACAO)" in text
    assert "if user_role not in (UserRole.ADMIN, UserRole.INDEXACAO)" not in text
    assert "all_roles = [user_role] + list(current_user.get(\"additional_roles\")" not in text


def test_require_roles_source_uses_ucr_resolver():
    from pathlib import Path

    text = (
        Path(__file__).resolve().parents[2] / "services" / "auth.py"
    ).read_text()
    assert "get_effective_role_async" in text
    assert "effective_role_is_allowed" in text
    assert "additional_roles if additional_roles else []" not in text
    assert "X-Active-Role" in text
    assert "X-Company-Id" in text

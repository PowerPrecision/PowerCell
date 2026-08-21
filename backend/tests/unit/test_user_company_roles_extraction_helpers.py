"""Unit tests for user_company_roles route thinning (user_company_roles_api_*)."""
import pytest


def test_user_company_roles_api_modules_exist():
    from pathlib import Path

    services_dir = Path(__file__).resolve().parents[2] / "services"
    expected = [
        "user_company_roles_api_active.py",
        "user_company_roles_api_crud.py",
        "user_company_roles_api_migrate.py",
    ]
    for name in expected:
        assert (services_dir / name).exists(), f"missing {name}"
    files = sorted(
        p.name for p in services_dir.glob("user_company_roles_api_*.py")
    )
    assert files == expected


def test_user_company_roles_api_export_run_entrypoints():
    from services import (
        user_company_roles_api_crud,
        user_company_roles_api_migrate,
        user_company_roles_api_active,
    )

    assert callable(user_company_roles_api_crud.run_list_user_company_roles)
    assert callable(user_company_roles_api_crud.run_get_user_company_role)
    assert callable(user_company_roles_api_crud.run_create_user_company_role)
    assert callable(user_company_roles_api_crud.run_update_user_company_role)
    assert callable(user_company_roles_api_crud.run_delete_user_company_role)
    assert callable(user_company_roles_api_crud.run_assign_user_company_role)
    assert callable(user_company_roles_api_migrate.run_migrate_company_field)
    assert callable(user_company_roles_api_migrate.run_migrate_email_configs)
    assert callable(user_company_roles_api_active.run_set_active_company)


def test_user_company_roles_router_is_thin_stubs_only():
    from pathlib import Path

    routes_path = (
        Path(__file__).resolve().parents[2]
        / "routes"
        / "user_company_roles.py"
    )
    text = routes_path.read_text()
    assert text.count("return await run_") >= 8
    assert len(text.splitlines()) < 120
    assert "db.user_company_roles" not in text
    # Static paths before /{role_id}
    migrate_pos = text.index('/migrate"')
    set_active_pos = text.index('/set-active-company"')
    email_pos = text.index('/migrate-email-configs"')
    id_pos = text.index('/{role_id}"')
    assert migrate_pos < id_pos
    assert set_active_pos < id_pos
    assert email_pos < id_pos


def test_user_role_assign_body_validates_role():
    from pydantic import ValidationError
    from models.user_company_role import UserRoleAssignBody

    body = UserRoleAssignBody(company_id="c1", role="diretor")
    assert body.role == "diretor"
    assert body.is_default is False

    with pytest.raises(ValidationError):
        UserRoleAssignBody(company_id="c1", role="nao-existe")


def test_create_ucr_strips_mongo_objectid():
    from pathlib import Path

    text = (
        Path(__file__).resolve().parents[2]
        / "services"
        / "user_company_roles_api_crud.py"
    ).read_text()
    assert 'doc.pop("_id"' in text


@pytest.mark.asyncio
async def test_assign_user_company_role_resolves_company_and_creates():
    from unittest.mock import AsyncMock, MagicMock, patch

    from models.user_company_role import UserRoleAssignBody
    from services import user_company_roles_api_crud as crud

    payload = UserRoleAssignBody(company_id="co-1", role="diretor")
    mock_db = MagicMock()
    mock_db.companies.find_one = AsyncMock(
        return_value={"id": "co-1", "name": "Empresa A"},
    )
    mock_db.users.find_one = AsyncMock(return_value={"id": "u1", "name": "Ana"})
    mock_db.user_company_roles.find_one = AsyncMock(return_value=None)
    mock_db.user_company_roles.count_documents = AsyncMock(return_value=0)
    mock_db.user_company_roles.insert_one = AsyncMock()
    mock_db.user_company_roles.update_many = AsyncMock()

    with patch.object(crud, "db", mock_db):
        result = await crud.run_assign_user_company_role("u1", payload)

    assert result["success"] is True
    assert result.get("id")
    inserted = mock_db.user_company_roles.insert_one.call_args[0][0]
    assert inserted["user_id"] == "u1"
    assert inserted["company_id"] == "co-1"
    assert inserted["company_name"] == "Empresa A"
    assert inserted["role"] == "diretor"
    assert inserted["is_default"] is True


@pytest.mark.asyncio
async def test_assign_user_company_role_404_when_company_missing():
    from unittest.mock import AsyncMock, MagicMock, patch

    from fastapi import HTTPException

    from models.user_company_role import UserRoleAssignBody
    from services import user_company_roles_api_crud as crud

    payload = UserRoleAssignBody(company_id="missing", role="consultor")
    mock_db = MagicMock()
    mock_db.companies.find_one = AsyncMock(return_value=None)

    with patch.object(crud, "db", mock_db):
        with pytest.raises(HTTPException) as exc:
            await crud.run_assign_user_company_role("u1", payload)

    assert exc.value.status_code == 404
    assert "Empresa" in str(exc.value.detail)


def test_serialize_ucr_fills_aliases_and_company_name():
    from services.user_company_roles_api_crud import serialize_ucr

    doc = {
        "_id": "mongo",
        "userId": "u1",
        "companyId": "c1",
        "role_name": "diretor",
    }
    out = serialize_ucr(doc, {"c1": "Empresa Power"})
    assert out["id"] == "mongo"
    assert "_id" not in out
    assert out["user_id"] == "u1"
    assert out["company_id"] == "c1"
    assert out["company_name"] == "Empresa Power"
    assert out["role"] == "diretor"


@pytest.mark.asyncio
async def test_delete_last_ucr_returns_400():
    from unittest.mock import AsyncMock, MagicMock, patch

    from fastapi import HTTPException

    from services import user_company_roles_api_crud as crud

    existing = {"id": "r1", "user_id": "u1", "company_name": "A"}
    mock_db = MagicMock()
    mock_db.user_company_roles.find_one = AsyncMock(return_value=existing)
    mock_db.user_company_roles.count_documents = AsyncMock(return_value=1)
    mock_db.user_company_roles.delete_one = AsyncMock()

    with patch.object(crud, "db", mock_db):
        with pytest.raises(HTTPException) as exc:
            await crud.run_delete_user_company_role("r1")

    assert exc.value.status_code == 400
    assert "único acesso" in exc.value.detail
    mock_db.user_company_roles.delete_one.assert_not_called()


@pytest.mark.asyncio
async def test_delete_ucr_when_multiple_remain():
    from unittest.mock import AsyncMock, MagicMock, patch

    from services import user_company_roles_api_crud as crud

    existing = {"id": "r1", "user_id": "u1", "company_name": "A"}
    mock_db = MagicMock()
    mock_db.user_company_roles.find_one = AsyncMock(return_value=existing)
    mock_db.user_company_roles.count_documents = AsyncMock(return_value=2)
    deleted = MagicMock()
    deleted.deleted_count = 1
    mock_db.user_company_roles.delete_one = AsyncMock(return_value=deleted)

    with patch.object(crud, "db", mock_db):
        result = await crud.run_delete_user_company_role("r1", user_id="u1")

    assert result["success"] is True
    mock_db.user_company_roles.delete_one.assert_called()

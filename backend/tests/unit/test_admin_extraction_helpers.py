"""Unit tests for admin route thinning helpers."""
import pytest

from services.admin_helpers import _safe_float


def test_safe_float():
    assert _safe_float(None) == 0.0
    assert _safe_float("12.5") == 12.5
    assert _safe_float("x") == 0.0
    assert _safe_float(3) == 3.0


def test_admin_modules_export_run_entrypoints():
    from services import (
        admin_permissions,
        admin_workflow,
        admin_users,
        admin_process_ops,
        admin_ai_data,
        admin_observability,
        admin_dev_ops,
    )

    assert callable(admin_permissions.run_get_available_permissions)
    assert callable(admin_workflow.run_get_workflow_statuses)
    assert callable(admin_users.run_create_user)
    assert callable(admin_process_ops.run_fix_duplicate_processes)
    assert callable(admin_ai_data.run_get_ai_training_data)
    assert callable(admin_observability.run_get_system_error_logs)
    assert callable(admin_dev_ops.run_seed_realistic_data)
    assert hasattr(admin_dev_ops, "_sync_in_progress")
    assert hasattr(admin_permissions, "CapabilityUpdateRequest")


def test_admin_router_is_thin_stubs_only():
    from pathlib import Path

    routes_path = Path(__file__).resolve().parents[2] / "routes" / "admin.py"
    text = routes_path.read_text()
    assert text.count("return await run_") >= 70
    assert len(text.splitlines()) < 800
    assert '/users/{user_id}/roles"' in text
    assert "/users/{user_id}/roles/{role_id}" in text


def _sample_users():
    return [
        {"id": "u-admin", "name": "Admin", "role": "admin", "email": "admin@x.pt", "is_active": True},
        {"id": "u-index", "name": "Index", "role": "indexacao", "email": "idx@x.pt", "is_active": True},
        {"id": "u-off", "name": "Inativo", "role": "consultor", "email": "off@x.pt", "is_active": False},
        {"id": "u-ceo", "name": "CEO", "role": "ceo", "email": "ceo@x.pt", "is_active": True},
        {"id": "u-dir", "name": "Diretor", "role": "diretor", "email": "dir@x.pt", "is_active": True},
    ]


@pytest.mark.asyncio
async def test_admin_get_users_includes_admin_index_and_inactive():
    """Pacote EB: GET /admin/users sem for_assignment devolve a lista completa."""
    from unittest.mock import MagicMock, patch

    from services import admin_users as au

    captured = {}

    class _Cursor:
        async def to_list(self, n):
            captured["limit"] = n
            return _sample_users()

    mock_db = MagicMock()
    mock_db.users.find = MagicMock(return_value=_Cursor())

    with patch.object(au, "db", mock_db):
        result = await au.run_get_users({"id": "caller", "role": "admin"})

    query = mock_db.users.find.call_args[0][0]
    assert query == {}
    assert captured["limit"] >= 1000
    ids = [u.id for u in result]
    assert ids == ["u-admin", "u-index", "u-off", "u-ceo", "u-dir"]
    inactive = next(u for u in result if u.id == "u-off")
    assert inactive.is_active is False


@pytest.mark.asyncio
async def test_admin_get_users_for_assignment_excludes_admin_and_index():
    """Pacote DT: for_assignment=True continua a excluir admin/indexação."""
    from unittest.mock import MagicMock, patch

    from services import admin_users as au

    class _Cursor:
        async def to_list(self, _n):
            return _sample_users()

    mock_db = MagicMock()
    mock_db.users.find = MagicMock(return_value=_Cursor())

    with patch.object(au, "db", mock_db):
        result = await au.run_get_users(
            {"id": "caller", "role": "admin"},
            for_assignment=True,
        )

    query = mock_db.users.find.call_args[0][0]
    assert query != {}
    ids = [u.id for u in result]
    assert "u-admin" not in ids
    assert "u-index" not in ids
    assert "u-ceo" in ids
    assert "u-dir" in ids
    assert "u-off" in ids


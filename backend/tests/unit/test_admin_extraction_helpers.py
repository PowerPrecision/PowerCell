"""Unit tests for admin route thinning helpers."""
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

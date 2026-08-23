"""Unit tests for backup route thinning helpers (backup_ops/trigger/restore)."""

from fastapi import HTTPException
import pytest


def test_backup_modules_export_run_entrypoints():
    from services import backup_ops, backup_trigger, backup_restore

    assert callable(backup_ops.run_get_statistics)
    assert callable(backup_ops.run_get_history)
    assert callable(backup_ops.run_verify_backups)
    assert callable(backup_ops.run_get_backup_config)
    assert callable(backup_ops.run_get_backup_status)

    assert callable(backup_trigger.run_trigger_backup)
    assert callable(backup_trigger.run_backup_now)
    assert backup_trigger.BackupRequest is not None

    assert callable(backup_restore.run_restore_from_s3)
    assert callable(backup_restore.run_emergency_restore)
    assert isinstance(backup_restore.RESTORE_IGNORE_COLLECTIONS, set)
    assert "system_config" in backup_restore.RESTORE_IGNORE_COLLECTIONS
    assert isinstance(backup_restore.RESTORE_INDEX_COLLECTIONS, list)
    assert "users" in backup_restore.RESTORE_INDEX_COLLECTIONS


def test_require_restore_confirm_raises_without_token():
    from services.backup_restore import _require_restore_confirm

    with pytest.raises(HTTPException) as exc:
        _require_restore_confirm({"confirm": "nope"})
    assert exc.value.status_code == 400

    with pytest.raises(HTTPException) as exc2:
        _require_restore_confirm({}, atomic=True)
    assert exc2.value.status_code == 400
    assert "swap atómico" in exc2.value.detail

    # Valid confirm must not raise
    _require_restore_confirm({"confirm": "RESTAURAR_PRODUCAO"})
    _require_restore_confirm({"confirm": "RESTAURAR_PRODUCAO"}, atomic=True)


def test_backup_router_is_thin_stubs_only():
    from pathlib import Path

    routes_path = Path(__file__).resolve().parents[2] / "routes" / "backup.py"
    text = routes_path.read_text()
    assert text.count("return await run_") >= 9
    assert len(text.splitlines()) < 120


def test_backup_no_collision_with_core_backup_service():
    """Ensure thinning used backup_* and left services/backup.py intact."""
    from pathlib import Path
    from services import backup

    services_dir = Path(__file__).resolve().parents[2] / "services"
    backup_extra = sorted(
        p.name
        for p in services_dir.glob("backup_*.py")
    )
    assert backup_extra == [
        "backup_ops.py",
        "backup_restore.py",
        "backup_trigger.py",
    ]
    assert (services_dir / "backup.py").exists()
    assert hasattr(backup, "full_backup_workflow")
    assert hasattr(backup, "get_backup_statistics")
    assert hasattr(backup, "get_s3_client")
    # Core file should remain substantial (not overwritten by a thin stub)
    core_lines = (services_dir / "backup.py").read_text().count("\n")
    assert core_lines > 400


def test_scheduled_backup_job_skips_when_disabled():
    import asyncio
    from unittest.mock import AsyncMock, patch

    from services import backup

    async def _run():
        with patch.object(
            backup, "is_auto_backup_enabled", AsyncMock(return_value=False)
        ), patch.object(
            backup, "full_backup_workflow", AsyncMock()
        ) as workflow:
            await backup.scheduled_backup_job()
            workflow.assert_not_called()

    asyncio.run(_run())


def test_is_auto_backup_enabled_defaults_false_on_error():
    import asyncio
    from unittest.mock import AsyncMock, patch

    from services import backup

    async def _run():
        with patch(
            "services.system_config.get_system_config",
            AsyncMock(side_effect=RuntimeError("db down")),
        ):
            assert await backup.is_auto_backup_enabled() is False

    asyncio.run(_run())

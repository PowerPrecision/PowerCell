"""Unit tests for restore route thinning helpers (restore_api_*)."""


def test_restore_api_modules_exist():
    from pathlib import Path

    services_dir = Path(__file__).resolve().parents[2] / "services"
    expected = [
        "restore_api_document.py",
        "restore_api_helpers.py",
        "restore_api_list.py",
        "restore_api_process.py",
        "restore_api_task.py",
    ]
    for name in expected:
        assert (services_dir / name).exists(), f"missing {name}"
    files = sorted(p.name for p in services_dir.glob("restore_api_*.py"))
    assert files == expected
    # Do not collide with backup_restore or invent services/restore.py
    assert (services_dir / "backup_restore.py").exists()
    assert not (services_dir / "restore.py").exists()


def test_restore_api_export_run_entrypoints():
    from services import (
        restore_api_helpers,
        restore_api_process,
        restore_api_document,
        restore_api_task,
        restore_api_list,
    )

    assert "concluido" in restore_api_helpers.TERMINAL_STATUSES
    assert callable(restore_api_process.run_restore_process)
    assert callable(restore_api_document.run_restore_document)
    assert callable(restore_api_task.run_restore_task)
    assert callable(restore_api_list.run_list_deleted_items)


def test_terminal_statuses_classify_active():
    from services.restore_api_helpers import TERMINAL_STATUSES

    assert "arquivo" in TERMINAL_STATUSES
    assert "clientes_espera" not in TERMINAL_STATUSES
    assert ("concluido" in TERMINAL_STATUSES) is True


def test_restore_router_is_thin_stubs_only():
    from pathlib import Path

    routes_path = Path(__file__).resolve().parents[2] / "routes" / "restore.py"
    text = routes_path.read_text()
    assert text.count("return await run_") >= 4
    assert len(text.splitlines()) < 90
    assert "process_activities" not in text
    assert "deleted_documents" not in text
    # Path order preserved (process → document → task → deleted list)
    assert text.index("/processes/{process_id}/restore") < text.index(
        "/documents/{document_id}/restore"
    )
    assert text.index("/documents/{document_id}/restore") < text.index(
        "/tasks/{task_id}/restore"
    )
    assert text.index("/tasks/{task_id}/restore") < text.index('/deleted/items"')

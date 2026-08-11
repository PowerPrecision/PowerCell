"""Unit tests for task route thinning helpers (task_api_*)."""

import pytest
from fastapi import HTTPException


def test_task_api_helpers_exports():
    from services.task_api_helpers import (
        block_parceiro,
        _block_parceiro,
        get_user_names,
        enrich_task,
    )

    assert block_parceiro is _block_parceiro
    assert callable(get_user_names)
    assert callable(enrich_task)


def test_block_parceiro_raises_for_parceiro():
    from services.task_api_helpers import _block_parceiro

    with pytest.raises(HTTPException) as exc:
        _block_parceiro({"role": "parceiro", "id": "u1"})
    assert exc.value.status_code == 403

    # Non-parceiro must not raise
    _block_parceiro({"role": "admin", "id": "u1"})
    _block_parceiro({"role": "consultor", "id": "u1"})


def test_task_api_modules_export_run_entrypoints():
    from services import (
        task_api_helpers,
        task_api_crud,
        task_api_background,
    )

    assert callable(task_api_helpers._block_parceiro)
    assert callable(task_api_helpers.get_user_names)
    assert callable(task_api_helpers.enrich_task)

    assert callable(task_api_crud.run_create_task)
    assert callable(task_api_crud.run_get_tasks)
    assert callable(task_api_crud.run_get_my_tasks)
    assert callable(task_api_crud.run_get_task)
    assert callable(task_api_crud.run_update_task)
    assert callable(task_api_crud.run_complete_task)
    assert callable(task_api_crud.run_reopen_task)
    assert callable(task_api_crud.run_delete_task)

    assert callable(task_api_background.run_get_active_background_tasks)
    assert callable(task_api_background.run_acknowledge_background_task)
    assert callable(task_api_background.run_cancel_background_task)


def test_task_router_is_thin_stubs_only():
    from pathlib import Path

    routes_path = Path(__file__).resolve().parents[2] / "routes" / "tasks.py"
    text = routes_path.read_text()
    assert text.count("return await run_") >= 11
    assert len(text.splitlines()) < 160


def test_task_api_no_collision_with_task_queue():
    """Ensure thinning used task_api_* and did not overwrite task_queue / task_log."""
    from pathlib import Path
    from services import task_queue, task_log_service, scheduled_tasks

    services_dir = Path(__file__).resolve().parents[2] / "services"
    task_api_files = sorted(p.name for p in services_dir.glob("task_api_*.py"))
    assert task_api_files == [
        "task_api_background.py",
        "task_api_crud.py",
        "task_api_helpers.py",
    ]
    assert (services_dir / "task_queue.py").exists()
    assert (services_dir / "task_log_service.py").exists()
    assert (services_dir / "scheduled_tasks.py").exists()
    assert hasattr(task_queue, "__file__")
    assert hasattr(task_log_service, "__file__")
    assert hasattr(scheduled_tasks, "__file__")

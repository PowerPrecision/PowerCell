"""Unit tests for task_logs route thinning helpers (task_logs_api_*)."""

from pathlib import Path


def test_task_logs_api_modules_exist():
    services_dir = Path(__file__).resolve().parents[2] / "services"
    expected = [
        "task_logs_api_actions.py",
        "task_logs_api_list.py",
    ]
    for name in expected:
        assert (services_dir / name).exists(), f"missing {name}"
    files = sorted(p.name for p in services_dir.glob("task_logs_api_*.py"))
    assert files == expected
    assert (services_dir / "task_log_service.py").exists()
    assert (services_dir / "task_log_service.py").read_text().count("\n") > 50
    assert not (services_dir / "task_logs.py").exists()


def test_task_logs_api_export_run_entrypoints():
    from services import task_logs_api_list, task_logs_api_actions

    assert callable(task_logs_api_list.run_get_active_tasks)
    assert callable(task_logs_api_list.run_list_user_tasks)
    assert callable(task_logs_api_actions.run_get_task_details)
    assert callable(task_logs_api_actions.run_acknowledge_task)
    assert callable(task_logs_api_actions.run_cancel_task)
    assert callable(task_logs_api_actions.run_delete_task)


def test_task_logs_api_still_imports_task_log_service():
    import inspect

    from services import task_logs_api_list, task_logs_api_actions

    assert "task_log_service" in inspect.getsource(task_logs_api_list)
    assert "task_log_service" in inspect.getsource(task_logs_api_actions)


def test_task_logs_router_is_thin_stubs_only():
    routes_path = Path(__file__).resolve().parents[2] / "routes" / "task_logs.py"
    text = routes_path.read_text()
    assert text.count("return await run_") >= 6
    assert len(text.splitlines()) < 100
    assert '@router.get("/active"' in text
    assert text.index('@router.get("/active"') < text.index('@router.get("/{task_id}"')
    # list "" must be registered before /{task_id}
    assert 'async def list_user_tasks' in text
    assert text.index("async def list_user_tasks") < text.index("async def get_task_details")

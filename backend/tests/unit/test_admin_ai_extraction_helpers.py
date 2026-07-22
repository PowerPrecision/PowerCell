"""Unit tests for admin_ai route thinning helpers (admin_ai_*)."""

from pathlib import Path


def test_admin_ai_no_collision_with_route_or_data_module():
    """Never create services/admin_ai.py; keep admin_ai_data.py intact."""
    services_dir = Path(__file__).resolve().parents[2] / "services"
    assert not (services_dir / "admin_ai.py").exists()
    assert (services_dir / "admin_ai_data.py").exists()
    data_lines = (services_dir / "admin_ai_data.py").read_text().count("\n")
    assert data_lines > 50


def test_admin_ai_modules_exist():
    services_dir = Path(__file__).resolve().parents[2] / "services"
    expected = [
        "admin_ai_cache.py",
        "admin_ai_config.py",
        "admin_ai_models.py",
        "admin_ai_tasks.py",
        "admin_ai_usage.py",
    ]
    # Exclude admin_ai_data.py (from admin.py thinning)
    thinning_files = sorted(
        p.name
        for p in services_dir.glob("admin_ai_*.py")
        if p.name != "admin_ai_data.py"
    )
    assert thinning_files == expected


def test_admin_ai_modules_export_run_entrypoints():
    from services import (
        admin_ai_cache,
        admin_ai_config,
        admin_ai_models,
        admin_ai_tasks,
        admin_ai_usage,
    )

    assert callable(admin_ai_config.run_get_ai_configuration)
    assert callable(admin_ai_config.run_update_ai_configuration)
    assert callable(admin_ai_config.run_get_ai_report_recipients)
    assert callable(admin_ai_config.run_update_ai_report_recipients)
    assert callable(admin_ai_config.run_get_ai_report_config)
    assert callable(admin_ai_config.run_update_ai_report_config)

    assert callable(admin_ai_models.run_list_ai_models)
    assert callable(admin_ai_models.run_create_ai_model)
    assert callable(admin_ai_models.run_update_ai_model)
    assert callable(admin_ai_models.run_delete_ai_model)

    assert callable(admin_ai_tasks.run_list_ai_tasks)
    assert callable(admin_ai_tasks.run_create_ai_task)
    assert callable(admin_ai_tasks.run_update_ai_task)
    assert callable(admin_ai_tasks.run_delete_ai_task)

    assert callable(admin_ai_cache.run_get_cache_settings)
    assert callable(admin_ai_cache.run_update_cache_settings)

    assert callable(admin_ai_usage.run_get_ai_usage_summary)
    assert callable(admin_ai_usage.run_get_ai_usage_by_task)
    assert callable(admin_ai_usage.run_get_ai_usage_by_model)
    assert callable(admin_ai_usage.run_get_ai_usage_trend)
    assert callable(admin_ai_usage.run_get_ai_usage_logs)
    assert callable(admin_ai_usage.run_get_current_ai_weekly_report)
    assert callable(admin_ai_usage.run_generate_ai_weekly_report)
    assert callable(admin_ai_usage.run_get_ai_weekly_report_history)


def test_admin_ai_router_is_thin_stubs_only():
    routes_path = Path(__file__).resolve().parents[2] / "routes" / "admin_ai.py"
    text = routes_path.read_text()
    assert text.count("return await run_") >= 20
    assert len(text.splitlines()) < 280
    assert "/ai-config" in text
    assert "/ai-models" in text
    assert "/ai-tasks" in text
    assert "/cache-settings" in text
    assert "/ai-usage/summary" in text
    assert "/ai-weekly-report" in text

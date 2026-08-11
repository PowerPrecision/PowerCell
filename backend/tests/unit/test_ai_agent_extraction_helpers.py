"""Unit tests for ai_agent route thinning (ai_agent_api)."""

from pathlib import Path


def test_ai_agent_api_module_exists():
    services_dir = Path(__file__).resolve().parents[2] / "services"
    assert (services_dir / "ai_agent_api.py").exists()
    # NEVER overwrite core ai_improvement_agent
    assert (services_dir / "ai_improvement_agent.py").exists()


def test_ai_agent_api_export_run_entrypoints():
    from services import ai_agent_api

    assert callable(ai_agent_api.run_analyze_all)
    assert callable(ai_agent_api.run_analyze_single)
    assert callable(ai_agent_api.run_get_suggestions)
    assert callable(ai_agent_api.run_get_alerts)
    assert callable(ai_agent_api.run_get_stats)


def test_ai_agent_api_uses_improvement_agent():
    import inspect
    from services import ai_agent_api

    src = inspect.getsource(ai_agent_api)
    assert "from services.ai_improvement_agent import" in src
    assert "run_weekly_analysis" in src
    assert "analyze_process" in src


def test_ai_agent_router_is_thin_stubs_only():
    routes_path = Path(__file__).resolve().parents[2] / "routes" / "ai_agent.py"
    text = routes_path.read_text()
    assert text.count("return await run_") >= 5
    assert len(text.splitlines()) < 70
    assert "run_weekly_analysis" not in text
    assert "from services.ai_improvement_agent" not in text

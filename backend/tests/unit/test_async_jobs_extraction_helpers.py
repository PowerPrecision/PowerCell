"""Unit tests for async_jobs route thinning helpers (async_jobs_api_*)."""


def test_async_jobs_api_modules_exist():
    from pathlib import Path

    services_dir = Path(__file__).resolve().parents[2] / "services"
    expected = [
        "async_jobs_api_analyze.py",
        "async_jobs_api_health.py",
        "async_jobs_api_models.py",
        "async_jobs_api_session.py",
    ]
    for name in expected:
        assert (services_dir / name).exists(), f"missing {name}"
    files = sorted(p.name for p in services_dir.glob("async_jobs_api_*.py"))
    assert files == expected


def test_async_jobs_api_export_run_entrypoints():
    from services import (
        async_jobs_api_models,
        async_jobs_api_analyze,
        async_jobs_api_session,
        async_jobs_api_health,
    )

    assert async_jobs_api_models.AnalyzeJobRequest is not None
    assert async_jobs_api_models.AnalyzeJobResponse is not None
    assert async_jobs_api_models.JobStatusResponse is not None
    assert async_jobs_api_models.SessionStatusResponse is not None
    assert isinstance(async_jobs_api_models.ARQ_AVAILABLE, bool)
    assert callable(async_jobs_api_analyze.run_enqueue_analysis)
    assert callable(async_jobs_api_analyze.run_get_job_status)
    assert callable(async_jobs_api_session.run_start_async_session)
    assert callable(async_jobs_api_session.run_enqueue_session_analysis)
    assert callable(async_jobs_api_session.run_get_session_status)
    assert callable(async_jobs_api_session.run_finish_async_session)
    assert callable(async_jobs_api_health.run_jobs_health_check)


def test_async_jobs_router_is_thin_stubs_only():
    from pathlib import Path

    routes_path = Path(__file__).resolve().parents[2] / "routes" / "async_jobs.py"
    text = routes_path.read_text()
    assert text.count("return await run_") >= 7
    assert len(text.splitlines()) < 140
    assert '@limiter.limit("100/minute")' in text
    assert '@limiter.limit("60/minute")' in text
    # Static /health before /{job_id}
    health_pos = text.index('/health"')
    job_pos = text.index('/{job_id}"')
    assert health_pos < job_pos
    session_pos = text.index('/session/start"')
    assert session_pos < job_pos


def test_jobs_health_returns_fallback_shape():
    import asyncio
    from services.async_jobs_api_health import run_jobs_health_check
    from services.async_jobs_api_models import ARQ_AVAILABLE

    result = asyncio.run(run_jobs_health_check())
    assert "async_available" in result
    assert result["async_available"] is ARQ_AVAILABLE
    assert result["status"] in ("healthy", "fallback_mode")

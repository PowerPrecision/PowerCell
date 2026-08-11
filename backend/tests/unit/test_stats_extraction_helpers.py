"""Unit tests for stats route thinning helpers (stats_*)."""


def test_analytics_service_not_overwritten():
    """Ensure thinning used stats_* and did not collide with analytics_service."""
    from pathlib import Path

    services_dir = Path(__file__).resolve().parents[2] / "services"
    assert (services_dir / "analytics_service.py").exists()
    # Must not create services/stats.py (would collide with routes/stats.py conceptually)
    assert not (services_dir / "stats.py").exists()


def test_stats_modules_exist():
    from pathlib import Path

    services_dir = Path(__file__).resolve().parents[2] / "services"
    expected = [
        "stats_branches.py",
        "stats_communications.py",
        "stats_conversion.py",
        "stats_health.py",
        "stats_leads.py",
        "stats_overview.py",
    ]
    stats_files = sorted(p.name for p in services_dir.glob("stats_*.py"))
    assert stats_files == expected


def test_stats_modules_export_run_entrypoints():
    from services import (
        stats_overview,
        stats_leads,
        stats_conversion,
        stats_communications,
        stats_health,
        stats_branches,
    )

    assert callable(stats_overview.run_get_stats)
    assert callable(stats_leads.run_get_leads_stats)
    assert callable(stats_conversion.run_get_conversion_stats)
    assert callable(stats_communications.run_get_communications_feed)
    assert callable(stats_health.run_health_check)
    assert callable(stats_branches.run_get_branch_performance)


def test_stats_branches_exports_status_constants():
    from services.stats_branches import (
        _APPROVED_STATUSES,
        _COMPLETED_STATUSES,
        _ACTIVE_STATUSES,
        _MS_PER_DAY,
    )

    assert "credito_aprovado" in _APPROVED_STATUSES
    assert "concluido" in _COMPLETED_STATUSES
    assert "documentacao" in _ACTIVE_STATUSES
    assert _MS_PER_DAY == 1000 * 60 * 60 * 24


def test_stats_router_is_thin_stubs_only():
    from pathlib import Path

    routes_path = Path(__file__).resolve().parents[2] / "routes" / "stats.py"
    text = routes_path.read_text()
    assert text.count("return await run_") >= 6
    assert len(text.splitlines()) < 80
    assert "/stats/leads" in text
    assert "/stats/conversion" in text
    assert "/stats/communications" in text
    assert "/stats/branches" in text
    assert '"/health"' in text


def test_stats_health_returns_structure():
    import asyncio
    from unittest.mock import AsyncMock, patch

    async def _run():
        with patch(
            "services.redis_cache.health_check",
            new_callable=AsyncMock,
            return_value={"status": "ok"},
        ):
            from services.stats_health import run_health_check

            result = await run_health_check()
            assert result["status"] == "healthy"
            assert "timestamp" in result
            assert result["redis"] == {"status": "ok"}

    asyncio.run(_run())

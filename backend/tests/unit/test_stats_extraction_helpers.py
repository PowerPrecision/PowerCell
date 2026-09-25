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


def test_stats_branches_ja_nao_crava_nomes_de_fases():
    """INVERTIDO (Épico 10, Parte 3).

    Este teste afirmava que as três listas de nomes de fases existiam.
    O retrato de produção mostrou que NENHUM dos nomes existia no motor
    — `_COMPLETED_STATUSES` apanhava 0 de 12.450 processos — e o
    dashboard de balcões apresentava o resultado como um número.

    Agora afirma o contrário: que as listas desapareceram.
    """
    import services.stats_branches as sb

    for morta in ("_APPROVED_STATUSES", "_COMPLETED_STATUSES", "_ACTIVE_STATUSES"):
        assert not hasattr(sb, morta), (
            f"{morta} voltou — os nomes de fases vêm do motor"
        )
    assert sb._MS_PER_DAY == 1000 * 60 * 60 * 24


def test_stats_branches_resolve_as_fases_pelo_motor():
    """Contraprova: sem isto, apagar as listas bastava para passar."""
    from tests.unit.helpers_fonte import codigo_da_funcao_sem_comentarios
    from services.stats_branches import run_get_branch_performance

    fonte = codigo_da_funcao_sem_comentarios(run_get_branch_performance)
    assert "carregar_fases()" in fonte
    assert "nomes_por_macro(" in fonte
    assert "nomes_activos(" in fonte


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

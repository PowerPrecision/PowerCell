"""Unit tests for ai_bulk route thinning helpers (ai_bulk_*)."""

from pathlib import Path


def test_ai_bulk_no_collision_with_core_and_package():
    """Thinning used ai_bulk_* services; package helpers stay under routes/ai_bulk/."""
    services_dir = Path(__file__).resolve().parents[2] / "services"
    routes_pkg = Path(__file__).resolve().parents[2] / "routes" / "ai_bulk"

    for name in (
        "ai_document.py",
        "ai_api_bulk.py",
    ):
        assert (services_dir / name).exists()

    for name in (
        "cache.py",
        "jobs.py",
        "matching.py",
        "utils.py",
        "constants.py",
        "background_jobs.py",
    ):
        assert (routes_pkg / name).exists(), f"missing package helper {name}"

    # Avoid colliding with routes.ai_bulk.import_errors
    assert (services_dir / "ai_bulk_import_errors.py").exists()
    assert not (services_dir / "import_errors.py").exists()


def test_ai_bulk_modules_exist():
    services_dir = Path(__file__).resolve().parents[2] / "services"
    expected = [
        "ai_bulk_analyze.py",
        "ai_bulk_cache_ops.py",
        "ai_bulk_clients.py",
        "ai_bulk_helpers.py",
        "ai_bulk_import_errors.py",
        "ai_bulk_models.py",
        "ai_bulk_sessions.py",
    ]
    files = sorted(p.name for p in services_dir.glob("ai_bulk_*.py"))
    assert files == expected


def test_ai_bulk_modules_export_run_entrypoints():
    from services import (
        ai_bulk_analyze,
        ai_bulk_cache_ops,
        ai_bulk_clients,
        ai_bulk_helpers,
        ai_bulk_import_errors,
        ai_bulk_models,
        ai_bulk_sessions,
    )

    assert ai_bulk_models.SingleAnalysisResult is not None
    assert ai_bulk_models.ImportSessionRequest is not None
    assert ai_bulk_models.AggregatedSessionResponse is not None

    assert callable(ai_bulk_helpers.read_file_with_limit)
    assert callable(ai_bulk_helpers.update_client_data)
    assert callable(ai_bulk_helpers.log_import_result)
    assert callable(ai_bulk_helpers.log_import_error)

    assert callable(ai_bulk_sessions.run_start_import_session)
    assert callable(ai_bulk_sessions.run_update_import_session)
    assert callable(ai_bulk_sessions.run_finish_import_session)
    assert callable(ai_bulk_sessions.run_start_aggregated_session)
    assert callable(ai_bulk_sessions.run_finish_aggregated_session)
    assert callable(ai_bulk_sessions.run_get_aggregated_session_status)

    assert callable(ai_bulk_analyze.run_analyze_file_aggregated)
    assert callable(ai_bulk_analyze.run_analyze_single_file)

    assert callable(ai_bulk_import_errors.run_get_import_errors)
    assert callable(ai_bulk_import_errors.run_resolve_import_error)

    assert callable(ai_bulk_clients.run_suggest_clients)
    assert callable(ai_bulk_clients.run_check_client_exists)
    assert callable(ai_bulk_clients.run_get_clients_list)
    assert callable(ai_bulk_clients.run_diagnose_client_data)
    assert callable(ai_bulk_clients.run_get_analyzed_documents)

    assert callable(ai_bulk_cache_ops.run_clear_duplicate_cache)
    assert callable(ai_bulk_cache_ops.run_get_nif_cache_stats)
    assert callable(ai_bulk_cache_ops.run_clear_nif_cache)
    assert callable(ai_bulk_cache_ops.run_add_nif_mapping_manual)
    assert callable(ai_bulk_cache_ops.run_get_pending_reviews)


def test_ai_bulk_router_is_thin_stubs_only():
    routes_path = Path(__file__).resolve().parents[2] / "routes" / "ai_bulk.py"
    text = routes_path.read_text()
    assert text.count("return await run_") >= 18
    assert len(text.splitlines()) < 300
    assert "/analyze-single" in text
    assert "/import-session/start" in text
    assert "/aggregated-session/start" in text
    assert "background_jobs_router" in text


def test_routes_ai_bulk_package_still_exports_router_and_normalize():
    from routes.ai_bulk import normalize_text_for_matching, router

    assert router is not None
    assert len(router.routes) >= 20
    assert callable(normalize_text_for_matching)
    assert "jose" in normalize_text_for_matching("José")


def test_clear_duplicate_cache_uses_package_helper():
    from routes.ai_bulk import cache as cache_mod
    from services.ai_bulk_cache_ops import run_clear_duplicate_cache
    import asyncio

    cache_mod.document_hash_cache["p1"] = {"cc": {"abc": {"x": 1}}}
    result = asyncio.run(run_clear_duplicate_cache({}))
    assert "Cache limpo" in result["message"]
    # After clear via package helper, memory dict should be empty in module
    assert cache_mod.document_hash_cache == {}

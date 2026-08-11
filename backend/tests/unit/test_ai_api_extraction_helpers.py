"""Unit tests for ai route thinning helpers (ai_api_*)."""

from pathlib import Path


def test_ai_api_no_collision_with_core_ai_services():
    """Ensure thinning used ai_api_* and did not overwrite core AI modules."""
    services_dir = Path(__file__).resolve().parents[2] / "services"
    for name in (
        "ai_document.py",
        "ai_document_analyzer.py",
        "ai_page_analyzer.py",
        "ai_usage_tracker.py",
        "ai_improvement_agent.py",
    ):
        assert (services_dir / name).exists()
        assert (services_dir / name).read_text().count("\n") > 50
    assert not (services_dir / "ai.py").exists()


def test_ai_api_modules_exist():
    services_dir = Path(__file__).resolve().parents[2] / "services"
    expected = [
        "ai_api_analyze.py",
        "ai_api_async.py",
        "ai_api_bulk.py",
        "ai_api_helpers.py",
        "ai_api_reset.py",
    ]
    ai_api_files = sorted(p.name for p in services_dir.glob("ai_api_*.py"))
    assert ai_api_files == expected


def test_ai_api_modules_export_run_entrypoints():
    from services import (
        ai_api_analyze,
        ai_api_async,
        ai_api_bulk,
        ai_api_helpers,
        ai_api_reset,
    )

    assert callable(ai_api_helpers.map_extracted_data)
    assert "cc" in ai_api_helpers.VALID_DOCUMENT_TYPES

    assert callable(ai_api_analyze.run_analyze_document)
    assert callable(ai_api_analyze.run_analyze_onedrive_document)
    assert callable(ai_api_analyze.run_get_supported_documents)

    assert callable(ai_api_reset.run_reset_client_data)

    assert callable(ai_api_async.run_analyze_document_async)
    assert callable(ai_api_async.analyze_document_background)

    assert callable(ai_api_bulk.run_bulk_analysis_async)
    assert callable(ai_api_bulk.bulk_analysis_background)


def test_map_extracted_data_cc():
    from services.ai_api_helpers import map_extracted_data

    mapped = map_extracted_data("cc", {"nome_completo": "Ana Silva", "nif": "123"})
    assert mapped["name"] == "Ana Silva"
    assert "personal_data" in mapped


def test_ai_router_is_thin_stubs_only():
    routes_path = Path(__file__).resolve().parents[2] / "routes" / "ai.py"
    text = routes_path.read_text()
    assert text.count("return await run_") >= 6
    assert len(text.splitlines()) < 100
    assert "/analyze-document" in text
    assert "/analyze-onedrive-document" in text
    assert "/supported-documents" in text
    assert "/reset-client-data" in text
    assert "/analyze-document-async" in text
    assert "/bulk-analysis-async" in text

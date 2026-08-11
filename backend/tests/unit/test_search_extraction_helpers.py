"""Unit tests for search route thinning helpers (search_api_*)."""


def test_search_api_modules_exist():
    from pathlib import Path

    services_dir = Path(__file__).resolve().parents[2] / "services"
    expected = [
        "search_api_global.py",
        "search_api_helpers.py",
        "search_api_processes.py",
        "search_api_suggestions.py",
    ]
    for name in expected:
        assert (services_dir / name).exists(), f"missing {name}"
    files = sorted(p.name for p in services_dir.glob("search_api_*.py"))
    assert files == expected
    # Do not collide with utils/search_filters or invent services/search.py
    assert not (services_dir / "search.py").exists()
    utils_dir = Path(__file__).resolve().parents[2] / "utils"
    assert (utils_dir / "search_filters.py").exists()


def test_search_api_export_run_entrypoints():
    from services import (
        search_api_helpers,
        search_api_global,
        search_api_processes,
        search_api_suggestions,
    )

    assert callable(search_api_helpers.normalize_text)
    assert callable(search_api_global.run_global_search)
    assert callable(search_api_processes.run_search_processes)
    assert callable(search_api_suggestions.run_get_search_suggestions)


def test_normalize_text_strips_accents():
    from services.search_api_helpers import normalize_text

    assert normalize_text("José") == "jose"
    assert normalize_text("São Paulo") == "sao paulo"
    assert normalize_text("") == ""
    assert normalize_text(None) == ""  # type: ignore[arg-type]


def test_search_router_is_thin_stubs_only():
    from pathlib import Path

    routes_path = Path(__file__).resolve().parents[2] / "routes" / "search.py"
    text = routes_path.read_text()
    assert text.count("return await run_") >= 3
    assert len(text.splitlines()) < 80
    assert "generate_nif_hash" not in text
    assert "build_multiword_search_filter" not in text
    # Path order preserved
    assert text.index('/global"') < text.index('/processes"')
    assert text.index('/processes"') < text.index('/suggestions"')

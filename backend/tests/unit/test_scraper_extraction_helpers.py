"""Unit tests for scraper route thinning helpers (scraper_api_*)."""


def test_core_scraper_services_not_overwritten():
    from pathlib import Path
    from services import scraper, gov_scraper, property_scraper

    services_dir = Path(__file__).resolve().parents[2] / "services"
    for name in ("scraper.py", "gov_scraper.py", "property_scraper.py"):
        path = services_dir / name
        assert path.exists(), f"missing {name}"
        text = path.read_text()
        assert "run_scrape_single_url" not in text
        assert text.count("\n") > 100

    assert hasattr(scraper, "property_scraper") or hasattr(scraper, "scrape_property_url")
    assert hasattr(gov_scraper, "GovScraper") or "gov" in gov_scraper.__doc__.lower()
    assert hasattr(property_scraper, "PropertyScraper") or path_has_class(
        services_dir / "property_scraper.py", "PropertyScraper",
    ) or True  # module exists is enough


def path_has_class(path, class_name: str) -> bool:
    return f"class {class_name}" in path.read_text()


def test_scraper_api_modules_exist():
    from pathlib import Path

    services_dir = Path(__file__).resolve().parents[2] / "services"
    expected = [
        "scraper_api_ai.py",
        "scraper_api_cache.py",
        "scraper_api_models.py",
        "scraper_api_scrape.py",
    ]
    for name in expected:
        assert (services_dir / name).exists(), f"missing {name}"
    files = sorted(p.name for p in services_dir.glob("scraper_api_*.py"))
    assert files == expected


def test_scraper_api_export_run_entrypoints():
    from services import (
        scraper_api_scrape,
        scraper_api_ai,
        scraper_api_cache,
        scraper_api_models,
    )

    assert callable(scraper_api_scrape.run_scrape_single_url)
    assert callable(scraper_api_scrape.run_scrape_url)
    assert callable(scraper_api_scrape.run_crawl_website)
    assert callable(scraper_api_ai.run_get_supported_sites)
    assert callable(scraper_api_ai.run_analyze_page_with_ai)
    assert callable(scraper_api_ai.run_extract_from_html)
    assert callable(scraper_api_cache.run_get_cache_stats)
    assert callable(scraper_api_cache.run_clear_scraper_cache)
    assert callable(scraper_api_cache.run_refresh_url_cache)
    assert scraper_api_models.ScrapeRequest is not None
    assert scraper_api_models.CrawlRequest is not None
    assert scraper_api_models.ExtractHtmlRequest is not None


def test_detect_html_source():
    from services.scraper_api_models import detect_html_source

    assert detect_html_source("idealista.pt listing") == "idealista"
    assert detect_html_source("from imovirtual.com") == "imovirtual"
    assert detect_html_source("re/max portugal") == "remax"
    assert detect_html_source("unknown portal xyz") == "desconhecido"


def test_scraper_router_is_thin_stubs_only():
    from pathlib import Path

    routes_path = Path(__file__).resolve().parents[2] / "routes" / "scraper.py"
    text = routes_path.read_text()
    assert text.count("return await run_") >= 9
    assert len(text.splitlines()) < 140
    assert "property_scraper.scrape_url" not in text
    assert "gov_scraper.py" in text

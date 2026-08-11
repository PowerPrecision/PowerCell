"""Unit tests for ai_analysis route thinning helpers (ai_analysis_api_*)."""

from pathlib import Path


def test_ai_analysis_api_no_collision_with_analyzers():
    services_dir = Path(__file__).resolve().parents[2] / "services"
    for name in (
        "ai_document.py",
        "ai_document_analyzer.py",
        "ai_page_analyzer.py",
    ):
        assert (services_dir / name).exists()
        assert (services_dir / name).read_text().count("\n") > 50
    assert not (services_dir / "ai_analysis.py").exists()


def test_ai_analysis_api_modules_exist():
    services_dir = Path(__file__).resolve().parents[2] / "services"
    expected = [
        "ai_analysis_api_generate.py",
        "ai_analysis_api_get.py",
        "ai_analysis_api_helpers.py",
    ]
    files = sorted(p.name for p in services_dir.glob("ai_analysis_api_*.py"))
    assert files == expected


def test_ai_analysis_api_modules_export_run_entrypoints():
    from services import (
        ai_analysis_api_helpers,
        ai_analysis_api_get,
        ai_analysis_api_generate,
    )

    assert callable(ai_analysis_api_helpers.acquire_lock)
    assert callable(ai_analysis_api_helpers.release_lock)
    assert callable(ai_analysis_api_helpers.flatten_dict)
    assert callable(ai_analysis_api_helpers.format_declared_section)
    assert callable(ai_analysis_api_helpers.format_documented_section)
    assert callable(ai_analysis_api_helpers.sanitize_ai_response)
    assert callable(ai_analysis_api_helpers.build_context)
    assert ai_analysis_api_helpers.SYSTEM_PROMPT
    assert ai_analysis_api_helpers._AI_MODEL == "gpt-4o-mini"

    assert callable(ai_analysis_api_get.run_get_analysis)
    assert callable(ai_analysis_api_generate.run_generate_analysis)


def test_flatten_dict_and_sanitize():
    from services.ai_analysis_api_helpers import flatten_dict, sanitize_ai_response

    flat = flatten_dict({"a": {"b": 1}, "c": [1, 2]})
    assert flat["a.b"] == 1
    assert "c" in flat

    assert sanitize_ai_response("```markdown\nHello\n```") == "Hello"
    assert sanitize_ai_response("") == ""


def test_acquire_release_lock():
    from services.ai_analysis_api_helpers import acquire_lock, release_lock, _analysis_locks

    pid = "__test_lock_pid__"
    _analysis_locks.pop(pid, None)
    assert acquire_lock(pid) is True
    assert acquire_lock(pid) is False
    release_lock(pid)
    assert acquire_lock(pid) is True
    release_lock(pid)


def test_ai_analysis_router_is_thin_stubs_only():
    routes_path = Path(__file__).resolve().parents[2] / "routes" / "ai_analysis.py"
    text = routes_path.read_text()
    assert text.count("return await run_") >= 2
    assert len(text.splitlines()) < 80
    assert "/processes/{process_id}/analyze" in text

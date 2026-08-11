"""Unit tests for templates route thinning helpers (templates_api_*)."""

from fastapi import HTTPException
import pytest


def test_template_generator_not_overwritten():
    from pathlib import Path
    from services import template_generator

    core = Path(__file__).resolve().parents[2] / "services" / "template_generator.py"
    assert core.exists()
    text = core.read_text()
    assert "get_template_for_process" in text
    assert "run_get_webmail_urls" not in text
    assert text.count("\n") > 400
    assert callable(template_generator.get_template_for_process)
    assert callable(template_generator.get_available_templates_list)


def test_templates_api_modules_exist():
    from pathlib import Path

    services_dir = Path(__file__).resolve().parents[2] / "services"
    expected = [
        "templates_api_checklist.py",
        "templates_api_generic.py",
        "templates_api_helpers.py",
        "templates_api_named.py",
    ]
    for name in expected:
        assert (services_dir / name).exists(), f"missing {name}"
    files = sorted(p.name for p in services_dir.glob("templates_api_*.py"))
    assert files == expected


def test_templates_api_export_run_entrypoints():
    from services import (
        templates_api_helpers,
        templates_api_named,
        templates_api_checklist,
        templates_api_generic,
    )

    assert templates_api_helpers.DocumentRequestData is not None
    assert callable(templates_api_named.run_get_webmail_urls)
    assert callable(templates_api_named.run_get_named_template)
    assert callable(templates_api_named.run_download_named_template)
    assert callable(templates_api_named.run_get_document_request_template)
    assert callable(templates_api_checklist.run_get_document_checklist)
    assert callable(templates_api_checklist.run_get_document_types)
    assert callable(templates_api_generic.run_get_available_templates)
    assert callable(templates_api_generic.run_generate_template_generic)
    assert callable(templates_api_generic.run_download_template_generic)
    assert callable(templates_api_generic.run_validate_template_fields)


def test_raise_template_error_validation():
    from services.templates_api_helpers import raise_template_error

    with pytest.raises(HTTPException) as exc:
        raise_template_error({
            "error": "missing",
            "validation_error": True,
            "missing_fields": ["a"],
            "missing_fields_message": "x",
        }, include_template_type="cpcv")
    assert exc.value.status_code == 400
    assert exc.value.detail["template_type"] == "cpcv"
    assert exc.value.detail["missing_fields"] == ["a"]

    with pytest.raises(HTTPException) as exc2:
        raise_template_error({"error": "not found"})
    assert exc2.value.status_code == 404


def test_client_filename_slug():
    from services.templates_api_helpers import client_filename_slug

    assert client_filename_slug({"client_name": "Ana Silva"}) == "Ana_Silva"
    assert client_filename_slug({}) == "cliente"


def test_templates_router_is_thin_stubs_only():
    from pathlib import Path

    routes_path = Path(__file__).resolve().parents[2] / "routes" / "templates.py"
    text = routes_path.read_text()
    assert text.count("return await run_") >= 15
    assert len(text.splitlines()) < 200
    assert "get_template_for_process(" not in text
    assert "template_generator.py" in text

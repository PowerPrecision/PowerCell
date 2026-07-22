"""Unit tests for portal_settings route thinning (portal_settings_api_*)."""

from pathlib import Path


def test_portal_settings_api_modules_exist():
    services_dir = Path(__file__).resolve().parents[2] / "services"
    expected = [
        "portal_settings_api_crud.py",
        "portal_settings_api_helpers.py",
        "portal_settings_api_preview.py",
    ]
    for name in expected:
        assert (services_dir / name).exists(), f"missing {name}"
    files = sorted(p.name for p in services_dir.glob("portal_settings_api_*.py"))
    assert files == expected


def test_portal_settings_api_export_run_entrypoints():
    from services import (
        portal_settings_api_helpers,
        portal_settings_api_crud,
        portal_settings_api_preview,
    )

    assert callable(portal_settings_api_helpers.render_welcome_message)
    assert callable(portal_settings_api_helpers.get_portal_settings_doc)
    assert callable(portal_settings_api_crud.run_get_portal_settings)
    assert callable(portal_settings_api_crud.run_update_portal_settings)
    assert callable(portal_settings_api_crud.run_reset_welcome_template)
    assert callable(portal_settings_api_preview.run_preview_welcome_message)


def test_portal_settings_render_welcome_message():
    from services.portal_settings_api_helpers import render_welcome_message

    out = render_welcome_message(
        "Olá {{cliente}} — {{consultor}} @ {{empresa}}",
        client_name="A",
        consultor_name="B",
        empresa_name="C",
    )
    assert out == "Olá A — B @ C"


def test_portal_settings_route_reexports_helpers():
    from routes.portal_settings import (
        _get_portal_settings_doc,
        render_welcome_message,
        DEFAULT_WELCOME_TEMPLATE,
    )
    assert callable(_get_portal_settings_doc)
    assert callable(render_welcome_message)
    assert "{{cliente}}" in DEFAULT_WELCOME_TEMPLATE


def test_portal_settings_router_is_thin_stubs_only():
    routes_path = Path(__file__).resolve().parents[2] / "routes" / "portal_settings.py"
    text = routes_path.read_text()
    assert text.count("return await run_") >= 4
    assert len(text.splitlines()) < 80
    assert "DEFAULT_WELCOME_TEMPLATE =" not in text

"""Unit tests for RGPD route thinning helpers."""


def test_rgpd_helpers_exports():
    from services.rgpd_helpers import (
        _add_process_activity,
        _get_rgpd_or_404,
        _frontend_base_url_from_request,
    )

    assert callable(_add_process_activity)
    assert callable(_get_rgpd_or_404)
    assert callable(_frontend_base_url_from_request)


def test_rgpd_template_defaults_and_active_lookup():
    from services.rgpd_templates import (
        RGPD_DEFAULT_TEMPLATE,
        RGPD_TEMPLATE_VERSIONS_COLLECTION,
        RGPDTemplateUpdate,
        _get_active_rgpd_template,
    )
    from services.rgpd_minutas import (
        MINUTA_DEFAULT_TEMPLATE,
        MINUTA_TEMPLATE_VERSIONS_COLLECTION,
        MinutaTemplateUpdate,
        _get_active_minuta_template,
    )

    assert "RGPD" in RGPD_DEFAULT_TEMPLATE
    assert "{{NOME}}" in RGPD_DEFAULT_TEMPLATE
    assert RGPD_TEMPLATE_VERSIONS_COLLECTION == "rgpd_template_versions"
    assert callable(_get_active_rgpd_template)
    assert RGPDTemplateUpdate is not None

    assert "MINUTA" in MINUTA_DEFAULT_TEMPLATE.upper() or "exclusiv" in MINUTA_DEFAULT_TEMPLATE.lower()
    assert "{{CONTRIBUINTE}}" in MINUTA_DEFAULT_TEMPLATE
    assert MINUTA_TEMPLATE_VERSIONS_COLLECTION == "minuta_template_versions"
    assert callable(_get_active_minuta_template)
    assert MinutaTemplateUpdate is not None


def test_rgpd_modules_export_run_entrypoints():
    from services import (
        rgpd_helpers,
        rgpd_request,
        rgpd_public,
        rgpd_admin_list,
        rgpd_templates,
        rgpd_minutas,
    )

    assert callable(rgpd_helpers._add_process_activity)
    assert callable(rgpd_helpers._get_rgpd_or_404)
    assert callable(rgpd_helpers._frontend_base_url_from_request)

    assert callable(rgpd_request.run_request_rgpd)
    assert callable(rgpd_request.run_resend_rgpd_email)

    assert callable(rgpd_public.run_validate_rgpd_token)
    assert callable(rgpd_public.run_sign_rgpd_form)
    assert callable(rgpd_public.run_get_rgpd_status)
    assert callable(rgpd_public.run_get_rgpd_form_data)
    assert callable(rgpd_public.run_list_rgpd_requests)

    assert callable(rgpd_admin_list.run_list_all_rgpd)
    assert callable(rgpd_admin_list.run_get_rgpd_by_id)
    assert callable(rgpd_admin_list.run_update_rgpd_data)
    assert callable(rgpd_admin_list.run_delete_rgpd)
    assert callable(rgpd_admin_list.run_get_rgpd_stats)

    assert callable(rgpd_templates._get_active_rgpd_template)
    assert callable(rgpd_templates.run_get_rgpd_template)
    assert callable(rgpd_templates.run_update_rgpd_template)
    assert callable(rgpd_templates.run_list_rgpd_template_versions)
    assert callable(rgpd_templates.run_get_rgpd_template_version)

    assert callable(rgpd_minutas._get_active_minuta_template)
    assert callable(rgpd_minutas.run_get_minuta_template)
    assert callable(rgpd_minutas.run_update_minuta_template)
    assert callable(rgpd_minutas.run_list_minuta_template_versions)
    assert callable(rgpd_minutas.run_get_minuta_template_version)


def test_rgpd_router_is_thin_stubs_only():
    from pathlib import Path

    routes_path = Path(__file__).resolve().parents[2] / "routes" / "rgpd.py"
    text = routes_path.read_text()
    assert text.count("return await run_") >= 18
    assert len(text.splitlines()) < 280


def test_rgpd_service_not_overwritten():
    """Ensure thinning did not collide with existing rgpd_service / gdpr."""
    from services import rgpd_service, gdpr

    assert callable(rgpd_service.create_rgpd_request)
    assert callable(rgpd_service.validate_token)
    assert callable(rgpd_service.sign_rgpd)
    assert callable(rgpd_service.send_rgpd_email)
    assert callable(rgpd_service.get_tipo_documento_label)
    assert rgpd_service.RGPD_REQUESTS_COLLECTION == "rgpd_requests"
    assert gdpr is not None
    assert hasattr(gdpr, "__file__")


def test_rgpd_routes_reexport_active_template_helpers():
    """Back-compat: routes.rgpd still exposes helpers used by older imports."""
    from routes.rgpd import (
        _get_active_rgpd_template,
        _get_active_minuta_template,
        RGPD_DEFAULT_TEMPLATE,
        MINUTA_DEFAULT_TEMPLATE,
    )

    assert callable(_get_active_rgpd_template)
    assert callable(_get_active_minuta_template)
    assert isinstance(RGPD_DEFAULT_TEMPLATE, str)
    assert isinstance(MINUTA_DEFAULT_TEMPLATE, str)


def test_rgpd_no_preexisting_collision_file_set():
    """Thinning used rgpd_* names that do not overwrite rgpd_service.py."""
    from pathlib import Path

    services_dir = Path(__file__).resolve().parents[2] / "services"
    rgpd_files = sorted(p.name for p in services_dir.glob("rgpd_*.py"))
    assert "rgpd_service.py" in rgpd_files
    for name in (
        "rgpd_helpers.py",
        "rgpd_request.py",
        "rgpd_public.py",
        "rgpd_admin_list.py",
        "rgpd_templates.py",
        "rgpd_minutas.py",
    ):
        assert name in rgpd_files


def test_frontend_base_url_from_request():
    from types import SimpleNamespace
    from services.rgpd_helpers import _frontend_base_url_from_request

    req = SimpleNamespace(headers={"referer": "https://app.example.com/path"})
    assert _frontend_base_url_from_request(req) == "https://app.example.com"

    req2 = SimpleNamespace(headers={"origin": "http://localhost:3000"})
    assert _frontend_base_url_from_request(req2) == "http://localhost:3000"

    req3 = SimpleNamespace(headers={})
    assert _frontend_base_url_from_request(req3) is None

"""Unit tests for form_config route thinning helpers."""


def test_form_config_defaults_export():
    from services.form_config_defaults import DEFAULT_FORM_CONFIG, DEFAULT_STEP_CONFIG

    assert isinstance(DEFAULT_FORM_CONFIG, list)
    assert len(DEFAULT_FORM_CONFIG) > 10
    assert "2" in DEFAULT_STEP_CONFIG
    assert DEFAULT_STEP_CONFIG["2"]["depends_on"]["field"] == "compra_tipo"


def test_form_config_modules_export_run_entrypoints():
    from services import form_config_fields, form_config_templates

    assert callable(form_config_fields.run_get_form_config)
    assert callable(form_config_fields.run_update_form_config)
    assert callable(form_config_fields.run_create_custom_field)
    assert callable(form_config_fields.run_delete_custom_field)
    assert callable(form_config_fields.run_reset_form_config)

    assert callable(form_config_templates.run_list_templates)
    assert callable(form_config_templates.run_preview_template)
    assert callable(form_config_templates.run_save_as_template)
    assert callable(form_config_templates.run_activate_template)
    assert callable(form_config_templates.run_duplicate_template)
    assert callable(form_config_templates.run_delete_template)


def test_form_config_system_templates():
    from services.form_config_templates import SYSTEM_TEMPLATES

    names = {t["name"] for t in SYSTEM_TEMPLATES}
    assert names == {"Crédito Habitação", "Refinanciamento", "Crédito Pessoal"}


def test_form_config_router_is_thin_stubs_only():
    from pathlib import Path

    routes_path = Path(__file__).resolve().parents[2] / "routes" / "form_config.py"
    text = routes_path.read_text()
    assert text.count("return await run_") >= 11
    assert len(text.splitlines()) < 150


def test_form_config_no_collision():
    from pathlib import Path

    services_dir = Path(__file__).resolve().parents[2] / "services"
    form_files = sorted(p.name for p in services_dir.glob("form_config_*.py"))
    assert form_files == [
        "form_config_defaults.py",
        "form_config_fields.py",
        "form_config_templates.py",
    ]


def test_form_config_defaults_reexported_from_route():
    from routes.form_config import DEFAULT_FORM_CONFIG, DEFAULT_STEP_CONFIG
    from services.form_config_defaults import (
        DEFAULT_FORM_CONFIG as D2,
        DEFAULT_STEP_CONFIG as S2,
    )

    assert DEFAULT_FORM_CONFIG is D2
    assert DEFAULT_STEP_CONFIG is S2

"""Unit tests for system_config route thinning helpers."""


def test_mask_sensitive_masks_nested_secrets():
    from services.system_config_api import mask_sensitive

    payload = {
        "email": {"smtp_password": "secret123", "smtp_user": "a@b.com"},
        "ai": {"api_key": "sk-test", "model": "gpt-4o-mini"},
        "settings": {"company_name": "Acme"},
    }
    masked = mask_sensitive(payload)
    assert masked["email"]["smtp_password"] == "••••••••"
    assert masked["email"]["smtp_user"] == "a@b.com"
    assert masked["ai"]["api_key"] == "••••••••"
    assert masked["ai"]["model"] == "gpt-4o-mini"
    assert masked["settings"]["company_name"] == "Acme"


def test_mask_sensitive_skips_empty_values():
    from services.system_config_api import mask_sensitive

    payload = {"email": {"smtp_password": "", "smtp_password_2": None}}
    masked = mask_sensitive(payload)
    assert masked["email"]["smtp_password"] == ""
    assert masked["email"]["smtp_password_2"] is None


def test_mask_system_email_config():
    from services.system_config_system_emails import _mask_system_email_config

    doc = {
        "purpose": "DOCUMENTS",
        "host": "mail.example.com",
        "encrypted_password": "cipher",
        "_has_password": True,
    }
    out = _mask_system_email_config(doc)
    assert "encrypted_password" not in out
    assert out["has_password"] is True
    assert out["purpose"] == "DOCUMENTS"


def test_system_config_modules_export_run_entrypoints():
    from services import (
        system_config,
        system_config_api,
        system_config_connections,
        system_config_admin_ops,
        system_config_system_emails,
    )

    # Existing core module must remain (load/save/cache)
    assert callable(system_config.get_system_config)
    assert callable(system_config.update_config_section)
    assert callable(system_config.invalidate_config_cache)
    assert callable(system_config.list_available_companies)

    assert callable(system_config_api.mask_sensitive)
    assert callable(system_config_api.run_get_config)
    assert callable(system_config_api.run_get_excel_export_permission)
    assert callable(system_config_api.run_get_config_fields)
    assert callable(system_config_api.run_get_available_companies)
    assert callable(system_config_api.run_update_config)
    assert "storage" in system_config_api.CONFIG_FIELDS
    assert "resend_api_key" in system_config_api.SENSITIVE_FIELDS

    assert callable(system_config_connections.run_test_service_connection)

    assert callable(system_config_admin_ops.run_complete_setup)
    assert callable(system_config_admin_ops.run_get_storage_info)
    assert callable(system_config_admin_ops.run_reset_cache)
    assert callable(system_config_admin_ops.run_reveal_secrets)

    assert callable(system_config_system_emails.run_list_system_email_configs)
    assert callable(system_config_system_emails.run_get_system_email_config)
    assert callable(system_config_system_emails.run_create_system_email_config)
    assert callable(system_config_system_emails.run_update_system_email_config)
    assert callable(system_config_system_emails.run_delete_system_email_config)
    assert callable(system_config_system_emails.run_test_system_email_config)
    assert hasattr(system_config_system_emails, "SystemEmailConfigCreate")
    assert hasattr(system_config_system_emails, "SystemEmailConfigUpdate")
    assert "DOCUMENTS" in system_config_system_emails.VALID_SYSTEM_EMAIL_PURPOSES


def test_system_config_router_is_thin_stubs_only():
    from pathlib import Path

    routes_path = Path(__file__).resolve().parents[2] / "routes" / "system_config.py"
    text = routes_path.read_text()
    assert text.count("return await run_") >= 15
    assert len(text.splitlines()) < 280
    # Core module must still exist; thinning must not overwrite it
    core = Path(__file__).resolve().parents[2] / "services" / "system_config.py"
    assert core.exists()
    assert "get_system_config" in core.read_text()


def test_system_config_thinning_no_name_collision():
    """Thinning uses system_config_* suffixes; core system_config.py untouched."""
    from pathlib import Path

    services_dir = Path(__file__).resolve().parents[2] / "services"
    syscfg_files = sorted(p.name for p in services_dir.glob("system_config*.py"))
    assert "system_config.py" in syscfg_files
    assert "system_config_api.py" in syscfg_files
    assert "system_config_connections.py" in syscfg_files
    assert "system_config_admin_ops.py" in syscfg_files
    assert "system_config_system_emails.py" in syscfg_files


def test_auto_backup_enabled_is_settings_boolean_field():
    from services.system_config_api import CONFIG_FIELDS

    settings = CONFIG_FIELDS["settings"]
    keys = [field.key for field in settings["fields"]]
    assert "auto_backup_enabled" in keys
    field = next(f for f in settings["fields"] if f.key == "auto_backup_enabled")
    assert field.type == "boolean"

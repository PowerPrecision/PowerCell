"""Unit tests for email route thinning helpers (template vars + labels)."""
from services.email_template_vars import (
    _extract_email_variables,
    _build_professional_email_html,
)
from services.email_labels_folders import validate_hex_color


def test_validate_hex_color():
    assert validate_hex_color("#ef4444") is True
    assert validate_hex_color("#fff") is True
    assert validate_hex_color("ef4444") is False
    assert validate_hex_color("#gg0000") is False
    assert validate_hex_color("") is False


def test_extract_email_variables_basic(monkeypatch):
    # Avoid depending on encryption internals
    monkeypatch.setattr(
        "services.email_template_vars.decrypt_sensitive_data",
        lambda process: process,
    )
    process = {
        "client_name": "Ana Silva",
        "client_email": "ana@example.com",
        "process_number": "P-1",
        "personal_data": {
            "nome_completo": "Ana Silva",
            "nif": "123456789",
            "estado_civil": "casado_adquiridos",
            "tipo_contrato": "efetivo",
            "salario_liquido": 1500,
        },
        "financial_data": {
            "valor_imovel": 250000,
            "requested_amount": 200000,
            "prazo_anos": 30,
        },
        "credit_data": {},
        "titular2_data": {},
        "real_estate_data": {"localidade": "Lisboa"},
    }
    user = {"name": "Consultor", "email": "c@x.com", "phone": "91"}
    vars_ = _extract_email_variables(process, user, "CC\nIRS")
    assert vars_["client_name"] == "Ana Silva"
    assert vars_["p1_nif"] == "123456789"
    assert vars_["p1_estado_civil"] == "Casado"
    assert vars_["p1_regime_casamento"] == "Comunhão de Adquiridos"
    assert vars_["p1_vinculo"] == "Contrato Efetivo"
    assert "1500" in vars_["p1_salario"] or "1.500" in vars_["p1_salario"]
    assert vars_["VALOR_IMOVEL"] != "N/A"
    assert vars_["VALOR_FINANCIAMENTO"] != "N/A"
    assert vars_["PRAZO_FINANCIAMENTO"] == "30 anos"
    assert vars_["COMPRA_SOZINHO"] == "Sim"
    assert vars_["sender_name"] == "Consultor"
    assert vars_["documents_list"] == "CC\nIRS"


def test_build_professional_email_html_contains_proponent():
    process = {
        "client_name": "Ana Silva",
        "personal_data": {"nome_completo": "Ana Silva", "nif": "123"},
        "titular2_data": {},
        "financial_data": {},
        "real_estate_data": {},
    }
    user = {"name": "João", "email": "j@x.com", "phone": "90"}
    html = _build_professional_email_html(process, user, "doc.pdf")
    assert "Ana Silva" in html
    assert "1º Proponente" in html
    assert "PrecisionCrédito" in html
    assert "João" in html


def test_documentation_bracket_placeholder_normalization():
    """Bank templates use [VAR]; documentation service normalizes to {VAR}."""
    import re

    template = "Imóvel [VALOR_IMOVEL] / prazo [PRAZO_FINANCIAMENTO] / {p1_nome}"
    normalized = re.sub(r"\[([A-Z_]+)\]", r"{\1}", template)
    assert normalized == "Imóvel {VALOR_IMOVEL} / prazo {PRAZO_FINANCIAMENTO} / {p1_nome}"


def test_email_documentation_module_exports():
    from services import email_documentation as mod

    for name in (
        "run_get_document_recipients",
        "run_preview_email_template",
        "run_preview_documentation_email",
        "run_send_documentation_email",
    ):
        assert callable(getattr(mod, name))


def test_email_mailbox_ops_module_exports():
    from services import email_mailbox_ops as mod

    for name in (
        "run_upload_attachments",
        "run_download_email_attachment",
        "run_mark_email",
        "run_unmark_email",
        "run_add_email_label",
        "run_remove_email_label",
        "run_get_email_attachments",
        "run_download_attachment",
        "run_preview_attachment",
        "run_download_webmail_attachment",
    ):
        assert callable(getattr(mod, name))


def test_email_remaining_modules_export_run_entrypoints():
    from services import email_templates_drafts as td
    from services import email_webmail as wm
    from services import email_process_crud as pc

    for name in (
        "run_get_email_templates",
        "run_list_auto_drafts",
        "run_get_unread_notifications",
    ):
        assert callable(getattr(td, name))
    for name in (
        "run_webmail_list",
        "run_webmail_stats",
        "run_webmail_sync",
        "run_get_configured_accounts",
        "build_ucr_mailbox_filter",
        "resolve_ucr_mailbox_filter",
    ):
        assert callable(getattr(wm, name))
    for name in (
        "run_send_email",
        "run_get_process_emails",
        "run_advanced_email_search",
        "run_create_email_record",
    ):
        assert callable(getattr(pc, name))
    assert isinstance(pc._sync_status, dict)


def test_emails_router_is_thin_stubs_only():
    """Route module should stay small; logic lives in services."""
    from pathlib import Path

    routes_path = Path(__file__).resolve().parents[2] / "routes" / "emails.py"
    text = routes_path.read_text()
    assert text.count("return await run_") >= 40
    # No fat IMAP/webmail bodies left in the route file
    assert "ISOLAMENTO DE DADOS (Segurança)" not in text
    assert len(text.splitlines()) < 800


def test_webmail_attachment_router_is_thin_stub():
    from pathlib import Path
    from routes.webmail import router

    routes_path = Path(__file__).resolve().parents[2] / "routes" / "webmail.py"
    text = routes_path.read_text()
    assert "/attachments/{attachment_id}" in text
    assert "return await run_download_webmail_attachment" in text
    assert len(text.splitlines()) < 80
    paths = [getattr(r, "path", "") for r in router.routes]
    assert any("attachments" in p for p in paths)

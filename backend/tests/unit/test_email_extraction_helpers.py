"""Unit tests for email route thinning helpers (template vars + labels)."""
import pytest
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
        "rewrite_box_for_caixa_geral",
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


def test_process_participant_email_helpers_include_cc():
    from services.email_process_crud import (
        normalize_participant_email,
        collect_emails_from_process_doc,
        collect_emails_from_client_doc,
        build_participant_address_match,
        build_process_emails_base_conditions,
    )

    assert normalize_participant_email("Ana Silva <ana@cliente.pt>") == "ana@cliente.pt"
    assert normalize_participant_email({"email": "B@X.PT"}) == "b@x.pt"

    process_doc = {
        "client_email": "ana@cliente.pt",
        "monitored_emails": ["extra@cliente.pt"],
        "titular2_data": {"email": "joao@cliente.pt"},
    }
    emails = collect_emails_from_process_doc(process_doc)
    assert emails == {"ana@cliente.pt", "extra@cliente.pt", "joao@cliente.pt"}

    client_doc = {"contacto": {"email": "ana@cliente.pt"}, "titular2_data": {"email": "t2@x.pt"}}
    assert "t2@x.pt" in collect_emails_from_client_doc(client_doc)

    match = build_participant_address_match({"ana@cliente.pt"})
    blob = str(match)
    assert "cc_emails" in blob
    assert "to_emails" in blob
    assert "from_email" in blob
    assert "(^|<)" in blob

    conditions = build_process_emails_base_conditions("proc-1", {"ana@cliente.pt"})
    assert {"process_id": "proc-1"} in conditions
    assert any("cc_emails" in str(c) for c in conditions)


def test_coerce_email_response_fields_fills_required():
    from services.email_process_crud import coerce_email_response_fields

    coerced = coerce_email_response_fields({
        "id": "e1",
        "from_email": "ana@cliente.pt",
        "subject": "Olá",
    })
    assert coerced["status"] in ("sent", "synced")
    assert coerced["created_at"]
    assert coerced["direction"] == "received"
    assert coerced["to_emails"] == []
    assert coerced["body"] == ""


def test_send_documentation_wrapper_hides_stack_trace():
    import asyncio
    from unittest.mock import AsyncMock, patch

    from fastapi import HTTPException
    from services.email_documentation import run_send_documentation_email

    async def _run():
        with patch(
            "services.email_documentation._send_documentation_email_impl",
            new_callable=AsyncMock,
            side_effect=RuntimeError("incorrect authentication data\nTraceback..."),
        ):
            try:
                await run_send_documentation_email("p1", {}, {"id": "u1", "email": "a@b.pt"})
                assert False, "expected HTTPException"
            except HTTPException as exc:
                assert exc.status_code == 500
                assert "Traceback" not in str(exc.detail)
                assert "incorrect authentication" not in str(exc.detail).lower()

    asyncio.run(_run())


def test_webmail_search_escapes_regex():
    """Pacote FF — pesquisa textual do webmail usa escape_regex."""
    from pathlib import Path

    src = (
        Path(__file__).resolve().parents[2]
        / "services"
        / "email_webmail.py"
    ).read_text()
    assert "from utils.input_sanitization import escape_regex, sanitize_string" in src
    assert "escape_regex(sanitize_string(search, max_length=200))" in src
    # User input must not be interpolated raw into $regex after sanitise-only.
    search_block = src.split("# === PESQUISA TEXTUAL ===", 1)[1].split(
        "# Montar query final", 1
    )[0]
    assert '{"$regex": search, "$options": "i"}' in search_block
    assert "escape_regex" in search_block


def test_send_email_accepts_account_override_signature():
    import inspect
    from services.email_service import send_email

    params = inspect.signature(send_email).parameters
    assert "account_override" in params


def test_facet_count_reads_empty_and_present():
    from services.email_webmail import _facet_count

    assert _facet_count({"unread": [{"n": 4}]}, "unread") == 4
    assert _facet_count({"unread": []}, "unread") == 0
    assert _facet_count({}, "unread") == 0
    assert _facet_count(None, "unread") == 0


def test_webmail_stats_uses_single_facet_not_sequential_counts():
    from pathlib import Path

    src = (
        Path(__file__).resolve().parents[2] / "services" / "email_webmail.py"
    ).read_text()
    start = src.index("async def run_webmail_stats")
    end = src.index("async def run_webmail_sync")
    stats = src[start:end]
    assert '"$facet"' in stats
    assert "count_documents(" not in stats


@pytest.mark.asyncio
async def test_enrich_emails_batches_with_in_instead_of_find_one():
    from unittest.mock import MagicMock, patch

    from services import email_enrich as mod

    class _Cursor:
        def __init__(self, docs):
            self._docs = docs

        async def to_list(self, n):
            return self._docs

    emails = [
        {"id": "e1", "process_id": "p1", "created_by": "u1"},
        {"id": "e2", "process_id": "p1", "created_by": "u2"},
        {"id": "e3", "process_id": "p2"},
    ]
    mock_db = MagicMock()
    mock_db.processes.find = MagicMock(return_value=_Cursor([
        {"id": "p1", "client_name": "Ana"},
        {"id": "p2", "client_name": "Bruno"},
    ]))
    mock_db.users.find = MagicMock(return_value=_Cursor([
        {"id": "u1", "name": "Consultor"},
        {"id": "u2", "name": "Mediador"},
    ]))

    with patch.object(mod, "db", mock_db):
        result = await mod.enrich_emails(emails)

    process_filter = mock_db.processes.find.call_args[0][0]
    user_filter = mock_db.users.find.call_args[0][0]
    assert set(process_filter["id"]["$in"]) == {"p1", "p2"}
    assert set(user_filter["id"]["$in"]) == {"u1", "u2"}
    assert mock_db.processes.find.call_count == 1
    assert mock_db.users.find.call_count == 1
    assert mock_db.processes.find_one.call_count == 0
    assert mock_db.users.find_one.call_count == 0
    assert result[0]["client_name"] == "Ana"
    assert result[0]["created_by_name"] == "Consultor"
    assert result[1]["created_by_name"] == "Mediador"
    assert result[2]["client_name"] == "Bruno"


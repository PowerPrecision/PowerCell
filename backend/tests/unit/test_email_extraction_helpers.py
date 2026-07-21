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

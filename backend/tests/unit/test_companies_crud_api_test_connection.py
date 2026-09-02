"""Unit tests for services/companies_crud_api_test_connection.py.

Testa o serviço ad-hoc de validação de ligação SMTP/IMAP do formulário
de configuração de email de Empresas (sem gravar nada, sem tocar em rede
real — os testes com sucesso simulado usam monkeypatch).
"""
import pytest
from fastapi import HTTPException

from models.company import CompanyEmailConnectionTest
from services.companies_crud_api_test_connection import (
    _friendly_error,
    run_test_email_connection,
)


async def test_no_fields_provided_raises_400():
    data = CompanyEmailConnectionTest()
    with pytest.raises(HTTPException) as exc_info:
        await run_test_email_connection(data)
    assert exc_info.value.status_code == 400
    assert "Preencha" in exc_info.value.detail


async def test_smtp_unreachable_host_raises_400_with_friendly_message():
    data = CompanyEmailConnectionTest(
        smtp_host="smtp.invalid-domain-does-not-exist-xyz.test",
        smtp_port=465,
        smtp_email="a@b.pt",
        smtp_password="x",
    )
    with pytest.raises(HTTPException) as exc_info:
        await run_test_email_connection(data)
    assert exc_info.value.status_code == 400
    assert "SMTP" in exc_info.value.detail


async def test_smtp_success_path(monkeypatch):
    import services.companies_crud_api_test_connection as module

    monkeypatch.setattr(module, "_test_smtp_sync", lambda host, port, email, password: None)
    data = CompanyEmailConnectionTest(
        smtp_host="smtp.empresa.pt", smtp_port=465, smtp_email="a@b.pt", smtp_password="x",
    )
    result = await run_test_email_connection(data)
    assert result["success"] is True
    assert result["results"]["smtp"]["success"] is True


async def test_imap_success_path(monkeypatch):
    import services.companies_crud_api_test_connection as module

    monkeypatch.setattr(module, "_test_imap_sync", lambda host, port, email, password: None)
    data = CompanyEmailConnectionTest(
        imap_host="imap.empresa.pt", imap_port=993, imap_email="a@b.pt", imap_password="x",
    )
    result = await run_test_email_connection(data)
    assert result["success"] is True
    assert result["results"]["imap"]["success"] is True


async def test_smtp_and_imap_tested_independently(monkeypatch):
    """SMTP falha, IMAP sucede — ambos devem ser reportados e o resultado geral deve falhar (400)."""
    import services.companies_crud_api_test_connection as module

    def fail_smtp(host, port, email, password):
        raise Exception("535 authentication failed")

    monkeypatch.setattr(module, "_test_smtp_sync", fail_smtp)
    monkeypatch.setattr(module, "_test_imap_sync", lambda host, port, email, password: None)

    data = CompanyEmailConnectionTest(
        smtp_host="smtp.empresa.pt", smtp_port=465, smtp_email="a@b.pt", smtp_password="wrong",
        imap_host="imap.empresa.pt", imap_port=993, imap_email="a@b.pt", imap_password="x",
    )
    with pytest.raises(HTTPException) as exc_info:
        await run_test_email_connection(data)
    assert exc_info.value.status_code == 400
    assert "SMTP" in exc_info.value.detail


@pytest.mark.parametrize(
    "raw_err,expected_fragment",
    [
        ("(535, b'5.7.8 Username and Password not accepted')", "credenciais inválidas"),
        ("AUTHENTICATIONFAILED", "credenciais inválidas"),
        ("[Errno 111] Connection refused", "ligação recusada"),
        ("timed out", "tempo de ligação esgotado"),
        ("certificate verify failed", "certificado SSL/TLS"),
        ("Name or service not known", "servidor não encontrado"),
    ],
)
def test_friendly_error_mappings(raw_err, expected_fragment):
    msg = _friendly_error(raw_err, "SMTP")
    assert expected_fragment in msg

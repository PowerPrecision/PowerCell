"""Testes unitários — FIX (Set 2026): resolução de credenciais SMTP.

Valida a cadeia de resolução de `send_email` para emails transacionais do
sistema (`force_system=True`) e o mapeamento de erros no magic link:

  1. SystemConfig.system_smtp (Bloco A — onde /contas-email grava)  ← prioridade
  2. system_email_configs por purpose (get_system_transporter)      — fallback
  3. Contas globais de ambiente (POWER_EMAIL/PRECISION_EMAIL)       — legacy

E, quando NADA está configurado, `send_email` devolve
``error_code="SMTP_NOT_CONFIGURED"`` — que `portal_magic_link` mapeia para
HTTP 400 (erro tratado) em vez de HTTP 500.

Convenção tests/unit: SEM MongoDB vivo — a camada `db` é mockada com
`fake_async_db` (tests/unit/conftest.py); `resend` e `smtplib.SMTP_SSL`
são mockados para não haver I/O de rede.
"""
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import services.system_config as system_config_mod
from tests.unit.conftest import FakeAsyncDatabase

pytestmark = pytest.mark.asyncio


# ── Helpers ────────────────────────────────────────────────────────────────

def _bloco_a_resend_doc():
    """Doc 'main' do system_config com o Bloco A (Resend) configurado —
    exactamente o que o PATCH /api/system-config/system_smtp do cartão
    "Email do Sistema (Transacional)" (/contas-email) grava."""
    return {
        "_id": "main",
        "company_id": "default",
        "system_smtp": {
            "resend_api_key": "re_FAKE_KEY_123",
            "smtp_from_email": "no-reply@powerealestate.pt",
            "smtp_from_name": "Power Real Estate",
            "email_signature": "<p>Obrigado.</p>",
        },
    }


def _bloco_a_vazio_doc():
    return {"_id": "main", "company_id": "default", "system_smtp": {}}


def _notifications_doc(password="password-em-claro"):
    """Doc purpose NOTIFICATIONS (texto claro — decrypt_email_secret devolve
    tal qual quando o valor não tem o prefixo ENC:)."""
    return {
        "purpose": "NOTIFICATIONS",
        "is_active": True,
        "host": "smtp.exemplo.pt",
        "port": 465,
        "user": "sistema@exemplo.pt",
        "encrypted_password": password,
        "from_name": "Sistema",
        "from_email": "sistema@exemplo.pt",
    }


def _build_db(system_config_doc=None, system_email_configs=None):
    fake = FakeAsyncDatabase()
    if system_config_doc is not None:
        fake.system_config.docs.append(dict(system_config_doc))
    for doc in (system_email_configs or []):
        fake.system_email_configs.docs.append(dict(doc))
    return fake


@pytest.fixture(autouse=True)
def _limpar_cache_config():
    """O get_system_config cacheia (TTL 60s) — limpar antes/depois de cada teste."""
    system_config_mod._config_cache.clear()
    yield
    system_config_mod._config_cache.clear()


async def _send_como_magic_link(db_fake, fake_resend_module):
    """Chamada idêntica à de portal_magic_link.send_magic_link_to_client."""
    import services.email_service as email_service

    with patch.object(email_service, "db", db_fake), \
         patch.object(system_config_mod, "db", db_fake), \
         patch("database.db", db_fake), \
         patch.dict(sys.modules, {"resend": fake_resend_module}), \
         patch.object(email_service, "get_email_accounts", return_value=[]):
        return await email_service.send_email(
            account_name="power",
            to_emails=["cliente@exemplo.pt"],
            subject="Portal do Cliente — Teste",
            body="corpo",
            body_html="<p>corpo</p>",
            force_system=True,
            system_purpose="NOTIFICATIONS",
        )


# ── Fix 1: Bloco A (onde a UI grava) tem prioridade ────────────────────────

async def test_bloco_a_prioritario_sobre_purpose():
    """Bloco A configurado + purpose NOTIFICATIONS válido → envia via Bloco A
    (Resend), NÃO via SMTP do purpose. Antes do fix, o purpose (outra UI)
    ganhava — o admin configurava num local e o sistema lia de outro."""
    fake_resend = MagicMock()
    fake_resend.Emails.send.side_effect = lambda params: {"id": "email-id"}

    result = await _send_como_magic_link(
        _build_db(
            system_config_doc=_bloco_a_resend_doc(),
            system_email_configs=[_notifications_doc()],
        ),
        fake_resend,
    )

    assert result.get("success") is True
    assert result.get("account") == "system_smtp"
    assert fake_resend.Emails.send.call_count == 1
    sent_params = fake_resend.Emails.send.call_args[0][0]
    assert sent_params["from"] == "Power Real Estate <no-reply@powerealestate.pt>"


async def test_bloco_a_resend_quando_configurado():
    """Bloco A configurado (sozinho) → Resend com o from do Bloco A."""
    fake_resend = MagicMock()
    fake_resend.Emails.send.side_effect = lambda params: {"id": "email-id"}

    result = await _send_como_magic_link(
        _build_db(system_config_doc=_bloco_a_resend_doc()), fake_resend
    )

    assert result.get("success") is True
    assert result.get("account") == "system_smtp"
    assert fake_resend.Emails.send.call_count == 1


async def test_bloco_a_smtp_legado():
    """Bloco A em modo SMTP legado (smtp_host+username, sem resend_api_key)
    → account system_smtp com o host do Bloco A (captura sem rede via mock
    de smtplib.SMTP_SSL)."""
    import services.email_service as email_service

    doc = {
        "_id": "main",
        "company_id": "default",
        "system_smtp": {
            "smtp_host": "smtp.powerealestate.pt",
            "smtp_port": 465,
            "smtp_username": "conta@powerealestate.pt",
            "smtp_password": "pwd-claro",
            "smtp_from_email": "no-reply@powerealestate.pt",
            "smtp_from_name": "Power Real Estate",
        },
    }
    fake_resend = MagicMock()
    smtp_ssl = MagicMock()
    # sendmail levanta para não percorrer o caminho de persistência (emails)
    smtp_ssl.return_value.__enter__.return_value.sendmail.side_effect = RuntimeError(
        "stop-apos-login"
    )

    db_fake = _build_db(system_config_doc=doc)
    with patch.object(email_service, "db", db_fake), \
         patch.object(system_config_mod, "db", db_fake), \
         patch("database.db", db_fake), \
         patch.dict(sys.modules, {"resend": fake_resend}), \
         patch.object(email_service, "get_email_accounts", return_value=[]), \
         patch.object(email_service.smtplib, "SMTP_SSL", smtp_ssl):
        result = await email_service.send_email(
            account_name="power",
            to_emails=["cliente@exemplo.pt"],
            subject="x",
            body="x",
            force_system=True,
            system_purpose="NOTIFICATIONS",
        )

    # O SMTP_SSL recebeu o host do Bloco A — prova que o Bloco A foi usado.
    smtp_ssl.assert_called_once()
    args, kwargs = smtp_ssl.call_args
    assert args[0] == "smtp.powerealestate.pt"
    assert result.get("success") is False  # sendmail mockado falhou — sem rede


async def test_purpose_fallback_quando_bloco_a_vazio():
    """Sem Bloco A + purpose NOTIFICATIONS válido → fallback para o SMTP do
    purpose (zero downtime preservado)."""
    import services.email_service as email_service

    fake_resend = MagicMock()
    smtp_ssl = MagicMock()
    smtp_ssl.return_value.__enter__.return_value.sendmail.side_effect = RuntimeError(
        "stop-apos-login"
    )

    db_fake = _build_db(
        system_config_doc=_bloco_a_vazio_doc(),
        system_email_configs=[_notifications_doc()],
    )
    with patch.object(email_service, "db", db_fake), \
         patch.object(system_config_mod, "db", db_fake), \
         patch("database.db", db_fake), \
         patch.dict(sys.modules, {"resend": fake_resend}), \
         patch.object(email_service, "get_email_accounts", return_value=[]), \
         patch.object(email_service.smtplib, "SMTP_SSL", smtp_ssl):
        result = await email_service.send_email(
            account_name="power",
            to_emails=["cliente@exemplo.pt"],
            subject="x",
            body="x",
            force_system=True,
            system_purpose="NOTIFICATIONS",
        )

    smtp_ssl.assert_called_once()
    args, _ = smtp_ssl.call_args
    assert args[0] == "smtp.exemplo.pt"  # host do purpose, não do Bloco A
    assert fake_resend.Emails.send.call_count == 0


# ── Fix 2: erro estruturado SMTP_NOT_CONFIGURED + 400 no magic link ───────

async def test_sem_config_devolve_error_code():
    """Nada configurado (Bloco A vazio, sem purpose, sem contas de ambiente)
    → success=False com error_code=SMTP_NOT_CONFIGURED (não exceção, não
    sucesso falso)."""
    fake_resend = MagicMock()

    result = await _send_como_magic_link(
        _build_db(system_config_doc=_bloco_a_vazio_doc()), fake_resend
    )

    assert result.get("success") is False
    assert result.get("error_code") == "SMTP_NOT_CONFIGURED"
    assert "não está configurado" in result.get("error", "").lower()
    assert fake_resend.Emails.send.call_count == 0


async def test_magic_link_400_quando_smtp_nao_configurado():
    """portal_magic_link mapeia SMTP_NOT_CONFIGURED → HTTP 400 com detalhe
    'SMTP não está configurado' (antes: 500 Internal Server Error)."""
    from fastapi import HTTPException

    import services.email_service as email_service
    import services.portal_magic_link as portal_magic_link

    async def _send_email_falha_config(**kwargs):
        return {
            "success": False,
            "error": "SMTP não está configurado. Configure o Email do Sistema...",
            "error_code": "SMTP_NOT_CONFIGURED",
        }

    process = {"client_email": "cliente@exemplo.pt", "client_name": "Cliente", "client_id": "cli-1"}
    request = MagicMock()

    with patch.object(email_service, "send_email", _send_email_falha_config), \
         patch.object(portal_magic_link, "ensure_portal_access_code",
                      new=AsyncMock(return_value="CODE")), \
         patch.object(portal_magic_link, "issue_portal_magic_link",
                      new=AsyncMock(return_value={"magic_link": "https://x/portal/ABC12345", "short_id": "ABC12345"})), \
         patch.object(portal_magic_link, "build_magic_link_email_bodies",
                      return_value=("texto", "<p>html</p>")):
        with pytest.raises(HTTPException) as exc_info:
            await portal_magic_link.send_magic_link_to_client(
                process_id="proc-1", process=process, user={"email": "admin@x.pt"},
                request=request,
            )

    assert exc_info.value.status_code == 400
    assert "SMTP não está configurado" in exc_info.value.detail


async def test_magic_link_500_quando_erro_de_envio():
    """Falha de envio real (credenciais/rede — sem error_code) continua a ser
    500 com a razão real (comportamento Bug 3, Fev 2026, preservado)."""
    from fastapi import HTTPException

    import services.email_service as email_service
    import services.portal_magic_link as portal_magic_link

    async def _send_email_falha_envio(**kwargs):
        return {"success": False, "error": "Falha de autenticação SMTP."}

    process = {"client_email": "cliente@exemplo.pt", "client_name": "Cliente", "client_id": "cli-1"}
    request = MagicMock()

    with patch.object(email_service, "send_email", _send_email_falha_envio), \
         patch.object(portal_magic_link, "ensure_portal_access_code",
                      new=AsyncMock(return_value="CODE")), \
         patch.object(portal_magic_link, "issue_portal_magic_link",
                      new=AsyncMock(return_value={"magic_link": "https://x/portal/ABC12345", "short_id": "ABC12345"})), \
         patch.object(portal_magic_link, "build_magic_link_email_bodies",
                      return_value=("texto", "<p>html</p>")):
        with pytest.raises(HTTPException) as exc_info:
            await portal_magic_link.send_magic_link_to_client(
                process_id="proc-1", process=process, user={"email": "admin@x.pt"},
                request=request,
            )

    assert exc_info.value.status_code == 500
    assert "Falha de autenticação SMTP" in exc_info.value.detail


async def test_magic_link_400_em_value_error_de_config():
    """ValueError (ex: purpose inválido no transporter) → 400, não 500
    (excepção de configuração é erro do lado do cliente)."""
    from fastapi import HTTPException

    import services.email_service as email_service
    import services.portal_magic_link as portal_magic_link

    async def _send_email_value_error(**kwargs):
        raise ValueError("Purpose inválido: 'X'")

    process = {"client_email": "cliente@exemplo.pt", "client_name": "Cliente", "client_id": "cli-1"}
    request = MagicMock()

    with patch.object(email_service, "send_email", _send_email_value_error), \
         patch.object(portal_magic_link, "ensure_portal_access_code",
                      new=AsyncMock(return_value="CODE")), \
         patch.object(portal_magic_link, "issue_portal_magic_link",
                      new=AsyncMock(return_value={"magic_link": "https://x/portal/ABC12345", "short_id": "ABC12345"})), \
         patch.object(portal_magic_link, "build_magic_link_email_bodies",
                      return_value=("texto", "<p>html</p>")):
        with pytest.raises(HTTPException) as exc_info:
            await portal_magic_link.send_magic_link_to_client(
                process_id="proc-1", process=process, user={"email": "admin@x.pt"},
                request=request,
            )

    assert exc_info.value.status_code == 400
    assert "SMTP não está configurado" in exc_info.value.detail

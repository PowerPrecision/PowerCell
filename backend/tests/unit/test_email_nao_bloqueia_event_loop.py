"""O envio de email não pode congelar o event loop do worker.

INCIDENTE (CI, 2026-09-21): três testes do registo público falharam com
`RuntimeError: No response returned.` ao fim de exactamente 30000ms. A causa
não estava no registo: `send_email` chamava `smtplib.SMTP_SSL(...)` — código
SÍNCRONO — directamente de uma corotina. Enquanto o SMTP esperava pelo
servidor (30s de timeout), o event loop ficava parado: nenhum outro pedido
era servido e a própria resposta do pedido em curso não chegava a sair.

Com um servidor de email externo a responder depressa ninguém dá por isso;
com um servidor inacessível, o worker inteiro congela. Estes testes fixam
que o transporte bloqueante corre FORA do event loop.
"""
import asyncio
import time
from unittest.mock import AsyncMock, patch

import pytest

from services import email_service
from tests.unit.conftest import FakeAsyncDatabase

BLOQUEIO = 0.6          # "servidor de email lento" (em produção seriam 30s)
TOLERANCIA_LOOP = 0.25  # o loop tem de continuar a correr durante o envio


def _conta():
    return email_service.EmailAccount(
        name="power",
        imap_server="mail.exemplo.pt",
        imap_port=993,
        smtp_server="mail.exemplo.pt",
        smtp_port=465,
        email="geral@exemplo.pt",
        password="segredo",
    )


class _SMTPLento:
    """SMTP que demora a ligar — como um servidor inacessível."""

    ligacoes = 0

    def __init__(self, *a, **kw):
        type(self).ligacoes += 1
        time.sleep(BLOQUEIO)          # bloqueante, tal como o smtplib real

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def login(self, *a, **kw):
        pass

    def sendmail(self, *a, **kw):
        pass


@pytest.fixture
def ambiente():
    _SMTPLento.ligacoes = 0
    db = FakeAsyncDatabase()
    alvos = [
        patch("database.db", db),
        patch.object(email_service, "db", db),
        patch.object(email_service.smtplib, "SMTP_SSL", _SMTPLento),
        patch("services.email_config_resolver.decrypt_email_secret", lambda v, _c="": "segredo"),
        patch.object(
            email_service, "get_email_accounts_async", AsyncMock(return_value=[_conta()])
        ),
    ]
    for a in alvos:
        a.start()
    yield db
    for a in reversed(alvos):
        a.stop()


async def _enviar():
    return await email_service.send_email(
        account_name="power",
        to_emails=["cliente@exemplo.pt"],
        subject="Assunto",
        body="Corpo",
        process_id=None,
    )


class TestTransporteForaDoEventLoop:
    async def test_o_loop_continua_a_correr_durante_o_envio(self, ambiente):
        """Prova directa: outra corotina avança enquanto o SMTP espera.

        Se o `smtplib` voltar a correr no event loop, o contador fica
        congelado e este teste fica vermelho.
        """
        batidas = 0

        async def _relogio():
            nonlocal batidas
            while True:
                await asyncio.sleep(0.02)
                batidas += 1

        tictac = asyncio.create_task(_relogio())
        try:
            await _enviar()
        finally:
            tictac.cancel()

        assert _SMTPLento.ligacoes == 1, "o SMTP nem chegou a ser usado"
        assert batidas >= TOLERANCIA_LOOP / 0.02 * 0.5, (
            f"o event loop esteve parado durante o envio (só {batidas} batidas) — "
            "o transporte SMTP voltou a correr dentro do loop"
        )

    async def test_dois_envios_em_paralelo_nao_somam_os_tempos(self, ambiente):
        """Fora do loop, dois envios lentos sobrepõem-se em vez de encadear."""
        inicio = time.monotonic()
        await asyncio.gather(_enviar(), _enviar())
        decorrido = time.monotonic() - inicio

        assert _SMTPLento.ligacoes == 2
        assert decorrido < BLOQUEIO * 1.8, (
            f"dois envios demoraram {decorrido:.2f}s — foram serializados no event loop"
        )


class TestTimeoutConfiguravel:
    def test_default_mantem_os_30_segundos(self, monkeypatch):
        monkeypatch.delenv("SMTP_CONNECT_TIMEOUT", raising=False)
        assert email_service.get_smtp_connect_timeout() == 30

    def test_env_var_manda(self, monkeypatch):
        monkeypatch.setenv("SMTP_CONNECT_TIMEOUT", "5")
        assert email_service.get_smtp_connect_timeout() == 5

    @pytest.mark.parametrize("valor", ["", "abc", "0", "-3"])
    def test_valor_invalido_cai_no_default(self, monkeypatch, valor):
        """Nunca desligar o timeout por engano — sem timeout, pendura para sempre."""
        monkeypatch.setenv("SMTP_CONNECT_TIMEOUT", valor)
        assert email_service.get_smtp_connect_timeout() == 30

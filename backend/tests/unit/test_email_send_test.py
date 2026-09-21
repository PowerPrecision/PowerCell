"""Envio de email de teste — prova a entrega, não só as credenciais.

O "Testar Ligação" faz `login()` em IMAP e SMTP: prova que as credenciais
são aceites e mais nada. Um envio a sério falha DEPOIS do login por relay
recusado, política de remetente, tamanho de anexo ou rate limit — foi o
que aconteceu no incidente de 2026-09-21 (SMTP verde, envio a falhar).

Estes testes fixam que o envio de teste passa pelo caminho de produção.
"""
import email as _email
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from services import email_service, users_api_email_config
from tests.unit.conftest import FakeAsyncDatabase


UTILIZADOR = {
    "id": "u-fernando",
    "email": "fernando@precisioncredito.pt",
    "role": "consultor",
}


def _conta():
    return email_service.EmailAccount(
        name="personal",
        imap_server="mail.precisioncredito.pt",
        imap_port=993,
        smtp_server="mail.precisioncredito.pt",
        smtp_port=465,
        email="fernando@precisioncredito.pt",
        password="segredo",
    )


class _SMTPFalso:
    """Captura a mensagem tal como sai para a rede."""

    enviadas: list = []
    erro = None

    def __init__(self, *a, **kw):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def login(self, *a, **kw):
        if type(self).erro:
            raise type(self).erro

    def sendmail(self, _de, _para, raw, *a, **kw):
        type(self).enviadas.append(_email.message_from_string(raw))

    def quit(self):
        pass


@pytest.fixture
def smtp():
    _SMTPFalso.enviadas = []
    _SMTPFalso.erro = None
    return _SMTPFalso


@pytest.fixture
def ambiente(smtp):
    """Patches partilhados: BD falsa, SMTP falso, empresa activa."""
    db = FakeAsyncDatabase()
    alvos = [
        patch("database.db", db),
        patch.object(email_service, "db", db),
        patch.object(email_service.smtplib, "SMTP_SSL", smtp),
        patch("services.email_config_resolver.decrypt_email_secret", lambda v, _c="": "segredo"),
        patch("services.auth.get_active_company_id_async", AsyncMock(return_value="c-1")),
        patch.object(
            email_service, "get_email_accounts_async", AsyncMock(return_value=[_conta()])
        ),
    ]
    for a in alvos:
        a.start()
    yield db
    for a in reversed(alvos):
        a.stop()


async def _correr(request=None):
    return await users_api_email_config.run_send_test_email(
        request or object(), None, dict(UTILIZADOR),
    )


class TestEnvioDeTeste:
    async def test_envia_mesmo_pelo_smtp(self, ambiente, smtp):
        """A diferença face ao 'Testar Ligação': uma mensagem sai na rede."""
        with patch(
            "services.email_config_resolver.resolve_sending_account",
            AsyncMock(return_value=(_conta(), "profile:user")),
        ):
            resposta = await _correr()

        assert resposta["success"] is True
        assert smtp.enviadas, "nenhuma mensagem chegou ao SMTP — só se autenticou"

        msg = smtp.enviadas[-1]
        assert msg["To"] == UTILIZADOR["email"], "o teste envia para o próprio"
        assert "teste" in (msg["Subject"] or "").lower()

    async def test_resposta_diz_que_conta_usou(self, ambiente):
        """Sem isto, diagnosticar uma falha obrigava a ler os logs."""
        with patch(
            "services.email_config_resolver.resolve_sending_account",
            AsyncMock(return_value=(_conta(), "profile:user")),
        ):
            resposta = await _correr()

        assert resposta["account"] == "fernando@precisioncredito.pt"
        assert resposta["config_source"] == "profile:user"
        assert "mail.precisioncredito.pt:465" == resposta["smtp_server"]
        assert resposta["sent_to"] == UTILIZADOR["email"]

    async def test_credenciais_recusadas_devolvem_502_com_contexto(self, ambiente, smtp):
        """O sintoma real do incidente: 535 no envio."""
        smtp.erro = email_service.smtplib.SMTPAuthenticationError(
            535, b"Incorrect authentication data"
        )

        with patch(
            "services.email_config_resolver.resolve_sending_account",
            AsyncMock(return_value=(_conta(), "profile:user")),
        ):
            with pytest.raises(HTTPException) as exc:
                await _correr()

        assert exc.value.status_code == 502
        detalhe = str(exc.value.detail)
        assert "fernando@precisioncredito.pt" in detalhe, "tem de dizer QUE conta falhou"
        assert "profile:user" in detalhe, "e de que configuração veio"

    async def test_sem_conta_resolvida_devolve_400(self, ambiente):
        with patch(
            "services.email_config_resolver.resolve_sending_account",
            AsyncMock(return_value=(None, "none")),
        ):
            with pytest.raises(HTTPException) as exc:
                await _correr()

        assert exc.value.status_code == 400
        assert "configure" in str(exc.value.detail).lower()

    async def test_nao_arquiva_no_historico_de_um_processo(self, ambiente):
        """Um email de teste não tem de poluir o histórico de processos."""
        with patch(
            "services.email_config_resolver.resolve_sending_account",
            AsyncMock(return_value=(_conta(), "profile:user")),
        ):
            await _correr()

        gravados = [d async for d in ambiente.emails.find({})]
        assert gravados == [], "sem process_id, o send_email não deve arquivar"


class TestPontoUnicoDeResolucao:
    """A duplicação desta lógica foi a causa do incidente de 2026-09-21."""

    def test_envio_de_documentacao_usa_o_helper_partilhado(self):
        from pathlib import Path

        raiz = Path(__file__).resolve().parents[2] / "services"
        documentacao = (raiz / "email_documentation.py").read_text()
        config_api = (raiz / "users_api_email_config.py").read_text()

        assert "resolve_sending_account" in documentacao, (
            "o envio de documentação tem de usar o resolvedor partilhado"
        )
        assert "resolve_sending_account" in config_api, (
            "o envio de teste tem de usar o MESMO resolvedor — se divergirem, "
            "o teste volta a mentir sobre o envio"
        )
        assert "load_caixa_geral_config" not in documentacao, (
            "a resolução foi extraída; reconstruí-la aqui reabre a divergência"
        )

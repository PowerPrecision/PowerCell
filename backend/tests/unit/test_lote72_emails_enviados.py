"""E-mails fantasma — o que se envia fica na BD e nos «Enviados» do servidor (Lote 7.2).

O relato: os emails enviados pelos consultores (Webmail ou dentro do processo) saem, mas não aparecem
na cronologia nem na pasta «Enviados» do servidor. A causa, lida no código: `send_email` só arquivava
em `db.emails` quando recebia um `process_id` (um envio do Webmail sem processo não deixava rasto
algum) e nunca fez APPEND IMAP — o SMTP entrega mas não guarda na caixa de quem enviou.

Estes testes correm o `send_email` REAL com o SMTP e o IMAP falseados AO NÍVEL DA CHAMADA (asserções sobre
os parâmetros que saem para a rede, não sobre o que um duplo decidiu fazer).
"""
from __future__ import annotations

import email as _email
from unittest.mock import AsyncMock, patch

import pytest

from services import email_service
from tests.unit.conftest import FakeAsyncDatabase


def _conta(smtp="mail.precisioncredito.pt", imap="imap.precisioncredito.pt", porta_imap=993, nome="personal"):
    return email_service.EmailAccount(
        name=nome, imap_server=imap, imap_port=porta_imap, smtp_server=smtp, smtp_port=465,
        email="Fernando@PrecisionCredito.pt", password="segredo",
    )


class _SMTPFalso:
    enviadas: list = []

    def __init__(self, *a, **kw):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def login(self, *a, **kw):
        pass

    def sendmail(self, de, para, raw, *a, **kw):
        type(self).enviadas.append({"de": de, "para": para, "raw": raw, "msg": _email.message_from_string(raw)})


class _IMAPFalso:
    """Regista o que o servidor IMAP receberia, parâmetro a parâmetro."""

    chamadas: list = []
    lista = [b'(\\HasNoChildren) "." "INBOX"', b'(\\HasNoChildren \\Sent) "." "INBOX.Enviados-do-servidor"']
    erro_no_login = None
    resposta_append = ("OK", [b"APPEND completed"])

    def __init__(self, host, porta, **kw):
        type(self).chamadas.append(("ligar", host, porta))

    def login(self, utilizador, senha):
        if type(self).erro_no_login:
            raise type(self).erro_no_login
        type(self).chamadas.append(("login", utilizador, senha))

    def list(self):
        return "OK", list(type(self).lista)

    def append(self, pasta, flags, data, mensagem):
        type(self).chamadas.append(("append", pasta, flags, mensagem))
        return type(self).resposta_append

    def logout(self):
        type(self).chamadas.append(("logout",))


@pytest.fixture
def mundo(monkeypatch):
    _SMTPFalso.enviadas = []
    _IMAPFalso.chamadas = []
    _IMAPFalso.lista = [b'(\\HasNoChildren) "." "INBOX"', b'(\\HasNoChildren \\Sent) "." "INBOX.Enviados-do-servidor"']
    _IMAPFalso.erro_no_login = None
    _IMAPFalso.resposta_append = ("OK", [b"APPEND completed"])
    monkeypatch.setenv("IMAP_APPEND_ENABLED", "true")
    db = FakeAsyncDatabase()
    alvos = [
        patch("database.db", db),
        patch.object(email_service, "db", db),
        patch.object(email_service.smtplib, "SMTP_SSL", _SMTPFalso),
        patch.object(email_service.imaplib, "IMAP4_SSL", _IMAPFalso),
        patch("services.email_config_resolver.decrypt_email_secret", lambda v, _c="": "segredo"),
        patch("services.email_service.resolve_email_signature", AsyncMock(return_value=(None, "none"))),
    ]
    for a in alvos:
        a.start()
    yield db
    for a in reversed(alvos):
        a.stop()


async def _enviar(conta=None, **extra):
    base = dict(
        account_name="personal", to_emails=["cliente@exemplo.pt"], subject="Assunto", body="Corpo",
        created_by="u-1", active_company_id="cmp-1", account_override=conta or _conta(),
    )
    base.update(extra)
    return await email_service.send_email(**base)


def _appends():
    return [c for c in _IMAPFalso.chamadas if c[0] == "append"]


@pytest.mark.asyncio
class TestOEmailFicaNaBaseDeDados:
    async def test_o_ataque_um_envio_do_webmail_sem_processo_deixa_rasto(self, mundo):
        """Antes: nada em `db.emails` (só havia arquivo com `process_id`)."""
        r = await _enviar(bcc_emails=["oculto@exemplo.pt"])

        assert r["success"] is True
        docs = [d async for d in mundo.emails.find({})]
        assert len(docs) == 1
        d = docs[0]
        assert (d["folder"], d["direction"], d["status"]) == ("Sent", "sent", "sent")
        assert d["process_id"] is None
        assert d["created_by"] == "u-1" and d["synced_for_user"] == "u-1"
        assert d["company_id"] == "cmp-1"
        assert d["to_emails"] == ["cliente@exemplo.pt"] and d["bcc_emails"] == ["oculto@exemplo.pt"]
        # o Message-ID gravado é o que SAIU na mensagem: é por ele que o sync não duplica
        assert d["message_id"] == _SMTPFalso.enviadas[0]["msg"]["Message-ID"]

    async def test_com_processo_fica_ligado_a_ele(self, mundo):
        await _enviar(process_id="p-9", skip_proc_tag=True)
        docs = [d async for d in mundo.emails.find({})]
        assert [d["process_id"] for d in docs] == ["p-9"]
        assert docs[0]["folder"] == "Sent"

    async def test_uma_resposta_herda_o_processo_do_email_a_que_responde(self, mundo):
        mundo.emails.docs.append({"id": "pai", "message_id": "<pai@exemplo.pt>", "process_id": "p-7", "direction": "received"})
        await _enviar(in_reply_to="<pai@exemplo.pt>")
        novo = [d async for d in mundo.emails.find({"direction": "sent"})][0]
        assert novo["process_id"] == "p-7"
        assert novo["in_reply_to"] == "<pai@exemplo.pt>"

    async def test_um_pai_sem_processo_nao_inventa_um(self, mundo):
        mundo.emails.docs.append({"id": "pai", "message_id": "<pai@exemplo.pt>", "process_id": None, "direction": "received"})
        await _enviar(in_reply_to="<pai@exemplo.pt>")
        novo = [d async for d in mundo.emails.find({"direction": "sent"})][0]
        assert novo["process_id"] is None

    async def test_o_registo_e_reconhecido_pela_sincronizacao_e_nao_se_duplica(self, mundo):
        """A chave com que o `sync_user_emails` decide «já tenho este»: message_id + utilizador + empresa + endereço."""
        await _enviar()
        msg_id = _SMTPFalso.enviadas[0]["msg"]["Message-ID"]
        existente = await mundo.emails.find_one({
            "message_id": msg_id, "synced_for_user": "u-1", "company_id": "cmp-1",
            "account": "fernando@precisioncredito.pt",
        })
        assert existente is not None, "o sync voltaria a importar o email que acabámos de enviar"

    async def test_os_emails_de_sistema_sem_processo_nao_poluem_a_base(self, mundo):
        await _enviar(force_system=True, reply_to="x@y.pt")
        assert [d async for d in mundo.emails.find({})] == []

    async def test_o_envio_de_teste_nao_arquiva_nem_copia(self, mundo):
        await _enviar(guardar_copia=False)
        assert [d async for d in mundo.emails.find({})] == []
        assert _appends() == []

    async def test_uma_falha_do_smtp_nao_deixa_registo(self, mundo):
        with patch.object(_SMTPFalso, "sendmail", side_effect=OSError("rede")):
            r = await _enviar()
        assert r["success"] is False
        assert [d async for d in mundo.emails.find({})] == []
        assert _appends() == []


@pytest.mark.asyncio
class TestACopiaNosEnviadosDoServidor:
    async def test_o_ataque_o_append_vai_para_a_pasta_marcada_como_sent(self, mundo):
        """Parâmetros que saem para o IMAP: servidor/porta da caixa, pasta `\\Sent`, `\\Seen`, a mensagem real."""
        await _enviar()

        assert ("ligar", "imap.precisioncredito.pt", 993) in _IMAPFalso.chamadas
        assert ("login", "Fernando@PrecisionCredito.pt", "segredo") in _IMAPFalso.chamadas
        (_, pasta, flags, mensagem), = _appends()
        assert pasta == '"INBOX.Enviados-do-servidor"'
        assert flags == "\\Seen"
        enviado = _SMTPFalso.enviadas[0]["msg"]
        copia = _email.message_from_bytes(mensagem)
        assert copia["Message-ID"] == enviado["Message-ID"]
        assert copia["Subject"] == "Assunto" and copia["To"] == "cliente@exemplo.pt"

    async def test_a_copia_nunca_leva_o_bcc(self, mundo):
        await _enviar(bcc_emails=["oculto@exemplo.pt"])
        (_, _, _, mensagem), = _appends()
        assert b"oculto@exemplo.pt" not in mensagem
        assert _email.message_from_bytes(mensagem)["Bcc"] is None

    async def test_sem_marca_sent_usa_um_nome_habitual(self, mundo):
        _IMAPFalso.lista = [b'(\\HasNoChildren) "/" "INBOX"', b'(\\HasNoChildren) "/" "Sent Items"']
        await _enviar()
        assert _appends()[0][1] == '"Sent Items"'

    async def test_sem_pasta_de_enviados_regista_a_falha_e_o_envio_continua_a_ter_sucesso(self, mundo):
        _IMAPFalso.lista = [b'(\\HasNoChildren) "." "INBOX"']
        r = await _enviar()
        assert r["success"] is True
        assert _appends() == []
        d = [x async for x in mundo.emails.find({})][0]
        assert d["imap_appended"] is False and "Enviados" in d["imap_append_error"]

    async def test_servidor_imap_em_baixo_nao_derruba_o_envio(self, mundo):
        _IMAPFalso.erro_no_login = OSError("ligação recusada")
        r = await _enviar()
        assert r["success"] is True
        d = [x async for x in mundo.emails.find({})][0]
        assert d["imap_appended"] is False and "ligação recusada" in d["imap_append_error"]

    async def test_o_append_bem_sucedido_fica_registado(self, mundo):
        await _enviar()
        d = [x async for x in mundo.emails.find({})][0]
        assert d["imap_appended"] is True and d["imap_folder"] == "INBOX.Enviados-do-servidor"

    @pytest.mark.parametrize("smtp", ["smtp.gmail.com", "smtp.office365.com", "SMTP.GMAIL.COM"])
    async def test_o_gmail_e_o_microsoft_365_guardam_sozinhos_e_nao_se_duplica(self, mundo, smtp):
        await _enviar(conta=_conta(smtp=smtp))
        assert _IMAPFalso.chamadas == [], "um APPEND em cima do que o servidor já guarda duplica o email"

    async def test_uma_porta_de_smtp_na_config_do_imap_cai_na_993(self, mundo):
        await _enviar(conta=_conta(porta_imap=465))
        assert ("ligar", "imap.precisioncredito.pt", 993) in _IMAPFalso.chamadas

    async def test_contas_de_sistema_nunca_fazem_append(self, mundo):
        await _enviar(conta=_conta(nome="system_smtp"))
        assert _appends() == []

    async def test_desligada_por_variavel_de_ambiente(self, mundo, monkeypatch):
        monkeypatch.setenv("IMAP_APPEND_ENABLED", "false")
        await _enviar()
        assert _IMAPFalso.chamadas == []

    async def test_em_testing_fica_desligada_por_omissao(self, mundo, monkeypatch):
        monkeypatch.delenv("IMAP_APPEND_ENABLED")
        monkeypatch.setenv("TESTING", "true")
        await _enviar()
        assert _IMAPFalso.chamadas == []

    async def test_o_envio_via_resend_nao_tem_caixa_onde_fazer_append(self, mundo):
        conta = _conta(smtp="resend")
        conta.password = "re_chave"
        with patch.object(email_service, "_send_via_resend") as resend:
            r = await _enviar(conta=conta)
        assert r["success"] is True and resend.called
        assert _IMAPFalso.chamadas == []


class TestAPastaDeEnviados:
    def test_a_marca_sent_vence_o_nome(self):
        class M:
            def list(self):
                return "OK", [b'(\\HasNoChildren \\Sent) "." "INBOX.Sent"', b'(\\HasNoChildren) "." "Enviados"']

        assert email_service._pasta_enviados_do_servidor(M()) == "INBOX.Sent"

    def test_sem_marca_o_primeiro_nome_habitual_da_lista(self):
        class M:
            def list(self):
                return "OK", [b'(\\HasNoChildren) "/" "INBOX"', b'(\\HasNoChildren) "/" "enviados"']

        assert email_service._pasta_enviados_do_servidor(M()) == "enviados"

    def test_nenhuma_pasta_reconhecivel(self):
        class M:
            def list(self):
                return "OK", [b'(\\HasNoChildren) "/" "INBOX"', b'(\\HasNoChildren) "/" "Arquivo"']

        assert email_service._pasta_enviados_do_servidor(M()) is None

    def test_list_a_falhar_nao_levanta(self):
        class M:
            def list(self):
                raise OSError("x")

        assert email_service._pasta_enviados_do_servidor(M()) is None


@pytest.mark.asyncio
class TestAContaPessoalTemOImapDaCaixa:
    async def test_o_resolver_passa_o_servidor_e_a_porta_IMAP_e_nao_os_do_smtp(self, mundo):
        """Antes: `imap_server = smtp_server` e `imap_port = smtp_port` — o APPEND ia para a porta 465."""
        mundo.users.docs.append({"id": "u-1", "role": "consultor", "email_config": {}})
        resolvido = {
            "email_address": "fernando@precisioncredito.pt", "encrypted_password": "enc",
            "smtp_server": "smtp.precisioncredito.pt", "smtp_port": 465,
            "imap_server": "imap.precisioncredito.pt", "imap_port": 993, "config_source": "user",
        }
        with patch("services.email_config_resolver.resolve_email_config_for_sync", AsyncMock(return_value=resolvido)), \
             patch("services.encryption.encryption_service.decrypt", lambda v: "segredo"):
            r = await email_service.send_email(
                account_name="personal", to_emails=["c@exemplo.pt"], subject="s", body="b",
                created_by="u-1", active_company_id="cmp-1",
            )
        assert r["success"] is True
        assert ("ligar", "imap.precisioncredito.pt", 993) in _IMAPFalso.chamadas

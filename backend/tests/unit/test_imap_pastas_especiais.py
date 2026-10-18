"""QA-7 (3): Enviados / Rascunhos / Eliminados descobrem-se no servidor, não por nomes rígidos.

Um email copiado para uma pasta que o cliente de email do utilizador não mostra (nome diferente do
que o cliente usa, ou pasta não subscrita) fica «perdido». A pasta é a que o SERVIDOR marca
(`\\Sent`, `\\Drafts`, `\\Trash`, RFC 6154); só sem marca se tentam os nomes habituais, em inglês e
em português. O fake está ao nível do protocolo (`LIST`, `APPEND`, `SUBSCRIBE`) e as asserções são
sobre o que SAI para o servidor.
"""
from types import SimpleNamespace
from unittest.mock import patch

import pytest

import services.email_service as email_service


class _IMAP:
    chamadas: list = []
    lista: list = []

    def __init__(self, *a, **kw):
        pass

    def login(self, *a):
        pass

    def list(self):
        return "OK", list(type(self).lista)

    def append(self, pasta, flags, data, mensagem):
        type(self).chamadas.append(("append", pasta))
        return "OK", [b"ok"]

    def subscribe(self, pasta):
        type(self).chamadas.append(("subscribe", pasta))
        return "OK", [b"ok"]

    def logout(self):
        pass


def _linha(nome, flags=""):
    return f'(\\HasNoChildren {flags}) "." "{nome}"'.encode()


@pytest.fixture(autouse=True)
def _imap():
    _IMAP.chamadas = []
    _IMAP.lista = []
    with patch.object(email_service.imaplib, "IMAP4_SSL", _IMAP):
        yield


def _pastas(tipo):
    return email_service._pastas_especiais_do_servidor(_IMAP("h", 993), tipo)


class TestDescobertaPorMarcaDoServidor:
    def test_a_marca_manda_mesmo_com_nome_inesperado(self):
        _IMAP.lista = [_linha("INBOX"), _linha("Mensagens Saidas", "\\Sent"),
                       _linha("Minutas", "\\Drafts"), _linha("Papelaria", "\\Trash")]
        assert _pastas("sent")[0] == "Mensagens Saidas"
        assert _pastas("drafts")[0] == "Minutas"
        assert _pastas("trash")[0] == "Papelaria"

    def test_a_marca_vem_antes_de_um_nome_habitual_que_tambem_existe(self):
        _IMAP.lista = [_linha("Enviados"), _linha("Outra", "\\Sent")]
        assert _pastas("sent") == ["Outra", "Enviados"]


class TestRecursoPortugues:
    @pytest.mark.parametrize("tipo,nome", [
        ("sent", "Enviados"), ("sent", "Itens Enviados"),
        ("drafts", "Rascunhos"),
        ("trash", "Eliminados"), ("trash", "Lixo"), ("trash", "Trash"),
    ])
    def test_sem_marca_encontra_o_nome_em_portugues(self, tipo, nome):
        _IMAP.lista = [_linha("INBOX"), _linha(nome)]
        assert _pastas(tipo) == [nome]

    @pytest.mark.parametrize("tipo,nome", [
        ("sent", "INBOX.Enviados"), ("drafts", "INBOX.Rascunhos"), ("trash", "INBOX.Eliminados"),
    ])
    def test_com_o_prefixo_inbox_do_servidor(self, tipo, nome):
        _IMAP.lista = [_linha("INBOX"), _linha(nome)]
        assert _pastas(tipo) == [nome]

    def test_so_devolve_pastas_que_existem(self):
        _IMAP.lista = [_linha("INBOX")]
        assert _pastas("sent") == [] and _pastas("drafts") == [] and _pastas("trash") == []

    def test_cada_tipo_so_ve_as_suas(self):
        _IMAP.lista = [_linha("Enviados"), _linha("Rascunhos"), _linha("Lixo")]
        assert _pastas("sent") == ["Enviados"]
        assert _pastas("drafts") == ["Rascunhos"]
        assert _pastas("trash") == ["Lixo"]


class TestAppendSubscreveAPasta:
    def test_depois_do_append_a_pasta_fica_subscrita(self):
        _IMAP.lista = [_linha("Itens Enviados", "\\Sent")]
        conta = SimpleNamespace(imap_server="h", imap_port=993, email="a@b.pt")
        r = email_service._imap_append_enviados_sync(conta, "pw", b"msg")
        assert r == {"ok": True, "folder": "Itens Enviados"}
        assert _IMAP.chamadas == [("append", '"Itens Enviados"'), ("subscribe", '"Itens Enviados"')]


class TestCandidatasParaASincronizacao:
    def _conta(self):
        return SimpleNamespace(name="x", imap_server="h", imap_port=993, email="a@b.pt", password="pw")

    def test_descobertas_primeiro_e_nomes_habituais_depois_sem_repetir(self, monkeypatch):
        monkeypatch.setenv("IMAP_PASTAS_DESCOBERTA_ENABLED", "true")
        _IMAP.lista = [_linha("Saidas", "\\Sent"), _linha("Enviados")]
        r = email_service.pastas_candidatas_sync(self._conta())
        assert r["sent"][:2] == ["Saidas", "Enviados"]
        assert r["sent"].count("Enviados") == 1
        assert "Itens Enviados" in r["sent"]  # o recurso continua lá
        assert "Rascunhos" in r["drafts"] and "Eliminados" in r["trash"] and "Lixo" in r["trash"]

    def test_sem_servidor_ficam_os_nomes_habituais(self, monkeypatch):
        monkeypatch.setenv("IMAP_PASTAS_DESCOBERTA_ENABLED", "true")

        class _Falha(_IMAP):
            def login(self, *a):
                raise OSError("sem rede")

        with patch.object(email_service.imaplib, "IMAP4_SSL", _Falha):
            r = email_service.pastas_candidatas_sync(self._conta())
        assert r["sent"] == list(email_service.NOMES_DA_PASTA_ENVIADOS)
        assert r["trash"] == list(email_service.NOMES_DA_PASTA_LIXO)

    def test_em_testes_nao_liga_a_servidor_nenhum(self):
        # TESTING=true (CI): a descoberta está desligada e não se abre ligação.
        abertas = []

        class _Conta(_IMAP):
            def __init__(self, *a, **kw):
                abertas.append(a)

        with patch.object(email_service.imaplib, "IMAP4_SSL", _Conta):
            r = email_service.pastas_candidatas_sync(self._conta())
        assert abertas == []
        assert r["drafts"] == list(email_service.NOMES_DA_PASTA_RASCUNHOS)

"""As primitivas de chave EXACTA do S3 que o PDF limpo do Index usa (Lote 12, Fase 5).

A lição do `test_s3_content_quarantine.py` outra vez: um S3 falseado que reimplementa a lógica
valida o duplo, não o código. Aqui o falso é um cliente `boto3` AO NÍVEL DA CHAMADA e as asserções são
sobre os PARÂMETROS que saem — a chave exacta, sem variações underscore/espaço (inspeccionar uma
chave e gravar outra é a forma discreta de uma verificação não valer nada), o corpo, o tipo.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from botocore.exceptions import ClientError


class ClienteBoto3Falso:
    def __init__(self):
        self.puts: list[dict] = []
        self.gets: list[dict] = []
        self.heads: list[dict] = []
        self.tamanho = 100
        self.corpo = b"%PDF-1.7 conteudo"
        self.erro_put: Exception | None = None
        self.erro_get: Exception | None = None
        self.codigo_head: str | None = None

    def put_object(self, **kw):
        self.puts.append(kw)
        if self.erro_put:
            raise self.erro_put

    def head_object(self, **kw):
        self.heads.append(kw)
        if self.codigo_head:
            raise ClientError({"Error": {"Code": self.codigo_head, "Message": "x"}}, "HeadObject")
        return {"ContentLength": self.tamanho, "ContentType": "application/pdf", "ETag": '"e"'}

    def get_object(self, **kw):
        self.gets.append(kw)
        if self.erro_get:
            raise self.erro_get

        class Corpo:
            def __init__(self, d):
                self.d = d

            def read(self):
                return self.d

        return {"Body": Corpo(self.corpo)}


@pytest.fixture
def s3():
    from services.s3_storage import s3_service

    cliente = ClienteBoto3Falso()
    with patch.object(s3_service, "s3_client", cliente), patch.object(s3_service, "bucket_name", "bucket-teste"):
        yield s3_service, cliente


CHAVE = "Documentação Clientes/Ana Maria/Index/recibo 01_limpo.pdf"


class TestPutObjectExact:
    def test_grava_na_chave_exacta_com_o_corpo_e_o_tipo(self, s3):
        servico, cliente = s3
        assert servico.put_object_exact(CHAVE, b"%PDF-1.7 x", "application/pdf") is True
        assert cliente.puts == [{"Bucket": "bucket-teste", "Key": CHAVE, "Body": b"%PDF-1.7 x", "ContentType": "application/pdf"}]

    def test_a_chave_nao_leva_variacoes(self, s3):
        servico, cliente = s3
        servico.put_object_exact(CHAVE, b"x")
        assert [p["Key"] for p in cliente.puts] == [CHAVE]

    @pytest.mark.parametrize("dados", [b"", None, "texto", 123])
    def test_corpo_vazio_ou_de_tipo_errado_nao_se_grava(self, s3, dados):
        servico, cliente = s3
        assert servico.put_object_exact(CHAVE, dados) is False
        assert cliente.puts == []

    def test_chave_vazia_nao_se_grava(self, s3):
        servico, cliente = s3
        assert servico.put_object_exact("", b"x") is False and cliente.puts == []

    def test_erro_do_s3_devolve_falso_sem_levantar(self, s3):
        servico, cliente = s3
        cliente.erro_put = ClientError({"Error": {"Code": "InternalError", "Message": "x"}}, "PutObject")
        assert servico.put_object_exact(CHAVE, b"x") is False
        cliente.erro_put = RuntimeError("rede")
        assert servico.put_object_exact(CHAVE, b"x") is False

    def test_sem_s3_configurado_devolve_falso(self):
        from services.s3_storage import s3_service

        with patch.object(s3_service, "is_configured", return_value=False):
            assert s3_service.put_object_exact(CHAVE, b"x") is False


class TestGetObjectExact:
    def test_le_a_chave_exacta_depois_de_perguntar_o_tamanho(self, s3):
        servico, cliente = s3
        assert servico.get_object_exact(CHAVE, 1000) == ("ok", cliente.corpo)
        assert [h["Key"] for h in cliente.heads] == [CHAVE]
        assert [g["Key"] for g in cliente.gets] == [CHAVE]  # nenhuma variação underscore/espaço

    def test_um_objecto_maior_que_o_limite_nao_se_descarrega(self, s3):
        servico, cliente = s3
        cliente.tamanho = 5000
        assert servico.get_object_exact(CHAVE, 1000) == ("grande", None)
        assert cliente.gets == []  # o tecto é ANTES de ler: senão a RAM do worker paga o objecto inteiro

    def test_ausente_e_diferente_de_erro(self, s3):
        servico, cliente = s3
        cliente.codigo_head = "404"
        assert servico.get_object_exact(CHAVE, 1000) == ("ausente", None)
        cliente.codigo_head = "InternalError"
        assert servico.get_object_exact(CHAVE, 1000) == ("erro", None)
        assert cliente.gets == []

    def test_falha_na_leitura_e_erro_nao_ausente(self, s3):
        servico, cliente = s3
        cliente.erro_get = ClientError({"Error": {"Code": "InternalError", "Message": "x"}}, "GetObject")
        assert servico.get_object_exact(CHAVE, 1000) == ("erro", None)
        cliente.erro_get = RuntimeError("rede")
        assert servico.get_object_exact(CHAVE, 1000) == ("erro", None)

    def test_sem_s3_configurado_e_erro(self):
        from services.s3_storage import s3_service

        with patch.object(s3_service, "is_configured", return_value=False):
            assert s3_service.get_object_exact(CHAVE, 10) == ("erro", None)

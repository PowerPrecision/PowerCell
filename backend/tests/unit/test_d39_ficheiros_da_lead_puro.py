"""D-39 — a parte PURA da consolidação dos ficheiros da lead e a primitiva de cópia do S3.

O S3 é falseado AO NÍVEL DA CHAMADA (cliente boto3): as asserções são sobre os parâmetros que
saem (`CopySource`, `Key`), nunca sobre um resultado que o próprio falso calculou.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from services import partner_lead_files as m

LEAD = "11111111-1111-4111-8111-111111111111"
CLIENTE = "22222222-2222-4222-8222-222222222222"
ORIGEM = f"Documentação Clientes/{LEAD}"
DESTINO = f"Documentação Clientes/{CLIENTE}"


class TestPastas:
    def test_a_origem_deriva_do_id(self):
        assert m.pasta_de_origem(LEAD) == ORIGEM

    def test_id_inutilizavel_nao_da_origem(self):
        assert m.pasta_de_origem("") is None
        assert m.pasta_de_origem("a/b") is None

    def test_destino_prefere_o_ponteiro_gravado(self):
        assert m.pasta_de_destino({"id": CLIENTE, "s3_folder": "Documentação Clientes/Legado Ana"}) == (
            "Documentação Clientes/Legado Ana"
        )

    def test_sem_ponteiro_deriva_do_id(self):
        assert m.pasta_de_destino({"id": CLIENTE}) == DESTINO

    def test_ponteiro_corrompido_deriva_do_id(self):
        assert m.pasta_de_destino({"id": CLIENTE, "s3_folder": [True, "x"]}) == DESTINO

    def test_ponteiro_de_processo_sobe_a_pasta_do_cliente(self):
        pasta = f"{DESTINO}/processos/33333333-3333-4333-8333-333333333333"
        assert m.pasta_de_destino({"id": CLIENTE, "s3_folder": pasta}) == DESTINO

    @pytest.mark.parametrize("fora", ["backups/dump.zip", "companies/logo", "/"])
    def test_ponteiro_fora_da_raiz_nao_e_destino(self, fora):
        assert m.pasta_de_destino({"id": CLIENTE, "s3_folder": fora}) is None

    def test_pastas_encaixadas_ou_iguais_nao_sao_compativeis(self):
        assert not m.pastas_compativeis(ORIGEM, ORIGEM)
        assert not m.pastas_compativeis(ORIGEM, f"{ORIGEM}/Index")
        assert not m.pastas_compativeis(f"{ORIGEM}/Index", ORIGEM)
        assert not m.pastas_compativeis(None, DESTINO)
        assert m.pastas_compativeis(ORIGEM, DESTINO)


class TestChaveDeDestino:
    def test_mantem_o_caminho_relativo(self):
        assert m.chave_de_destino(f"{ORIGEM}/Index/cc.pdf", ORIGEM, DESTINO) == f"{DESTINO}/Index/cc.pdf"

    def test_fora_da_origem_nao_tem_destino(self):
        assert m.chave_de_destino("backups/dump.zip", ORIGEM, DESTINO) is None
        assert m.chave_de_destino(f"{DESTINO}/Index/x.pdf", ORIGEM, DESTINO) is None

    def test_a_fronteira_e_por_segmento(self):
        # A origem de OUTRA lead cujo id começa pelo mesmo texto não se arrasta.
        assert m.chave_de_destino(f"{ORIGEM}9/Index/x.pdf", ORIGEM, DESTINO) is None

    def test_a_propria_pasta_nao_e_um_ficheiro(self):
        assert m.chave_de_destino(ORIGEM, ORIGEM, DESTINO) is None


class TestSufixo:
    def test_antes_da_extensao(self):
        assert m.com_sufixo("a/b/cc.pdf", 2) == "a/b/cc (2).pdf"

    def test_sem_extensao(self):
        assert m.com_sufixo("a/b/ficheiro", 3) == "a/b/ficheiro (3)"

    def test_ponto_no_inicio_nao_e_extensao(self):
        assert m.com_sufixo("a/.oculto", 2) == "a/.oculto (2)"

    def test_so_o_nome_e_alterado(self):
        assert m.com_sufixo("a.b/c.d/e.pdf", 2) == "a.b/c.d/e (2).pdf"


class TestMesmoConteudo:
    def test_tamanho_e_etag_iguais(self):
        assert m.mesmo_conteudo({"tamanho": 10, "etag": "x"}, {"tamanho": 10, "etag": "x"})

    def test_etag_diferente(self):
        assert not m.mesmo_conteudo({"tamanho": 10, "etag": "x"}, {"tamanho": 10, "etag": "y"})

    def test_tamanho_diferente(self):
        assert not m.mesmo_conteudo({"tamanho": 10, "etag": "x"}, {"tamanho": 11, "etag": "x"})

    def test_multipart_so_compara_o_tamanho(self):
        assert m.mesmo_conteudo({"tamanho": 10, "etag": "abc-2"}, {"tamanho": 10, "etag": "def"})

    def test_sem_tamanho_nunca_e_igual(self):
        assert not m.mesmo_conteudo({"etag": "x"}, {"etag": "x"})

    def test_sem_etag_nunca_e_igual(self):
        assert not m.mesmo_conteudo({"tamanho": 1, "etag": ""}, {"tamanho": 1, "etag": ""})


class TestChavesDosRegistos:
    def test_topo_e_anexos_sem_repeticoes(self):
        docs = [
            {"s3_path": "a/1.pdf", "attached_files": [{"s3_path": "a/1.pdf"}, {"s3_path": "a/2.pdf"}]},
            {"attached_files": [{"s3_path": "a/3.pdf"}, "lixo", {"s3_path": ""}, {"s3_path": None}]},
            {"s3_path": "  "},
        ]
        assert m.chaves_dos_registos(docs) == ["a/1.pdf", "a/2.pdf", "a/3.pdf"]


class _Cliente:
    def __init__(self):
        self.copias: list[dict] = []
        self.erro = None

    def copy_object(self, **kw):
        self.copias.append(kw)
        if self.erro:
            raise self.erro


@pytest.fixture
def s3():
    from services.s3_storage import s3_service

    cliente = _Cliente()
    with patch.object(s3_service, "s3_client", cliente), patch.object(s3_service, "bucket_name", "bucket-teste"):
        yield s3_service, cliente


class TestCopyObjectExact:
    def test_os_parametros_que_saem(self, s3):
        servico, cliente = s3
        assert servico.copy_object_exact(f"{ORIGEM}/Index/a b.pdf", f"{DESTINO}/Index/a b.pdf") is True
        assert cliente.copias == [{
            "CopySource": {"Bucket": "bucket-teste", "Key": f"{ORIGEM}/Index/a b.pdf"},
            "Bucket": "bucket-teste",
            "Key": f"{DESTINO}/Index/a b.pdf",
        }]

    def test_as_chaves_nao_levam_variacoes(self, s3):
        servico, cliente = s3
        servico.copy_object_exact("x/Documentação Clientes/a b", "y/c d")
        assert cliente.copias[0]["CopySource"]["Key"] == "x/Documentação Clientes/a b"
        assert cliente.copias[0]["Key"] == "y/c d"

    @pytest.mark.parametrize("origem,destino", [("", "b"), ("a", ""), ("a", "a"), (None, "b")])
    def test_chaves_invalidas_ou_iguais_nao_copiam(self, s3, origem, destino):
        servico, cliente = s3
        assert servico.copy_object_exact(origem, destino) is False
        assert cliente.copias == []

    def test_falha_do_s3_e_falso_e_nao_levanta(self, s3):
        from botocore.exceptions import ClientError

        servico, cliente = s3
        cliente.erro = ClientError({"Error": {"Code": "500", "Message": "x"}}, "CopyObject")
        assert servico.copy_object_exact("a", "b") is False

    def test_nunca_apaga_a_origem(self, s3):
        servico, cliente = s3
        assert not hasattr(cliente, "delete_object")
        assert servico.copy_object_exact("a", "b") is True

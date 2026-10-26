"""Os comprovativos do cliente substituídos pelos do Index (decisão do Flavio, Out 2026).

O que conta para o processo são os extratos, recibos e declarações que o Index carregou; os do cliente desses
tipos deixam de contar e de se ver logo que o Index carrega o primeiro desse tipo, por titular. Sem Index (Via
Verde, rede sem Index) nada muda. O Index tem uma opção para os voltar a ver.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from services import index_substituicao as sub

PROC = {"id": "p1"}
PROC_DOIS = {"id": "p1", "second_client_id": "cli-2", "second_client_name": "Bruno"}


def doc(id_, *, index=False, cat=None, subcat=None, nome="", **extra):
    return {"id": id_, "s3_path": f"x/{id_}", "filename": nome or f"{id_}.pdf", "ai_category": cat,
            "ai_subcategory": subcat, "uploaded_by_index": index, **extra}


def recibo(id_, **kw):
    return doc(id_, cat="Financeiros", subcat="Recibo de Vencimento", **kw)


def extrato(id_, **kw):
    return doc(id_, cat="Bancários", subcat="Extrato Bancário", **kw)


def declaracao(id_, **kw):
    return doc(id_, cat="Financeiros", subcat="Declaração da Entidade Patronal", **kw)


class TestARegra:
    def test_o_recibo_do_index_substitui_os_recibos_do_cliente_seja_qual_for_o_nome(self):
        docs = [recibo("c1", nome="scan001.pdf"), recibo("c2", nome="recibo agosto.pdf"), recibo("i1", index=True)]
        assert sub.documentos_substituidos(docs, PROC) == {"c1", "c2"}

    def test_so_o_tipo_que_o_index_carregou(self):
        docs = [recibo("c1"), extrato("c2"), declaracao("c3"), recibo("i1", index=True)]
        assert sub.documentos_substituidos(docs, PROC) == {"c1"}

    def test_os_tres_tipos(self):
        docs = [recibo("c1"), extrato("c2"), declaracao("c3"),
                recibo("i1", index=True), extrato("i2", index=True), declaracao("i3", index=True)]
        assert sub.documentos_substituidos(docs, PROC) == {"c1", "c2", "c3"}

    def test_a_identificacao_e_o_resto_nunca_se_escondem(self):
        docs = [doc("c1", cat="Identificação", subcat="Cartão de Cidadão"), doc("c2", cat="Outros"),
                doc("i1", index=True, cat="Identificação", subcat="Cartão de Cidadão"), doc("i2", index=True, cat="Outros")]
        assert sub.documentos_substituidos(docs, PROC) == set()

    def test_sem_index_nada_muda(self):
        docs = [recibo("c1"), recibo("i1", index=True)]
        assert sub.documentos_substituidos(docs, {**PROC, "skip_index": True}) == set()
        assert sub.documentos_substituidos(docs, None) == set()

    def test_sem_upload_do_index_nada_se_esconde(self):
        assert sub.documentos_substituidos([recibo("c1"), extrato("c2")], PROC) == set()

    def test_upload_do_index_ainda_por_categorizar_nao_esconde_nada(self):
        docs = [recibo("c1"), doc("i1", index=True, nome="digitalizacao.pdf")]
        assert sub.documentos_substituidos(docs, PROC) == set()

    def test_o_tipo_que_a_analise_do_index_gravou_manda(self):
        docs = [recibo("c1"), doc("i1", index=True, cat="Outros", nome="a.pdf", index_facts={"tipo": "recibo_vencimento"})]
        assert sub.documentos_substituidos(docs, PROC) == {"c1"}

    def test_o_pdf_limpo_nao_conta(self):
        docs = [recibo("c1"), recibo("l1", is_clean_pdf=True)]
        assert sub.documentos_substituidos(docs, PROC) == set()

    def test_varios_trabalhos_do_mesmo_titular_saem_todos(self):
        """O Index volta a carregar os comprovativos de todos os trabalhos: o trabalho não entra na chave."""
        docs = [recibo("c1", index_facts={"tipo": "recibo_vencimento", "employer_nif": "500000000"}),
                recibo("c2", index_facts={"tipo": "recibo_vencimento", "employer_nif": "600000000"}),
                recibo("i1", index=True)]
        assert sub.documentos_substituidos(docs, PROC) == {"c1", "c2"}


class TestPorTitular:
    def test_o_do_1o_titular_nao_esconde_os_do_2o(self):
        docs = [recibo("c1"), recibo("c2", titular="titular2"), recibo("i1", index=True, titular="titular1")]
        assert sub.documentos_substituidos(docs, PROC_DOIS) == {"c1"}

    def test_o_do_2o_titular_so_esconde_os_do_2o(self):
        docs = [recibo("c1"), recibo("c2", titular="titular2"), recibo("i1", index=True, titular="titular2")]
        assert sub.documentos_substituidos(docs, PROC_DOIS) == {"c2"}

    def test_o_envio_do_proprio_2o_cliente_e_do_2o_titular(self):
        docs = [recibo("c1"), recibo("c2"), recibo("i1", index=True, titular="titular2")]
        registos = {"x/c2": {"client_id": "cli-2"}}
        assert sub.documentos_substituidos(docs, PROC_DOIS, registos) == {"c2"}

    def test_o_marcador_vence_o_cliente_do_envio(self):
        proc, registo = PROC_DOIS, {"client_id": "cli-2", "titular": "titular1"}
        assert sub.titular_do_documento(recibo("c1"), proc, registo) == "titular1"

    def test_sem_marcador_e_do_1o(self):
        assert sub.titular_do_documento(recibo("c1"), PROC_DOIS) == "titular1"

    def test_sem_2o_titular_tudo_e_do_1o(self):
        docs = [recibo("c1", titular="titular2"), recibo("i1", index=True)]
        assert sub.documentos_substituidos(docs, PROC) == {"c1"}
        assert sub.titular_do_documento(recibo("c1", titular="titular2"), PROC) == "titular1"

    def test_marcador_invalido_nao_conta(self):
        assert sub.titular_do_documento(recibo("c1", titular="titular3"), PROC_DOIS) == "titular1"


def _listagem():
    return {
        "files": {
            "Financeiros": [{"name": "a.pdf", "doc_id": "c1", "size": 10}, {"name": "b.pdf", "doc_id": "i1", "size": 5}],
            "Pessoais": [{"name": "cc.pdf", "doc_id": "c9", "size": 1}],
        },
        "stats": {"total_files": 3, "total_size": 16, "total_size_formatted": "16 B"},
    }


@pytest.mark.asyncio
class TestAListagem:
    async def _aplicar(self, papel, incluir=False, substituidos=frozenset({"c1"})):
        with patch.object(sub, "ids_substituidos", AsyncMock(return_value=set(substituidos))):
            return await sub.aplicar_a_listagem(_listagem(), "p1", papel, incluir)

    async def test_ninguem_ve_o_substituido_por_omissao(self):
        for papel in ("consultor", "intermediario", "indexacao", "diretor"):
            r = await self._aplicar(papel)
            assert [f["doc_id"] for f in r["files"]["Financeiros"]] == ["i1"]
            assert r["stats"]["total_files"] == 2 and r["stats"]["total_size"] == 6

    async def test_o_index_ve_quantos_e_pode_pedi_los(self):
        r = await self._aplicar("indexacao")
        assert r["superseded_count"] == 1
        r = await self._aplicar("indexacao", incluir=True)
        assert r["files"]["Financeiros"][0] == {"name": "a.pdf", "doc_id": "c1", "size": 10, "superseded": True}
        assert r["superseded_count"] == 1 and r["stats"]["total_files"] == 3

    async def test_quem_nao_ve_o_index_nao_sabe_que_existem(self):
        r = await self._aplicar("consultor", incluir=True)
        assert [f["doc_id"] for f in r["files"]["Financeiros"]] == ["i1"]
        assert "superseded_count" not in r and "superseded" not in repr(r)

    async def test_sem_substituidos_a_listagem_fica_igual(self):
        r = await self._aplicar("consultor", substituidos=frozenset())
        assert r == _listagem()


def test_quem_pode_ver_os_substituidos():
    assert sub.pode_ver_os_substituidos("indexacao") and sub.pode_ver_os_substituidos("Diretor")
    assert not sub.pode_ver_os_substituidos("consultor") and not sub.pode_ver_os_substituidos(None)

"""Libertar a pasta `Index` quando o processo passa a indexado (Bloco 2).

S3 falseado SÓ nas fronteiras (listar, existir, renomear); a decisão (que
ficheiros, para onde, o que fica) e o repontar dos pedidos do Portal são
os REAIS, e as asserções são sobre os PARÂMETROS que saem para o S3.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services import index_release as rel

BASE = "Documentação Clientes/cli-1"
INDEX = f"{BASE}/Index"


class S3Falso:
    """Só o que o S3 real faz: lista, diz se existe, renomeia."""

    def __init__(self, ficheiros_na_index, existentes=(), falha_rename=False):
        self._ficheiros = ficheiros_na_index
        self.existentes = set(existentes)
        self.falha_rename = falha_rename
        self.renomeados: list[tuple[str, str]] = []
        self.list_files_args = None

    def is_configured(self):
        return True

    def list_files(self, client_id, client_name, second, s3_folder):
        self.list_files_args = (client_id, s3_folder)
        return {"files": {"Index": [{"name": n, "path": f"{INDEX}/{n}"} for n in self._ficheiros]}}

    def file_exists(self, caminho):
        return caminho in self.existentes

    def rename_file(self, origem, destino):
        if self.falha_rename:
            return False
        self.renomeados.append((origem, destino))
        return True


async def _semear(db, *, indexado=True, categorias=None):
    await db.processes.insert_one({
        "id": "p-1", "client_name": "Ana", "s3_folder": BASE,
        "is_indexed": indexado,
    })
    for nome, cat in (categorias or {}).items():
        doc = {
            "id": f"m-{nome}", "process_id": "p-1", "filename": nome,
            "s3_path": f"{INDEX}/{nome}", "in_index_queue": True,
        }
        if cat:
            doc["ai_category"] = cat
        await db.document_metadata.insert_one(doc)


@pytest.fixture
def ambiente(fake_async_db):
    def montar(s3, historico=None):
        historico = historico if historico is not None else AsyncMock()
        return historico, [
            patch.object(rel, "db", fake_async_db),
            patch.object(rel, "s3_service", s3),
            patch.object(rel, "log_history", historico),
        ]
    return montar


async def _correr(patches, user=None):
    for p in patches:
        p.start()
    try:
        return await rel.libertar_ficheiros_do_index("p-1", user=user or {"id": "u1", "role": "diretor"})
    finally:
        for p in patches:
            p.stop()


@pytest.mark.asyncio
class TestLibertacao:
    async def test_move_para_a_pasta_da_categoria_e_actualiza_os_metadados(self, fake_async_db, ambiente):
        await _semear(fake_async_db, categorias={"cc.pdf": "Identificação"})
        s3 = S3Falso(["cc.pdf"])
        _, patches = ambiente(s3)
        rep = await _correr(patches)

        assert s3.renomeados == [(f"{INDEX}/cc.pdf", f"{BASE}/Identificação/cc.pdf")]
        assert rep["movidos"] == 1
        meta = await fake_async_db.document_metadata.find_one({"id": "m-cc.pdf"})
        assert meta["s3_path"] == f"{BASE}/Identificação/cc.pdf"
        assert meta["in_index_queue"] is False

    async def test_o_listar_usa_a_pasta_do_processo(self, fake_async_db, ambiente):
        await _semear(fake_async_db, categorias={"cc.pdf": "Identificação"})
        s3 = S3Falso(["cc.pdf"])
        _, patches = ambiente(s3)
        await _correr(patches)
        assert s3.list_files_args == ("p-1", BASE)

    @pytest.mark.parametrize("categoria", [None, "", "  ", "Index", "index"])
    async def test_sem_categoria_utilizavel_o_ficheiro_fica_e_conta(self, fake_async_db, ambiente, categoria):
        await _semear(fake_async_db, categorias={"x.pdf": categoria})
        s3 = S3Falso(["x.pdf"])
        _, patches = ambiente(s3)
        rep = await _correr(patches)
        assert s3.renomeados == []
        assert rep["sem_categoria"] == 1 and rep["movidos"] == 0
        meta = await fake_async_db.document_metadata.find_one({"id": "m-x.pdf"})
        assert meta["in_index_queue"] is True

    async def test_ficheiro_sem_registo_de_metadados_fica(self, fake_async_db, ambiente):
        await _semear(fake_async_db)
        s3 = S3Falso(["orfao.pdf"])
        _, patches = ambiente(s3)
        rep = await _correr(patches)
        assert s3.renomeados == [] and rep["sem_categoria"] == 1

    async def test_processo_por_indexar_nao_move_nada(self, fake_async_db, ambiente):
        await _semear(fake_async_db, indexado=False, categorias={"cc.pdf": "Identificação"})
        s3 = S3Falso(["cc.pdf"])
        _, patches = ambiente(s3)
        rep = await _correr(patches)
        assert s3.renomeados == [] and rep["executado"] is False

    async def test_via_verde_conta_como_indexado(self, fake_async_db, ambiente):
        await fake_async_db.processes.insert_one(
            {"id": "p-1", "client_name": "Ana", "s3_folder": BASE, "skip_index": True}
        )
        await fake_async_db.document_metadata.insert_one(
            {"id": "m", "process_id": "p-1", "s3_path": f"{INDEX}/a.pdf", "ai_category": "Imóvel"}
        )
        s3 = S3Falso(["a.pdf"])
        _, patches = ambiente(s3)
        rep = await _correr(patches)
        assert rep["movidos"] == 1

    async def test_conflito_de_nome_nunca_sobrescreve(self, fake_async_db, ambiente):
        await _semear(fake_async_db, categorias={"cc.pdf": "Identificação"})
        s3 = S3Falso(["cc.pdf"], existentes={f"{BASE}/Identificação/cc.pdf", f"{BASE}/Identificação/cc_2.pdf"})
        _, patches = ambiente(s3)
        await _correr(patches)
        assert s3.renomeados == [(f"{INDEX}/cc.pdf", f"{BASE}/Identificação/cc_3.pdf")]
        meta = await fake_async_db.document_metadata.find_one({"id": "m-cc.pdf"})
        assert meta["s3_path"].endswith("cc_3.pdf") and meta["filename"] == "cc_3.pdf"

    async def test_falha_do_s3_deixa_tudo_como_estava(self, fake_async_db, ambiente):
        await _semear(fake_async_db, categorias={"cc.pdf": "Identificação"})
        s3 = S3Falso(["cc.pdf"], falha_rename=True)
        historico, patches = ambiente(s3)
        rep = await _correr(patches)
        assert rep["falhados"] == 1 and rep["movidos"] == 0
        meta = await fake_async_db.document_metadata.find_one({"id": "m-cc.pdf"})
        assert meta["s3_path"] == f"{INDEX}/cc.pdf" and meta["in_index_queue"] is True
        historico.assert_not_called()

    async def test_o_pedido_do_portal_acompanha_o_ficheiro(self, fake_async_db, ambiente):
        await _semear(fake_async_db, categorias={"cc.pdf": "Identificação"})
        await fake_async_db.documents.insert_one({
            "id": "d1", "process_id": "p-1", "s3_path": f"{INDEX}/cc.pdf",
            "attached_files": [
                {"s3_path": f"{INDEX}/cc.pdf", "name": "cc.pdf"},
                {"s3_path": f"{BASE}/Outros/outro.pdf", "name": "outro.pdf"},
            ],
        })
        s3 = S3Falso(["cc.pdf"])
        _, patches = ambiente(s3)
        await _correr(patches)
        d = await fake_async_db.documents.find_one({"id": "d1"})
        novo = f"{BASE}/Identificação/cc.pdf"
        assert d["s3_path"] == novo
        assert d["attached_files"][0]["s3_path"] == novo
        # O outro anexo não se toca.
        assert d["attached_files"][1]["s3_path"] == f"{BASE}/Outros/outro.pdf"

    async def test_um_so_registo_no_historico_com_o_actor(self, fake_async_db, ambiente):
        await _semear(fake_async_db, categorias={"a.pdf": "Imóvel", "b.pdf": "Bancários"})
        s3 = S3Falso(["a.pdf", "b.pdf"])
        historico, patches = ambiente(s3)
        user = {"id": "u9", "role": "diretor"}
        await _correr(patches, user=user)
        assert historico.await_count == 1
        assert historico.call_args.kwargs["user"] == user

    async def test_o_perfil_indexacao_nao_deixa_rasto_no_historico(self, fake_async_db):
        """É quase sempre o indexador a marcar como indexado — com o
        `log_history` REAL, não com um duplo."""
        from services import history as modulo_historico

        await _semear(fake_async_db, categorias={"a.pdf": "Imóvel"})
        s3 = S3Falso(["a.pdf"])
        with patch.object(rel, "db", fake_async_db), patch.object(rel, "s3_service", s3), \
                patch.object(modulo_historico, "db", fake_async_db):
            rep = await rel.libertar_ficheiros_do_index(
                "p-1", user={"id": "ix", "role": "indexacao"}
            )
        assert rep["movidos"] == 1
        assert await fake_async_db.history.find_one({"process_id": "p-1"}) is None

    async def test_nunca_propaga_uma_excecao(self, fake_async_db, ambiente):
        await _semear(fake_async_db, categorias={"a.pdf": "Imóvel"})
        s3 = S3Falso(["a.pdf"])
        s3.list_files = MagicMock(side_effect=RuntimeError("S3 em baixo"))
        _, patches = ambiente(s3)
        rep = await _correr(patches)
        assert rep["erro"] == "RuntimeError" and rep["movidos"] == 0

    async def test_o_tecto_adia_o_excedente(self, fake_async_db, ambiente, monkeypatch):
        monkeypatch.setattr(rel, "MAXIMO_POR_LIBERTACAO", 1)
        await _semear(fake_async_db, categorias={"a.pdf": "Imóvel", "b.pdf": "Imóvel"})
        s3 = S3Falso(["a.pdf", "b.pdf"])
        _, patches = ambiente(s3)
        rep = await _correr(patches)
        assert rep["movidos"] == 1 and rep["adiados"] == 1

    async def test_so_mexe_em_chaves_da_Index(self, fake_async_db, ambiente):
        """Defesa em profundidade: mesmo que a listagem devolva outra coisa,
        uma chave fora da `Index` não se move."""
        await _semear(fake_async_db, categorias={"a.pdf": "Imóvel"})
        # COM categoria: se a guarda faltasse, este ficheiro mover-se-ia.
        await fake_async_db.document_metadata.insert_one(
            {"id": "mx", "process_id": "p-1", "s3_path": f"{BASE}/Financeiros/x.pdf", "ai_category": "Imóvel"}
        )
        s3 = S3Falso(["a.pdf"])
        s3.list_files = lambda *a, **k: {"files": {"Index": [{"name": "x", "path": f"{BASE}/Financeiros/x.pdf"}]}}
        _, patches = ambiente(s3)
        rep = await _correr(patches)
        assert s3.renomeados == [] and rep["movidos"] == 0


class TestALigacaoAoMarcarComoIndexado:
    def test_a_libertacao_corre_ANTES_do_motor_financeiro(self):
        """O motor lê o `s3_path` dos metadados: se corresse primeiro,
        encontrava as chaves antigas."""
        from services import process_indexing
        from tests.unit.helpers_fonte import codigo_da_funcao_sem_comentarios

        fonte = codigo_da_funcao_sem_comentarios(process_indexing.run_mark_indexed_side_effects)
        assert "libertar_index_sem_falhar(" in fonte
        assert fonte.index("libertar_index_sem_falhar(") < fonte.index("trigger_financial_engine_safe(")
        assert "resposta['index_release']" in fonte

    @pytest.mark.asyncio
    async def test_uma_falha_na_libertacao_nao_derruba_a_indexacao(self):
        from services import process_indexing

        with patch("services.index_release.libertar_ficheiros_do_index",
                   AsyncMock(side_effect=RuntimeError("boom"))):
            res = await process_indexing.libertar_index_sem_falhar("p-1", {"id": "u"})
        assert res["movidos"] == 0 and res["erro"] == "RuntimeError"

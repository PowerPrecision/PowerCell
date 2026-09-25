"""O `rename` move a chave E o mapeamento (Épico 10, Gestor S3, Passo 4).

A CEGUEIRA AUTO-INFLIGIDA
=========================
`run_s3_rename` copiava os objectos para o prefixo novo e apagava os
antigos — e não tocava em nada na base de dados. Consequências, por ordem
de gravidade:

1. `processes.s3_folder` continuava a apontar para o nome ANTIGO. Com o
   isolamento do Passo 3, a pasta passa a ser **órfã**: invisível a toda a
   gente excepto ADMIN/CEO. Renomear passou a ser apagar do mundo.
2. `document_metadata.s3_path` também aponta para o antigo — e é ele que
   sustenta o separador Documentos do processo, o badge IA, as validades e
   a análise. Os ficheiros desapareciam da ficha.
3. `documents.s3_path` / `attached_files` são os pedidos do Portal. O
   cliente ficava a ver um documento que já não está onde diz.

A medição de produção provou-o: **205 ligações partidas**, cada uma um
`rename` antigo.

REGRA: nunca bloqueia. Quando isto corre, os objectos JÁ se moveram no S3 —
levantar aqui mostraria um erro sobre uma operação bem sucedida e deixaria
o estado pior. Mesma lei do `document_portal_revoke`.
"""
from __future__ import annotations

import pytest

from services.s3_explorer_paths import RAIZ_DO_EXPLORADOR as R
from services.s3_folder_relink import religar_apos_rename, reescrever_prefixo

ANTIGO = f"{R}/Joao_Silva"
NOVO = f"{R}/Joao_Silva_Santos"


class TestReescreverPrefixo:
    """Puro: troca o prefixo sem tocar no resto do caminho."""

    def test_troca_o_prefixo(self):
        assert reescrever_prefixo(f"{ANTIGO}/Financeiros/irs.pdf", ANTIGO, NOVO) == \
            f"{NOVO}/Financeiros/irs.pdf"

    def test_a_propria_pasta_tambem_e_reescrita(self):
        assert reescrever_prefixo(ANTIGO, ANTIGO, NOVO) == NOVO

    def test_nao_toca_no_que_nao_e_do_prefixo(self):
        outro = f"{R}/Maria/Financeiros/a.pdf"
        assert reescrever_prefixo(outro, ANTIGO, NOVO) == outro

    def test_prefixo_parecido_nao_conta(self):
        """`Joao_Silva_2` começa por `Joao_Silva` e é OUTRO cliente.

        Sem fronteira de segmento, renomear um cliente arrastava o vizinho
        cujo nome começasse igual — e o sufixo `_2` é precisamente como o
        sistema desambigua homónimos, portanto é o caso comum, não o raro.
        """
        vizinho = f"{R}/Joao_Silva_2/Financeiros/a.pdf"
        assert reescrever_prefixo(vizinho, ANTIGO, NOVO) == vizinho

    def test_barra_final_nao_engana(self):
        assert reescrever_prefixo(f"{ANTIGO}/", ANTIGO, NOVO) == f"{NOVO}/"

    def test_valor_vazio_devolve_vazio(self):
        assert reescrever_prefixo("", ANTIGO, NOVO) == ""
        assert reescrever_prefixo(None, ANTIGO, NOVO) is None


class TestReligar:
    async def test_actualiza_o_mapeamento_do_processo(self, fake_async_db, monkeypatch):
        import services.s3_folder_relink as alvo

        monkeypatch.setattr(alvo, "db", fake_async_db)
        await fake_async_db.processes.insert_one({"id": "p1", "s3_folder": ANTIGO})

        r = await religar_apos_rename(ANTIGO, NOVO)

        doc = await fake_async_db.processes.find_one({"id": "p1"})
        assert doc["s3_folder"] == NOVO
        assert r["processos"] == 1

    async def test_actualiza_os_metadados_dos_documentos(self, fake_async_db, monkeypatch):
        """Sem isto, os ficheiros somem do separador Documentos da ficha."""
        import services.s3_folder_relink as alvo

        monkeypatch.setattr(alvo, "db", fake_async_db)
        await fake_async_db.document_metadata.insert_one(
            {"id": "d1", "s3_path": f"{ANTIGO}/Financeiros/irs.pdf"})

        r = await religar_apos_rename(ANTIGO, NOVO)

        doc = await fake_async_db.document_metadata.find_one({"id": "d1"})
        assert doc["s3_path"] == f"{NOVO}/Financeiros/irs.pdf"
        assert r["documentos"] == 1

    async def test_actualiza_os_pedidos_do_portal(self, fake_async_db, monkeypatch):
        """O cliente via um documento que já não estava onde dizia."""
        import services.s3_folder_relink as alvo

        monkeypatch.setattr(alvo, "db", fake_async_db)
        await fake_async_db.documents.insert_one({
            "id": "req1",
            "s3_path": f"{ANTIGO}/Identificacao/cc.pdf",
            "attached_files": [{"s3_path": f"{ANTIGO}/Identificacao/cc.pdf"}],
        })

        r = await religar_apos_rename(ANTIGO, NOVO)

        pedido = await fake_async_db.documents.find_one({"id": "req1"})
        assert pedido["s3_path"] == f"{NOVO}/Identificacao/cc.pdf"
        assert pedido["attached_files"][0]["s3_path"] == f"{NOVO}/Identificacao/cc.pdf"
        assert r["pedidos_portal"] == 1

    async def test_nao_arrasta_o_vizinho_de_nome_parecido(self, fake_async_db, monkeypatch):
        import services.s3_folder_relink as alvo

        monkeypatch.setattr(alvo, "db", fake_async_db)
        await fake_async_db.processes.insert_one({"id": "p1", "s3_folder": ANTIGO})
        await fake_async_db.processes.insert_one({"id": "p2", "s3_folder": f"{R}/Joao_Silva_2"})

        await religar_apos_rename(ANTIGO, NOVO)

        vizinho = await fake_async_db.processes.find_one({"id": "p2"})
        assert vizinho["s3_folder"] == f"{R}/Joao_Silva_2"

    async def test_nunca_levanta_quando_a_base_de_dados_falha(self, fake_async_db, monkeypatch):
        """Os objectos JÁ se moveram no S3. Levantar aqui mostraria um erro
        sobre uma operação bem sucedida e deixaria o estado pior."""
        import services.s3_folder_relink as alvo

        class BaseDeDadosPartida:
            def __getattr__(self, _):
                raise RuntimeError("Mongo em baixo")

        monkeypatch.setattr(alvo, "db", BaseDeDadosPartida())
        r = await religar_apos_rename(ANTIGO, NOVO)
        assert r["erro"] is True

    async def test_renomear_uma_SUBpasta_nao_mexe_no_mapeamento(self, fake_async_db, monkeypatch):
        """`s3_folder` é a pasta do CLIENTE. Renomear `Financeiros` não a
        muda — mas os caminhos dos documentos lá dentro mudam."""
        import services.s3_folder_relink as alvo

        monkeypatch.setattr(alvo, "db", fake_async_db)
        await fake_async_db.processes.insert_one({"id": "p1", "s3_folder": ANTIGO})
        await fake_async_db.document_metadata.insert_one(
            {"id": "d1", "s3_path": f"{ANTIGO}/Financeiros/irs.pdf"})

        r = await religar_apos_rename(f"{ANTIGO}/Financeiros", f"{ANTIGO}/Financas")

        processo = await fake_async_db.processes.find_one({"id": "p1"})
        assert processo["s3_folder"] == ANTIGO
        doc = await fake_async_db.document_metadata.find_one({"id": "d1"})
        assert doc["s3_path"] == f"{ANTIGO}/Financas/irs.pdf"
        assert r["processos"] == 0
        assert r["documentos"] == 1

    async def test_nada_para_religar_nao_e_erro(self, fake_async_db, monkeypatch):
        import services.s3_folder_relink as alvo

        monkeypatch.setattr(alvo, "db", fake_async_db)
        r = await religar_apos_rename(ANTIGO, NOVO)
        assert r["erro"] is False
        assert r["processos"] == 0

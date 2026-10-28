"""A bancada do Index lista os MESMOS ficheiros da aba Documentos do processo (Out 2026).

O que se afirma, e porquê:
  · **A lista vem da pasta S3** (a do processo + a raiz do cliente): o que entrou na fase de lead não tinha
    registo e nunca aparecia ao Index.
  · **Uma chave sem registo ganha um** com o `process_id` deste processo (para ver, descarregar e analisar).
  · **Nada desaparece:** os registos do processo que a listagem não traz continuam; sem S3 fica a leitura antiga.
  · **Ver/Download** aceitam um registo da raiz do cliente gravado com outro processo, mas só se a chave
    estiver na pasta DESTE processo (uma chave de outro processo continua 404).
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from services import index_api as api
from services import index_document_content as conteudo
from services import index_ficheiros_do_s3 as fs3
from services import index_status as ist
from services import index_store as st

PID = "proc-1"
CLI = "cli-1"
RAIZ = f"Documentação Clientes/{CLI}"
PASTA = f"{RAIZ}/processos/{PID}"
INDEXADOR = {"id": "u-idx", "name": "Ivo Index", "role": "indexacao"}


def _listagem(*ficheiros):
    por_cat: dict = {}
    for cat, chave in ficheiros:
        por_cat.setdefault(cat, []).append({"name": chave.rsplit("/", 1)[-1], "path": chave})
    return {"files": por_cat, "base_path": PASTA}


def _s3(listagem):
    s3 = MagicMock()
    s3.is_configured.return_value = True
    s3.list_files.return_value = listagem
    return s3


def _patches(fake_db, s3):
    from services import audit_trail_service as audit
    from services import index_finalize as fin
    from services import index_jobs as jobs
    from services import index_substituicao as subst

    return [patch.object(m, "db", fake_db) for m in (api, st, ist, jobs, fin, subst, fs3, audit)] + [
        patch("database.db", fake_db), patch.object(fs3, "s3_service", s3)]


async def _bancada(fake_db, s3):
    ps = _patches(fake_db, s3)
    for p in ps:
        p.start()
    try:
        return await api.run_get_index_workstation(INDEXADOR, PID)
    finally:
        for p in reversed(ps):
            p.stop()


@pytest.fixture
async def processo(fake_async_db):
    await fake_async_db.processes.insert_one({"id": PID, "network_id": "r", "is_deleted": False, "client_id": CLI,
                                              "client_name": "Ana", "s3_folder": PASTA})
    return fake_async_db


class TestListaDaBancada:
    @pytest.mark.asyncio
    async def test_ficheiro_da_lead_sem_registo_aparece_e_fica_registado(self, processo):
        db = processo
        await db.document_metadata.insert_one({"id": "d1", "process_id": PID, "filename": "recibo.pdf",
                                               "s3_path": f"{PASTA}/Financeiros/recibo.pdf"})
        s3 = _s3(_listagem(("Financeiros", f"{PASTA}/Financeiros/recibo.pdf"),
                           ("Pessoais", f"{RAIZ}/Pessoais/cc.pdf")))
        r = await _bancada(db, s3)

        nomes = [f["filename"] for f in r["files"]]
        assert nomes == ["recibo.pdf", "cc.pdf"]
        novo = await db.document_metadata.find_one({"s3_path": f"{RAIZ}/Pessoais/cc.pdf"})
        assert novo["process_id"] == PID and novo["id"] and novo["registered_from"] == "bancada_index_s3"
        assert r["process"]["documents_total"] == 2

    @pytest.mark.asyncio
    async def test_registo_da_raiz_com_outro_processo_aparece_sem_duplicar(self, processo):
        db = processo
        chave = f"{RAIZ}/Pessoais/cc.pdf"
        await db.document_metadata.insert_one({"id": "d-outro", "process_id": "proc-2", "filename": "cc.pdf", "s3_path": chave})
        r = await _bancada(db, _s3(_listagem(("Pessoais", chave))))

        assert [f["id"] for f in r["files"]] == ["d-outro"]
        assert len(await db.document_metadata.find({"s3_path": chave}).to_list(10)) == 1

    @pytest.mark.asyncio
    async def test_abrir_duas_vezes_nao_cria_registos_repetidos(self, processo):
        db = processo
        s3 = _s3(_listagem(("Outros", f"{PASTA}/x.pdf")))
        a = await _bancada(db, s3)
        b = await _bancada(db, s3)
        assert a["files"][0]["id"] == b["files"][0]["id"]
        assert len(await db.document_metadata.find({"s3_path": f"{PASTA}/x.pdf"}).to_list(10)) == 1

    @pytest.mark.asyncio
    async def test_registos_do_processo_fora_da_listagem_nao_desaparecem(self, processo):
        db = processo
        await db.document_metadata.insert_one({"id": "d-velho", "process_id": PID, "filename": "velho.pdf",
                                               "s3_path": "outra/pasta/velho.pdf"})
        r = await _bancada(db, _s3(_listagem(("Outros", f"{PASTA}/x.pdf"))))
        assert sorted(f["filename"] for f in r["files"]) == ["velho.pdf", "x.pdf"]

    @pytest.mark.asyncio
    async def test_sem_s3_fica_a_leitura_antiga(self, processo):
        db = processo
        await db.document_metadata.insert_one({"id": "d1", "process_id": PID, "filename": "a.pdf", "s3_path": f"{PASTA}/a.pdf"})
        s3 = _s3(None)
        s3.is_configured.return_value = False
        r = await _bancada(db, s3)
        assert [f["id"] for f in r["files"]] == ["d1"]
        s3.list_files.assert_not_called()

    @pytest.mark.asyncio
    async def test_listagem_que_rebenta_nao_parte_a_bancada(self, processo):
        db = processo
        await db.document_metadata.insert_one({"id": "d1", "process_id": PID, "filename": "a.pdf", "s3_path": f"{PASTA}/a.pdf"})
        s3 = _s3(None)
        s3.list_files.side_effect = RuntimeError("s3 em baixo")
        r = await _bancada(db, s3)
        assert [f["id"] for f in r["files"]] == ["d1"]


class TestVerEDescarregar:
    async def _pedir(self, db, document_id):
        servir = AsyncMock(return_value="bytes")
        with patch.object(conteudo, "db", db), patch.object(conteudo, "servir_ficheiro_do_s3", servir), \
                patch.object(conteudo, "assert_can_view_process_documents", AsyncMock()), \
                patch.object(conteudo, "fronteira_levantada", return_value=True), \
                patch("services.financial_validation._exigir_posse_do_comprovativo", AsyncMock()):
            return await conteudo.run_conteudo_do_ficheiro_do_processo(INDEXADOR, PID, document_id)

    @pytest.mark.asyncio
    async def test_registo_da_raiz_do_cliente_com_outro_processo_abre(self, processo):
        db = processo
        await db.document_metadata.insert_one({"id": "d-raiz", "process_id": "proc-2", "filename": "cc.pdf",
                                               "s3_path": f"{RAIZ}/Pessoais/cc.pdf"})
        assert await self._pedir(db, "d-raiz") == "bytes"

    @pytest.mark.asyncio
    async def test_ficheiro_da_pasta_de_outro_processo_continua_404(self, processo):
        db = processo
        await db.document_metadata.insert_one({"id": "d-alheio", "process_id": "proc-2", "filename": "r.pdf",
                                               "s3_path": f"{RAIZ}/processos/proc-2/Financeiros/r.pdf"})
        with pytest.raises(HTTPException) as e:
            await self._pedir(db, "d-alheio")
        assert e.value.status_code == 404

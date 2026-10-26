"""Os comprovativos do cliente substituídos pelos do Index, contra um MongoDB REAL (Out 2026).

O que se afirma aqui é o que a regra pura não vê: que cada leitor (a análise, os metadados profissionais, o
motor financeiro, a bancada) deixa de contar o recibo do cliente LOGO que o Index carrega o dele, que o envio
do próprio 2.º cliente (registo `documents` do Portal) fica com o 2.º titular, e que sem Index nada muda.
S3 e modelo são falseados NA FRONTEIRA, como no `test_index_motor_mongo`.
"""
from __future__ import annotations

import os
import uuid
from unittest.mock import patch

import pytest
import pytest_asyncio
from motor.motor_asyncio import AsyncIOMotorClient

from services import financial_engine as fe
from services import index_api as api
from services import index_jobs as jobs
from services import index_status as ist
from services import index_store as st
from services import index_substituicao as sub
from services import process_ai_log as ailog
from services import task_log_service as tls
from services.background_tasks import aguardar_tarefas_pendentes

pytestmark = pytest.mark.asyncio

USER = {"id": "u-index", "name": "Ivo Index", "role": "indexacao"}
PID = "proc-sub"
S3: dict[str, bytes] = {}


@pytest_asyncio.fixture
async def bd(monkeypatch):
    url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    cliente = AsyncIOMotorClient(url, serverSelectionTimeoutMS=2000)
    try:
        await cliente.admin.command("ping")
    except Exception:
        cliente.close()
        pytest.skip("MongoDB não disponível")
    base = cliente[f"test_index_subst_{uuid.uuid4().hex[:8]}"]
    from services import push_notifications as push
    from services import realtime_notifications as rt

    for modulo in (jobs, st, ist, ailog, tls, rt, push, sub, fe, api):
        monkeypatch.setattr(modulo, "db", base)
    monkeypatch.setattr("database.db", base)
    monkeypatch.setenv("INDEX_AI_PROVIDER", "mock")
    await base.processes.insert_one({
        "id": PID, "process_number": 7, "client_name": "Ana Cliente", "network_id": "rede-A",
        "is_indexed": False, "index_status": "in_review", "status": "indexacao", "assigned_indexacao_id": "u-index",
    })
    yield base
    await aguardar_tarefas_pendentes()
    await cliente.drop_database(base.name)
    cliente.close()


@pytest.fixture(autouse=True)
def s3_falso():
    S3.clear()

    async def ler(caminho):
        return (S3[caminho], None) if caminho in S3 else (None, "ilegivel")

    with patch.object(jobs, "_ler_ficheiro", ler):
        yield


async def doc(bd, nome, *, sub_=None, categoria=None, **extra):
    id_ = str(uuid.uuid4())
    caminho = f"Documentação Clientes/{PID}/{nome}"
    S3[caminho] = nome.encode()
    await bd.document_metadata.insert_one({
        "id": id_, "process_id": PID, "s3_path": caminho, "filename": nome,
        "ai_category": categoria, "ai_subcategory": sub_, **extra,
    })
    return id_


async def recibo(bd, nome, **extra):
    return await doc(bd, nome, sub_="Recibo de Vencimento", categoria="Financeiros", **extra)


async def extrato(bd, nome, **extra):
    return await doc(bd, nome, sub_="Extrato Bancário", categoria="Bancários", **extra)


async def analisar():
    await jobs.iniciar_analise(PID, USER)
    await aguardar_tarefas_pendentes()


class TestLogoNoPrimeiroUpload:
    async def test_o_recibo_do_cliente_sai_e_o_extrato_fica(self, bd):
        c_rec = await recibo(bd, "scan_cliente.pdf")
        c_ext = await extrato(bd, "extrato_cliente.pdf")
        assert await sub.ids_substituidos(PID) == set()
        i_rec = await recibo(bd, "recibo_validado.pdf", uploaded_by_index=True)
        assert await sub.ids_substituidos(PID) == {c_rec}
        assert c_ext not in await sub.ids_substituidos(PID) and i_rec not in await sub.ids_substituidos(PID)

    async def test_a_analise_nao_le_o_substituido(self, bd):
        c_rec = await recibo(bd, "scan_cliente.pdf")
        await recibo(bd, "recibo_validado.pdf", uploaded_by_index=True)
        await analisar()
        assert (await bd.document_metadata.find_one({"id": c_rec})).get("index_facts") is None

    async def test_os_metadados_esquecem_o_que_o_cliente_ja_tinha_analisado(self, bd):
        c_rec = await recibo(bd, "scan_cliente.pdf")
        await analisar()
        meta = await bd.process_professional_metadata.find_one({"process_id": PID})
        assert meta["jobs"][0]["source_document_ids"] == [c_rec]
        i_rec = await recibo(bd, "recibo_validado.pdf", uploaded_by_index=True)
        await analisar()
        meta = await bd.process_professional_metadata.find_one({"process_id": PID})
        assert meta["jobs"][0]["source_document_ids"] == [i_rec]
        # a pesquisa avançada (projecção por documento) e os factos também já não o têm
        assert {d["id"] for d in await bd.process_index_documents.find({}).to_list(20)} == {i_rec}
        assert len(await st.factos_do_processo(PID)) == 1

    async def test_o_motor_financeiro_conta_so_o_do_index(self, bd):
        c_rec = await recibo(bd, "recibo_vencimento_cliente.pdf")
        i_rec = await recibo(bd, "recibo_vencimento_index.pdf", uploaded_by_index=True)
        ids = {d["id"] for d in await fe.collect_financial_documents(PID)}
        assert i_rec in ids and c_rec not in ids

    async def test_a_bancada_marca_o_substituido_e_nao_o_conta_por_analisar(self, bd):
        c_rec = await recibo(bd, "scan_cliente.pdf")
        await recibo(bd, "recibo_validado.pdf", uploaded_by_index=True)
        bancada = await api.run_get_index_workstation(USER, PID)
        por_id = {f["id"]: f for f in bancada["files"]}
        assert por_id[c_rec]["superseded"] is True
        assert sum(1 for f in bancada["files"] if f["superseded"]) == 1
        assert bancada["process"]["documents_to_analyse"] == 1
        assert bancada["process"]["titulares"] == []          # um só comprador: nada a escolher


class TestSegundoTitular:
    async def _dois_titulares(self, bd):
        await bd.processes.update_one({"id": PID}, {"$set": {"second_client_id": "cli-2", "second_client_name": "Bruno Dias"}})

    async def test_o_do_1o_titular_nao_esconde_o_envio_do_2o_cliente(self, bd):
        await self._dois_titulares(bd)
        c1 = await recibo(bd, "recibo_ana.pdf")
        c2 = await recibo(bd, "recibo_bruno.pdf")
        # o 2.º titular enviou-o pelo Portal: o registo do envio tem o client_id dele
        await bd.documents.insert_one({"id": "d2", "s3_path": f"Documentação Clientes/{PID}/recibo_bruno.pdf",
                                       "client_id": "cli-2", "source": "client_portal"})
        await recibo(bd, "recibo_ana_validado.pdf", uploaded_by_index=True, titular="titular1")
        assert await sub.ids_substituidos(PID) == {c1}
        await recibo(bd, "recibo_bruno_validado.pdf", uploaded_by_index=True, titular="titular2")
        assert await sub.ids_substituidos(PID) == {c1, c2}

    async def test_a_bancada_oferece_os_titulares_e_diz_de_quem_e_cada_ficheiro(self, bd):
        await self._dois_titulares(bd)
        c1 = await recibo(bd, "recibo_ana.pdf")
        i2 = await recibo(bd, "recibo_bruno_validado.pdf", uploaded_by_index=True, titular="titular2")
        bancada = await api.run_get_index_workstation(USER, PID)
        assert [t["id"] for t in bancada["process"]["titulares"]] == ["titular1", "titular2"]
        assert bancada["process"]["titulares"][1]["nome"] == "Bruno Dias"
        por_id = {f["id"]: f for f in bancada["files"]}
        assert por_id[c1]["titular"] == "titular1" and por_id[i2]["titular"] == "titular2"
        assert por_id[c1]["superseded"] is False


class TestSemIndex:
    async def test_via_verde_nada_muda(self, bd):
        await bd.processes.update_one({"id": PID}, {"$set": {"skip_index": True}})
        c_rec = await recibo(bd, "recibo_vencimento_cliente.pdf")
        await recibo(bd, "recibo_vencimento_outro.pdf", uploaded_by_index=True)
        assert await sub.ids_substituidos(PID) == set()
        assert c_rec in {d["id"] for d in await fe.collect_financial_documents(PID)}

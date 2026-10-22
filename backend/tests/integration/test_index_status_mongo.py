"""`index_status` contra um MongoDB REAL (Lote 12, Fase 1).

Real porque o duplo de Mongo não prova o que aqui importa: a semântica de
`$ne`/`$exists` sobre campos ausentes (a fila tem de apanhar o legado), os
índices ÚNICOS (incluindo o parcial de «um job activo por processo e tipo») e a
migração sobre documentos reais.
"""
from __future__ import annotations

import os
import uuid

import pytest
import pytest_asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import DuplicateKeyError

from services import index_status as ist
from services import index_status_migration as mig
from services.db_indexes import INDEX_DEFINITIONS

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def bd():
    url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    cliente = AsyncIOMotorClient(url, serverSelectionTimeoutMS=2000)
    try:
        await cliente.admin.command("ping")
    except Exception:
        cliente.close()
        pytest.skip("MongoDB não disponível")
    base = cliente[f"test_index_status_{uuid.uuid4().hex[:8]}"]
    yield base
    await cliente.drop_database(base.name)
    cliente.close()


async def _criar(base, colecao: str, nome: str) -> None:
    """Cria UM índice a partir da DECLARAÇÃO de produção (`INDEX_DEFINITIONS`)."""
    definicao = next(i for i in INDEX_DEFINITIONS[colecao] if i["name"] == nome)
    extra = {k: v for k, v in definicao.items() if k not in {"keys", "name"}}
    await base[colecao].create_index(definicao["keys"], name=nome, **extra)


PROCESSOS = [
    {"id": "legado-novo"},                                              # sem nenhum campo
    {"id": "legado-false", "is_indexed": False},
    {"id": "pending", "index_status": "pending", "is_indexed": False},
    {"id": "em-revisao", "index_status": "in_review", "is_indexed": False},
    {"id": "indexado", "index_status": "indexed", "is_indexed": True},
    {"id": "indexado-legado", "is_indexed": True},                      # sem index_status
    {"id": "dispensado", "skip_index": True, "index_status": "indexed", "index_skipped": True},
    {"id": "dispensado-legado", "skip_index": True},                    # sem index_status
    {"id": "indexado-a-rever", "is_indexed": True, "index_status": "indexed", "has_pending_review": True},
    {"id": "indexado-ok", "is_indexed": True, "index_status": "indexed", "has_pending_review": False},
]


async def _ids(base, condicao) -> set[str]:
    docs = await base.processes.find(condicao, {"_id": 0, "id": 1}).to_list(100)
    return {d["id"] for d in docs}


class TestAFilaApanhaOLegado:
    async def test_fila_de_espera(self, bd):
        await bd.processes.insert_many([dict(p) for p in PROCESSOS])
        assert await _ids(bd, ist.condicao_da_fila("pending")) == {
            "legado-novo", "legado-false", "pending", "em-revisao",
        }

    async def test_a_fila_nunca_inclui_dispensados_nem_indexados(self, bd):
        await bd.processes.insert_many([dict(p) for p in PROCESSOS])
        fila = await _ids(bd, ist.condicao_da_fila("pending"))
        assert not fila & {"indexado", "indexado-legado", "dispensado", "dispensado-legado"}

    async def test_revisoes_pendentes(self, bd):
        await bd.processes.insert_many([dict(p) for p in PROCESSOS])
        assert await _ids(bd, ist.condicao_da_fila("reviews")) == {"indexado-a-rever"}

    async def test_aba_desconhecida_nao_devolve_nada(self, bd):
        await bd.processes.insert_many([dict(p) for p in PROCESSOS])
        assert await _ids(bd, ist.condicao_da_fila("tudo")) == set()

    async def test_a_condicao_da_fila_concorda_com_a_derivacao(self, bd):
        # a condição Mongo e a função pura são a MESMA pergunta: não podem divergir
        await bd.processes.insert_many([dict(p) for p in PROCESSOS])
        na_fila = await _ids(bd, ist.condicao_da_fila("pending"))
        por_derivacao = {
            p["id"] for p in PROCESSOS
            if ist.derivar_estado(p)["index_status"] in ist.ESTADOS_NA_FILA
        }
        assert na_fila == por_derivacao


class TestTransicoesAtomicas:
    async def test_corrida_de_varios_pedidos_arranca_uma_so_vez(self, bd):
        import asyncio
        from unittest.mock import patch

        await bd.processes.insert_one({"id": "p", "index_status": "pending", "assigned_indexacao_id": "u1"})
        with patch.object(ist, "db", bd):
            r = await asyncio.gather(*(ist.registar_trabalho("p", "u1") for _ in range(6)))
        assert sum(1 for x in r if x["iniciado"]) == 1
        assert all(x["registado"] for x in r)
        doc = await bd.processes.find_one({"id": "p"})
        assert doc["index_status"] == "in_review" and doc["index_work_started_at"] and doc["index_last_activity_at"]

    async def test_sobre_legado_sem_campo_de_estado(self, bd):
        from unittest.mock import patch

        await bd.processes.insert_one({"id": "p", "assigned_indexacao_id": "u1"})
        with patch.object(ist, "db", bd):
            assert (await ist.registar_trabalho("p", "u1"))["iniciado"] is True

    async def test_so_o_atribuido_conta(self, bd):
        from unittest.mock import patch

        await bd.processes.insert_one({"id": "p", "index_status": "pending", "assigned_indexacao_id": "u1"})
        with patch.object(ist, "db", bd):
            assert (await ist.registar_trabalho("p", "u2"))["registado"] is False
        assert (await bd.processes.find_one({"id": "p"}))["index_status"] == "pending"


class TestMigracaoReal:
    async def test_converge_numa_passagem_e_a_segunda_escreve_zero(self, bd):
        await bd.processes.insert_many([dict(p) for p in PROCESSOS[:8]])
        docs = await mig.ler_processos(bd)
        assert await mig.aplicar(bd, docs) > 0
        docs = await mig.ler_processos(bd)
        assert mig.resumo(docs)["a_escrever"] == 0
        assert await mig.aplicar(bd, docs) == 0
        por_id = {d["id"]: d for d in docs}
        assert por_id["legado-novo"]["index_status"] == "pending"
        assert por_id["indexado-legado"]["index_status"] == "indexed"
        assert por_id["dispensado-legado"]["index_status"] == "indexed"
        assert por_id["dispensado-legado"]["index_skipped"] is True

    async def test_migracao_nao_muda_is_indexed_nem_skip_index(self, bd):
        await bd.processes.insert_many([dict(p) for p in PROCESSOS])
        antes = {p["id"]: (p.get("is_indexed"), p.get("skip_index")) for p in PROCESSOS}
        await mig.aplicar(bd, await mig.ler_processos(bd))
        depois = {
            d["id"]: (d.get("is_indexed"), d.get("skip_index"))
            for d in await bd.processes.find({}, {"_id": 0}).to_list(100)
        }
        assert depois == antes

    async def test_dispensado_depois_de_migrar_continua_fora_da_fila(self, bd):
        await bd.processes.insert_many([dict(p) for p in PROCESSOS])
        await mig.aplicar(bd, await mig.ler_processos(bd))
        assert "dispensado-legado" not in await _ids(bd, ist.condicao_da_fila("pending"))


class TestIndicesUnicos:
    async def test_um_processo_um_documento_de_metadados(self, bd):
        await _criar(bd, "process_professional_metadata", "idx_prof_meta_processo")
        await bd.process_professional_metadata.insert_one({"process_id": "p1"})
        with pytest.raises(DuplicateKeyError):
            await bd.process_professional_metadata.insert_one({"process_id": "p1"})
        await bd.process_professional_metadata.insert_one({"process_id": "p2"})

    async def test_um_nif_uma_entidade(self, bd):
        await _criar(bd, "employers", "idx_employers_nif")
        await bd.employers.insert_one({"nif": "501964843", "name": "Acme"})
        with pytest.raises(DuplicateKeyError):
            await bd.employers.insert_one({"nif": "501964843", "name": "Outra"})

    async def test_um_job_activo_por_processo_e_tipo(self, bd):
        await _criar(bd, "task_logs", "idx_index_job_activo_unico")
        await bd.task_logs.insert_one({"id": "1", "index_job_key": "p1:INDEX_ANALYSIS"})
        with pytest.raises(DuplicateKeyError):
            await bd.task_logs.insert_one({"id": "2", "index_job_key": "p1:INDEX_ANALYSIS"})
        # outro tipo, ou outro processo, convivem
        await bd.task_logs.insert_one({"id": "3", "index_job_key": "p1:INDEX_SANITIZE"})
        await bd.task_logs.insert_one({"id": "4", "index_job_key": "p2:INDEX_ANALYSIS"})

    async def test_o_indice_parcial_ignora_tarefas_alheias_e_jobs_terminados(self, bd):
        # sem este comportamento todo o `task_logs` (que não tem a chave) colidiria em `null`
        await _criar(bd, "task_logs", "idx_index_job_activo_unico")
        for i in range(5):
            await bd.task_logs.insert_one({"id": f"x{i}", "task_type": "PDF_GEN"})
        await bd.task_logs.insert_one({"id": "a", "index_job_key": "p:INDEX_ANALYSIS"})
        # terminar = retirar a chave: o seguinte pode nascer
        await bd.task_logs.update_one({"id": "a"}, {"$unset": {"index_job_key": ""}})
        await bd.task_logs.insert_one({"id": "b", "index_job_key": "p:INDEX_ANALYSIS"})

    async def test_os_indices_da_fila_criam_se(self, bd):
        await _criar(bd, "processes", "idx_index_fila")
        await _criar(bd, "processes", "idx_index_revisoes")
        nomes = {i["name"] async for i in bd.processes.list_indexes()}
        assert {"idx_index_fila", "idx_index_revisoes"} <= nomes

    async def test_a_fila_usa_o_indice_composto(self, bd):
        await _criar(bd, "processes", "idx_index_fila")
        await bd.processes.insert_many([
            {"id": str(i), "network_id": "n1", "index_status": "pending", "created_at": str(i)}
            for i in range(50)
        ])
        plano = await bd.command(
            "explain",
            {"find": "processes", "filter": {"network_id": "n1", "index_status": "pending"},
             "sort": {"created_at": -1}},
            verbosity="queryPlanner",
        )
        texto = str(plano["queryPlanner"]["winningPlan"])
        assert "idx_index_fila" in texto and "COLLSCAN" not in texto

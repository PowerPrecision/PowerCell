"""A API do Index contra um MongoDB REAL (Lote 12, Fase 3).

Real porque o que importa é o que um duplo esconde: a semântica do `$and`/`$or`/`$ne`/`$exists`
da fila (documentos sem `index_status`, que a migração ainda não tocou) combinada com a condição
de REDE de verdade, a paginação e a ordenação, e o `$regex` do directório global de entidades.
"""
from __future__ import annotations

import os
import uuid
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from motor.motor_asyncio import AsyncIOMotorClient

from services import index_api as api
from services import index_jobs as jobs
from services import index_status as ist
from services import index_store as st
from services.tenant_network import TenantScope

pytestmark = pytest.mark.asyncio

USER = {"id": "u-index", "name": "Ivo", "role": "indexacao"}
NIF = "501964843"


@pytest_asyncio.fixture
async def bd(monkeypatch):
    url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    cliente = AsyncIOMotorClient(url, serverSelectionTimeoutMS=2000)
    try:
        await cliente.admin.command("ping")
    except Exception:
        cliente.close()
        pytest.skip("MongoDB não disponível")
    base = cliente[f"test_index_api_{uuid.uuid4().hex[:8]}"]
    for modulo in (api, st, ist, jobs):
        monkeypatch.setattr(modulo, "db", base)
    monkeypatch.setattr("database.db", base)
    yield base
    await cliente.drop_database(base.name)
    cliente.close()


def _ambito(*redes):
    return patch("services.tenant_network.resolve_vista_scope", AsyncMock(return_value=TenantScope(network_ids=redes)))


async def _processos(bd, n_a=3, n_b=2):
    docs = []
    for i in range(n_a):
        docs.append({"id": f"a{i}", "network_id": "rede-A", "client_name": f"Ana {i}", "process_number": 100 + i,
                     "is_deleted": False, "created_at": f"2026-10-0{i + 1}"})  # SEM index_status: legado
    for i in range(n_b):
        docs.append({"id": f"b{i}", "network_id": "rede-B", "client_name": f"Bia {i}", "process_number": 200 + i,
                     "is_deleted": False, "created_at": f"2026-10-0{i + 1}"})
    docs += [
        {"id": "a-idx", "network_id": "rede-A", "client_name": "Indexada", "is_deleted": False, "is_indexed": True,
         "index_status": "indexed", "has_pending_review": True, "indexed_at": "2026-10-10"},
        {"id": "a-eli", "network_id": "rede-A", "client_name": "Eliminada", "is_deleted": True},
        {"id": "a-vv", "network_id": "rede-A", "client_name": "ViaVerde", "is_deleted": False, "skip_index": True},
    ]
    await bd.processes.insert_many(docs)


class TestAFilaContraMongoReal:
    async def test_legado_sem_index_status_esta_na_fila_da_sua_rede(self, bd):
        await _processos(bd)
        with _ambito("rede-A"):
            r = await api.run_get_index_queue(USER, tab="pending")
        assert {p["id"] for p in r["items"]} == {"a0", "a1", "a2"}
        assert all(p["index_status"] == "pending" for p in r["items"])

    async def test_a_rede_A_nunca_ve_a_B_e_vice_versa(self, bd):
        await _processos(bd)
        with _ambito("rede-A"):
            a = await api.run_get_index_queue(USER, tab="pending")
        with _ambito("rede-B"):
            b = await api.run_get_index_queue(USER, tab="pending")
        assert not ({p["id"] for p in a["items"]} & {p["id"] for p in b["items"]})
        assert {p["id"] for p in b["items"]} == {"b0", "b1"}

    async def test_uma_rede_convidada_ve_o_processo_partilhado(self, bd):
        await _processos(bd)
        await bd.processes.update_one({"id": "a0"}, {"$set": {"partner_network_ids": ["rede-B"]}})
        with _ambito("rede-B"):
            r = await api.run_get_index_queue(USER, tab="pending")
        assert "a0" in {p["id"] for p in r["items"]} and "a1" not in {p["id"] for p in r["items"]}

    async def test_paginacao_e_ordem(self, bd):
        await _processos(bd, n_a=5)
        with _ambito("rede-A"):
            p1 = await api.run_get_index_queue(USER, tab="pending", page=1, size=2)
            p3 = await api.run_get_index_queue(USER, tab="pending", page=3, size=2)
        assert p1["total"] == 5 and [p["id"] for p in p1["items"]] == ["a0", "a1"]
        assert [p["id"] for p in p3["items"]] == ["a4"]

    async def test_pesquisa_por_nome_e_escapada(self, bd):
        await _processos(bd)
        with _ambito("rede-A"):
            r = await api.run_get_index_queue(USER, tab="pending", q="ana 1")
            vazio = await api.run_get_index_queue(USER, tab="pending", q=".*")
        assert [p["id"] for p in r["items"]] == ["a1"]
        assert vazio["items"] == []  # `.*` é texto, não expressão regular

    async def test_revisoes_so_indexados_com_campos_a_rever(self, bd):
        await _processos(bd)
        with _ambito("rede-A"):
            r = await api.run_get_index_queue(USER, tab="reviews")
        assert [p["id"] for p in r["items"]] == ["a-idx"]

    async def test_via_verde_e_eliminados_fora_da_fila(self, bd):
        await _processos(bd)
        with _ambito("rede-A"):
            r = await api.run_get_index_queue(USER, tab="pending")
        assert not {"a-vv", "a-eli", "a-idx"} & {p["id"] for p in r["items"]}


class TestEdicaoEDirectorioContraMongoReal:
    async def test_editar_um_nif_alimenta_o_directorio_global_e_a_fila_de_revisoes(self, bd):
        await bd.processes.insert_one({"id": "p", "network_id": "rede-A", "is_deleted": False, "is_indexed": True,
                                       "has_pending_review": True, "indexed_at": "2026-10-10"})
        await bd.process_professional_metadata.insert_one({"process_id": "p", "jobs": [{
            "job_id": "job_a",
            "employer_nif": {"value": None, "needs_review": True},
            "employer_name": {"value": "Acme Lda", "needs_review": False},
            "job_title": {"value": "Eng.", "needs_review": False},
            "net_salary": {"value": "1000", "needs_review": False},
            "contract_type": {"value": "efetivo", "needs_review": False},
            "source_document_ids": ["d1"]}]})
        with _ambito("rede-A"):
            antes = await api.run_get_index_queue(USER, tab="reviews")
            r = await api.run_edit_professional_job(USER, "p", "job_a", {"employer_nif": NIF})
            depois = await api.run_get_index_queue(USER, tab="reviews")
        assert [p["id"] for p in antes["items"]] == ["p"]
        assert r["has_pending_review"] is False and depois["items"] == []
        achadas = await api.run_search_employers(USER, "acme")
        assert achadas["items"] == [{"nif": NIF, "name": "Acme Lda"}]

    async def test_o_directorio_e_pesquisavel_de_qualquer_rede_mas_so_leva_nif_e_nome(self, bd):
        await bd.employers.insert_one({"nif": NIF, "name": "Acme Lda", "name_normalizado": "acme lda"})
        r = await api.run_search_employers(USER, NIF[:5])
        assert r["items"] == [{"nif": NIF, "name": "Acme Lda"}]

    async def test_pesquisa_com_regex_hostil_e_texto(self, bd):
        await bd.employers.insert_one({"nif": NIF, "name": "Acme Lda", "name_normalizado": "acme lda"})
        assert (await api.run_search_employers(USER, ".*"))["items"] == []
        assert (await api.run_search_employers(USER, "(("))["items"] == []

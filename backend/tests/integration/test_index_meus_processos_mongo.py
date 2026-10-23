"""«Os Meus Processos» do Index: a fila filtrada pelo indexador ATRIBUÍDO a quem pergunta — MongoDB real.

Real porque o perigo é a semântica de `{campo: None}`: um `assigned_indexacao_id: None` casa com TODOS os
processos por atribuir (e com os que não têm o campo), isto é, com a lista de ninguém — e um duplo não a reproduz.
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
from services import process_owner as dono
from services import workflow_phases as fases
from services.tenant_network import TenantScope

pytestmark = pytest.mark.asyncio

EU = {"id": "ix1", "name": "Ana", "role": "indexacao"}
OUTRO = {"id": "ix2", "name": "Bruno", "role": "indexacao"}


@pytest_asyncio.fixture
async def bd(monkeypatch):
    url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    cliente = AsyncIOMotorClient(url, serverSelectionTimeoutMS=2000)
    try:
        await cliente.admin.command("ping")
    except Exception:
        cliente.close()
        pytest.skip("MongoDB não disponível")
    base = cliente[f"test_index_meus_{uuid.uuid4().hex[:8]}"]
    for modulo in (api, st, ist, jobs, fases, dono):
        monkeypatch.setattr(modulo, "db", base)
    monkeypatch.setattr("database.db", base)
    monkeypatch.delenv("TENANT_DEFAULT_NETWORK_ID", raising=False)
    await base.workflow_statuses.insert_many([
        {"name": "novo", "order": 1, "is_active": True}, {"name": "concluido", "order": 2, "is_active": False},
    ])
    fases.invalidar_cache_de_fases()
    await base.processes.insert_many([
        _p("meu-pendente", "ix1", "pending"),
        _p("meu-em-tratamento", "ix1", "in_review"),
        _p("do-outro", "ix2", "pending"),
        _p("por-atribuir", None, "pending"),
        {"id": "sem-campo", "network_id": "rede-A", "status": "novo", "client_name": "x", "process_number": 9,
         "is_deleted": False, "is_indexed": False, "index_status": "pending", "created_at": "2026-10-02"},
        _p("meu-de-outra-rede", "ix1", "pending", network_id="rede-B"),
        _p("meu-fechado", "ix1", "pending", status="concluido"),
        _p("meu-indexado", "ix1", "indexed", is_indexed=True, has_pending_review=True, indexed_at="2026-10-05"),
    ])
    yield base
    fases.invalidar_cache_de_fases()
    await cliente.drop_database(base.name)
    cliente.close()


def _p(pid, indexador, estado, **extra):
    doc = {"id": pid, "network_id": "rede-A", "status": "novo", "client_name": pid, "process_number": 1,
           "is_deleted": False, "is_indexed": False, "index_status": estado, "created_at": "2026-10-01",
           "assigned_indexacao_id": indexador, **extra}
    return doc


def _ambito():
    return patch("services.tenant_network.resolve_vista_scope", AsyncMock(return_value=TenantScope(network_ids=("rede-A",))))


async def _fila(utilizador, **kw):
    with _ambito():
        return await api.run_get_index_queue(utilizador, tab=kw.pop("tab", "pending"), **kw)


def _ids(r):
    return {p["id"] for p in r["items"]}


class TestOsMeusProcessos:
    async def test_so_os_atribuidos_a_quem_pergunta(self, bd):
        r = await _fila(EU, mine=True)
        assert _ids(r) == {"meu-pendente", "meu-em-tratamento"}
        assert r["total"] == 2

    async def test_sem_a_bandeira_a_fila_e_a_de_toda_a_rede(self, bd):
        r = await _fila(EU)
        assert {"meu-pendente", "do-outro", "por-atribuir", "sem-campo"} <= _ids(r)

    async def test_outro_indexador_ve_os_dele_e_nunca_os_meus(self, bd):
        assert _ids(await _fila(OUTRO, mine=True)) == {"do-outro"}

    async def test_sem_id_de_utilizador_nao_casa_com_os_por_atribuir(self, bd):
        """O perigo: `assigned_indexacao_id: None` casa com os processos de ninguém."""
        for sem_id in ({"role": "indexacao"}, {"id": None, "role": "indexacao"}, {"id": "", "role": "indexacao"}):
            r = await _fila(sem_id, mine=True)
            assert _ids(r) == set() and r["total"] == 0, sem_id

    async def test_a_fronteira_de_rede_continua_a_valer(self, bd):
        assert "meu-de-outra-rede" not in _ids(await _fila(EU, mine=True))

    async def test_so_activos_e_so_por_tratar_nesta_aba(self, bd):
        ids = _ids(await _fila(EU, mine=True))
        assert "meu-fechado" not in ids and "meu-indexado" not in ids

    async def test_as_revisoes_tambem_se_filtram_por_mim(self, bd):
        r = await _fila(EU, mine=True, tab="reviews")
        assert _ids(r) == {"meu-indexado"}

    async def test_combina_com_o_estado_e_a_pesquisa(self, bd):
        assert _ids(await _fila(EU, mine=True, index_status="in_review")) == {"meu-em-tratamento"}
        assert _ids(await _fila(EU, mine=True, q="pendente")) == {"meu-pendente"}

    async def test_as_linhas_trazem_as_colunas_do_ecra(self, bd):
        (linha,) = [p for p in (await _fila(EU, mine=True))["items"] if p["id"] == "meu-pendente"]
        for campo in ("client_name", "process_number", "index_status", "documents_total", "index_alerts_open", "created_at"):
            assert campo in linha, campo
        assert "company" in linha

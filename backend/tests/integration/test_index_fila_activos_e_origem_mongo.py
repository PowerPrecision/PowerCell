"""A fila do Index: só processos ACTIVOS, e a empresa de ORIGEM de cada um (Out 2026) — MongoDB real.

Real porque o que se afirma é a semântica do `$or` por rede dona com `$nin` sobre um campo que pode
faltar (o carimbo e o `status` de um legado), combinada com o workflow POR REDE: um mesmo nome de fase
fecha numa rede e mantém-se activo noutra, e uma união de «terminais» esconderia trabalho real.
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

USER = {"id": "u-index", "name": "Ivo", "role": "indexacao"}


@pytest_asyncio.fixture
async def bd(monkeypatch):
    url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    cliente = AsyncIOMotorClient(url, serverSelectionTimeoutMS=2000)
    try:
        await cliente.admin.command("ping")
    except Exception:
        cliente.close()
        pytest.skip("MongoDB não disponível")
    base = cliente[f"test_index_fila_{uuid.uuid4().hex[:8]}"]
    for modulo in (api, st, ist, jobs, fases, dono):
        monkeypatch.setattr(modulo, "db", base)
    monkeypatch.setattr("database.db", base)
    monkeypatch.delenv("TENANT_DEFAULT_NETWORK_ID", raising=False)
    fases.invalidar_cache_de_fases()
    yield base
    fases.invalidar_cache_de_fases()
    await cliente.drop_database(base.name)
    cliente.close()


def _ambito(*redes):
    return patch("services.tenant_network.resolve_vista_scope", AsyncMock(return_value=TenantScope(network_ids=redes)))


async def _workflows(bd):
    """Modelo: `concluido` é terminal. Rede B tem o seu: aí `concluido` está ACTIVO e `arrumado` fecha."""
    await bd.workflow_statuses.insert_many([
        {"name": "novo", "order": 1, "is_active": True},
        {"name": "concluido", "order": 2, "is_active": False},
        {"name": "novo", "order": 1, "is_active": True, "network_id": "rede-B"},
        {"name": "concluido", "order": 2, "is_active": True, "network_id": "rede-B"},
        {"name": "arrumado", "order": 3, "is_active": False, "network_id": "rede-B"},
    ])
    fases.invalidar_cache_de_fases()


def _p(pid, rede, status, **extra):
    return {"id": pid, "network_id": rede, "status": status, "client_name": pid, "process_number": 1,
            "is_deleted": False, "created_at": "2026-10-01", **extra}


async def _fila(*redes, tab="pending"):
    with _ambito(*redes):
        return await api.run_get_index_queue(USER, tab=tab)


def _ids(r):
    return {p["id"] for p in r["items"]}


class TestSoProcessosActivos:
    async def test_um_processo_numa_fase_terminal_nao_e_trabalho_de_indexacao(self, bd):
        await _workflows(bd)
        await bd.processes.insert_many([_p("vivo", "rede-A", "novo"), _p("fechado", "rede-A", "concluido")])
        assert _ids(await _fila("rede-A")) == {"vivo"}

    async def test_o_workflow_e_o_da_rede_DONA(self, bd):
        """`concluido` fecha na rede A (modelo) e está ACTIVO na B: uma união escondia o da B."""
        await _workflows(bd)
        await bd.processes.insert_many([
            _p("a-fechado", "rede-A", "concluido"), _p("b-vivo", "rede-B", "concluido"),
            _p("b-fechado", "rede-B", "arrumado"), _p("b-novo", "rede-B", "novo"),
        ])
        assert _ids(await _fila("rede-B")) == {"b-vivo", "b-novo"}
        assert _ids(await _fila("rede-A")) == set()

    async def test_o_legado_sem_carimbo_e_sem_estado_continua_na_fila(self, bd):
        """Nada de `status` nem de rede (a migração ainda não tocou): não é «inactivo»."""
        await bd.processes.insert_one({"id": "velho", "client_name": "V", "is_deleted": False, "created_at": "2026-10-01"})
        # sem rede de omissão o legado não é de ninguém — com ela, é da rede de omissão
        os.environ["TENANT_DEFAULT_NETWORK_ID"] = "rede-A"
        try:
            with patch("services.tenant_network.resolve_vista_scope",
                       AsyncMock(return_value=TenantScope(network_ids=("rede-A",), inclui_rede_de_omissao=True))):
                r = await api.run_get_index_queue(USER, tab="pending")
        finally:
            del os.environ["TENANT_DEFAULT_NETWORK_ID"]
        assert _ids(r) == {"velho"}

    async def test_o_legado_por_carimbar_segue_o_workflow_da_rede_de_omissao(self, bd, monkeypatch):
        await _workflows(bd)
        monkeypatch.setenv("TENANT_DEFAULT_NETWORK_ID", "rede-B")
        await bd.processes.insert_many([
            {"id": "l-vivo", "status": "concluido", "is_deleted": False, "created_at": "2026-10-01", "client_name": "x"},
            {"id": "l-fechado", "status": "arrumado", "is_deleted": False, "created_at": "2026-10-02", "client_name": "y"},
        ])
        with patch("services.tenant_network.resolve_vista_scope",
                   AsyncMock(return_value=TenantScope(network_ids=("rede-B",), inclui_rede_de_omissao=True))):
            r = await api.run_get_index_queue(USER, tab="pending")
        # na rede de omissão (B) `concluido` está activo e `arrumado` fecha
        assert _ids(r) == {"l-vivo"}

    async def test_is_active_false_tambem_exclui(self, bd):
        await _workflows(bd)
        await bd.processes.insert_many([_p("on", "rede-A", "novo"), _p("off", "rede-A", "novo", is_active=False)])
        assert _ids(await _fila("rede-A")) == {"on"}

    async def test_vale_tambem_para_as_revisoes_pendentes(self, bd):
        await _workflows(bd)
        rev = {"is_indexed": True, "has_pending_review": True, "indexed_at": "2026-10-05"}
        await bd.processes.insert_many([_p("r-vivo", "rede-A", "novo", **rev), _p("r-fechado", "rede-A", "concluido", **rev)])
        assert _ids(await _fila("rede-A", tab="reviews")) == {"r-vivo"}

    async def test_o_total_conta_so_os_activos(self, bd):
        await _workflows(bd)
        await bd.processes.insert_many([_p("a", "rede-A", "novo"), _p("b", "rede-A", "novo"), _p("c", "rede-A", "concluido")])
        r = await _fila("rede-A")
        assert r["total"] == 2

    async def test_continua_dentro_da_rede_do_utilizador(self, bd):
        await _workflows(bd)
        await bd.processes.insert_many([_p("a", "rede-A", "novo"), _p("b", "rede-B", "novo")])
        assert _ids(await _fila("rede-A")) == {"a"}


class TestAEmpresaDeOrigem:
    async def test_cada_linha_diz_a_empresa_do_processo(self, bd):
        await _workflows(bd)
        await bd.processes.insert_many([
            _p("p1", "rede-A", "novo", company_name="Power Real Estate", company_id="c1", client_name="Ana"),
        ])
        (item,) = (await _fila("rede-A"))["items"]
        assert item["company"] == {"name": "Power Real Estate", "other_network": False}

    async def test_um_processo_partilhado_de_outra_rede_di_lo(self, bd):
        await _workflows(bd)
        await bd.processes.insert_one(_p("p1", "rede-A", "novo", company_name="Power", partner_network_ids=["rede-B"]))
        (item,) = (await _fila("rede-B"))["items"]
        assert item["company"] == {"name": "Power", "other_network": True}

    async def test_o_nome_vem_da_empresa_quando_o_carimbo_so_tem_o_id(self, bd):
        await _workflows(bd)
        await bd.companies.insert_one({"id": "c9", "name": "Precision", "network_id": "rede-A"})
        await bd.processes.insert_one(_p("p1", "rede-A", "novo", company_id="c9"))
        (item,) = (await _fila("rede-A"))["items"]
        assert item["company"]["name"] == "Precision"

    async def test_sem_empresa_determinavel_e_null_e_a_fila_nao_parte(self, bd):
        await _workflows(bd)
        await bd.processes.insert_one(_p("p1", "rede-sem-empresas", "novo"))
        r = await _fila("rede-sem-empresas")
        assert r["items"][0]["company"] is None

    async def test_o_dto_nao_leva_ids_nem_redes(self, bd):
        await _workflows(bd)
        await bd.processes.insert_one(_p("p1", "rede-A", "novo", company_name="Power", company_id="c1"))
        (item,) = (await _fila("rede-A"))["items"]
        assert set(item["company"]) == {"name", "other_network"}
        assert "network_id" not in item and "company_id" not in item

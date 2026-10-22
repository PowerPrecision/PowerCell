"""Ordenação e filtros da fila do Index (Out 2026) — MongoDB real.

Real porque o que se afirma é a COLAÇÃO (acentos, maiúsculas, números dentro de texto), a ordem estável da
paginação com datas repetidas, o `$nor` da origem e o legado sem `index_status`: nada disto o duplo em memória
prova. Os dados passam pelo `run_get_index_queue` de produção.
"""
from __future__ import annotations

import os
import uuid
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from fastapi import HTTPException
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
    base = cliente[f"test_index_ordem_{uuid.uuid4().hex[:8]}"]
    for modulo in (api, st, ist, jobs, fases, dono):
        monkeypatch.setattr(modulo, "db", base)
    monkeypatch.setattr("database.db", base)
    monkeypatch.delenv("TENANT_DEFAULT_NETWORK_ID", raising=False)
    fases.invalidar_cache_de_fases()
    await base.workflow_statuses.insert_many([
        {"name": "novo", "order": 1, "is_active": True}, {"name": "concluido", "order": 2, "is_active": False},
    ])
    fases.invalidar_cache_de_fases()
    yield base
    fases.invalidar_cache_de_fases()
    await cliente.drop_database(base.name)
    cliente.close()


def _ambito(*redes, vista=False):
    return patch(
        "services.tenant_network.resolve_vista_scope",
        AsyncMock(return_value=TenantScope(network_ids=redes, sem_fronteira=vista)),
    )


def _p(pid, rede="rede-A", **extra):
    base = {"id": pid, "network_id": rede, "status": "novo", "client_name": pid, "process_number": "1",
            "is_deleted": False, "created_at": "2026-10-01", "index_status": "pending"}
    base.update(extra)
    return base


async def _fila(*redes, tab="pending", **kw):
    with _ambito(*redes):
        return await api.run_get_index_queue(USER, tab=tab, **kw)


def _ids(r):
    return [p["id"] for p in r["items"]]


class TestOrdenacao:
    async def test_por_omissao_a_fila_e_a_entrada_mais_antiga_primeiro(self, bd):
        await bd.processes.insert_many([
            _p("novo", created_at="2026-10-09"), _p("velho", created_at="2026-10-01"), _p("meio", created_at="2026-10-05"),
        ])
        r = await _fila("rede-A")
        assert _ids(r) == ["velho", "meio", "novo"] and r["sort_by"] == "created_asc"

    async def test_created_desc(self, bd):
        await bd.processes.insert_many([_p("a", created_at="2026-10-01"), _p("b", created_at="2026-10-09")])
        assert _ids(await _fila("rede-A", sort_by="created_desc")) == ["b", "a"]

    async def test_as_revisoes_por_omissao_a_indexacao_mais_recente_primeiro(self, bd):
        for pid, quando in (("a", "2026-10-01"), ("b", "2026-10-09"), ("c", "2026-10-05")):
            await bd.processes.insert_one(_p(pid, is_indexed=True, index_status="indexed", has_pending_review=True, indexed_at=quando))
        r = await _fila("rede-A", tab="reviews")
        assert _ids(r) == ["b", "c", "a"] and r["sort_by"] == "indexed_desc"
        assert _ids(await _fila("rede-A", tab="reviews", sort_by="indexed_asc")) == ["a", "c", "b"]

    async def test_o_nome_ordena_sem_distinguir_maiusculas_nem_acentos(self, bd):
        for nome in ("zé", "Álvaro", "bruno", "Ana"):
            await bd.processes.insert_one(_p(nome, client_name=nome))
        assert _ids(await _fila("rede-A", sort_by="client_asc")) == ["Álvaro", "Ana", "bruno", "zé"]
        assert _ids(await _fila("rede-A", sort_by="client_desc")) == ["zé", "bruno", "Ana", "Álvaro"]

    async def test_o_numero_do_processo_ordena_numericamente(self, bd):
        for n in ("PROC-10", "PROC-9", "PROC-100", "PROC-2"):
            await bd.processes.insert_one(_p(n, process_number=n))
        assert _ids(await _fila("rede-A", sort_by="number_asc")) == ["PROC-2", "PROC-9", "PROC-10", "PROC-100"]

    async def test_por_alertas(self, bd):
        await bd.processes.insert_many([_p("a", index_alerts_open=3), _p("b", index_alerts_open=0), _p("c", index_alerts_open=7)])
        assert _ids(await _fila("rede-A", sort_by="alerts_desc")) == ["c", "a", "b"]

    async def test_por_empresa(self, bd):
        await bd.processes.insert_many([_p("a", company_name="Precision"), _p("b", company_name="Power"), _p("c", company_name="domus")])
        assert _ids(await _fila("rede-A", sort_by="company_asc")) == ["c", "b", "a"]

    async def test_a_paginacao_e_estavel_com_datas_repetidas(self, bd):
        """Sem desempate, dez processos com a mesma data repetiam ou saltavam linhas entre páginas."""
        await bd.processes.insert_many([_p(f"p{i:02d}", created_at="2026-10-01") for i in range(10)])
        vistos: list[str] = []
        for pagina in (1, 2, 3, 4):
            vistos += _ids(await _fila("rede-A", page=pagina, size=3, sort_by="created_asc"))
        assert vistos == [f"p{i:02d}" for i in range(10)]
        assert len(set(vistos)) == 10

    async def test_a_ordem_nunca_alarga_o_ambito(self, bd):
        await bd.processes.insert_many([_p("a", "rede-A"), _p("b", "rede-B")])
        assert _ids(await _fila("rede-A", sort_by="client_desc")) == ["a"]

    @pytest.mark.parametrize("valor", ["", "created", "created_sideways", "cliente_asc", "$where_asc", "client_asc; drop", "_asc"])
    async def test_valores_fora_da_lista_sao_422(self, bd, valor):
        if valor == "":
            pytest.skip("vazio = omissão")
        with pytest.raises(HTTPException) as e:
            await _fila("rede-A", sort_by=valor)
        assert e.value.status_code == 422

    async def test_indexed_so_ordena_as_revisoes(self, bd):
        with pytest.raises(HTTPException) as e:
            await _fila("rede-A", tab="pending", sort_by="indexed_asc")
        assert e.value.status_code == 422


class TestFiltros:
    async def test_por_estado_na_fila_de_espera(self, bd):
        await bd.processes.insert_many([
            _p("a", index_status="pending"), _p("b", index_status="in_review"),
            {k: v for k, v in _p("legado").items() if k != "index_status"},
        ])
        assert set(_ids(await _fila("rede-A", index_status="in_review"))) == {"b"}
        # o legado sem `index_status` lê-se como por indexar
        assert set(_ids(await _fila("rede-A", index_status="pending"))) == {"a", "legado"}

    async def test_o_estado_do_outro_separador_e_422(self, bd):
        for aba, valor in (("pending", "indexed"), ("reviews", "pending"), ("reviews", "in_review"), ("pending", "lixo")):
            with pytest.raises(HTTPException) as e:
                await _fila("rede-A", tab=aba, index_status=valor)
            assert e.value.status_code == 422, (aba, valor)

    async def test_indexed_nas_revisoes_e_o_que_ja_se_tem(self, bd):
        await bd.processes.insert_one(_p("a", is_indexed=True, index_status="indexed", has_pending_review=True, indexed_at="2026-10-09"))
        assert _ids(await _fila("rede-A", tab="reviews", index_status="indexed")) == ["a"]

    async def test_por_empresa(self, bd):
        await bd.processes.insert_many([
            _p("a", company_id="c-power", company_name="Power"), _p("b", company_id="c-prec", company_name="Precision"),
            _p("c", company_id="c-power", company_name="Power"),
        ])
        assert set(_ids(await _fila("rede-A", company_id="c-power"))) == {"a", "c"}

    async def test_uma_empresa_de_outra_rede_nunca_devolve_nada_nem_as_dela(self, bd):
        await bd.processes.insert_many([_p("a", "rede-A", company_id="c-a"), _p("b", "rede-B", company_id="c-b")])
        r = await _fila("rede-A", company_id="c-b")
        assert r["items"] == [] and r["total"] == 0

    async def test_origem_propria_e_partilhada(self, bd):
        await bd.processes.insert_many([
            _p("minha", "rede-A"), _p("deles", "rede-B", partner_network_ids=["rede-A"]), _p("alheia", "rede-B"),
        ])
        assert set(_ids(await _fila("rede-A"))) == {"minha", "deles"}
        assert _ids(await _fila("rede-A", origin="own")) == ["minha"]
        assert _ids(await _fila("rede-A", origin="shared")) == ["deles"]

    async def test_o_master_sem_fronteira_nao_tem_partilhados(self, bd):
        await bd.processes.insert_many([_p("a", "rede-A"), _p("b", "rede-B", partner_network_ids=["rede-A"])])
        with _ambito(vista=True):
            todos = await api.run_get_index_queue(USER, tab="pending", origin="own")
            partilhados = await api.run_get_index_queue(USER, tab="pending", origin="shared")
        assert set(_ids(todos)) == {"a", "b"} and partilhados["items"] == []

    async def test_origem_invalida_e_422(self, bd):
        with pytest.raises(HTTPException) as e:
            await _fila("rede-A", origin="todas")
        assert e.value.status_code == 422

    async def test_os_filtros_combinam_com_a_pesquisa_e_a_ordem(self, bd):
        await bd.processes.insert_many([
            _p("a", client_name="Ana Silva", company_id="c1", index_status="in_review", created_at="2026-10-01"),
            _p("b", client_name="Ana Costa", company_id="c1", index_status="in_review", created_at="2026-10-02"),
            _p("c", client_name="Ana Dias", company_id="c2", index_status="in_review"),
            _p("d", client_name="Rui", company_id="c1", index_status="in_review"),
        ])
        r = await _fila("rede-A", q="ana", company_id="c1", index_status="in_review", sort_by="created_desc")
        assert _ids(r) == ["b", "a"] and r["total"] == 2
        assert r["filters"] == {"index_status": "in_review", "company_id": "c1"}

    async def test_o_total_respeita_os_filtros(self, bd):
        await bd.processes.insert_many([_p(f"a{i}", company_id="c1") for i in range(4)] + [_p("x", company_id="c2")])
        r = await _fila("rede-A", company_id="c1", page=1, size=2)
        assert r["total"] == 4 and len(r["items"]) == 2


class TestAsOpcoesDoFiltro:
    async def test_as_empresas_da_fila_com_contagem_e_sem_filtros(self, bd):
        await bd.processes.insert_many([
            _p("a", company_id="c-power", company_name="Power"), _p("b", company_id="c-power", company_name="Power"),
            _p("c", company_id="c-prec", company_name="Precision"), _p("d"),
        ])
        r = await _fila("rede-A", company_id="c-prec")  # filtrar NÃO encolhe as opções
        assert r["facets"]["companies"] == [
            {"id": "c-power", "name": "Power", "count": 2}, {"id": "c-prec", "name": "Precision", "count": 1},
        ]
        assert r["facets"]["statuses"] == ["pending", "in_review"]

    async def test_as_opcoes_so_vem_do_ambito(self, bd):
        await bd.processes.insert_many([_p("a", "rede-A", company_id="c-a", company_name="A"), _p("b", "rede-B", company_id="c-b", company_name="B")])
        r = await _fila("rede-A")
        assert [c["id"] for c in r["facets"]["companies"]] == ["c-a"]

    async def test_as_revisoes_so_tem_o_estado_indexado(self, bd):
        r = await _fila("rede-A", tab="reviews")
        assert r["facets"]["statuses"] == ["indexed"]

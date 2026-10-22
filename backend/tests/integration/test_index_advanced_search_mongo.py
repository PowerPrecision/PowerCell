"""A pesquisa avançada de metadados do Index contra um MongoDB REAL (Out 2026).

Real porque o que um duplo esconde é exactamente o que esta pesquisa faz de difícil: o `$convert` do
salário (guardado como TEXTO — uma comparação lexicográfica diz que «900» é maior do que «1500»), o
`$unwind` que faz os filtros valerem para o MESMO emprego, o `$lookup` à fronteira de processos (dono +
redes convidadas, eliminados fora) e o `$facet` do total.
"""
from __future__ import annotations

import os
import uuid
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from fastapi import HTTPException
from motor.motor_asyncio import AsyncIOMotorClient

from services import index_advanced_search as pesquisa
from services import index_store as store
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
    base = cliente[f"test_index_busca_{uuid.uuid4().hex[:8]}"]
    monkeypatch.setattr(store, "db", base)
    yield base
    await cliente.drop_database(base.name)
    cliente.close()


def _ambito(*redes):
    return patch("services.tenant_network.resolve_vista_scope", AsyncMock(return_value=TenantScope(network_ids=redes)))


def _campo(valor, rever=False):
    return {"value": valor, "needs_review": rever, "confidence": "alta", "edited_by_human": False}


def _job(jid, *, nif="501964843", nome="Empresa Simulada, Lda", salario="1200.00", contrato="efetivo",
         periodo="2026-09", local="Lisboa", cargo="Técnico", rever=False):
    return {
        "job_id": jid, "employer_nif": _campo(nif), "employer_name": _campo(nome),
        "job_title": _campo(cargo), "net_salary": _campo(salario, rever), "contract_type": _campo(contrato),
        "employer_location": local, "period": periodo, "source_document_ids": ["d1"],
    }


async def _semear(bd):
    """Quatro processos: A1/A2 (rede A), B1 (rede B), A3 eliminado; A4 partilhado de B com a rede A."""
    await bd.processes.insert_many([
        {"id": "a1", "network_id": "rede-A", "process_number": 101, "is_deleted": False, "client_name": "Ana Segredo"},
        {"id": "a2", "network_id": "rede-A", "process_number": 102, "is_deleted": False},
        {"id": "b1", "network_id": "rede-B", "process_number": 201, "is_deleted": False},
        {"id": "a3", "network_id": "rede-A", "process_number": 103, "is_deleted": True},
        {"id": "b2", "network_id": "rede-B", "process_number": 202, "is_deleted": False, "partner_network_ids": ["rede-A"]},
    ])
    await bd.process_professional_metadata.insert_many([
        {"process_id": "a1", "network_id": "rede-A", "jobs": [
            _job("j-a1-1", salario="900.00", contrato="efetivo", periodo="2026-08", local="Lisboa"),
            _job("j-a1-2", nif="509442013", nome="Outra Empresa SA", salario="2500.00", contrato="termo_certo",
                 periodo="2026-09", local="Porto", cargo="Gerente"),
        ]},
        {"process_id": "a2", "network_id": "rede-A", "jobs": [
            _job("j-a2-1", salario="1500.00", contrato="efetivo", periodo="2026-09", local="Setúbal", cargo="Engenheiro"),
        ]},
        {"process_id": "b1", "network_id": "rede-B", "jobs": [_job("j-b1-1", salario="1500.00")]},
        {"process_id": "a3", "network_id": "rede-A", "jobs": [_job("j-a3-1", salario="1500.00")]},
        {"process_id": "b2", "network_id": "rede-B", "jobs": [_job("j-b2-1", salario="1100.00", local="Faro")]},
        {"process_id": "fantasma", "network_id": "rede-A", "jobs": [_job("j-f-1", salario="1500.00")]},
    ])


async def _procurar(**filtros):
    with _ambito("rede-A"):
        return await pesquisa.run_advanced_search(USER, **filtros)


def _ids(r):
    return sorted(i["job_id"] for i in r["items"])


class TestAFronteira:
    async def test_so_aparecem_processos_do_ambito_vivos_e_existentes(self, bd):
        await _semear(bd)
        r = await _procurar()
        # a1 (2 empregos), a2, e b2 (partilhado com a rede A); NÃO: b1 (outra rede), a3 (eliminado), fantasma (sem processo)
        assert _ids(r) == ["j-a1-1", "j-a1-2", "j-a2-1", "j-b2-1"]
        assert r["total"] == 4

    async def test_outra_rede_nao_ve_os_da_rede_A(self, bd):
        await _semear(bd)
        with _ambito("rede-B"):
            r = await pesquisa.run_advanced_search(USER)
        assert _ids(r) == ["j-b1-1", "j-b2-1"]

    async def test_a_resposta_nao_leva_dados_do_cliente(self, bd):
        await _semear(bd)
        r = await _procurar(min_salary=900, max_salary=900)
        assert "Segredo" not in str(r) and "client_name" not in str(r)
        item = r["items"][0]
        assert set(item) == {"process_id", "process_number", "company_name", "job_id", "employer", "job_title",
                             "net_salary", "contract_type", "period", "needs_review", "source_documents"}


class TestOSalarioEUmNumero:
    async def test_900_nao_e_maior_do_que_1500(self, bd):
        """Guardado como texto, «900.00» > «1500.00» na ordem lexicográfica."""
        await _semear(bd)
        r = await _procurar(min_salary=1000)
        assert "j-a1-1" not in _ids(r)  # 900 € fica fora de «≥ 1000»
        assert {"j-a2-1", "j-a1-2", "j-b2-1"} <= set(_ids(r))

    async def test_intervalo_fechado(self, bd):
        await _semear(bd)
        r = await _procurar(min_salary=1000, max_salary=2000)
        assert _ids(r) == ["j-a2-1", "j-b2-1"]

    async def test_o_limite_e_inclusivo(self, bd):
        await _semear(bd)
        r = await _procurar(min_salary=1500, max_salary=1500)
        assert _ids(r) == ["j-a2-1"]

    async def test_um_valor_ilegivel_fica_fora_de_qualquer_intervalo(self, bd):
        await _semear(bd)
        await bd.processes.insert_one({"id": "x", "network_id": "rede-A", "process_number": 9, "is_deleted": False})
        await bd.process_professional_metadata.insert_one(
            {"process_id": "x", "network_id": "rede-A", "jobs": [_job("j-x", salario="abc")]})
        assert "j-x" not in _ids(await _procurar(min_salary=0))
        assert "j-x" in _ids(await _procurar())  # sem filtro de salário, aparece (com net_salary null)

    async def test_ordenar_por_salario_e_numerico(self, bd):
        await _semear(bd)
        r = await _procurar(sort="salary_desc")
        assert [i["net_salary"] for i in r["items"]] == [2500.0, 1500.0, 1100.0, 900.0]
        r = await _procurar(sort="salary_asc")
        assert [i["net_salary"] for i in r["items"]] == [900.0, 1100.0, 1500.0, 2500.0]


class TestOsFiltrosValemParaOMesmoEmprego:
    async def test_salario_e_contrato_no_mesmo_emprego(self, bd):
        """a1 tem um efetivo a 900 € e um a termo a 2500 €: «efetivo e ≥ 2000» não casa com NENHUM."""
        await _semear(bd)
        assert _ids(await _procurar(contract_type=["efetivo"], min_salary=2000)) == []
        assert _ids(await _procurar(contract_type=["termo_certo"], min_salary=2000)) == ["j-a1-2"]

    async def test_varios_contratos(self, bd):
        await _semear(bd)
        r = await _procurar(contract_type=["termo_certo", "efetivo"])
        assert len(r["items"]) == 4


class TestOsTextos:
    async def test_localizacao_sem_acentos_nem_maiusculas(self, bd):
        await _semear(bd)
        assert _ids(await _procurar(employer_location="setubal")) == ["j-a2-1"]
        assert _ids(await _procurar(employer_location="SETÚBAL")) == ["j-a2-1"]

    async def test_o_texto_do_utilizador_nao_e_uma_expressao_regular(self, bd):
        await _semear(bd)
        assert (await _procurar(job_title=".*"))["items"] == []
        assert (await _procurar(employer_name="(("))["items"] == []

    async def test_cargo(self, bd):
        await _semear(bd)
        assert _ids(await _procurar(job_title="gerente")) == ["j-a1-2"]

    async def test_nif_por_prefixo(self, bd):
        await _semear(bd)
        assert _ids(await _procurar(employer_nif="5094")) == ["j-a1-2"]

    async def test_o_nome_consulta_tambem_o_directorio_de_entidades(self, bd):
        """O recibo diz «Outra Empresa SA»; o directório conhece o NIF como «Grupo Outra». Procurar
        «grupo outra» encontra o emprego por NIF — a mesma entidade escrita de várias maneiras."""
        await _semear(bd)
        await bd.employers.insert_one({"nif": "509442013", "name": "Grupo Outra", "name_normalizado": "grupo outra"})
        assert _ids(await _procurar(employer_name="grupo outra")) == ["j-a1-2"]
        assert _ids(await _procurar(employer_name="outra empresa")) == ["j-a1-2"]  # e pelo nome do recibo

    async def test_um_directorio_em_baixo_nao_derruba_a_pesquisa(self, bd, monkeypatch):
        await _semear(bd)

        class Quebrado:
            def find(self, *a, **k):
                raise RuntimeError("down")

        monkeypatch.setattr(store, "db", type("D", (), {
            "employers": Quebrado(), "process_professional_metadata": bd.process_professional_metadata})())
        with _ambito("rede-A"):
            r = await pesquisa.run_advanced_search(USER, employer_name="outra empresa")
        assert _ids(r) == ["j-a1-2"]


class TestOPeriodo:
    async def test_intervalo_de_periodos(self, bd):
        await _semear(bd)
        assert _ids(await _procurar(period_from="2026-09")) == ["j-a1-2", "j-a2-1", "j-b2-1"]
        assert _ids(await _procurar(period_to="2026-08")) == ["j-a1-1"]


class TestPaginacaoETotal:
    async def test_total_e_independente_da_pagina(self, bd):
        await _semear(bd)
        p1 = await _procurar(size=3, page=1, sort="salary_desc")
        p2 = await _procurar(size=3, page=2, sort="salary_desc")
        assert p1["total"] == p2["total"] == 4
        assert len(p1["items"]) == 3 and len(p2["items"]) == 1
        assert {i["job_id"] for i in p1["items"]}.isdisjoint({i["job_id"] for i in p2["items"]})

    async def test_pagina_alem_do_fim_e_vazia_e_mantem_o_total(self, bd):
        await _semear(bd)
        r = await _procurar(size=10, page=9)
        assert r["items"] == [] and r["total"] == 4

    async def test_sem_resultados_o_total_e_zero(self, bd):
        await _semear(bd)
        r = await _procurar(min_salary=99999)
        assert r["items"] == [] and r["total"] == 0

    async def test_o_tecto_da_pagina(self, bd):
        await _semear(bd)
        assert (await _procurar(size=5000))["size"] == pesquisa.TAMANHO_MAXIMO_DA_PAGINA


class TestOsPedidosInvalidos:
    @pytest.mark.parametrize("filtros", [
        {"min_salary": 2000, "max_salary": 1000},
        {"period_from": "2026-13"},
        {"period_from": "2026-09", "period_to": "2026-01"},
        {"contract_type": ["inventado"]},
        {"sort": "aleatorio"},
        {"employer_name": "a"},
        {"employer_nif": "12"},
    ])
    async def test_422_com_motivo(self, bd, filtros):
        with pytest.raises(HTTPException) as e:
            await _procurar(**filtros)
        assert e.value.status_code == 422 and e.value.detail

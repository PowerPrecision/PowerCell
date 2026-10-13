"""Quem lista nunca devolve o que o detalhe recusa — contra um MongoDB REAL (QA, Out 2026).

A QA reportou «cartões-fantasma» no Kanban (o «olho» respondia «Processo não
encontrado») e «Registos de Clientes» com registos de outra rede. A reprodução
contra um Mongo real, na ordem em que a QA a faria, mostrou que a query do
quadro estava certa e que o que o ecrã mostrava era a CACHE do utilizador
anterior (corrigido no `AuthContext`); e que os Registos tinham dois defeitos
próprios (eliminados e processos partilhados — corrigidos em
`admin_observability`).

O que fica fixado aqui é a INVARIANTE que daria o sintoma se alguma vez falhasse,
e que um duplo de Mongo não consegue provar (`$or`/`$and`/`$in` sobre campos
ausentes, nulos e vazios): **todo o documento que a listagem devolve é aceite
pelo predicado que o detalhe usa** (`processo_no_ambito`), e nenhum eliminado
aparece. Cobre a pilha por carimbar com e sem `TENANT_DEFAULT_NETWORK_ID`.
"""
from __future__ import annotations

import os
import uuid

import pytest
import pytest_asyncio
from motor.motor_asyncio import AsyncIOMotorClient

from tests.unit.helpers_tenant import REDE_DOMUS, REDE_INCUMBENTE, tenant_db

pytestmark = pytest.mark.asyncio

P, D = REDE_INCUMBENTE, REDE_DOMUS

PROCESSOS = [
    {"id": "p-power", "network_id": P, "company_id": "cmp-power", "status": "novo"},
    {"id": "p-domus", "network_id": D, "company_id": "cmp-domus", "status": "novo"},
    {"id": "p-legado", "status": "novo"},
    {"id": "p-power-sem-rede", "company_id": "cmp-power", "status": "novo"},
    {"id": "p-power-nome", "company": "Power Real Estate", "status": "novo"},
    {"id": "p-partilhado", "network_id": P, "company_id": "cmp-power",
     "partner_network_ids": [D], "status": "novo"},
    {"id": "p-domus-apagado", "network_id": D, "company_id": "cmp-domus",
     "is_deleted": True, "status": "novo"},
    {"id": "p-power-concluido", "network_id": P, "company_id": "cmp-power", "status": "concluidos"},
    {"id": "p-vazio", "network_id": "", "company_id": "", "status": "novo"},
    {"id": "p-nulo", "network_id": None, "company_id": None, "status": "novo"},
]
EMPRESAS_REAIS = [
    {"id": "cmp-power", "name": "Power Real Estate", "network_id": P},
    {"id": "cmp-domus", "name": "Domus", "network_id": D},
]
UCRS = [
    {"user_id": "u-domus", "company_id": "cmp-domus", "company_name": "Domus", "role": "diretor"},
    {"user_id": "u-power", "company_id": "cmp-power", "company_name": "Power Real Estate", "role": "diretor"},
]
DOMUS = {"id": "u-domus", "role": "diretor", "company": "Domus"}
CEO_DOMUS = {"id": "u-domus", "role": "ceo", "company": "Domus"}
POWER = {"id": "u-power", "role": "diretor", "company": "Power Real Estate"}


@pytest_asyncio.fixture
async def bd():
    url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    cliente = AsyncIOMotorClient(url, serverSelectionTimeoutMS=2000)
    try:
        await cliente.admin.command("ping")
    except Exception:
        cliente.close()
        pytest.skip("MongoDB não disponível")
    base = cliente[f"test_listagens_{uuid.uuid4().hex[:8]}"]
    await base.processes.insert_many([dict(p) for p in PROCESSOS])
    await base.companies.insert_many([dict(e) for e in EMPRESAS_REAIS])
    await base.user_company_roles.insert_many([dict(u) for u in UCRS])
    yield base
    await cliente.drop_database(base.name)
    cliente.close()


async def _quadro(bd, utilizador):
    from services.process_list_filters import build_kanban_query
    from services.tenant_network import build_tenant_process_condition

    cond = await build_tenant_process_condition(utilizador)
    query = build_kanban_query(
        utilizador, "diretor", tenant_condition=cond, show_all=True, view_mode="all",
    )
    return [d async for d in bd.processes.find(query, {"_id": 0})]


async def _ids_do_detalhe_ok(utilizador, docs):
    from services.tenant_network import processo_no_ambito, resolve_tenant_scope

    scope = await resolve_tenant_scope(utilizador)
    return {d["id"] for d in docs if processo_no_ambito(d, scope)}


@pytest.mark.parametrize("com_omissao", [True, False], ids=["omissao-definida", "sem-omissao"])
async def test_o_quadro_nunca_devolve_o_que_o_detalhe_recusa(bd, monkeypatch, com_omissao):
    if com_omissao:
        monkeypatch.setenv("TENANT_DEFAULT_NETWORK_ID", P)
    else:
        monkeypatch.delenv("TENANT_DEFAULT_NETWORK_ID", raising=False)

    with tenant_db(bd):
        docs = await _quadro(bd, DOMUS)
        aceites = await _ids_do_detalhe_ok(DOMUS, docs)

    devolvidos = {d["id"] for d in docs}
    assert devolvidos == aceites, f"cartões-fantasma: {sorted(devolvidos - aceites)}"
    assert "p-domus-apagado" not in devolvidos, "um eliminado não é um cartão"
    assert "p-domus" in devolvidos and "p-partilhado" in devolvidos


async def test_com_omissao_definida_a_ilha_nao_ve_nada_da_power_nem_a_pilha(bd, monkeypatch):
    monkeypatch.setenv("TENANT_DEFAULT_NETWORK_ID", P)
    with tenant_db(bd):
        docs = await _quadro(bd, DOMUS)
    assert {d["id"] for d in docs} == {"p-domus", "p-partilhado"}


async def test_contraprova_a_casa_ve_os_seus_e_a_pilha(bd, monkeypatch):
    monkeypatch.setenv("TENANT_DEFAULT_NETWORK_ID", P)
    with tenant_db(bd):
        docs = await _quadro(bd, POWER)
    ids = {d["id"] for d in docs}
    assert {"p-power", "p-partilhado", "p-legado", "p-vazio", "p-nulo"} <= ids
    assert "p-domus" not in ids and "p-domus-apagado" not in ids


async def test_os_registos_so_trazem_os_da_casa_e_nenhum_eliminado(bd, monkeypatch):
    import services.admin_observability as obs

    monkeypatch.setenv("TENANT_DEFAULT_NETWORK_ID", P)
    with tenant_db(bd, obs):
        r = await obs.run_list_client_registrations(CEO_DOMUS, limit=100)
    ids = {p["id"] for p in r["registrations"]}
    assert ids == {"p-domus"}, f"registos de outra rede / eliminados: {sorted(ids - {'p-domus'})}"
    assert r["total"] == 1

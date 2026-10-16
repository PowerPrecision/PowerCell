"""«Processos do cliente» na modal de detalhes respeitam a empresa activa — MongoDB REAL (Lote 7.3).

A modal lista `GET /clients/{id}` → `processes`. A regra do pedido: só os processos da empresa que está activa no
cabeçalho (ou partilhados com ela). O ecrã não filtra nada — se o servidor devolver a mais, a modal mostra a mais —
por isso a fronteira prova-se aqui, com utilizadores que trabalham nas DUAS redes e com o Master.
"""
from __future__ import annotations

import os
import uuid

import pytest
import pytest_asyncio
from motor.motor_asyncio import AsyncIOMotorClient

from tests.unit.helpers_tenant import EMPRESAS, REDE_DOMUS, REDE_INCUMBENTE, tenant_db

pytestmark = pytest.mark.asyncio

P, D = REDE_INCUMBENTE, REDE_DOMUS

#: O CEO com acesso às duas redes (o caso real do grupo) escolhe a empresa no cabeçalho.
def _ceo(empresa):
    return {"id": "u-ceo", "role": "ceo", "effective_role": "ceo", "name": "Rita", "company": "Power Real Estate",
            **({"vista_empresa_id": empresa} if empresa else {})}


def _master(empresa=None):
    return {"id": "u-m", "role": "master", "effective_role": "master", "name": "Sistema",
            **({"vista_empresa_id": empresa} if empresa else {})}


@pytest_asyncio.fixture
async def bd(monkeypatch):
    url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    cliente = AsyncIOMotorClient(url, serverSelectionTimeoutMS=2000)
    try:
        await cliente.admin.command("ping")
    except Exception:
        cliente.close()
        pytest.skip("MongoDB não disponível")
    monkeypatch.setenv("TENANT_DEFAULT_NETWORK_ID", P)
    base = cliente[f"test_proc73_{uuid.uuid4().hex[:8]}"]
    await base.companies.insert_many([dict(e) for e in EMPRESAS])
    await base.user_company_roles.insert_many([
        {"user_id": "u-ceo", "company_id": "cmp-power", "company_name": "Power Real Estate", "role": "ceo", "is_default": True},
        {"user_id": "u-ceo", "company_id": "cmp-domus", "company_name": "Domus", "role": "ceo", "is_default": False},
    ])
    await base.users.insert_many([
        {"id": "u-ceo", "name": "Rita", "role": "ceo", "company": "Power Real Estate", "is_active": True},
        {"id": "u-m", "name": "Sistema", "role": "master", "is_active": True},
    ])
    await base.clients.insert_one({
        "id": "cli-1", "nome": "Cliente Comum", "network_id": P, "company_id": "cmp-power",
        "process_ids": ["p-power", "p-domus", "p-partilhado"], "contacto": {"email": "c@x.pt"},
    })
    comuns = {"client_id": "cli-1", "client_name": "Cliente Comum", "status": "novo", "process_type": "credito"}
    await base.processes.insert_many([
        {"id": "p-power", "process_number": 101, "network_id": P, "company_id": "cmp-power", **comuns},
        # o processo que a Power moveu para a Domus (Lote 6): a ficha do cliente não mudou
        {"id": "p-domus", "process_number": 202, "network_id": D, "company_id": "cmp-domus", **comuns},
        {"id": "p-partilhado", "process_number": 303, "network_id": P, "company_id": "cmp-power",
         "partner_network_ids": [D], **comuns},
    ])
    await base.workflow_statuses.insert_one({"name": "novo", "label": "Novo", "order": 1, "is_active": True})
    yield base
    await cliente.drop_database(base.name)
    cliente.close()


def _mods():
    import services.client_crud as crud
    import services.client_window as janela
    import services.client_list_search as lista
    import services.by_id_scope as por_id

    return crud, janela, lista, por_id


async def _processos(bd, user):
    from services.client_crud import run_get_client

    with tenant_db(bd, *_mods()):
        ficha = await run_get_client("cli-1", user)
    return {p["id"] for p in ficha["processes"]}


async def test_com_a_power_activa_so_os_processos_da_power(bd):
    """O CEO das duas redes, a trabalhar COMO Power: o processo da Domus não entra."""
    assert await _processos(bd, _ceo("cmp-power")) == {"p-power", "p-partilhado"}


async def test_com_a_domus_activa_so_o_da_domus_e_o_partilhado_com_ela(bd):
    """O mesmo CEO, agora COMO Domus: o cliente é de outra rede (visitante) → só o que é da Domus ou lhe foi partilhado."""
    assert await _processos(bd, _ceo("cmp-domus")) == {"p-domus", "p-partilhado"}


async def test_o_master_com_empresa_escolhida_tambem_e_estreitado(bd):
    assert await _processos(bd, _master("cmp-power")) == {"p-power", "p-partilhado"}
    assert await _processos(bd, _master("cmp-domus")) == {"p-domus", "p-partilhado"}


async def test_contraprova_o_master_na_vista_sistema_ve_todos(bd):
    assert await _processos(bd, _master()) == {"p-power", "p-domus", "p-partilhado"}


async def test_a_resposta_nao_traz_ids_de_processos_fora_da_empresa_nem_no_resto_da_ficha(bd):
    from services.client_crud import run_get_client

    with tenant_db(bd, *_mods()):
        ficha = await run_get_client("cli-1", _ceo("cmp-power"))
    assert "p-domus" not in str(ficha)
    assert set(ficha["process_ids"]) == {"p-power", "p-partilhado"}

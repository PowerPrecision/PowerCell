"""Alterar a empresa de um cliente — contra um MongoDB REAL (Lote 2, Out 2026).

Real porque o duplo de Mongo não implementa `$pull` (com um subdocumento como
critério, em `partner_companies`) nem prova os `update_many` sobre as colecções
que acompanham o processo — e é aí que mora o risco: uma tarefa que ficasse com
o carimbo antigo continuaria a mostrar o nome do cliente à empresa de onde ele
saiu.
"""
from __future__ import annotations

import os
import uuid
from unittest.mock import patch

import pytest
import pytest_asyncio
from motor.motor_asyncio import AsyncIOMotorClient

from services.auth import hash_password
from tests.unit.helpers_tenant import EMPRESAS, REDE_DOMUS, REDE_INCUMBENTE, tenant_db

pytestmark = pytest.mark.asyncio

SENHA = "Segredo-Certo-9!"
MASTER = {"id": "u-master", "role": "master", "effective_role": "master", "name": "Master", "email": "m@p.pt"}
S3 = "Documentação Clientes/uuid-do-cliente"


@pytest_asyncio.fixture
async def bd(monkeypatch):
    url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    cliente = AsyncIOMotorClient(url, serverSelectionTimeoutMS=2000)
    try:
        await cliente.admin.command("ping")
    except Exception:
        cliente.close()
        pytest.skip("MongoDB não disponível")
    monkeypatch.setenv("TENANT_DEFAULT_NETWORK_ID", REDE_INCUMBENTE)
    base = cliente[f"test_transferir_cliente_{uuid.uuid4().hex[:8]}"]
    await base.companies.insert_many([dict(e) for e in EMPRESAS])
    await base.users.insert_one({"id": "u-master", "email": MASTER["email"],
                                 "password": hash_password(SENHA), "is_active": True})
    await base.clients.insert_one({
        "id": "cli-1", "nome": "Ana", "process_ids": ["p1"], "s3_folder": S3,
        "network_id": REDE_INCUMBENTE, "company_id": "cmp-power", "company_name": "Power Real Estate",
    })
    await base.processes.insert_one({
        "id": "p1", "client_id": "cli-1", "s3_folder": S3,
        "network_id": REDE_INCUMBENTE, "company_id": "cmp-power", "company_name": "Power Real Estate",
        "partner_network_ids": [REDE_DOMUS, "rede_x"],
        "partner_companies": [{"company_id": "cmp-domus", "network_id": REDE_DOMUS, "company_name": "Domus"},
                              {"company_id": "cmp-x", "network_id": "rede_x", "company_name": "X"}],
    })
    for colecao in ("tasks", "deadlines", "visits"):
        await base[colecao].insert_many([
            {"id": f"{colecao}-a", "process_id": "p1", "network_id": REDE_INCUMBENTE, "company_id": "cmp-power"},
            {"id": f"{colecao}-b", "process_id": "outro", "network_id": REDE_INCUMBENTE, "company_id": "cmp-power"},
        ])
    yield base
    await cliente.drop_database(base.name)
    cliente.close()


async def _transferir(bd, destino="cmp-domus"):
    import services.admin_helpers as helpers
    import services.client_company_transfer as mod
    import services.reauth_password as reauth

    with tenant_db(bd, helpers, mod, reauth), patch("services.history.db", bd):
        return await mod.run_transfer_client_company(
            "cli-1", mod.TransferirClienteIn(company_id=destino, password=SENHA), MASTER,
        )


async def test_a_transferencia_completa_contra_mongo_real(bd):
    resposta = await _transferir(bd)
    assert resposta["transferido"] is True

    cliente = await bd.clients.find_one({"id": "cli-1"})
    processo = await bd.processes.find_one({"id": "p1"})
    for doc in (cliente, processo):
        assert (doc["company_id"], doc["network_id"]) == ("cmp-domus", REDE_DOMUS)
        assert doc["s3_folder"] == S3  # o S3 não se mexe

    # A Domus deixou de ser «convidada» do que agora é seu; as outras partilhas ficam.
    assert processo["partner_network_ids"] == ["rede_x"]
    assert [e["network_id"] for e in processo["partner_companies"]] == ["rede_x"]


async def test_as_colecoes_do_processo_acompanham_so_as_dele(bd):
    await _transferir(bd)
    for colecao in ("tasks", "deadlines", "visits"):
        movido = await bd[colecao].find_one({"id": f"{colecao}-a"})
        intacto = await bd[colecao].find_one({"id": f"{colecao}-b"})
        assert (movido["company_id"], movido["network_id"]) == ("cmp-domus", REDE_DOMUS)
        assert (intacto["company_id"], intacto["network_id"]) == ("cmp-power", REDE_INCUMBENTE)


async def test_a_segunda_passagem_nao_altera_nada(bd):
    await _transferir(bd)
    antes = await bd.processes.find_one({"id": "p1"}, {"_id": 0})
    resposta = await _transferir(bd)
    assert resposta["transferido"] is False
    assert await bd.processes.find_one({"id": "p1"}, {"_id": 0}) == antes

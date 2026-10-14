"""Alterar a empresa de PROCESSOS de um cliente — contra um MongoDB REAL (Lote 2; reescrito no Lote 6).

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


async def _transferir(bd, destino="cmp-domus", processos=("p1",)):
    import services.admin_helpers as helpers
    import services.client_company_transfer as mod
    import services.reauth_password as reauth

    with tenant_db(bd, helpers, mod, reauth), patch("services.history.db", bd):
        return await mod.run_transfer_client_company(
            "cli-1", mod.TransferirClienteIn(company_id=destino, process_ids=list(processos), password=SENHA), MASTER,
        )


async def test_a_transferencia_completa_contra_mongo_real(bd):
    resposta = await _transferir(bd)
    assert resposta["transferido"] is True

    cliente = await bd.clients.find_one({"id": "cli-1"})
    processo = await bd.processes.find_one({"id": "p1"})
    # O PROCESSO muda de empresa; o CLIENTE fica (pode ter processos em várias empresas).
    assert (processo["company_id"], processo["network_id"]) == ("cmp-domus", REDE_DOMUS)
    assert (cliente["company_id"], cliente["network_id"]) == ("cmp-power", REDE_INCUMBENTE)
    for doc in (cliente, processo):
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


async def test_depois_de_mover_um_processo_cada_empresa_le_so_os_ficheiros_do_seu(bd):
    """A consequência nos DOCUMENTOS (Lote 6): o cliente fica com processos em duas empresas.

    A pasta do cliente passa a ser reclamada por duas redes, e antes disto «ambígua» queria dizer
    que NINGUÉM a lia — nem a Power o BI do próprio cliente, nem a Domus o do processo que recebeu.
    Agora a subpasta de um processo é desse processo, e a raiz do cliente é de quem vê qualquer um
    dos processos dele.
    """
    from services.document_path_scope import ficheiro_no_ambito
    import services.document_path_scope as janela
    import services.by_id_scope as por_id

    await bd.processes.insert_one({
        "id": "p2", "client_id": "cli-1", "network_id": REDE_INCUMBENTE, "company_id": "cmp-power",
    })
    await bd.clients.update_one({"id": "cli-1"}, {"$set": {"process_ids": ["p1", "p2"]}})
    await bd.processes.update_one({"id": "p1"}, {"$unset": {"s3_folder": ""}})
    await bd.user_company_roles.insert_many([
        {"user_id": "u-power", "company_id": "cmp-power", "company_name": "Power Real Estate", "role": "diretor"},
        {"user_id": "u-domus", "company_id": "cmp-domus", "company_name": "Domus", "role": "diretor"},
    ])
    await _transferir(bd, processos=("p1",))
    power = {"id": "u-power", "role": "diretor", "effective_role": "diretor", "company": "Power Real Estate"}
    domus = {"id": "u-domus", "role": "diretor", "effective_role": "diretor", "company": "Domus"}
    raiz = "Documentação Clientes/cli-1"

    with tenant_db(bd, janela, por_id):
        # raiz do cliente (o BI): as duas empresas têm um processo dele
        assert await ficheiro_no_ambito(f"{raiz}/bi.pdf", power) is True
        assert await ficheiro_no_ambito(f"{raiz}/bi.pdf", domus) is True
        # subpastas de cada processo: só quem vê esse processo
        assert await ficheiro_no_ambito(f"{raiz}/processos/p1/a.pdf", domus) is True
        assert await ficheiro_no_ambito(f"{raiz}/processos/p1/a.pdf", power) is False
        assert await ficheiro_no_ambito(f"{raiz}/processos/p2/b.pdf", power) is True
        assert await ficheiro_no_ambito(f"{raiz}/processos/p2/b.pdf", domus) is False

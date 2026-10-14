"""D-18 — a migração dos `co_buyers` contra um MongoDB REAL.

O que um duplo in-memory não prova: a igualdade de ARRAYS de subdocumentos (a condição da escrita é o
array tal como foi lido), o `$unset` quando não sobra ninguém, e a desencriptação do NIF/CC cifrados em
repouso — a prova de identidade só é possível sobre o documento desencriptado.
"""
from __future__ import annotations

import importlib.util
import os
import uuid
from pathlib import Path

import pytest
import pytest_asyncio
from motor.motor_asyncio import AsyncIOMotorClient

from services.encryption import encryption_service

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "migrar_co_buyers_adicionais.py"


def _script():
    spec = importlib.util.spec_from_file_location("migrar_co_buyers_adicionais", SCRIPT)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def _processo(id, co_buyers):
    """Como o servidor grava: os campos sensíveis cifrados em repouso."""
    doc = {
        "id": id, "client_name": "Ana Costa", "is_deleted": False,
        "personal_data": {"nif": "234567890"}, "co_buyers": co_buyers,
    }
    return encryption_service.encrypt_process(doc)


@pytest_asyncio.fixture
async def bd():
    url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    cliente = AsyncIOMotorClient(url, serverSelectionTimeoutMS=2000)
    try:
        await cliente.admin.command("ping")
    except Exception:
        cliente.close()
        pytest.skip("MongoDB não disponível")
    base = cliente[f"test_cobuyers_{uuid.uuid4().hex[:8]}"]
    yield base
    await cliente.drop_database(base.name)
    cliente.close()


@pytest.mark.asyncio
async def test_migra_so_o_provado_com_nif_cifrado_e_e_idempotente(bd):
    titular = {"nome": "Ana Costa", "nif": "234567890", "estado_civil": "solteira"}
    segundo = {"nome": "Rui Santos", "nif": "345678901"}
    await bd.processes.insert_many([
        _processo("p-migravel", [dict(titular), dict(segundo)]),
        _processo("p-so-titular", [dict(titular)]),
        _processo("p-ambiguo", [dict(segundo)]),
    ])
    # o NIF está mesmo cifrado em repouso (senão o teste não prova a desencriptação)
    cru = await bd.processes.find_one({"id": "p-migravel"})
    assert cru["co_buyers"][0]["nif"].startswith("ENC:")

    migrar = _script().migrar
    r = await migrar(bd, aplicar=True)
    assert r["resumo"]["retirar_o_titular_1"] == 2

    migravel = await bd.processes.find_one({"id": "p-migravel"})
    assert len(migravel["co_buyers"]) == 1
    assert encryption_service.decrypt_process(migravel)["co_buyers"][0]["nome"] == "Rui Santos"
    assert "co_buyers" not in await bd.processes.find_one({"id": "p-so-titular"})
    assert len((await bd.processes.find_one({"id": "p-ambiguo"}))["co_buyers"]) == 1  # intacto

    depois = await migrar(bd, aplicar=True)
    assert depois["resumo"]["retirar_o_titular_1"] == 0
    assert await bd.audit_logs.count_documents({"action": "co_buyers_migrados"}) == 1


@pytest.mark.asyncio
async def test_edicao_concorrente_nao_e_pisada(bd):
    titular = {"nome": "Ana Costa", "nif": "234567890"}
    await bd.processes.insert_one(_processo("p1", [dict(titular), {"nome": "Rui Santos"}]))
    modulo = _script()

    original = bd.processes.update_one

    class Intercepta:
        def __getattr__(self, nome):
            return getattr(bd.processes, nome)

        async def update_one(self, filtro, operacao, *a, **k):
            # alguém acrescenta um comprador entre a leitura e a escrita
            await bd.processes.update_one({"id": "p1"}, {"$push": {"co_buyers": {"nome": "Novo"}}})
            return await original(filtro, operacao, *a, **k)

    class DbFalsa:
        processes = Intercepta()
        audit_logs = bd.audit_logs

    r = await modulo.migrar(DbFalsa(), aplicar=True)
    assert r["registos"][0]["estado"] == "inalterado"
    assert len((await bd.processes.find_one({"id": "p1"}))["co_buyers"]) == 3

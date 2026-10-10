"""O índice TTL dos rascunhos passa de 7 para 15 dias num MongoDB REAL.

Um duplo não prova isto: em produção JÁ existe um `ttl_email_drafts` com
`expireAfterSeconds=604800`, e criar o mesmo nome com outro prazo faz o Mongo
levantar `IndexOptionsConflict` (código 85). O que se prova aqui é que o
caminho de conflito do `_create_index_safe` o resolve — sem este teste, uma
subida de prazo podia deixar o índice antigo a purgar aos 7 dias e o código a
dizer 15.
"""
from __future__ import annotations

import os
import uuid

import pytest
import pytest_asyncio
from motor.motor_asyncio import AsyncIOMotorClient

from services.db_indexes import RASCUNHOS_TTL_SEGUNDOS, create_ttl_indexes

SETE_DIAS = 604_800


@pytest_asyncio.fixture
async def base():
    url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    cliente = AsyncIOMotorClient(url, serverSelectionTimeoutMS=2000)
    try:
        await cliente.admin.command("ping")
    except Exception:
        cliente.close()
        pytest.skip("MongoDB não disponível")
    nome = f"test_rascunhos_ttl_{uuid.uuid4().hex[:8]}"
    bd = cliente[nome]
    yield bd
    await cliente.drop_database(nome)
    cliente.close()


async def _ttl_dos_rascunhos(bd):
    info = await bd.emails.index_information()
    assert "ttl_email_drafts" in info, sorted(info)
    return info["ttl_email_drafts"]


@pytest.mark.asyncio
async def test_um_indice_antigo_de_7_dias_passa_a_15(base):
    await base.emails.insert_one({"id": "e1", "status": "draft"})
    await base.emails.create_index(
        [("updated_at_dt", 1)], name="ttl_email_drafts",
        expireAfterSeconds=SETE_DIAS, partialFilterExpression={"status": "draft"},
    )
    assert (await _ttl_dos_rascunhos(base))["expireAfterSeconds"] == SETE_DIAS

    resultado = await create_ttl_indexes(base)

    indice = await _ttl_dos_rascunhos(base)
    assert indice["expireAfterSeconds"] == RASCUNHOS_TTL_SEGUNDOS == 1_296_000
    assert indice["partialFilterExpression"] == {"status": "draft"}
    assert not [e for e in resultado["errors"] if "ttl_email_drafts" in e]


@pytest.mark.asyncio
async def test_a_segunda_passagem_nao_mexe_em_nada(base):
    await base.emails.insert_one({"id": "e1", "status": "draft"})
    await create_ttl_indexes(base)
    antes = await _ttl_dos_rascunhos(base)

    segunda = await create_ttl_indexes(base)

    assert await _ttl_dos_rascunhos(base) == antes
    assert not [e for e in segunda["errors"] if "ttl_email_drafts" in e]


@pytest.mark.asyncio
async def test_numa_base_nova_nasce_com_15_dias(base):
    await base.emails.insert_one({"id": "e1", "status": "draft"})
    await create_ttl_indexes(base)
    assert (await _ttl_dos_rascunhos(base))["expireAfterSeconds"] == 1_296_000

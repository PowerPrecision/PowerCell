"""D-38 contra um MongoDB REAL: a procura de duplicados por rede.

O que o duplo em memória NÃO prova — e que aqui se prova:

* o `$or` de seis ramos (hash + claro, NIF/email/telemóvel) combinado com a
  condição de rede (`$and` + `$or` + `$in: [None, ""]`);
* `id: {"$ne": ...}` (a edição não casa consigo própria) e o filtro de eliminados;
* os blind indexes REAIS (`encrypt_client_data`) — o hash do telemóvel só existe
  se o cifrador o gerar, e o teste usa o cifrador de produção.
"""
from __future__ import annotations

import os
import uuid

import pytest
import pytest_asyncio
from motor.motor_asyncio import AsyncIOMotorClient

from tests.unit.helpers_tenant import EMPRESAS, REDE_DOMUS, REDE_INCUMBENTE, tenant_db


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
    base = cliente[f"test_duplicados_{uuid.uuid4().hex[:8]}"]
    await base.companies.insert_many([dict(e) for e in EMPRESAS])
    yield base
    await cliente.drop_database(base.name)
    cliente.close()


def _cifrado(id_, rede=None, empresa=None, **extra):
    from services.encryption import encrypt_client_data

    doc = {
        "id": id_, "nome": f"Cliente {id_}",
        "contacto": {"email": f"{id_}@x.pt", "telefone": extra.pop("telefone", "")},
        "dados_pessoais": {"nif": extra.pop("nif", "")},
        **extra,
    }
    if rede:
        doc["network_id"] = rede
    if empresa:
        doc["company_id"] = empresa
    return encrypt_client_data(doc)


@pytest_asyncio.fixture
async def mundo(bd):
    import services.client_uniqueness as cu

    await bd.clients.insert_many([
        _cifrado("pw", REDE_INCUMBENTE, "cmp-power", telefone="912345678", nif="285739461"),
        _cifrado("dm", REDE_DOMUS, "cmp-domus", telefone="933333333", nif="500000000"),
        _cifrado("leg", telefone="966666666"),
        _cifrado("gone", REDE_INCUMBENTE, "cmp-power", telefone="944444444", is_deleted=True, status="eliminado"),
    ])
    with tenant_db(bd, cu):
        yield cu


async def _id(cu, rede, **kw):
    achado = await cu.encontrar_cliente_duplicado(
        kw.get("nif"), kw.get("email"), kw.get("telefone"), rede=rede, excluir_id=kw.get("excluir_id"),
    )
    return achado and achado["id"]


class TestProcuraComBlindIndexesReais:
    @pytest.mark.asyncio
    async def test_telefone_com_e_sem_indicativo_acha_o_mesmo(self, mundo):
        for escrito in ("912345678", "912 345 678", "+351 912 345 678", "00351912345678"):
            assert await _id(mundo, REDE_INCUMBENTE, telefone=escrito) == "pw", escrito

    @pytest.mark.asyncio
    async def test_nif_e_email_continuam_a_funcionar(self, mundo):
        assert await _id(mundo, REDE_INCUMBENTE, nif="285739461") == "pw"
        assert await _id(mundo, REDE_INCUMBENTE, email="PW@x.pt") == "pw"

    @pytest.mark.asyncio
    async def test_cada_rede_so_ve_a_sua(self, mundo):
        assert await _id(mundo, REDE_DOMUS, telefone="912345678") is None
        assert await _id(mundo, REDE_DOMUS, telefone="933333333") == "dm"
        assert await _id(mundo, REDE_INCUMBENTE, telefone="933333333") is None

    @pytest.mark.asyncio
    async def test_a_pilha_por_carimbar_so_conta_para_a_rede_de_omissao(self, mundo):
        assert await _id(mundo, REDE_INCUMBENTE, telefone="966666666") == "leg"
        assert await _id(mundo, REDE_DOMUS, telefone="966666666") is None
        assert await _id(mundo, None, telefone="966666666") == "leg"
        assert await _id(mundo, None, telefone="912345678") is None, "sem rede: nunca um cliente de uma rede concreta"

    @pytest.mark.asyncio
    async def test_eliminado_nao_bloqueia(self, mundo):
        assert await _id(mundo, REDE_INCUMBENTE, telefone="944444444") is None

    @pytest.mark.asyncio
    async def test_a_edicao_nao_casa_consigo_propria(self, mundo):
        assert await _id(mundo, REDE_INCUMBENTE, telefone="912345678", excluir_id="pw") is None

    @pytest.mark.asyncio
    async def test_telefone_curto_nao_procura(self, mundo):
        assert await _id(mundo, REDE_INCUMBENTE, telefone="12345") is None

    @pytest.mark.asyncio
    async def test_assert_levanta_409_com_o_campo(self, mundo):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            await mundo.assert_cliente_unico(None, None, "+351 912 345 678", rede=REDE_INCUMBENTE)
        assert exc.value.status_code == 409
        assert exc.value.detail["matched_fields"] == ["telefone"]

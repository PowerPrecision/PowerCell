"""D-42/D-40 contra um MongoDB REAL: a identidade global e os índices únicos parciais.

(Nasceu como `test_duplicados_por_rede_mongo.py`, do D-38: a procura por rede. Os testes
que a afirmavam foram INVERTIDOS — ver o `worklog.md`.)

O que o duplo em memória NÃO prova — e que aqui se prova:

* o `$or` de hash + claro (NIF/email) com `id: {"$ne": ...}` e o filtro de eliminados;
* os blind indexes REAIS (`encrypt_client_data`);
* os ÍNDICES ÚNICOS PARCIAIS, tal como `db_indexes` os declara: recusam o duplicado, deixam passar
  eliminados, vazios e documentos sem hash, e FALHAM a construção quando já há duplicados (a
  razão de a limpeza ter de vir antes).
"""
from __future__ import annotations

import os
import uuid

import pytest
import pytest_asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import DuplicateKeyError

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
    base = cliente[f"test_identidade_{uuid.uuid4().hex[:8]}"]
    await base.companies.insert_many([dict(e) for e in EMPRESAS])
    yield base
    await cliente.drop_database(base.name)
    cliente.close()


def _cifrado(id_, rede=None, empresa=None, **extra):
    from services.encryption import encrypt_client_data

    doc = {
        "id": id_, "nome": f"Cliente {id_}",
        "contacto": {"email": extra.pop("email", f"{id_}@x.pt"), "telefone": extra.pop("telefone", "")},
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
        _cifrado("leg", telefone="966666666", nif="100000001"),
        _cifrado("gone", REDE_INCUMBENTE, "cmp-power", nif="777777777", is_deleted=True, status="eliminado"),
    ])
    with tenant_db(bd, cu):
        yield cu


async def _id(cu, **kw):
    achado = await cu.encontrar_cliente_duplicado(kw.get("nif"), kw.get("email"), excluir_id=kw.get("excluir_id"))
    return achado and achado["id"]


class TestProcuraGlobalComBlindIndexesReais:
    @pytest.mark.asyncio
    async def test_nif_e_email_acham_o_cliente_seja_qual_for_a_rede(self, mundo):
        assert await _id(mundo, nif="285739461") == "pw"
        assert await _id(mundo, email="PW@x.pt") == "pw"
        assert await _id(mundo, nif="500000000") == "dm", "a Domus também se acha a partir de qualquer lado"
        assert await _id(mundo, nif="100000001") == "leg", "e a pilha por carimbar"

    @pytest.mark.asyncio
    async def test_o_telemovel_nao_identifica_ninguem(self, mundo):
        """INVERTIDO (era a chave de unicidade no D-38): o telemóvel já não entra na procura."""
        assert not hasattr(mundo, "CAMPO_TELEFONE")
        achado = await mundo.encontrar_cliente_duplicado(None, None)
        assert achado is None
        from services.client_uniqueness import construir_condicoes_de_duplicado

        assert construir_condicoes_de_duplicado(None, None) == []

    @pytest.mark.asyncio
    async def test_eliminado_nao_bloqueia(self, mundo):
        assert await _id(mundo, nif="777777777") is None

    @pytest.mark.asyncio
    async def test_a_edicao_nao_casa_consigo_propria(self, mundo):
        assert await _id(mundo, nif="285739461", excluir_id="pw") is None

    @pytest.mark.asyncio
    async def test_assert_levanta_409_com_o_cliente_da_propria_rede(self, mundo):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            await mundo.assert_cliente_unico("285739461", None, rede=REDE_INCUMBENTE)
        assert exc.value.status_code == 409
        assert exc.value.detail["matched_fields"] == ["nif"]
        assert exc.value.detail["existing_client_id"] == "pw"

    @pytest.mark.asyncio
    async def test_assert_e_opaco_para_o_cliente_de_outra_rede(self, mundo):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            await mundo.assert_cliente_unico("500000000", None, rede=REDE_INCUMBENTE)
        assert set(exc.value.detail) == {"message", "code"}

    @pytest.mark.asyncio
    async def test_resolver_identidade_com_dados_reais(self, mundo):
        # a Domus apresenta NIF + Email do cliente da Power → associa
        r = await mundo.resolver_identidade("285739461", "pw@x.pt", rede=REDE_DOMUS)
        assert (r.veredicto, r.cliente["id"]) == (mundo.IDENTIDADE_ASSOCIAR, "pw")
        # só o NIF → opaco, e o cliente nunca sai da função
        r = await mundo.resolver_identidade("285739461", "outro@x.pt", rede=REDE_DOMUS)
        assert (r.veredicto, r.cliente) == (mundo.IDENTIDADE_OPACA, None)
        # a Power conhece-o por si
        r = await mundo.resolver_identidade("285739461", "pw@x.pt", rede=REDE_INCUMBENTE)
        assert (r.veredicto, r.cliente["id"]) == (mundo.IDENTIDADE_DA_MESMA_REDE, "pw")
        # a pilha por carimbar é da rede de omissão
        r = await mundo.resolver_identidade("100000001", "leg@x.pt", rede=REDE_INCUMBENTE)
        assert r.veredicto == mundo.IDENTIDADE_DA_MESMA_REDE
        r = await mundo.resolver_identidade("100000001", "leg@x.pt", rede=REDE_DOMUS)
        assert r.veredicto == mundo.IDENTIDADE_ASSOCIAR
        # livre
        r = await mundo.resolver_identidade("123456789", "livre@x.pt", rede=REDE_DOMUS)
        assert r.veredicto == mundo.IDENTIDADE_NOVA

    @pytest.mark.asyncio
    async def test_associar_regista_a_rede_sem_mexer_no_resto(self, mundo, bd):
        antes = await bd.clients.find_one({"id": "pw"}, {"_id": 0})
        assert await mundo.associar_rede_ao_cliente("pw", REDE_DOMUS) is True
        assert await mundo.associar_rede_ao_cliente("pw", REDE_DOMUS) is True
        depois = await bd.clients.find_one({"id": "pw"}, {"_id": 0})
        assert depois.pop("redes_associadas") == [REDE_DOMUS]
        assert depois == antes
        assert await mundo.associar_rede_ao_cliente("pw", "") is False
        assert await mundo.associar_rede_ao_cliente("nao-existe", REDE_DOMUS) is False


# ====================================================================
# OS ÍNDICES ÚNICOS PARCIAIS — tal como `db_indexes` os declara
# ====================================================================

NOMES = ("idx_client_nif_hash_unico", "idx_client_email_hash_unico")


async def _criar_indices(bd):
    from services.db_indexes import INDEX_DEFINITIONS, _create_index_safe

    resultados = {"created": [], "errors": [], "skipped": []}
    for idx in INDEX_DEFINITIONS["clients"]:
        if idx["name"] in NOMES:
            await _create_index_safe(bd.clients, idx, "clients", resultados)
    return resultados


class TestIndicesUnicosParciais:
    @pytest.mark.asyncio
    async def test_declarados_em_db_indexes_e_nao_so_num_passo_de_operacoes(self):
        from services.db_indexes import INDEX_DEFINITIONS

        declarados = {i["name"]: i for i in INDEX_DEFINITIONS["clients"]}
        for nome in NOMES:
            assert declarados[nome]["unique"] is True
            assert "partialFilterExpression" in declarados[nome]

    @pytest.mark.asyncio
    async def test_recusam_o_duplicado_de_nif_e_de_email(self, bd):
        resultados = await _criar_indices(bd)
        assert resultados["errors"] == [] and len(resultados["created"]) == 2
        await bd.clients.insert_one(_cifrado("a", nif="285739461", email="a@x.pt"))
        with pytest.raises(DuplicateKeyError):
            await bd.clients.insert_one(_cifrado("b", REDE_DOMUS, nif="285739461", email="b@x.pt"))
        with pytest.raises(DuplicateKeyError):
            await bd.clients.insert_one(_cifrado("c", REDE_DOMUS, nif="999999990", email="a@x.pt"))

    @pytest.mark.asyncio
    async def test_um_eliminado_nao_bloqueia_a_recriacao(self, bd):
        await _criar_indices(bd)
        await bd.clients.insert_one(_cifrado("a", nif="285739461", email="a@x.pt", is_deleted=True))
        await bd.clients.insert_one(_cifrado("a2", nif="285739461", email="a@x.pt"))
        await bd.clients.insert_one(_cifrado("a3", nif="285739461", email="a@x.pt", is_deleted=True))

    @pytest.mark.asyncio
    async def test_is_deleted_false_ausente_e_null_contam_todos_como_activos(self, bd):
        await _criar_indices(bd)
        await bd.clients.insert_one(_cifrado("a", nif="285739461", email="a@x.pt", is_deleted=False))
        for extra in ({}, {"is_deleted": None}, {"is_deleted": False}):
            with pytest.raises(DuplicateKeyError):
                await bd.clients.insert_one(_cifrado(f"x{len(extra)}", nif="285739461", email="z@x.pt", **extra))

    @pytest.mark.asyncio
    async def test_sem_nif_ou_sem_email_nao_colide(self, bd):
        """Muitos clientes sem NIF têm de poder coexistir (o campo vazio não é uma identidade)."""
        await _criar_indices(bd)
        await bd.clients.insert_one(_cifrado("a", nif="", email="a@x.pt"))
        await bd.clients.insert_one(_cifrado("b", nif="", email="b@x.pt"))
        await bd.clients.insert_one({"id": "sem-nada", "nome": "x"})
        await bd.clients.insert_one({"id": "sem-nada-2", "nome": "y"})
        await bd.clients.insert_one({"id": "hash-vazio", "nome": "z", "dados_pessoais": {"nif_hash": ""}})
        await bd.clients.insert_one({"id": "hash-vazio-2", "nome": "w", "dados_pessoais": {"nif_hash": ""}})

    @pytest.mark.asyncio
    async def test_com_duplicados_na_base_a_construcao_falha_e_diz_porque(self, bd, caplog):
        """É a razão de a limpeza vir ANTES: o índice não se constrói, o resto da aplicação não é afectado."""
        await bd.clients.insert_many([
            _cifrado("a", nif="285739461", email="a@x.pt"),
            _cifrado("b", REDE_DOMUS, nif="285739461", email="b@x.pt"),
        ])
        with caplog.at_level("ERROR"):
            resultados = await _criar_indices(bd)
        assert any("nif_hash_unico" in e and "duplicados" in e for e in resultados["errors"])
        assert any("resolve_client_duplicates" in r.message for r in caplog.records)
        # o email, sem duplicados, constrói-se à mesma
        assert any("idx_client_email_hash_unico" in c for c in resultados["created"])
        # e a pesquisa por hash continua a ter o seu índice normal declarado à parte
        nomes = set((await bd.clients.index_information()))
        assert "idx_client_nif_hash_unico" not in nomes

    @pytest.mark.asyncio
    async def test_criar_duas_vezes_e_idempotente(self, bd):
        await _criar_indices(bd)
        segunda = await _criar_indices(bd)
        assert segunda["errors"] == []

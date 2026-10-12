"""Pesquisa/categorias globais e travão do Portal contra um MongoDB REAL (D-31, remate 2).

O que um duplo NÃO prova — e que aqui se prova:

* **as PROJECÇÕES**: o duplo de Mongo ignora o segundo argumento do `find`, logo
  esconde um campo de atribuição que falte na projecção da lista agregada (o
  consultor atribuído só pelo singular legado deixava de ver o seu processo);
* `$in` sobre `process_id`, `$or` sobre `assigned_to`/`created_by` e `$group`;
* os índices TTL: `expireAfterSeconds == 0` nas DUAS colecções de tentativas e
  o `expire_at` gravado como BSON Date (a purga em si corre num ciclo de 60 s do
  servidor e foi observada à mão: ver o `worklog.md`).
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio
from fastapi import HTTPException
from motor.motor_asyncio import AsyncIOMotorClient

from tests.unit.helpers_tenant import EMPRESAS, REDE_DOMUS, UCRS, tenant_db

PASTA = "Documentação Clientes"
NUNO = {"id": "u-nuno", "name": "Nuno", "email": "nuno@domus.pt", "role": "consultor",
        "effective_role": "consultor", "is_active": True}
ADM = {"id": "u-adm", "name": "Adm", "email": "adm@domus.pt", "role": "administrativo",
       "effective_role": "administrativo", "is_active": True}
BRUNO = {"id": "u-bruno", "name": "Bruno", "email": "bruno@domus.pt", "role": "diretor",
         "effective_role": "diretor", "is_active": True}


@pytest_asyncio.fixture
async def bd():
    url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    cliente = AsyncIOMotorClient(url, serverSelectionTimeoutMS=2000)
    try:
        await cliente.admin.command("ping")
    except Exception:
        cliente.close()
        pytest.skip("MongoDB não disponível")
    nome = f"test_pesquisa_pre_idx_{uuid.uuid4().hex[:8]}"
    base = cliente[nome]
    yield base
    await cliente.drop_database(nome)
    cliente.close()


async def _semear(base):
    await base.companies.insert_many([dict(e) for e in EMPRESAS])
    await base.user_company_roles.insert_many([
        *[dict(u) for u in UCRS],
        {"user_id": "u-nuno", "company_id": "cmp-domus", "company_name": "Domus",
         "role": "consultor", "is_default": True},
        {"user_id": "u-adm", "company_id": "cmp-domus", "company_name": "Domus",
         "role": "administrativo", "is_default": True},
    ])
    await base.users.insert_many([
        {**u, "company": "Domus"} for u in (NUNO, ADM, BRUNO)
    ])
    comum = {"network_id": REDE_DOMUS, "company_id": "cmp-domus", "status": "novo"}
    await base.clients.insert_one({
        "id": "c-do-nuno", "nome": "Do Nuno", "assigned_to": "u-nuno", **comum,
    })
    await base.processes.insert_many([
        {"id": "p-indexado", "is_indexed": True, "client_id": "x0", **comum},
        {"id": "p-canonico", "is_indexed": False, "client_id": "x1",
         "assigned_consultor_id": "u-nuno", **comum},
        {"id": "p-legado", "is_indexed": False, "client_id": "x2", "consultant_id": "u-nuno", **comum},
        {"id": "p-lista", "is_indexed": False, "client_id": "x3",
         "assigned_mediador_ids": ["u-outro", "u-nuno"], **comum},
        {"id": "p-cliente", "is_indexed": False, "client_id": "c-do-nuno", **comum},
        {"id": "p-vedado", "is_indexed": False, "client_id": "x4",
         "assigned_consultor_id": "u-outro", **comum},
        {"id": "p-power", "is_indexed": False, "client_id": "x5", "status": "novo",
         "network_id": "grupo_power_precision", "company_id": "cmp-power"},
    ])

    def doc(i, pid, nome, **extra):
        return {"id": i, "process_id": pid, "filename": nome, "is_categorized": True,
                "ai_category": "Identificação", "ai_summary": "cartao",
                "s3_path": f"{PASTA}/{pid}/Identificação/{nome}", **extra}

    await base.document_metadata.insert_many([
        doc("m-indexado", "p-indexado", "a.pdf"), doc("m-canonico", "p-canonico", "b.pdf"),
        doc("m-legado", "p-legado", "c.pdf"), doc("m-lista", "p-lista", "d.pdf"),
        doc("m-cliente", "p-cliente", "e.pdf"), doc("m-vedado", "p-vedado", "f.pdf"),
        doc("m-power", "p-power", "g.pdf"),
        doc("m-index", "p-indexado", "h.pdf", s3_path=f"{PASTA}/p-indexado/Index/h.pdf"),
        doc("m-fila", "p-indexado", "i.pdf", in_index_queue=True),
    ])


@pytest.fixture
def ligado(bd):
    import services.document_queries as dq
    import services.document_visibility as dv

    s3 = MagicMock()
    s3.get_presigned_url.side_effect = lambda c: f"https://s3/{c}"
    with tenant_db(bd, dv, dq), patch.object(dq, "s3_service", s3):
        yield dv, dq


class _Pedido:
    process_id = None
    categories = None
    query = "cartao"
    limit = 100


@pytest.mark.asyncio
class TestAVisibilidadeFinaContraOMongoReal:
    async def test_o_consultor_ve_so_os_seus_e_os_indexados(self, bd, ligado):
        dv, dq = ligado
        await _semear(bd)

        ids = set(await dv.ids_de_processos_com_documentos_visiveis(NUNO))

        assert ids == {"p-indexado", "p-canonico", "p-legado", "p-lista", "p-cliente"}

    async def test_a_gestao_ve_a_pre_indexacao_da_sua_rede_e_nao_a_alheia(self, bd, ligado):
        dv, _ = ligado
        await _semear(bd)

        for gestao in (BRUNO, ADM):
            ids = set(await dv.ids_de_processos_com_documentos_visiveis(gestao))
            assert {"p-vedado", "p-canonico", "p-indexado"} <= ids
            assert "p-power" not in ids

    @pytest.mark.parametrize("quem", [NUNO, ADM, BRUNO])
    async def test_a_lista_agregada_concorda_com_a_guarda_individual(self, bd, ligado, quem):
        dv, _ = ligado
        await _semear(bd)

        agregada = set(await dv.ids_de_processos_com_documentos_visiveis(quem))
        individual = set()
        for p in await bd.processes.find({}, {"_id": 0}).to_list(100):
            try:
                await dv.assert_can_view_process_documents(quem, p)
            except HTTPException:
                continue
            individual.add(p["id"])
        assert agregada == individual

    async def test_a_pesquisa_devolve_so_o_que_o_consultor_abre(self, bd, ligado):
        _, dq = ligado
        await _semear(bd)

        r = await dq.run_search_documents(_Pedido(), user=NUNO)

        assert {d["id"] for d in r["results"]} == {
            "m-indexado", "m-canonico", "m-legado", "m-lista", "m-cliente",
        }

    async def test_as_categorias_contam_pelas_duas_vias(self, bd, ligado):
        _, dq = ligado
        await _semear(bd)

        consultor = await dq.run_get_all_categories(user=NUNO)          # em memória
        gestao = await dq.run_get_all_categories(user=BRUNO)            # agregação Mongo
        administrativo = await dq.run_get_all_categories(user=ADM)      # em memória

        assert consultor["categories"] == [{"name": "Identificação", "count": 5}]
        # Diretor vê a Index (+2) e todo o pré-indexado da rede (+1 vedado).
        assert gestao["categories"] == [{"name": "Identificação", "count": 8}]
        # Administrativo: o pré-indexado todo, mas não a Index.
        assert administrativo["categories"] == [{"name": "Identificação", "count": 6}]


@pytest.mark.asyncio
class TestOTTLDasTentativasDoPortalContraOMongoReal:
    async def test_os_dois_indices_nascem_com_zero_segundos(self, bd):
        from services.db_indexes import create_ttl_indexes

        await bd.portal_verify_attempts.insert_one({"_id": "x"})
        await bd.portal_login_attempts.insert_one({"_id": "y"})
        resultado = await create_ttl_indexes(bd)

        assert not resultado["errors"], resultado["errors"]
        for colecao, nome in (("portal_verify_attempts", "ttl_portal_verify_attempts"),
                              ("portal_login_attempts", "ttl_portal_login_attempts")):
            info = await bd[colecao].index_information()
            assert info[nome]["expireAfterSeconds"] == 0, colecao
            assert info[nome]["key"] == [("expire_at", 1)]

    async def test_as_duas_portas_gravam_uma_BSON_Date(self, bd):
        from services import portal_brute_force, portal_security

        with patch.object(portal_security, "db", bd):
            await portal_security._record_failed_attempt("portal_verify:c1")
        await portal_brute_force.registar_falha(bd, "portal_login", "a@x.pt")

        verify = await bd.portal_verify_attempts.find_one({"_id": "portal_verify:c1"})
        login = await bd.portal_login_attempts.find_one({"_id": "portal_login:a@x.pt"})
        assert isinstance(verify["expire_at"], datetime)
        assert isinstance(login["expire_at"], datetime)
        # `$type: "date"` é a pergunta que o TTL do servidor faz ao campo.
        assert await bd.portal_login_attempts.count_documents(
            {"expire_at": {"$type": "date"}}) == 1
        assert verify["expire_at"].replace(tzinfo=timezone.utc) > datetime.now(timezone.utc)

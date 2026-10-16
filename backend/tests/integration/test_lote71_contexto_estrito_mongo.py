"""Contexto estrito de empresa — contra um MongoDB REAL (Lote 7.1, Out 2026).

O ataque, escrito primeiro: um CEO com acesso à Precision (rede do grupo incumbente) e à Domus (outra
rede) trabalha COMO Domus (`X-Company-Id = cmp-domus`) e pede, por id, um processo, um cliente, uma tarefa
e um ficheiro da Precision. Antes do Lote 7.1 o cabeçalho era ignorado para quem não era Master (o âmbito
era a UNIÃO das redes dele) e o Master abria tudo por id: o registo abria. Agora tem de responder 404,
«forçando a troca na UI».

A pesquisa global é a única excepção: procura nas duas redes e etiqueta cada resultado com a empresa dona.
"""
from __future__ import annotations

import os
import uuid

import pytest
import pytest_asyncio
from fastapi import HTTPException
from motor.motor_asyncio import AsyncIOMotorClient

from tests.unit.helpers_tenant import EMPRESAS, REDE_DOMUS, REDE_INCUMBENTE, tenant_db

pytestmark = pytest.mark.asyncio

P, D = REDE_INCUMBENTE, REDE_DOMUS

#: O CEO que trabalha nas duas redes (Precision e Domus), a operar COMO Domus.
CEO_COMO_DOMUS = {
    "id": "u-ceo", "role": "ceo", "effective_role": "ceo", "name": "Rui",
    "vista_empresa_id": "cmp-domus",
}
#: O mesmo CEO, agora COMO Precision.
CEO_COMO_PRECISION = {**CEO_COMO_DOMUS, "vista_empresa_id": "cmp-precision"}
#: O mesmo CEO sem cabeçalho (pedido sem `X-Company-Id`): âmbito completo, nada a estreitar.
CEO_SEM_EMPRESA = {k: v for k, v in CEO_COMO_DOMUS.items() if k != "vista_empresa_id"}
#: O Master a operar como Domus, e o Master na vista «Sistema».
MASTER_COMO_DOMUS = {
    "id": "u-master", "role": "master", "effective_role": "master", "name": "Master",
    "vista_empresa_id": "cmp-domus",
}
MASTER_SISTEMA = {k: v for k, v in MASTER_COMO_DOMUS.items() if k != "vista_empresa_id"}
#: Um cabeçalho forjado: o CEO diz «sou a empresa Y» e não é.
CEO_COM_CABECALHO_FORJADO = {**CEO_COMO_DOMUS, "vista_empresa_id": "cmp-estranha"}


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
    base = cliente[f"test_ctx_estrito_{uuid.uuid4().hex[:8]}"]
    await base.companies.insert_many([dict(e) for e in EMPRESAS] + [
        {"id": "cmp-estranha", "name": "Estranha", "network_id": "grupo_estranho"},
    ])
    await base.user_company_roles.insert_many([
        {"user_id": "u-ceo", "company_id": "cmp-precision", "company_name": "Precision Crédito", "role": "ceo"},
        {"user_id": "u-ceo", "company_id": "cmp-domus", "company_name": "Domus", "role": "ceo"},
    ])
    await base.users.insert_many([
        {"id": "u-ceo", "name": "Rui", "role": "ceo", "is_active": True},
        {"id": "u-master", "name": "Master", "role": "master", "is_active": True},
    ])
    await base.processes.insert_many([
        {"id": "p-precision", "client_id": "c-precision", "client_name": "Cliente da Precision", "status": "novo",
         "network_id": P, "company_id": "cmp-precision", "company_name": "Precision Crédito"},
        {"id": "p-domus", "client_id": "c-domus", "client_name": "Cliente da Domus", "status": "novo",
         "network_id": D, "company_id": "cmp-domus", "company_name": "Domus"},
        # Partilhado pela Precision com a Domus: a Domus vê (janela), continua a ser da Precision.
        {"id": "p-partilhado", "client_id": "c-outro", "client_name": "Cliente Partilhado", "status": "novo",
         "network_id": P, "company_id": "cmp-precision", "company_name": "Precision Crédito",
         "partner_network_ids": [D]},
    ])
    await base.clients.insert_many([
        {"id": "c-precision", "nome": "Silva da Precision", "network_id": P, "company_id": "cmp-precision",
         "company_name": "Precision Crédito", "process_ids": ["p-precision"], "contacto": {},
         "dados_pessoais": {"nif": "111111111"}},
        {"id": "c-outro", "nome": "Outro da Precision", "network_id": P, "company_id": "cmp-precision",
         "company_name": "Precision Crédito", "process_ids": ["p-partilhado"], "contacto": {},
         "dados_pessoais": {"nif": "333333333"}},
        {"id": "c-domus", "nome": "Silva da Domus", "network_id": D, "company_id": "cmp-domus",
         "company_name": "Domus", "process_ids": ["p-domus"], "contacto": {},
         "dados_pessoais": {"nif": "222222222"}},
    ])
    await base.tasks.insert_many([
        {"id": "t-precision", "title": "Silva — tarefa da Precision", "network_id": P, "company_id": "cmp-precision",
         "process_id": "p-precision", "assigned_to": ["alguem"], "created_by": "alguem"},
        {"id": "t-domus", "title": "Silva — tarefa da Domus", "network_id": D, "company_id": "cmp-domus",
         "process_id": "p-domus", "assigned_to": ["alguem"], "created_by": "alguem"},
    ])
    yield base
    await cliente.drop_database(base.name)
    cliente.close()


def _modulos():
    import services.by_id_scope as por_id
    import services.document_path_scope as caminhos
    import services.process_owner as dona
    import services.process_scope_guard as guarda_processo
    import services.search_api_global as pesquisa

    return por_id, caminhos, dona, guarda_processo, pesquisa


class _Pedido:
    """O mínimo de um `Request` para as dependências de router."""

    def __init__(self, **path_params):
        self.path_params = path_params
        self.method = "GET"
        self.headers = {}
        self.query_params = {}
        self.scope = {"route": None}

        class _Url:
            path = "/x"

        self.url = _Url()


async def _recusa(coro) -> bool:
    try:
        await coro
    except HTTPException as exc:
        assert exc.status_code == 404, exc.detail
        return True
    return False


# ───────────────────────── abrir por id ─────────────────────────

async def test_o_ataque_o_ceo_como_domus_nao_abre_um_processo_da_precision(bd):
    from services.process_scope_guard import exigir_processo_no_ambito

    with tenant_db(bd, *_modulos()):
        assert await _recusa(exigir_processo_no_ambito(_Pedido(process_id="p-precision"), CEO_COMO_DOMUS))


async def test_o_ceo_como_domus_abre_o_processo_da_domus(bd):
    from services.process_scope_guard import exigir_processo_no_ambito

    with tenant_db(bd, *_modulos()):
        assert not await _recusa(exigir_processo_no_ambito(_Pedido(process_id="p-domus"), CEO_COMO_DOMUS))


async def test_o_ceo_como_domus_continua_a_ver_o_processo_que_lhe_partilharam(bd):
    from services.process_scope_guard import exigir_processo_no_ambito

    with tenant_db(bd, *_modulos()):
        assert not await _recusa(exigir_processo_no_ambito(_Pedido(process_id="p-partilhado"), CEO_COMO_DOMUS))


async def test_trocar_de_empresa_troca_o_que_abre(bd):
    """A contraprova da troca: o MESMO CEO, agora como Precision, abre o da Precision e não o da Domus."""
    from services.process_scope_guard import exigir_processo_no_ambito

    with tenant_db(bd, *_modulos()):
        assert not await _recusa(exigir_processo_no_ambito(_Pedido(process_id="p-precision"), CEO_COMO_PRECISION))
        assert await _recusa(exigir_processo_no_ambito(_Pedido(process_id="p-domus"), CEO_COMO_PRECISION))


async def test_sem_cabecalho_o_ceo_ve_o_que_o_seu_ambito_completo_permite(bd):
    from services.process_scope_guard import exigir_processo_no_ambito

    with tenant_db(bd, *_modulos()):
        assert not await _recusa(exigir_processo_no_ambito(_Pedido(process_id="p-precision"), CEO_SEM_EMPRESA))
        assert not await _recusa(exigir_processo_no_ambito(_Pedido(process_id="p-domus"), CEO_SEM_EMPRESA))


async def test_um_cabecalho_forjado_nao_alarga_nem_estreita(bd):
    """`X-Company-Id` de uma empresa que não é dele: o âmbito é o normal (nunca alarga)."""
    from services.process_scope_guard import exigir_processo_no_ambito

    with tenant_db(bd, *_modulos()):
        assert not await _recusa(exigir_processo_no_ambito(_Pedido(process_id="p-domus"), CEO_COM_CABECALHO_FORJADO))
        assert not await _recusa(exigir_processo_no_ambito(_Pedido(process_id="p-precision"), CEO_COM_CABECALHO_FORJADO))


async def test_o_master_como_domus_tambem_recebe_404_na_precision(bd):
    """O Lote 2 deixava o Master abrir por id com qualquer empresa escolhida; o 7.1 inverte-o."""
    from services.process_scope_guard import exigir_processo_no_ambito

    with tenant_db(bd, *_modulos()):
        assert await _recusa(exigir_processo_no_ambito(_Pedido(process_id="p-precision"), MASTER_COMO_DOMUS))
        assert not await _recusa(exigir_processo_no_ambito(_Pedido(process_id="p-domus"), MASTER_COMO_DOMUS))


async def test_o_master_na_vista_sistema_continua_a_abrir_tudo(bd):
    from services.process_scope_guard import exigir_processo_no_ambito

    with tenant_db(bd, *_modulos()):
        for pid in ("p-precision", "p-domus"):
            assert not await _recusa(exigir_processo_no_ambito(_Pedido(process_id=pid), MASTER_SISTEMA))


async def test_o_ceo_como_domus_nao_abre_o_cliente_nem_a_tarefa_da_precision(bd):
    from services.by_id_scope import exigir_cliente_no_ambito, exigir_tarefa_no_ambito

    with tenant_db(bd, *_modulos()):
        assert await _recusa(exigir_cliente_no_ambito(_Pedido(client_id="c-precision"), CEO_COMO_DOMUS))
        assert await _recusa(exigir_tarefa_no_ambito(_Pedido(task_id="t-precision"), CEO_COMO_DOMUS))
        assert not await _recusa(exigir_cliente_no_ambito(_Pedido(client_id="c-domus"), CEO_COMO_DOMUS))
        assert not await _recusa(exigir_tarefa_no_ambito(_Pedido(task_id="t-domus"), CEO_COMO_DOMUS))


async def test_o_master_como_domus_nao_abre_o_cliente_da_precision(bd):
    from services.by_id_scope import exigir_cliente_no_ambito

    with tenant_db(bd, *_modulos()):
        assert await _recusa(exigir_cliente_no_ambito(_Pedido(client_id="c-precision"), MASTER_COMO_DOMUS))
        assert not await _recusa(exigir_cliente_no_ambito(_Pedido(client_id="c-precision"), MASTER_SISTEMA))


# ───────────────────────── listar ─────────────────────────

async def test_as_listagens_ficam_na_empresa_escolhida_para_o_ceo(bd):
    from services.tenant_network import build_tenant_condition, build_tenant_process_condition

    with tenant_db(bd, *_modulos()):
        condicao = await build_tenant_condition(CEO_COMO_DOMUS)
        condicao_processos = await build_tenant_process_condition(CEO_COMO_DOMUS)

    clientes = {c["id"] async for c in bd.clients.find(condicao)}
    processos = {p["id"] async for p in bd.processes.find(condicao_processos)}
    assert clientes == {"c-domus"}
    # Os processos incluem o que a Precision partilhou com a Domus, e nenhum outro da Precision.
    assert processos == {"p-domus", "p-partilhado"}


async def test_sem_empresa_escolhida_a_listagem_do_ceo_junta_as_duas_redes(bd):
    from services.tenant_network import build_tenant_condition

    with tenant_db(bd, *_modulos()):
        condicao = await build_tenant_condition(CEO_SEM_EMPRESA)
    assert {c["id"] async for c in bd.clients.find(condicao)} == {"c-precision", "c-outro", "c-domus"}


# ───────────────────────── a excepção de ouro: a pesquisa global ─────────────────────────

async def test_a_pesquisa_global_procura_nas_duas_redes_e_etiqueta_a_empresa(bd):
    from services.search_api_global import run_global_search

    with tenant_db(bd, *_modulos()):
        r = await run_global_search("Silva", 10, CEO_COMO_DOMUS)

    clientes = {c["id"]: c for c in r["clients"]}
    assert set(clientes) == {"c-precision", "c-domus"}
    assert clientes["c-precision"]["empresa"]["company_name"] == "Precision Crédito"
    assert clientes["c-domus"]["empresa"]["company_name"] == "Domus"
    # Só o resultado de OUTRA empresa pede a troca de empresa.
    assert clientes["c-precision"]["empresa"]["e_de_outra_rede"] is True
    assert clientes["c-domus"]["empresa"]["e_de_outra_rede"] is False

    tarefas = {t["id"]: t for t in r["tasks"]}
    assert set(tarefas) == {"t-precision", "t-domus"}
    assert tarefas["t-precision"]["empresa"]["company_name"] == "Precision Crédito"


async def test_a_pesquisa_global_nao_devolve_o_carimbo_cru(bd):
    from services.search_api_global import run_global_search

    with tenant_db(bd, *_modulos()):
        r = await run_global_search("Silva", 10, CEO_COMO_DOMUS)

    for tarefa in r["tasks"]:
        assert not {"company_id", "company_name", "network_id", "company"} & set(tarefa)


async def test_a_pesquisa_global_de_um_utilizador_nao_atravessa_redes_que_nao_sao_dele(bd):
    """A excepção é do que ele PODE ver: um consultor só da Domus nunca recebe a Precision."""
    from services.search_api_global import run_global_search

    await bd.user_company_roles.insert_one(
        {"user_id": "u-dom", "company_id": "cmp-domus", "company_name": "Domus", "role": "consultor"},
    )
    consultor_da_domus = {"id": "u-dom", "role": "consultor", "effective_role": "consultor", "name": "Dom"}
    with tenant_db(bd, *_modulos()):
        r = await run_global_search("Silva", 10, consultor_da_domus)

    assert {c["id"] for c in r["clients"]} == {"c-domus"}
    assert {t["id"] for t in r["tasks"]} == {"t-domus"}
    assert {p["id"] for p in r["processes"]} <= {"p-domus", "p-partilhado"}


async def test_a_pesquisa_global_do_master_cobre_todas_as_redes(bd):
    from services.search_api_global import run_global_search

    with tenant_db(bd, *_modulos()):
        r = await run_global_search("Silva", 10, MASTER_COMO_DOMUS)
    assert {c["id"] for c in r["clients"]} == {"c-precision", "c-domus"}


# ───────────────────────── ficheiros (S3) ─────────────────────────

async def test_o_ceo_como_domus_nao_abre_um_ficheiro_da_pasta_da_precision(bd):
    from services.document_path_scope import ficheiro_no_ambito

    chave_precision = "Documentação Clientes/c-precision/irs.pdf"
    chave_domus = "Documentação Clientes/c-domus/irs.pdf"
    with tenant_db(bd, *_modulos()):
        assert await ficheiro_no_ambito(chave_precision, CEO_COMO_DOMUS) is False
        assert await ficheiro_no_ambito(chave_domus, CEO_COMO_DOMUS) is True
        assert await ficheiro_no_ambito(chave_precision, CEO_COMO_PRECISION) is True


# ───────────────────────── superfícies que decidem pelo PAPEL (calendário, imóveis, finanças) ─────────────────────────

async def test_o_master_com_empresa_escolhida_trabalha_os_dados_como_admin_dela(bd):
    """`e_papel_sem_fronteira(papel)` abria tudo ao Master fosse qual fosse a empresa escolhida."""
    from services.tenant_access_context import carregar_contexto_de_acesso, papel_para_os_dados

    with tenant_db(bd, *_modulos()):
        assert await papel_para_os_dados(MASTER_COMO_DOMUS, "master") == "admin"
        assert await papel_para_os_dados(MASTER_SISTEMA, "master") == "master"
        # Quem não é Master nunca é promovido nem despromovido por aqui.
        assert await papel_para_os_dados(CEO_COMO_DOMUS, "ceo") == "ceo"

        contexto = await carregar_contexto_de_acesso(MASTER_COMO_DOMUS)
    assert contexto.redes == (D,)
    assert contexto.papel == "admin"
    # A condição de rede que as colecções sem partilha (prazos, visitas) aplicam fica na Domus.
    assert {c["id"] async for c in bd.clients.find(contexto.condicao_de_rede)} == {"c-domus"}


async def test_o_master_com_empresa_escolhida_nao_ve_os_imoveis_de_outra_rede(bd):
    from services.property_scope import carregar_contexto_dos_imoveis, pode_ver_imovel

    await bd.properties.insert_many([
        {"id": "i-domus", "reference": "IMO-1", "network_id": D, "company_id": "cmp-domus"},
        {"id": "i-precision", "reference": "IMO-2", "network_id": P, "company_id": "cmp-precision"},
    ])
    with tenant_db(bd):
        contexto = await carregar_contexto_dos_imoveis(MASTER_COMO_DOMUS)
        sistema = await carregar_contexto_dos_imoveis(MASTER_SISTEMA)

    visiveis = {i["id"] async for i in bd.properties.find(contexto.condicao)}
    assert visiveis == {"i-domus"}
    assert {i["id"] async for i in bd.properties.find(sistema.condicao)} == {"i-domus", "i-precision"}
    assert pode_ver_imovel({"id": "i-precision", "network_id": P}, papel=contexto.papel, scope=contexto.scope) is False
    assert pode_ver_imovel({"id": "i-domus", "network_id": D}, papel=contexto.papel, scope=contexto.scope) is True


async def test_a_pesquisa_global_tambem_atravessa_redes_nos_processos(bd):
    """Os PROCESSOS são a terceira colecção da pesquisa (o mutante que a deixava estrita sobrevivia)."""
    from services.search_api_global import run_global_search

    with tenant_db(bd, *_modulos()):
        r = await run_global_search("Cliente", 10, CEO_COMO_DOMUS)

    processos = {p["id"]: p for p in r["processes"]}
    assert {"p-precision", "p-domus"} <= set(processos)
    assert processos["p-precision"]["empresa"]["company_name"] == "Precision Crédito"
    assert processos["p-precision"]["empresa"]["e_de_outra_rede"] is True
    assert processos["p-domus"]["empresa"]["e_de_outra_rede"] is False
    assert not {"company_id", "company_name", "network_id"} & set(processos["p-precision"])


# ───────────────────────── documentos do processo (visibilidade) ─────────────────────────

async def test_o_master_como_domus_nao_abre_os_documentos_de_um_processo_da_precision(bd):
    from services.document_visibility import assert_can_view_process_documents

    precision = await bd.processes.find_one({"id": "p-precision"}, {"_id": 0})
    domus = await bd.processes.find_one({"id": "p-domus"}, {"_id": 0})
    with tenant_db(bd, *_modulos()):
        with pytest.raises(HTTPException) as exc:
            await assert_can_view_process_documents(MASTER_COMO_DOMUS, precision)
        assert exc.value.status_code in (403, 404)
        await assert_can_view_process_documents(MASTER_COMO_DOMUS, domus)
        # Vista «Sistema»: o Master continua a abrir tudo.
        await assert_can_view_process_documents(MASTER_SISTEMA, precision)

"""«Janela, não porta» também para os estados FECHADOS — contra um MongoDB REAL (Lote 7.2, Out 2026).

O relato: o visitante B2B vê o Processo A (partilhado) e, se o Processo B do mesmo cliente estiver em
«Desistência», também o lista/abre. A regra é cega ao estado: o visitante só alcança os `process_ids`
que a sua empresa recebeu por partilha explícita — activo, desistido, concluído ou eliminado.
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

DOMUS = {"id": "u-domus", "role": "diretor", "effective_role": "diretor", "name": "Bruno", "company": "Domus"}
POWER = {"id": "u-power", "role": "diretor", "effective_role": "diretor", "name": "Ana", "company": "Power Real Estate"}
DOMUS_COM_EMPRESA = {**DOMUS, "vista_empresa_id": "cmp-domus"}

#: Os processos do MESMO cliente que a Domus NÃO recebeu, em estados fechados e abertos.
NAO_PARTILHADOS = {"p-desistencia", "p-concluido", "p-eliminado", "p-privado"}


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
    base = cliente[f"test_janela72_{uuid.uuid4().hex[:8]}"]
    await base.companies.insert_many([dict(e) for e in EMPRESAS])
    await base.user_company_roles.insert_many([
        {"user_id": "u-domus", "company_id": "cmp-domus", "company_name": "Domus", "role": "diretor"},
        {"user_id": "u-power", "company_id": "cmp-power", "company_name": "Power Real Estate", "role": "diretor"},
    ])
    await base.users.insert_many([
        {"id": "u-domus", "name": "Bruno", "role": "diretor", "company": "Domus", "is_active": True},
        {"id": "u-power", "name": "Ana", "role": "diretor", "company": "Power Real Estate", "is_active": True},
    ])
    await base.clients.insert_one({
        "id": "cli-p", "nome": "Cliente da Power", "network_id": P, "company_id": "cmp-power",
        "process_ids": ["p-partilhado", "p-desistencia", "p-concluido", "p-eliminado", "p-privado"],
        "contacto": {"email": "cli@p.pt"}, "dados_pessoais": {"nif": "123456789"},
    })
    comuns = {"client_id": "cli-p", "client_name": "Cliente da Power", "network_id": P, "company_id": "cmp-power",
              "client_email": "cli@p.pt", "personal_data": {"email": "cli@p.pt", "nif": "123456789"}}
    await base.processes.insert_many([
        {"id": "p-partilhado", "status": "novo", "partner_network_ids": [D], **comuns},
        {"id": "p-desistencia", "status": "desistencia", **comuns},
        {"id": "p-concluido", "status": "concluido", **comuns},
        {"id": "p-eliminado", "status": "novo", "is_deleted": True, **comuns},
        {"id": "p-privado", "status": "novo", **comuns},
    ])
    await base.workflow_statuses.insert_many([
        {"name": "novo", "label": "Novo", "order": 1, "is_active": True},
        {"name": "desistencia", "label": "Desistência", "order": 8, "is_active": False},
        {"name": "concluido", "label": "Concluído", "order": 9, "is_active": False},
    ])
    yield base
    await cliente.drop_database(base.name)
    cliente.close()


def _modulos():
    import services.client_crud as crud
    import services.client_window as janela
    import services.client_list_search as lista
    import services.client_list_titulares as titulares
    import services.client_process_ops as ops
    import services.client_active_processes as activos
    import services.by_id_scope as por_id

    return crud, janela, lista, titulares, ops, activos, por_id


def _ids_em(obj) -> set[str]:
    """Todos os ids de processos que aparecem em qualquer sítio de uma resposta."""
    texto = str(obj)
    return {pid for pid in NAO_PARTILHADOS | {"p-partilhado"} if pid in texto}


async def test_a_ficha_do_cliente_so_traz_o_processo_partilhado(bd):
    from services.client_crud import run_get_client

    with tenant_db(bd, *_modulos()):
        ficha = await run_get_client("cli-p", DOMUS)
    assert _ids_em(ficha) == {"p-partilhado"}, _ids_em(ficha)


@pytest.mark.parametrize("historico", [False, True])
async def test_clientes_registados_nao_traz_os_outros_processos(bd, historico):
    from services.client_list_search import run_list_clients

    with tenant_db(bd, *_modulos()):
        r = await run_list_clients(DOMUS, show_all=True, limit=100, historico=historico)
    assert _ids_em(r) <= {"p-partilhado"}, _ids_em(r)


async def test_os_processos_do_cliente_e_o_aviso_de_activos_nao_trazem_os_outros(bd):
    from services.client_active_processes import processos_activos_do_cliente
    from services.client_process_ops import run_get_client_processes

    with tenant_db(bd, *_modulos()):
        try:
            r1 = await run_get_client_processes("cli-p", DOMUS, include_archived=True)
        except Exception as exc:  # o cliente é de outra rede: 404 é a resposta certa
            r1 = {"erro": getattr(exc, "status_code", 0)}
        try:
            r2 = await processos_activos_do_cliente("cli-p", DOMUS)
        except Exception as exc:
            r2 = {"erro": getattr(exc, "status_code", 0)}
    assert _ids_em(r1) <= {"p-partilhado"}, r1
    assert _ids_em(r2) <= {"p-partilhado"}, r2


async def test_a_condicao_das_listagens_e_do_quadro_nao_traz_os_outros(bd):
    """A condição que o quadro, a lista e a pesquisa partilham (com a rede de omissão definida)."""
    from services.tenant_network import build_tenant_process_condition

    with tenant_db(bd, *_modulos()):
        condicao = await build_tenant_process_condition(DOMUS)
    visiveis = {p["id"] async for p in bd.processes.find(condicao)}
    assert visiveis == {"p-partilhado"}, visiveis


async def test_a_pesquisa_global_nao_traz_os_outros(bd):
    from services.search_api_global import run_global_search
    import services.search_api_global as pesquisa
    import services.process_owner as dona

    with tenant_db(bd, *_modulos(), pesquisa, dona):
        r = await run_global_search("Cliente", 20, DOMUS)
    assert _ids_em(r) <= {"p-partilhado"}, _ids_em(r)


async def test_contraprova_o_dono_ve_todos_os_seus_processos(bd):
    from services.client_crud import run_get_client

    with tenant_db(bd, *_modulos()):
        ficha = await run_get_client("cli-p", POWER)
    assert {p["id"] for p in ficha["processes"]} >= {"p-partilhado", "p-desistencia", "p-concluido", "p-privado"}


# ───────────────────────── processos antigos, sem carimbo, em estados fechados ─────────────────────────

@pytest_asyncio.fixture
async def bd_com_legado(bd, monkeypatch):
    """O mesmo cliente, agora com processos FECHADOS e ANTIGOS: sem carimbo de rede nem de empresa."""
    monkeypatch.delenv("TENANT_DEFAULT_NETWORK_ID", raising=False)  # dev/CI/QA: a pilha por carimbar é visível a todos
    antigo = {"client_id": "cli-p", "client_name": "Cliente da Power", "client_email": "cli@p.pt",
              "personal_data": {"email": "cli@p.pt", "nif": "123456789"}}
    await bd.processes.insert_many([
        {"id": "p-legado-desistencia", "status": "desistencia", **antigo},
        {"id": "p-legado-concluido", "status": "concluido", **antigo},
        {"id": "p-legado-activo", "status": "novo", **antigo},
    ])
    await bd.clients.update_one({"id": "cli-p"}, {"$push": {"process_ids": {"$each": [
        "p-legado-desistencia", "p-legado-concluido", "p-legado-activo",
    ]}}})
    return bd


async def test_o_ataque_o_processo_antigo_desistido_nao_entra_na_janela_do_visitante(bd_com_legado):
    """Antes: o ramo «sem carimbo» do âmbito deixava entrar os processos antigos (fechados incluídos)."""
    from services.client_crud import run_get_client

    with tenant_db(bd_com_legado, *_modulos()):
        ficha = await run_get_client("cli-p", DOMUS)

    ids = {p["id"] for p in ficha["processes"]}
    assert ids == {"p-partilhado"}, f"a janela do visitante deixou passar: {sorted(ids - {'p-partilhado'})}"
    assert set(ficha["process_ids"]) == {"p-partilhado"}
    assert "p-legado" not in str(ficha["latest_activity"])


async def test_o_dono_continua_a_ver_os_processos_antigos(bd_com_legado):
    from services.client_crud import run_get_client

    with tenant_db(bd_com_legado, *_modulos()):
        ficha = await run_get_client("cli-p", POWER)
    ids = {p["id"] for p in ficha["processes"]}
    assert {"p-legado-desistencia", "p-legado-concluido", "p-partilhado"} <= ids


@pytest.mark.parametrize("historico", [False, True])
async def test_clientes_registados_nao_traz_os_processos_antigos_do_cliente_visitado(bd_com_legado, historico):
    """A listagem parte dos PROCESSOS: sem a janela, os antigos/desistidos entravam pela linha do cliente."""
    from services.client_list_search import run_list_clients

    with tenant_db(bd_com_legado, *_modulos()):
        r = await run_list_clients(DOMUS, show_all=True, limit=100, historico=historico)

    texto = str(r)
    assert "p-legado" not in texto, [p for p in ("p-legado-desistencia", "p-legado-concluido", "p-legado-activo") if p in texto]
    for linha in r["clients"]:
        assert {p["id"] for p in linha["processes"]} <= {"p-partilhado"}


async def test_clientes_registados_o_dono_continua_a_ver_os_antigos(bd_com_legado):
    from services.client_list_search import run_list_clients

    with tenant_db(bd_com_legado, *_modulos()):
        r = await run_list_clients(POWER, show_all=True, limit=100, historico=True)
        activos = await run_list_clients(POWER, show_all=True, limit=100, historico=False)
    todos = str(r) + str(activos)
    assert "p-legado-desistencia" in todos or "p-legado-concluido" in todos


async def test_o_processo_carimbado_com_a_rede_do_visitante_continua_a_ver_se(bd_com_legado):
    """Um processo MOVIDO para a Domus (Lote 6) é dela: o visitante da ficha vê-o, partilhado ou não."""
    from services.client_crud import run_get_client

    await bd_com_legado.processes.insert_one({
        "id": "p-movido", "client_id": "cli-p", "status": "desistencia", "network_id": D,
        "company_id": "cmp-domus", "client_name": "Cliente da Power",
    })
    await bd_com_legado.clients.update_one({"id": "cli-p"}, {"$push": {"process_ids": "p-movido"}})
    with tenant_db(bd_com_legado, *_modulos()):
        ficha = await run_get_client("cli-p", DOMUS)
    assert {p["id"] for p in ficha["processes"]} == {"p-partilhado", "p-movido"}

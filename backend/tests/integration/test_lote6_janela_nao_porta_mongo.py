"""«Janela, não porta» — contra um MongoDB REAL (Lote 6, Out 2026).

Partilhar UM processo com outra empresa abre aquele negócio, não o cliente todo. O ataque, escrito
primeiro: a Domus recebe da Power o processo `p-partilhado` de um cliente que tem outro processo,
`p-privado`. Com a ficha do titular aberta (tem de abrir), a Domus NÃO pode ver nem derivar:

* o outro processo, a actividade dele, o código de acesso e o magic link do Portal do cliente;
* a ficha do cliente na lista «Clientes Registados» (as linhas saem dos processos);
* nem reescrever, ao editar a ficha, os outros processos do cliente.

E o operador da Domus (ou o Master com a Domus seleccionada) nunca vê nem atribui a um operador
da Power, mesmo num processo partilhado.
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
MASTER_NA_DOMUS = {
    "id": "u-master", "role": "master", "effective_role": "master", "name": "Master",
    "vista_empresa_id": "cmp-domus",
}
MASTER_SEM_VISTA = {"id": "u-master", "role": "master", "effective_role": "master", "name": "Master"}


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
    base = cliente[f"test_janela_{uuid.uuid4().hex[:8]}"]
    await base.companies.insert_many([dict(e) for e in EMPRESAS])
    await base.user_company_roles.insert_many([
        {"user_id": "u-domus", "company_id": "cmp-domus", "company_name": "Domus", "role": "diretor"},
        {"user_id": "u-power", "company_id": "cmp-power", "company_name": "Power Real Estate", "role": "diretor"},
        {"user_id": "dom-1", "company_id": "cmp-domus", "company_name": "Domus", "role": "consultor"},
        {"user_id": "pow-1", "company_id": "cmp-power", "company_name": "Power Real Estate", "role": "consultor"},
    ])
    await base.users.insert_many([
        {"id": "u-domus", "name": "Bruno", "role": "diretor", "company": "Domus", "is_active": True},
        {"id": "u-power", "name": "Ana", "role": "diretor", "company": "Power Real Estate", "is_active": True},
        {"id": "dom-1", "name": "Operador Domus", "role": "consultor", "company": "Domus", "is_active": True},
        {"id": "pow-1", "name": "Operador Power", "role": "consultor", "company": "Power Real Estate", "is_active": True},
        {"id": "u-master", "name": "Master", "role": "master", "is_active": True},
    ])
    await base.clients.insert_many([
        {"id": "cli-p", "nome": "Cliente da Power", "network_id": P, "company_id": "cmp-power",
         "process_ids": ["p-partilhado", "p-privado"], "portal_access_code": "COD-SECRETO",
         "contacto": {"email": "cli@p.pt"}, "dados_pessoais": {"nif": "123456789"}},
        {"id": "cli-d", "nome": "Cliente da Domus", "network_id": D, "company_id": "cmp-domus",
         "process_ids": ["p-domus"], "contacto": {"email": "d@d.pt"}, "dados_pessoais": {}},
    ])
    await base.processes.insert_many([
        {"id": "p-partilhado", "client_id": "cli-p", "client_name": "Cliente da Power", "status": "novo",
         "network_id": P, "company_id": "cmp-power", "partner_network_ids": [D],
         "client_email": "cli@p.pt", "personal_data": {"email": "cli@p.pt", "nif": "123456789"}},
        {"id": "p-privado", "client_id": "cli-p", "client_name": "Cliente da Power", "status": "novo",
         "network_id": P, "company_id": "cmp-power", "client_email": "cli@p.pt",
         "personal_data": {"email": "cli@p.pt", "nif": "123456789"}},
        {"id": "p-domus", "client_id": "cli-d", "client_name": "Cliente da Domus", "status": "novo",
         "network_id": D, "company_id": "cmp-domus"},
    ])
    await base.activities.insert_many([
        {"id": "a-1", "process_id": "p-partilhado", "comment": "nota do partilhado", "created_at": "2026-10-01"},
        {"id": "a-2", "process_id": "p-privado", "comment": "SEGREDO do privado", "created_at": "2026-10-10"},
    ])
    await base.portal_tokens.insert_many([
        {"process_id": "p-privado", "short_id": "SEGREDO-PRIV", "created_at": "2026-10-01"},
    ])
    yield base
    await cliente.drop_database(base.name)
    cliente.close()


def _modulos():
    import services.client_crud as crud
    import services.client_window as janela
    import services.client_list_search as lista
    import services.client_list_titulares as titulares
    import services.assignment_network_guard as guarda
    import services.admin_users_scope as escopo
    import services.users_api_list as ulist
    import services.user_company_labels as etiquetas
    import services.origem_financeira as origem
    import services.by_id_scope as por_id
    import services.client_uniqueness as unicidade

    return crud, janela, lista, titulares, guarda, escopo, ulist, etiquetas, origem, por_id, unicidade


# ───────────────────────── a ficha do cliente ─────────────────────────

async def test_o_visitante_ve_so_o_processo_partilhado(bd):
    from services.client_crud import run_get_client

    with tenant_db(bd, *_modulos()):
        ficha = await run_get_client("cli-p", DOMUS)

    assert [p["id"] for p in ficha["processes"]] == ["p-partilhado"]
    assert ficha["process_ids"] == ["p-partilhado"]
    assert "SEGREDO" not in str(ficha["latest_activity"])
    assert (ficha["latest_activity"] or {}).get("id") == "a-1"


async def test_o_visitante_nao_recebe_o_acesso_do_cliente_ao_portal(bd):
    from services.client_crud import run_get_client

    with tenant_db(bd, *_modulos()):
        ficha = await run_get_client("cli-p", DOMUS)

    assert ficha["portal_access"] is None
    assert "portal_access_code" not in ficha
    assert "COD-SECRETO" not in str(ficha)
    assert "SEGREDO-PRIV" not in str(ficha)


async def test_contraprova_o_dono_ve_tudo_incluindo_o_acesso(bd):
    from services.client_crud import run_get_client

    with tenant_db(bd, *_modulos()):
        ficha = await run_get_client("cli-p", POWER)

    assert {p["id"] for p in ficha["processes"]} == {"p-partilhado", "p-privado"}
    assert ficha["portal_access"]["short_id"] == "SEGREDO-PRIV"
    assert ficha["portal_access"]["portal_access_code"] == "COD-SECRETO"


async def test_o_master_sem_empresa_escolhida_nao_tem_janela(bd):
    """Lote 6: «a conta Master não tem janela». Lote 7.1: só na vista «Sistema».

    Com a Domus escolhida (`MASTER_NA_DOMUS`) o Master é um operador da Domus e, como ela, é um
    VISITANTE da ficha de um cliente da Power que só alcança por um processo partilhado — a asserção
    antiga («vê os dois processos») foi INVERTIDA, não apagada. O contexto estrito vale também para
    quem não tem fronteira de dados.
    """
    from services.client_crud import run_get_client

    with tenant_db(bd, *_modulos()):
        sistema = await run_get_client("cli-p", MASTER_SEM_VISTA)
        na_domus = await run_get_client("cli-p", MASTER_NA_DOMUS)

    assert {p["id"] for p in sistema["processes"]} == {"p-partilhado", "p-privado"}
    assert {p["id"] for p in na_domus["processes"]} == {"p-partilhado"}
    assert na_domus["portal_access"] is None


# ───────────────────────── a lista «Clientes Registados» ─────────────────────────

@pytest.mark.parametrize("quem", [DOMUS, MASTER_NA_DOMUS], ids=["diretor-domus", "master-na-domus"])
async def test_a_lista_de_clientes_nao_traz_a_ficha_de_outra_rede(bd, quem):
    from services.client_list_search import run_list_clients

    with tenant_db(bd, *_modulos()):
        resposta = await run_list_clients(quem, show_all=True, limit=100)

    ids = {c["id"] for c in resposta["clients"]}
    assert ids == {"cli-d"}, f"clientes de outra rede na lista: {sorted(ids - {'cli-d'})}"
    assert "123456789" not in str(resposta)


async def test_contraprova_o_processo_partilhado_continua_a_ver_se_como_processo(bd):
    """A janela é sobre o CLIENTE: o processo partilhado não desaparece de onde é um processo."""
    from services.process_list_filters import build_kanban_query
    from services.tenant_network import build_tenant_process_condition

    with tenant_db(bd, *_modulos()):
        cond = await build_tenant_process_condition(DOMUS)
        query = build_kanban_query(DOMUS, "diretor", tenant_condition=cond, show_all=True, view_mode="all")
        docs = [d async for d in bd.processes.find(query, {"_id": 0, "id": 1})]
    assert {d["id"] for d in docs} == {"p-domus", "p-partilhado"}


# ───────────────────────── a edição da ficha ─────────────────────────

async def test_editar_a_ficha_nao_reescreve_os_outros_processos(bd):
    from unittest.mock import MagicMock

    from models.client import ClientUpdate
    from services.client_crud import run_update_client

    request = MagicMock()

    async def _json():
        return {}

    request.json = _json
    quem = {**DOMUS, "permissions": {"actions": ["edit_client"]}}

    with tenant_db(bd, *_modulos()):
        await run_update_client("cli-p", ClientUpdate(contacto={"email": "novo@dominio.pt"}), request, quem)

    partilhado = await bd.processes.find_one({"id": "p-partilhado"})
    privado = await bd.processes.find_one({"id": "p-privado"})
    assert partilhado["client_email"] == "novo@dominio.pt"
    assert privado["client_email"] == "cli@p.pt", "o processo de fora da janela foi reescrito"


async def test_apagar_o_nif_a_partir_de_um_processo_partilhado_nao_limpa_os_outros(bd):
    """Os espelhos do NIF vivem em cada processo. O visitante apaga o NIF da ficha e a limpeza só
    chega ao processo que a janela dele alcança — o outro continua com o valor."""
    from unittest.mock import MagicMock

    from models.client import ClientUpdate
    from services.client_crud import run_update_client

    corpo = {"dados_pessoais": {"nif": ""}}
    request = MagicMock()

    async def _json():
        return corpo

    request.json = _json
    quem = {**DOMUS, "permissions": {"actions": ["edit_client"]}}

    with tenant_db(bd, *_modulos()):
        await run_update_client("cli-p", ClientUpdate(**corpo), request, quem)

    partilhado = await bd.processes.find_one({"id": "p-partilhado"})
    privado = await bd.processes.find_one({"id": "p-privado"})
    assert not partilhado["personal_data"].get("nif"), "o processo da janela devia ter o NIF limpo"
    assert privado["personal_data"]["nif"] == "123456789", "a limpeza atravessou a janela"


# ───────────────────────── quem se pode atribuir ─────────────────────────

async def test_o_operador_da_domus_nao_ve_a_equipa_da_power_num_processo_partilhado(bd):
    from services.users_api_list import run_get_users

    with tenant_db(bd, *_modulos()):
        lista = await run_get_users(None, DOMUS, for_assignment=True, process_id="p-partilhado")
    assert {u["id"] for u in lista} <= {"u-domus", "dom-1"}
    assert "pow-1" not in {u["id"] for u in lista}


async def test_o_master_com_a_domus_so_ve_a_domus_mesmo_num_processo_partilhado(bd):
    from services.users_api_list import run_get_users

    with tenant_db(bd, *_modulos()):
        lista = await run_get_users(None, MASTER_NA_DOMUS, for_assignment=True, process_id="p-partilhado")
    ids = {u["id"] for u in lista}
    assert "dom-1" in ids
    assert not ids & {"pow-1", "u-power"}, f"equipa de outra empresa na dropdown: {sorted(ids)}"


@pytest.mark.parametrize("para_atribuicao", [True, False])
async def test_o_master_com_a_domus_so_ve_a_domus_na_lista_geral_de_utilizadores(bd, para_atribuicao):
    """Sem processo no pedido a lista é a da empresa escolhida — também fora das dropdowns de atribuição."""
    from services.users_api_list import run_get_users

    with tenant_db(bd, *_modulos()):
        lista = await run_get_users(None, MASTER_NA_DOMUS, for_assignment=para_atribuicao)
    ids = {u["id"] for u in lista}
    assert "dom-1" in ids
    assert not ids & {"pow-1", "u-power"}, f"equipa de outra empresa na lista: {sorted(ids)}"


async def test_o_master_sem_empresa_escolhida_continua_a_ver_o_que_o_processo_alcanca(bd):
    from services.users_api_list import run_get_users

    with tenant_db(bd, *_modulos()):
        lista = await run_get_users(None, MASTER_SEM_VISTA, for_assignment=True, process_id="p-partilhado")
    ids = {u["id"] for u in lista}
    assert {"dom-1", "pow-1"} <= ids


async def test_o_master_com_a_domus_nao_atribui_a_power_nem_num_processo_partilhado(bd):
    from fastapi import HTTPException

    from services.assignment_network_guard import exigir_atribuidos_da_minha_rede

    processo = await bd.processes.find_one({"id": "p-partilhado"}, {"_id": 0})
    with tenant_db(bd, *_modulos()):
        with pytest.raises(HTTPException) as erro:
            await exigir_atribuidos_da_minha_rede(MASTER_NA_DOMUS, ["pow-1"], processo=processo, base=bd)
        assert erro.value.status_code == 403
        # contraprova: a Domus, no processo que a alcança, atribui-se
        await exigir_atribuidos_da_minha_rede(MASTER_NA_DOMUS, ["dom-1"], processo=processo, base=bd)


async def test_escolher_a_domus_num_processo_que_nao_e_dela_nao_a_abre(bd):
    from fastapi import HTTPException

    from services.assignment_network_guard import exigir_atribuidos_da_minha_rede

    processo = await bd.processes.find_one({"id": "p-privado"}, {"_id": 0})
    with tenant_db(bd, *_modulos()):
        with pytest.raises(HTTPException):
            await exigir_atribuidos_da_minha_rede(MASTER_NA_DOMUS, ["dom-1"], processo=processo, base=bd)


async def test_uma_tarefa_nao_se_atribui_a_outra_rede(bd):
    from fastapi import HTTPException

    from models.task import TaskCreate
    from services import task_api_crud

    with tenant_db(bd, *_modulos(), task_api_crud):
        with pytest.raises(HTTPException) as erro:
            await task_api_crud.run_create_task(TaskCreate(title="x", assigned_to=["pow-1"]), DOMUS)
    assert erro.value.status_code == 403


async def test_reatribuir_uma_tarefa_a_outra_rede_tambem_e_recusado(bd):
    from fastapi import HTTPException

    from models.task import TaskCreate, TaskUpdate
    from unittest.mock import AsyncMock, patch

    from services import task_api_crud, task_api_helpers

    # A notificação não é o objecto do teste (e tem a sua cadeia de `db`): o que se afirma é a guarda.
    with tenant_db(bd, *_modulos(), task_api_crud, task_api_helpers), patch.object(
        task_api_crud, "send_realtime_notification", AsyncMock(),
    ):
        tarefa = await task_api_crud.run_create_task(TaskCreate(title="x", assigned_to=["dom-1"]), DOMUS)
        with pytest.raises(HTTPException) as erro:
            await task_api_crud.run_update_task(tarefa.id, TaskUpdate(assigned_to=["pow-1"]), DOMUS)
        assert erro.value.status_code == 403
        # contraprova: dentro da própria rede reatribui-se
        await task_api_crud.run_update_task(tarefa.id, TaskUpdate(assigned_to=["u-domus"]), DOMUS)


async def test_atribuir_se_a_si_proprio_nunca_atravessa_uma_rede(bd):
    """O valor por omissão de uma tarefa é o próprio: um utilizador cuja rede não se determina
    (sem UCR) não pode ficar sem poder criar tarefas para si."""
    from services.assignment_network_guard import exigir_atribuidos_da_minha_rede

    await bd.users.insert_one({"id": "u-orfao", "name": "Sem UCR", "role": "consultor", "is_active": True})
    orfao = {"id": "u-orfao", "role": "consultor", "effective_role": "consultor", "name": "Sem UCR"}
    with tenant_db(bd, *_modulos()):
        await exigir_atribuidos_da_minha_rede(orfao, ["u-orfao"], base=bd)


async def test_contraprova_atribuir_a_outro_continua_a_exigir_a_mesma_rede(bd):
    from fastapi import HTTPException

    from services.assignment_network_guard import exigir_atribuidos_da_minha_rede

    with tenant_db(bd, *_modulos()):
        with pytest.raises(HTTPException) as erro:
            await exigir_atribuidos_da_minha_rede(DOMUS, ["u-domus", "pow-1"], base=bd)
    assert erro.value.status_code == 403


# ───────────────────────── Origem Financeira ─────────────────────────

async def test_os_candidatos_a_angariador_sao_da_empresa_escolhida_pelo_master(bd):
    from services import origem_financeira

    with tenant_db(bd, *_modulos()):
        candidatos = await origem_financeira._utilizadores_do_ambito(MASTER_NA_DOMUS)
    ids = {u["id"] for u in candidatos}
    assert "dom-1" in ids
    assert not ids & {"pow-1", "u-power"}


async def test_contraprova_o_master_sem_empresa_escolhida_ve_todos_os_candidatos(bd):
    from services import origem_financeira

    with tenant_db(bd, *_modulos()):
        candidatos = await origem_financeira._utilizadores_do_ambito(MASTER_SEM_VISTA)
    assert {"dom-1", "pow-1"} <= {u["id"] for u in candidatos}

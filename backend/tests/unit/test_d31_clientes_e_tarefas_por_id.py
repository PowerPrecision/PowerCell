"""
D-31 — o cliente e a tarefa pedidos POR ID têm de ser da rede de quem pede.

O ACHADO (adenda de RBAC)
  `GET/PUT/DELETE /clients/{id}` e `/tasks/{id}` faziam `find_one({"id": x})`
  e mais nada: `get_current_user` autoriza o VERBO, não o OBJECTO. Um
  consultor da Domus (ilha) que soubesse o id de um cliente da Power lia-o com
  o NIF desencriptado, editava-o ou eliminava-o em cascata.

COMO SE TESTA
  A dependência lê `request.path_params`, que só existe quando o FastAPI
  resolve a rota — por isso monta-se uma aplicação com os ROUTERS REAIS
  (`routes.clients`, `routes.tasks`, `routes.restore`) e pede-se por HTTP. Os
  `run_*` são substituídos por sentinelas: se a guarda deixar passar, o
  sentinela é chamado e o teste vê-o; o teste do ataque exige que o handler
  NUNCA seja chamado (um 404 que viesse do handler provava o contrário).
"""
from __future__ import annotations

import contextlib
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from services import by_id_scope as guard
from services.auth import get_current_user
from tests.unit.helpers_tenant import (  # noqa: F401  (rede_de_omissao_incumbente é fixture)
    REDE_DOMUS,
    REDE_INCUMBENTE,
    rede_de_omissao_incumbente,
    semear,
    tenant_db,
)

UTILIZADORES = {
    "ana": {"id": "u-ana", "role": "diretor", "effective_role": "diretor", "name": "Ana"},         # Power
    "bruno": {"id": "u-bruno", "role": "diretor", "effective_role": "diretor", "name": "Bruno"},   # Domus
    "carla": {"id": "u-carla", "role": "consultor", "effective_role": "consultor", "name": "Carla"},
    "master": {"id": "u-master", "role": "master", "effective_role": "master", "name": "M"},
    "admin_domus": {"id": "u-adm-domus", "role": "admin", "effective_role": "admin", "name": "A"},
}

DETALHE = {"sentinela": "handler chamado"}
# As rotas de tarefas têm `response_model`: o sentinela tem de o cumprir.
DETALHE_DA_TAREFA = {
    "id": "sentinela", "title": "handler chamado", "assigned_to": [], "created_by": "x",
    "created_at": "2026-10-11T00:00:00+00:00",
}

# ── nomes dos handlers que o ataque nunca pode alcançar ──
HANDLERS_DE_CLIENTES = [
    "run_get_client", "run_update_client", "run_delete_client", "run_assign_client_to_user",
    "run_link_process_to_client", "run_unlink_process_from_client", "run_create_process_for_client",
    "run_resend_portal_access", "run_get_client_processes", "run_get_client_active_processes",
]
HANDLERS_DE_TAREFAS = [
    "run_get_task", "run_update_task", "run_complete_task", "run_reopen_task", "run_delete_task",
]


def _cenario(fake_db):
    semear(fake_db)
    fake_db.user_company_roles.docs.append(
        {"user_id": "u-adm-domus", "company_id": "cmp-domus", "company_name": "Domus", "role": "admin"}
    )
    fake_db.clients.docs.extend([
        # Antigo, sem carimbo, TEM processo (só pelo lado do processo).
        {"id": "c-legado-com-processo", "nome": "Antigo da Power", "contacto": {}, "dados_pessoais": {}},
        # Registo público por reivindicar: a Pool.
        {"id": "c-pool", "nome": "Registo Público", "contacto": {}, "dados_pessoais": {}, "lead_status": "new"},
        # Criado à mão por um utilizador da Domus: `POST /clients` não carimba.
        {"id": "c-manual-domus", "nome": "Manual da Domus", "contacto": {}, "dados_pessoais": {}},
        # Titular de um processo PARTILHADO da Power com a Domus.
        {"id": "c-partilhado", "nome": "Do Processo Partilhado", "network_id": REDE_INCUMBENTE,
         "company_id": "cmp-power", "contacto": {}, "dados_pessoais": {}},
        # Pool "disfarçada": sem carimbo nem process_ids, mas um processo da Power refere-a.
        {"id": "c-sem-vinculo-no-cliente", "nome": "Vínculo só no processo", "contacto": {}, "dados_pessoais": {}},
    ])
    fake_db.clients.docs.extend([
        {"id": "c-segundo-titular", "nome": "2.º Titular", "contacto": {}, "dados_pessoais": {},
         "process_ids": ["p-com-segundo"]},
        {"id": "c-co-titular", "nome": "Co-titular", "contacto": {}, "dados_pessoais": {},
         "process_ids": ["p-com-segundo"]},
    ])
    fake_db.processes.docs.extend([
        {"id": "p-com-segundo", "client_id": "c-domus", "second_client_id": "c-segundo-titular",
         "client_ids": ["c-domus", "c-co-titular"], "status": "novo",
         "company_id": "cmp-domus", "network_id": REDE_DOMUS},
        {"id": "p-antigo", "client_id": "c-legado-com-processo", "status": "novo"},
        {"id": "p-manual-domus", "client_id": "c-manual-domus", "status": "novo",
         "company_id": "cmp-domus", "network_id": REDE_DOMUS},
        {"id": "p-power-partilhado", "client_id": "c-partilhado", "status": "novo",
         "company_id": "cmp-power", "network_id": REDE_INCUMBENTE, "partner_network_ids": [REDE_DOMUS]},
        {"id": "p-vinculo", "client_id": "c-sem-vinculo-no-cliente", "status": "novo",
         "company_id": "cmp-power", "network_id": REDE_INCUMBENTE},
    ])
    fake_db.tasks.docs.extend([
        {"id": "t-power", "title": "da Power", "assigned_to": ["u-ana"], "created_by": "u-ana",
         "network_id": REDE_INCUMBENTE, "company_id": "cmp-power"},
        {"id": "t-domus", "title": "da Domus", "assigned_to": ["u-bruno"], "created_by": "u-bruno",
         "network_id": REDE_DOMUS, "company_id": "cmp-domus"},
        {"id": "t-legada", "title": "antiga", "assigned_to": ["u-ana"], "created_by": "u-ana"},
        # Da Power, atribuída ao Bruno (Domus): a atribuição é explícita.
        {"id": "t-para-o-bruno", "title": "pedida ao Bruno", "assigned_to": ["u-bruno"],
         "created_by": "u-ana", "network_id": REDE_INCUMBENTE, "company_id": "cmp-power"},
        # Da Power, criada pelo Bruno e atribuída a outra pessoa.
        {"id": "t-criada-pelo-bruno", "title": "criada", "assigned_to": ["u-ana"],
         "created_by": "u-bruno", "network_id": REDE_INCUMBENTE, "company_id": "cmp-power"},
        # Sem carimbo, ligada a um processo da Domus.
        {"id": "t-do-processo-da-domus", "title": "do processo", "assigned_to": ["u-ana"],
         "created_by": "u-ana", "process_id": "p-manual-domus"},
        # Sem carimbo, ligada ao processo partilhado com a Domus.
        {"id": "t-do-processo-partilhado", "title": "partilhada", "assigned_to": ["u-ana"],
         "created_by": "u-ana", "process_id": "p-power-partilhado"},
    ])
    return fake_db


@pytest.fixture
def mundo(fake_async_db, rede_de_omissao_incumbente):
    import routes.clients as rc
    import routes.restore as rr
    import routes.tasks as rt
    import services.auth as auth_mod
    import services.process_scope_guard as psg

    _cenario(fake_async_db)
    atual = {"user": UTILIZADORES["ana"]}

    chamadas: dict[str, AsyncMock] = {}
    with contextlib.ExitStack() as pilha:
        pilha.enter_context(tenant_db(fake_async_db, guard, auth_mod, psg))
        for nome in HANDLERS_DE_CLIENTES:
            chamadas[nome] = AsyncMock(return_value=DETALHE)
            pilha.enter_context(patch.object(rc, nome, chamadas[nome]))
        for nome in HANDLERS_DE_TAREFAS:
            chamadas[nome] = AsyncMock(return_value=DETALHE_DA_TAREFA)
            pilha.enter_context(patch.object(rt, nome, chamadas[nome]))
        for nome in ("run_restore_client", "run_restore_task", "run_restore_process"):
            chamadas[nome] = AsyncMock(return_value=DETALHE)
            pilha.enter_context(patch.object(rr, nome, chamadas[nome]))

        app = FastAPI()
        app.include_router(rc.router)
        app.include_router(rt.router)
        app.include_router(rr.router)
        app.dependency_overrides[get_current_user] = lambda: atual["user"]
        # `require_roles` resolve a sua própria cadeia de autenticação; o
        # teste ao router pede só a guarda de âmbito, por isso as dependências
        # de papel são substituídas pelo mesmo utilizador.
        from services.auth import require_roles  # noqa: F401
        yield TestClient(app), atual, chamadas


def _como(atual, nome):
    atual["user"] = UTILIZADORES[nome]


def _corpo_do_cliente():
    return {"nome": "Novo Nome"}


# ═══════════════════════════════════════════════════════════════════
#  CLIENTES — O ATAQUE
# ═══════════════════════════════════════════════════════════════════
class TestOAtaqueAosClientes:
    @pytest.mark.parametrize("metodo", ["get", "put", "delete"])
    def test_a_Domus_nao_le_nem_edita_nem_elimina_um_cliente_da_Power(self, mundo, metodo):
        http, atual, chamadas = mundo
        _como(atual, "bruno")
        kwargs = {"json": _corpo_do_cliente()} if metodo == "put" else {}
        r = getattr(http, metodo)("/clients/c-power", **kwargs)
        assert r.status_code == 404
        assert r.json()["detail"] == "Cliente não encontrado"
        for nome in HANDLERS_DE_CLIENTES:
            chamadas[nome].assert_not_called()

    @pytest.mark.parametrize("metodo,caminho", [
        ("post", "/clients/c-power/assign"),
        ("post", "/clients/c-power/link-process?process_id=p-domus"),
        ("delete", "/clients/c-power/unlink-process/p-power"),
        ("post", "/clients/c-power/create-process"),
        ("post", "/clients/c-power/resend-portal-access"),
        ("get", "/clients/c-power/processes"),
        ("get", "/clients/c-power/active-processes"),
    ])
    def test_nem_as_sub_rotas(self, mundo, metodo, caminho):
        http, atual, chamadas = mundo
        _como(atual, "bruno")
        r = getattr(http, metodo)(caminho)
        assert r.status_code == 404, caminho
        for nome in HANDLERS_DE_CLIENTES:
            chamadas[nome].assert_not_called()

    def test_um_admin_da_Domus_e_local_e_tambem_nao_abre_a_Power(self, mundo):
        http, atual, _ = mundo
        _como(atual, "admin_domus")
        assert http.get("/clients/c-power").status_code == 404

    def test_o_404_de_um_alheio_nao_revela_se_existe(self, mundo):
        """Alheio: 404 da guarda. Inexistente: passa a guarda e é o handler que responde."""
        http, atual, chamadas = mundo
        _como(atual, "bruno")
        assert http.get("/clients/c-power").status_code == 404
        assert http.get("/clients/nao-existe").status_code == 200
        assert chamadas["run_get_client"].await_count == 1  # só o inexistente chegou lá

    def test_um_cliente_antigo_por_carimbar_com_processo_fecha_a_Domus(self, mundo):
        http, atual, _ = mundo
        _como(atual, "bruno")
        assert http.get("/clients/c-legado-com-processo").status_code == 404

    def test_uma_pool_disfarcada_tambem_fecha(self, mundo):
        """Sem carimbo e sem `process_ids`, mas um processo refere-a: não é da Pool."""
        http, atual, _ = mundo
        _como(atual, "bruno")
        assert http.get("/clients/c-sem-vinculo-no-cliente").status_code == 404

    def test_um_convidado_de_um_processo_partilhado_NAO_elimina_nem_atribui_o_cliente_do_dono(self, mundo):
        http, atual, chamadas = mundo
        _como(atual, "bruno")
        assert http.delete("/clients/c-partilhado").status_code == 404
        assert http.post("/clients/c-partilhado/assign").status_code == 404
        assert http.post("/clients/c-partilhado/create-process").status_code == 404
        chamadas["run_delete_client"].assert_not_called()
        chamadas["run_assign_client_to_user"].assert_not_called()


# ═══════════════════════════════════════════════════════════════════
#  CLIENTES — A CONTRAPROVA (os fluxos principais não regridem)
# ═══════════════════════════════════════════════════════════════════
class TestOsFluxosLegitimosDosClientes:
    @pytest.mark.parametrize("metodo", ["get", "put", "delete"])
    def test_a_Power_abre_os_seus(self, mundo, metodo):
        http, atual, _ = mundo
        _como(atual, "ana")
        kwargs = {"json": _corpo_do_cliente()} if metodo == "put" else {}
        assert getattr(http, metodo)("/clients/c-power", **kwargs).status_code == 200

    def test_a_Domus_abre_os_seus(self, mundo):
        http, atual, _ = mundo
        _como(atual, "bruno")
        assert http.get("/clients/c-domus").status_code == 200

    def test_quem_trabalha_nas_duas_redes_abre_ambas(self, mundo):
        http, atual, _ = mundo
        _como(atual, "carla")
        assert http.get("/clients/c-power").status_code == 200
        assert http.get("/clients/c-domus").status_code == 200

    def test_o_Master_abre_qualquer_um(self, mundo):
        http, atual, _ = mundo
        _como(atual, "master")
        for cid in ("c-power", "c-domus", "c-legado-com-processo", "c-pool"):
            assert http.get(f"/clients/{cid}").status_code == 200

    def test_a_rede_de_omissao_abre_o_legado_por_carimbar(self, mundo):
        http, atual, _ = mundo
        _como(atual, "ana")
        assert http.get("/clients/c-legado-com-processo").status_code == 200

    @pytest.mark.parametrize("metodo,caminho", [
        ("get", "/clients/c-pool"),
        ("post", "/clients/c-pool/assign"),
    ])
    def test_a_Pool_continua_a_poder_ser_aberta_e_reivindicada_por_qualquer_rede(self, mundo, metodo, caminho):
        """Claim-based routing: um registo por reivindicar ainda não é de ninguém."""
        http, atual, _ = mundo
        _como(atual, "bruno")
        assert getattr(http, metodo)(caminho).status_code == 200

    @pytest.mark.parametrize("metodo,caminho", [
        ("get", "/clients/c-manual-domus"),
        ("put", "/clients/c-manual-domus"),
        ("delete", "/clients/c-manual-domus"),
        ("post", "/clients/c-manual-domus/create-process"),
    ])
    def test_o_cliente_criado_a_mao_na_Domus_abre_pelo_processo_da_propria_Domus(self, mundo, metodo, caminho):
        """`POST /clients` não carimba: sem este ramo, o cartão do cliente do
        próprio processo da Domus passava a dar 404."""
        http, atual, _ = mundo
        _como(atual, "bruno")
        kwargs = {"json": _corpo_do_cliente()} if metodo == "put" else {}
        assert getattr(http, metodo)(caminho, **kwargs).status_code == 200

    @pytest.mark.parametrize("metodo", ["get", "put"])
    def test_o_convidado_de_um_processo_partilhado_le_e_edita_o_titular(self, mundo, metodo):
        """D-25: o convidado vê o processo, logo vê (e corrige) o titular."""
        http, atual, _ = mundo
        _como(atual, "bruno")
        kwargs = {"json": _corpo_do_cliente()} if metodo == "put" else {}
        assert getattr(http, metodo)("/clients/c-partilhado", **kwargs).status_code == 200

    @pytest.mark.parametrize("cid", ["c-segundo-titular", "c-co-titular"])
    def test_o_2o_titular_e_o_co_titular_de_um_processo_meu_abrem(self, mundo, cid):
        """O vínculo vive em TRÊS campos do processo, não só no `client_id`."""
        http, atual, _ = mundo
        _como(atual, "bruno")
        assert http.get(f"/clients/{cid}").status_code == 200

    def test_as_rotas_estaticas_nao_sao_afectadas(self, mundo):
        http, atual, _ = mundo
        _como(atual, "bruno")
        with patch("routes.clients.run_search_clients", AsyncMock(return_value=[])):
            assert http.get("/clients/search?q=ab").status_code == 200


# ═══════════════════════════════════════════════════════════════════
#  TAREFAS
# ═══════════════════════════════════════════════════════════════════
class TestOAtaqueasTarefas:
    @pytest.mark.parametrize("metodo,caminho", [
        ("get", "/tasks/t-power"),
        ("put", "/tasks/t-power"),
        ("put", "/tasks/t-power/complete"),
        ("put", "/tasks/t-power/reopen"),
        ("delete", "/tasks/t-power"),
    ])
    def test_a_Domus_nao_mexe_numa_tarefa_da_Power(self, mundo, metodo, caminho):
        http, atual, chamadas = mundo
        _como(atual, "bruno")
        kwargs = {"json": {"title": "x"}} if metodo == "put" and caminho.endswith("t-power") else {}
        r = getattr(http, metodo)(caminho, **kwargs)
        assert r.status_code == 404, caminho
        assert r.json()["detail"] == "Tarefa não encontrada"
        for nome in HANDLERS_DE_TAREFAS:
            chamadas[nome].assert_not_called()

    def test_uma_tarefa_antiga_por_carimbar_fecha_a_Domus(self, mundo):
        http, atual, _ = mundo
        _como(atual, "bruno")
        assert http.get("/tasks/t-legada").status_code == 404

    def test_um_admin_da_Domus_e_local(self, mundo):
        http, atual, _ = mundo
        _como(atual, "admin_domus")
        assert http.get("/tasks/t-power").status_code == 404

    def test_o_404_nao_revela_se_existe(self, mundo):
        http, atual, chamadas = mundo
        _como(atual, "bruno")
        assert http.get("/tasks/t-power").status_code == 404
        assert http.get("/tasks/nao-existe").status_code == 200
        assert chamadas["run_get_task"].await_count == 1


class TestOsFluxosLegitimosDasTarefas:
    def test_a_Power_abre_as_suas_e_a_legada(self, mundo):
        http, atual, _ = mundo
        _como(atual, "ana")
        assert http.get("/tasks/t-power").status_code == 200
        assert http.get("/tasks/t-legada").status_code == 200

    def test_a_Domus_abre_as_suas(self, mundo):
        http, atual, _ = mundo
        _como(atual, "bruno")
        for metodo, caminho in (("get", "/tasks/t-domus"), ("put", "/tasks/t-domus/complete"),
                                ("delete", "/tasks/t-domus")):
            assert getattr(http, metodo)(caminho).status_code == 200

    def test_a_tarefa_atribuida_a_mim_abre_mesmo_sendo_de_outra_rede(self, mundo):
        http, atual, _ = mundo
        _como(atual, "bruno")
        assert http.get("/tasks/t-para-o-bruno").status_code == 200

    def test_a_tarefa_criada_por_mim_abre_mesmo_sendo_de_outra_rede(self, mundo):
        http, atual, _ = mundo
        _como(atual, "bruno")
        assert http.get("/tasks/t-criada-pelo-bruno").status_code == 200

    def test_a_tarefa_de_um_processo_que_eu_vejo_abre(self, mundo):
        http, atual, _ = mundo
        _como(atual, "bruno")
        assert http.get("/tasks/t-do-processo-da-domus").status_code == 200
        assert http.get("/tasks/t-do-processo-partilhado").status_code == 200

    def test_o_Master_abre_qualquer_uma(self, mundo):
        http, atual, _ = mundo
        _como(atual, "master")
        for tid in ("t-power", "t-domus", "t-legada"):
            assert http.get(f"/tasks/{tid}").status_code == 200

    def test_o_Master_nem_resolve_o_ambito(self, mundo):
        """Camada própria: o âmbito do Master também é «sem fronteira», e as duas
        camadas dizem o mesmo — só uma observação de comportamento as distingue."""
        http, atual, _ = mundo
        _como(atual, "master")
        with patch.object(guard, "resolve_tenant_scope", AsyncMock(side_effect=AssertionError("não devia resolver"))):
            assert http.get("/tasks/t-power").status_code == 200
            assert http.get("/clients/c-power").status_code == 200

    def test_as_rotas_de_trabalhos_em_segundo_plano_e_estaticas_passam(self, mundo):
        """`acknowledge`/`cancel` operam em `background_jobs`: o id não está em `tasks`."""
        http, atual, _ = mundo
        _como(atual, "bruno")
        with patch("routes.tasks.run_acknowledge_background_task", AsyncMock(return_value={"ok": 1})), \
             patch("routes.tasks.run_cancel_background_task", AsyncMock(return_value={"ok": 1})), \
             patch("routes.tasks.run_get_my_tasks", AsyncMock(return_value=[])):
            assert http.post("/tasks/job-123/acknowledge").status_code == 200
            assert http.delete("/tasks/job-123/cancel").status_code == 200
            assert http.get("/tasks/my-tasks").status_code == 200


# ═══════════════════════════════════════════════════════════════════
#  RESTAURAR (também é um pedido por id)
# ═══════════════════════════════════════════════════════════════════
class TestRestaurar:
    def test_nao_se_restaura_o_que_e_de_outra_rede(self, mundo):
        http, atual, chamadas = mundo
        _como(atual, "bruno")
        # `require_roles` do restore usa o utilizador sobreposto; os papéis de
        # teste (diretor) estão nas listas de cliente e processo.
        assert http.post("/clients/c-power/restore").status_code == 404
        assert http.post("/tasks/t-power/restore").status_code == 404
        assert http.post("/processes/p-power/restore").status_code == 404
        for nome in ("run_restore_client", "run_restore_task", "run_restore_process"):
            chamadas[nome].assert_not_called()

    def test_restaura_o_que_e_da_propria_rede(self, mundo):
        http, atual, _ = mundo
        _como(atual, "ana")
        assert http.post("/clients/c-power/restore").status_code == 200
        assert http.post("/processes/p-power/restore").status_code == 200


# ═══════════════════════════════════════════════════════════════════
#  OS INVENTÁRIOS: a guarda não pode sair dos routers
# ═══════════════════════════════════════════════════════════════════
class TestAGuardaEstaLigada:
    def test_os_routers_levam_a_dependencia(self):
        import routes.clients as rc
        import routes.restore as rr
        import routes.tasks as rt

        def deps(router):
            return {d.dependency for d in router.dependencies}

        assert guard.exigir_cliente_no_ambito in deps(rc.router)
        assert guard.exigir_tarefa_no_ambito in deps(rt.router)
        assert {guard.exigir_cliente_no_ambito, guard.exigir_tarefa_no_ambito} <= deps(rr.router)

    def test_toda_a_rota_com_id_de_cliente_ou_tarefa_esta_num_router_com_guarda(self):
        """Contraprova do inventário: as rotas com o id no caminho existem mesmo."""
        import routes.clients as rc
        import routes.tasks as rt

        com_cliente = [r for r in rc.router.routes if "{client_id}" in r.path]
        com_tarefa = [r for r in rt.router.routes if "{task_id}" in r.path]
        assert len(com_cliente) >= 9
        assert len(com_tarefa) >= 7

    def test_o_nome_do_parametro_no_caminho_e_o_que_a_guarda_le(self):
        """A guarda lê `client_id`/`task_id`; um parâmetro renomeado numa rota
        deixaria essa rota SEM guarda sem dar erro nenhum."""
        import routes.clients as rc
        import routes.restore as rr
        import routes.tasks as rt
        import re

        for router, esperado in ((rc.router, "client_id"), (rt.router, "task_id")):
            for rota in router.routes:
                ids = set(re.findall(r"{(\w+_id)}", rota.path))
                if not ids:
                    continue  # rotas estáticas (`/me`, `/search`, listagem, criação)
                # O id do router tem de estar no caminho com o NOME que a guarda lê;
                # `unlink-process` leva também o processo a desligar (não é o objecto
                # que se pede: o objecto é o cliente).
                assert esperado in ids, (rota.path, ids)
                assert ids <= {esperado, "process_id"}, (rota.path, ids)
        for rota in rr.router.routes:
            ids = set(re.findall(r"{(\w+_id)}", rota.path))
            if "/clients/" in rota.path:
                assert ids == {"client_id"}
            if "/tasks/" in rota.path:
                assert ids == {"task_id"}
            if "/processes/" in rota.path:
                assert ids == {"process_id"}


# ═══════════════════════════════════════════════════════════════════
#  O PREDICADO PURO
# ═══════════════════════════════════════════════════════════════════
class TestAPool:
    def test_so_e_da_pool_o_que_nao_tem_marca_nem_processo_nem_conversao(self):
        assert guard.cliente_e_da_pool({"id": "x"}) is True
        assert guard.cliente_e_da_pool({"id": "x", "lead_status": "new"}) is True
        assert guard.cliente_e_da_pool({"id": "x", "lead_status": "converted"}) is False
        assert guard.cliente_e_da_pool({"id": "x", "process_ids": ["p"]}) is False
        assert guard.cliente_e_da_pool({"id": "x", "network_id": "r"}) is False
        assert guard.cliente_e_da_pool({"id": "x", "company_id": "c"}) is False
        assert guard.cliente_e_da_pool({"id": "x", "company": "Power"}) is False

    def test_a_tarefa_do_utilizador(self):
        assert guard.tarefa_e_do_utilizador({"created_by": "u"}, "u")
        assert guard.tarefa_e_do_utilizador({"assigned_to": ["a", "u"]}, "u")
        assert guard.tarefa_e_do_utilizador({"assigned_to": "u"}, "u")  # escalar legado
        assert not guard.tarefa_e_do_utilizador({"assigned_to": ["a"], "created_by": "b"}, "u")
        assert not guard.tarefa_e_do_utilizador({"created_by": ""}, "")  # sem utilizador não é de ninguém

    def test_as_projeccoes_levam_o_carimbo(self):
        """Uma projecção sem o carimbo faz o documento contar como legado e a guarda abrir."""
        from services.tenant_network import CAMPOS_DO_CARIMBO

        for campo in CAMPOS_DO_CARIMBO:
            assert campo in guard.PROJECCAO_DO_CLIENTE
            assert campo in guard.PROJECCAO_DA_TAREFA

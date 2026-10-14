"""Lote 2 (Out 2026) — o Master e a empresa que escolhe no cabeçalho.

DOIS DEFEITOS COM A MESMA RAIZ
==============================
O Master não tem fronteira de dados (`resolve_tenant_scope` devolve «tudo»).
Daí:

* **Listagens que ignoravam a empresa escolhida.** Com a Domus seleccionada no
  cabeçalho, a «Visão Global — Registos de Clientes» (e a lista de clientes, as
  tarefas, os processos…) mostrava os clientes da Precision: a condição de rede
  do Master era `{}`. A empresa activa é uma VISTA — para o Master, a vista é
  a rede dessa empresa (`tenant_network.resolve_vista_scope`).
* **Abrir por id com um chapéu de Admin.** `utilizador_e_global` olha para o
  perfil ACTIVO: um Master que veste o chapéu de Admin de uma empresa ficava
  com o âmbito dessa empresa e recebia 404 ao abrir os ficheiros de um cliente
  de outra. Abrir por id é global para a CONTA Master.

As duas metades são deliberadamente opostas (listar estreita, abrir alarga) e
cada uma precisa da sua contraprova.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi import HTTPException

from tests.unit.helpers_tenant import (  # noqa: F401  (fixtures)
    REDE_DOMUS,
    REDE_INCUMBENTE,
    casa,
    db_tenant,
    por_id,
    rede_de_omissao_incumbente,
    tenant_db,
)

MASTER = {"id": "u-master", "name": "Master", "email": "m@sistema.pt", "role": "master"}
ADMIN_DOMUS = {"id": "u-adm-domus", "name": "Admin Domus", "email": "a@domus.pt", "role": "admin"}


def _sessao(pessoa: dict, *, efectivo: str | None = None, vista: str | None = None) -> dict:
    """O utilizador como o `get_current_user` o entrega."""
    sessao = {**pessoa, "effective_role": efectivo or pessoa["role"], "is_active": True}
    if vista:
        sessao["vista_empresa_id"] = vista
    return sessao


@pytest.fixture
def mundo(db_tenant, rede_de_omissao_incumbente):  # noqa: F811
    # O Master tem um UCR de Admin SÓ na Domus — o caso do chapéu.
    db_tenant.users.docs.extend([dict(MASTER), dict(ADMIN_DOMUS)])
    db_tenant.user_company_roles.docs.extend([
        {"user_id": "u-master", "company_id": "cmp-domus", "company_name": "Domus",
         "role": "admin", "is_default": True},
        {"user_id": "u-adm-domus", "company_id": "cmp-domus", "company_name": "Domus",
         "role": "admin", "is_default": True},
    ])
    return db_tenant


# ════════════════════════════════════════════════════════════════════
#  1 · A VISTA: listar respeita a empresa escolhida
# ════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
class TestAVistaDaEmpresaNasListagens:
    async def _ids_de_clientes(self, mundo, user):
        from services.tenant_network import build_tenant_condition

        with tenant_db(mundo):
            condicao = await build_tenant_condition(user)
        return {c["id"] for c in mundo.clients.docs if casa(c, condicao)}

    async def test_a_exploracao_domus_escolhida_nao_mostra_a_precision(self, mundo):
        """O ataque (era o defeito): Master com a Domus seleccionada via a Power."""
        ids = await self._ids_de_clientes(mundo, _sessao(MASTER, vista="cmp-domus"))
        assert ids == {"c-domus"}

    async def test_power_escolhida_mostra_a_rede_incumbente_e_a_pilha_antiga(self, mundo):
        ids = await self._ids_de_clientes(mundo, _sessao(MASTER, vista="cmp-power"))
        assert ids == {"c-power", "c-legado"}

    async def test_sem_empresa_escolhida_o_master_continua_a_ver_tudo(self, mundo):
        # Contraprova: a vista global («Sistema») não foi estreitada.
        ids = await self._ids_de_clientes(mundo, _sessao(MASTER))
        assert ids == {"c-power", "c-domus", "c-legado"}

    async def test_empresa_inexistente_nao_esvazia_nem_estreita(self, mundo):
        ids = await self._ids_de_clientes(mundo, _sessao(MASTER, vista="cmp-que-nao-existe"))
        assert ids == {"c-power", "c-domus", "c-legado"}

    async def test_a_vista_vale_para_o_master_com_qualquer_chapeu(self, mundo):
        # Com o chapéu de Admin (UCR só na Domus) e a Power escolhida, a vista é a Power.
        ids = await self._ids_de_clientes(
            mundo, _sessao(MASTER, efectivo="admin", vista="cmp-power"),
        )
        assert ids == {"c-power", "c-legado"}

    async def test_quem_nao_e_master_nao_ganha_vista(self, mundo):
        """Uma chave forjada no dicionário de um Admin local não muda o âmbito dele."""
        forjado = _sessao(ADMIN_DOMUS, vista="cmp-power")
        ids = await self._ids_de_clientes(mundo, forjado)
        assert ids == {"c-domus"}

    async def test_a_condicao_de_processos_segue_a_mesma_vista(self, mundo):
        from services.tenant_network import build_tenant_process_condition

        with tenant_db(mundo):
            domus = await build_tenant_process_condition(_sessao(MASTER, vista="cmp-domus"))
            tudo = await build_tenant_process_condition(_sessao(MASTER))
        assert {p["id"] for p in mundo.processes.docs if casa(p, domus)} == {"p-domus", "p-domus-sem-rede"}
        assert {p["id"] for p in mundo.processes.docs if casa(p, tudo)} == por_id(mundo.processes.docs)

    async def test_visao_global_registos_de_clientes_respeita_a_vista(self, mundo):
        """O ecrã da queixa: `GET /admin/client-registrations`."""
        from services import admin_observability

        with tenant_db(mundo, admin_observability):
            domus = await admin_observability.run_list_client_registrations(
                _sessao(MASTER, vista="cmp-domus"),
            )
            global_ = await admin_observability.run_list_client_registrations(_sessao(MASTER))
        assert {r["id"] for r in domus["registrations"]} == {"p-domus", "p-domus-sem-rede"}
        assert domus["total"] == 2
        assert {r["id"] for r in global_["registrations"]} == por_id(mundo.processes.docs)

    async def test_as_estatisticas_dos_registos_tambem(self, mundo):
        from services import admin_observability

        with tenant_db(mundo, admin_observability):
            domus = await admin_observability.run_get_client_registrations_stats(
                _sessao(MASTER, vista="cmp-domus"),
            )
        assert domus["total"] == 2


# ════════════════════════════════════════════════════════════════════
#  2 · A VISTA CHEGA AO UTILIZADOR (o cabeçalho `X-Company-Id`)
# ════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
class TestOCabecalhoChegaAoUtilizador:
    """Um nível ABAIXO: o `get_current_user` real a ler o cabeçalho real."""

    @staticmethod
    def _pedido(**cabecalhos):
        class _Req:
            headers = dict(cabecalhos)
        return _Req()

    @staticmethod
    def _credenciais(user_id: str):
        from fastapi.security import HTTPAuthorizationCredentials

        from tests.unit.test_ws_portal_isolation import token_de_staff

        return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token_de_staff(user_id))

    async def _sessao_de(self, fake_db, user_id: str, role: str, **cabecalhos):
        from services import auth

        await fake_db.users.insert_one({"id": user_id, "name": user_id, "is_active": True, "role": role})
        with patch.object(auth, "db", fake_db):
            return await auth.get_current_user(self._pedido(**cabecalhos), self._credenciais(user_id))

    async def test_o_master_recebe_a_empresa_do_cabecalho(self, fake_async_db):
        user = await self._sessao_de(fake_async_db, "m1", "master", **{"X-Company-Id": "cmp-domus"})
        assert user["vista_empresa_id"] == "cmp-domus"

    @pytest.mark.parametrize("valor", ["", "default", "all", "   "])
    async def test_valores_que_nao_sao_uma_empresa_nao_criam_vista(self, fake_async_db, valor):
        user = await self._sessao_de(fake_async_db, "m1", "master", **{"X-Company-Id": valor})
        assert "vista_empresa_id" not in user

    async def test_quem_nao_e_master_nunca_recebe_vista(self, fake_async_db):
        user = await self._sessao_de(fake_async_db, "a1", "admin", **{"X-Company-Id": "cmp-domus"})
        assert "vista_empresa_id" not in user


# ════════════════════════════════════════════════════════════════════
#  3 · ABRIR POR ID: o Master passa com qualquer chapéu
# ════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
class TestAbrirPorIdEGlobalParaOMaster:
    async def test_a_exploracao_chapeu_de_admin_da_domus_nao_tira_a_power(self, mundo):
        """O caso real: Master com UCR de Admin só na Domus abre os ficheiros de um cliente da Power."""
        from services import by_id_scope
        from services.by_id_scope import cliente_no_ambito, id_flexivel_no_ambito

        master_com_chapeu = _sessao(MASTER, efectivo="admin")
        with tenant_db(mundo, by_id_scope):
            assert await id_flexivel_no_ambito("c-power", master_com_chapeu) is True
            assert await id_flexivel_no_ambito("p-power", master_com_chapeu) is True
            assert await cliente_no_ambito("c-power", master_com_chapeu) is True

    async def test_contraprova_um_admin_da_domus_continua_a_receber_404(self, mundo):
        from services import by_id_scope
        from services.by_id_scope import cliente_no_ambito, id_flexivel_no_ambito

        admin = _sessao(ADMIN_DOMUS)
        with tenant_db(mundo, by_id_scope):
            assert await id_flexivel_no_ambito("c-power", admin) is False
            assert await id_flexivel_no_ambito("p-power", admin) is False
            assert await cliente_no_ambito("c-power", admin) is False
            assert await id_flexivel_no_ambito("c-domus", admin) is True  # e o da casa abre

    async def test_um_id_que_nao_existe_continua_a_ser_none(self, mundo):
        # O Master passa a guarda, mas o handler é que responde o 404 de «não existe».
        from services import by_id_scope
        from services.by_id_scope import id_flexivel_no_ambito

        with tenant_db(mundo, by_id_scope):
            assert await id_flexivel_no_ambito("42e1451a-ab14", _sessao(MASTER, efectivo="admin")) is None

    async def test_os_documentos_do_processo_tambem_abrem_ao_master_com_chapeu(self, mundo):
        """A guarda do router deixava passar e a de documentos recusava logo a seguir (403)."""
        from services import document_visibility

        processo = next(p for p in mundo.processes.docs if p["id"] == "p-power")
        with tenant_db(mundo, document_visibility):
            await document_visibility.assert_can_view_process_documents(
                _sessao(MASTER, efectivo="admin"), processo,
            )

    async def test_contraprova_um_admin_da_domus_nao_abre_os_documentos_da_power(self, mundo):
        from services import document_visibility

        processo = next(p for p in mundo.processes.docs if p["id"] == "p-power")
        with tenant_db(mundo, document_visibility):
            with pytest.raises(HTTPException) as erro:
                await document_visibility.assert_can_view_process_documents(
                    _sessao(ADMIN_DOMUS), processo,
                )
        assert erro.value.status_code == 403

    async def test_o_router_real_deixa_o_master_com_chapeu_chegar_ao_handler(self, mundo):
        """A dependência REAL do router `/documents/client/{client_id}/files`."""
        from starlette.requests import Request

        from services import by_id_scope
        from services.by_id_scope import exigir_alvo_do_documento_no_ambito

        def _pedido(client_id):
            return Request({
                "type": "http", "method": "GET", "headers": [],
                "path": f"/api/documents/client/{client_id}/files",
                "path_params": {"client_id": client_id}, "query_string": b"",
            })

        with tenant_db(mundo, by_id_scope):
            await exigir_alvo_do_documento_no_ambito(_pedido("c-power"), _sessao(MASTER, efectivo="admin"))
            with pytest.raises(HTTPException) as erro:
                await exigir_alvo_do_documento_no_ambito(_pedido("c-power"), _sessao(ADMIN_DOMUS))
        assert erro.value.status_code == 404


# ════════════════════════════════════════════════════════════════════
#  4 · A DROPDOWN DE ATRIBUIÇÃO DO MASTER
# ════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
class TestADropdownDoMasterSegueAEmpresaEscolhida:
    @pytest.fixture
    def equipa(self, mundo):
        from tests.unit.helpers_tenant import ANA, BRUNO, CARLA

        for pessoa, empresa in ((ANA, "Power Real Estate"), (BRUNO, "Domus"), (CARLA, "Precision Crédito")):
            mundo.users.docs.append({**pessoa, "is_active": True, "company": empresa})
        return mundo

    async def _lista(self, equipa, user, **kw):
        from services import admin_users_scope, assignment_network_guard, users_api_list

        with tenant_db(equipa, users_api_list, admin_users_scope, assignment_network_guard):
            lista = await users_api_list.run_get_users(None, user, for_assignment=True, **kw)
        return {u["id"] for u in lista}

    async def test_com_a_domus_escolhida_so_aparece_a_equipa_da_domus(self, equipa):
        ids = await self._lista(equipa, _sessao(MASTER, vista="cmp-domus"))
        # A Carla trabalha nas duas redes (UCR também na Domus): é equipa da Domus.
        assert {"u-bruno", "u-carla"} <= ids
        assert "u-ana" not in ids

    async def test_com_a_power_escolhida_aparece_a_equipa_da_rede_incumbente(self, equipa):
        ids = await self._lista(equipa, _sessao(MASTER, vista="cmp-power"))
        assert {"u-ana", "u-carla"} <= ids and "u-bruno" not in ids

    async def test_sem_empresa_escolhida_o_master_ve_toda_a_equipa(self, equipa):
        # Contraprova: a vista global continua a listar tudo.
        ids = await self._lista(equipa, _sessao(MASTER))
        assert {"u-ana", "u-bruno", "u-carla"} <= ids

    async def test_a_lista_nao_fica_vazia_com_o_chapeu_de_admin_de_outra_empresa(self, equipa):
        # O Master só tem UCR de Admin na Domus; escolhe a Power: a equipa da Power
        # tem de aparecer (antes ficava com o âmbito do chapéu, a Domus).
        ids = await self._lista(equipa, _sessao(MASTER, efectivo="admin", vista="cmp-power"))
        assert {"u-ana", "u-carla"} <= ids

    async def test_com_um_processo_a_vista_e_o_alcance_do_processo_JUNTAM_SE(self, equipa):
        # INVERTIDO no Lote 6 («janela, não porta»). Antes mandava só o alcance do processo: com a
        # Domus escolhida, num processo da Power, a dropdown mostrava a equipa da POWER. A regra do
        # produto é que o Master atribui à empresa que tem escolhida — nunca à de outra rede — e
        # escolher uma empresa que o processo não alcança não a abre. Resultado: nada a atribuir.
        ids = await self._lista(equipa, _sessao(MASTER, vista="cmp-domus"), process_id="p-power")
        assert not ids & {"u-ana", "u-carla", "u-bruno"}, f"atribuível fora da regra: {sorted(ids)}"

    async def test_contraprova_escolhida_a_empresa_do_processo_vê_se_a_equipa_dela(self, equipa):
        ids = await self._lista(equipa, _sessao(MASTER, vista="cmp-power"), process_id="p-power")
        assert "u-bruno" not in ids
        assert {"u-ana", "u-carla"} <= ids


# ════════════════════════════════════════════════════════════════════
#  5 · NOTIFICAÇÕES: uma regra de automação não atravessa redes
# ════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
class TestAutomacaoNotificaSoARedeDoProcesso:
    """`send_notification` com `target_role` notificava TODOS os utilizadores com o
    cargo, de todas as redes — com o nome do cliente na mensagem."""

    @pytest.fixture
    def regra_mundo(self, mundo):
        mundo.processes.docs.extend([])
        # Dois diretores por rede (UCRs): Ana/Bruno vêm do cenário base (u-ana Power, u-bruno Domus).
        mundo.user_company_roles.docs.append(
            {"user_id": "u-diretor-power-2", "company_id": "cmp-precision",
             "company_name": "Precision Crédito", "role": "diretor", "is_default": True}
        )
        return mundo

    @staticmethod
    def _regra(**cfg):
        return {
            "id": "r1", "name": "Avisar diretores",
            "action": "send_notification",
            "action_config": {"message": "Novo caso de {client_name}", "target_role": "diretor", **cfg},
        }

    async def _correr(self, mundo, process_id):
        from services import alert_audience, workflow_engine

        with tenant_db(mundo, workflow_engine, alert_audience):
            ok = await workflow_engine.execute_action(
                self._regra(), {"process_id": process_id, "client_name": "Maria"},
            )
        return ok, [n["user_id"] for n in mundo.notifications.docs]

    async def test_a_exploracao_um_processo_da_power_nao_notifica_a_domus(self, regra_mundo):
        _, destinatarios = await self._correr(regra_mundo, "p-power")
        assert "u-bruno" not in destinatarios
        assert set(destinatarios) == {"u-ana", "u-diretor-power-2"}

    async def test_um_processo_da_domus_so_notifica_a_domus(self, regra_mundo):
        _, destinatarios = await self._correr(regra_mundo, "p-domus")
        assert destinatarios == ["u-bruno"]

    async def test_sem_processo_nao_se_notifica_ninguem(self, regra_mundo):
        # Falha fechada: sem rede determinável a alternativa era difundir o nome de um
        # cliente a todos os que têm o cargo.
        _, destinatarios = await self._correr(regra_mundo, None)
        assert destinatarios == []

    async def test_a_notificacao_leva_o_processo_e_a_regra(self, regra_mundo):
        await self._correr(regra_mundo, "p-domus")
        (n,) = regra_mundo.notifications.docs
        assert n["process_id"] == "p-domus" and n["rule_id"] == "r1"
        assert n["message"] == "Novo caso de Maria"


class TestSemDifusaoPorCargoAoSistemaInteiro:
    def test_a_funcao_que_difundia_a_todos_deixou_de_existir(self):
        import services.realtime_notifications as rn

        assert not hasattr(rn, "broadcast_notification")

    def test_nenhum_emissor_de_notificacoes_lista_utilizadores_por_cargo_sem_rede(self):
        """Inventário por AST do que acabou de ser corrigido: o motor de automações
        não volta a consultar `users` por cargo. (Os restantes emissores por cargo
        — alertas, relatório semanal — têm o seu ponto único e os seus testes.)"""
        import inspect

        from services import workflow_engine
        from tests.unit.helpers_fonte import codigo_sem_comentarios

        fonte = codigo_sem_comentarios(inspect.getsource(workflow_engine))
        assert "deep_role_filter(config" not in fonte
        assert "gestao_da_rede_do_processo" in fonte


@pytest.mark.asyncio
class TestClientesEmEsperaAvisaCadaRedeDoSeu:
    """A contagem somava os processos de todas as redes e ia a TODA a gestão."""

    async def _correr(self, mundo, processos):
        from services import alert_audience, scheduled_tasks

        mundo.processes.docs.clear()
        mundo.processes.docs.extend(processos)
        servico = scheduled_tasks.ScheduledTasksService()
        servico.db = mundo
        with tenant_db(mundo, alert_audience):
            criadas = await servico.check_clients_waiting_too_long(days=15)
        return criadas, {n["user_id"]: n["message"] for n in mundo.notifications.docs}

    @staticmethod
    def _espera(pid, **carimbo):
        return {"id": pid, "status": "clientes_espera", "created_at": "2020-01-01T00:00:00+00:00", **carimbo}

    async def test_a_exploracao_a_domus_nao_e_avisada_dos_clientes_da_power(self, mundo):
        _, avisos = await self._correr(mundo, [
            self._espera("w1", network_id=REDE_INCUMBENTE, company_id="cmp-power"),
            self._espera("w2", network_id=REDE_INCUMBENTE, company_id="cmp-power"),
            self._espera("w3", network_id=REDE_DOMUS, company_id="cmp-domus"),
        ])
        assert "2 cliente(s)" in avisos["u-ana"]  # a gestão da Power vê os 2 dela
        assert "1 cliente(s)" in avisos["u-bruno"]  # a da Domus só o dela

    async def test_uma_rede_sem_clientes_em_espera_nao_recebe_aviso(self, mundo):
        _, avisos = await self._correr(mundo, [
            self._espera("w1", network_id=REDE_DOMUS, company_id="cmp-domus"),
        ])
        assert "u-ana" not in avisos and "u-bruno" in avisos

    async def test_o_aviso_de_hoje_nao_se_repete(self, mundo):
        primeira, _ = await self._correr(mundo, [self._espera("w1", network_id=REDE_DOMUS, company_id="cmp-domus")])
        segunda, _ = await self._correr(mundo, [self._espera("w1", network_id=REDE_DOMUS, company_id="cmp-domus")])
        assert primeira == 3 and segunda == 0  # Bruno, o Admin da Domus e o Master (UCR de Admin lá)


@pytest.mark.asyncio
class TestAListaDeEmpresasNaoEEstreitadaPelaVista:
    """O Master escolhe a empresa de DESTINO de uma transferência noutra rede: a lista de
    empresas é administração do sistema, não uma listagem de dados de cliente."""

    async def test_o_master_com_a_domus_escolhida_continua_a_ver_todas_as_empresas(self, mundo):
        from services import companies_crud_api_list, tenant_network

        with tenant_db(mundo, companies_crud_api_list):
            resposta = await companies_crud_api_list.run_list_companies(
                user=_sessao(MASTER, vista="cmp-domus"),
            )
            # Contraprova: sem `vista=False` a lista seria só a da Domus.
            domus = await tenant_network.build_tenant_condition(_sessao(MASTER, vista="cmp-domus"))
        nomes = {c["id"] if isinstance(c, dict) else c.id for c in resposta.companies}
        assert nomes == {"cmp-power", "cmp-precision", "cmp-domus"}
        assert {e["id"] for e in mundo.companies.docs if casa(e, domus)} == {"cmp-domus"}

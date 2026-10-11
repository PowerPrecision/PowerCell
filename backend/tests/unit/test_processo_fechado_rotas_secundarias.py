"""
Processo FECHADO — as cinco áreas que ainda escreviam (D-34, Out 2026).

O QUE ESTAVA ABERTO
  A guarda do processo fechado cobria campos, ficheiros e notas, mas deixava
  cinco superfícies de fora «porque não editam o processo»: mover no Kanban
  (inclusive entre duas fases terminais), mensagens ao cliente, gerar/enviar o
  link do Portal, os registos internos de finanças e desligar o cliente. O
  resultado: um «arquivo» que ainda mexia — e que ia contra a regra do dono do
  produto («para fazer qualquer coisa, reabre-se primeiro»).

COMO SE TESTA
  * o ATAQUE primeiro: cada área tentada, nos routers REAIS, por TODOS os
    perfis — Master, Admin, CEO e Diretor. Sem excepção por cargo;
  * as finanças e o `unlink-process` não têm `{process_id}` no caminho, logo
    escapam à dependência de router: testam-se ao nível do serviço, com a
    contraprova de que num processo ABERTO continuam a funcionar;
  * a lista de excepções é afirmada por IGUALDADE — se alguém voltar a pôr
    uma destas cinco lá dentro, este ficheiro fica vermelho;
  * o 403 de «fechado» nunca é um oráculo sobre um processo de outra rede.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from models.finance import ProcessFinanceCreate
from services import process_closed_guard as guarda
from services.auth import get_current_user
from tests.unit.helpers_fonte import codigo_da_funcao_sem_comentarios
from tests.unit.helpers_tenant import (  # noqa: F401  (rede_de_omissao_incumbente é fixture)
    rede_de_omissao_incumbente,
    semear,
    tenant_db,
)

FECHADO = "p-fechado"
FECHADO_2 = "p-fechado-arquivo"
ABERTO = "p-aberto"
FECHADO_DA_DOMUS = "p-fechado-domus"

# Perfis de gestão: nenhum tem bypass. Admin e CEO são locais (Power).
PERFIS = {
    "master": {"id": "u-master", "role": "master", "effective_role": "master", "name": "M"},
    "admin": {"id": "u-admin", "role": "admin", "effective_role": "admin", "name": "A"},
    "ceo": {"id": "u-ceo", "role": "ceo", "effective_role": "ceo", "name": "C"},
    "diretor": {"id": "u-ana", "role": "diretor", "effective_role": "diretor", "name": "Ana"},
}


def _cenario(fake_db):
    semear(fake_db)
    fake_db.user_company_roles.docs.extend([
        {"user_id": "u-master", "company_id": "cmp-power", "company_name": "Power Real Estate",
         "role": "master", "is_default": True},
        {"user_id": "u-admin", "company_id": "cmp-power", "company_name": "Power Real Estate",
         "role": "admin", "is_default": True},
        {"user_id": "u-ceo", "company_id": "cmp-power", "company_name": "Power Real Estate",
         "role": "ceo", "is_default": True},
    ])
    power = {"company_id": "cmp-power", "network_id": "grupo_power_precision"}
    fake_db.processes.docs.extend([
        {"id": FECHADO, "status": "concluido", "client_name": "Fechado", **power},
        {"id": FECHADO_2, "status": "arquivo", "client_name": "Arquivo", **power},
        {"id": ABERTO, "status": "fase_bancaria", "client_name": "Aberto", **power},
        {"id": FECHADO_DA_DOMUS, "status": "concluido", "client_name": "Da Domus",
         "company_id": "cmp-domus", "network_id": "grupo_domus"},
    ])
    return fake_db


@pytest.fixture
def app_e_cliente(fake_async_db, rede_de_omissao_incumbente):
    """Os routers REAIS do processo, o utilizador à escolha e a BD falsa em toda a cadeia."""
    import routes.processes as processos
    import services.auth as auth_mod
    import services.process_scope_guard as psg
    import services.workflow_phases as wp

    _cenario(fake_async_db)
    atual = {"user": PERFIS["master"]}

    app = FastAPI()
    app.include_router(processos.router)
    app.dependency_overrides[get_current_user] = lambda: atual["user"]

    with tenant_db(fake_async_db, guarda, auth_mod, psg, wp):
        cliente = TestClient(app, raise_server_exceptions=False)
        cliente.definir_utilizador = lambda u: atual.update(user=u)
        yield cliente


def _fechou(resposta) -> bool:
    return resposta.status_code == 403 and "fechado" in resposta.text


# ====================================================================
# O ATAQUE — as cinco áreas, por todos os perfis
# ====================================================================

TENTATIVAS = {
    "kanban_para_uma_fase_activa": ("PUT", "/processes/kanban/{pid}/move?new_status=fase_bancaria", None),
    "kanban_entre_duas_terminais": ("PUT", "/processes/kanban/{pid}/move?new_status=arquivo", None),
    "mensagem_ao_cliente": ("POST", "/processes/{pid}/portal-messages", {"content": "olá"}),
    "gerar_link_do_portal": ("POST", "/processes/{pid}/generate-magic-link", None),
    "enviar_link_do_portal": ("POST", "/processes/{pid}/generate-magic-link/send", None),
    "origem_financeira": ("PUT", "/processes/{pid}/origem-financeira", {"tipo": "organica"}),
    "servico_pago_pelo_parceiro": ("PUT", "/processes/{pid}/partner-service", {"pago": True}),
}


class TestAsCincoAreasRecusamUmProcessoFechado:
    @pytest.mark.parametrize("perfil", sorted(PERFIS))
    @pytest.mark.parametrize("tentativa", sorted(TENTATIVAS))
    def test_fechado_e_403_para_todos_os_perfis(self, app_e_cliente, tentativa, perfil):
        metodo, caminho, corpo = TENTATIVAS[tentativa]
        app_e_cliente.definir_utilizador(PERFIS[perfil])
        resposta = app_e_cliente.request(metodo, caminho.format(pid=FECHADO), json=corpo)
        assert _fechou(resposta), f"{perfil}/{tentativa} → {resposta.status_code} {resposta.text[:120]}"

    def test_o_kanban_nao_mexe_nem_entre_duas_fases_terminais(self, app_e_cliente):
        """«concluído» → «arquivo»: antes passava. O estado gravado não pode mudar."""
        import services.process_closed_guard as g

        resposta = app_e_cliente.put(f"/processes/kanban/{FECHADO}/move?new_status=arquivo")
        assert _fechou(resposta)
        assert g.db.processes.docs[[d["id"] for d in g.db.processes.docs].index(FECHADO)]["status"] == "concluido"

    @pytest.mark.parametrize("tentativa", sorted(TENTATIVAS))
    def test_aberto_a_guarda_nao_atrapalha(self, app_e_cliente, tentativa):
        """Contraprova: uma guarda que recusasse sempre passava o teste de cima."""
        metodo, caminho, corpo = TENTATIVAS[tentativa]
        resposta = app_e_cliente.request(metodo, caminho.format(pid=ABERTO), json=corpo)
        assert not _fechou(resposta), f"{tentativa} → {resposta.text[:120]}"

    def test_ler_as_mensagens_do_portal_continua_a_poder(self, app_e_cliente):
        """Ler (e marcar como lidas, que é um GET) não é escrever."""
        assert not _fechou(app_e_cliente.get(f"/processes/{FECHADO}/portal-messages"))
        assert not _fechou(app_e_cliente.get(f"/processes/{FECHADO}/portal-messages/unread"))

    def test_reabrir_continua_a_funcionar(self, app_e_cliente):
        """A saída tem de existir — é a única porta que a regra deixa."""
        resposta = app_e_cliente.post(f"/processes/{FECHADO}/reopen", json={"new_status": "fase_bancaria"})
        assert not _fechou(resposta)

    def test_outra_rede_nao_ve_o_estado_sem_oraculo(self, app_e_cliente):
        """Um diretor da Power não descobre que um processo da Domus está fechado."""
        app_e_cliente.definir_utilizador(PERFIS["diretor"])
        resposta = app_e_cliente.post(f"/processes/{FECHADO_DA_DOMUS}/generate-magic-link")
        assert not _fechou(resposta)


# ====================================================================
# A LISTA DE EXCEPÇÕES — por igualdade
# ====================================================================

class TestAListaDeExcepcoes:
    def test_so_ficam_reabrir_eliminar_e_revogar_a_partilha(self):
        assert set(guarda.ROTAS_QUE_FUNCIONAM_COM_O_PROCESSO_FECHADO) == {
            ("POST", "/processes/{process_id}/reopen"),
            ("DELETE", "/processes/{process_id}"),
            ("DELETE", "/processes/{process_id}/partners/{company_id}"),
        }

    @pytest.mark.parametrize("sufixo", [
        "/kanban/{process_id}/move", "/portal-messages", "/generate-magic-link",
        "/generate-magic-link/send", "/origem-financeira", "/partner-service",
    ])
    def test_nenhuma_das_cinco_areas_voltou_a_lista(self, sufixo):
        assert not any(
            caminho.endswith(sufixo)
            for (_m, caminho) in guarda.ROTAS_QUE_FUNCIONAM_COM_O_PROCESSO_FECHADO
        )


# ====================================================================
# FINANÇAS — o caminho não leva o processo, o registo é que o conhece
# ====================================================================

def _registo(finance_id="f1", process_id=FECHADO, company_id="cmp-power"):
    return {
        "id": finance_id, "process_id": process_id, "client_id": "c-power",
        "company_id": company_id, "status": "pending", "base_business_value": 100000.0,
        "expected_commission": 1000.0, "tax_amount": 230.0, "total_with_tax": 1230.0,
        "created_at": "2026-01-01T00:00:00+00:00", "updated_at": "2026-01-01T00:00:00+00:00",
    }


def _corpo(process_id):
    return ProcessFinanceCreate(
        process_id=process_id, client_id="c-power", company_id="cmp-power",
        base_business_value=100000.0, applied_fee_type="percentage", applied_fee_value=1.0,
    )


@pytest.fixture
def financas(fake_async_db, rede_de_omissao_incumbente):
    import services.finance_process_records as fpr
    import services.workflow_phases as wp

    _cenario(fake_async_db)
    fake_async_db.process_finances.docs.extend([
        _registo("f-fechado", FECHADO),
        _registo("f-aberto", ABERTO),
    ])
    with tenant_db(fake_async_db, guarda, fpr, wp):
        yield fpr, fake_async_db


class TestFinancasDeUmProcessoFechado:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("perfil", ["master", "diretor"])
    async def test_criar_e_403(self, financas, perfil):
        fpr, bd = financas
        with pytest.raises(HTTPException) as exc:
            await fpr.run_create_process_finance(_corpo(FECHADO), PERFIS[perfil])
        assert exc.value.status_code == 403 and "fechado" in exc.value.detail
        assert not [d for d in bd.process_finances.docs if d["process_id"] == FECHADO and d["id"] != "f-fechado"]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("perfil", ["master", "diretor"])
    async def test_alterar_o_estado_e_403_e_nada_muda(self, financas, perfil):
        fpr, bd = financas
        with pytest.raises(HTTPException) as exc:
            await fpr.run_update_process_finance_status("f-fechado", "paid", PERFIS[perfil])
        assert exc.value.status_code == 403
        assert next(d for d in bd.process_finances.docs if d["id"] == "f-fechado")["status"] == "pending"

    @pytest.mark.asyncio
    async def test_editar_e_403_e_nada_muda(self, financas):
        from models.finance import ProcessFinanceUpdate

        fpr, bd = financas
        with pytest.raises(HTTPException) as exc:
            await fpr.run_update_process_finance(
                "f-fechado", ProcessFinanceUpdate(base_business_value=999.0), PERFIS["master"])
        assert exc.value.status_code == 403
        assert next(d for d in bd.process_finances.docs if d["id"] == "f-fechado")["base_business_value"] == 100000.0

    @pytest.mark.asyncio
    @pytest.mark.parametrize("perfil", ["master", "diretor"])
    async def test_eliminar_e_403_e_o_registo_fica(self, financas, perfil):
        fpr, bd = financas
        with pytest.raises(HTTPException) as exc:
            await fpr.run_delete_process_finance("f-fechado", PERFIS[perfil])
        assert exc.value.status_code == 403
        assert any(d["id"] == "f-fechado" for d in bd.process_finances.docs)

    @pytest.mark.asyncio
    async def test_num_processo_aberto_tudo_continua_a_funcionar(self, financas):
        """Contraprova: a guarda não pode ter tornado as finanças imutáveis."""
        fpr, bd = financas
        resultado = await fpr.run_update_process_finance_status("f-aberto", "paid", PERFIS["master"])
        assert resultado["new_status"] == "paid"
        criado = await fpr.run_create_process_finance(
            _corpo(ABERTO).model_copy(update={"company_id": "cmp-precision"}), PERFIS["master"])
        assert criado["process_id"] == ABERTO
        await fpr.run_delete_process_finance("f-aberto", PERFIS["master"])
        assert not any(d["id"] == "f-aberto" for d in bd.process_finances.docs)

    @pytest.mark.asyncio
    async def test_a_leitura_de_um_registo_fechado_continua_a_poder(self, financas):
        fpr, _bd = financas
        doc = await fpr.run_get_process_finance_by_id("f-fechado", PERFIS["master"])
        assert doc["id"] == "f-fechado"

    @pytest.mark.asyncio
    async def test_o_403_nao_e_oraculo_sobre_registos_de_outra_empresa(self, financas):
        """Quem não vê o registo recebe o 404 de sempre, não «fechado»."""
        fpr, bd = financas
        bd.process_finances.docs.append(_registo("f-domus", FECHADO_DA_DOMUS, "cmp-domus"))
        with pytest.raises(HTTPException) as exc:
            await fpr.run_update_process_finance_status("f-domus", "paid", PERFIS["diretor"])
        assert exc.value.status_code == 404

    def test_os_quatro_escritores_chamam_mesmo_a_guarda(self):
        """Sem isto, apagar a chamada deixava o resto verde por acaso."""
        import services.finance_process_records as fpr

        for nome in ("run_create_process_finance", "run_update_process_finance",
                     "run_update_process_finance_status", "run_delete_process_finance"):
            codigo = codigo_da_funcao_sem_comentarios(getattr(fpr, nome))
            assert "_exigir_processo_do_registo_aberto" in codigo, nome

    def test_a_guarda_corre_depois_do_ambito_e_antes_de_escrever(self):
        import services.finance_process_records as fpr

        for nome, escrita in (("run_update_process_finance_status", "update_one"),
                              ("run_delete_process_finance", "delete_one")):
            codigo = codigo_da_funcao_sem_comentarios(getattr(fpr, nome))
            assert codigo.index("exigir_registo_no_ambito") < codigo.index(
                "_exigir_processo_do_registo_aberto") < codigo.index(escrita), nome


# ====================================================================
# LIGAÇÕES — desligar o cliente de um processo fechado
# ====================================================================

@pytest.fixture
def ligacoes(fake_async_db, rede_de_omissao_incumbente):
    import services.client_process_ops as ops
    import services.workflow_phases as wp

    _cenario(fake_async_db)
    fake_async_db.clients.docs[0]["process_ids"] = [FECHADO, ABERTO]
    for pid in (FECHADO, ABERTO):
        proc = next(d for d in fake_async_db.processes.docs if d["id"] == pid)
        proc["client_id"] = "c-power"
    with tenant_db(fake_async_db, guarda, ops, wp):
        yield ops, fake_async_db


class TestDesligarUmProcessoFechado:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("perfil", sorted(PERFIS))
    async def test_desligar_e_403_e_a_relacao_fica(self, ligacoes, perfil):
        ops, bd = ligacoes
        with pytest.raises(HTTPException) as exc:
            await ops.run_unlink_process_from_client("c-power", FECHADO, PERFIS[perfil])
        assert exc.value.status_code == 403 and "fechado" in exc.value.detail
        cliente = next(d for d in bd.clients.docs if d["id"] == "c-power")
        processo = next(d for d in bd.processes.docs if d["id"] == FECHADO)
        assert FECHADO in cliente["process_ids"] and processo["client_id"] == "c-power"

    @pytest.mark.asyncio
    async def test_num_processo_aberto_continua_a_poder(self, ligacoes):
        ops, bd = ligacoes
        with patch("services.history.log_history", AsyncMock()):
            resultado = await ops.run_unlink_process_from_client("c-power", ABERTO, PERFIS["master"])
        assert resultado["success"] is True
        # (o duplo de Mongo não implementa `$pull`: a prova é o `$unset` do processo)
        assert "client_id" not in next(d for d in bd.processes.docs if d["id"] == ABERTO)

    @pytest.mark.asyncio
    async def test_um_processo_de_outra_rede_nao_responde_fechado(self, ligacoes):
        """Sem oráculo: a Power não descobre o estado de um processo da Domus."""
        ops, _bd = ligacoes
        with patch("services.history.log_history", AsyncMock()):
            resultado = await ops.run_unlink_process_from_client(
                "c-power", FECHADO_DA_DOMUS, PERFIS["diretor"])
        assert resultado["success"] is True

    def test_o_servico_chama_a_guarda_antes_de_escrever(self):
        import services.client_process_ops as ops

        codigo = codigo_da_funcao_sem_comentarios(ops.run_unlink_process_from_client)
        assert codigo.index("exigir_processo_aberto_por_id") < codigo.index("update_one")


# ====================================================================
# A LISTAGEM DIZ QUAIS ESTÃO FECHADOS — para o ecrã não oferecer o que o 403 recusa
# ====================================================================

class TestAListagemFinanceiraMarcaOsFechados:
    @pytest.mark.asyncio
    async def test_a_flag_e_calculada_ao_servir(self, financas):
        fpr, bd = financas
        resposta = await fpr.run_list_process_finances(None, None, None, None, PERFIS["master"])
        por_id = {f["id"]: f for f in resposta["finances"]}
        assert por_id["f-fechado"]["processo_fechado"] is True
        assert por_id["f-aberto"]["processo_fechado"] is False
        # nunca se persiste: um processo reaberto deixa de estar marcado
        assert all("processo_fechado" not in d for d in bd.process_finances.docs)

    @pytest.mark.asyncio
    async def test_reabrir_o_processo_desmarca_o_registo(self, financas):
        fpr, bd = financas
        next(d for d in bd.processes.docs if d["id"] == FECHADO)["status"] = "fase_bancaria"
        resposta = await fpr.run_list_process_finances(None, None, None, None, PERFIS["master"])
        assert {f["id"]: f["processo_fechado"] for f in resposta["finances"]}["f-fechado"] is False

    @pytest.mark.asyncio
    async def test_uma_falha_a_ler_os_processos_nao_derruba_a_listagem(self, financas):
        fpr, _bd = financas
        with patch.object(fpr, "carregar_fases", AsyncMock(side_effect=RuntimeError("bd em baixo"))):
            resposta = await fpr.run_list_process_finances(None, None, None, None, PERFIS["master"])
        assert resposta["total"] == 2
        assert all(f["processo_fechado"] is False for f in resposta["finances"])

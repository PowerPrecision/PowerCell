"""Pagamentos num processo FECHADO — a excepção cirúrgica ao D-34 (Out 2026).

O NEGÓCIO
  O parceiro paga no INÍCIO (comprovativo). As comissões imobiliárias e de
  crédito pagam-se no FIM, quando o processo já está «Concluído». O D-34
  fechou todos os escritores de `/finance/processes` num processo terminal —
  e com isso obrigava o administrativo a reabrir um processo só para
  registar uma entrada de dinheiro.

A EXCEPÇÃO  (e só ela)
  * só o estado «pago», e só a partir de pendente/faturado;
  * por duas vias: o PATCH do estado e «Marcar como Pago» da Lista de Processos;
  * o administrativo passa a poder fazê-lo — e SÓ isto (não fatura, não cancela,
    não edita valores);
  * deixa rasto no histórico e no trilho de auditoria;
  * tudo o resto (criar, editar valores, faturar, cancelar, eliminar,
    reverter) continua fechado.

OS TESTES
  O ATAQUE de sempre (cada outra escrita num processo fechado, por todos os
  perfis, tem de continuar a ser 403) e a contraprova de que a excepção não
  alargou nada.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from models.finance import ProcessFinanceUpdate
from services import process_closed_guard as guarda
from services.auth import get_current_user
from tests.unit.helpers_fonte import codigo_da_funcao_sem_comentarios
from tests.unit.helpers_tenant import (  # noqa: F401
    rede_de_omissao_incumbente,
    tenant_db,
)
from tests.unit.test_processo_fechado_rotas_secundarias import (
    ABERTO, FECHADO, FECHADO_2, FECHADO_DA_DOMUS, PERFIS, _cenario, _registo,
)

ADMINISTRATIVO = {
    "id": "u-adm", "role": "administrativo", "effective_role": "administrativo", "name": "Adm",
}
CONSULTOR = {"id": "u-cons", "role": "consultor", "effective_role": "consultor", "name": "Cons"}
TODOS_OS_QUE_PODEM = {**PERFIS, "administrativo": ADMINISTRATIVO}


def _semear(bd):
    _cenario(bd)
    bd.user_company_roles.docs.append(
        {"user_id": "u-adm", "company_id": "cmp-power", "company_name": "Power Real Estate",
         "role": "administrativo", "is_default": True},
    )
    bd.process_finances.docs.extend([
        _registo("f-fechado", FECHADO),
        {**_registo("f-faturado", FECHADO_2), "status": "invoiced"},
        {**_registo("f-cancelado", "p-fechado-cancelado"), "status": "cancelled"},
        {**_registo("f-pago", "p-fechado-pago"), "status": "paid"},
        _registo("f-aberto", ABERTO),
        _registo("f-domus", FECHADO_DA_DOMUS, "cmp-domus"),
    ])
    for pid in ("p-fechado-cancelado", "p-fechado-pago"):
        bd.processes.docs.append(
            {"id": pid, "status": "concluido", "client_name": pid,
             "company_id": "cmp-power", "network_id": "grupo_power_precision"})


@pytest.fixture
def financas(fake_async_db, rede_de_omissao_incumbente):
    import services.finance_process_records as fpr
    import services.workflow_phases as wp

    _semear(fake_async_db)
    with tenant_db(fake_async_db, guarda, fpr, wp), \
            patch("services.history.log_history", AsyncMock()) as historia, \
            patch("services.audit_trail_service.log_audit_event", AsyncMock()) as trilho:
        yield fpr, fake_async_db, historia, trilho


def _estado(bd, finance_id):
    return next(d for d in bd.process_finances.docs if d["id"] == finance_id)["status"]


class TestMarcarComoPagoComOProcessoFechado:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("perfil", sorted(TODOS_OS_QUE_PODEM))
    async def test_passa_a_paga_para_quem_pode(self, financas, perfil):
        fpr, bd, _h, _t = financas
        resultado = await fpr.run_update_process_finance_status(
            "f-fechado", "paid", TODOS_OS_QUE_PODEM[perfil])
        assert resultado["new_status"] == "paid"
        assert _estado(bd, "f-fechado") == "paid"

    @pytest.mark.asyncio
    async def test_a_partir_de_faturada_tambem_passa(self, financas):
        fpr, bd, _h, _t = financas
        await fpr.run_update_process_finance_status("f-faturado", "paid", PERFIS["master"])
        assert _estado(bd, "f-faturado") == "paid"

    @pytest.mark.asyncio
    async def test_deixa_rasto_no_historico_e_no_trilho(self, financas):
        fpr, _bd, historia, trilho = financas
        await fpr.run_update_process_finance_status("f-fechado", "paid", ADMINISTRATIVO)
        historia.assert_awaited_once()
        assert historia.await_args.args[0] == FECHADO
        trilho.assert_awaited_once()
        assert trilho.await_args.kwargs["action"] == "finance_marked_paid"
        assert trilho.await_args.kwargs["metadata"]["finance_id"] == "f-fechado"

    @pytest.mark.asyncio
    async def test_repetir_nao_duplica_o_rasto(self, financas):
        fpr, _bd, historia, _t = financas
        await fpr.run_update_process_finance_status("f-pago", "paid", PERFIS["master"])
        historia.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_um_rasto_que_falha_nao_faz_o_pagamento_falhar(self, financas):
        fpr, bd, historia, trilho = financas
        historia.side_effect = RuntimeError("bd em baixo")
        trilho.side_effect = RuntimeError("bd em baixo")
        await fpr.run_update_process_finance_status("f-fechado", "paid", PERFIS["master"])
        assert _estado(bd, "f-fechado") == "paid"


class TestTudoOResto_ContinuaFechado:
    """A excepção é cirúrgica: nada mais num processo fechado se abriu."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("perfil", sorted(PERFIS))
    @pytest.mark.parametrize("estado", ["pending", "invoiced", "cancelled"])
    async def test_outros_estados_sao_403(self, financas, perfil, estado):
        fpr, bd, _h, _t = financas
        with pytest.raises(HTTPException) as exc:
            await fpr.run_update_process_finance_status("f-pago", estado, PERFIS[perfil])
        assert exc.value.status_code == 403 and "fechado" in exc.value.detail
        assert _estado(bd, "f-pago") == "paid"

    @pytest.mark.asyncio
    async def test_cancelada_nao_passa_a_paga(self, financas):
        """«Cancelado → pago» é uma decisão sobre o valor: exige reabrir."""
        fpr, bd, _h, _t = financas
        with pytest.raises(HTTPException) as exc:
            await fpr.run_update_process_finance_status("f-cancelado", "paid", PERFIS["master"])
        assert exc.value.status_code == 403
        assert _estado(bd, "f-cancelado") == "cancelled"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("perfil", sorted(PERFIS))
    async def test_o_put_dos_valores_continua_fechado_mesmo_com_status_paid(self, financas, perfil):
        """O PUT pode levar valores: não é a via do pagamento."""
        fpr, bd, _h, _t = financas
        with pytest.raises(HTTPException) as exc:
            await fpr.run_update_process_finance(
                "f-fechado",
                ProcessFinanceUpdate(status="paid", base_business_value=1.0),
                PERFIS[perfil],
            )
        assert exc.value.status_code == 403
        registo = next(d for d in bd.process_finances.docs if d["id"] == "f-fechado")
        assert registo["status"] == "pending" and registo["base_business_value"] == 100000.0

    @pytest.mark.asyncio
    async def test_eliminar_continua_fechado(self, financas):
        fpr, bd, _h, _t = financas
        with pytest.raises(HTTPException) as exc:
            await fpr.run_delete_process_finance("f-fechado", PERFIS["master"])
        assert exc.value.status_code == 403
        assert any(d["id"] == "f-fechado" for d in bd.process_finances.docs)


class TestOAdministrativoSoMarcaComoPago:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("estado", ["pending", "invoiced", "cancelled"])
    async def test_nao_altera_o_resto_nem_com_o_processo_aberto(self, financas, estado):
        fpr, bd, _h, _t = financas
        with pytest.raises(HTTPException) as exc:
            await fpr.run_update_process_finance_status("f-aberto", estado, ADMINISTRATIVO)
        assert exc.value.status_code == 403 and "marcar uma comissão como paga" in exc.value.detail
        assert _estado(bd, "f-aberto") == "pending"

    @pytest.mark.asyncio
    async def test_marca_como_paga_num_processo_aberto(self, financas):
        fpr, bd, _h, _t = financas
        await fpr.run_update_process_finance_status("f-aberto", "paid", ADMINISTRATIVO)
        assert _estado(bd, "f-aberto") == "paid"

    @pytest.mark.asyncio
    async def test_a_rota_de_edicao_continua_sem_ele(self):
        import routes.finance as rota

        papeis_do_put = _papeis_da_rota(rota, "PUT", "/finance/processes/{finance_id}")
        assert "administrativo" not in papeis_do_put
        assert "administrativo" in _papeis_da_rota(rota, "PATCH", "/finance/processes/{finance_id}/status")
        assert "consultor" not in _papeis_da_rota(rota, "PATCH", "/finance/processes/{finance_id}/status")


class TestSemOraculoEForaDoAmbito:
    @pytest.mark.asyncio
    async def test_registo_de_outra_rede_e_404_e_nada_muda(self, financas):
        fpr, bd, _h, _t = financas
        with pytest.raises(HTTPException) as exc:
            await fpr.run_update_process_finance_status("f-domus", "paid", PERFIS["diretor"])
        assert exc.value.status_code == 404
        assert _estado(bd, "f-domus") == "pending"


# ====================================================================
# «Marcar como Pago» da Lista de Processos — por processo
# ====================================================================

class TestMarcarOProcessoComoPago:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("perfil", sorted(TODOS_OS_QUE_PODEM))
    async def test_paga_o_que_esta_pendente_ou_faturado(self, financas, perfil):
        fpr, bd, _h, _t = financas
        r = await fpr.run_mark_process_finances_paid(FECHADO, TODOS_OS_QUE_PODEM[perfil])
        assert r == {"process_id": FECHADO, "updated": 1, "finance_ids": ["f-fechado"]}
        assert _estado(bd, "f-fechado") == "paid"

    @pytest.mark.asyncio
    async def test_so_toca_nas_empresas_do_ambito(self, financas):
        """Uma partilha tem um registo por empresa; o de outra rede não é meu."""
        fpr, bd, _h, _t = financas
        bd.process_finances.docs.append(_registo("f-fechado-domus", FECHADO, "cmp-domus"))
        r = await fpr.run_mark_process_finances_paid(FECHADO, PERFIS["diretor"])
        assert r["finance_ids"] == ["f-fechado"]
        assert _estado(bd, "f-fechado-domus") == "pending"

    @pytest.mark.asyncio
    async def test_nao_toca_nos_cancelados_nem_nos_pagos(self, financas):
        fpr, bd, _h, _t = financas
        bd.process_finances.docs.append({**_registo("f-extra", FECHADO, "cmp-precision"), "status": "cancelled"})
        r = await fpr.run_mark_process_finances_paid(FECHADO, PERFIS["master"])
        assert r["finance_ids"] == ["f-fechado"]
        assert _estado(bd, "f-extra") == "cancelled"

    @pytest.mark.asyncio
    async def test_e_idempotente(self, financas):
        fpr, _bd, _h, _t = financas
        await fpr.run_mark_process_finances_paid(FECHADO, PERFIS["master"])
        r = await fpr.run_mark_process_finances_paid(FECHADO, PERFIS["master"])
        assert r["updated"] == 0

    @pytest.mark.asyncio
    async def test_sem_registos_no_ambito_e_404_como_se_nao_existisse(self, financas):
        fpr, _bd, _h, _t = financas
        with pytest.raises(HTTPException) as exc:
            await fpr.run_mark_process_finances_paid(FECHADO_DA_DOMUS, PERFIS["diretor"])
        assert exc.value.status_code == 404
        with pytest.raises(HTTPException) as exc2:
            await fpr.run_mark_process_finances_paid("nao-existe", PERFIS["diretor"])
        assert exc2.value.status_code == 404
        assert exc.value.detail == exc2.value.detail

    @pytest.mark.asyncio
    async def test_deixa_rasto_por_registo(self, financas):
        fpr, _bd, historia, trilho = financas
        await fpr.run_mark_process_finances_paid(FECHADO, PERFIS["master"])
        historia.assert_awaited_once()
        trilho.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_um_papel_sem_direito_e_403(self, financas):
        fpr, bd, _h, _t = financas
        with pytest.raises(HTTPException) as exc:
            await fpr.run_mark_process_finances_paid(FECHADO, CONSULTOR)
        assert exc.value.status_code == 403
        assert _estado(bd, "f-fechado") == "pending"


# ====================================================================
# As rotas reais
# ====================================================================

def _papeis_da_rota(modulo, metodo, caminho):
    from fastapi.routing import APIRoute

    for rota in modulo.router.routes:
        if isinstance(rota, APIRoute) and rota.path == caminho and metodo in rota.methods:
            for dep in rota.dependant.dependencies:
                alvo = getattr(dep.call, "__closure__", None)
                if alvo:
                    for celula in alvo:
                        conteudo = celula.cell_contents
                        if isinstance(conteudo, (list, tuple, set, frozenset)) and conteudo:
                            return {str(p) for p in conteudo}
    raise AssertionError(f"rota {metodo} {caminho} não encontrada")


@pytest.fixture
def cliente_http(fake_async_db, rede_de_omissao_incumbente):
    import routes.finance as rota
    import services.auth as auth_mod
    import services.finance_process_records as fpr
    import services.workflow_phases as wp

    _semear(fake_async_db)
    atual = {"user": PERFIS["master"]}
    app = FastAPI()
    app.include_router(rota.router)
    app.dependency_overrides[get_current_user] = lambda: atual["user"]
    with tenant_db(fake_async_db, guarda, auth_mod, fpr, wp), \
            patch("services.history.log_history", AsyncMock()), \
            patch("services.audit_trail_service.log_audit_event", AsyncMock()):
        c = TestClient(app, raise_server_exceptions=False)
        c.definir_utilizador = lambda u: atual.update(user=u)
        yield c, fake_async_db


class TestAsRotasReais:
    def test_o_administrativo_marca_a_comissao_de_um_processo_fechado(self, cliente_http):
        c, bd = cliente_http
        c.definir_utilizador(ADMINISTRATIVO)
        r = c.post(f"/finance/processes/by-process/{FECHADO}/mark-paid")
        assert r.status_code == 200, r.text
        assert r.json()["updated"] == 1
        assert _estado(bd, "f-fechado") == "paid"

    def test_o_patch_para_paid_funciona_fechado_e_para_invoiced_nao(self, cliente_http):
        c, bd = cliente_http
        c.definir_utilizador(ADMINISTRATIVO)
        assert c.patch("/finance/processes/f-fechado/status?status=invoiced").status_code == 403
        assert c.patch("/finance/processes/f-fechado/status?status=paid").status_code == 200
        assert _estado(bd, "f-fechado") == "paid"

    def test_o_consultor_nao_marca(self, cliente_http):
        c, bd = cliente_http
        c.definir_utilizador(CONSULTOR)
        assert c.post(f"/finance/processes/by-process/{FECHADO}/mark-paid").status_code == 403
        assert c.patch("/finance/processes/f-fechado/status?status=paid").status_code == 403
        assert _estado(bd, "f-fechado") == "pending"

    def test_o_put_dos_valores_continua_fechado_para_o_administrativo(self, cliente_http):
        c, _bd = cliente_http
        c.definir_utilizador(ADMINISTRATIVO)
        assert c.put("/finance/processes/f-fechado", json={"status": "paid"}).status_code == 403


class TestLigacao:
    def test_o_estado_deixa_passar_so_pago_antes_da_guarda(self):
        import services.finance_process_records as fpr

        codigo = codigo_da_funcao_sem_comentarios(fpr.run_update_process_finance_status)
        assert "e_marcar_como_pago_permitido_fechado" in codigo
        assert codigo.index("e_marcar_como_pago_permitido_fechado") < codigo.index(
            "_exigir_processo_do_registo_aberto")

    def test_so_o_estado_tem_a_excepcao(self):
        """Apagar a guarda de outro escritor, ou copiar a excepção para ele, falha aqui."""
        import services.finance_process_records as fpr

        for nome in ("run_create_process_finance", "run_update_process_finance",
                     "run_delete_process_finance"):
            codigo = codigo_da_funcao_sem_comentarios(getattr(fpr, nome))
            assert "e_marcar_como_pago_permitido_fechado" not in codigo, nome
            assert "_exigir_processo_do_registo_aberto" in codigo, nome

"""
SERVIÇO PAGO PELO PARCEIRO — o controlo simples do CRM

O parceiro paga-nos (não recebe comissões): uma caixa «Serviço pago pelo
parceiro» e um texto livre «Observações», visíveis à equipa interna. O que
se prova:

  1. só se aplica a processos COM parceiro;
  2. quem vê e quem altera (papel EFECTIVO) — e que a Indexação e o próprio
     parceiro não vêem;
  3. o âmbito: 404 para o que não vê, e alterar é da casa DONA;
  4. o dado vive à parte (nunca no documento do processo) e o parceiro nunca
     o recebe;
  5. o rasto diz que mudou sem copiar o texto das observações; gravar o que
     já lá está não deixa rasto.
"""
from __future__ import annotations

import contextlib

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from tests.unit.helpers_tenant import (  # noqa: F401
    REDE_DOMUS,
    REDE_INCUMBENTE,
    rede_de_omissao_incumbente,
    semear,
    tenant_db,
)


def _ator(papel: str, uid: str = "u-ana") -> dict:
    """`u-ana` trabalha na Power (UCR do cenário); `u-bruno` na Domus."""
    return {"id": uid, "name": uid, "email": f"{uid}@x.pt", "role": papel, "effective_role": papel}


def _processo(pid="p-1", **extra):
    return {
        "id": pid, "client_name": "Cliente", "network_id": REDE_INCUMBENTE, "company_id": "cmp-power",
        "assigned_parceiro_id": "pt-1", "parceiro_name": "Rui", **extra,
    }


@pytest.fixture
def com_bd(fake_async_db, rede_de_omissao_incumbente):
    import services.audit_trail_service as audit
    import services.history as history
    import services.servico_do_parceiro as svc

    semear(fake_async_db)
    fake_async_db.processes.docs.clear()
    fake_async_db.processes.docs.append(_processo())
    with contextlib.ExitStack() as pilha:
        pilha.enter_context(tenant_db(fake_async_db, svc, history, audit))
        yield fake_async_db


# ════════════════════════════════════════════════════════════════════
#  PURA
# ════════════════════════════════════════════════════════════════════
class TestLimparObservacoes:
    def test_tira_etiquetas_e_controlo_e_mantem_as_quebras_de_linha(self):
        from services.servico_do_parceiro import limpar_observacoes

        assert limpar_observacoes("  Pago <b>50%</b>\x00 hoje \r\n\r\nResto  em  Nov ") == "Pago 50% hoje\n\nResto em Nov"

    def test_nao_estraga_texto_legitimo(self):
        from services.servico_do_parceiro import limpar_observacoes

        assert limpar_observacoes("Ana & Rui — 3 < 5 e 5 > 3") == "Ana & Rui — 3 < 5 e 5 > 3"
        assert limpar_observacoes("<img src=x onerror=alert(1)>ok") == "ok"

    def test_tem_tecto_e_aceita_none(self):
        from services.servico_do_parceiro import LIMITE_DE_OBSERVACOES, limpar_observacoes

        assert len(limpar_observacoes("x" * 5000)) == LIMITE_DE_OBSERVACOES
        assert limpar_observacoes(None) == ""


# ════════════════════════════════════════════════════════════════════
#  APLICABILIDADE
# ════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
class TestAplicabilidade:
    async def test_sem_parceiro_diz_nao_aplicavel_e_nao_deixa_gravar(self, com_bd):
        import services.servico_do_parceiro as svc

        com_bd.processes.docs[0].pop("assigned_parceiro_id")
        lido = await svc.run_get_servico("p-1", _ator("administrativo"))
        assert lido["aplicavel"] is False and lido["pode_alterar"] is False and lido["parceiro"] is None
        with pytest.raises(HTTPException) as erro:
            await svc.run_set_servico("p-1", svc.ServicoDoParceiroBody(pago=True), _ator("administrativo"))
        assert erro.value.status_code == 422
        assert com_bd.process_partner_service.docs == []

    async def test_com_parceiro_nasce_por_pagar(self, com_bd):
        import services.servico_do_parceiro as svc

        lido = await svc.run_get_servico("p-1", _ator("administrativo"))
        assert lido == {
            "process_id": "p-1", "aplicavel": True, "parceiro": {"id": "pt-1", "nome": "Rui"},
            "pago": False, "pago_em": None, "observacoes": "", "actualizado_por": None,
            "actualizado_em": None, "pode_alterar": True,
        }


# ════════════════════════════════════════════════════════════════════
#  QUEM VÊ, QUEM ALTERA
# ════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
class TestPapeis:
    @pytest.mark.parametrize("papel", ["master", "admin", "ceo", "diretor", "administrativo", "consultor", "intermediario"])
    async def test_a_equipa_que_ve_o_processo_ve_o_controlo(self, com_bd, papel):
        import services.servico_do_parceiro as svc

        assert (await svc.run_get_servico("p-1", _ator(papel)))["aplicavel"] is True

    @pytest.mark.parametrize("papel", ["indexacao", "parceiro", "cliente", ""])
    async def test_a_indexacao_o_parceiro_e_o_resto_nao_veem(self, com_bd, papel):
        import services.servico_do_parceiro as svc

        with pytest.raises(HTTPException) as erro:
            await svc.run_get_servico("p-1", _ator(papel))
        assert erro.value.status_code == 403

    @pytest.mark.parametrize("papel,pode", [
        ("master", True), ("admin", True), ("ceo", True), ("diretor", True), ("administrativo", True),
        ("consultor", False), ("intermediario", False),
    ])
    async def test_o_ecra_sabe_se_pode_alterar(self, com_bd, papel, pode):
        import services.servico_do_parceiro as svc

        assert (await svc.run_get_servico("p-1", _ator(papel)))["pode_alterar"] is pode

    @pytest.mark.parametrize("papel", ["consultor", "intermediario", "indexacao", "parceiro"])
    async def test_quem_nao_altera_recebe_403_e_nada_e_gravado(self, com_bd, papel):
        import services.servico_do_parceiro as svc

        with pytest.raises(HTTPException) as erro:
            await svc.run_set_servico("p-1", svc.ServicoDoParceiroBody(pago=True), _ator(papel))
        assert erro.value.status_code == 403
        assert com_bd.process_partner_service.docs == []

    @pytest.mark.parametrize("papel", ["master", "admin", "ceo", "diretor", "administrativo"])
    async def test_a_gestao_e_o_administrativo_alteram(self, com_bd, papel):
        import services.servico_do_parceiro as svc

        r = await svc.run_set_servico("p-1", svc.ServicoDoParceiroBody(pago=True), _ator(papel))
        assert r["pago"] is True


# ════════════════════════════════════════════════════════════════════
#  ÂMBITO
# ════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
class TestAmbito:
    async def test_outra_rede_nao_ve_e_o_404_e_igual_ao_de_inexistente(self, com_bd):
        import services.servico_do_parceiro as svc

        with pytest.raises(HTTPException) as alheio:
            await svc.run_get_servico("p-1", _ator("admin", "u-bruno"))
        with pytest.raises(HTTPException) as nada:
            await svc.run_get_servico("nao-existe", _ator("admin", "u-bruno"))
        assert alheio.value.status_code == nada.value.status_code == 404
        assert alheio.value.detail == nada.value.detail
        with pytest.raises(HTTPException) as escrita:
            await svc.run_set_servico("p-1", svc.ServicoDoParceiroBody(pago=True), _ator("admin", "u-bruno"))
        assert escrita.value.status_code == 404

    async def test_uma_rede_convidada_ve_mas_nao_altera(self, com_bd):
        """A casa DONA do processo é quem sabe se o parceiro lhe pagou."""
        import services.servico_do_parceiro as svc

        com_bd.processes.docs[0]["partner_network_ids"] = [REDE_DOMUS]
        lido = await svc.run_get_servico("p-1", _ator("diretor", "u-bruno"))
        assert lido["aplicavel"] is True and lido["pode_alterar"] is False
        with pytest.raises(HTTPException) as erro:
            await svc.run_set_servico("p-1", svc.ServicoDoParceiroBody(pago=True), _ator("diretor", "u-bruno"))
        assert erro.value.status_code == 403

    async def test_o_master_atravessa_redes(self, com_bd):
        import services.servico_do_parceiro as svc

        r = await svc.run_set_servico("p-1", svc.ServicoDoParceiroBody(pago=True), _ator("master", "u-bruno"))
        assert r["pago"] is True


# ════════════════════════════════════════════════════════════════════
#  GRAVAR
# ════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
class TestGravar:
    async def test_marcar_pago_e_escrever_observacoes(self, com_bd):
        import services.servico_do_parceiro as svc

        r = await svc.run_set_servico(
            "p-1", svc.ServicoDoParceiroBody(pago=True, observacoes="Transferência de 14/10\nRef. 8841"),
            _ator("administrativo"),
        )
        assert r["pago"] is True and r["pago_em"] and r["observacoes"] == "Transferência de 14/10\nRef. 8841"
        assert r["actualizado_por"] == "u-ana"
        doc = com_bd.process_partner_service.docs[0]
        assert doc["process_id"] == "p-1" and doc["network_id"] == REDE_INCUMBENTE, "leva o carimbo do processo"

    async def test_gravar_so_a_caixa_nao_apaga_as_observacoes_e_vice_versa(self, com_bd):
        import services.servico_do_parceiro as svc

        await svc.run_set_servico("p-1", svc.ServicoDoParceiroBody(observacoes="nota"), _ator("administrativo"))
        r = await svc.run_set_servico("p-1", svc.ServicoDoParceiroBody(pago=True), _ator("administrativo"))
        assert r["observacoes"] == "nota" and r["pago"] is True
        r = await svc.run_set_servico("p-1", svc.ServicoDoParceiroBody(observacoes=""), _ator("administrativo"))
        assert r["observacoes"] == "" and r["pago"] is True

    async def test_desmarcar_limpa_a_data_e_remarcar_volta_a_dar_uma_nova(self, com_bd):
        import services.servico_do_parceiro as svc

        a = await svc.run_set_servico("p-1", svc.ServicoDoParceiroBody(pago=True), _ator("administrativo"))
        b = await svc.run_set_servico("p-1", svc.ServicoDoParceiroBody(pago=False), _ator("administrativo"))
        assert b["pago"] is False and b["pago_em"] is None
        c = await svc.run_set_servico("p-1", svc.ServicoDoParceiroBody(pago=True), _ator("administrativo"))
        assert c["pago_em"] and c["pago_em"] != a["pago_em"]

    async def test_a_data_de_pagamento_nao_muda_ao_editar_so_as_observacoes(self, com_bd):
        import services.servico_do_parceiro as svc

        a = await svc.run_set_servico("p-1", svc.ServicoDoParceiroBody(pago=True), _ator("administrativo"))
        b = await svc.run_set_servico("p-1", svc.ServicoDoParceiroBody(observacoes="x"), _ator("administrativo"))
        assert b["pago_em"] == a["pago_em"]

    async def test_um_pedido_vazio_e_422(self, com_bd):
        import services.servico_do_parceiro as svc

        with pytest.raises(HTTPException) as erro:
            await svc.run_set_servico("p-1", svc.ServicoDoParceiroBody(), _ator("administrativo"))
        assert erro.value.status_code == 422

    @pytest.mark.parametrize("campo", ["valor", "comissao", "amount", "process_id", "network_id", "actualizado_por_id"])
    async def test_o_corpo_nao_aceita_campos_a_mais(self, campo):
        import services.servico_do_parceiro as svc

        with pytest.raises(ValidationError):
            svc.ServicoDoParceiroBody(**{campo: 1})

    async def test_so_ha_um_registo_por_processo(self, com_bd):
        import services.servico_do_parceiro as svc

        for pago in (True, False, True):
            await svc.run_set_servico("p-1", svc.ServicoDoParceiroBody(pago=pago), _ator("administrativo"))
        assert len(com_bd.process_partner_service.docs) == 1

    async def test_o_documento_do_processo_nunca_leva_o_controlo(self, com_bd):
        """Vive à parte: um `PUT /processes/{id}` genérico não o sobrescreve e
        os leitores do processo não o devolvem."""
        import services.servico_do_parceiro as svc

        antes = dict(com_bd.processes.docs[0])
        await svc.run_set_servico("p-1", svc.ServicoDoParceiroBody(pago=True, observacoes="n"), _ator("administrativo"))
        assert com_bd.processes.docs[0] == antes


# ════════════════════════════════════════════════════════════════════
#  RASTO
# ════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
class TestRasto:
    async def test_marcar_deixa_rasto_no_historico_e_no_trilho(self, com_bd):
        import services.servico_do_parceiro as svc

        await svc.run_set_servico("p-1", svc.ServicoDoParceiroBody(pago=True), _ator("administrativo"))
        assert [h["action"] for h in com_bd.history.docs] == ["Marcou o serviço como pago pelo parceiro"]
        trilho = com_bd.audit_trail.docs[0]
        assert trilho["field"] == "servico_do_parceiro" and "pago=sim" in str(trilho["new_value"])
        assert trilho["metadata"]["papel_efectivo"] == "administrativo"

    async def test_desmarcar_tambem(self, com_bd):
        import services.servico_do_parceiro as svc

        await svc.run_set_servico("p-1", svc.ServicoDoParceiroBody(pago=True), _ator("administrativo"))
        await svc.run_set_servico("p-1", svc.ServicoDoParceiroBody(pago=False), _ator("administrativo"))
        assert com_bd.history.docs[-1]["action"] == "Desmarcou o serviço como pago pelo parceiro"

    async def test_as_observacoes_registam_que_mudaram_mas_nunca_o_texto(self, com_bd):
        import services.servico_do_parceiro as svc

        await svc.run_set_servico("p-1", svc.ServicoDoParceiroBody(observacoes="Acordo especial de 30%"), _ator("administrativo"))
        assert [h["action"] for h in com_bd.history.docs] == ["Atualizou as observações do serviço do parceiro"]
        assert "30%" not in repr(com_bd.history.docs) and "30%" not in repr(com_bd.audit_trail.docs)

    async def test_gravar_o_que_ja_la_esta_nao_deixa_rasto(self, com_bd):
        import services.servico_do_parceiro as svc

        corpo = svc.ServicoDoParceiroBody(pago=True, observacoes="igual")
        await svc.run_set_servico("p-1", corpo, _ator("administrativo"))
        antes = (len(com_bd.history.docs), len(com_bd.audit_trail.docs))
        await svc.run_set_servico("p-1", corpo, _ator("administrativo"))
        assert (len(com_bd.history.docs), len(com_bd.audit_trail.docs)) == antes

    async def test_um_actor_silenciado_nao_deixa_rasto_mas_a_operacao_vale(self, com_bd):
        import services.servico_do_parceiro as svc

        silenciado = {**_ator("administrativo"), "track_history": False}
        r = await svc.run_set_servico("p-1", svc.ServicoDoParceiroBody(pago=True), silenciado)
        assert r["pago"] is True and com_bd.history.docs == [] and com_bd.audit_trail.docs == []

    async def test_uma_falha_no_rasto_nao_falha_a_operacao(self, com_bd, monkeypatch):
        import services.servico_do_parceiro as svc

        async def rebenta(*a, **k):
            raise RuntimeError("mongo")

        monkeypatch.setattr(svc, "log_history", rebenta)
        r = await svc.run_set_servico("p-1", svc.ServicoDoParceiroBody(pago=True), _ator("administrativo"))
        assert r["pago"] is True


# ════════════════════════════════════════════════════════════════════
#  O PARCEIRO NUNCA O VÊ
# ════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
class TestOParceiroNaoVe:
    async def test_nenhuma_saida_do_portal_do_parceiro_leva_o_controlo(self, com_bd):
        import services.partner_portal_read as ppr
        import services.servico_do_parceiro as svc
        from tests.unit.test_parceiro_leitura import PT1

        com_bd.workflow_statuses.docs.append({"name": "fase_documental", "order": 1, "macro_fase": "novo"})
        com_bd.processes.docs[0].update({"status": "fase_documental", "process_number": "P1"})
        await svc.run_set_servico(
            "p-1", svc.ServicoDoParceiroBody(pago=True, observacoes="PAGO-SEGREDO-5000"), _ator("administrativo")
        )
        with tenant_db(com_bd, ppr):
            saidas = [
                await ppr.run_list_cases(PT1),
                await ppr.run_get_dashboard(PT1),
                await ppr.run_get_case(PT1, "p-1"),
            ]
        blob = repr(saidas).lower()
        for proibido in ("pago-segredo", "pago_em", "servico", "partner_service", "observacoes"):
            assert proibido not in blob, proibido

    def test_o_portal_do_parceiro_nunca_le_a_colecao_do_controlo(self):
        from pathlib import Path

        backend = Path(__file__).resolve().parents[2]
        for ficheiro in sorted(backend.glob("services/partner_*.py")) + [backend / "routes/partner_portal.py"]:
            assert "process_partner_service" not in ficheiro.read_text(encoding="utf-8"), ficheiro.name
            assert "servico_do_parceiro" not in ficheiro.read_text(encoding="utf-8"), ficheiro.name

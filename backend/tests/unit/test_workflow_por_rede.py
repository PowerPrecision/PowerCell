"""
Workflow POR REDE (multi-tenant, Out 2026).

O PEDIDO
  Cada empresa tem a sua operação: as fases do funil, as flags, as macro-fases
  e os modelos de tarefas deixam de ser globais.
  * migração que DUPLICA o workflow global para todas as redes existentes;
  * a administração (Master/Admin/CEO) edita APENAS o workflow da rede em
    contexto.

COMO SE TESTA
  O cenário tem DUAS redes cujos workflows diferem de propósito — a mesma fase
  `concluidos` é terminal na Power/Precision e ACTIVA na Domus; a Domus tem uma
  fase `triagem_domus` que não existe na outra. É isto que distingue «um
  workflow por rede» de «um workflow global lido de um sítio diferente».

  * o ATAQUE primeiro: um administrador da Power não escreve no workflow da
    Domus nem no modelo, por mais ids que adivinhe;
  * a semântica do PROCESSO (fechado? portal inativo? reabrir? mover?) segue a
    rede DONA — um processo partilhado continua a significar o que significa em
    casa;
  * a semântica de quem OLHA (colunas, filtros) segue a rede de quem olha;
  * inventário por AST: um chamador novo que leia o workflow sem dizer de que
    rede falha por omissão.
"""
from __future__ import annotations

import ast
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from models.workflow import WorkflowStatusCreate, WorkflowStatusUpdate
from services import workflow_phases as wp
from services.auth import get_current_user
from tests.unit.helpers_tenant import (  # noqa: F401  (rede_de_omissao_incumbente é fixture)
    REDE_DOMUS,
    REDE_INCUMBENTE,
    rede_de_omissao_incumbente,
    semear,
    tenant_db,
)

BACKEND = Path(__file__).resolve().parents[2]


def _fase(name, order, *, activa=True, **extra):
    return {
        "id": f"id-{name}", "name": name, "label": name.replace("_", " ").title(),
        "order": order, "color": "blue", "is_active": activa, **extra,
    }


#: O MODELO (sem `network_id`): o que existia antes da migração.
MODELO = [
    _fase("novo", 1),
    _fase("fase_bancaria", 2),
    _fase("concluidos", 3, activa=False),
]


def _da_rede(rede, fases):
    return [{**f, "id": f"{rede}:{f['name']}", "network_id": rede} for f in fases]


#: A Power/Precision: o modelo tal e qual.
FASES_INCUMBENTE = _da_rede(REDE_INCUMBENTE, MODELO)
#: A Domus trabalha de outra maneira: tem uma triagem própria e, para ela,
#: `concluidos` NÃO é o fim — é uma fase de acompanhamento pós-venda.
FASES_DOMUS = _da_rede(REDE_DOMUS, [
    _fase("triagem_domus", 1),
    _fase("novo", 2),
    _fase("concluidos", 3, activa=True),
    _fase("arquivo", 4, activa=False),
])


@pytest.fixture
def mundo(fake_async_db, rede_de_omissao_incumbente):
    """Duas redes, workflows diferentes, e o modelo."""
    import services.workflow_scope as ws

    semear(fake_async_db)
    fake_async_db.workflow_statuses.docs.extend([dict(f) for f in MODELO])
    fake_async_db.workflow_statuses.docs.extend([dict(f) for f in FASES_INCUMBENTE])
    fake_async_db.workflow_statuses.docs.extend([dict(f) for f in FASES_DOMUS])
    fake_async_db.user_company_roles.docs.extend([
        {"user_id": "u-admin", "company_id": "cmp-power", "company_name": "Power Real Estate",
         "role": "admin", "is_default": True},
        {"user_id": "u-admin-domus", "company_id": "cmp-domus", "company_name": "Domus",
         "role": "admin", "is_default": True},
        {"user_id": "u-ceo", "company_id": "cmp-power", "company_name": "Power Real Estate",
         "role": "ceo", "is_default": True},
        {"user_id": "u-master", "company_id": "cmp-power", "company_name": "Power Real Estate",
         "role": "master", "is_default": True},
    ])
    with tenant_db(fake_async_db, ws):
        wp.invalidar_cache_de_fases()
        yield fake_async_db
    wp.invalidar_cache_de_fases()


def _nomes(fases):
    """Nomes de uma lista de dicts OU de modelos de resposta."""
    return [f["name"] if isinstance(f, dict) else f.name for f in fases]


# ====================================================================
# LER: o workflow de UMA rede
# ====================================================================

class TestCarregarFases:
    @pytest.mark.asyncio
    async def test_cada_rede_le_o_seu_workflow(self, mundo):
        assert _nomes(await wp.carregar_fases(rede=REDE_INCUMBENTE)) == ["novo", "fase_bancaria", "concluidos"]
        assert _nomes(await wp.carregar_fases(rede=REDE_DOMUS)) == ["triagem_domus", "novo", "concluidos", "arquivo"]

    @pytest.mark.asyncio
    async def test_sem_rede_e_o_modelo(self, mundo):
        assert _nomes(await wp.carregar_fases()) == ["novo", "fase_bancaria", "concluidos"]
        assert all(not f.get("network_id") for f in await wp.carregar_fases())

    @pytest.mark.asyncio
    async def test_uma_rede_sem_fases_proprias_recebe_o_modelo(self, mundo):
        """Nada muda para quem ainda não migrou, e uma rede nova funciona logo."""
        fases = await wp.carregar_fases(rede="rede:nova")
        assert _nomes(fases) == ["novo", "fase_bancaria", "concluidos"]

    @pytest.mark.asyncio
    async def test_o_modelo_nao_se_mistura_com_as_redes(self, mundo):
        """O ataque: ler o workflow de uma rede NÃO devolve fases de outra."""
        fases = await wp.carregar_fases(rede=REDE_DOMUS)
        assert all(f.get("network_id") == REDE_DOMUS for f in fases)

    @pytest.mark.asyncio
    async def test_a_cache_e_por_rede(self, mundo):
        """Sem isto, a primeira rede a perguntar servia a todas as outras."""
        incumbente = await wp.carregar_fases(rede=REDE_INCUMBENTE)
        domus = await wp.carregar_fases(rede=REDE_DOMUS)
        assert _nomes(incumbente) != _nomes(domus)
        assert _nomes(await wp.carregar_fases(rede=REDE_INCUMBENTE)) == _nomes(incumbente)

    @pytest.mark.asyncio
    async def test_invalidar_esquece_todas_as_redes(self, mundo):
        await wp.carregar_fases(rede=REDE_INCUMBENTE)
        await wp.carregar_fases(rede=REDE_DOMUS)
        mundo.workflow_statuses.docs[:] = [d for d in mundo.workflow_statuses.docs if d.get("network_id") != REDE_DOMUS]
        wp.invalidar_cache_de_fases()
        assert _nomes(await wp.carregar_fases(rede=REDE_DOMUS)) == ["novo", "fase_bancaria", "concluidos"]

    @pytest.mark.asyncio
    async def test_uma_leitura_falhada_nao_fica_em_cache(self, mundo):
        with patch.object(mundo.workflow_statuses, "find", side_effect=RuntimeError("bd")):
            assert await wp.carregar_fases(rede=REDE_DOMUS) == []
        assert _nomes(await wp.carregar_fases(rede=REDE_DOMUS))[0] == "triagem_domus"


class TestRedeDoProcesso:
    def test_e_a_do_dono(self, rede_de_omissao_incumbente):
        assert wp.rede_do_processo({"network_id": REDE_DOMUS}) == REDE_DOMUS

    def test_por_carimbar_pertence_a_rede_de_omissao(self, rede_de_omissao_incumbente):
        assert wp.rede_do_processo({"id": "legado"}) == REDE_INCUMBENTE

    def test_sem_omissao_nem_carimbo_e_o_modelo(self, monkeypatch):
        monkeypatch.delenv("TENANT_DEFAULT_NETWORK_ID", raising=False)
        assert wp.rede_do_processo({"id": "x"}) is None
        assert wp.rede_do_processo(None) is None


class TestOQueQuemOlhaVe:
    @pytest.mark.asyncio
    async def test_um_utilizador_de_uma_rede_ve_o_workflow_dela(self, mundo):
        from services.tenant_network import resolve_tenant_scope

        scope = await resolve_tenant_scope({"id": "u-bruno", "role": "diretor"})
        assert _nomes(await wp.fases_do_ambito(scope))[0] == "triagem_domus"

    @pytest.mark.asyncio
    async def test_quem_trabalha_nas_duas_redes_ve_a_juncao_por_nome(self, mundo):
        from services.tenant_network import resolve_tenant_scope

        scope = await resolve_tenant_scope({"id": "u-carla", "role": "consultor"})
        nomes = _nomes(await wp.fases_do_ambito(scope))
        assert sorted(nomes) == sorted({"novo", "fase_bancaria", "concluidos", "triagem_domus", "arquivo"})
        assert len(nomes) == len(set(nomes)), "um nome é uma fase uma vez só"

    @pytest.mark.asyncio
    async def test_o_master_ve_a_juncao_de_todas_as_redes(self, mundo):
        from services.tenant_network import resolve_tenant_scope

        scope = await resolve_tenant_scope({"id": "u-master", "role": "master"})
        assert "triagem_domus" in _nomes(await wp.fases_do_ambito(scope))
        assert "fase_bancaria" in _nomes(await wp.fases_do_ambito(scope))

    def test_juntar_a_primeira_rede_ganha_a_definicao_e_a_menor_ordem(self):
        a = [_fase("x", 5, color="red")]
        b = [_fase("x", 2, color="green"), _fase("y", 3)]
        juntas = wp.juntar_fases([a, b])
        x = next(f for f in juntas if f["name"] == "x")
        assert x["color"] == "red" and x["order"] == 2
        assert [f["name"] for f in juntas] == ["x", "y"]


# ====================================================================
# O PROCESSO: segue o workflow da rede DONA
# ====================================================================

class TestOProcessoSegueARedeDona:
    """A mesma fase, o mesmo nome, dois sentidos."""

    @pytest.mark.asyncio
    async def test_concluidos_fecha_na_power_e_nao_na_domus(self, mundo):
        import services.process_closed_guard as pcg

        with tenant_db(mundo, pcg):
            na_power = {"id": "p1", "status": "concluidos", "network_id": REDE_INCUMBENTE}
            na_domus = {"id": "p2", "status": "concluidos", "network_id": REDE_DOMUS}
            assert await pcg.processo_esta_fechado(na_power) is True
            assert await pcg.processo_esta_fechado(na_domus) is False

    @pytest.mark.asyncio
    async def test_arquivo_so_fecha_na_domus(self, mundo):
        import services.process_closed_guard as pcg

        with tenant_db(mundo, pcg):
            assert await pcg.processo_esta_fechado({"id": "p", "status": "arquivo", "network_id": REDE_DOMUS}) is True

    @pytest.mark.asyncio
    async def test_o_portal_fecha_pelo_workflow_do_dono(self, mundo):
        from services import portal_estado as pe

        assert await pe.processo_esta_inativo({"status": "concluidos", "network_id": REDE_INCUMBENTE}) is True
        assert await pe.processo_esta_inativo({"status": "concluidos", "network_id": REDE_DOMUS}) is False

    @pytest.mark.asyncio
    async def test_o_portal_escolhe_o_processo_activo_de_cada_rede(self, mundo):
        """Um cliente com um processo em cada rede: o da Domus ainda está activo."""
        from services import portal_estado as pe

        da_power = {"id": "a", "status": "concluidos", "network_id": REDE_INCUMBENTE}
        da_domus = {"id": "b", "status": "concluidos", "network_id": REDE_DOMUS}
        escolhido = await pe.escolher_processo_do_cliente([da_power, da_domus])
        assert escolhido["id"] == "b"

    @pytest.mark.asyncio
    async def test_um_processo_partilhado_continua_a_significar_o_que_significa_em_casa(self, mundo):
        """O ataque ao «workflow de quem olha»: a Precision vê o processo da Domus
        mas quem governa o seu estado é a Domus."""
        import services.process_closed_guard as pcg

        partilhado = {"id": "p", "status": "concluidos", "network_id": REDE_DOMUS,
                      "partner_network_ids": [REDE_INCUMBENTE]}
        with tenant_db(mundo, pcg):
            assert await pcg.processo_esta_fechado(partilhado) is False

    @pytest.mark.asyncio
    async def test_reabrir_oferece_as_fases_activas_da_rede_dona(self, mundo):
        import services.process_reopen as pr

        processo = {"id": "p", "status": "arquivo", "network_id": REDE_DOMUS, "is_deleted": False}
        mundo.processes.docs.append(processo)
        with tenant_db(mundo, pr), \
                patch.object(pr, "run_move_process_kanban", AsyncMock(return_value={"ok": True})) as mover:
            await pr.run_reopen_process(
                "p", "triagem_domus", {"id": "u", "role": "admin"},
                can_view_fn=lambda *_: True, inject_cdc_fn=lambda *_: None, broadcast_fn=AsyncMock(),
                create_finance_snapshot_fn=AsyncMock(),
            )
            mover.assert_awaited_once()
            # uma fase que só existe noutra rede não serve
            with pytest.raises(HTTPException) as erro:
                await pr.run_reopen_process(
                    "p", "fase_bancaria", {"id": "u", "role": "admin"},
                    can_view_fn=lambda *_: True, inject_cdc_fn=lambda *_: None, broadcast_fn=AsyncMock(),
                    create_finance_snapshot_fn=AsyncMock(),
                )
        assert erro.value.status_code == 400

    @pytest.mark.asyncio
    async def test_as_flags_de_proposito_sao_as_da_rede_dona(self, mundo):
        from services.workflow_lookup import get_flagged_workflow_status_names, get_inactive_workflow_status_names
        import services.workflow_lookup as wl

        mundo.workflow_statuses.docs.append(
            {**_fase("fase_bancaria", 9), "id": "dom-fb", "network_id": REDE_DOMUS, "trigger_countdown": True})
        with tenant_db(mundo, wl):
            assert await get_flagged_workflow_status_names("trigger_countdown", REDE_DOMUS) == ["fase_bancaria"]
            assert await get_flagged_workflow_status_names("trigger_countdown", REDE_INCUMBENTE) == []
            assert await get_inactive_workflow_status_names(REDE_DOMUS) == ["arquivo"]
            assert await get_inactive_workflow_status_names(REDE_INCUMBENTE) == ["concluidos"]

    @pytest.mark.asyncio
    async def test_a_primeira_fase_e_a_da_rede(self, mundo):
        import services.workflow_lookup as wl

        with tenant_db(mundo, wl):
            assert await wl.get_first_workflow_status(REDE_DOMUS) == "triagem_domus"
            assert await wl.get_first_workflow_status(REDE_INCUMBENTE) == "novo"

    @pytest.mark.asyncio
    async def test_mover_para_uma_fase_que_so_existe_noutra_rede_e_400(self, mundo):
        import services.process_kanban_move as pkm

        mundo.processes.docs.append({"id": "pd", "status": "novo", "network_id": REDE_DOMUS, "company_id": "cmp-domus"})
        with tenant_db(mundo, pkm):
            with pytest.raises(HTTPException) as erro:
                await pkm.run_move_process_kanban(
                    "pd", "fase_bancaria", {"id": "u", "role": "admin"}, deed_date=None,
                    can_view_fn=lambda *_: True, inject_cdc_fn=lambda *_: None,
                    broadcast_fn=AsyncMock(), create_finance_snapshot_fn=AsyncMock(),
                )
        assert erro.value.status_code == 400 and "inválido" in erro.value.detail

    @pytest.mark.asyncio
    async def test_a_listagem_marca_fechado_pelo_dono(self, mundo):
        import services.finance_process_records as fpr

        mundo.processes.docs.extend([
            {"id": "a", "status": "concluidos", "network_id": REDE_INCUMBENTE},
            {"id": "b", "status": "concluidos", "network_id": REDE_DOMUS},
        ])
        with tenant_db(mundo, fpr):
            marcados = await fpr.marcar_processos_fechados([
                {"process_id": "a"}, {"process_id": "b"},
            ])
        assert [m["processo_fechado"] for m in marcados] == [True, False]

    @pytest.mark.asyncio
    async def test_comissoes_pendentes_marcam_fechado_pelo_dono(self, mundo):
        import services.process_pending_commissions as ppc

        linhas = [
            {"id": "a", "status": "concluidos", "network_id": REDE_INCUMBENTE},
            {"id": "b", "status": "concluidos", "network_id": REDE_DOMUS},
        ]
        with tenant_db(mundo, ppc):
            await ppc.enriquecer_comissoes_pendentes(
                linhas, {"id": "u-master", "role": "master"}, papel="master",
            )
        assert [l["processo_fechado"] for l in linhas] == [True, False]

    @pytest.mark.asyncio
    async def test_a_fase_inicial_de_um_processo_novo_e_a_da_rede_onde_nasce(self, mundo):
        from services.process_create import resolve_initial_workflow_status
        import services.process_create as pc

        with tenant_db(mundo, pc):
            assert await resolve_initial_workflow_status(is_lead=False, rede=REDE_DOMUS) == ("triagem_domus", "triagem_domus")
            assert (await resolve_initial_workflow_status(is_lead=False, rede=REDE_INCUMBENTE))[0] == "novo"

    @pytest.mark.asyncio
    async def test_nomes_terminais_de_todas_as_redes_e_a_uniao(self, mundo):
        assert set(await wp.nomes_terminais_de_todas_as_redes()) >= {"concluidos", "arquivo"}

    @pytest.mark.asyncio
    async def test_so_processos_com_fase_activa_e_exacto_por_rede(self, mundo):
        processos = [
            {"id": "a", "status": "concluidos", "network_id": REDE_INCUMBENTE},  # fechado em casa
            {"id": "b", "status": "concluidos", "network_id": REDE_DOMUS},        # activo em casa
            {"id": "c", "status": "novo", "network_id": REDE_INCUMBENTE},
        ]
        assert sorted(p["id"] for p in await wp.so_processos_com_fase_activa(processos)) == ["b", "c"]


# ====================================================================
# EDITAR: a rede em contexto
# ====================================================================

POWER_ADMIN = {"id": "u-admin", "role": "admin", "effective_role": "admin", "name": "Admin Power"}
DOMUS_ADMIN = {"id": "u-admin-domus", "role": "admin", "effective_role": "admin", "name": "Admin Domus"}
CEO = {"id": "u-ceo", "role": "ceo", "effective_role": "ceo", "name": "CEO"}
MASTER = {"id": "u-master", "role": "master", "effective_role": "master", "name": "Master"}


def _pedido(company_id=None):
    headers = {"X-Company-Id": company_id} if company_id else {}
    return MagicMock(headers=headers, state=MagicMock(spec=[]))


class TestARedeEmContexto:
    @pytest.mark.asyncio
    async def test_e_a_da_empresa_activa(self, mundo):
        import services.workflow_scope as ws

        with tenant_db(mundo, ws), patch("services.auth.get_active_company_id_async", AsyncMock(return_value="cmp-domus")):
            assert await ws.rede_do_workflow_em_contexto(MASTER, _pedido("cmp-domus")) == REDE_DOMUS

    @pytest.mark.asyncio
    async def test_sem_header_e_a_rede_do_utilizador(self, mundo):
        import services.workflow_scope as ws

        with tenant_db(mundo, ws):
            assert await ws.rede_do_workflow_em_contexto(DOMUS_ADMIN, _pedido()) == REDE_DOMUS

    @pytest.mark.asyncio
    async def test_um_admin_nao_pede_a_rede_dos_outros(self, mundo):
        """404 igual ao de «não existe»: não se confirma que a rede existe."""
        import services.workflow_scope as ws

        with tenant_db(mundo, ws):
            with pytest.raises(HTTPException) as erro:
                await ws.rede_do_workflow_em_contexto(POWER_ADMIN, _pedido(), rede_pedida=REDE_DOMUS)
            with pytest.raises(HTTPException) as inexistente:
                await ws.rede_do_workflow_em_contexto(POWER_ADMIN, _pedido(), rede_pedida="rede:nao-existe")
        assert erro.value.status_code == inexistente.value.status_code == 404
        assert erro.value.detail == inexistente.value.detail

    @pytest.mark.asyncio
    async def test_o_master_pede_qualquer_rede_que_exista(self, mundo):
        import services.workflow_scope as ws

        with tenant_db(mundo, ws):
            assert await ws.rede_do_workflow_em_contexto(MASTER, _pedido(), rede_pedida=REDE_DOMUS) == REDE_DOMUS
            with pytest.raises(HTTPException):
                await ws.rede_do_workflow_em_contexto(MASTER, _pedido(), rede_pedida="rede:nao-existe")

    @pytest.mark.asyncio
    async def test_a_empresa_activa_de_fora_do_ambito_nao_vale(self, mundo):
        """Um header com a empresa dos outros não muda a rede que se edita."""
        import services.workflow_scope as ws

        with tenant_db(mundo, ws), patch("services.auth.get_active_company_id_async", AsyncMock(return_value="cmp-domus")):
            assert await ws.rede_do_workflow_em_contexto(POWER_ADMIN, _pedido("cmp-domus")) == REDE_INCUMBENTE


class TestMaterializar:
    @pytest.mark.asyncio
    async def test_copia_o_modelo_para_a_rede_que_nao_tem(self, mundo):
        import services.workflow_scope as ws

        with tenant_db(mundo, ws):
            criadas = await ws.garantir_workflow_da_rede("rede:nova")
        copia = [d for d in mundo.workflow_statuses.docs if d.get("network_id") == "rede:nova"]
        assert criadas == 3 and sorted(d["name"] for d in copia) == ["concluidos", "fase_bancaria", "novo"]
        ids = {d["id"] for d in copia}
        assert len(ids) == 3 and not ids & {f["id"] for f in MODELO}, "ids novos, nunca os do modelo"

    @pytest.mark.asyncio
    async def test_e_idempotente(self, mundo):
        import services.workflow_scope as ws

        with tenant_db(mundo, ws):
            await ws.garantir_workflow_da_rede("rede:nova")
            segunda = await ws.garantir_workflow_da_rede("rede:nova")
        assert segunda == 0
        assert len([d for d in mundo.workflow_statuses.docs if d.get("network_id") == "rede:nova"]) == 3

    @pytest.mark.asyncio
    async def test_nunca_altera_uma_fase_que_a_rede_ja_tem(self, mundo):
        """Correr outra vez não desfaz a edição de um administrador."""
        import services.workflow_scope as ws

        proprio = next(d for d in mundo.workflow_statuses.docs if d.get("network_id") == REDE_INCUMBENTE and d["name"] == "novo")
        proprio["label"] = "Editado pelo admin"
        with tenant_db(mundo, ws):
            await ws.garantir_workflow_da_rede(REDE_INCUMBENTE)
        assert proprio["label"] == "Editado pelo admin"

    @pytest.mark.asyncio
    async def test_so_cria_as_que_faltam(self, mundo):
        import services.workflow_scope as ws

        mundo.workflow_statuses.docs[:] = [
            d for d in mundo.workflow_statuses.docs
            if not (d.get("network_id") == REDE_INCUMBENTE and d["name"] == "concluidos")
        ]
        with tenant_db(mundo, ws):
            assert await ws.garantir_workflow_da_rede(REDE_INCUMBENTE) == 1

    @pytest.mark.asyncio
    async def test_o_modelo_nao_e_tocado(self, mundo):
        import services.workflow_scope as ws

        antes = [dict(d) for d in mundo.workflow_statuses.docs if not d.get("network_id")]
        with tenant_db(mundo, ws):
            await ws.garantir_workflow_da_rede("rede:nova")
        assert [d for d in mundo.workflow_statuses.docs if not d.get("network_id")] == antes


class TestEditarSoARedeEmContexto:
    @pytest.fixture
    def admin(self, mundo):
        import services.admin_workflow as aw
        import services.workflow_scope as ws

        with tenant_db(mundo, aw, ws):
            yield aw, mundo

    @pytest.mark.asyncio
    async def test_criar_so_cria_na_rede_do_admin(self, admin):
        aw, bd = admin
        nova = await aw.run_create_workflow_status(
            WorkflowStatusCreate(name="avaliacao_power", label="Avaliação", order=9), POWER_ADMIN, _pedido())
        assert nova.network_id == REDE_INCUMBENTE
        todos = [d for d in bd.workflow_statuses.docs if d["name"] == "avaliacao_power"]
        assert len(todos) == 1 and todos[0]["network_id"] == REDE_INCUMBENTE
        assert "avaliacao_power" not in _nomes(await wp.carregar_fases(rede=REDE_DOMUS))
        assert "avaliacao_power" not in _nomes([d for d in bd.workflow_statuses.docs if not d.get("network_id")])

    @pytest.mark.asyncio
    async def test_o_mesmo_nome_pode_existir_em_duas_redes(self, admin):
        aw, bd = admin
        await aw.run_create_workflow_status(
            WorkflowStatusCreate(name="comum", label="Comum", order=9), POWER_ADMIN, _pedido())
        await aw.run_create_workflow_status(
            WorkflowStatusCreate(name="comum", label="Comum", order=9), DOMUS_ADMIN, _pedido())
        assert len([d for d in bd.workflow_statuses.docs if d["name"] == "comum"]) == 2

    @pytest.mark.asyncio
    async def test_o_mesmo_nome_na_mesma_rede_e_400(self, admin):
        aw, _bd = admin
        with pytest.raises(HTTPException) as erro:
            await aw.run_create_workflow_status(
                WorkflowStatusCreate(name="fase_bancaria", label="X", order=9), POWER_ADMIN, _pedido())
        assert erro.value.status_code == 400

    @pytest.mark.asyncio
    async def test_criar_numa_rede_sem_copia_materializa_antes(self, admin):
        """Senão a rede passava a ter UMA fase e deixava de herdar o modelo."""
        aw, bd = admin
        bd.workflow_statuses.docs[:] = [d for d in bd.workflow_statuses.docs if d.get("network_id") != REDE_INCUMBENTE]
        await aw.run_create_workflow_status(
            WorkflowStatusCreate(name="extra", label="Extra", order=9), POWER_ADMIN, _pedido())
        wp.invalidar_cache_de_fases()
        assert _nomes(await wp.carregar_fases(rede=REDE_INCUMBENTE)) == ["novo", "fase_bancaria", "concluidos", "extra"]

    @pytest.mark.asyncio
    async def test_actualizar_uma_fase_da_propria_rede(self, admin):
        aw, bd = admin
        fase = next(d for d in bd.workflow_statuses.docs if d.get("network_id") == REDE_INCUMBENTE and d["name"] == "novo")
        r = await aw.run_update_workflow_status(fase["id"], WorkflowStatusUpdate(label="Novo (Power)"), POWER_ADMIN, _pedido())
        assert r.label == "Novo (Power)"
        domus = next(d for d in bd.workflow_statuses.docs if d.get("network_id") == REDE_DOMUS and d["name"] == "novo")
        assert domus["label"] != "Novo (Power)"

    @pytest.mark.asyncio
    async def test_o_ataque_actualizar_uma_fase_de_outra_rede_pelo_id_e_404(self, admin):
        aw, bd = admin
        da_domus = next(d for d in bd.workflow_statuses.docs if d.get("network_id") == REDE_DOMUS and d["name"] == "novo")
        with pytest.raises(HTTPException) as erro:
            await aw.run_update_workflow_status(da_domus["id"], WorkflowStatusUpdate(label="Hackeado"), POWER_ADMIN, _pedido())
        assert erro.value.status_code == 404
        assert da_domus["label"] != "Hackeado"

    @pytest.mark.asyncio
    async def test_o_ataque_apagar_uma_fase_de_outra_rede_pelo_id_e_404(self, admin):
        aw, bd = admin
        da_domus = next(d for d in bd.workflow_statuses.docs if d.get("network_id") == REDE_DOMUS and d["name"] == "arquivo")
        with pytest.raises(HTTPException) as erro:
            await aw.run_delete_workflow_status(da_domus["id"], POWER_ADMIN, _pedido())
        assert erro.value.status_code == 404
        assert any(d["id"] == da_domus["id"] for d in bd.workflow_statuses.docs)

    @pytest.mark.asyncio
    async def test_editar_pelo_id_do_modelo_edita_a_copia_da_rede_e_nunca_o_modelo(self, admin):
        """O ecrã mostra o modelo enquanto a rede não tem o seu: editar materializa."""
        aw, bd = admin
        bd.workflow_statuses.docs[:] = [d for d in bd.workflow_statuses.docs if d.get("network_id") != REDE_INCUMBENTE]
        modelo = next(d for d in bd.workflow_statuses.docs if not d.get("network_id") and d["name"] == "novo")
        r = await aw.run_update_workflow_status(modelo["id"], WorkflowStatusUpdate(label="Só da Power"), POWER_ADMIN, _pedido())
        assert r.network_id == REDE_INCUMBENTE and r.label == "Só da Power"
        assert modelo["label"] != "Só da Power", "o modelo nunca se edita por esta via"
        assert modelo["id"] != r.id

    @pytest.mark.asyncio
    async def test_apagar_so_move_os_processos_da_propria_rede(self, admin):
        """O mesmo NOME numa rede vizinha é outra fase: os processos de lá ficam."""
        aw, bd = admin
        bd.processes.docs.extend([
            {"id": "pa", "status": "concluidos", "network_id": REDE_INCUMBENTE},
            {"id": "pb", "status": "concluidos", "network_id": REDE_DOMUS},
        ])
        fase = next(d for d in bd.workflow_statuses.docs if d.get("network_id") == REDE_INCUMBENTE and d["name"] == "concluidos")
        r = await aw.run_delete_workflow_status(fase["id"], POWER_ADMIN, _pedido())
        estados = {p["id"]: p["status"] for p in bd.processes.docs if p["id"] in ("pa", "pb")}
        assert r["processes_moved"] == 1
        assert estados["pa"] != "concluidos" and estados["pb"] == "concluidos"
        assert any(d.get("network_id") == REDE_DOMUS and d["name"] == "concluidos" for d in bd.workflow_statuses.docs)

    @pytest.mark.asyncio
    async def test_o_editor_diz_onde_se_esta_a_editar(self, admin):
        aw, _bd = admin
        r = await aw.run_get_workflow_editor(DOMUS_ADMIN, _pedido())
        assert r["network_id"] == REDE_DOMUS and r["empresas"] == ["Domus"]
        assert r["tem_workflow_proprio"] is True
        assert _nomes(r["statuses"])[0] == "triagem_domus"

    @pytest.mark.asyncio
    async def test_o_editor_de_uma_rede_sem_copia_mostra_o_modelo_e_di_lo(self, admin):
        aw, bd = admin
        bd.workflow_statuses.docs[:] = [d for d in bd.workflow_statuses.docs if d.get("network_id") != REDE_INCUMBENTE]
        r = await aw.run_get_workflow_editor(POWER_ADMIN, _pedido())
        assert r["tem_workflow_proprio"] is False
        assert _nomes(r["statuses"]) == ["novo", "fase_bancaria", "concluidos"]

    @pytest.mark.asyncio
    async def test_o_workflow_que_o_utilizador_ve_e_o_da_rede_dele(self, admin):
        aw, _bd = admin
        da_domus = await aw.run_get_workflow_statuses(DOMUS_ADMIN, _pedido())
        da_power = await aw.run_get_workflow_statuses(POWER_ADMIN, _pedido())
        assert _nomes(da_domus)[0] == "triagem_domus" and "triagem_domus" not in _nomes(da_power)

    @pytest.mark.asyncio
    async def test_fix_duplicates_nao_trata_o_mesmo_nome_de_redes_diferentes_como_duplicado(self, admin):
        aw, bd = admin
        antes = len(bd.workflow_statuses.docs)
        r = await aw.run_fix_duplicate_workflow_statuses(MASTER)
        assert r["report"]["removed"] == 0 and len(bd.workflow_statuses.docs) == antes


class TestQuemEdita:
    @pytest.fixture
    def cliente(self, mundo):
        import routes.admin as rota
        import services.admin_workflow as aw
        import services.auth as auth_mod
        import services.workflow_scope as ws

        atual = {"user": POWER_ADMIN}
        app = FastAPI()
        app.include_router(rota.router)
        app.dependency_overrides[get_current_user] = lambda: atual["user"]
        with tenant_db(mundo, aw, ws, auth_mod):
            c = TestClient(app, raise_server_exceptions=False)
            c.definir_utilizador = lambda u: atual.update(user=u)
            yield c, mundo

    @pytest.mark.parametrize("utilizador", [POWER_ADMIN, CEO, MASTER])
    def test_admin_ceo_e_master_editam(self, cliente, utilizador):
        c, bd = cliente
        c.definir_utilizador(utilizador)
        r = c.post("/admin/workflow-statuses", json={"name": f"fase_{utilizador['id']}", "label": "L", "order": 9})
        assert r.status_code == 200, r.text

    @pytest.mark.parametrize("papel", ["diretor", "administrativo", "consultor", "intermediario", "indexacao"])
    def test_os_outros_nao_editam_mas_leem(self, cliente, papel):
        c, _bd = cliente
        c.definir_utilizador({"id": "u-x", "role": papel, "effective_role": papel})
        assert c.post("/admin/workflow-statuses", json={"name": "x", "label": "L", "order": 9}).status_code == 403
        assert c.get("/admin/workflow-statuses/editor").status_code == 403
        assert c.get("/admin/workflow-statuses").status_code in (200, 404)

    def test_a_rota_de_leitura_aceita_a_rede_pedida_validada(self, cliente):
        c, _bd = cliente
        assert c.get(f"/admin/workflow-statuses?network_id={REDE_DOMUS}").status_code == 404
        c.definir_utilizador(MASTER)
        r = c.get(f"/admin/workflow-statuses?network_id={REDE_DOMUS}")
        assert r.status_code == 200 and r.json()[0]["name"] == "triagem_domus"

    def test_o_ataque_o_admin_da_power_nao_escreve_na_domus_por_http(self, cliente):
        c, bd = cliente
        da_domus = next(d for d in bd.workflow_statuses.docs if d.get("network_id") == REDE_DOMUS and d["name"] == "arquivo")
        assert c.put(f"/admin/workflow-statuses/{da_domus['id']}", json={"label": "X"}).status_code == 404
        assert c.delete(f"/admin/workflow-statuses/{da_domus['id']}").status_code == 404

    def test_infra_continua_so_do_master(self, cliente):
        c, _bd = cliente
        assert c.post("/admin/workflow-statuses/fix-duplicates").status_code == 403
        assert c.post("/admin/workflow-statuses/migrate-portal-labels").status_code == 403
        c.definir_utilizador(MASTER)
        assert c.post("/admin/workflow-statuses/fix-duplicates").status_code == 200


# ====================================================================
# O INVENTÁRIO — um chamador novo não pode ler o workflow sem dizer de que rede
# ====================================================================

#: Ficheiros que PODEM chamar `carregar_fases()` sem rede (o modelo), com o motivo.
CARREGAR_FASES_SEM_REDE_PERMITIDO = {
    "workflow_phases.py": "É o motor: o modelo é o recurso e a junção de redes lê-o de propósito.",
}

#: Quem pode tocar em `db.workflow_statuses` directamente (o resto lê pelo motor).
ACESSO_DIRECTO_PERMITIDO = {
    "workflow_phases.py": "O motor de leitura (por rede) e as consultas de redes.",
    "workflow_lookup.py": "As flags de propósito e o backfill (a regra de leitura é `ler_fases_da_rede`).",
    "workflow_scope.py": "A cópia da rede (copy-on-write) e a pergunta «tem workflow próprio?».",
    "admin_workflow.py": "A edição: tudo filtrado pela rede em contexto.",
    "process_kanban_diagnose.py": "Diagnóstico de infra (Master): olha para a colecção inteira de propósito.",
    "db_indexes.py": "Declara os índices da colecção; não lê fases.",
    "repor_ao_modelo.py": "Lê os NOMES do MODELO (a regra é a dele, não a de uma rede) e apaga só a cópia da rede em contexto, depois de validada a password.",
}


def _ficheiros_de_producao():
    for pasta in ("services", "routes"):
        for caminho in sorted((BACKEND / pasta).glob("*.py")):
            yield caminho


class TestInventario:
    def test_o_leitor_encontra_chamadores_conhecidos(self):
        """Contraprova: sem ela uma lista vazia passava tudo."""
        achados = set()
        for caminho in _ficheiros_de_producao():
            for no in ast.walk(ast.parse(caminho.read_text(encoding="utf-8"))):
                if isinstance(no, ast.Call) and getattr(no.func, "id", getattr(no.func, "attr", "")) == "carregar_fases":
                    achados.add(caminho.name)
        assert {"process_closed_guard.py", "portal_estado.py", "phase_automation.py", "process_kanban_move.py"} <= achados

    def test_nenhum_chamador_le_o_workflow_sem_dizer_de_que_rede(self):
        sem_rede = []
        for caminho in _ficheiros_de_producao():
            if caminho.name in CARREGAR_FASES_SEM_REDE_PERMITIDO:
                continue
            for no in ast.walk(ast.parse(caminho.read_text(encoding="utf-8"))):
                if not isinstance(no, ast.Call):
                    continue
                nome = getattr(no.func, "id", getattr(no.func, "attr", ""))
                if nome == "carregar_fases" and not any(k.arg == "rede" for k in no.keywords):
                    sem_rede.append(f"{caminho.name}:{no.lineno}")
        assert not sem_rede, f"carregar_fases() sem `rede=`: {sem_rede}"

    def test_ninguem_le_a_colecao_de_fases_a_mao(self):
        intrusos = []
        for caminho in _ficheiros_de_producao():
            if caminho.name in ACESSO_DIRECTO_PERMITIDO:
                continue
            texto = caminho.read_text(encoding="utf-8")
            if "db.workflow_statuses" in texto or ".workflow_statuses." in texto:
                intrusos.append(caminho.name)
        assert not intrusos, (
            f"{intrusos} leem `workflow_statuses` directamente: uma leitura à mão ignora a rede. "
            "Use `carregar_fases(rede=…)` / `fases_do_utilizador` / `fases_do_ambito`."
        )

    def test_as_excepcoes_escritas_ainda_existem(self):
        for nome in {**CARREGAR_FASES_SEM_REDE_PERMITIDO, **ACESSO_DIRECTO_PERMITIDO}:
            assert (BACKEND / "services" / nome).exists(), nome

    def test_o_indice_unico_so_por_nome_ja_nao_existe_no_restauro(self):
        """Um único por `name` recusava as cópias por rede."""
        fonte = (BACKEND / "services" / "backup_restore.py").read_text(encoding="utf-8")
        assert 'idx_workflow_name' not in fonte
        assert 'idx_workflow_network_name' in fonte

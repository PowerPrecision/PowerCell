"""O fluxo mestre do Portal, de ponta a ponta (Bloco 3, ponto 19).

    Pré-registo → Upload obrigatório (Portal) → Fase Index (automática)
        → perfil trancado ao cliente → sai da Index → atribuição automática
        → (mais tarde) fase terminal → Portal bloqueado

O QUE FALTAVA BLINDAR (achados da leitura do percurso)
  1. A criação do processo era «ler se já existe; depois inserir» — dois
     passos. O cliente envia vários ficheiros ao mesmo tempo e CADA
     confirmação corre a verificação: dois processos, dois números.
  2. O avanço do pré-registo para a Index lia o estado e escrevia sem
     condição: o segundo pedido avançava outra vez (relógio de fases a contar
     duas vezes, dois indexadores).
  3. O perfil só trancava se a fase de entrada NÃO estivesse na macro-fase
     «novo». Se o administrador classificasse a Index aí, o cliente editava os
     dados que a Indexação estava a validar. Agora a ENTREGA da recolha
     (`portal_submitted_at`) tranca, seja qual for a classificação da fase.

O último bloco é a máquina de estados inteira num só teste: cada passo
afirma o estado a que chegou E o que ainda não aconteceu.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from services import (
    onboarding_mandatory_config as omc,
    phase_automation,
    portal_onboarding_advance as adv,
    portal_profile,
    process_assignment,
    process_indexing,
    process_phase_clock,
    workflow_phases,
)

FASES = [
    {"name": "fase_index", "order": 1, "is_active": True, "macro_fase": "novo"},
    {"name": "fase_documental", "order": 2, "is_active": True, "macro_fase": "analise"},
    {"name": "fase_bancaria", "order": 3, "is_active": True, "macro_fase": "analise"},
    {"name": "concluidos", "order": 4, "is_active": False, "macro_fase": "concluido"},
]


async def _semear_fases(db):
    for fase in FASES:
        await db.workflow_statuses.insert_one(dict(fase))


async def _semear_cliente_com_checklist_completa(db, client_id="c-1"):
    await db.clients.insert_one(
        {"id": client_id, "nome": "Joana Silva", "process_ids": [],
         "contacto": {"email": "joana@exemplo.pt"}, "dados_pessoais": {"nome": "Joana Silva"}}
    )
    await db.documents.insert_one(
        {"id": "d-1", "client_id": client_id, "source": "mandatory_checklist",
         "status": "RECEIVED", "category": "Index"}
    )


@pytest.fixture
async def mundo(fake_async_db):
    await _semear_fases(fake_async_db)
    with patch.object(omc, "db", fake_async_db), \
         patch.object(adv, "db", fake_async_db), \
         patch.object(workflow_phases, "db", fake_async_db), \
         patch.object(portal_profile, "db", fake_async_db), \
         patch.object(process_assignment, "db", fake_async_db), \
         patch.object(process_indexing, "db", fake_async_db), \
         patch.object(phase_automation, "db", fake_async_db), \
         patch("services.process_service.db", fake_async_db), \
         patch("database.db", fake_async_db), \
         patch("services.history.log_history", AsyncMock()):
        yield fake_async_db


# ─────────────────────────────────────────────────────────────────────
# 1. A criação do processo é atómica
# ─────────────────────────────────────────────────────────────────────

class TestSoUmProcessoPorCliente:
    async def test_dois_pedidos_em_simultaneo_criam_UM_processo(self, mundo):
        """O ataque é o dia-a-dia: o cliente larga 5 ficheiros de uma vez."""
        await _semear_cliente_com_checklist_completa(mundo)
        resultados = await asyncio.gather(
            omc.create_process_from_client_onboarding("c-1"),
            omc.create_process_from_client_onboarding("c-1"),
            omc.create_process_from_client_onboarding("c-1"),
        )
        processos = await mundo.processes.find({"client_id": "c-1"}).to_list(10)
        assert len(processos) == 1
        assert sum(1 for r in resultados if r.get("completed")) == 1
        perdedores = [r for r in resultados if not r.get("completed")]
        assert {r["error"] for r in perdedores} == {"creation_in_progress"}

    async def test_um_pedido_seguinte_ve_o_processo_existente_sem_reivindicar(self, mundo):
        await _semear_cliente_com_checklist_completa(mundo)
        primeiro = await omc.create_process_from_client_onboarding("c-1")
        # Já existe: responde com ele, não com «em curso».
        await mundo.clients.update_one({"id": "c-1"}, {"$set": {"process_ids": [primeiro["process_id"]]}})
        segundo = await omc.create_process_from_client_onboarding("c-1")
        assert segundo["already_existed"] is True
        assert segundo["process_id"] == primeiro["process_id"]

    async def test_a_reivindicacao_e_UMA_operacao_com_a_condicao_no_filtro(self):
        """O duplo não prova atomicidade (single-thread). O que se afirma um
        nível abaixo: é um `find_one_and_update` com a guarda no PRÓPRIO
        filtro, e não um `find_one` seguido de um `update_one`."""
        chamadas = {}

        class _Colecao:
            async def find_one_and_update(self, filtro, update, **kw):
                chamadas["filtro"], chamadas["update"] = filtro, update
                return {"id": "c-1"}

        class _Db:
            clients = _Colecao()

        with patch.object(omc, "db", _Db()):
            assert await omc.reivindicar_criacao_do_processo("c-1") is True

        assert chamadas["filtro"]["id"] == "c-1"
        ramos = chamadas["filtro"]["$or"]
        campo = omc.CAMPO_DA_REIVINDICACAO
        assert {campo: {"$exists": False}} in ramos
        assert {campo: None} in ramos
        assert any("$lt" in r.get(campo, {}) for r in ramos if isinstance(r.get(campo), dict))
        assert campo in chamadas["update"]["$set"]

    async def test_uma_reivindicacao_antiga_pode_ser_retomada(self, mundo):
        """Quem a ganhou morreu a meio: o cliente não fica sem processo."""
        await _semear_cliente_com_checklist_completa(mundo)
        velha = (datetime.now(timezone.utc) - omc.VALIDADE_DA_REIVINDICACAO - timedelta(seconds=5)).isoformat()
        await mundo.clients.update_one({"id": "c-1"}, {"$set": {omc.CAMPO_DA_REIVINDICACAO: velha}})
        assert await omc.reivindicar_criacao_do_processo("c-1") is True

    async def test_uma_reivindicacao_recente_nao_e_retomada(self, mundo):
        await _semear_cliente_com_checklist_completa(mundo)
        recente = (datetime.now(timezone.utc) - timedelta(seconds=10)).isoformat()
        await mundo.clients.update_one({"id": "c-1"}, {"$set": {omc.CAMPO_DA_REIVINDICACAO: recente}})
        assert await omc.reivindicar_criacao_do_processo("c-1") is False

    async def test_se_a_criacao_falha_o_direito_e_devolvido(self, mundo):
        await _semear_cliente_com_checklist_completa(mundo)
        with patch("services.process_service.get_next_process_number",
                   AsyncMock(side_effect=RuntimeError("mongo caiu"))):
            with pytest.raises(RuntimeError):
                await omc.create_process_from_client_onboarding("c-1")
        # O pedido seguinte tem de poder tentar JÁ, sem esperar a validade.
        r = await omc.create_process_from_client_onboarding("c-1")
        assert r["completed"] is True

    async def test_clientes_diferentes_nao_se_bloqueiam_entre_si(self, mundo):
        await _semear_cliente_com_checklist_completa(mundo, "c-1")
        await _semear_cliente_com_checklist_completa(mundo, "c-2")
        await mundo.documents.update_one({"id": "d-1"}, {"$set": {"client_id": "c-1"}})
        a, b = await asyncio.gather(
            omc.create_process_from_client_onboarding("c-1"),
            omc.create_process_from_client_onboarding("c-2"),
        )
        assert a["completed"] and b["completed"]


# ─────────────────────────────────────────────────────────────────────
# 2. O avanço para a Index é atómico
# ─────────────────────────────────────────────────────────────────────

class TestSoAvancaUmaVez:
    @pytest.fixture
    def indexador(self):
        async def _atribuir(process_id, update_status=True):
            return True, {"indexador": "ix-1"}, "ok"

        with patch.object(process_assignment, "assign_to_indexer", AsyncMock(side_effect=_atribuir)) as m:
            yield m

    async def _processo_em_pre_registo(self, db):
        await db.processes.insert_one(
            {"id": "p-1", "client_id": "c-1", "client_name": "Joana", "status": None}
        )

    async def test_avanca_para_a_primeira_fase_real_e_marca_a_entrega(self, mundo, indexador):
        await self._processo_em_pre_registo(mundo)
        await adv._auto_advance_from_pre_registo("p-1", "c-1")
        p = await mundo.processes.find_one({"id": "p-1"})
        assert p["status"] == "fase_index"
        assert p["portal_submitted_at"]
        indexador.assert_awaited_once()

    async def test_tres_pedidos_em_simultaneo_avancam_UMA_vez(self, mundo, indexador):
        await self._processo_em_pre_registo(mundo)
        await asyncio.gather(*[adv._auto_advance_from_pre_registo("p-1", "c-1") for _ in range(3)])
        # Um só indexador atribuído e um só relógio de fases a contar.
        assert indexador.await_count == 1
        p = await mundo.processes.find_one({"id": "p-1"})
        assert p["status"] == "fase_index"

    async def test_pedidos_que_LERAM_o_estado_antigo_so_um_escreve(self, mundo, indexador):
        """O interleaving real: os três leem «pré-registo» ANTES de qualquer
        escrita. Num duplo single-thread os pedidos correm um a seguir ao
        outro e o segundo já vê o estado novo — a corrida desaparece e a
        condição no filtro parece desnecessária. Aqui cede-se o controlo
        depois de cada leitura para a reproduzir."""
        await self._processo_em_pre_registo(mundo)
        original = mundo.processes.find_one

        async def _le_e_cede(*a, **kw):
            resultado = await original(*a, **kw)
            await asyncio.sleep(0)
            await asyncio.sleep(0)
            return resultado

        with patch.object(mundo.processes, "find_one", _le_e_cede):
            await asyncio.gather(*[adv._auto_advance_from_pre_registo("p-1", "c-1") for _ in range(3)])
        assert indexador.await_count == 1

    async def test_um_processo_que_ja_nao_esta_em_pre_registo_nao_e_tocado(self, mundo, indexador):
        await mundo.processes.insert_one(
            {"id": "p-2", "client_id": "c-1", "status": "fase_bancaria"}
        )
        await adv._auto_advance_from_pre_registo("p-2", "c-1")
        p = await mundo.processes.find_one({"id": "p-2"})
        assert p["status"] == "fase_bancaria" and "portal_submitted_at" not in p
        indexador.assert_not_called()

    async def test_a_escrita_leva_a_condicao_de_estado_no_filtro(self, mundo, indexador):
        """Um nível abaixo: sem a condição no filtro, a leitura de cima é a
        única defesa e dois pedidos passam ambos."""
        await self._processo_em_pre_registo(mundo)
        filtros = []
        original = mundo.processes.update_one

        async def _espia(filtro, update, **kw):
            filtros.append(filtro)
            return await original(filtro, update, **kw)

        with patch.object(mundo.processes, "update_one", _espia):
            await adv._auto_advance_from_pre_registo("p-1", "c-1")
        avanco = [f for f in filtros if "status" in f]
        assert avanco, "o avanço tem de condicionar o estado no filtro"
        assert avanco[0]["status"] == {"$in": ["pre_registo", None]}


# ─────────────────────────────────────────────────────────────────────
# 3. O perfil tranca com a ENTREGA, seja qual for a classificação da fase
# ─────────────────────────────────────────────────────────────────────

class TestOPerfilTranca:
    async def _trancado(self, db, fases=None) -> bool:
        query = portal_profile.construir_query_do_perfil_trancado(["p-1"], fases or FASES)
        return await db.processes.find_one(query, {"_id": 0, "id": 1}) is not None

    async def test_fase_de_entrada_em_macro_novo_COM_entrega_tranca(self, mundo):
        """O defeito: a Index classificada em «novo» deixava o cliente editar."""
        await mundo.processes.insert_one(
            {"id": "p-1", "status": "fase_index", "portal_submitted_at": "2026-10-10T10:00:00+00:00"}
        )
        assert await self._trancado(mundo) is True

    async def test_a_mesma_fase_SEM_entrega_nao_tranca(self, mundo):
        """Contraprova: um processo criado pela equipa na fase «novo», onde o
        cliente ainda recolhe documentos, continua editável."""
        await mundo.processes.insert_one({"id": "p-1", "status": "fase_index"})
        assert await self._trancado(mundo) is False

    @pytest.mark.parametrize("marca", [None, ""])
    async def test_marca_vazia_nao_conta(self, mundo, marca):
        await mundo.processes.insert_one(
            {"id": "p-1", "status": "fase_index", "portal_submitted_at": marca}
        )
        assert await self._trancado(mundo) is False

    async def test_fase_fora_da_recolha_tranca_mesmo_sem_marca(self, mundo):
        """A regra antiga continua: processos legados sem a marca."""
        await mundo.processes.insert_one({"id": "p-1", "status": "fase_bancaria"})
        assert await self._trancado(mundo) is True

    @pytest.mark.parametrize("estado", [None, "pre_registo"])
    async def test_um_lead_com_marca_nao_tranca(self, mundo, estado):
        """A marca é de um avanço que já não está em curso."""
        await mundo.processes.insert_one(
            {"id": "p-1", "status": estado, "portal_submitted_at": "2026-10-10T10:00:00+00:00"}
        )
        assert await self._trancado(mundo) is False

    async def test_processo_eliminado_nao_tranca(self, mundo):
        await mundo.processes.insert_one(
            {"id": "p-1", "status": "fase_index", "is_deleted": True,
             "portal_submitted_at": "2026-10-10T10:00:00+00:00"}
        )
        assert await self._trancado(mundo) is False

    async def test_so_o_processo_do_cliente_conta(self, mundo):
        await mundo.processes.insert_one(
            {"id": "p-outro", "status": "fase_index",
             "portal_submitted_at": "2026-10-10T10:00:00+00:00"}
        )
        assert await self._trancado(mundo) is False

    def test_os_dois_leitores_do_perfil_usam_a_regra_nova(self):
        from tests.unit.helpers_fonte import codigo_sem_comentarios

        fonte = codigo_sem_comentarios(open(portal_profile.__file__).read())
        assert fonte.count("construir_query_do_perfil_trancado(") >= 3  # def + 2 chamadas
        assert "construir_query_de_processo_a_trancar(process_ids" not in fonte.split(
            "def construir_query_do_perfil_trancado"
        )[1].split("async def carregar_campos_editaveis")[1]


# ─────────────────────────────────────────────────────────────────────
# 4. A máquina de estados, de ponta a ponta
# ─────────────────────────────────────────────────────────────────────

CONSULTOR = {"id": "u-cons", "name": "Carla", "email": "c@x.pt"}
MEDIADOR = {"id": "u-med", "name": "Marta", "email": "m@x.pt"}
INDEXADOR = {"id": "u-ix", "name": "Rui", "email": "ix@x.pt", "role": "indexacao"}


class TestOPercursoInteiro:
    async def test_do_pre_registo_ao_portal_bloqueado(self, mundo):
        from fastapi import HTTPException

        from services import portal_estado

        # Fase 1 de configuração: o Admin/CEO define o que acontece à saída da
        # Index — só o intermediário e uma tarefa.
        await mundo.workflow_statuses.update_one(
            {"name": "fase_documental"},
            {"$set": {
                "auto_assign_roles": ["intermediario"],
                "task_templates": [{"id": "t1", "title": "Pedir IRS", "priority": "Alta",
                                    "due_in_days": 5, "assigned_role": "intermediario"}],
            }},
        )
        workflow_phases.invalidar_cache_de_fases()
        for u in (CONSULTOR, MEDIADOR, INDEXADOR):
            await mundo.users.insert_one({**u, "is_active": True})

        async def _menos_ocupado(papel, company_id=None, network_id=None):
            return CONSULTOR if papel == "consultor" else MEDIADOR

        async def _atribuir_indexador(process_id, update_status=True):
            await mundo.processes.update_one(
                {"id": process_id}, {"$set": {"assigned_indexacao_id": INDEXADOR["id"]}}
            )
            return True, {}, "ok"

        with patch.object(process_assignment, "_find_least_busy_user", AsyncMock(side_effect=_menos_ocupado)), \
             patch.object(process_assignment, "_notify_newly_assigned_users", AsyncMock()), \
             patch.object(process_assignment, "assign_to_indexer", AsyncMock(side_effect=_atribuir_indexador)), \
             patch("services.process_sharing.sincronizar_parceiros_sem_falhar", AsyncMock()), \
             patch.object(process_indexing, "libertar_index_sem_falhar", AsyncMock(return_value={})), \
             patch.object(process_indexing, "trigger_financial_engine_safe", AsyncMock(return_value={})), \
             patch.object(process_indexing, "notify_assigned_users_indexing_complete", AsyncMock()), \
             patch.object(process_indexing, "trigger_indexer_waitlist", AsyncMock()), \
             patch("services.workflow_engine.process_trigger", AsyncMock()), \
             patch("services.process_sharing.sincronizar_parceiros_sem_falhar", AsyncMock()):

            # ── 1. PRÉ-REGISTO: sem processo, o Portal não tem o que bloquear ──
            await _semear_cliente_com_checklist_completa(mundo)
            assert await mundo.processes.count_documents({}) == 0

            # ── 2. UPLOAD OBRIGATÓRIO completo → o processo nasce ──
            await adv._trigger_onboarding_check("c-1")
            (processo,) = await mundo.processes.find({"client_id": "c-1"}).to_list(5)
            pid = processo["id"]

            # ── 3. FASE INDEX (automática) + indexador + perfil TRANCADO ──
            assert processo["status"] == "fase_index"
            assert processo["assigned_indexacao_id"] == INDEXADOR["id"]
            assert processo["portal_submitted_at"]
            query = portal_profile.construir_query_do_perfil_trancado([pid], FASES)
            assert await mundo.processes.find_one(query) is not None
            # Ainda sem consultor/intermediário: só saem da Index depois de indexado.
            assert not processo.get("assigned_mediador_ids")
            assert not processo.get("assigned_consultor_ids")
            assert await mundo.tasks.count_documents({"process_id": pid}) == 0

            # ── 4. SAÍDA DA INDEX → atribuição automática do intermediário ──
            await process_indexing.run_mark_process_indexed(
                pid, INDEXADOR, user_role="indexacao", all_roles=[],
                broadcast_fn=AsyncMock(),
            )
            depois = await mundo.processes.find_one({"id": pid})
            assert depois["is_indexed"] is True
            assert depois["status"] == "fase_documental"
            assert depois["assigned_mediador_ids"] == [MEDIADOR["id"]]
            assert not depois.get("assigned_consultor_ids")  # a fase só pediu o intermediário
            (tarefa,) = await mundo.tasks.find({"process_id": pid}).to_list(5)
            assert tarefa["assigned_to"] == [MEDIADOR["id"]]
            assert tarefa["title"] == "Pedir IRS" and tarefa["priority"] == "Alta"
            assert depois["assigned_indexacao_id"] is None  # a mesa da Indexação libertou-se
            # O perfil continua trancado depois de sair da Index.
            query = portal_profile.construir_query_do_perfil_trancado([pid], FASES)
            assert await mundo.processes.find_one(query) is not None

            # ── 5. O Portal está ABERTO enquanto a fase for activa ──
            await portal_estado.exigir_processo_activo(depois)

            # ── 6. FASE TERMINAL → Portal bloqueado ──
            await mundo.processes.update_one({"id": pid}, {"$set": {"status": "concluidos"}})
            fechado = await mundo.processes.find_one({"id": pid})
            with pytest.raises(HTTPException) as exc:
                await portal_estado.exigir_processo_activo(fechado)
            assert exc.value.status_code == 403

            # ── 7. Reabrir (volta a uma fase activa) → o Portal reabre ──
            await mundo.processes.update_one({"id": pid}, {"$set": {"status": "fase_bancaria"}})
            await portal_estado.exigir_processo_activo(await mundo.processes.find_one({"id": pid}))

    async def test_o_percurso_nao_cria_um_segundo_processo_se_o_check_repete(self, mundo):
        """Cada confirmação de upload repete a verificação."""
        await _semear_cliente_com_checklist_completa(mundo)
        with patch.object(process_assignment, "assign_to_indexer", AsyncMock(return_value=(True, {}, "ok"))), \
             patch("services.workflow_engine.process_trigger", AsyncMock()):
            await asyncio.gather(*[adv._trigger_onboarding_check("c-1") for _ in range(4)])
            await adv._trigger_onboarding_check("c-1")
        assert await mundo.processes.count_documents({"client_id": "c-1"}) == 1

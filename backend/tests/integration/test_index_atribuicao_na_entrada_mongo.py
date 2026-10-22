"""A entrada de um processo no pipeline atribui, sem ninguém escolher, um Index E um Intermediário (Out 2026).

MongoDB real: o que se afirma é a escolha por CARGA entre candidatos reais, o pool da rede do processo e o conjunto
canónico de campos do mediador. Só se falseiam as notificações (email/push), que não são o assunto.
"""
from __future__ import annotations

import os
import uuid
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from motor.motor_asyncio import AsyncIOMotorClient

from services import process_assignment as pa
from services import process_create as pc

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def bd(monkeypatch):
    url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    cliente = AsyncIOMotorClient(url, serverSelectionTimeoutMS=2000)
    try:
        await cliente.admin.command("ping")
    except Exception:
        cliente.close()
        pytest.skip("MongoDB não disponível")
    base = cliente[f"test_entrada_{uuid.uuid4().hex[:8]}"]
    from services import history, network_triage, workflow_phases
    from services import realtime_notifications as rt
    from services import push_notifications as push

    for modulo in (pa, network_triage, history, workflow_phases, rt, push):
        monkeypatch.setattr(modulo, "db", base)
    monkeypatch.setattr("database.db", base)
    workflow_phases.invalidar_cache_de_fases()
    monkeypatch.setattr(pa, "_notify_newly_assigned_users", AsyncMock())
    monkeypatch.setattr("services.notification_service.send_notification_with_preference_check", AsyncMock())
    await base.workflow_statuses.insert_many([
        {"id": "w1", "name": "novo", "order": 1, "is_active": True},
        {"id": "w3", "name": "concluido", "order": 9, "is_active": False},
    ])
    await base.companies.insert_many([
        {"id": "c1", "name": "Power", "network_id": "rede-A"},
        {"id": "c2", "name": "Domus", "network_id": "rede-B"},
    ])
    pessoas = (
        ("ix1", "Index 1", "indexacao", "c1"), ("ix2", "Index 2", "indexacao", "c1"),
        ("im1", "Interm 1", "intermediario", "c1"), ("im2", "Interm 2", "intermediario", "c1"),
        ("imB", "Interm B", "intermediario", "c2"), ("co1", "Consultor 1", "consultor", "c1"),
        ("dir", "Diretor", "diretor", "c1"),
    )
    for uid, nome, papel, empresa in pessoas:
        await base.users.insert_one({"id": uid, "name": nome, "email": f"{uid}@x.pt", "role": papel, "is_active": True,
                                     "company": "Power" if empresa == "c1" else "Domus"})
        await base.user_company_roles.insert_one({"user_id": uid, "company_id": empresa, "role": papel, "is_active": True})
    yield base
    workflow_phases.invalidar_cache_de_fases()
    await cliente.drop_database(base.name)
    cliente.close()


async def _processo(bd, pid, **extra):
    doc = {"id": pid, "client_name": "Cliente", "network_id": "rede-A", "status": "novo", "is_deleted": False,
           "is_indexed": False, "is_active": True, "index_status": "pending", **extra}
    await bd.processes.insert_one(doc)
    return doc


async def _carga_mediador(bd, uid, n):
    for i in range(n):
        await bd.processes.insert_one({"id": f"carga-{uid}-{i}", "network_id": "rede-A", "status": "novo", "is_deleted": False,
                                       "is_active": True, "assigned_mediador_ids": [uid]})


async def _doc(bd, pid):
    return await bd.processes.find_one({"id": pid}, {"_id": 0})


class TestIntermediarioNaEntrada:
    async def test_atribui_o_menos_ocupado_da_equipa_com_o_conjunto_canonico_de_campos(self, bd):
        await _processo(bd, "p1")
        await _carga_mediador(bd, "im1", 3)
        r = await pa.auto_assign_intermediario_on_entry("p1")
        assert r["mediador_id"] == "im2"
        doc = await _doc(bd, "p1")
        assert doc["assigned_mediador_id"] == "im2" and doc["assigned_mediador_ids"] == ["im2"]
        assert doc["mediador_id"] == "im2" and doc["mediador_name"] == "Interm 2"
        from services.assignment_drift import desfasamentos_do_processo

        assert desfasamentos_do_processo(doc) == []

    async def test_o_consultor_nunca_e_tocado(self, bd):
        await _processo(bd, "p1")
        await pa.auto_assign_intermediario_on_entry("p1")
        doc = await _doc(bd, "p1")
        assert not doc.get("assigned_consultor_ids") and not doc.get("consultor_id") and not doc.get("consultant_id")

    async def test_so_preenche_o_que_esta_vazio(self, bd):
        await _processo(bd, "p1", assigned_mediador_id="im1", assigned_mediador_ids=["im1"], mediador_id="im1", mediador_name="Interm 1")
        await _carga_mediador(bd, "im1", 9)
        await pa.auto_assign_intermediario_on_entry("p1")
        assert (await _doc(bd, "p1"))["assigned_mediador_ids"] == ["im1"]

    async def test_nunca_escolhe_de_outra_rede_nem_da_gestao(self, bd):
        await bd.users.update_many({"id": {"$in": ["im1", "im2"]}}, {"$set": {"is_active": False}})
        await _processo(bd, "p1")
        r = await pa.auto_assign_intermediario_on_entry("p1")
        assert r == {} or "mediador_id" not in r
        assert not (await _doc(bd, "p1")).get("assigned_mediador_ids")

    async def test_nunca_levanta(self, bd):
        await _processo(bd, "p1")
        with patch.object(pa, "dual_auto_assign_on_pre_registo_transition", AsyncMock(side_effect=RuntimeError("bd"))):
            assert await pa.auto_assign_intermediario_on_entry("p1") == {}

    async def test_a_carga_distribui_por_varios_processos(self, bd):
        for i in range(4):
            await _processo(bd, f"p{i}")
            await pa.auto_assign_intermediario_on_entry(f"p{i}")
        atribuidos = [(await _doc(bd, f"p{i}"))["assigned_mediador_ids"][0] for i in range(4)]
        assert sorted(atribuidos) == ["im1", "im1", "im2", "im2"]


class TestIndexadorNaEntrada:
    async def test_a_atribuicao_automatica_carimba_o_relogio_do_sla(self, bd):
        await _processo(bd, "p1")
        ok, dados, _ = await pa.assign_to_indexer("p1", update_status=False)
        assert ok and dados["assigned"]
        doc = await _doc(bd, "p1")
        assert doc["assigned_indexacao_id"] in ("ix1", "ix2") and doc["index_assigned_at"]
        assert doc["index_status"] == "pending"  # atribuído NÃO é em tratamento

    async def test_distribui_por_carga(self, bd):
        for i in range(4):
            await _processo(bd, f"p{i}")
            await pa.assign_to_indexer(f"p{i}", update_status=False)
        atribuidos = sorted([(await _doc(bd, f"p{i}"))["assigned_indexacao_id"] for i in range(4)])
        assert atribuidos == ["ix1", "ix1", "ix2", "ix2"]


class TestCriacaoDoProcesso:
    async def test_um_processo_novo_ganha_indexador_e_intermediario(self, bd):
        doc = await _processo(bd, "p1")
        await pc.maybe_auto_assign_indexer_on_create("p1", doc, is_lead=False, initial_status="novo")
        d = await _doc(bd, "p1")
        assert d["assigned_indexacao_id"] in ("ix1", "ix2") and d["assigned_mediador_ids"][0] in ("im1", "im2")

    async def test_uma_lead_nao_recebe_nenhum(self, bd):
        doc = await _processo(bd, "p1")
        await pc.maybe_auto_assign_indexer_on_create("p1", doc, is_lead=True, initial_status="lead")
        d = await _doc(bd, "p1")
        assert not d.get("assigned_indexacao_id") and not d.get("assigned_mediador_ids")

    async def test_via_verde_salta_o_index_mas_recebe_intermediario(self, bd):
        doc = await _processo(bd, "p1", skip_index=True)
        await pc.maybe_auto_assign_indexer_on_create("p1", doc, is_lead=False, initial_status="novo")
        d = await _doc(bd, "p1")
        assert not d.get("assigned_indexacao_id") and d["assigned_mediador_ids"][0] in ("im1", "im2")

    async def test_o_intermediario_que_cria_o_processo_mantem_se(self, bd):
        doc = await _processo(bd, "p1", assigned_mediador_id="im1", assigned_mediador_ids=["im1"], mediador_id="im1", mediador_name="Interm 1")
        await _carga_mediador(bd, "im1", 5)
        await pc.maybe_auto_assign_indexer_on_create("p1", doc, is_lead=False, initial_status="novo")
        assert (await _doc(bd, "p1"))["assigned_mediador_ids"] == ["im1"]

    async def test_sem_indexadores_o_intermediario_entra_na_mesma(self, bd):
        await bd.users.update_many({"role": "indexacao"}, {"$set": {"is_active": False}})
        doc = await _processo(bd, "p1")
        await pc.maybe_auto_assign_indexer_on_create("p1", doc, is_lead=False, initial_status="novo")
        d = await _doc(bd, "p1")
        assert not d.get("assigned_indexacao_id") and d["assigned_mediador_ids"]


class TestTriagemDaRedeDeDestino:
    async def test_a_entrada_na_triagem_atribui_indexador_e_intermediario_da_rede_de_destino(self, bd):
        from services import network_triage

        await _processo(bd, "p1", hub_triage={"network_id": "rede-A", "state": "em_triagem"})
        await network_triage._atribuir_indexador_da_rede("p1", "rede-A")
        d = await _doc(bd, "p1")
        assert d["assigned_indexacao_id"] in ("ix1", "ix2") and d["assigned_mediador_ids"][0] in ("im1", "im2")

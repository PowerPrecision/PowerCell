"""O caso Domus: uma rede SEM Index nunca entra na fila do Index e o consultor entra com o processo (Out 2026).

MongoDB real. Duas redes na mesma base: a Power (com indexador) e a Domus (sem). O que se afirma é a DIFERENÇA de
fluxos — o mesmo escritor, a mesma chamada, redes diferentes —, porque cada metade sozinha passa com a outra partida.
"""
from __future__ import annotations

import os
import uuid
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from motor.motor_asyncio import AsyncIOMotorClient

from services import index_status
from services import network_triage as nt
from services import process_assignment as pa

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
    base = cliente[f"test_sem_index_{uuid.uuid4().hex[:8]}"]
    from services import history, workflow_phases
    from services import realtime_notifications as rt
    from services import push_notifications as push

    for modulo in (pa, nt, history, workflow_phases, rt, push):
        monkeypatch.setattr(modulo, "db", base)
    monkeypatch.setattr("database.db", base)
    workflow_phases.invalidar_cache_de_fases()
    monkeypatch.setattr(pa, "_notify_newly_assigned_users", AsyncMock())
    await base.workflow_statuses.insert_many([
        {"id": "w1", "name": "novo", "order": 1, "is_active": True},
        {"id": "w3", "name": "concluido", "order": 9, "is_active": False},
    ])
    await base.companies.insert_many([
        {"id": "c1", "name": "Power", "network_id": "rede-power"},
        {"id": "c2", "name": "Domus", "network_id": "rede-domus"},
    ])
    pessoas = (
        ("ix1", "Index Power", "indexacao", "c1"),
        ("co-p", "Consultor Power", "consultor", "c1"),
        ("co-d1", "Consultor Domus 1", "consultor", "c2"),
        ("co-d2", "Consultor Domus 2", "consultor", "c2"),
        ("im-d", "Interm Domus", "intermediario", "c2"),
        ("dir-d", "Diretor Domus", "diretor", "c2"),
    )
    for uid, nome, papel, empresa in pessoas:
        await base.users.insert_one({"id": uid, "name": nome, "email": f"{uid}@x.pt", "role": papel,
                                     "is_active": True, "company": "Power" if empresa == "c1" else "Domus"})
        await base.user_company_roles.insert_one({"user_id": uid, "company_id": empresa, "role": papel, "is_active": True})
    yield base
    workflow_phases.invalidar_cache_de_fases()
    await cliente.drop_database(base.name)
    cliente.close()


async def _nasce(bd, pid, rede, **extra):
    """Um processo a nascer pelo MESMO caminho dos escritores: carimbo → regime de indexação → gravar."""
    doc = {"id": pid, "client_name": "Cliente", "network_id": rede, "status": "novo", "is_deleted": False,
           "is_active": True, **extra}
    await nt.aplicar_regime_de_indexacao(doc)
    await bd.processes.insert_one(dict(doc))
    return doc


async def _doc(bd, pid):
    return await bd.processes.find_one({"id": pid}, {"_id": 0})


class TestOBypassDeEstado:
    async def test_a_rede_sem_index_nasce_dispensada_e_fora_da_fila(self, bd):
        await _nasce(bd, "d1", "rede-domus")
        doc = await _doc(bd, "d1")
        assert doc["skip_index"] is True and doc["index_dispensado_por"] == nt.MARCA_SEM_INDEX
        assert doc["index_status"] == index_status.INDEXED and doc["index_skipped"] is True
        fila = await bd.processes.count_documents(index_status.condicao_da_fila("pending"))
        assert fila == 0

    async def test_a_rede_com_index_nasce_na_fila(self, bd):
        await _nasce(bd, "p1", "rede-power")
        doc = await _doc(bd, "p1")
        assert not doc.get("skip_index") and doc["index_status"] == index_status.PENDING
        assert await bd.processes.count_documents(index_status.condicao_da_fila("pending")) == 1

    async def test_a_mesma_chamada_da_resultados_diferentes_conforme_a_rede(self, bd):
        await _nasce(bd, "p1", "rede-power")
        await _nasce(bd, "d1", "rede-domus")
        na_fila = {d["id"] async for d in bd.processes.find(index_status.condicao_da_fila("pending"), {"id": 1})}
        assert na_fila == {"p1"}


class TestAtribuicaoDoConsultorNaEntrada:
    async def test_rede_sem_index_recebe_o_consultor_menos_ocupado_da_sua_equipa(self, bd):
        for i in range(3):
            await bd.processes.insert_one({"id": f"carga-{i}", "network_id": "rede-domus", "status": "novo",
                                           "is_deleted": False, "is_active": True, "assigned_consultor_ids": ["co-d1"]})
        await _nasce(bd, "d1", "rede-domus")
        r = await pa.auto_assign_consultor_on_entry("d1")
        assert r["consultant_id"] == "co-d2"
        doc = await _doc(bd, "d1")
        assert doc["assigned_consultor_ids"] == ["co-d2"] and doc["assigned_consultor_id"] == "co-d2"
        assert doc["consultor_id"] == "co-d2" and doc["consultant_id"] == "co-d2"
        from services.assignment_drift import desfasamentos_do_processo

        assert desfasamentos_do_processo(doc) == []

    async def test_nunca_sai_da_rede_do_processo_nem_escolhe_a_gestao(self, bd):
        await _nasce(bd, "d1", "rede-domus")
        await pa.auto_assign_consultor_on_entry("d1")
        escolhido = (await _doc(bd, "d1"))["assigned_consultor_ids"][0]
        assert escolhido in ("co-d1", "co-d2")  # nunca o `co-p` da Power nem o diretor da Domus

    async def test_rede_com_index_mantem_a_regra_actual_sem_consultor_forcado(self, bd):
        await _nasce(bd, "p1", "rede-power")
        assert await pa.auto_assign_consultor_on_entry("p1") == {}
        doc = await _doc(bd, "p1")
        assert not doc.get("assigned_consultor_ids") and not doc.get("consultant_id")

    async def test_via_verde_pedida_a_mao_numa_rede_com_index_nao_forca_consultor(self, bd):
        await _nasce(bd, "p1", "rede-power", skip_index=True)
        assert (await _doc(bd, "p1")).get("index_dispensado_por") is None
        assert await pa.auto_assign_consultor_on_entry("p1") == {}
        assert not (await _doc(bd, "p1")).get("assigned_consultor_ids")

    async def test_nao_sobrepoe_o_consultor_que_ja_la_esta(self, bd):
        await _nasce(bd, "d1", "rede-domus", assigned_consultor_id="co-d1", assigned_consultor_ids=["co-d1"],
                     consultor_id="co-d1", consultant_id="co-d1", consultor_name="Consultor Domus 1")
        for i in range(5):
            await bd.processes.insert_one({"id": f"c{i}", "network_id": "rede-domus", "status": "novo", "is_deleted": False,
                                           "is_active": True, "assigned_consultor_ids": ["co-d1"]})
        await pa.auto_assign_consultor_on_entry("d1")
        assert (await _doc(bd, "d1"))["assigned_consultor_ids"] == ["co-d1"]

    async def test_sem_consultores_na_rede_nao_falha_nem_inventa(self, bd):
        await bd.users.update_many({"id": {"$in": ["co-d1", "co-d2"]}}, {"$set": {"is_active": False}})
        await _nasce(bd, "d1", "rede-domus")
        await pa.auto_assign_consultor_on_entry("d1")
        assert not (await _doc(bd, "d1")).get("assigned_consultor_ids")

    async def test_nunca_levanta(self, bd):
        await _nasce(bd, "d1", "rede-domus")
        with patch.object(pa, "dual_auto_assign_on_pre_registo_transition", AsyncMock(side_effect=RuntimeError("bd"))):
            assert await pa.auto_assign_consultor_on_entry("d1") == {}

    async def test_processo_inexistente_nao_levanta(self, bd):
        assert await pa.auto_assign_consultor_on_entry("nao-existe") == {}


class TestOEscritorDeProcessosLigaTudo:
    """O mesmo escritor real, duas redes: a diferença de fluxos de ponta a ponta."""

    async def _entrada(self, bd, monkeypatch, pid, rede):
        from services import process_create as pc

        monkeypatch.setattr(pc, "db", bd, raising=False)
        doc = await _nasce(bd, pid, rede)
        await pc.maybe_auto_assign_indexer_on_create(pid, doc, is_lead=False, initial_status="novo")
        return await _doc(bd, pid)

    async def test_rede_sem_index_nasce_com_consultor_e_intermediario_e_sem_indexador(self, bd, monkeypatch):
        doc = await self._entrada(bd, monkeypatch, "d1", "rede-domus")
        assert doc["assigned_consultor_ids"][0] in ("co-d1", "co-d2")
        assert doc["assigned_mediador_ids"] == ["im-d"]
        assert not doc.get("assigned_indexacao_id")
        assert doc["index_status"] == index_status.INDEXED

    async def test_rede_com_index_nasce_com_indexador_e_sem_consultor(self, bd, monkeypatch):
        doc = await self._entrada(bd, monkeypatch, "p1", "rede-power")
        assert doc.get("assigned_indexacao_id") == "ix1"
        assert not doc.get("assigned_consultor_ids") and not doc.get("consultant_id")
        assert doc["index_status"] == index_status.PENDING


class TestACapacidadeDaRede:
    async def test_so_a_rede_com_indexador_tem_index(self, bd):
        assert await nt.capacidades_da_rede("rede-power") == {"has_index": True}
        assert await nt.capacidades_da_rede("rede-domus") == {"has_index": False}

    async def test_sem_rede_o_modulo_fica_a_vista(self, bd):
        assert await nt.capacidades_da_rede(None) == {"has_index": True}

    async def test_a_empresa_resolve_por_id_e_por_nome(self, bd):
        assert await nt.rede_da_empresa("c2") == "rede-domus"
        assert await nt.rede_da_empresa("Domus") == "rede-domus"
        assert await nt.rede_da_empresa("default") is None
        assert await nt.rede_da_empresa("nao-existe") is None

    async def test_se_o_ultimo_indexador_sai_a_rede_deixa_de_ter_index(self, bd):
        await bd.users.update_one({"id": "ix1"}, {"$set": {"is_active": False}})
        # sem NENHUMA rede com Index a regra não se liga (instalação nova): ninguém é «sem Index»
        assert await nt.capacidades_da_rede("rede-domus") == {"has_index": True}

    async def test_auth_me_diz_a_capacidade_da_empresa_em_vigor(self, bd):
        from services.auth_profile_handlers import _capacidades_da_empresa_em_vigor

        assert await _capacidades_da_empresa_em_vigor({"role": "consultor"}, "c2") == {"has_index": False}
        assert await _capacidades_da_empresa_em_vigor({"role": "consultor"}, "c1") == {"has_index": True}
        # o Master escolheu a Domus no cabeçalho: a vista manda
        assert await _capacidades_da_empresa_em_vigor({"role": "master", "vista_empresa_id": "c2"}, "c1") == {"has_index": False}
        # o Master sem empresa escolhida está na vista Sistema (todas as redes) e NÃO herda `users.company`
        assert await _capacidades_da_empresa_em_vigor({"role": "master"}, "c2") == {"has_index": True}

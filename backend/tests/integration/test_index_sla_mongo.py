"""SLA de inactividade do Index em DOIS níveis — MongoDB real (Out 2026).

Nível 1 (intocado → reatribui) e nível 2 (estagnado → só avisa) com a atribuição, o histórico, as notificações e a
gestão da rede REAIS; o relógio é o parâmetro `agora` (nada de `sleep`). Os processos nascem como a produção os deixa:
`assigned_indexacao_id` + `index_assigned_at` do `assign_to_indexer`, e o arranque/actividade de `registar_trabalho`.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from motor.motor_asyncio import AsyncIOMotorClient

from services import index_sla as sla
from services import index_status as ist

pytestmark = pytest.mark.asyncio

AGORA = datetime(2026, 10, 22, 12, 0, tzinfo=timezone.utc)


def _h(horas: float) -> str:
    return (AGORA - timedelta(hours=horas)).isoformat()


def _d(dias: float) -> str:
    return (AGORA - timedelta(days=dias)).isoformat()


LISBOA = sla.FUSO_DOS_DIAS_UTEIS


def _mover_uteis(desde: datetime, dias_uteis: int, sentido: int) -> datetime:
    """`dias_uteis` dias úteis antes (-1) ou depois (+1) de `desde`, em RELÓGIO DE PAREDE de Lisboa.

    A contagem do SLA é a que o utilizador faz — «sexta às 17:00 + 5 dias úteis = sexta às 17:00» —,
    por isso a mudança de hora (25/10/2026) não pode deslocar a fronteira uma hora.
    """
    local = desde.astimezone(LISBOA).replace(tzinfo=None)
    faltam = dias_uteis
    while faltam > 0:
        local += timedelta(days=sentido)
        if local.weekday() < 5:
            faltam -= 1
    return local.replace(tzinfo=LISBOA).astimezone(timezone.utc)


def _du_dt(dias_uteis: int) -> datetime:
    """O momento que fica `dias_uteis` DIAS ÚTEIS antes de AGORA (salta sábados e domingos)."""
    return _mover_uteis(AGORA, dias_uteis, -1)


def _du(dias_uteis: int) -> str:
    return _du_dt(dias_uteis).isoformat()


def _depois_uteis(dias_uteis: int, desde: datetime = AGORA) -> timedelta:
    """O intervalo (a somar a AGORA) que leva a `dias_uteis` dias úteis depois de `desde`."""
    return _mover_uteis(desde, dias_uteis, +1) - AGORA


@pytest_asyncio.fixture
async def bd(monkeypatch):
    url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    cliente = AsyncIOMotorClient(url, serverSelectionTimeoutMS=2000)
    try:
        await cliente.admin.command("ping")
    except Exception:
        cliente.close()
        pytest.skip("MongoDB não disponível")
    base = cliente[f"test_index_sla_{uuid.uuid4().hex[:8]}"]
    from services import alert_audience, history, network_triage, process_assignment, workflow_phases
    from services import realtime_notifications as rt
    from services import push_notifications as push

    for modulo in (sla, ist, process_assignment, network_triage, history, alert_audience, workflow_phases, rt, push):
        monkeypatch.setattr(modulo, "db", base)
    monkeypatch.setattr("database.db", base)
    workflow_phases.invalidar_cache_de_fases()
    monkeypatch.delenv("INDEX_SLA_UNTOUCHED_HOURS", raising=False)
    monkeypatch.delenv("INDEX_SLA_STALE_DAYS", raising=False)
    monkeypatch.delenv("INDEX_SLA_ENABLED", raising=False)

    await base.workflow_statuses.insert_many([
        {"id": "w1", "name": "novo", "order": 1, "is_active": True},
        {"id": "w2", "name": "em_analise", "order": 2, "is_active": True},
        {"id": "w3", "name": "concluido", "order": 9, "is_active": False},
    ])
    await base.companies.insert_many([
        {"id": "c1", "name": "Power", "network_id": "rede-A"},
        {"id": "c2", "name": "Domus", "network_id": "rede-B"},
    ])
    for uid, nome, papel, empresa in (
        ("ix1", "Ana Index", "indexacao", "c1"), ("ix2", "Bruno Index", "indexacao", "c1"),
        ("ix3", "Carla Index", "indexacao", "c1"), ("ixB", "Dora Index", "indexacao", "c2"),
        ("dir1", "Diretor A", "diretor", "c1"), ("dirB", "Diretor B", "diretor", "c2"),
    ):
        await base.users.insert_one({"id": uid, "name": nome, "email": f"{uid}@x.pt", "role": papel, "is_active": True, "company": "Power" if empresa == "c1" else "Domus"})
        await base.user_company_roles.insert_one({"user_id": uid, "company_id": empresa, "role": papel, "is_active": True})
    yield base
    workflow_phases.invalidar_cache_de_fases()
    await cliente.drop_database(base.name)
    cliente.close()


async def _processo(bd, pid="p1", **extra):
    doc = {"id": pid, "process_number": 100, "client_name": "Cliente Segredo", "network_id": "rede-A", "status": "novo",
           "is_deleted": False, "is_indexed": False, "index_status": "pending", "assigned_indexacao_id": "ix1",
           "indexacao_name": "Ana Index", "index_assigned_at": _h(49), "created_at": _d(10), "updated_at": _d(10), **extra}
    await bd.processes.insert_one(doc)
    return doc


async def _doc(bd, pid="p1"):
    return await bd.processes.find_one({"id": pid}, {"_id": 0})


async def _avisos(bd, **filtro):
    return await bd.notifications.find(filtro, {"_id": 0}).to_list(50)


# ====================================================================
# PURO
# ====================================================================
class TestConfiguracao:
    def test_omissoes(self):
        assert sla.horas_sem_pegar({}) == 48 and sla.dias_sem_actividade({}) == 5 and sla.sla_activo({}) is True

    @pytest.mark.parametrize("valor", ["0", "-3", "x", "", None])
    def test_valor_invalido_cai_na_omissao_e_nunca_desliga_o_limiar(self, valor):
        assert sla.horas_sem_pegar({"INDEX_SLA_UNTOUCHED_HOURS": valor}) == 48
        assert sla.dias_sem_actividade({"INDEX_SLA_STALE_DAYS": valor}) == 5

    def test_valores_validos_e_interruptor(self):
        assert sla.horas_sem_pegar({"INDEX_SLA_UNTOUCHED_HOURS": "24"}) == 24
        assert sla.dias_sem_actividade({"INDEX_SLA_STALE_DAYS": "3"}) == 3
        assert sla.sla_activo({"INDEX_SLA_ENABLED": "false"}) is False


class TestPredicados:
    def test_intocado_so_com_atribuicao_pendente_e_prazo_vencido(self):
        base = {"assigned_indexacao_id": "u", "index_status": "pending", "index_assigned_at": _h(49)}
        assert sla.esta_intocado(base, AGORA, 48) is True
        assert sla.esta_intocado({**base, "index_assigned_at": _h(47)}, AGORA, 48) is False
        assert sla.esta_intocado({**base, "index_status": "in_review"}, AGORA, 48) is False
        assert sla.esta_intocado({**base, "assigned_indexacao_id": None}, AGORA, 48) is False
        assert sla.esta_intocado({**base, "is_indexed": True}, AGORA, 48) is False
        assert sla.esta_intocado({**base, "skip_index": True}, AGORA, 48) is False
        assert sla.esta_intocado({k: v for k, v in base.items() if k != "index_assigned_at"}, AGORA, 48) is False

    def test_estagnado_so_depois_de_comecar_e_alem_do_prazo(self):
        base = {"assigned_indexacao_id": "u", "index_status": "in_review", "index_last_activity_at": _du(6)}
        assert sla.esta_estagnado(base, AGORA, 5) is True
        assert sla.esta_estagnado({**base, "index_last_activity_at": _du(4)}, AGORA, 5) is False
        assert sla.esta_estagnado({**base, "index_status": "pending"}, AGORA, 5) is False
        assert sla.esta_estagnado({**base, "assigned_indexacao_id": None}, AGORA, 5) is False

    def test_a_referencia_cai_em_cascata_ate_ao_updated_at_do_legado(self):
        assert sla.ultima_actividade({"index_last_activity_at": _d(1), "index_work_started_at": _d(9), "updated_at": _d(20)}) == AGORA - timedelta(days=1)
        assert sla.ultima_actividade({"index_work_started_at": _d(9), "updated_at": _d(20)}) == AGORA - timedelta(days=9)
        assert sla.ultima_actividade({"updated_at": _d(20)}) == AGORA - timedelta(days=20)
        assert sla.ultima_actividade({}) is None

    def test_alertar_uma_vez_lembrar_e_reabrir_com_actividade(self):
        p = {"assigned_indexacao_id": "u", "index_status": "in_review", "index_last_activity_at": _du(6)}
        assert sla.deve_alertar(p, AGORA, 5) is True
        assert sla.deve_alertar({**p, "index_stagnation_alerted_at": _du(1)}, AGORA, 5) is False  # já avisou
        antigo = (_du_dt(5) - timedelta(hours=2)).isoformat()   # passaram mais de 5 dias ÚTEIS
        assert sla.deve_alertar({**p, "index_stagnation_alerted_at": antigo}, AGORA, 5) is True  # lembrete
        # houve actividade DEPOIS do último alerta e voltou a parar: novo ciclo
        meio = (_du_dt(5) - timedelta(hours=12)).isoformat()
        p2 = {**p, "index_last_activity_at": meio, "index_stagnation_alerted_at": _du(9)}
        assert sla.deve_alertar(p2, AGORA, 5) is True

    def test_escolha_prefere_quem_ainda_nao_teve_o_processo(self):
        livres = [{"id": "a"}, {"id": "b"}, {"id": "c"}]
        assert sla.escolher_novo_indexador(livres, ["a"])["id"] == "b"
        assert sla.escolher_novo_indexador(livres, ["a", "b", "c"])["id"] == "a"  # todos já tiveram: o menos carregado
        assert sla.escolher_novo_indexador([], []) is None


# ====================================================================
# NÍVEL 1 — INTOCADO
# ====================================================================
class TestNivel1Intocado:
    async def test_passadas_48h_sem_pegar_retira_e_reatribui_a_outro(self, bd):
        await _processo(bd)
        r = await sla.correr_sla_do_index(agora=AGORA)
        assert r["nivel1"]["reatribuidos"] == 1
        doc = await _doc(bd)
        assert doc["assigned_indexacao_id"] in ("ix2", "ix3") and doc["assigned_indexacao_id"] != "ix1"
        assert doc["indexacao_name"].endswith("Index") and doc["indexacao_name"] != "Ana Index"
        assert doc["index_assigned_at"] == AGORA.isoformat()  # o relógio recomeça para o novo
        assert doc["index_sla_anteriores"] == ["ix1"] and doc["index_sla_reatribuicoes"] == 1
        assert doc["index_status"] == "pending"

    async def test_deixa_historico_e_avisa_os_dois(self, bd):
        await _processo(bd)
        await sla.correr_sla_do_index(agora=AGORA)
        novo = (await _doc(bd))["assigned_indexacao_id"]
        antigo = await _avisos(bd, user_id="ix1")
        assert len(antigo) == 1 and antigo[0]["type"] == "process_unassigned" and "48h" in antigo[0]["message"]
        recebido = await _avisos(bd, user_id=novo)
        assert len(recebido) == 1 and recebido[0]["type"] == "process_assigned"
        assert recebido[0]["link"] == "/index/p1"
        hist = await bd.history.find({"process_id": "p1"}, {"_id": 0}).to_list(10)
        assert hist and "Reatribuído automaticamente" in hist[0]["action"]

    async def test_antes_das_48h_nao_toca(self, bd):
        await _processo(bd, index_assigned_at=_h(47))
        r = await sla.correr_sla_do_index(agora=AGORA)
        assert r["nivel1"]["reatribuidos"] == 0
        assert (await _doc(bd))["assigned_indexacao_id"] == "ix1"

    async def test_o_limiar_e_configuravel(self, bd, monkeypatch):
        await _processo(bd, index_assigned_at=_h(30))
        await sla.correr_sla_do_index(agora=AGORA)
        assert (await _doc(bd))["assigned_indexacao_id"] == "ix1"
        monkeypatch.setenv("INDEX_SLA_UNTOUCHED_HOURS", "24")
        await sla.correr_sla_do_index(agora=AGORA)
        assert (await _doc(bd))["assigned_indexacao_id"] != "ix1"

    async def test_um_processo_ja_em_tratamento_nunca_e_reatribuido_pelo_nivel_1(self, bd):
        await _processo(bd, index_status="in_review", index_assigned_at=_h(500), index_work_started_at=_h(400),
                        index_last_activity_at=_h(1))
        r = await sla.correr_sla_do_index(agora=AGORA)
        assert r["nivel1"]["reatribuidos"] == 0 and (await _doc(bd))["assigned_indexacao_id"] == "ix1"

    async def test_sem_outro_indexador_com_vaga_mantem_quem_esta(self, bd):
        await bd.users.update_many({"id": {"$in": ["ix2", "ix3"]}}, {"$set": {"is_active": False}})
        await _processo(bd)
        r = await sla.correr_sla_do_index(agora=AGORA)
        assert r["nivel1"]["sem_candidato"] == 1 and r["nivel1"]["reatribuidos"] == 0
        doc = await _doc(bd)
        assert doc["assigned_indexacao_id"] == "ix1" and doc["index_assigned_at"] == _h(49)  # o relógio não foi reposto

    async def test_um_indexador_sem_vaga_nao_recebe(self, bd):
        await bd.users.update_one({"id": "ix3"}, {"$set": {"is_active": False}})
        for i in range(15):  # ix2 está no limite de carga
            await bd.processes.insert_one({"id": f"carga{i}", "network_id": "rede-A", "status": "novo", "is_deleted": False,
                                           "is_indexed": False, "assigned_indexacao_id": "ix2"})
        await _processo(bd)
        r = await sla.correr_sla_do_index(agora=AGORA)
        assert r["nivel1"]["sem_candidato"] == 1 and (await _doc(bd))["assigned_indexacao_id"] == "ix1"

    async def test_a_equipa_e_a_rede_do_processo_e_nunca_outra(self, bd):
        await bd.users.update_many({"id": {"$in": ["ix2", "ix3"]}}, {"$set": {"is_active": False}})
        await _processo(bd)  # rede-A; o único outro indexador (ixB) é da rede-B
        await sla.correr_sla_do_index(agora=AGORA)
        assert (await _doc(bd))["assigned_indexacao_id"] == "ix1"

    async def test_se_o_indexador_comeca_entre_a_leitura_e_a_escrita_ganha_quem_trabalha(self, bd):
        await _processo(bd)
        from services import process_assignment as pa

        original = pa.indexadores_disponiveis

        async def comeca_a_meio(processo, **kw):
            await ist.registar_trabalho("p1", "ix1")  # o indexador abre a bancada neste instante
            return await original(processo, **kw)

        with patch.object(pa, "indexadores_disponiveis", comeca_a_meio):
            r = await sla.correr_sla_do_index(agora=AGORA)
        assert r["nivel1"]["corridas"] == 1 and r["nivel1"]["reatribuidos"] == 0
        doc = await _doc(bd)
        assert doc["assigned_indexacao_id"] == "ix1" and doc["index_status"] == "in_review"
        assert await _avisos(bd) == []

    async def test_indexado_dispensado_eliminado_ou_fase_terminal_ficam_de_fora(self, bd):
        await _processo(bd, "i", is_indexed=True, index_status="indexed")
        await _processo(bd, "d", skip_index=True)
        await _processo(bd, "x", is_deleted=True)
        await _processo(bd, "t", status="concluido")
        r = await sla.correr_sla_do_index(agora=AGORA)
        assert r["nivel1"]["reatribuidos"] == 0
        for pid in "idxt":
            assert (await _doc(bd, pid))["assigned_indexacao_id"] == "ix1"

    async def test_nao_reatribui_duas_vezes_seguidas(self, bd):
        await _processo(bd)
        await sla.correr_sla_do_index(agora=AGORA)
        primeiro = (await _doc(bd))["assigned_indexacao_id"]
        r2 = await sla.correr_sla_do_index(agora=AGORA + timedelta(hours=1))
        assert r2["nivel1"]["reatribuidos"] == 0 and (await _doc(bd))["assigned_indexacao_id"] == primeiro

    async def test_passadas_mais_48h_passa_para_o_terceiro_e_nao_volta_ao_primeiro(self, bd):
        await _processo(bd)
        await sla.correr_sla_do_index(agora=AGORA)
        segundo = (await _doc(bd))["assigned_indexacao_id"]
        await sla.correr_sla_do_index(agora=AGORA + timedelta(hours=49))
        doc = await _doc(bd)
        assert doc["assigned_indexacao_id"] not in ("ix1", segundo)
        assert doc["index_sla_anteriores"] == ["ix1", segundo]

    async def test_legado_sem_carimbo_comeca_a_contar_hoje_e_nao_e_reatribuido_em_massa(self, bd):
        doc = await _processo(bd)
        await bd.processes.update_one({"id": "p1"}, {"$unset": {"index_assigned_at": ""}})
        r = await sla.correr_sla_do_index(agora=AGORA)
        assert r["legados_carimbados"] == 1 and r["nivel1"]["reatribuidos"] == 0
        assert (await _doc(bd))["index_assigned_at"] == AGORA.isoformat()
        r2 = await sla.correr_sla_do_index(agora=AGORA + timedelta(hours=49))
        assert r2["nivel1"]["reatribuidos"] == 1 and doc

    async def test_desligado_nao_faz_nada(self, bd, monkeypatch):
        await _processo(bd)
        monkeypatch.setenv("INDEX_SLA_ENABLED", "false")
        assert await sla.correr_sla_do_index(agora=AGORA) == {"activo": False}
        assert (await _doc(bd))["assigned_indexacao_id"] == "ix1"

    async def test_um_aviso_que_falha_nao_desfaz_a_reatribuicao_nem_para_o_ciclo(self, bd):
        await _processo(bd, "p1")
        await _processo(bd, "p2")
        with patch("services.realtime_notifications.send_realtime_notification", AsyncMock(side_effect=RuntimeError("push em baixo"))):
            r = await sla.correr_sla_do_index(agora=AGORA)
        assert r["nivel1"]["reatribuidos"] == 2
        assert (await _doc(bd, "p1"))["assigned_indexacao_id"] != "ix1"


# ====================================================================
# NÍVEL 2 — ESTAGNADO
# ====================================================================
async def _em_tratamento(bd, pid="p1", dias=6, **extra):
    return await _processo(bd, pid, index_status="in_review", index_assigned_at=_d(30), index_work_started_at=_d(20),
                           index_last_activity_at=_du(dias), **extra)


class TestNivel2Estagnado:
    async def test_estagnado_nao_perde_a_atribuicao_e_avisa_indexador_e_chefia(self, bd):
        await _em_tratamento(bd, dias=6)
        r = await sla.correr_sla_do_index(agora=AGORA)
        assert r["nivel2"]["alertados"] == 1 and r["nivel1"]["reatribuidos"] == 0
        doc = await _doc(bd)
        assert doc["assigned_indexacao_id"] == "ix1" and doc["index_status"] == "in_review"  # NÃO se retira
        assert doc["index_stagnation_alerted_at"] == AGORA.isoformat()
        indexador = await _avisos(bd, user_id="ix1")
        chefia = await _avisos(bd, user_id="dir1")
        assert len(indexador) == 1 and indexador[0]["type"] == "index_stagnation" and "6 dias" in indexador[0]["message"]
        assert len(chefia) == 1 and chefia[0]["type"] == "index_stagnation" and "Ana Index" in chefia[0]["message"]
        assert chefia[0]["link"] == "/index/p1"

    async def test_a_chefia_de_outra_rede_nunca_e_avisada(self, bd):
        await _em_tratamento(bd)
        await sla.correr_sla_do_index(agora=AGORA)
        assert await _avisos(bd, user_id="dirB") == [] and await _avisos(bd, user_id="ixB") == []

    async def test_dentro_do_prazo_nao_avisa(self, bd):
        await _em_tratamento(bd, dias=4)
        r = await sla.correr_sla_do_index(agora=AGORA)
        assert r["nivel2"]["alertados"] == 0 and await _avisos(bd) == []

    async def test_o_prazo_e_configuravel(self, bd, monkeypatch):
        await _em_tratamento(bd, dias=4)
        monkeypatch.setenv("INDEX_SLA_STALE_DAYS", "3")
        r = await sla.correr_sla_do_index(agora=AGORA)
        assert r["nivel2"]["alertados"] == 1

    async def test_nao_repete_o_alerta_no_ciclo_seguinte_mas_lembra_passado_o_periodo(self, bd):
        await _em_tratamento(bd, dias=6)
        await sla.correr_sla_do_index(agora=AGORA)
        r2 = await sla.correr_sla_do_index(agora=AGORA + timedelta(hours=1))
        assert r2["nivel2"]["estagnados"] == 1 and r2["nivel2"]["alertados"] == 0
        assert len(await _avisos(bd, user_id="ix1")) == 1
        # O relógio do SLA é simulado; o da junção de avisos do mesmo processo (10 min) é real.
        # Cinco dias úteis depois a janela já fechou: fecha-se à mão para o lembrete não se juntar.
        await bd.notifications.update_many({}, {"$set": {"agrupar_ate": "2000-01-01T00:00:00+00:00"}})
        r3 = await sla.correr_sla_do_index(agora=AGORA + _depois_uteis(5) + timedelta(minutes=1))
        assert r3["nivel2"]["alertados"] == 1 and len(await _avisos(bd, user_id="ix1")) == 2

    async def test_actividade_do_indexador_reabre_o_ciclo(self, bd):
        await _em_tratamento(bd, dias=6)
        await sla.correr_sla_do_index(agora=AGORA)
        with patch.object(ist, "_agora", lambda: (AGORA + timedelta(days=1)).isoformat()):
            assert (await ist.registar_trabalho("p1", "ix1"))["registado"] is True
        r = await sla.correr_sla_do_index(agora=AGORA + timedelta(days=2))
        assert r["nivel2"]["estagnados"] == 0  # voltou a estar activo
        depois = AGORA + _depois_uteis(1)   # a actividade foi aqui; 5 dias úteis depois volta a estar parado
        r = await sla.correr_sla_do_index(agora=AGORA + _depois_uteis(5, depois) + timedelta(minutes=1))
        assert r["nivel2"]["alertados"] == 1  # parou outra vez: alerta novo, sem esperar pelo lembrete

    async def test_um_processo_so_atribuido_e_parado_ha_dez_dias_e_nivel_1_nao_e_alerta_de_estagnacao(self, bd):
        await _processo(bd, index_assigned_at=_d(10))
        r = await sla.correr_sla_do_index(agora=AGORA)
        assert r["nivel2"]["estagnados"] == 0 and r["nivel1"]["reatribuidos"] == 1
        assert await _avisos(bd, type="index_stagnation") == []

    async def test_legado_em_tratamento_sem_carimbos_usa_o_updated_at(self, bd):
        await _processo(bd, index_status="in_review", index_assigned_at=_d(30), updated_at=_d(8))
        r = await sla.correr_sla_do_index(agora=AGORA)
        assert r["nivel2"]["alertados"] == 1

    async def test_sem_ninguem_avisado_a_marca_nao_avanca(self, bd):
        await _em_tratamento(bd)
        with patch("services.realtime_notifications.send_realtime_notification", AsyncMock(side_effect=RuntimeError("em baixo"))):
            r = await sla.correr_sla_do_index(agora=AGORA)
        assert r["nivel2"]["alertados"] == 0
        assert "index_stagnation_alerted_at" not in await _doc(bd)
        r2 = await sla.correr_sla_do_index(agora=AGORA + timedelta(hours=1))  # tenta de novo no ciclo seguinte
        assert r2["nivel2"]["alertados"] == 1

    async def test_sem_rede_determinavel_so_o_indexador_e_avisado(self, bd):
        await _em_tratamento(bd, network_id=None)
        with patch.dict(os.environ, {"TENANT_DEFAULT_NETWORK_ID": ""}):
            await sla.correr_sla_do_index(agora=AGORA)
        assert len(await _avisos(bd, user_id="ix1")) == 1
        assert await _avisos(bd, user_id="dir1") == [] and await _avisos(bd, user_id="dirB") == []

    async def test_indexado_ou_dispensado_nunca_alerta(self, bd):
        await _em_tratamento(bd, "i", is_indexed=True)
        await _em_tratamento(bd, "d", skip_index=True)
        r = await sla.correr_sla_do_index(agora=AGORA)
        assert r["nivel2"]["estagnados"] == 0


# ====================================================================
# OS DOIS NÍVEIS NO MESMO CICLO + LIGAÇÃO AO JOB
# ====================================================================
class TestOsDoisNiveisJuntos:
    async def test_intocado_e_estagnado_no_mesmo_ciclo_cada_um_com_o_seu_tratamento(self, bd):
        await _processo(bd, "intocado")
        await _em_tratamento(bd, "estagnado", dias=7)
        r = await sla.correr_sla_do_index(agora=AGORA)
        assert r["nivel1"]["reatribuidos"] == 1 and r["nivel2"]["alertados"] == 1
        assert (await _doc(bd, "intocado"))["assigned_indexacao_id"] != "ix1"
        assert (await _doc(bd, "estagnado"))["assigned_indexacao_id"] == "ix1"

    async def test_o_job_horario_chama_o_sla_e_soma_o_que_tocou(self, bd):
        from services.scheduled_tasks import ScheduledTasksService

        await _processo(bd, "intocado")
        await _em_tratamento(bd, "estagnado", dias=7)
        tarefas = ScheduledTasksService.__new__(ScheduledTasksService)
        with patch.object(sla, "_agora", lambda: AGORA):
            assert await tarefas.run_index_sla() == 2

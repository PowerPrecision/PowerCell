"""Regras das notificações definidas com o Flavio (Nov 2026, «Reduzir notificações a mais»).

Uma secção por regra, provadas contra um MongoDB REAL (upserts, `$setOnInsert`, índices únicos).

1. Processos parados: um resumo por pessoa, só ao passar os 7 e os 14 dias, fora do Telegram.
2. Processos acabados (fase final do motor) ou eliminados não geram avisos.
3. A gestão (Diretor/CEO) recebe o resumo dos parados há mais de 21 dias da SUA empresa.
4. A gestão é sempre a da empresa do processo, não a da rede inteira.
5. Documentos a expirar: aos 60, 7 e 0 dias, juntos por cliente, fora do Telegram.
6. Lembrete mensal ao dia 25, do mês corrente, um por pessoa, uma vez por mês.
7. Ninguém é avisado do que ele próprio fez.
8. Telegram: por omissão só o que pede acção rápida; as escolhas antigas são esquecidas.
9. Chat de grupo: só apita a quem é mencionado com @nome.
11. Telegram: no máximo uma mensagem por pessoa a cada 15 minutos, com tudo o que chegou.
13. Na app só apita (som, toast, push) o que também iria para o Telegram.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from motor.motor_asyncio import AsyncIOMotorClient

from services import (
    alert_audience,
    avisos_de_rotina,
    db_indexes,
    notification_policy,
    realtime_notifications as rt,
    telegram_bot,
    telegram_link,
    telegram_notifications as tg,
    workflow_phases,
)
from services.scheduled_tasks import ScheduledTasksService
from services.telegram_bot import ResultadoDoEnvio

AGORA = datetime(2026, 11, 3, 10, 0, tzinfo=timezone.utc)
REDE = "rede-pp"


class _Dia(datetime):
    momento = AGORA

    @classmethod
    def now(cls, tz=None):
        return cls.momento


def _dias_atras(dias: int) -> str:
    return (AGORA - timedelta(days=dias)).isoformat()


@pytest_asyncio.fixture
async def bd(monkeypatch):
    url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    cliente = AsyncIOMotorClient(url, serverSelectionTimeoutMS=2000)
    try:
        await cliente.admin.command("ping")
    except Exception:
        cliente.close()
        pytest.skip("MongoDB não disponível")
    base = cliente[f"test_regras_notif_{uuid.uuid4().hex[:8]}"]
    resultados = {"created": [], "errors": [], "skipped": []}
    for colecao in ("telegram_links", "telegram_outbox", "avisos_de_rotina"):
        for idx in db_indexes.INDEX_DEFINITIONS[colecao]:
            await db_indexes._create_index_safe(getattr(base, colecao), idx, colecao, resultados)
    assert resultados["errors"] == []

    # O motor: «em_curso» é activa; «concluido» e a fase final criada pelo admin não.
    await base.workflow_statuses.insert_many([
        {"name": "em_curso", "label": "Em curso", "order": 1, "is_active": True, "network_id": None},
        {"name": "concluido", "label": "Concluído", "order": 2, "is_active": False, "network_id": None},
        {"name": "negocio_perdido", "label": "Negócio perdido", "order": 3, "is_active": False, "network_id": None},
    ])
    # Uma rede, três empresas (como o grupo PowerPrecision).
    await base.companies.insert_many([
        {"id": "cmp-power", "name": "Power", "network_id": REDE},
        {"id": "cmp-prec", "name": "Precision", "network_id": REDE},
        {"id": "cmp-sis", "name": "Sistema", "network_id": REDE},
    ])
    await base.user_company_roles.insert_many([
        {"user_id": "ceo-power", "company_id": "cmp-power", "role": "ceo"},
        {"user_id": "dir-power", "company_id": "cmp-power", "role": "diretor"},
        {"user_id": "ceo-prec", "company_id": "cmp-prec", "role": "ceo"},
        {"user_id": "master", "company_id": "cmp-sis", "role": "master"},
    ])

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:abc")
    monkeypatch.setenv("TELEGRAM_JANELA_SEGUNDOS", "0")
    monkeypatch.setenv("FRONTEND_URL", "https://app.exemplo.pt")
    monkeypatch.delenv("TENANT_DEFAULT_NETWORK_ID", raising=False)
    workflow_phases._cache_de_fases.clear()
    rt._invalidate_pref_cache()

    enviadas: list[dict] = []

    async def enviar_falso(chat_id, texto, *, url_botao="", texto_botao=""):
        enviadas.append({"chat_id": chat_id, "texto": texto, "url": url_botao})
        return ResultadoDoEnvio(ok=True)

    push = AsyncMock()
    with patch.object(notification_policy, "db", base), patch.object(telegram_link, "db", base), \
            patch.object(tg, "db", base), patch.object(rt, "db", base), \
            patch.object(alert_audience, "db", base), patch.object(workflow_phases, "db", base), \
            patch.object(telegram_bot, "enviar_mensagem", enviar_falso), \
            patch.object(rt, "entregar_a_utilizador", AsyncMock()), patch.object(rt, "send_push_notification", push), \
            patch("services.presenca.esta_online", AsyncMock(return_value=False)):
        base.enviadas = enviadas
        base.push = push
        yield base
    workflow_phases._cache_de_fases.clear()
    notification_policy.definir_ator(None)
    await cliente.drop_database(base.name)
    cliente.close()


@pytest.fixture
def servico(bd):
    svc = ScheduledTasksService()
    svc.db = bd
    return svc


async def _ligar_telegram(bd, user_id="u1", **extra):
    await bd.telegram_links.insert_one({"user_id": user_id, "ativo": True, "chat_id": 555, **extra})


async def _ligar_telegram_com_tudo(bd, user_id="u1"):
    """Telegram com TODAS as categorias ligadas: o que não deve ir, não vai mesmo assim."""
    await _ligar_telegram(
        bd, user_id, preferencias={c: True for c in telegram_link.CATEGORIAS},
        preferencias_versao=telegram_link.VERSAO_DAS_PREFERENCIAS,
    )


def _processo(pid, *, dias=10, status="em_curso", consultor="u1", mediador=None, empresa="cmp-power", **extra):
    doc = {
        "id": pid, "process_number": int(pid[1:]) if pid[1:].isdigit() else 0, "client_name": f"Cliente {pid}",
        "client_id": f"c-{pid}", "status": status, "updated_at": _dias_atras(dias), "network_id": REDE,
        "company_id": empresa, "assigned_consultor_ids": [consultor] if consultor else [],
        "assigned_mediador_ids": [mediador] if mediador else [],
    }
    doc.update(extra)
    return doc


async def _avisos(bd, tipo=None, user_id=None):
    filtro = {}
    if tipo:
        filtro["type"] = tipo
    if user_id:
        filtro["user_id"] = user_id
    return await bd.notifications.find(filtro, {"_id": 0}).to_list(100)


# ════════════════════════════════════════════════════════════════════
# 1. PROCESSOS PARADOS — UM RESUMO, SÓ AO PASSAR OS 7 E OS 14 DIAS
# ════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_parados_um_resumo_por_pessoa_e_nao_um_aviso_por_processo(bd, servico):
    await bd.processes.insert_many([
        _processo("p1", dias=8, mediador="u2"),
        _processo("p2", dias=9),
        _processo("p3", dias=20),
        _processo("p4", dias=2),  # não está parado
    ])
    criados = await avisos_de_rotina.avisar_processos_parados(servico, AGORA)

    u1 = await _avisos(bd, "processos_parados", "u1")
    assert len(u1) == 1 and criados == 2
    assert u1[0]["message"].startswith("⚠️ Tem 3 processos parados. URGENTE rever.")
    assert "1 há mais de 14 dias" in u1[0]["message"] and "2 há mais de 7 dias" in u1[0]["message"]
    u2 = await _avisos(bd, "processos_parados", "u2")
    assert len(u2) == 1 and u2[0]["message"].startswith("⚠️ Tem 1 processo parado.")


@pytest.mark.asyncio
async def test_parados_nao_repete_todos_os_dias_so_ao_passar_os_14(bd, servico):
    await bd.processes.insert_one(_processo("p1", dias=8))
    await avisos_de_rotina.avisar_processos_parados(servico, AGORA)
    # no dia seguinte, e nas horas seguintes, nada de novo
    for horas in (1, 24, 48):
        await avisos_de_rotina.avisar_processos_parados(servico, AGORA + timedelta(hours=horas))
    assert len(await _avisos(bd, "processos_parados")) == 1
    # passou os 14 dias: um aviso novo
    await avisos_de_rotina.avisar_processos_parados(servico, AGORA + timedelta(days=6))
    assert len(await _avisos(bd, "processos_parados")) == 2


@pytest.mark.asyncio
async def test_parados_processo_mexido_comeca_a_contar_outra_vez(bd, servico):
    await bd.processes.insert_one(_processo("p1", dias=8))
    await avisos_de_rotina.avisar_processos_parados(servico, AGORA)
    novo = AGORA + timedelta(days=1)
    await bd.processes.update_one({"id": "p1"}, {"$set": {"updated_at": novo.isoformat()}})
    await avisos_de_rotina.avisar_processos_parados(servico, novo + timedelta(days=3))
    assert len(await _avisos(bd, "processos_parados")) == 1
    await avisos_de_rotina.avisar_processos_parados(servico, novo + timedelta(days=7))
    assert len(await _avisos(bd, "processos_parados")) == 2


@pytest.mark.asyncio
async def test_parados_nao_vao_para_o_telegram(bd, servico):
    await _ligar_telegram_com_tudo(bd, "u1")
    await bd.processes.insert_one(_processo("p1", dias=30))
    await avisos_de_rotina.avisar_processos_parados(servico, AGORA)
    assert len(await _avisos(bd, "processos_parados", "u1")) == 1
    assert await bd.telegram_outbox.count_documents({}) == 0


@pytest.mark.asyncio
async def test_parados_vai_a_consultor_e_intermediario_mas_nao_ao_index(bd, servico):
    await bd.processes.insert_one(_processo("p1", dias=8, mediador="u2", assigned_indexacao_id="idx1"))
    await avisos_de_rotina.avisar_processos_parados(servico, AGORA)
    assert {a["user_id"] for a in await _avisos(bd, "processos_parados")} == {"u1", "u2"}


# ════════════════════════════════════════════════════════════════════
# 2. PROCESSOS ACABADOS OU ELIMINADOS NÃO AVISAM
# ════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_parados_ignora_fases_finais_do_motor_e_eliminados(bd, servico):
    await bd.processes.insert_many([
        _processo("p1", dias=30, status="concluido"),
        _processo("p2", dias=30, status="negocio_perdido"),  # fase final criada no motor
        _processo("p3", dias=30, is_deleted=True),
    ])
    assert await avisos_de_rotina.avisar_processos_parados(servico, AGORA) == 0
    assert await _avisos(bd) == []


@pytest.mark.asyncio
async def test_parados_usa_o_workflow_da_rede_do_processo(bd, servico):
    """Uma rede cujo workflow fecha «em_curso» não recebe avisos desses processos."""
    await bd.workflow_statuses.insert_many([
        {"name": "em_curso", "label": "Em curso", "order": 1, "is_active": False, "network_id": "rede-outra"},
        {"name": "analise", "label": "Análise", "order": 2, "is_active": True, "network_id": "rede-outra"},
    ])
    await bd.processes.insert_many([
        _processo("p1", dias=30, network_id="rede-outra", empresa=None),
        _processo("p2", dias=30, consultor="u2"),
    ])
    await avisos_de_rotina.avisar_processos_parados(servico, AGORA)
    assert {a["user_id"] for a in await _avisos(bd, "processos_parados")} == {"u2"}


@pytest.mark.asyncio
async def test_documentos_a_expirar_ignora_processos_acabados_e_eliminados(bd, servico):
    expira = (AGORA + timedelta(days=5)).strftime("%Y-%m-%d")
    await bd.processes.insert_many([
        _processo("p1", status="concluido"),
        _processo("p2", is_deleted=True),
    ])
    await bd.document_metadata.insert_many([
        {"id": "d1", "process_id": "p1", "expiry_date": expira, "ai_category": "CC"},
        {"id": "d2", "process_id": "p2", "expiry_date": expira, "ai_category": "CC"},
    ])
    assert await avisos_de_rotina.avisar_documentos_a_expirar(servico, AGORA) == 0


# ════════════════════════════════════════════════════════════════════
# 3. GESTÃO: RESUMO DOS PARADOS HÁ MAIS DE 21 DIAS, SÓ DA SUA EMPRESA
# ════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_gestao_recebe_o_resumo_so_da_sua_empresa(bd, servico):
    await bd.processes.insert_many([
        _processo("p1", dias=30, empresa="cmp-power"),
        _processo("p2", dias=25, empresa="cmp-power"),
        _processo("p3", dias=15, empresa="cmp-power"),  # ainda não chega à gestão
    ])
    await avisos_de_rotina.avisar_processos_parados(servico, AGORA)
    gestao = await _avisos(bd, "processos_parados_gestao")
    assert {a["user_id"] for a in gestao} == {"ceo-power", "dir-power"}
    assert gestao[0]["message"].startswith("⚠️ A sua empresa tem 2 processos parados há mais de 21 dias.")
    # e no dia seguinte não repete
    await avisos_de_rotina.avisar_processos_parados(servico, AGORA + timedelta(days=1))
    assert len(await _avisos(bd, "processos_parados_gestao")) == 2


# ════════════════════════════════════════════════════════════════════
# 4. A GESTÃO É A DA EMPRESA DO PROCESSO
# ════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_gestao_do_processo_e_a_da_empresa_nao_a_da_rede(bd):
    processo = _processo("p1", empresa="cmp-power")
    assert set(await alert_audience.gestao_do_processo(processo, ["ceo", "diretor"])) == {"ceo-power", "dir-power"}
    assert "ceo-prec" not in await alert_audience.gestao_do_processo(processo, ["ceo", "diretor", "admin"])
    # o nome da empresa também serve
    assert await alert_audience.gestao_do_processo({"company_name": "Precision"}, ["ceo"]) == ["ceo-prec"]


@pytest.mark.asyncio
async def test_o_master_continua_a_ser_procurado_na_rede(bd):
    processo = _processo("p1", empresa="cmp-power")
    assert "master" in await alert_audience.gestao_do_processo(processo, ["ceo", "master"])


@pytest.mark.asyncio
async def test_processo_sem_empresa_cai_na_gestao_da_rede(bd):
    processo = {"id": "p9", "network_id": REDE}
    assert set(await alert_audience.gestao_do_processo(processo, ["ceo"])) == {"ceo-power", "ceo-prec"}


@pytest.mark.asyncio
async def test_clientes_em_espera_contados_por_empresa(bd, servico):
    await bd.processes.insert_many([
        _processo("p1", status="clientes_espera", empresa="cmp-power", created_at=_dias_atras(40)),
        _processo("p2", status="clientes_espera", empresa="cmp-power", created_at=_dias_atras(40)),
        _processo("p3", status="clientes_espera", empresa="cmp-prec", created_at=_dias_atras(40)),
    ])
    await servico.check_clients_waiting_too_long(days=15)
    avisos = {a["user_id"]: a["message"] for a in await _avisos(bd, "clients_waiting")}
    assert avisos["ceo-power"].startswith("⚠️ 2 cliente(s)")
    assert avisos["ceo-prec"].startswith("⚠️ 1 cliente(s)")


# ════════════════════════════════════════════════════════════════════
# 5. DOCUMENTOS A EXPIRAR — 60, 7 E 0 DIAS, JUNTOS POR CLIENTE
# ════════════════════════════════════════════════════════════════════
def _validade(dias: int) -> str:
    return (AGORA + timedelta(days=dias)).strftime("%Y-%m-%d")


@pytest.mark.asyncio
async def test_documentos_do_mesmo_cliente_num_so_aviso(bd, servico):
    await bd.processes.insert_one(_processo("p1", mediador="u2"))
    await bd.document_metadata.insert_many([
        {"id": "d1", "process_id": "p1", "expiry_date": _validade(5), "ai_category": "Cartão de Cidadão"},
        {"id": "d2", "process_id": "p1", "expiry_date": _validade(0), "ai_category": "Recibo"},
        {"id": "d3", "process_id": "p1", "expiry_date": _validade(90), "ai_category": "IRS"},  # fora da janela
    ])
    assert await avisos_de_rotina.avisar_documentos_a_expirar(servico, AGORA) == 2
    aviso = (await _avisos(bd, "documentos_a_expirar", "u1"))[0]
    assert aviso["message"].startswith("📄 2 documentos de Cliente p1 a expirar:")
    assert "Recibo expira hoje" in aviso["message"] and "Cartão de Cidadão expira a" in aviso["message"]
    assert "IRS" not in aviso["message"]


@pytest.mark.asyncio
async def test_documento_avisa_aos_60_aos_7_e_no_dia_e_mais_nada(bd, servico):
    await bd.processes.insert_one(_processo("p1"))
    expira = AGORA + timedelta(days=50)
    await bd.document_metadata.insert_one(
        {"id": "d1", "process_id": "p1", "expiry_date": expira.strftime("%Y-%m-%d"), "ai_category": "CC"}
    )
    for dia in range(0, 51):
        await avisos_de_rotina.avisar_documentos_a_expirar(servico, AGORA + timedelta(days=dia))
        await avisos_de_rotina.avisar_documentos_a_expirar(servico, AGORA + timedelta(days=dia, hours=5))
    avisos = await _avisos(bd, "documentos_a_expirar", "u1")
    assert len(avisos) == 3
    assert any("expira hoje" in a["message"] for a in avisos)


@pytest.mark.asyncio
async def test_documentos_a_expirar_nao_vao_para_o_telegram(bd, servico):
    await _ligar_telegram_com_tudo(bd, "u1")
    await bd.processes.insert_one(_processo("p1"))
    await bd.document_metadata.insert_one(
        {"id": "d1", "process_id": "p1", "expiry_date": _validade(3), "ai_category": "CC"}
    )
    await avisos_de_rotina.avisar_documentos_a_expirar(servico, AGORA)
    assert len(await _avisos(bd, "documentos_a_expirar")) == 1
    assert await bd.telegram_outbox.count_documents({}) == 0


@pytest.mark.asyncio
async def test_o_antigo_watchdog_nao_repete_o_que_ja_foi_avisado(bd, servico):
    await bd.processes.insert_one(_processo("p1"))
    await bd.document_metadata.insert_one(
        {"id": "d1", "process_id": "p1", "expiry_date": _validade(3), "ai_category": "CC"}
    )
    _Dia.momento = AGORA
    with patch.object(avisos_de_rotina, "datetime", _Dia):
        await servico.check_expiring_documents()
        await servico.check_document_expirations_watchdog()
    assert len(await _avisos(bd, "documentos_a_expirar")) == 1


# ════════════════════════════════════════════════════════════════════
# 6. LEMBRETE MENSAL AO DIA 25, UM POR PESSOA, UMA VEZ POR MÊS
# ════════════════════════════════════════════════════════════════════
async def _lembrete(servico, momento):
    from services import scheduled_tasks

    _Dia.momento = momento
    with patch.object(scheduled_tasks, "datetime", _Dia), \
            patch.object(ScheduledTasksService, "send_monthly_reminder_email", AsyncMock()) as email:
        await servico.send_monthly_document_reminder()
    return email


@pytest.mark.asyncio
async def test_lembrete_mensal_so_a_partir_do_dia_25_e_uma_vez(bd, servico):
    await bd.processes.insert_many([
        _processo("p1", client_email="a@x.pt"),
        _processo("p2", client_email="b@x.pt"),
        _processo("p3", status="concluido", client_email="c@x.pt"),
    ])
    email = await _lembrete(servico, datetime(2026, 11, 24, 9, tzinfo=timezone.utc))
    assert await _avisos(bd) == [] and email.await_count == 0

    email = await _lembrete(servico, datetime(2026, 11, 25, 9, tzinfo=timezone.utc))
    avisos = await _avisos(bd, "monthly_document_reminder", "u1")
    assert len(avisos) == 1
    assert "de Novembro a 2 clientes" in avisos[0]["message"]
    assert email.await_count == 2
    assert email.await_args.kwargs["month_name"] == "Novembro"

    # o job corre de hora a hora: as passagens seguintes do mês não repetem
    email = await _lembrete(servico, datetime(2026, 11, 25, 10, tzinfo=timezone.utc))
    email2 = await _lembrete(servico, datetime(2026, 11, 28, 10, tzinfo=timezone.utc))
    assert email.await_count == 0 and email2.await_count == 0
    assert len(await _avisos(bd, "monthly_document_reminder")) == 1


@pytest.mark.asyncio
async def test_lembrete_mensal_nao_vai_para_o_telegram(bd, servico):
    await _ligar_telegram_com_tudo(bd, "u1")
    await bd.processes.insert_one(_processo("p1"))
    await _lembrete(servico, datetime(2026, 11, 25, 9, tzinfo=timezone.utc))
    assert len(await _avisos(bd, "monthly_document_reminder")) == 1
    assert await bd.telegram_outbox.count_documents({}) == 0


# ════════════════════════════════════════════════════════════════════
# 7. NINGUÉM É AVISADO DO QUE ELE PRÓPRIO FEZ
# ════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_quem_fez_a_accao_nao_e_avisado(bd):
    await bd.processes.insert_one(_processo("p1"))
    await _ligar_telegram(bd, "u1")
    notification_policy.definir_ator("u1")
    for tipo in ("process_assigned", "process_status_change", "document_upload", "task_assigned"):
        assert await notification_policy.deve_notificar("u1", tipo, "p1") is False
        assert await tg.agendar("u1", tipo, process_id="p1") is False
    assert await rt.send_realtime_notification("u1", "Atribuído", "x", "process_assigned", process_id="p1") is None
    # o resultado de um trabalho que a pessoa pediu continua a chegar-lhe
    assert await notification_policy.deve_notificar("u1", "index_analysis_done", "p1") is True
    # e os outros continuam a ser avisados do que u1 fez
    await bd.processes.update_one({"id": "p1"}, {"$set": {"assigned_mediador_ids": ["u2"]}})
    assert await notification_policy.deve_notificar("u2", "process_status_change", "p1") is True


def test_o_ator_e_definido_na_autenticacao():
    import inspect

    from services import auth

    assert "definir_ator(user.get(\"id\"))" in inspect.getsource(auth.get_current_user)


# ════════════════════════════════════════════════════════════════════
# 8. TELEGRAM — SÓ O QUE PEDE ACÇÃO RÁPIDA, POR OMISSÃO
# ════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_telegram_por_omissao_so_o_que_pede_accao_rapida(bd):
    await bd.processes.insert_one(_processo("p1"))
    await _ligar_telegram(bd, "u1")
    entram = [
        ("process_assigned", {}), ("task_assigned", {}), ("portal_message", {}), ("visit_request", {}),
        ("chat_message", {"conversa": "direta:u9"}), ("index_conversa", {}), ("deadline_missed", {}),
        ("event_reminder", {"urgente": True}), ("deadline_approaching", {"urgente": True}),
    ]
    ficam = [
        ("process_status_change", {}), ("document_upload", {}), ("indexing_complete", {}),
        ("deadline_approaching", {}), ("event_reminder", {}), ("partner_note", {}), ("task_completed", {}),
        ("chat_group_message", {"conversa": "grupo:g1"}), ("pre_approval_countdown", {}),
    ]
    for tipo, extra in entram:
        assert await tg.agendar("u1", tipo, process_id="p1", **extra) is True, tipo
    for tipo, extra in ficam:
        assert await tg.agendar("u1", tipo, process_id="p1", **extra) is False, tipo


@pytest.mark.asyncio
async def test_escolhas_antigas_sao_esquecidas_e_as_novas_valem(bd):
    await bd.processes.insert_one(_processo("p1"))
    # escolhas gravadas com as omissões antigas (sem versão): «estados» ligado
    await _ligar_telegram(bd, "u1", preferencias={"estados": True, "documentos": True})
    assert await tg.agendar("u1", "process_status_change", process_id="p1") is False
    # quem escolhe agora fica com a escolha
    await telegram_link.run_atualizar_preferencias({"id": "u1"}, {"estados": True}, None)
    assert await tg.agendar("u1", "process_status_change", process_id="p1") is True
    estado = await telegram_link.run_estado({"id": "u1"})
    assert estado["preferencias"]["estados"] is True and estado["preferencias"]["documentos"] is False


@pytest.mark.asyncio
async def test_lembrete_de_prazo_a_1_hora_e_urgente_os_outros_nao(bd, servico):
    await _ligar_telegram(bd, "u1")
    vence = datetime.now(timezone.utc) + timedelta(minutes=30)
    await bd.deadlines.insert_one({
        "id": "dl1", "title": "Escritura", "type": "event", "due_date": vence.isoformat(),
        "assigned_user_ids": ["u1"], "reminder_time": ["1h", "1d"],
    })
    with patch("services.notification_service.send_notification_with_preference_check", AsyncMock()):
        await servico.check_upcoming_deadlines()
    avisos = await _avisos(bd, "event_reminder", "u1")
    urgentes = [a for a in avisos if a.get("urgente")]
    assert len(urgentes) == 1 and urgentes[0]["alerta"] is True
    assert all(a["alerta"] is False for a in avisos if not a.get("urgente"))
    assert await bd.telegram_outbox.count_documents({}) == 1


# ════════════════════════════════════════════════════════════════════
# 9. CHAT DE GRUPO — SÓ APITA A QUEM É MENCIONADO
# ════════════════════════════════════════════════════════════════════
def test_mencao_com_arroba():
    from services.chat_messages import menciona

    assert menciona("Olá @ana, viste o processo?", "Ana Silva")
    assert menciona("@Ana Silva podes ver?", "Ana Silva")
    assert not menciona("Olá @anabela", "Ana Silva")
    assert not menciona("Olá Ana", "Ana Silva")
    assert not menciona("", "Ana")


@pytest.mark.asyncio
async def test_grupo_so_entra_no_telegram_de_quem_e_mencionado(bd):
    from services import chat_messages
    from models.chat import ChatMessageCreate

    await _ligar_telegram(bd, "u2")
    await bd.telegram_links.insert_one({"user_id": "u3", "ativo": True, "chat_id": 777})
    await bd.chat_groups.insert_one({
        "id": "g1", "name": "Equipa",
        "members": [
            {"user_id": "u1", "user_name": "Rui"},
            {"user_id": "u2", "user_name": "Ana Silva"},
            {"user_id": "u3", "user_name": "Bruno"},
        ],
    })
    with patch.object(chat_messages, "db", bd), patch.object(chat_messages, "entregar_a_utilizador", AsyncMock()):
        await chat_messages.run_send_message(
            ChatMessageCreate(group_id="g1", content="@ana podes ver isto?"), {"id": "u1", "name": "Rui", "role": "consultor"},
        )
    filas = {g["user_id"] for g in await bd.telegram_outbox.find({}).to_list(10)}
    assert filas == {"u2"}


# ════════════════════════════════════════════════════════════════════
# 11. TELEGRAM — NO MÁXIMO UMA MENSAGEM A CADA 15 MINUTOS POR PESSOA
# ════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_tudo_o_que_chega_sai_numa_so_mensagem(bd):
    await bd.processes.insert_many([_processo("p12"), _processo("p13")])
    await _ligar_telegram(bd, "u1")
    await tg.agendar("u1", "process_assigned", process_id="p12")
    await tg.agendar("u1", "process_assigned", process_id="p13")
    await tg.agendar("u1", "portal_message", process_id="p12")
    await tg.agendar("u1", "chat_message", conversa="direta:u9", remetente="Ana")
    assert await bd.telegram_outbox.count_documents({}) == 1
    await tg.enviar_pendentes()
    assert len(bd.enviadas) == 1
    texto = bd.enviadas[0]["texto"]
    assert "4 novidades" in texto
    assert "Processo atribuído a si — processo nº 12" in texto and "processo nº 13" in texto
    assert "Mensagem nova no chat de Ana" in texto
    assert bd.enviadas[0]["url"] == "https://app.exemplo.pt/"


@pytest.mark.asyncio
async def test_depois_de_uma_mensagem_a_seguinte_espera_15_minutos(bd):
    await bd.processes.insert_one(_processo("p12"))
    await _ligar_telegram(bd, "u1")
    await tg.agendar("u1", "process_assigned", process_id="p12")
    await tg.enviar_pendentes()
    assert len(bd.enviadas) == 1

    await tg.agendar("u1", "portal_message", process_id="p12")
    await tg.agendar("u1", "visit_request", process_id="p12")
    assert await tg.enviar_pendentes() == 0, "saiu outra mensagem antes dos 15 minutos"
    grupo = await bd.telegram_outbox.find_one({"status": "pendente"})
    ligacao = await bd.telegram_links.find_one({"user_id": "u1"})
    espera = grupo["enviar_apos"] - ligacao["ultimo_envio_em"]
    assert timedelta(minutes=14, seconds=59) <= espera <= timedelta(minutes=15, seconds=1)
    assert grupo["total"] == 2


@pytest.mark.asyncio
async def test_um_grupo_que_chega_a_hora_antes_do_intervalo_e_adiado(bd):
    await bd.processes.insert_one(_processo("p12"))
    await _ligar_telegram(bd, "u1", ultimo_envio_em=datetime.now(timezone.utc) - timedelta(minutes=5))
    await bd.telegram_outbox.insert_one({
        "id": "g1", "user_id": "u1", "chave": "pessoa", "status": "pendente", "total": 1,
        "eventos": [{"tipo": "process_assigned", "process_id": "p12"}],
        "enviar_apos": datetime.now(timezone.utc) - timedelta(seconds=1),
    })
    await tg.enviar_pendentes()
    assert bd.enviadas == []
    grupo = await bd.telegram_outbox.find_one({"id": "g1"})
    assert grupo["status"] == "pendente"
    assert grupo["enviar_apos"].replace(tzinfo=timezone.utc) > datetime.now(timezone.utc) + timedelta(minutes=9)


# ════════════════════════════════════════════════════════════════════
# 13. NA APP SÓ APITA O QUE IRIA PARA O TELEGRAM
# ════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_na_app_so_apita_o_importante(bd):
    await bd.processes.insert_many([_processo("p1"), _processo("p2")])
    estado = await rt.send_realtime_notification("u1", "Estado", "x", "process_status_change", process_id="p1")
    assert estado["alerta"] is False
    assert bd.push.await_count == 0, "um aviso sem importância fez push para o telemóvel"

    atribuido = await rt.send_realtime_notification("u1", "Atribuído", "x", "process_assigned", process_id="p2")
    assert atribuido["alerta"] is True
    assert bd.push.await_count == 1


@pytest.mark.asyncio
async def test_aviso_importante_que_se_junta_ao_grupo_apita_uma_vez(bd):
    await bd.processes.insert_one(_processo("p1"))
    await rt.send_realtime_notification("u1", "Estado", "x", "process_status_change", process_id="p1")
    junto = await rt.send_realtime_notification("u1", "Mensagem", "x", "portal_message", process_id="p1")
    assert junto["agrupada"] is True and junto["apitar"] is True
    outra = await rt.send_realtime_notification("u1", "Mensagem", "x", "portal_message", process_id="p1")
    assert outra["apitar"] is False
    assert await bd.notifications.count_documents({"user_id": "u1"}) == 1

"""Notificações na app: sem ruído, só dos processos da pessoa, e a rajada do mesmo processo num só aviso.

Provado contra um MongoDB REAL (`find_one_and_update` com `$push/$slice` e comparação de datas ISO).
"""
from __future__ import annotations

import os
import uuid
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from motor.motor_asyncio import AsyncIOMotorClient

from services import notification_policy, realtime_notifications as rt


@pytest_asyncio.fixture
async def bd(monkeypatch):
    url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    cliente = AsyncIOMotorClient(url, serverSelectionTimeoutMS=2000)
    try:
        await cliente.admin.command("ping")
    except Exception:
        cliente.close()
        pytest.skip("MongoDB não disponível")
    base = cliente[f"test_notif_app_{uuid.uuid4().hex[:8]}"]
    await base.processes.insert_many([
        {"id": "p1", "process_number": 1234, "client_name": "Rita", "assigned_consultor_ids": ["u1"]},
        {"id": "p2", "process_number": 99, "assigned_consultor_ids": ["outro"]},
    ])
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    rt._invalidate_pref_cache()
    entregas = AsyncMock()
    push = AsyncMock()
    with patch.object(rt, "db", base), patch.object(notification_policy, "db", base), \
            patch.object(rt, "entregar_a_utilizador", entregas), patch.object(rt, "send_push_notification", push), \
            patch("services.presenca.esta_online", AsyncMock(return_value=False)):
        yield base, entregas, push
    await cliente.drop_database(base.name)
    cliente.close()


async def _enviar(tipo, process_id="p1", title="Aviso", user_id="u1"):
    return await rt.send_realtime_notification(
        user_id=user_id, title=title, message=f"{title} (detalhe)", notification_type=tipo, process_id=process_id,
    )


@pytest.mark.asyncio
async def test_rajada_do_mesmo_processo_fica_num_so_aviso(bd):
    base, entregas, push = bd
    primeiro = await _enviar("process_assigned", title="Processo atribuído")
    await _enviar("process_status_change", title="Estado alterado")
    await _enviar("process_status_change", title="Estado alterado")
    await _enviar("document_upload", title="Documento novo")

    avisos = await base.notifications.find({"user_id": "u1"}).to_list(10)
    assert len(avisos) == 1
    aviso = avisos[0]
    assert aviso["id"] == primeiro["id"] and aviso["grupo_total"] == 4 and aviso["read"] is False
    assert aviso["message"].startswith("4 novidades no processo nº 1234")
    assert "Documento novo" in aviso["message"] and "Estado alterado" in aviso["message"]
    # só o primeiro faz push; os seguintes chegam ao sino como «agrupada»
    assert push.await_count == 1
    assert entregas.await_args_list[-1].args[2]["agrupada"] is True


@pytest.mark.asyncio
async def test_aviso_lido_abre_um_aviso_novo(bd):
    base, _, _ = bd
    await _enviar("process_assigned")
    await base.notifications.update_many({}, {"$set": {"read": True}})
    await _enviar("process_status_change")
    assert await base.notifications.count_documents({"user_id": "u1"}) == 2


@pytest.mark.asyncio
async def test_janela_fechada_abre_um_aviso_novo(bd):
    base, _, _ = bd
    await _enviar("process_assigned")
    await base.notifications.update_many({}, {"$set": {"agrupar_ate": "2000-01-01T00:00:00+00:00"}})
    await _enviar("process_status_change")
    assert await base.notifications.count_documents({"user_id": "u1"}) == 2


@pytest.mark.asyncio
async def test_processos_diferentes_nao_se_juntam(bd):
    base, _, _ = bd
    await base.processes.update_one({"id": "p2"}, {"$set": {"assigned_consultor_ids": ["u1"]}})
    await _enviar("process_assigned", process_id="p1")
    await _enviar("process_assigned", process_id="p2")
    assert await base.notifications.count_documents({"user_id": "u1"}) == 2


@pytest.mark.asyncio
async def test_aviso_de_processo_de_outra_pessoa_nao_chega(bd):
    base, entregas, _ = bd
    assert await _enviar("process_status_change", process_id="p2") is None
    assert await _enviar("document_upload", process_id="nao-existe") is None
    assert await base.notifications.count_documents({}) == 0
    entregas.assert_not_awaited()


@pytest.mark.asyncio
async def test_ruido_nao_chega(bd):
    base, _, _ = bd
    for tipo in ("process_updated", "index_sanitize_done", "document_auto_fetch"):
        assert await _enviar(tipo) is None
    assert await base.notifications.count_documents({}) == 0


@pytest.mark.asyncio
async def test_avisos_de_gestao_e_pessoais_continuam_a_chegar(bd):
    base, _, _ = bd
    # registo novo à gestão: ninguém está atribuído ao processo e o aviso tem de chegar
    assert await _enviar("new_registration", process_id="p2", user_id="admin") is not None
    # tarefa da pessoa num processo que não é dela
    assert await _enviar("task_assigned", process_id="p2") is not None
    # aviso sem processo
    assert await _enviar("info", process_id=None) is not None
    assert await base.notifications.count_documents({}) == 3

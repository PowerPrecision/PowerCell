"""«Atribuir a mim» do Index: puxar um processo por indexar que o colega ainda não abriu (Out 2026).

O Index passou a ver a rede inteira em «Todos os Processos» para trabalhar de forma proactiva. A
atribuição continua automática; o que se acrescenta é o indexador poder ASSUMIR um processo, com a
regra escolhida pela direcção: **só os «Por indexar»** (ninguém começou). O que já está «Em tratamento»
fica com quem o começou — a mesma lógica do SLA das 48 h, que também só mexe em processos intocados.

Afirma-se: assume um processo por indexar (de um colega ou sem ninguém); recusa em tratamento,
indexado, Via Verde ou já seu; é stealth (sem histórico, só auditoria); avisa o colega que o perde;
e uma corrida com o colega a começar entre a leitura e a escrita perde para quem trabalha.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from services import index_api as api
from tests.unit.test_index_api import INDEXADOR, PID, _Contexto

COLEGA = {"id": "u-colega", "name": "Rui Colega", "role": "indexacao"}


async def _processo(db, **campos):
    base = {"id": PID, "process_number": 12, "network_id": "r", "is_deleted": False, "is_indexed": False,
            "index_status": "pending", "assigned_indexacao_id": COLEGA["id"], "indexacao_name": COLEGA["name"]}
    base.update(campos)
    await db.processes.insert_one(base)


def _avisos():
    return patch("services.realtime_notifications.send_realtime_notification", AsyncMock(return_value=True))


@pytest.mark.asyncio
async def test_assume_um_processo_por_indexar_de_um_colega(fake_async_db):
    await _processo(fake_async_db)
    with _Contexto(fake_async_db), _avisos() as avisar:
        r = await api.run_assumir_processo(INDEXADOR, PID)
    doc = await fake_async_db.processes.find_one({"id": PID})
    assert r["success"] is True
    assert doc["assigned_indexacao_id"] == INDEXADOR["id"] and doc["indexacao_name"] == INDEXADOR["name"]
    assert doc["index_assigned_at"]  # o relógio das 48 h recomeça com o novo dono
    assert doc["index_status"] == "pending"  # assumir não é começar: começa ao abrir a bancada
    destinos = [c.args[0] for c in avisar.await_args_list]
    assert COLEGA["id"] in destinos


@pytest.mark.asyncio
async def test_assume_um_processo_sem_indexador(fake_async_db):
    await _processo(fake_async_db, assigned_indexacao_id=None, indexacao_name=None)
    with _Contexto(fake_async_db), _avisos():
        await api.run_assumir_processo(INDEXADOR, PID)
    assert (await fake_async_db.processes.find_one({"id": PID}))["assigned_indexacao_id"] == INDEXADOR["id"]


@pytest.mark.asyncio
@pytest.mark.parametrize("campos", [
    {"index_status": "in_review"},
    {"is_indexed": True, "index_status": "indexed"},
    {"skip_index": True},
])
async def test_recusa_o_que_nao_esta_por_indexar(fake_async_db, campos):
    await _processo(fake_async_db, **campos)
    with _Contexto(fake_async_db), _avisos(), pytest.raises(HTTPException) as erro:
        await api.run_assumir_processo(INDEXADOR, PID)
    assert erro.value.status_code == 409
    assert (await fake_async_db.processes.find_one({"id": PID}))["assigned_indexacao_id"] == COLEGA["id"]


@pytest.mark.asyncio
async def test_o_que_ja_e_seu_e_400(fake_async_db):
    await _processo(fake_async_db, assigned_indexacao_id=INDEXADOR["id"])
    with _Contexto(fake_async_db), _avisos(), pytest.raises(HTTPException) as erro:
        await api.run_assumir_processo(INDEXADOR, PID)
    assert erro.value.status_code == 400


@pytest.mark.asyncio
async def test_e_stealth_sem_historico_so_auditoria(fake_async_db):
    await _processo(fake_async_db)
    with _Contexto(fake_async_db), _avisos():
        await api.run_assumir_processo(INDEXADOR, PID)
    assert await fake_async_db.history.count_documents({}) == 0
    assert await fake_async_db.audit_trail.count_documents({"process_id": PID}) == 1


@pytest.mark.asyncio
async def test_corrida_o_colega_comecou_entre_a_leitura_e_a_escrita(fake_async_db):
    """A escrita é condicional ao estado lido: se o colega abriu a bancada entretanto, ninguém lho tira."""
    await _processo(fake_async_db)
    original = api._carregar_processo

    async def ler_e_o_colega_comeca(process_id, user):
        proc = await original(process_id, user)
        await fake_async_db.processes.update_one({"id": PID}, {"$set": {"index_status": "in_review"}})
        return proc

    with _Contexto(fake_async_db), _avisos(), patch.object(api, "_carregar_processo", ler_e_o_colega_comeca), \
            pytest.raises(HTTPException) as erro:
        await api.run_assumir_processo(INDEXADOR, PID)
    assert erro.value.status_code == 409
    assert (await fake_async_db.processes.find_one({"id": PID}))["assigned_indexacao_id"] == COLEGA["id"]


def test_a_rota_so_aceita_o_perfil_index():
    """A gestão atribui pelo «Gerir»; o «Atribuir a mim» é do indexador (perfil EFECTIVO)."""
    from routes import index_module

    rota = next(r for r in index_module.router.routes if r.path.endswith("/processes/{process_id}/assumir"))
    assert "POST" in rota.methods
    assert index_module.PAPEIS_QUE_ASSUMEM == ["indexacao"]


@pytest.mark.asyncio
async def test_a_gestao_leva_403_e_o_index_passa():
    from unittest.mock import MagicMock

    from routes import index_module

    pedido = MagicMock()
    with patch("services.auth.get_effective_role_async", AsyncMock(return_value="diretor")), \
            pytest.raises(HTTPException) as erro:
        await index_module._so_o_index(pedido, {"id": "u-dir", "role": "diretor"})
    assert erro.value.status_code == 403
    with patch("services.auth.get_effective_role_async", AsyncMock(return_value="indexacao")):
        assert await index_module._so_o_index(pedido, dict(INDEXADOR))

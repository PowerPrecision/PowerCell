"""Pedido de alteração de atribuição do Index (Out 2026).

O Index não muda atribuições; passa a poder PEDIR à chefia, com um motivo opcional. Afirma-se: o pedido
grava-se com o motivo (ou sem ele), é stealth (sem histórico, só auditoria), avisa só a chefia da rede do
processo, não aceita um segundo pedido pendente, e a lista e a resolução respeitam a rede (um pedido de
outra rede é 404). A rota de pedir é só do Index e a de resolver só da chefia.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from services import audit_trail_service as audit
from services import index_assignment_requests as pedidos
from services.tenant_network import TenantScope
from tests.unit.test_index_api import GESTOR, INDEXADOR, PID

OUTRO_PID = "proc-2"


class _Contexto:
    def __init__(self, fake_db, chefia=("u-dir",), redes=("r",)):
        self.patches = [
            patch.object(pedidos, "db", fake_db),
            patch.object(audit, "db", fake_db),
            patch("database.db", fake_db),
            patch("services.alert_audience.gestao_da_rede_do_processo", AsyncMock(return_value=list(chefia))),
            patch("services.tenant_network.resolve_vista_scope",
                  AsyncMock(return_value=TenantScope(network_ids=tuple(redes)))),
        ]
        self.avisar = AsyncMock(return_value=True)
        self.patches.append(patch("services.realtime_notifications.send_realtime_notification", self.avisar))

    def __enter__(self):
        for p in self.patches:
            p.start()
        return self

    def __exit__(self, *a):
        for p in reversed(self.patches):
            p.stop()


async def _processos(db):
    await db.processes.insert_one({"id": PID, "process_number": 12, "client_name": "Ana", "network_id": "r",
                                   "is_deleted": False, "assigned_indexacao_id": "u-colega"})
    await db.processes.insert_one({"id": OUTRO_PID, "process_number": 13, "network_id": "outra-rede",
                                   "is_deleted": False})


@pytest.mark.asyncio
async def test_pede_com_motivo_e_avisa_a_chefia_da_rede(fake_async_db):
    await _processos(fake_async_db)
    with _Contexto(fake_async_db) as ctx:
        r = await pedidos.run_pedir_alteracao(INDEXADOR, PID, "  O cliente é de outro balcão  ")
    doc = await fake_async_db.index_assignment_requests.find_one({"process_id": PID})
    assert r["success"] is True
    assert doc["estado"] == "pendente" and doc["motivo"] == "O cliente é de outro balcão"
    assert doc["requested_by"] == INDEXADOR["id"] and doc["network_id"] == "r"
    destinos = [c.args[0] for c in ctx.avisar.await_args_list]
    assert destinos == ["u-dir"]
    assert "O cliente é de outro balcão" in ctx.avisar.await_args_list[0].args[2]


@pytest.mark.asyncio
async def test_o_motivo_e_opcional(fake_async_db):
    await _processos(fake_async_db)
    with _Contexto(fake_async_db):
        await pedidos.run_pedir_alteracao(INDEXADOR, PID, "   ")
    assert (await fake_async_db.index_assignment_requests.find_one({"process_id": PID}))["motivo"] is None


@pytest.mark.asyncio
async def test_e_stealth_sem_historico_so_auditoria(fake_async_db):
    await _processos(fake_async_db)
    with _Contexto(fake_async_db):
        await pedidos.run_pedir_alteracao(INDEXADOR, PID, None)
    assert await fake_async_db.history.count_documents({}) == 0
    assert await fake_async_db.audit_trail.count_documents({"process_id": PID}) == 1
    # o pedido não mexe na atribuição
    assert (await fake_async_db.processes.find_one({"id": PID}))["assigned_indexacao_id"] == "u-colega"


@pytest.mark.asyncio
async def test_segundo_pedido_pendente_e_409(fake_async_db):
    await _processos(fake_async_db)
    with _Contexto(fake_async_db):
        await pedidos.run_pedir_alteracao(INDEXADOR, PID, None)
        with pytest.raises(HTTPException) as erro:
            await pedidos.run_pedir_alteracao(INDEXADOR, PID, "outra vez")
    assert erro.value.status_code == 409
    assert await fake_async_db.index_assignment_requests.count_documents({}) == 1


@pytest.mark.asyncio
async def test_processo_inexistente_e_404(fake_async_db):
    with _Contexto(fake_async_db), pytest.raises(HTTPException) as erro:
        await pedidos.run_pedir_alteracao(INDEXADOR, "nao-existe", None)
    assert erro.value.status_code == 404


@pytest.mark.asyncio
async def test_a_lista_respeita_a_rede_e_o_index_so_ve_os_seus(fake_async_db):
    await _processos(fake_async_db)
    with _Contexto(fake_async_db):
        await pedidos.run_pedir_alteracao(INDEXADOR, PID, None)
        await pedidos.run_pedir_alteracao({"id": "u-colega", "name": "Rui"}, PID, None)
        await pedidos.run_pedir_alteracao(INDEXADOR, OUTRO_PID, None)  # processo de outra rede
        da_chefia = await pedidos.run_listar_pedidos(GESTOR, so_meus=False)
        do_index = await pedidos.run_listar_pedidos(INDEXADOR, so_meus=True)
    assert {(p["process_id"], p["requested_by"]) for p in da_chefia["itens"]} == {
        (PID, INDEXADOR["id"]), (PID, "u-colega")}
    assert [(p["process_id"], p["requested_by"]) for p in do_index["itens"]] == [(PID, INDEXADOR["id"])]


@pytest.mark.asyncio
async def test_a_chefia_conclui_e_o_index_e_avisado(fake_async_db):
    await _processos(fake_async_db)
    with _Contexto(fake_async_db) as ctx:
        pid = (await pedidos.run_pedir_alteracao(INDEXADOR, PID, None))["pedido"]["id"]
        ctx.avisar.reset_mock()
        await pedidos.run_resolver_pedido(GESTOR, pid, "concluido", "Passei ao Rui")
        with pytest.raises(HTTPException) as erro:
            await pedidos.run_resolver_pedido(GESTOR, pid, "recusado")
        # depois de tratado pode pedir de novo
        await pedidos.run_pedir_alteracao(INDEXADOR, PID, None)
    doc = await fake_async_db.index_assignment_requests.find_one({"id": pid})
    assert doc["estado"] == "concluido" and doc["resolved_by"] == GESTOR["id"]
    assert doc["nota_da_resolucao"] == "Passei ao Rui"
    assert erro.value.status_code == 409
    assert ctx.avisar.await_args_list[0].args[0] == INDEXADOR["id"]


@pytest.mark.asyncio
async def test_resolver_um_pedido_de_outra_rede_e_404(fake_async_db):
    await _processos(fake_async_db)
    with _Contexto(fake_async_db, redes=("outra-rede",)):
        pid = (await pedidos.run_pedir_alteracao(INDEXADOR, OUTRO_PID, None))["pedido"]["id"]
    with _Contexto(fake_async_db, redes=("r",)), pytest.raises(HTTPException) as erro:
        await pedidos.run_resolver_pedido(GESTOR, pid, "recusado")
    assert erro.value.status_code == 404
    assert (await fake_async_db.index_assignment_requests.find_one({"id": pid}))["estado"] == "pendente"


def test_as_rotas_e_os_papeis():
    from routes import index_module

    caminhos = {r.path: r.methods for r in index_module.router.routes}
    assert "POST" in caminhos["/index/processes/{process_id}/pedido-atribuicao"]
    assert "GET" in caminhos["/index/pedidos-atribuicao"]
    assert "POST" in caminhos["/index/pedidos-atribuicao/{pedido_id}/resolver"]
    assert "indexacao" not in index_module.PAPEIS_QUE_TRATAM_PEDIDOS


@pytest.mark.asyncio
async def test_o_index_nao_resolve_pedidos():
    from routes import index_module

    with patch("services.auth.get_effective_role_async", AsyncMock(return_value="indexacao")), \
            pytest.raises(HTTPException) as erro:
        await index_module._so_a_chefia(MagicMock(), dict(INDEXADOR))
    assert erro.value.status_code == 403

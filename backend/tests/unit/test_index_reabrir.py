"""«Reabrir» um processo já indexado (Nov 2026).

O pedido do Flavio: «posso ter terminado um processo hoje mas daqui a 2 meses pedem-me para analisar os
recibos e extratos desses 2 meses». O Index tem de VER o que já indexou e, se for preciso, reabri-lo.

Afirma-se:
* o Index reabre para si (atribuído e «Em tratamento»), a gestão devolve-o à fila (sem dono);
* o limite de 15 processos activos do indexador vale também aqui (409);
* só se reabre o que está indexado; dois a reabrir ao mesmo tempo não se pisam (409);
* stealth: o Index não deixa histórico, mas a reabertura fica SEMPRE no `audit_trail` (com o motivo);
* a fase do workflow não muda — nem ao reabrir, nem ao voltar a marcar como indexado (sem 2.º salto
  e sem voltar a correr a automação da fase);
* «Indexados»: a aba mostra o que uma pessoa indexou (incluindo processos fechados) e, em «Os Meus»,
  conta quem o indexou (ao indexar o processo fica sem Index).
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from services import history as historico
from services import index_api as api
from services import index_queue_query as consulta
from services import index_status as ist
from services import process_assignment as atribuicao
from services import process_indexing as pi
from tests.unit.test_index_api import INDEXADOR, PID, _Contexto

ADMIN = {"id": "u-adm", "name": "Alda Admin", "role": "admin"}


async def _indexado(db, **campos):
    base = {
        "id": PID, "process_number": 12, "network_id": "r", "status": "aprovacao", "client_name": "Rita",
        "is_deleted": False, "is_indexed": True, "index_status": "indexed", "index_skipped": False,
        "assigned_indexacao_id": None, "indexacao_name": None,
        "indexed_at": "2026-09-01T10:00:00+00:00", "indexed_by": INDEXADOR["id"], "indexed_by_name": INDEXADOR["name"],
    }
    base.update(campos)
    await db.processes.insert_one(base)


class _Mais(_Contexto):
    """Os módulos que o «Reabrir» toca além dos da bancada."""

    def __init__(self, fake_db):
        super().__init__(fake_db)
        self.patches += [patch.object(m, "db", fake_db) for m in (historico, atribuicao, pi)]


async def _reabrir(db, user, papel, **kw):
    with _Mais(db):
        return await api.run_reabrir_processo(user, PID, papel=papel, all_roles=[papel], **kw)


# ====================================================================
# QUEM REABRE E PARA ONDE VAI
# ====================================================================
@pytest.mark.asyncio
async def test_o_index_reabre_para_si_e_fica_em_tratamento(fake_async_db):
    await _indexado(fake_async_db)
    r = await _reabrir(fake_async_db, INDEXADOR, "indexacao", motivo="O banco pediu os recibos de out e nov")
    doc = await fake_async_db.processes.find_one({"id": PID})
    assert r["success"] is True and r["index_status"] == "in_review"
    assert doc["is_indexed"] is False and doc["index_status"] == "in_review"
    assert doc["assigned_indexacao_id"] == INDEXADOR["id"] and doc["indexacao_name"] == INDEXADOR["name"]
    assert doc["index_reaberto"] is True and doc["index_reopen_count"] == 1
    assert doc["index_reopen_reason"] == "O banco pediu os recibos de out e nov"
    assert doc["status"] == "aprovacao"  # a fase do workflow não muda


@pytest.mark.asyncio
async def test_a_gestao_reabre_para_a_fila(fake_async_db):
    await _indexado(fake_async_db)
    with patch.object(atribuicao, "assign_to_indexer", AsyncMock(return_value=(False, {}, ""))) as auto:
        r = await _reabrir(fake_async_db, ADMIN, "admin")
    doc = await fake_async_db.processes.find_one({"id": PID})
    assert r["index_status"] == "pending"
    assert doc["is_indexed"] is False and doc["assigned_indexacao_id"] is None
    auto.assert_awaited_once()  # a atribuição automática escolhe o indexador (menor carga, limite 15)
    assert auto.await_args.kwargs.get("update_status") is False  # sem mexer na fase


@pytest.mark.asyncio
@pytest.mark.parametrize("papel", ["consultor", "intermediario", "diretor"])
async def test_quem_nao_pode_marcar_tambem_nao_reabre(fake_async_db, papel):
    await _indexado(fake_async_db)
    with pytest.raises(HTTPException) as e:
        await _reabrir(fake_async_db, {"id": "u-x", "name": "X", "role": papel}, papel)
    assert e.value.status_code == 403
    assert (await fake_async_db.processes.find_one({"id": PID}))["is_indexed"] is True


@pytest.mark.asyncio
async def test_so_se_reabre_o_que_esta_indexado(fake_async_db):
    await _indexado(fake_async_db, is_indexed=False, index_status="pending")
    with pytest.raises(HTTPException) as e:
        await _reabrir(fake_async_db, INDEXADOR, "indexacao")
    assert e.value.status_code == 409


@pytest.mark.asyncio
async def test_o_limite_de_15_activos_vale_ao_reabrir(fake_async_db):
    await _indexado(fake_async_db)
    with patch.object(atribuicao, "_count_active_processes_for_indexer", AsyncMock(return_value=15)):
        with pytest.raises(HTTPException) as e:
            await _reabrir(fake_async_db, INDEXADOR, "indexacao")
    assert e.value.status_code == 409 and "15" in e.value.detail
    assert (await fake_async_db.processes.find_one({"id": PID}))["is_indexed"] is True


@pytest.mark.asyncio
async def test_corrida_dois_a_reabrir_o_segundo_leva_409(fake_async_db):
    await _indexado(fake_async_db)
    original = ist.reabrir

    async def outro_reabriu_antes(process_id, *a, **kw):
        await fake_async_db.processes.update_one({"id": process_id}, {"$set": {"is_indexed": False}})
        return await original(process_id, *a, **kw)

    with patch.object(ist, "reabrir", outro_reabriu_antes):
        with pytest.raises(HTTPException) as e:
            await _reabrir(fake_async_db, INDEXADOR, "indexacao")
    assert e.value.status_code == 409


# ====================================================================
# O RASTO
# ====================================================================
@pytest.mark.asyncio
async def test_o_index_e_invisivel_no_historico_mas_fica_no_audit_trail(fake_async_db):
    await _indexado(fake_async_db)
    await _reabrir(fake_async_db, INDEXADOR, "indexacao", motivo="extratos de 2 meses")
    assert await fake_async_db.history.count_documents({"process_id": PID}) == 0
    (registo,) = await fake_async_db.audit_trail.find({"process_id": PID}).to_list(10)
    assert registo["action"] == "Indexação reaberta"
    assert "extratos de 2 meses" in str(registo)


@pytest.mark.asyncio
async def test_a_gestao_fica_no_historico_e_no_audit_trail(fake_async_db):
    await _indexado(fake_async_db)
    with patch.object(atribuicao, "assign_to_indexer", AsyncMock(return_value=(False, {}, ""))):
        await _reabrir(fake_async_db, ADMIN, "admin")
    assert await fake_async_db.history.count_documents({"process_id": PID}) == 1
    assert await fake_async_db.audit_trail.count_documents({"process_id": PID}) == 1


# ====================================================================
# VOLTAR A MARCAR COMO INDEXADO: SEM 2.º SALTO DE FASE
# ====================================================================
@pytest.mark.asyncio
async def test_voltar_a_marcar_nao_salta_a_fase_e_limpa_a_bandeira(fake_async_db):
    await _indexado(fake_async_db)
    await _reabrir(fake_async_db, INDEXADOR, "indexacao")
    efeitos = AsyncMock(return_value={"success": True})
    with _Mais(fake_async_db), \
            patch.object(pi, "load_workflow_status_pipeline", AsyncMock(return_value=["novo", "aprovacao", "escritura"])), \
            patch.object(pi, "run_mark_indexed_side_effects", efeitos):
        await pi.run_mark_process_indexed(
            PID, INDEXADOR, user_role="indexacao", all_roles=["indexacao"], broadcast_fn=AsyncMock())
    doc = await fake_async_db.processes.find_one({"id": PID})
    assert doc["is_indexed"] is True and doc["status"] == "aprovacao"
    assert doc["index_reaberto"] is False
    assert efeitos.await_args.kwargs["reabertura"] is True
    assert efeitos.await_args.kwargs["next_status"] is None


@pytest.mark.asyncio
async def test_sem_reabertura_o_salto_de_fase_continua_igual(fake_async_db):
    await fake_async_db.processes.insert_one({"id": PID, "status": "novo", "is_deleted": False, "is_indexed": False})
    efeitos = AsyncMock(return_value={"success": True})
    with _Mais(fake_async_db), \
            patch.object(pi, "load_workflow_status_pipeline", AsyncMock(return_value=["novo", "aprovacao"])), \
            patch.object(pi, "run_mark_indexed_side_effects", efeitos):
        await pi.run_mark_process_indexed(
            PID, INDEXADOR, user_role="indexacao", all_roles=["indexacao"], broadcast_fn=AsyncMock())
    assert (await fake_async_db.processes.find_one({"id": PID}))["status"] == "aprovacao"
    assert efeitos.await_args.kwargs["reabertura"] is False


@pytest.mark.asyncio
async def test_na_reabertura_a_automacao_da_fase_nao_volta_a_correr():
    nomes = ("log_mark_indexed_history", "notify_assigned_users_indexing_complete", "trigger_indexer_waitlist",
             "broadcast_assignment_delta", "libertar_index_sem_falhar", "trigger_financial_engine_safe",
             "agendar_finalizacao_sem_falhar", "auto_assign_after_indexacao")
    mocks = {n: AsyncMock(return_value=(None, False) if n == "auto_assign_after_indexacao" else {}) for n in nomes}
    patches = [patch.object(pi, n, m) for n, m in mocks.items()]
    for p in patches:
        p.start()
    try:
        await pi.run_mark_indexed_side_effects(
            process={"id": PID, "status": "aprovacao"}, process_id=PID, user=INDEXADOR,
            current_status="aprovacao", next_status=None, now="2026-11-04T00:00:00+00:00",
            broadcast_fn=AsyncMock(), reabertura=True,
        )
    finally:
        for p in reversed(patches):
            p.stop()
    mocks["auto_assign_after_indexacao"].assert_not_awaited()
    mocks["libertar_index_sem_falhar"].assert_awaited_once()  # os ficheiros novos saem da pasta Index


def test_o_interruptor_desligar_tambem_marca_a_reabertura():
    s = pi.build_unindex_update_set({"id": "u1", "name": "Zé"}, "2026-11-04T00:00:00+00:00", {"is_indexed": True})
    assert s["index_reaberto"] is True and "status" not in s


# ====================================================================
# A ABA «INDEXADOS»
# ====================================================================
def test_a_aba_indexados_e_o_que_uma_pessoa_indexou():
    assert ist.condicao_da_fila("indexed") == {"is_indexed": True}


def test_a_aba_indexados_ordena_pela_data_de_indexacao():
    assert consulta.validar_ordenacao("indexed", None)[0] == "indexed_at"
    assert consulta.validar_ordenacao("indexed", "indexed_asc")[1] == 1
    with pytest.raises(HTTPException):
        consulta.validar_ordenacao("pending", "indexed_desc")


@pytest.mark.asyncio
async def test_os_meus_indexados_contam_quem_indexou(fake_async_db):
    from services.tenant_network import TenantScope

    await _indexado(fake_async_db, id="meu", indexed_by=INDEXADOR["id"], status="concluido")
    await _indexado(fake_async_db, id="do-outro", indexed_by="u-outro")
    await _indexado(fake_async_db, id="dispensado", is_indexed=False, skip_index=True, indexed_by=None)
    with _Mais(fake_async_db), \
            patch("services.tenant_network.resolve_vista_scope", AsyncMock(return_value=TenantScope(network_ids=("r",)))), \
            patch.object(api, "condicao_de_processo_activo", AsyncMock(return_value={"id": {"$in": []}})):
        r = await api.run_get_index_queue(INDEXADOR, tab="indexed", mine=True)
        todos = await api.run_get_index_queue(INDEXADOR, tab="indexed")
    assert {p["id"] for p in r["items"]} == {"meu"}  # fechado no workflow, mas aparece (é para ver)
    assert {p["id"] for p in todos["items"]} == {"meu", "do-outro"}

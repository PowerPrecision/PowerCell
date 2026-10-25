"""Sem acções cruzadas entre indexadores (Out 2026, decisão do cliente).

O Index vê a rede inteira em «Todos os Processos», mas só AGE nos processos que são seus. Num processo
atribuído a outro indexador, o perfil `indexacao` não pode analisar, extrair dados, limpar PDFs, editar
os metadados, dispensar alertas, nem marcar (ou desmarcar) como indexado: tem de o assumir primeiro
(«Atribuir a mim»). Um processo sem indexador fica livre, e a gestão continua a poder agir em qualquer um.

Afirma-se: a regra pura; a dependência que a aplica a cada rota de escrita da bancada; e o fluxo canónico
do «marcar como indexado» (bancada, CRM e interruptor do detalhe) recusa ANTES de escrever o que quer que
seja — incluindo os NIFs confirmados na bancada.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from routes import index_module
from services import index_api as api
from services import index_finalize as fin
from services import index_status as ist
from services import process_indexing as pi
from tests.unit.test_index_api import GESTOR, INDEXADOR, PID, _Contexto

COLEGA = {"id": "u-colega", "name": "Rui Colega", "role": "indexacao"}


async def _processo(db, **campos):
    base = {"id": PID, "process_number": 12, "network_id": "r", "is_deleted": False, "is_indexed": False,
            "index_status": "in_review", "assigned_indexacao_id": COLEGA["id"], "status": "fase1"}
    base.update(campos)
    await db.processes.insert_one(base)


# ====================================================================
# 1. A regra
# ====================================================================
@pytest.mark.parametrize("dono, papel, recusa", [
    (COLEGA["id"], "indexacao", True),     # o processo é de um colega
    (INDEXADOR["id"], "indexacao", False),  # é meu
    (None, "indexacao", False),             # ninguém o tem
    ("", "indexacao", False),
    (COLEGA["id"], "diretor", False),       # a gestão age em qualquer um
    (COLEGA["id"], "ceo", False),
    (COLEGA["id"], "INDEXACAO", True),      # o papel chega em qualquer caixa
])
def test_a_regra(dono, papel, recusa):
    proc = {"id": PID, "assigned_indexacao_id": dono}
    if recusa:
        with pytest.raises(HTTPException) as erro:
            ist.exigir_titularidade(proc, INDEXADOR, papel)
        assert erro.value.status_code == 403
        assert "Atribuir a mim" in erro.value.detail
    else:
        ist.exigir_titularidade(proc, INDEXADOR, papel)


@pytest.mark.asyncio
async def test_o_servico_le_o_dono_na_base_de_dados(fake_async_db):
    await _processo(fake_async_db)
    with _Contexto(fake_async_db), pytest.raises(HTTPException) as erro:
        await api.run_exigir_titularidade(INDEXADOR, PID, "indexacao")
    assert erro.value.status_code == 403
    with _Contexto(fake_async_db):
        await api.run_exigir_titularidade(GESTOR, PID, "diretor")
        await fake_async_db.processes.update_one({"id": PID}, {"$set": {"assigned_indexacao_id": INDEXADOR["id"]}})
        await api.run_exigir_titularidade(INDEXADOR, PID, "indexacao")


# ====================================================================
# 2. As rotas de escrita da bancada
# ====================================================================
ROTAS_DE_ESCRITA = [
    ("POST", "/processes/{process_id}/analyze"),
    ("POST", "/processes/{process_id}/extract"),
    ("POST", "/processes/{process_id}/sanitize"),
    ("PATCH", "/processes/{process_id}/professional-metadata/{job_id}"),
    ("POST", "/processes/{process_id}/alerts/{alert_id}/dismiss"),
    ("POST", "/processes/{process_id}/mark-indexed"),
]


def _dependencias(dependant):
    for d in dependant.dependencies:
        yield d.call
        yield from _dependencias(d)


@pytest.mark.parametrize("metodo, caminho", ROTAS_DE_ESCRITA)
def test_cada_rota_de_escrita_exige_a_titularidade(metodo, caminho):
    rota = next(r for r in index_module.router.routes
                if r.path == "/index" + caminho and metodo in r.methods)
    assert index_module._so_o_titular in set(_dependencias(rota.dependant))


@pytest.mark.parametrize("caminho", ["/processes/{process_id}/assumir", "/processes/{process_id}/start",
                                     "/processes/{process_id}"])
def test_ler_comecar_e_assumir_nao_exigem_a_titularidade(caminho):
    """Assumir é precisamente o caminho para ganhar a titularidade; ler a bancada é livre."""
    for rota in (r for r in index_module.router.routes if r.path == "/index" + caminho):
        assert index_module._so_o_titular not in set(_dependencias(rota.dependant))


@pytest.mark.asyncio
async def test_a_dependencia_usa_o_perfil_efectivo():
    pedido = MagicMock()
    with patch.object(index_module, "get_effective_role_async", AsyncMock(return_value="indexacao")), \
            patch.object(index_module, "run_exigir_titularidade", AsyncMock()) as exigir:
        await index_module._so_o_titular(pedido, PID, dict(INDEXADOR))
    exigir.assert_awaited_once_with(INDEXADOR, PID, "indexacao")


# ====================================================================
# 3. Marcar / desmarcar como indexado (o fluxo canónico)
# ====================================================================
@pytest.mark.asyncio
async def test_marcar_como_indexado_o_processo_de_um_colega_e_403_e_nada_muda(fake_async_db):
    await _processo(fake_async_db)
    with patch.object(pi, "db", fake_async_db), pytest.raises(HTTPException) as erro:
        await pi.run_mark_process_indexed(PID, INDEXADOR, user_role="indexacao", all_roles=[],
                                          broadcast_fn=AsyncMock())
    assert erro.value.status_code == 403
    doc = await fake_async_db.processes.find_one({"id": PID})
    assert doc["is_indexed"] is False and doc["status"] == "fase1"


@pytest.mark.asyncio
async def test_desligar_o_interruptor_no_processo_de_um_colega_e_403(fake_async_db):
    await _processo(fake_async_db, is_indexed=True, index_status="indexed")
    with patch.object(pi, "db", fake_async_db), pytest.raises(HTTPException) as erro:
        await pi.run_set_process_indexed_flag(PID, INDEXADOR, is_indexed=False, user_role="indexacao",
                                              all_roles=[], broadcast_fn=AsyncMock())
    assert erro.value.status_code == 403
    assert (await fake_async_db.processes.find_one({"id": PID}))["is_indexed"] is True


@pytest.mark.asyncio
async def test_a_gestao_continua_a_poder_desligar(fake_async_db):
    await _processo(fake_async_db, is_indexed=True, index_status="indexed")
    with patch.object(pi, "db", fake_async_db), patch("services.history.log_history", AsyncMock()):
        r = await pi.run_set_process_indexed_flag(PID, GESTOR, is_indexed=False, user_role="admin",
                                                  all_roles=[], broadcast_fn=AsyncMock())
    assert r["is_indexed"] is False


@pytest.mark.asyncio
async def test_na_bancada_os_nifs_nao_se_gravam_antes_da_recusa(fake_async_db):
    await _processo(fake_async_db)
    with patch.object(pi, "db", fake_async_db), patch.object(fin, "db", fake_async_db), \
            patch.object(fin, "aplicar_nifs_confirmados", AsyncMock()) as nifs, \
            pytest.raises(HTTPException) as erro:
        await fin.run_mark_indexed(PID, INDEXADOR, user_role="indexacao", all_roles=[],
                                   broadcast_fn=AsyncMock(), employers=[{"job_id": "j", "nif": "501964843"}])
    assert erro.value.status_code == 403
    nifs.assert_not_awaited()


# ====================================================================
# 4. A bancada diz ao ecrã de quem é o processo
# ====================================================================
@pytest.mark.asyncio
async def test_a_bancada_diz_se_o_processo_e_de_outro_indexador_e_de_quem(fake_async_db):
    await _processo(fake_async_db, indexacao_name=COLEGA["name"])
    with _Contexto(fake_async_db):
        alheio = await api.run_get_index_workstation(INDEXADOR, PID)
        do_dono = await api.run_get_index_workstation(COLEGA, PID)
    assert alheio["process"]["assigned_to_other"] is True
    assert alheio["process"]["assigned_indexacao_name"] == COLEGA["name"]
    assert do_dono["process"]["assigned_to_other"] is False


@pytest.mark.asyncio
async def test_um_processo_sem_indexador_nao_e_de_outro(fake_async_db):
    await _processo(fake_async_db, assigned_indexacao_id=None)
    with _Contexto(fake_async_db):
        r = await api.run_get_index_workstation(INDEXADOR, PID)
    assert r["process"]["assigned_to_other"] is False

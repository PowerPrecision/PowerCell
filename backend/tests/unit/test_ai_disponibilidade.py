"""IA sem créditos → a bancada do Index bloqueia «Analisar»/«Extrair dados» até a IA voltar (Nov 2026)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from services import ai_disponibilidade as disp
from services import index_api


@pytest.fixture(autouse=True)
def _limpo():
    disp._marcado_localmente = None
    disp._sonda_em_curso = None
    yield
    disp._marcado_localmente = None


@pytest.mark.asyncio
async def test_sem_registo_a_ia_esta_disponivel(fake_async_db):
    assert (await disp.estado_da_ia(fake_async_db))["disponivel"] is True


@pytest.mark.asyncio
async def test_sem_creditos_bloqueia_e_uma_resposta_boa_desbloqueia(fake_async_db):
    with patch.object(disp, "db", fake_async_db):
        await disp.registar_sem_creditos()
        estado = await disp.estado_da_ia(fake_async_db)
        assert estado["disponivel"] is False and estado["motivo"] == "sem_creditos"
        assert "créditos" in estado["mensagem"]
        await disp._limpar()
        assert (await disp.estado_da_ia(fake_async_db))["disponivel"] is True


@pytest.mark.asyncio
async def test_bloqueado_ha_muito_faz_uma_sonda_e_nao_mais(fake_async_db):
    antigo = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
    await fake_async_db.system_flags.insert_one({"id": disp.ID_DO_ESTADO, "sem_creditos": True, "verificado_em": antigo})
    sonda = AsyncMock()
    with patch.object(disp, "_sondar", sonda):
        await disp.estado_da_ia(fake_async_db)
        await disp.estado_da_ia(fake_async_db)  # a primeira ainda não acabou → não lança outra
        await disp._sonda_em_curso
    assert sonda.await_count == 1


@pytest.mark.asyncio
async def test_acabado_de_verificar_nao_sonda(fake_async_db):
    agora = datetime.now(timezone.utc).isoformat()
    await fake_async_db.system_flags.insert_one({"id": disp.ID_DO_ESTADO, "sem_creditos": True, "verificado_em": agora})
    sonda = AsyncMock()
    with patch.object(disp, "_sondar", sonda):
        await disp.estado_da_ia(fake_async_db)
    assert disp._sonda_em_curso is None and sonda.await_count == 0


@pytest.mark.asyncio
async def test_o_servidor_recusa_analisar_sem_ia(fake_async_db):
    agora = datetime.now(timezone.utc).isoformat()
    await fake_async_db.system_flags.insert_one({"id": disp.ID_DO_ESTADO, "sem_creditos": True, "verificado_em": agora})
    iniciar = AsyncMock()
    with patch.object(index_api, "db", fake_async_db), \
         patch.object(index_api, "_carregar_processo", AsyncMock(return_value={"id": "p"})), \
         patch.object(index_api.index_jobs, "iniciar_analise", iniciar):
        with pytest.raises(HTTPException) as erro:
            await index_api.run_analyze_process({"id": "u"}, "p", force=True)
    assert erro.value.status_code == 503 and iniciar.await_count == 0


# ====================================================================
# «Eliminar» na bancada do Index (soft delete, Nov 2026) — no mesmo ficheiro por partilhar o arranque
# ====================================================================
class _S3:
    def __init__(self, existe=True, renomeia=True):
        self.existe, self.renomeia, self.renomeados = existe, renomeia, []

    def is_configured(self):
        return True

    def file_exists(self, caminho):
        return self.existe

    def rename_file(self, origem, destino):
        self.renomeados.append((origem, destino))
        return self.renomeia


PASTA = "Documentação Clientes/cli-1/processos/p"
PROC = {"id": "p", "client_name": "Ana", "s3_folder": PASTA, "network_id": "r1"}


async def _eliminar(fake_async_db, s3, documento="d1"):
    from services import s3_storage

    with patch.object(index_api, "db", fake_async_db), \
         patch.object(index_api, "_carregar_processo", AsyncMock(return_value=PROC)), \
         patch.object(s3_storage, "s3_service", s3), \
         patch("services.document_portal_revoke.revoke_portal_files_on_delete", AsyncMock()), \
         patch("services.history.log_history", AsyncMock()), \
         patch.object(index_api.index_jobs, "concluir_resultados", AsyncMock()) as concluir, \
         patch.object(index_api, "_trabalhou", AsyncMock()):
        r = await index_api.run_delete_document({"id": "u"}, "p", documento)
    return r, concluir


@pytest.mark.asyncio
async def test_eliminar_e_soft_delete_e_tira_o_ficheiro_da_pasta(fake_async_db):
    await fake_async_db.document_metadata.insert_one(
        {"id": "d1", "process_id": "p", "filename": "x.pdf", "s3_path": f"{PASTA}/Index/x.pdf"})
    s3 = _S3()
    r, concluir = await _eliminar(fake_async_db, s3)
    assert r["success"] is True
    assert s3.renomeados == [(f"{PASTA}/Index/x.pdf", f"Eliminados/{PASTA}/Index/x.pdf")]
    doc = await fake_async_db.document_metadata.find_one({"id": "d1"})
    assert doc is not None  # nunca se apaga o registo
    assert doc["is_deleted"] is True and doc["status"] == "eliminado"
    assert doc["deleted_from_s3_path"] == f"{PASTA}/Index/x.pdf"
    assert concluir.await_count == 1  # metadados e matriz refeitos sem ele


@pytest.mark.asyncio
async def test_eliminar_recusa_um_caminho_fora_da_pasta_do_processo(fake_async_db):
    await fake_async_db.document_metadata.insert_one(
        {"id": "d1", "process_id": "p", "s3_path": "Documentação Clientes/outro/x.pdf"})
    s3 = _S3()
    with pytest.raises(HTTPException) as erro:
        await _eliminar(fake_async_db, s3)
    assert erro.value.status_code == 403 and s3.renomeados == []
    assert (await fake_async_db.document_metadata.find_one({"id": "d1"})).get("is_deleted") is None


@pytest.mark.asyncio
async def test_eliminar_com_falha_no_s3_nao_marca(fake_async_db):
    await fake_async_db.document_metadata.insert_one({"id": "d1", "process_id": "p", "s3_path": f"{PASTA}/Index/x.pdf"})
    with pytest.raises(HTTPException) as erro:
        await _eliminar(fake_async_db, _S3(renomeia=False))
    assert erro.value.status_code == 500
    assert (await fake_async_db.document_metadata.find_one({"id": "d1"})).get("is_deleted") is None


@pytest.mark.asyncio
async def test_eliminar_de_outro_processo_e_404(fake_async_db):
    await fake_async_db.document_metadata.insert_one({"id": "d1", "process_id": "outro", "s3_path": f"{PASTA}/x.pdf"})
    with pytest.raises(HTTPException) as erro:
        await _eliminar(fake_async_db, _S3())
    assert erro.value.status_code == 404

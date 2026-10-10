"""Jobs e MFA da recolha governamental contra um MongoDB REAL (Bloco 5).

O duplo de Mongo dos testes unitários aplica `update_one` a TODOS os
documentos que casam; o Mongo real actua num só — e foi essa diferença que
escondeu o `update_one({"process_id": ...})` a tocar no job errado. Aqui prova-se
o que o duplo não pode: a escolha do job, a ordenação e o `$in` sobre estados.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
import pytest_asyncio
from motor.motor_asyncio import AsyncIOMotorClient

from services import gov_fetch_jobs as jobs
from services import mfa_cache


def iso(minutos_atras=0):
    return (datetime.now(timezone.utc) - timedelta(minutes=minutos_atras)).isoformat()


@pytest_asyncio.fixture
async def bd():
    url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    cliente = AsyncIOMotorClient(url, serverSelectionTimeoutMS=2000)
    try:
        await cliente.admin.command("ping")
    except Exception:
        cliente.close()
        pytest.skip("MongoDB não disponível")
    nome = f"test_recolha_gov_{uuid.uuid4().hex[:8]}"
    base = cliente[nome]

    async def sem_redis():
        return None

    with patch.object(mfa_cache, "_get_db", return_value=base), \
         patch.object(jobs, "db", base), \
         patch.object(mfa_cache, "_get_redis", side_effect=sem_redis):
        yield base
    await cliente.drop_database(nome)
    cliente.close()


async def semear(bd, id_, **campos):
    doc = {"id": id_, "process_id": "p1", "source": "financas", "status": "processing",
           "created_at": iso(1), "updated_at": iso(1), **campos}
    await bd.portal_scraper_jobs.insert_one(doc)


async def estado(bd, id_):
    return (await bd.portal_scraper_jobs.find_one({"id": id_}))["status"]


@pytest.mark.asyncio
async def test_com_historico_de_jobs_so_o_activo_mais_recente_muda(bd):
    await semear(bd, "a-2024", status="success", created_at=iso(100000))
    await semear(bd, "b-erro", status="error", created_at=iso(5000))
    await semear(bd, "c-velho-activo", status="processing", created_at=iso(40))
    await semear(bd, "d-novo", status="processing", created_at=iso(1))
    await semear(bd, "e-outro-proc", process_id="p2", status="processing", created_at=iso(0))

    await mfa_cache.set_mfa_status("p1", "awaiting_mfa")

    assert await estado(bd, "d-novo") == "awaiting_mfa"
    assert await estado(bd, "c-velho-activo") == "processing"
    assert await estado(bd, "a-2024") == "success"
    assert await estado(bd, "b-erro") == "error"
    assert await estado(bd, "e-outro-proc") == "processing"


@pytest.mark.asyncio
async def test_codigo_via_mongo_fim_a_fim_e_apagado_ao_consumir(bd):
    await semear(bd, "j", status="processing")
    pausas = []

    async def cliente(_s):
        pausas.append(1)
        if len(pausas) == 2:
            assert await mfa_cache.set_mfa_code("p1", "424242") is True

    codigo = await mfa_cache.aguardar_codigo_mfa("p1", timeout_s=20, intervalo_s=2, dormir=cliente)
    assert codigo == "424242"
    doc = await bd.portal_scraper_jobs.find_one({"id": "j"})
    assert doc["status"] == "processing"
    assert "mfa_code" not in doc


@pytest.mark.asyncio
async def test_job_activo_devolve_o_mais_recente_sem_o_codigo(bd):
    await semear(bd, "velho", created_at=iso(50), mfa_code="111111")
    await semear(bd, "novo", status="awaiting_mfa", created_at=iso(2), mfa_code="222222")
    activo = await jobs.job_activo_do_processo("p1")
    assert activo["id"] == "novo"
    assert "mfa_code" not in activo


@pytest.mark.asyncio
async def test_encerrar_jobs_mortos_so_toca_nos_activos_antigos(bd):
    idade = jobs.IDADE_MAXIMA_DE_UM_JOB_SEGUNDOS / 60 + 5
    await semear(bd, "morto", created_at=iso(idade), mfa_code="1")
    await semear(bd, "terminado", status="success", created_at=iso(idade))
    await semear(bd, "vivo", created_at=iso(3))
    assert await jobs.encerrar_jobs_mortos() == 1
    assert await estado(bd, "morto") == "error"
    assert await estado(bd, "terminado") == "success"
    assert await estado(bd, "vivo") == "processing"
    assert "mfa_code" not in await bd.portal_scraper_jobs.find_one({"id": "morto"})


@pytest.mark.asyncio
async def test_delete_mfa_code_limpa_todos_os_jobs_do_processo_e_so_esse(bd):
    await semear(bd, "a", mfa_code="1")
    await semear(bd, "b", mfa_code="2")
    await semear(bd, "c", process_id="p2", mfa_code="3")
    await mfa_cache.delete_mfa_code("p1")
    assert "mfa_code" not in await bd.portal_scraper_jobs.find_one({"id": "a"})
    assert "mfa_code" not in await bd.portal_scraper_jobs.find_one({"id": "b"})
    assert (await bd.portal_scraper_jobs.find_one({"id": "c"}))["mfa_code"] == "3"

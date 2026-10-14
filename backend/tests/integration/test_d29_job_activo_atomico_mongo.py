"""D-29 FECHADA — «um job de recolha activo por processo» é ATÓMICO, provado contra um MongoDB REAL.

Verificar «há um activo?» e criar o job eram duas operações: dois pedidos simultâneos passavam ambos,
arrancavam dois logins no Portal das Finanças e o cliente recebia dois SMS (o código que escrevia servia
um só). O índice único parcial (`process_id`, filtro `active: True`) recusa o segundo.

O duplo in-memory não implementa índices únicos parciais: só um Mongo real prova isto.
"""
from __future__ import annotations

import asyncio
import os
import uuid
from unittest.mock import patch

import pytest
import pytest_asyncio
from motor.motor_asyncio import AsyncIOMotorClient

from services import db_indexes, gov_fetch_jobs, portal_gov_fetch
from services.gov_fetch_jobs import JobJaActivo, criar_job, encerrar_jobs_mortos


@pytest_asyncio.fixture
async def bd():
    url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    cliente = AsyncIOMotorClient(url, serverSelectionTimeoutMS=2000)
    try:
        await cliente.admin.command("ping")
    except Exception:
        cliente.close()
        pytest.skip("MongoDB não disponível")
    base = cliente[f"test_d29_{uuid.uuid4().hex[:8]}"]
    resultados = {"created": [], "errors": [], "skipped": []}
    for idx in db_indexes.INDEX_DEFINITIONS["portal_scraper_jobs"]:
        await db_indexes._create_index_safe(base.portal_scraper_jobs, idx, "portal_scraper_jobs", resultados)
    assert resultados["errors"] == []
    with patch.object(gov_fetch_jobs, "db", base), patch.object(portal_gov_fetch, "db", base):
        yield base
    await cliente.drop_database(base.name)
    cliente.close()


@pytest.mark.asyncio
async def test_dois_pedidos_em_simultaneo_so_um_cria_o_job(bd):
    resultados = await asyncio.gather(
        *[criar_job("proc-1", "financas") for _ in range(8)], return_exceptions=True,
    )
    criados = [r for r in resultados if isinstance(r, str)]
    perdidos = [r for r in resultados if isinstance(r, JobJaActivo)]
    assert len(criados) == 1 and len(perdidos) == 7
    assert await bd.portal_scraper_jobs.count_documents({"process_id": "proc-1"}) == 1


@pytest.mark.asyncio
async def test_processos_diferentes_nao_se_bloqueiam(bd):
    a, b = await asyncio.gather(criar_job("proc-A", "financas"), criar_job("proc-B", "financas"))
    assert a != b


@pytest.mark.asyncio
async def test_terminado_o_job_o_processo_pode_ter_outro(bd):
    job = await criar_job("proc-1", "financas")
    with pytest.raises(JobJaActivo):
        await criar_job("proc-1", "seguranca_social")

    await portal_gov_fetch._gravar_estado_do_job(job, {"status": "success"})
    segundo = await criar_job("proc-1", "seguranca_social")
    assert segundo != job


@pytest.mark.asyncio
async def test_um_erro_tambem_liberta(bd):
    job = await criar_job("proc-1", "financas")
    await portal_gov_fetch._gravar_estado_do_job(job, {"status": "error", "error_type": "x"})
    await criar_job("proc-1", "financas")


@pytest.mark.asyncio
async def test_awaiting_mfa_continua_a_ocupar_o_lugar(bd):
    """Um estado ACTIVO que não é o inicial não liberta — senão o MFA abria a porta a um 2.º login."""
    job = await criar_job("proc-1", "financas")
    await portal_gov_fetch._gravar_estado_do_job(job, {"status": "awaiting_mfa"})
    doc = await bd.portal_scraper_jobs.find_one({"id": job})
    assert doc["active"] is True
    with pytest.raises(JobJaActivo):
        await criar_job("proc-1", "financas")


@pytest.mark.asyncio
async def test_um_job_morto_deixa_de_bloquear_o_processo(bd):
    """O contentor reiniciou a meio: sem esta limpeza o `active: True` trancava o processo para sempre."""
    job = await criar_job("proc-1", "financas")
    await bd.portal_scraper_jobs.update_one({"id": job}, {"$set": {"created_at": "2020-01-01T00:00:00+00:00"}})
    assert await encerrar_jobs_mortos("proc-1") == 1
    assert (await bd.portal_scraper_jobs.find_one({"id": job}))["active"] is False
    await criar_job("proc-1", "financas")


@pytest.mark.asyncio
async def test_jobs_antigos_sem_o_campo_nao_colidem(bd):
    """Os jobs anteriores ao índice não têm `active`: ficam fora do índice parcial."""
    for i in range(3):
        await bd.portal_scraper_jobs.insert_one({"id": f"velho-{i}", "process_id": "proc-1", "status": "success"})
    await criar_job("proc-1", "financas")


@pytest.mark.asyncio
async def test_o_pedido_que_perde_a_corrida_recebe_o_job_em_curso(bd):
    """Ponta a ponta de `_iniciar_recolha`: o segundo clique liga-se ao job do primeiro."""
    from fastapi import BackgroundTasks

    async def corpo(**_kw):
        return None

    dados = {"nif": "123456789", "password": "x"}
    cliente = {"process": {"id": "proc-9", "client_name": "Ana", "client_email": "a@x.pt"}}
    with patch.dict(os.environ, {"ENVIRONMENT": "production"}):
        respostas = await asyncio.gather(*[
            portal_gov_fetch._iniciar_recolha(
                portal_gov_fetch.FINANCAS, corpo, dict(dados), "nif", 9, BackgroundTasks(), cliente,
            )
            for _ in range(6)
        ], return_exceptions=True)

    erros = [r for r in respostas if isinstance(r, Exception)]
    assert erros == [], erros
    import json

    corpos = [json.loads(r.body) for r in respostas]
    assert len({c["scraper_job_id"] for c in corpos}) == 1, "todos apontam para o MESMO job"
    assert sum(1 for c in corpos if c.get("already_running")) == 5
    assert await bd.portal_scraper_jobs.count_documents({"process_id": "proc-9"}) == 1

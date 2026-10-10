"""MFA e jobs da recolha governamental (Bloco 5, pontos 8 e 9).

Cada teste descreve um defeito que existia: o `update_one({"process_id"})` sem
ordenação a actuar no job ERRADO, o código velho lido como se fosse novo, o job
preso para sempre, o estado devolvido a quem tivesse o id.

Nota: o duplo de Mongo aplica `update_one` a TODOS os documentos que casam, ao
contrário do Mongo real (que actua num só). Os testes de «qual job é tocado»
usam por isso `find_one_and_update`/`update_many`, cuja semântica o duplo
reproduz — e há um teste de integração contra um `mongod` real.
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from services import gov_fetch_jobs as jobs
from services import mfa_cache


def iso(minutos_atras=0):
    return (datetime.now(timezone.utc) - timedelta(minutes=minutos_atras)).isoformat()


@pytest.fixture
def bd(fake_async_db):
    with patch.object(mfa_cache, "_get_db", return_value=fake_async_db), \
         patch.object(jobs, "db", fake_async_db), \
         patch.object(mfa_cache, "_get_redis", return_value=None) as redis:
        async def sem_redis():
            return None
        redis.side_effect = sem_redis
        yield fake_async_db


async def semear(bd, **campos):
    base = {"id": "j", "process_id": "p1", "source": "financas", "status": "processing",
            "created_at": iso(1), "updated_at": iso(1)}
    base.update(campos)
    await bd.portal_scraper_jobs.insert_one(base)
    return base["id"]


async def job(bd, job_id):
    return await bd.portal_scraper_jobs.find_one({"id": job_id})


# ── set_mfa_status: o job certo ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_set_mfa_status_actua_no_job_activo_mais_recente_e_nao_no_antigo(bd):
    await semear(bd, id="antigo", status="error", created_at=iso(600))
    await semear(bd, id="novo", status="processing", created_at=iso(1))

    await mfa_cache.set_mfa_status("p1", "awaiting_mfa")

    assert (await job(bd, "novo"))["status"] == "awaiting_mfa"
    assert (await job(bd, "antigo"))["status"] == "error", "ressuscitou um job que já terminou"


@pytest.mark.asyncio
async def test_set_mfa_status_com_dois_activos_escolhe_o_mais_recente(bd):
    await semear(bd, id="velho", created_at=iso(30))
    await semear(bd, id="recente", created_at=iso(2))
    await mfa_cache.set_mfa_status("p1", "awaiting_mfa")
    assert (await job(bd, "recente"))["status"] == "awaiting_mfa"
    assert (await job(bd, "velho"))["status"] == "processing"


@pytest.mark.asyncio
async def test_voltar_a_processing_apaga_o_codigo_em_claro(bd):
    await semear(bd, id="j1", status="awaiting_mfa", mfa_code="123456")
    await mfa_cache.set_mfa_status("p1", "processing")
    atual = await job(bd, "j1")
    assert atual["status"] == "processing"
    assert "mfa_code" not in atual


@pytest.mark.asyncio
async def test_set_mfa_status_sem_job_activo_nao_levanta_nem_inventa(bd):
    await semear(bd, id="fim", status="success")
    await mfa_cache.set_mfa_status("p1", "awaiting_mfa")
    assert (await job(bd, "fim"))["status"] == "success"


# ── delete_mfa_code ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_delete_mfa_code_limpa_todos_os_jobs_do_processo(bd):
    await semear(bd, id="a", mfa_code="111111")
    await semear(bd, id="b", mfa_code="222222")
    await semear(bd, id="outro", process_id="p2", mfa_code="999999")
    await mfa_cache.delete_mfa_code("p1")
    assert "mfa_code" not in await job(bd, "a")
    assert "mfa_code" not in await job(bd, "b")
    assert (await job(bd, "outro"))["mfa_code"] == "999999"


# ── set_mfa_code ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_set_mfa_code_sem_ninguem_a_espera_nao_diz_que_guardou(bd):
    await semear(bd, id="j", status="processing")
    assert await mfa_cache.set_mfa_code("p1", "123456") is False
    assert "mfa_code" not in await job(bd, "j")


@pytest.mark.asyncio
async def test_set_mfa_code_com_job_a_espera_guarda(bd):
    await semear(bd, id="j", status="awaiting_mfa")
    assert await mfa_cache.set_mfa_code("p1", "123456") is True
    assert (await job(bd, "j"))["mfa_code"] == "123456"


# ── aguardar_codigo_mfa ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_um_codigo_velho_nao_e_lido_como_se_fosse_deste_pedido(bd):
    """Antes de esperar, o código deixado por uma execução anterior é apagado."""
    await semear(bd, id="j", status="processing", mfa_code="000000")

    async def sem_pausa(_s):
        return None

    codigo = await mfa_cache.aguardar_codigo_mfa("p1", timeout_s=4, intervalo_s=2, dormir=sem_pausa)
    assert codigo is None
    assert (await job(bd, "j"))["status"] == "awaiting_mfa"


@pytest.mark.asyncio
async def test_recebido_o_codigo_o_job_volta_a_processing(bd):
    """Senão o ecrã mostrava outra vez o campo do código logo após o envio."""
    await semear(bd, id="j", status="processing")
    pausas = []

    async def cliente_escreve(_s):
        pausas.append(1)
        if len(pausas) == 2:
            await mfa_cache.set_mfa_code("p1", "654321")

    codigo = await mfa_cache.aguardar_codigo_mfa("p1", timeout_s=20, intervalo_s=2, dormir=cliente_escreve)
    assert codigo == "654321"
    atual = await job(bd, "j")
    assert atual["status"] == "processing"
    assert "mfa_code" not in atual


@pytest.mark.asyncio
async def test_esperar_o_codigo_regista_que_houve_MFA_para_a_politica(bd):
    from services import gov_fetch_policy as politica

    estado = {"mfa": False}
    token = politica._estado_da_tentativa.set(estado)
    try:
        async def sem_pausa(_s):
            return None
        await semear(bd, id="j")
        await mfa_cache.aguardar_codigo_mfa("p1", timeout_s=2, intervalo_s=2, dormir=sem_pausa)
    finally:
        politica._estado_da_tentativa.reset(token)
    assert estado["mfa"] is True


# ── jobs mortos, posse e projecção ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_job_activo_acima_do_tempo_maximo_e_encerrado_com_mensagem(bd):
    idade = jobs.IDADE_MAXIMA_DE_UM_JOB_SEGUNDOS / 60 + 5
    await semear(bd, id="morto", created_at=iso(idade), mfa_code="123456")
    await semear(bd, id="vivo", process_id="p2", created_at=iso(2))

    encerrados = await jobs.encerrar_jobs_mortos()

    assert encerrados >= 1
    morto = await job(bd, "morto")
    assert morto["status"] == "error"
    assert morto["error_type"] == "scraper_unavailable"
    assert morto["message"] == jobs.MENSAGEM_DE_JOB_MORTO
    assert "mfa_code" not in morto
    assert (await job(bd, "vivo"))["status"] == "processing"


@pytest.mark.asyncio
async def test_um_job_terminado_nao_e_tocado_pela_limpeza(bd):
    idade = jobs.IDADE_MAXIMA_DE_UM_JOB_SEGUNDOS / 60 + 5
    await semear(bd, id="feito", status="success", created_at=iso(idade))
    await jobs.encerrar_jobs_mortos()
    assert (await job(bd, "feito"))["status"] == "success"


def test_o_tempo_maximo_de_um_job_cobre_o_pior_caso_da_politica():
    from services import gov_fetch_policy as p
    assert jobs.IDADE_MAXIMA_DE_UM_JOB_SEGUNDOS > p.ESPERA_PELO_SEMAFORO_SEGUNDOS + p.ORCAMENTO_TOTAL_SEGUNDOS


@pytest.mark.asyncio
async def test_ler_job_de_outro_processo_e_indistinguivel_de_inexistente(bd):
    await semear(bd, id="alheio", process_id="p2")
    assert await jobs.ler_job_do_processo("alheio", "p1") is None
    assert await jobs.ler_job_do_processo("nao-existe", "p1") is None


@pytest.mark.asyncio
async def test_a_leitura_nunca_devolve_o_codigo_nem_campos_internos(bd):
    await semear(bd, id="j", status="awaiting_mfa", mfa_code="123456", segredo_interno="x")
    lido = await jobs.ler_job_do_processo("j", "p1")
    assert lido["status"] == "awaiting_mfa"
    assert "mfa_code" not in lido
    assert "segredo_interno" not in lido
    assert "process_id" not in lido
    assert set(lido) <= set(jobs.CAMPOS_PUBLICOS_DO_JOB)


@pytest.mark.asyncio
async def test_job_activo_do_processo_ignora_terminados_e_outros_processos(bd):
    await semear(bd, id="fim", status="error")
    await semear(bd, id="outro", process_id="p2")
    assert await jobs.job_activo_do_processo("p1") is None
    await semear(bd, id="vivo", status="awaiting_mfa", mfa_code="1")
    activo = await jobs.job_activo_do_processo("p1")
    assert activo["id"] == "vivo"
    assert "mfa_code" not in activo

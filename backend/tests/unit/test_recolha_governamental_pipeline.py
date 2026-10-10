"""Pipeline de recolha no Estado, de ponta a ponta (Bloco 5, pontos 8 e 9).

Só as fronteiras são falseadas: o scraper (Playwright), o S3, o email e o
WebSocket. O arquivo, os jobs, o mapeamento de erros e a política são os REAIS.
"""
import ast
import inspect
import pathlib
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import BackgroundTasks, HTTPException

from services import gov_fetch_archive as arq
from services import gov_fetch_jobs as jobs
from services import mfa_cache
from services import portal_gov_fetch as pgf
from services.gov_scraper import ScraperDocument, ScraperResult

PDF = b"%PDF-1.4\n" + b"conteudo " * 60


def sdoc(label, filename):
    return ScraperDocument(filename, PDF, "application/pdf", "Financeiros", label)


@pytest.fixture
def mundo(fake_async_db, monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    fake_async_db.processes.docs.append({
        "id": "p1", "client_name": "Ana Costa", "client_id": "c1",
        "s3_folder": "Documentação Clientes/c1/processos/p1",
    })
    s3 = patch.object(arq.s3_service, "upload_file", side_effect=lambda **kw: f"{kw['s3_folder']}/{kw['category']}/{kw['filename']}")
    mocks = SimpleNamespace(
        db=fake_async_db,
        email=AsyncMock(),
        equipa=AsyncMock(),
        tempo_real=AsyncMock(),
    )
    with patch.object(pgf, "db", fake_async_db), patch.object(arq, "db", fake_async_db), \
         patch.object(jobs, "db", fake_async_db), patch.object(mfa_cache, "_get_db", return_value=fake_async_db), \
         patch.object(pgf, "_send_portal_fetch_email", mocks.email), \
         patch.object(pgf, "_notify_assigned_team_fetch", mocks.equipa), \
         patch.object(pgf, "_notificar_recolha", mocks.tempo_real), \
         s3 as upload:
        mocks.upload = upload
        yield mocks


async def novo_job(mundo, source="financas"):
    return await jobs.criar_job("p1", source)


async def ler(mundo, job_id):
    return await mundo.db.portal_scraper_jobs.find_one({"id": job_id})


async def correr_financas(mundo, job_id, resultado_do_scraper):
    with patch("services.gov_scraper.fetch_financas_documents", AsyncMock(return_value=resultado_do_scraper)):
        await pgf._run_financas_background(
            nif="123456789", password="segredo", process_id="p1", client_name="Ana Costa",
            client_email="ana@example.com", process={"id": "p1"}, scraper_job_id=job_id,
        )


# ── sucesso, parcial e falhas de arquivo ───────────────────────────────────

@pytest.mark.asyncio
async def test_sucesso_completo(mundo):
    job_id = await novo_job(mundo)
    await correr_financas(mundo, job_id, ScraperResult(True, [sdoc("Declaração de IRS", "I.pdf"), sdoc("Nota de Liquidação IRS", "N.pdf")]))
    job = await ler(mundo, job_id)
    assert job["status"] == "success"
    assert job["documents_count"] == 2
    assert job["documents_missing"] == []
    assert "2 documentos obtidos" in job["message"]
    mundo.tempo_real.assert_awaited_once()
    assert mundo.tempo_real.await_args.kwargs["docs_count"] == 2


@pytest.mark.asyncio
async def test_so_a_declaracao_e_parcial_e_diz_qual_falta(mundo):
    job_id = await novo_job(mundo)
    await correr_financas(mundo, job_id, ScraperResult(True, [sdoc("Declaração de IRS", "I.pdf")]))
    job = await ler(mundo, job_id)
    assert job["status"] == "success"
    assert job["documents_count"] == 1
    assert job["documents_missing"] == ["Nota de Liquidação IRS"]
    assert "Nota de Liquidação IRS" in job["message"]


@pytest.mark.asyncio
async def test_o_s3_em_baixo_nao_e_sucesso_com_zero_documentos(mundo):
    """Antes: «0 documentos obtidos» com estado success e registos sem ficheiro."""
    mundo.upload.side_effect = lambda **kw: None
    job_id = await novo_job(mundo)
    await correr_financas(mundo, job_id, ScraperResult(True, [sdoc("Declaração de IRS", "I.pdf")]))
    job = await ler(mundo, job_id)
    assert job["status"] == "error"
    assert job["error_type"] == "arquivo_falhou"
    assert await mundo.db.documents.find_one({"process_id": "p1"}) is None


@pytest.mark.asyncio
async def test_sucesso_do_scraper_sem_documentos_e_sem_documentos(mundo):
    job_id = await novo_job(mundo)
    await correr_financas(mundo, job_id, ScraperResult(True, []))
    job = await ler(mundo, job_id)
    assert job["status"] == "error" and job["error_type"] == "sem_documentos"


# ── nada do que vem depois do arquivo transforma sucesso em erro ───────────

@pytest.mark.asyncio
@pytest.mark.parametrize("quem", ["email", "equipa", "tempo_real"])
async def test_uma_falha_ao_notificar_nao_transforma_um_sucesso_em_erro(mundo, quem):
    """A cópia anterior chamava a notificação da equipa sem guarda no mesmo `try`
    do scraper: a excepção sobrescrevia o job `success` com `unexpected_error`."""
    getattr(mundo, quem).side_effect = RuntimeError("notificação em baixo")
    job_id = await novo_job(mundo)
    await correr_financas(mundo, job_id, ScraperResult(True, [sdoc("Declaração de IRS", "I.pdf"), sdoc("Nota de Liquidação IRS", "N.pdf")]))
    job = await ler(mundo, job_id)
    assert job["status"] == "success"
    assert job.get("error_type") is None
    assert len(mundo.db.documents.docs) == 2


@pytest.mark.asyncio
async def test_falhar_a_gravar_o_estado_do_job_nao_levanta(mundo):
    job_id = await novo_job(mundo)
    with patch.object(mundo.db.portal_scraper_jobs, "update_one", AsyncMock(side_effect=RuntimeError("mongo"))):
        await pgf._gravar_estado_do_job(job_id, {"status": "success"})  # não levanta


@pytest.mark.asyncio
async def test_excepcao_no_scraper_deixa_o_job_em_erro_e_avisa_o_ecra(mundo):
    job_id = await novo_job(mundo)
    with patch("services.gov_scraper.fetch_financas_documents", AsyncMock(side_effect=RuntimeError("playwright"))):
        await pgf._run_financas_background(
            nif="123456789", password="x", process_id="p1", client_name="A", client_email="a@b.c",
            process={"id": "p1"}, scraper_job_id=job_id,
        )
    job = await ler(mundo, job_id)
    assert job["status"] == "error" and job["error_type"] == "scraper_unavailable"
    mundo.tempo_real.assert_awaited_once()  # antes o caminho inesperado não avisava o ecrã


@pytest.mark.asyncio
async def test_seguranca_social_usa_o_mesmo_pipeline(mundo):
    job_id = await novo_job(mundo, "seguranca_social")
    res = ScraperResult(True, [sdoc("Situação Contributiva", "S.pdf")])
    with patch("services.gov_scraper.fetch_seg_social_documents", AsyncMock(return_value=res)):
        await pgf._run_seguranca_social_background(
            niss="12345678901", password="x", process_id="p1", client_name="A", client_email="a@b.c",
            process={"id": "p1"}, scraper_job_id=job_id,
        )
    job = await ler(mundo, job_id)
    assert job["status"] == "success"
    assert job["documents_missing"] == ["Extrato de Remunerações"]
    registo = await mundo.db.documents.find_one({"process_id": "p1"})
    assert registo["source"] == "auto_seguranca_social"
    assert registo["uploaded_by"] == "system_seguranca_social_scraper"


# ── erros do scraper → o que o cliente lê ──────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.parametrize(
    "erro,tipo",
    [
        ("credenciais_invalidas", "credenciais_invalidas"),
        ("mfa_timeout", "mfa_timeout"),
        ("mfa_codigo_incorreto", "mfa_codigo_incorreto"),
        ("mfa_no_input", "mfa_error"),
        ("mfa_error", "mfa_error"),
        ("mfa_requerido", "mfa_requerido"),
        ("timeout", "timeout_scraper"),
        ("timeout_login", "timeout_scraper"),
        ("sem_documentos", "sem_documentos"),
        ("scraper_ocupado", "scraper_ocupado"),
        ("memory_error", "scraper_unavailable"),
        ("selector_desatualizado", "scraper_unavailable"),
        ("qualquer_coisa_nova", "scraper_unavailable"),
    ],
)
async def test_cada_erro_do_scraper_tem_o_tipo_certo(mundo, erro, tipo):
    job_id = await novo_job(mundo)
    await correr_financas(mundo, job_id, ScraperResult(False, error=erro, step_failed="x"))
    job = await ler(mundo, job_id)
    assert job["status"] == "error"
    assert job["error_type"] == tipo
    assert job["message"]
    assert "mfa_code" not in job


@pytest.mark.parametrize("fonte", [pgf.FINANCAS, pgf.SEGURANCA_SOCIAL])
def test_toda_a_mensagem_de_erro_existe_nas_duas_fontes(fonte):
    for tipo in set(pgf._TIPO_DE_ERRO.values()) | {"scraper_unavailable"}:
        erro = next((k for k, v in pgf._TIPO_DE_ERRO.items() if v == tipo), "x")
        resolvido, mensagem = pgf.classificar_falha(erro, fonte)
        assert resolvido == tipo and mensagem


def test_a_mensagem_de_timeout_do_mfa_nao_promete_um_tempo_fixo_escrito_a_mao():
    from services.gov_fetch_policy import MFA_ESPERA_SEGUNDOS
    _, mensagem = pgf.classificar_falha("mfa_timeout", pgf.FINANCAS)
    assert str(MFA_ESPERA_SEGUNDOS // 60) in mensagem


# ── iniciar a recolha ──────────────────────────────────────────────────────

CLIENTE = {"process": {"id": "p1", "client_name": "Ana Costa", "client_email": "ana@example.com"}}


@pytest.mark.asyncio
async def test_um_segundo_clique_na_mesma_fonte_reutiliza_o_job_em_curso(mundo):
    tarefas = BackgroundTasks()
    r1 = await pgf.run_fetch_financas_documents({"nif": "123456789", "password": "x"}, tarefas, CLIENTE)
    r2 = await pgf.run_fetch_financas_documents({"nif": "123456789", "password": "x"}, tarefas, CLIENTE)
    import json
    j1, j2 = json.loads(r1.body), json.loads(r2.body)
    assert j1["scraper_job_id"] == j2["scraper_job_id"]
    assert j2["already_running"] is True
    assert len(tarefas.tasks) == 1, "arrancou um segundo login (e um segundo SMS)"
    assert len(mundo.db.portal_scraper_jobs.docs) == 1


@pytest.mark.asyncio
async def test_outra_fonte_com_um_job_activo_e_409(mundo):
    tarefas = BackgroundTasks()
    await pgf.run_fetch_financas_documents({"nif": "123456789", "password": "x"}, tarefas, CLIENTE)
    with pytest.raises(HTTPException) as erro:
        await pgf.run_fetch_seguranca_social_documents({"niss": "12345678901", "password": "x"}, tarefas, CLIENTE)
    assert erro.value.status_code == 409


@pytest.mark.asyncio
async def test_depois_de_terminar_pode_iniciar_outra(mundo):
    tarefas = BackgroundTasks()
    r1 = await pgf.run_fetch_financas_documents({"nif": "123456789", "password": "x"}, tarefas, CLIENTE)
    import json
    primeiro = json.loads(r1.body)["scraper_job_id"]
    await pgf._gravar_estado_do_job(primeiro, {"status": "error"})
    r2 = await pgf.run_fetch_financas_documents({"nif": "123456789", "password": "x"}, tarefas, CLIENTE)
    assert json.loads(r2.body)["scraper_job_id"] != primeiro


@pytest.mark.asyncio
async def test_um_job_morto_nao_impede_um_pedido_novo(mundo):
    from datetime import datetime, timedelta, timezone
    velho = (datetime.now(timezone.utc) - timedelta(seconds=jobs.IDADE_MAXIMA_DE_UM_JOB_SEGUNDOS + 600)).isoformat()
    await mundo.db.portal_scraper_jobs.insert_one(
        {"id": "morto", "process_id": "p1", "source": "financas", "status": "awaiting_mfa", "created_at": velho, "updated_at": velho}
    )
    tarefas = BackgroundTasks()
    import json
    r = await pgf.run_fetch_financas_documents({"nif": "123456789", "password": "x"}, tarefas, CLIENTE)
    assert json.loads(r.body)["scraper_job_id"] != "morto"
    assert (await ler(mundo, "morto"))["status"] == "error"


@pytest.mark.asyncio
@pytest.mark.parametrize("corpo", [{"nif": "12", "password": "x"}, {"nif": "abcdefghi", "password": "x"}, {"nif": "123456789", "password": ""}, {}])
async def test_pedido_invalido_e_400_e_nao_cria_job(mundo, corpo):
    with pytest.raises(HTTPException) as erro:
        await pgf.run_fetch_financas_documents(corpo, BackgroundTasks(), CLIENTE)
    assert erro.value.status_code == 400
    assert not mundo.db.portal_scraper_jobs.docs


@pytest.mark.asyncio
async def test_em_dev_o_scraper_nao_arranca(mundo, monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "dev")
    tarefas = BackgroundTasks()
    r = await pgf.run_fetch_financas_documents({"nif": "123456789", "password": "x"}, tarefas, CLIENTE)
    assert r["dev_mode"] is True
    assert not tarefas.tasks and not mundo.db.portal_scraper_jobs.docs


# ── MFA ────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_mfa_so_aceita_codigo_quando_ha_job_a_espera(mundo):
    await mundo.db.portal_scraper_jobs.insert_one({"id": "j", "process_id": "p1", "source": "financas", "status": "processing", "created_at": "2026-10-10T10:00:00+00:00"})
    with pytest.raises(HTTPException) as erro:
        await pgf.run_submit_mfa_code({"mfa_code": "123456"}, CLIENTE)
    assert erro.value.status_code == 409
    assert "processar" in erro.value.detail


@pytest.mark.asyncio
async def test_mfa_a_resposta_descreve_o_job_mais_recente_e_nao_o_mais_antigo(mundo):
    docs = mundo.db.portal_scraper_jobs.docs
    docs.append({"id": "velho", "process_id": "p1", "source": "financas", "status": "success", "created_at": "2026-01-01T10:00:00+00:00"})
    docs.append({"id": "novo", "process_id": "p1", "source": "financas", "status": "processing", "created_at": "2026-10-10T09:59:00+00:00"})
    with pytest.raises(HTTPException) as erro:
        await pgf.run_submit_mfa_code({"mfa_code": "123456"}, CLIENTE)
    assert "processar" in erro.value.detail, "respondeu com o estado do job de Janeiro"


@pytest.mark.asyncio
async def test_mfa_do_processo_errado_e_403(mundo):
    with pytest.raises(HTTPException) as erro:
        await pgf.run_submit_mfa_code({"process_id": "outro", "mfa_code": "123456"}, CLIENTE)
    assert erro.value.status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize("codigo", ["", "123", "123456789", "12ab56"])
async def test_mfa_formato_invalido_e_400(mundo, codigo):
    with pytest.raises(HTTPException) as erro:
        await pgf.run_submit_mfa_code({"mfa_code": codigo}, CLIENTE)
    assert erro.value.status_code == 400


# ── estado do job: posse ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_estado_do_job_de_outro_processo_e_404(mundo):
    await mundo.db.portal_scraper_jobs.insert_one({"id": "alheio", "process_id": "p2", "source": "financas", "status": "processing", "created_at": "2026-10-10T10:00:00+00:00"})
    with pytest.raises(HTTPException) as erro:
        await pgf.run_get_scraper_job_status("alheio", CLIENTE)
    assert erro.value.status_code == 404


@pytest.mark.asyncio
async def test_estado_do_job_proprio_nao_leva_o_codigo(mundo):
    await mundo.db.portal_scraper_jobs.insert_one(
        {"id": "meu", "process_id": "p1", "source": "financas", "status": "awaiting_mfa", "mfa_code": "123456", "created_at": "2026-10-10T10:00:00+00:00"}
    )
    lido = await pgf.run_get_scraper_job_status("meu", CLIENTE)
    assert lido["status"] == "awaiting_mfa" and "mfa_code" not in lido


def test_a_rota_do_estado_do_job_exige_autenticacao_do_cliente():
    """O endpoint estava aberto a qualquer pessoa com o id do job."""
    fonte = pathlib.Path(__file__).resolve().parents[2] / "routes" / "portal.py"
    arvore = ast.parse(fonte.read_text(encoding="utf-8"))
    funcao = next(n for n in ast.walk(arvore) if isinstance(n, ast.AsyncFunctionDef) and n.name == "get_scraper_job_status")
    assert "get_current_client" in ast.unparse(funcao.args), "a rota do estado do job perdeu o Depends(get_current_client)"
    assert "client_data" in ast.unparse(funcao)


def test_o_polling_do_ecra_envia_o_token():
    fonte = pathlib.Path(__file__).resolve().parents[3] / "frontend" / "src" / "pages" / "ClientPortal.jsx"
    texto = fonte.read_text(encoding="utf-8")
    trecho = texto[texto.index("/portal/scraper-job/"):][:400]
    assert "Authorization" in trecho

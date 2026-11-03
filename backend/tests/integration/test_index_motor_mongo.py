"""O motor do Index de ponta a ponta contra um MongoDB REAL (Lote 12, Fase 2).

Real porque o que importa aqui é o que um duplo esconde: o índice único parcial do
«um job activo por processo e tipo» (concorrência a sério), o `$setOnInsert` do
directório de entidades, a substituição de alertas e o recálculo dos metadados.
S3 e modelo são falseados NA FRONTEIRA (`_ler_ficheiro`, `analisar_documento`):
tudo o resto — estado, jobs, TaskLog, notificações, Log da IA — é o real.
"""
from __future__ import annotations

import asyncio
import os
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from motor.motor_asyncio import AsyncIOMotorClient

from models.task_log import TaskType
from services import index_ai as ia
from services import index_jobs as jobs
from services import index_status as ist
from services import index_store as st
from services import process_ai_log as ailog
from services import task_log_service as tls
from services.background_tasks import aguardar_tarefas_pendentes
from services.db_indexes import INDEX_DEFINITIONS

pytestmark = pytest.mark.asyncio

USER = {"id": "u-index", "name": "Ivo Index", "role": "indexacao"}
PID = "proc-1"
HOJE = datetime.now(timezone.utc).date()


@pytest_asyncio.fixture
async def bd(monkeypatch):
    url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    cliente = AsyncIOMotorClient(url, serverSelectionTimeoutMS=2000)
    try:
        await cliente.admin.command("ping")
    except Exception:
        cliente.close()
        pytest.skip("MongoDB não disponível")
    base = cliente[f"test_index_motor_{uuid.uuid4().hex[:8]}"]
    # o índice único parcial é o árbitro da concorrência: cria-se a partir da DECLARAÇÃO de produção
    d = next(i for i in INDEX_DEFINITIONS["task_logs"] if i["name"] == "idx_index_job_activo_unico")
    await base.task_logs.create_index(d["keys"], name=d["name"], unique=True,
                                      partialFilterExpression=d["partialFilterExpression"])
    from services import push_notifications as push
    from services import realtime_notifications as rt

    # Cada módulo importou `db` para si (a armadilha da ordem de import): patcha-se um a um.
    for modulo in (jobs, st, ist, ailog, tls, rt, push):
        monkeypatch.setattr(modulo, "db", base)
    monkeypatch.setattr("database.db", base)
    monkeypatch.setenv("INDEX_AI_PROVIDER", "mock")
    await base.processes.insert_one({
        "id": PID, "process_number": 42, "client_name": "Ana Cliente", "network_id": "rede-A",
        "is_indexed": False, "index_status": "in_review", "status": "indexacao",
        "personal_data": {"nif": "123456789"},
    })
    yield base
    await aguardar_tarefas_pendentes()
    await cliente.drop_database(base.name)
    cliente.close()


S3: dict[str, bytes] = {}


@pytest.fixture(autouse=True)
def s3_falso():
    S3.clear()

    async def ler(caminho):
        if caminho not in S3:
            return None, "ilegivel"
        return S3[caminho], None

    with patch.object(jobs, "_ler_ficheiro", ler):
        yield


async def doc(bd, nome, conteudo=b"conteudo", categoria=None, sub=None, pid=PID, **extra):
    id_ = str(uuid.uuid4())
    caminho = f"Documentação Clientes/{pid}/{nome}"
    S3[caminho] = conteudo + nome.encode()
    await bd.document_metadata.insert_one({
        "id": id_, "process_id": pid, "s3_path": caminho, "filename": nome,
        "ai_category": categoria, "ai_subcategory": sub, **extra,
    })
    return id_


async def tres_documentos(bd):
    r = await doc(bd, "recibo_vencimento_setembro.pdf", categoria="Rendimentos", sub="Recibo de Vencimento")
    e = await doc(bd, "extrato_setembro.pdf", categoria="Bancários", sub="Extrato Bancário")
    i = await doc(bd, "cc.pdf", categoria="Identificação", sub="Cartão de Cidadão")
    return r, e, i


async def correr(force=False):
    r = await jobs.iniciar_analise(PID, USER, force=force)
    await aguardar_tarefas_pendentes()
    return r


async def tarefa(bd, task_id):
    return await bd.task_logs.find_one({"task_id": task_id}, {"_id": 0})


# ── o caminho feliz ────────────────────────────────────────────────────────
class TestAnaliseDePontaAPonta:
    async def test_corre_em_background_e_termina_com_resumo(self, bd):
        await tres_documentos(bd)
        r = await jobs.iniciar_analise(PID, USER)
        assert r["iniciado"] is True and r["task_id"]          # devolve JÁ, com o id do job
        await aguardar_tarefas_pendentes()
        t = await tarefa(bd, r["task_id"])
        assert t["status"] == "completed" and t["task_type"] == "INDEX_ANALYSIS"
        assert t["result_data"]["analisados"] == 3 and t["result_data"]["falhas"] == 0
        assert "falhados" not in t["result_data"]               # a lista interna não vai para o ecrã

    async def test_cada_ficheiro_fica_categorizado_e_com_impressao(self, bd):
        r, e, i = await tres_documentos(bd)
        await correr()
        rec = await bd.document_metadata.find_one({"id": r})
        ext = await bd.document_metadata.find_one({"id": e})
        ide = await bd.document_metadata.find_one({"id": i})
        assert rec["ai_category"] == "Financeiros" and rec["ai_subcategory"] == "Recibo de Vencimento"
        assert ext["ai_category"] == "Bancários"
        assert ide["ai_category"] == "Identificação" and ide["ai_subtype"] == "cc"
        for d in (rec, ext, ide):
            assert ia.tem_a_impressao_atual(d["analysis_fingerprint"]) and d["index_facts"]

    async def test_os_metadados_profissionais_e_o_directorio(self, bd):
        await tres_documentos(bd)
        await correr()
        meta = await bd.process_professional_metadata.find_one({"process_id": PID})
        assert meta["network_id"] == "rede-A" and len(meta["jobs"]) == 1
        j = meta["jobs"][0]
        assert j["employer_name"]["value"] == "Empresa Simulada, Lda"
        assert j["net_salary"]["value"] == "1000.00"            # Decimal serializado em texto, nunca float
        assert meta["has_pending_review"] is False
        emp = await bd.employers.find({}).to_list(10)
        assert len(emp) == 1 and emp[0]["name"] == "Empresa Simulada, Lda"
        assert set(emp[0]) - {"_id"} == {"nif", "name", "name_normalizado", "first_seen_at"}

    async def test_nada_pessoal_fica_em_lado_nenhum(self, bd):
        await tres_documentos(bd)
        await correr()
        tudo = ""
        # (`task_logs.process_name` é do TaskLog genérico, anterior ao Index: fica fora desta afirmação)
        for col in ("document_metadata", "process_professional_metadata", "employers", "process_index_alerts",
                    "process_ai_log", "notifications"):
            tudo += repr(await bd[col].find({}).to_list(100))
        assert "Ana Cliente" not in tudo and "123456789" not in tudo

    async def test_a_ia_nunca_toca_na_ficha(self, bd):
        await tres_documentos(bd)
        antes = await bd.processes.find_one({"id": PID}, {"_id": 0})
        await correr()
        depois = await bd.processes.find_one({"id": PID}, {"_id": 0})
        mudou = {k for k in set(antes) | set(depois) if antes.get(k) != depois.get(k)}
        assert mudou <= {"has_pending_review", "index_alerts_open"}, mudou
        assert depois["is_indexed"] is False and depois["status"] == "indexacao"

    async def test_os_contadores_do_processo(self, bd):
        await tres_documentos(bd)
        await correr()
        p = await bd.processes.find_one({"id": PID})
        assert p["has_pending_review"] is False and p["index_alerts_open"] == 0

    async def test_o_log_da_ia_regista_cada_ficheiro(self, bd):
        await tres_documentos(bd)
        await correr()
        linhas = await bd.process_ai_log.find({"process_id": PID}).to_list(20)
        assert len(linhas) == 3 and all(x["accao"] == "analisar" and x["estado"] == "sucesso" for x in linhas)
        assert all(x["gatilho"] == "manual" for x in linhas)
        # a Indexação é silenciosa: o log não leva o nome de quem carregou
        assert all(x["utilizador_nome"] is None and x["utilizador_id"] is None for x in linhas)

    async def test_a_notificacao_final_chega_a_quem_pediu_sem_nomes_nem_valores(self, bd):
        await tres_documentos(bd)
        await correr()
        n = await bd.notifications.find({"user_id": "u-index"}).to_list(10)
        assert len(n) == 1 and n[0]["type"] == "index_analysis_done" and n[0]["link"] == f"/index/{PID}"
        assert "#42" in n[0]["title"] and "3 documento(s) analisado(s)" in n[0]["message"]
        assert "Ana" not in n[0]["message"] and "1000" not in n[0]["message"]


# ── uma vez por ficheiro ───────────────────────────────────────────────────
class TestUmaVezPorFicheiro:
    async def test_a_segunda_corrida_salta_tudo_sem_chamar_o_modelo(self, bd):
        await tres_documentos(bd)
        await correr()
        with patch.object(jobs, "analisar_documento", AsyncMock(side_effect=AssertionError("pagou outra vez"))):
            r = await correr()
        t = await tarefa(bd, r["task_id"])
        assert t["status"] == "completed" and t["result_data"]["analisados"] == 0 and t["result_data"]["saltados"] == 3
        saltos = await bd.process_ai_log.find({"estado": "saltado", "motivo": "ja_analisado"}).to_list(10)
        assert len(saltos) == 3

    async def test_force_volta_a_analisar(self, bd):
        await tres_documentos(bd)
        await correr()
        r = await correr(force=True)
        assert (await tarefa(bd, r["task_id"]))["result_data"]["analisados"] == 3

    async def test_um_ficheiro_substituido_no_mesmo_caminho_volta_a_ser_analisado(self, bd):
        r_id, _, _ = await tres_documentos(bd)
        await correr()
        caminho = (await bd.document_metadata.find_one({"id": r_id}))["s3_path"]
        S3[caminho] = b"outro conteudo completamente diferente"
        r = await correr()
        assert (await tarefa(bd, r["task_id"]))["result_data"]["analisados"] == 1

    async def test_uma_impressao_de_um_esquema_antigo_nao_conta(self, bd):
        await tres_documentos(bd)
        await correr()
        with patch.object(ia, "ESQUEMA_VERSAO", "99"), patch.object(jobs, "tem_a_impressao_atual", ia.tem_a_impressao_atual):
            r = await correr()
        assert (await tarefa(bd, r["task_id"]))["result_data"]["analisados"] == 3


# ── a pessoa dispõe ────────────────────────────────────────────────────────
class TestAPessoaDispoe:
    async def test_uma_edicao_humana_sobrevive_a_reanalise_forcada(self, bd):
        await tres_documentos(bd)
        await correr()
        await bd.process_professional_metadata.update_one(
            {"process_id": PID},
            {"$set": {"jobs.0.job_title": {"value": "Diretora", "needs_review": False, "edited_by_human": True,
                                           "confidence": None, "source": None}}},
        )
        await correr(force=True)
        meta = await bd.process_professional_metadata.find_one({"process_id": PID})
        assert meta["jobs"][0]["job_title"]["value"] == "Diretora"
        assert meta["jobs"][0]["job_title"]["edited_by_human"] is True
        assert meta["jobs"][0]["employer_name"]["value"] == "Empresa Simulada, Lda"  # o resto actualiza-se

    async def test_um_alerta_dispensado_nao_ressuscita(self, bd):
        await tres_documentos(bd)
        # extrato SEM o crédito do ordenado → recibo_sem_credito
        real = ia.analisar_documento

        async def sem_credito(**kw):
            r = await real(**kw)
            if kw["tipo"] == ia.TIPO_EXTRATO:
                r.factos["movimentos"] = [{**r.factos["movimentos"][0], "v": "5.00"}]
            return r

        with patch.object(jobs, "analisar_documento", sem_credito):
            await correr()
        alerta = await bd.process_index_alerts.find_one({"code": "recibo_sem_credito"})
        assert alerta and alerta["severity"] == "aviso" and alerta["network_id"] == "rede-A"
        # (o saldo do extrato falseado também deixa de bater: dois alertas abertos)
        assert {a["code"] for a in await bd.process_index_alerts.find({}).to_list(10)} == {"recibo_sem_credito", "saldo_nao_bate"}
        assert (await bd.processes.find_one({"id": PID}))["index_alerts_open"] == 2

        await bd.process_index_alerts.update_one({"id": alerta["id"]}, {"$set": {"dismissed_by_human": True}})
        with patch.object(jobs, "analisar_documento", sem_credito):
            await correr(force=True)
        todos = await bd.process_index_alerts.find({"code": "recibo_sem_credito"}).to_list(10)
        assert len(todos) == 1 and todos[0]["dismissed_by_human"] is True
        # o dispensado não conta como aberto; o outro, que ninguém dispensou, continua
        assert (await bd.processes.find_one({"id": PID}))["index_alerts_open"] == 1

    async def test_campos_em_duvida_acendem_a_revisao_e_nao_entram_no_directorio(self, bd):
        await tres_documentos(bd)
        real = ia.analisar_documento

        async def duvidoso(**kw):
            r = await real(**kw)
            if kw["tipo"] == ia.TIPO_RECIBO:
                r.job.employer_nif.needs_review = True
                r.job.job_title.value, r.job.job_title.needs_review = None, True
            return r

        with patch.object(jobs, "analisar_documento", duvidoso):
            await correr()
        p = await bd.processes.find_one({"id": PID})
        assert p["has_pending_review"] is True
        assert await bd.employers.count_documents({}) == 0       # NIF em dúvida não polui o directório global
        n = await bd.notifications.find_one({"user_id": "u-index"})
        assert "campo(s) a rever" in n["message"]


# ── zero bloqueios ─────────────────────────────────────────────────────────
class TestZeroBloqueios:
    async def test_a_ia_em_baixo_nao_falha_o_job_nem_toca_no_processo(self, bd):
        await tres_documentos(bd)
        erro = RuntimeError("Rate limit 429 sk-SEGREDO")
        with patch("services.ai_document.call_openai_api", AsyncMock(side_effect=erro)), \
             patch("services.index_ai._mensagens", return_value=([], False, 1.0)), \
             patch.object(ia, "resolver_modelo", AsyncMock(return_value="m")), \
             patch.object(ia, "_registar_uso", AsyncMock()), \
             patch.dict(os.environ, {"INDEX_AI_PROVIDER": "openai"}):
            r = await correr()
        t = await tarefa(bd, r["task_id"])
        assert t["status"] == "completed" and t["result_data"]["falhas"] == 3 and t["result_data"]["analisados"] == 0
        p = await bd.processes.find_one({"id": PID})
        assert p["is_indexed"] is False and p["index_status"] == "in_review"
        # as falhas ficam no Log da IA com um CÓDIGO, nunca o texto do erro
        linhas = await bd.process_ai_log.find({"estado": "falha"}).to_list(10)
        assert len(linhas) == 3 and {x["motivo"] for x in linhas} == {"limite_do_fornecedor"}
        assert "SEGREDO" not in repr(await bd.process_ai_log.find({}).to_list(10) + [t])
        # …e viram um alerta INFORMATIVO, que nunca bloqueia
        alerta = await bd.process_index_alerts.find_one({"code": "analise_falhou"})
        assert alerta["severity"] == "info"

    async def test_um_ficheiro_que_falha_nao_para_os_outros(self, bd):
        await tres_documentos(bd)
        real = ia.analisar_documento

        async def uma_falha(**kw):
            if kw["tipo"] == ia.TIPO_EXTRATO:
                return ia.ResultadoDaAnalise(ok=False, tipo=kw["tipo"], motivo="erro_da_ia")
            return await real(**kw)

        with patch.object(jobs, "analisar_documento", uma_falha):
            r = await correr()
        res = (await tarefa(bd, r["task_id"]))["result_data"]
        assert res["analisados"] == 2 and res["falhas"] == 1

    async def test_s3_em_baixo_e_uma_falha_do_ficheiro_nao_do_job(self, bd):
        await tres_documentos(bd)
        S3.clear()
        r = await correr()
        t = await tarefa(bd, r["task_id"])
        assert t["status"] == "completed" and t["result_data"]["falhas"] == 3

    async def test_ficheiro_demasiado_grande_fica_de_fora_sem_falha(self, bd):
        await tres_documentos(bd)

        async def grande(caminho):
            return None, "demasiado_grande"

        with patch.object(jobs, "_ler_ficheiro", grande):
            r = await correr()
        res = (await tarefa(bd, r["task_id"]))["result_data"]
        assert res["falhas"] == 0 and res["saltados"] == 3

    async def test_processo_inexistente_falha_o_job_e_liberta_a_chave(self, bd):
        r = await jobs.iniciar_analise("nao-existe", USER)
        await aguardar_tarefas_pendentes()
        t = await tarefa(bd, r["task_id"])
        assert t["status"] == "failed" and "index_job_key" not in t

    async def test_uma_excepcao_inesperada_nunca_deixa_o_job_preso(self, bd):
        await tres_documentos(bd)
        with patch.object(jobs, "concluir_resultados", AsyncMock(side_effect=RuntimeError("bd"))):
            r = await correr()
        t = await tarefa(bd, r["task_id"])
        assert t["status"] == "failed" and "index_job_key" not in t
        assert "bd" not in (t["error_message"] or "")            # o texto interno não vai para o ecrã
        # e outro pode nascer
        r2 = await jobs.iniciar_analise(PID, USER)
        assert r2["iniciado"] is True
        await aguardar_tarefas_pendentes()


# ── um job activo por (processo, tipo) ─────────────────────────────────────
class TestUmJobActivo:
    async def test_dois_pedidos_em_simultaneo_so_um_corre(self, bd):
        await tres_documentos(bd)
        a, b, c = await asyncio.gather(*(jobs.iniciar_analise(PID, USER) for _ in range(3)))
        iniciados = [x for x in (a, b, c) if x["iniciado"]]
        assert len(iniciados) == 1
        assert {x["task_id"] for x in (a, b, c)} == {iniciados[0]["task_id"]}   # os outros apontam para o que corre
        await aguardar_tarefas_pendentes()

    async def test_so_um_documento_de_job_ficou_activo_na_base_de_dados(self, bd):
        await tres_documentos(bd)
        await asyncio.gather(*(jobs.reivindicar_job(PID, TaskType.INDEX_ANALYSIS, "u") for _ in range(6)))
        assert await bd.task_logs.count_documents({"index_job_key": f"{PID}:INDEX_ANALYSIS"}) == 1

    async def test_os_perdedores_da_corrida_cancelam_o_seu_tasklog(self, bd):
        await asyncio.gather(*(jobs.reivindicar_job(PID, TaskType.INDEX_ANALYSIS, "u") for _ in range(4)))
        estados = [t["status"] for t in await bd.task_logs.find({}).to_list(20)]
        assert estados.count("cancelled") + estados.count("pending") == len(estados)
        assert estados.count("pending") == 1

    async def test_tipos_diferentes_convivem(self, bd):
        a, _ = await jobs.reivindicar_job(PID, TaskType.INDEX_ANALYSIS, "u")
        b, _ = await jobs.reivindicar_job(PID, TaskType.INDEX_SANITIZE, "u")
        assert a and b and a != b

    async def test_processos_diferentes_convivem(self, bd):
        a, _ = await jobs.reivindicar_job("p1", TaskType.INDEX_ANALYSIS, "u")
        b, _ = await jobs.reivindicar_job("p2", TaskType.INDEX_ANALYSIS, "u")
        assert a and b

    async def test_terminado_o_job_outro_pode_nascer(self, bd):
        await tres_documentos(bd)
        await correr()
        r = await jobs.iniciar_analise(PID, USER)
        assert r["iniciado"] is True
        await aguardar_tarefas_pendentes()

    async def test_um_job_morto_a_meio_liberta_se_ao_fim_do_prazo(self, bd):
        task_id, _ = await jobs.reivindicar_job(PID, TaskType.INDEX_ANALYSIS, "u")
        # o servidor caiu: o job deixou de bater há mais do que o prazo
        antigo = (datetime.now(timezone.utc) - timedelta(minutes=jobs.PRAZO_SEM_BATIMENTO_MINUTOS + 1)).isoformat()
        await bd.task_logs.update_one({"task_id": task_id}, {"$set": {jobs.CAMPO_DO_BATIMENTO: antigo}})
        novo, existente = await jobs.reivindicar_job(PID, TaskType.INDEX_ANALYSIS, "u")
        assert novo and existente is None and novo != task_id

    async def test_um_pedido_repetido_nao_cria_tasklogs_nem_eventos(self, bd):
        # o pré-teste evita criar (e anunciar ao ecrã) um TaskLog que só ia ser cancelado
        await jobs.reivindicar_job(PID, TaskType.INDEX_ANALYSIS, "u")
        for _ in range(3):
            await jobs.reivindicar_job(PID, TaskType.INDEX_ANALYSIS, "u")
        assert await bd.task_logs.count_documents({}) == 1

    async def test_um_job_recente_nao_se_liberta(self, bd):
        a, _ = await jobs.reivindicar_job(PID, TaskType.INDEX_ANALYSIS, "u")
        b, existente = await jobs.reivindicar_job(PID, TaskType.INDEX_ANALYSIS, "u")
        assert b is None and existente == a


# ── âmbito dos ficheiros ───────────────────────────────────────────────────
class TestOQueSeAnalisa:
    async def test_so_o_que_o_index_le(self, bd):
        await tres_documentos(bd)
        await doc(bd, "caderneta_predial.pdf", categoria="Imóvel", sub="Caderneta Predial")
        r = await correr()
        assert (await tarefa(bd, r["task_id"]))["result_data"]["analisados"] == 3

    async def test_ficheiros_purgados_nao_se_reanalisam(self, bd):
        # um original eliminado já não tem bytes para ler: não vai ao modelo
        r_id, _, _ = await tres_documentos(bd)
        await bd.document_metadata.update_one({"id": r_id}, {"$set": {"file_state": "purgado"}})
        r = await correr()
        assert (await tarefa(bd, r["task_id"]))["result_data"]["analisados"] == 2

    async def test_os_dados_de_um_original_purgado_continuam_a_contar(self, bd):
        """Inverte a regra da Fase 2 («um purgado deixa de contar»): eliminar os BYTES do original não
        torna falsos os dados que se leram dele — senão a purga apagava os metadados profissionais."""
        r_id, _, _ = await tres_documentos(bd)
        await correr()
        await bd.document_metadata.update_one({"id": r_id}, {"$set": {"file_state": "purgado"}})
        await correr()
        meta = await bd.process_professional_metadata.find_one({"process_id": PID})
        assert len(meta["jobs"]) == 1

    async def test_o_pdf_limpo_nao_e_reanalisado_nem_conta_duas_vezes(self, bd):
        r_id, _, _ = await tres_documentos(bd)
        await correr()
        await doc(bd, "recibo_vencimento_setembro_limpo.pdf", categoria="Rendimentos", sub="Recibo de Vencimento",
                  is_clean_pdf=True, clean_of=[r_id])
        r = await correr()
        assert (await tarefa(bd, r["task_id"]))["result_data"]["analisados"] == 0
        assert len((await bd.process_professional_metadata.find_one({"process_id": PID}))["jobs"]) == 1

    async def test_um_recibo_apagado_deixa_de_contar_nos_metadados(self, bd):
        r_id, _, _ = await tres_documentos(bd)
        await correr()
        assert len((await bd.process_professional_metadata.find_one({"process_id": PID}))["jobs"]) == 1
        await bd.document_metadata.delete_one({"id": r_id})
        await correr()
        assert (await bd.process_professional_metadata.find_one({"process_id": PID}))["jobs"] == []

    async def test_so_os_ficheiros_do_proprio_processo(self, bd):
        await tres_documentos(bd)
        await doc(bd, "recibo_vencimento.pdf", pid="outro", categoria="Rendimentos", sub="Recibo de Vencimento")
        r = await correr()
        assert (await tarefa(bd, r["task_id"]))["result_data"]["analisados"] == 3

    async def test_sem_documentos_conclui_sem_alertas(self, bd):
        r = await correr()
        t = await tarefa(bd, r["task_id"])
        assert t["status"] == "completed" and t["result_data"]["analisados"] == 0
        meta = await bd.process_professional_metadata.find_one({"process_id": PID})
        assert meta["jobs"] == [] and meta["has_pending_review"] is False


# ── o directório de entidades ──────────────────────────────────────────────
class TestDirectorio:
    async def test_o_primeiro_nome_ganha_com_mongo_real(self, bd):
        from models.index_module import CampoRevisavel, TrabalhoProfissional

        def j(nome):
            return TrabalhoProfissional(job_id="x", employer_nif=CampoRevisavel(value="501964843"),
                                        employer_name=CampoRevisavel(value=nome))

        await bd.employers.create_index("nif", unique=True)
        assert await st.registar_entidades([j("Acme, Lda")]) == 1
        assert await st.registar_entidades([j("Outro Nome")]) == 0
        docs = await bd.employers.find({}).to_list(10)
        assert len(docs) == 1 and docs[0]["name"] == "Acme, Lda"

    async def test_nif_incoerente_com_a_entidade_conhecida_gera_alerta(self, bd):
        await bd.employers.insert_one({"nif": "509442013", "name": "Empresa Simulada", "name_normalizado": "empresa simulada"})
        await tres_documentos(bd)
        await correr()
        # a simulação usa 501964843/509442013/500000000 conforme o nome do ficheiro; força um NIF diferente do conhecido
        meta_nif = (await bd.process_professional_metadata.find_one({"process_id": PID}))["jobs"][0]["employer_nif"]["value"]
        codigos = {a["code"] for a in await bd.process_index_alerts.find({}).to_list(20)}
        assert ("nif_entidade_incoerente" in codigos) == (meta_nif != "509442013")


# ── ficheiros que ficavam por analisar (QA Index, Out 2026) ────────────────
def _classificador(tipo):
    """Falseia a classificação por CONTEÚDO (a IA real) e conta as chamadas."""
    chamada = AsyncMock(return_value=ia.ClassificacaoDoDocumento(tipo=tipo))
    return patch.object(jobs, "classificar_documento", chamada), chamada


async def correr_um(documento_id, force=True):
    r = await jobs.iniciar_analise(PID, USER, force=force, documento_id=documento_id)
    await aguardar_tarefas_pendentes()
    return r


class TestFicheirosSemPistasNoNome:
    async def test_um_recibo_chamado_07_julho_e_classificado_pelo_conteudo_e_analisado(self, bd):
        d = await doc(bd, "07-Julho.pdf")
        ctx, chamada = _classificador(ia.TIPO_RECIBO)
        with ctx:
            r = await correr()
        assert chamada.await_count == 1
        assert (await tarefa(bd, r["task_id"]))["result_data"]["analisados"] == 1
        gravado = await bd.document_metadata.find_one({"id": d})
        assert gravado["index_classified_type"] == ia.TIPO_RECIBO and gravado["ai_category"] == "Financeiros"
        assert ia.tem_a_impressao_atual(gravado["analysis_fingerprint"])

    async def test_a_classificacao_e_uma_vez_por_conteudo_tambem_quando_e_outro(self, bd):
        d = await doc(bd, "Mapa_CRC.pdf")
        ctx, chamada = _classificador(ia.TIPO_OUTRO)
        with ctx:
            r1 = await correr()
            r2 = await correr()
        assert chamada.await_count == 1                           # a segunda corrida não paga outra vez
        for r in (r1, r2):
            res = (await tarefa(bd, r["task_id"]))["result_data"]
            assert res["analisados"] == 0 and res["falhas"] == 0 and res["ignorados"] == 1
        assert (await bd.document_metadata.find_one({"id": d}))["index_classified_type"] == ia.TIPO_OUTRO
        assert await bd.process_index_alerts.count_documents({"code": "analise_falhou"}) == 0

    async def test_nao_saber_o_tipo_nao_se_grava(self, bd):
        d = await doc(bd, "digitalizacao.pdf")
        ctx, _ = _classificador(None)                              # IA em baixo / motor simulado
        with ctx:
            await correr()
        assert "index_classified_type" not in await bd.document_metadata.find_one({"id": d})

    async def test_um_ficheiro_sem_tipo_que_nao_se_le_nao_vira_alerta(self, bd):
        d = await doc(bd, "certidao.pdf")
        S3.pop((await bd.document_metadata.find_one({"id": d}))["s3_path"])
        ctx, chamada = _classificador(ia.TIPO_RECIBO)
        with ctx:
            r = await correr()
        assert chamada.await_count == 0
        assert (await tarefa(bd, r["task_id"]))["result_data"]["falhas"] == 0
        assert await bd.process_index_alerts.count_documents({}) == 0


class TestAnalisarUmFicheiro:
    async def test_so_o_ficheiro_pedido_e_sempre_de_novo(self, bd):
        r_id, e_id, _ = await tres_documentos(bd)
        await correr()
        with patch.object(jobs, "analisar_documento", wraps=ia.analisar_documento) as chamada:
            r = await correr_um(e_id)
        assert chamada.await_count == 1 and chamada.await_args.kwargs["document_id"] == e_id
        assert (await tarefa(bd, r["task_id"]))["result_data"]["analisados"] == 1
        # os metadados do processo continuam a contar com TUDO o que está analisado
        assert len((await bd.process_professional_metadata.find_one({"process_id": PID}))["jobs"]) == 1

    async def test_sem_tipo_reconhecivel_falha_com_o_motivo_e_o_caminho(self, bd):
        d = await doc(bd, "scan001.pdf")
        ctx, _ = _classificador(ia.TIPO_OUTRO)
        with ctx:
            await correr_um(d)
        alerta = await bd.process_index_alerts.find_one({"code": "analise_falhou"})
        assert alerta["refs"] == [{"document_id": d, "page": None}]
        assert "Analisar como" in alerta["detail"]

    async def test_analisar_um_mantem_a_falha_dos_outros(self, bd):
        _, e_id, i_id = await tres_documentos(bd)
        real = ia.analisar_documento

        async def extrato_cortado(**kw):
            if kw["tipo"] == ia.TIPO_EXTRATO:
                return ia.ResultadoDaAnalise(ok=False, tipo=kw["tipo"], motivo="resposta_incompleta")
            return await real(**kw)

        with patch.object(jobs, "analisar_documento", extrato_cortado):
            await correr()
        alerta = await bd.process_index_alerts.find_one({"code": "analise_falhou"})
        assert alerta["refs"][0]["document_id"] == e_id and "cortada" in alerta["detail"]
        await correr_um(i_id)                                      # outro ficheiro: a falha do extrato fica
        abertos = await bd.process_index_alerts.find({"code": "analise_falhou"}).to_list(10)
        assert [a["refs"][0]["document_id"] for a in abertos] == [e_id] and "cortada" in abertos[0]["detail"]
        await correr_um(e_id)                                      # agora o próprio: resolve-se
        assert await bd.process_index_alerts.count_documents({"code": "analise_falhou"}) == 0

    async def test_uma_excepcao_num_ficheiro_nao_deixa_os_outros_por_analisar(self, bd):
        """Antes, uma excepção a meio matava o job: TODOS ficavam «Por analisar» e sem alerta nenhum."""
        _, e_id, _ = await tres_documentos(bd)
        real = ia.analisar_documento

        async def rebenta(**kw):
            if kw["tipo"] == ia.TIPO_EXTRATO:
                raise KeyError("valor inesperado")
            return await real(**kw)

        with patch.object(jobs, "analisar_documento", rebenta):
            r = await correr()
        t = await tarefa(bd, r["task_id"])
        assert t["status"] == "completed"
        assert t["result_data"]["analisados"] == 2 and t["result_data"]["falhas"] == 1
        alerta = await bd.process_index_alerts.find_one({"code": "analise_falhou"})
        assert alerta["refs"][0]["document_id"] == e_id and alerta["detail"]



# ── jobs mortos, repetição e paralelismo (análise que «demorava mais de 4h», Nov 2026) ─────────
def _ha(minutos: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(minutes=minutos)).isoformat()


async def _matar(bd, task_id, minutos=None):
    """O processo que corria o job morreu: o TaskLog fica `processing` e deixa de bater."""
    minutos = jobs.PRAZO_SEM_BATIMENTO_MINUTOS + 1 if minutos is None else minutos
    await bd.task_logs.update_one({"task_id": task_id},
                                  {"$set": {"status": "processing", jobs.CAMPO_DO_BATIMENTO: _ha(minutos)}})


class TestJobsMortos:
    async def test_um_job_que_ainda_bate_continua_activo(self, bd):
        task_id, _ = await jobs.reivindicar_job(PID, TaskType.INDEX_ANALYSIS, "u")
        await bd.task_logs.update_one({"task_id": task_id}, {"$set": {"created_at": _ha(240)}})  # longo mas vivo
        assert (await jobs.job_activo(PID, TaskType.INDEX_ANALYSIS))["task_id"] == task_id
        novo, existente = await jobs.reivindicar_job(PID, TaskType.INDEX_ANALYSIS, "u")
        assert novo is None and existente == task_id

    async def test_um_job_morto_deixa_de_bloquear_o_ecra(self, bd):
        """O bug: o ecrã dizia «Já há uma análise a correr» (botões bloqueados) enquanto a chave existisse."""
        task_id, _ = await jobs.reivindicar_job(PID, TaskType.INDEX_ANALYSIS, "u")
        await _matar(bd, task_id)
        assert await jobs.job_activo(PID, TaskType.INDEX_ANALYSIS) is None

    async def test_um_job_antigo_sem_batimento_conta_pelo_prazo_da_criacao(self, bd):
        task_id, _ = await jobs.reivindicar_job(PID, TaskType.INDEX_ANALYSIS, "u")
        await bd.task_logs.update_one({"task_id": task_id}, {"$unset": {jobs.CAMPO_DO_BATIMENTO: ""}})
        assert await jobs.job_activo(PID, TaskType.INDEX_ANALYSIS)          # recente: vivo
        await bd.task_logs.update_one({"task_id": task_id},
                                      {"$set": {"created_at": _ha(jobs.PRAZO_DO_JOB_MINUTOS + 1)}})
        assert await jobs.job_activo(PID, TaskType.INDEX_ANALYSIS) is None

    async def test_o_vigia_liberta_fecha_e_retoma_a_analise(self, bd):
        await bd.users.insert_one({"id": USER["id"], "name": USER["name"], "role": "indexacao"})
        await tres_documentos(bd)
        task_id, _ = await jobs.reivindicar_job(PID, TaskType.INDEX_ANALYSIS, USER["id"],
                                                metadata={"force": False, "gatilho": "manual"})
        await _matar(bd, task_id)
        contas = await jobs.retomar_jobs_mortos()
        await aguardar_tarefas_pendentes()
        assert contas == {"libertados": 1, "retomados": 1}
        morto = await tarefa(bd, task_id)
        assert morto["status"] == "failed" and "index_job_key" not in morto
        retoma = await bd.task_logs.find_one({"task_id": {"$ne": task_id}}, {"_id": 0})
        assert retoma["status"] == "completed" and retoma["result_data"]["analisados"] == 3
        assert retoma["metadata"]["retomas"] == 1 and retoma["user_id"] == USER["id"]

    async def test_um_job_que_morre_sempre_nao_entra_em_ciclo(self, bd):
        task_id, _ = await jobs.reivindicar_job(PID, TaskType.INDEX_ANALYSIS, "u",
                                                metadata={"retomas": jobs.RETOMAS_MAXIMAS})
        await _matar(bd, task_id)
        assert await jobs.retomar_jobs_mortos() == {"libertados": 1, "retomados": 0}
        assert await bd.task_logs.count_documents({}) == 1

    async def test_dois_vigias_ao_mesmo_tempo_retomam_uma_vez(self, bd):
        task_id, _ = await jobs.reivindicar_job(PID, TaskType.INDEX_ANALYSIS, "u")
        await _matar(bd, task_id)
        a, b = await asyncio.gather(jobs.retomar_jobs_mortos(), jobs.retomar_jobs_mortos())
        await aguardar_tarefas_pendentes()
        assert a["libertados"] + b["libertados"] == 1 and a["retomados"] + b["retomados"] == 1

    async def test_um_job_vivo_nao_e_tocado_pelo_vigia(self, bd):
        task_id, _ = await jobs.reivindicar_job(PID, TaskType.INDEX_ANALYSIS, "u")
        assert await jobs.retomar_jobs_mortos() == {"libertados": 0, "retomados": 0}
        assert (await tarefa(bd, task_id))["index_job_key"]

    async def test_o_batimento_actualiza_enquanto_o_job_corre(self, bd, monkeypatch):
        task_id, _ = await jobs.reivindicar_job(PID, TaskType.INDEX_ANALYSIS, "u")
        await bd.task_logs.update_one({"task_id": task_id}, {"$set": {jobs.CAMPO_DO_BATIMENTO: _ha(60)}})
        monkeypatch.setattr(jobs, "BATIMENTO_SEGUNDOS", 0.01)
        async with jobs.batimento(task_id):
            await asyncio.sleep(0.05)
        assert (await tarefa(bd, task_id))[jobs.CAMPO_DO_BATIMENTO] > _ha(1)


class TestPedidoAMeioDeUmaAnalise:
    async def test_um_ficheiro_carregado_a_meio_e_analisado_no_fim(self, bd):
        """O bug: o upload a meio dava «já a correr» e o ficheiro novo ficava «Por analisar» indefinidamente."""
        await doc(bd, "recibo_vencimento_agosto.pdf", categoria="Rendimentos", sub="Recibo de Vencimento")
        real = ia.analisar_documento
        entrou, solta = asyncio.Event(), asyncio.Event()

        async def lento(**kw):
            entrou.set()
            await solta.wait()
            return await real(**kw)

        with patch.object(jobs, "analisar_documento", lento):
            primeiro = await jobs.iniciar_analise(PID, USER)
            await entrou.wait()
            novo = await doc(bd, "recibo_vencimento_setembro.pdf", categoria="Rendimentos", sub="Recibo de Vencimento")
            pedido = await jobs.iniciar_analise(PID, USER, gatilho="automatico")   # o upload
            assert pedido == {"task_id": primeiro["task_id"], "iniciado": False}
            solta.set()
            await aguardar_tarefas_pendentes()
            await aguardar_tarefas_pendentes()
        d = await bd.document_metadata.find_one({"id": novo})
        assert ia.tem_a_impressao_atual(d.get("analysis_fingerprint"))
        assert await bd.task_logs.count_documents({"status": "completed"}) == 2
        assert await bd.task_logs.count_documents({"index_job_key": {"$exists": True}}) == 0

    async def test_sem_pedidos_a_meio_nao_ha_segunda_corrida(self, bd):
        await tres_documentos(bd)
        await correr()
        await aguardar_tarefas_pendentes()
        assert await bd.task_logs.count_documents({}) == 1


class TestFicheirosEmParalelo:
    async def test_os_ficheiros_vao_a_ia_varios_de_cada_vez_com_tecto(self, bd, monkeypatch):
        for n in range(7):
            await doc(bd, f"recibo_vencimento_{n}.pdf", categoria="Rendimentos", sub="Recibo de Vencimento")
        monkeypatch.setenv("INDEX_FICHEIROS_EM_SIMULTANEO", "3")
        real = ia.analisar_documento
        agora = maximo = 0

        async def conta(**kw):
            nonlocal agora, maximo
            agora += 1
            maximo = max(maximo, agora)
            await asyncio.sleep(0.02)
            agora -= 1
            return await real(**kw)

        with patch.object(jobs, "analisar_documento", conta):
            r = await correr()
        t = await tarefa(bd, r["task_id"])
        assert t["status"] == "completed" and t["result_data"]["analisados"] == 7
        assert maximo == 3

    @pytest.mark.parametrize("valor,esperado", [(None, 3), ("1", 1), ("5", 5), ("99", 6), ("0", 3), ("x", 3)])
    async def test_a_configuracao(self, valor, esperado):
        ambiente = {} if valor is None else {"INDEX_FICHEIROS_EM_SIMULTANEO": valor}
        assert jobs.ficheiros_em_simultaneo(ambiente) == esperado

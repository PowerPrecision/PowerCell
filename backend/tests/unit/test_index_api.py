"""API do módulo Index (Lote 12, Fase 3): RBAC, fila, bancada, edição, alertas, fecho.

O que se afirma, e porquê:
  · **RBAC:** Master/Admin/CEO/Diretor/Indexação entram; Consultor, Intermediário, Administrativo e
    Parceiro levam 403 e o handler NUNCA corre. A regra QA-5 (IA manual só para os altos perfis)
    não se altera: as duas listas diferem num único papel (Indexação).
  · **Zero bloqueios:** «marcar como indexado» não pergunta pela IA, por campos em dúvida nem por
    alertas; um NIF que não se aplica volta em `rejected` e a indexação segue.
  · **Rede:** a fila lista só o âmbito de PROCESSOS de quem pergunta.
  · **A edição humana sobrevive à reanálise** e o código continua a reforçar o NIF.
"""
from __future__ import annotations

import ast
import inspect
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from models.auth import UserRole
from routes import index_module
from services import index_access as acesso
from services import index_api as api
from services import index_finalize as fin
from services import index_jobs as jobs
from services import index_status as ist
from services import index_store as st
from services.document_ai_access import PAPEIS_DE_GESTAO_DA_IA
from services.tenant_network import TenantScope
from tests.unit.helpers_fonte import codigo_da_funcao_sem_comentarios, codigo_sem_comentarios

PID = "proc-1"
INDEXADOR = {"id": "u-idx", "name": "Ivo Index", "role": "indexacao"}
GESTOR = {"id": "u-dir", "name": "Diana", "role": "diretor"}

NIF_VALIDO = "501964843"   # NIF português com dígito de controlo válido
NIF_INVALIDO = "501964844"


def _trabalho(job_id="job_a", **campos):
    base = {
        "job_id": job_id,
        "employer_nif": {"value": NIF_VALIDO, "needs_review": False, "confidence": "alta"},
        "employer_name": {"value": "Acme Lda", "needs_review": False, "confidence": "alta"},
        "job_title": {"value": None, "needs_review": True},
        "net_salary": {"value": "1234.50", "needs_review": False, "confidence": "alta"},
        "contract_type": {"value": "efetivo", "needs_review": False},
        "period": "2026-09",
        "source_document_ids": ["d-1"],
    }
    base.update(campos)
    return base


def _modulos(fake_db):
    """Cada módulo importou `db` para si (a armadilha da ordem de import): patcha-se um a um."""
    from services import audit_trail_service as audit

    return [patch.object(m, "db", fake_db) for m in (api, st, ist, jobs, fin, audit)] + [patch("database.db", fake_db)]


class _Contexto:
    def __init__(self, fake_db):
        self.patches = _modulos(fake_db)

    def __enter__(self):
        for p in self.patches:
            p.start()
        return self

    def __exit__(self, *a):
        for p in reversed(self.patches):
            p.stop()


# ====================================================================
# 1. RBAC
# ====================================================================
class TestAcesso:
    def test_a_lista_do_index_e_a_da_gestao_mais_indexacao(self):
        assert set(acesso.PAPEIS_DE_IA_DO_INDEX) - set(PAPEIS_DE_GESTAO_DA_IA) == {UserRole.INDEXACAO}
        assert set(PAPEIS_DE_GESTAO_DA_IA) <= set(acesso.PAPEIS_DE_IA_DO_INDEX)

    def test_a_regra_qa5_nao_foi_alargada(self):
        assert UserRole.INDEXACAO not in PAPEIS_DE_GESTAO_DA_IA

    @pytest.mark.asyncio
    @pytest.mark.parametrize("papel", ["master", "admin", "ceo", "diretor", "indexacao"])
    async def test_entram(self, papel):
        user = {"id": "u", "role": papel}
        with patch("services.auth.get_effective_role_async", AsyncMock(return_value=papel)):
            assert await index_module._acesso(MagicMock(), user) == user

    @pytest.mark.asyncio
    @pytest.mark.parametrize("papel", ["consultor", "intermediario", "administrativo", "parceiro"])
    async def test_o_resto_leva_403(self, papel):
        with patch("services.auth.get_effective_role_async", AsyncMock(return_value=papel)):
            with pytest.raises(HTTPException) as e:
                await index_module._acesso(MagicMock(), {"id": "u", "role": papel})
        assert e.value.status_code == 403

    @pytest.mark.parametrize("papel,esperado", [("indexacao", True), ("master", False), ("consultor", False)])
    def test_o_upload_do_index_so_conta_para_a_indexacao(self, papel, esperado):
        assert acesso.e_upload_do_index({"role": papel}) is esperado
        assert acesso.e_upload_do_index({"role": "consultor", "effective_role": papel}) is esperado
        assert acesso.e_upload_do_index(None) is False


class TestInventarioDasRotas:
    """Por AST: uma rota nova do Index nasce com a guarda, o limite e a assinatura certa."""

    @pytest.fixture(scope="class")
    def rotas(self):
        arvore = ast.parse(codigo_sem_comentarios(inspect.getsource(index_module)))
        achadas = []
        for no in ast.walk(arvore):
            if not isinstance(no, ast.AsyncFunctionDef):
                continue
            decs = [ast.unparse(d) for d in no.decorator_list]
            if not any(d.startswith("router.") for d in decs):
                continue
            achadas.append((no, decs))
        return achadas

    def test_o_leitor_ve_as_rotas(self, rotas):
        assert len(rotas) >= 10, "o leitor ficou cego"

    def test_todas_levam_a_guarda_de_papel(self, rotas):
        for no, _ in rotas:
            assert "Depends(_acesso)" in ast.unparse(no.args), no.name

    def test_todas_limitadas_com_request_e_response(self, rotas):
        for no, decs in rotas:
            assert any("limiter.limit" in d for d in decs), no.name
            nomes = [a.arg for a in no.args.args]
            assert "request" in nomes and "response" in nomes, no.name

    def test_o_router_tem_rede_antes_do_estado_fechado(self):
        from services.process_closed_guard import exigir_processo_editavel
        from services.process_scope_guard import exigir_processo_no_ambito

        deps = [d.dependency for d in index_module.router.dependencies]
        assert deps.index(exigir_processo_no_ambito) < deps.index(exigir_processo_editavel)

    def test_o_router_esta_registado_no_servidor(self):
        fonte = open("server.py", encoding="utf-8").read()
        assert "app.include_router(index_module_router" in fonte


# ====================================================================
# 2. A FILA (por rede)
# ====================================================================
async def _semear_processos(fake):
    base = {"is_deleted": False, "is_indexed": False}
    await fake.processes.insert_many([
        {**base, "id": "a1", "network_id": "rede-A", "client_name": "Ana", "process_number": 1,
         "index_status": "pending", "created_at": "2026-10-01"},
        {**base, "id": "a2", "network_id": "rede-A", "client_name": "Bruno", "process_number": 2,
         "index_status": "in_review", "created_at": "2026-10-02"},
        {**base, "id": "b1", "network_id": "rede-B", "client_name": "Carla", "process_number": 3,
         "index_status": "pending", "created_at": "2026-10-01"},
        {**base, "id": "a3", "network_id": "rede-A", "client_name": "Diogo", "process_number": 4,
         "is_indexed": True, "index_status": "indexed", "has_pending_review": True, "indexed_at": "2026-10-05"},
        {**base, "id": "a4", "network_id": "rede-A", "client_name": "Eva", "process_number": 5,
         "is_indexed": True, "index_status": "indexed", "has_pending_review": False, "indexed_at": "2026-10-06"},
        {**base, "id": "a5", "network_id": "rede-A", "client_name": "Via Verde", "process_number": 6,
         "skip_index": True, "index_status": "indexed"},
    ])


class TestAFila:
    @pytest.mark.asyncio
    async def test_a_fila_de_espera_so_tem_o_que_falta_indexar_na_minha_rede(self, fake_async_db):
        await _semear_processos(fake_async_db)
        with _Contexto(fake_async_db), patch("services.tenant_network.resolve_vista_scope",
                                             AsyncMock(return_value=TenantScope(network_ids=("rede-A",)))):
            r = await api.run_get_index_queue(INDEXADOR, tab="pending")
        assert {p["id"] for p in r["items"]} == {"a1", "a2"}
        assert r["total"] == 2
        # o mais antigo primeiro: quem espera há mais tempo
        assert [p["id"] for p in r["items"]] == ["a1", "a2"]

    @pytest.mark.asyncio
    async def test_a_rede_B_nunca_aparece_na_fila_da_rede_A(self, fake_async_db):
        await _semear_processos(fake_async_db)
        with _Contexto(fake_async_db), patch("services.tenant_network.resolve_vista_scope",
                                             AsyncMock(return_value=TenantScope(network_ids=("rede-A",)))):
            for aba in ("pending", "reviews"):
                r = await api.run_get_index_queue(INDEXADOR, tab=aba)
                assert "b1" not in {p["id"] for p in r["items"]}

    @pytest.mark.asyncio
    async def test_a_rede_B_ve_so_o_seu(self, fake_async_db):
        await _semear_processos(fake_async_db)
        with _Contexto(fake_async_db), patch("services.tenant_network.resolve_vista_scope",
                                             AsyncMock(return_value=TenantScope(network_ids=("rede-B",)))):
            r = await api.run_get_index_queue(INDEXADOR, tab="pending")
        assert {p["id"] for p in r["items"]} == {"b1"}

    @pytest.mark.asyncio
    async def test_as_revisoes_pendentes_sao_so_os_indexados_com_campos_a_rever(self, fake_async_db):
        await _semear_processos(fake_async_db)
        with _Contexto(fake_async_db), patch("services.tenant_network.resolve_vista_scope",
                                             AsyncMock(return_value=TenantScope(network_ids=("rede-A",)))):
            r = await api.run_get_index_queue(INDEXADOR, tab="reviews")
        assert [p["id"] for p in r["items"]] == ["a3"]

    @pytest.mark.asyncio
    async def test_a_via_verde_nao_esta_na_fila(self, fake_async_db):
        await _semear_processos(fake_async_db)
        with _Contexto(fake_async_db), patch("services.tenant_network.resolve_vista_scope",
                                             AsyncMock(return_value=TenantScope(network_ids=("rede-A",)))):
            r = await api.run_get_index_queue(INDEXADOR, tab="pending")
        assert "a5" not in {p["id"] for p in r["items"]}

    @pytest.mark.asyncio
    async def test_aba_desconhecida_e_400_nunca_tudo(self, fake_async_db):
        with _Contexto(fake_async_db):
            with pytest.raises(HTTPException) as e:
                await api.run_get_index_queue(INDEXADOR, tab="todos")
        assert e.value.status_code == 400

    @pytest.mark.asyncio
    async def test_a_fila_nao_traz_metadados_profissionais_nem_campos_alheios(self, fake_async_db):
        await _semear_processos(fake_async_db)
        await fake_async_db.processes.update_one({"id": "a1"}, {"$set": {
            "personal_data": {"nif": "999888777"}, "financial_data": {"x": 1}}})
        await fake_async_db.process_professional_metadata.insert_one(
            {"process_id": "a1", "jobs": [_trabalho()]})
        with _Contexto(fake_async_db), patch("services.tenant_network.resolve_vista_scope",
                                             AsyncMock(return_value=TenantScope(network_ids=("rede-A",)))):
            r = await api.run_get_index_queue(INDEXADOR, tab="pending")
        texto = repr(r)
        assert "999888777" not in texto and "Acme" not in texto and "financial_data" not in texto

    @pytest.mark.asyncio
    async def test_conta_os_documentos_a_analisar(self, fake_async_db):
        await _semear_processos(fake_async_db)
        await fake_async_db.document_metadata.insert_many([
            {"id": "d1", "process_id": "a1", "filename": "recibo_vencimento.pdf", "ai_category": "Rendimentos",
             "ai_subcategory": "Recibo de Vencimento"},
            {"id": "d2", "process_id": "a1", "filename": "extrato.pdf", "ai_category": "Bancários",
             "ai_subcategory": "Extrato Bancário", "analysis_fingerprint": "sha256:v1:x"},
            {"id": "d3", "process_id": "a1", "filename": "foto.jpg"},
        ])
        with _Contexto(fake_async_db), patch("services.tenant_network.resolve_vista_scope",
                                             AsyncMock(return_value=TenantScope(network_ids=("rede-A",)))):
            r = await api.run_get_index_queue(INDEXADOR, tab="pending")
        a1 = next(p for p in r["items"] if p["id"] == "a1")
        assert a1["documents_total"] == 3 and a1["documents_to_analyse"] == 1


# ====================================================================
# 3. A BANCADA
# ====================================================================
class TestABancada:
    @pytest.mark.asyncio
    async def test_devolve_estado_ficheiros_metadados_alertas_e_jobs(self, fake_async_db):
        await fake_async_db.processes.insert_one({"id": PID, "network_id": "rede-A", "client_name": "Ana",
                                                  "index_status": "pending", "is_deleted": False})
        await fake_async_db.document_metadata.insert_one({
            "id": "d1", "process_id": PID, "filename": "cc.pdf", "s3_path": "x/cc.pdf",
            "ai_category": "Identificação", "ai_subtype": "cc"})
        await fake_async_db.process_professional_metadata.insert_one(
            {"process_id": PID, "jobs": [_trabalho()], "has_pending_review": True})
        await fake_async_db.process_index_alerts.insert_one({
            "id": "al-1", "process_id": PID, "code": "nif_invalido", "severity": "alerta",
            "message": "m", "dismissed_by_human": False})
        with _Contexto(fake_async_db):
            r = await api.run_get_index_workstation(INDEXADOR, PID)
        assert r["process"]["index_status"] == "pending"
        assert r["files"][0]["analysis_type"] == "identificacao" or r["files"][0]["analysis_type"]
        assert r["professional_metadata"]["jobs"][0]["job_id"] == "job_a"
        assert r["alerts"][0]["code"] == "nif_invalido"
        assert r["active_jobs"] == {"analysis": None, "finalize": None, "sanitize": None}

    @pytest.mark.asyncio
    async def test_diz_se_o_processo_e_do_utilizador_para_o_ecra_decidir_se_arranca_o_tratamento(self, fake_async_db):
        await fake_async_db.processes.insert_one({"id": PID, "network_id": "r", "is_deleted": False, "index_status": "pending",
                                                  "assigned_indexacao_id": INDEXADOR["id"]})
        outro = {**INDEXADOR, "id": "outro"}
        with _Contexto(fake_async_db):
            meu = await api.run_get_index_workstation(INDEXADOR, PID)
            alheio = await api.run_get_index_workstation(outro, PID)
        assert meu["process"]["assigned_to_me"] is True
        assert alheio["process"]["assigned_to_me"] is False

    @pytest.mark.asyncio
    async def test_um_processo_por_atribuir_nao_e_de_ninguem(self, fake_async_db):
        await fake_async_db.processes.insert_one({"id": PID, "network_id": "r", "is_deleted": False, "index_status": "pending"})
        sem_id = {k: v for k, v in INDEXADOR.items() if k != "id"}
        with _Contexto(fake_async_db):
            r = await api.run_get_index_workstation(sem_id, PID)
        assert r["process"]["assigned_to_me"] is False  # `None == None` não é «é meu»

    @pytest.mark.asyncio
    async def test_a_estagnacao_so_aparece_em_tratamento_e_com_alerta_dado(self, fake_async_db):
        await fake_async_db.processes.insert_many([
            {"id": "a", "network_id": "r", "is_deleted": False, "index_status": "in_review", "index_stagnation_alerted_at": "2026-10-01T00:00:00+00:00"},
            {"id": "b", "network_id": "r", "is_deleted": False, "index_status": "in_review"},
            {"id": "c", "network_id": "r", "is_deleted": False, "index_status": "pending", "index_stagnation_alerted_at": "2026-10-01T00:00:00+00:00"},
        ])
        with _Contexto(fake_async_db):
            a, b, c = [(await api.run_get_index_workstation(INDEXADOR, i))["process"]["stagnant"] for i in "abc"]
        assert (a, b, c) == (True, False, False)

    @pytest.mark.asyncio
    async def test_processo_inexistente_ou_eliminado_e_404(self, fake_async_db):
        await fake_async_db.processes.insert_one({"id": PID, "is_deleted": True})
        with _Contexto(fake_async_db):
            for pid in ("nao-existe", PID):
                with pytest.raises(HTTPException) as e:
                    await api.run_get_index_workstation(INDEXADOR, pid)
                assert e.value.status_code == 404

    @pytest.mark.asyncio
    async def test_purgados_nao_aparecem(self, fake_async_db):
        await fake_async_db.processes.insert_one({"id": PID, "network_id": "r", "is_deleted": False})
        await fake_async_db.document_metadata.insert_many([
            {"id": "d1", "process_id": PID, "filename": "a.pdf", "file_state": "purgado"},
            {"id": "d2", "process_id": PID, "filename": "b.pdf", "file_state": "original"},
        ])
        with _Contexto(fake_async_db):
            r = await api.run_get_index_workstation(INDEXADOR, PID)
        assert [f["id"] for f in r["files"]] == ["d2"]

    @pytest.mark.asyncio
    async def test_um_utilizador_de_outra_rede_leva_404_na_dependencia_do_router(self, fake_async_db):
        """A parede é a dependência do router (o handler nunca corre)."""
        from services import process_scope_guard as guarda

        await fake_async_db.processes.insert_one({"id": PID, "network_id": "rede-A"})
        request = MagicMock()
        request.path_params = {"process_id": PID}
        with patch.object(guarda, "db", fake_async_db), \
                patch.object(guarda, "resolve_tenant_scope", AsyncMock(return_value=TenantScope(network_ids=("rede-B",)))):
            with pytest.raises(HTTPException) as e:
                await guarda.exigir_processo_no_ambito(request, {"id": "u", "role": "indexacao"})
        assert e.value.status_code == 404


# ====================================================================
# 4. CLAIM / ANALISAR
# ====================================================================
class TestAccoes:
    @pytest.mark.asyncio
    async def test_abrir_a_bancada_arranca_o_tratamento_so_do_atribuido(self, fake_async_db):
        await fake_async_db.processes.insert_one({"id": PID, "network_id": "r", "is_deleted": False, "is_indexed": False,
                                                  "index_status": "pending", "assigned_indexacao_id": INDEXADOR["id"]})
        outro = {**INDEXADOR, "id": "outro"}
        with _Contexto(fake_async_db), patch.object(ist, "db", fake_async_db):
            r0 = await api.run_start_work(outro, PID)
            r1 = await api.run_start_work(INDEXADOR, PID)
            r2 = await api.run_start_work(INDEXADOR, PID)
        assert r0["iniciado"] is False and r1["iniciado"] is True
        assert r2["iniciado"] is False and r2["registado"] is True  # idempotente: só carimba a actividade
        assert (await fake_async_db.processes.find_one({"id": PID}))["index_status"] == "in_review"

    @pytest.mark.asyncio
    async def test_as_acoes_de_escrita_carimbam_a_actividade_do_atribuido(self, fake_async_db):
        await fake_async_db.processes.insert_one({"id": PID, "network_id": "r", "is_deleted": False, "is_indexed": False,
                                                  "index_status": "pending", "assigned_indexacao_id": INDEXADOR["id"]})
        iniciar = AsyncMock(return_value={"task_id": "t-1", "iniciado": True})
        with _Contexto(fake_async_db), patch.object(ist, "db", fake_async_db), patch.object(jobs, "iniciar_analise", iniciar):
            await api.run_analyze_process(INDEXADOR, PID, force=False)
        doc = await fake_async_db.processes.find_one({"id": PID})
        assert doc["index_status"] == "in_review" and doc["index_last_activity_at"]

    def test_o_claim_e_o_release_deixaram_de_existir(self):
        assert not hasattr(api, "run_claim_process") and not hasattr(api, "run_release_process")

    @pytest.mark.asyncio
    async def test_analisar_devolve_ja_com_o_task_id(self, fake_async_db):
        await fake_async_db.processes.insert_one({"id": PID, "network_id": "r", "is_deleted": False})
        iniciar = AsyncMock(return_value={"task_id": "t-1", "iniciado": True})
        with _Contexto(fake_async_db), patch.object(jobs, "iniciar_analise", iniciar):
            r = await api.run_analyze_process(INDEXADOR, PID, force=False)
        assert r["task_id"] == "t-1" and r["started"] is True
        assert iniciar.await_args.kwargs == {"force": False, "gatilho": "manual"}

    @pytest.mark.asyncio
    async def test_extrair_forca_a_reanalise(self, fake_async_db):
        await fake_async_db.processes.insert_one({"id": PID, "network_id": "r", "is_deleted": False})
        iniciar = AsyncMock(return_value={"task_id": "t-1", "iniciado": True})
        with _Contexto(fake_async_db), patch.object(jobs, "iniciar_analise", iniciar):
            await api.run_analyze_process(INDEXADOR, PID, force=True)
        assert iniciar.await_args.kwargs["force"] is True

    @pytest.mark.asyncio
    async def test_ja_havia_uma_analise_diz_se_e_nao_e_erro(self, fake_async_db):
        await fake_async_db.processes.insert_one({"id": PID, "network_id": "r", "is_deleted": False})
        with _Contexto(fake_async_db), patch.object(
                jobs, "iniciar_analise", AsyncMock(return_value={"task_id": "t-0", "iniciado": False})):
            r = await api.run_analyze_process(INDEXADOR, PID)
        assert r["success"] is True and r["started"] is False and r["task_id"] == "t-0"


class TestSanitizar:
    @pytest.mark.asyncio
    async def test_devolve_ja_com_o_task_id(self, fake_async_db):
        from services import index_sanitize

        await fake_async_db.processes.insert_one({"id": PID, "network_id": "r", "is_deleted": False})
        iniciar = AsyncMock(return_value={"task_id": "t-7", "iniciado": True})
        with _Contexto(fake_async_db), patch.object(index_sanitize, "iniciar_sanitizacao", iniciar):
            r = await api.run_sanitize_process(INDEXADOR, PID)
        assert r["task_id"] == "t-7" and r["started"] is True
        assert "margem de segurança" in r["message"]

    @pytest.mark.asyncio
    async def test_ja_havia_uma_limpeza_a_correr_nao_e_erro(self, fake_async_db):
        from services import index_sanitize

        await fake_async_db.processes.insert_one({"id": PID, "network_id": "r", "is_deleted": False})
        with _Contexto(fake_async_db), patch.object(
                index_sanitize, "iniciar_sanitizacao", AsyncMock(return_value={"task_id": "t-0", "iniciado": False})):
            r = await api.run_sanitize_process(INDEXADOR, PID)
        assert r["success"] is True and r["started"] is False

    @pytest.mark.asyncio
    async def test_processo_inexistente_e_404(self, fake_async_db):
        with _Contexto(fake_async_db):
            with pytest.raises(HTTPException) as e:
                await api.run_sanitize_process(INDEXADOR, "nao-existe")
        assert e.value.status_code == 404


# ====================================================================
# 5. EDIÇÃO HUMANA
# ====================================================================
class TestAplicarEdicao:
    def test_um_nif_valido_fica_editado_e_sem_duvida(self):
        antes = [_trabalho(employer_nif={"value": "123", "needs_review": True})]
        depois = st.aplicar_edicao(antes, "job_a", {"employer_nif": NIF_VALIDO})
        campo = depois[0].employer_nif
        assert campo.value == NIF_VALIDO and campo.edited_by_human is True and campo.needs_review is False

    def test_o_codigo_reforca_o_nif_que_a_pessoa_escreveu(self):
        depois = st.aplicar_edicao([_trabalho()], "job_a", {"employer_nif": NIF_INVALIDO})
        campo = depois[0].employer_nif
        assert campo.edited_by_human is True
        assert campo.needs_review is True  # gralha: continua a rever

    def test_o_nif_aceita_pontuacao(self):
        depois = st.aplicar_edicao([_trabalho()], "job_a", {"employer_nif": f"{NIF_VALIDO[:3]} {NIF_VALIDO[3:]}"})
        assert depois[0].employer_nif.value == NIF_VALIDO

    def test_vazio_de_proposito_conta_como_revisto(self):
        depois = st.aplicar_edicao([_trabalho()], "job_a", {"job_title": None})
        assert depois[0].job_title.edited_by_human and not depois[0].job_title.needs_review

    def test_vencimento_e_decimal(self):
        from decimal import Decimal

        depois = st.aplicar_edicao([_trabalho()], "job_a", {"net_salary": "1.500,75"})
        assert depois[0].net_salary.value == Decimal("1500.75")

    @pytest.mark.parametrize("valor", ["abc", "-5", ""])
    def test_vencimento_sem_forma_e_recusado(self, valor):
        with pytest.raises(st.EdicaoInvalida):
            st.aplicar_edicao([_trabalho()], "job_a", {"net_salary": valor or "x"})

    def test_campo_desconhecido_e_recusado(self):
        with pytest.raises(st.EdicaoInvalida):
            st.aplicar_edicao([_trabalho()], "job_a", {"source_document_ids": ["x"]})

    def test_job_inexistente_e_recusado(self):
        with pytest.raises(st.EdicaoInvalida):
            st.aplicar_edicao([_trabalho()], "job_zzz", {"job_title": "x"})

    def test_pedido_vazio_e_recusado(self):
        with pytest.raises(st.EdicaoInvalida):
            st.aplicar_edicao([_trabalho()], "job_a", {})

    def test_so_o_trabalho_pedido_muda(self):
        trabalhos = [_trabalho("job_a"), _trabalho("job_b", job_title={"value": "Eng.", "needs_review": False})]
        depois = st.aplicar_edicao(trabalhos, "job_a", {"job_title": "Chefe"})
        assert depois[0].job_title.value == "Chefe" and depois[1].job_title.value == "Eng."
        assert not depois[1].job_title.edited_by_human

    def test_contrato_fora_dos_valores_permitidos_e_recusado(self):
        with pytest.raises(st.EdicaoInvalida):
            st.aplicar_edicao([_trabalho()], "job_a", {"contract_type": "escravatura"})

    def test_a_edicao_sobrevive_a_reanalise(self):
        """A IA propõe, a pessoa dispõe: o que ela escreveu não é pisado pelo recálculo."""
        editados = st.aplicar_edicao([_trabalho()], "job_a", {"job_title": "Chefe"})
        gravado = [editados[0].model_dump(mode="json")]
        recalculado = [st.TrabalhoProfissional.model_validate(_trabalho())]
        final = st.aplicar_edicoes_humanas(gravado, recalculado)
        assert final[0].job_title.value == "Chefe" and final[0].job_title.edited_by_human


class TestEditarNoServico:
    @pytest.mark.asyncio
    async def test_grava_actualiza_o_contador_e_alimenta_o_directorio(self, fake_async_db):
        await fake_async_db.processes.insert_one({"id": PID, "network_id": "rede-A", "is_deleted": False,
                                                  "has_pending_review": True})
        await fake_async_db.process_professional_metadata.insert_one({
            "process_id": PID, "jobs": [_trabalho(employer_nif={"value": NIF_VALIDO, "needs_review": True})]})
        with _Contexto(fake_async_db):
            r = await api.run_edit_professional_job(
                INDEXADOR, PID, "job_a",
                {"employer_nif": NIF_VALIDO, "job_title": "Analista"})
        assert r["has_pending_review"] is False
        proc = await fake_async_db.processes.find_one({"id": PID})
        assert proc["has_pending_review"] is False
        assert await fake_async_db.employers.find_one({"nif": NIF_VALIDO})

    @pytest.mark.asyncio
    async def test_valor_invalido_e_422_nunca_500(self, fake_async_db):
        await fake_async_db.processes.insert_one({"id": PID, "network_id": "r", "is_deleted": False})
        await fake_async_db.process_professional_metadata.insert_one({"process_id": PID, "jobs": [_trabalho()]})
        with _Contexto(fake_async_db):
            with pytest.raises(HTTPException) as e:
                await api.run_edit_professional_job(INDEXADOR, PID, "job_a", {"net_salary": "abc"})
        assert e.value.status_code == 422

    @pytest.mark.asyncio
    async def test_sem_metadados_ainda_e_422_com_motivo(self, fake_async_db):
        await fake_async_db.processes.insert_one({"id": PID, "network_id": "r", "is_deleted": False})
        with _Contexto(fake_async_db):
            with pytest.raises(HTTPException) as e:
                await api.run_edit_professional_job(INDEXADOR, PID, "job_a", {"job_title": "x"})
        assert e.value.status_code == 422 and "metadados" in e.value.detail.lower()

    @pytest.mark.asyncio
    async def test_a_auditoria_leva_nomes_de_campos_nunca_valores(self, fake_async_db):
        await fake_async_db.processes.insert_one({"id": PID, "network_id": "r", "is_deleted": False})
        await fake_async_db.process_professional_metadata.insert_one({"process_id": PID, "jobs": [_trabalho()]})
        auditar = AsyncMock()
        with _Contexto(fake_async_db), patch("services.audit_trail_service.log_audit_event", auditar):
            await api.run_edit_professional_job(INDEXADOR, PID, "job_a", {"job_title": "SEGREDO-DO-CARGO"})
        assert "SEGREDO-DO-CARGO" not in repr(auditar.await_args)
        assert "job_title" in repr(auditar.await_args)


# ====================================================================
# 6. ALERTAS E DIRECTÓRIO
# ====================================================================
class TestAlertas:
    @pytest.mark.asyncio
    async def test_dispensar_actualiza_o_contador(self, fake_async_db):
        await fake_async_db.processes.insert_one({"id": PID, "network_id": "r", "is_deleted": False,
                                                  "index_alerts_open": 2})
        await fake_async_db.process_index_alerts.insert_many([
            {"id": "al-1", "process_id": PID, "code": "nif_invalido", "dismissed_by_human": False},
            {"id": "al-2", "process_id": PID, "code": "contas_nao_batem", "dismissed_by_human": False},
        ])
        with _Contexto(fake_async_db):
            r = await api.run_dismiss_alert(INDEXADOR, PID, "al-1")
        assert r["alerts_open"] == 1
        assert (await fake_async_db.processes.find_one({"id": PID}))["index_alerts_open"] == 1

    @pytest.mark.asyncio
    async def test_um_alerta_de_outro_processo_e_404(self, fake_async_db):
        await fake_async_db.processes.insert_one({"id": PID, "network_id": "r", "is_deleted": False})
        await fake_async_db.process_index_alerts.insert_one(
            {"id": "al-x", "process_id": "outro", "code": "nif_invalido"})
        with _Contexto(fake_async_db):
            with pytest.raises(HTTPException) as e:
                await api.run_dismiss_alert(INDEXADOR, PID, "al-x")
        assert e.value.status_code == 404
        assert not (await fake_async_db.process_index_alerts.find_one({"id": "al-x"})).get("dismissed_by_human")

    @pytest.mark.asyncio
    async def test_dispensar_e_idempotente(self, fake_async_db):
        await fake_async_db.processes.insert_one({"id": PID, "network_id": "r", "is_deleted": False})
        await fake_async_db.process_index_alerts.insert_one(
            {"id": "al-1", "process_id": PID, "code": "nif_invalido", "dismissed_by_human": False})
        with _Contexto(fake_async_db):
            await api.run_dismiss_alert(INDEXADOR, PID, "al-1")
            r = await api.run_dismiss_alert(INDEXADOR, PID, "al-1")
        assert r["alerts_open"] == 0


class TestDirectorio:
    @pytest.mark.asyncio
    async def test_pesquisa_por_nome_e_por_nif_sem_dados_de_clientes(self, fake_async_db):
        await fake_async_db.employers.insert_many([
            {"nif": NIF_VALIDO, "name": "Acme Lda", "name_normalizado": "acme lda", "process_id": "NUNCA",
             "client_name": "NUNCA"},
        ])
        with _Contexto(fake_async_db):
            por_nome = await api.run_search_employers(INDEXADOR, "acme")
            por_nif = await api.run_search_employers(INDEXADOR, NIF_VALIDO[:4])
        for r in (por_nome, por_nif):
            assert r["items"] == [{"nif": NIF_VALIDO, "name": "Acme Lda"}]
        assert "NUNCA" not in repr(por_nome)

    @pytest.mark.asyncio
    async def test_pesquisa_curta_nao_devolve_o_directorio_inteiro(self, fake_async_db):
        await fake_async_db.employers.insert_one({"nif": NIF_VALIDO, "name": "Acme", "name_normalizado": "acme"})
        with _Contexto(fake_async_db):
            assert (await api.run_search_employers(INDEXADOR, "a"))["items"] == []
            assert (await api.run_search_employers(INDEXADOR, ""))["items"] == []


# ====================================================================
# 7. MARCAR COMO INDEXADO — nunca bloqueado
# ====================================================================
class TestMarcarComoIndexado:
    def _marca(self, **kw):
        return patch("services.process_indexing.run_mark_process_indexed", AsyncMock(
            return_value={"success": True, "is_indexed": True}))

    @pytest.mark.asyncio
    async def test_marca_mesmo_sem_metadados_sem_ia_e_com_alertas_abertos(self, fake_async_db):
        await fake_async_db.processes.insert_one({"id": PID, "network_id": "r", "index_alerts_open": 5,
                                                  "has_pending_review": True})
        await fake_async_db.process_index_alerts.insert_one(
            {"id": "al", "process_id": PID, "code": "nif_invalido", "dismissed_by_human": False})
        with _Contexto(fake_async_db), self._marca() as marcar, \
                patch("services.document_ai_trigger.ia_da_entrada_ligada", return_value=False):
            r = await fin.run_mark_indexed(PID, INDEXADOR, user_role="indexacao", all_roles=["indexacao"],
                                           broadcast_fn=AsyncMock())
        assert r["success"] is True
        marcar.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_um_nif_que_nao_se_aplica_nao_recusa_a_indexacao(self, fake_async_db):
        await fake_async_db.processes.insert_one({"id": PID, "network_id": "r"})
        with _Contexto(fake_async_db), self._marca() as marcar:
            r = await fin.run_mark_indexed(
                PID, INDEXADOR, user_role="indexacao", all_roles=["indexacao"], broadcast_fn=AsyncMock(),
                employers=[{"job_id": "job_zzz", "nif": NIF_VALIDO}, {"job_id": "x", "nif": "abc"}])
        marcar.assert_awaited_once()
        assert r["employers"]["applied"] == 0 and len(r["employers"]["rejected"]) == 2

    @pytest.mark.asyncio
    async def test_os_nifs_confirmados_aplicam_se_ANTES_de_marcar(self, fake_async_db):
        await fake_async_db.processes.insert_one({"id": PID, "network_id": "r"})
        await fake_async_db.process_professional_metadata.insert_one({
            "process_id": PID, "jobs": [_trabalho(employer_nif={"value": None, "needs_review": True})]})
        visto = {}

        async def marcar(*a, **k):
            doc = await fake_async_db.process_professional_metadata.find_one({"process_id": PID})
            visto["nif"] = doc["jobs"][0]["employer_nif"]["value"]
            return {"success": True}

        with _Contexto(fake_async_db), patch("services.process_indexing.run_mark_process_indexed", marcar):
            r = await fin.run_mark_indexed(
                PID, INDEXADOR, user_role="indexacao", all_roles=["indexacao"], broadcast_fn=AsyncMock(),
                employers=[{"job_id": "job_a", "nif": NIF_VALIDO}])
        assert r["employers"]["applied"] == 1 and visto["nif"] == NIF_VALIDO

    @pytest.mark.asyncio
    async def test_sem_permissao_e_403_e_nao_escreve_nada(self, fake_async_db):
        await fake_async_db.processes.insert_one({"id": PID, "network_id": "r"})
        await fake_async_db.process_professional_metadata.insert_one({"process_id": PID, "jobs": [_trabalho()]})
        with _Contexto(fake_async_db), self._marca() as marcar:
            with pytest.raises(HTTPException) as e:
                await fin.run_mark_indexed(
                    PID, {"id": "u", "role": "consultor"}, user_role="consultor", all_roles=["consultor"],
                    broadcast_fn=AsyncMock(), employers=[{"job_id": "job_a", "nif": NIF_VALIDO + "0"}])
        assert e.value.status_code == 403
        marcar.assert_not_awaited()
        doc = await fake_async_db.process_professional_metadata.find_one({"process_id": PID})
        assert doc["jobs"][0]["employer_nif"].get("edited_by_human") is not True

    def test_o_fecho_e_agendado_depois_de_libertar_a_pasta_index(self):
        from services import process_indexing

        fonte = codigo_da_funcao_sem_comentarios(process_indexing.run_mark_indexed_side_effects)
        assert fonte.index("libertar_index_sem_falhar") < fonte.index("agendar_finalizacao_sem_falhar")
        assert fonte.index("agendar_finalizacao_sem_falhar") < fonte.index("build_mark_indexed_response")

    @pytest.mark.asyncio
    async def test_o_agendamento_do_fecho_nunca_derruba_a_indexacao(self):
        from services import process_indexing

        with patch("services.index_finalize.agendar_finalizacao", AsyncMock(side_effect=RuntimeError("boom"))):
            r = await process_indexing.agendar_finalizacao_sem_falhar({"id": PID}, INDEXADOR)
        assert r["agendado"] is False


# ====================================================================
# 8. O FECHO EM BACKGROUND
# ====================================================================
class TestOFecho:
    @pytest.mark.asyncio
    async def test_sem_ia_ligada_nao_agenda(self, fake_async_db):
        with _Contexto(fake_async_db), patch.object(fin, "ia_da_entrada_ligada", return_value=False):
            r = await fin.agendar_finalizacao({"id": PID}, INDEXADOR)
        assert r["agendado"] is False and r["motivo"] == "ia_desligada"

    @pytest.mark.asyncio
    async def test_agenda_um_job_e_nao_dois(self, fake_async_db):
        spawn = MagicMock()
        reivindicar = AsyncMock(side_effect=[("t-1", None), (None, "t-1")])
        with _Contexto(fake_async_db), patch.object(fin, "ia_da_entrada_ligada", return_value=True), \
                patch.object(jobs, "reivindicar_job", reivindicar), patch.object(fin, "spawn_background_task", spawn), \
                patch.object(fin, "correr_finalizacao", MagicMock(return_value="coro")):
            a = await fin.agendar_finalizacao({"id": PID}, INDEXADOR)
            b = await fin.agendar_finalizacao({"id": PID}, INDEXADOR)
        assert a == {"agendado": True, "task_id": "t-1"}
        assert b["agendado"] is False and b["task_id"] == "t-1"
        assert spawn.call_count == 1

    @pytest.mark.asyncio
    async def test_uma_analise_a_falhar_nao_impede_o_fecho_de_terminar_bem(self, fake_async_db):
        await fake_async_db.processes.insert_one({"id": PID, "network_id": "r", "is_deleted": False})
        actualizar = AsyncMock()
        notificar = AsyncMock()
        with _Contexto(fake_async_db), \
                patch.object(fin.TaskLogService, "update_task", actualizar), \
                patch.object(jobs, "analisar_e_concluir", AsyncMock(side_effect=RuntimeError("modelo em baixo"))), \
                patch.object(jobs, "notificar_fim", notificar), patch.object(jobs, "libertar_job", AsyncMock()) as liberta:
            await fin.correr_finalizacao("t-1", PID, INDEXADOR, gatilho="automatico")
        estados = [c.kwargs.get("status") for c in actualizar.await_args_list]
        assert fin.TaskStatus.COMPLETED in estados and fin.TaskStatus.FAILED not in estados
        notificar.assert_awaited_once()
        liberta.assert_awaited_once_with("t-1")

    @pytest.mark.asyncio
    async def test_processo_inexistente_falha_o_job_e_liberta_a_chave(self, fake_async_db):
        actualizar = AsyncMock()
        with _Contexto(fake_async_db), patch.object(fin.TaskLogService, "update_task", actualizar), \
                patch.object(jobs, "libertar_job", AsyncMock()) as liberta:
            await fin.correr_finalizacao("t-1", "nao-existe", INDEXADOR, gatilho="automatico")
        assert fin.TaskStatus.FAILED in [c.kwargs.get("status") for c in actualizar.await_args_list]
        liberta.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_a_sanitizacao_a_falhar_nao_derruba_o_fecho(self, fake_async_db):
        class Falha:
            @staticmethod
            async def sanitizar_do_fecho(*a, **k):
                raise RuntimeError("pdf partido")

        with patch.dict("sys.modules", {"services.index_sanitize": Falha}), patch("services.index_sanitize", Falha, create=True):
            r = await fin._sanitizar_sem_falhar({"id": PID}, INDEXADOR)
        assert r == {"sanitizacao_falhou": True}


class TestUploadPosIndexacao:
    @pytest.mark.asyncio
    async def test_regista_o_ficheiro_marca_o_index_e_lanca_a_analise(self, fake_async_db):
        iniciar = AsyncMock(return_value={"task_id": "t", "iniciado": True})
        with _Contexto(fake_async_db), patch.object(fin, "ia_da_entrada_ligada", return_value=True), \
                patch.object(jobs, "iniciar_analise", iniciar):
            await fin.agendar_analise_pos_indexacao(
                PID, INDEXADOR, s3_path="Documentação Clientes/c/Financeiros/recibo.pdf", filename="recibo.pdf",
                client_name="Ana", categoria="Financeiros")
        reg = await fake_async_db.document_metadata.find_one({"process_id": PID})
        assert reg["uploaded_by_index"] is True and reg["in_index_queue"] is False
        iniciar.assert_awaited_once()
        assert iniciar.await_args.kwargs["gatilho"] == "automatico"

    @pytest.mark.asyncio
    async def test_um_upload_do_consultor_nao_fica_marcado_como_do_index(self, fake_async_db):
        with _Contexto(fake_async_db), patch.object(fin, "ia_da_entrada_ligada", return_value=True), \
                patch.object(jobs, "iniciar_analise", AsyncMock(return_value={"task_id": "t", "iniciado": True})):
            await fin.agendar_analise_pos_indexacao(
                PID, {"id": "c", "role": "consultor"}, s3_path="a/b.pdf", filename="b.pdf")
        assert (await fake_async_db.document_metadata.find_one({"process_id": PID}))["uploaded_by_index"] is False

    @pytest.mark.asyncio
    async def test_um_registo_existente_nao_se_duplica(self, fake_async_db):
        await fake_async_db.document_metadata.insert_one({"id": "d", "process_id": PID, "s3_path": "a/b.pdf"})
        with _Contexto(fake_async_db), patch.object(fin, "ia_da_entrada_ligada", return_value=True), \
                patch.object(jobs, "iniciar_analise", AsyncMock(return_value={"task_id": "t", "iniciado": True})):
            await fin.agendar_analise_pos_indexacao(PID, INDEXADOR, s3_path="a/b.pdf", filename="b.pdf")
        assert len(await fake_async_db.document_metadata.find({"process_id": PID}).to_list(None)) == 1

    @pytest.mark.asyncio
    async def test_com_a_ia_desligada_nao_faz_nada(self, fake_async_db):
        iniciar = AsyncMock()
        with _Contexto(fake_async_db), patch.object(fin, "ia_da_entrada_ligada", return_value=False), \
                patch.object(jobs, "iniciar_analise", iniciar):
            await fin.agendar_analise_pos_indexacao(PID, INDEXADOR, s3_path="a/b.pdf")
        iniciar.assert_not_awaited()
        assert await fake_async_db.document_metadata.find_one({"process_id": PID}) is None

    @pytest.mark.asyncio
    async def test_nunca_levanta(self, fake_async_db):
        with _Contexto(fake_async_db), patch.object(fin, "ia_da_entrada_ligada", return_value=True), \
                patch.object(jobs, "iniciar_analise", AsyncMock(side_effect=RuntimeError("x"))):
            await fin.agendar_analise_pos_indexacao(PID, INDEXADOR, s3_path="a/b.pdf")

    @pytest.mark.parametrize("caminho", [
        "services.document_upload.run_upload_file_s3",
        "services.document_direct_upload.run_confirm_upload",
    ])
    def test_os_dois_uploads_do_staff_chamam_o_gatilho_no_ramo_sem_ia(self, caminho):
        import importlib

        modulo, nome = caminho.rsplit(".", 1)
        fonte = codigo_da_funcao_sem_comentarios(getattr(importlib.import_module(modulo), nome))
        assert "agendar_analise_pos_indexacao" in fonte
        assert fonte.index("not plano.passa_pela_ia") < fonte.index("agendar_analise_pos_indexacao")
        assert "carregado_pelo_index" in fonte


class TestDirectorioPontuacaoHostil:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("texto", [".*", "((", "  ..  ", "%%"])
    async def test_pontuacao_nao_devolve_o_directorio_inteiro(self, fake_async_db, texto):
        await fake_async_db.employers.insert_one({"nif": NIF_VALIDO, "name": "Acme", "name_normalizado": "acme"})
        with _Contexto(fake_async_db):
            assert (await api.run_search_employers(INDEXADOR, texto))["items"] == []

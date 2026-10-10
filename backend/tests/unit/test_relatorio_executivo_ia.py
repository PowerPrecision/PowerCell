"""
Análise de IA OPCIONAL no PDF do relatório executivo.

O QUE SE GARANTE
  1. Sem o pedido NÃO há chamada ao modelo e o PDF é o de sempre.
  2. O que vai ao modelo são só números agregados — nunca emails, ids, nomes
     de clientes nem movimentos.
  3. Dev simula; só produção COM chave chama o modelo, e o modelo vem do painel.
  4. O modelo não é uma parede: o que o PDF imprime passa por `limpar_texto`;
     falha ou resposta inaproveitável → PDF SEM a secção e o servidor di-lo.
  5. A secção aparece (ou não) no PDF — lido com PyMuPDF, não só «a função correu».
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services import executive_report as er
from services import executive_report_ai as ia

RELATORIO = {
    "start_date": "2026-10-05", "end_date": "2026-10-11",
    "gerado_em": "2026-10-12T08:00:00+00:00", "filtros": {}, "notas": [], "serie_diaria": [],
    "por_fase": [{"fase": "aprovado", "rotulo": "Aprovado", "n": 7}],
    "summary": {"total_users": 2, "total_phase_changes": 9, "total_processes_moved": 6,
                "total_tasks_completed": 11, "total_tasks_pending": 4, "total_tasks_overdue": 3},
    "users": [
        {"user_id": "u-secreto-1", "name": "Ana Costa", "email": "ana.costa@exemplo.pt", "role": "consultor",
         "phase_changes": 6, "processes_moved": 4, "tasks_completed": 8, "tasks_pending": 1, "tasks_overdue": 0},
        {"user_id": "u-secreto-2", "name": "Rui Dias", "email": "rui.dias@exemplo.pt", "role": "intermediario",
         "phase_changes": None, "processes_moved": None, "tasks_completed": 3, "tasks_pending": 3, "tasks_overdue": 3},
    ],
    "movimentos": [{"user_name": "Ana Costa", "process_number": 4321, "de": "x", "para": "y"}],
}

TEXTO_BOM = (
    "A equipa manteve um ritmo estável. A Ana Costa fez avançar mais processos e concluiu mais tarefas, "
    "enquanto o Rui Dias concentra as tarefas em atraso.\n\nRecomenda-se acompanhar o atraso acumulado."
)


class TestOQueVaiAoModelo:
    def test_so_numeros_agregados(self):
        texto = json.dumps(ia.dados_para_o_modelo(RELATORIO), ensure_ascii=False)
        for proibido in ("@", "u-secreto", "4321", "exemplo.pt", "movimentos"):
            assert proibido not in texto, proibido

    def test_os_numeros_chegam_e_o_nulo_continua_nulo(self):
        dados = ia.dados_para_o_modelo(RELATORIO)
        ana, rui = dados["colaboradores"]
        assert ana["fases_alteradas"] == 6 and ana["tarefas_concluidas"] == 8
        assert rui["fases_alteradas"] is None and rui["processos_avancados"] is None  # sem registo, não zero
        assert dados["totais"]["tarefas_em_atraso"] == 3
        assert dados["fases_mais_usadas"] == [{"fase": "Aprovado", "entradas": 7}]
        assert dados["periodo"] == {"inicio": "2026-10-05", "fim": "2026-10-11"}

    def test_tectos(self):
        grande = {**RELATORIO, "users": [dict(RELATORIO["users"][0], name=f"P{i}") for i in range(60)],
                  "por_fase": [{"fase": f"f{i}", "n": i} for i in range(30)]}
        dados = ia.dados_para_o_modelo(grande)
        assert len(dados["colaboradores"]) == ia.MAX_PESSOAS_ENVIADAS
        assert len(dados["fases_mais_usadas"]) == ia.MAX_FASES_ENVIADAS

    def test_o_prompt_proibe_inventar_e_juizos(self):
        assert "APENAS os números" in ia.SYSTEM_PROMPT
        assert "sem juízos de valor" in ia.SYSTEM_PROMPT
        mensagens = ia.construir_mensagens(ia.dados_para_o_modelo(RELATORIO))
        assert [m["role"] for m in mensagens] == ["system", "user"]
        assert "Ana Costa" in mensagens[1]["content"]

    def test_sem_colaboradores_nao_ha_nada_a_analisar(self):
        assert ia.ha_dados_para_analisar(ia.dados_para_o_modelo({**RELATORIO, "users": []})) is False
        assert ia.ha_dados_para_analisar(ia.dados_para_o_modelo(RELATORIO)) is True


class TestLimparTexto:
    def test_texto_normal_passa_com_os_paragrafos(self):
        assert ia.limpar_texto(TEXTO_BOM) == TEXTO_BOM

    def test_tira_html_e_markdown(self):
        bruto = "## Título\n\n**A Ana** fez <b>avançar</b> `mais` processos do que o Rui neste período de análise.\n"
        texto = ia.limpar_texto(bruto)
        assert texto is not None
        for resto in ("<", ">", "**", "`", "#"):
            assert resto not in texto
        assert "avançar" in texto and "mais" in texto  # o conteúdo ficou

    @pytest.mark.parametrize("bruto", [
        None, 42, "", "   ", "curto demais",
        "Contacte ana@exemplo.pt para mais detalhes sobre o desempenho da equipa neste período, por favor.",
        "Veja https://exemplo.pt/relatorio para os detalhes completos do desempenho da equipa no período.",
        "Mais informação em www.exemplo.pt sobre o desempenho da equipa e das tarefas concluídas no período.",
    ])
    def test_recusa(self, bruto):
        assert ia.limpar_texto(bruto) is None

    def test_tecto_corta_numa_frase(self):
        frase = "A equipa manteve o ritmo do período. "
        texto = ia.limpar_texto(frase * 200)
        assert texto is not None and len(texto) <= ia.MAX_CARACTERES
        assert texto.endswith(".")

    def test_junta_as_linhas_dentro_do_paragrafo(self):
        texto = ia.limpar_texto("A equipa concluiu muitas tarefas\nneste período de análise do relatório executivo.")
        assert "\n" not in texto


class TestProvider:
    def test_dev_simula(self):
        assert ia.resolver_provider({"ENVIRONMENT": "dev", "OPENAI_API_KEY": "k"}) == ia.PROVIDER_MOCK
        assert ia.resolver_provider({}) == ia.PROVIDER_MOCK

    def test_producao_sem_chave_simula(self):
        assert ia.resolver_provider({"ENVIRONMENT": "production"}) == ia.PROVIDER_MOCK

    @pytest.mark.parametrize("chave", ["OPENAI_API_KEY", "EMERGENT_LLM_KEY"])
    def test_producao_com_chave_usa_o_modelo(self, chave):
        assert ia.resolver_provider({"ENVIRONMENT": "production", chave: "k"}) == ia.PROVIDER_OPENAI

    def test_a_variavel_manda_e_o_desconhecido_cai_no_simulado(self):
        assert ia.resolver_provider({"EXEC_REPORT_AI_PROVIDER": "mock", "ENVIRONMENT": "production",
                                     "OPENAI_API_KEY": "k"}) == ia.PROVIDER_MOCK
        assert ia.resolver_provider({"EXEC_REPORT_AI_PROVIDER": "xpto"}) == ia.PROVIDER_MOCK


class TestGerarAnalise:
    @pytest.mark.asyncio
    async def test_em_dev_o_texto_e_simulado_e_nao_chama_o_modelo(self):
        chamar = AsyncMock()
        with patch.object(ia, "_chamar_modelo", chamar):
            r = await ia.gerar_analise(RELATORIO, ambiente={"ENVIRONMENT": "dev"})
        assert r["origem"] == ia.ORIGEM_SIMULADA and "simulado" in r["texto"].lower()
        assert "Ana Costa" in r["texto"]
        chamar.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_o_simulado_e_deterministico(self):
        a = await ia.gerar_analise(RELATORIO, ambiente={})
        b = await ia.gerar_analise(RELATORIO, ambiente={})
        assert a == b

    @pytest.mark.asyncio
    async def test_sem_colaboradores_nao_gasta_chamada(self):
        chamar = AsyncMock()
        with patch.object(ia, "_chamar_modelo", chamar):
            r = await ia.gerar_analise({**RELATORIO, "users": []},
                                       ambiente={"ENVIRONMENT": "production", "OPENAI_API_KEY": "k"})
        assert r is None
        chamar.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_producao_usa_o_modelo_do_painel_e_o_texto_limpo(self):
        chamar = AsyncMock(return_value=("## Análise\n\n" + TEXTO_BOM, {"entrada": 300, "saida": 120}))
        with patch.object(ia, "resolver_modelo", AsyncMock(return_value="gpt-4o")), \
                patch.object(ia, "_chamar_modelo", chamar), \
                patch.object(ia, "_registar_uso", AsyncMock()) as uso:
            r = await ia.gerar_analise(RELATORIO, ambiente={"ENVIRONMENT": "production", "OPENAI_API_KEY": "k"})
        assert r["origem"] == ia.ORIGEM_IA and "##" not in r["texto"] and "Ana Costa" in r["texto"]
        assert chamar.await_args.args[1] == "gpt-4o"
        assert uso.await_args.args[3] is True  # sucesso registado

    @pytest.mark.asyncio
    @pytest.mark.parametrize("falha", ["excepcao", "vazio", "com_endereco", "curto"])
    async def test_falha_ou_resposta_inaproveitavel_nao_para_o_pdf(self, falha):
        if falha == "excepcao":
            chamar = AsyncMock(side_effect=RuntimeError("openai em baixo"))
        else:
            texto = {"vazio": "", "com_endereco": "Escreva para x@y.pt " * 10, "curto": "Ok."}[falha]
            chamar = AsyncMock(return_value=(texto, {}))
        with patch.object(ia, "resolver_modelo", AsyncMock(return_value="m")), \
                patch.object(ia, "_chamar_modelo", chamar), patch.object(ia, "_registar_uso", AsyncMock()):
            r = await ia.gerar_analise(RELATORIO, ambiente={"ENVIRONMENT": "production", "OPENAI_API_KEY": "k"})
        assert r is None

    @pytest.mark.asyncio
    async def test_o_pedido_ao_cliente_openai_leva_o_modelo_e_so_numeros(self):
        """Um nível abaixo: o que SAI para o SDK, não o resultado."""
        criar = AsyncMock(return_value=MagicMock(
            choices=[MagicMock(message=MagicMock(content=TEXTO_BOM))],
            usage=MagicMock(prompt_tokens=10, completion_tokens=5)))
        cliente = MagicMock()
        cliente.chat.completions.create = criar
        with patch("services.ai_document.get_openai_client", return_value=cliente), \
                patch.object(ia, "resolver_modelo", AsyncMock(return_value="gpt-4o-config")), \
                patch.object(ia, "_registar_uso", AsyncMock()):
            await ia.gerar_analise(RELATORIO, ambiente={"ENVIRONMENT": "production", "OPENAI_API_KEY": "k"})
        enviado = criar.await_args.kwargs
        assert enviado["model"] == "gpt-4o-config"
        conteudo = json.dumps(enviado["messages"], ensure_ascii=False)
        assert "@" not in conteudo and "u-secreto" not in conteudo and "4321" not in conteudo
        assert enviado["max_tokens"] <= 800

    @pytest.mark.asyncio
    async def test_o_modelo_vem_do_painel_de_ia(self):
        with patch("services.ai_page_analyzer.get_ai_config",
                   AsyncMock(return_value={ia.CHAVE_AI_CONFIG: "modelo-do-admin"})):
            assert await ia.resolver_modelo() == "modelo-do-admin"
        with patch("services.ai_page_analyzer.get_ai_config", AsyncMock(side_effect=RuntimeError("x"))):
            assert await ia.resolver_modelo() == ia.MODELO_OMISSAO

    def test_a_tarefa_esta_registada_no_painel_de_ia(self):
        from config import AI_CONFIG_DEFAULTS

        assert ia.CHAVE_AI_CONFIG in AI_CONFIG_DEFAULTS


class TestOPdf:
    """Lido com PyMuPDF: a secção está (ou não) no documento que se descarrega."""

    @staticmethod
    def _texto(pdf: bytes) -> str:
        import fitz

        with fitz.open(stream=pdf, filetype="pdf") as doc:
            return "\n".join(p.get_text() for p in doc)

    def _construir(self, analise):
        from services.executive_report_pdf import construir_pdf

        return construir_pdf(RELATORIO, empresa={"nome": "Power"}, analise=analise)

    def test_sem_analise_o_pdf_e_o_de_sempre(self):
        texto = self._texto(self._construir(None))
        assert "Análise de desempenho" not in texto and "inteligência artificial" not in texto

    def test_com_analise_a_seccao_e_o_aviso_estao_no_pdf(self):
        texto = self._texto(self._construir({"texto": TEXTO_BOM, "origem": ia.ORIGEM_IA}))
        assert "Análise de desempenho" in texto
        assert "manteve um ritmo estável" in texto
        assert "gerado por inteligência artificial" in texto.replace("\n", " ").lower() or "inteligência artificial" in texto

    def test_a_analise_simulada_diz_que_e_simulada(self):
        texto = self._texto(self._construir({"texto": "Texto de teste com mais de sessenta caracteres para o PDF.", "origem": ia.ORIGEM_SIMULADA}))
        assert "simulado" in texto.lower()
        assert "gerado por inteligência artificial" not in texto.replace("\n", " ").lower()

    def test_html_no_texto_nao_parte_o_pdf(self):
        self._construir({"texto": "A equipa <b>fez</b> & concluiu tarefas suficientes para este período de análise.", "origem": ia.ORIGEM_IA})


class TestAOpcaoDeVerdade:
    """Sem o pedido não há chamada — a razão de ser do «opcional»."""

    def _rel(self):
        return {**RELATORIO, "movimentos": []}

    async def _pdf(self, **kw):
        import services.executive_report_api as api

        gerar = AsyncMock(return_value=self._rel())
        analise = kw.pop("analise", AsyncMock(return_value={"texto": TEXTO_BOM, "origem": ia.ORIGEM_IA}))
        with patch.object(er, "resolver_ambito", AsyncMock(return_value=er.Ambito(chave="x"))), \
                patch.object(er, "gerar_relatorio", gerar), \
                patch.object(ia, "gerar_analise", analise), \
                patch.object(api, "_branding", AsyncMock(return_value={"empresa": {}, "logo_bytes": None, "accent": "#334155"})):
            ceo = {"id": "u", "role": "ceo", "name": "CEO"}
            resp = await api.run_team_performance_pdf(ceo, "2026-10-05", "2026-10-11", **kw)
            semanal = None
            with patch("services.executive_weekly.obter_semana", AsyncMock(return_value=self._rel())):
                semanal = await api.run_weekly_pdf(ceo, "2026-10-05", **kw)
        return resp, semanal, analise

    @pytest.mark.asyncio
    async def test_por_omissao_nao_chama_o_modelo(self):
        resp, semanal, analise = await self._pdf()
        analise.assert_not_awaited()
        assert resp.headers["x-analise-ia"] == semanal.headers["x-analise-ia"] == "nao-pedida"
        assert "Análise de desempenho" not in TestOPdf._texto(resp.body)

    @pytest.mark.asyncio
    async def test_pedida_chama_o_modelo_nos_dois_pdfs_e_o_texto_vai_no_documento(self):
        resp, semanal, analise = await self._pdf(ai_analysis=True)
        assert analise.await_count == 2
        for r in (resp, semanal):
            assert r.headers["x-analise-ia"] == "incluida"
            assert "manteve um ritmo estável" in TestOPdf._texto(r.body)
            assert "X-Analise-IA" in r.headers["access-control-expose-headers"]

    @pytest.mark.asyncio
    async def test_pedida_em_dev_diz_simulada(self):
        simulada = AsyncMock(return_value={"texto": "Texto simulado de teste com sessenta caracteres no mínimo ok.", "origem": ia.ORIGEM_SIMULADA})
        resp, _, _ = await self._pdf(ai_analysis=True, analise=simulada)
        assert resp.headers["x-analise-ia"] == "simulada"

    @pytest.mark.asyncio
    async def test_pedida_mas_indisponivel_o_pdf_sai_e_o_servidor_di_lo(self):
        resp, semanal, _ = await self._pdf(ai_analysis=True, analise=AsyncMock(return_value=None))
        for r in (resp, semanal):
            assert r.body[:5] == b"%PDF-"
            assert r.headers["x-analise-ia"] == "indisponivel"
            assert "Análise de desempenho" not in TestOPdf._texto(r.body)

    def test_as_rotas_trazem_o_parametro_desligado_por_omissao(self):
        import ast
        from pathlib import Path

        fonte = (Path(__file__).resolve().parents[2] / "routes" / "admin.py").read_text(encoding="utf-8")
        arvore = ast.parse(fonte)
        encontradas = {}
        for no in ast.walk(arvore):
            if isinstance(no, ast.AsyncFunctionDef) and no.name in {"get_team_performance_pdf", "get_executive_weekly_pdf"}:
                args = {a.arg: d for a, d in zip(no.args.args[-len(no.args.defaults):], no.args.defaults)}
                encontradas[no.name] = ast.unparse(args["ai_analysis"])
        assert set(encontradas) == {"get_team_performance_pdf", "get_executive_weekly_pdf"}
        for texto in encontradas.values():
            assert texto.startswith("Query(False")

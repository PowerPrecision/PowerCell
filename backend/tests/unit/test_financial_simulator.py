"""Testes unitários do Motor de Simulação Financeira (DSTI & Cenários).

ÉPICO "Motor de Simulação Financeira" — cobertura de
``services/financial_simulator.py`` (matemática pura + orquestração
síncrona) e das funções puras de ``services/financial_engine.py`` que
decidem quando o motor dispara.

REGRA DE ARQUITETURA (ver tests/unit/conftest.py): sem MongoDB vivo.
Tudo aqui é determinístico — a Euribor e a configuração entram como
argumentos, nunca por I/O.
"""

from unittest.mock import AsyncMock, patch

import pytest

from models.system_config import SystemConfig
from services.dsti_service import calculate_dsti
from services.financial_simulator import (
    MONTHS_PER_YEAR,
    REASON_NO_CAPITAL,
    REASON_NO_INCOME,
    SCENARIO_FIXA,
    SCENARIO_MISTA,
    SCENARIO_ORDER,
    SCENARIO_VARIAVEL,
    build_scenario_definitions,
    build_simulation,
    calcular_capital_em_divida,
    calcular_prestacao_mensal,
    calcular_taeg,
    calcular_taeg_fluxos,
    project_dsti,
    resolve_euribor_index,
    resolve_simulation_inputs,
    simulate_scenario,
)


# ====================================================================
# FIXTURES
# ====================================================================


@pytest.fixture
def config():
    """Configuração por defeito do sistema (defaults dos modelos)."""
    return SystemConfig()


@pytest.fixture
def euribor_rates():
    """Payload típico de `euribor_service.get_euribor_rates()` (API viva)."""
    return {
        "euribor_1m": 2.30,
        "euribor_3m": 2.35,
        "euribor_6m": 2.40,
        "euribor_12m": 2.45,
        "fetched_at": "2026-09-21T08:00:00+00:00",
        "is_fallback": False,
        "source": "api",
    }


@pytest.fixture
def process():
    """Processo de Crédito Habitação com rendimentos e dados de crédito."""
    return {
        "id": "proc-ch-1",
        "process_number": "P-2026-0042",
        "client_name": "Ana Silva",
        "process_type": "credito_habitacao",
        "financial_data": {
            "rendimento_liquido_total": 2200.0,
            "prestacao_creditos_mensal": 180.0,
            "numero_creditos_ativos": 2,
        },
        "credit_data": {"requested_amount": 200000, "loan_term_years": 30},
        "real_estate_data": {"valor_imovel": 250000},
    }


def _simulate(process, config, euribor_rates):
    return build_simulation(
        process=process,
        dsti_base=calculate_dsti(process),
        euribor_rates=euribor_rates,
        sim_config=config.financial_simulator,
        credit_config=config.credit_services,
        dsti_config=config.dsti_analysis,
    )


# ====================================================================
# MATEMÁTICA — Sistema Francês
# ====================================================================


class TestPrestacaoMensal:
    def test_valor_conhecido_sistema_frances(self):
        """200.000 € a 3,5% / 30 anos → 898,09 €/mês (referência conhecida)."""
        assert round(calcular_prestacao_mensal(200000, 3.5, 360), 2) == 898.09

    def test_taxa_zero_degrada_para_amortizacao_linear(self):
        assert calcular_prestacao_mensal(120000, 0, 240) == pytest.approx(500.0)

    def test_parametros_invalidos_devolvem_zero(self):
        assert calcular_prestacao_mensal(0, 3.5, 360) == 0.0
        assert calcular_prestacao_mensal(200000, 3.5, 0) == 0.0
        assert calcular_prestacao_mensal(None, None, None) == 0.0

    def test_prazo_maior_baixa_prestacao(self):
        curto = calcular_prestacao_mensal(200000, 3.5, 240)
        longo = calcular_prestacao_mensal(200000, 3.5, 480)
        assert longo < curto

    def test_taxa_maior_sobe_prestacao(self):
        barato = calcular_prestacao_mensal(200000, 2.0, 360)
        caro = calcular_prestacao_mensal(200000, 4.0, 360)
        assert caro > barato


class TestCapitalEmDivida:
    def test_antes_de_pagar_devolve_capital_inteiro(self):
        assert calcular_capital_em_divida(200000, 3.5, 360, 0) == 200000.0

    def test_no_fim_do_prazo_fica_zero(self):
        assert calcular_capital_em_divida(200000, 3.5, 360, 360) == 0.0

    def test_amortizacao_e_lenta_no_inicio(self):
        """Após 5 de 30 anos ainda falta >85% do capital (juros à cabeça)."""
        saldo = calcular_capital_em_divida(200000, 3.5, 360, 60)
        assert 0 < saldo < 200000
        assert saldo / 200000 > 0.85

    def test_taxa_zero_amortiza_linearmente(self):
        assert calcular_capital_em_divida(120000, 0, 240, 120) == 60000.0

    def test_saldo_coerente_com_prestacoes_pagas(self):
        """Saldo(k) reconstruído mês a mês bate com a fórmula fechada."""
        capital, taxa, meses = 150000, 3.0, 300
        prestacao = calcular_prestacao_mensal(capital, taxa, meses)
        r = taxa / 100 / MONTHS_PER_YEAR
        saldo = capital
        for _ in range(24):
            saldo = saldo * (1 + r) - prestacao
        assert calcular_capital_em_divida(
            capital, taxa, meses, 24
        ) == pytest.approx(saldo, abs=0.01)


class TestTaeg:
    def test_sem_encargos_taeg_iguala_tan(self):
        prestacao = calcular_prestacao_mensal(200000, 3.5, 360)
        assert calcular_taeg(200000, prestacao, 0, 360) == pytest.approx(
            3.5, abs=0.01
        )

    def test_seguros_aumentam_a_taeg(self):
        prestacao = calcular_prestacao_mensal(200000, 3.5, 360)
        sem = calcular_taeg(200000, prestacao, 0, 360)
        com = calcular_taeg(200000, prestacao, 40, 360)
        assert com > sem

    def test_fluxos_variaveis_ficam_entre_as_duas_taxas(self):
        """Fluxo misto (3% depois 4%) → TAEG entre 3% e 4%."""
        capital = 100000
        prest_baixa = calcular_prestacao_mensal(capital, 3.0, 240)
        prest_alta = calcular_prestacao_mensal(capital, 4.0, 240)
        taeg = calcular_taeg_fluxos(
            capital, [prest_baixa] * 60 + [prest_alta] * 180
        )
        assert 3.0 < taeg < 4.0

    def test_dados_invalidos_devolvem_zero(self):
        assert calcular_taeg_fluxos(0, [500] * 12) == 0.0
        assert calcular_taeg_fluxos(100000, []) == 0.0
        assert calcular_taeg(100000, 0, 0, 240) == 0.0


# ====================================================================
# RESOLUÇÃO DO INDEXANTE
# ====================================================================


class TestResolveEuriborIndex:
    def test_usa_o_indice_pedido(self, euribor_rates):
        resolved = resolve_euribor_index(euribor_rates, "6m")
        assert resolved["index"] == "6m"
        assert resolved["rate_pct"] == 2.40
        assert resolved["is_fallback"] is False

    def test_indice_em_falta_cai_para_outra_maturidade(self):
        resolved = resolve_euribor_index({"euribor_3m": 2.1}, "12m")
        assert resolved["index"] == "3m"
        assert resolved["rate_pct"] == 2.1
        assert resolved["is_fallback"] is True

    def test_payload_de_fallback_e_sinalizado(self, euribor_rates):
        resolved = resolve_euribor_index(
            {**euribor_rates, "is_fallback": True, "source": "fallback"}, "12m"
        )
        assert resolved["is_fallback"] is True
        assert resolved["source"] == "fallback"

    def test_sem_taxas_nao_rebenta(self):
        resolved = resolve_euribor_index({}, "12m")
        assert resolved["rate_pct"] == 0.0
        assert resolved["is_fallback"] is True


# ====================================================================
# DEFINIÇÃO E SIMULAÇÃO DE CENÁRIOS
# ====================================================================


class TestScenarioDefinitions:
    def test_tres_cenarios_na_ordem_canonica(self, config):
        definitions = build_scenario_definitions(
            euribor_pct=2.45, sim_config=config.financial_simulator, num_meses=360
        )
        assert [d["key"] for d in definitions] == list(SCENARIO_ORDER)

    def test_taxas_saem_da_configuracao_sem_hardcoding(self, config):
        cfg = config.financial_simulator
        definitions = build_scenario_definitions(
            euribor_pct=2.0, sim_config=cfg, num_meses=360
        )
        by_key = {d["key"]: d for d in definitions}
        assert by_key[SCENARIO_VARIAVEL]["taxa_inicial_pct"] == pytest.approx(
            2.0 + cfg.spread_variavel
        )
        assert by_key[SCENARIO_FIXA]["taxa_inicial_pct"] == pytest.approx(
            2.0 + cfg.premio_taxa_fixa + cfg.spread_fixa
        )
        assert by_key[SCENARIO_MISTA]["taxa_posterior_pct"] == pytest.approx(
            2.0 + cfg.spread_mista
        )

    def test_spread_alterado_na_configuracao_muda_a_taxa(self, config):
        config.financial_simulator.spread_variavel = 2.5
        definitions = build_scenario_definitions(
            euribor_pct=2.0, sim_config=config.financial_simulator, num_meses=360
        )
        variavel = next(d for d in definitions if d["key"] == SCENARIO_VARIAVEL)
        assert variavel["taxa_inicial_pct"] == pytest.approx(4.5)

    def test_periodo_fixo_da_mista_limitado_pelo_prazo(self, config):
        config.financial_simulator.periodo_fixo_mista_anos = 10
        definitions = build_scenario_definitions(
            euribor_pct=2.0, sim_config=config.financial_simulator, num_meses=60
        )
        mista = next(d for d in definitions if d["key"] == SCENARIO_MISTA)
        assert mista["periodo_fixo_meses"] == 60


class TestSimulateScenario:
    def test_cenario_de_taxa_unica_nao_tem_segundo_patamar(self):
        scenario = simulate_scenario(
            definition={
                "key": SCENARIO_VARIAVEL,
                "label": "Taxa Variável",
                "descricao": "",
                "indexado": True,
                "spread_pct": 1.0,
                "taxa_inicial_pct": 3.5,
                "taxa_posterior_pct": 3.5,
                "periodo_fixo_meses": 0,
            },
            capital=200000,
            num_meses=360,
        )
        assert scenario["tem_segundo_patamar"] is False
        assert scenario["prestacao_mensal"] == scenario["prestacao_posterior"]
        assert scenario["prestacao_mensal"] == 898.09
        assert scenario["total_juros"] == pytest.approx(
            scenario["total_pago"] - 200000, abs=0.01
        )

    def test_taxa_mista_recalcula_sobre_o_capital_residual(self):
        scenario = simulate_scenario(
            definition={
                "key": SCENARIO_MISTA,
                "label": "Taxa Mista",
                "descricao": "",
                "indexado": True,
                "spread_pct": 1.0,
                "taxa_inicial_pct": 4.0,
                "taxa_posterior_pct": 3.0,
                "periodo_fixo_meses": 60,
            },
            capital=200000,
            num_meses=360,
        )
        assert scenario["tem_segundo_patamar"] is True
        # Taxa desce após o período fixo → prestação desce
        assert scenario["prestacao_posterior"] < scenario["prestacao_mensal"]
        # A prestação posterior é a do capital residual no prazo remanescente
        esperada = calcular_prestacao_mensal(
            scenario["capital_residual_pos_periodo_fixo"], 3.0, 300
        )
        assert scenario["prestacao_posterior"] == pytest.approx(esperada, abs=0.01)

    def test_seguros_entram_na_prestacao_total_e_no_custo(self):
        base = simulate_scenario(
            definition={
                "key": SCENARIO_FIXA, "label": "Taxa Fixa", "descricao": "",
                "indexado": False, "spread_pct": 1.0,
                "taxa_inicial_pct": 3.5, "taxa_posterior_pct": 3.5,
                "periodo_fixo_meses": 360,
            },
            capital=200000, num_meses=360,
        )
        com_seguros = simulate_scenario(
            definition={
                "key": SCENARIO_FIXA, "label": "Taxa Fixa", "descricao": "",
                "indexado": False, "spread_pct": 1.0,
                "taxa_inicial_pct": 3.5, "taxa_posterior_pct": 3.5,
                "periodo_fixo_meses": 360,
            },
            capital=200000, num_meses=360, seguros_mensal=35,
        )
        assert com_seguros["prestacao_total_mensal"] == pytest.approx(
            base["prestacao_mensal"] + 35, abs=0.01
        )
        assert com_seguros["total_seguros"] == pytest.approx(35 * 360, abs=0.01)
        assert com_seguros["total_pago"] > base["total_pago"]
        # Os juros não mudam — seguros não são juros
        assert com_seguros["total_juros"] == base["total_juros"]


# ====================================================================
# CRUZAMENTO COM O DSTI
# ====================================================================


class TestProjectDsti:
    def test_soma_a_nova_prestacao_aos_encargos_existentes(self):
        dsti_base = {
            "is_calculable": True,
            "available_income": 1200.0,
            "components": {
                "rendimento_bruto_total": 4000.0,
                "prestacao_creditos_mensal": 200.0,
                "renda_habitacao": 0.0,
                "despesas_co_titular": 0.0,
            },
        }
        projected = project_dsti(dsti_base, 600.0, limite_pct=50.0)
        assert projected["dsti_pct"] == pytest.approx(20.0)  # (200+600)/4000
        assert projected["dentro_limite"] is True
        assert projected["folga_mensal"] == pytest.approx(600.0)

    def test_acima_do_limite_e_sinalizado(self):
        dsti_base = {
            "is_calculable": True,
            "available_income": 500.0,
            "components": {
                "rendimento_bruto_total": 2000.0,
                "prestacao_creditos_mensal": 300.0,
                "renda_habitacao": 0.0,
                "despesas_co_titular": 0.0,
            },
        }
        projected = project_dsti(dsti_base, 900.0, limite_pct=50.0)
        assert projected["dsti_pct"] == pytest.approx(60.0)
        assert projected["dentro_limite"] is False
        assert projected["risk_level"] == "critico"

    def test_limite_vem_da_configuracao(self):
        dsti_base = {
            "is_calculable": True,
            "available_income": 900.0,
            "components": {
                "rendimento_bruto_total": 3000.0,
                "prestacao_creditos_mensal": 0.0,
                "renda_habitacao": 0.0,
                "despesas_co_titular": 0.0,
            },
        }
        prestacao = 1200.0  # 40% do rendimento bruto
        assert project_dsti(dsti_base, prestacao, limite_pct=50.0)["dentro_limite"]
        assert not project_dsti(
            dsti_base, prestacao, limite_pct=35.0
        )["dentro_limite"]

    def test_sem_rendimento_nao_e_calculavel(self):
        projected = project_dsti(
            {"is_calculable": False, "components": {}}, 500.0, limite_pct=50.0
        )
        assert projected["is_calculable"] is False
        assert projected["risk_level"] == "sem_dados"
        assert projected["dentro_limite"] is False


# ====================================================================
# RESOLUÇÃO DOS INPUTS (capital / prazo)
# ====================================================================


class TestResolveSimulationInputs:
    def test_le_montante_e_prazo_do_processo(self, process, config):
        inputs = resolve_simulation_inputs(
            process, credit_config=config.credit_services
        )
        assert inputs["capital"] == 200000.0
        assert inputs["prazo_anos"] == 30
        assert inputs["num_meses"] == 360
        assert inputs["capital_origem"] == "processo"
        assert inputs["avisos"] == []

    def test_sem_montante_deriva_do_ltv_configurado(self, process, config):
        process["credit_data"] = {}
        config.credit_services.max_loan_to_value = 80.0
        inputs = resolve_simulation_inputs(
            process, credit_config=config.credit_services
        )
        assert inputs["capital"] == 200000.0  # 80% de 250.000
        assert inputs["capital_origem"] == "ltv_valor_imovel"
        assert any("80%" in aviso for aviso in inputs["avisos"])

    def test_capital_proprio_limita_o_financiamento(self, process, config):
        process["credit_data"] = {}
        process["financial_data"]["capital_proprio"] = 100000
        config.credit_services.max_loan_to_value = 90.0
        inputs = resolve_simulation_inputs(
            process, credit_config=config.credit_services
        )
        assert inputs["capital"] == 150000.0  # 250.000 - 100.000

    def test_sem_prazo_usa_o_default_da_configuracao(self, process, config):
        process["credit_data"] = {"requested_amount": 180000}
        config.credit_services.default_term_years = 40
        inputs = resolve_simulation_inputs(
            process, credit_config=config.credit_services
        )
        assert inputs["prazo_anos"] == 40
        assert inputs["prazo_origem"] == "configuracao"
        assert any("40 anos" in aviso for aviso in inputs["avisos"])

    def test_sem_dados_de_credito_nem_imovel_fica_a_zero(self, config):
        inputs = resolve_simulation_inputs({}, credit_config=config.credit_services)
        assert inputs["capital"] == 0.0


# ====================================================================
# SIMULAÇÃO COMPLETA
# ====================================================================


class TestBuildSimulation:
    def test_gera_os_tres_cenarios(self, process, config, euribor_rates):
        result = _simulate(process, config, euribor_rates)
        assert result["success"] is True
        assert [c["key"] for c in result["cenarios"]] == list(SCENARIO_ORDER)
        for cenario in result["cenarios"]:
            assert cenario["prestacao_mensal"] > 0
            assert cenario["taeg_pct"] > 0
            assert cenario["dsti"]["is_calculable"] is True

    def test_variavel_e_mais_barata_que_fixa_com_premio_positivo(
        self, process, config, euribor_rates
    ):
        result = _simulate(process, config, euribor_rates)
        by_key = {c["key"]: c for c in result["cenarios"]}
        assert (
            by_key[SCENARIO_VARIAVEL]["prestacao_mensal"]
            < by_key[SCENARIO_FIXA]["prestacao_mensal"]
        )

    def test_cruza_a_euribor_em_vigor(self, process, config, euribor_rates):
        result = _simulate(process, config, euribor_rates)
        assert result["taxa_indexante"]["index"] == "12m"
        assert result["taxa_indexante"]["rate_pct"] == 2.45
        variavel = next(
            c for c in result["cenarios"] if c["key"] == SCENARIO_VARIAVEL
        )
        assert variavel["taxa_inicial_pct"] == pytest.approx(
            2.45 + config.financial_simulator.spread_variavel
        )

    def test_euribor_estimada_gera_aviso(self, process, config, euribor_rates):
        result = _simulate(
            process,
            config,
            {**euribor_rates, "is_fallback": True, "source": "fallback"},
        )
        assert result["success"] is True
        assert any("estimados" in aviso for aviso in result["avisos"])

    def test_euribor_indisponivel_nao_aborta_a_simulacao(self, process, config):
        result = _simulate(process, config, {})
        assert result["success"] is True
        assert any("Euribor indisponível" in aviso for aviso in result["avisos"])
        variavel = next(
            c for c in result["cenarios"] if c["key"] == SCENARIO_VARIAVEL
        )
        # Só o spread contratado
        assert variavel["taxa_inicial_pct"] == pytest.approx(
            config.financial_simulator.spread_variavel
        )

    def test_avisa_quando_nenhum_cenario_respeita_o_limite(
        self, process, config, euribor_rates
    ):
        process["financial_data"]["rendimento_liquido_total"] = 800.0
        result = _simulate(process, config, euribor_rates)
        assert result["success"] is True
        assert all(
            not c["dsti"]["dentro_limite"] for c in result["cenarios"]
        )
        assert any("limite de taxa de esforço" in a for a in result["avisos"])

    def test_validade_da_proposta_vem_da_configuracao(
        self, process, config, euribor_rates
    ):
        result = _simulate(process, config, euribor_rates)
        assert result["valido_ate"] is not None
        config.credit_services.simulation_validity_days = 0
        assert _simulate(process, config, euribor_rates)["valido_ate"] is None

    def test_resumo_de_rendimentos_reflete_o_dsti(
        self, process, config, euribor_rates
    ):
        result = _simulate(process, config, euribor_rates)
        rendimentos = result["rendimentos"]
        assert rendimentos["rendimento_liquido_total"] == 2200.0
        assert rendimentos["prestacao_creditos_mensal"] == 180.0
        assert result["dsti_atual"]["dsti_pct"] > 0


class TestBuildSimulationDegradacao:
    """O motor nunca inventa números — sinaliza o que falta."""

    def test_sem_rendimento_devolve_pedido_de_revisao(
        self, process, config, euribor_rates
    ):
        process["financial_data"] = {}
        result = _simulate(process, config, euribor_rates)
        assert result["success"] is False
        assert result["reason"] == REASON_NO_INCOME
        assert "rendimento" in result["missing"]
        assert "cenarios" not in result

    def test_sem_montante_nem_imovel_devolve_pedido_de_revisao(
        self, process, config, euribor_rates
    ):
        process["credit_data"] = {}
        process["real_estate_data"] = {}
        result = _simulate(process, config, euribor_rates)
        assert result["success"] is False
        assert result["reason"] == REASON_NO_CAPITAL
        assert "montante_financiamento" in result["missing"]

    def test_processo_vazio_nao_rebenta(self, config, euribor_rates):
        result = build_simulation(
            process={},
            dsti_base=calculate_dsti({}),
            euribor_rates=euribor_rates,
            sim_config=config.financial_simulator,
            credit_config=config.credit_services,
            dsti_config=config.dsti_analysis,
        )
        assert result["success"] is False
        assert result["missing"]


# ====================================================================
# GATILHO (financial_engine — funções puras)
# ====================================================================


class TestClassificacaoDeDocumentos:
    @pytest.mark.parametrize(
        "doc,expected",
        [
            ({"ai_subcategory": "Recibo Vencimento"}, "recibo_vencimento"),
            ({"ai_subcategory": "Irs"}, "irs"),
            ({"ai_subcategory": "Nota Liquidacao"}, "nota_liquidacao"),
            ({"filename": "recibo_vencimento_jan.pdf"}, "recibo_vencimento"),
            ({"ai_category": "Financeiros", "filename": "doc.pdf"}, "irs"),
            ({"ai_category": "Identificação", "filename": "cc.pdf"}, None),
            ({"ai_subcategory": "Caderneta Predial"}, None),
            ({}, None),
            (None, None),
        ],
    )
    def test_classifica_documentos_financeiros(self, doc, expected):
        from services.financial_engine import classify_financial_document

        assert classify_financial_document(doc) == expected


class TestDecisaoDeDisparo:
    def _docs(self, n=1):
        return [{"id": f"d{i}", "financial_doc_type": "irs"} for i in range(n)]

    def test_dispara_com_processo_de_credito_e_documentos(self):
        from services.financial_engine import decide_trigger

        decision = decide_trigger(
            {"process_type": "credito_habitacao"}, self._docs(2), enabled=True
        )
        assert decision["triggered"] is True
        assert decision["documents"] == 2
        assert decision["reason"] is None

    def test_nao_dispara_com_motor_desligado(self):
        from services.financial_engine import SKIP_DISABLED, decide_trigger

        decision = decide_trigger(
            {"process_type": "credito_habitacao"}, self._docs(), enabled=False
        )
        assert decision["triggered"] is False
        assert decision["reason"] == SKIP_DISABLED

    def test_nao_dispara_fora_do_credito(self):
        from services.financial_engine import SKIP_NOT_CREDIT, decide_trigger

        decision = decide_trigger(
            {"process_type": "arrendamento"}, self._docs(), enabled=True
        )
        assert decision["triggered"] is False
        assert decision["reason"] == SKIP_NOT_CREDIT

    def test_nao_dispara_sem_documentos_financeiros(self):
        from services.financial_engine import SKIP_NO_DOCUMENTS, decide_trigger

        decision = decide_trigger(
            {"process_type": "credito_habitacao"}, [], enabled=True
        )
        assert decision["triggered"] is False
        assert decision["reason"] == SKIP_NO_DOCUMENTS


class TestResumoDeCenarios:
    def test_resume_os_campos_uteis_para_a_ui(
        self, process, config, euribor_rates
    ):
        from services.financial_engine import summarize_scenarios

        simulation = _simulate(process, config, euribor_rates)
        resumo = summarize_scenarios(simulation)
        assert len(resumo) == 3
        for linha in resumo:
            assert set(linha) == {
                "key", "label", "taxa_pct", "prestacao_mensal",
                "taeg_pct", "dsti_pct", "dentro_limite",
            }

    def test_simulacao_falhada_resume_para_lista_vazia(self):
        from services.financial_engine import summarize_scenarios

        assert summarize_scenarios({"success": False}) == []


# ====================================================================
# GESTÃO DE FALHAS — o motor nunca encrava o processo
# ====================================================================


class TestGestaoDeFalhas:
    """Regra de ouro: extracção ilegível → aviso de revisão manual, nunca
    um processo bloqueado nem números inventados."""

    async def test_documentos_financeiros_sao_recolhidos_do_processo(
        self, fake_async_db
    ):
        from services import financial_engine

        await fake_async_db.document_metadata.insert_one(
            {"id": "d1", "process_id": "p1", "filename": "irs_2025.pdf",
             "ai_category": "Financeiros", "ai_subcategory": "Irs"}
        )
        await fake_async_db.document_metadata.insert_one(
            {"id": "d2", "process_id": "p1", "filename": "recibo.pdf",
             "ai_category": "Financeiros", "ai_subcategory": "Recibo Vencimento"}
        )
        await fake_async_db.document_metadata.insert_one(
            {"id": "d3", "process_id": "p1", "filename": "cc.pdf",
             "ai_category": "Identificação", "ai_subcategory": "Cc"}
        )
        await fake_async_db.document_metadata.insert_one(
            {"id": "d4", "process_id": "outro", "filename": "irs.pdf",
             "ai_category": "Financeiros", "ai_subcategory": "Irs"}
        )

        with patch.object(financial_engine, "db", fake_async_db):
            docs = await financial_engine.collect_financial_documents("p1")

        assert {d["id"] for d in docs} == {"d1", "d2"}
        assert {d["financial_doc_type"] for d in docs} == {
            "irs", "recibo_vencimento",
        }

    async def test_irs_ilegivel_marca_revisao_manual_sem_bloquear(
        self, fake_async_db
    ):
        from services import financial_engine

        await fake_async_db.processes.insert_one(
            {"id": "p1", "client_name": "Ana", "status": "analise"}
        )

        with patch.object(financial_engine, "db", fake_async_db):
            await financial_engine.flag_manual_review(
                "p1", reason="sem_rendimento", task_id=None
            )

        process = await fake_async_db.processes.find_one({"id": "p1"})
        estado = process["financial_simulation"]
        assert estado["status"] == financial_engine.STATUS_NEEDS_REVIEW
        assert estado["reason"] == "sem_rendimento"
        assert "revisão manual" in estado["message"]
        # O processo NÃO é bloqueado nem revertido
        assert process["status"] == "analise"
        # Aviso visível na timeline do consultor
        atividade = process["activities"][-1]
        assert atividade["action"] == "SIMULACAO_FINANCEIRA_REVISAO_MANUAL"
        assert atividade["type"] == "system"

    async def test_revisao_manual_marca_a_tarefa_como_falhada(
        self, fake_async_db
    ):
        from models.task_log import TaskStatus
        from services import financial_engine

        await fake_async_db.processes.insert_one({"id": "p1"})
        update_mock = AsyncMock()

        with patch.object(financial_engine, "db", fake_async_db), patch(
            "services.task_log_service.TaskLogService.update_task", update_mock
        ):
            await financial_engine.flag_manual_review(
                "p1", reason="pdf_falhou", task_id="task_xyz"
            )

        update_mock.assert_awaited_once()
        assert update_mock.await_args.args[0] == "task_xyz"
        assert update_mock.await_args.kwargs["status"] == TaskStatus.FAILED
        assert update_mock.await_args.kwargs["error_message"]

    async def test_motor_com_processo_inexistente_nao_rebenta(
        self, fake_async_db
    ):
        from services import financial_engine

        with patch.object(financial_engine, "db", fake_async_db):
            result = await financial_engine.run_financial_engine("nao-existe")

        assert result == {"success": False, "reason": "processo_inexistente"}

    async def test_sem_documentos_legiveis_pede_revisao_manual(
        self, fake_async_db
    ):
        """Documentos financeiros presentes mas todos ilegíveis: o motor
        termina em revisão manual em vez de simular com zeros."""
        from services import financial_engine

        await fake_async_db.processes.insert_one(
            {"id": "p1", "client_name": "Ana", "process_type": "credito_habitacao"}
        )
        await fake_async_db.document_metadata.insert_one(
            {"id": "d1", "process_id": "p1", "filename": "irs_ilegivel.pdf",
             "ai_category": "Financeiros", "ai_subcategory": "Irs"}
        )

        with patch.object(financial_engine, "db", fake_async_db), patch.object(
            financial_engine, "_extract_document_data", AsyncMock(return_value=None)
        ):
            result = await financial_engine.run_financial_engine("p1")

        assert result == {"success": False, "reason": "extracao_falhou"}
        process = await fake_async_db.processes.find_one({"id": "p1"})
        assert (
            process["financial_simulation"]["status"]
            == financial_engine.STATUS_NEEDS_REVIEW
        )
        assert "irs_ilegivel.pdf" in process["financial_simulation"]["message"]

    async def test_rendimentos_consolidados_nao_apagam_dados_manuais(
        self, fake_async_db
    ):
        """A persistência é por campo — o que o consultor escreveu à mão
        no financial_data não é apagado pelo motor."""
        from services import financial_engine

        await fake_async_db.processes.insert_one(
            {
                "id": "p1",
                "financial_data": {
                    "valor_pretendido": 175000,
                    "rendimento_liquido_total": 0,
                },
            }
        )

        with patch.object(financial_engine, "db", fake_async_db):
            await financial_engine.persist_financial_data(
                "p1", {"rendimento_liquido_total": 2100.0, "salarios": [{"x": 1}]}
            )

        financial = (await fake_async_db.processes.find_one({"id": "p1"}))[
            "financial_data"
        ]
        assert financial["valor_pretendido"] == 175000  # preservado
        assert financial["rendimento_liquido_total"] == 2100.0  # actualizado
        assert financial["salarios"] == [{"x": 1}]  # acrescentado

    async def test_disparo_falhado_nao_propaga_para_a_indexacao(self):
        """`trigger_financial_engine_safe` devolve sempre um payload —
        um motor em baixo nunca faz falhar o mark-indexed."""
        from services.process_indexing import trigger_financial_engine_safe

        with patch(
            "services.financial_engine.trigger_financial_engine_after_indexing",
            AsyncMock(side_effect=RuntimeError("motor em baixo")),
        ):
            result = await trigger_financial_engine_safe({"id": "p1"}, {"id": "u1"})

        assert result == {
            "triggered": False,
            "reason": None,
            "task_id": None,
            "documents": 0,
        }

    def test_resposta_do_mark_indexed_inclui_o_bloco_do_motor(self):
        from services.process_indexing import build_mark_indexed_response

        payload = build_mark_indexed_response(
            process={},
            process_id="p1",
            process_ref="#1",
            current_status="analise",
            next_status="aprovacao",
            assigned_ids=[],
            consultant_result=None,
            is_pre_registo_transition=False,
            financial_engine={
                "triggered": True, "reason": None,
                "task_id": "task_1", "documents": 2,
            },
        )
        assert payload["financial_engine"]["triggered"] is True
        assert payload["financial_engine"]["task_id"] == "task_1"

    def test_resposta_sem_motor_traz_bloco_neutro(self):
        """Retrocompatibilidade: o frontend lê sempre a mesma forma."""
        from services.process_indexing import build_mark_indexed_response

        payload = build_mark_indexed_response(
            process={}, process_id="p1", process_ref="#1",
            current_status=None, next_status=None, assigned_ids=[],
            consultant_result=None, is_pre_registo_transition=False,
        )
        assert payload["financial_engine"] == {
            "triggered": False, "reason": None, "task_id": None, "documents": 0,
        }


# ====================================================================
# PDF — helpers puros de formatação
# ====================================================================


class TestFormatacaoDaProposta:
    def test_valores_em_formato_pt(self):
        from services.financial_proposal_pdf import format_eur, format_pct

        assert format_eur(1234.5) == "1.234,50 €"
        assert format_eur(0) == "0,00 €"
        assert format_eur(None) == "0,00 €"
        assert format_pct(3.456) == "3,46%"

    def test_nome_do_ficheiro_usa_o_numero_do_processo(self):
        from datetime import datetime, timezone

        from services.financial_proposal_pdf import build_proposal_filename

        moment = datetime(2026, 9, 21, tzinfo=timezone.utc)
        assert build_proposal_filename(
            {"process_number": "P-2026/0042"}, now=moment
        ) == "proposta_financeira_P-2026_0042_20260921.pdf"

    def test_sem_numero_cai_para_o_id(self):
        from datetime import datetime, timezone

        from services.financial_proposal_pdf import build_proposal_filename

        moment = datetime(2026, 9, 21, tzinfo=timezone.utc)
        assert build_proposal_filename(
            {"id": "abcdef1234567890"}, now=moment
        ) == "proposta_financeira_abcdef12_20260921.pdf"

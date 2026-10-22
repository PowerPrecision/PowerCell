"""Afinações do Index (Out 2026): justificação exacta dos alertas, nota da IA saneada, pesquisa avançada
(validação e pipeline), leitura dos pedidos do Portal pelo Index e a saída da Index sem consultor forçado.

O que corre contra um MongoDB real (a pesquisa, a fila) vive em `tests/integration/`.
"""
from __future__ import annotations

import ast
import inspect
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from models.index_module import AlertaDaMatriz, TrabalhoProfissional
from services import index_advanced_search as busca
from services import index_ai as ia
from services import index_matrix as mx
from services import index_store as st
from tests.unit.helpers_fonte import codigo_sem_comentarios
from tests.unit.test_index_matrix import ident, mov, recibo, extrato, NIF_MAL

HOJE = date(2026, 10, 21)


def avalia(*factos, **kw):
    return mx.avaliar(list(factos), hoje=HOJE, **kw)


def por_codigo(achados, codigo):
    (a,) = [x for x in achados if x["code"] == codigo]
    return a


# ====================================================================
# 1. A JUSTIFICAÇÃO EXACTA DE CADA ALERTA
# ====================================================================
class TestFormatacao:
    @pytest.mark.parametrize("valor, texto", [
        (Decimal("0"), "0,00 €"), (Decimal("1234.5"), "1.234,50 €"), (Decimal("1000000"), "1.000.000,00 €"),
        (Decimal("0.005"), "0,01 €"), (Decimal("-150"), "-150,00 €"),
    ])
    def test_euros_em_portugues(self, valor, texto):
        assert mx._eur(valor) == texto

    def test_a_data_em_portugues_e_o_desconhecido_diz_se(self):
        assert mx._dia("2026-03-12") == "12/03/2026"
        assert mx._dia(None) == "data desconhecida" and mx._dia("lixo") == "data desconhecida"

    def test_uma_lista_comprida_corta_e_di_lo(self):
        assert mx._lista(["a", "b", "c", "d", "e"]) == "a; b; c; e mais 2"
        assert mx._lista(["a"]) == "a"


class TestEmReciboSemCredito:
    def test_diz_o_liquido_a_tolerancia_e_a_janela(self):
        r = avalia(recibo(), extrato(movimentos=[mov("350.00")]))
        d = por_codigo(r, "recibo_sem_credito")["detalhe"]
        assert "1.000,00 €" in d and "09/2026" in d
        assert "±10,00 €" in d                       # a tolerância do caso (1 % de 1000)
        assert "01/09/2026" in d and "31/10/2026" in d  # o mês do recibo e o seguinte

    def test_extrato_em_falta_di_lo(self):
        d = por_codigo(avalia(recibo()), "extrato_em_falta")["detalhe"]
        assert "09/2026" in d and "1.000,00 €" in d


class TestEmContasNaoBatem:
    def test_bruto_menos_descontos_diferente_do_liquido(self):
        r = avalia(recibo(net="900.00"), extrato(movimentos=[mov("900.00")]))
        d = por_codigo(r, "contas_nao_batem")["detalhe"]
        assert "1.180,00 €" in d and "180,00 €" in d and "1.000,00 €" in d and "900,00 €" in d
        assert "diferença de 100,00 €" in d

    def test_a_taxa_da_seguranca_social(self):
        r = avalia(recibo(ss="300.00"), extrato())
        d = por_codigo(r, "contas_nao_batem")["detalhe"]
        assert "Segurança Social" in d and "25,42 %" in d and "11 % ou 23,75 %" in d

    def test_as_varias_razoes_juntam_se_numa_so_justificacao(self):
        """Duas verificações dão o mesmo código: descartar a segunda escondia o motivo."""
        r = avalia(recibo(net="900.00", ss="300.00"), extrato(movimentos=[mov("900.00")]))
        (a,) = [x for x in r if x["code"] == "contas_nao_batem"]
        assert "diferença de" in a["detalhe"] and "Segurança Social" in a["detalhe"]

    def test_o_irs_acima_do_plausivel(self):
        r = avalia(recibo(irs="700.00", deductions="180.00"), extrato())
        d = [x for x in r if x["code"] == "contas_nao_batem"][0]["detalhe"]
        assert "IRS" in d and "59,3 %" in d


class TestEmSaldoNaoBate:
    def test_diz_a_conta_inteira(self):
        e = extrato(opening="500.00", closing="1500.00", movimentos=[mov("1000.00"), mov("200.00", k="d")])
        d = por_codigo(avalia(e), "saldo_nao_bate")["detalhe"]
        assert "500,00 €" in d and "1.000,00 €" in d and "200,00 €" in d
        assert "dá 1.300,00 €" in d and "saldo final indicado é 1.500,00 €" in d and "diferença de 200,00 €" in d

    def test_contraprova_um_saldo_certo_nao_alerta(self):
        e = extrato(opening="500.00", closing="1300.00", movimentos=[mov("1000.00"), mov("200.00", k="d")])
        assert avalia(e) == []


class TestEmMovimentoEstranho:
    def test_numerario_alto_diz_o_valor_a_data_e_a_pagina(self):
        e = extrato(movimentos=[mov("1500.00", k="d", d="2026-03-12", canal="numerario", page=2)])
        d = por_codigo(avalia(e), "movimento_estranho")["detalhe"]
        assert d == "Levantamento em numerário de 1.500,00 € a 12/03/2026 (pág. 2)."

    def test_um_deposito_diz_deposito(self):
        e = extrato(movimentos=[mov("2000.00", k="c", d="2026-03-05", canal="numerario")])
        assert "Depósito em numerário de 2.000,00 €" in por_codigo(avalia(e), "movimento_estranho")["detalhe"]

    def test_a_recorrencia_diz_quantas_vezes_e_o_total(self):
        e = extrato(movimentos=[mov("150.00", cp="abc") for _ in range(4)])
        d = por_codigo(avalia(e), "movimento_estranho")["detalhe"]
        assert "4 movimentos de 100,00 € ou mais" in d and "600,00 €" in d

    def test_a_contraparte_nunca_vai_para_o_texto(self):
        """Só se guarda a impressão (12 hex): nem ela nem um nome entram na justificação."""
        e = extrato(movimentos=[mov("150.00", cp="deadbeef0001") for _ in range(3)])
        assert "deadbeef0001" not in por_codigo(avalia(e), "movimento_estranho")["detalhe"]

    def test_a_nota_da_ia_acompanha_o_movimento_verificado(self):
        e = extrato(movimentos=[mov("1500.00", d="2026-03-12", canal="transferencia", page=3)])
        e["achados"] = [{"tipo": "numerario_atipico", "v": "1500.00", "d": "2026-03-12", "page": 3,
                         "nota": "Levantamento sem origem aparente"}]
        d = por_codigo(avalia(e), "movimento_estranho")["detalhe"]
        assert "Movimento atípico de 1.500,00 € a 12/03/2026 (pág. 3)" in d
        assert "nota da IA: Levantamento sem origem aparente" in d

    def test_o_valor_do_alerta_sai_do_movimento_nao_da_nota(self):
        """A IA diz «500 €» na nota mas o movimento verificado é de 1.500 €: vale o movimento."""
        e = extrato(movimentos=[mov("1500.00", d="2026-03-12")])
        e["achados"] = [{"tipo": "numerario_atipico", "v": "1500.00", "d": "2026-03-12", "nota": "Levantamento de 500 €"}]
        d = por_codigo(avalia(e), "movimento_estranho")["detalhe"]
        assert d.startswith("Movimento atípico de 1.500,00 €")

    def test_uma_nota_sem_movimento_que_a_sustente_nao_cria_alerta(self):
        e = extrato(movimentos=[mov("100.00")])
        e["achados"] = [{"tipo": "numerario_atipico", "v": "9999.00", "d": "2026-03-12", "nota": "inventado"}]
        assert avalia(e) == []

    def test_o_movimento_nao_se_repete_se_o_codigo_e_a_ia_o_apontam(self):
        e = extrato(movimentos=[mov("1500.00", k="d", d="2026-03-12", canal="numerario", page=2)])
        e["achados"] = [{"tipo": "numerario_atipico", "v": "1500.00", "d": "2026-03-12", "page": 2, "nota": "levantamento alto"}]
        d = por_codigo(avalia(e), "movimento_estranho")["detalhe"]
        assert d == "Levantamento em numerário de 1.500,00 € a 12/03/2026 (pág. 2) — nota da IA: levantamento alto."


class TestEmReciboIrreal:
    def test_cada_motivo_diz_se(self):
        r = avalia(recibo(period="2027-05", net="2000.00", gross="1000.00", deductions="0.00"), extrato())
        d = por_codigo(r, "recibo_irreal")["detalhe"]
        assert "05/2027 ainda não existe" in d and "líquido (2.000,00 €) é superior ao ilíquido (1.000,00 €)" in d

    def test_o_iban(self):
        r = avalia(recibo(iban="PT50000000000000000000001"), extrato(iban="PT50000000000000000000002"))
        assert "IBAN" in por_codigo(r, "recibo_irreal")["detalhe"]


class TestEmNifEIdentificacao:
    def test_nif_invalido_diz_o_nif(self):
        d = por_codigo(avalia(recibo(employer_nif=NIF_MAL), extrato()), "nif_invalido")["detalhe"]
        assert NIF_MAL in d and "09/2026" in d

    def test_nif_incoerente_diz_os_dois(self):
        r = avalia(recibo(), extrato(), entidades={"acme": "509442013"})
        d = por_codigo(r, "nif_entidade_incoerente")["detalhe"]
        assert "501964843" in d and "509442013" in d

    def test_identificacao_expirada_e_ilegivel(self):
        assert "validade" in por_codigo(avalia(ident(expirada=True)), "identificacao_expirada")["detalhe"]
        assert "ilegível" in por_codigo(avalia(ident(legivel=False)), "identificacao_ilegivel")["detalhe"]


class TestTodoAchadoTemJustificacao:
    def test_nenhum_achado_da_matriz_sai_sem_detalhe(self):
        """Contraprova do inventário: junta TODOS os códigos que a matriz sabe produzir."""
        factos = [
            recibo(period="2027-05", net="2000.00", gross="1000.00", deductions="0.00", ss="300.00",
                   employer_nif=NIF_MAL),
            recibo("r2", period="2026-03"),
            extrato(opening="500.00", closing="9999.00",
                    movimentos=[mov("1500.00", k="d", canal="numerario"), *[mov("150.00", cp="x") for _ in range(3)]]),
            ident(expirada=True), ident("i2", legivel=False),
        ]
        achados = avalia(*factos, entidades={"acme": "509442013"})
        produzidos = {a["code"] for a in achados}
        assert {"nif_invalido", "contas_nao_batem", "recibo_irreal", "saldo_nao_bate", "movimento_estranho",
                "identificacao_expirada", "identificacao_ilegivel", "extrato_em_falta"} <= produzidos
        assert [a["code"] for a in achados if not a.get("detalhe")] == []


# ====================================================================
# 2. O DETALHE CHEGA AO ALERTA, À BASE DE DADOS E AO ECRÃ
# ====================================================================
class TestODetalheDoAlerta:
    def _alerta(self, **kw):
        return AlertaDaMatriz(id="a", process_id="p", code="saldo_nao_bate", run_id="r", **kw)

    def test_e_texto_simples_numa_linha_com_tecto(self):
        a = self._alerta(detail="  duas\n\nlinhas   e   espaços  " + "x" * 900)
        assert "\n" not in a.detail and "  " not in a.detail and len(a.detail) <= 600

    def test_vazio_e_nada(self):
        assert self._alerta(detail="   ").detail is None and self._alerta().detail is None

    def test_a_severidade_e_a_mensagem_continuam_a_vir_da_tabela(self):
        a = self._alerta(detail="x", severity="info", message="inventada")
        assert a.severity != "info" and a.message != "inventada"

    async def test_a_substituicao_grava_o_detalhe(self, fake_async_db):
        with patch.object(st, "db", fake_async_db):
            await st.substituir_alertas("p", "rede", "run-1", [
                {"code": "saldo_nao_bate", "refs": [{"document_id": "d1", "page": None}], "periodo": None,
                 "detalhe": "Saldo inicial 500 + … diferença de 200,00 €."},
            ])
        (doc,) = await fake_async_db.process_index_alerts.find({"process_id": "p"}).to_list(10)
        assert doc["detail"] == "Saldo inicial 500 + … diferença de 200,00 €."

    async def test_reescrever_a_justificacao_nao_ressuscita_um_dispensado(self, fake_async_db):
        """O detalhe NÃO entra na assinatura: um texto novo não faz renascer o que a pessoa dispensou."""
        achado = {"code": "saldo_nao_bate", "refs": [{"document_id": "d1", "page": None}], "periodo": None,
                  "detalhe": "versão 1"}
        with patch.object(st, "db", fake_async_db):
            await st.substituir_alertas("p", None, "r1", [achado])
            (doc,) = await fake_async_db.process_index_alerts.find({"process_id": "p"}).to_list(10)
            await st.dispensar_alerta("p", doc["id"], "u")
            await st.substituir_alertas("p", None, "r2", [{**achado, "detalhe": "versão 2, reescrita"}])
        todos = await fake_async_db.process_index_alerts.find({"process_id": "p"}).to_list(10)
        assert len(todos) == 1 and todos[0]["dismissed_by_human"] is True

    def test_a_bancada_devolve_o_detalhe(self):
        from services import index_api

        fonte = codigo_sem_comentarios(inspect.getsource(index_api.run_get_index_workstation))
        assert '"detail": a.get("detail")' in fonte or "'detail': a.get('detail')" in fonte


# ====================================================================
# 3. A NOTA DA IA É SANEADA
# ====================================================================
class TestNotaDaIA:
    @pytest.mark.parametrize("bruto", [None, "", "   ", "curta", 42, {"x": 1}, ["a"]])
    def test_o_que_nao_e_texto_util_e_nada(self, bruto):
        assert ia.nota_da_ia(bruto) is None

    def test_tira_ibans_numeros_longos_e_enderecos(self):
        t = ia.nota_da_ia("Levantamento para PT50 0002 0123 1234 5678 9015 4, NIF 501964843, ver https://x.pt/a e www.y.pt")
        assert "PT50" not in t and "501964843" not in t and "http" not in t and "www" not in t
        assert t.count("…") >= 3

    @pytest.mark.parametrize("iban", ["PT50BKBK0123456789012", "pt50 0002 0123 1234 5678 9015 4", "ES9121000418450200051332"])
    def test_um_iban_com_letras_no_meio_tambem_sai(self, iban):
        """O padrão dos «números longos» não apanha um IBAN compacto (as letras partem a sequência)."""
        t = ia.nota_da_ia(f"Transferência de 500 € para a conta {iban} no dia 12")
        assert iban.upper()[:4] not in t.upper() and "500 €" in t

    def test_nao_guarda_html(self):
        assert "<" not in ia.nota_da_ia("<script>alert(1)</script> levantamento alto")

    def test_tem_tecto(self):
        assert len(ia.nota_da_ia("levantamento " * 100)) <= ia.TECTO_DA_NOTA_DA_IA

    def test_um_valor_curto_e_uma_data_sobrevivem(self):
        assert ia.nota_da_ia("Levantamento em numerário de 1.500 € a 12/03") == "Levantamento em numerário de 1.500 € a 12/03"

    def test_o_extrato_normalizado_leva_a_nota_saneada(self):
        bruto = {"movements": [{"amount": 1500, "kind": "debit", "date": "2026-03-12", "channel": "numerario"}],
                 "findings": [{"type": "numerario_atipico", "amount": 1500, "date": "2026-03-12",
                               "description": "Levantamento de 1.500 € para IBAN PT50000201231234567890154"}]}
        (achado,) = ia.normalizar_extrato(bruto, document_id="d")["factos"]["achados"]
        assert achado["nota"] and "PT50" not in achado["nota"]

    def test_o_esquema_pede_a_justificacao_e_o_prompt_di_lo(self):
        """Ao nível do que SAI para o modelo: o esquema declara `description` e o prompt exige-a."""
        props = ia.definicao_da_ferramenta(ia.TIPO_EXTRATO)["function"]["parameters"]["properties"]
        assert "description" in props["findings"]["items"]["properties"]
        prompt = ia.PROMPTS_POR_TIPO[ia.TIPO_EXTRATO]
        assert "description" in prompt and "nomes de pessoas" in prompt and "IBANs" in prompt

    def test_o_esquema_do_recibo_pede_a_localidade(self):
        props = ia.definicao_da_ferramenta(ia.TIPO_RECIBO)["function"]["parameters"]["properties"]
        assert "employer_location" in props

    def test_a_versao_do_esquema_nao_mudou(self):
        """Mudar a versão invalidava a impressão de TODOS os ficheiros já analisados (milhares de chamadas pagas)."""
        assert ia.ESQUEMA_VERSAO == "2"


# ====================================================================
# 4. A LOCALIDADE DA ENTIDADE
# ====================================================================
class TestLocalidade:
    def test_o_recibo_normalizado_leva_a_localidade(self):
        r = ia.normalizar_recibo({"employer_location": {"value": "  Setúbal ", "confidence": "alta"}}, document_id="d")
        assert r["job"].employer_location == "Setúbal"

    def test_nao_e_revisavel_um_trabalho_sem_localidade_nao_fica_a_rever(self):
        t = TrabalhoProfissional(job_id="j")
        assert "employer_location" not in t.campos_a_rever()

    def test_vem_do_recibo_mais_recente_que_a_tem(self):
        nif = {"value": "501964843"}
        a = TrabalhoProfissional(job_id="x", period="2026-08", employer_location="Porto", employer_nif=nif)
        b = TrabalhoProfissional(job_id="x", period="2026-09", employer_nif=nif)  # o mais recente não a traz
        (t,) = st.calcular_trabalhos([("d1", a), ("d2", b)])
        assert t.employer_location == "Porto"

    def test_um_texto_longo_ou_vazio_nao_e_localidade(self):
        assert TrabalhoProfissional(job_id="x", employer_location="   ").employer_location is None
        assert len(TrabalhoProfissional(job_id="x", employer_location="L" * 500).employer_location) == 80


# ====================================================================
# 5. A PESQUISA AVANÇADA — validação e pipeline (o que corre sem Mongo)
# ====================================================================
def _filtros(**kw):
    base = dict(min_salary=None, max_salary=None, contract_type=None, employer_nif=None, employer_name=None,
                employer_location=None, job_title=None, period_from=None, period_to=None, sort="period_desc")
    base.update(kw)
    return base


class TestValidacao:
    def test_sem_filtros_e_valido(self):
        f = busca.validar_filtros(**_filtros())
        assert f["contract_type"] == [] and f["sort"] == "period_desc"

    @pytest.mark.parametrize("kw", [
        {"min_salary": Decimal("-1")}, {"max_salary": Decimal("-1")},
        {"min_salary": Decimal("2"), "max_salary": Decimal("1")},
        {"period_from": "2026-00"}, {"period_to": "26-09"}, {"period_from": "2026-09", "period_to": "2026-08"},
        {"contract_type": ["x"]}, {"sort": "x"}, {"employer_name": "a"}, {"job_title": "a"},
        {"employer_location": "a"}, {"employer_nif": "12"}, {"employer_nif": "abc"},
    ])
    def test_invalidos_sao_422_com_motivo(self, kw):
        with pytest.raises(HTTPException) as e:
            busca.validar_filtros(**_filtros(**kw))
        assert e.value.status_code == 422 and e.value.detail

    def test_o_intervalo_igual_e_valido_e_o_contrato_repetido_junta_se(self):
        f = busca.validar_filtros(**_filtros(min_salary=Decimal("1000"), max_salary=Decimal("1000"),
                                             contract_type=["efetivo", "efetivo", "termo_certo"]))
        assert f["contract_type"] == ["efetivo", "termo_certo"]

    def test_o_nif_aceita_pontuacao(self):
        assert busca.validar_filtros(**_filtros(employer_nif="501 964"))["employer_nif"] == "501964"

    def test_texto_so_com_espacos_e_sem_filtro(self):
        assert busca.validar_filtros(**_filtros(job_title="    "))["job_title"] is None

    def test_os_contratos_validos_sao_os_do_modelo(self):
        from typing import get_args

        from models.index_module import TipoDeContrato

        assert set(busca.CONTRATOS_VALIDOS) == set(get_args(TipoDeContrato))


class TestRegexSemAcentos:
    @pytest.mark.parametrize("pedido, texto", [
        ("joao", "João"), ("JOAO", "joão"), ("Setubal", "Setúbal"), ("acao", "Ação"), ("concelho", "Conçelho"),
    ])
    def test_casa_com_e_sem_acentos(self, pedido, texto):
        import re

        assert re.search(busca.regex_sem_acentos(pedido), texto, re.IGNORECASE)

    @pytest.mark.parametrize("hostil", [".*", "((", "[a-", "a|b", "\\", "$^", "a{2,", "?"])
    def test_o_texto_hostil_nao_e_uma_expressao(self, hostil):
        import re

        padrao = busca.regex_sem_acentos(hostil)
        re.compile(padrao)  # nunca é uma expressão inválida
        assert not re.search(padrao, "qualquer texto normal sem pontuação", re.IGNORECASE)


class TestPipeline:
    def _pipeline(self, **kw):
        f = busca.validar_filtros(**_filtros(**kw))
        return busca.construir_pipeline(f, [], {"network_id": {"$in": ["r"]}}, pagina=2, tamanho=10)

    def test_a_ordem_das_etapas(self):
        etapas = [list(e)[0] for e in self._pipeline(min_salary=Decimal("1000"))]
        # o salário converte-se ANTES de comparar; a fronteira vem DEPOIS dos filtros (menos lookups) e antes do total
        assert etapas == ["$unwind", "$addFields", "$match", "$lookup", "$match", "$facet"]

    def test_sem_filtros_nao_ha_match_de_trabalho(self):
        etapas = [list(e)[0] for e in self._pipeline()]
        assert etapas == ["$unwind", "$addFields", "$lookup", "$match", "$facet"]

    def test_o_salario_e_convertido_a_numero(self):
        conv = self._pipeline()[1]["$addFields"]["net_salary_num"]["$convert"]
        assert conv["to"] == "double" and conv["onError"] is None

    def test_o_lookup_leva_a_fronteira_e_exclui_eliminados(self):
        lookup = next(e for e in self._pipeline() if "$lookup" in e)["$lookup"]
        corpo = str(lookup["pipeline"][0])
        assert "is_deleted" in corpo and "network_id" in corpo and lookup["from"] == "processes"

    def test_a_paginacao_e_o_tecto(self):
        facet = self._pipeline()[-1]["$facet"]["items"]
        assert {"$skip": 10} in facet and {"$limit": 10} in facet

    def test_o_intervalo_de_salario_e_numerico_e_inclusivo(self):
        match = self._pipeline(min_salary=Decimal("1000.5"), max_salary=Decimal("2000"))[2]["$match"]["$and"][0]
        assert match == {"net_salary_num": {"$ne": None, "$gte": 1000.5, "$lte": 2000.0}}

    def test_o_nome_junta_o_directorio_por_nif(self):
        f = busca.validar_filtros(**_filtros(employer_name="acme"))
        com = busca.construir_pipeline(f, ["509442013"], {}, pagina=1, tamanho=5)[2]["$match"]["$and"][0]
        assert "$or" in com and {"jobs.employer_nif.value": {"$in": ["509442013"]}} in com["$or"]
        sem = busca.construir_pipeline(f, [], {}, pagina=1, tamanho=5)[2]["$match"]["$and"][0]
        assert "$or" not in sem

    def test_a_projeccao_nao_leva_o_cliente(self):
        projeccao = str(self._pipeline()[-1]["$facet"]["items"][-1])
        assert "client_name" not in projeccao

    def test_o_dto_e_uma_lista_positiva(self):
        r = busca.resultado_do_trabalho({
            "process_id": "p", "net_salary_num": 1200.0,
            "proc": {"process_number": 5, "company_name": "X", "client_name": "SEGREDO", "status": "novo"},
            "jobs": {"job_id": "j", "employer_nif": {"value": "501964843"}, "employer_name": {"value": "Acme"},
                     "job_title": {"value": "Eng"}, "contract_type": {"value": "efetivo"}, "period": "2026-09",
                     "employer_location": "Lisboa", "net_salary": {"value": "1200.00", "needs_review": True},
                     "source_document_ids": ["a", "b"]}})
        assert "SEGREDO" not in str(r) and r["needs_review"] is True and r["source_documents"] == 2
        assert r["net_salary"] == 1200.0 and r["employer"]["location"] == "Lisboa"


class TestOServicoDaPesquisa:
    async def test_um_pipeline_que_falha_e_503_nao_500(self):
        with patch.object(busca.store, "agregar_metadados_profissionais", AsyncMock(side_effect=RuntimeError("time"))), \
             patch.object(busca, "build_tenant_process_condition", AsyncMock(return_value={})):
            with pytest.raises(HTTPException) as e:
                await busca.run_advanced_search({"id": "u"})
        assert e.value.status_code == 503

    async def test_a_condicao_de_ambito_que_falha_nunca_abre(self):
        """Se não se calcula a fronteira, a excepção SOBE: nunca «sem filtro»."""
        agrega = AsyncMock(return_value=[])
        with patch.object(busca.store, "agregar_metadados_profissionais", agrega), \
             patch.object(busca, "build_tenant_process_condition", AsyncMock(side_effect=RuntimeError("sem âmbito"))):
            with pytest.raises(RuntimeError):
                await busca.run_advanced_search({"id": "u"})
        agrega.assert_not_called()

    async def test_so_o_modulo_de_persistencia_toca_na_colecao(self):
        arvore = ast.parse(codigo_sem_comentarios(inspect.getsource(busca)))
        acessos = [n for n in ast.walk(arvore) if isinstance(n, ast.Attribute) and n.attr in
                   ("process_professional_metadata", "employers")]
        assert acessos == []


# ====================================================================
# 6. O INDEX LÊ OS PEDIDOS DO PORTAL (o 403 do separador Documentos)
# ====================================================================
class TestIndexLeOsPedidosDoPortal:
    def test_o_index_entra_na_leitura(self):
        from routes.documents import PAPEIS_QUE_LEEM_OS_PEDIDOS_DO_PORTAL
        from models.auth import UserRole

        assert UserRole.INDEXACAO in PAPEIS_QUE_LEEM_OS_PEDIDOS_DO_PORTAL

    @pytest.mark.parametrize("papel", ["indexacao", "consultor", "diretor"])
    async def test_a_guarda_de_papel_do_endpoint_deixa_passar(self, papel):
        from routes.documents import PAPEIS_QUE_LEEM_OS_PEDIDOS_DO_PORTAL
        from services.auth import require_roles

        with patch("services.auth.get_effective_role_async", AsyncMock(return_value=papel)):
            user = {"id": "u", "role": papel}
            assert await require_roles(PAPEIS_QUE_LEEM_OS_PEDIDOS_DO_PORTAL)(MagicMock(), user) == user

    @pytest.mark.parametrize("papel", ["parceiro", "cliente"])
    async def test_contraprova_quem_nunca_leu_continua_sem_ler(self, papel):
        from routes.documents import PAPEIS_QUE_LEEM_OS_PEDIDOS_DO_PORTAL
        from services.auth import require_roles

        with patch("services.auth.get_effective_role_async", AsyncMock(return_value=papel)):
            with pytest.raises(HTTPException) as e:
                await require_roles(PAPEIS_QUE_LEEM_OS_PEDIDOS_DO_PORTAL)(MagicMock(), {"id": "u", "role": papel})
        assert e.value.status_code == 403

    def test_o_endpoint_usa_a_lista_e_as_escritas_continuam_sem_o_index(self):
        """Só a LEITURA abriu: criar, editar e apagar pedidos continuam fechados ao Index."""
        import routes.documents as rotas

        fonte = codigo_sem_comentarios(inspect.getsource(rotas))
        assert "Depends(require_roles(PAPEIS_QUE_LEEM_OS_PEDIDOS_DO_PORTAL))" in fonte
        arvore = ast.parse(fonte)
        for no in ast.walk(arvore):
            if isinstance(no, ast.AsyncFunctionDef) and any(
                "portal-requests" in ast.unparse(d) and not ast.unparse(d).startswith("router.get")
                for d in no.decorator_list
            ):
                assert "INDEXACAO" not in ast.unparse(no.args), no.name

    def test_a_guarda_de_visibilidade_ja_admitia_o_index(self):
        """O 403 vinha SÓ da lista de papéis do endpoint: a guarda de documentos sempre deixou o Index."""
        from services.document_visibility import user_can_view_process_documents

        proc = {"id": "p", "network_id": "r", "is_indexed": False}
        from services.tenant_network import TenantScope

        assert user_can_view_process_documents({"id": "u", "role": "indexacao"}, proc, scope=TenantScope(network_ids=("r",)))
        assert not user_can_view_process_documents({"id": "u", "role": "consultor"}, proc, scope=TenantScope(network_ids=("r",)))


# ====================================================================
# 7. MARCAR COMO INDEXADO NÃO FORÇA UM CONSULTOR
# ====================================================================
class TestIndexadoSemConsultorForcado:
    def test_a_resposta_so_diz_atribuido_se_alguem_foi(self):
        from services.process_indexing import build_mark_indexed_response

        base = dict(process={}, process_id="p", process_ref="#1", current_status="a", next_status="b",
                    assigned_ids=[], is_pre_registo_transition=True)
        sem = build_mark_indexed_response(**base, consultant_result=None)
        com = build_mark_indexed_response(**base, consultant_result={"consultant_id": "c"})
        assert sem["dual_auto_assigned"] is False and sem["consultant_auto_assigned"] is None
        assert com["dual_auto_assigned"] is True

    async def test_a_saida_da_index_chama_a_automacao_mas_a_omissao_ja_nao_atribui(self):
        """Ao nível da CHAMADA: a automação corre (tarefas, fase), e o plano por omissão não leva papéis."""
        from services import phase_automation as pa
        from services import process_indexing as pi

        chamada = AsyncMock(return_value=pa.Resultado())
        with patch.object(pi.phase_automation, "ao_entrar_na_fase_sem_falhar", chamada):
            resultado, _ = await pi.auto_assign_after_indexacao({}, "p", {"id": "u"}, "pre_registo", "#1", fase_nova="f")
        assert resultado is None
        assert chamada.await_args.kwargs["origem"] == pa.ORIGEM_INDEXACAO
        assert pa.plano_da_fase({"name": "f"}, pa.ORIGEM_INDEXACAO).papeis == ()

    def test_a_omissao_nao_aparece_como_lista_de_papeis_atribuiveis(self):
        from services import phase_automation as pa

        assert pa.PAPEIS_POR_OMISSAO_DA_SAIDA_DA_INDEX == ()
        assert pa.PAPEIS_ATRIBUIVEIS == ("consultor", "intermediario")  # a configuração explícita continua possível

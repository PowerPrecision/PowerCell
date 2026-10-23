"""Matriz de verificação — o EXTRATO conferido como o faria um analista de crédito.

O caso que motivou isto (ecrã do cliente): saldo inicial 381,00 €, créditos 2.419,75 €, débitos 1.762,67 €,
saldo final indicado 381,00 € — e três avisos de «movimento atípico» de 50–70 €, sem dizer de que ficheiro.
Tudo sobre as funções de PRODUÇÃO: `normalizar_extrato` (o que sai do modelo) → `avaliar` (a matriz).
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from services import index_ai as ia
from services import index_matrix as mx

HOJE = date(2026, 10, 22)


def linha(data, valor, tipo="credit", saldo=None, canal="transferencia", contraparte=None, pagina=1):
    return {"date": data, "amount": valor, "kind": tipo, "balance": saldo, "channel": canal,
            "counterpart": contraparte, "page": pagina}


def extrato_bruto(movimentos, abertura=None, fecho=None, **mudar):
    base = {"bank_name": {"value": "Banco Teste"}, "period_start": {"value": "2026-08-01"},
            "period_end": {"value": "2026-08-31"}, "opening_balance": {"value": abertura},
            "closing_balance": {"value": fecho}, "movements": movimentos, "findings": []}
    base.update(mudar)
    return base


def avaliar(bruto, doc="e1"):
    # o modelo devolve cada campo como {"value": …}: o normalizador é que o desembrulha
    bruto = {k: (v["value"] if isinstance(v, dict) and set(v) <= {"value", "confidence", "page"} else v) for k, v in bruto.items()}
    factos = ia.normalizar_extrato(bruto, document_id=doc)["factos"]
    return mx.avaliar([factos], hoje=HOJE), factos


def do_saldo(achados):
    return [a for a in achados if a["code"] == "saldo_nao_bate"]


def do_movimento(achados):
    return [a for a in achados if a["code"] == "movimento_estranho"]


class TestOSaldoLinhaALinha:
    def extrato_certo(self):
        # 1000 → +500 = 1500 → -200 = 1300 → -50 = 1250 → +100 = 1350
        return [
            linha("2026-08-02", 500, "credit", 1500, pagina=1),
            linha("2026-08-05", 200, "debit", 1300, pagina=1),
            linha("2026-08-11", 50, "debit", 1250, pagina=2),
            linha("2026-08-20", 100, "credit", 1350, pagina=2),
        ]

    def test_um_extrato_coerente_nao_tem_aviso(self):
        achados, _ = avaliar(extrato_bruto(self.extrato_certo(), 1000, 1350))
        assert do_saldo(achados) == []

    def test_um_movimento_em_falta_e_localizado_na_linha_onde_o_saldo_salta(self):
        movimentos = self.extrato_certo()
        del movimentos[1]    # falta o débito de 200 €: o saldo impresso passa de 1500 para 1250 (−250)
        achados, _ = avaliar(extrato_bruto(movimentos, 1000, 1350))
        (a,) = do_saldo(achados)
        detalhe = a["detalhe"]
        assert "linha a linha" in detalhe
        assert "11/08/2026" in detalhe and "pág. 2" in detalhe        # onde
        assert "1.500,00 €" in detalhe and "1.450,00 €" in detalhe    # o saldo anterior e o que devia ficar
        assert "1.250,00 €" in detalhe                                # o que o extrato indica
        assert "200,00 €" in detalhe                                  # a diferença: o movimento que falta
        assert "Pode faltar um movimento" in detalhe

    def test_um_valor_mal_lido_e_localizado(self):
        movimentos = self.extrato_certo()
        movimentos[2]["amount"] = 5       # o débito era 50 €, leu-se 5 €
        achados, _ = avaliar(extrato_bruto(movimentos, 1000, 1350))
        (a,) = do_saldo(achados)
        assert "11/08/2026" in a["detalhe"] and "45,00 €" in a["detalhe"]

    def test_o_primeiro_movimento_que_nao_parte_do_saldo_inicial(self):
        achados, _ = avaliar(extrato_bruto(self.extrato_certo(), 900, 1350))      # saldo inicial errado
        (a,) = do_saldo(achados)
        assert "primeiro movimento não parte do saldo inicial" in a["detalhe"]
        assert "02/08/2026" in a["detalhe"]

    def test_o_saldo_final_indicado_diferente_do_do_ultimo_movimento(self):
        achados, _ = avaliar(extrato_bruto(self.extrato_certo(), 1000, 381))
        (a,) = do_saldo(achados)
        assert "depois do último movimento (1.350,00 €)" in a["detalhe"] and "381,00 €" in a["detalhe"]
        assert "falha em" not in a["detalhe"]         # as linhas estão certas: só o final difere

    def test_extrato_listado_do_mais_recente_para_o_mais_antigo_tambem_confere(self):
        achados, _ = avaliar(extrato_bruto(self.extrato_certo()[::-1], 1000, 1350))
        assert do_saldo(achados) == []

    def test_saldo_negativo_e_aceite(self):
        movimentos = [linha("2026-08-02", 300, "debit", -100), linha("2026-08-03", 50, "debit", -150),
                      linha("2026-08-04", 400, "credit", 250)]
        achados, _ = avaliar(extrato_bruto(movimentos, 200, 250))
        assert do_saldo(achados) == []

    def test_so_quebras_reais_com_tolerancia_de_centimos(self):
        movimentos = [linha("2026-08-02", 10.005, "credit", 1010.01), linha("2026-08-03", 20, "debit", 990.01),
                      linha("2026-08-04", 5, "credit", 995.01)]
        achados, _ = avaliar(extrato_bruto(movimentos, 1000, 995.01))
        assert do_saldo(achados) == []

    def test_o_aviso_lista_no_maximo_tres_pontos(self):
        saldos = [1010, 1100, 1020, 1130, 1030, 1140, 1040]     # o primeiro passo está certo, os outros seis falham
        movimentos = [linha(f"2026-08-{d + 1:02d}", 10, "credit", saldo) for d, saldo in enumerate(saldos)]
        achados, _ = avaliar(extrato_bruto(movimentos, 1000, None))
        (a,) = do_saldo(achados)
        assert "falha em 6 ponto(s)" in a["detalhe"] and "e mais 3" in a["detalhe"]

    def test_sem_coluna_de_saldo_nao_se_inventa_a_conferencia(self):
        # 1 de 4 movimentos com saldo: abaixo de 80 % → cai para a conferência dos totais
        movimentos = [linha("2026-08-02", 100, "credit", 1100), linha("2026-08-03", 50), linha("2026-08-04", 50),
                      linha("2026-08-05", 50)]
        achados, _ = avaliar(extrato_bruto(movimentos, 1000, 1000))
        (a,) = do_saldo(achados)
        assert "linha a linha" not in a["detalhe"].split("Este extrato")[0]
        assert "não traz o saldo linha a linha" in a["detalhe"]

    def test_o_limiar_de_80_por_cento_das_linhas_com_saldo(self):
        def com_saldo(n_com):
            movimentos = [linha(f"2026-08-{d + 2:02d}", 100, "credit", 1100 + 100 * d if d < n_com else None)
                          for d in range(5)]
            movimentos[0]["balance"] = 1100
            return movimentos
        # 3 de 5 (60 %) com saldo e uma quebra: NÃO se confere linha a linha (cai nos totais)
        parcial = [linha("2026-08-02", 100, "credit", 1100), linha("2026-08-03", 100, "credit", 9999),
                   linha("2026-08-04", 100, "credit", 1300), linha("2026-08-05", 100), linha("2026-08-06", 100)]
        achados, _ = avaliar(extrato_bruto(parcial, 1000, 1500))
        assert all("falha em" not in a["detalhe"] for a in do_saldo(achados))
        # 4 de 5 (80 %) com a mesma quebra: confere e localiza
        quase = [linha("2026-08-02", 100, "credit", 1100), linha("2026-08-03", 100, "credit", 9999),
                 linha("2026-08-04", 100, "credit", 1300), linha("2026-08-05", 100, "credit", 1400), linha("2026-08-06", 100)]
        achados, _ = avaliar(extrato_bruto(quase, 1000, 1500))
        assert any("falha em" in a["detalhe"] for a in do_saldo(achados))

    def test_o_saldo_chega_ao_facto_e_vai_ao_modelo_pedido(self):
        _, factos = avaliar(extrato_bruto(self.extrato_certo(), 1000, 1350))
        assert [m["s"] for m in factos["movimentos"]] == ["1500.00", "1300.00", "1250.00", "1350.00"]
        _, sem = avaliar(extrato_bruto([linha("2026-08-02", 10)], 1, 11))
        assert sem["movimentos"][0]["s"] is None
        definicao = ia.definicao_da_ferramenta(ia.TIPO_EXTRATO) if hasattr(ia, "definicao_da_ferramenta") else None
        texto = repr(definicao) + ia.PROMPTS_POR_TIPO[ia.TIPO_EXTRATO]
        assert "balance" in texto and "pela ORDEM em que aparecem" in texto


class TestOsTotaisDoCasoDoCliente:
    """O caso do ecrã: 381,00 + 2.419,75 − 1.762,67 = 1.038,08, mas o final indicado é 381,00."""

    def movimentos(self):
        # créditos e débitos que somam os valores do ecrã, SEM coluna de saldo
        return [linha("2026-08-02", 2419.75, "credit"), linha("2026-08-03", 1000, "debit"),
                linha("2026-08-04", 762.67, "debit")]

    def test_o_aviso_mostra_as_contas_e_a_pista_do_valor_repetido(self):
        achados, _ = avaliar(extrato_bruto(self.movimentos(), 381, 381))
        (a,) = do_saldo(achados)
        d = a["detalhe"]
        assert "Saldo inicial 381,00 €" in d and "créditos 2.419,75 €" in d and "débitos 1.762,67 €" in d
        assert "1.038,08 €" in d and "657,08 €" in d
        assert "igual ao saldo inicial" in d and "mesmo valor lido duas vezes" in d
        assert "não traz o saldo linha a linha" in d      # e diz o que falta para o localizar

    def test_sem_a_coincidencia_nao_ha_pista(self):
        achados, _ = avaliar(extrato_bruto(self.movimentos(), 381, 500))
        (a,) = do_saldo(achados)
        assert "igual ao saldo inicial" not in a["detalhe"]

    def test_os_totais_certos_nao_avisam(self):
        achados, _ = avaliar(extrato_bruto(self.movimentos(), 381, 1038.08))
        assert do_saldo(achados) == []


class TestOsMovimentosAtipicos:
    def achado_da_ia(self, valor, dia="2026-08-11"):
        return {"type": "numerario_atipico", "amount": valor, "date": dia, "page": 1,
                "description": "Movimento fora do padrão."}

    def movimentos(self):
        return [linha("2026-08-11", 60, "debit"), linha("2026-08-29", 50, "debit"),
                linha("2026-08-29", 70, "debit"), linha("2026-08-15", 300, "debit", canal="numerario")]

    def test_valores_pequenos_apontados_pela_ia_nao_geram_aviso(self):
        bruto = extrato_bruto(self.movimentos(), findings=[
            self.achado_da_ia(60), self.achado_da_ia(50, "2026-08-29"), self.achado_da_ia(70, "2026-08-29")])
        achados, _ = avaliar(bruto)
        assert do_movimento(achados) == []

    def test_um_valor_acima_do_minimo_continua_a_avisar_com_valor_data_e_pagina(self):
        bruto = extrato_bruto(self.movimentos(), findings=[self.achado_da_ia(300, "2026-08-15")])
        achados, _ = avaliar(bruto)
        (a,) = do_movimento(achados)
        assert "300,00 €" in a["detalhe"] and "15/08/2026" in a["detalhe"] and "pág. 1" in a["detalhe"]
        assert "60,00 €" not in a["detalhe"]

    def test_o_minimo_e_uma_constante_explicita(self):
        assert mx.ATIPICO_DA_IA_MINIMO == Decimal("250.00")

    def test_a_ia_nao_pode_apontar_um_movimento_que_nao_existe(self):
        achados, _ = avaliar(extrato_bruto(self.movimentos(), findings=[self.achado_da_ia(9999, "2026-08-15")]))
        assert do_movimento(achados) == []


class TestNumerarioFraccionado:
    def test_varios_depositos_pequenos_em_numerario_que_somam_o_limiar(self):
        movimentos = [linha("2026-06-01", 200, canal="numerario"), linha("2026-06-02", 200, canal="numerario"),
                      linha("2026-06-02", 100, canal="numerario"), linha("2026-06-03", 300, canal="numerario"),
                      linha("2026-06-04", 250, canal="numerario")]
        achados, _ = avaliar(extrato_bruto(movimentos))
        (a,) = do_movimento(achados)
        assert "5 depósitos em numerário entre 01/06/2026 e 04/06/2026" in a["detalhe"]
        assert "1.050,00 €" in a["detalhe"]

    def test_espalhados_por_mais_de_uma_semana_nao_contam(self):
        movimentos = [linha("2026-06-01", 400, canal="numerario"), linha("2026-06-10", 400, canal="numerario"),
                      linha("2026-06-20", 400, canal="numerario")]
        achados, _ = avaliar(extrato_bruto(movimentos))
        assert do_movimento(achados) == []

    def test_poucos_movimentos_ou_pouco_dinheiro_nao_contam(self):
        achados, _ = avaliar(extrato_bruto([linha("2026-06-01", 400, canal="numerario"),
                                            linha("2026-06-02", 400, canal="numerario")]))
        assert do_movimento(achados) == []
        achados, _ = avaliar(extrato_bruto([linha(f"2026-06-0{d}", 100, canal="numerario") for d in (1, 2, 3)]))
        assert do_movimento(achados) == []

    def test_transferencias_nao_sao_numerario(self):
        achados, _ = avaliar(extrato_bruto([linha(f"2026-06-0{d}", 500) for d in (1, 2, 3)]))
        assert do_movimento(achados) == []

    def test_depositos_e_levantamentos_nao_se_misturam(self):
        movimentos = [linha("2026-06-01", 400, canal="numerario"), linha("2026-06-02", 400, "debit", canal="numerario"),
                      linha("2026-06-03", 400, canal="numerario")]
        achados, _ = avaliar(extrato_bruto(movimentos))
        assert do_movimento(achados) == []

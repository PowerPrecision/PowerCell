"""Matriz de verificação do Index (Lote 12, Fase 2): cada regra com a sua contraprova."""
from __future__ import annotations

from datetime import date

import pytest

from models.index_module import ALERTAS
from services import index_matrix as mx

HOJE = date(2026, 10, 21)
NIF_OK, NIF_MAL = "501964843", "518789370"


def recibo(doc="r1", **mudar):
    base = {"tipo": "recibo_vencimento", "document_id": doc, "period": "2026-09", "net": "1000.00",
            "gross": "1180.00", "deductions": "180.00", "ss": "129.80", "irs": "50.20", "iban": None,
            "employer_nif": NIF_OK, "employer_name": "Acme, Lda"}
    base.update(mudar)
    return base


def mov(valor="1000.00", k="c", d="2026-09-28", canal="transferencia", cp=None, page=1):
    return {"d": d, "v": valor, "k": k, "canal": canal, "cp": cp, "page": page}


def extrato(doc="e1", movimentos=None, **mudar):
    base = {"tipo": "extrato_bancario", "document_id": doc, "iban": None, "period_start": "2026-09-01",
            "period_end": "2026-09-30", "opening": None, "closing": None,
            "movimentos": movimentos if movimentos is not None else [mov()], "achados": []}
    base.update(mudar)
    return base


def ident(doc="i1", **mudar):
    base = {"tipo": "identificacao", "document_id": doc, "subtype": "cc", "expirada": False, "legivel": True}
    base.update(mudar)
    return base


def codigos(achados):
    return [a["code"] for a in achados]


def avalia(*factos, **kw):
    return mx.avaliar(list(factos), hoje=HOJE, **kw)


class TestTudoEmOrdem:
    def test_o_caso_limpo_nao_tem_alertas(self):
        assert avalia(recibo(), extrato(), ident()) == []

    def test_sem_nada_nao_ha_alertas(self):
        assert avalia() == []


class TestReciboSemCredito:
    def test_o_liquido_nao_aparece_no_extrato(self):
        r = avalia(recibo(), extrato(movimentos=[mov("350.00")]))
        assert codigos(r) == ["recibo_sem_credito"]
        assert {x["document_id"] for x in r[0]["refs"]} == {"r1", "e1"}   # aponta os DOIS documentos

    def test_contraprova_com_o_credito_nao_ha_alerta(self):
        assert "recibo_sem_credito" not in codigos(avalia(recibo(), extrato()))

    @pytest.mark.parametrize("valor, ha_alerta", [
        ("1000.00", False), ("1000.99", False), ("999.50", False),
        ("1010.00", False), ("990.00", False),      # a tolerância é o maior de 1 € e 1 % (10 €)
        ("1010.01", True), ("989.99", True), ("500.00", True),
    ])
    def test_tolerancia(self, valor, ha_alerta):
        assert ("recibo_sem_credito" in codigos(avalia(recibo(), extrato(movimentos=[mov(valor)])))) is ha_alerta

    def test_so_conta_um_credito_nao_um_debito(self):
        assert "recibo_sem_credito" in codigos(avalia(recibo(), extrato(movimentos=[mov("1000.00", k="d")])))

    def test_credito_do_mes_seguinte_conta(self):
        # ordenado de setembro pago a 3 de outubro
        assert "recibo_sem_credito" not in codigos(avalia(recibo(), extrato(
            period_end="2026-10-31", movimentos=[mov("1000.00", d="2026-10-03")])))

    def test_credito_fora_do_intervalo_nao_conta(self):
        assert "recibo_sem_credito" in codigos(avalia(recibo(), extrato(
            period_start="2026-09-01", period_end="2026-12-31", movimentos=[mov("1000.00", d="2026-12-20")])))

    def test_data_desconhecida_e_duvida_a_favor_do_cliente(self):
        assert "recibo_sem_credito" not in codigos(avalia(recibo(), extrato(movimentos=[mov("1000.00", d=None)])))

    def test_sem_liquido_nao_ha_verificacao(self):
        # um campo em falta não é erro: a verificação não corre
        assert avalia(recibo(net=None), extrato(movimentos=[mov("1.00")])) == []


class TestExtratoEmFalta:
    def test_sem_extrato_e_informativo_nunca_recibo_sem_credito(self):
        r = avalia(recibo())
        assert codigos(r) == ["extrato_em_falta"]
        assert ALERTAS["extrato_em_falta"][0] == "info"

    def test_extrato_de_outro_periodo_tambem_e_em_falta(self):
        r = avalia(recibo(), extrato(period_start="2026-01-01", period_end="2026-01-31"))
        assert codigos(r) == ["extrato_em_falta"]

    def test_um_por_recibo_com_o_periodo(self):
        r = avalia(recibo("r1", period="2026-07"), recibo("r2", period="2026-08"))
        assert sorted(x["periodo"] for x in r) == ["2026-07", "2026-08"]

    def test_intervalo_desconhecido_usa_as_datas_dos_movimentos(self):
        e = extrato(period_start=None, period_end=None, movimentos=[mov("1000.00", d="2026-09-28")])
        assert avalia(recibo(), e) == []


class TestContasDoRecibo:
    def test_bruto_menos_descontos_nao_da_liquido(self):
        assert "contas_nao_batem" in codigos(avalia(recibo(gross="1500.00"), extrato()))

    def test_arredondamento_de_centimos_e_tolerado(self):
        assert avalia(recibo(gross="1180.04"), extrato()) == []

    def test_taxa_de_ss_fora_das_duas_taxas(self):
        assert "contas_nao_batem" in codigos(avalia(recibo(ss="300.00"), extrato()))

    @pytest.mark.parametrize("ss", ["129.80", "280.25"])  # 11 % e 23,75 % de 1180
    def test_as_duas_taxas_validas(self, ss):
        assert "contas_nao_batem" not in codigos(avalia(recibo(ss=ss), extrato()))

    def test_irs_implausivel(self):
        assert "contas_nao_batem" in codigos(avalia(recibo(irs="800.00"), extrato()))

    def test_sem_bruto_nao_ha_verificacao_de_taxas(self):
        assert avalia(recibo(gross=None, ss="9999.00"), extrato()) == []


class TestNifDaEntidade:
    def test_nif_sem_digito_de_controlo(self):
        assert "nif_invalido" in codigos(avalia(recibo(employer_nif=NIF_MAL), extrato()))
        assert ALERTAS["nif_invalido"][0] == "alerta"

    def test_nif_valido_nao_alerta(self):
        assert "nif_invalido" not in codigos(avalia(recibo(), extrato()))

    def test_sem_nif_nao_e_invalido(self):
        assert "nif_invalido" not in codigos(avalia(recibo(employer_nif=None), extrato()))

    def test_entidade_conhecida_com_outro_nif(self):
        c = codigos(avalia(recibo(employer_nif="509442013"), extrato(), entidades={"acme": NIF_OK}))
        assert "nif_entidade_incoerente" in c

    def test_o_nome_compara_se_sem_acentos_nem_lda(self):
        assert mx.nome_normalizado_da_entidade("ACME, Lda.") == mx.nome_normalizado_da_entidade("Acmé Limitada")

    def test_contraprova_mesmo_nif_nao_alerta(self):
        assert "nif_entidade_incoerente" not in codigos(avalia(recibo(), extrato(), entidades={"acme": NIF_OK}))

    def test_entidade_desconhecida_nao_alerta(self):
        assert "nif_entidade_incoerente" not in codigos(avalia(recibo(), extrato(), entidades={}))


class TestReciboIrreal:
    def test_periodo_no_futuro(self):
        assert "recibo_irreal" in codigos(avalia(recibo(period="2026-12"), extrato()))

    def test_o_mes_corrente_nao_e_futuro(self):
        assert "recibo_irreal" not in codigos(avalia(recibo(period="2026-10"), extrato()))

    def test_sem_entidade_nenhuma(self):
        assert "recibo_irreal" in codigos(avalia(recibo(employer_nif=None, employer_name=None), extrato()))

    def test_so_com_nome_nao_e_irreal(self):
        assert "recibo_irreal" not in codigos(avalia(recibo(employer_nif=None), extrato()))

    def test_liquido_acima_do_bruto(self):
        assert "recibo_irreal" in codigos(avalia(recibo(net="2000.00", gross="1180.00", deductions=None), extrato(movimentos=[mov("2000.00")])))

    def test_iban_do_ordenado_diferente_do_das_contas(self):
        r = avalia(recibo(iban="PT50000201231234567890154"), extrato(iban="PT50003500000000000000000"))
        assert "recibo_irreal" in codigos(r)

    def test_contraprova_iban_igual(self):
        iban = "PT50000201231234567890154"
        assert "recibo_irreal" not in codigos(avalia(recibo(iban=iban), extrato(iban=iban)))

    def test_iban_desconhecido_de_um_lado_nao_conclui(self):
        assert "recibo_irreal" not in codigos(avalia(recibo(iban="PT50000201231234567890154"), extrato(iban=None)))


class TestSaldoDoExtrato:
    def test_saldo_que_nao_bate(self):
        e = extrato(opening="500.00", closing="9000.00", movimentos=[mov("1000.00")])
        assert "saldo_nao_bate" in codigos(avalia(e))

    def test_saldo_que_bate(self):
        e = extrato(opening="500.00", closing="1500.00", movimentos=[mov("1000.00")])
        assert "saldo_nao_bate" not in codigos(avalia(e))

    def test_debitos_entram_na_conta(self):
        e = extrato(opening="500.00", closing="1300.00", movimentos=[mov("1000.00"), mov("200.00", k="d")])
        assert "saldo_nao_bate" not in codigos(avalia(e))

    def test_sem_saldos_nao_ha_verificacao(self):
        assert avalia(extrato(opening=None, closing=None)) == []

    def test_extrato_no_tecto_pode_estar_truncado_e_nao_se_confere(self):
        movs = [mov("1.00", k="d", d=f"2026-09-{(i % 28) + 1:02d}") for i in range(mx.TECTO_DE_MOVIMENTOS)]
        assert avalia(extrato(opening="0.00", closing="99999.00", movimentos=movs)) == []


class TestMovimentosEstranhos:
    def test_numerario_alto(self):
        e = extrato(movimentos=[mov("1500.00", canal="numerario")])
        assert "movimento_estranho" in codigos(avalia(e))

    def test_contraprova_numerario_baixo(self):
        assert avalia(extrato(movimentos=[mov("200.00", canal="numerario")])) == []

    def test_transferencias_recorrentes_para_a_mesma_contraparte(self):
        movs = [mov("300.00", k="d", d=f"2026-09-{d:02d}", cp="abc123") for d in (3, 10, 17)]
        assert "movimento_estranho" in codigos(avalia(extrato(movimentos=movs)))

    def test_contraprova_duas_vezes_nao_e_recorrencia(self):
        movs = [mov("300.00", k="d", cp="abc123"), mov("300.00", k="d", cp="abc123")]
        assert avalia(extrato(movimentos=movs)) == []

    def test_valores_pequenos_repetidos_nao_contam(self):
        movs = [mov("5.00", k="d", cp="cafe") for _ in range(10)]
        assert avalia(extrato(movimentos=movs)) == []

    def test_debitos_diretos_repetidos_nao_contam(self):
        movs = [mov("300.00", k="d", canal="debito_direto", cp="renda") for _ in range(6)]
        assert avalia(extrato(movimentos=movs)) == []

    def test_achado_da_ia_validado_pelo_codigo(self):
        e = extrato(movimentos=[mov("600.00", canal="numerario", d="2026-09-10")],
                    achados=[{"tipo": "numerario_atipico", "v": "600.00", "d": "2026-09-10", "page": 2}])
        assert "movimento_estranho" in codigos(avalia(e))

    def test_achado_da_ia_que_cita_valor_inexistente_e_descartado(self):
        # «um modelo não é uma parede»: o valor não existe no extrato
        e = extrato(movimentos=[mov("100.00", d="2026-09-10")],
                    achados=[{"tipo": "numerario_atipico", "v": "5000.00", "d": "2026-09-10", "page": 2}])
        assert avalia(e) == []

    def test_achado_da_ia_com_data_que_nao_bate_e_descartado(self):
        e = extrato(movimentos=[mov("600.00", d="2026-09-10")],
                    achados=[{"tipo": "numerario_atipico", "v": "600.00", "d": "2026-09-11"}])
        assert avalia(e) == []

    def test_a_recorrencia_e_o_saldo_dos_achados_da_ia_nao_se_aceitam(self):
        e = extrato(movimentos=[mov("100.00")], achados=[
            {"tipo": "transferencias_recorrentes", "v": "100.00", "d": "2026-09-28"},
            {"tipo": "saldo_incoerente", "v": "100.00", "d": "2026-09-28"}])
        assert avalia(e) == []


class TestIdentificacao:
    def test_expirada(self):
        assert codigos(avalia(ident(expirada=True))) == ["identificacao_expirada"]

    def test_valida_e_validade_desconhecida_nao_alertam(self):
        assert avalia(ident(expirada=False)) == [] and avalia(ident(expirada=None)) == []

    def test_ilegivel_vence_expirada(self):
        assert codigos(avalia(ident(legivel=False, expirada=True))) == ["identificacao_ilegivel"]


class TestPropriedades:
    def test_nenhum_achado_tem_codigo_fora_da_tabela(self):
        casos = avalia(recibo(employer_nif=NIF_MAL, period="2026-12"), extrato(opening="0.00", closing="9.00"),
                       ident(expirada=True), entidades={})
        assert casos and all(c["code"] in ALERTAS for c in casos)

    def test_sem_repeticoes(self):
        r = avalia(recibo(), recibo())  # o mesmo recibo duas vezes
        assert len(r) == len({(a["code"], tuple(x["document_id"] for x in a["refs"]), a["periodo"]) for a in r})

    def test_nao_muta_a_entrada(self):
        fs = [recibo(), extrato()]
        copia = [dict(f) for f in fs]
        mx.avaliar(fs, hoje=HOJE)
        assert fs == copia

    def test_dados_corrompidos_nao_rebentam(self):
        lixo = [recibo(net="abc", gross="x", period="2026-xx"), extrato(movimentos=[{"v": "zzz", "k": "c"}, {}]),
                {"tipo": "outro"}, ident(expirada="talvez")]
        try:
            mx.avaliar(lixo, hoje=HOJE)
        except Exception as exc:  # pragma: no cover
            pytest.fail(f"a matriz rebentou com dados corrompidos: {exc!r}")

    def test_os_achados_so_referem_documentos_com_id(self):
        r = avalia(recibo(doc=None))
        assert all(x["document_id"] for a in r for x in a["refs"])

"""Recibos e extratos estrangeiros (Reino Unido, França, Países Baixos, Luxemburgo) e linhas que a IA saltava.

Pedido do Flavio (Out 2026): «A IA continua a não analisar os documentos correctamente. Está a ignorar linhas
e depois as contas não batem certo. Alguns extratos e recibos podem ser estrangeiros (Inglaterra, França,
Holanda e Luxemburgo). A IA tem de saber de que país são e analisar consoante as regras desse país.»
"""
from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, patch

import pytest

from services import index_ai as ia
from services import index_matrix as mx
from services import index_paises as pa

HOJE = date(2026, 10, 21)


def campo(v, conf="alta", page=1):
    return {"value": v, "confidence": conf, "page": page}


def recibo(doc="r1", **mudar):
    base = {"tipo": "recibo_vencimento", "document_id": doc, "period": "2026-09", "net": "1000.00",
            "gross": "1180.00", "deductions": "180.00", "ss": "129.80", "irs": "50.20", "iban": None,
            "employer_nif": "501964843", "employer_name": "Acme, Lda"}
    base.update(mudar)
    return base


def mov(valor="1000.00", k="c", d="2026-09-28", s=None):
    return {"d": d, "v": valor, "k": k, "canal": "transferencia", "cp": None, "page": 1, "s": s}


def extrato(doc="e1", movimentos=None, **mudar):
    base = {"tipo": "extrato_bancario", "document_id": doc, "iban": None, "period_start": "2026-09-01",
            "period_end": "2026-09-30", "opening": None, "closing": None,
            "movimentos": movimentos if movimentos is not None else [mov()], "achados": []}
    base.update(mudar)
    return base


def codigos(achados):
    return [a["code"] for a in achados]


def do_codigo(achados, code):
    return [a for a in achados if a["code"] == code]


# ── o país e a moeda ─────────────────────────────────────────────────────────
class TestPaisDoDocumento:
    def test_o_que_o_modelo_leu_com_sinonimos(self):
        assert pa.pais_do_documento("UK") == "GB"
        assert pa.pais_do_documento("Inglaterra") == "GB"
        assert pa.pais_do_documento("Holanda") == "NL"
        assert pa.pais_do_documento("fr") == "FR"
        assert pa.pais_do_documento("Luxembourg") == "LU"

    def test_sem_nada_e_portugal(self):
        assert pa.pais_do_documento(None) == "PT"
        assert pa.pais_do_documento("Marte") == "PT"

    def test_libras_sem_pais_sao_do_reino_unido(self):
        assert pa.pais_do_documento(None, moeda="GBP") == "GB"

    def test_no_extrato_o_iban_da_conta_manda(self):
        assert pa.pais_do_documento("PT", iban="LU280019400644750000", iban_manda=True) == "LU"
        # num recibo, o IBAN do ordenado só serve à falta de melhor (pode ser uma conta noutro país)
        assert pa.pais_do_documento("FR", iban="PT50000201231234567890154") == "FR"
        assert pa.pais_do_documento(None, iban="NL91ABNA0417164300") == "NL"

    def test_a_moeda_e_a_do_pais_sem_outra_indicacao(self):
        assert pa.moeda_do_documento(None, "GB") == "GBP"
        assert pa.moeda_do_documento(None, "FR") == "EUR"
        assert pa.moeda_do_documento("£", "PT") == "GBP"


# ── recibos: regras de cada país ─────────────────────────────────────────────
class TestRecibosPortugueses:
    def test_subsidio_de_refeicao_fora_da_base_da_ss_nao_e_aviso(self):
        # base 1.000 € (SS 110 €) + subsídio de refeição 180 € isento: 110/1180 = 9,3 % dava «contas não batem»
        r = recibo(gross="1180.00", ss="110.00", irs="70.00", deductions="180.00", net="1000.00", rubricas=[
            {"k": "abono", "cat": "vencimento_base", "v": "1000.00", "ss": True},
            {"k": "abono", "cat": "subsidio_refeicao", "v": "180.00", "ss": False},
            {"k": "desconto", "cat": "seguranca_social", "v": "110.00", "ss": None},
            {"k": "desconto", "cat": "imposto", "v": "70.00", "ss": None},
        ])
        assert "contas_nao_batem" not in codigos(mx.avaliar([r], hoje=HOJE))

    def test_subsidio_de_refeicao_sem_a_marca_de_isento_tambem_conta(self):
        r = recibo(gross="1180.00", ss="110.00", irs="70.00", deductions="180.00", rubricas=[
            {"k": "abono", "cat": "vencimento_base", "v": "1000.00", "ss": None},
            {"k": "abono", "cat": "subsidio_refeicao", "v": "180.00", "ss": None},
            {"k": "desconto", "cat": "seguranca_social", "v": "110.00", "ss": None},
            {"k": "desconto", "cat": "imposto", "v": "70.00", "ss": None},
        ])
        assert mx.conferencia_do_recibo(r) == []

    def test_base_impressa_manda(self):
        assert mx.conferencia_do_recibo(recibo(gross="1180.00", ss="110.00", irs="70.00", ss_base="1000.00")) == []

    def test_ss_errada_continua_a_avisar(self):
        motivos = mx.conferencia_do_recibo(recibo(gross="1180.00", ss="40.00", irs="140.00"))
        assert any("Segurança Social" in m and "11 %" in m for m in motivos)


class TestRecibosEstrangeiros:
    def test_payslip_ingles_com_ni_nao_avisa_e_fala_em_libras(self):
        # Gross 3.000 £, Income Tax 390 £, NI 160 £ (≈5 %): com as regras portuguesas era «SS não é 11 %»
        r = recibo(pais="GB", currency="GBP", gross="3000.00", ss="160.00", irs="390.00", deductions="550.00",
                   net="2450.00", employer_nif=None, employer_name="Acme Ltd")
        assert mx.conferencia_do_recibo(r) == []
        r2 = {**r, "net": "2500.00"}
        (a,) = do_codigo(mx.avaliar([r2], hoje=HOJE), "contas_nao_batem")
        assert "£" in a["detalhe"] and "€" not in a["detalhe"]

    def test_ni_acima_do_plausivel_no_reino_unido(self):
        r = recibo(pais="GB", currency="GBP", gross="3000.00", ss="600.00", irs="0", deductions="600.00", net="2400.00")
        (m,) = mx.conferencia_do_recibo(r)
        assert "National Insurance" in m and "Reino Unido" in m

    def test_franca_liquido_e_o_net_paye_depois_do_pas(self):
        # brut 3.000 − cotisations 690 = net avant impôt 2.310; − PAS 150 = net payé 2.160
        r = recibo(pais="FR", gross="3000.00", ss="690.00", deductions="690.00", net_before_tax="2310.00",
                   irs="150.00", net="2160.00", employer_nif=None)
        assert mx.conferencia_do_recibo(r) == []

    def test_franca_part_patronale_lida_como_do_trabalhador(self):
        r = recibo(pais="FR", gross="3000.00", ss="1350.00", deductions="1350.00", irs="0", net="1650.00")
        (m,) = mx.conferencia_do_recibo(r)
        assert "cotisations salariales" in m and "França" in m

    def test_luxemburgo_e_paises_baixos(self):
        lu = recibo(pais="LU", gross="5000.00", ss="622.50", irs="600.00", deductions="1222.50", net="3777.50")
        nl = recibo(pais="NL", gross="4000.00", ss="300.00", irs="1100.00", deductions="1400.00", net="2600.00")
        assert mx.conferencia_do_recibo(lu) == [] and mx.conferencia_do_recibo(nl) == []
        lu_mal = {**lu, "ss": "1200.00", "deductions": "1800.00", "net": "3200.00"}
        assert any("Luxemburgo" in m for m in mx.conferencia_do_recibo(lu_mal))

    def test_numero_estrangeiro_nao_e_um_nif_invalido(self):
        r = recibo(pais="FR", employer_nif="732829320")  # um SIREN (9 dígitos), não um NIF português
        assert "nif_invalido" not in codigos(mx.avaliar([r], hoje=HOJE))
        assert "nif_invalido" in codigos(mx.avaliar([{**r, "pais": "PT", "employer_nif": "518789370"}], hoje=HOJE))

    def test_ordenado_em_libras_nao_se_procura_num_extrato_em_euros(self):
        r = recibo(pais="GB", currency="GBP", gross="3000.00", ss="160.00", irs="390.00", deductions="550.00",
                   net="2450.00")
        em_euros = extrato(movimentos=[mov("2850.00")])
        assert "recibo_sem_credito" not in codigos(mx.avaliar([r, em_euros], hoje=HOJE))
        em_libras = extrato(currency="GBP", movimentos=[mov("100.00")])
        (a,) = do_codigo(mx.avaliar([r, em_libras], hoje=HOJE), "recibo_sem_credito")
        assert "2.450,00 £" in a["detalhe"]
        com_credito = extrato(currency="GBP", movimentos=[mov("2450.00")])
        assert "recibo_sem_credito" not in codigos(mx.avaliar([r, com_credito], hoje=HOJE))


# ── linhas que ficavam por ler ───────────────────────────────────────────────
class TestLinhasPorLer:
    def test_linhas_do_recibo_que_nao_somam_o_iliquido(self):
        r = recibo(rubricas=[
            {"k": "abono", "cat": "vencimento_base", "v": "1000.00", "ss": True},   # faltou o subsídio de 180 €
            {"k": "desconto", "cat": "seguranca_social", "v": "129.80", "ss": None},
            {"k": "desconto", "cat": "imposto", "v": "50.20", "ss": None},
        ])
        (a,) = do_codigo(mx.avaliar([r], hoje=HOJE), "contas_nao_batem")
        assert "linhas de abonos lidas somam 1.000,00 €" in a["detalhe"] and "por ler" in a["detalhe"]

    def test_totais_impressos_do_extrato_denunciam_o_movimento_que_falta(self):
        e = extrato(total_credits="1500.00", total_debits="200.00",
                    movimentos=[mov("1000.00"), mov("200.00", k="d")])
        (a,) = do_codigo(mx.avaliar([e], hoje=HOJE), "saldo_nao_bate")
        assert "faltam 500,00 €" in a["detalhe"]
        ok = extrato(total_credits="1000.00", total_debits="200.00", movimentos=[mov("1000.00"), mov("200.00", k="d")])
        assert "saldo_nao_bate" not in codigos(mx.avaliar([ok], hoje=HOJE))

    def test_faltar_o_ultimo_movimento_com_o_saldo_linha_a_linha_certo(self):
        movs = [mov("100.00", s="1100.00"), mov("50.00", k="d", s="1050.00"), mov("20.00", k="d", s="1030.00")]
        e = extrato(opening="1000.00", total_debits="100.00", movimentos=movs)
        (a,) = do_codigo(mx.avaliar([e], hoje=HOJE), "saldo_nao_bate")
        assert "débitos" in a["detalhe"] and "faltam 30,00 €" in a["detalhe"]


# ── normalização ─────────────────────────────────────────────────────────────
def recibo_bruto(**mudar):
    base = {
        "employer_nif": campo("501964843"), "employer_name": campo("Acme, Lda"),
        "job_title": campo("Técnica"), "contract_type": campo("efetivo"),
        "net_salary": campo(1000), "gross_salary": campo(1180), "total_deductions": campo(180),
        "social_security": campo(110), "irs_withheld": campo(70), "period": campo("2026-09"),
        "credit_iban": campo(None), "lines": [
            {"kind": "earning", "category": "vencimento_base", "amount": 1000, "subject_to_social_security": True},
            {"kind": "earning", "category": "subsidio_refeicao", "amount": "180,00", "subject_to_social_security": False},
            {"kind": "deduction", "category": "seguranca_social", "amount": 110},
            {"kind": "deduction", "category": "imposto", "amount": 70},
        ],
    }
    base.update(mudar)
    return base


class TestNormalizacao:
    def test_recibo_portugues_guarda_as_linhas_sem_texto(self):
        r = ia.normalizar_recibo(recibo_bruto(), document_id="r")
        f = r["factos"]
        assert f["pais"] == "PT" and f["currency"] == "EUR"
        assert f["rubricas"][1] == {"k": "abono", "cat": "subsidio_refeicao", "v": "180.00", "ss": False}
        assert r["job"].country == "PT" and r["job"].currency == "EUR"

    def test_categoria_desconhecida_vai_para_outro(self):
        f = ia.normalizar_recibo(recibo_bruto(lines=[
            {"kind": "deduction", "category": "inventada", "amount": 5},
            {"kind": "earning", "category": "imposto", "amount": 5},   # categoria de desconto num abono
            {"kind": "nada", "category": "imposto", "amount": 5},
        ]))["factos"]
        assert [x["cat"] for x in f["rubricas"]] == ["outro_desconto", "outro_abono"]

    def test_recibo_estrangeiro_nao_tem_nif(self):
        r = ia.normalizar_recibo(recibo_bruto(country="FR", employer_nif=campo("732829320")), document_id="r")
        assert r["factos"]["pais"] == "FR" and r["factos"]["employer_nif"] is None
        assert r["job"].employer_nif.value is None

    def test_payslip_em_libras(self):
        r = ia.normalizar_recibo(recibo_bruto(country="GB", currency="GBP"))
        assert r["factos"]["currency"] == "GBP" and r["job"].currency == "GBP"

    def test_extrato_traz_pais_moeda_e_totais(self):
        f = ia.normalizar_extrato({
            "iban": campo("GB33BUKB20201555555555"), "country": "PT", "currency": None,
            "total_credits": campo(1500), "total_debits": campo("200,00"),
            "movements": [{"amount": 1000, "kind": "credit"}],
        })["factos"]
        assert f["pais"] == "GB" and f["currency"] == "GBP"
        assert f["total_credits"] == "1500.00" and f["total_debits"] == "200.00"

    def test_o_esquema_pede_o_pais_as_linhas_e_os_totais(self):
        recibo_props = ia.definicao_da_ferramenta(ia.TIPO_RECIBO)["function"]["parameters"]["properties"]
        extrato_props = ia.definicao_da_ferramenta(ia.TIPO_EXTRATO)["function"]["parameters"]["properties"]
        assert {"country", "currency", "lines", "net_before_tax", "social_security_base"} <= set(recibo_props)
        assert {"country", "currency", "total_credits", "total_debits"} <= set(extrato_props)
        for tipo in (ia.TIPO_RECIBO, ia.TIPO_EXTRATO):
            assert "Net payé" in ia.PROMPTS_POR_TIPO[tipo] and "Paid in" in ia.PROMPTS_POR_TIPO[tipo]


# ── a análise relê quando as contas não batem ────────────────────────────────
OPENAI = {"INDEX_AI_PROVIDER": "openai"}


def _analisar(chamada, tipo=ia.TIPO_RECIBO, conteudo=b"x", filename="r.pdf"):
    return (
        patch("services.index_ai.resolver_modelo", AsyncMock(return_value="m")),
        patch("services.ai_document.call_openai_api", chamada),
        patch("services.index_ai._registar_uso", AsyncMock()),
    )


class TestReleitura:
    @pytest.mark.asyncio
    async def test_leitura_que_nao_bate_e_relida_uma_vez_e_fica_a_boa(self):
        sem_linha = recibo_bruto(lines=recibo_bruto()["lines"][:1] + recibo_bruto()["lines"][2:])  # saltou o subsídio
        chamada = AsyncMock(side_effect=[{"data": sem_linha, "model": "m"}, {"data": recibo_bruto(), "model": "m"}])
        a, b, c = _analisar(chamada)
        with a, b, c, patch("services.index_ai._mensagens", return_value=([{"role": "system", "content": "p"}], False, 60.0)):
            r = await ia.analisar_documento(tipo=ia.TIPO_RECIBO, conteudo=b"x", filename="r.pdf", ambiente=OPENAI)
        assert chamada.await_count == 2
        nota = chamada.await_args_list[1].kwargs["messages"][-1]["content"]
        assert "CONFERÊNCIA AUTOMÁTICA" in nota and "1.000,00 €" in nota
        assert r.ok and len(r.factos["rubricas"]) == 4
        assert mx.conferencia_do_recibo(r.factos) == []

    @pytest.mark.asyncio
    async def test_leitura_que_bate_nao_paga_segunda_chamada(self):
        chamada = AsyncMock(return_value={"data": recibo_bruto(), "model": "m"})
        a, b, c = _analisar(chamada)
        with a, b, c, patch("services.index_ai._mensagens", return_value=([], False, 60.0)):
            r = await ia.analisar_documento(tipo=ia.TIPO_RECIBO, conteudo=b"x", filename="r.pdf", ambiente=OPENAI)
        assert r.ok and chamada.await_count == 1

    @pytest.mark.asyncio
    async def test_releitura_pior_fica_a_primeira(self):
        primeira = recibo_bruto(net_salary=campo(990))           # não bate, mas leu as quatro linhas
        pior = recibo_bruto(net_salary=campo(900), lines=[])     # também não bate e leu menos
        chamada = AsyncMock(side_effect=[{"data": primeira, "model": "m"}, {"data": pior, "model": "m"}])
        a, b, c = _analisar(chamada)
        with a, b, c, patch("services.index_ai._mensagens", return_value=([], False, 60.0)):
            r = await ia.analisar_documento(tipo=ia.TIPO_RECIBO, conteudo=b"x", filename="r.pdf", ambiente=OPENAI)
        assert r.factos["net"] == "990.00"

    @pytest.mark.asyncio
    async def test_releitura_que_falha_fica_a_primeira(self):
        primeira = recibo_bruto(net_salary=campo(990))
        chamada = AsyncMock(side_effect=[{"data": primeira, "model": "m"}, RuntimeError("timeout")])
        a, b, c = _analisar(chamada)
        with a, b, c, patch("services.index_ai._mensagens", return_value=([], False, 60.0)):
            r = await ia.analisar_documento(tipo=ia.TIPO_RECIBO, conteudo=b"x", filename="r.pdf", ambiente=OPENAI)
        assert r.ok and r.factos["net"] == "990.00"


# ── extratos longos aos blocos ───────────────────────────────────────────────
def _pdf_de_extrato(paginas: int, linhas_por_pagina: int = 45) -> bytes:
    import fitz  # PyMuPDF

    doc = fitz.open()
    for p in range(paginas):
        pagina = doc.new_page(width=842, height=1191)
        for y in range(linhas_por_pagina):
            texto = f"{(y % 28) + 1:02d}/09  PAG{p + 1} MOV{y + 1:02d} COMPRA NUM ESTABELECIMENTO COMERCIAL QUALQUER  -10,00  {1000 - y:>8},00"
            pagina.insert_text((30, 40 + 24 * y), texto, fontsize=9)
    out = doc.tobytes()
    doc.close()
    return out


class TestExtratoAosBlocos:
    def test_extrato_curto_vai_num_so_pedido(self):
        assert ia._blocos_do_extrato(_pdf_de_extrato(1, 10), "e.pdf", "application/pdf") == []
        assert ia._blocos_do_extrato(b"nao e pdf", "e.pdf", "application/pdf") == []
        assert ia._blocos_do_extrato(b"x", "e.jpg", "image/jpeg") == []

    def test_extrato_longo_vai_por_blocos_sem_perder_paginas(self):
        blocos = ia._blocos_do_extrato(_pdf_de_extrato(6), "e.pdf", "application/pdf")
        assert len(blocos) >= 3
        textos = [m[1]["content"] for m, _ in blocos]
        assert "BLOCO 1 de" in textos[0]
        for p in range(1, 7):  # todas as páginas, cada uma num só bloco
            assert sum(f"PAG{p} MOV45" in t for t in textos) == 1
        assert all(t == ia.TIMEOUT_EXTRATO for _, t in blocos)

    def test_nunca_mais_do_que_o_maximo_de_blocos(self):
        grupos = ia._no_maximo([[i] for i in range(30)], ia.MAXIMO_DE_BLOCOS)
        assert len(grupos) == ia.MAXIMO_DE_BLOCOS and sum(grupos, []) == list(range(30))

    def test_juntar_blocos(self):
        b1 = {"bank_name": campo("ING"), "iban": campo(None), "period_start": campo("2026-09-01"),
              "period_end": campo("2026-09-15"), "opening_balance": campo(1000), "closing_balance": campo(900),
              "total_credits": campo(None), "movements": [{"amount": 100, "kind": "debit"}], "findings": []}
        b2 = {"bank_name": campo(None), "iban": campo("NL91ABNA0417164300"), "period_end": campo("2026-09-30"),
              "opening_balance": campo(900), "closing_balance": campo(1400), "total_credits": campo(500),
              "movements": [{"amount": 500, "kind": "credit"}], "findings": [{"type": "numerario_atipico"}]}
        j = ia.juntar_blocos([b1, b2])
        assert [m["amount"] for m in j["movements"]] == [100, 500]
        assert j["opening_balance"]["value"] == 1000 and j["closing_balance"]["value"] == 1400
        assert j["bank_name"]["value"] == "ING" and j["iban"]["value"] == "NL91ABNA0417164300"
        assert j["period_start"]["value"] == "2026-09-01" and j["period_end"]["value"] == "2026-09-30"
        assert j["total_credits"]["value"] == 500 and len(j["findings"]) == 1

    @pytest.mark.asyncio
    async def test_analise_de_um_extrato_longo_junta_todos_os_movimentos(self):
        conteudo = _pdf_de_extrato(6)
        n_blocos = len(ia._blocos_do_extrato(conteudo, "e.pdf", "application/pdf"))

        async def responde(**kw):
            texto = kw["messages"][1]["content"]
            i = int(texto.split("BLOCO ")[1].split(" ")[0])
            saldo = 1000 - 10 * (i - 1)
            return {"data": {
                "iban": campo("PT50000201231234567890154"), "bank_name": campo("BPI"),
                "opening_balance": campo(saldo), "closing_balance": campo(saldo - 10),
                "movements": [{"date": "2026-09-02", "amount": 10, "kind": "debit", "balance": saldo - 10}],
                "findings": [],
            }, "model": "m"}

        chamada = AsyncMock(side_effect=responde)
        a, b, c = _analisar(chamada)
        with a, b, c:
            r = await ia.analisar_documento(tipo=ia.TIPO_EXTRATO, conteudo=conteudo, filename="e.pdf",
                                            mime="application/pdf", ambiente=OPENAI)
        assert r.ok and chamada.await_count == n_blocos
        assert len(r.factos["movimentos"]) == n_blocos
        assert r.factos["opening"] == "1000.00" and r.factos["closing"] == f"{1000 - 10 * n_blocos}.00"

    @pytest.mark.asyncio
    async def test_um_bloco_que_falha_faz_falhar_o_extrato(self):
        conteudo = _pdf_de_extrato(6)
        respostas = [{"data": {"movements": [{"amount": 1, "kind": "debit"}]}, "model": "m"}] * 20
        respostas[1] = {"data": {"movements": []}, "model": "m", "truncated": True}
        chamada = AsyncMock(side_effect=respostas)
        a, b, c = _analisar(chamada)
        with a, b, c:
            r = await ia.analisar_documento(tipo=ia.TIPO_EXTRATO, conteudo=conteudo, filename="e.pdf",
                                            mime="application/pdf", ambiente=OPENAI)
        assert r.ok is False and r.motivo == "resposta_incompleta"

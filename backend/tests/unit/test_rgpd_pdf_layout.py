"""Testes unitários — PACOTE DP: layout profissional do PDF RGPD.

Cobre a refatoração de `services/rgpd_pdf.py` (design profissional,
estrutura multi-página e blocos de assinatura estruturados) SEM I/O de
MongoDB (ver regra arquitetural em tests/unit/conftest.py):
- Parsing do CSS `_RGPD_PDF_HTML_STYLE` (fonte única de verdade do layout);
- `_build_signature_block` (Local/Data isolados + linha visível + 40px);
- `_build_prefilled_rgpd_pdf` (smoke: PDF válido, 3 partes em páginas
  próprias, texto legal preservado, rodapé com numeração).

Os templates por defeito (`RGPD_DEFAULT_TEMPLATE` / `MINUTA_DEFAULT_TEMPLATE`)
são usados tal como estão — o texto legal NÃO é alterado em lado nenhum.
"""
from io import BytesIO

import pytest
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, Spacer, Table

from pypdf import PdfReader

from services.rgpd_minutas import MINUTA_DEFAULT_TEMPLATE
from services.rgpd_pdf import (
    _RGPD_PDF_HTML_STYLE,
    _build_prefilled_rgpd_pdf,
    _build_signature_block,
    _parse_css_line_height,
    _parse_css_margin_cm,
    _parse_css_signature_margin_top_cm,
)
from services.rgpd_templates import RGPD_DEFAULT_TEMPLATE


CONSENT_DATA = {
    "nome": "João Silva",
    "contribuinte": "123456789",
    "tipo_documento": "Cartão de Cidadão",
    "numero_documento": "00000000",
    "validade_documento": "01/01/2030",
    "morada": "Rua das Flores, 12",
    "localidade": "Lisboa",
    "concelho": "Lisboa",
    "codigo_postal": "1100-000",
    "data_assinatura": "___/___/______",
}


def _render_template(template: str) -> str:
    """Substitui os placeholders do template pelos dados do cliente —
    o mesmo que `_get_rendered_rgpd_text` faz no fluxo real (mantém o
    teste unitário sem I/O de Mongo)."""
    rendered = template
    for key, value in {
        "{{NOME}}": CONSENT_DATA["nome"],
        "{{NOME_CLIENTE}}": CONSENT_DATA["nome"],
        "{{CONTRIBUINTE}}": CONSENT_DATA["contribuinte"],
        "{{MORADA}}": CONSENT_DATA["morada"],
        "{{LOCALIDADE}}": CONSENT_DATA["localidade"],
        "{{CODIGO_POSTAL}}": CONSENT_DATA["codigo_postal"],
        "{{TIPO_DOCUMENTO}}": "Cartão de Cidadão",
        "{{NUMERO_DOCUMENTO}}": CONSENT_DATA["numero_documento"],
        "{{VALIDADE_DOCUMENTO}}": CONSENT_DATA["validade_documento"],
        "{{DATA_ASSINATURA}}": CONSENT_DATA["data_assinatura"],
        "{{NOME_EMPRESA}}": "Precision Crédito, Lda.",
        "{{MORADA_EMPRESA}}": "Av. da Liberdade 100, Lisboa",
        "{{CONTACTO_EMPRESA}}": "+351 210 000 000",
    }.items():
        rendered = rendered.replace(key, value)
    return rendered


def _norm_text(text: str) -> str:
    """Normaliza espaços em branco — a extração do pypdf quebra linhas
    longas (justificação) com `\n`, partindo frases entre linhas."""
    return " ".join(text.split())


class TestCssDesignProfissional:
    """PACOTE DP — o CSS embutido é a fonte única de verdade do layout."""

    def test_margens_de_pagina_generosas_de_2_5cm(self):
        assert _parse_css_margin_cm(_RGPD_PDF_HTML_STYLE) == 2.5

    def test_line_height_confortavel_de_1_5(self):
        assert _parse_css_line_height(_RGPD_PDF_HTML_STYLE) == 1.5

    def test_declara_font_family_sans_serif_limpa(self):
        assert "Helvetica, Arial, sans-serif" in _RGPD_PDF_HTML_STYLE

    def test_declara_page_break_entre_as_3_partes(self):
        # Equivalente CSS dos PageBreak() inseridos pelo builder entre
        # Dados do Cliente, Consentimentos e Minuta de Exclusividade.
        assert "page-break-after: always" in _RGPD_PDF_HTML_STYLE

    def test_margin_da_pagina_ignora_margin_top_da_assinatura(self):
        # O lookahead negativo impede que o margin-top: 40px do bloco de
        # assinatura seja lido como margem da página.
        css_so_margin_top = "body { margin-top: 40px; }"
        assert _parse_css_margin_cm(css_so_margin_top) == 2.0  # default

        css_misturado = (
            ".signature-block { margin-top: 60px; margin: 1cm; }"
        )
        assert _parse_css_margin_cm(css_misturado) == 1.0

    def test_margin_top_do_bloco_de_assinatura_40px(self):
        # 40px @ 96dpi ≈ 1,06cm de espaço físico para assinar à caneta
        assert _parse_css_signature_margin_top_cm(_RGPD_PDF_HTML_STYLE) == (
            pytest.approx(1.06, abs=0.01)
        )

    def test_margin_top_default_quando_ausente_no_css(self):
        assert _parse_css_signature_margin_top_cm(
            "body { margin: 2.5cm; }"
        ) == pytest.approx(1.06, abs=0.01)

    def test_margin_top_converte_unidades(self):
        assert _parse_css_signature_margin_top_cm("a{margin-top:2cm}") == 2.0
        assert _parse_css_signature_margin_top_cm("a{margin-top:20mm}") == 2.0
        assert _parse_css_signature_margin_top_cm("a{margin-top:1in}") == 2.54
        assert _parse_css_signature_margin_top_cm("a{margin-top:80px}") == (
            pytest.approx(2.12, abs=0.01)
        )


class TestBlocoDeAssinatura:
    """PACOTE DP — `_build_signature_block` estrutura a assinatura."""

    @pytest.fixture
    def bloco(self):
        sig_style = ParagraphStyle(
            "TestSig", fontName="Helvetica", fontSize=9, leading=13.5
        )
        body_style = ParagraphStyle(
            "TestBody", fontName="Helvetica", fontSize=9, leading=13.5
        )
        return _build_signature_block(
            sig_style=sig_style,
            body_style=body_style,
            avail_width_pt=450.0,
            margin_top_cm=1.06,
        )

    def test_local_e_data_numa_linha_isolada_tabela(self, bloco):
        # A primeira flowable é uma Table de 1 linha x 2 colunas (sem
        # bordos): "Local" à esquerda, "Data" à direita.
        assert isinstance(bloco[0], Table)
        row = bloco[0]._cellvalues[0]
        assert len(row) == 2
        cell_texts = [getattr(cell, "text", "") for cell in row]
        assert any(t.startswith("Local:") for t in cell_texts)
        assert any(t.startswith("Data:") for t in cell_texts)

    def test_assinatura_do_cliente_em_bloco_abaixo(self, bloco):
        paragraphs = [f for f in bloco if isinstance(f, Paragraph)]
        labels = [p.text for p in paragraphs]
        assert "<b>Assinatura do Cliente:</b>" in labels

    def test_linha_de_assinatura_visivel(self, bloco):
        # Linha visível de underscores (para assinar à caneta por cima)
        paragraphs = [f for f in bloco if isinstance(f, Paragraph)]
        sig_lines = [
            p.text for p in paragraphs if p.text and set(p.text) == {"_"}
        ]
        assert sig_lines, "linha visível de assinatura em falta"
        assert len(sig_lines[0]) >= 30

    def test_margem_superior_40px_aplicada_como_espaco_fisico(self, bloco):
        # O margin-top do CSS (1,06cm) vira um Spacer entre a etiqueta e
        # a linha visível — espaço físico para assinar.
        spacers = [f.height for f in bloco if isinstance(f, Spacer)]
        assert any(abs(h - 1.06 * cm) < 0.6 for h in spacers)

    def test_legenda_assinar_a_caneta_preservada(self, bloco):
        texts = [getattr(f, "text", "") for f in bloco]
        assert any("(Assinar à caneta)" in t for t in texts)


class TestBuildPrefilledRgpdPdf:
    """PACOTE DP — smoke test do builder completo (sem I/O)."""

    @pytest.fixture(scope="module")
    def pdf_bytes(self):
        return _build_prefilled_rgpd_pdf(
            _render_template(RGPD_DEFAULT_TEMPLATE),
            _render_template(MINUTA_DEFAULT_TEMPLATE),
            CONSENT_DATA,
        )

    @pytest.fixture(scope="module")
    def textos_por_pagina(self, pdf_bytes):
        reader = PdfReader(BytesIO(pdf_bytes))
        return [page.extract_text() or "" for page in reader.pages]

    def test_gera_pdf_valido(self, pdf_bytes):
        assert pdf_bytes[:5] == b"%PDF-"
        assert len(pdf_bytes) > 5000

    def test_minimo_3_paginas(self, pdf_bytes):
        # 3 partes fundamentais: Dados do Cliente / Consentimentos / Minuta.
        # (Com o template por defeito de 11 secções, a Parte 1 flui para
        # 2 páginas físicas — mas as 3 partes começam em páginas próprias.)
        reader = PdfReader(BytesIO(pdf_bytes))
        assert len(reader.pages) >= 3

    def test_parte_1_cabecalho_corporativo_e_dados_do_cliente(
        self, textos_por_pagina
    ):
        primeira = textos_por_pagina[0]
        assert "AUTORIZAÇÃO PARA TRATAMENTO DE DADOS PESSOAIS" in primeira
        assert "RGPD — Regulamento (UE) 2016/679" in primeira
        # Dados do Cliente (secções do template legal, pré-preenchidas):
        assert "RESPONSÁVEL PELO TRATAMENTO" in primeira
        assert "TITULAR DOS DADOS" in primeira
        assert "João Silva" in primeira

    def test_parte_2_consentimentos_em_pagina_propria(self, textos_por_pagina):
        consent_idx = [
            i for i, t in enumerate(textos_por_pagina) if "CONSENTIMENTO" in t
        ]
        assert consent_idx, "secção de consentimentos em falta"
        idx = consent_idx[0]
        # Começa em página PRÓPRIA: nunca partilha com o texto legal...
        assert "RESPONSÁVEL PELO TRATAMENTO" not in textos_por_pagina[idx]
        # ...nem com a Minuta.
        assert "MINUTA DE EXCLUSIVIDADE" not in textos_por_pagina[idx]
        # Opções A/B/C/D com Autorizo/Não Autorizo:
        assert "Autorizo o tratamento dos meus dados pessoais" in (
            _norm_text(textos_por_pagina[idx])
        )
        assert "Não Autorizo" in textos_por_pagina[idx]

    def test_parte_3_minuta_em_pagina_propria(self, textos_por_pagina):
        minuta_idx = [
            i
            for i, t in enumerate(textos_por_pagina)
            if "venho por este meio" in _norm_text(t)
        ]
        assert minuta_idx, "minuta de exclusividade em falta"
        idx = minuta_idx[0]
        consent_idx = [
            i for i, t in enumerate(textos_por_pagina) if "CONSENTIMENTO" in t
        ][0]
        # A Minuta começa SEMPRE depois (página própria, nunca partilha
        # com os consentimentos):
        assert idx > consent_idx
        assert "Não Autorizo" not in textos_por_pagina[idx]

    def test_texto_legal_e_minuta_preservados(self, textos_por_pagina):
        # Normaliza espaços (a extração do pypdf quebra linhas longas).
        all_text = _norm_text(" ".join(textos_por_pagina))
        for trecho in [
            "RESPONSÁVEL PELO TRATAMENTO",
            "TITULAR DOS DADOS",
            "FINALIDADE DO TRATAMENTO",
            "DIREITOS DO TITULAR",
            "DECLARAÇÃO FINAL",
            "Autorizo o tratamento dos meus dados pessoais",
            "Não Autorizo",
            "Assinatura do Cliente",
            "MINUTA DE EXCLUSIVIDADE",
            "venho por este meio solicitar",
            "Banco de Portugal",
        ]:
            assert trecho in all_text, f"texto legal em falta: {trecho}"

    def test_bloco_de_assinatura_estruturado_nas_paginas_de_assinatura(
        self, textos_por_pagina
    ):
        for pagina in textos_por_pagina[1:]:
            if "CONSENTIMENTO" in pagina or "venho por este meio" in (
                _norm_text(pagina)
            ):
                linhas = [
                    linha.strip()
                    for linha in pagina.splitlines()
                    if linha.strip()
                ]
                local_idx = next(
                    (
                        i
                        for i, linha in enumerate(linhas)
                        if "Local:" in linha
                    ),
                    None,
                )
                data_idx = next(
                    (
                        i
                        for i, linha in enumerate(linhas)
                        if "Data:" in linha
                    ),
                    None,
                )
                sig_idx = next(
                    (
                        i
                        for i, linha in enumerate(linhas)
                        if "Assinatura do Cliente" in linha
                    ),
                    None,
                )
                assert local_idx is not None, "linha de Local em falta"
                assert data_idx is not None, "linha de Data em falta"
                assert sig_idx is not None, "etiqueta de assinatura em falta"
                # "Local" e "Data" na MESMA linha isolada (tabela) —
                # extraídos como linhas adjacentes, sem texto entre elas:
                assert abs(local_idx - data_idx) <= 1
                # A assinatura fica num BLOCO ABAIXO (linha distinta):
                assert sig_idx > local_idx and sig_idx > data_idx
                assert "Assinatura" not in linhas[local_idx]
                # Linha visível por baixo da etiqueta:
                assert any(
                    set(linha) == {"_"} and len(linha) >= 30
                    for linha in linhas[sig_idx:]
                ), "linha visível de assinatura em falta"

    def test_rodape_corporativo_com_numeracao(self, textos_por_pagina):
        total = len(textos_por_pagina)
        primeira = textos_por_pagina[0]
        ultima = textos_por_pagina[-1]
        assert "RGPD — Autorização para Tratamento de Dados Pessoais" in (
            primeira
        )
        assert "Página 1 de" in primeira
        assert f"Página {total} de {total}" in ultima

    def test_negrito_real_com_a_fonte_ttf(self):
        # PACOTE DP — com a DejaVuSans registada, o <b> resolve via
        # mapeamento de família (nunca mais lança exceção do tt2ps).
        import services.rgpd_pdf as rgpd_pdf_mod

        rgpd_pdf_mod._ensure_font()
        if not rgpd_pdf_mod._FONT_REGISTERED:
            pytest.skip("DejaVuSans não disponível neste ambiente")

        from reportlab.lib.fonts import tt2ps

        bold = tt2ps("DejaVuSans", 1, 0)
        assert bold in ("DejaVuSans-Bold", "DejaVuSans")

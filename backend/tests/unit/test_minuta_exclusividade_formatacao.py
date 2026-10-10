"""Formatação da Minuta de Exclusividade assinada (Bloco 5, ponto 36).

O oráculo é o PDF REAL, lido com o PyMuPDF (texto, fontes e coordenadas): nenhum
duplo do renderizador. O defeito era o `_build_minuta_pdf` desenhar o texto linha
a linha num canvas — perdia quebras, negrito, alinhamento e parágrafos inteiros.
"""
import re
from unittest.mock import AsyncMock, patch

import fitz  # PyMuPDF
import pytest

from services import minuta_pdf as mp
from services import rgpd_pdf, rgpd_service
from services.rgpd_minutas import MINUTA_DEFAULT_TEMPLATE

CONSENT = {"nome": "Ana Costa", "localidade": "Lisboa", "data_assinatura": "10/10/2026 11:00"}
LARGURA, ALTURA = 595.28, 841.89  # A4 em pontos
MARGEM = 2.5 * 28.3465 + 6  # margem da página + 6 pt de enchimento da moldura do platypus


def pdf(texto, consent=CONSENT):
    return rgpd_service._build_minuta_pdf(texto, consent)


def paginas(dados):
    return list(fitz.open(stream=dados, filetype="pdf"))


def texto(dados):
    return "\n".join(p.get_text() for p in paginas(dados))


def linhas(dados):
    """[(texto, bbox, é_negrito)] de todas as linhas do documento."""
    saida = []
    for numero, pagina in enumerate(paginas(dados)):
        for bloco in pagina.get_text("dict")["blocks"]:
            for linha in bloco.get("lines", []):
                spans = linha["spans"]
                conteudo = "".join(s["text"] for s in spans).strip()
                if conteudo:
                    negrito = any("Bold" in s["font"] for s in spans)
                    saida.append((conteudo, fitz.Rect(linha["bbox"]), negrito, numero))
    return saida


def linha_com(dados, trecho):
    return next(l for l in linhas(dados) if trecho in l[0])


# ── quebras de linha e parágrafos ──────────────────────────────────────────

def test_o_texto_por_omissao_sai_inteiro_e_o_titulo_uma_so_vez():
    renderizado = MINUTA_DEFAULT_TEMPLATE.replace("{{", "<<").replace("}}", ">>")
    for var in ("NOME", "TIPO_DOCUMENTO", "NUMERO_DOCUMENTO", "VALIDADE_DOCUMENTO", "CONTRIBUINTE", "MORADA", "LOCALIDADE", "CODIGO_POSTAL", "NOME_EMPRESA"):
        renderizado = renderizado.replace(f"<<{var}>>", f"valor-{var.lower()}")
    dados = pdf(renderizado)
    t = texto(dados)
    assert t.count("MINUTA DE EXCLUSIVIDADE") == 1, "o título repete-se (o do cabeçalho + o do template)"
    assert "venho por este meio solicitar" in t.replace("\n", " ")
    assert "abdicando dos serviços de outras entidades" in t.replace("\n", " ")


def test_o_html_do_administrador_nao_sai_com_tags_literais():
    dados = pdf("<p>Primeiro parágrafo.</p><p>Segundo parágrafo.</p>")
    t = texto(dados)
    assert "<p>" not in t and "</p>" not in t
    assert "Primeiro parágrafo." in t and "Segundo parágrafo." in t


def test_cada_paragrafo_comeca_numa_linha_nova_e_o_espaco_entre_eles_e_preservado():
    dados = pdf("<p>Um.</p><p><br></p><p>Dois.</p><p>Tres.</p>")
    um, dois, tres = (linha_com(dados, x)[1] for x in ("Um.", "Dois.", "Tres."))
    assert dois.y0 > um.y1 and tres.y0 > dois.y1
    assert (dois.y0 - um.y1) > (tres.y0 - dois.y1) + 5, "a linha em branco do editor perdeu-se"


def test_quebra_dentro_de_um_paragrafo_e_respeitada():
    dados = pdf("<p>linha-a<br>linha-b</p>")
    a, b = linha_com(dados, "linha-a")[1], linha_com(dados, "linha-b")[1]
    assert b.y0 >= a.y1 - 1 and b.y0 > a.y0


def test_texto_simples_com_linhas_vazias_mantem_os_paragrafos():
    dados = pdf("Primeiro bloco.\n\nSegundo bloco.\nContinua o segundo.")
    p1, p2, p2b = (linha_com(dados, x)[1] for x in ("Primeiro bloco.", "Segundo bloco.", "Continua o segundo."))
    assert p2.y0 > p1.y1 and p2b.y0 > p2.y0


# ── negrito ────────────────────────────────────────────────────────────────

def test_o_negrito_do_editor_sai_a_negrito_e_o_resto_nao():
    dados = pdf("<p>Antes <strong>destacado</strong> depois.</p>")
    spans = [s for p in paginas(dados) for b in p.get_text("dict")["blocks"] for l in b.get("lines", []) for s in l["spans"]]
    por_texto = {s["text"].strip(): "Bold" in s["font"] for s in spans if s["text"].strip()}
    assert por_texto["destacado"] is True
    assert por_texto["Antes"] is False and por_texto["depois."] is False


def test_um_titulo_h2_sai_a_negrito():
    dados = pdf("<h2>Cláusula Primeira</h2><p>texto</p>")
    assert linha_com(dados, "Cláusula Primeira")[2] is True


# ── alinhamento ────────────────────────────────────────────────────────────

def centro(rect):
    return (rect.x0 + rect.x1) / 2


def test_alinhamento_do_quill_ao_centro():
    dados = pdf('<p class="ql-align-center">Centrado</p>')
    assert abs(centro(linha_com(dados, "Centrado")[1]) - LARGURA / 2) < 6


def test_alinhamento_do_quill_a_direita():
    dados = pdf('<p class="ql-align-right">Direita</p>')
    assert abs(linha_com(dados, "Direita")[1].x1 - (LARGURA - MARGEM)) < 4


def test_text_align_em_estilo_tambem_vale():
    dados = pdf('<p style="text-align: right">Direita-estilo</p><p style="text-align:center;">Centro-estilo</p>')
    assert abs(linha_com(dados, "Direita-estilo")[1].x1 - (LARGURA - MARGEM)) < 4
    assert abs(centro(linha_com(dados, "Centro-estilo")[1]) - LARGURA / 2) < 6


def test_sem_alinhamento_pedido_o_corpo_fica_justificado_a_esquerda():
    dados = pdf("<p>Curto</p>")
    assert abs(linha_com(dados, "Curto")[1].x0 - MARGEM) < 3


def test_titulo_com_alinhamento():
    dados = pdf('<h2 class="ql-align-center">Titulo Centrado</h2>')
    assert abs(centro(linha_com(dados, "Titulo Centrado")[1]) - LARGURA / 2) < 6


def test_so_o_alinhamento_passa_pelo_filtro_de_atributos():
    ok = rgpd_pdf._atributo_permitido
    assert ok("p", "class", "ql-align-center") and ok("p", "class", "ql-align-justify ql-align-center")
    assert not ok("p", "class", "ql-size-huge")
    assert not ok("p", "class", "ql-align-center evil")
    assert not ok("p", "style", "text-align:center")  # converte-se antes, nunca passa em bruto
    assert not ok("p", "style", "color:red")
    assert not ok("a", "href", "javascript:alert(1)")
    assert not ok("p", "onclick", "x()")


def test_atributos_perigosos_nao_chegam_ao_pdf_nem_o_partem():
    dados = pdf('<p onclick="x()" style="color:red" class="evil">Seguro</p><script>alert(1)</script>')
    t = texto(dados)
    assert "Seguro" in t
    assert "onclick" not in t and "alert" not in t


@pytest.mark.parametrize(
    "entrada,esperado",
    [
        ('<p style="text-align: center">x</p>', '<p class="ql-align-center">x</p>'),
        ("<p style='text-align:right;'>x</p>", '<p class="ql-align-right">x</p>'),
        ('<p class="ql-indent-1" style="text-align:justify">x</p>', '<p class="ql-indent-1 ql-align-justify">x</p>'),
        ('<h2 style="TEXT-ALIGN: Center">x</h2>', '<h2 class="ql-align-center">x</h2>'),
        ('<p style="color:red">x</p>', "<p>x</p>"),
        ('<p style="text-align:center; background:url(javascript:alert(1))">x</p>', "<p>x</p>"),
        ("<span style=\"text-align:center\">x</span>", "<span style=\"text-align:center\">x</span>"),
    ],
)
def test_text_align_em_estilo_converte_se_em_classe_e_o_resto_do_css_cai(entrada, esperado):
    assert rgpd_pdf._estilo_de_alinhamento_para_classe(entrada) == esperado


# ── variáveis por resolver ─────────────────────────────────────────────────

def test_uma_variavel_por_resolver_nao_apaga_o_paragrafo():
    """Antes: qualquer linha com `{{` era DESCARTADA e a minuta saía sem o texto principal."""
    dados = pdf("Eu, Ana Costa, venho solicitar os serviços da {{EMPRESA_NOVA}} em exclusivo.")
    t = texto(dados).replace("\n", " ")
    assert "venho solicitar os serviços da" in t
    assert "em exclusivo" in t
    assert "{{" not in t and mp.LINHA_EM_BRANCO in t


def test_preencher_variaveis_regista_aviso(caplog):
    with caplog.at_level("WARNING"):
        saida = mp.preencher_variaveis_em_falta("a {{X}} b {{Y}} c {{X}}")
    assert saida == f"a {mp.LINHA_EM_BRANCO} b {mp.LINHA_EM_BRANCO} c {mp.LINHA_EM_BRANCO}"
    assert any("{{X}}" in m and "{{Y}}" in m for m in caplog.messages)


# ── título ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "entrada,resto",
    [
        ("MINUTA DE EXCLUSIVIDADE\n\nCorpo", "Corpo"),
        ("  Minuta de Exclusividade\nCorpo", "Corpo"),
        ("<p><strong>MINUTA DE EXCLUSIVIDADE</strong></p><p>Corpo</p>", "<p>Corpo</p>"),
        ("<h1>MINUTA DE EXCLUSIVIDADE</h1><p>Corpo</p>", "<p>Corpo</p>"),
        ('<p class="ql-align-center"><u><b>MINUTA DE EXCLUSIVIDADE</b></u></p><p>Corpo</p>', "<p>Corpo</p>"),
    ],
)
def test_o_titulo_repetido_sai_do_corpo(entrada, resto):
    assert mp.sem_titulo_repetido(entrada).strip() == resto


@pytest.mark.parametrize("entrada", ["Corpo MINUTA DE EXCLUSIVIDADE no meio", "<p>Outro título</p>", "", None])
def test_so_o_titulo_do_inicio_sai(entrada):
    assert mp.sem_titulo_repetido(entrada) == (entrada or "")


# ── paginação ──────────────────────────────────────────────────────────────

def test_um_paragrafo_muito_comprido_nao_ultrapassa_a_margem_inferior():
    """Antes a pergunta «cabe?» só se fazia no fim do parágrafo."""
    longo = "<p>" + " ".join(f"palavra{i}" for i in range(1500)) + "</p>"
    dados = pdf(longo)
    assert len(paginas(dados)) >= 3
    corpo = [l for l in linhas(dados) if l[1].y1 < ALTURA - 2.0 * 28.3465]  # sem o rodapé
    assert len(corpo) > 40
    for conteudo, rect, _, _ in corpo:
        assert rect.y1 <= ALTURA - 2.4 * 28.3465, f"linha fora da área útil: {conteudo[:30]}"
        assert rect.x1 <= LARGURA - MARGEM + 4


def test_o_bloco_de_assinatura_nao_se_parte_entre_paginas():
    """Percorre todos os comprimentos de texto: algures a fronteira da página
    cai dentro do bloco, e é aí que um fluxo sem `KeepTogether` o parte."""
    partidos = []
    for repeticoes in range(1, 60):
        dados = pdf("".join("<p>" + "linha de teste " * 14 + "</p>" for _ in range(repeticoes)))
        marcas = ("Lisboa,", "Assinatura do Cliente", "Titular dos Dados", "Por favor assine")
        locais = {l[3] for l in linhas(dados) if any(m in l[0] for m in marcas)}
        if len(locais) != 1:
            partidos.append(repeticoes)
    assert not partidos, f"bloco de assinatura partido com {partidos} parágrafos"


# ── caracteres e assinatura ────────────────────────────────────────────────

def test_aspas_e_travessoes_tipograficos_nao_viram_pontos_de_interrogacao():
    dados = pdf("<p>“Citação” — travessão – e reticências…</p>")
    t = texto(dados)
    assert "“Citação”" in t and "—" in t and "…" in t and "?" not in t


def test_a_assinatura_manuscrita_e_incluida():
    import base64
    import io

    from PIL import Image

    imagem = Image.new("RGB", (400, 120), "white")
    buffer = io.BytesIO()
    imagem.save(buffer, "PNG")
    consent = {**CONSENT, "assinatura": "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()}
    com = pdf("<p>Corpo</p>", consent)
    sem = pdf("<p>Corpo</p>")
    assert sum(len(p.get_images()) for p in paginas(com)) == 1
    assert sum(len(p.get_images()) for p in paginas(sem)) == 0


def test_assinatura_corrompida_nao_impede_a_minuta():
    dados = pdf("<p>Corpo</p>", {**CONSENT, "assinatura": "data:image/png;base64,@@@@"})
    assert "Corpo" in texto(dados)


def test_local_e_data_aparecem_quando_conhecidos():
    assert "Lisboa, 10/10/2026" in texto(pdf("<p>x</p>"))
    assert "Lisboa," not in texto(pdf("<p>x</p>", {"nome": "A"}))


def test_o_rodape_numera_as_paginas():
    t = texto(pdf("<p>" + "x " * 4000 + "</p>"))
    assert re.search(r"Página 1 de \d+", t)


def test_se_a_conversao_do_html_falhar_a_minuta_sai_em_texto_simples():
    """A minuta assinada tem de existir, mesmo que o texto do administrador não converta."""
    with patch.object(rgpd_pdf, "_html_to_flowables", side_effect=ValueError("html impossível")):
        dados = pdf("<p>Texto que tem de sobreviver.</p>")
    assert "Texto que tem de sobreviver." in texto(dados)


def test_texto_vazio_ou_ilegivel_ainda_gera_uma_minuta_valida():
    assert paginas(pdf(""))
    assert paginas(pdf(None))
    assert paginas(pdf("<<<>>> & <p"))


# ── o PDF pré-preenchido partilha a mesma regra ────────────────────────────

def test_o_pdf_combinado_tambem_nao_repete_o_titulo_nem_perde_alinhamento():
    dados = rgpd_pdf._build_prefilled_rgpd_pdf(
        "Texto RGPD.", 'MINUTA DE EXCLUSIVIDADE\n\nCorpo da minuta {{X}}.', CONSENT,
    )
    ultima = paginas(dados)[-1].get_text()
    assert ultima.count("MINUTA DE EXCLUSIVIDADE") == 1
    assert "{{" not in ultima
    dados = rgpd_pdf._build_prefilled_rgpd_pdf("Texto RGPD.", '<p class="ql-align-center">Centrada</p>', CONSENT)
    ultima = paginas(dados)[-1]
    rect = next(fitz.Rect(l["bbox"]) for b in ultima.get_text("dict")["blocks"] for l in b.get("lines", []) if "Centrada" in "".join(s["text"] for s in l["spans"]))
    assert abs(centro(rect) - LARGURA / 2) < 6


# ── valores com caracteres especiais num modelo HTML ───────────────────────

@pytest.mark.asyncio
async def test_um_nome_com_e_comercial_nao_parte_o_html_do_modelo(fake_async_db):
    fake_async_db.processes.docs.append({"id": "p1", "client_name": "Silva & Filhos <Lda>", "personal_data": {}})
    empresa = {"nome": "Precision", "nif": "1", "morada": "Rua A", "email": "a@b.c", "contacto": "9"}
    with patch.object(rgpd_service, "db", fake_async_db), \
         patch.object(rgpd_service, "_get_company_legal_data", AsyncMock(return_value=empresa)), \
         patch.object(rgpd_service, "_titular_fallback_data", AsyncMock(return_value={})), \
         patch("services.rgpd_minutas._get_active_minuta_template", AsyncMock(return_value="<p>Eu, <strong>{{NOME}}</strong>, da {{NOME_EMPRESA}}.</p>")):
        renderizado = await rgpd_service._get_rendered_minuta_text(
            "p1", {"client_name": "Silva & Filhos <Lda>"}, {"nome": "Silva & Filhos <Lda>"},
        )
    assert "Silva &amp; Filhos &lt;Lda&gt;" in renderizado
    t = texto(pdf(renderizado))
    assert "Silva & Filhos <Lda>" in t.replace("\n", " ")


@pytest.mark.asyncio
async def test_num_modelo_de_texto_simples_o_valor_nao_e_escapado_duas_vezes(fake_async_db):
    fake_async_db.processes.docs.append({"id": "p1", "client_name": "Silva & Filhos", "personal_data": {}})
    empresa = {"nome": "Precision", "nif": "1", "morada": "Rua A", "email": "a@b.c", "contacto": "9"}
    with patch.object(rgpd_service, "db", fake_async_db), \
         patch.object(rgpd_service, "_get_company_legal_data", AsyncMock(return_value=empresa)), \
         patch.object(rgpd_service, "_titular_fallback_data", AsyncMock(return_value={})), \
         patch("services.rgpd_minutas._get_active_minuta_template", AsyncMock(return_value="Eu, {{NOME}}, da {{NOME_EMPRESA}}.")):
        renderizado = await rgpd_service._get_rendered_minuta_text(
            "p1", {"client_name": "Silva & Filhos"}, {"nome": "Silva & Filhos"},
        )
    assert "Silva & Filhos" in renderizado and "&amp;" not in renderizado
    assert "Silva & Filhos" in texto(pdf(renderizado)).replace("\n", " ")

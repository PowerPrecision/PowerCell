"""
Serviço RGPD PDF — geração de PDF RGPD PRÉ-PREENCHIDO com dados do cliente.

PACOTE DE — endpoint de download de PDF RGPD pré-preenchido (sem assinatura
digital). Reutiliza a infraestrutura existente em `services/rgpd_service.py`:
- `_get_rendered_rgpd_text(process_id, rgpd_request, consent_data)` — busca o
  processo, desencripta, obtém o template RGPD ativo e substitui os
  placeholders `{{NOME}}`, `{{CONTRIBUINTE}}`, etc.

PACOTE DG — novo builder `_build_prefilled_rgpd_pdf` baseado em
`reportlab.platypus` (SimpleDocTemplate + Flowables) que:
- Honra o `rgpd_text` dinâmico (11 secções do template admin) — o builder
  anterior `_build_rgpd_pdf` (em `rgpd_service.py`) ignora o template e
  usa texto hardcoded; NÃO é modificado (continua a ser usado pelo fluxo
  de assinatura digital `sign_rgpd`).
- Paginação automática via `SimpleDocTemplate` (sem `c.showPage()` manual).
- Campos em falta → linhas em branco "_____" (para preenchimento à caneta).
- Data e Local da assinatura → linhas em branco (não pré-preenchidos).
- Checkboxes A/B/C/D → quadrados vazios ☐ (Unicode U+2610), NÃO
  pré-marcados como "Não Autorizo".
- Regista TTF font (DejaVuSans) para suporte Unicode (acentos PT + ☐).

PACOTE FR-2 — Estética do PDF RGPD:
- Cabeçalho HTML com CSS embutido (`_RGPD_PDF_HTML_STYLE`) como fonte
  única de verdade para margens laterais, `text-align: justify` e
  `line-height` legível — lido via `_parse_css_margin_cm` /
  `_parse_css_line_height` e aplicado aos estilos reportlab.
- Texto simples (ex.: `RGPD_DEFAULT_TEMPLATE`) é convertido em HTML real
  (`_wrap_plain_text_as_html`) com `<p>`/`<br>` respeitados, em vez do
  antigo fallback linha-a-linha.
- Títulos de secção / termos-chave RGPD (ex.: "RESPONSÁVEL PELO
  TRATAMENTO", "TITULAR DOS DADOS") são sempre convertidos em `<strong>`/
  `<b>` (negrito), mesmo quando o template de origem não os marca.

PACOTE DP — Design profissional do PDF RGPD (estrutura multi-página):
- CSS `_RGPD_PDF_HTML_STYLE` reforçado: font-family sans-serif limpa
  (Helvetica/Arial), margens generosas de 2,5cm e line-height 1,5.
- 3 partes fundamentais, cada uma a começar em página própria
  (equivalente reportlab do CSS `page-break-after: always`):
  1) Cabeçalho corporativo + texto legal RGPD (Dados do Cliente);
  2) Consentimentos (Autorizo/Não Autorizo) + bloco de assinatura;
  3) Minuta de Exclusividade + bloco de assinatura.
  (Se o template legal for longo, a Parte 1 flui naturalmente para
  páginas adicionais; as Partes 2 e 3 começam sempre em página própria.)
- `_build_signature_block` (novo, partilhado RGPD+Minuta): "Local" e
  "Data" numa linha isolada (tabela 2 colunas); "Assinatura do Cliente"
  num bloco abaixo com linha visível e margem superior de 40px (lida do
  CSS) para assinatura física à caneta.
- Rodapé corporativo em todas as páginas: régua fina + título do
  documento + numeração "Página X de Y" (padrão NumberedCanvas).
- DejaVuSans-Bold registada com mapeamento de família — `<b>` passa a
  renderizar negrito REAL (antes era silenciosamente ignorado com a
  TTF, porque tt2ps não resolvia "DejaVuSans-Bold").
"""
from __future__ import annotations

import io
import logging
import os
import re
from datetime import datetime, timezone

# PACOTE DI — HTML parsing (lxml) + sanitização (bleach) para conversão
# do conteúdo HTML do SmartRichEditor (ReactQuill) em Flowables do reportlab.
from lxml import html as lxml_html
import bleach

from fastapi import HTTPException

from database import db
from services.process_service import decrypt_sensitive_data
# PACOTE DE — reutilização das funções internas (underscore prefix) de rgpd_service.
# Python não enforce privacy; importação cross-module é aceitável aqui.
# `_get_rendered_rgpd_text` renderiza o template RGPD ativo com os
# placeholders substituídos pelos dados do cliente (ou linhas em branco).
# PACOTE DI — `_get_rendered_minuta_text` (mesmo padrão) para a Minuta.
from services.rgpd_service import (
    _get_rendered_rgpd_text,
    _get_rendered_minuta_text,
)
from services.rgpd_helpers import _add_process_activity

logger = logging.getLogger(__name__)


# PACOTE DI — Tags permitidas no conteúdo HTML vindo do SmartRichEditor.
# Permite apenas tags seguras e suportadas pelo conversor de Flowables.
_PACOTE_DI_ALLOWED_TAGS = [
    "p", "br", "strong", "b", "em", "i", "u",
    "ul", "ol", "li",
    "h1", "h2", "h3", "h4", "h5", "h6",
    "div", "span",
]


# ---------------------------------------------------------------------------
# PACOTE DG — Registo de fonte TTF (DejaVuSans) para suporte Unicode
# (acentos PT + símbolo ☐ U+2610 BALLOT BOX). Procura em vários paths
# Linux; fallback para Helvetica se não encontrar (acentos podem aparecer mal).
# ---------------------------------------------------------------------------
_FONT_REGISTERED = False


def _register_dejavu_bold_variant(pdfmetrics, regular_path: str) -> str:
    """PACOTE DP — Regista a variante Bold e o mapeamento de família.

    Sem isto, o markup `<b>`/`<strong>` era silenciosamente IGNORADO com
    a TTF (tt2ps não resolvia "DejaVuSans-Bold") — os títulos de secção
    e etiquetas saíam sem negrito. Sem Bold disponível, o mapeamento
    degrada graciosamente para a regular (comportamento antigo).

    Args:
        pdfmetrics: módulo reportlab.pdfbase (já importado com sucesso).
        regular_path: Caminho da DejaVuSans regular já registada.

    Returns:
        Nome da variante bold efectiva ("DejaVuSans-Bold" ou
        "DejaVuSans" quando degrada para a regular).
    """
    from reportlab.pdfbase.ttfonts import TTFont

    bold_name = "DejaVuSans"
    bold_path = os.path.join(
        os.path.dirname(regular_path), "DejaVuSans-Bold.ttf"
    )
    if os.path.exists(bold_path):
        try:
            pdfmetrics.registerFont(TTFont("DejaVuSans-Bold", bold_path))
            bold_name = "DejaVuSans-Bold"
        except Exception as bold_err:
            logger.warning(
                "PACOTE DP — Erro ao registar DejaVuSans-Bold %s: %s "
                "(a usar só a regular)",
                bold_path,
                bold_err,
            )
    try:
        pdfmetrics.registerFontFamily(
            "DejaVuSans",
            normal="DejaVuSans",
            bold=bold_name,
            italic="DejaVuSans",  # sem oblíqua no bundle padrão
            boldItalic=bold_name,
        )
    except Exception as family_err:
        logger.warning(
            "PACOTE DP — Erro no mapeamento de família DejaVuSans: %s "
            "(negrito/itálico podem não renderizar)",
            family_err,
        )
    return bold_name


def _ensure_font() -> None:
    """Regista DejaVuSans no reportlab (idempotente). Fallback Helvetica.

    PACOTE DL — expandido com mais caminhos (Docker minimal, macOS, repo bundle)
    para garantir que ☐ (U+2610) renderiza como quadrado vazio e não como
    glyph .notdef (quadrado preto) do Helvetica.
    """
    global _FONT_REGISTERED
    if _FONT_REGISTERED:
        return
    # PACOTE DL — caminhos expandidos para maior compatibilidade
    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans.ttf",
        "/usr/local/share/fonts/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        # Docker minimal / Alpine
        "/usr/share/fonts/ttf/dejavu/DejaVuSans.ttf",
        # macOS (dev)
        "/System/Library/Fonts/Supplemental/DejaVuSans.ttf",
        "/Library/Fonts/DejaVuSans.ttf",
        # Repo bundle (fallback absoluto)
        os.path.join(os.path.dirname(__file__), "..", "assets", "fonts", "DejaVuSans.ttf"),
    ]
    try:
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
    except ImportError:
        logger.warning(
            "PACOTE DL — reportlab.pdfbase indisponível, a usar Helvetica"
        )
        return
    for path in font_paths:
        if os.path.exists(path):
            try:
                pdfmetrics.registerFont(TTFont("DejaVuSans", path))
                _FONT_REGISTERED = True
                # PACOTE DP — variante Bold + mapeamento de família para
                # `<b>` renderizar negrito REAL (ver helper).
                _register_dejavu_bold_variant(pdfmetrics, path)
                logger.info("PACOTE DL — DejaVuSans registada: %s", path)
                return
            except Exception as e:
                logger.warning(
                    "PACOTE DL — Erro ao registar DejaVuSans %s: %s", path, e
                )
    logger.warning(
        "PACOTE DL — DejaVuSans não encontrada em nenhum caminho. "
        "A usar Helvetica — ☐ (U+2610) pode não renderizar corretamente. "
        "Instalar fonts-dejavu ou colocar DejaVuSans.ttf em backend/assets/fonts/"
    )


def _blank_line(width: int = 30) -> str:
    """Linha em branco contínua para preenchimento à caneta."""
    return "_" * width


def _escape_xml(text) -> str:
    """Escape XML special chars for reportlab Paragraph."""
    if not text:
        return ""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


# ---------------------------------------------------------------------------
# PACOTE FR-2 — Estética do PDF RGPD.
#
# O PDF saía com aspeto de "texto bruto": o template por defeito
# (`RGPD_DEFAULT_TEMPLATE`, em `rgpd_service.py`) é texto simples (sem
# markup HTML), pelo que cada linha era convertida num parágrafo isolado
# sem qualquer negrito nos títulos de secção ("1. RESPONSÁVEL PELO
# TRATAMENTO", "2. TITULAR DOS DADOS", ...).
#
# `_RGPD_PDF_HTML_STYLE` é o cabeçalho HTML com CSS embutido que define a
# estética do documento (margens laterais decentes, texto justificado e
# "line-height" legível). Não é injetado como texto no PDF — é a fonte
# única de verdade: `_parse_css_margin_cm` / `_parse_css_line_height` leem
# estes valores e aplicam-nos aos estilos/margens reais do reportlab, para
# que CSS e layout nunca fiquem dessincronizados.
#
# O conteúdo (HTML rico do SmartRichEditor OU texto simples) passa sempre
# pela mesma pipeline `_html_to_flowables`: texto simples é primeiro
# convertido em HTML real (`_wrap_plain_text_as_html`) com `<p>`/`<br>`
# verdadeiros e títulos de secção / termos-chave RGPD marcados
# `<strong>`, garantindo negrito consistente em ambos os casos.
# ---------------------------------------------------------------------------
_RGPD_PDF_HTML_STYLE = """
<style>
  /* PACOTE DP — Design profissional do PDF RGPD. Fonte única de verdade:
     lido por _parse_css_margin_cm / _parse_css_line_height /
     _parse_css_signature_margin_top_cm e aplicado aos estilos reportlab. */
  body {
    font-family: Helvetica, Arial, sans-serif;
    margin: 2.5cm;             /* margens de página generosas */
    text-align: justify;
    line-height: 1.5;          /* interlinha confortável */
  }
  /* 3 partes em páginas distintas — o builder insere PageBreak()
     (equivalente reportlab) entre Dados do Cliente, Consentimentos e
     Minuta de Exclusividade. */
  .page {
    page-break-after: always;
  }
  h1, h2, h3, h4, h5, h6, .section-title, strong, b {
    font-weight: bold;
  }
  /* Bloco de assinatura — linha visível com margem superior para o
     cliente assinar fisicamente (40px ≈ 1,06cm). */
  .signature-block .sig-line {
    margin-top: 40px;
  }
</style>
""".strip()

# Títulos / termos-chave RGPD que devem sair sempre a negrito no PDF, ainda
# que o template de origem seja texto simples (sem `<strong>`/`<b>`).
_RGPD_PDF_BOLD_KEYWORDS = [
    "RESPONSÁVEL PELO TRATAMENTO",
    "TITULAR DOS DADOS",
    "FINALIDADE DO TRATAMENTO",
    "BASE LEGAL",
    "DESTINATÁRIOS DOS DADOS",
    "PRAZO DE CONSERVAÇÃO",
    "DIREITOS DO TITULAR",
    "PARTILHA DE DADOS",
    "TRANSFERÊNCIA INTERNACIONAL",
    "DECISÕES AUTOMATIZADAS",
    "DECLARAÇÃO FINAL",
    "CONSENTIMENTO",
]


def _parse_css_margin_cm(css: str, default_cm: float = 2.0) -> float:
    r"""Lê o valor de `margin` do cabeçalho `<style>` (px/cm/mm/in) e
    devolve-o em centímetros, para usar como margem lateral do PDF.

    PACOTE DP — o lookahead negativo `(?![-\w])` exclui propriedades
    compostas (`margin-top`, `margin-left`, ...) para que a margem da
    página nunca seja lida da margem do bloco de assinatura.
    """
    match = re.search(
        r"margin(?![-\w])\s*:\s*(\d+(?:\.\d+)?)\s*(px|cm|mm|in)?",
        css,
        re.IGNORECASE,
    )
    if not match:
        return default_cm
    value = float(match.group(1))
    unit = (match.group(2) or "px").lower()
    if unit == "cm":
        return value
    if unit == "mm":
        return round(value / 10.0, 2)
    if unit == "in":
        return round(value * 2.54, 2)
    # px assumindo 96 DPI
    return round((value / 96.0) * 2.54, 2)


def _parse_css_line_height(css: str, default: float = 1.5) -> float:
    """Lê o valor de `line-height` do cabeçalho `<style>` (rácio, ex.:
    `1.5`) para calcular o "leading" (interlinha) dos parágrafos."""
    match = re.search(r"line-height\s*:\s*(\d+(?:\.\d+)?)", css, re.IGNORECASE)
    if not match:
        return default
    return float(match.group(1))


def _parse_css_signature_margin_top_cm(
    css: str, default_px: float = 40.0
) -> float:
    """PACOTE DP — Lê o `margin-top` do bloco `.signature-block` do
    cabeçalho `<style>` (px/cm/mm/in) e devolve-o em centímetros.

    É o espaço físico reservado acima da linha de assinatura para o
    cliente assinar à caneta (40px @ 96dpi ≈ 1,06cm).
    """
    match = re.search(
        r"margin-top\s*:\s*(\d+(?:\.\d+)?)\s*(px|cm|mm|in)?",
        css,
        re.IGNORECASE,
    )
    if not match:
        return round((default_px / 96.0) * 2.54, 2)
    value = float(match.group(1))
    unit = (match.group(2) or "px").lower()
    if unit == "cm":
        return value
    if unit == "mm":
        return round(value / 10.0, 2)
    if unit == "in":
        return round(value * 2.54, 2)
    # px assumindo 96 DPI
    return round((value / 96.0) * 2.54, 2)


def _is_section_heading(line: str) -> bool:
    """Deteta se uma linha de texto simples é um título de secção RGPD
    (ex.: '1. RESPONSÁVEL PELO TRATAMENTO') ou um termo-chave legal
    conhecido — para ser convertida em `<strong>` (negrito) no PDF."""
    stripped = line.strip()
    if not stripped:
        return False
    upper = stripped.upper()
    if any(keyword in upper for keyword in _RGPD_PDF_BOLD_KEYWORDS):
        return True
    if not any(ch.isalpha() for ch in stripped):
        return False
    # Título numerado em maiúsculas: "1. RESPONSÁVEL PELO TRATAMENTO"
    is_numbered_title = bool(re.match(r"^\d+\.\s+[A-ZÀ-Ü]", stripped))
    # Linha curta totalmente em maiúsculas SEM ser um par "Label: valor"
    # (ex.: "DECLARAÇÃO FINAL:" sim; "NIF: 515657514" não).
    is_short_caps_title = (
        stripped.isupper()
        and len(stripped) < 80
        and (":" not in stripped or stripped.endswith(":"))
    )
    return is_numbered_title or is_short_caps_title


def _wrap_plain_text_as_html(text: str) -> str:
    """PACOTE FR-2 — Converte texto simples (ex.: `RGPD_DEFAULT_TEMPLATE`)
    num fragmento HTML real, para que passe pela MESMA pipeline
    HTML→Flowables usada para o conteúdo rico do SmartRichEditor:

    - Parágrafos separados por linha vazia → `<p>`.
    - Quebras de linha dentro de um parágrafo → `<br/>` reais.
    - Títulos de secção / termos-chave RGPD (ver `_is_section_heading`)
      → `<strong>`.

    Substitui o antigo fallback que tratava cada linha como um parágrafo
    isolado, sem qualquer negrito nos títulos.
    """
    if not text:
        return ""
    paragraphs = re.split(r"\n\s*\n", text.strip())
    html_paragraphs = []
    for para in paragraphs:
        rendered_lines = []
        for raw_line in para.split("\n"):
            stripped = raw_line.strip()
            if not stripped:
                continue
            escaped = _escape_xml(stripped)
            if _is_section_heading(stripped):
                escaped = f"<strong>{escaped}</strong>"
            rendered_lines.append(escaped)
        if rendered_lines:
            html_paragraphs.append(f"<p>{'<br/>'.join(rendered_lines)}</p>")
    return "".join(html_paragraphs)


# ---------------------------------------------------------------------------
# PACOTE DG — Consenso A/B/C/D — descrições (sem pré-marcar).
# Adaptado das descrições hardcoded em `_build_rgpd_pdf` (rgpd_service.py
# linhas 911-925) mas com acentos PT correctos (a fonte DejaVuSans suporta).
# ---------------------------------------------------------------------------
CONSENT_OPTIONS_DG = [
    (
        "A",
        "Autorizo o tratamento dos meus dados pessoais para a análise da "
        "minha simulação de crédito habitação.",
    ),
    (
        "B",
        "Autorizo a comunicação dos meus dados pessoais às instituições de "
        "crédito parceiras para proposta de financiamento.",
    ),
    (
        "C",
        "Autorizo o envio de comunicações comerciais sobre produtos de "
        "crédito habitação e seguros.",
    ),
    (
        "D",
        "Autorizo a conservação dos meus dados pelo período estritamente "
        "necessário à execução do processo de crédito.",
    ),
]


# ---------------------------------------------------------------------------
# PACOTE DI — _html_to_flowables
#
# Converte HTML (produzido pelo SmartRichEditor/ReactQuill na admin) em
# Flowables do reportlab. Antes deste helper, o `_build_prefilled_rgpd_pdf`
# fazia `_escape_xml(line)` que ESCAPAVA todas as tags (`<p>` virava
# `&lt;p&gt;`) — o user via o markup literal no PDF e a formatação era
# perdida. Agora:
#   - `<p>` → Paragraph (um por tag)
#   - `<h1>`-`<h6>` → Paragraph com header style (font maior, bold)
#   - `<ul>`/`<ol>` → ListFlowable com ListItem por `<li>`
#   - `<strong>`/`<b>` → `<b>` (reportlab nativo)
#   - `<em>`/`<i>` → `<i>`
#   - `<u>` → `<u>`
#   - `<br>` standalone → Spacer
#   - `<div>`/`<span>` → recurse into children
#   - texto nu (sem wrapper) → Paragraph com body style
# Sanitiza com `bleach.clean` (defesa em profundidade — remove `<script>`,
# `on*` attributes, etc). PACOTE FR-2 — quando o texto NÃO contém tags
# HTML (ex.: `RGPD_DEFAULT_TEMPLATE`, que é plain-text), é primeiro
# convertido em HTML real via `_wrap_plain_text_as_html` (ver
# `_html_to_flowables`) para passar pela mesma pipeline; `_pacote_di_
# plain_text_to_flowables` fica apenas como fallback de última linha se o
# parse `lxml` falhar.
# ---------------------------------------------------------------------------
def _pacote_di_serialize_inline(el) -> str:
    """Serializa o conteúdo inline de um elemento lxml para uma string
    HTML compatível com reportlab Paragraph (<b>, <i>, <u>, <br/>)."""
    if el is None:
        return ""
    parts = []
    if el.text:
        parts.append(_escape_xml(el.text))
    for child in el.iterchildren():
        # Ignorar comentários / PI (tag não-str)
        if not isinstance(getattr(child, "tag", None), str):
            if getattr(child, "tail", None):
                parts.append(_escape_xml(child.tail))
            continue
        tag = child.tag.lower()
        inner = _pacote_di_serialize_inline(child)
        if tag in ("strong", "b"):
            parts.append(f"<b>{inner}</b>")
        elif tag in ("em", "i"):
            parts.append(f"<i>{inner}</i>")
        elif tag == "u":
            parts.append(f"<u>{inner}</u>")
        elif tag == "br":
            parts.append("<br/>")
        elif tag in ("p", "div"):
            # Block dentro de inline — insere quebra
            parts.append(inner)
            parts.append("<br/>")
        else:
            # span, li, etc — conteúdo inline sem wrapper
            parts.append(inner)
        if getattr(child, "tail", None):
            parts.append(_escape_xml(child.tail))
    return "".join(parts)


def _pacote_di_process_node(
    el,
    body_style,
    section_style,
    header_styles,
):
    """Processa um elemento lxml e devolve uma lista de Flowables.

    Args:
        el: elemento lxml (lxml.html.HtmlElement).
        body_style: ParagraphStyle para texto normal.
        section_style: ParagraphStyle para secções.
        header_styles: dict {h1: style, h2: style, ...} para headers.
    """
    from reportlab.platypus import Paragraph, Spacer, ListFlowable, ListItem
    from reportlab.lib.units import cm

    flowables = []
    if el is None:
        return flowables

    # Ignorar comentários / PI (tag não-str)
    if not isinstance(getattr(el, "tag", None), str):
        return flowables

    tag = el.tag.lower()

    if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
        text = _pacote_di_serialize_inline(el)
        if text.strip():
            style = header_styles.get(tag, section_style)
            # PACOTE FR-2 — títulos de secção (<h1>-<h6>) saem SEMPRE a
            # negrito, mesmo que o HTML de origem não tenha <strong>/<b>
            # explícito.
            if "<b>" not in text:
                text = f"<b>{text}</b>"
            flowables.append(Paragraph(text, style))
    elif tag == "p":
        text = _pacote_di_serialize_inline(el)
        if text.strip():
            # PACOTE FR-2 — parágrafos cujo texto completo corresponde a um
            # título de secção / termo-chave RGPD (ex.: "RESPONSÁVEL PELO
            # TRATAMENTO") saem a negrito mesmo sem `<strong>` explícito.
            plain_text = re.sub(r"<[^>]+>", "", text).strip()
            if "<b>" not in text and _is_section_heading(plain_text):
                text = f"<b>{text}</b>"
            flowables.append(Paragraph(text, body_style))
        else:
            flowables.append(Spacer(1, 0.15 * cm))
    elif tag == "br":
        flowables.append(Spacer(1, 0.25 * cm))
    elif tag in ("ul", "ol"):
        items = []
        for li in el.iterchildren("li"):
            li_text = _pacote_di_serialize_inline(li)
            if li_text.strip():
                items.append(
                    ListItem(Paragraph(li_text, body_style))
                )
        if items:
            if tag == "ol":
                flowables.append(
                    ListFlowable(
                        items,
                        bulletType="1",
                        leftIndent=18,
                        bulletFontName=body_style.fontName,
                        bulletFontSize=body_style.fontSize,
                    )
                )
            else:
                # PACOTE DL — <ul> usa ☐ (U+2610 BALLOT BOX) como bullet
                # em vez do bullet padrão (• que é um círculo preenchido).
                # Isto garante que os bullets são quadrados vazios para
                # assinatura manual, consistentes com as checkboxes de consentimento.
                font_name = body_style.fontName
                # Se DejaVuSans não está registada, usar ASCII "[ ]" como fallback
                if _FONT_REGISTERED:
                    bullet_char = "\u2610"  # ☐
                    flowables.append(
                        ListFlowable(
                            items,
                            bulletType="bullet",
                            start=bullet_char,
                            leftIndent=18,
                            bulletFontName=font_name,
                            bulletFontSize=body_style.fontSize,
                        )
                    )
                else:
                    # PACOTE DL — fallback ASCII: prefixar cada item com [ ] manualmente
                    for item in items:
                        # O ListItem já tem um Paragraph dentro; em vez de ListFlowable,
                        # criar Paragraphs directos com prefixo [ ]
                        pass  # ListFlowable abaixo com start='square' que é menos pior
                    flowables.append(
                        ListFlowable(
                            items,
                            bulletType="bullet",
                            leftIndent=18,
                            bulletFontName=font_name,
                            bulletFontSize=body_style.fontSize,
                        )
                    )
    elif tag in ("div", "span"):
        # Block container — recurse into children
        if el.text and el.text.strip():
            flowables.append(
                Paragraph(_escape_xml(el.text.strip()), body_style)
            )
        for child in el.iterchildren():
            flowables.extend(
                _pacote_di_process_node(
                    child, body_style, section_style, header_styles
                )
            )
    else:
        # Tag desconhecida — tentar como Paragraph com conteúdo inline
        text = _pacote_di_serialize_inline(el)
        if text.strip():
            flowables.append(Paragraph(text, body_style))
    return flowables


def _pacote_di_plain_text_to_flowables(text, body_style, section_style):
    """Fallback plain-text: split por \\n (backward-compat com o
    comportamento anterior — `RGPD_DEFAULT_TEMPLATE` é plain-text)."""
    from reportlab.platypus import Paragraph, Spacer
    from reportlab.lib.units import cm

    flowables = []
    for line in text.split("\n"):
        line_stripped = line.strip()
        if not line_stripped:
            flowables.append(Spacer(1, 0.25 * cm))
            continue
        is_header = (
            line_stripped[0].isdigit() and "." in line_stripped[:4]
        ) or (line_stripped.isupper() and len(line_stripped) < 80)
        style = section_style if is_header else body_style
        flowables.append(Paragraph(_escape_xml(line_stripped), style))
    return flowables


def _html_to_flowables(html_text, styles, font_name, line_height_ratio=1.5):
    """PACOTE DI — Converte HTML (SmartRichEditor) em Flowables reportlab.

    Args:
        html_text: String HTML ou plain-text.
        styles: dict com chaves ``body``, ``section`` e ``headers``
            (dict ``{h1: style, ...}``).
        font_name: Nome da fonte registada (ex.: ``DejaVuSans``) para
            criar header styles em falta.
        line_height_ratio: PACOTE FR-2 — rácio "line-height" (lido do
            cabeçalho `<style>` via `_parse_css_line_height`) usado para
            calcular o "leading" dos títulos `<h1>`-`<h6>` criados aqui.

    Returns:
        Lista de Flowables do reportlab.
    """
    from reportlab.lib.styles import ParagraphStyle

    if not html_text:
        return []

    text_str = html_text if isinstance(html_text, str) else str(html_text)
    body_style = styles.get("body")
    section_style = styles.get("section") or body_style
    raw_headers = styles.get("headers") or {}

    # Garantir header styles h1-h6 (criar se em falta)
    header_sizes = {"h1": 14, "h2": 13, "h3": 12, "h4": 11, "h5": 10, "h6": 10}
    header_styles = {}
    for level, size in header_sizes.items():
        header_styles[level] = raw_headers.get(level) or ParagraphStyle(
            f"PacoteDI_{level}",
            parent=body_style,
            fontName=font_name,
            fontSize=size,
            leading=round(size * line_height_ratio, 1),
            spaceBefore=8,
            spaceAfter=4,
        )

    # PACOTE FR-2 — Detetar se contém tags HTML. Se não, converte o texto
    # simples num fragmento HTML real (`<p>`/`<br>`/`<strong>`) para que
    # passe pela MESMA pipeline de conversão do HTML rico — em vez do
    # antigo fallback linha-a-linha sem negrito nos títulos de secção.
    if "<" not in text_str or ">" not in text_str:
        text_str = _wrap_plain_text_as_html(text_str)
        if not text_str:
            return []

    # PACOTE DI — Sanitizar com bleach (defesa em profundidade)
    try:
        cleaned = bleach.clean(
            text_str,
            tags=_PACOTE_DI_ALLOWED_TAGS,
            attributes={},
            strip=True,
        )
    except Exception as clean_err:
        logger.warning(
            "[PACOTE DI] bleach.clean falhou (%s) — a usar texto bruto",
            clean_err,
        )
        cleaned = text_str

    # PACOTE DI — Parse com lxml.html. Wrap num <div> para garantir
    # root único (lxml.html.fromstring falha com fragments múltiplos).
    try:
        wrapped = f"<div>{cleaned}</div>"
        tree = lxml_html.fromstring(wrapped)
    except Exception as parse_err:
        logger.warning(
            "[PACOTE DI] lxml parse falhou (%s) — fallback plain-text",
            parse_err,
        )
        return _pacote_di_plain_text_to_flowables(
            text_str, body_style, section_style
        )

    flowables = []
    # tree é o <div> wrapper — iterar os filhos directos
    for el in tree.iterchildren():
        flowables.extend(
            _pacote_di_process_node(
                el, body_style, section_style, header_styles
            )
        )
    return flowables


def _build_signature_block(
    sig_style,
    body_style,
    avail_width_pt: float,
    margin_top_cm: float,
    sig_label: str = "Assinatura do Cliente",
) -> list:
    """PACOTE DP — Bloco de assinatura estruturado (reutilizável).

    Equivalente reportlab de um bloco HTML `<table>`/flexbox (ver
    `.signature-block` no CSS `_RGPD_PDF_HTML_STYLE`). Estrutura:

    1. "Local" e "Data" numa LINHA ISOLADA — tabela de 2 colunas sem
       bordos (Local à esquerda, Data à direita), nunca "coladas" à
       assinatura nem a outro texto;
    2. "Assinatura do Cliente" num BLOCO ABAIXO — etiqueta a negrito,
       margem superior generosa (margin-top: 40px lido do CSS — espaço
       físico para assinar à caneta) e linha visível de underscores.

    Args:
        sig_style: ParagraphStyle para Local/Data e etiqueta de assinatura.
        body_style: ParagraphStyle base (para a legenda sob a linha).
        avail_width_pt: Largura útil da página (pontos) para a tabela.
        margin_top_cm: Margem superior do bloco (cm), lida do CSS.
        sig_label: Etiqueta do bloco de assinatura.

    Returns:
        Lista de Flowables prontos a estender na story.
    """
    from reportlab.platypus import Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.units import cm
    from reportlab.lib.enums import TA_RIGHT
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.colors import HexColor

    flowables = []

    # (1) "Local e Data" — linha isolada (tabela 2 colunas, sem bordos)
    local_cell = Paragraph(f"Local: {_blank_line(35)}", sig_style)
    data_style = ParagraphStyle(
        "SigDateRight", parent=sig_style, alignment=TA_RIGHT
    )
    data_cell = Paragraph("Data: ___/___/______", data_style)
    local_date_table = Table(
        [[local_cell, data_cell]],
        colWidths=[avail_width_pt * 0.62, avail_width_pt * 0.38],
    )
    local_date_table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    flowables.append(local_date_table)

    # (2) "Assinatura do Cliente" — bloco abaixo: margem superior
    # (40px lida do CSS — espaço físico para assinar) + linha visível.
    flowables.append(Spacer(1, 0.6 * cm))
    flowables.append(Paragraph(f"<b>{_escape_xml(sig_label)}:</b>", sig_style))
    flowables.append(Spacer(1, margin_top_cm * cm))
    flowables.append(Paragraph(_blank_line(45), sig_style))
    flowables.append(
        Paragraph(
            "(Assinar à caneta)",
            ParagraphStyle(
                "SigCaption",
                parent=body_style,
                fontSize=8,
                textColor=HexColor("#666666"),
                spaceBefore=2,
            ),
        )
    )
    return flowables


def _make_numbered_canvas_class(
    font_name: str,
    x_left: float,
    x_right: float,
    y_footer: float,
    doc_title: str,
):
    """PACOTE DP — Fábrica do canvas com rodapé corporativo numerado.

    O total de páginas só é conhecido no fim — usa-se o padrão canónico
    NumberedCanvas do reportlab: o estado de cada página é guardado em
    showPage() e o rodapé é desenhado no save(), quando o total já é
    conhecido. Régua fina + identificação do documento (esq.) +
    numeração "Página X de Y" (dir.), abaixo da área de conteúdo
    (margem inferior).

    Args:
        font_name: Nome da fonte registada (DejaVuSans ou Helvetica).
        x_left: Coordenada x da margem esquerda (pontos).
        x_right: Coordenada x da margem direita (pontos).
        y_footer: Baseline do rodapé (pontos, a partir do fundo).
        doc_title: Identificação do documento no rodapé (esquerda).

    Returns:
        Classe canvas a passar como `canvasmaker` ao `doc.build`.
    """
    from reportlab.pdfgen import canvas as pdfgen_canvas
    from reportlab.lib.colors import HexColor

    class _NumberedCanvas(pdfgen_canvas.Canvas):
        """Canvas com rodapé corporativo e numeração de páginas."""

        def __init__(self, *args, **kwargs):
            pdfgen_canvas.Canvas.__init__(self, *args, **kwargs)
            self._saved_page_states = []

        def showPage(self):
            self._saved_page_states.append(dict(self.__dict__))
            self._startPage()

        def save(self):
            total = len(self._saved_page_states)
            for state in self._saved_page_states:
                self.__dict__.update(state)
                self._draw_footer(total)
                pdfgen_canvas.Canvas.showPage(self)
            pdfgen_canvas.Canvas.save(self)

        def _draw_footer(self, total: int):
            self.saveState()
            try:
                self.setLineWidth(0.4)
                self.setStrokeColor(HexColor("#BBBBBB"))
                self.line(x_left, y_footer + 11, x_right, y_footer + 11)
                self.setFont(font_name, 7)
                self.setFillColor(HexColor("#777777"))
                self.drawString(x_left, y_footer, doc_title)
                self.drawRightString(
                    x_right, y_footer, f"Página {self._pageNumber} de {total}"
                )
            finally:
                self.restoreState()

    return _NumberedCanvas


def _build_prefilled_rgpd_pdf(rgpd_text: str, minuta_text: str, consent_data: dict) -> bytes:
    """
    PACOTE DG — Builder de PDF RGPD pré-preenchido para assinatura manual.

    Usa `reportlab.platypus` (SimpleDocTemplate) para paginação automática.

    PACOTE DP — Design profissional e estrutura multi-página:
    - CSS embutido `_RGPD_PDF_HTML_STYLE` (fonte única de verdade):
      margens generosas (2,5cm), line-height 1,5 e família sans-serif
      limpa (Helvetica/Arial/DejaVuSans).
    - 3 partes fundamentais, cada uma a começar em página própria
      (equivalente reportlab de `page-break-after: always` — ver `.page`
      no CSS):
      * Parte 1 (pág. 1+) — Cabeçalho corporativo (título + subtítulo
        legal + régua dupla) e texto legal RGPD com os Dados do Cliente
        (secções "2. TITULAR DOS DADOS", "3. TIPO DE DOCUMENTO", etc.).
        Se o template for longo, flui naturalmente para páginas extra.
      * Parte 2 — Consentimentos (Autorizo/Não Autorizo) + bloco de
        assinatura. Começa SEMPRE em página própria.
      * Parte 3 — Minuta de Exclusividade + bloco de assinatura.
        Começa SEMPRE em página própria.
    - Bloco de assinatura estruturado (`_build_signature_block`):
      "Local" e "Data" numa linha isolada; "Assinatura do Cliente" num
      bloco abaixo com linha visível e margem superior de 40px (lida do
      CSS) para assinatura física à caneta.
    - Rodapé corporativo em todas as páginas (régua fina + título do
      documento + "Página X de Y") via NumberedCanvas.

    - Template dinâmico (`rgpd_text`) é respeitado (11 secções do admin).
    - Campos em falta → linhas em branco "_____".
    - Data e Local → linhas em branco.
    - Checkboxes → quadrados vazios ☐ (Unicode U+2610).

    Args:
        rgpd_text: Template RGPD já renderizado (placeholders substituídos).
        minuta_text: Template Minuta de Exclusividade já renderizado
            (PACOTE DI — adicionado para incluir a Minuta após o RGPD).
        consent_data: Dict com nome, contribuinte, etc. (não usado directamente
            aqui porque o `rgpd_text` já tem os placeholders substituídos —
            mantém-se no signature para paridade com `_build_rgpd_pdf`).

    Returns:
        Bytes do PDF gerado, ou ``b""`` se o reportlab não estiver disponível.
    """
    try:
        from reportlab.platypus import (
            SimpleDocTemplate,
            Paragraph,
            Spacer,
            HRFlowable,
            PageBreak,
        )
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import cm
        from reportlab.lib.enums import TA_JUSTIFY, TA_CENTER
        from reportlab.lib.colors import HexColor
    except ImportError:
        logger.error("PACOTE DG — reportlab não disponível")
        return b""

    _ensure_font()
    # PACOTE DP — DejaVuSans (sans-serif limpa, com suporte Unicode para
    # acentos PT + ☐ U+2610) é a fonte TTF efetivamente usada quando
    # disponível; Helvetica é o fallback. Ambas honram a família
    # "Helvetica, Arial, sans-serif" declarada no CSS.
    font_name = "DejaVuSans" if _FONT_REGISTERED else "Helvetica"

    # PACOTE FR-2/DP — margens, "line-height" e a margem superior do bloco
    # de assinatura vêm do cabeçalho HTML/CSS `_RGPD_PDF_HTML_STYLE` (fonte
    # única de verdade), em vez de valores hardcoded duplicados no CSS.
    margin_cm = _parse_css_margin_cm(_RGPD_PDF_HTML_STYLE)
    line_height_ratio = _parse_css_line_height(_RGPD_PDF_HTML_STYLE)
    sig_margin_top_cm = _parse_css_signature_margin_top_cm(_RGPD_PDF_HTML_STYLE)
    body_font_size = 9
    body_leading = round(body_font_size * line_height_ratio, 1)
    # Largura útil da página (A4 − margens laterais) para a tabela do bloco
    # de assinatura ("Local"/"Data").
    avail_width_pt = A4[0] - 2 * margin_cm * cm

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=margin_cm * cm,
        rightMargin=margin_cm * cm,
        topMargin=margin_cm * cm,
        bottomMargin=margin_cm * cm,
        title="RGPD — Autorização para Tratamento de Dados Pessoais",
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "Title",
        parent=styles["Title"],
        fontName=font_name,
        fontSize=14,
        alignment=TA_CENTER,
        spaceAfter=6,
    )
    # PACOTE DP — subtítulo legal do cabeçalho corporativo (discreto,
    # cinzento, centrado), logo abaixo do título principal.
    subtitle_style = ParagraphStyle(
        "Subtitle",
        parent=title_style,
        fontSize=10,
        textColor=HexColor("#555555"),
        spaceAfter=8,
    )
    body_style = ParagraphStyle(
        "Body",
        parent=styles["Normal"],
        fontName=font_name,
        fontSize=body_font_size,
        leading=body_leading,
        alignment=TA_JUSTIFY,
        spaceAfter=4,
    )
    section_style = ParagraphStyle(
        "Section",
        parent=body_style,
        fontName=font_name,
        fontSize=body_font_size,
        leading=body_leading,
        spaceBefore=6,
        spaceAfter=2,
    )
    consent_title_style = ParagraphStyle(
        "ConsentTitle",
        parent=body_style,
        fontName=font_name,
        fontSize=11,
        leading=round(11 * line_height_ratio, 1),
        spaceBefore=0,
        spaceAfter=4,
    )
    checkbox_style = ParagraphStyle(
        "Checkbox",
        parent=body_style,
        fontName=font_name,
        fontSize=body_font_size,
        leading=body_leading,
        leftIndent=20,
        spaceAfter=2,
    )
    sig_style = ParagraphStyle(
        "Sig",
        parent=body_style,
        fontName=font_name,
        fontSize=body_font_size,
        leading=body_leading,
        spaceBefore=10,
    )

    story = []

    # ==================================================================
    # PACOTE DP — PARTE 1: CABEÇALHO CORPORATIVO + DADOS DO CLIENTE
    # ==================================================================
    # Cabeçalho corporativo: título centrado, subtítulo legal e régua
    # dupla (grossa + fina) — o clássico "double rule" de documento
    # corporativo. O texto legal RGPD (que contém os Dados do Cliente
    # do titular — secções "2. TITULAR DOS DADOS" e
    # "3. TIPO DE DOCUMENTO DE IDENTIFICAÇÃO") segue na mesma página.
    story.append(
        Paragraph(
            "AUTORIZAÇÃO PARA TRATAMENTO DE DADOS PESSOAIS", title_style
        )
    )
    story.append(
        Paragraph("RGPD — Regulamento (UE) 2016/679", subtitle_style)
    )
    story.append(Spacer(1, 0.1 * cm))
    story.append(
        HRFlowable(width="100%", thickness=1.4, color=HexColor("#333333"))
    )
    story.append(
        HRFlowable(width="100%", thickness=0.4, color=HexColor("#333333"))
    )
    story.append(Spacer(1, 0.5 * cm))

    # 2. Renderizar o template dinâmico (respeita edição do admin)
    # O `rgpd_text` já tem placeholders substituídos por `_get_rendered_rgpd_text`.
    # PACOTE DI — o conteúdo é HTML (vindo do SmartRichEditor/ReactQuill).
    # O helper `_html_to_flowables` faz parse com `lxml.html` + sanitiza com
    # `bleach.clean` e converte `<p>`/`<ul>`/`<strong>`/etc. em Flowables.
    # PACOTE FR-2 — se o texto NÃO contiver tags HTML (ex.:
    # `RGPD_DEFAULT_TEMPLATE`, que é plain-text), é primeiro convertido em
    # HTML real (`<p>`/`<br>`/`<strong>`) pelo próprio `_html_to_flowables`,
    # garantindo negrito consistente nos títulos de secção.
    if rgpd_text:
        rgpd_styles = {
            "body": body_style,
            "section": section_style,
            "headers": {},  # _html_to_flowables cria header styles via font_name
        }
        rgpd_flowables = _html_to_flowables(
            rgpd_text, rgpd_styles, font_name, line_height_ratio
        )
        story.extend(rgpd_flowables)

    # ==================================================================
    # PACOTE DP — PARTE 2: CONSENTIMENTOS (página própria)
    # ==================================================================
    # Equivalente reportlab do CSS `page-break-after: always` (ver
    # `.page` em `_RGPD_PDF_HTML_STYLE`): a secção de consentimentos
    # NUNCA partilha página com o texto legal — começa sempre numa
    # página nova, isolada.
    story.append(PageBreak())

    # 3. Opções de consentimento A/B/C/D com checkboxes VAZIAS
    story.append(Paragraph("<b>CONSENTIMENTO</b>", consent_title_style))
    story.append(
        HRFlowable(
            width="30%",
            thickness=0.5,
            color=HexColor("#333333"),
            hAlign="LEFT",
        )
    )
    story.append(Spacer(1, 0.25 * cm))

    # PACOTE DL — ☐ = &#9744; (Unicode U+2610 BALLOT BOX). Vazio, NÃO pré-marcado.
    # PACOTE DL — se DejaVuSans não está registada, usar fallback ASCII [ ]
    # para evitar que ☐ renderize como quadrado preto (glyph .notdef do Helvetica).
    checkbox_char = "&#9744;" if _FONT_REGISTERED else "[ &nbsp; ]"
    for letter, description in CONSENT_OPTIONS_DG:
        story.append(
            Paragraph(
                f"<b>{letter})</b> {_escape_xml(description)}", body_style
            )
        )
        checkbox_line = (
            f"{checkbox_char} Autorizo &nbsp;&nbsp;&nbsp;&nbsp; "
            f"{checkbox_char} Não Autorizo"
        )
        story.append(Paragraph(checkbox_line, checkbox_style))
        story.append(Spacer(1, 0.3 * cm))

    # 4. PACOTE DP — Bloco de assinatura estruturado (ver
    # `_build_signature_block`): "Local" e "Data" numa LINHA ISOLADA e
    # "Assinatura do Cliente" num bloco abaixo, com linha visível e
    # margem superior (margin-top: 40px do CSS) para assinatura física.
    story.extend(
        _build_signature_block(
            sig_style=sig_style,
            body_style=body_style,
            avail_width_pt=avail_width_pt,
            margin_top_cm=sig_margin_top_cm,
        )
    )

    # ------------------------------------------------------------------
    # PACOTE DI — Minuta de Exclusividade (nova página, mesmo PDF)
    # ------------------------------------------------------------------
    # Após a assinatura do RGPD, insere-se uma quebra de página e a
    # Minuta de Exclusividade. O `minuta_text` é HTML (vindo do
    # SmartRichEditor/ReactQuill) — usa-se o mesmo helper `_html_to_flowables`.
    # PACOTE DP — PARTE 3: começa sempre em página própria (page-break
    # após os consentimentos) e usa o MESMO bloco de assinatura
    # estruturado (`_build_signature_block`) — helper partilhado.
    # ------------------------------------------------------------------
    if minuta_text:
        story.append(PageBreak())
        story.append(Paragraph("MINUTA DE EXCLUSIVIDADE", title_style))
        story.append(
            HRFlowable(width="100%", thickness=1.4, color=HexColor("#333333"))
        )
        story.append(
            HRFlowable(width="100%", thickness=0.4, color=HexColor("#333333"))
        )
        story.append(Spacer(1, 0.4 * cm))
        # Renderizar o texto da Minuta (mesma abordagem HTML→Flowables)
        minuta_styles = {
            "body": body_style,
            "section": section_style,
            "headers": {},
        }
        minuta_flowables = _html_to_flowables(
            minuta_text, minuta_styles, font_name, line_height_ratio
        )
        story.extend(minuta_flowables)
        # PACOTE DP — bloco de assinatura estruturado (mesma estrutura da
        # página de consentimentos — helper partilhado).
        story.extend(
            _build_signature_block(
                sig_style=sig_style,
                body_style=body_style,
                avail_width_pt=avail_width_pt,
                margin_top_cm=sig_margin_top_cm,
            )
        )

    # ------------------------------------------------------------------
    # PACOTE DP — Rodapé corporativo com numeração ("Página X de Y")
    # ------------------------------------------------------------------
    # Fábrica de canvas (padrão NumberedCanvas — ver docstring do helper):
    # régua fina + identificação do documento + numeração em todas as
    # páginas, abaixo da área de conteúdo (margem inferior de 2,5cm).
    numbered_canvas = _make_numbered_canvas_class(
        font_name=font_name,
        x_left=margin_cm * cm,
        x_right=A4[0] - margin_cm * cm,
        y_footer=1.3 * cm,
        doc_title="RGPD — Autorização para Tratamento de Dados Pessoais",
    )

    doc.build(story, canvasmaker=numbered_canvas)
    return buffer.getvalue()


async def run_generate_prefilled_rgpd_pdf(
    process_id: str,
    user: dict,
) -> tuple[bytes, str]:
    """
    Gera um PDF RGPD PRÉ-PREENCHIDO com os dados reais do cliente/processo.

    PACOTE DG — usa o novo builder `_build_prefilled_rgpd_pdf` (platypus)
    em vez do `_generate_rgpd_pdf_bytes` (Canvas low-level). Ver module
    docstring para detalhes das 5 correcções.

    Fluxo:
    1. Busca o processo em `db.processes` (404 se não existir / eliminado).
    2. Desencripta campos sensíveis via `decrypt_sensitive_data`.
    3. Monta `consent_data` sintético com Nome, NIF, documento, morada —
       faz fallback para linhas em branco "_____" quando os campos não
       existem (para preenchimento manual). A `data_assinatura` fica como
       `"___/___/______"` (não pré-preenchida).
    4. Renderiza o template RGPD ativo (`_get_rendered_rgpd_text`) — os
       placeholders `{{...}}` são substituídos pelos valores do cliente
       (ou pelas linhas em branco).
    5. Gera o PDF A4 (`_build_prefilled_rgpd_pdf`) via platypus.
    6. Regista atividade de auditoria no processo (`_add_process_activity`).
    7. Devolve `(pdf_bytes, safe_filename)` para o route devolver como
       `StreamingResponse`.

    Args:
        process_id: ID do processo (string UUID).
        user: Dict do utilizador autenticado (com `id` e `name`).

    Returns:
        Tuplo `(pdf_bytes, filename)` onde `pdf_bytes` é o PDF em bytes e
        `filename` é o nome seguro para o header `Content-Disposition`.

    Raises:
        HTTPException: 404 se o processo não for encontrado; 500 se a geração
        do PDF falhar.
    """
    # 1. Buscar o processo (exclui eliminados)
    process = await db.processes.find_one(
        {"id": process_id, "is_deleted": {"$ne": True}},
        {"_id": 0},
    )
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")

    # 2. Desencriptar campos sensíveis (NIF, morada, documento, etc.)
    process = decrypt_sensitive_data(process)

    # 3. Montar consent_data sintético a partir dos dados do processo
    personal = process.get("personal_data") or {}
    real_estate = process.get("real_estate_data") or {}
    doc_id = personal.get("documento_id") or {}
    if isinstance(doc_id, dict):
        doc_type = doc_id.get("type", "") or ""
        doc_number = doc_id.get("number", "") or ""
    else:
        doc_type, doc_number = "", str(doc_id or "")

    # PACOTE DG — campos em falta → linhas em branco (para caneta)
    consent_data = {
        "nome": (
            process.get("client_name")
            or personal.get("nome")
            or personal.get("nome_completo")
            or _blank_line(50)
        ),
        "contribuinte": personal.get("nif") or _blank_line(15),
        "tipo_documento": doc_type or "",
        "numero_documento": doc_number or _blank_line(20),
        "validade_documento": (
            personal.get("data_validade_cc") or _blank_line(15)
        ),
        "morada": (
            personal.get("morada_fiscal")
            or personal.get("morada")
            or _blank_line(60)
        ),
        "localidade": real_estate.get("localidade") or _blank_line(25),
        "concelho": real_estate.get("concelho") or _blank_line(20),
        "codigo_postal": real_estate.get("codigo_postal") or _blank_line(10),
        # PACOTE DG — Data em branco para assinatura manual
        "data_assinatura": "___/___/______",
    }

    # 4 + 5. Renderizar template + gerar PDF (platypus).
    # PACOTE DG — substitui `_generate_rgpd_pdf_bytes` (que chamava o
    # builder Canvas `_build_rgpd_pdf` com texto hardcoded) pelo novo
    # `_build_prefilled_rgpd_pdf` que respeita o `rgpd_text` dinâmico.
    try:
        rgpd_text = await _get_rendered_rgpd_text(
            process_id, {}, consent_data
        )
        # PACOTE DI — buscar Minuta de Exclusividade (mesmo padrão do
        # `_get_rendered_rgpd_text`). Se falhar, fallback a string vazia
        # (o PDF é gerado só com o RGPD — não bloqueia o download).
        minuta_text = ""
        try:
            minuta_text = await _get_rendered_minuta_text(
                process_id, {}, consent_data
            )
        except Exception as minuta_err:
            logger.warning(
                "[PACOTE DI] Erro ao buscar Minuta para processo %s: %s",
                process_id,
                minuta_err,
            )
        pdf_bytes = _build_prefilled_rgpd_pdf(
            rgpd_text, minuta_text, consent_data
        )
    except Exception as exc:
        logger.error(
            "[RGPD-PDF] Erro ao gerar PDF pré-preenchido para processo %s: %s",
            process_id,
            exc,
            exc_info=True,
        )
        raise HTTPException(
            status_code=500,
            detail="Erro ao gerar o PDF RGPD pré-preenchido",
        )

    if not pdf_bytes:
        raise HTTPException(
            status_code=500,
            detail="PDF RGPD gerado está vazio (reportlab indisponível?)",
        )

    # 6. Nome seguro do ficheiro (apenas [a-zA-Z0-9_-])
    safe_name = re.sub(
        r"[^a-zA-Z0-9_-]",
        "_",
        process.get("client_name") or "cliente",
    )[:50]
    filename = f"RGPD_{safe_name}.pdf"

    # 7. Auditoria — não falha o download se o registo falhar
    try:
        await _add_process_activity(
            process_id,
            user.get("id", "system"),
            user.get("name", "Sistema"),
            "RGPD pré-preenchido descarregado pelo utilizador",
            details=(
                f"PDF gerado com dados do cliente "
                f"({consent_data.get('nome') or 'N/A'}). "
                f"Destinado a impressão e assinatura manual."
            ),
        )
    except Exception as exc:
        logger.warning(
            "[RGPD-PDF] Atividade de auditoria não registada para %s: %s",
            process_id,
            exc,
        )

    return pdf_bytes, filename

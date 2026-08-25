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
  body {
    margin: 2cm;
    text-align: justify;
    line-height: 1.5;
  }
  h1, h2, h3, h4, h5, h6, .section-title, strong, b {
    font-weight: bold;
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
    """Lê o valor de `margin` do cabeçalho `<style>` (px/cm/mm/in) e
    devolve-o em centímetros, para usar como margem lateral do PDF."""
    match = re.search(
        r"margin\s*:\s*(\d+(?:\.\d+)?)\s*(px|cm|mm|in)?", css, re.IGNORECASE
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


def _build_prefilled_rgpd_pdf(rgpd_text: str, minuta_text: str, consent_data: dict) -> bytes:
    """
    PACOTE DG — Novo builder de PDF RGPD pré-preenchido para assinatura manual.

    Usa `reportlab.platypus` (SimpleDocTemplate) para paginação automática.

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
        )
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import cm
        from reportlab.lib.enums import TA_JUSTIFY, TA_CENTER, TA_LEFT
        from reportlab.lib.colors import HexColor, black
    except ImportError:
        logger.error("PACOTE DG — reportlab não disponível")
        return b""

    _ensure_font()
    font_name = "DejaVuSans" if _FONT_REGISTERED else "Helvetica"

    # PACOTE FR-2 — margens e "line-height" vêm do cabeçalho HTML/CSS
    # `_RGPD_PDF_HTML_STYLE` (fonte única de verdade), em vez de valores
    # hardcoded duplicados aqui e no CSS.
    margin_cm = _parse_css_margin_cm(_RGPD_PDF_HTML_STYLE)
    line_height_ratio = _parse_css_line_height(_RGPD_PDF_HTML_STYLE)
    body_font_size = 9
    body_leading = round(body_font_size * line_height_ratio, 1)

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
        fontSize=body_font_size,
        leading=body_leading,
        spaceBefore=8,
        spaceAfter=2,
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

    # 1. Título
    story.append(
        Paragraph(
            "AUTORIZAÇÃO PARA TRATAMENTO DE DADOS PESSOAIS", title_style
        )
    )
    story.append(
        Paragraph(
            "RGPD — Regulamento (UE) 2016/679",
            ParagraphStyle(
                "Subtitle", parent=title_style, fontSize=10, spaceAfter=8
            ),
        )
    )
    story.append(
        HRFlowable(width="100%", thickness=0.5, color=HexColor("#333333"))
    )
    story.append(Spacer(1, 0.4 * cm))

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

    story.append(Spacer(1, 0.6 * cm))
    story.append(
        HRFlowable(width="100%", thickness=0.5, color=HexColor("#333333"))
    )
    story.append(Spacer(1, 0.3 * cm))

    # 3. Opções de consentimento A/B/C/D com checkboxes VAZIAS
    story.append(Paragraph("<b>CONSENTIMENTO</b>", consent_title_style))
    story.append(Spacer(1, 0.2 * cm))

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

    # 4. Secção de assinatura — LOCAL e DATA em branco (assinatura manual)
    story.append(Spacer(1, 0.5 * cm))
    story.append(
        Paragraph(
            f"Local: {_blank_line(35)} &nbsp;&nbsp;&nbsp; "
            f"Data: ___/___/______",
            sig_style,
        )
    )
    story.append(Spacer(1, 1 * cm))

    # Linha de assinatura
    story.append(
        Paragraph("Assinatura do Titular dos Dados:", sig_style)
    )
    story.append(Spacer(1, 0.8 * cm))
    story.append(
        HRFlowable(width="60%", thickness=0.5, color=black, hAlign="LEFT")
    )
    story.append(
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

    # ------------------------------------------------------------------
    # PACOTE DI — Minuta de Exclusividade (nova página, mesmo PDF)
    # ------------------------------------------------------------------
    # Após a assinatura do RGPD, insere-se uma quebra de página e a
    # Minuta de Exclusividade. O `minuta_text` é HTML (vindo do
    # SmartRichEditor/ReactQuill) — usa-se o mesmo helper `_html_to_flowables`.
    # ------------------------------------------------------------------
    if minuta_text:
        from reportlab.platypus import PageBreak
        # PACOTE DI — Minuta de Exclusividade (nova página)
        story.append(PageBreak())
        story.append(Paragraph("MINUTA DE EXCLUSIVIDADE", title_style))
        story.append(
            HRFlowable(width="100%", thickness=0.5, color=HexColor("#333333"))
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
        # Secção de assinatura da Minuta
        story.append(Spacer(1, 0.5 * cm))
        story.append(
            Paragraph(
                f"Local: {_blank_line(35)} &nbsp;&nbsp;&nbsp; "
                f"Data: ___/___/______",
                sig_style,
            )
        )
        story.append(Spacer(1, 1 * cm))
        story.append(
            Paragraph("Assinatura do Titular dos Dados:", sig_style)
        )
        story.append(Spacer(1, 0.8 * cm))
        story.append(
            HRFlowable(width="60%", thickness=0.5, color=black, hAlign="LEFT")
        )
        story.append(
            Paragraph(
                "(Assinar à caneta)",
                ParagraphStyle(
                    "MinutaSigCaption",
                    parent=body_style,
                    fontSize=8,
                    textColor=HexColor("#666666"),
                    spaceBefore=2,
                ),
            )
        )

    doc.build(story)
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

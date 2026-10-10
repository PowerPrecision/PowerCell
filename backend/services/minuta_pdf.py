"""PDF da Minuta de Exclusividade assinada (Bloco 5, ponto 36).

PORQUÊ ESTE MÓDULO
==================
Havia DOIS renderizadores da minuta, e só um sabia ler o texto:

* o do PDF pré-preenchido (`rgpd_pdf._build_prefilled_rgpd_pdf`) converte o HTML
  do editor rico em parágrafos, negrito, listas e alinhamento;
* o da minuta **assinada**, gerada automaticamente quando o cliente assina e
  anexada ao processo e ao email (`rgpd_service._build_minuta_pdf`), escrevia o
  texto com `canvas.drawString`, linha a linha. Daí a «perda de formatação»:

  - o HTML do template do administrador saía com as TAGS literais (`<p>…</p>`);
  - não havia negrito nem alinhamento (nem sequer o título do documento no
    corpo);
  - qualquer linha que ainda tivesse uma variável por resolver (`{{X}}`) era
    **descartada em silêncio** — e a minuta é, por omissão, um único
    parágrafo, pelo que a página saía só com o título e a assinatura;
  - a quebra de linha era uma estimativa por contagem de caracteres
    (`fonte × 0.48`), e as linhas de um parágrafo comprido seguiam para além da
    margem inferior da página (a pergunta «cabe?» só se fazia no fim do
    parágrafo);
  - a fonte era Helvetica: aspas e travessões tipográficos saíam como `?`.

Agora o texto passa pela MESMA pipeline do PDF pré-preenchido
(`rgpd_pdf._html_to_flowables`, DejaVu, paginação do platypus) e há um só sítio
que conhece a regra de uma minuta bem formada.

REGRAS
======
1. **Nada se descarta em silêncio**: uma variável por resolver passa a uma linha
   em branco (`__________`) e fica um aviso no log. Um documento legal com um
   parágrafo a menos não dá erro nenhum.
2. **O título é desenhado uma vez**: o template por omissão começa por «MINUTA DE
   EXCLUSIVIDADE» e o cabeçalho do PDF também.
3. **O texto do administrador nunca rebenta a geração**: se o HTML não converter,
   cai para texto simples — a minuta assinada tem de existir.
"""
from __future__ import annotations

import base64
import io
import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

TITULO = "MINUTA DE EXCLUSIVIDADE"
LINHA_EM_BRANCO = "__________"

_RE_VARIAVEL_POR_RESOLVER = re.compile(r"\{\{[^{}]*\}\}")

# O título repetido, em qualquer das formas em que o texto pode chegar:
# HTML (`<p><strong>MINUTA…</strong></p>`, `<h1>`…) ou texto simples (1.ª linha).
_RE_TITULO_HTML = re.compile(
    r"^\s*<(p|h[1-6]|div)\b[^>]*>\s*(?:<(?:strong|b|u|em|i|span)\b[^>]*>\s*)*"
    + re.escape(TITULO)
    + r"\s*(?:</(?:strong|b|u|em|i|span)>\s*)*</\1>\s*",
    re.IGNORECASE,
)
_RE_TITULO_TEXTO = re.compile(r"^\s*" + re.escape(TITULO) + r"\s*(?:\n|$)", re.IGNORECASE)


def sem_titulo_repetido(texto: Optional[str]) -> str:
    """Tira o título do início do texto: o cabeçalho do PDF já o desenha."""
    texto = texto or ""
    sem_html = _RE_TITULO_HTML.sub("", texto, count=1)
    if sem_html != texto:
        return sem_html
    return _RE_TITULO_TEXTO.sub("", texto, count=1)


def preencher_variaveis_em_falta(texto: Optional[str]) -> str:
    """Troca `{{VARIAVEL}}` ainda por resolver por uma linha em branco."""
    texto = texto or ""
    achadas = _RE_VARIAVEL_POR_RESOLVER.findall(texto)
    if achadas:
        logger.warning(
            "[MINUTA-PDF] %d variável(is) por resolver deixada(s) em branco: %s",
            len(achadas), ", ".join(sorted(set(achadas))),
        )
    return _RE_VARIAVEL_POR_RESOLVER.sub(LINHA_EM_BRANCO, texto)


def preparar_texto(texto: Optional[str]) -> str:
    """O texto pronto a converter: sem título repetido e sem variáveis soltas."""
    return preencher_variaveis_em_falta(sem_titulo_repetido(texto))


def _imagem_da_assinatura(consent_data: dict):
    """A assinatura manuscrita como `Image` platypus (máx. 8×4 cm), ou `None`."""
    from reportlab.lib.units import cm
    from reportlab.lib.utils import ImageReader
    from reportlab.platypus import Image

    bruto = (consent_data or {}).get("assinatura") or ""
    if "," not in bruto:
        return None
    try:
        dados = base64.b64decode(bruto.split(",", 1)[1])
        largura, altura = ImageReader(io.BytesIO(dados)).getSize()
        escala = min(1.0, (8 * cm) / largura, (4 * cm) / altura)
        return Image(io.BytesIO(dados), width=largura * escala, height=altura * escala, hAlign="LEFT")
    except Exception as exc:
        logger.warning("[MINUTA-PDF] Assinatura não incluída: %s", type(exc).__name__)
        return None


def build_signed_minuta_pdf(minuta_text: str, consent_data: dict) -> bytes:
    """A Minuta de Exclusividade assinada, em PDF (A4, rodapé «Página X de Y»).

    Devolve `b""` se o reportlab não estiver disponível (o chamador já trata
    esse caso: simplesmente não anexa a minuta).
    """
    try:
        from reportlab.lib.colors import HexColor
        from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.platypus import HRFlowable, KeepTogether, Paragraph, SimpleDocTemplate, Spacer
    except ImportError:
        logger.error("[MINUTA-PDF] reportlab não disponível")
        return b""

    from services import rgpd_pdf as base

    consent_data = consent_data or {}
    base._ensure_font()
    fonte = "DejaVuSans" if base._FONT_REGISTERED else "Helvetica"
    negrito = "DejaVuSans-Bold" if base._FONT_REGISTERED else "Helvetica-Bold"
    margem = 2.5 * cm

    corpo = ParagraphStyle(
        "MinutaCorpo", fontName=fonte, fontSize=10.5, leading=16, alignment=TA_JUSTIFY, spaceAfter=8,
    )
    titulo = ParagraphStyle(
        "MinutaTitulo", fontName=negrito, fontSize=14, leading=18, alignment=TA_CENTER, spaceAfter=6,
    )
    legenda = ParagraphStyle("MinutaLegenda", parent=corpo, fontSize=9, leading=12, alignment=0, spaceAfter=2)
    estilos = {"body": corpo, "section": corpo, "headers": {}}

    texto = preparar_texto(minuta_text)
    try:
        conteudo = base._html_to_flowables(texto, estilos, fonte, 1.5)
    except Exception as exc:  # o texto do administrador nunca impede a minuta
        logger.error("[MINUTA-PDF] Conversão do texto falhou (%s) — a usar texto simples", type(exc).__name__)
        simples = re.sub(r"<[^>]+>", "", texto)
        conteudo = base._pacote_di_plain_text_to_flowables(simples, corpo, corpo)

    historia = [
        Paragraph(TITULO, titulo),
        HRFlowable(width="100%", thickness=1.2, color=HexColor("#333333")),
        Spacer(1, 0.5 * cm),
        *conteudo,
        Spacer(1, 0.8 * cm),
    ]

    bloco = []
    localidade = (consent_data.get("localidade") or "").strip()
    data_assinatura = (consent_data.get("data_assinatura") or "").strip()
    if localidade and data_assinatura:
        so_data = data_assinatura.split(" ")[0]
        bloco.append(Paragraph(f"{base._escape_xml(localidade)}, {base._escape_xml(so_data)}", corpo))
    bloco.append(Paragraph("<b>Assinatura do Cliente</b>", corpo))
    bloco.append(Paragraph("Titular dos Dados", legenda))
    bloco.append(Paragraph("<i>Por favor assine conforme o seu cartão de identificação.</i>", legenda))
    imagem = _imagem_da_assinatura(consent_data)
    if imagem is not None:
        bloco.append(Spacer(1, 0.3 * cm))
        bloco.append(imagem)
    historia.append(KeepTogether(bloco))

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4, leftMargin=margem, rightMargin=margem, topMargin=margem, bottomMargin=margem,
        title="Minuta de Exclusividade",
    )
    canvas_numerado = base._make_numbered_canvas_class(
        font_name=fonte, x_left=margem, x_right=A4[0] - margem, y_footer=1.3 * cm,
        doc_title="Minuta de Exclusividade",
    )
    doc.build(historia, canvasmaker=canvas_numerado)
    return buffer.getvalue()

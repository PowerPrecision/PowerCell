"""PDF do relatório executivo (Bloco 4, ponto 16).

Compila os gráficos e as tabelas do Dashboard Executivo (ou do Relatório
Semanal) num PDF limpo. É GERADO NO SERVIDOR, a partir do MESMO relatório
que o ecrã mostra — nunca de uma captura do browser:

* os números do PDF e do ecrã não podem divergir (um PDF que discorda do
  ecrã que o originou é pior do que não ter PDF);
* gráficos feitos com `reportlab.graphics` são vectoriais, nítidos a
  imprimir, e não dependem do tamanho da janela de quem carrega no botão.

Reutiliza a infraestrutura do PDF RGPD/proposta (fonte DejaVu com
negrito, escape XML, rodapé numerado) e o branding da proposta financeira
(emissor, logótipo, cor de destaque). Degrada sem rebentar: sem logótipo,
sem fonte DejaVu ou sem branding, o PDF sai igual com os valores neutros.

`reportlab` é síncrono: quem chama corre isto num executor (ver
`executive_report_api`), nunca directamente no event loop.
"""
from __future__ import annotations

import io
import logging
from datetime import datetime
from typing import Any, Optional

logger = logging.getLogger(__name__)

TITULO = "Relatório Executivo — Desempenho da Equipa"
MAX_PESSOAS_NO_GRAFICO = 12
MAX_FASES_NO_GRAFICO = 10
MAX_MOVIMENTOS_NO_PDF = 40

ROTULOS_DOS_PAPEIS = {
    "consultor": "Consultor", "intermediario": "Intermediário",
    "administrativo": "Administrativo", "diretor": "Diretor",
    "ceo": "CEO", "admin": "Admin",
}

# Paleta validada para daltonismo (ΔE CVD ≥ 12 entre vizinhas, no claro e no
# escuro): o par vermelho/verde de antes falhava a verificação (ΔE 5).
COR_FASES = "#2563eb"  # azul
COR_CONCLUIDAS = "#0d9488"  # verde-azulado
COR_ATRASO = "#d97706"  # âmbar


def formatar_data(texto: Any) -> str:
    """`2026-10-05` / ISO completo → `05/10/2026`. Ilegível → o próprio texto."""
    bruto = str(texto or "")[:10]
    try:
        return datetime.strptime(bruto, "%Y-%m-%d").strftime("%d/%m/%Y")
    except ValueError:
        return str(texto or "—")


def _numero(valor: Any) -> str:
    """`None` (histórico desligado) é «—», nunca 0."""
    return "—" if valor is None else str(int(valor))


def _primeiro_nome(nome: Any) -> str:
    partes = str(nome or "").split()
    return partes[0] if partes else "—"


def linhas_da_tabela(relatorio: dict) -> list[list[str]]:
    """Cabeçalho + uma linha por pessoa. Pura (testável sem reportlab)."""
    linhas = [["Colaborador", "Perfil", "Fases alteradas", "Processos", "Concluídas", "Pendentes", "Em atraso"]]
    for u in relatorio.get("users") or []:
        linhas.append([
            str(u.get("name") or "—"),
            ROTULOS_DOS_PAPEIS.get(u.get("role"), str(u.get("role") or "—")),
            _numero(u.get("phase_changes")),
            _numero(u.get("processes_moved")),
            _numero(u.get("tasks_completed")),
            _numero(u.get("tasks_pending")),
            _numero(u.get("tasks_overdue")),
        ])
    return linhas


def dados_do_grafico_de_pessoas(relatorio: dict) -> tuple[list[str], list[list[int]]]:
    """Nomes e três séries (fases, concluídas, em atraso) das pessoas mais activas."""
    ordenadas = sorted(
        relatorio.get("users") or [],
        key=lambda u: -((u.get("phase_changes") or 0) + (u.get("tasks_completed") or 0)),
    )[:MAX_PESSOAS_NO_GRAFICO]
    nomes = [_primeiro_nome(u.get("name")) for u in ordenadas]
    return nomes, [
        [int(u.get("phase_changes") or 0) for u in ordenadas],
        [int(u.get("tasks_completed") or 0) for u in ordenadas],
        [int(u.get("tasks_overdue") or 0) for u in ordenadas],
    ]


def _grafico_de_barras(nomes, series, cores, fonte, largura, altura, horizontal=False):
    from reportlab.graphics.charts.barcharts import HorizontalBarChart, VerticalBarChart
    from reportlab.graphics.shapes import Drawing
    from reportlab.lib import colors

    desenho = Drawing(largura, altura)
    grafico = HorizontalBarChart() if horizontal else VerticalBarChart()
    grafico.x, grafico.y = 40, 28
    grafico.width, grafico.height = largura - 55, altura - 45
    grafico.data = series
    grafico.categoryAxis.categoryNames = nomes
    grafico.categoryAxis.labels.fontName = fonte
    grafico.categoryAxis.labels.fontSize = 7
    if not horizontal:
        grafico.categoryAxis.labels.angle = 0
        grafico.categoryAxis.labels.boxAnchor = "n"
        grafico.categoryAxis.labels.dy = -3
    grafico.valueAxis.labels.fontName = fonte
    grafico.valueAxis.labels.fontSize = 7
    grafico.valueAxis.valueMin = 0
    maximo = max((max(s) for s in series if s), default=0)
    grafico.valueAxis.valueMax = max(maximo + max(1, round(maximo * 0.15)), 4)
    grafico.valueAxis.visibleGrid = True
    grafico.valueAxis.gridStrokeColor = colors.HexColor("#E5E7EB")
    grafico.valueAxis.valueStep = max(1, round(grafico.valueAxis.valueMax / 5))
    grafico.barWidth = 6 if len(series) > 1 else 9
    grafico.groupSpacing = 6
    for indice, cor in enumerate(cores):
        grafico.bars[indice].fillColor = colors.HexColor(cor)
        grafico.bars[indice].strokeColor = None
    desenho.add(grafico)
    return desenho


def construir_pdf(
    relatorio: dict,
    *,
    empresa: Optional[dict] = None,
    logo_bytes: Optional[bytes] = None,
    accent: str = "#334155",
    gerado_por: str = "",
    titulo: str = TITULO,
    subtitulo: str = "",
) -> bytes:
    """Constrói o PDF. Síncrono — correr num executor."""
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_RIGHT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import (
        CondPageBreak, Image, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
    )

    from services import rgpd_pdf

    empresa = empresa or {}
    rgpd_pdf._ensure_font()
    fonte = "DejaVuSans" if rgpd_pdf._FONT_REGISTERED else "Helvetica"
    negrito = "DejaVuSans-Bold" if rgpd_pdf._FONT_REGISTERED else "Helvetica-Bold"
    esc = rgpd_pdf._escape_xml

    cor_destaque = colors.HexColor(accent)
    cinza = colors.HexColor("#6B7280")
    grelha = colors.HexColor("#D1D5DB")
    zebra = colors.HexColor("#F3F4F6")

    margem = 1.6 * cm
    largura_util = A4[0] - 2 * margem
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4, leftMargin=margem, rightMargin=margem,
        topMargin=1.4 * cm, bottomMargin=2.0 * cm,
        title=titulo, author=empresa.get("nome") or "",
    )

    base = getSampleStyleSheet()
    s_titulo = ParagraphStyle("ExecTitulo", parent=base["Title"], fontName=negrito,
                              fontSize=16, leading=20, textColor=cor_destaque, alignment=0, spaceAfter=2)
    s_sub = ParagraphStyle("ExecSub", parent=base["Normal"], fontName=fonte,
                           fontSize=9, leading=12, textColor=cinza)
    s_seccao = ParagraphStyle("ExecSeccao", parent=base["Heading2"], fontName=negrito,
                              fontSize=11, leading=14, textColor=cor_destaque, spaceBefore=12, spaceAfter=5)
    s_nota = ParagraphStyle("ExecNota", parent=base["Normal"], fontName=fonte,
                            fontSize=7.5, leading=10, textColor=cinza)
    s_celula = ParagraphStyle("ExecCelula", parent=base["Normal"], fontName=fonte, fontSize=8, leading=10)
    s_emissor = ParagraphStyle("ExecEmissor", parent=s_nota, alignment=TA_RIGHT)

    historia: list = []

    # ── Cabeçalho: logótipo + emissor ──────────────────────────────
    cabecalho_esq: Any = ""
    if logo_bytes:
        try:
            imagem = Image(io.BytesIO(logo_bytes))
            proporcao = imagem.imageWidth / float(imagem.imageHeight or 1)
            imagem.drawHeight = 1.2 * cm
            imagem.drawWidth = 1.2 * cm * proporcao
            cabecalho_esq = imagem
        except Exception as erro:  # logótipo inválido não impede o PDF
            logger.warning("[EXEC-PDF] Logótipo ignorado: %s", erro)
    linhas_emissor = [empresa.get("nome"), empresa.get("morada"), empresa.get("email")]
    emissor = Paragraph("<br/>".join(esc(l) for l in linhas_emissor if l), s_emissor)
    cabecalho = Table([[cabecalho_esq, emissor]], colWidths=[largura_util * 0.5, largura_util * 0.5])
    cabecalho.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                                   ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    historia += [cabecalho, Spacer(1, 6), Paragraph(esc(titulo), s_titulo)]

    periodo = f"{formatar_data(relatorio.get('start_date'))} — {formatar_data(relatorio.get('end_date'))}"
    historia.append(Paragraph(esc(f"Período: {periodo}" + (f" · {subtitulo}" if subtitulo else "")), s_sub))
    filtros = relatorio.get("filtros") or {}
    partes = []
    if filtros.get("user_ids"):
        partes.append(f"{len(filtros['user_ids'])} utilizador(es) seleccionado(s)")
    if filtros.get("papeis"):
        partes.append("perfis: " + ", ".join(ROTULOS_DOS_PAPEIS.get(p, p) for p in filtros["papeis"]))
    historia.append(Paragraph(esc("Filtros: " + ("; ".join(partes) if partes else "toda a equipa")), s_sub))
    historia.append(Spacer(1, 8))

    # ── Indicadores ───────────────────────────────────────────────
    resumo = relatorio.get("summary") or {}
    indicadores = [
        ("Fases alteradas", resumo.get("total_phase_changes")),
        ("Processos avançados", resumo.get("total_processes_moved")),
        ("Tarefas concluídas", resumo.get("total_tasks_completed")),
        ("Tarefas pendentes", resumo.get("total_tasks_pending")),
        ("Tarefas em atraso", resumo.get("total_tasks_overdue")),
    ]
    s_valor = ParagraphStyle("ExecValor", parent=s_celula, fontName=negrito, fontSize=15, leading=18, alignment=1)
    s_rotulo = ParagraphStyle("ExecRotulo", parent=s_nota, alignment=1)
    kpis = Table(
        [[Paragraph(str(int(v or 0)), s_valor) for _, v in indicadores],
         [Paragraph(esc(r), s_rotulo) for r, _ in indicadores]],
        colWidths=[largura_util / len(indicadores)] * len(indicadores),
    )
    kpis.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.5, grelha), ("INNERGRID", (0, 0), (-1, -1), 0.25, grelha),
                              ("BACKGROUND", (0, 0), (-1, -1), zebra), ("TOPPADDING", (0, 0), (-1, -1), 5),
                              ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    historia.append(kpis)

    # ── Gráficos ──────────────────────────────────────────────────
    nomes, series = dados_do_grafico_de_pessoas(relatorio)
    if nomes:
        historia.append(Paragraph("Actividade por colaborador", s_seccao))
        historia.append(_grafico_de_barras(nomes, series, [COR_FASES, COR_CONCLUIDAS, COR_ATRASO], fonte, largura_util, 190))
        legenda = (f'<font color="{COR_FASES}">■</font> Fases alteradas &nbsp; '
                   f'<font color="{COR_CONCLUIDAS}">■</font> Tarefas concluídas &nbsp; '
                   f'<font color="{COR_ATRASO}">■</font> Tarefas em atraso')
        historia.append(Paragraph(legenda, s_nota))
        if len(relatorio.get("users") or []) > MAX_PESSOAS_NO_GRAFICO:
            historia.append(Paragraph(f"Gráfico limitado às {MAX_PESSOAS_NO_GRAFICO} pessoas mais activas; a tabela abaixo lista todas.", s_nota))

    fases = (relatorio.get("por_fase") or [])[:MAX_FASES_NO_GRAFICO]
    if fases:
        historia.append(Paragraph("Entradas por fase", s_seccao))
        historia.append(_grafico_de_barras(
            [str(f.get("rotulo") or f.get("fase")) for f in fases][::-1],
            [[int(f.get("n") or 0) for f in fases][::-1]], [COR_FASES], fonte,
            largura_util, max(110, 22 * len(fases) + 30), horizontal=True,
        ))

    serie = relatorio.get("serie_diaria") or []
    if serie:
        historia.append(Paragraph("Evolução diária", s_seccao))
        historia.append(_grafico_de_barras(
            [formatar_data(d["dia"])[:5] for d in serie],
            [[d["mudancas_de_fase"] for d in serie], [d["tarefas_concluidas"] for d in serie]],
            [COR_FASES, COR_CONCLUIDAS], fonte, largura_util, 150,
        ))
        historia.append(Paragraph(
            f'<font color="{COR_FASES}">■</font> Fases alteradas &nbsp; <font color="{COR_CONCLUIDAS}">■</font> Tarefas concluídas', s_nota))
    elif relatorio.get("serie_omitida"):
        historia.append(Paragraph("Evolução diária omitida: o período excede 92 dias.", s_nota))

    # ── Tabela por colaborador ────────────────────────────────────
    # Sem isto o título ficava sozinho no fundo da página, com a tabela na seguinte.
    historia.append(CondPageBreak(4.5 * cm))
    historia.append(Paragraph("Detalhe por colaborador", s_seccao))
    dados = linhas_da_tabela(relatorio)
    tabela = Table(
        [[Paragraph(esc(c), s_celula) for c in linha] for linha in dados],
        colWidths=[largura_util * f for f in (0.24, 0.14, 0.13, 0.12, 0.14, 0.12, 0.11)],
        repeatRows=1,
    )
    estilo = [("BACKGROUND", (0, 0), (-1, 0), cor_destaque), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
              ("GRID", (0, 0), (-1, -1), 0.25, grelha), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
              ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]
    for i in range(2, len(dados), 2):
        estilo.append(("BACKGROUND", (0, i), (-1, i), zebra))
    tabela.setStyle(TableStyle(estilo))
    # Cabeçalho a branco: os Paragraph não herdam o TEXTCOLOR do estilo da tabela.
    for celula in tabela._cellvalues[0]:
        celula.style = ParagraphStyle("ExecCab", parent=s_celula, fontName=negrito, textColor=colors.white)
    historia.append(tabela)
    if relatorio.get("truncado"):
        historia.append(Paragraph(f"Lista limitada às primeiras {relatorio.get('limite_de_utilizadores')} pessoas.", s_nota))

    # ── Movimentos (relatório semanal) ────────────────────────────
    movimentos = relatorio.get("movimentos")
    if movimentos:
        historia.append(Paragraph("Movimentos de fase da semana", s_seccao))
        cab = ["Quando", "Colaborador", "Processo", "De", "Para"]
        corpo = [[Paragraph(esc(c), s_celula) for c in cab]]
        for m in movimentos[:MAX_MOVIMENTOS_NO_PDF]:
            corpo.append([Paragraph(esc(c), s_celula) for c in (
                formatar_data(m.get("em")), m.get("user_name") or "—",
                f"#{m.get('process_number')}" if m.get("process_number") is not None else "—",
                m.get("de_rotulo") or "—", m.get("para_rotulo") or "—")])
        tab_mov = Table(corpo, colWidths=[largura_util * f for f in (0.14, 0.26, 0.12, 0.24, 0.24)], repeatRows=1)
        tab_mov.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.25, grelha), ("BACKGROUND", (0, 0), (-1, 0), zebra),
                                     ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]))
        historia.append(tab_mov)
        if len(movimentos) > MAX_MOVIMENTOS_NO_PDF:
            historia.append(Paragraph(f"Mostrados {MAX_MOVIMENTOS_NO_PDF} de {len(movimentos)} movimentos.", s_nota))

    # ── Critérios e proveniência ──────────────────────────────────
    notas = [f"• {esc(n)}" for n in (relatorio.get("notas") or [])]
    gerado = formatar_data(relatorio.get("gerado_em"))
    notas.append(esc(f"Gerado em {gerado}" + (f" por {gerado_por}" if gerado_por else "") + "."))
    historia.append(Spacer(1, 10))
    historia.append(KeepTogether([Paragraph("Critérios", s_seccao)] + [Paragraph(n, s_nota) for n in notas]))

    canvas_numerado = rgpd_pdf._make_numbered_canvas_class(
        fonte, margem, A4[0] - margem, 1.1 * cm,
        f"{empresa.get('nome') or ''} — {titulo}".strip(" —"),
    )
    doc.build(historia, canvasmaker=canvas_numerado)
    return buffer.getvalue()


def nome_do_ficheiro(relatorio: dict, prefixo: str = "relatorio-executivo") -> str:
    return f"{prefixo}_{relatorio.get('start_date', 'inicio')}_{relatorio.get('end_date', 'fim')}.pdf"

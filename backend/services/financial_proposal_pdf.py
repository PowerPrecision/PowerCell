"""
Gerador de PDF da Proposta Financeira (3 cenários de Crédito Habitação).

ÉPICO "Motor de Simulação Financeira" (Eixo 3): recebe o resultado de
``services/financial_simulator.build_simulation`` e produz um PDF limpo,
pronto a apresentar ao cliente, com o enquadramento financeiro do processo
e a comparação lado a lado de **Taxa Fixa / Taxa Mista / Taxa Variável**.

ZERO HARDCODING DE EMPRESA:
    O emissor do documento (nome, NIF, morada, email, telefone) vem de
    ``rgpd_service._get_company_legal_data()`` — a mesma fonte oficial já
    usada pelo RGPD e pela Minuta de Exclusividade (``SystemConfig.settings``).
    O logótipo vem de ``email_branding.resolve_company_logo_url(company_id)``
    (system_config da empresa → ``db.companies`` → fallback global) e a cor
    de destaque de ``SystemConfig.settings.primary_color``. Nenhum nome,
    morada, cor ou URL de marca está escrito neste ficheiro.

REUTILIZAÇÃO:
    - Infra-estrutura de PDF (registo da fonte DejaVu com variante Bold,
      escape XML, canvas numerado com rodapé corporativo) → ``rgpd_pdf.py``.
      Não há um segundo registo de fontes nem um segundo NumberedCanvas.
    - Leitura de campos aninhados do processo → ``template_generator
      .get_nested_value`` (o mesmo resolvedor dos templates de documentos).

DEGRADAÇÃO GRACIOSA:
    Logótipo inacessível, fonte DejaVu ausente ou branding por configurar
    nunca impedem a geração: o PDF sai sem logo / com Helvetica / com os
    campos legais em branco, e o incidente fica em log.
"""
from __future__ import annotations

import io
import logging
import re
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Tamanho máximo aceite para o logótipo remoto (evita puxar um ficheiro
# enorme para dentro de um PDF por engano numa configuração errada).
_MAX_LOGO_BYTES = 2 * 1024 * 1024
_LOGO_FETCH_TIMEOUT_SECONDS = 6

# Cor de destaque usada apenas se a configuração não definir nenhuma.
# (Não é branding: é o fallback neutro do reportlab para não rebentar.)
_NEUTRAL_ACCENT = "#334155"

DOCUMENT_TITLE = "Proposta de Financiamento — Crédito Habitação"


# ====================================================================
# FORMATAÇÃO (pt-PT)
# ====================================================================


def format_eur(value: Any, *, decimals: int = 2) -> str:
    """Formata um valor monetário em pt-PT (``1.234,56 €``)."""
    try:
        number = float(value or 0)
    except (TypeError, ValueError):
        number = 0.0
    formatted = f"{number:,.{decimals}f}"
    # en-US (1,234.56) → pt-PT (1.234,56)
    formatted = formatted.replace(",", "\x00").replace(".", ",").replace("\x00", ".")
    return f"{formatted} €"


def format_pct(value: Any, *, decimals: int = 2) -> str:
    """Formata uma percentagem em pt-PT (``3,25%``)."""
    try:
        number = float(value or 0)
    except (TypeError, ValueError):
        number = 0.0
    return f"{number:.{decimals}f}".replace(".", ",") + "%"


def format_date_pt(iso_value: Any) -> str:
    """Formata um ISO timestamp como ``dd/mm/aaaa`` (vazio se inválido)."""
    if not iso_value:
        return ""
    try:
        text = str(iso_value).replace("Z", "+00:00")
        return datetime.fromisoformat(text).strftime("%d/%m/%Y")
    except (TypeError, ValueError):
        return ""


def build_proposal_filename(process: dict, *, now: Optional[datetime] = None) -> str:
    """Nome do ficheiro da proposta: ``proposta_financeira_<ref>_<data>.pdf``.

    ``<ref>`` é o número do processo quando existe (é o que o consultor
    procura na pasta do cliente); caso contrário, o prefixo do id.
    """
    moment = now or datetime.now(timezone.utc)
    reference = (
        str(process.get("process_number") or "").strip()
        or str(process.get("id") or "")[:8]
        or "processo"
    )
    slug = re.sub(r"[^A-Za-z0-9._-]+", "_", reference).strip("_") or "processo"
    return f"proposta_financeira_{slug}_{moment.strftime('%Y%m%d')}.pdf"


# ====================================================================
# BRANDING (configuração — nunca literais)
# ====================================================================


async def _fetch_logo_bytes(logo_url: Optional[str]) -> Optional[bytes]:
    """Descarrega o logótipo da empresa; ``None`` se indisponível."""
    if not logo_url or not str(logo_url).lower().startswith(("http://", "https://")):
        return None
    try:
        import httpx

        async with httpx.AsyncClient(timeout=_LOGO_FETCH_TIMEOUT_SECONDS) as client:
            response = await client.get(logo_url)
        if response.status_code != 200:
            logger.debug(
                f"[PROPOSTA-PDF] Logótipo devolveu status {response.status_code}"
            )
            return None
        content = response.content
        if not content or len(content) > _MAX_LOGO_BYTES:
            logger.debug("[PROPOSTA-PDF] Logótipo vazio ou demasiado grande")
            return None
        return content
    except Exception as e:  # pragma: no cover — degradação graciosa
        logger.debug(f"[PROPOSTA-PDF] Logótipo indisponível: {e}")
        return None


async def resolve_proposal_branding(company_id: Optional[str] = None) -> dict:
    """Dados do emissor + logótipo + cor de destaque para a proposta.

    Returns:
        ``{"empresa": {...}, "logo_bytes": bytes|None, "accent": "#RRGGBB"}``.
        Nunca levanta excepção — campos indisponíveis ficam vazios.
    """
    empresa = {"nome": "", "nif": "", "morada": "", "email": "", "contacto": ""}
    accent = _NEUTRAL_ACCENT
    logo_url = None

    try:
        from services.rgpd_service import _get_company_legal_data

        empresa = await _get_company_legal_data()
    except Exception as e:  # pragma: no cover — degradação graciosa
        logger.warning(f"[PROPOSTA-PDF] Dados legais da empresa indisponíveis: {e}")

    try:
        from services.email_branding import resolve_company_logo_url

        logo_url = await resolve_company_logo_url(company_id)
    except Exception as e:  # pragma: no cover
        logger.debug(f"[PROPOSTA-PDF] Logótipo não resolvido: {e}")

    try:
        from services.system_config import get_system_config

        config = await get_system_config(company_id or "default")
        configured = (config.settings.primary_color or "").strip()
        if re.fullmatch(r"#[0-9A-Fa-f]{6}", configured):
            accent = configured
    except Exception as e:  # pragma: no cover
        logger.debug(f"[PROPOSTA-PDF] Cor de destaque não resolvida: {e}")

    return {
        "empresa": empresa,
        "logo_bytes": await _fetch_logo_bytes(logo_url),
        "accent": accent,
    }


# ====================================================================
# CONSTRUÇÃO DO PDF (reportlab platypus)
# ====================================================================


def _scenario_rows(simulation: dict) -> list[list[str]]:
    """Linhas da tabela comparativa (métrica × 3 cenários)."""
    cenarios = simulation.get("cenarios") or []
    tem_seguros = float(simulation.get("seguros_mensal") or 0) > 0

    def column(getter) -> list[str]:
        return [getter(c) for c in cenarios]

    def taxa_posterior(c: dict) -> str:
        if not c.get("tem_segundo_patamar"):
            return "—"
        return format_pct(c.get("taxa_posterior_pct"))

    def prestacao_posterior(c: dict) -> str:
        if not c.get("tem_segundo_patamar"):
            return "—"
        return format_eur(c.get("prestacao_posterior"))

    def periodo_fixo(c: dict) -> str:
        if c.get("key") == "variavel":
            return "—"
        anos = float(c.get("periodo_fixo_anos") or 0)
        if anos <= 0:
            return "—"
        if not c.get("tem_segundo_patamar"):
            return "Todo o prazo"
        return f"{anos:.0f} anos".replace(".0", "")

    def dsti_cell(c: dict) -> str:
        dsti = c.get("dsti") or {}
        if not dsti.get("is_calculable"):
            return "Sem dados"
        marca = "✔" if dsti.get("dentro_limite") else "✘"
        return f"{format_pct(dsti.get('dsti_pct'))} {marca}"

    rows: list[list[str]] = [
        ["Taxa nominal (TAN)"] + column(lambda c: format_pct(c.get("taxa_inicial_pct"))),
        ["Spread"] + column(lambda c: format_pct(c.get("spread_pct"))),
        ["Período de taxa fixa"] + column(periodo_fixo),
        ["TAN após período fixo"] + column(taxa_posterior),
        ["Prestação mensal"] + column(lambda c: format_eur(c.get("prestacao_mensal"))),
        ["Prestação após período fixo"] + column(prestacao_posterior),
    ]

    if tem_seguros:
        rows.append(
            ["Seguros (mensal)"]
            + column(lambda c: format_eur(c.get("seguros_mensal")))
        )
        rows.append(
            ["Prestação total mensal"]
            + column(lambda c: format_eur(c.get("prestacao_total_mensal")))
        )

    rows.extend(
        [
            ["TAEG"] + column(lambda c: format_pct(c.get("taeg_pct"))),
            ["Total de juros"] + column(lambda c: format_eur(c.get("total_juros"))),
            ["Total pago"] + column(lambda c: format_eur(c.get("total_pago"))),
            ["Taxa de esforço projetada"] + column(dsti_cell),
        ]
    )
    return rows


def _summary_rows(simulation: dict, process: dict) -> list[list[str]]:
    """Linhas do bloco "Enquadramento Financeiro"."""
    from services.template_generator import get_nested_value

    inputs = simulation.get("inputs") or {}
    rendimentos = simulation.get("rendimentos") or {}
    indexante = simulation.get("taxa_indexante") or {}
    dsti_atual = simulation.get("dsti_atual") or {}

    morada_imovel = (
        get_nested_value(process, "real_estate_data.morada_imovel")
        or get_nested_value(process, "real_estate_data.morada")
        or get_nested_value(process, "property_address")
        or ""
    )

    rows = [
        ["Montante a financiar", format_eur(inputs.get("capital"))],
        ["Prazo", f"{int(inputs.get('prazo_anos') or 0)} anos"],
    ]
    if float(inputs.get("valor_imovel") or 0) > 0:
        rows.append(["Valor do imóvel", format_eur(inputs.get("valor_imovel"))])
    if float(inputs.get("capital_proprio") or 0) > 0:
        rows.append(["Capital próprio", format_eur(inputs.get("capital_proprio"))])
    if morada_imovel:
        rows.append(["Imóvel", str(morada_imovel)])

    rows.extend(
        [
            [
                "Rendimento bruto mensal (agregado)",
                format_eur(rendimentos.get("rendimento_bruto_total")),
            ],
            [
                "Rendimento líquido mensal (agregado)",
                format_eur(rendimentos.get("rendimento_liquido_total")),
            ],
        ]
    )
    if float(rendimentos.get("prestacao_creditos_mensal") or 0) > 0:
        contratos = int(rendimentos.get("numero_creditos") or 0)
        sufixo = (
            f" ({contratos} contrato{'s' if contratos != 1 else ''})"
            if contratos > 0
            else ""
        )
        rows.append(
            [
                "Encargos de crédito atuais",
                f"{format_eur(rendimentos.get('prestacao_creditos_mensal'))}"
                f"{sufixo}",
            ]
        )
    if float(rendimentos.get("renda_habitacao") or 0) > 0:
        rows.append(
            ["Renda de habitação atual", format_eur(rendimentos.get("renda_habitacao"))]
        )

    rows.extend(
        [
            [
                "Taxa de esforço atual",
                format_pct(dsti_atual.get("dsti_pct")),
            ],
            [
                "Prestação máxima comportável",
                format_eur(dsti_atual.get("max_installment")),
            ],
            [
                f"Euribor {str(indexante.get('index', '')).upper()}",
                f"{format_pct(indexante.get('rate_pct'), decimals=3)}"
                + (" (estimativa)" if indexante.get("is_fallback") else ""),
            ],
            [
                "Limite de taxa de esforço considerado",
                format_pct(simulation.get("limite_dsti_pct")),
            ],
        ]
    )
    return rows


def build_financial_proposal_pdf(
    *,
    process: dict,
    simulation: dict,
    empresa: dict,
    logo_bytes: Optional[bytes] = None,
    accent: str = _NEUTRAL_ACCENT,
) -> bytes:
    """Constrói o PDF da proposta (síncrono — reportlab é bloqueante).

    Args:
        process: Documento do processo (cliente, imóvel, referência).
        simulation: Resultado ``success=True`` de ``build_simulation``.
        empresa: Dados legais do emissor (``_get_company_legal_data``).
        logo_bytes: Bytes do logótipo já descarregado (opcional).
        accent: Cor de destaque hexadecimal da empresa.

    Returns:
        Bytes do PDF.
    """
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_RIGHT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import (
        Image,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    # Infra-estrutura partilhada com o PDF RGPD (fonte + escape + rodapé)
    from services import rgpd_pdf

    rgpd_pdf._ensure_font()
    font_name = "DejaVuSans" if rgpd_pdf._FONT_REGISTERED else "Helvetica"
    font_bold = (
        "DejaVuSans-Bold" if rgpd_pdf._FONT_REGISTERED else "Helvetica-Bold"
    )
    escape = rgpd_pdf._escape_xml

    accent_color = colors.HexColor(accent)
    muted = colors.HexColor("#6B7280")
    grid = colors.HexColor("#D1D5DB")
    zebra = colors.HexColor("#F3F4F6")

    margin = 1.8 * cm
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=margin,
        rightMargin=margin,
        topMargin=1.5 * cm,
        bottomMargin=2.0 * cm,
        title=DOCUMENT_TITLE,
        author=empresa.get("nome") or "",
    )

    base = getSampleStyleSheet()
    style_title = ParagraphStyle(
        "ProposalTitle", parent=base["Title"], fontName=font_bold,
        fontSize=16, leading=20, textColor=accent_color, spaceAfter=2,
    )
    style_subtitle = ParagraphStyle(
        "ProposalSubtitle", parent=base["Normal"], fontName=font_name,
        fontSize=9, leading=12, textColor=muted, alignment=TA_CENTER,
    )
    style_section = ParagraphStyle(
        "ProposalSection", parent=base["Heading2"], fontName=font_bold,
        fontSize=11, leading=14, textColor=accent_color,
        spaceBefore=12, spaceAfter=6,
    )
    style_body = ParagraphStyle(
        "ProposalBody", parent=base["Normal"], fontName=font_name,
        fontSize=8.5, leading=12, alignment=TA_JUSTIFY,
    )
    style_note = ParagraphStyle(
        "ProposalNote", parent=style_body, fontSize=7.5, leading=10,
        textColor=muted,
    )
    style_cell = ParagraphStyle(
        "ProposalCell", parent=base["Normal"], fontName=font_name,
        fontSize=8, leading=10,
    )
    # Bloco do emissor: alinhado à direita, para equilibrar o logótipo à
    # esquerda (e continuar legível quando não há logótipo configurado).
    style_issuer = ParagraphStyle(
        "ProposalIssuer", parent=style_note, alignment=TA_RIGHT,
    )

    story: list = []

    # ── Cabeçalho: logótipo + emissor ───────────────────────────────
    emissor_linhas = [escape(empresa.get("nome") or "")]
    if empresa.get("nif"):
        emissor_linhas.append(f"NIF {escape(empresa['nif'])}")
    if empresa.get("morada"):
        emissor_linhas.append(escape(empresa["morada"]))
    contactos = " · ".join(
        escape(v) for v in (empresa.get("email"), empresa.get("contacto")) if v
    )
    if contactos:
        emissor_linhas.append(contactos)
    emissor_html = "<br/>".join(linha for linha in emissor_linhas if linha)

    logo_flowable = ""
    if logo_bytes:
        try:
            logo = Image(io.BytesIO(logo_bytes))
            ratio = (logo.imageHeight or 1) / (logo.imageWidth or 1)
            logo.drawWidth = 3.6 * cm
            logo.drawHeight = min(3.6 * cm * ratio, 1.8 * cm)
            if logo.drawHeight >= 1.8 * cm:
                logo.drawWidth = 1.8 * cm / ratio
            logo.hAlign = "LEFT"
            logo_flowable = logo
        except Exception as e:  # pragma: no cover — logótipo inválido
            logger.warning(f"[PROPOSTA-PDF] Logótipo não utilizável: {e}")

    content_width = doc.width
    header = Table(
        [[logo_flowable, Paragraph(emissor_html, style_issuer)]],
        colWidths=[content_width * 0.35, content_width * 0.65],
    )
    header.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("LINEBELOW", (0, 0), (-1, 0), 1.2, accent_color),
            ]
        )
    )
    story.append(header)
    story.append(Spacer(1, 10))

    # ── Título + identificação do processo ──────────────────────────
    story.append(Paragraph(escape(DOCUMENT_TITLE), style_title))

    process_number = process.get("process_number") or ""
    referencia = f"Processo {escape(str(process_number))}" if process_number else ""
    cliente = escape(process.get("client_name") or "")
    emitido = format_date_pt(simulation.get("calculated_at")) or format_date_pt(
        datetime.now(timezone.utc).isoformat()
    )
    validade = format_date_pt(simulation.get("valido_ate"))
    subtitulo = " · ".join(
        parte
        for parte in (
            cliente,
            referencia,
            f"Emitida em {emitido}" if emitido else "",
            f"Válida até {validade}" if validade else "",
        )
        if parte
    )
    story.append(Paragraph(subtitulo, style_subtitle))
    story.append(Spacer(1, 14))

    # ── Enquadramento financeiro ────────────────────────────────────
    story.append(Paragraph("Enquadramento Financeiro", style_section))
    summary_data = [
        [Paragraph(escape(label), style_cell), Paragraph(escape(value), style_cell)]
        for label, value in _summary_rows(simulation, process)
    ]
    summary_table = Table(
        summary_data, colWidths=[content_width * 0.45, content_width * 0.55]
    )
    summary_table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.4, grid),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.white, zebra]),
            ]
        )
    )
    story.append(summary_table)

    # ── Comparação dos 3 cenários ───────────────────────────────────
    story.append(Paragraph("Cenários de Financiamento", style_section))

    cenarios = simulation.get("cenarios") or []
    header_row = [Paragraph("", style_cell)] + [
        Paragraph(f"<b>{escape(c.get('label'))}</b>", style_cell) for c in cenarios
    ]
    body_rows = [
        [Paragraph(f"<b>{escape(row[0])}</b>", style_cell)]
        + [Paragraph(escape(cell), style_cell) for cell in row[1:]]
        for row in _scenario_rows(simulation)
    ]

    label_width = content_width * 0.34
    scenario_width = (content_width - label_width) / max(len(cenarios), 1)
    scenarios_table = Table(
        [header_row] + body_rows,
        colWidths=[label_width] + [scenario_width] * len(cenarios),
        repeatRows=1,
    )
    scenarios_table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.4, grid),
                ("BACKGROUND", (0, 0), (-1, 0), accent_color),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (1, 0), (-1, -1), "CENTER"),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, zebra]),
            ]
        )
    )
    story.append(scenarios_table)
    story.append(Spacer(1, 8))

    # ── Descrição de cada cenário ───────────────────────────────────
    for cenario in cenarios:
        story.append(
            Paragraph(
                f"<b>{escape(cenario.get('label'))}</b> — "
                f"{escape(cenario.get('descricao'))}",
                style_note,
            )
        )
        story.append(Spacer(1, 3))

    # ── Avisos do motor + nota legal ────────────────────────────────
    avisos = [a for a in (simulation.get("avisos") or []) if a]
    if avisos:
        story.append(Paragraph("Notas da Simulação", style_section))
        for aviso in avisos:
            story.append(Paragraph(f"• {escape(aviso)}", style_note))
            story.append(Spacer(1, 2))

    story.append(Spacer(1, 10))
    story.append(
        Paragraph(
            "Simulação de carácter informativo, sem valor vinculativo, "
            "gerada automaticamente a partir dos documentos financeiros "
            "indexados no processo. As condições finais dependem da análise "
            "e aprovação da instituição de crédito. As prestações dos "
            "cenários indexados variam com a evolução da Euribor.",
            style_note,
        )
    )

    numbered_canvas = rgpd_pdf._make_numbered_canvas_class(
        font_name,
        margin,
        A4[0] - margin,
        1.1 * cm,
        f"{empresa.get('nome') or ''} — {DOCUMENT_TITLE}".strip(" —"),
    )
    doc.build(story, canvasmaker=numbered_canvas)

    return buffer.getvalue()


async def generate_financial_proposal_pdf(
    process: dict,
    simulation: dict,
    *,
    company_id: Optional[str] = None,
) -> tuple[bytes, str]:
    """Resolve o branding e gera o PDF da proposta num executor.

    ``reportlab`` é bloqueante: a construção corre fora do event loop para
    não travar o servidor enquanto o motor trabalha em background.

    Returns:
        ``(pdf_bytes, filename)``.
    """
    import asyncio

    branding = await resolve_proposal_branding(
        company_id or process.get("company_id") or process.get("company")
    )

    loop = asyncio.get_event_loop()
    pdf_bytes = await loop.run_in_executor(
        None,
        lambda: build_financial_proposal_pdf(
            process=process,
            simulation=simulation,
            empresa=branding["empresa"],
            logo_bytes=branding["logo_bytes"],
            accent=branding["accent"],
        ),
    )
    return pdf_bytes, build_proposal_filename(process)

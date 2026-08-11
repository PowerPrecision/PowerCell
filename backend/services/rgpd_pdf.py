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
"""
from __future__ import annotations

import io
import logging
import os
import re
from datetime import datetime, timezone

from fastapi import HTTPException

from database import db
from services.process_service import decrypt_sensitive_data
# PACOTE DE — reutilização das funções internas (underscore prefix) de rgpd_service.
# Python não enforce privacy; importação cross-module é aceitável aqui.
# `_get_rendered_rgpd_text` renderiza o template RGPD ativo com os
# placeholders substituídos pelos dados do cliente (ou linhas em branco).
from services.rgpd_service import _get_rendered_rgpd_text
from services.rgpd_helpers import _add_process_activity

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# PACOTE DG — Registo de fonte TTF (DejaVuSans) para suporte Unicode
# (acentos PT + símbolo ☐ U+2610 BALLOT BOX). Procura em vários paths
# Linux; fallback para Helvetica se não encontrar (acentos podem aparecer mal).
# ---------------------------------------------------------------------------
_FONT_REGISTERED = False


def _ensure_font() -> None:
    """Regista DejaVuSans no reportlab (idempotente). Fallback Helvetica."""
    global _FONT_REGISTERED
    if _FONT_REGISTERED:
        return
    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans.ttf",
        "/usr/local/share/fonts/dejavu/DejaVuSans.ttf",
    ]
    try:
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
    except ImportError:
        logger.warning(
            "PACOTE DG — reportlab.pdfbase indisponível, a usar Helvetica"
        )
        return
    for path in font_paths:
        if os.path.exists(path):
            try:
                pdfmetrics.registerFont(TTFont("DejaVuSans", path))
                _FONT_REGISTERED = True
                logger.info("PACOTE DG — DejaVuSans registada: %s", path)
                return
            except Exception as e:
                logger.warning(
                    "PACOTE DG — Erro ao registar DejaVuSans %s: %s", path, e
                )
    logger.warning(
        "PACOTE DG — DejaVuSans não encontrada, a usar Helvetica "
        "(acentos podem aparecer mal)"
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


def _build_prefilled_rgpd_pdf(rgpd_text: str, consent_data: dict) -> bytes:
    """
    PACOTE DG — Novo builder de PDF RGPD pré-preenchido para assinatura manual.

    Usa `reportlab.platypus` (SimpleDocTemplate) para paginação automática.

    - Template dinâmico (`rgpd_text`) é respeitado (11 secções do admin).
    - Campos em falta → linhas em branco "_____".
    - Data e Local → linhas em branco.
    - Checkboxes → quadrados vazios ☐ (Unicode U+2610).

    Args:
        rgpd_text: Template RGPD já renderizado (placeholders substituídos).
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

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
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
        fontSize=9,
        leading=13,
        alignment=TA_JUSTIFY,
        spaceAfter=4,
    )
    section_style = ParagraphStyle(
        "Section",
        parent=body_style,
        fontName=font_name,
        fontSize=9,
        leading=13,
        spaceBefore=6,
        spaceAfter=2,
    )
    consent_title_style = ParagraphStyle(
        "ConsentTitle",
        parent=body_style,
        fontName=font_name,
        fontSize=9,
        leading=13,
        spaceBefore=8,
        spaceAfter=2,
    )
    checkbox_style = ParagraphStyle(
        "Checkbox",
        parent=body_style,
        fontName=font_name,
        fontSize=9,
        leading=13,
        leftIndent=20,
        spaceAfter=2,
    )
    sig_style = ParagraphStyle(
        "Sig",
        parent=body_style,
        fontName=font_name,
        fontSize=9,
        leading=13,
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
    # Linhas vazias → Spacer; outras → Paragraph.
    if rgpd_text:
        for line in rgpd_text.split("\n"):
            line_stripped = line.strip()
            if not line_stripped:
                story.append(Spacer(1, 0.25 * cm))
                continue
            # Detectar headers de secção (linhas começando com número ou ALL CAPS)
            is_header = (
                line_stripped[0].isdigit() and "." in line_stripped[:4]
            ) or (line_stripped.isupper() and len(line_stripped) < 80)
            style = section_style if is_header else body_style
            story.append(Paragraph(_escape_xml(line_stripped), style))

    story.append(Spacer(1, 0.6 * cm))
    story.append(
        HRFlowable(width="100%", thickness=0.5, color=HexColor("#333333"))
    )
    story.append(Spacer(1, 0.3 * cm))

    # 3. Opções de consentimento A/B/C/D com checkboxes VAZIAS
    story.append(Paragraph("<b>CONSENTIMENTO</b>", consent_title_style))
    story.append(Spacer(1, 0.2 * cm))

    # PACOTE DG — ☐ = &#9744; (Unicode U+2610 BALLOT BOX). Vazio, NÃO pré-marcado.
    for letter, description in CONSENT_OPTIONS_DG:
        story.append(
            Paragraph(
                f"<b>{letter})</b> {_escape_xml(description)}", body_style
            )
        )
        checkbox_line = (
            "&#9744; Autorizo &nbsp;&nbsp;&nbsp;&nbsp; "
            "&#9744; Não Autorizo"
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
        pdf_bytes = _build_prefilled_rgpd_pdf(rgpd_text, consent_data)
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

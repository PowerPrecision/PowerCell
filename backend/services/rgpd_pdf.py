"""
Serviço RGPD PDF — geração de PDF RGPD PRÉ-PREENCHIDO com dados do cliente.

PACOTE DE — endpoint de download de PDF RGPD pré-preenchido (sem assinatura
digital). Reutiliza a infraestrutura existente em `services/rgpd_service.py`:
- `_get_rendered_rgpd_text(process_id, rgpd_request, consent_data)` — busca o
  processo, desencripta, obtém o template RGPD ativo e substitui os
  placeholders `{{NOME}}`, `{{CONTRIBUINTE}}`, etc.
- `_generate_rgpd_pdf_bytes(process_id, rgpd_request, consent_data)` — wrapper
  async que gera o PDF A4 com reportlab Canvas (cabeçalho + consentimento +
  opções A/B/C/D + secção de assinatura).

Diferença para o fluxo de assinatura digital: o `consent_data` é montado
sinteticamente a partir dos dados do processo (Nome, NIF, Morada, etc.) e a
data de assinatura é a data atual (UTC). Não há token de cliente nem
assinatura base64 — o PDF destina-se a impressão + assinatura manual.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

from fastapi import HTTPException

from database import db
from services.process_service import decrypt_sensitive_data
# PACOTE DE — reutilização das funções internas (underscore prefix) de rgpd_service.
# Python não enforce privacy; importação cross-module é aceitável aqui.
# `_generate_rgpd_pdf_bytes` internamente chama `_get_rendered_rgpd_text`
# (renderiza o template RGPD ativo com os placeholders substituídos pelos
# dados do cliente) e depois `_build_rgpd_pdf` (gera o PDF A4 via reportlab).
from services.rgpd_service import _generate_rgpd_pdf_bytes
from services.rgpd_helpers import _add_process_activity

logger = logging.getLogger(__name__)


async def run_generate_prefilled_rgpd_pdf(
    process_id: str,
    user: dict,
) -> tuple[bytes, str]:
    """
    Gera um PDF RGPD PRÉ-PREENCHIDO com os dados reais do cliente/processo.

    Fluxo:
    1. Busca o processo em `db.processes` (404 se não existir / eliminado).
    2. Desencripta campos sensíveis via `decrypt_sensitive_data`.
    3. Monta `consent_data` sintético com Nome, NIF, documento, morada e
       data atual (UTC) — faz fallback para strings vazias quando os campos
       não existem no processo.
    4. Renderiza o template RGPD ativo (`_get_rendered_rgpd_text`) substituindo
       os placeholders `{{...}}` pelos valores do cliente.
    5. Gera o PDF A4 (`_generate_rgpd_pdf_bytes`) via reportlab.
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

    consent_data = {
        "nome": (
            process.get("client_name")
            or personal.get("nome")
            or personal.get("nome_completo")
            or ""
        ),
        "contribuinte": personal.get("nif") or "",
        "tipo_documento": doc_type,
        "numero_documento": doc_number,
        "validade_documento": personal.get("data_validade_cc") or "",
        "morada": (
            personal.get("morada_fiscal")
            or personal.get("morada")
            or ""
        ),
        "localidade": real_estate.get("localidade") or "",
        "concelho": real_estate.get("concelho") or "",
        "codigo_postal": real_estate.get("codigo_postal") or "",
        "data_assinatura": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
    }

    # 4 + 5. Renderizar template + gerar PDF.
    # `_generate_rgpd_pdf_bytes` internamente chama `_get_rendered_rgpd_text`
    # (passa `rgpd_request={}` e o `consent_data` sintético) e depois
    # `_build_rgpd_pdf` num executor (não bloqueia o event loop).
    try:
        pdf_bytes = await _generate_rgpd_pdf_bytes(process_id, {}, consent_data)
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
                f"PDF gerado com dados do cliente ({consent_data.get('nome') or 'N/A'}). "
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

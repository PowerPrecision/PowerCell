"""
====================================================================
PACOTE DJ — SERVIÇO DE REVISÃO HUMAN-IN-THE-LOOP DE DOCUMENTOS
====================================================================
Fluxo HITL (Human-in-the-Loop) para análise IA de documentos:

1. `run_analyze_document_for_review(doc_id, user)`
   - IA gera sugestões (categoria, subcategoria, validade, nome, filename)
   - Persiste em `suggested_*` (NÃO aplica a `ai_*`)
   - Marca `ai_review_status='pending'`

2. `run_apply_review(doc_id, body, user)`
   - Consultor aprova sugestões (opcionalmente com edições)
   - Copia `suggested_*` → `ai_*`
   - Marca `ai_review_status='approved'` (ou `'edited'` se houve edições)

3. `run_reject_review(doc_id, body, user)`
   - Consultor rejeita as sugestões
   - Marca `ai_review_status='rejected'`
   - Mantém `suggested_*` para auditoria

4. `run_get_pending_reviews(process_id, user)`
   - Lista documentos de um processo com `ai_review_status='pending'`

Princípio chave:
- A IA escreve SEMPRE em `suggested_*` (não toca em `ai_*`).
- Os campos `ai_*` (aplicados) só são actualizados quando o consultor
  aprova via `run_apply_review`.
- O fluxo de auto-categorização em background (`document_auto_categorize.py`)
  NÃO é afectado — continua a escrever directamente em `ai_*` para uploads
  novos. Este serviço é uma via paralela, accionada on-demand pelo
  endpoint `POST /documents/{doc_id}/ai-analyze-review`.
====================================================================
"""
from __future__ import annotations

import base64 as _b64
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import HTTPException

from database import db
from services.document_constants import (
    DEFAULT_FILE_PREFIX,
    ERROR_S3_ACCESS,
    ERROR_S3_FILE_NOT_FOUND,
    MIME_TYPE_PDF,
)
from services.document_auto_categorize import (
    _DOC_TYPE_MAP,
    _extract_validade_from_ocr,
    should_run_ocr_for_category,
)
from services.document_categorization import (
    categorize_document_with_ai,
    extract_text_from_pdf,
)
from services.s3_storage import s3_service

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------
# Helper interno — sanitiza um documento para resposta API
# --------------------------------------------------------------------
def _sanitize_pending_doc(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Reduz um document_metadata aos campos relevantes para a UI de revisão.

    PACOTE DJ — expõe sugestões (`suggested_*`) e valores actualmente
    aplicados (`ai_*` / `expiry_date` / `filename`) lado-a-lado para o
    frontend montar o modal de revisão (Actual vs Sugerido).
    """
    if not doc:
        return {}
    return {
        "id": doc.get("id"),
        "process_id": doc.get("process_id"),
        "client_name": doc.get("client_name"),
        "s3_path": doc.get("s3_path"),
        "filename": doc.get("filename"),
        # Estado de revisão
        "ai_review_status": doc.get("ai_review_status"),
        "ai_reviewed_at": doc.get("ai_reviewed_at"),
        "ai_reviewed_by": doc.get("ai_reviewed_by"),
        "ai_applied_fields": doc.get("ai_applied_fields"),
        # Valores actuais (aplicados)
        "current_category": doc.get("ai_category"),
        "current_subcategory": doc.get("ai_subcategory"),
        "current_confidence": doc.get("ai_confidence"),
        "current_expiry_date": doc.get("expiry_date"),
        "current_filename": doc.get("filename"),
        "current_nome": (doc.get("extracted_data") or {}).get("nome_completo")
        or (doc.get("extracted_data") or {}).get("nome"),
        # Sugestões IA (ainda não aplicadas)
        "suggested_category": doc.get("suggested_category"),
        "suggested_subcategory": doc.get("suggested_subcategory"),
        "suggested_confidence": doc.get("suggested_confidence"),
        "suggested_expiry_date": doc.get("suggested_expiry_date"),
        "suggested_filename": doc.get("suggested_filename"),
        "suggested_nome": doc.get("suggested_nome"),
        # Metadata auxiliar
        "is_categorized": doc.get("is_categorized"),
        "ai_analyzed": doc.get("ai_analyzed"),
        "mime_type": doc.get("mime_type"),
        "updated_at": doc.get("updated_at"),
    }


# --------------------------------------------------------------------
# 2a. Trigger de análise IA — guarda SUGESTÕES (não aplica)
# --------------------------------------------------------------------
async def run_analyze_document_for_review(doc_id: str, user: dict) -> dict:
    """
    PACOTE DJ — Analisa um documento com IA e guarda SUGESTÕES (não aplica).

    Marca `ai_review_status='pending'`. O consultor deve aprovar/rejeitar
    via `run_apply_review` / `run_reject_review`.

    Fluxo:
    1. Carrega `document_metadata` por `id` (ou `doc_id`).
    2. Obtém conteúdo S3 (`s3_service.get_file_content`).
    3. Extrai texto do PDF (se aplicável).
    4. Chama `categorize_document_with_ai` → categoria/subcategoria/
       confiança/expiry_date.
    5. Se `should_run_ocr_for_category(category)`, chama
       `analyze_document_from_base64` para OCR de entidades e extrai
       `nome`. Usa `_extract_validade_from_ocr` como fallback para
       validade (CCs image-based não têm texto extraível).
    6. Persiste TUDO em `suggested_*` + `ai_review_status='pending'`.
       **NÃO escreve em `ai_*`** — esses ficam para `run_apply_review`.
    7. Retorna sugestões + valores actuais para a UI.
    """
    # 1. Carregar metadados do documento
    doc = await db.document_metadata.find_one(
        {"$or": [{"id": doc_id}, {"doc_id": doc_id}]}, {"_id": 0}
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Documento não encontrado")

    doc_id_resolved = doc.get("id") or doc_id
    s3_path = doc.get("s3_path")
    filename = doc.get("filename") or ""
    if not s3_path:
        raise HTTPException(
            status_code=400, detail="Documento sem s3_path associado"
        )

    # 2. Obter conteúdo do S3
    try:
        file_content = s3_service.get_file_content(s3_path)
        if not file_content:
            raise HTTPException(status_code=404, detail=ERROR_S3_FILE_NOT_FOUND)
    except HTTPException:
        raise
    except (IOError, OSError, ValueError, KeyError, TypeError) as e:
        logger.error(f"[DJ-REVIEW] Erro ao obter ficheiro do S3: {e}")
        raise HTTPException(status_code=500, detail=ERROR_S3_ACCESS)

    # 3. Extrair texto do PDF (se aplicável)
    extracted_text = ""
    if filename.lower().endswith(".pdf"):
        try:
            extracted_text = extract_text_from_pdf(file_content)
        except Exception as text_err:
            logger.warning(
                f"[DJ-REVIEW] Falha na extracção de texto PDF: {text_err}"
            )
            extracted_text = ""
    text_for_analysis = (
        extracted_text if extracted_text else f"{DEFAULT_FILE_PREFIX}{filename}"
    )

    # 4. Categorização IA (categoria/subcategoria/confiança/expiry_date)
    try:
        existing_categories = await db.document_metadata.distinct("ai_category")
        cat_result = await categorize_document_with_ai(
            text_content=text_for_analysis,
            filename=filename,
            existing_categories=existing_categories,
        )
    except Exception as cat_err:
        logger.error(f"[DJ-REVIEW] Erro na categorização IA: {cat_err}")
        return {
            "success": False,
            "error": f"Erro na categorização IA: {type(cat_err).__name__}",
            "doc_id": doc_id_resolved,
        }

    if not cat_result.get("success"):
        return {
            "success": False,
            "error": cat_result.get("error", "categorize_failed"),
            "doc_id": doc_id_resolved,
        }

    ai_category = cat_result.get("category") or ""
    expiry_from_cat = cat_result.get("expiry_date")

    # 5. OCR de entidades (se a categoria o sugerir) — extrai nome + validade
    nome_extraido: Optional[str] = None
    validade_from_ocr: Optional[str] = None
    extracted_data: Optional[Dict[str, Any]] = None

    if should_run_ocr_for_category(ai_category) and len(file_content) > 0:
        try:
            from services.ai_document import analyze_document_from_base64

            document_type = _DOC_TYPE_MAP.get(ai_category, "cc")
            b64_content = _b64.b64encode(file_content).decode("utf-8")
            mime_type = (
                MIME_TYPE_PDF
                if filename.lower().endswith(".pdf")
                else "image/jpeg"
            )

            ocr_result = await analyze_document_from_base64(
                b64_content, mime_type, document_type
            )

            if ocr_result and ocr_result.get("extracted_data"):
                extracted_data = ocr_result["extracted_data"]
                nome_extraido = (
                    extracted_data.get("nome_completo")
                    or extracted_data.get("nome")
                )
                validade_from_ocr = _extract_validade_from_ocr(extracted_data)
                logger.info(
                    f"[DJ-REVIEW] OCR extraído para {filename}: "
                    f"nome={'sim' if nome_extraido else 'não'}, "
                    f"validade_ocr={'sim' if validade_from_ocr else 'não'}"
                )
        except Exception as ocr_err:
            # OCR é best-effort — não bloqueia a revisão
            logger.warning(
                f"[DJ-REVIEW] Erro no OCR (não bloqueia revisão): {ocr_err}"
            )

    # 6. Persistir em suggested_* (NÃO em ai_*)
    now = datetime.now(timezone.utc).isoformat()
    expiry_suggested = expiry_from_cat or validade_from_ocr

    update_payload: Dict[str, Any] = {
        "suggested_category": ai_category,
        "suggested_subcategory": cat_result.get("subcategory"),
        "suggested_confidence": cat_result.get("confidence"),
        "suggested_expiry_date": expiry_suggested,
        "suggested_filename": cat_result.get("suggested_filename"),
        "suggested_nome": nome_extraido,
        "ai_review_status": "pending",
        "ai_reviewed_at": None,
        "ai_reviewed_by": None,
        "updated_at": now,
    }
    # Se OCR devolveu extracted_data, guardá-lo também para auditoria
    # (não substituímos extracted_data existente se OCR falhou)
    if extracted_data:
        update_payload["extracted_data"] = extracted_data

    try:
        await db.document_metadata.update_one(
            {"id": doc_id_resolved},
            {"$set": update_payload},
        )
    except Exception as db_err:
        logger.error(f"[DJ-REVIEW] Erro ao persistir sugestões: {db_err}")
        return {
            "success": False,
            "error": f"Erro ao persistir sugestões: {type(db_err).__name__}",
            "doc_id": doc_id_resolved,
        }

    logger.info(
        f"[DJ-REVIEW] Sugestões geradas para doc {doc_id_resolved} "
        f"({filename}): cat={ai_category}, validade={expiry_suggested}, "
        f"nome={'sim' if nome_extraido else 'não'}"
    )

    # 7. Retornar sugestões + valores actuais
    return {
        "success": True,
        "doc_id": doc_id_resolved,
        "suggestions": {
            "category": ai_category,
            "subcategory": cat_result.get("subcategory"),
            "confidence": cat_result.get("confidence"),
            "expiry_date": expiry_suggested,
            "nome": nome_extraido,
            "filename": cat_result.get("suggested_filename"),
            "tags": cat_result.get("tags", []),
            "summary": cat_result.get("summary"),
        },
        "current": {
            "category": doc.get("ai_category"),
            "subcategory": doc.get("ai_subcategory"),
            "confidence": doc.get("ai_confidence"),
            "expiry_date": doc.get("expiry_date"),
            "filename": doc.get("filename"),
            "nome": (doc.get("extracted_data") or {}).get("nome_completo")
            or (doc.get("extracted_data") or {}).get("nome"),
        },
        "ai_review_status": "pending",
    }


# --------------------------------------------------------------------
# 2b. Aplicar sugestões (copia suggested_* → ai_*)
# --------------------------------------------------------------------
async def run_apply_review(doc_id: str, body: dict, user: dict) -> dict:
    """
    PACOTE DJ — Aplica sugestões da IA (copia `suggested_*` → `ai_*`).

    Body:
        {
            "fields": ['categoria','validade','nome','filename'],
            "edited_values": {  # opcional — overrides do consultor
                "categoria": "...", "validade": "...",
                "nome": "...", "filename": "..."
            }
        }

    - Se `edited_values` estiver presente → `ai_review_status='edited'`.
    - Caso contrário → `ai_review_status='approved'`.
    - `ai_applied_fields` regista quais campos foram aplicados (auditoria).
    - O rename real no S3 NÃO é feito aqui — apenas metadata. O frontend
      deve chamar `/rename-smart/{process_id}` separadamente se precisar
      de reflectir o novo nome no S3.
    """
    doc = await db.document_metadata.find_one(
        {"$or": [{"id": doc_id}, {"doc_id": doc_id}]}, {"_id": 0}
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Documento não encontrado")

    doc_id_resolved = doc.get("id") or doc_id

    fields: List[str] = body.get("fields") if isinstance(body, dict) else None
    if not fields or not isinstance(fields, list):
        raise HTTPException(
            status_code=400,
            detail="Body deve incluir 'fields' (lista não vazia)",
        )
    # Validar campos suportados
    supported = {"categoria", "validade", "nome", "filename"}
    invalid = [f for f in fields if f not in supported]
    if invalid:
        raise HTTPException(
            status_code=400,
            detail=f"Campos inválidos: {invalid}. Suportados: {sorted(supported)}",
        )

    edited_values: Dict[str, Any] = (
        body.get("edited_values") if isinstance(body, dict) else None
    ) or {}
    is_edited = bool(edited_values)

    now = datetime.now(timezone.utc).isoformat()
    update_fields: Dict[str, Any] = {}

    if "categoria" in fields:
        cat = edited_values.get("categoria") or doc.get("suggested_category")
        update_fields["ai_category"] = cat
        update_fields["ai_subcategory"] = doc.get("suggested_subcategory")
        update_fields["ai_confidence"] = doc.get("suggested_confidence")
        # Marcar como categorizado quando a categoria é aplicada
        update_fields["is_categorized"] = True
        update_fields["categorized_at"] = now

    if "validade" in fields:
        val = edited_values.get("validade") or doc.get("suggested_expiry_date")
        update_fields["expiry_date"] = val

    if "nome" in fields:
        nome = edited_values.get("nome") or doc.get("suggested_nome")
        # Merge no dict extracted_data (não substituir o dict inteiro)
        existing_extracted = doc.get("extracted_data") or {}
        existing_extracted["nome_completo"] = nome
        update_fields["extracted_data"] = existing_extracted

    if "filename" in fields:
        fname = edited_values.get("filename") or doc.get("suggested_filename")
        if fname:
            update_fields["filename"] = fname
            # Nota: rename real no S3 fica para endpoint separado
            # (/rename-smart/{process_id}). Aqui só actualizamos metadata.

    update_fields["ai_review_status"] = "edited" if is_edited else "approved"
    update_fields["ai_reviewed_at"] = now
    update_fields["ai_reviewed_by"] = user.get("id")
    update_fields["ai_applied_fields"] = fields
    update_fields["updated_at"] = now

    try:
        await db.document_metadata.update_one(
            {"id": doc_id_resolved},
            {"$set": update_fields},
        )
    except Exception as db_err:
        logger.error(f"[DJ-APPLY] Erro ao aplicar sugestões: {db_err}")
        raise HTTPException(
            status_code=500, detail="Erro ao aplicar sugestões"
        )

    logger.info(
        f"[DJ-APPLY] Doc {doc_id_resolved}: aplicados campos={fields}, "
        f"edited={is_edited}, by={user.get('id')}"
    )

    return {
        "success": True,
        "doc_id": doc_id_resolved,
        "applied_fields": fields,
        "status": update_fields["ai_review_status"],
        "reviewed_at": now,
        "reviewed_by": user.get("id"),
    }


# --------------------------------------------------------------------
# 2c. Rejeitar sugestões
# --------------------------------------------------------------------
async def run_reject_review(doc_id: str, body: dict, user: dict) -> dict:
    """
    PACOTE DJ — Rejeita sugestões da IA.

    Body (opcional):
        { "reason": "motivo da rejeição" }  # guardado em log apenas

    - Marca `ai_review_status='rejected'`.
    - Mantém `suggested_*` para auditoria (não limpa).
    - Não modifica `ai_*` (valores aplicados continuam como estão).
    """
    doc = await db.document_metadata.find_one(
        {"$or": [{"id": doc_id}, {"doc_id": doc_id}]}, {"_id": 0}
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Documento não encontrado")

    doc_id_resolved = doc.get("id") or doc_id
    now = datetime.now(timezone.utc).isoformat()
    reason = ""
    if isinstance(body, dict):
        reason = str(body.get("reason") or "")[:500]

    try:
        await db.document_metadata.update_one(
            {"id": doc_id_resolved},
            {
                "$set": {
                    "ai_review_status": "rejected",
                    "ai_reviewed_at": now,
                    "ai_reviewed_by": user.get("id"),
                    "updated_at": now,
                }
            },
        )
    except Exception as db_err:
        logger.error(f"[DJ-REJECT] Erro ao rejeitar sugestões: {db_err}")
        raise HTTPException(
            status_code=500, detail="Erro ao rejeitar sugestões"
        )

    logger.info(
        f"[DJ-REJECT] Doc {doc_id_resolved}: sugestões rejeitadas "
        f"by={user.get('id')} reason={reason!r}"
    )

    return {
        "success": True,
        "doc_id": doc_id_resolved,
        "status": "rejected",
        "reviewed_at": now,
        "reviewed_by": user.get("id"),
    }


# --------------------------------------------------------------------
# 2d. Listar documentos pendentes de revisão
# --------------------------------------------------------------------
async def run_get_pending_reviews(process_id: str, user: dict) -> dict:
    """
    PACOTE DJ — Lista documentos pendentes de revisão para um processo.

    Query: `{"process_id": process_id, "ai_review_status": "pending"}`.

    Retorna `{pending: [...], total: N}` com documentos sanitizados
    (inclui `suggested_*`, `current_*`, `filename`, `ai_confidence`).
    """
    cursor = db.document_metadata.find(
        {"process_id": process_id, "ai_review_status": "pending"},
        {"_id": 0},
    )
    pending_docs_raw = await cursor.to_list(2000)
    pending = [_sanitize_pending_doc(d) for d in pending_docs_raw]

    logger.info(
        f"[DJ-PENDING] Processo {process_id}: {len(pending)} docs pendentes "
        f"(requester={user.get('id')})"
    )

    return {
        "success": True,
        "process_id": process_id,
        "pending": pending,
        "total": len(pending),
    }

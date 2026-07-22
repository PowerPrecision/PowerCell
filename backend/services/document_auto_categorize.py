"""
Categorização automática em background após upload S3.

Extraído de `routes/documents.py` (`auto_categorize_document_background`).
Mantém-se re-exportado em `routes.documents` para testes que importam daí.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from database import db
from services.document_constants import DEFAULT_FILE_PREFIX, MIME_TYPE_PDF

logger = logging.getLogger(__name__)

_OCR_CATEGORIES = {
    "Identificação",
    "Identificacao",
    "Identidade",
    "Fiscal",
    "Financiamento",
    "Financeiros",
}

_DOC_TYPE_MAP = {
    "Identificação": "cc",
    "Identidade": "cc",
    "Identificacao": "cc",
    "Fiscal": "irs",
    "Financeiros": "irs",
    "Financiamento": "irs",
}


def should_run_ocr_for_category(ai_category: str) -> bool:
    """True se a categoria IA sugere OCR de entidades (CC/IRS/etc.)."""
    if ai_category in _OCR_CATEGORIES:
        return True
    lower = (ai_category or "").lower()
    return any(cat in lower for cat in ["ident", "fiscal", "financeiro", "cc", "irs"])


def build_auto_cat_metadata(
    *,
    doc_id: str,
    process_id: str,
    client_name: str,
    s3_path: str,
    filename: str,
    result: dict,
    extracted_text: str,
    extracted_data,
    file_content: bytes,
    now: str,
) -> dict:
    """Monta o documento de metadados pós-categorização IA."""
    return {
        "id": doc_id,
        "process_id": process_id,
        "client_name": client_name,
        "s3_path": s3_path,
        "filename": filename,
        "ai_category": result.get("category"),
        "ai_subcategory": result.get("subcategory"),
        "ai_confidence": result.get("confidence"),
        "ai_tags": result.get("tags", []),
        "ai_summary": result.get("summary"),
        "expiry_date": result.get("expiry_date"),
        "expiry_alert_sent": False,
        "extracted_text": extracted_text[:5000] if extracted_text else None,
        "extracted_data": extracted_data,
        "file_size": len(file_content),
        "mime_type": MIME_TYPE_PDF if filename.lower().endswith(".pdf") else None,
        "is_categorized": True,
        "categorized_at": now,
        "updated_at": now,
    }


async def auto_categorize_document_background(
    process_id: str,
    client_name: str,
    s3_path: str,
    filename: str,
    file_content: bytes,
):
    """
    Categoriza automaticamente um documento com IA em background,
    extraindo texto do PDF e aplicando classificação com GPT.

    Também executa OCR de entidades (Nome, NIF, Morada, Validade) quando
    a categoria sugere identificação/fiscal.

    Nunca propaga excepções (tarefa de background resiliente).
    """
    from services.document_categorization import (
        extract_text_from_pdf,
        categorize_document_with_ai,
    )

    try:
        logger.info("[AUTO-CAT] Iniciando categorização automática")

        existing = await db.document_metadata.find_one({"s3_path": s3_path}, {"_id": 0})

        extracted_text = ""
        if filename.lower().endswith(".pdf"):
            extracted_text = extract_text_from_pdf(file_content)

        text_for_analysis = (
            extracted_text if extracted_text else f"{DEFAULT_FILE_PREFIX}{filename}"
        )

        existing_categories = await db.document_metadata.distinct("ai_category")

        result = await categorize_document_with_ai(
            text_content=text_for_analysis,
            filename=filename,
            existing_categories=existing_categories,
        )

        if not result.get("success"):
            logger.warning("[AUTO-CAT] Falha ao categorizar documento")
            return

        now = datetime.now(timezone.utc).isoformat()
        doc_id = existing.get("id") if existing else str(uuid.uuid4())

        extracted_data = None
        ai_category = result.get("category", "")

        if should_run_ocr_for_category(ai_category) and len(file_content) > 0:
            try:
                from services.ai_document import analyze_document_from_base64
                import base64 as b64

                document_type = _DOC_TYPE_MAP.get(ai_category, "cc")
                b64_content = b64.b64encode(file_content).decode("utf-8")
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
                    logger.info(
                        f"[AUTO-CAT] OCR extraído: {list(extracted_data.keys())}"
                    )

                    if extracted_data:
                        process = await db.processes.find_one(
                            {"id": process_id}, {"_id": 0}
                        )
                        if process and not process.get("is_data_confirmed"):
                            from services.data_conflict import create_conflict_suggestions

                            await create_conflict_suggestions(
                                process_id, extracted_data, filename, doc_id
                            )
                else:
                    logger.info("[AUTO-CAT] OCR não retornou dados extraídos")
            except Exception as ocr_err:
                logger.warning(
                    f"[AUTO-CAT] Erro no OCR (não bloqueia categorização): {ocr_err}"
                )

        metadata = build_auto_cat_metadata(
            doc_id=doc_id,
            process_id=process_id,
            client_name=client_name,
            s3_path=s3_path,
            filename=filename,
            result=result,
            extracted_text=extracted_text,
            extracted_data=extracted_data,
            file_content=file_content,
            now=now,
        )

        if existing:
            await db.document_metadata.update_one({"id": doc_id}, {"$set": metadata})
            logger.info("[AUTO-CAT] Metadados actualizados")
        else:
            metadata["created_at"] = now
            await db.document_metadata.insert_one(metadata)
            logger.info("[AUTO-CAT] Metadados criados")

        # Após categorização IA, tentar satisfazer pedido portal pendente
        # (útil quando o upload staff foi para Index/Outros e só agora há categoria)
        try:
            from services.document_portal_fulfill import (
                fulfill_portal_requests_on_staff_upload,
            )

            fulfill_cat = (
                result.get("subcategory")
                or ai_category
                or result.get("category")
                or ""
            )
            await fulfill_portal_requests_on_staff_upload(
                process_id,
                category=fulfill_cat,
                filename=filename,
                s3_path=s3_path,
                user={"id": "system_auto_cat", "name": "Categorização IA"},
            )
        except Exception as fulfill_err:
            logger.warning(
                f"[AUTO-CAT] Portal fulfill skip: {type(fulfill_err).__name__}: {fulfill_err}"
            )

        logger.info("[AUTO-CAT] Categorização concluída")

    except Exception as e:
        logger.error(
            f"[AUTO-CAT] Erro ao categorizar documento: {type(e).__name__}: {e}"
        )

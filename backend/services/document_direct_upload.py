"""
Upload directo S3 via pre-signed URL + confirmação pós-PUT.

Extraído de `routes/documents.py` (`generate_upload_url`, `confirm_upload`).
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

from fastapi import BackgroundTasks, HTTPException

from database import db
from services.document_auto_categorize import auto_categorize_document_background
from services.document_constants import (
    DEFAULT_CLIENT_NAME,
    DEFAULT_FILE_PREFIX,
    ERROR_PROCESS_NOT_FOUND,
)
from services.document_filenames import normalize_filename, sanitize_for_log
from services.document_process_resolve import extract_second_client_name
from services.document_upload import _auto_fulfill_portal_request
from services.history import log_history
from services.s3_storage import s3_service

logger = logging.getLogger(__name__)


async def run_generate_upload_url(data: dict, *, user: dict) -> dict:
    """Gera pre-signed URL PUT para upload directo frontend → S3."""
    process_id = data.get("process_id")
    filename = data.get("filename")
    content_type = data.get("content_type")
    category = data.get("category", "Outros")
    custom_filename = data.get("custom_filename")

    if not process_id:
        raise HTTPException(status_code=400, detail="process_id é obrigatório")
    if not filename:
        raise HTTPException(status_code=400, detail="filename é obrigatório")
    if not content_type:
        raise HTTPException(status_code=400, detail="content_type é obrigatório")

    if not s3_service.is_configured():
        raise HTTPException(
            status_code=503,
            detail=(
                "Serviço de armazenamento S3 não configurado. "
                "Contacte o administrador."
            ),
        )

    process = await db.processes.find_one({"id": process_id})
    if not process:
        raise HTTPException(status_code=404, detail=ERROR_PROCESS_NOT_FOUND)

    client_name = process.get("client_name", DEFAULT_CLIENT_NAME)
    second_client_name = extract_second_client_name(process)
    s3_folder = process.get("s3_folder")

    if custom_filename:
        normalized_filename = normalize_filename(custom_filename, category)
    else:
        normalized_filename = normalize_filename(filename, category)

    result = s3_service.generate_upload_presigned_url(
        client_id=process_id,
        client_name=client_name,
        category=category,
        filename=normalized_filename,
        content_type=content_type,
        second_client_name=second_client_name,
        s3_folder=s3_folder,
        expiration=300,
    )

    if not result:
        raise HTTPException(
            status_code=500,
            detail="Erro ao gerar URL de upload. Por favor tente novamente.",
        )

    logger.info(
        f"[DIRECT-UPLOAD] URL gerada para {normalized_filename} "
        f"por {user.get('email')}"
    )

    return {
        "success": True,
        "upload_url": result["upload_url"],
        "file_key": result["file_key"],
        "normalized_filename": normalized_filename,
        "original_filename": filename,
        "expires_at": result["expires_at"],
        "expires_in_seconds": result["expires_in_seconds"],
        "method": "PUT",
        "headers": {"Content-Type": content_type},
    }


async def _triage_category_with_ai(
    *,
    category: str,
    original_filename: str,
    file_key: str,
) -> tuple[str, Optional[dict], Optional[bytes]]:
    """
    Se categoria for Outros/Auto, tenta triagem IA.

    Returns:
        (category, ai_categorization_detail|None, file_content|None)
    """
    ai_categorization_detail = None
    file_content = None

    if category.lower().strip() not in ("outros", "auto", "", "other"):
        return category, None, None

    try:
        from services.document_categorization import (
            extract_text_from_pdf,
            categorize_document_with_ai,
        )

        file_content = await asyncio.to_thread(s3_service.get_file_content, file_key)

        text_for_analysis = f"{DEFAULT_FILE_PREFIX}{original_filename}"
        if file_content and original_filename.lower().endswith(".pdf"):
            extracted = await asyncio.to_thread(
                extract_text_from_pdf, file_content, max_chars=3000
            )
            if extracted:
                text_for_analysis = extracted

        existing_categories = await db.document_metadata.distinct("ai_category")
        ai_result = await categorize_document_with_ai(
            text_content=text_for_analysis,
            filename=original_filename,
            existing_categories=existing_categories,
        )

        if ai_result.get("success") and ai_result.get("category"):
            ai_suggested = ai_result["category"]
            ai_categorization_detail = {
                "original_category": category or "Outros",
                "ai_category": ai_suggested,
                "ai_subcategory": ai_result.get("subcategory"),
                "ai_confidence": ai_result.get("confidence"),
            }
            category = ai_suggested
            logger.info(
                f"[CONFIRM-UPLOAD-IA] Categoria IA: {ai_suggested} "
                f"para {sanitize_for_log(original_filename)}"
            )
    except Exception as ai_err:
        logger.warning(f"[CONFIRM-UPLOAD-IA] Erro na triagem IA: {ai_err}")

    return category, ai_categorization_detail, file_content


async def run_confirm_upload(
    data: dict,
    *,
    background_tasks: BackgroundTasks,
    user: dict,
) -> dict:
    """Confirma PUT S3 e agenda auto-categorização + histórico."""
    process_id = data.get("process_id")
    file_key = data.get("file_key")
    original_filename = data.get("original_filename")
    category = data.get("category", "Outros")
    file_size = data.get("file_size")  # reserved / accepted from client
    content_type = data.get("content_type", "application/octet-stream")
    _ = (file_size, content_type)  # kept for API compat; not persisted here

    if not process_id:
        raise HTTPException(status_code=400, detail="process_id é obrigatório")
    if not file_key:
        raise HTTPException(status_code=400, detail="file_key é obrigatório")
    if not original_filename:
        raise HTTPException(status_code=400, detail="original_filename é obrigatório")

    process = await db.processes.find_one({"id": process_id})
    if not process:
        raise HTTPException(status_code=404, detail=ERROR_PROCESS_NOT_FOUND)

    client_name = process.get("client_name", DEFAULT_CLIENT_NAME)

    if not s3_service.file_exists(file_key):
        raise HTTPException(
            status_code=400,
            detail="Ficheiro não encontrado no S3. O upload pode ter falhado.",
        )

    normalized_filename = file_key.split("/")[-1] if "/" in file_key else file_key
    temporary_url = s3_service.get_presigned_url(file_key) or ""

    category, ai_categorization_detail, file_content = await _triage_category_with_ai(
        category=category,
        original_filename=original_filename,
        file_key=file_key,
    )

    if not file_content:
        try:
            file_content = s3_service.get_file_content(file_key)
        except Exception:
            pass

    try:
        if file_content:
            background_tasks.add_task(
                auto_categorize_document_background,
                process_id=process_id,
                client_name=client_name,
                s3_path=file_key,
                filename=normalized_filename,
                file_content=file_content,
            )
    except Exception as e:
        logger.warning(f"[CONFIRM-UPLOAD] Erro ao agendar categorização: {e}")

    try:
        await log_history(
            process_id=process_id,
            user=user,
            action="Carregou documento (upload direto)",
            field="documento",
            new_value=f"{normalized_filename} ({category})",
        )
    except Exception as e:
        logger.warning(f"[CONFIRM-UPLOAD] Erro ao registar histórico: {e}")

    # Auto-Match — o documento acabou de ser gravado (S3 + categoria); tenta
    # imediatamente satisfazer um pedido pendente do Portal do Cliente.
    portal_fulfill = await _auto_fulfill_portal_request(
        process_id,
        {
            "category": category,
            "filename": normalized_filename or original_filename,
            "s3_path": file_key,
            "content_type": content_type,
            "file_size": file_size,
        },
        user=user,
    )

    logger.info(f"[CONFIRM-UPLOAD] Upload confirmado: {normalized_filename}")

    response_data: dict[str, Any] = {
        "success": True,
        "s3_path": file_key,
        "normalized_filename": normalized_filename,
        "original_filename": original_filename,
        "category": category,
        "temporary_url": temporary_url,
        "message": "Upload registado com sucesso",
        "auto_categorization": "iniciada" if file_content else " indisponível",
        "portal_fulfilled": portal_fulfill.get("fulfilled", 0),
    }
    if ai_categorization_detail:
        response_data["ai_categorization"] = ai_categorization_detail

    return response_data

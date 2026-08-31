"""
Pipeline de upload S3 via backend (validação MIME, conversão, IA, histórico).

Extraído de `routes/documents.py` (`upload_file_s3`).
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from io import BytesIO
from typing import Any, Optional

from fastapi import BackgroundTasks, HTTPException

from database import db
from services.document_auto_categorize import auto_categorize_document_background
from services.document_constants import (
    DEFAULT_CLIENT_NAME,
    DEFAULT_FILE_PREFIX,
    ERROR_S3_UPLOAD_FAILED,
    MIME_TYPE_PDF,
)
from services.document_filenames import (
    is_image_file,
    normalize_filename,
    sanitize_for_log,
)
from services.document_process_resolve import (
    extract_second_client_name,
    resolve_process_from_flexible_id,
)
from services.document_processor import convert_image_to_pdf, IMG2PDF_AVAILABLE
from services.history import log_history
from services.s3_storage import s3_service

logger = logging.getLogger(__name__)


async def _auto_fulfill_portal_request(
    process_id: str,
    document: dict[str, Any],
    *,
    user: Optional[dict] = None,
) -> dict[str, Any]:
    """
    Auto-Match: assim que um documento interno é gravado (upload feito pela
    equipa no CRM), procura no processo um pedido do Portal do Cliente
    (`documents` com `status` REQUESTED/PENDING) cuja categoria ou tipo
    corresponda ao documento acabado de carregar.

    Quando há correspondência, actualiza esse pedido para o estado de
    sucesso equivalente ("RECEIVED" — o "submetido" do lado do cliente) e
    associa-lhe o `document_id` do ficheiro carregado, para que o Portal do
    Cliente deixe de mostrar o pedido como "Pendente".

    `document` deve conter: category, filename, s3_path, content_type,
    file_size e, opcionalmente, document_id (id do pedido específico a
    satisfazer directamente).

    Nunca propaga excepções — falha de matching não pode bloquear o upload.
    """
    try:
        from services.document_portal_fulfill import (
            fulfill_portal_requests_on_staff_upload,
        )

        result = await fulfill_portal_requests_on_staff_upload(
            process_id,
            category=document.get("category"),
            filename=document.get("filename"),
            s3_path=document.get("s3_path"),
            content_type=document.get("content_type"),
            file_size=document.get("file_size"),
            user=user,
            document_id=document.get("document_id"),
            linked_document_id=document.get("linked_document_id"),
        )

        # Observabilidade: o motor de auto-match falhou silenciosamente em
        # encontrar um pedido portal correspondente (sem excepção — é um
        # comportamento normal quando não há pedido pendente). Registamos um
        # aviso estruturado para dar visibilidade aos admins sobre estas
        # falhas de correspondência, sem bloquear o upload.
        reason = result.get("reason")
        if reason in ("weak_match", "no_match"):
            logger.warning(
                "[PORTAL-FULFILL] Falha de correspondência automática "
                f"reason={reason} process_id={process_id} "
                f"category={document.get('category')!r} "
                f"filename={sanitize_for_log(document.get('filename') or '')!r} "
                f"user={(user or {}).get('id') or 'staff'}"
            )

        return result
    except Exception as e:
        logger.warning(
            f"[UPLOAD] Erro ao marcar pedido portal como recebido: {e}"
        )
        return {"fulfilled": 0, "document_ids": []}


async def _validate_and_maybe_convert(
    file_content: bytes,
    original_filename: str,
    content_type: str,
) -> tuple[bytes, str, str, bool, bool, bool, dict]:
    """
    Validação MIME + conversão automática + fallback imagem→PDF.

    Returns:
        (content, filename, content_type, converted_to_pdf, was_extracted,
         was_converted, conversion_info)
    """
    from services.file_validation import validate_and_convert_file

    was_extracted = False
    was_converted = False
    conversion_info: dict = {}

    try:
        validated_content, detected_mime, _mime_description, conversion_info = (
            validate_and_convert_file(
                file_content, original_filename, auto_convert=True
            )
        )
        was_extracted = conversion_info.get("was_extracted", False)
        was_converted = conversion_info.get("was_converted", False)

        if was_extracted or was_converted:
            logger.info(
                f"[UPLOAD] Ficheiro processado: {sanitize_for_log(original_filename)} "
                f"(extraído: {was_extracted}, convertido: {was_converted}, "
                f"método: {conversion_info.get('conversion_method') or conversion_info.get('extraction_method')})"
            )
            file_content = validated_content
            content_type = detected_mime
            if detected_mime == MIME_TYPE_PDF and not original_filename.lower().endswith(
                ".pdf"
            ):
                original_filename = (
                    original_filename.rsplit(".", 1)[0] + ".pdf"
                    if "." in original_filename
                    else original_filename + ".pdf"
                )
    except HTTPException as e:
        logger.warning(
            f"[UPLOAD] Ficheiro rejeitado: {sanitize_for_log(original_filename)} "
            f"- {e.detail}"
        )
        raise
    except Exception as e:
        logger.warning(
            f"[UPLOAD] Erro na validação/conversão, usando ficheiro original: {e}"
        )

    converted_to_pdf = was_converted
    if (
        not was_converted
        and is_image_file(original_filename, content_type)
        and IMG2PDF_AVAILABLE
    ):
        try:
            logger.info(
                f"[UPLOAD] A converter imagem para PDF: "
                f"{sanitize_for_log(original_filename)}"
            )
            pdf_bytes, new_filename = await convert_image_to_pdf(
                file_content, original_filename
            )
            if new_filename != original_filename:
                file_content = pdf_bytes
                original_filename = new_filename
                content_type = MIME_TYPE_PDF
                converted_to_pdf = True
                logger.info(
                    f"[UPLOAD] Conversão concluída: {sanitize_for_log(new_filename)}"
                )
        except (IOError, OSError, ValueError, KeyError, TypeError) as e:
            logger.warning(
                f"[UPLOAD] Não foi possível converter imagem para PDF: {e}"
            )

    ext_lower = (
        original_filename.lower().rsplit(".", 1)[-1]
        if "." in original_filename
        else ""
    )
    if ext_lower in ["heic", "heif"] and not converted_to_pdf:
        logger.info(
            f"[UPLOAD] Ficheiro HEIC/HEIF aceite: "
            f"{sanitize_for_log(original_filename)}"
        )

    return (
        file_content,
        original_filename,
        content_type,
        converted_to_pdf,
        was_extracted,
        was_converted,
        conversion_info,
    )


async def _triage_upload_category(
    category: str,
    original_filename: str,
    file_content: bytes,
) -> tuple[str, Optional[dict]]:
    """Triagem IA quando categoria é Outros/Auto. Returns (category, detail)."""
    auto_categorization_detail = None
    needs_ai = category.lower().strip() in ("outros", "auto", "", "other")
    if not needs_ai:
        return category, None

    try:
        from services.document_categorization import (
            extract_text_from_pdf,
            categorize_document_with_ai,
        )

        text_for_analysis = f"{DEFAULT_FILE_PREFIX}{original_filename}"
        if original_filename.lower().endswith(".pdf") and len(file_content) > 0:
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
            auto_categorization_detail = {
                "original_category": category or "Outros",
                "ai_category": ai_suggested,
                "ai_subcategory": ai_result.get("subcategory"),
                "ai_confidence": ai_result.get("confidence"),
            }
            category = ai_suggested
            logger.info(
                f"[UPLOAD-IA] Categoria IA: {ai_suggested} "
                f"(confiança: {ai_result.get('confidence', 0):.0%}) "
                f"para {sanitize_for_log(original_filename)}"
            )
        else:
            logger.warning(
                "[UPLOAD-IA] IA não conseguiu categorizar, "
                "a usar 'Outros' como fallback"
            )
            category = category or "Outros"
    except Exception as ai_err:
        logger.warning(
            f"[UPLOAD-IA] Erro na triagem IA (fallback para 'Outros'): {ai_err}"
        )
        category = category or "Outros"

    return category, auto_categorization_detail


async def run_upload_file_s3(
    client_id: str,
    *,
    file_content: bytes,
    original_filename: str,
    content_type: str,
    category: str,
    empresa_nif: Optional[str],
    custom_filename: Optional[str],
    user: dict,
    background_tasks: BackgroundTasks,
    client_original_filename: Optional[str] = None,
) -> dict[str, Any]:
    """
    Pipeline completo de upload S3.

    Returns:
        Payload JSON do upload (sem JSONResponse — a rota envolve se necessário).
    """
    if not s3_service.is_configured():
        raise HTTPException(
            status_code=503,
            detail=(
                "Serviço de armazenamento S3 não configurado. "
                "Contacte o administrador para configurar as credenciais AWS."
            ),
        )

    process, effective_id = await resolve_process_from_flexible_id(
        client_id,
        log_prefix="[UPLOAD]",
        allow_client_without_process=False,
        raise_on_client_without_process=True,
    )
    client_id = effective_id

    if empresa_nif:
        personal_data = process.get("personal_data", {})
        personal_data["employer_nif"] = empresa_nif
        await db.processes.update_one(
            {"id": client_id},
            {"$set": {"personal_data": personal_data}},
        )

    client_name = process.get("client_name", DEFAULT_CLIENT_NAME)
    second_client_name = extract_second_client_name(process)
    s3_folder = process.get("s3_folder")

    (
        file_content,
        original_filename,
        content_type,
        converted_to_pdf,
        was_extracted,
        was_converted,
        conversion_info,
    ) = await _validate_and_maybe_convert(
        file_content, original_filename, content_type
    )

    category, auto_categorization_detail = await _triage_upload_category(
        category, original_filename, file_content
    )

    if custom_filename:
        normalized_filename = normalize_filename(custom_filename, category)
        logger.info(
            f"Nome personalizado usado: {sanitize_for_log(normalized_filename)}"
        )
    else:
        normalized_filename = normalize_filename(original_filename, category)
        logger.info(f"Nome normalizado: {sanitize_for_log(normalized_filename)}")

    file_buffer = BytesIO(file_content)
    s3_path = s3_service.upload_file(
        file_buffer,
        client_id,
        client_name,
        category,
        normalized_filename,
        content_type,
        second_client_name=second_client_name,
        s3_folder=s3_folder,
    )

    if not s3_path:
        raise HTTPException(status_code=500, detail=ERROR_S3_UPLOAD_FAILED)

    try:
        temporary_url = s3_service.get_presigned_url(s3_path) or ""
    except Exception as e:
        logger.warning(f"[UPLOAD] Erro ao gerar URL temporário: {e}")
        temporary_url = ""

    try:
        file_content_copy = bytes(file_content)
        background_tasks.add_task(
            auto_categorize_document_background,
            process_id=client_id,
            client_name=client_name,
            s3_path=s3_path,
            filename=normalized_filename,
            file_content=file_content_copy,
        )
    except Exception as e:
        logger.warning(f"[UPLOAD] Erro ao agendar categorização: {e}")

    try:
        await log_history(
            process_id=client_id,
            user=user,
            action="Carregou documento",
            field="documento",
            new_value=f"{normalized_filename} ({category})",
        )
    except Exception as e:
        logger.warning(f"[UPLOAD] Erro ao registar histórico: {e}")

    # Auto-Match — o documento acabou de ser gravado (S3 + categoria); tenta
    # imediatamente satisfazer um pedido pendente do Portal do Cliente.
    portal_fulfill = await _auto_fulfill_portal_request(
        client_id,
        {
            "category": category,
            "filename": normalized_filename,
            "s3_path": s3_path,
            "content_type": content_type,
            "file_size": len(file_content) if file_content else None,
        },
        user=user,
    )

    logger.info(f"[UPLOAD] Upload concluído com sucesso: {normalized_filename}")

    response_data: dict[str, Any] = {
        "success": True,
        "path": s3_path,
        "message": "Ficheiro guardado com sucesso",
        "original_filename": client_original_filename,
        "normalized_filename": normalized_filename,
        "converted_to_pdf": converted_to_pdf,
        "was_extracted": was_extracted,
        "was_converted": was_converted,
        "conversion_method": conversion_info.get("conversion_method"),
        "auto_categorization": "iniciada",
        "temporary_url": temporary_url,
        "category": category,
        "portal_fulfilled": portal_fulfill.get("fulfilled", 0),
    }
    if auto_categorization_detail:
        response_data["ai_categorization"] = auto_categorization_detail
    return response_data

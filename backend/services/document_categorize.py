"""
Categorização IA on-demand (um doc ou todos os do processo).

Extraído de `routes/documents.py` (`categorize_document`, `categorize_all_documents`).
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException

from database import db
from services.document_constants import (
    DEFAULT_CLIENT_NAME,
    DEFAULT_FILE_PREFIX,
    ERROR_CATEGORIZE_DOC,
    ERROR_PROCESS_NOT_FOUND,
    ERROR_S3_ACCESS,
    ERROR_S3_FILE_NOT_FOUND,
    MIME_TYPE_PDF,
)
from services.document_categorization import (
    categorize_document_with_ai,
    extract_text_from_pdf,
)
from services.document_process_resolve import extract_second_client_name
from services.s3_storage import s3_service

logger = logging.getLogger(__name__)


def build_category_metadata(
    *,
    doc_id: str,
    process_id: str,
    client_name: str,
    s3_path: str,
    filename: str,
    result: dict,
    extracted_text: str,
    file_content: bytes,
    now: str,
    include_mime: bool = True,
) -> dict:
    meta = {
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
        "file_size": len(file_content),
        "is_categorized": True,
        "categorized_at": now,
        "updated_at": now,
    }
    if include_mime:
        meta["mime_type"] = (
            MIME_TYPE_PDF if filename.lower().endswith(".pdf") else None
        )
    return meta


async def run_categorize_document(
    process_id: str,
    *,
    s3_path: str,
    filename: str,
) -> dict[str, Any]:
    """Categoriza um documento S3 com IA e persiste metadados."""
    process = await db.processes.find_one({"id": process_id}, {"_id": 0})
    if not process:
        raise HTTPException(status_code=404, detail=ERROR_PROCESS_NOT_FOUND)

    client_name = process.get("client_name", DEFAULT_CLIENT_NAME)
    now = datetime.now(timezone.utc).isoformat()
    existing = await db.document_metadata.find_one({"s3_path": s3_path}, {"_id": 0})

    try:
        file_content = s3_service.get_file_content(s3_path)
        if not file_content:
            raise HTTPException(status_code=404, detail=ERROR_S3_FILE_NOT_FOUND)
    except HTTPException:
        raise
    except (IOError, OSError, ValueError, KeyError, TypeError) as e:
        logger.error(f"Erro ao obter ficheiro do S3: {e}")
        raise HTTPException(status_code=500, detail=ERROR_S3_ACCESS)

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
        raise HTTPException(
            status_code=500, detail=result.get("error", ERROR_CATEGORIZE_DOC)
        )

    doc_id = existing.get("id") if existing else str(uuid.uuid4())
    metadata = build_category_metadata(
        doc_id=doc_id,
        process_id=process_id,
        client_name=client_name,
        s3_path=s3_path,
        filename=filename,
        result=result,
        extracted_text=extracted_text,
        file_content=file_content,
        now=now,
    )

    if existing:
        await db.document_metadata.update_one({"id": doc_id}, {"$set": metadata})
    else:
        metadata["created_at"] = now
        await db.document_metadata.insert_one(metadata)

    return {
        "success": True,
        "id": doc_id,
        "category": result.get("category"),
        "subcategory": result.get("subcategory"),
        "confidence": result.get("confidence"),
        "tags": result.get("tags", []),
        "summary": result.get("summary"),
        "expiry_date": result.get("expiry_date"),
    }


async def run_categorize_all_documents(process_id: str) -> dict[str, Any]:
    """Categoriza todos os ficheiros S3 ainda não categorizados do processo."""
    process = await db.processes.find_one({"id": process_id}, {"_id": 0})
    if not process:
        raise HTTPException(status_code=404, detail=ERROR_PROCESS_NOT_FOUND)

    client_name = process.get("client_name", DEFAULT_CLIENT_NAME)
    second_client_name = extract_second_client_name(process)

    loop = asyncio.get_event_loop()
    files_data = await loop.run_in_executor(
        None,
        lambda: s3_service.list_files(
            process_id, client_name, second_client_name
        ),
    )
    files = files_data.get("files", {})

    results: dict[str, Any] = {
        "total": 0,
        "categorized": 0,
        "skipped": 0,
        "errors": 0,
        "documents": [],
    }
    existing_categories = await db.document_metadata.distinct("ai_category")
    now = datetime.now(timezone.utc).isoformat()

    for _category, file_list in files.items():
        for file_info in file_list:
            results["total"] += 1
            s3_path = file_info.get("path")
            filename = file_info.get("name")
            if not s3_path or not filename:
                continue

            existing = await db.document_metadata.find_one(
                {"s3_path": s3_path, "is_categorized": True},
                {"_id": 0},
            )
            if existing:
                results["skipped"] += 1
                results["documents"].append(
                    {
                        "filename": filename,
                        "status": "skipped",
                        "category": existing.get("ai_category"),
                    }
                )
                continue

            try:
                file_content = s3_service.get_file_content(s3_path)
                if not file_content:
                    results["errors"] += 1
                    continue

                extracted_text = ""
                if filename.lower().endswith(".pdf"):
                    extracted_text = extract_text_from_pdf(file_content)
                text_for_analysis = (
                    extracted_text
                    if extracted_text
                    else f"{DEFAULT_FILE_PREFIX}{filename}"
                )

                result = await categorize_document_with_ai(
                    text_content=text_for_analysis,
                    filename=filename,
                    existing_categories=existing_categories,
                )

                if result.get("success"):
                    doc_id = str(uuid.uuid4())
                    metadata = build_category_metadata(
                        doc_id=doc_id,
                        process_id=process_id,
                        client_name=client_name,
                        s3_path=s3_path,
                        filename=filename,
                        result=result,
                        extracted_text=extracted_text,
                        file_content=file_content,
                        now=now,
                        include_mime=False,
                    )
                    metadata["created_at"] = now
                    await db.document_metadata.insert_one(metadata)

                    if (
                        result.get("category")
                        and result["category"] not in existing_categories
                    ):
                        existing_categories.append(result["category"])

                    results["categorized"] += 1
                    results["documents"].append(
                        {
                            "filename": filename,
                            "status": "categorized",
                            "category": result.get("category"),
                            "subcategory": result.get("subcategory"),
                            "expiry_date": result.get("expiry_date"),
                        }
                    )
                else:
                    results["errors"] += 1
                    results["documents"].append(
                        {
                            "filename": filename,
                            "status": "error",
                            "error": result.get("error"),
                        }
                    )
            except (IOError, OSError, ValueError, KeyError, TypeError) as e:
                logger.error("Erro ao categorizar documento")
                results["errors"] += 1
                results["documents"].append(
                    {"filename": filename, "status": "error", "error": str(e)}
                )

    return results

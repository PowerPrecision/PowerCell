"""
Queries de listagem/metadados/pesquisa/categorias de documentos.

Extraído de `routes/documents.py`.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any, Optional

from fastapi import HTTPException

from database import db
from services.document_constants import (
    DEFAULT_CLIENT_NAME,
    ERROR_PROCESS_NOT_FOUND,
)
from services.document_process_resolve import extract_second_client_name
from services.s3_storage import s3_service

logger = logging.getLogger(__name__)


def serialize_metadata_doc(doc: dict) -> dict:
    s3_path = doc.get("s3_path", "")
    return {
        "id": doc.get("id") or str(uuid.uuid4()),
        "filename": doc.get("filename"),
        "original_name": doc.get("filename"),
        "category": doc.get("ai_category"),
        "subcategory": doc.get("ai_subcategory"),
        "s3_path": s3_path,
        "file_size": doc.get("file_size"),
        "upload_date": doc.get("created_at") or doc.get("categorized_at"),
        "mime_type": doc.get("mime_type"),
    }


async def run_get_process_documents(process_id: str) -> dict[str, Any]:
    """Lista docs (metadata + fallback S3) para modal de envio a balcões."""
    process = await db.processes.find_one({"id": process_id}, {"_id": 0})
    if not process:
        raise HTTPException(status_code=404, detail=ERROR_PROCESS_NOT_FOUND)

    metadata_docs = await db.document_metadata.find(
        {"process_id": process_id}, {"_id": 0}
    ).to_list(1000)

    documents = []
    existing_s3_paths: set[str] = set()
    for doc in metadata_docs:
        s3_path = doc.get("s3_path", "")
        if s3_path:
            existing_s3_paths.add(s3_path)
        documents.append(serialize_metadata_doc(doc))

    if s3_service.is_configured():
        try:
            client_name = process.get("client_name", DEFAULT_CLIENT_NAME)
            second_client_name = extract_second_client_name(process)
            s3_folder = process.get("s3_folder")
            loop = asyncio.get_event_loop()
            files_result = await loop.run_in_executor(
                None,
                lambda: s3_service.list_files(
                    process_id, client_name, second_client_name, s3_folder
                ),
            )
            if isinstance(files_result, dict) and files_result.get("error"):
                logger.warning(f"[DOCS-PROCESS] S3 error: {files_result['error']}")
            elif isinstance(files_result, dict) and files_result.get("files"):
                for category, files in files_result["files"].items():
                    if not isinstance(files, list):
                        continue
                    for f in files:
                        s3_path = f.get("path") or f.get("key") or ""
                        filename = f.get("name") or f.get("filename") or ""
                        if s3_path and s3_path not in existing_s3_paths:
                            existing_s3_paths.add(s3_path)
                            documents.append(
                                {
                                    "id": str(uuid.uuid4()),
                                    "filename": filename,
                                    "original_name": filename,
                                    "category": category if category != "Outros" else None,
                                    "s3_path": s3_path,
                                    "file_size": f.get("size"),
                                    "upload_date": f.get("last_modified"),
                                    "mime_type": None,
                                }
                            )
        except Exception as e:
            logger.warning(f"[DOCS-PROCESS] Fallback S3 falhou: {e}")

    return {
        "process_id": process_id,
        "client_name": process.get("client_name"),
        "documents": documents,
        "total": len(documents),
    }


async def run_get_document_metadata(process_id: str) -> dict[str, Any]:
    process = await db.processes.find_one({"id": process_id}, {"_id": 0})
    if not process:
        raise HTTPException(status_code=404, detail=ERROR_PROCESS_NOT_FOUND)

    metadata_list = await db.document_metadata.find(
        {"process_id": process_id},
        {"_id": 0, "extracted_text": 0},
    ).to_list(1000)

    for doc in metadata_list:
        s3_path = doc.get("s3_path")
        if s3_path:
            doc["temporary_url"] = s3_service.get_presigned_url(s3_path) or ""

    categories = await db.document_metadata.distinct(
        "ai_category",
        {"process_id": process_id, "ai_category": {"$ne": None}},
    )
    return {
        "process_id": process_id,
        "client_name": process.get("client_name"),
        "documents": metadata_list,
        "total": len(metadata_list),
        "categorized": sum(1 for d in metadata_list if d.get("is_categorized")),
        "categories": sorted(categories),
    }


async def run_search_documents(request) -> dict[str, Any]:
    from services.document_categorization import search_documents_by_content

    query: dict[str, Any] = {"is_categorized": True}
    if request.process_id:
        query["process_id"] = request.process_id
    if request.categories:
        query["ai_category"] = {"$in": request.categories}

    documents = await db.document_metadata.find(query, {"_id": 0}).to_list(1000)
    results = await search_documents_by_content(
        query=request.query,
        process_id=request.process_id,
        documents=documents,
        limit=request.limit,
    )
    for doc in results:
        s3_path = doc.get("s3_path")
        if s3_path:
            doc["temporary_url"] = s3_service.get_presigned_url(s3_path) or ""

    return {
        "query": request.query,
        "total_results": len(results),
        "results": results,
    }


async def run_get_all_categories(process_id: Optional[str] = None) -> dict[str, Any]:
    query: dict[str, Any] = {"ai_category": {"$ne": None}}
    if process_id:
        query["process_id"] = process_id

    pipeline = [
        {"$match": query},
        {"$group": {"_id": "$ai_category", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]
    category_counts = await db.document_metadata.aggregate(pipeline).to_list(100)
    return {
        "categories": [
            {"name": cat["_id"], "count": cat["count"]}
            for cat in category_counts
            if cat["_id"]
        ],
        "total_categories": len(category_counts),
    }

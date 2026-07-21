"""
Renomeação inteligente de documentos (IA / manual).

Extraído de `routes/documents.py` (`rename_document_smart`,
`rename_all_documents_smart`).
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException

from database import db
from services.document_constants import (
    DEFAULT_CLIENT_NAME,
    ERROR_DOC_NOT_CATEGORIZED,
    ERROR_NEW_NAME_REQUIRED,
    ERROR_PROCESS_NOT_FOUND,
    ERROR_RENAME_FAILED,
    ERROR_S3_PATH_REQUIRED,
)
from services.document_filenames import generate_smart_filename
from services.s3_storage import s3_service

logger = logging.getLogger(__name__)


def resolve_smart_new_filename(
    *,
    old_filename: str,
    apply_ai_name: bool,
    novo_nome: str | None,
    metadata: dict | None,
    client_name: str,
) -> str:
    """Calcula o novo nome (IA ou manual) preservando extensão."""
    original_ext = (
        old_filename.rsplit(".", 1)[-1] if "." in old_filename else "pdf"
    )

    if apply_ai_name:
        if not metadata or not metadata.get("is_categorized"):
            raise HTTPException(
                status_code=400, detail=ERROR_DOC_NOT_CATEGORIZED
            )
        return generate_smart_filename(
            category=metadata.get("ai_category", "Documento"),
            subcategory=metadata.get("ai_subcategory", ""),
            client_name=client_name,
            expiry_date=metadata.get("expiry_date"),
            original_extension=original_ext,
        )

    if not novo_nome:
        raise HTTPException(status_code=400, detail=ERROR_NEW_NAME_REQUIRED)
    if not novo_nome.endswith(f".{original_ext}"):
        return f"{novo_nome}.{original_ext}"
    return novo_nome


def build_renamed_s3_path(s3_path: str, new_filename: str) -> str:
    if "/" in s3_path:
        return f"{s3_path.rsplit('/', 1)[0]}/{new_filename}"
    return new_filename


async def run_rename_document_smart(
    process_id: str,
    data: dict,
) -> dict[str, Any]:
    """Renomeia um documento (nome IA ou manual)."""
    s3_path = data.get("s3_path")
    apply_ai_name = data.get("apply_ai_name", True)
    novo_nome = data.get("novo_nome")

    if not s3_path:
        raise HTTPException(status_code=400, detail=ERROR_S3_PATH_REQUIRED)

    process = await db.processes.find_one({"id": process_id}, {"_id": 0})
    if not process:
        raise HTTPException(status_code=404, detail=ERROR_PROCESS_NOT_FOUND)

    client_name = process.get("client_name", DEFAULT_CLIENT_NAME)
    old_filename = s3_path.rsplit("/", 1)[-1] if "/" in s3_path else s3_path
    metadata = await db.document_metadata.find_one({"s3_path": s3_path}, {"_id": 0})

    new_filename = resolve_smart_new_filename(
        old_filename=old_filename,
        apply_ai_name=apply_ai_name,
        novo_nome=novo_nome,
        metadata=metadata,
        client_name=client_name,
    )
    new_path = build_renamed_s3_path(s3_path, new_filename)

    if new_path == s3_path:
        return {
            "success": True,
            "old_name": old_filename,
            "new_name": new_filename,
            "new_path": new_path,
            "message": "Ficheiro já tem o nome correcto",
        }

    try:
        loop = asyncio.get_event_loop()
        success = await loop.run_in_executor(
            None, lambda: s3_service.rename_file(s3_path, new_path)
        )
        if not success:
            raise HTTPException(status_code=500, detail=ERROR_RENAME_FAILED)

        if metadata:
            await db.document_metadata.update_one(
                {"s3_path": s3_path},
                {
                    "$set": {
                        "s3_path": new_path,
                        "filename": new_filename,
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    }
                },
            )

        logger.info("Documento renomeado")
        return {
            "success": True,
            "old_name": old_filename,
            "new_name": new_filename,
            "new_path": new_path,
            "message": "Documento renomeado com sucesso",
        }
    except HTTPException:
        raise
    except (IOError, OSError, ValueError, KeyError, TypeError) as e:
        logger.error(f"Erro ao renomear documento: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def run_rename_all_documents_smart(process_id: str) -> dict[str, Any]:
    """Renomeia todos os docs já categorizados do processo."""
    process = await db.processes.find_one({"id": process_id}, {"_id": 0})
    if not process:
        raise HTTPException(status_code=404, detail=ERROR_PROCESS_NOT_FOUND)

    client_name = process.get("client_name", DEFAULT_CLIENT_NAME)
    documents = await db.document_metadata.find(
        {"process_id": process_id, "is_categorized": True},
        {"_id": 0},
    ).to_list(500)

    results: dict[str, Any] = {
        "total": len(documents),
        "renamed": 0,
        "skipped": 0,
        "errors": 0,
        "details": [],
    }

    for doc in documents:
        s3_path = doc.get("s3_path")
        if not s3_path:
            results["skipped"] += 1
            continue

        old_filename = doc.get("filename", s3_path.rsplit("/", 1)[-1])
        original_ext = (
            old_filename.rsplit(".", 1)[-1] if "." in old_filename else "pdf"
        )
        new_filename = generate_smart_filename(
            category=doc.get("ai_category", "Documento"),
            subcategory=doc.get("ai_subcategory", ""),
            client_name=client_name,
            expiry_date=doc.get("expiry_date"),
            original_extension=original_ext,
        )
        new_path = build_renamed_s3_path(s3_path, new_filename)

        if new_path == s3_path:
            results["skipped"] += 1
            results["details"].append(
                {
                    "file": old_filename,
                    "status": "skipped",
                    "reason": "Nome já correcto",
                }
            )
            continue

        try:
            loop = asyncio.get_event_loop()
            success = await loop.run_in_executor(
                None,
                lambda s=s3_path, n=new_path: s3_service.rename_file(s, n),
            )
            if success:
                await db.document_metadata.update_one(
                    {"s3_path": s3_path},
                    {
                        "$set": {
                            "s3_path": new_path,
                            "filename": new_filename,
                            "updated_at": datetime.now(timezone.utc).isoformat(),
                        }
                    },
                )
                results["renamed"] += 1
                results["details"].append(
                    {
                        "file": old_filename,
                        "new_name": new_filename,
                        "status": "renamed",
                    }
                )
            else:
                results["errors"] += 1
                results["details"].append(
                    {
                        "file": old_filename,
                        "status": "error",
                        "reason": "Falha no S3",
                    }
                )
        except (IOError, OSError, ValueError, KeyError, TypeError) as e:
            results["errors"] += 1
            results["details"].append(
                {"file": old_filename, "status": "error", "reason": str(e)}
            )

    return results

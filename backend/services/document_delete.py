"""
Eliminação S3 com protecção de scope global + bulk delete.

Extraído de `routes/documents.py` (`delete_file_s3`, `bulk_delete_files`).
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import HTTPException
from fastapi.responses import JSONResponse

from database import db
from services.document_constants import ERROR_DELETE_FILE
from services.document_process_resolve import (
    assert_s3_file_belongs_to_process,
    build_s3_valid_prefixes,
    resolve_process_from_flexible_id,
)
from services.history import log_history
from services.s3_storage import s3_service

logger = logging.getLogger(__name__)


def process_references_document(
    other_proc: dict,
    *,
    file_path: str,
    doc_id: str | None,
) -> bool:
    """True se outro processo referencia o doc (document_ids/required/checklist/s3)."""
    doc_ids = other_proc.get("document_ids") or []
    required_docs = other_proc.get("required_documents") or []
    checklist = other_proc.get("checklist") or []

    if file_path in doc_ids or (doc_id and doc_id in doc_ids):
        return True

    if isinstance(required_docs, list):
        for req_doc in required_docs:
            if isinstance(req_doc, dict):
                if req_doc.get("s3_path") == file_path or req_doc.get("id") == doc_id:
                    return True
            elif isinstance(req_doc, str) and (
                req_doc == file_path or req_doc == doc_id
            ):
                return True

    if isinstance(checklist, list):
        for check_item in checklist:
            if isinstance(check_item, dict):
                if (
                    check_item.get("s3_path") == file_path
                    or check_item.get("document_id") == doc_id
                ):
                    return True

    other_s3_folder = other_proc.get("s3_folder")
    if other_s3_folder and file_path.startswith(other_s3_folder.rstrip("/") + "/"):
        return True

    return False


async def _assert_no_cross_process_refs(
    *,
    client_id: str,
    file_path: str,
    process: dict,
    doc_metadata: dict | None,
) -> None:
    doc_scope = doc_metadata.get("doc_scope") if doc_metadata else None
    doc_client_id = doc_metadata.get("client_id") if doc_metadata else None

    if not (
        doc_scope == "global" or (doc_client_id and doc_client_id != client_id)
    ):
        return

    effective_client_id = doc_client_id or process.get("client_id") or client_id
    other_processes = await db.processes.find(
        {
            "client_id": effective_client_id,
            "id": {"$ne": client_id},
            "is_deleted": {"$ne": True},
            "status": {"$nin": ["eliminados", "desistencias"]},
        },
        {
            "_id": 0,
            "id": 1,
            "process_number": 1,
            "client_name": 1,
            "status": 1,
            "document_ids": 1,
            "required_documents": 1,
            "checklist": 1,
            "s3_folder": 1,
        },
    ).to_list(100)

    doc_id = doc_metadata.get("id") if doc_metadata else None
    for other_proc in other_processes:
        if process_references_document(
            other_proc, file_path=file_path, doc_id=doc_id
        ):
            proc_number = other_proc.get("process_number", "N/A")
            proc_name = other_proc.get("client_name", "Cliente")
            raise HTTPException(
                status_code=409,
                detail=(
                    "Não é possível eliminar: Este documento está a ser utilizado "
                    f"no Processo #{proc_number} ({proc_name})."
                ),
            )


async def run_delete_file_s3(
    client_id: str,
    file_path: str,
    *,
    user: dict,
) -> JSONResponse:
    """Elimina ficheiro S3 + metadados com protecção de scope cruzado."""
    process, _effective_id = await resolve_process_from_flexible_id(
        client_id,
        log_prefix="[DELETE]",
        client_without_process_detail=(
            "Cliente encontrado mas sem processo associado. "
            "Não é possível eliminar ficheiros."
        ),
    )

    if file_path.endswith("/"):
        raise HTTPException(
            status_code=400,
            detail=(
                "Caminho inválido: não pode eliminar pastas. "
                "Selecione um ficheiro específico."
            ),
        )

    assert_s3_file_belongs_to_process(file_path, process)

    doc_metadata = await db.document_metadata.find_one(
        {"s3_path": file_path}, {"_id": 0}
    )
    await _assert_no_cross_process_refs(
        client_id=client_id,
        file_path=file_path,
        process=process,
        doc_metadata=doc_metadata,
    )

    filename = file_path.split("/")[-1] if "/" in file_path else file_path
    success = s3_service.delete_file(file_path)
    if not success:
        raise HTTPException(status_code=500, detail=ERROR_DELETE_FILE)

    if doc_metadata:
        await db.document_metadata.delete_one({"s3_path": file_path})

    await log_history(
        process_id=client_id,
        user=user,
        action="Eliminou documento",
        field="documento",
        old_value=filename,
    )

    return JSONResponse(
        status_code=200,
        content={"success": True, "message": "Ficheiro eliminado"},
    )


async def run_bulk_delete_files(
    client_id: str,
    data: dict,
    *,
    user: dict,
) -> JSONResponse:
    """Elimina múltiplos ficheiros S3 (paths no scope do processo)."""
    file_paths = data.get("file_paths", [])
    if not file_paths or not isinstance(file_paths, list) or len(file_paths) == 0:
        raise HTTPException(
            status_code=400, detail="Lista de ficheiros vazia ou inválida"
        )

    process, _effective_id = await resolve_process_from_flexible_id(
        client_id,
        log_prefix="[DELETE-BATCH]",
    )
    valid_prefixes = build_s3_valid_prefixes(process)

    deleted_count = 0
    failed_files: list[str] = []

    for file_path in file_paths:
        if file_path.endswith("/"):
            continue
        if not any(file_path.startswith(prefix) for prefix in valid_prefixes):
            failed_files.append(file_path)
            continue
        try:
            if s3_service.delete_file(file_path):
                deleted_count += 1
            else:
                failed_files.append(file_path)
        except Exception as e:
            logger.warning(f"Erro ao eliminar ficheiro {file_path}: {e}")
            failed_files.append(file_path)

    if deleted_count > 0:
        await log_history(
            process_id=client_id,
            user=user,
            action="Eliminou documentos em massa",
            field="documento",
            old_value=f"{deleted_count} ficheiro(s)",
        )

    result: dict[str, Any] = {
        "success": True,
        "deleted_count": deleted_count,
        "total_requested": len(file_paths),
    }
    if failed_files:
        result["failed_count"] = len(failed_files)
        result["failed_files"] = failed_files

    return JSONResponse(status_code=200, content=result)

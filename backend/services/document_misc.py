"""
Endpoints auxiliares de documentos (check-file, NIF empregador, download URL, init folders).

Extraído de `routes/documents.py`.
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

from fastapi import HTTPException, UploadFile

from database import db
from services.document_constants import (
    DEFAULT_CLIENT_NAME,
    ERROR_DOWNLOAD_URL,
    ERROR_S3_FILE_NOT_FOUND,
)
from services.document_process_resolve import (
    assert_s3_file_belongs_to_process,
    extract_second_client_name,
    resolve_process_from_flexible_id,
)
from services.document_s3_paths import s3_path_variations
from services.s3_storage import s3_service

logger = logging.getLogger(__name__)


async def run_check_file_upload(file: UploadFile) -> dict[str, Any]:
    """Pré-valida ficheiro (tipo detectado + conversão possível)."""
    from services.file_converter import can_convert_file, detect_file_type

    try:
        file_content = await file.read()
        filename = file.filename
        if not file_content or len(file_content) == 0:
            return {
                "can_upload": False,
                "reason": "Ficheiro vazio",
                "filename": filename,
            }

        detected_mime, detected_ext, confidence = detect_file_type(file_content)
        conversion_check = can_convert_file(file_content, filename)
        file_size_mb = len(file_content) / (1024 * 1024)
        return {
            "can_upload": conversion_check["can_convert"] is not False,
            "filename": filename,
            "file_size_mb": round(file_size_mb, 2),
            "detected_type": detected_mime,
            "detected_extension": detected_ext,
            "confidence": confidence,
            "conversion_info": conversion_check,
            "recommendation": conversion_check.get(
                "suggested_action", "Pode fazer upload diretamente"
            ),
        }
    except Exception as e:
        logger.error(f"[CHECK-FILE] Erro: {e}")
        raise HTTPException(
            status_code=500, detail=f"Erro ao verificar ficheiro: {str(e)}"
        )


async def run_initialize_folders(client_id: str) -> dict[str, Any]:
    process, effective_id = await resolve_process_from_flexible_id(
        client_id,
        log_prefix="[INIT-FOLDERS]",
        client_without_process_detail=(
            "Cliente encontrado mas sem processo associado. "
            "Não é possível inicializar pastas."
        ),
    )
    existing_s3_folder = process.get("s3_folder")
    if existing_s3_folder and s3_service._folder_exists(existing_s3_folder):
        logger.info(
            f"Pasta S3 já existe para cliente {client_id}: {existing_s3_folder}"
        )
        return {
            "success": True,
            "s3_folder": existing_s3_folder,
            "already_exists": True,
        }

    client_name = process.get("client_name", DEFAULT_CLIENT_NAME)
    second_client_name = extract_second_client_name(process)
    success, s3_folder_path = s3_service.initialize_client_folders(
        effective_id, client_name, second_client_name=second_client_name
    )
    if success and s3_folder_path:
        await db.processes.update_one(
            {"id": effective_id},
            {"$set": {"s3_folder": s3_folder_path}},
        )
    return {"success": success, "s3_folder": s3_folder_path}


async def run_get_download_url(client_id: str, file_path: str) -> dict[str, Any]:
    process, _effective_id = await resolve_process_from_flexible_id(
        client_id,
        log_prefix="[DOWNLOAD]",
        client_without_process_detail=(
            "Cliente encontrado mas sem processo associado. "
            "Não é possível gerar link de download."
        ),
    )
    assert_s3_file_belongs_to_process(file_path, process)
    url = s3_service.get_presigned_url(file_path)
    if not url:
        raise HTTPException(status_code=500, detail=ERROR_DOWNLOAD_URL)
    return {"success": True, "url": url}


async def run_get_download_url_by_path(file_path: str) -> dict[str, Any]:
    loop = asyncio.get_event_loop()
    for path in s3_path_variations(file_path):
        exists = await loop.run_in_executor(
            None, lambda p=path: s3_service.file_exists(p)
        )
        if exists:
            url = s3_service.get_presigned_url(path)
            if url:
                logger.info(f"[DOWNLOAD-URL] URL gerado para: {path}")
                return {"url": url, "path": path}
    logger.warning(
        f"[DOWNLOAD-URL] Ficheiro não encontrado "
        f"(tentadas variações): {file_path}"
    )
    raise HTTPException(status_code=404, detail=ERROR_S3_FILE_NOT_FOUND)


async def run_check_employer_nif(nif: str) -> dict[str, Any]:
    if not re.match(r"^\d{9}$", nif):
        raise HTTPException(
            status_code=400,
            detail="NIF inválido. Deve conter exatamente 9 dígitos.",
        )

    processes = await db.processes.find(
        {
            "$or": [
                {"personal_data.employer_nif": nif},
                {
                    "personal_data.nif": nif,
                    "personal_data.nif": {"$regex": "^5"},
                },
            ]
        },
        {
            "_id": 0,
            "id": 1,
            "client_name": 1,
            "status": 1,
            "created_at": 1,
            "personal_data.employer_name": 1,
            "personal_data.employer_nif": 1,
            "consultor_name": 1,
            "mediador_name": 1,
        },
    ).to_list(100)

    workflow_statuses = await db.workflow_statuses.find(
        {}, {"_id": 0, "name": 1, "label": 1, "color": 1}
    ).to_list(100)
    status_map = {s["name"]: s for s in workflow_statuses}

    results = []
    for proc in processes:
        status_info = status_map.get(proc.get("status"), {})
        results.append(
            {
                "id": proc.get("id"),
                "client_name": proc.get("client_name"),
                "employer_name": proc.get("personal_data", {}).get("employer_name"),
                "status": proc.get("status"),
                "status_label": status_info.get("label", proc.get("status")),
                "status_color": status_info.get("color", "#6B7280"),
                "consultor_name": proc.get("consultor_name"),
                "mediador_name": proc.get("mediador_name"),
                "created_at": proc.get("created_at"),
            }
        )

    return {
        "nif": nif,
        "exists": len(results) > 0,
        "total_count": len(results),
        "processes": results,
    }

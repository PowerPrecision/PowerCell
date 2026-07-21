"""
Verificação de conflitos de nome antes de upload S3.

Extraído de `routes/documents.py` (`check_upload_conflict`).
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import HTTPException

from database import db
from services.document_constants import (
    DEFAULT_CLIENT_NAME,
    ERROR_PROCESS_NOT_FOUND,
)
from services.document_filenames import normalize_filename
from services.s3_storage import s3_service, sanitize_folder_name

logger = logging.getLogger(__name__)


def resolve_upload_base_path(
    process: dict,
    process_id: str,
) -> str:
    """Caminho base S3 do processo (s3_folder ou path derivado)."""
    s3_folder = process.get("s3_folder")
    if s3_folder:
        return s3_folder.rstrip("/")

    client_name = process.get("client_name", DEFAULT_CLIENT_NAME)
    second_client_name = (
        process.get("second_client_name") or process.get("titular2", {}).get("nome")
    )
    return s3_service._get_client_base_path_for_upload(
        process_id, client_name, second_client_name
    )


def suggest_alternate_filenames(
    *,
    base_path: str,
    safe_category: str,
    normalized: str,
    max_suggestions: int = 3,
) -> list[dict]:
    """Gera nomes `name_2.ext` … que ainda não existem no S3."""
    name_part, ext = (
        normalized.rsplit(".", 1) if "." in normalized else (normalized, "pdf")
    )
    suggested = []
    for i in range(2, 2 + max_suggestions):
        new_name = f"{name_part}_{i}.{ext}"
        new_path = f"{base_path}/{safe_category}/{new_name}"
        if not s3_service.file_exists(new_path):
            suggested.append({"filename": new_name, "path": new_path})
    return suggested


def find_filename_conflicts(
    *,
    filenames: list[str],
    base_path: str,
    category: str,
) -> list[dict]:
    """Lista conflitos de path para cada filename normalizado."""
    safe_category = sanitize_folder_name(category)
    conflicts = []
    for filename in filenames:
        normalized = normalize_filename(filename, category)
        target_path = f"{base_path}/{safe_category}/{normalized}"
        if s3_service.file_exists(target_path):
            conflicts.append(
                {
                    "original_filename": filename,
                    "normalized_filename": normalized,
                    "existing_path": target_path,
                    "existing_size": None,
                    "suggested_names": suggest_alternate_filenames(
                        base_path=base_path,
                        safe_category=safe_category,
                        normalized=normalized,
                    ),
                }
            )
    return conflicts


async def run_check_upload_conflict(data: dict) -> dict:
    """
    Verifica conflitos de nomes ANTES do upload.

    Body esperado: process_id, filenames[], category (opcional).
    """
    process_id = data.get("process_id")
    filenames = data.get("filenames", [])
    category = data.get("category", "Outros")

    if not process_id or not filenames:
        raise HTTPException(
            status_code=400, detail="process_id e filenames são obrigatórios"
        )

    process = await db.processes.find_one({"id": process_id}, {"_id": 0})
    if not process:
        raise HTTPException(status_code=404, detail=ERROR_PROCESS_NOT_FOUND)

    base_path = resolve_upload_base_path(process, process_id)
    conflicts = find_filename_conflicts(
        filenames=filenames, base_path=base_path, category=category
    )

    return {
        "has_conflicts": len(conflicts) > 0,
        "conflict_count": len(conflicts),
        "total_files": len(filenames),
        "conflicts": conflicts,
        "base_path": base_path,
        "category": category,
    }

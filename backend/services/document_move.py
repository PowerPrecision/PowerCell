"""
Verificação de conflito e move/rename de ficheiros S3 por categoria.

Extraído de `routes/documents.py` (`check_move_conflict`, `move_file_to_category`).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import HTTPException

from database import db
from services.document_constants import ERROR_PROCESS_NOT_FOUND
from services.document_upload_conflict import (
    resolve_upload_base_path,
    suggest_alternate_filenames,
)
from services.history import log_history
from services.s3_storage import s3_service, sanitize_folder_name

logger = logging.getLogger(__name__)


def build_move_target_path(
    *,
    base_path: str,
    source_path: str,
    target_category: str | None,
    target_filename: str | None,
) -> tuple[str, str, str]:
    """
    Returns:
        (target_path, safe_category, final_filename)
    """
    current_filename = source_path.split("/")[-1] if "/" in source_path else source_path
    current_category_part = source_path.split("/")[-2] if "/" in source_path else ""

    if target_category:
        safe_category = sanitize_folder_name(target_category)
    elif current_category_part:
        safe_category = current_category_part
    else:
        safe_category = "Outros"

    final_filename = target_filename if target_filename else current_filename
    target_path = f"{base_path}/{safe_category}/{final_filename}"
    return target_path, safe_category, final_filename


async def run_check_move_conflict(data: dict) -> dict:
    """Verifica conflito ao mover/renomear um ficheiro no S3."""
    process_id = data.get("process_id")
    source_path = data.get("source_path")
    target_category = data.get("target_category")
    target_filename = data.get("target_filename")

    if not process_id or not source_path:
        raise HTTPException(
            status_code=400, detail="process_id e source_path são obrigatórios"
        )

    process = await db.processes.find_one({"id": process_id}, {"_id": 0})
    if not process:
        raise HTTPException(status_code=404, detail=ERROR_PROCESS_NOT_FOUND)

    base_path = resolve_upload_base_path(process, process_id)
    target_path, safe_category, final_filename = build_move_target_path(
        base_path=base_path,
        source_path=source_path,
        target_category=target_category,
        target_filename=target_filename,
    )

    if target_path == source_path:
        return {
            "has_conflict": False,
            "target_path": target_path,
            "message": "O ficheiro já está no destino pretendido",
        }

    if s3_service.file_exists(target_path):
        suggested = suggest_alternate_filenames(
            base_path=base_path,
            safe_category=safe_category,
            normalized=final_filename,
        )
        return {
            "has_conflict": True,
            "source_path": source_path,
            "conflict_path": target_path,
            "conflict_filename": final_filename,
            "suggested_names": suggested,
            "message": (
                f"Já existe um ficheiro chamado '{final_filename}' no destino"
            ),
        }

    return {
        "has_conflict": False,
        "target_path": target_path,
        "message": "Nenhum conflito detectado",
    }


def _auto_rename_path(base_path: str, safe_category: str, final_filename: str) -> str:
    name_part, ext = (
        final_filename.rsplit(".", 1)
        if "." in final_filename
        else (final_filename, "pdf")
    )
    counter = 2
    while s3_service.file_exists(
        f"{base_path}/{safe_category}/{name_part}_{counter}.{ext}"
    ):
        counter += 1
        if counter > 100:
            raise HTTPException(
                status_code=409,
                detail="Não foi possível gerar um nome único para o ficheiro",
            )
    return f"{name_part}_{counter}.{ext}"


async def run_move_file_to_category(
    process_id: str,
    data: dict,
    *,
    user: dict,
) -> dict:
    """Move (e opcionalmente renomeia) um ficheiro S3 para outra categoria."""
    source_path = data.get("source_path")
    target_category = data.get("target_category")
    target_filename = data.get("target_filename")
    overwrite = data.get("overwrite", False)
    auto_rename = data.get("auto_rename", False)

    if not source_path or not target_category:
        raise HTTPException(
            status_code=400, detail="source_path e target_category são obrigatórios"
        )

    process = await db.processes.find_one({"id": process_id}, {"_id": 0})
    if not process:
        raise HTTPException(status_code=404, detail=ERROR_PROCESS_NOT_FOUND)

    base_path = resolve_upload_base_path(process, process_id)

    current_filename = source_path.split("/")[-1] if "/" in source_path else source_path
    final_filename = target_filename if target_filename else current_filename
    safe_category = sanitize_folder_name(target_category)
    new_path = f"{base_path}/{safe_category}/{final_filename}"

    if new_path == source_path:
        return {
            "success": True,
            "message": "Ficheiro já está na categoria correta",
            "new_path": new_path,
            "was_renamed": False,
        }

    conflict_exists = s3_service.file_exists(new_path)
    was_renamed = False

    if conflict_exists and not overwrite:
        if auto_rename:
            final_filename = _auto_rename_path(
                base_path, safe_category, final_filename
            )
            new_path = f"{base_path}/{safe_category}/{final_filename}"
            was_renamed = True
            logger.info(
                f"Ficheiro renomeado automaticamente para evitar conflito: "
                f"{final_filename}"
            )
        else:
            suggested = suggest_alternate_filenames(
                base_path=base_path,
                safe_category=safe_category,
                normalized=final_filename,
            )
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "FILE_EXISTS",
                    "message": (
                        f"Já existe um ficheiro chamado '{final_filename}' "
                        "no destino"
                    ),
                    "conflict_path": new_path,
                    "suggested_names": [s["filename"] for s in suggested],
                },
            )

    success = s3_service.rename_file(source_path, new_path)

    if not success:
        raise HTTPException(status_code=500, detail="Erro ao mover ficheiro")

    await db.document_metadata.update_one(
        {"s3_path": source_path},
        {
            "$set": {
                "s3_path": new_path,
                "ai_category": target_category,
                "filename": final_filename,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        },
    )

    action_msg = f"Moveu documento para {target_category}"
    if was_renamed:
        action_msg += f" (renomeado para {final_filename})"

    await log_history(
        process_id=process_id,
        user=user,
        action=action_msg,
        field="documento",
        old_value=current_filename,
        new_value=final_filename,
    )

    logger.info(f"Ficheiro movido: {source_path} -> {new_path}")

    return {
        "success": True,
        "message": f"Ficheiro movido para {target_category}",
        "new_path": new_path,
        "old_path": source_path,
        "new_filename": final_filename,
        "was_renamed": was_renamed,
    }

"""AI import log create/update/finalize helpers.

Extraído de `routes/ai_import_logs.py`.
Do **not** overwrite services/admin_ai_data.py (admin AI import logs).
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from database import db
from models.ai_import_log import ImportStatus

logger = logging.getLogger(__name__)


async def create_ai_import_log(
    process_id: str,
    client_name: str,
    created_by: str = None,
    created_by_name: str = None
) -> str:
    """Cria um novo log de importação IA. Returns ID do log criado."""
    log_id = str(uuid.uuid4())

    log = {
        "id": log_id,
        "process_id": process_id,
        "client_name": client_name,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": created_by,
        "created_by_name": created_by_name,
        "status": ImportStatus.PENDING.value,
        "total_documents": 0,
        "success_count": 0,
        "error_count": 0,
        "partial_count": 0,
        "duration_ms": None,
        "documents": [],
        "auto_filled_fields": {},
        "conflict_resolutions": [],
        "notes": None
    }

    await db.ai_import_logs.insert_one(log)
    logger.info(f"Log de importação IA criado: {log_id} para cliente {client_name}")

    return log_id


async def update_ai_import_log(
    log_id: str,
    document_result: dict = None,
    status: str = None,
    auto_filled_fields: dict = None,
    duration_ms: int = None,
    notes: str = None
):
    """Actualiza um log de importação IA."""
    update = {"$set": {}}

    if document_result:
        await db.ai_import_logs.update_one(
            {"id": log_id},
            {
                "$push": {"documents": document_result},
                "$inc": {
                    "total_documents": 1,
                    "success_count": 1 if document_result.get("status") == "success" else 0,
                    "error_count": 1 if document_result.get("status") == "error" else 0,
                    "partial_count": 1 if document_result.get("status") == "partial" else 0
                }
            }
        )

    if status:
        update["$set"]["status"] = status

    if auto_filled_fields:
        update["$set"]["auto_filled_fields"] = auto_filled_fields

    if duration_ms is not None:
        update["$set"]["duration_ms"] = duration_ms

    if notes:
        update["$set"]["notes"] = notes

    if update["$set"]:
        await db.ai_import_logs.update_one({"id": log_id}, update)


async def finalize_ai_import_log(log_id: str, duration_ms: int):
    """Finaliza um log de importação calculando o status final."""
    log = await db.ai_import_logs.find_one({"id": log_id})

    if not log:
        return

    if log["error_count"] == log["total_documents"]:
        final_status = ImportStatus.ERROR.value
    elif log["error_count"] > 0:
        final_status = ImportStatus.PARTIAL.value
    else:
        final_status = ImportStatus.SUCCESS.value

    await db.ai_import_logs.update_one(
        {"id": log_id},
        {"$set": {
            "status": final_status,
            "duration_ms": duration_ms
        }}
    )

    logger.info(f"Log de importação IA finalizado: {log_id} - Status: {final_status}")

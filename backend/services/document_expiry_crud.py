"""
CRUD de validades manuais (`document_expiries`) + upcoming/calendar.

Extraído de `routes/documents.py`. Distinto de `document_expiring_dashboard`
(que usa `document_metadata.expiry_date`).
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

from fastapi import HTTPException

from database import db
from models.auth import UserRole
from models.document import DocumentExpiryCreate, DocumentExpiryResponse
from services.document_constants import ERROR_PROCESS_NOT_FOUND, ERROR_RECORD_NOT_FOUND
from utils.input_sanitization import sanitize_string

logger = logging.getLogger(__name__)

EXPIRY_WARNING_DAYS = 60

DOCUMENT_TYPES = [
    {"type": "cc", "name": "Cartão de Cidadão", "validity_years": 5},
    {"type": "irs", "name": "Declaração de IRS", "validity_years": 1},
    {"type": "recibo", "name": "Recibo Vencimento", "validity_months": 3},
    {"type": "outro", "name": "Outro", "validity_years": None},
]


async def run_create_document_expiry(
    data: DocumentExpiryCreate, *, user: dict
) -> DocumentExpiryResponse:
    process = await db.processes.find_one({"id": data.process_id})
    if not process:
        raise HTTPException(status_code=404, detail=ERROR_PROCESS_NOT_FOUND)

    doc_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    sanitized_document_name = (
        sanitize_string(data.document_name, max_length=300)
        if data.document_name
        else data.document_name
    )
    sanitized_notes = (
        sanitize_string(data.notes, max_length=1000) if data.notes else data.notes
    )
    doc = {
        "id": doc_id,
        "process_id": data.process_id,
        "document_type": data.document_type,
        "document_name": sanitized_document_name,
        "expiry_date": data.expiry_date,
        "notes": sanitized_notes,
        "created_at": now,
        "created_by": user["id"],
    }
    await db.document_expiries.insert_one(doc)
    return DocumentExpiryResponse(**{k: v for k, v in doc.items() if k != "_id"})


async def run_get_document_expiries(
    process_id: Optional[str], *, user: dict
) -> list[DocumentExpiryResponse]:
    query: dict[str, Any] = {}
    if process_id:
        query["process_id"] = process_id
    elif user["role"] == UserRole.CONSULTOR:
        processes = await db.processes.find(
            {"assigned_consultor_id": user["id"]}, {"id": 1}
        ).to_list(1000)
        query["process_id"] = {"$in": [p["id"] for p in processes]}
    elif user["role"] == UserRole.INTERMEDIARIO:
        processes = await db.processes.find(
            {"assigned_mediador_id": user["id"]}, {"id": 1}
        ).to_list(1000)
        query["process_id"] = {"$in": [p["id"] for p in processes]}

    docs = await db.document_expiries.find(query, {"_id": 0}).to_list(1000)
    return [DocumentExpiryResponse(**d) for d in docs]


async def run_get_upcoming_expiries(
    days: int = EXPIRY_WARNING_DAYS, *, user: dict
) -> list[dict]:
    today = datetime.now(timezone.utc).date()
    future_date = today + timedelta(days=days)
    excluded_statuses = ["concluido", "desistencia", "desistência"]

    query: dict[str, Any] = {
        "expiry_date": {"$gte": today.isoformat(), "$lte": future_date.isoformat()}
    }
    if user["role"] == UserRole.CONSULTOR:
        procs = await db.processes.find(
            {
                "$or": [
                    {"assigned_consultor_id": user["id"]},
                    {"consultor_id": user["id"]},
                ]
            },
            {"id": 1},
        ).to_list(1000)
        query["process_id"] = {"$in": [p["id"] for p in procs]} if procs else {"$in": []}

    docs = (
        await db.document_expiries.find(query, {"_id": 0})
        .sort("expiry_date", 1)
        .to_list(1000)
    )

    result = []
    for doc in docs:
        process = await db.processes.find_one({"id": doc["process_id"]}, {"_id": 0})
        if process and process.get("status", "").lower() not in excluded_statuses:
            expiry = datetime.strptime(doc["expiry_date"], "%Y-%m-%d").date()
            days_until = (expiry - today).days
            result.append(
                {
                    **doc,
                    "client_name": process.get("client_name"),
                    "days_until_expiry": days_until,
                    "urgency": (
                        "critical"
                        if days_until <= 7
                        else "warning"
                        if days_until <= 30
                        else "normal"
                    ),
                }
            )
    return result


async def run_get_expiry_calendar_events(*, user: dict) -> list[dict]:
    upcoming = await run_get_upcoming_expiries(
        days=EXPIRY_WARNING_DAYS, user=user
    )
    events = []
    for doc in upcoming:
        color = (
            "#EF4444"
            if doc["urgency"] == "critical"
            else "#F59E0B"
            if doc["urgency"] == "warning"
            else "#3B82F6"
        )
        events.append(
            {
                "id": f"doc-expiry-{doc['id']}",
                "title": f"📄 {doc['document_name']} - {doc['client_name']}",
                "date": doc["expiry_date"],
                "color": color,
            }
        )
    return events


async def run_delete_document_expiry(doc_id: str) -> dict:
    delete_result = await db.document_expiries.delete_one({"id": doc_id})
    if delete_result.deleted_count == 0:
        raise HTTPException(status_code=404, detail=ERROR_RECORD_NOT_FOUND)
    return {"message": "Eliminado"}

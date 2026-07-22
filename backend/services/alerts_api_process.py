"""Alerts process / check handlers.

Extraído de `routes/alerts.py`.
Do **not** overwrite services/alerts.py — use alerts_api_*.
"""
from __future__ import annotations

from fastapi import HTTPException

from database import db
from services.alerts import (
    get_process_alerts,
    check_age_alert,
    check_pre_approval_countdown,
    check_document_expiry_alerts,
    check_property_documents,
    create_deed_reminder,
)


async def _get_process_or_404(process_id: str) -> dict:
    process = await db.processes.find_one({"id": process_id}, {"_id": 0})
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")
    return process


async def run_get_alerts_for_process(process_id: str):
    process = await _get_process_or_404(process_id)
    alerts = await get_process_alerts(process)
    return {
        "process_id": process_id,
        "client_name": process.get("client_name"),
        "status": process.get("status"),
        "alerts": alerts,
        "total_alerts": len(alerts),
        "has_critical": any(a.get("priority") == "critical" for a in alerts),
        "has_high": any(a.get("priority") == "high" for a in alerts)
    }


async def run_check_age_eligibility(process_id: str):
    process = await _get_process_or_404(process_id)
    return check_age_alert(process)


async def run_get_pre_approval_countdown(process_id: str):
    process = await _get_process_or_404(process_id)
    return await check_pre_approval_countdown(process)


async def run_get_document_alerts(process_id: str):
    process = await _get_process_or_404(process_id)
    doc_alerts = await check_document_expiry_alerts(process_id)
    return {
        "process_id": process_id,
        "alerts": doc_alerts,
        "total": len(doc_alerts)
    }


async def run_check_property_docs(process_id: str):
    process = await _get_process_or_404(process_id)
    return await check_property_documents(process)


async def run_create_deed_reminder(process_id: str, deed_date: str, user: dict):
    process = await _get_process_or_404(process_id)
    deadline_id = await create_deed_reminder(process, deed_date, user)
    if deadline_id:
        return {
            "success": True,
            "deadline_id": deadline_id,
            "message": "Lembrete de escritura criado com sucesso"
        }
    return {
        "success": False,
        "message": "Não foi possível criar o lembrete (data pode já ter passado)"
    }

"""Associate lead to client/process endpoint.

Extraído de `routes/leads.py`.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException

from database import db


async def run_associate_client(
    lead_id: str,
    client_id: str,
    user: dict,
):
    """Associar um lead a um cliente/processo."""
    # Verificar se lead existe
    lead = await db.property_leads.find_one({"id": lead_id})
    if not lead:
        raise HTTPException(status_code=404, detail="Lead não encontrado")

    # Verificar se cliente existe
    process = await db.processes.find_one({"id": client_id})
    if not process:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")

    now = datetime.now(timezone.utc).isoformat()

    # Actualizar lead
    await db.property_leads.update_one(
        {"id": lead_id},
        {
            "$set": {"client_id": client_id, "updated_at": now},
            "$push": {
                "history": {
                    "timestamp": now,
                    "event": f"Associado ao cliente {process.get('client_name')}",
                    "user": user.get("email")
                }
            }
        }
    )

    return {
        "success": True,
        "message": f"Lead associado a {process.get('client_name')}"
    }

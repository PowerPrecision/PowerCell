"""PACOTE DH — Eventos visíveis ao cliente no Portal.

Endpoint consumido pelo Portal do Cliente para listar prazos/eventos da
agenda marcados como `visible_to_client=True`, não concluídos e com
`due_date >= hoje`. Ordenados por `due_date` ascendente.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from database import db

logger = logging.getLogger(__name__)

# PACOTE DH — Opções válidas de reminder_time (espelho de models/deadline.py).
VALID_REMINDER_TIMES = {"1h", "3h", "1d", "3d", "7d"}


async def run_get_portal_events(client_data: dict) -> dict:
    """
    Retorna eventos/prazos visíveis ao cliente (visible_to_client=True),
    não concluídos, com due_date >= hoje. Ordenados por due_date asc.

    Args:
        client_data: Dict injetado por `get_current_client` com
            {process_id, process, token_payload}.

    Returns:
        {"events": [...], "total": int} — campos sanitizados (sem _id nem
        assigned_user_ids) para não expor internals ao cliente.
    """
    process_id = client_data.get("process_id")
    if not process_id:
        # Sem processo associado não há eventos para mostrar.
        return {"events": [], "total": 0}

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    cursor = db.deadlines.find(
        {
            "process_id": process_id,
            "visible_to_client": True,
            "completed": {"$ne": True},
            "due_date": {"$gte": today},
        },
        {"_id": 0},
    ).sort("due_date", 1).limit(20)

    deadlines = await cursor.to_list(length=20)

    # Sanitizar — expor apenas campos client-friendly (sem internals).
    events = []
    for d in deadlines:
        events.append({
            "id": d.get("id"),
            "title": d.get("title", ""),
            "description": d.get("description", ""),
            "due_date": d.get("due_date", ""),
            # PACOTE DH — default "deadline" para documentos antigos sem `type`.
            "type": d.get("type", "deadline"),
            "priority": d.get("priority", "medium"),
        })

    return {"events": events, "total": len(events)}

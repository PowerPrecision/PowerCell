"""PACOTE DH — Eventos visíveis ao cliente no Portal.

Endpoint consumido pelo Portal do Cliente para listar prazos/eventos da
agenda marcados como `visible_to_client=True`, não concluídos.

PACOTE DO.2: `include_past=True` devolve também datas anteriores (calendário
mensal). O default continua a ser só `due_date >= hoje` (lista "Próximos").
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from database import db

logger = logging.getLogger(__name__)

# PACOTE DH — Opções válidas de reminder_time (espelho de models/deadline.py).
VALID_REMINDER_TIMES = {"1h", "3h", "1d", "3d", "7d"}


def build_portal_events_filter(
    process_id: str,
    today: str,
    *,
    include_past: bool = False,
) -> dict:
    """Filtro Mongo para eventos do portal (só visible_to_client)."""
    query: dict = {
        "process_id": process_id,
        "visible_to_client": True,
        "completed": {"$ne": True},
    }
    if not include_past:
        query["due_date"] = {"$gte": today}
    return query


def serialize_portal_event(doc: dict) -> dict:
    """Campos client-friendly (sem _id nem assigned_user_ids)."""
    return {
        "id": doc.get("id"),
        "title": doc.get("title", ""),
        "description": doc.get("description", ""),
        "due_date": doc.get("due_date", ""),
        # PACOTE DH — default "deadline" para documentos antigos sem `type`.
        "type": doc.get("type", "deadline"),
        "priority": doc.get("priority", "medium"),
    }


async def run_get_portal_events(
    client_data: dict,
    *,
    include_past: bool = False,
) -> dict:
    """
    Retorna eventos/prazos visíveis ao cliente (visible_to_client=True),
    não concluídos. Por omissão só due_date >= hoje. Ordenados por due_date asc.

    Args:
        client_data: Dict injetado por `get_current_client` com
            {process_id, process, token_payload}.
        include_past: Se True, inclui datas anteriores (calendário visual).

    Returns:
        {"events": [...], "total": int} — campos sanitizados (sem _id nem
        assigned_user_ids) para não expor internals ao cliente.
    """
    process_id = client_data.get("process_id")
    if not process_id:
        # Sem processo associado não há eventos para mostrar.
        return {"events": [], "total": 0}

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    query = build_portal_events_filter(
        process_id, today, include_past=include_past
    )

    cursor = db.deadlines.find(query, {"_id": 0}).sort("due_date", 1).limit(100)
    deadlines = await cursor.to_list(length=100)

    events = [serialize_portal_event(d) for d in deadlines]
    return {"events": events, "total": len(events)}

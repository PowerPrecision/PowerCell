"""Kanban board + single visit get.

Extraído de `routes/visits.py`.
"""
from __future__ import annotations

from typing import Optional

from fastapi import HTTPException

from database import db


async def run_get_visits_kanban(user: dict, *, consultor_id: Optional[str] = None):
    """
    Retorna visitas organizadas por estado para o Quadro de Visitas.
    Colunas: solicitada, agendada, concluida, cancelada
    """
    query = {}

    # RBAC
    user_role = (user.get("role") or "").lower()
    if user_role in ["consultor", "intermediario"]:
        query["$or"] = [
            {"consultor_id": user.get("id")},
            {"consultor_ids": user.get("id")},
        ]
    elif consultor_id:
        query["consultor_id"] = consultor_id

    visits = await db.visits.find(query, {"_id": 0, "scraped_data.raw_data": 0}).sort("scheduled_date", 1).to_list(200)

    solicitadas = [v for v in visits if v.get("status") == "solicitada"]
    agendadas = [v for v in visits if v.get("status") == "agendada"]
    concluidas = [v for v in visits if v.get("status") == "concluida"]
    canceladas = [v for v in visits if v.get("status") in ("cancelada", "recusada")]

    return {
        "solicitadas": solicitadas,
        "agendadas": agendadas,
        "concluidas": concluidas,
        "canceladas": canceladas,
        "total": len(visits),
    }


async def run_get_visit(visit_id: str, user: dict):
    """Obtém detalhe de uma visita."""
    visit = await db.visits.find_one({"id": visit_id}, {"_id": 0, "scraped_data.raw_data": 0})
    if not visit:
        raise HTTPException(status_code=404, detail="Visita não encontrada")
    return visit

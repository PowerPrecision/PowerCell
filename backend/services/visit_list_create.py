"""List + create CRM visits.

Extraído de `routes/visits.py`.
"""
from __future__ import annotations

import uuid
import logging
import asyncio
from typing import Optional
from datetime import datetime, timezone

from fastapi import HTTPException

from database import db
from services.visit_helpers import (
    _create_calendar_event_for_visit,
    _update_portal_visit_status,
    _run_scraper_for_visit,
)

logger = logging.getLogger(__name__)


async def run_list_visits(
    user: dict,
    *,
    status: Optional[str] = None,
    consultor_id: Optional[str] = None,
    property_id: Optional[str] = None,
    client_id: Optional[str] = None,
    process_id: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
):
    """
    Lista visitas com filtros opcionais.
    Consultores só vêem as suas visitas; admins/ceo/diretores vêem todas.
    Suporta filtro por process_id para a aba de Visitas no ProcessDetailsModal.
    """
    query = {}

    # Filtros
    if status:
        query["status"] = status

    if consultor_id:
        query["consultor_id"] = consultor_id
    if property_id:
        query["property_id"] = property_id
    if client_id:
        query["client_id"] = client_id
    if process_id:
        # Suportar ambos: client_id (legacy) e process_id (novo)
        query["$or"] = [
            {"client_id": process_id},
            {"process_id": process_id},
        ]

    # Filtro por data
    if date_from or date_to:
        date_query = {}
        if date_from:
            date_query["$gte"] = date_from
        if date_to:
            date_query["$lte"] = date_to
        query["scheduled_date"] = date_query

    # RBAC: consultores e intermediários só vêem as suas visitas
    user_role = (user.get("role") or "").lower()
    if user_role in ["consultor", "intermediario"]:
        rbac_filter = [
            {"consultor_id": user.get("id")},
            {"consultor_ids": user.get("id")},
        ]
        # Se já tem $or (do process_id), combinar com $and
        if "$or" in query:
            or_clause = query.pop("$or")
            query["$and"] = [
                {"$or": or_clause},
                {"$or": rbac_filter},
            ]
        else:
            query["$or"] = rbac_filter

    visits = await db.visits.find(query, {"_id": 0, "scraped_data.raw_data": 0}).sort("scheduled_date", 1).to_list(200)

    # Enriquecer com nomes (denormalizados, mas confirmamos)
    for visit in visits:
        # Garantir que temos os nomes
        if not visit.get("property_title") and visit.get("property_id"):
            prop = await db.properties.find_one({"id": visit["property_id"]}, {"title": 1, "photos": 1})
            if prop:
                visit["property_title"] = prop.get("title", "")
                visit["property_photo"] = (prop.get("photos") or [None])[0]

    return visits


async def run_create_visit(data: dict, user: dict):
    """
    Criar uma nova visita a um imóvel.

    v2: Suporta URL do imóvel (Idealista/Imovirtual) que invoca o scraper
    em background para auto-popular os dados da visita.

    Body:
    - property_id: ID do imóvel (obrigatório se não houver property_url)
    - client_id: ID do processo/cliente (obrigatório)
    - scheduled_date: Data/hora da visita ISO (obrigatório)
    - consultor_id: ID do consultor (opcional, padrão = user actual)
    - notes: Notas (opcional)
    - property_url: URL do imóvel para scraper (opcional — Idealista/Imovirtual)
    """
    property_id = data.get("property_id")
    client_id = data.get("client_id")
    scheduled_date = data.get("scheduled_date")
    consultor_id = data.get("consultor_id") or user.get("id")
    notes = data.get("notes", "")
    property_url = data.get("property_url", "").strip()

    if not client_id:
        raise HTTPException(status_code=400, detail="client_id é obrigatório")
    if not property_id and not property_url:
        raise HTTPException(status_code=400, detail="property_id ou property_url é obrigatório")
    if not scheduled_date:
        raise HTTPException(status_code=400, detail="scheduled_date é obrigatório")

    # Buscar processo ativo para este client_id e obter o process_id
    process = await db.processes.find_one({"id": client_id}, {
        "client_name": 1, "client_email": 1, "client_phone": 1,
        "status": 1, "assigned_consultor_id": 1,
    })
    client_name = process.get("client_name", "") if process else ""
    client_email = process.get("client_email", "") if process else ""
    client_phone = process.get("client_phone", "") if process else ""
    process_id = client_id  # Na arquitetura actual, client_id = process_id

    # Buscar dados do imóvel (se property_id fornecido)
    prop_data = {}
    if property_id:
        prop = await db.properties.find_one({"id": property_id}, {"title": 1, "photos": 1, "address": 1})
        if not prop:
            raise HTTPException(status_code=404, detail="Imóvel não encontrado")
        prop_data = {
            "property_title": prop.get("title", ""),
            "property_photo": (prop.get("photos") or [None])[0],
            "property_address": prop.get("address", {}),
        }

    # Buscar dados do consultor
    consultor = await db.users.find_one({"id": consultor_id}, {"name": 1, "email": 1, "phone": 1})
    consultor_name = consultor.get("name", "") if consultor else user.get("name", "")

    now = datetime.now(timezone.utc).isoformat()
    visit_id = str(uuid.uuid4())

    visit_doc = {
        "id": visit_id,
        "property_id": property_id,
        **prop_data,
        "client_id": client_id,
        "process_id": process_id,  # Explícito para queries
        "client_name": client_name,
        "client_email": client_email,
        "client_phone": client_phone,
        "consultor_id": consultor_id,
        "consultor_name": consultor_name,
        "scheduled_date": scheduled_date,
        "status": "agendada",
        "notes": notes,
        "created_at": now,
        "updated_at": now,
        "created_by": user.get("id"),
        "company_id": user.get("company_id"),
    }

    # Se tem property_url, adicionar ao documento e lançar scraper em background
    if property_url:
        visit_doc["scraped_url"] = property_url
        visit_doc["scraper_status"] = "pending"

        # Se não temos property_id, é uma visita com imóvel externo
        if not property_id:
            visit_doc["property_id"] = None
            # Usar URL como fallback para o título
            visit_doc.setdefault("property_title", f"Imóvel de {property_url.split('//')[-1][:50]}...")

    await db.visits.insert_one(visit_doc)

    # Incrementar visit_count no imóvel (se existir)
    if property_id:
        await db.properties.update_one(
            {"id": property_id},
            {"$inc": {"visit_count": 1}}
        )

    # Registar no histórico do processo
    try:
        from services.history import log_history
        await log_history(
            client_id,
            user=user,
            action="VISIT_CREATED",
            field="visita",
            old_value=None,
            new_value=f"Visita criada a '{visit_doc.get('property_title', '')}' para {scheduled_date}"
        )
    except Exception as e:
        logger.warning(f"[VISITS] Erro ao registar histórico: {e}")

    # ── Criar evento no calendário (visita já nasce agendada) ──
    await _create_calendar_event_for_visit(visit_doc)

    # ── Atualizar portal ──
    await _update_portal_visit_status(visit_doc, "agendada", scheduled_date)

    # ── Lançar scraper em background se URL fornecida ──
    if property_url:
        asyncio.create_task(_run_scraper_for_visit(visit_id, property_url))
        logger.info(f"[VISITS] Scraper lançado em background para visita {visit_id}")

    logger.info(f"[VISITS] Visita criada: {visit_id} — Imóvel {property_id or property_url}, Cliente {client_name}")

    visit_doc.pop("_id", None)
    return visit_doc

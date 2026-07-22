"""Shared helpers for CRM visits (calendar / scraper / portal sync).

Extraído de `routes/visits.py`. Prefer `visit_*` (not `visits_*`) and do
**not** collide with existing `portal_client_visits.py`.
"""
from __future__ import annotations

import uuid
import logging
from datetime import datetime, timezone

from database import db

logger = logging.getLogger(__name__)


async def _create_calendar_event_for_visit(visit: dict):
    """
    Cria um registo na coleção de deadlines (calendário do CRM)
    quando uma visita transita para 'agendada'.

    Título: 'Visita Imóvel: [Nome do Imóvel]'
    Associado ao consultor e ao processo.
    """
    try:
        deadline_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        property_name = visit.get("property_title") or "Imóvel"
        scheduled_date = visit.get("scheduled_date")
        client_name_suffix = ""
        client_name_val = visit.get("client_name", "")
        if client_name_val:
            client_name_suffix = f" — {client_name_val}"

        consultor_id = visit.get("consultor_id")
        process_id = visit.get("process_id") or visit.get("client_id")  # process_id explícito ou fallback para client_id

        assigned_users = [uid for uid in [consultor_id] if uid]

        deadline_doc = {
            "id": deadline_id,
            "process_id": process_id,
            "visit_id": visit.get("id"),  # Referência cruzada
            "title": f"Visita Imóvel: {property_name}",
            "description": (
                f"Visita agendada a '{property_name}'{client_name_suffix}"
                f"\nNotas: {visit.get('notes', '—')}"
            ),
            "due_date": scheduled_date or now,
            "priority": "alta",
            "completed": False,
            "created_by": consultor_id or "system",
            "created_at": now,
            "assigned_user_ids": assigned_users,
            "source": "visit_schedule",
            "assigned_consultor_id": consultor_id,
            "assigned_mediador_id": None,
        }

        await db.deadlines.insert_one(deadline_doc)
        logger.info(f"[VISITS] Evento de calendário criado: {deadline_id} para visita {visit.get('id')}")
        return deadline_id

    except Exception as e:
        logger.warning(f"[VISITS] Erro ao criar evento de calendário: {e}")
        return None


async def _remove_calendar_event_for_visit(visit_id: str):
    """
    Remove o evento de calendário associado a uma visita
    quando é cancelada ou recusada.
    """
    try:
        result = await db.deadlines.delete_many({"visit_id": visit_id})
        if result.deleted_count > 0:
            logger.info(f"[VISITS] {result.deleted_count} evento(s) de calendário removido(s) para visita {visit_id}")
    except Exception as e:
        logger.warning(f"[VISITS] Erro ao remover evento de calendário: {e}")


async def _update_portal_visit_status(visit: dict, new_status: str, scheduled_date: str = None):
    """
    Atualiza o estado da visita no Portal do Cliente.

    Quando a visita é agendada, define a data oficial.
    Quando é recusada/cancelada, atualiza o estado no portal.
    """
    try:
        process_id = visit.get("process_id") or visit.get("client_id")  # process_id explícito ou fallback
        visit_id = visit.get("id")

        update_fields = {
            "portal_status": new_status,
            "portal_updated_at": datetime.now(timezone.utc).isoformat(),
        }

        if new_status == "agendada" and scheduled_date:
            update_fields["portal_scheduled_date"] = scheduled_date

        if new_status in ("cancelada", "recusada"):
            update_fields["portal_cancelled_at"] = datetime.now(timezone.utc).isoformat()
            update_fields.pop("portal_scheduled_date", None)

        await db.visits.update_one(
            {"id": visit_id},
            {"$set": update_fields}
        )

        # Notificar via WebSocket para a sala do processo
        try:
            from services.websocket_manager import manager, WSEventType, create_ws_message
            ws_data = {
                "visit_id": visit_id,
                "status": new_status,
                "property_title": visit.get("property_title", "Imóvel"),
            }
            if scheduled_date:
                ws_data["scheduled_date"] = scheduled_date

            ws_message = create_ws_message(WSEventType.PORTAL_MESSAGE, {
                "type": "visit_status_update",
                **ws_data,
            })
            await manager.broadcast_to_room(f"process_{process_id}", ws_message)
        except Exception as ws_err:
            logger.debug(f"[VISITS] Erro ao notificar portal via WS: {ws_err}")

        logger.info(f"[VISITS] Portal atualizado: visita {visit_id} → {new_status}")

    except Exception as e:
        logger.warning(f"[VISITS] Erro ao atualizar portal: {e}")


async def _run_scraper_for_visit(visit_id: str, url: str):
    """
    Invoca o scraper em background para extrair dados do imóvel
    a partir de um URL (Idealista/Imovirtual).

    Atualiza o documento da visita com os dados extraídos.
    """
    try:
        from services.property_scraper import extract_property_data
        scraped_result = await extract_property_data(url)

        # source == "error" is a soft failure from the scraper — treat as error
        if scraped_result.source == "error":
            raw = getattr(scraped_result, "raw_data", None) or {}
            err_msg = raw.get("error") or "Falha ao extrair dados do imóvel"
            await db.visits.update_one(
                {"id": visit_id},
                {"$set": {
                    "scraper_status": "error",
                    "scraper_error": str(err_msg),
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }}
            )
            logger.warning(f"[VISITS] Scraper retornou erro para visita {visit_id}: {err_msg}")
            return

        scraped_data = {
            "title": scraped_result.title,
            "price": scraped_result.price,
            "location": scraped_result.location,
            "typology": scraped_result.typology,
            "area": scraped_result.area,
            "photo_url": scraped_result.photo_url,
            "source": scraped_result.source,
            "url": url,
            "consultant": {
                "name": scraped_result.consultant.name if scraped_result.consultant else None,
                "phone": scraped_result.consultant.phone if scraped_result.consultant else None,
                "email": scraped_result.consultant.email if scraped_result.consultant else None,
                "agency_name": scraped_result.consultant.agency_name if scraped_result.consultant else None,
            } if scraped_result.consultant else None,
        }

        # Atualizar visita com dados do scraper
        update_fields = {
            "scraped_data": scraped_data,
            "scraped_url": url,
            "scraper_status": "completed",
            "scraper_error": None,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

        # Auto-popular campos da visita com dados extraídos
        if scraped_data.get("title"):
            update_fields["property_title"] = scraped_data["title"]

        if scraped_data.get("price"):
            update_fields["scraped_price"] = scraped_data["price"]

        if scraped_data.get("photo_url"):
            update_fields["property_photo"] = scraped_data["photo_url"]

        if scraped_data.get("location"):
            update_fields["property_address"] = {
                "municipality": scraped_data["location"],
                "district": "",
            }

        if scraped_data.get("typology"):
            update_fields["scraped_typology"] = scraped_data["typology"]

        await db.visits.update_one(
            {"id": visit_id},
            {"$set": update_fields}
        )

        logger.info(f"[VISITS] Scraper completado para visita {visit_id}: {scraped_data.get('title', 'sem título')}")

    except Exception as e:
        logger.warning(f"[VISITS] Erro no scraper para visita {visit_id}: {e}")
        # Marcar erro no scraper
        try:
            await db.visits.update_one(
                {"id": visit_id},
                {"$set": {
                    "scraper_status": "error",
                    "scraper_error": str(e),
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }}
            )
        except Exception:
            pass

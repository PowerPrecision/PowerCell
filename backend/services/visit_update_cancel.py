"""Update + cancel CRM visits (calendar / portal sync).

Extraído de `routes/visits.py`.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import HTTPException

from database import db
from services.visit_helpers import (
    _create_calendar_event_for_visit,
    _remove_calendar_event_for_visit,
    _update_portal_visit_status,
)

logger = logging.getLogger(__name__)


async def run_update_visit(visit_id: str, data: dict, user: dict):
    """
    Actualizar visita (status, data, notas, etc.)

    v2 — Sincronização com Calendário e Portal:
    - Status → 'agendada': Cria evento no calendário + atualiza portal
    - Status → 'cancelada'/'recusada': Remove evento do calendário + atualiza portal
    - scheduled_date alterado: Atualiza evento do calendário
    """
    visit = await db.visits.find_one({"id": visit_id})
    if not visit:
        raise HTTPException(status_code=404, detail="Visita não encontrada")

    now = datetime.now(timezone.utc).isoformat()
    update_fields = {"updated_at": now}

    old_status = visit.get("status")
    new_status = data.get("status")

    # Campos actualizáveis
    if "status" in data:
        if new_status not in ["agendada", "concluida", "cancelada", "solicitada", "recusada"]:
            raise HTTPException(status_code=400, detail="Status inválido. Use: agendada, concluida, cancelada, recusada")
        update_fields["status"] = new_status

    if "scheduled_date" in data:
        update_fields["scheduled_date"] = data["scheduled_date"]

    if "notes" in data:
        update_fields["notes"] = data["notes"]

    if "consultor_id" in data:
        consultor = await db.users.find_one({"id": data["consultor_id"]}, {"name": 1})
        update_fields["consultor_id"] = data["consultor_id"]
        update_fields["consultor_name"] = consultor.get("name", "") if consultor else ""

    await db.visits.update_one(
        {"id": visit_id},
        {"$set": update_fields}
    )

    # ── Sincronização com Calendário e Portal ──
    if new_status and new_status != old_status:
        # Status → 'agendada': Criar evento no calendário + atualizar portal + notificar cliente
        if new_status == "agendada":
            scheduled_date = data.get("scheduled_date") or visit.get("scheduled_date")

            # Atualizar consultor na visita se fornecido
            updated_visit = {**visit, **update_fields}

            # Criar evento no calendário
            await _create_calendar_event_for_visit(updated_visit)

            # Atualizar portal do cliente
            await _update_portal_visit_status(visit, "agendada", scheduled_date)

            # Notificar cliente por email sobre o agendamento confirmado
            try:
                from services.notification_service import send_notification_with_preference_check
                client_email_addr = visit.get("client_email")
                if client_email_addr and scheduled_date:
                    try:
                        dt = datetime.fromisoformat(scheduled_date.replace("Z", "+00:00"))
                        formatted_date = dt.strftime("%d/%m/%Y às %H:%M")
                    except Exception:
                        formatted_date = scheduled_date

                    property_name = visit.get("property_title", "Imóvel")
                    await send_notification_with_preference_check(
                        client_email_addr,
                        "Visita Agendada",
                        f"A sua visita a '{property_name}' foi agendada para {formatted_date}. "
                        f"O seu consultor entrará em contacto se necessário.",
                        notification_type="visit_update",
                    )
                    logger.info(f"[VISITS] Cliente notificado do agendamento: {client_email_addr}")
            except Exception as e:
                logger.warning(f"[VISITS] Erro ao notificar cliente do agendamento: {e}")

        # Status → 'cancelada' ou 'recusada': Remover evento do calendário + atualizar portal
        elif new_status in ("cancelada", "recusada"):
            await _remove_calendar_event_for_visit(visit_id)
            await _update_portal_visit_status(visit, new_status)

            # Notificar cliente sobre cancelamento/recusa
            try:
                from services.notification_service import send_notification_with_preference_check
                client_email = visit.get("client_email")
                if client_email:
                    status_text = "cancelada" if new_status == "cancelada" else "recusada"
                    await send_notification_with_preference_check(
                        client_email,
                        f"Visita {status_text.capitalize()}",
                        f"A sua visita a '{visit.get('property_title', 'Imóvel')}' foi {status_text}. "
                        f"Contacte o seu consultor para mais informações.",
                        notification_type="visit_update",
                    )
            except Exception as e:
                logger.warning(f"[VISITS] Erro ao notificar cliente sobre {new_status}: {e}")

        # Status → 'concluida': Marcar evento como completo
        elif new_status == "concluida":
            try:
                await db.deadlines.update_many(
                    {"visit_id": visit_id},
                    {"$set": {"completed": True, "completed_at": now}}
                )
            except Exception as e:
                logger.warning(f"[VISITS] Erro ao marcar evento como completo: {e}")

            await _update_portal_visit_status(visit, "concluida")

    # Se scheduled_date foi alterado sem mudança de status, atualizar evento no calendário
    if "scheduled_date" in data and (not new_status or new_status == old_status):
        try:
            await db.deadlines.update_many(
                {"visit_id": visit_id},
                {"$set": {"due_date": data["scheduled_date"]}}
            )
        except Exception as e:
            logger.warning(f"[VISITS] Erro ao atualizar data do evento: {e}")

    # Registar no histórico
    if new_status and new_status != old_status:
        try:
            from services.history import log_history
            status_labels = {
                "solicitada": "Solicitada", "agendada": "Agendada",
                "concluida": "Concluída", "cancelada": "Cancelada", "recusada": "Recusada",
            }
            await log_history(
                visit.get("client_id", ""),
                user=user,
                action="VISIT_STATUS_CHANGED",
                field="visita",
                old_value=status_labels.get(old_status, old_status),
                new_value=status_labels.get(new_status, new_status)
            )
        except Exception as e:
            logger.warning(f"[VISITS] Erro ao registar histórico: {e}")

    updated = await db.visits.find_one({"id": visit_id}, {"_id": 0, "scraped_data.raw_data": 0})
    return updated


async def run_cancel_visit(visit_id: str, user: dict):
    """Cancelar visita (soft delete — muda status para 'cancelada')."""
    visit = await db.visits.find_one({"id": visit_id})
    if not visit:
        raise HTTPException(status_code=404, detail="Visita não encontrada")

    now = datetime.now(timezone.utc).isoformat()
    await db.visits.update_one(
        {"id": visit_id},
        {"$set": {"status": "cancelada", "updated_at": now, "cancelled_at": now, "cancelled_by": user.get("id")}}
    )

    # Remover evento do calendário
    await _remove_calendar_event_for_visit(visit_id)

    # Atualizar portal
    await _update_portal_visit_status(visit, "cancelada")

    return {"success": True, "message": "Visita cancelada"}

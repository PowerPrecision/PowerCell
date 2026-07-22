"""Create / update / status / refresh / delete lead endpoints.

Extraído de `routes/leads.py`.
"""
from __future__ import annotations

import uuid
import logging
from datetime import datetime, timezone

from fastapi import HTTPException

from database import db
from models.lead import PropertyLeadCreate, PropertyLeadUpdate, LeadStatus
from services.scraper import scrape_property_url
from utils.input_sanitization import (
    sanitize_string, sanitize_name, sanitize_email, sanitize_phone, sanitize_url,
)

logger = logging.getLogger(__name__)


async def run_create_lead(
    lead_data: PropertyLeadCreate,
    user: dict,
):
    """Criar um novo lead na base de dados."""
    # Verificar duplicados
    existing = await db.property_leads.find_one({"url": lead_data.url})
    if existing:
        raise HTTPException(status_code=400, detail="Já existe um lead com este URL")

    now = datetime.now(timezone.utc).isoformat()

    lead_dict = lead_data.model_dump()
    lead_dict["id"] = str(uuid.uuid4())
    lead_dict["status"] = LeadStatus.NOVO.value
    lead_dict["created_at"] = now
    lead_dict["updated_at"] = now
    lead_dict["created_by"] = user.get("email")
    lead_dict["created_by_id"] = user.get("id")  # Para filtros por consultor
    lead_dict["history"] = [{
        "timestamp": now,
        "event": "Lead criado",
        "user": user.get("email")
    }]

    # Sanitize user-provided string fields before DB insert
    if lead_dict.get("title"):
        lead_dict["title"] = sanitize_string(lead_dict["title"], max_length=300)
    if lead_dict.get("description"):
        lead_dict["description"] = sanitize_string(lead_dict["description"], max_length=2000)
    if lead_dict.get("location"):
        lead_dict["location"] = sanitize_string(lead_dict["location"], max_length=200)
    if lead_dict.get("notes"):
        lead_dict["notes"] = sanitize_string(lead_dict["notes"], max_length=1000)
    if lead_dict.get("url"):
        lead_dict["url"] = sanitize_url(lead_dict["url"])
    # Sanitize consultant fields if present
    consultant = lead_dict.get("consultant")
    if consultant:
        if consultant.get("name"):
            consultant["name"] = sanitize_name(consultant["name"])
        if consultant.get("phone"):
            consultant["phone"] = sanitize_phone(consultant["phone"])
        if consultant.get("email"):
            consultant["email"] = sanitize_email(consultant["email"])

    await db.property_leads.insert_one(lead_dict)
    return lead_dict


async def run_update_lead(
    lead_id: str,
    update_data: PropertyLeadUpdate,
    user: dict,
):
    """Actualizar dados de um lead."""
    lead = await db.property_leads.find_one({"id": lead_id})
    if not lead:
        raise HTTPException(status_code=404, detail="Lead não encontrado")

    now = datetime.now(timezone.utc).isoformat()
    update_dict = update_data.model_dump(exclude_none=True)
    update_dict["updated_at"] = now

    # Registar mudança de estado no histórico
    if "status" in update_dict and update_dict["status"] != lead.get("status"):
        # Garantir que o histórico existe
        history = lead.get("history", [])
        history.append({
            "timestamp": now,
            "event": f"Status alterado para {update_dict['status']}",
            "user": user.get("email")
        })
        update_dict["history"] = history

    await db.property_leads.update_one({"id": lead_id}, {"$set": update_dict})

    # Retornar objeto actualizado (sem _id)
    return await db.property_leads.find_one({"id": lead_id}, {"_id": 0})


async def run_update_lead_status(
    lead_id: str,
    status: str,
    user: dict,
):
    """Endpoint rápido para mudar estado (Drag & Drop)."""
    lead = await db.property_leads.find_one({"id": lead_id})
    if not lead:
        raise HTTPException(status_code=404, detail="Lead não encontrado")

    # Validar se o status existe no Enum
    # status vem como query param string, validar contra os valores do enum
    valid_statuses = [s.value for s in LeadStatus]
    if status not in valid_statuses:
         raise HTTPException(status_code=400, detail="Estado inválido")

    now = datetime.now(timezone.utc).isoformat()

    # Preparar entrada de histórico
    history_entry = {
        "timestamp": now,
        "event": f"Status alterado para {status}",
        "user": user.get("email")
    }

    await db.property_leads.update_one(
        {"id": lead_id},
        {
            "$set": {"status": status, "updated_at": now},
            "$push": {"history": history_entry}
        }
    )
    return {"success": True, "status": status}


async def run_refresh_lead_price(
    lead_id: str,
    user: dict,
):
    """
    Verificar se o preço do lead mudou visitando o URL novamente.
    Se mudou, actualiza a DB e adiciona entrada ao histórico.
    """
    # Buscar lead
    lead = await db.property_leads.find_one({"id": lead_id}, {"_id": 0})
    if not lead:
        raise HTTPException(status_code=404, detail="Lead não encontrado")

    url = lead.get("url")
    if not url:
        raise HTTPException(status_code=400, detail="Lead não tem URL associado")

    old_price = lead.get("price")

    try:
        # Fazer scraping novamente
        scraped_data = await scrape_property_url(url)

        if scraped_data.get("error"):
            return {
                "success": False,
                "message": f"Erro ao verificar: {scraped_data.get('error')}",
                "old_price": old_price,
                "new_price": None,
                "price_changed": False
            }

        new_price = scraped_data.get("preco")
        now = datetime.now(timezone.utc).isoformat()

        # Verificar se o preço mudou
        price_changed = new_price is not None and new_price != old_price

        update_fields = {
            "updated_at": now,
            "last_checked_at": now
        }

        history_entry = {
            "timestamp": now,
            "event": "Preço verificado",
            "user": user.get("email")
        }

        if price_changed:
            update_fields["price"] = new_price
            history_entry["event"] = f"Preço alterado de {old_price or 'N/D'}€ para {new_price}€"
            logger.info(f"Lead {lead_id}: Preço alterado de {old_price} para {new_price}")

        # Também actualizar outros campos se disponíveis
        if scraped_data.get("titulo"):
            update_fields["title"] = scraped_data.get("titulo")
        if scraped_data.get("localizacao"):
            update_fields["location"] = scraped_data.get("localizacao")

        await db.property_leads.update_one(
            {"id": lead_id},
            {
                "$set": update_fields,
                "$push": {"history": history_entry}
            }
        )

        return {
            "success": True,
            "message": "Preço alterado" if price_changed else "Preço sem alteração",
            "old_price": old_price,
            "new_price": new_price,
            "price_changed": price_changed
        }

    except Exception as e:
        logger.error(f"Erro ao verificar preço do lead {lead_id}: {str(e)}")
        return {
            "success": False,
            "message": f"Erro ao verificar preço: {str(e)}",
            "old_price": old_price,
            "new_price": None,
            "price_changed": False
        }


async def run_delete_lead(lead_id: str, user: dict):
    """Eliminar lead."""
    result = await db.property_leads.delete_one({"id": lead_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Lead não encontrado")
    return {"success": True}

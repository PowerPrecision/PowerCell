"""Interested clients, visits, and photo ops.

Extraído de `routes/properties.py`.
"""
from __future__ import annotations

import logging
from typing import Optional
from datetime import datetime, timezone

from fastapi import HTTPException

from database import db
from models.property import PropertyHistory

logger = logging.getLogger(__name__)


async def run_add_interested_client(
    property_id: str,
    client_id: str,
    user: dict
):
    """Adicionar cliente interessado a um imóvel."""
    prop = await db.properties.find_one({"id": property_id})
    if not prop:
        raise HTTPException(status_code=404, detail="Imóvel não encontrado")
    
    # Verificar se cliente existe
    process = await db.processes.find_one({"id": client_id})
    if not process:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    
    # Adicionar se não existe
    if client_id not in prop.get("interested_clients", []):
        now = datetime.now(timezone.utc).isoformat()
        await db.properties.update_one(
            {"id": property_id},
            {
                "$addToSet": {"interested_clients": client_id},
                "$inc": {"inquiry_count": 1},
                "$push": {
                    "history": PropertyHistory(
                        timestamp=now,
                        event=f"Cliente interessado: {process.get('client_name')}",
                        user=user.get("email")
                    ).model_dump()
                }
            }
        )
    
    return {"success": True, "message": f"Cliente {process.get('client_name')} adicionado"}


async def run_get_interested_clients(
    property_id: str,
    user: dict
):
    """Obter lista de clientes interessados num imóvel."""
    prop = await db.properties.find_one({"id": property_id}, {"interested_clients": 1})
    
    if not prop:
        raise HTTPException(status_code=404, detail="Imóvel não encontrado")
    
    client_ids = prop.get("interested_clients", [])
    
    if not client_ids:
        return []
    
    clients = await db.processes.find(
        {"id": {"$in": client_ids}},
        {"_id": 0, "id": 1, "client_name": 1, "client_email": 1, "client_phone": 1, "status": 1}
    ).to_list(100)
    
    return clients


async def run_register_visit(
    property_id: str,
    user: dict,
    client_id: Optional[str] = None,
    notes: Optional[str] = None
):
    """Registar uma visita ao imóvel."""
    prop = await db.properties.find_one({"id": property_id})
    if not prop:
        raise HTTPException(status_code=404, detail="Imóvel não encontrado")
    
    now = datetime.now(timezone.utc).isoformat()
    
    event_text = "Visita registada"
    if client_id:
        process = await db.processes.find_one({"id": client_id}, {"client_name": 1})
        if process:
            event_text = f"Visita com {process.get('client_name')}"
    
    if notes:
        event_text += f" - {notes}"
    
    await db.properties.update_one(
        {"id": property_id},
        {
            "$inc": {"visit_count": 1},
            "$push": {
                "history": PropertyHistory(
                    timestamp=now,
                    event=event_text,
                    user=user.get("email")
                ).model_dump()
            }
        }
    )
    
    return {"success": True, "message": "Visita registada"}


async def run_upload_property_photo(
    property_id: str,
    photo_url: str,
    user: dict
):
    """
    Adicionar foto a um imóvel.
    Aceita URL de foto (pode ser do OneDrive, Dropbox, etc.)
    """
    prop = await db.properties.find_one({"id": property_id})
    if not prop:
        raise HTTPException(status_code=404, detail="Imóvel não encontrado")
    
    now = datetime.now(timezone.utc).isoformat()
    
    await db.properties.update_one(
        {"id": property_id},
        {
            "$addToSet": {"photos": photo_url},
            "$set": {"updated_at": now},
            "$push": {
                "history": PropertyHistory(
                    timestamp=now,
                    event="Foto adicionada",
                    user=user.get("email")
                ).model_dump()
            }
        }
    )
    
    return {"success": True, "message": "Foto adicionada", "photo_url": photo_url}


async def run_remove_property_photo(
    property_id: str,
    photo_url: str,
    user: dict
):
    """Remover foto de um imóvel."""
    prop = await db.properties.find_one({"id": property_id})
    if not prop:
        raise HTTPException(status_code=404, detail="Imóvel não encontrado")
    
    now = datetime.now(timezone.utc).isoformat()
    
    await db.properties.update_one(
        {"id": property_id},
        {
            "$pull": {"photos": photo_url},
            "$set": {"updated_at": now}
        }
    )
    
    return {"success": True, "message": "Foto removida"}

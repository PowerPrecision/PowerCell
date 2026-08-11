"""Property CRUD: create / get / update / status / delete.

Extraído de `routes/properties.py`.
"""
from __future__ import annotations

import uuid
import logging
import asyncio
from datetime import datetime, timezone

from fastapi import HTTPException

from database import db
from models.property import (
    Property, PropertyCreate, PropertyUpdate,
    PropertyStatus, PropertyHistory,
)
from services.alerts import check_and_notify_matches_for_new_property
from utils.input_sanitization import (
    sanitize_string, sanitize_name, sanitize_email, sanitize_phone,
    sanitize_url, sanitize_html,
)
from services.property_helpers import get_next_reference

logger = logging.getLogger(__name__)


async def run_create_property(
    data: PropertyCreate,
    user: dict
):
    """Criar novo imóvel angariado."""
    now = datetime.now(timezone.utc).isoformat()
    
    # Gerar referência se não fornecida
    internal_ref = data.internal_reference or await get_next_reference()
    
    # Sanitizar inputs do utilizador antes de guardar
    sanitized_title = sanitize_string(data.title, max_length=300) if data.title else data.title
    sanitized_description = sanitize_html(data.description) if data.description else data.description
    sanitized_notes = sanitize_string(data.notes, max_length=1000) if data.notes else data.notes
    sanitized_private_notes = sanitize_string(data.private_notes, max_length=1000) if data.private_notes else data.private_notes
    sanitized_video_url = sanitize_url(data.video_url) if data.video_url else data.video_url
    sanitized_virtual_tour_url = sanitize_url(data.virtual_tour_url) if data.virtual_tour_url else data.virtual_tour_url
    
    # Sanitizar owner fields
    sanitized_owner = data.owner
    if sanitized_owner:
        if hasattr(sanitized_owner, 'name') and sanitized_owner.name:
            sanitized_owner = sanitized_owner.model_copy(update={"name": sanitize_name(sanitized_owner.name)})
        if hasattr(sanitized_owner, 'phone') and sanitized_owner.phone:
            sanitized_owner = sanitized_owner.model_copy(update={"phone": sanitize_phone(sanitized_owner.phone)})
        if hasattr(sanitized_owner, 'email') and sanitized_owner.email:
            sanitized_owner = sanitized_owner.model_copy(update={"email": sanitize_email(sanitized_owner.email)})
    
    # Obter nome do agente se atribuído
    agent_name = None
    if data.assigned_agent_id:
        agent = await db.users.find_one({"id": data.assigned_agent_id}, {"name": 1})
        if agent:
            agent_name = agent["name"]
    
    # Verificar URL duplicado (não bloqueia, apenas avisa)
    warning = None
    if data.source_url:
        existing = await db.properties.find_one(
            {"source_url": data.source_url},
            {"id": 1, "title": 1, "client_name": 1, "status": 1}
        )
        if existing:
            warning = f"Este URL já foi utilizado no imóvel '{existing.get('title', '')}' (status: {existing.get('status', '')})"
            if existing.get("client_name"):
                warning += f" para o cliente {existing['client_name']}"
    
    property_doc = Property(
        id=str(uuid.uuid4()),
        internal_reference=internal_ref,
        property_type=data.property_type,
        title=sanitized_title,
        description=sanitized_description,
        source_url=data.source_url,
        address=data.address,
        features=data.features,
        condition=data.condition,
        financials=data.financials,
        owner=sanitized_owner,
        photos=data.photos,
        video_url=sanitized_video_url,
        virtual_tour_url=sanitized_virtual_tour_url,
        documents=data.documents,
        status=data.status,
        assigned_agent_id=data.assigned_agent_id,
        assigned_agent_name=agent_name,
        process_id=data.process_id,
        client_id=data.client_id,
        client_name=data.client_name,
        notes=sanitized_notes,
        private_notes=sanitized_private_notes,
        history=[
            PropertyHistory(
                timestamp=now,
                event="Imóvel criado",
                user=user.get("email")
            )
        ],
        created_at=now,
        updated_at=now,
        created_by=user.get("email")
    )
    
    await db.properties.insert_one(property_doc.model_dump())
    
    logger.info(f"Imóvel criado: {property_doc.id} ({internal_ref}) por {user.get('email')}")
    
    # Verificar matches em background (não bloqueia resposta)
    asyncio.create_task(check_and_notify_matches_for_new_property(property_doc.id))
    
    # Incluir warning na resposta se URL duplicado
    response = property_doc.model_dump()
    if warning:
        response["warning"] = warning
    
    return response


async def run_get_property(
    property_id: str,
    user: dict
):
    """Obter detalhes de um imóvel."""
    prop = await db.properties.find_one({"id": property_id}, {"_id": 0})
    
    if not prop:
        raise HTTPException(status_code=404, detail="Imóvel não encontrado")
    
    # Incrementar contador de visualizações
    await db.properties.update_one(
        {"id": property_id},
        {"$inc": {"view_count": 1}}
    )
    
    return Property(**prop)


async def run_update_property(
    property_id: str,
    data: PropertyUpdate,
    user: dict
):
    """Actualizar um imóvel."""
    prop = await db.properties.find_one({"id": property_id})
    
    if not prop:
        raise HTTPException(status_code=404, detail="Imóvel não encontrado")
    
    now = datetime.now(timezone.utc).isoformat()
    
    # Preparar actualização
    update_dict = data.model_dump(exclude_none=True)
    
    # Sanitizar campos de texto antes de guardar
    if "title" in update_dict and update_dict["title"]:
        update_dict["title"] = sanitize_string(update_dict["title"], max_length=300)
    if "description" in update_dict and update_dict["description"]:
        update_dict["description"] = sanitize_html(update_dict["description"])
    if "notes" in update_dict and update_dict["notes"]:
        update_dict["notes"] = sanitize_string(update_dict["notes"], max_length=1000)
    if "private_notes" in update_dict and update_dict["private_notes"]:
        update_dict["private_notes"] = sanitize_string(update_dict["private_notes"], max_length=1000)
    if "video_url" in update_dict and update_dict["video_url"]:
        update_dict["video_url"] = sanitize_url(update_dict["video_url"])
    if "virtual_tour_url" in update_dict and update_dict["virtual_tour_url"]:
        update_dict["virtual_tour_url"] = sanitize_url(update_dict["virtual_tour_url"])
    
    # Sanitizar owner fields if present
    if "owner" in update_dict and update_dict["owner"]:
        owner = update_dict["owner"]
        if isinstance(owner, dict):
            if owner.get("name"):
                owner["name"] = sanitize_name(owner["name"])
            if owner.get("phone"):
                owner["phone"] = sanitize_phone(owner["phone"])
            if owner.get("email"):
                owner["email"] = sanitize_email(owner["email"])
            update_dict["owner"] = owner
    
    update_dict["updated_at"] = now
    
    # Actualizar nome do agente se mudou
    if "assigned_agent_id" in update_dict:
        agent = await db.users.find_one({"id": update_dict["assigned_agent_id"]}, {"name": 1})
        update_dict["assigned_agent_name"] = agent["name"] if agent else None
    
    # Registar mudança de status no histórico
    if "status" in update_dict and update_dict["status"] != prop.get("status"):
        history_entry = PropertyHistory(
            timestamp=now,
            event=f"Status alterado para {update_dict['status']}",
            user=user.get("email")
        )
        await db.properties.update_one(
            {"id": property_id},
            {"$push": {"history": history_entry.model_dump()}}
        )
    
    await db.properties.update_one(
        {"id": property_id},
        {"$set": update_dict}
    )
    
    updated = await db.properties.find_one({"id": property_id}, {"_id": 0})
    
    return Property(**updated)


async def run_update_property_status(
    property_id: str,
    status: PropertyStatus,
    user: dict
):
    """Actualizar apenas o status de um imóvel."""
    prop = await db.properties.find_one({"id": property_id})
    
    if not prop:
        raise HTTPException(status_code=404, detail="Imóvel não encontrado")
    
    now = datetime.now(timezone.utc).isoformat()
    
    history_entry = PropertyHistory(
        timestamp=now,
        event=f"Status alterado para {status.value}",
        user=user.get("email")
    )
    
    await db.properties.update_one(
        {"id": property_id},
        {
            "$set": {"status": status.value, "updated_at": now},
            "$push": {"history": history_entry.model_dump()}
        }
    )
    
    return {"success": True, "status": status.value}


async def run_delete_property(
    property_id: str,
    user: dict
):
    """Eliminar um imóvel (apenas admin/CEO/diretor)."""
    result = await db.properties.delete_one({"id": property_id})
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Imóvel não encontrado")
    
    logger.info(f"Imóvel {property_id} eliminado por {user.get('email')}")
    
    return {"success": True, "message": "Imóvel eliminado"}

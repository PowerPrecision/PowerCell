"""Process OneDrive / cloud link CRUD.

Extraído de `routes/onedrive.py`.
Do **not** overwrite `services/onedrive.py`.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException
from pydantic import BaseModel

from database import db
from services.onedrive_url_validation import is_valid_link_url

logger = logging.getLogger(__name__)


class LinkCreate(BaseModel):
    """Payload para criar uma ligação OneDrive para um processo."""

    name: str
    url: str
    description: Optional[str] = ""


class LinkUpdate(BaseModel):
    """Payload para atualizar uma ligação OneDrive existente."""

    name: Optional[str] = None
    url: Optional[str] = None
    description: Optional[str] = None


async def run_get_process_links(process_id: str, user: dict):
    """Obter todos os links de um processo."""
    process_exists = await db.processes.find_one(
        {"id": process_id},
        {"id": 1},
    )
    if not process_exists:
        raise HTTPException(status_code=404, detail="Processo não encontrado")

    process = await db.processes.find_one(
        {"id": process_id},
        {"onedrive_links": 1, "_id": 0},
    )
    return process.get("onedrive_links") if process else []


async def run_add_process_link(process_id: str, link_data: LinkCreate, user: dict):
    """Adicionar um novo link a um processo."""
    process = await db.processes.find_one({"id": process_id})
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")

    if not is_valid_link_url(link_data.url):
        raise HTTPException(
            status_code=400,
            detail="URL inválido. Use um link HTTP/HTTPS válido.",
        )

    new_link = {
        "id": str(uuid.uuid4()),
        "name": link_data.name,
        "url": link_data.url,
        "description": link_data.description or "",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": user.get("id") or user.get("email"),
    }

    await db.processes.update_one(
        {"id": process_id},
        {"$push": {"onedrive_links": new_link}},
    )

    logger.info(f"Link adicionado ao processo {process_id}: {link_data.name}")
    return new_link


async def run_delete_process_link(process_id: str, link_id: str, user: dict):
    """Remover um link de um processo."""
    process = await db.processes.find_one({"id": process_id})
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")

    result = await db.processes.update_one(
        {"id": process_id},
        {"$pull": {"onedrive_links": {"id": link_id}}},
    )

    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Link não encontrado")

    logger.info(f"Link {link_id} removido do processo {process_id}")
    return {"success": True, "message": "Link removido com sucesso"}


async def run_update_process_link(
    process_id: str,
    link_id: str,
    link_data: LinkUpdate,
    user: dict,
):
    """Actualizar um link existente."""
    process = await db.processes.find_one({"id": process_id})
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")

    update_fields = {}
    if link_data.name is not None:
        update_fields["onedrive_links.$.name"] = link_data.name
    if link_data.url is not None:
        update_fields["onedrive_links.$.url"] = link_data.url
    if link_data.description is not None:
        update_fields["onedrive_links.$.description"] = link_data.description

    if not update_fields:
        raise HTTPException(status_code=400, detail="Nenhum campo para actualizar")

    result = await db.processes.update_one(
        {"id": process_id, "onedrive_links.id": link_id},
        {"$set": update_fields},
    )

    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Link não encontrado")

    return {"success": True, "message": "Link actualizado com sucesso"}

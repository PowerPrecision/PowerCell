"""Minutas CRUD handlers.

Extraído de `routes/minutas.py`.
Do **not** overwrite services/rgpd_minutas.py.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException

from database import db
from services.minutas_api_models import MinutaCreate, MinutaUpdate
from utils.input_sanitization import sanitize_html, sanitize_string

logger = logging.getLogger(__name__)


async def run_list_minutas(
    categoria: Optional[str],
    search: Optional[str],
    limit: int,
    skip: int,
    user: dict,
):
    """Listar todas as minutas."""
    query = {}

    if categoria:
        query["categoria"] = categoria

    if search:
        query["$or"] = [
            {"titulo": {"$regex": search, "$options": "i"}},
            {"descricao": {"$regex": search, "$options": "i"}},
            {"tags": {"$in": [search]}},
        ]

    minutas = await db.minutas.find(
        query,
        {"_id": 0},
    ).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)

    total = await db.minutas.count_documents(query)

    return {
        "success": True,
        "total": total,
        "minutas": minutas,
    }


async def run_create_minuta(data: MinutaCreate, user: dict):
    """Criar uma nova minuta."""
    minuta = {
        "id": str(uuid.uuid4()),
        "titulo": sanitize_string(data.titulo.strip(), max_length=300),
        "categoria": data.categoria,
        "descricao": (
            sanitize_string(data.descricao.strip(), max_length=2000)
            if data.descricao else None
        ),
        "conteudo": sanitize_html(data.conteudo, allow_basic_formatting=True),
        "tags": [t.lower().strip() for t in (data.tags or []) if t.strip()],
        "created_by": user.get("id"),
        "created_by_name": user.get("name", user.get("email", "")).split("@")[0],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    await db.minutas.insert_one(minuta)
    minuta.pop("_id", None)

    logger.info(f"Minuta criada: {minuta['titulo']} por {user.get('email')}")

    return {
        "success": True,
        "minuta": minuta,
    }


async def run_get_minuta(minuta_id: str, user: dict):
    """Obter uma minuta especifica."""
    minuta = await db.minutas.find_one(
        {"id": minuta_id},
        {"_id": 0},
    )

    if not minuta:
        raise HTTPException(status_code=404, detail="Minuta nao encontrada")

    return {
        "success": True,
        "minuta": minuta,
    }


async def run_update_minuta(minuta_id: str, data: MinutaUpdate, user: dict):
    """Actualizar uma minuta. Apenas o criador ou admin pode editar."""
    minuta = await db.minutas.find_one({"id": minuta_id}, {"_id": 0})

    if not minuta:
        raise HTTPException(status_code=404, detail="Minuta nao encontrada")

    is_owner = minuta.get("created_by") == user.get("id")
    is_admin = user.get("role") in ["admin", "ceo"]

    if not is_owner and not is_admin:
        raise HTTPException(
            status_code=403,
            detail="Sem permissao para editar esta minuta",
        )

    updates = {"updated_at": datetime.now(timezone.utc).isoformat()}

    if data.titulo is not None:
        updates["titulo"] = sanitize_string(data.titulo.strip(), max_length=300)
    if data.categoria is not None:
        updates["categoria"] = data.categoria
    if data.descricao is not None:
        updates["descricao"] = (
            sanitize_string(data.descricao.strip(), max_length=2000)
            if data.descricao else None
        )
    if data.conteudo is not None:
        updates["conteudo"] = sanitize_html(
            data.conteudo, allow_basic_formatting=True,
        )
    if data.tags is not None:
        updates["tags"] = [t.lower().strip() for t in data.tags if t.strip()]

    await db.minutas.update_one(
        {"id": minuta_id},
        {"$set": updates},
    )

    updated = await db.minutas.find_one({"id": minuta_id}, {"_id": 0})

    logger.info(f"Minuta actualizada: {minuta_id} por {user.get('email')}")

    return {
        "success": True,
        "minuta": updated,
    }


async def run_delete_minuta(minuta_id: str, user: dict):
    """Eliminar uma minuta. Apenas o criador ou admin pode eliminar."""
    minuta = await db.minutas.find_one({"id": minuta_id}, {"_id": 0})

    if not minuta:
        raise HTTPException(status_code=404, detail="Minuta nao encontrada")

    is_owner = minuta.get("created_by") == user.get("id")
    is_admin = user.get("role") in ["admin", "ceo"]

    if not is_owner and not is_admin:
        raise HTTPException(
            status_code=403,
            detail="Sem permissao para eliminar esta minuta",
        )

    await db.minutas.delete_one({"id": minuta_id})

    logger.info(f"Minuta eliminada: {minuta_id} por {user.get('email')}")

    return {
        "success": True,
        "message": "Minuta eliminada",
    }

"""Admin AI models CRUD handlers.

Extraído de `routes/admin_ai.py`. Prefer `admin_ai_models` / `admin_ai_*` —
do **not** create `services/admin_ai.py` or overwrite `admin_ai_data.py`.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException

from database import db


async def run_list_ai_models(user: dict) -> dict:
    """Lista todos os modelos de IA configurados."""
    from config import AI_MODELS

    db_models = await db.ai_models.find({}, {"_id": 0}).to_list(100)

    if db_models:
        return {"models": db_models, "source": "database"}

    models_list = [
        {"key": key, **value}
        for key, value in AI_MODELS.items()
    ]
    return {"models": models_list, "source": "config"}


async def run_create_ai_model(
    key: str,
    name: str,
    provider: str,
    model_id: str,
    description: str = "",
    cost_per_1k_input: float = 0.0,
    cost_per_1k_output: float = 0.0,
    max_tokens: int = 4096,
    user: Optional[dict] = None,
) -> dict:
    """Cria um novo modelo de IA."""
    existing = await db.ai_models.find_one({"key": key})
    if existing:
        raise HTTPException(status_code=400, detail=f"Modelo '{key}' já existe")

    model_doc = {
        "key": key,
        "name": name,
        "provider": provider,
        "model_id": model_id,
        "description": description,
        "cost_per_1k_input": cost_per_1k_input,
        "cost_per_1k_output": cost_per_1k_output,
        "max_tokens": max_tokens,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "is_active": True,
    }

    await db.ai_models.insert_one(model_doc)
    del model_doc["_id"]

    return {"success": True, "model": model_doc}


async def run_update_ai_model(
    model_key: str,
    name: Optional[str] = None,
    description: Optional[str] = None,
    cost_per_1k_input: Optional[float] = None,
    cost_per_1k_output: Optional[float] = None,
    is_active: Optional[bool] = None,
    user: Optional[dict] = None,
) -> dict:
    """Actualiza um modelo de IA."""
    update_data = {"updated_at": datetime.now(timezone.utc).isoformat()}

    if name is not None:
        update_data["name"] = name
    if description is not None:
        update_data["description"] = description
    if cost_per_1k_input is not None:
        update_data["cost_per_1k_input"] = cost_per_1k_input
    if cost_per_1k_output is not None:
        update_data["cost_per_1k_output"] = cost_per_1k_output
    if is_active is not None:
        update_data["is_active"] = is_active

    result = await db.ai_models.update_one({"key": model_key}, {"$set": update_data})

    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Modelo não encontrado")

    return {"success": True}


async def run_delete_ai_model(model_key: str, user: Optional[dict] = None) -> dict:
    """Remove um modelo de IA."""
    result = await db.ai_models.delete_one({"key": model_key})

    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Modelo não encontrado")

    return {"success": True}

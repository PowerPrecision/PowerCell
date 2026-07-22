"""Admin AI / system cache settings handlers.

Extraído de `routes/admin_ai.py`. Prefer `admin_ai_cache` / `admin_ai_*` —
do **not** create `services/admin_ai.py` or overwrite `admin_ai_data.py`.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException

from database import db


async def run_get_cache_settings(user: dict) -> dict:
    """Obtém configurações de cache."""
    config = await db.system_config.find_one({"type": "cache_settings"}, {"_id": 0})
    return config or {"cache_limit": 1000, "notify_at_percentage": 80}


async def run_update_cache_settings(
    cache_limit: Optional[int] = None,
    notify_at_percentage: Optional[int] = None,
    user: Optional[dict] = None,
) -> dict:
    """Actualiza configurações de cache."""
    settings = {}
    if cache_limit is not None:
        settings["cache_limit"] = cache_limit
    if notify_at_percentage is not None:
        settings["notify_at_percentage"] = notify_at_percentage

    if not settings:
        raise HTTPException(status_code=400, detail="Nenhum campo para actualizar")

    settings["type"] = "cache_settings"
    settings["updated_at"] = datetime.now(timezone.utc).isoformat()

    await db.system_config.update_one(
        {"type": "cache_settings"},
        {"$set": settings},
        upsert=True,
    )

    return {"success": True, "settings": settings}

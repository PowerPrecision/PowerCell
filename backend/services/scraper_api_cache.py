"""Cache management handlers for scraper routes.

Extraído de `routes/scraper.py`.
Do **not** overwrite `services/scraper.py` / `gov_scraper.py` / `property_scraper.py`.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException

from database import db
from services.scraper import property_scraper
from services.scraper_api_models import ScrapeRequest

logger = logging.getLogger(__name__)


async def run_get_cache_stats(user: dict):
    """Retorna estatísticas do cache de scraping + limite / notificação."""
    stats = await property_scraper.get_cache_stats()

    cache_config = await db.system_config.find_one(
        {"type": "cache_settings"}, {"_id": 0},
    )
    cache_limit = cache_config.get("cache_limit", 1000) if cache_config else 1000
    notify_percentage = (
        cache_config.get("notify_at_percentage", 80) if cache_config else 80
    )

    total = stats.get("total_entries", 0)
    percentage_used = (total / cache_limit * 100) if cache_limit > 0 else 0

    should_notify = percentage_used >= notify_percentage
    notification = None

    if should_notify:
        notification = {
            "type": "warning",
            "message": (
                f"Cache de scraping está a {percentage_used:.0f}% da "
                f"capacidade ({total}/{cache_limit})"
            ),
            "action": "Considere limpar o cache ou aumentar o limite",
        }

        await db.notifications.update_one(
            {"type": "cache_limit_warning", "dismissed": False},
            {
                "$set": {
                    "type": "cache_limit_warning",
                    "message": notification["message"],
                    "percentage": percentage_used,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "dismissed": False,
                }
            },
            upsert=True,
        )

    return {
        **stats,
        "cache_limit": cache_limit,
        "percentage_used": round(percentage_used, 1),
        "should_notify": should_notify,
        "notification": notification,
    }


async def run_clear_scraper_cache(url: Optional[str], user: dict):
    """Limpa o cache de scraping (URL específica ou completo)."""
    deleted = await property_scraper.clear_cache(url)
    return {
        "success": True,
        "deleted_count": deleted,
        "message": f"Cache {'da URL' if url else 'completo'} limpo",
    }


async def run_refresh_url_cache(request: ScrapeRequest, user: dict):
    """Força o refresh do cache para uma URL específica."""
    try:
        await property_scraper.clear_cache(request.url)
        result = await property_scraper.scrape_url(request.url, use_cache=True)
        return {
            "success": True,
            "message": "Cache actualizado",
            "data": result,
        }
    except Exception as e:
        logger.error(f"Erro ao refrescar cache: {e}")
        raise HTTPException(status_code=500, detail=str(e))

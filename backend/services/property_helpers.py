"""Shared helpers for property routes.

Extraído de `routes/properties.py`.
Do not confuse with `services/property_scraper.py` (portal URL scraping).
"""
from __future__ import annotations

from database import db


async def get_next_reference() -> str:
    """Gera próxima referência interna (IMO-001, IMO-002...)"""
    last = await db.properties.find_one(
        {"internal_reference": {"$regex": "^IMO-"}},
        sort=[("internal_reference", -1)]
    )
    if last and last.get("internal_reference"):
        try:
            num = int(last["internal_reference"].split("-")[1])
            return f"IMO-{num + 1:03d}"
        except (ValueError, IndexError):
            pass
    return "IMO-001"

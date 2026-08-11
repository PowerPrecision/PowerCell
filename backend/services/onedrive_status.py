"""GET /onedrive/status.

Extraído de `routes/onedrive.py`.
Do **not** overwrite `services/onedrive.py`.
"""
from __future__ import annotations

import os

ONEDRIVE_SHARED_LINK = os.environ.get("ONEDRIVE_SHARED_LINK", "")
ONEDRIVE_WEB_URL = os.environ.get("ONEDRIVE_WEB_URL", "")


async def run_get_onedrive_status(user: dict):
    """Verificar estado da integração OneDrive."""
    return {
        "configured": bool(ONEDRIVE_SHARED_LINK),
        "method": "direct_link",
        "shared_link": ONEDRIVE_SHARED_LINK,
        "web_url": ONEDRIVE_WEB_URL,
    }

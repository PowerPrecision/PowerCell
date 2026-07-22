"""Changelog list handler.

Extraído de `routes/changelog.py`.
Do **not** overwrite changelog_service.py — use changelog_api_*.
"""
from __future__ import annotations

import logging

from fastapi import HTTPException

from services.changelog_service import get_changelogs

logger = logging.getLogger(__name__)


async def run_list_changelogs(limit: int):
    try:
        return await get_changelogs(limit=limit)
    except Exception as e:
        logger.error("Erro ao listar changelogs: %s", e)
        raise HTTPException(status_code=500, detail="Erro ao carregar atualizações")

"""
Helpers para GET /processes/{id}.

Extraído de `routes/processes.py` — latest_activity (PACOTE DA) e
portal_access (PACOTE DC).
"""
from __future__ import annotations

import logging
import os
from typing import Any, Optional

from fastapi import HTTPException

from database import db

logger = logging.getLogger(__name__)


async def load_process_doc_or_404(process_id: str) -> dict:
    process = await db.processes.find_one({"id": process_id}, {"_id": 0})
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")
    return process


def assert_can_view_process_or_403(user: dict, process: dict, can_view_fn) -> None:
    if not can_view_fn(user, process):
        raise HTTPException(status_code=403, detail="Acesso negado")


async def attach_latest_activity(process: dict, process_id: str) -> None:
    """PACOTE DA — injecta latest_activity (última nota com comment)."""
    try:
        latest_act = await db.activities.find_one(
            {"process_id": process_id, "comment": {"$exists": True, "$ne": ""}},
            {"_id": 0},
            sort=[("created_at", -1)],
        )
        process["latest_activity"] = latest_act
    except Exception as e:
        logger.warning(
            f"[GET-PROCESS] Erro ao buscar latest_activity para {process_id}: {e}"
        )
        process["latest_activity"] = None


async def attach_portal_access(process: dict, process_id: str) -> None:
    """PACOTE DC — código de acesso + magic link activo."""
    try:
        portal_access_code = None
        client_id = process.get("client_id")
        if client_id:
            client_doc = await db.clients.find_one(
                {"id": client_id}, {"portal_access_code": 1, "_id": 0},
            )
            if client_doc:
                portal_access_code = client_doc.get("portal_access_code")

        active_short_id = None
        active_magic_link = None
        token_doc = await db.portal_tokens.find_one(
            {"process_id": process_id},
            {"_id": 0, "short_id": 1, "created_at": 1},
        )
        if token_doc and token_doc.get("short_id"):
            active_short_id = token_doc["short_id"]
            fe_url = os.environ.get("FRONTEND_URL", "").rstrip("/")
            if fe_url:
                active_magic_link = f"{fe_url}/portal/{active_short_id}"

        process["portal_access"] = {
            "portal_access_code": portal_access_code,
            "short_id": active_short_id,
            "magic_link": active_magic_link,
            "has_active_token": active_short_id is not None,
        }
    except Exception as e:
        logger.warning(
            f"[GET-PROCESS] Erro ao buscar portal_access para {process_id}: {e}"
        )
        process["portal_access"] = None


def ensure_client_id_default(process: dict) -> None:
    process.setdefault("client_id", process.get("client_id") or "")


def serialize_process_detail_response(process: dict, process_id: str) -> Any:
    """ProcessResponse ou dict fallback se validação falhar."""
    from models.process import ProcessResponse
    try:
        return ProcessResponse(**process)
    except Exception as e:
        logger.warning(
            f"Erro de validação ProcessResponse para processo {process_id}: {e}"
        )
        return process


def build_portal_access_payload(
    *,
    portal_access_code: Optional[str],
    short_id: Optional[str],
    frontend_url: str,
) -> dict:
    """Constrói o dict portal_access (testável sem DB)."""
    magic_link = None
    fe = (frontend_url or "").rstrip("/")
    if short_id and fe:
        magic_link = f"{fe}/portal/{short_id}"
    return {
        "portal_access_code": portal_access_code,
        "short_id": short_id,
        "magic_link": magic_link,
        "has_active_token": short_id is not None,
    }

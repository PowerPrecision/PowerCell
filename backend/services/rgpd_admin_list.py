"""Admin RGPD list / CRUD / stats orchestration.

Extraído de `routes/rgpd.py`. Uses `RGPD_REQUESTS_COLLECTION` from
existing `services/rgpd_service.py`.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException

from database import db
from models.rgpd import RGPDConsentData
from services.rgpd_service import RGPD_REQUESTS_COLLECTION
from services.rgpd_helpers import _get_rgpd_or_404

logger = logging.getLogger(__name__)


async def run_list_all_rgpd(
    user: dict,
    status: Optional[str] = None,
    search: Optional[str] = None,
    page: int = 1,
    limit: int = 20,
):
    """Listar todos os RGPDs (administração)."""
    try:
        query = {}

        if status:
            query["status"] = status

        if search:
            query["$or"] = [
                {"client_name": {"$regex": search, "$options": "i"}},
                {"consent_data.contribuinte": {"$regex": search, "$options": "i"}},
                {"consent_data.nome": {"$regex": search, "$options": "i"}},
            ]

        skip = (page - 1) * limit

        total = await db[RGPD_REQUESTS_COLLECTION].count_documents(query)

        requests = await db[RGPD_REQUESTS_COLLECTION].find(
            query,
            {"_id": 0, "token": 0},
        ).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)

        return {
            "requests": requests,
            "total": total,
            "page": page,
            "limit": limit,
            "pages": (total + limit - 1) // limit,
        }
    except Exception as e:
        logger.error(f"Erro ao obter RGPD admin all: {e}")
        return {
            "requests": [],
            "total": 0,
            "page": page,
            "limit": limit,
            "pages": 0,
        }


async def run_get_rgpd_by_id(request_id: str, user: dict):
    """Obter detalhes de um RGPD específico."""
    request = await db[RGPD_REQUESTS_COLLECTION].find_one(
        {"id": request_id},
        {"_id": 0, "token": 0},
    )

    if not request:
        raise HTTPException(status_code=404, detail="RGPD não encontrado")

    process = await db.processes.find_one(
        {"id": request["process_id"]},
        {"_id": 0, "id": 1, "client_name": 1, "status": 1},
    )

    return {
        "rgpd": request,
        "process": process,
    }


async def run_update_rgpd_data(request_id: str, consent_data: RGPDConsentData, user: dict):
    """Atualizar dados do RGPD."""
    existing = await _get_rgpd_or_404(request_id)

    update_data = consent_data.model_dump()

    if existing.get("consent_data", {}).get("data_assinatura"):
        update_data["data_assinatura"] = existing["consent_data"]["data_assinatura"]

    if existing.get("consent_data", {}).get("assinatura") and not update_data.get("assinatura"):
        update_data["assinatura"] = existing["consent_data"]["assinatura"]

    await db[RGPD_REQUESTS_COLLECTION].update_one(
        {"id": request_id},
        {"$set": {"consent_data": update_data}},
    )

    logger.info("RGPD request updated by user")

    return {
        "success": True,
        "message": "RGPD atualizado com sucesso",
        "request_id": request_id,
    }


async def run_delete_rgpd(request_id: str, user: dict):
    """Eliminar um RGPD."""
    result = await db[RGPD_REQUESTS_COLLECTION].delete_one({"id": request_id})

    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="RGPD não encontrado")

    logger.info("RGPD request deleted by user")

    return {
        "success": True,
        "message": "RGPD eliminado com sucesso",
    }


async def run_get_rgpd_stats(user: dict):
    """Obter estatísticas de RGPD."""
    try:
        pipeline = [
            {
                "$group": {
                    "_id": "$status",
                    "count": {"$sum": 1},
                }
            }
        ]

        status_counts = await db[RGPD_REQUESTS_COLLECTION].aggregate(pipeline).to_list(10)

        stats = {
            "pending": 0,
            "signed": 0,
            "expired": 0,
            "cancelled": 0,
            "total": 0,
        }

        for item in status_counts:
            if item["_id"]:
                stats[item["_id"]] = item["count"]
                stats["total"] += item["count"]

        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        signed_today = await db[RGPD_REQUESTS_COLLECTION].count_documents({
            "status": "signed",
            "signed_at": {"$gte": today.isoformat()},
        })

        stats["signed_today"] = signed_today

        return stats
    except Exception as e:
        logger.error(f"Erro ao obter estatísticas RGPD: {e}")
        return {
            "pending": 0,
            "signed": 0,
            "expired": 0,
            "cancelled": 0,
            "total": 0,
            "signed_today": 0,
        }

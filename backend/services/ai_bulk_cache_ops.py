"""NIF/duplicate cache and pending-review handlers for AI bulk import.

Extraído de `routes/ai_bulk.py`.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from database import db
from routes.ai_bulk import cache as ai_bulk_cache
from routes.ai_bulk.matching import find_client_by_name, find_client_by_nif

logger = logging.getLogger(__name__)


async def run_clear_duplicate_cache(user: dict):
    """Limpar cache de documentos duplicados."""
    count = ai_bulk_cache.clear_duplicate_cache()
    return {"message": f"Cache limpo. {count} documentos removidos do cache."}


async def run_get_nif_cache_stats(user: dict):
    """Obter estatísticas do cache de sessão NIF."""
    now = datetime.now(timezone.utc)
    db_count = await db.nif_mappings.count_documents({})

    stats = {
        "total_entries_memory": len(ai_bulk_cache.nif_session_cache),
        "total_entries_db": db_count,
        "ttl_days": ai_bulk_cache.NIF_CACHE_TTL_SECONDS // 86400,
        "entries": [],
    }

    for folder_key, cached in ai_bulk_cache.nif_session_cache.items():
        matched_at = cached.get("matched_at")
        if isinstance(matched_at, str):
            matched_at = datetime.fromisoformat(matched_at.replace("Z", "+00:00"))

        age_seconds = (now - matched_at).total_seconds() if matched_at else 0

        stats["entries"].append({
            "folder": folder_key,
            "nif": cached.get("nif"),
            "client_name": cached.get("client_name"),
            "age_days": round(age_seconds / 86400, 1),
            "expires_in_days": max(
                0,
                round(
                    (ai_bulk_cache.NIF_CACHE_TTL_SECONDS - age_seconds) / 86400,
                    1,
                ),
            ),
        })

    return stats


async def run_clear_nif_cache(user: dict):
    """Limpar todo o cache de sessão NIF."""
    memory_count, _ = ai_bulk_cache.clear_nif_cache()

    db_result = await db.nif_mappings.delete_many({})
    db_count = db_result.deleted_count

    logger.info(
        f"[NIF CACHE] Cache limpo manualmente. Memória: {memory_count}, DB: {db_count}"
    )
    return {
        "message": (
            f"Cache NIF limpo. {memory_count} mapeamentos removidos da memória, "
            f"{db_count} da base de dados."
        )
    }


async def run_add_nif_mapping_manual(folder_name: str, nif: str, user: dict):
    """Adicionar mapeamento NIF → Cliente manualmente."""
    process = await find_client_by_nif(nif)

    if not process:
        process = await find_client_by_name(folder_name)

        if process:
            await db.processes.update_one(
                {"id": process["id"]},
                {
                    "$set": {
                        "personal_data.nif": nif,
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    }
                },
            )
            logger.info("[NIF] NIF adicionado ao cliente")
        else:
            return {
                "success": False,
                "error": "Nenhum cliente encontrado com o NIF ou nome fornecido",
            }

    await ai_bulk_cache.cache_nif_mapping(
        folder_name=folder_name,
        nif=nif,
        process_id=process["id"],
        client_name=process.get("client_name"),
    )

    return {
        "success": True,
        "message": (
            f"Mapeamento adicionado: '{folder_name}' -> NIF {nif} "
            f"-> '{process.get('client_name')}'"
        ),
    }


async def run_get_pending_reviews(user: dict):
    """Obter lista de processos com dados pendentes de revisão."""
    try:
        processes = await db.processes.find(
            {"ai_pending_review": {"$exists": True, "$ne": []}},
            {"_id": 0, "id": 1, "client_name": 1, "status": 1, "ai_pending_review": 1},
        ).to_list(100)

        result = []
        for process in processes:
            pending_reviews = process.get("ai_pending_review", [])
            if pending_reviews:
                result.append({
                    "process_id": process.get("id"),
                    "client_name": process.get("client_name"),
                    "status": process.get("status"),
                    "pending_count": len(pending_reviews),
                    "pending_reviews": pending_reviews,
                })

        return {"total": len(result), "processes": result}

    except Exception as e:
        logger.error(f"Erro ao obter revisões pendentes: {e}")
        return {"total": 0, "processes": []}

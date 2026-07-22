"""Client-side match wrappers (properties / leads / all / summary).

Extraído de `routes/match.py`.
Delegates to services/client_match.py — do **not** overwrite that module.
"""
from __future__ import annotations

from services.client_match import (
    find_matching_leads_for_client,
    find_matching_properties_for_client,
    find_all_matches_for_client,
    get_match_summary_for_client,
)


async def run_get_all_matches_for_client(process_id: str, user: dict):
    """Encontrar TODOS os imóveis compatíveis (angariados + leads) para um cliente."""
    return await find_all_matches_for_client(process_id)


async def run_get_matching_properties(process_id: str, user: dict):
    """Encontrar imóveis ANGARIADOS compatíveis com o perfil do cliente."""
    matches = await find_matching_properties_for_client(process_id)

    return {
        "process_id": process_id,
        "total_matches": len(matches),
        "matches": matches,
        "source": "properties"
    }


async def run_get_matching_leads(process_id: str, user: dict):
    """Encontrar leads de imóveis compatíveis com o perfil do cliente."""
    matches = await find_matching_leads_for_client(process_id)

    return {
        "process_id": process_id,
        "total_matches": len(matches),
        "matches": matches,
        "source": "leads"
    }


async def run_get_client_match_summary(process_id: str, user: dict):
    """Obter resumo de correspondências para um cliente."""
    summary = await get_match_summary_for_client(process_id)
    summary["process_id"] = process_id

    return summary

"""Property / lead → client match wrappers.

Extraído de `routes/match.py`.
Delegates to services/client_match.py — do **not** overwrite that module.
"""
from __future__ import annotations

from services.client_match import (
    find_matching_clients_for_lead,
    find_matching_clients_for_property,
)


async def run_get_matching_clients_for_property(property_id: str, user: dict):
    """Encontrar clientes que podem ter interesse num imóvel ANGARIADO."""
    matches = await find_matching_clients_for_property(property_id)

    return {
        "property_id": property_id,
        "total_matches": len(matches),
        "matches": matches,
    }


async def run_get_matching_clients_for_lead(lead_id: str, user: dict):
    """Encontrar clientes que podem ter interesse num imóvel específico (lead)."""
    matches = await find_matching_clients_for_lead(lead_id)

    return {
        "lead_id": lead_id,
        "total_matches": len(matches),
        "matches": matches,
    }

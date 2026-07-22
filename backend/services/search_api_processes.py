"""Advanced process search handler.

Extraído de `routes/search.py`.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from database import db
from utils.input_sanitization import sanitize_string
from utils.search_filters import (
    create_accent_insensitive_regex,
    build_multiword_search_filter,
)


async def run_search_processes(
    q: str,
    status: Optional[str],
    process_type: Optional[str],
    limit: int,
    user: dict,
) -> List[Dict[str, Any]]:
    """Pesquisa avançada em processos."""
    # Sanitize search term to prevent ReDoS / regex injection
    search_term = sanitize_string(q, max_length=200)
    if not search_term:
        return []

    regex_pattern = create_accent_insensitive_regex(search_term)
    simple_regex = {"$regex": re.escape(search_term), "$options": "i"}

    name_filter = build_multiword_search_filter(search_term, "client_name")

    query = {
        "$or": [
            name_filter,
            {"client_email": simple_regex},
            {"personal_data.nif": simple_regex},
            {"personal_data.email": simple_regex},
            {"personal_data.telefone": simple_regex},
        ]
    }

    if status:
        query["status"] = status

    if process_type:
        query["process_type"] = process_type

    processes = await db.processes.find(
        query,
        {"_id": 0}
    ).sort("updated_at", -1).limit(limit).to_list(limit)

    return processes

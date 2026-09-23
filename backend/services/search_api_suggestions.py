"""Search suggestions handler.

Extraído de `routes/search.py`.
"""
from __future__ import annotations

from typing import List

from database import db
from services.tenant_network import build_tenant_condition
from utils.input_sanitization import sanitize_string
from utils.search_filters import (
    create_accent_insensitive_regex,
    build_multiword_search_filter,
)


async def run_get_search_suggestions(q: str, user: dict) -> List[str]:
    """Obter sugestões de pesquisa baseadas no histórico e dados existentes."""
    # Sanitize search term to prevent ReDoS / regex injection
    search_term = sanitize_string(q, max_length=200)
    if not search_term:
        return []
    search_term = search_term.lower()
    suggestions = set()

    # Regex que ignora acentos para sugestões
    regex_pattern = create_accent_insensitive_regex(search_term)
    name_filter = build_multiword_search_filter(search_term, "client_name")

    # Isolamento multi-tenant (Lote 4, ponto 10). As sugestões devolvem
    # NOMES DE CLIENTES: é fuga de dados pessoais mesmo sem chegar a
    # abrir o processo.
    tenant_condition = await build_tenant_condition(user)

    # Buscar nomes de clientes que começam com o termo
    clients = await db.processes.find(
        {"$and": [tenant_condition, name_filter]},
        {"_id": 0, "client_name": 1}
    ).limit(5).to_list(5)

    for client in clients:
        suggestions.add(client.get("client_name", ""))

    # Buscar títulos de tarefas
    tasks = await db.tasks.find(
        {"$and": [tenant_condition, {"title": regex_pattern}]},
        {"_id": 0, "title": 1}
    ).limit(3).to_list(3)

    for task in tasks:
        suggestions.add(task.get("title", ""))

    return list(suggestions)[:10]

"""IDs de utilizadores atribuídos a um processo (portal notify helpers).

Extraído de `routes/portal.py`. Fonte de verdade para
`process_portal_messages.collect_assigned_user_ids`.
"""
from __future__ import annotations


def get_all_assigned_user_ids(process: dict) -> list:
    """Lista deduplicada de TODOS os user_ids atribuídos ao processo.

    Inclui consultores, mediadores, indexação e parceiro.
    Usa os campos novos (_ids) com fallback para os antigos (_id).
    """
    ids = set()

    for uid in (process.get("assigned_consultor_ids") or []):
        if uid:
            ids.add(uid)
    uid = process.get("assigned_consultor_id")
    if uid:
        ids.add(uid)

    for uid in (process.get("assigned_mediador_ids") or []):
        if uid:
            ids.add(uid)
    uid = process.get("assigned_mediador_id")
    if uid:
        ids.add(uid)

    uid = process.get("assigned_indexacao_id")
    if uid:
        ids.add(uid)

    uid = process.get("assigned_parceiro_id")
    if uid:
        ids.add(uid)

    return list(ids)


# Compat alias (routes.portal used underscore prefix)
_get_all_assigned_user_ids = get_all_assigned_user_ids

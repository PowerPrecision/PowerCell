"""
====================================================================
ENRIQUECIMENTO BATCH DE LISTAGENS DE PROCESSOS - CREDITOIMO
====================================================================
Pipelines de aggregação partilhados por GET /processes, /paginated,
/kanban e /my-clients — evita duplicação e divergência de chaves.

Extraído de routes/processes.py.
====================================================================
"""
import logging
from typing import List, Optional

from database import db

logger = logging.getLogger(__name__)


async def enrich_with_portal_flags(
    processes: List[dict],
    *,
    process_ids: Optional[List[str]] = None,
) -> None:
    """
    Injeta has_unread_messages e has_new_documents em cada processo.

    Mutates `processes` in place. Se a lista estiver vazia, no-op.
    """
    if not processes:
        return

    ids = process_ids or [p["id"] for p in processes if p.get("id")]
    if not ids:
        for p in processes:
            p.setdefault("has_unread_messages", False)
            p.setdefault("has_new_documents", False)
        return

    unread = await db.portal_messages.aggregate([
        {"$match": {
            "process_id": {"$in": ids},
            "sender_type": "client",
            "read_by_staff": False,
        }},
        {"$group": {"_id": "$process_id", "unread_count": {"$sum": 1}}},
    ]).to_list(1000)
    unread_map = {r["_id"]: r["unread_count"] > 0 for r in unread}

    new_docs = await db.documents.aggregate([
        {"$match": {
            "process_id": {"$in": ids},
            "status": "uploaded",
        }},
        {"$group": {"_id": "$process_id", "new_count": {"$sum": 1}}},
    ]).to_list(1000)
    new_docs_map = {r["_id"]: r["new_count"] > 0 for r in new_docs}

    for p in processes:
        pid = p.get("id")
        p["has_unread_messages"] = unread_map.get(pid, False)
        p["has_new_documents"] = new_docs_map.get(pid, False)


async def enrich_with_latest_note(
    processes: List[dict],
    *,
    process_ids: Optional[List[str]] = None,
    note_key: str = "latest_note",
    at_key: str = "latest_note_at",
    by_key: str = "latest_note_by",
    set_activity_preview: bool = True,
) -> None:
    """
    Injeta a última nota/comentário da coleção activities.

    Por defeito usa as chaves latest_note / latest_note_at / latest_note_by
    (GET /processes e /paginated). My Clients usa note_key="latest_activity_note".
    """
    if not processes:
        return

    ids = process_ids or [p["id"] for p in processes if p.get("id")]
    notes_map = {}
    if ids:
        rows = await db.activities.aggregate([
            {"$match": {
                "process_id": {"$in": ids},
                "comment": {"$exists": True, "$ne": ""},
            }},
            {"$sort": {"created_at": -1}},
            {"$group": {
                "_id": "$process_id",
                note_key: {"$first": "$comment"},
                at_key: {"$first": "$created_at"},
                by_key: {"$first": "$user_name"},
            }},
        ]).to_list(1000)
        notes_map = {r["_id"]: r for r in rows}

    for p in processes:
        note_info = notes_map.get(p.get("id"))
        if note_info:
            p[note_key] = note_info.get(note_key)
            p[at_key] = note_info.get(at_key)
            p[by_key] = note_info.get(by_key)
        else:
            p[note_key] = None
            p[at_key] = None
            p[by_key] = None
        if set_activity_preview:
            p["latest_activity_preview"] = p.get(note_key)


async def get_latest_notes_map(
    process_ids: List[str],
    *,
    note_key: str = "latest_activity_note",
    at_key: str = "latest_activity_note_at",
    by_key: str = "latest_activity_note_by",
) -> dict:
    """
    Devolve mapa process_id → {note_key, at_key, by_key} sem mutar processos.

    Útil quando o caller reconstrói um DTO (ex.: My Clients) em vez de
    enriquecer o documento in-place.
    """
    if not process_ids:
        return {}

    rows = await db.activities.aggregate([
        {"$match": {
            "process_id": {"$in": process_ids},
            "comment": {"$exists": True, "$ne": ""},
        }},
        {"$sort": {"created_at": -1}},
        {"$group": {
            "_id": "$process_id",
            note_key: {"$first": "$comment"},
            at_key: {"$first": "$created_at"},
            by_key: {"$first": "$user_name"},
        }},
    ]).to_list(1000)
    return {r["_id"]: r for r in rows}


async def get_portal_flags_maps(process_ids: List[str]) -> tuple:
    """
    Devolve (unread_map, new_docs_map) sem mutar processos.

    Útil para My Clients onde o DTO é reconstruído.
    """
    unread_map = {}
    new_docs_map = {}
    if not process_ids:
        return unread_map, new_docs_map

    unread = await db.portal_messages.aggregate([
        {"$match": {
            "process_id": {"$in": process_ids},
            "sender_type": "client",
            "read_by_staff": False,
        }},
        {"$group": {"_id": "$process_id", "unread_count": {"$sum": 1}}},
    ]).to_list(1000)
    unread_map = {r["_id"]: r["unread_count"] > 0 for r in unread}

    new_docs = await db.documents.aggregate([
        {"$match": {
            "process_id": {"$in": process_ids},
            "status": "uploaded",
        }},
        {"$group": {"_id": "$process_id", "new_count": {"$sum": 1}}},
    ]).to_list(1000)
    new_docs_map = {r["_id"]: r["new_count"] > 0 for r in new_docs}
    return unread_map, new_docs_map


async def enrich_with_latest_activity(processes: List[dict]) -> None:
    """
    Injeta latest_activity (objeto completo da última activity com comment).

    Usado pelo Kanban / ProcessDetailsModal. Falhas são logadas e
    latest_activity fica None.
    """
    if not processes:
        return

    process_ids = [p["id"] for p in processes if p.get("id")]
    if not process_ids:
        for p in processes:
            p.setdefault("latest_activity", None)
        return

    try:
        rows = await db.activities.aggregate([
            {"$match": {
                "process_id": {"$in": process_ids},
                "comment": {"$exists": True, "$ne": ""},
            }},
            {"$sort": {"created_at": -1}},
            {"$group": {
                "_id": "$process_id",
                "comment": {"$first": "$comment"},
                "user_name": {"$first": "$user_name"},
                "user_role": {"$first": "$user_role"},
                "created_at": {"$first": "$created_at"},
            }},
        ]).to_list(1000)
        acts_map = {r["_id"]: r for r in rows}
        for p in processes:
            act = acts_map.get(p.get("id"))
            if act:
                p["latest_activity"] = {k: v for k, v in act.items() if k != "_id"}
            else:
                p["latest_activity"] = None
    except Exception as e:
        logger.warning(f"[ENRICH] Erro no batch enrichment latest_activity: {e}")
        for p in processes:
            p.setdefault("latest_activity", None)


async def enrich_with_client_lookup(processes: List[dict]) -> None:
    """
    Preenche client_name/email/phone/nif em falta via batch lookup em clients.

    Processos Fase 3 não embutem dados pessoais — este passo usa setdefault
    para não sobrescrever valores já presentes.
    """
    if not processes:
        return

    client_ids_to_fetch = set()
    for p in processes:
        if p.get("client_id") and not p.get("client_name"):
            client_ids_to_fetch.add(p["client_id"])

    if not client_ids_to_fetch:
        return

    client_docs = await db.clients.find(
        {"id": {"$in": list(client_ids_to_fetch)}},
        {"_id": 0, "id": 1, "nome": 1, "contacto": 1, "dados_pessoais": 1}
    ).to_list(len(client_ids_to_fetch))

    try:
        from services.encryption import decrypt_client_data
        client_docs = [decrypt_client_data(c) for c in client_docs]
    except Exception:
        pass

    client_map = {}
    for c in client_docs:
        contacto = c.get("contacto") or {}
        dados_pessoais = c.get("dados_pessoais") or {}
        client_map[c["id"]] = {
            "nome": c.get("nome", ""),
            "email": contacto.get("email", ""),
            "telefone": contacto.get("telefone", ""),
            "nif": dados_pessoais.get("nif", c.get("nif", "")),
        }

    for p in processes:
        cid = p.get("client_id")
        if cid and cid in client_map:
            cinfo = client_map[cid]
            p.setdefault("client_name", cinfo["nome"])
            p.setdefault("client_email", cinfo["email"])
            p.setdefault("client_phone", cinfo["telefone"])
            p.setdefault("client_nif", cinfo["nif"])

"""
Helpers para GET /processes/my-clients.

Extraído de `routes/processes.py` para isolar formatação, ordenação e
enriquecimento batch (mensagens/documentos/notas) da lógica HTTP.
"""
from __future__ import annotations

from typing import Any, Callable, Optional

from services.process_list_filters import role_has_client_portfolio


LEAD_CLIENTS_PROJECTION = {
    "_id": 0,
    "id": 1,
    "nome": 1,
    "contacto": 1,
    "created_at": 1,
    "updated_at": 1,
    "fonte": 1,
    "assigned_to": 1,
    "lead_status": 1,
}


def format_lead_as_my_client_row(lead: dict) -> dict:
    """Converte um documento `clients` (lead) no shape da lista my-clients."""
    contacto = lead.get("contacto", {}) or {}
    return {
        "id": lead.get("id"),
        "client_id": lead.get("id"),
        "process_number": None,
        "client_name": lead.get("nome", "Sem nome"),
        "client_email": contacto.get("email", ""),
        "client_phone": contacto.get("telefone", ""),
        "status": "lead",
        "status_label": "Lead",
        "status_color": "#8B5CF6",
        "process_type": "lead",
        "consultor_name": "",
        "pending_actions": [],
        "pending_count": 0,
        "created_at": lead.get("created_at"),
        "updated_at": lead.get("updated_at"),
        "deed_date": None,
        "has_property": False,
        "is_lead": True,
    }


def my_clients_sort_key(status_map: dict) -> Callable[[dict], tuple]:
    """Ordena leads primeiro, depois por order do workflow e nome."""

    def get_sort_key(item: dict) -> tuple:
        if item.get("is_lead"):
            return (0, (item.get("client_name") or "").lower())
        status_info = status_map.get(item.get("status"), {})
        phase_order = status_info.get("order", 999)
        client_name = (item.get("client_name") or "").lower()
        return (phase_order, client_name)

    return get_sort_key


def group_tasks_by_process(tasks: list[dict]) -> dict[str, list[dict]]:
    """Agrupa tarefas por process_id."""
    tasks_by_process: dict[str, list[dict]] = {}
    for task in tasks:
        pid = task.get("process_id")
        if not pid:
            continue
        tasks_by_process.setdefault(pid, []).append(task)
    return tasks_by_process


def build_pending_actions(
    pending_tasks: list[dict],
    fase: Optional[str] = None,
) -> list[dict]:
    """Monta a lista de acções pendentes (até 3 tarefas + hint documental)."""
    pending_actions: list[dict] = []

    for task in pending_tasks[:3]:
        pending_actions.append({
            "type": "task",
            "title": task.get("title", "Tarefa"),
            "priority": task.get("priority", "normal"),
            "due_date": task.get("due_date"),
        })

    if len(pending_tasks) > 3:
        pending_actions.append({
            "type": "info",
            "title": f"+{len(pending_tasks) - 3} tarefas adicionais",
            "priority": "normal",
        })

    if fase in ("fase_documental", "fase_documental_ii"):
        pending_actions.append({
            "type": "document",
            "title": "Verificar documentos em falta",
            "priority": "high",
        })

    return pending_actions


def build_my_clients_process_row(
    process: dict,
    *,
    status_map: dict,
    tasks_by_process: dict[str, list[dict]],
    consultor_map: dict[str, str],
    unread_map: dict[str, bool],
    new_docs_map: dict[str, bool],
    notes_map: dict[str, dict],
) -> dict:
    """Linha enriquecida de um processo (não-lead) para my-clients."""
    status_info = status_map.get(process.get("status"), {})
    pending_tasks = tasks_by_process.get(process["id"], [])
    pending_actions = build_pending_actions(
        pending_tasks, process.get("status"),
    )
    note = notes_map.get(process.get("id"), {})

    return {
        "id": process["id"],
        "client_id": process.get("client_id"),
        "process_number": process.get("process_number"),
        "client_name": process.get("client_name", "Sem nome"),
        "client_email": process.get("client_email"),
        "client_phone": process.get("client_phone"),
        "status": process.get("status"),
        "status_label": status_info.get("label", process.get("status", "Desconhecido")),
        "status_color": status_info.get("color", "#6B7280"),
        "process_type": process.get("process_type"),
        "consultor_name": consultor_map.get(process.get("assigned_consultor_id"), ""),
        "pending_actions": pending_actions,
        "pending_count": len(pending_tasks),
        "created_at": process.get("created_at"),
        "updated_at": process.get("updated_at"),
        "deed_date": process.get("deed_date"),
        "has_property": bool(process.get("property_id")),
        "has_unread_messages": unread_map.get(process.get("id"), False),
        "has_new_documents": new_docs_map.get(process.get("id"), False),
        "latest_activity_note": note.get("latest_activity_note"),
        "latest_activity_note_at": note.get("latest_activity_note_at"),
        "latest_activity_note_by": note.get("latest_activity_note_by"),
    }


def finalize_lead_row(lead_row: dict) -> dict:
    """Garante flags de portal/notas nos leads formatados."""
    lead_row["has_unread_messages"] = False
    lead_row["has_new_documents"] = False
    lead_row["latest_activity_note"] = None
    return lead_row


async def fetch_unread_messages_map(db: Any, process_ids: list[str]) -> dict[str, bool]:
    """process_id → tem mensagens não lidas do cliente."""
    if not process_ids:
        return {}
    rows = await db.portal_messages.aggregate([
        {"$match": {
            "process_id": {"$in": process_ids},
            "sender_type": "client",
            "read_by_staff": False,
        }},
        {"$group": {"_id": "$process_id", "unread_count": {"$sum": 1}}},
    ]).to_list(1000)
    return {r["_id"]: r["unread_count"] > 0 for r in rows}


async def fetch_new_documents_map(db: Any, process_ids: list[str]) -> dict[str, bool]:
    """process_id → tem documentos em estado uploaded."""
    if not process_ids:
        return {}
    rows = await db.documents.aggregate([
        {"$match": {
            "process_id": {"$in": process_ids},
            "status": "uploaded",
        }},
        {"$group": {"_id": "$process_id", "new_count": {"$sum": 1}}},
    ]).to_list(1000)
    return {r["_id"]: r["new_count"] > 0 for r in rows}


async def fetch_latest_activity_notes_map(
    db: Any, process_ids: list[str],
) -> dict[str, dict]:
    """process_id → última nota (comment) da coleção activities."""
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
            "latest_activity_note": {"$first": "$comment"},
            "latest_activity_note_at": {"$first": "$created_at"},
            "latest_activity_note_by": {"$first": "$user_name"},
        }},
    ]).to_list(1000)
    return {r["_id"]: r for r in rows}


async def fetch_orphan_leads_for_my_clients(
    db: Any,
    user_id: str,
    role: str,
    leads_query_builder,
) -> list[dict]:
    """
    Leads órfãos (só consultor/intermediário).
    `leads_query_builder(user_id)` → filtro Mongo.
    """
    from models.auth import UserRole
    if role not in [UserRole.CONSULTOR, UserRole.INTERMEDIARIO]:
        return []
    from services.encryption import decrypt_clients_list
    # PACOTE DG — excluir clientes eliminados (soft-delete) da lista de leads órfãos.
    leads_cursor = await db.clients.find(
        {"$and": [leads_query_builder(user_id), {"is_deleted": {"$ne": True}}]},
        LEAD_CLIENTS_PROJECTION,
    ).to_list(500)
    leads_cursor = decrypt_clients_list(leads_cursor)
    return [format_lead_as_my_client_row(lead) for lead in leads_cursor]


async def fetch_pending_tasks_by_process(
    db: Any, process_ids: list[str],
) -> dict[str, list[dict]]:
    if not process_ids:
        return {}
    tasks = await db.tasks.find(
        {"process_id": {"$in": process_ids}, "completed": {"$ne": True}},
        {"_id": 0, "id": 1, "process_id": 1, "title": 1, "priority": 1, "due_date": 1},
    ).to_list(500)
    return group_tasks_by_process(tasks)


async def fetch_consultor_name_map(
    db: Any, items: list[dict],
) -> dict[str, str]:
    consultor_ids = list({
        p.get("assigned_consultor_id")
        for p in items
        if p.get("assigned_consultor_id")
    })
    if not consultor_ids:
        return {}
    consultores = await db.users.find(
        {"id": {"$in": consultor_ids}},
        {"_id": 0, "id": 1, "name": 1},
    ).to_list(100)
    return {c["id"]: c["name"] for c in consultores}


def assemble_my_clients_rows(
    paginated_items: list[dict],
    *,
    status_map: dict,
    tasks_by_process: dict[str, list[dict]],
    consultor_map: dict[str, str],
    unread_map: dict[str, bool],
    new_docs_map: dict[str, bool],
    notes_map: dict[str, dict],
) -> list[dict]:
    rows: list[dict] = []
    for p in paginated_items:
        if p.get("is_lead"):
            rows.append(finalize_lead_row(p))
            continue
        rows.append(build_my_clients_process_row(
            p,
            status_map=status_map,
            tasks_by_process=tasks_by_process,
            consultor_map=consultor_map,
            unread_map=unread_map,
            new_docs_map=new_docs_map,
            notes_map=notes_map,
        ))
    return rows


def build_my_clients_response(
    *,
    clients: list[dict],
    total: int,
    page: int,
    size: int,
    pages: int,
    user_id: str,
    user_role: str,
    leads_count: int,
) -> dict:
    return {
        "clients": clients,
        "total": total,
        "page": page,
        "size": size,
        "pages": pages,
        "user_id": user_id,
        "user_role": user_role,
        "leads_count": leads_count,
    }


def process_ids_from_my_clients_page(paginated_items: list[dict]) -> list[str]:
    """IDs de processos (exclui leads) na página actual."""
    return [
        p["id"] for p in paginated_items
        if p.get("id") and not p.get("is_lead")
    ]


async def run_get_my_clients(
    *,
    db: Any,
    user: dict,
    role: str,
    page: int,
    size: int,
    decrypt_list_fn,
    my_clients_projection: dict,
    build_process_query_fn,
    build_leads_query_fn,
    slice_page_fn,
    load_status_map_fn,
) -> dict:
    """Orquestra GET /processes/my-clients."""
    user_id = user["id"]
    user_email = user.get("email", "")

    # Admin / CEO / Indexação: sem carteira — devolver vazio de imediato.
    if not role_has_client_portfolio(role):
        return build_my_clients_response(
            clients=[],
            total=0,
            page=page,
            size=size,
            pages=0,
            user_id=user_id,
            user_role=role,
            leads_count=0,
        )

    query = build_process_query_fn(user_id, user_email, role)
    processes = await db.processes.find(
        query,
        my_clients_projection,
    ).to_list(5000)
    processes = decrypt_list_fn(
        processes,
        fields_to_decrypt=["client_phone", "client_nif"],
    )

    leads = await fetch_orphan_leads_for_my_clients(
        db, user_id, role, build_leads_query_fn,
    )
    status_map = await load_status_map_fn()

    all_items = sorted(processes + leads, key=my_clients_sort_key(status_map))
    paginated_items, total, pages = slice_page_fn(all_items, page, size)

    process_ids = process_ids_from_my_clients_page(paginated_items)
    tasks_by_process = await fetch_pending_tasks_by_process(db, process_ids)
    consultor_map = await fetch_consultor_name_map(db, paginated_items)
    unread_map = await fetch_unread_messages_map(db, process_ids)
    new_docs_map = await fetch_new_documents_map(db, process_ids)
    notes_map = await fetch_latest_activity_notes_map(db, process_ids)

    clients_list = assemble_my_clients_rows(
        paginated_items,
        status_map=status_map,
        tasks_by_process=tasks_by_process,
        consultor_map=consultor_map,
        unread_map=unread_map,
        new_docs_map=new_docs_map,
        notes_map=notes_map,
    )

    return build_my_clients_response(
        clients=clients_list,
        total=total,
        page=page,
        size=size,
        pages=pages,
        user_id=user_id,
        user_role=role,
        leads_count=len(leads),
    )

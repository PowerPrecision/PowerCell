"""
Dashboard de documentos a expirar.

Extraído de `routes/documents.py` (`get_expiring_documents_dashboard`).
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any, Optional

from database import db
from models.auth import UserRole
from services.document_constants import DEFAULT_CLIENT_NAME, DEFAULT_CONSULTOR_NAME


def build_expiry_doc_query(
    today: datetime,
    days_ahead: int,
    urgency: Optional[str] = None,
) -> dict:
    """Mongo query para document_metadata com expiry_date no intervalo."""
    future_date = today + timedelta(days=days_ahead)
    doc_query: dict[str, Any] = {
        "expiry_date": {
            "$ne": None,
            "$gte": today.strftime("%Y-%m-%d"),
            "$lte": future_date.strftime("%Y-%m-%d"),
        }
    }
    if not urgency:
        return doc_query

    if urgency == "critical":
        critical_date = (today + timedelta(days=7)).strftime("%Y-%m-%d")
        doc_query["expiry_date"]["$lt"] = critical_date
    elif urgency == "high":
        high_start = (today + timedelta(days=7)).strftime("%Y-%m-%d")
        high_end = (today + timedelta(days=30)).strftime("%Y-%m-%d")
        doc_query["expiry_date"]["$gte"] = high_start
        doc_query["expiry_date"]["$lt"] = high_end
    elif urgency == "medium":
        medium_start = (today + timedelta(days=30)).strftime("%Y-%m-%d")
        doc_query["expiry_date"]["$gte"] = medium_start
    return doc_query


def build_expiring_processes_query(
    process_ids: list[str],
    *,
    is_management: bool,
    user_id: str,
    consultor_id: Optional[str] = None,
) -> dict:
    """Filtro de processos para o dashboard (ACL + consultor)."""
    processes_query: dict[str, Any] = {"id": {"$in": process_ids}}
    if not is_management:
        processes_query["$or"] = [
            {"assigned_consultor_id": user_id},
            {"consultor_id": user_id},
            {"assigned_mediador_id": user_id},
            {"mediador_id": user_id},
        ]
    elif consultor_id:
        processes_query["$or"] = [
            {"assigned_consultor_id": consultor_id},
            {"consultor_id": consultor_id},
            {"assigned_mediador_id": consultor_id},
            {"mediador_id": consultor_id},
        ]
    return processes_query


def filter_docs_by_authorized_and_search(
    expiring_docs: list[dict],
    process_map: dict[str, dict],
    search: Optional[str] = None,
) -> list[dict]:
    authorized_process_ids = set(process_map.keys())
    filtered = [d for d in expiring_docs if d.get("process_id") in authorized_process_ids]
    if not search:
        return filtered
    search_lower = search.lower()
    search_process_ids = [
        pid for pid, p in process_map.items()
        if search_lower in (p.get("client_name") or "").lower()
    ]
    return [d for d in filtered if d.get("process_id") in search_process_ids]


def collect_assignee_ids_from_processes(processes: list[dict]) -> set[str]:
    ids: set[str] = set()
    for p in processes:
        for key in (
            "assigned_consultor_id", "consultor_id",
            "assigned_mediador_id", "mediador_id",
        ):
            if p.get(key):
                ids.add(p[key])
    return ids


def compute_expiry_stats(filtered_docs: list[dict], today: datetime) -> dict:
    stats = {"critical": 0, "high": 0, "medium": 0, "total": len(filtered_docs)}
    today_naive = today.replace(tzinfo=None) if today.tzinfo else today
    for doc in filtered_docs:
        try:
            expiry = datetime.strptime(doc["expiry_date"], "%Y-%m-%d")
            days_until = (expiry - today_naive).days
            if days_until < 7:
                stats["critical"] += 1
            elif days_until < 30:
                stats["high"] += 1
            else:
                stats["medium"] += 1
        except (ValueError, KeyError, TypeError):
            pass
    return stats


def _days_until_and_urgency(expiry_date: str, today: datetime) -> tuple[Optional[int], str]:
    today_naive = today.replace(tzinfo=None) if today.tzinfo else today
    try:
        expiry = datetime.strptime(expiry_date, "%Y-%m-%d")
        days_until = (expiry - today_naive).days
        if days_until < 7:
            return days_until, "critical"
        if days_until < 30:
            return days_until, "high"
        return days_until, "medium"
    except (ValueError, KeyError, TypeError):
        return None, "unknown"


def group_expiring_docs_by_client(
    filtered_docs: list[dict],
    process_map: dict[str, dict],
    consultor_map: dict[str, str],
    today: datetime,
) -> list[dict]:
    clients_data: dict[str, dict] = {}

    for doc in filtered_docs:
        process_id = doc.get("process_id")
        if not process_id or process_id not in process_map:
            continue

        process = process_map[process_id]
        client_name = doc.get("client_name") or process.get(
            "client_name", DEFAULT_CLIENT_NAME,
        )

        if process_id not in clients_data:
            consultor_id = (
                process.get("assigned_consultor_id")
                or process.get("consultor_id")
                or process.get("assigned_mediador_id")
                or process.get("mediador_id")
            )
            clients_data[process_id] = {
                "process_id": process_id,
                "client_name": client_name,
                "consultor_id": consultor_id,
                "consultor_name": consultor_map.get(
                    consultor_id, DEFAULT_CONSULTOR_NAME,
                ),
                "documents": [],
                "critical_count": 0,
                "high_count": 0,
                "medium_count": 0,
            }

        days_until, urgency_level = _days_until_and_urgency(
            doc.get("expiry_date"), today,
        )
        if urgency_level == "critical":
            clients_data[process_id]["critical_count"] += 1
        elif urgency_level == "high":
            clients_data[process_id]["high_count"] += 1
        elif urgency_level == "medium":
            clients_data[process_id]["medium_count"] += 1

        clients_data[process_id]["documents"].append({
            "id": doc.get("id"),
            "filename": doc.get("filename"),
            "category": doc.get("ai_category"),
            "subcategory": doc.get("ai_subcategory"),
            "expiry_date": doc.get("expiry_date"),
            "days_until": days_until,
            "urgency": urgency_level,
            "s3_path": doc.get("s3_path"),
        })

    return sort_clients_by_urgency(list(clients_data.values()))


def sort_clients_by_urgency(clients_list: list[dict]) -> list[dict]:
    clients_list.sort(
        key=lambda x: (-x["critical_count"], -x["high_count"], -x["medium_count"]),
    )
    return clients_list


async def run_get_expiring_documents_dashboard(
    *,
    days_ahead: int,
    urgency: Optional[str],
    consultor_id: Optional[str],
    search: Optional[str],
    user: dict,
) -> dict:
    """Orquestra GET /documents/expiring-dashboard."""
    user_role = user.get("role", "")
    user_id = user.get("id", "")
    is_management = user_role in UserRole.MANAGEMENT_ROLES

    today = datetime.now(timezone.utc)
    doc_query = build_expiry_doc_query(today, days_ahead, urgency)

    expiring_docs = await db.document_metadata.find(
        doc_query,
        {"_id": 0, "extracted_text": 0},
    ).to_list(1000)

    process_ids = list({
        doc.get("process_id") for doc in expiring_docs if doc.get("process_id")
    })
    processes_query = build_expiring_processes_query(
        process_ids,
        is_management=is_management,
        user_id=user_id,
        consultor_id=consultor_id,
    )
    processes = await db.processes.find(
        processes_query,
        {
            "_id": 0, "id": 1, "client_name": 1,
            "assigned_consultor_id": 1, "consultor_id": 1,
            "assigned_mediador_id": 1, "mediador_id": 1,
        },
    ).to_list(500)
    process_map = {p["id"]: p for p in processes}

    filtered_docs = filter_docs_by_authorized_and_search(
        expiring_docs, process_map, search,
    )

    consultor_ids = collect_assignee_ids_from_processes(processes)
    consultors = await db.users.find(
        {"id": {"$in": list(consultor_ids)}},
        {"_id": 0, "id": 1, "name": 1},
    ).to_list(100)
    consultor_map = {
        c["id"]: c.get("name", DEFAULT_CONSULTOR_NAME) for c in consultors
    }

    stats = compute_expiry_stats(filtered_docs, today)
    clients_list = group_expiring_docs_by_client(
        filtered_docs, process_map, consultor_map, today,
    )

    consultors_filter = []
    if is_management:
        from services.role_query import deep_role_in_filter
        all_consultors = await db.users.find(
            deep_role_in_filter(["consultor", "intermediario"]),
            {"_id": 0, "id": 1, "name": 1},
        ).to_list(100)
        consultors_filter = [
            {"id": c["id"], "name": c.get("name", DEFAULT_CONSULTOR_NAME)}
            for c in all_consultors
        ]

    return {
        "stats": stats,
        "clients": clients_list,
        "total_clients": len(clients_list),
        "is_management": is_management,
        "consultors_filter": consultors_filter,
        "filters_applied": {
            "days_ahead": days_ahead,
            "urgency": urgency,
            "consultor_id": consultor_id,
            "search": search,
        },
    }

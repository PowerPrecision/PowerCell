"""
Diagnóstico do Kanban (GET /processes/kanban/diagnose).

Extraído de `routes/processes.py` — verifica statuses, processes, users,
agregações portal/documents e sample query.
"""
from __future__ import annotations

import traceback
from typing import Any

from database import db

WORKFLOW_REQUIRED_FIELDS = ["name", "id", "label", "color", "order"]
INACTIVE_STATUS_NAMES = ["concluidos", "desistencias", "eliminados"]


async def check_workflow_statuses(report: dict[str, Any]) -> None:
    """Preenche report['checks']['workflow_statuses'] e blocking_issue se vazio."""
    try:
        statuses = await db.workflow_statuses.find(
            {}, {"_id": 0},
        ).sort("order", 1).to_list(100)
        report["checks"]["workflow_statuses"] = {
            "count": len(statuses),
            "items": [],
        }
        for s in statuses:
            missing = [
                f for f in WORKFLOW_REQUIRED_FIELDS
                if f not in s or s.get(f) is None
            ]
            report["checks"]["workflow_statuses"]["items"].append({
                "name": s.get("name"),
                "id": s.get("id"),
                "has_all_fields": len(missing) == 0,
                "missing_fields": missing,
            })
        if not statuses:
            report["blocking_issue"] = (
                "workflow_statuses está vazia — o kanban não tem colunas."
            )
    except Exception as e:
        report["checks"]["workflow_statuses"] = {
            "error": str(e),
            "traceback": traceback.format_exc(),
        }
        report["blocking_issue"] = f"Erro ao ler workflow_statuses: {e}"


async def check_processes_counts(report: dict[str, Any]) -> None:
    try:
        total_processes = await db.processes.count_documents(
            {"is_deleted": {"$ne": True}},
        )
        active_processes = await db.processes.count_documents({
            "is_deleted": {"$ne": True},
            "status": {"$nin": INACTIVE_STATUS_NAMES},
        })
        report["checks"]["processes"] = {
            "total": total_processes,
            "active": active_processes,
        }
    except Exception as e:
        report["checks"]["processes"] = {"error": str(e)}
        if not report["blocking_issue"]:
            report["blocking_issue"] = f"Erro ao ler processes: {e}"


async def check_users_count(report: dict[str, Any]) -> None:
    try:
        total_users = await db.users.count_documents({})
        report["checks"]["users"] = {"total": total_users}
    except Exception as e:
        report["checks"]["users"] = {"error": str(e)}


async def check_portal_messages_agg(report: dict[str, Any]) -> None:
    try:
        unread_pipeline = [
            {"$match": {"sender_type": "client", "read_by_staff": False}},
            {"$group": {"_id": "$process_id", "unread_count": {"$sum": 1}}},
        ]
        unread_results = await db.portal_messages.aggregate(
            unread_pipeline,
        ).to_list(10)
        report["checks"]["portal_messages"] = {
            "aggregation_works": True,
            "sample_count": len(unread_results),
        }
    except Exception as e:
        report["checks"]["portal_messages"] = {"error": str(e)}


async def check_documents_agg(report: dict[str, Any]) -> None:
    try:
        new_docs_pipeline = [
            {"$match": {"status": "uploaded"}},
            {"$group": {"_id": "$process_id", "new_count": {"$sum": 1}}},
        ]
        new_docs_results = await db.documents.aggregate(
            new_docs_pipeline,
        ).to_list(10)
        report["checks"]["documents"] = {
            "aggregation_works": True,
            "sample_count": len(new_docs_results),
        }
    except Exception as e:
        report["checks"]["documents"] = {"error": str(e)}


async def check_kanban_sample_query(report: dict[str, Any]) -> None:
    try:
        query = {"is_deleted": {"$ne": True}}
        projection = {
            "_id": 0, "id": 1, "status": 1, "client_name": 1,
            "assigned_consultor_id": 1, "updated_at": 1,
        }
        sample = await db.processes.find(query, projection).to_list(5)
        report["checks"]["kanban_query"] = {
            "works": True,
            "sample_count": len(sample),
            "sample_statuses": [p.get("status") for p in sample],
        }
    except Exception as e:
        report["checks"]["kanban_query"] = {
            "error": str(e),
            "traceback": traceback.format_exc(),
        }
        if not report["blocking_issue"]:
            report["blocking_issue"] = f"Erro na query do kanban: {e}"


def finalize_kanban_diagnose_report(report: dict[str, Any]) -> dict[str, Any]:
    """Define can_load / blocking_issue final a partir dos checks."""
    ws_ok = report["checks"].get("workflow_statuses", {}).get("count", 0) > 0
    proc_ok = "error" not in report["checks"].get("processes", {})
    query_ok = report["checks"].get("kanban_query", {}).get("works", False)

    if ws_ok and proc_ok and query_ok and not report["blocking_issue"]:
        report["can_load"] = True
    elif not report["blocking_issue"]:
        report["blocking_issue"] = (
            "Problema desconhecido — verifique os checks individuais."
        )
    return report


async def run_kanban_diagnose() -> dict[str, Any]:
    """Executa todos os checks e devolve o relatório."""
    report: dict[str, Any] = {
        "checks": {},
        "can_load": False,
        "blocking_issue": None,
    }
    await check_workflow_statuses(report)
    await check_processes_counts(report)
    await check_users_count(report)
    await check_portal_messages_agg(report)
    await check_documents_agg(report)
    await check_kanban_sample_query(report)
    return finalize_kanban_diagnose_report(report)

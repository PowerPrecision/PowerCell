"""List deleted items handler.

Extraído de `routes/restore.py`.
Do **not** overwrite services/backup_restore.py.
"""
from __future__ import annotations

from database import db
from services.process_status import DELETED_STATUS_VALUES


async def run_list_deleted_items(item_type: str, limit: int, user: dict):
    """Lista itens eliminados recentemente que podem ser restaurados."""
    from services.tenant_network import (
        build_tenant_condition,
        build_tenant_process_condition,
        com_isolamento,
    )

    items = []

    # Fronteira de rede: o Master vê tudo; os outros só o que é da sua rede.
    # `{}` (Master) não filtra.
    cond_processos = await build_tenant_process_condition(user or {})
    cond_tarefas = await build_tenant_condition(user or {})

    if item_type in ["all", "processes"]:
        # Processos eliminados
        # Fix: Normalize process status filters — reconhece tanto o
        # singular ("eliminado") como o plural legado ("eliminados").
        deleted_processes = await db.processes.find(
            com_isolamento(cond_processos, {"status": {"$in": DELETED_STATUS_VALUES}, "is_active": False}),
            {"_id": 0}
        ).sort("updated_at", -1).limit(limit).to_list(limit)

        for p in deleted_processes:
            items.append({
                "type": "process",
                "id": p["id"],
                "name": p.get("client_name", "Sem nome"),
                "deleted_at": p.get("updated_at"),
                "can_restore": True
            })

    if item_type in ["all", "documents"]:
        # Documentos eliminados
        consulta_docs: dict = {"deleted": True}
        if cond_processos:
            # Os documentos não levam carimbo de rede: herdam o do processo.
            visiveis = await db.processes.find(cond_processos, {"_id": 0, "id": 1}).to_list(20000)
            consulta_docs["process_id"] = {"$in": [p["id"] for p in visiveis if p.get("id")]}
        deleted_docs = await db.documents.find(
            consulta_docs,
            {"_id": 0}
        ).sort("deleted_at", -1).limit(limit).to_list(limit)

        for d in deleted_docs:
            items.append({
                "type": "document",
                "id": d["id"],
                "name": d.get("filename", "Sem nome"),
                "deleted_at": d.get("deleted_at"),
                "can_restore": True
            })

    if item_type in ["all", "tasks"]:
        # Tarefas eliminadas
        deleted_tasks = await db.tasks.find(
            com_isolamento(cond_tarefas, {"deleted": True}),
            {"_id": 0}
        ).sort("deleted_at", -1).limit(limit).to_list(limit)

        for t in deleted_tasks:
            items.append({
                "type": "task",
                "id": t["id"],
                "name": t.get("title", "Sem título"),
                "deleted_at": t.get("deleted_at"),
                "can_restore": True
            })

    return {
        "items": items,
        "total": len(items)
    }

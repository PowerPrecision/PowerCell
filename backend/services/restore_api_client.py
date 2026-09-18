"""Restore client handler — POST /clients/{client_id}/restore.

PACOTE 11 (Eixo 4 — "Restauro Rápido"): o soft-delete de clientes
(services/client_delete.py) anunciava um ``restore_endpoint`` que NÃO
existia no backend — o ecrã de ficha do cliente não tinha forma de
recuperar um cliente eliminado. Este handler fecha essa assimetria,
simétrico ao restore de processos (services/restore_api_process.py).

Política:
- Restaura o registo quando ``is_deleted``/``deleted``/``status`` indica
  eliminação (procura primeiro em ``clients``, depois em ``processes``
  — o modelo unificado cliente↔processo do client_delete.py).
- ``status`` volta a ``previous_status`` quando guardado; senão resolve
  DINAMICAMENTE a 1ª fase activa do workflow (workflow_lookup.py).
- Cascata simétrica ao delete: processos do 1º titular + documentos +
  tarefas + pedidos RGPD associados voltam a ficar visíveis.
- 2º titular: o delete faz UNLINK (mantém o processo activo); o restore
  NÃO religa automaticamente (metadados de auditoria preservados).
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException

from database import db

logger = logging.getLogger(__name__)


def _is_deleted_doc(doc: dict) -> bool:
    """Detector de soft-delete compatível com todas as variantes."""
    if not doc:
        return False
    return bool(
        doc.get("is_deleted")
        or doc.get("deleted")
        or doc.get("status") in ("eliminado", "eliminados")
    )


async def _resolve_restored_status(previous_status) -> str | None:
    """``previous_status`` quando válido; senão 1ª fase dinâmica do workflow."""
    if previous_status and previous_status not in ("eliminado", "eliminados"):
        return previous_status
    from services.workflow_lookup import get_first_workflow_status
    return await get_first_workflow_status()


async def run_restore_client(client_id: str, user: dict) -> dict:
    """Restaura um cliente eliminado (soft delete) + cascata."""
    # Procurar o cliente nas DUAS colecções (modelo unificado — ver
    # client_delete.py: primeiro 'clients', depois 'processes' quando o
    # próprio cliente É um processo).
    client = await db.clients.find_one({"id": client_id})

    if client:
        collection = db.clients
        doc = client
    else:
        doc = await db.processes.find_one({"id": client_id})
        collection = db.processes

    if not doc:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")

    if not _is_deleted_doc(doc):
        raise HTTPException(
            status_code=400,
            detail="Cliente não está eliminado — não precisa de restauração",
        )

    now = datetime.now(timezone.utc).isoformat()
    restored_status = await _resolve_restored_status(doc.get("previous_status"))

    # 1) Restaurar o próprio cliente
    restore_set = {
        "is_deleted": False,
        "deleted": False,
        "deleted_at": None,
        "status": restored_status,
        "is_active": True,
        "restored_at": now,
        "restored_by": user.get("id", ""),
        "updated_at": now,
    }
    await collection.update_one({"id": client_id}, {"$set": restore_set})

    restored_processes: list[str] = []

    # 2) Cascata — restaurar processos onde o cliente é 1º titular
    #    (soft-deletados junto com ele pelo client_delete.py).
    process_filter = {"client_id": client_id, "is_deleted": True}
    async for proc in db.processes.find(process_filter, {"_id": 0, "id": 1}):
        proc_previous = proc.get("previous_status") if isinstance(proc, dict) else None
        proc_status = await _resolve_restored_status(proc_previous)
        await db.processes.update_one(
            {"id": proc["id"]},
            {"$set": {
                "is_deleted": False,
                "deleted": False,
                "deleted_at": None,
                "status": proc_status,
                "is_active": True,
                "restored_at": now,
                "restored_by": user.get("id", ""),
                "updated_at": now,
            }},
        )
        restored_processes.append(proc["id"])

    # Processo-cliente legado (client.process_ids) também restaurado acima
    # quando tem client_id == client_id; sem client_id, restaurar por ID
    # directo (o modelo unificado usa o próprio ID do cliente).
    if collection is db.clients and isinstance(client.get("process_ids"), list):
        for legacy_pid in client["process_ids"]:
            legacy_proc = await db.processes.find_one(
                {"id": legacy_pid, "is_deleted": True}
            )
            if legacy_proc and legacy_proc.get("client_id") != client_id:
                continue  # só restaurar processos do próprio cliente
            if legacy_proc:
                proc_status = await _resolve_restored_status(
                    legacy_proc.get("previous_status")
                )
                await db.processes.update_one(
                    {"id": legacy_pid},
                    {"$set": {
                        "is_deleted": False,
                        "deleted": False,
                        "deleted_at": None,
                        "status": proc_status,
                        "is_active": True,
                        "restored_at": now,
                        "restored_by": user.get("id", ""),
                        "updated_at": now,
                    }},
                )
                if legacy_pid not in restored_processes:
                    restored_processes.append(legacy_pid)

    # 3) Cascata — documentos / tarefas / pedidos RGPD dos processos
    #    restaurados (e do próprio registo, no modelo unificado).
    cascade_ids = list({client_id, *restored_processes})
    for coll, restore_ops in (
        (db.documents, {"$set": {"deleted": False, "is_deleted": False, "deleted_at": None}}),
        (db.tasks, {"$set": {"deleted": False, "is_deleted": False, "deleted_at": None}}),
        (db.rgpd_requests, {"$set": {"is_deleted": False, "deleted_at": None}}),
    ):
        try:
            await coll.update_many(
                {"process_id": {"$in": cascade_ids}}, restore_ops
            )
        except Exception as cascade_err:  # pragma: no cover — best-effort
            # Degradação graciosa: o cliente já foi restaurado; falhas na
            # cascata ficam logadas sem rebentar o restauro.
            logger.warning(
                f"[RESTORE-CLIENT] Falha na cascata de restauração: {cascade_err}"
            )

    # 4) Log de auditoria (process_activities, espelho do process_restored)
    try:
        await db.process_activities.insert_one({
            "id": str(uuid.uuid4()),
            "process_id": client_id,
            "type": "client_restored",
            "description": f"Cliente restaurado por {user.get('name', 'Utilizador')}",
            "created_at": now,
            "user_id": user.get("id", ""),
            "user_name": user.get("name", ""),
        })
    except Exception as audit_err:  # pragma: no cover — best-effort
        logger.warning(
            f"[RESTORE-CLIENT] Falha ao registar auditoria: {audit_err}"
        )

    return {
        "success": True,
        "message": "Cliente restaurado com sucesso",
        "client_id": client_id,
        "restored_status": restored_status,
        "restored_processes": restored_processes,
    }

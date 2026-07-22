"""Operações em massa sobre processos (admin) — não confundir com admin_process_migration routes.

Extraído de `routes/admin.py`.
"""
from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone, timedelta
from typing import List, Optional

from fastapi import HTTPException, Query, Request, BackgroundTasks
from pydantic import BaseModel

from database import db
from models.auth import UserRole, UserCreate, UserUpdate, UserResponse
from models.workflow import WorkflowStatusCreate, WorkflowStatusUpdate, WorkflowStatusResponse
from models.email_config import EmailConfigCreate, EmailConfigResponse
from services.auth import hash_password, require_roles, get_current_user
from services.admin_helpers import _safe_float, _audit_log
from services.permissions import (
    get_default_permissions_for_role,
    get_all_available_permissions,
    get_role_display_info,
    validate_permissions,
    DEFAULT_PERMISSIONS_BY_ROLE,
    get_user_capabilities,
    build_permissions_document,
)
from models.permissions import (
    CAPABILITIES,
    CATEGORIES,
    SUPER_ADMIN_ROLES,
    ROLE_CAPABILITY_DEFAULTS,
    get_all_capabilities,
    get_capabilities_by_category,
    get_role_defaults,
    resolve_capability,
    validate_capabilities,
)

logger = logging.getLogger(__name__)


async def run_fix_duplicate_processes(user: dict):
    """
    Remove processos duplicados causados por merge.
    
    Identifica duplicados por:
    1. Mesmo email (client_email)
    2. Mesmo NIF (personal_data.nif)
    
    Mantém o processo mais recente (maior created_at) e remove os mais antigos.
    """
    from collections import defaultdict
    
    # Buscar todos os processos
    all_processes = await db.processes.find({}).to_list(length=None)
    
    # Agrupar por email
    by_email = defaultdict(list)
    # Agrupar por NIF
    by_nif = defaultdict(list)
    
    for proc in all_processes:
        email = proc.get("client_email", "").lower().strip() if proc.get("client_email") else None
        nif = proc.get("personal_data", {}).get("nif") if proc.get("personal_data") else None
        
        if email:
            by_email[email].append(proc)
        if nif:
            by_nif[nif].append(proc)
    
    # Identificar duplicados
    ids_to_remove = set()
    report = {
        "analyzed": len(all_processes),
        "duplicates_by_email": [],
        "duplicates_by_nif": [],
        "removed": 0
    }
    
    # Processar duplicados por email
    for email, procs in by_email.items():
        if len(procs) > 1:
            # Ordenar por created_at descendente (mais recente primeiro)
            procs.sort(key=lambda x: x.get("created_at", ""), reverse=True)
            
            duplicate_info = {
                "key": email,
                "count": len(procs),
                "keeping": procs[0].get("id"),
                "keeping_name": procs[0].get("client_name"),
                "removing": []
            }
            
            # Manter o mais recente, remover os outros
            for proc in procs[1:]:
                proc_id = proc.get("id")
                if proc_id not in ids_to_remove:
                    ids_to_remove.add(proc_id)
                    duplicate_info["removing"].append({
                        "id": proc_id,
                        "name": proc.get("client_name"),
                        "created_at": proc.get("created_at")
                    })
            
            report["duplicates_by_email"].append(duplicate_info)
    
    # Processar duplicados por NIF
    for nif, procs in by_nif.items():
        if len(procs) > 1:
            # Ordenar por created_at descendente
            procs.sort(key=lambda x: x.get("created_at", ""), reverse=True)
            
            duplicate_info = {
                "key": nif,
                "count": len(procs),
                "keeping": procs[0].get("id"),
                "keeping_name": procs[0].get("client_name"),
                "removing": []
            }
            
            # Manter o mais recente, remover os outros (se ainda não marcados)
            for proc in procs[1:]:
                proc_id = proc.get("id")
                if proc_id not in ids_to_remove:
                    ids_to_remove.add(proc_id)
                    duplicate_info["removing"].append({
                        "id": proc_id,
                        "name": proc.get("client_name"),
                        "created_at": proc.get("created_at")
                    })
            
            report["duplicates_by_nif"].append(duplicate_info)
    
    total_duplicates = len(report["duplicates_by_email"]) + len(report["duplicates_by_nif"])
    
    if total_duplicates == 0:
        return {
            "success": True,
            "message": "Não foram encontrados processos duplicados",
            "report": report
        }
    
    # Remover duplicados
    for proc_id in ids_to_remove:
        # Mover documentos associados para o processo mantido? Não, apagar tudo
        await db.documents.delete_many({"process_id": proc_id})
        await db.tasks.delete_many({"process_id": proc_id})
        await db.history.delete_many({"process_id": proc_id})
        await db.processes.delete_one({"id": proc_id})
        report["removed"] += 1
    
    # Registrar no histórico
    await db.history.insert_one({
        "id": str(uuid.uuid4()),
        "process_id": None,
        "user_id": user["id"],
        "user_name": user.get("name", "Admin"),
        "action": f"Correção de processos duplicados - {report['removed']} processos removidos",
        "field": "process_duplicates_fixed",
        "old_value": None,
        "new_value": str(report["removed"]),
        "created_at": datetime.now(timezone.utc).isoformat()
    })
    
    # Verificar resultado final
    remaining = await db.processes.count_documents({})
    report["remaining_count"] = remaining
    
    return {
        "success": True,
        "message": f"Removidos {report['removed']} processos duplicados",
        "report": report
    }


async def run_migrate_process_numbers(user: dict):
    """Atribui números sequenciais a processos que ainda não têm.

    Os processos sem ``process_number`` são ordenados por data de
    criação (mais antigos primeiro) e recebem números a partir do
    último número existente + 1.

    Porquê uma migração dedicada: durante a migração de dados do
    Trello, muitos processos foram criados sem número sequencial.
    Este endpoint resolve essa lacuna de forma controlada e idempotente
    (pode ser executado múltiplas vezes sem duplicar números).

    Args:
        user: Utilizador admin autenticado (injetado).

    Returns:
        dict: Relatório com message, updated, first_number, last_number.
    """
    # Buscar processos sem número, ordenados por data de criação
    processes_without_number = await db.processes.find(
        {"$or": [{"process_number": {"$exists": False}}, {"process_number": None}]},
        {"_id": 0, "id": 1, "created_at": 1, "client_name": 1}
    ).sort("created_at", 1).to_list(10000)
    
    if not processes_without_number:
        return {"message": "Todos os processos já têm número atribuído", "updated": 0}
    
    # Obter o maior número existente
    max_result = await db.processes.find_one(
        {"process_number": {"$exists": True, "$ne": None}},
        {"process_number": 1},
        sort=[("process_number", -1)]
    )
    
    next_number = (max_result["process_number"] + 1) if max_result and max_result.get("process_number") else 1
    
    updated_count = 0
    for process in processes_without_number:
        await db.processes.update_one(
            {"id": process["id"]},
            {"$set": {"process_number": next_number}}
        )
        next_number += 1
        updated_count += 1
    
    return {
        "message": f"Números atribuídos a {updated_count} processos",
        "updated": updated_count,
        "first_number": next_number - updated_count,
        "last_number": next_number - 1
    }


async def run_update_process_active_status(user: dict):
    """Recalcula o campo ``is_active`` de todos os processos baseado no status.

    Processos com status "desistencias" ou "concluidos" são marcados como
    ``is_active=False``. Todos os restantes são marcados como ``is_active=True``.

    Porquê este endpoint existe: durante a migração do Trello e desenvolvimento
    iterativo, o campo ``is_active`` pode ficar dessincronizado do status.
    Este endpoint corrige essa inconsistência em massa.

    Args:
        user: Utilizador admin autenticado (injetado).

    Returns:
        dict: Relatório com inactive_updated, active_updated, total_updated.
    """
    # Status que devem ser marcados como inativos
    inactive_statuses = ["desistencias", "concluidos"]
    
    # Actualizar processos inativos
    inactive_result = await db.processes.update_many(
        {"status": {"$in": inactive_statuses}},
        {"$set": {"is_active": False}}
    )
    
    # Actualizar processos ativos (todos os outros)
    active_result = await db.processes.update_many(
        {"status": {"$nin": inactive_statuses}},
        {"$set": {"is_active": True}}
    )
    
    return {
        "message": "Status de atividade atualizado",
        "inactive_updated": inactive_result.modified_count,
        "active_updated": active_result.modified_count,
        "total_updated": inactive_result.modified_count + active_result.modified_count
    }


async def run_sync_process_emails(user: dict):
    """
    Migração: sincroniza personal_data.email → client_email em todos os processos.

    Corrige processos onde o email existe em personal_data.email mas client_email
    está vazio ou diferente. Também gera/actualiza o email_hash.
    """
    from services.encryption import generate_email_hash
    from utils.input_sanitization import sanitize_email

    pipeline = [
        {"$match": {
            "status": {"$ne": "eliminado"},
            "$or": [
                {"personal_data.email": {"$exists": True, "$ne": "", "$ne": None}},
                {"personal_data.email_hash": {"$exists": True, "$ne": None}},
            ]
        }},
        {"$project": {"id": 1, "client_email": 1, "personal_data.email": 1, "personal_data.email_hash": 1}}
    ]

    processes = await db.processes.aggregate(pipeline).to_list(length=None)
    updated = 0
    errors = 0

    for proc in processes:
        try:
            pd_email = (proc.get("personal_data") or {}).get("email", "")
            pd_email = str(pd_email).strip() if pd_email else ""
            current = str(proc.get("client_email", "") or "").strip()

            update_fields = {}

            # Sync email se personal_data.email tem valor e client_email está vazio/diferente
            if pd_email and pd_email != current:
                sanitized = sanitize_email(pd_email)
                if sanitized:
                    update_fields["client_email"] = sanitized

            # Garantir que email_hash existe
            if pd_email:
                email_hash = generate_email_hash(pd_email.lower().strip())
                if email_hash:
                    existing_hash = (proc.get("personal_data") or {}).get("email_hash")
                    if existing_hash != email_hash:
                        update_fields["personal_data.email_hash"] = email_hash

            if update_fields:
                await db.processes.update_one(
                    {"id": proc["id"]},
                    {"$set": update_fields}
                )
                updated += 1
        except Exception as e:
            errors += 1
            logger.error(f"Erro ao sincronizar email do processo {proc.get('id')}: {e}")

    return {
        "success": True,
        "total_checked": len(processes),
        "updated": updated,
        "errors": errors,
        "message": f"Sincronização concluída: {updated} processos actualizados de {len(processes)} verificados."
    }



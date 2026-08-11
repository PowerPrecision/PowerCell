"""Process migration status/dry-run/run/rollback/reset handlers.

Extraído de `routes/admin_process_migration.py`.
"""
from __future__ import annotations

import logging

from fastapi import BackgroundTasks, HTTPException

from database import db
from services.system_error_logger import system_error_logger
from services.admin_proc_migration_helpers import (
    _migration_state,
    _is_stale,
    _reset_stale_state,
    STALE_THRESHOLD_SECONDS,
    now_iso,
    run_migration_task,
)

logger = logging.getLogger(__name__)


async def run_get_migration_status(user: dict):
    """
    Verificar o estado actual da migração Fase 1 (Separação Cliente ↔ Processo).

    Retorna:
    - Estatísticas de quantos processos precisam de migração
    - Estado da última migração executada
    - Informações sobre backups existentes
    """
    total_clients = await db.clients.count_documents({})
    total_processes = await db.processes.count_documents({})

    # Processos com client_id (query corrigida: $and para evitar chaves duplicadas)
    processes_with_client_id = await db.processes.count_documents({
        "$and": [
            {"client_id": {"$exists": True}},
            {"client_id": {"$ne": None}},
            {"client_id": {"$ne": ""}},
        ]
    })
    processes_without_client_id = total_processes - processes_with_client_id

    # Processos com campos de negócio no nível raiz
    processes_with_property_value = await db.processes.count_documents({"property_value": {"$exists": True, "$ne": None}})
    processes_with_loan_value = await db.processes.count_documents({"loan_value": {"$exists": True, "$ne": None}})
    processes_with_bank_assigned = await db.processes.count_documents({"bank_assigned": {"$exists": True, "$ne": None}})

    # Processos migrados (com _migration_version)
    processes_migrated = await db.processes.count_documents({"_migration_version": "phase1"})

    # Backups existentes (coleções legacy podem não existir)
    try:
        clients_backup_count = await db.clients_legacy.count_documents({})
        has_clients_backup = clients_backup_count > 0
    except Exception:
        has_clients_backup = False
        clients_backup_count = 0
    try:
        processes_backup_count = await db.processes_legacy.count_documents({})
        has_processes_backup = processes_backup_count > 0
    except Exception:
        has_processes_backup = False
        processes_backup_count = 0

    # Clientes com dados financeiros (ainda não limpos)
    clients_with_financial = await db.clients.count_documents({"dados_financeiros": {"$exists": True}})

    # Calcular se a migração é necessária
    migration_needed = (
        processes_without_client_id > 0
        or processes_migrated < total_processes
        or clients_with_financial > 0
    )

    def pct(count, total):
        return round(count / total * 100, 1) if total > 0 else 0

    # Detect stale "running" state
    stale_info = None
    if _migration_state.get("status") == "running":
        if _is_stale():
            started = _migration_state.get("started_at") or _migration_state.get("last_updated")
            stale_info = {
                "is_stale": True,
                "started_at": started,
                "stale_threshold_seconds": STALE_THRESHOLD_SECONDS,
                "message": f"Migration has been in 'running' state for over {STALE_THRESHOLD_SECONDS // 60} minutes. "
                           f"Use POST /admin/process-migration/reset to clear the stuck state.",
            }
        else:
            stale_info = {"is_stale": False}

    return {
        "migration_needed": migration_needed,
        "current_state": _migration_state,
        "stale_state": stale_info,
        "overview": {
            "total_clients": total_clients,
            "total_processes": total_processes,
        },
        "process_migration": {
            "with_client_id": {
                "count": processes_with_client_id,
                "percentage": pct(processes_with_client_id, total_processes),
            },
            "without_client_id": {
                "count": processes_without_client_id,
                "percentage": pct(processes_without_client_id, total_processes),
            },
            "already_migrated": processes_migrated,
            "with_property_value": processes_with_property_value,
            "with_loan_value": processes_with_loan_value,
            "with_bank_assigned": processes_with_bank_assigned,
        },
        "client_cleanup": {
            "with_financial_data": clients_with_financial,
        },
        "backups": {
            "clients_legacy_exists": has_clients_backup,
            "processes_legacy_exists": has_processes_backup,
            "clients_backup_count": clients_backup_count,
            "processes_backup_count": processes_backup_count,
        },
    }


async def run_dry_run_migration(background_tasks: BackgroundTasks, user: dict):
    """
    Executar simulação da migração Fase 1 (não modifica a BD).

    A simulação corre em background e analisa:
    - Quantos clientes seriam criados/deduplicados
    - Quantos processos seriam migrados
    - Quais os erros encontrados
    """
    # Auto-reset stale state (e.g. server crashed mid-migration)
    was_stale = _reset_stale_state()

    if _migration_state["status"] == "running":
        raise HTTPException(
            status_code=409,
            detail="Já existe uma migração em execução. Aguarde a conclusão ou use o botão Reset se estiver preso."
        )

    # Auto-reset non-running terminal states so we can re-run
    if _migration_state["status"] in ("completed", "failed", "rolled_back"):
        _migration_state.update({
            "status": "idle",
            "started_at": None,
            "completed_at": None,
            "started_by": None,
            "last_report": None,
            "mode": None,
            "last_updated": now_iso(),
        })

    background_tasks.add_task(run_migration_task, dry_run=True, started_by=user.get("email", "unknown"))

    logger.info(f"🔄 Dry-run de migração iniciado por {user.get('email')}")

    result = {
        "success": True,
        "message": "Simulação (dry-run) iniciada em background. Verifique o estado para acompanhar o progresso.",
        "started_by": user.get("email"),
        "note": "A simulação não modifica a base de dados. Verifique o relatório antes de executar a migração real."
    }
    if was_stale:
        result["auto_reset"] = True
        result["message"] += " (stale state was auto-reset)"
    return result


async def run_run_migration(background_tasks: BackgroundTasks, user: dict):
    """
    Executar a migração Fase 1 (modifica a BD).

    A migração corre em background e:
    - Cria backup das colecções originais (clients_legacy, processes_legacy)
    - Deduplica clientes por NIF/Email/Nome
    - Adiciona client_id a todos os processos
    - Adiciona campos de negócio ao nível raiz dos processos
    - Remove dados financeiros dos clientes
    - Cria índices necessários

    Acesso: Apenas Admin, CEO ou Diretor
    """
    # Auto-reset stale state (e.g. server crashed mid-migration)
    was_stale = _reset_stale_state()

    # Allow re-running if previous migration completed, failed, or was rolled back.
    # Only block if genuinely still running (and not stale).
    if _migration_state["status"] == "running":
        raise HTTPException(
            status_code=409,
            detail="Já existe uma migração em execução. Aguarde a conclusão ou use o botão Reset se estiver preso."
        )

    # Auto-reset non-running terminal states so we can re-run
    if _migration_state["status"] in ("completed", "failed", "rolled_back"):
        _migration_state.update({
            "status": "idle",
            "started_at": None,
            "completed_at": None,
            "started_by": None,
            "last_report": None,
            "mode": None,
            "last_updated": now_iso(),
        })

    # Avisar se não há backup
    has_backup = await db.clients_legacy.count_documents({}) > 0
    if not has_backup:
        logger.warning("⚠️  Executando migração SEM backup prévio (será criado automaticamente)")

    background_tasks.add_task(run_migration_task, dry_run=False, started_by=user.get("email", "unknown"))

    logger.info(f"🚀 Migração Fase 1 iniciada por {user.get('email')}")

    result = {
        "success": True,
        "message": "Migração Fase 1 iniciada em background. Um backup será criado automaticamente antes das alterações.",
        "started_by": user.get("email"),
        "warning": "A migração modifica a base de dados. Certifique-se de que fez um backup antes de prosseguir.",
        "note": "A migração pode demorar alguns minutos dependendo do volume de dados. Verifique o estado para acompanhar."
    }
    if was_stale:
        result["auto_reset"] = True
        result["message"] += " (stale state was auto-reset)"
    return result


async def run_rollback_migration(user: dict):
    """
    Reverter a migração restaurando as colecções originais a partir dos backups.

    Isto restaura as colecções `clients` e `processes` para o estado anterior
    à migração, usando as colecções `clients_legacy` e `processes_legacy`.

    Acesso: Apenas Admin, CEO ou Diretor
    """
    if _migration_state["status"] == "running":
        raise HTTPException(
            status_code=409,
            detail="Não é possível reverter enquanto uma migração está em execução."
        )

    has_clients_backup = await db.clients_legacy.count_documents({}) > 0
    has_processes_backup = await db.processes_legacy.count_documents({}) > 0

    if not has_clients_backup and not has_processes_backup:
        raise HTTPException(
            status_code=404,
            detail="Não existem backups para reverter. Execute a migração primeiro (cria backups automaticamente)."
        )

    restored = {}

    # Restaurar clients
    if has_clients_backup:
        await db.clients.drop()
        bulk = []
        async for doc in db.clients_legacy.find({}, {"_id": 0}):
            bulk.append(doc)
        if bulk:
            await db.clients.insert_many(bulk)
        restored["clients"] = len(bulk)
        logger.info(f"✅ Clients restaurados: {len(bulk)} documentos")

    # Restaurar processes
    if has_processes_backup:
        await db.processes.drop()
        bulk = []
        async for doc in db.processes_legacy.find({}, {"_id": 0}):
            bulk.append(doc)
        if bulk:
            await db.processes.insert_many(bulk)
        restored["processes"] = len(bulk)
        logger.info(f"✅ Processes restaurados: {len(bulk)} documentos")

    # Reset do estado
    _migration_state.update({
        "status": "rolled_back",
        "completed_at": now_iso(),
        "last_report": {"rollback": restored},
        "last_updated": now_iso(),
    })

    await system_error_logger.log_error(
        error_type="migration_phase1_rollback",
        message=f"Rollback de migração Fase 1 executado por {user.get('email')}",
        component="admin_process_migration",
        details=restored,
        severity="warning",
        request_path="/api/admin/process-migration/rollback"
    )

    return {
        "success": True,
        "message": "Rollback executado com sucesso. As colecções foram restauradas para o estado anterior à migração.",
        "restored": restored,
        "rolled_back_by": user.get("email"),
    }


async def run_reset_migration_state(user: dict):
    """
    Reset forçado do estado da migração para 'idle'.

    Útil quando uma migração fica presa no estado 'running' (por exemplo,
    o servidor reiniciou a meio e o estado em memória ficou inconsistente),
    ou quando se pretende re-executar a migração após uma execução anterior.

    Acesso: Apenas Admin, CEO ou Diretor
    """
    if _migration_state["status"] == "idle":
        return {
            "success": True,
            "message": "O estado já está em 'idle'. Nenhuma acção necessária.",
            "current_state": _migration_state,
        }

    previous_state = dict(_migration_state)

    _migration_state.update({
        "status": "idle",
        "started_at": None,
        "completed_at": None,
        "started_by": None,
        "last_report": None,
        "mode": None,
        "last_updated": now_iso(),
    })

    logger.warning(
        f"⚠️  Migration state manually reset from 'running' to 'idle' by {user.get('email')}. "
        f"Previous state: {previous_state}"
    )

    await system_error_logger.log_error(
        error_type="migration_state_reset",
        message=f"Estado da migração resetado manualmente por {user.get('email')}",
        component="admin_process_migration",
        details={"previous_state": previous_state},
        severity="warning",
        request_path="/api/admin/process-migration/reset"
    )

    return {
        "success": True,
        "message": "Estado da migração resetado de 'running' para 'idle'. Pode agora iniciar uma nova migração.",
        "previous_state": previous_state,
        "reset_by": user.get("email"),
    }

"""
====================================================================
ROTAS DE ADMINISTRAÇÃO - MIGRAÇÃO FASE 1: Separação Cliente ↔ Processo
====================================================================
Endpoints para executar e monitorizar a migração que separa a entidade
Cliente (dados pessoais/fiscais) da entidade Processo (dossier/negócio).

ACESSO: Apenas Admin, CEO ou Diretor

ENDPOINTS:
  GET  /admin/process-migration/status    — Estado actual da migração
  POST /admin/process-migration/dry-run   — Simulação (não modifica a BD)
  POST /admin/process-migration/run       — Executar migração
  POST /admin/process-migration/rollback  — Reverter migração
====================================================================
"""

import logging
import copy
import re
import uuid
from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException
from datetime import datetime, timezone
from typing import Optional

from database import db
from services.auth import get_current_user, require_roles
from models.auth import UserRole
from services.system_error_logger import system_error_logger

router = APIRouter(prefix="/admin/process-migration", tags=["Admin Process Migration"])
logger = logging.getLogger(__name__)


# ─── Estado da migração (in-memory) ──────────────────────────────────────────

_migration_state = {
    "status": "idle",          # idle | running | completed | failed
    "started_at": None,
    "completed_at": None,
    "started_by": None,
    "last_report": None,
    "mode": None,              # dry-run | apply
}


# ─── Helpers ─────────────────────────────────────────────────────────────────

def generate_client_key(nif: str = None, email: str = None, nome: str = None) -> str:
    """Gerar chave única para deduplicação de clientes."""
    if nif:
        nif_clean = re.sub(r'[^\d]', '', str(nif))
        if len(nif_clean) == 9 and nif_clean.isdigit():
            return f"nif:{nif_clean}"
    if email:
        email_clean = str(email).lower().strip()
        if email_clean:
            return f"email:{email_clean}"
    if nome:
        nome_norm = str(nome).lower().strip()
        nome_norm = re.sub(r'[^\w\s]', '', nome_norm)
        nome_norm = re.sub(r'\s+', '_', nome_norm)
        if nome_norm:
            return f"nome:{nome_norm}"
    return None


def extract_personal_from_process(process: dict) -> dict:
    """Extrair dados pessoais de um processo para criar/atualizar o Cliente."""
    personal = process.get("personal_data") or {}
    if not isinstance(personal, dict):
        personal = {}

    client_email = process.get("client_email") or personal.get("email")
    client_phone = process.get("client_phone") or personal.get("phone")

    dados_pessoais = {}
    PERSONAL_FIELDS = [
        "nif", "documento_id", "data_validade_cc", "data_nascimento", "birth_date",
        "naturalidade", "nacionalidade", "morada_fiscal", "estado_civil", "profissao",
        "nome_pai", "nome_mae", "sexo", "altura", "compra_tipo", "menor_35_anos",
        "niss", "codigo_postal", "morada"
    ]
    for field in PERSONAL_FIELDS:
        if personal.get(field) is not None:
            dados_pessoais[field] = personal[field]

    contacto = {
        "email": client_email,
        "telefone": client_phone,
    }

    nome = process.get("client_name") or personal.get("nome_completo") or personal.get("nome") or ""

    return {
        "nome": nome,
        "contacto": contacto,
        "dados_pessoais": dados_pessoais,
    }


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ─── Tarefa de migração em background ────────────────────────────────────────

async def run_migration_task(dry_run: bool, started_by: str):
    """
    Executar a migração completa em background.
    """
    global _migration_state

    _migration_state = {
        "status": "running",
        "started_at": now_iso(),
        "completed_at": None,
        "started_by": started_by,
        "last_report": None,
        "mode": "dry-run" if dry_run else "apply",
    }

    logger.info("=" * 60)
    logger.info(f"INICIANDO MIGRAÇÃO FASE 1 (modo={'DRY-RUN' if dry_run else 'APLICAR'})")
    logger.info("=" * 60)

    stats = {
        "clients_existing": 0,
        "processes_existing": 0,
        "clients_created": 0,
        "clients_deduplicated": 0,
        "processes_migrated": 0,
        "processes_without_client_id": 0,
        "documents_referenced": 0,
        "tasks_referenced": 0,
        "history_referenced": 0,
        "activities_referenced": 0,
        "annotations_referenced": 0,
        "errors": [],
    }

    try:
        # ── Passo 0: Contar registos ──────────────────────────────────────
        stats["clients_existing"] = await db.clients.count_documents({})
        stats["processes_existing"] = await db.processes.count_documents({})

        logger.info(f"📊 Estado actual: {stats['clients_existing']} clientes, {stats['processes_existing']} processos")

        # ── Passo 1: Backup (apenas em modo apply) ────────────────────────
        if not dry_run:
            logger.info("📦 Passo 1: Criar backup das colecções originais...")

            if await db.clients_legacy.count_documents({}) > 0:
                logger.warning("   ⚠️  'clients_legacy' já existe — a saltar backup de clients")
            else:
                bulk = []
                async for doc in db.clients.find({}, {"_id": 0}):
                    bulk.append(doc)
                if bulk:
                    await db.clients_legacy.insert_many(bulk)
                    logger.info(f"   ✅ Backup 'clients' → 'clients_legacy' ({len(bulk)} docs)")

            if await db.processes_legacy.count_documents({}) > 0:
                logger.warning("   ⚠️  'processes_legacy' já existe — a saltar backup de processes")
            else:
                bulk = []
                async for doc in db.processes.find({}, {"_id": 0}):
                    bulk.append(doc)
                if bulk:
                    await db.processes_legacy.insert_many(bulk)
                    logger.info(f"   ✅ Backup 'processes' → 'processes_legacy' ({len(bulk)} docs)")

        # ── Passo 2: Construir mapa de deduplicação ───────────────────────
        logger.info("🔍 Passo 2: Construir mapa de deduplicação de clientes...")

        client_key_map = {}   # key → client_id
        client_id_map = {}    # old_client_id → new_client_id

        existing_clients = await db.clients.find({}, {"_id": 0}).to_list(length=100000)

        for client in existing_clients:
            old_id = client.get("id")
            nome = client.get("nome", "")
            contacto = client.get("contacto") or {}
            email = contacto.get("email") or ""
            telefone = contacto.get("telefone") or ""
            dados_pessoais = client.get("dados_pessoais") or {}
            nif = dados_pessoais.get("nif") or ""

            key = generate_client_key(nif=nif, email=email, nome=nome)

            if key and key not in client_key_map:
                new_client_id = old_id  # Manter o mesmo ID
                new_client = {
                    "id": new_client_id,
                    "nome": nome,
                    "contacto": {
                        "email": email,
                        "email_secundario": contacto.get("email_secundario"),
                        "telefone": telefone,
                        "telefone_secundario": contacto.get("telefone_secundario"),
                    },
                    "dados_pessoais": dados_pessoais,
                    "process_ids": client.get("process_ids", []),
                    "fonte": client.get("fonte"),
                    "tags": client.get("tags", []),
                    "notas": client.get("notas"),
                    "assigned_to": client.get("assigned_to"),
                    "assigned_at": client.get("assigned_at"),
                    "registration_completed": client.get("registration_completed"),
                    "created_at": client.get("created_at", now_iso()),
                    "updated_at": now_iso(),
                    "created_by": client.get("created_by"),
                }

                # Preservar blind indexes
                for hash_field in ["nif_hash", "email_hash", "telefone_hash"]:
                    if dados_pessoais.get(hash_field):
                        new_client["dados_pessoais"][hash_field] = dados_pessoais[hash_field]

                client_key_map[key] = new_client_id
                client_id_map[old_id] = new_client_id

                if not dry_run:
                    await db.clients.update_one(
                        {"id": new_client_id},
                        {"$set": new_client, "$unset": {"dados_financeiros": "", "co_buyers": "", "co_applicants": ""}}
                    )

                stats["clients_deduplicated"] += 1
            elif key and key in client_key_map:
                client_id_map[old_id] = client_key_map[key]

        logger.info(f"   ✅ {len(client_key_map)} clientes únicos identificados")

        # ── Passo 3: Migrar processos ─────────────────────────────────────
        logger.info("🔄 Passo 3: Migrar processos para a nova estrutura...")

        processes = await db.processes.find({}, {"_id": 0}).to_list(length=100000)

        for process in processes:
            old_process_id = process.get("id")
            client_name = process.get("client_name", "")
            client_email = process.get("client_email", "")
            client_phone = process.get("client_phone", "")
            personal_data = process.get("personal_data") or {}
            nif = personal_data.get("nif") or process.get("client_nif") or ""

            key = generate_client_key(nif=nif, email=client_email, nome=client_name)
            existing_client_id = process.get("client_id")

            if existing_client_id and existing_client_id in client_id_map:
                resolved_client_id = client_id_map[existing_client_id]
            elif key and key in client_key_map:
                resolved_client_id = client_key_map[key]
            else:
                # Cliente não encontrado — criar novo
                new_client_id = existing_client_id or str(uuid.uuid4())
                client_data = extract_personal_from_process(process)
                new_client = {
                    "id": new_client_id,
                    "nome": client_data["nome"],
                    "contacto": client_data["contacto"],
                    "dados_pessoais": client_data["dados_pessoais"],
                    "process_ids": [old_process_id],
                    "fonte": process.get("source", "migrated_from_process"),
                    "tags": [],
                    "notas": None,
                    "created_at": process.get("created_at", now_iso()),
                    "updated_at": now_iso(),
                    "created_by": process.get("created_by"),
                }

                if key:
                    client_key_map[key] = new_client_id
                client_id_map[new_client_id] = new_client_id
                resolved_client_id = new_client_id

                if not dry_run:
                    existing = await db.clients.find_one({"id": new_client_id})
                    if not existing:
                        await db.clients.insert_one(new_client)
                    else:
                        await db.clients.update_one(
                            {"id": new_client_id},
                            {"$addToSet": {"process_ids": old_process_id}, "$set": {"updated_at": now_iso()}}
                        )

                stats["clients_created"] += 1

            # ── Construir novo documento de processo ───────────────────────
            new_process = copy.deepcopy(process)
            new_process["client_id"] = resolved_client_id

            if "client_ids" not in new_process:
                new_process["client_ids"] = [resolved_client_id]
            elif resolved_client_id not in new_process["client_ids"]:
                new_process["client_ids"].append(resolved_client_id)

            financial = process.get("financial_data") or {}
            credit = process.get("credit_data") or {}
            real_estate = process.get("real_estate_data") or {}

            if "property_value" not in new_process:
                new_process["property_value"] = real_estate.get("valor_imovel") or financial.get("valor_pretendido")
            if "loan_value" not in new_process:
                new_process["loan_value"] = credit.get("requested_amount")
            if "bank_assigned" not in new_process:
                new_process["bank_assigned"] = credit.get("bank_name")
            if "honorarios" not in new_process:
                new_process["honorarios"] = financial.get("comissao_mediacao")
            if "comissao_banco" not in new_process:
                new_process["comissao_banco"] = None

            if "co_buyers" not in new_process:
                new_process["co_buyers"] = process.get("co_buyers", [])
            if "co_applicants" not in new_process:
                new_process["co_applicants"] = process.get("co_applicants", [])

            new_process.pop("dados_financeiros", None)
            new_process["_migrated_at"] = now_iso()
            new_process["_migration_version"] = "phase1"

            if not dry_run:
                await db.processes.update_one(
                    {"id": old_process_id},
                    {"$set": new_process}
                )
                await db.clients.update_one(
                    {"id": resolved_client_id},
                    {"$addToSet": {"process_ids": old_process_id}, "$set": {"updated_at": now_iso()}}
                )

            stats["processes_migrated"] += 1

            # Referências
            stats["documents_referenced"] += await db.documents.count_documents({"process_id": old_process_id})
            stats["tasks_referenced"] += await db.tasks.count_documents({"process_id": old_process_id})
            stats["history_referenced"] += await db.history.count_documents({"process_id": old_process_id})
            stats["activities_referenced"] += await db.activities.count_documents({"process_id": old_process_id})
            stats["annotations_referenced"] += await db.annotations.count_documents({"process_id": old_process_id})

        # ── Passo 4: Validação de integridade ─────────────────────────────
        logger.info("✅ Passo 4: Validação de integridade...")

        if not dry_run:
            processes_no_client = await db.processes.count_documents({"client_id": {"$exists": False}})
            stats["processes_without_client_id"] = processes_no_client
            if processes_no_client > 0:
                stats["errors"].append(f"{processes_no_client} processos sem client_id")

            all_client_ids = await db.processes.distinct("client_id")
            for cid in all_client_ids:
                if cid and not await db.clients.find_one({"id": cid}):
                    stats["errors"].append(f"Processo referencia client_id inexistente: {cid}")

        # ── Passo 5: Criar índices ────────────────────────────────────────
        if not dry_run:
            logger.info("📇 Passo 5: Criar/verificar índices...")
            await db.processes.create_index("client_id", name="idx_client_id")
            await db.clients.create_index("dados_pessoais.nif_hash", name="idx_nif_hash", sparse=True)
            await db.clients.create_index("contacto.email", name="idx_email", sparse=True)

        # ── Relatório final ────────────────────────────────────────────────
        logger.info("=" * 70)
        logger.info(f"📋 MIGRAÇÃO {'DRY-RUN' if dry_run else 'APLICADA'} CONCLUÍDA")
        logger.info(f"   Clientes processados: {stats['clients_deduplicated']}")
        logger.info(f"   Clientes criados: {stats['clients_created']}")
        logger.info(f"   Processos migrados: {stats['processes_migrated']}")
        logger.info(f"   Erros: {len(stats['errors'])}")
        logger.info("=" * 70)

        _migration_state.update({
            "status": "completed",
            "completed_at": now_iso(),
            "last_report": stats,
        })

        # Registar no sistema de logs
        await system_error_logger.log_error(
            error_type="migration_phase1_complete",
            message=f"Migração Fase 1 {'(dry-run)' if dry_run else '(aplicada)'} concluída",
            component="admin_process_migration",
            details=stats,
            severity="info",
            request_path="/api/admin/process-migration/run"
        )

    except Exception as e:
        logger.error(f"❌ Erro na migração: {e}", exc_info=True)
        _migration_state.update({
            "status": "failed",
            "completed_at": now_iso(),
            "last_report": {"errors": [str(e)]},
        })
        await system_error_logger.log_error(
            error_type="migration_phase1_error",
            message=f"Erro na migração Fase 1: {e}",
            component="admin_process_migration",
            details={"error": str(e)},
            severity="error",
            request_path="/api/admin/process-migration/run"
        )


# ─── ENDPOINTS ───────────────────────────────────────────────────────────────

@router.get("/status")
async def get_migration_status(
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO, UserRole.DIRETOR]))
):
    """
    Verificar o estado actual da migração Fase 1 (Separação Cliente ↔ Processo).

    Retorna:
    - Estatísticas de quantos processos precisam de migração
    - Estado da última migração executada
    - Informações sobre backups existentes
    """
    total_clients = await db.clients.count_documents({})
    total_processes = await db.processes.count_documents({})

    # Processos com client_id
    processes_with_client_id = await db.processes.count_documents({"client_id": {"$exists": True, "$ne": None, "$ne": ""}})
    processes_without_client_id = total_processes - processes_with_client_id

    # Processos com campos de negócio no nível raiz
    processes_with_property_value = await db.processes.count_documents({"property_value": {"$exists": True, "$ne": None}})
    processes_with_loan_value = await db.processes.count_documents({"loan_value": {"$exists": True, "$ne": None}})
    processes_with_bank_assigned = await db.processes.count_documents({"bank_assigned": {"$exists": True, "$ne": None}})

    # Processos migrados (com _migration_version)
    processes_migrated = await db.processes.count_documents({"_migration_version": "phase1"})

    # Backups existentes
    has_clients_backup = await db.clients_legacy.count_documents({}) > 0
    has_processes_backup = await db.processes_legacy.count_documents({}) > 0
    clients_backup_count = await db.clients_legacy.count_documents({}) if has_clients_backup else 0
    processes_backup_count = await db.processes_legacy.count_documents({}) if has_processes_backup else 0

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

    return {
        "migration_needed": migration_needed,
        "current_state": _migration_state,
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


@router.post("/dry-run")
async def dry_run_migration(
    background_tasks: BackgroundTasks,
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO, UserRole.DIRETOR]))
):
    """
    Executar simulação da migração Fase 1 (não modifica a BD).

    A simulação corre em background e analisa:
    - Quantos clientes seriam criados/deduplicados
    - Quantos processos seriam migrados
    - Quais os erros encontrados
    """
    if _migration_state["status"] == "running":
        raise HTTPException(
            status_code=409,
            detail="Já existe uma migração em execução. Aguarde a conclusão."
        )

    background_tasks.add_task(run_migration_task, dry_run=True, started_by=user.get("email", "unknown"))

    logger.info(f"🔄 Dry-run de migração iniciado por {user.get('email')}")

    return {
        "success": True,
        "message": "Simulação (dry-run) iniciada em background. Verifique o estado para acompanhar o progresso.",
        "started_by": user.get("email"),
        "note": "A simulação não modifica a base de dados. Verifique o relatório antes de executar a migração real."
    }


@router.post("/run")
async def run_migration(
    background_tasks: BackgroundTasks,
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO, UserRole.DIRETOR]))
):
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
    if _migration_state["status"] == "running":
        raise HTTPException(
            status_code=409,
            detail="Já existe uma migração em execução. Aguarde a conclusão."
        )

    # Avisar se não há backup
    has_backup = await db.clients_legacy.count_documents({}) > 0
    if not has_backup:
        logger.warning("⚠️  Executando migração SEM backup prévio (será criado automaticamente)")

    background_tasks.add_task(run_migration_task, dry_run=False, started_by=user.get("email", "unknown"))

    logger.info(f"🚀 Migração Fase 1 iniciada por {user.get('email')}")

    return {
        "success": True,
        "message": "Migração Fase 1 iniciada em background. Um backup será criado automaticamente antes das alterações.",
        "started_by": user.get("email"),
        "warning": "A migração modifica a base de dados. Certifique-se de que fez um backup antes de prosseguir.",
        "note": "A migração pode demorar alguns minutos dependendo do volume de dados. Verifique o estado para acompanhar."
    }


@router.post("/rollback")
async def rollback_migration(
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO, UserRole.DIRETOR]))
):
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

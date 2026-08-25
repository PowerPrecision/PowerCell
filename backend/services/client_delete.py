"""DELETE /clients/{id} — soft delete + regra do 2º titular.

Extraído de `routes/clients.py`.
"""
from __future__ import annotations

import uuid
import logging
import asyncio
import copy
import re
import os
import unicodedata
from typing import List, Optional
from datetime import datetime, timezone

from fastapi import HTTPException, Request

from database import db
from models.client import (
    Client, ClientCreate, ClientUpdate,
    ClientContact, ClientPersonalData,
    find_or_create_client_key,
    generate_portal_access_code,
)
from services.auth import get_effective_role
from models.auth import UserRole
from services.encryption import (
    encryption_service,
    encrypt_client_data,
    decrypt_client_data,
    decrypt_clients_list,
    generate_nif_hash,
    generate_email_hash,
    generate_telefone_hash,
)
from services.process_service import get_next_process_number
from services.s3_storage import s3_service
from utils.input_sanitization import (
    sanitize_email, sanitize_name, sanitize_phone, sanitize_nif,
    sanitize_string, sanitize_url, log_sanitization_rejection,
)
from utils.search_filters import create_accent_insensitive_regex, build_multiword_search_filter

logger = logging.getLogger(__name__)

async def run_delete_client(
    client_id: str,
    user: dict
):
    """
    Eliminar um cliente/processo (sempre soft delete, nunca hard delete).

    Nota: Neste sistema, clientes e processos são a mesma entidade.
    Esta função procura primeiro na colecção 'processes' e depois em 'clients'.

    POLÍTICA DE SOFT DELETE OBRIGATÓRIO:
    - Todos as eliminações são soft delete (status='eliminado' + is_deleted=True).
    - Hard delete foi removido para garantir integridade dos dados e permitir undo.
    - Nenhum documento é permanentemente removido do MongoDB.

    REGRA DE PROTEÇÃO DE ELIMINAÇÃO — REGRA DO 2º TITULAR (Pacote L, Fix #1):
    Ao eliminar um cliente, os processos que o referenciam são tratados
    de forma DIFERENCIADA, consoante o papel do cliente nesse processo:

    1. TITULAR PRINCIPAL (process.client_id == client_id):
       → soft-delete em cascata: processo + documentos + tarefas
         (is_deleted=True, status='eliminado'). O processo é destruído
         porque o 1º titular desaparece.

    2. APENAS 2º TITULAR (process.second_client_id == client_id
       E process.client_id != client_id):
       → NÃO elimina o processo. Apenas remove a associação
         (unset second_client_id + second_client_data), mantendo o
         processo ATIVO para o 1º titular. Regista metadados de auditoria
         (second_titular_unlinked_at / _by / _reason) para rastreabilidade.

    Isto evita a regressão crítica de QA em que a eliminação de um 2º titular
    destruía processos que ainda tinham um 1º titular ativo, causando perda
    silenciosa de dados e bloqueio do trabalho do consultor responsável.

    Apenas Admin, CEO, Diretor e Administrativo podem eliminar.
    """
    # Verificar também se é diretor ou administrativo
    if user.get("role") not in ["admin", "ceo", "diretor", "administrativo"]:
        raise HTTPException(status_code=403, detail="Sem permissão para eliminar clientes")

    now = datetime.now(timezone.utc).isoformat()

    # ════════════════════════════════════════════════════════════════════
    # FASE 1 — PROTEÇÃO DE ELIMINAÇÃO: desligar o cliente como 2º TITULAR
    # ════════════════════════════════════════════════════════════════════
    # Processos onde este cliente é APENAS o 2º titular NÃO devem ser
    # eliminados — apenas desligar a associação e manter o processo ativo
    # para o 1º titular. Esta é a "Regra do 2º Titular" do Pacote L.
    #
    # Query:
    #   second_client_id == client_id          → é o 2º titular
    #   client_id != client_id                 → mas NÃO é também o 1º titular
    #   is_deleted != True                     → processo ainda ativo
    second_titular_unlinks = 0
    unlinked_process_ids: List[str] = []
    async for proc in db.processes.find({
        "second_client_id": client_id,
        "client_id": {"$ne": client_id},
        "is_deleted": {"$ne": True},
    }):
        await db.processes.update_one(
            {"id": proc["id"]},
            {
                "$unset": {
                    "second_client_id": "",
                    "second_client_data": "",
                },
                "$set": {
                    "updated_at": now,
                    "second_titular_unlinked_at": now,
                    "second_titular_unlinked_by": user["id"],
                    "second_titular_unlinked_reason": (
                        f"2º titular (cliente {client_id}) eliminado — "
                        f"processo mantido ativo para o 1º titular"
                    ),
                },
            },
        )
        second_titular_unlinks += 1
        unlinked_process_ids.append(proc["id"])
        logger.info(
            f"Processo {proc['id']}: 2º titular (cliente {client_id}) desligado — "
            f"processo mantido ativo para o 1º titular {proc.get('client_id')}"
        )

    # ════════════════════════════════════════════════════════════════════
    # FASE 2 — Eliminar o cliente/processo em si (procura em processes)
    # ════════════════════════════════════════════════════════════════════
    # Procurar primeiro em processes (tabela principal). No modelo unificado,
    # o próprio cliente É um processo, pelo que esta branch cobre o caso em
    # que o cliente a eliminar é o TITULAR PRINCIPAL do seu próprio processo.
    process = await db.processes.find_one({"id": client_id})

    if process:
        # Verificar se o processo está activo
        active_statuses = ["arquivado", "cancelado", "concluido", "desistencias"]
        if process.get("status") not in active_statuses:
            # Permitir eliminar mas avisar
            logger.warning(f"Processo {client_id} eliminado com status activo: {process.get('status')}")

        # Soft delete obrigatório - permite undo
        # Define AMBOS status e is_deleted para consistência em todas as queries.
        # Guarda previous_status para o endpoint de restore poder recuperar.
        await db.processes.update_one(
            {"id": client_id},
            {"$set": {
                "status": "eliminado",
                "is_deleted": True,
                "is_active": False,
                "previous_status": process.get("status"),
                "deleted_at": now,
                "deleted_by": user["id"],
                "updated_at": now
            }}
        )

        # Marcar documentos como eliminados (soft delete)
        await db.documents.update_many(
            {"process_id": client_id},
            {"$set": {
                "deleted": True,
                "is_deleted": True,
                "deleted_at": now,
                "deleted_by": user["id"]
            }}
        )

        # Marcar tarefas como eliminadas (soft delete)
        await db.tasks.update_many(
            {"process_id": client_id},
            {"$set": {
                "deleted": True,
                "is_deleted": True,
                "deleted_at": now,
                "deleted_by": user["id"]
            }}
        )

        # Pacote FQ-4 — marcar pedidos RGPD associados como eliminados
        # (soft delete), em espelho com documentos/tarefas, para que
        # desapareçam de listagens ativas enquanto o cliente está no lixo.
        await db.rgpd_requests.update_many(
            {"process_id": client_id},
            {"$set": {
                "is_deleted": True,
                "deleted_at": now,
                "deleted_by": user["id"]
            }}
        )

        logger.info(
            f"Processo/Cliente {client_id} ({process.get('client_name')}) movido para lixo "
            f"por {user.get('email')} | 2º titular desligado de {second_titular_unlinks} "
            f"processo(s): {unlinked_process_ids}"
        )

        return {
            "success": True,
            "message": f"Cliente '{process.get('client_name')}' movido para o lixo",
            "can_undo": True,
            "restore_endpoint": f"/api/processes/{client_id}/restore",
            "second_titular_unlinks": second_titular_unlinks,
            "unlinked_process_ids": unlinked_process_ids,
        }

    # ════════════════════════════════════════════════════════════════════
    # FASE 3 — Caminho legado: cliente na colecção 'clients'
    # ════════════════════════════════════════════════════════════════════
    # Se não encontrou em processes, procurar em clients (compatibilidade).
    client = await db.clients.find_one({"id": client_id})

    if not client:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")

    # Soft delete obrigatório para cliente na coleção clients
    await db.clients.update_one(
        {"id": client_id},
        {"$set": {
            "deleted": True,
            "is_deleted": True,
            "is_active": False,
            "status": "eliminado",
            "deleted_at": now,
            "deleted_by": user["id"]
        }}
    )

    # REGRA DO 2º TITULAR — cascata DIFERENCIADA nos processos que referenciam
    # este cliente (legacy collection 'clients' tem process_ids):
    #   - 1º titular (process.client_id == client_id)  → soft-delete o processo
    #     + documentos + tarefas (is_deleted=True). Isto é a cascata principal.
    #   - 2º titular only (second_client_id == client_id E client_id != client_id)
    #     → já tratado na FASE 1 acima (apenas desligado, processo mantido ativo).
    #
    # Nota: anteriormente este bloco fazia apenas $unset client_id, o que deixava
    # processos órfãos ativos. Agora, conforme a regra do Pacote L, os processos
    # onde o cliente é o TITULAR PRINCIPAL são efetivamente soft-deleted.
    primary_cascade_ids: List[str] = []
    if client.get("process_ids"):
        async for proc in db.processes.find({
            "id": {"$in": client["process_ids"]},
            "client_id": client_id,        # confirmar: é o 1º titular
            "is_deleted": {"$ne": True},   # ainda ativo
        }):
            await db.processes.update_one(
                {"id": proc["id"]},
                {"$set": {
                    "status": "eliminado",
                    "is_deleted": True,
                    "is_active": False,
                    "previous_status": proc.get("status"),
                    "deleted_at": now,
                    "deleted_by": user["id"],
                    "updated_at": now,
                }},
            )
            # Cascata soft-delete de documentos e tarefas deste processo
            await db.documents.update_many(
                {"process_id": proc["id"]},
                {"$set": {
                    "deleted": True,
                    "is_deleted": True,
                    "deleted_at": now,
                    "deleted_by": user["id"],
                }},
            )
            await db.tasks.update_many(
                {"process_id": proc["id"]},
                {"$set": {
                    "deleted": True,
                    "is_deleted": True,
                    "deleted_at": now,
                    "deleted_by": user["id"],
                }},
            )
            # Pacote FQ-4 — cascata de soft-delete inclui também os
            # pedidos RGPD associados a este processo.
            await db.rgpd_requests.update_many(
                {"process_id": proc["id"]},
                {"$set": {
                    "is_deleted": True,
                    "deleted_at": now,
                    "deleted_by": user["id"],
                }},
            )
            primary_cascade_ids.append(proc["id"])

    cascade_count = len(primary_cascade_ids)
    logger.info(
        f"Cliente {client_id} movido para lixo por {user.get('email')} | "
        f"cascade 1º titular: {cascade_count} processo(s) {primary_cascade_ids} | "
        f"2º titular desligado: {second_titular_unlinks} processo(s) {unlinked_process_ids}"
    )

    return {
        "success": True,
        "message": f"Cliente movido para o lixo",
        "can_undo": True,
        "restore_endpoint": f"/api/clients/{client_id}/restore",
        "cascade_count": cascade_count,
        "cascade_process_ids": primary_cascade_ids,
        "second_titular_unlinks": second_titular_unlinks,
        "unlinked_process_ids": unlinked_process_ids,
    }

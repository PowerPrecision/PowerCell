"""Link/unlink/create-process + list processes for a client.

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

async def run_link_process_to_client(
    client_id: str,
    process_id: str,
    user: dict
):
    """
    Vincular um processo existente a um cliente.
    
    Isto permite que um cliente tenha múltiplos processos de compra.
    """
    # Verificar se cliente existe
    client = await db.clients.find_one({"id": client_id})
    if not client:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    
    # Verificar se processo existe
    process = await db.processes.find_one({"id": process_id})
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")
    
    # Verificar se já está vinculado
    if process_id in client.get("process_ids", []):
        return {"success": True, "message": "Processo já vinculado a este cliente"}
    
    now = datetime.now(timezone.utc).isoformat()
    
    # Adicionar processo ao cliente
    await db.clients.update_one(
        {"id": client_id},
        {
            "$addToSet": {"process_ids": process_id},
            "$set": {"updated_at": now}
        }
    )
    
    # Actualizar processo com referência ao cliente
    await db.processes.update_one(
        {"id": process_id},
        {
            "$set": {
                "client_id": client_id,
                "updated_at": now
            }
        }
    )
    
    logger.info(f"Processo {process_id} vinculado ao cliente {client_id} por {user.get('email')}")
    
    return {
        "success": True,
        "message": f"Processo vinculado ao cliente {client.get('nome')}"
    }

async def run_unlink_process_from_client(
    client_id: str,
    process_id: str,
    user: dict
):
    """Desvincular um processo de um cliente (apenas admin/CEO/Administrativo)."""
    client = await db.clients.find_one({"id": client_id})
    if not client:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    
    now = datetime.now(timezone.utc).isoformat()
    
    # Remover processo do cliente
    await db.clients.update_one(
        {"id": client_id},
        {
            "$pull": {"process_ids": process_id},
            "$set": {"updated_at": now}
        }
    )
    
    # Remover referência ao cliente do processo
    await db.processes.update_one(
        {"id": process_id},
        {
            "$unset": {"client_id": ""},
            "$set": {"updated_at": now}
        }
    )
    
    logger.info(f"Processo {process_id} desvinculado do cliente {client_id} por {user.get('email')}")
    
    return {"success": True, "message": "Processo desvinculado"}

async def run_create_process_for_client(
    client_id: str,
    user: dict,
    process_type: str = 'credito_habitacao',
    description: Optional[str] = None
):
    """
    Criar um novo processo para um cliente existente.
    
    Isto permite que o mesmo cliente tenha múltiplos processos de compra.
    O client_id pode ser:
    - Um ID real de cliente na colecção clients
    - Um ID de processo (quando o cliente é virtual/agregado de processos)
    """
    
    # Sanitizar inputs
    if description:
        description = sanitize_string(description, max_length=500)
    process_type = sanitize_string(process_type, max_length=100)
    if not process_type:
        raise HTTPException(status_code=400, detail="Tipo de processo inválido.")
    
    client = None
    source_process = None
    
    # Primeiro, tentar encontrar na colecção clients
    client = await db.clients.find_one({"id": client_id})
    
    # Se não encontrou, pode ser um process_id (cliente virtual)
    if not client:
        # Tentar encontrar um processo com este ID ou client_id
        source_process = await db.processes.find_one(
            {"$or": [{"id": client_id}, {"client_id": client_id}]},
            {"_id": 0}
        )
        
        if not source_process:
            raise HTTPException(status_code=404, detail="Cliente não encontrado")
        
        # Usar dados do processo como fonte
        client = {
            "id": client_id,
            "nome": source_process.get("client_name"),
            "contacto": {
                "email": source_process.get("client_email", ""),
                "telefone": source_process.get("client_phone", "")
            },
            "dados_pessoais": source_process.get("personal_data", {}),
            "dados_financeiros": source_process.get("financial_data", {}),
            "co_buyers": source_process.get("co_buyers", []),
            "co_applicants": source_process.get("co_applicants", [])
        }
    
    # Obter próximo número de processo
    last_process = await db.processes.find_one(
        {},
        sort=[("process_number", -1)],
        projection={"process_number": 1}
    )
    next_number = (last_process.get("process_number", 0) if last_process else 0) + 1
    
    now = datetime.now(timezone.utc).isoformat()
    process_id = str(uuid.uuid4())
    
    # Preparar personal_data com campos consistentes
    personal_data = client.get("dados_pessoais", {}).copy() if client.get("dados_pessoais") else {}
    client_email = client.get("contacto", {}).get("email", "")
    client_phone = client.get("contacto", {}).get("telefone", "")
    client_name = client.get("nome")
    
    # Garantir consistência de campos em personal_data
    if client_email and not personal_data.get("email"):
        personal_data["email"] = client_email
    if client_phone and not personal_data.get("telefone"):
        personal_data["telefone"] = client_phone
    if client_name and not personal_data.get("nome"):
        personal_data["nome"] = client_name
    
    # Obter estado inicial do workflow
    first_status = await db.workflow_statuses.find_one({}, {"_id": 0}, sort=[("order", 1)])
    initial_status = first_status["name"] if first_status else "clientes_espera"
    
    # Criar novo processo com dados do cliente
    new_process = {
        "id": process_id,
        "process_number": next_number,
        "client_id": client_id,
        "client_name": client_name,
        "client_email": client_email,
        "client_phone": client_phone,
        "process_type": process_type,
        "status": initial_status,
        "description": description,
        # Dados pessoais e financeiros com campos consistentes
        "personal_data": personal_data,
        "financial_data": client.get("dados_financeiros", {}),
        "real_estate_data": {},
        "credit_data": {},
        # 2º Titular / Fiador herdados do cliente
        "co_buyers": client.get("co_buyers", []),
        "co_applicants": client.get("co_applicants", []),
        # Metadados
        "created_at": now,
        "updated_at": now,
        "created_by": user.get("email"),
        "source": "client_portal"
    }
    
    # Auto-assign based on creator role
    if user["role"] == "intermediario":
        new_process["assigned_mediador_id"] = user["id"]
        new_process["mediador_name"] = user["name"]
    elif user["role"] in ["consultor", "diretor"]:
        new_process["assigned_consultor_id"] = user["id"]
        new_process["consultor_name"] = user["name"]

    await db.processes.insert_one(new_process)
    
    # Se temos um cliente real, actualizar a lista de processos
    if not source_process:
        await db.clients.update_one(
            {"id": client_id},
            {
                "$addToSet": {"process_ids": process_id},
                "$set": {"updated_at": now}
            }
        )
    
    logger.info(f"Novo processo {process_id} criado para cliente {client_id} por {user.get('email')}")

    return {
        "success": True,
        "process_id": process_id,
        "process_number": next_number,
        "message": f"Processo #{next_number} criado para {client.get('nome')}"
    }

async def run_get_client_processes(
    client_id: str,
    user: dict,
    include_archived: bool = False
):
    """Obter todos os processos de um cliente (incluindo como 2º titular)."""
    client = await db.clients.find_one({"id": client_id})
    
    if not client:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    
    # Processos como titular principal
    process_ids_as_main = client.get("process_ids") or []
    
    # Processos como 2º titular (second_client_id)
    processes_as_second = await db.processes.find(
        {"second_client_id": client_id},
        {"_id": 0, "id": 1}
    ).to_list(length=50)
    process_ids_as_second = [p["id"] for p in processes_as_second]
    
    # Combinar IDs (sem duplicados)
    all_process_ids = list(dict.fromkeys(process_ids_as_main + process_ids_as_second))
    
    if not all_process_ids:
        return {
            "client_name": client.get("nome"),
            "processes": [],
            "total": 0
        }
    
    query = {"id": {"$in": all_process_ids}}
    if not include_archived:
        query["status"] = {"$nin": ["arquivado", "cancelado"]}
    
    processes = await db.processes.find(
        query,
        {"_id": 0}
    ).sort("created_at", -1).to_list(length=50)
    
    # Adicionar client_role a cada processo
    for p in processes:
        if p.get("second_client_id") == client_id and p.get("client_id") != client_id:
            p["client_role"] = "2º titular"
        elif p.get("client_id") == client_id:
            p["client_role"] = "titular"
        else:
            p["client_role"] = "2º titular"
    
    return {
        "client_name": client.get("nome"),
        "processes": processes,
        "total": len(processes)
    }

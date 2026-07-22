"""GET /clients/me — clientes/processos atribuídos ao utilizador.

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

async def run_get_my_assigned_clients(
    request: Request,
    user: dict,
    search: Optional[str] = None,
    limit: int = 100,
    skip: int = 0
):
    """
    Obter clientes/processos atribuídos ao utilizador logado.
    
    Retorna apenas os processos onde o utilizador actual está atribuído
    (assigned_consultor_id, assigned_mediador_id, assigned_indexacao_id, ou created_by).
    
    Permissões: Qualquer utilizador autenticado com role de staff.
    """
    from models.auth import UserRole
    
    user_id = user.get("id", "")
    user_email = user.get("email", "")
    user_role = get_effective_role(request, user)
    
    # Construir query baseada no papel
    if user_role == UserRole.CONSULTOR:
        query = {
            "$or": [
                {"assigned_consultor_ids": user_id},
                {"assigned_consultor_id": user_id},
                {"created_by": user_email}
            ]
        }
    elif user_role == UserRole.INTERMEDIARIO:
        query = {
            "$or": [
                {"assigned_mediador_ids": user_id},
                {"assigned_mediador_id": user_id},
                {"created_by": user_email}
            ]
        }
    elif user_role == UserRole.INDEXACAO:
        query = {
            "$or": [
                {"assigned_indexacao_id": user_id},
                {"created_by": user_email}
            ]
        }
    elif user_role in [UserRole.ADMIN, UserRole.CEO, UserRole.DIRETOR, UserRole.ADMINISTRATIVO]:
        query = {
            "status": {"$nin": ["concluidos", "desistencias", "eliminado"]},
            "is_active": {"$ne": False}
        }
    else:
        query = {"created_by": user_email}
    
    # Filter out soft-deleted processes
    if "$or" in query:
        query = {"$and": [query, {"is_deleted": {"$ne": True}}]}
    else:
        query["is_deleted"] = {"$ne": True}
    
    # Search filter
    if search:
        search = sanitize_string(search, max_length=200)
        name_filter = build_multiword_search_filter(search, "client_name")
        search_filter = {
            "$or": [
                name_filter,
                {"client_email": {"$regex": re.escape(search), "$options": "i"}}
            ]
        }
        query = {"$and": [query, search_filter]}
    
    # Buscar ordem das fases do workflow para ordenação composta
    workflow_statuses = await db.workflow_statuses.find({}, {"_id": 0}).sort("order", 1).to_list(100)
    status_order = {s["name"]: idx for idx, s in enumerate(workflow_statuses)}
    status_map = {s["name"]: s for s in workflow_statuses}
    
    # Buscar processos (até 5000 para ordenação Python-side)
    processes = await db.processes.find(
        query,
        {"_id": 0, "id": 1, "process_number": 1, "client_name": 1,
         "client_email": 1, "client_phone": 1, "status": 1,
         "assigned_consultor_id": 1, "assigned_mediador_id": 1,
         "created_at": 1, "updated_at": 1}
    ).to_list(5000)
    
    # Desencriptar dados sensíveis
    from services.process_service import decrypt_processes_list
    processes = decrypt_processes_list(processes)
    
    # Ordenação composta: 1ª por fase do workflow, 2ª por nome do cliente
    processes.sort(key=lambda p: (status_order.get(p.get("status"), 999), (p.get("client_name") or "").lower()))
    
    # Aplicar paginação (após ordenação)
    processes = processes[skip:skip + limit]
    
    clients_list = []
    for p in processes:
        status_info = status_map.get(p.get("status"), {})
        clients_list.append({
            "id": p["id"],
            "process_number": p.get("process_number"),
            "client_name": p.get("client_name", "Sem nome"),
            "client_email": p.get("client_email"),
            "client_phone": p.get("client_phone"),
            "status": p.get("status"),
            "status_label": status_info.get("label", p.get("status", "Desconhecido")),
            "status_color": status_info.get("color", "#6B7280"),
            "created_at": p.get("created_at"),
            "updated_at": p.get("updated_at"),
        })
    
    return {
        "clients": clients_list,
        "total": len(clients_list)
    }

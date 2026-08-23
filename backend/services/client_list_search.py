"""GET /clients/search + GET /clients — pesquisa e listagem de clientes.

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
from services.client_list_filters import (
    build_client_entity_query,
    client_doc_to_list_item,
)

logger = logging.getLogger(__name__)


def _merge_entity_client_docs(
    clients: list,
    extra_docs: list,
    search: Optional[str] = None,
) -> list:
    """Copia fonte/tipo para as linhas existentes e acrescenta clientes sem processo."""
    if not extra_docs:
        return clients
    extra_by_id = {d["id"]: d for d in extra_docs if d.get("id")}
    present = {c.get("id") for c in clients if c.get("id")}
    search_lc = (search or "").strip().lower()

    for c in clients:
        extra = extra_by_id.get(c.get("id"))
        if not extra:
            continue
        if extra.get("fonte") and not c.get("fonte"):
            c["fonte"] = extra["fonte"]
        item = client_doc_to_list_item(extra)
        c["tipo_cliente"] = item["tipo_cliente"]

    for doc in extra_docs:
        cid = doc.get("id")
        if not cid or cid in present:
            continue
        if search_lc:
            blob = " ".join([
                str(doc.get("nome") or ""),
                str((doc.get("contacto") or {}).get("email") or ""),
                str((doc.get("dados_pessoais") or {}).get("nif") or ""),
            ]).lower()
            if search_lc not in blob:
                continue
        clients.append(client_doc_to_list_item(doc))
        present.add(cid)
    return clients


async def _enrich_clients_fonte(clients: list) -> list:
    """Preenche ``fonte`` / ``tipo_cliente`` a partir da colecção clients."""
    ids = [c.get("id") for c in clients if c.get("id")]
    if not ids:
        return clients
    docs = await db.clients.find(
        {"id": {"$in": ids}},
        {
            "_id": 0, "id": 1, "fonte": 1, "tipo": 1, "tipo_cliente": 1,
            "titular2_data": 1, "titular2_name": 1,
        },
    ).to_list(length=None)
    by_id = {d["id"]: d for d in docs if d.get("id")}
    for c in clients:
        extra = by_id.get(c.get("id"))
        if not extra:
            continue
        if extra.get("fonte") and not c.get("fonte"):
            c["fonte"] = extra["fonte"]
        if not c.get("tipo_cliente"):
            c["tipo_cliente"] = client_doc_to_list_item(extra)["tipo_cliente"]
    return clients

async def run_search_clients(
    q: str,
    user: dict,
    limit: int = 10
):
    """Pesquisa leve de clientes para autocomplete."""
    q = sanitize_string(q, max_length=200)

    simple_regex = {"$regex": re.escape(q), "$options": "i"}
    name_filter = build_multiword_search_filter(q, "nome")

    # Para email/NIF, usar pesquisa simples (contígua)
    or_conditions = [
        name_filter,
        {"contacto.email": simple_regex},
        {"dados_pessoais.nif": simple_regex},
    ]

    # PACOTE DG — excluir clientes eliminados (soft-delete) do autocomplete.
    query = {"$or": or_conditions, "is_deleted": {"$ne": True}}

    clients = await db.clients.find(
        query,
        {"_id": 0, "id": 1, "nome": 1, "contacto.email": 1, "contacto.telefone": 1, "dados_pessoais.nif": 1, "is_active": 1}
    ).sort("nome", 1).limit(limit).to_list(length=limit)

    results = [
        {
            "id": c.get("id"),
            "nome": c.get("nome"),
            "nif": c.get("dados_pessoais", {}).get("nif") if isinstance(c.get("dados_pessoais"), dict) else None,
            "email": c.get("contacto", {}).get("email") if isinstance(c.get("contacto"), dict) else None,
            "telefone": c.get("contacto", {}).get("telefone") if isinstance(c.get("contacto"), dict) else None,
            "is_active": c.get("is_active", True),
        }
        for c in clients
    ]

    results = decrypt_clients_list(results)

    return {"results": results}

async def run_list_clients(
    user: dict,
    search: Optional[str] = None,
    has_active_process: Optional[bool] = None,
    show_all: Optional[bool] = True,
    status_filter: Optional[str] = None,
    assignment_filter: Optional[str] = None,
    indexacao_filter: Optional[str] = None,
    exclude_deleted: Optional[bool] = False,
    deleted_only: Optional[bool] = False,
    limit: Optional[int] = 100,
    skip: Optional[int] = 0,
    fonte: Optional[str] = None,
    tipo: Optional[str] = None,
    status: Optional[str] = None,
):
    """
    Listar clientes.
    - show_all=True: Todos os utilizadores vêem todos os clientes da empresa
    - show_all=False: Utilizadores vêem apenas os seus clientes (atribuídos)
    
    Filtros disponíveis:
    - status_filter: Filtrar por fase do processo
    - assignment_filter: 'both' (consultor+intermediario), 'consultor', 'intermediario', 'none'
    
    Nota: Todos podem ver a lista de clientes para referência,
    mas apenas têm acesso total a processos que lhes estão atribuídos.
    """
    # Apply defaults for None values (handles empty string from query params)
    show_all = show_all if show_all is not None else True
    exclude_deleted = exclude_deleted if exclude_deleted is not None else False
    deleted_only = deleted_only if deleted_only is not None else False
    limit = limit if limit is not None else 100
    skip = skip if skip is not None else 0

    user_role = user.get("role", "")
    user_id = user.get("id", "")
    user_email = user.get("email", "")
    
    # Sanitize search params used in MongoDB queries
    if search:
        search = sanitize_string(search, max_length=200)
    if status_filter:
        status_filter = sanitize_string(status_filter, max_length=50)
    if assignment_filter:
        assignment_filter = sanitize_string(assignment_filter, max_length=50)
    if fonte:
        fonte = sanitize_string(fonte, max_length=50)
    if tipo:
        tipo = sanitize_string(tipo, max_length=50)
    if status:
        status = sanitize_string(status, max_length=50)

    # PACOTE FK — filtros da entidade Cliente (independentes do processo).
    client_entity_query = build_client_entity_query(fonte=fonte, tipo=tipo, status=status)
    matching_client_ids = None
    extra_client_docs: list[dict] = []
    if client_entity_query:
        extra_client_docs = await db.clients.find(
            client_entity_query,
            {
                "_id": 0, "id": 1, "nome": 1, "contacto": 1, "dados_pessoais": 1,
                "process_ids": 1, "fonte": 1, "created_at": 1, "updated_at": 1,
                "is_active": 1, "is_deleted": 1, "prioridade": 1, "priority": 1,
                "titular2_data": 1, "titular2_name": 1, "tipo": 1, "tipo_cliente": 1,
            },
        ).to_list(length=None)
        matching_client_ids = [d["id"] for d in extra_client_docs if d.get("id")]
        if not matching_client_ids:
            workflow_statuses = await db.workflow_statuses.find(
                {}, {"_id": 0}
            ).sort("order", 1).to_list(100)
            available_statuses = [
                {"name": s["name"], "label": s.get("label", s["name"])}
                for s in workflow_statuses
            ]
            return {
                "clients": [],
                "total": 0,
                "showing_all": bool(show_all),
                "available_statuses": available_statuses,
            }
    
    # Buscar workflow statuses para labels
    workflow_statuses = await db.workflow_statuses.find({}, {"_id": 0}).sort("order", 1).to_list(100)
    status_map = {s["name"]: s for s in workflow_statuses}
    
    # Se show_all=True OU é admin/ceo/diretor, mostrar todos
    if show_all or user_role in ["admin", "ceo", "diretor"]:
        # Mostrar todos os clientes da empresa
        process_query = {}
        
        if search:
            simple_regex = {"$regex": re.escape(search), "$options": "i"}
            name_filter = build_multiword_search_filter(search, "client_name")
            process_query = {
                "$or": [
                    name_filter,
                    {"client_email": simple_regex},
                    {"personal_data.nif": simple_regex}
                ]
            }

        # PACOTE FK — restringir processos aos clientes que casam fonte/tipo/estado
        if matching_client_ids is not None:
            id_filter = {"client_id": {"$in": matching_client_ids}}
            if process_query:
                process_query = {"$and": [process_query, id_filter]}
            else:
                process_query = id_filter
        
        # Filtro por fase/status
        if status_filter:
            if process_query:
                process_query = {"$and": [process_query, {"status": status_filter}]}
            else:
                process_query = {"status": status_filter}
        
        # Filtro por tipo de atribuição
        if assignment_filter:
            assignment_query = None
            if assignment_filter == "both":
                # Tem consultor E intermediario
                assignment_query = {
                    "assigned_consultor_id": {"$exists": True, "$ne": None},
                    "assigned_mediador_id": {"$exists": True, "$ne": None}
                }
            elif assignment_filter == "consultor":
                # Tem apenas consultor (sem intermediario)
                assignment_query = {
                    "assigned_consultor_id": {"$exists": True, "$ne": None},
                    "$or": [
                        {"assigned_mediador_id": None},
                        {"assigned_mediador_id": {"$exists": False}}
                    ]
                }
            elif assignment_filter == "intermediario":
                # Tem apenas intermediario (sem consultor)
                assignment_query = {
                    "assigned_mediador_id": {"$exists": True, "$ne": None},
                    "$or": [
                        {"assigned_consultor_id": None},
                        {"assigned_consultor_id": {"$exists": False}}
                    ]
                }
            elif assignment_filter == "none":
                # Não tem nenhum atribuido
                assignment_query = {
                    "$and": [
                        {"$or": [
                            {"assigned_consultor_id": None},
                            {"assigned_consultor_id": {"$exists": False}}
                        ]},
                        {"$or": [
                            {"assigned_mediador_id": None},
                            {"assigned_mediador_id": {"$exists": False}}
                        ]}
                    ]
                }
            
            if assignment_query:
                if process_query:
                    if "$and" in process_query:
                        process_query["$and"].append(assignment_query)
                    else:
                        process_query = {"$and": [process_query, assignment_query]}
                else:
                    process_query = assignment_query
        
        # Filtro por indexação
        if indexacao_filter:
            indexacao_filter = sanitize_string(indexacao_filter, max_length=50)
            indexacao_query = None
            if indexacao_filter == "assigned":
                # Tem indexação atribuída
                indexacao_query = {"assigned_indexacao_id": {"$exists": True, "$ne": None}}
            elif indexacao_filter == "unassigned":
                # Sem indexação atribuída
                indexacao_query = {
                    "$or": [
                        {"assigned_indexacao_id": None},
                        {"assigned_indexacao_id": {"$exists": False}}
                    ]
                }
            
            if indexacao_query:
                if process_query:
                    if "$and" in process_query:
                        process_query["$and"].append(indexacao_query)
                    else:
                        process_query = {"$and": [process_query, indexacao_query]}
                else:
                    process_query = indexacao_query
        
        # Filtro de eliminados (soft delete)
        # PACOTE DG — usar is_deleted como filtro principal (defesa em
        # profundidade: manter também o filtro de status="eliminado" para
        # documentos legados com inconsistência de campos).
        if deleted_only:
            deleted_query = {"is_deleted": True, "status": "eliminado"}
            if process_query:
                if "$and" in process_query:
                    process_query["$and"].append(deleted_query)
                else:
                    process_query = {"$and": [process_query, deleted_query]}
            else:
                process_query = deleted_query
        elif exclude_deleted:
            deleted_query = {"is_deleted": {"$ne": True}, "status": {"$ne": "eliminado"}}
            if process_query:
                if "$and" in process_query:
                    process_query["$and"].append(deleted_query)
                else:
                    process_query = {"$and": [process_query, deleted_query]}
            else:
                process_query = deleted_query
        
        # Buscar todos os processos (clientes únicos)
        # NOTA: Não aplicar limit/skip ao nível dos processos pois isso limitaria
        # o número de clientes únicos. A paginação aplica-se ao resultado final.
        # FIX (Pacote K): adicionado is_deleted à projection para o cálculo de
        # "cliente ativo" poder filtrar processos eliminados.
        processes = await db.processes.find(
            process_query,
            {"_id": 0, "id": 1, "client_name": 1, "client_email": 1, "client_phone": 1, 
             "personal_data": 1, "status": 1, "process_number": 1, "client_id": 1,
             "assigned_consultor_id": 1, "assigned_mediador_id": 1,
             "consultor_name": 1, "mediador_name": 1, "is_active": 1, "is_deleted": 1, "created_at": 1,
             "updated_at": 1, "prioridade": 1, "priority": 1}
        ).sort("client_name", 1).to_list(length=None)
        
        # Agrupar por cliente
        clients_map = {}
        for proc in processes:
            key = proc.get("client_id") or proc.get("client_name", "").lower().strip()
            if not key:
                continue
            
            # Determinar prioridade do processo (suporta campo PT e EN)
            proc_priority = proc.get("prioridade") or proc.get("priority") or ""
            
            if key not in clients_map:
                clients_map[key] = {
                    "id": proc.get("client_id") or proc.get("id"),
                    "nome": proc.get("client_name"),
                    "contacto": {
                        "email": proc.get("client_email"),
                        "telefone": proc.get("client_phone")
                    },
                    "dados_pessoais": proc.get("personal_data", {}),
                    "nif": proc.get("personal_data", {}).get("nif"),
                    "process_ids": [],
                    "active_processes_count": 0,
                    "processes": [],  # Lista de processos com fase
                    "created_at": proc.get("created_at"),  # For sorting by date
                    "updated_at": proc.get("updated_at"),  # Last update date
                    "prioridade": proc_priority,  # Prioridade mais alta dos processos
                    "is_active": True,  # Valor por defeito; será ajustado abaixo com base nos processos
                }
            
            # Update created_at to earliest process date
            proc_date = proc.get("created_at")
            if proc_date and (not clients_map[key].get("created_at") or proc_date < clients_map[key]["created_at"]):
                clients_map[key]["created_at"] = proc_date
            
            # Update updated_at to latest date
            proc_updated = proc.get("updated_at")
            if proc_updated and (not clients_map[key].get("updated_at") or proc_updated > clients_map[key]["updated_at"]):
                clients_map[key]["updated_at"] = proc_updated
            
            # Adicionar informação do processo
            status_info = status_map.get(proc.get("status"), {})
            process_info = {
                "id": proc.get("id"),
                "process_number": proc.get("process_number"),
                "status": proc.get("status"),
                "status_label": status_info.get("label", proc.get("status")),
                "status_color": status_info.get("color", "#6B7280"),
                "is_active": proc.get("is_active", True),
                "consultor_name": proc.get("consultor_name"),
                "mediador_name": proc.get("mediador_name"),
                "prioridade": proc_priority,
            }
            clients_map[key]["processes"].append(process_info)
            clients_map[key]["process_ids"].append(proc.get("id"))
            
            # Determinar fase principal (primeiro processo ativo ou primeiro processo)
            if not clients_map[key].get("fase_principal"):
                clients_map[key]["fase_principal"] = process_info
            
            # Atualizar prioridade do cliente para a mais alta entre os seus processos
            PRIORITY_WEIGHT = {"alta": 3, "media": 2, "baixa": 1}
            current_weight = PRIORITY_WEIGHT.get(clients_map[key].get("prioridade", ""), 0)
            new_weight = PRIORITY_WEIGHT.get(proc_priority, 0)
            if new_weight > current_weight:
                clients_map[key]["prioridade"] = proc_priority
            
            # FIX (Pacote K): Cálculo de "processo ativo" baseado em status + is_deleted
            # (anteriormente usava a flag is_active desnormalizada + lista de status
            # com typos "concluidos"/"arquivado"). Um processo conta como ativo se
            # NÃO estiver eliminado (is_deleted) e o status NÃO for terminal.
            # Estados terminais: concluido, desistencia, desistencias, eliminado.
            INACTIVE_STATUSES = ("concluido", "desistencia", "desistencias", "eliminado")
            proc_is_active = (
                not proc.get("is_deleted", False)
                and proc.get("status") not in INACTIVE_STATUSES
            )
            if proc_is_active:
                clients_map[key]["active_processes_count"] += 1
        
        # Determinar is_active de cada cliente com base nos seus processos
        # FIX (Pacote K): Um cliente é ativo se tiver pelo menos UM processo
        # onde is_deleted=False E status NOT IN (concluido, desistencia,
        # desistencias, eliminado). Anteriormente usava a flag is_active
        # desnormalizada, que pode dessincronizar do status real.
        for key in clients_map:
            all_processes = clients_map[key].get("processes", [])
            if all_processes:
                has_any_active = any(
                    not p.get("is_deleted", False)
                    and p.get("status") not in INACTIVE_STATUSES
                    for p in all_processes
                )
                clients_map[key]["is_active"] = has_any_active
            # Se não tem processos, mantém o valor por defeito (True)
        
        clients = list(clients_map.values())
        
        # Ordenação composta: 1ª por prioridade (alta primeiro), 2ª por fase do workflow, 3ª por nome
        status_order = {s["name"]: idx for idx, s in enumerate(workflow_statuses)}
        PRIORITY_SORT = {"alta": 3, "high": 3, "media": 2, "medium": 2, "baixa": 1, "low": 1}
        clients.sort(key=lambda c: (
            -PRIORITY_SORT.get(c.get("prioridade", ""), 0),
            status_order.get(c.get("fase_principal", {}).get("status"), 999),
            (c.get("nome") or "").lower()
        ))
        
        # Filtrar por ter processo activo
        if has_active_process is not None:
            clients = [c for c in clients if (c["active_processes_count"] > 0) == has_active_process]

        clients = _merge_entity_client_docs(clients, extra_client_docs, search)
        clients = await _enrich_clients_fonte(clients)
        
        # Aplicar paginação ao resultado final (clientes, não processos)
        total_count = len(clients)
        clients = clients[skip:skip + limit]
        
        # Desencriptar dados sensíveis
        clients = decrypt_clients_list(clients)
        
        # Adicionar lista de fases disponíveis para o filtro
        available_statuses = [{"name": s["name"], "label": s.get("label", s["name"])} for s in workflow_statuses]
        
        return {
            "clients": clients,
            "total": total_count,
            "showing_all": True,
            "available_statuses": available_statuses
        }
    
    # show_all=False - Mostrar apenas clientes do utilizador
    # Construir query baseada no papel do utilizador
    if user_role == "consultor":
        role_query = {
            "$or": [
                {"assigned_consultor_id": user_id},
                {"created_by": user_email}
            ]
        }
    elif user_role == "intermediario":
        role_query = {
            "$or": [
                {"assigned_mediador_id": user_id},
                {"created_by": user_email}
            ]
        }
    else:
        role_query = {"created_by": user_email}
    
    process_query = role_query
    
    if search:
        simple_regex = {"$regex": re.escape(search), "$options": "i"}
        name_filter = build_multiword_search_filter(search, "client_name")
        search_filter = {
            "$or": [
                name_filter,
                {"client_email": simple_regex},
                {"personal_data.nif": simple_regex}
            ]
        }
        process_query = {"$and": [process_query, search_filter]}
    
    if matching_client_ids is not None:
        id_filter = {"client_id": {"$in": matching_client_ids}}
        if "$and" in process_query:
            process_query["$and"].append(id_filter)
        else:
            process_query = {"$and": [process_query, id_filter]}
    
    # Filtro de eliminados (soft delete) - non-show_all path
    # PACOTE DG — usar is_deleted como filtro principal (defesa em
    # profundidade: manter também o filtro de status="eliminado" para
    # documentos legados com inconsistência de campos).
    if deleted_only:
        deleted_query = {"is_deleted": True, "status": "eliminado"}
        if "$and" in process_query:
            process_query["$and"].append(deleted_query)
        else:
            process_query = {"$and": [process_query, deleted_query]}
    elif exclude_deleted:
        deleted_query = {"is_deleted": {"$ne": True}, "status": {"$ne": "eliminado"}}
        if "$and" in process_query:
            process_query["$and"].append(deleted_query)
        else:
            process_query = {"$and": [process_query, deleted_query]}
    
    # Buscar processos e transformar em "clientes"
    # FIX (Pacote K): adicionado is_deleted à projection para o cálculo de
    # "cliente ativo" poder filtrar processos eliminados.
    processes = await db.processes.find(
        process_query,
        {"_id": 0, "id": 1, "client_name": 1, "client_email": 1, "client_phone": 1, 
         "personal_data": 1, "status": 1, "process_number": 1, "client_id": 1, "created_at": 1,
         "is_deleted": 1,
         "prioridade": 1, "priority": 1}
    ).sort("client_name", 1).skip(skip).limit(limit).to_list(length=limit)
    
    # Agrupar por cliente (usando client_id ou client_name como chave)
    clients_map = {}
    for proc in processes:
        key = proc.get("client_id") or proc.get("client_name", "").lower().strip()
        if not key:
            continue
        
        if key not in clients_map:
            # Determinar prioridade do processo (suporta campo PT e EN)
            proc_priority = proc.get("prioridade") or proc.get("priority") or ""
            
            clients_map[key] = {
                "id": proc.get("client_id") or f"process_{proc.get('id')}",
                "nome": proc.get("client_name"),
                "contacto": {
                    "email": proc.get("client_email"),
                    "telefone": proc.get("client_phone")
                },
                "dados_pessoais": proc.get("personal_data", {}),
                "nif": proc.get("personal_data", {}).get("nif"),
                "process_ids": [],
                "active_processes_count": 0,
                "created_at": proc.get("created_at"),
                "prioridade": proc_priority,
            }
        
        # Update created_at to earliest process date
        proc_date = proc.get("created_at")
        if proc_date and (not clients_map[key].get("created_at") or proc_date < clients_map[key]["created_at"]):
            clients_map[key]["created_at"] = proc_date
        
        clients_map[key]["process_ids"].append(proc.get("id"))
        
        # Atualizar prioridade do cliente para a mais alta
        proc_priority = proc.get("prioridade") or proc.get("priority") or ""
        PRIORITY_WEIGHT = {"alta": 3, "media": 2, "baixa": 1}
        current_weight = PRIORITY_WEIGHT.get(clients_map[key].get("prioridade", ""), 0)
        new_weight = PRIORITY_WEIGHT.get(proc_priority, 0)
        if new_weight > current_weight:
            clients_map[key]["prioridade"] = proc_priority
        
        # FIX (Pacote K): Cálculo de "processo ativo" baseado em status + is_deleted
        # (anteriormente usava lista de status com typos e sem desistencias).
        # Estados terminais: concluido, desistencia, desistencias, eliminado.
        INACTIVE_STATUSES = ("concluido", "desistencia", "desistencias", "eliminado")
        proc_is_active = (
            not proc.get("is_deleted", False)
            and proc.get("status") not in INACTIVE_STATUSES
        )
        if proc_is_active:
            clients_map[key]["active_processes_count"] += 1
    
    clients = list(clients_map.values())
    
    # M5 - Ordenar: 1ª por prioridade (alta primeiro), 2ª por nome
    PRIORITY_SORT = {"alta": 3, "high": 3, "media": 2, "medium": 2, "baixa": 1, "low": 1}
    clients.sort(key=lambda c: (
        -PRIORITY_SORT.get(c.get("prioridade", ""), 0),
        (c.get("nome") or "").lower()
    ))
    
    # Filtrar por ter processo activo
    if has_active_process is not None:
        clients = [c for c in clients if (c["active_processes_count"] > 0) == has_active_process]

    clients = _merge_entity_client_docs(clients, extra_client_docs, search)
    clients = await _enrich_clients_fonte(clients)
    
    # Desencriptar dados sensíveis
    clients = decrypt_clients_list(clients)
    
    return {
        "clients": clients,
        "total": len(clients),
        "showing_all": False
    }

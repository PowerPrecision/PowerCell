"""GET /clients/registered — listagem Registo de Cliente / Sala de Triagem.

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

async def run_list_registered_clients(
    user: dict,
    search: Optional[str] = None,
    has_process: Optional[bool] = None,
    assigned_to_me: bool = False,
    include_ghosts: bool = False,
    triage_mode: bool = False,
    sort_field: str = 'nome',
    sort_order: str = 'asc',
    limit: int = 50,
    skip: int = 0,
    cursor: Optional[str] = None,
    cursor_id: Optional[str] = None
):
    """
    Listar clientes registados via formulário público.

    PÁGINA: Registo de Cliente
    ACESSO: Todos os utilizadores

    Filtros disponíveis:
    - search: Pesquisar por nome, email ou NIF
    - has_process: True = com processo, False = sem processo
    - assigned_to_me: Mostrar apenas clientes atribuídos ao utilizador atual (para INDEXACAO)
    - triage_mode: PACOTE BN — Sala de Triagem. Alarga a query para incluir:
      (a) Leads normais pendentes de triagem (lead_status="new" sem processo)
      (b) Clientes com processo em status "pre_registo" (cliente ainda a preencher no Portal)
      (c) Clientes com processo sem assigned_indexacao_id (pronto para indexação, na fila)
      Cada cliente é enriquecido com `triage_status` para o frontend renderizar badges.

    Ordenação por defeito: data de registo (mais recentes primeiro)
    """
    user_role = user.get("role", "")
    user_id = user.get("id", "")

    # Sanitize search params used in MongoDB queries
    if search:
        search = sanitize_string(search, max_length=200)
    sort_field = sanitize_string(sort_field, max_length=50)

    # ==================================================================
    # PACOTE BN — SALA DE TRIAGEM
    # ==================================================================
    # Em triage_mode, a query inclui 3 tipos de itens:
    # (a) Leads normais pendentes (lead_status="new" ou ausente, sem processo)
    # (b) Clientes com processo em "pre_registo" (cliente ainda a preencher Portal)
    # (c) Clientes com processo sem assigned_indexacao_id (na fila de espera
    #     para indexação — status inicial de entrada sem indexador atribuído)
    #
    # Para (b) e (c), precisamos de identificar os process_ids relevantes
    # e depois trazer os clientes associados. A query de clientes usa um $or
    # entre "lead sem processo" e "cliente com processo triável".
    # ==================================================================
    triage_process_ids = set()
    if triage_mode:
        # Buscar processos que estão em pre_registo OU com status vazio (Lead)
        # OU sem assigned_indexacao_id (status inicial de entrada aguardando atribuição
        # ao indexador). Excluímos processos eliminados e processos já com indexador atribuído.
        # PACOTE DB — incluímos status=None (novos registos do formulário público).
        triage_processes_cursor = db.processes.find(
            {
                "is_deleted": {"$ne": True},
                "$or": [
                    {"status": {"$in": ["pre_registo", None]}},
                    {"assigned_indexacao_id": {"$in": [None, ""]}},
                ],
            },
            {"_id": 0, "id": 1, "client_id": 1, "status": 1, "assigned_indexacao_id": 1}
        )
        triage_processes = await triage_processes_cursor.to_list(length=500)
        # Mapa client_id → info do processo triável (para enriquecimento)
        triage_client_map = {}
        for p in triage_processes:
            cid = p.get("client_id")
            if cid:
                # Prioridade: pre_registo/Lead tem prioridade sobre "sem indexador"
                # (um processo pode estar em pre_registo/Lead E sem indexador)
                # PACOTE DB — aceita pre_registo OU None (Lead)
                p_status = p.get("status")
                if cid not in triage_client_map or p_status in ("pre_registo", None):
                    triage_client_map[cid] = {
                        "process_id": p.get("id"),
                        "status": p_status,
                        "has_indexador": bool(p.get("assigned_indexacao_id")),
                    }
                triage_process_ids.add(p.get("id"))

    # Construir query
    # REGRAS DE NEGÓCIO (Triagem Manual):
    # - lead_status="new" → Lead pendente de triagem na página de Registos
    # - lead_status="converted" → Lead já transformado em Processo → NÃO aparece por defeito
    # - Sem lead_status → Compatibilidade retroactiva (tratar como "new")
    #
    # REGRA DE NEGÓCIO (Clientes Fantasmas):
    # - Um cliente que apenas foi registado para atuar como 2º Titular
    #   (second_client_id) NÃO deve aparecer na listagem geral.
    # - Só ganha "vida" se for titular principal (client_id) em pelo menos
    #   um processo, ou se for um novo lead sem processo atribuído.
    query = {"registration_completed": True, "is_deleted": {"$ne": True}}

    # ── Filtro de Clientes Fantasmas ──
    # Um cliente "fantasma" é aquele que apenas foi registado para atuar como
    # 2º Titular (second_client_id) num processo. Não deve poluir a listagem
    # geral — só aparece se for 1º Titular em pelo menos um processo, ou se
    # for um novo lead sem processo associado (pendente de triagem).
    #
    # O filtro pode ser bypassado com include_ghosts=True (útil para admin/debug).
    primary_client_ids = []
    if not include_ghosts:
        # Obter todos os IDs de clientes que são titular principal (client_id)
        # em pelo menos um processo — estes clientes têm "vida" no sistema.
        #
        # IMPORTANTE: A query ignora propositadamente is_active e status.
        # Se um cliente FOI alguma vez client_id (1º titular) de QUALQUER processo
        # (activo, cancelado, inactivo, concluído, etc.), ele ganha "vida"
        # permanente e NÃO deve ser filtrado como fantasma.
        primary_client_ids = await db.processes.distinct(
            "client_id",
            {
                "client_id": {"$nin": [None, ""]},
                # NÃO filtrar por is_active nem por status — um 1º titular
                # mantém-se "vivo" mesmo que o processo seja cancelado/inactivado
            }
        )

        # Um cliente deve aparecer na listagem SE:
        # 1. É ou foi titular principal em pelo menos um processo (tem "vida" permanente)
        # 2. OU é um novo lead sem nenhum processo associado (pendente de triagem)
        ghost_filter = {
            "$or": [
                {"id": {"$in": primary_client_ids}},           # É/foi 1º titular → tem "vida" permanente
                {"process_ids": {"$exists": False}},            # Novo lead — sem processos
                {"process_ids": []},                             # Novo lead — lista vazia
                {"process_ids": None},                           # Novo lead — null
            ]
        }

        # Aplicar o filtro de fantasmas como $and (nunca como $or directo na query
        # para evitar conflito com o $or de pesquisa que vem a seguir)
        query["$and"] = query.get("$and", [])
        query["$and"].append(ghost_filter)

    # Filtro de pesquisa - ignora acentos no nome
    # NOTA: Para NIF, usamos blind index (nif_hash) para pesquisa exata
    # A pesquisa por regex em NIF plain text é mantida para compatibilidade com dados antigos
    if search:
        simple_regex = {"$regex": re.escape(search), "$options": "i"}
        name_filter = build_multiword_search_filter(search, "nome")

        # Verificar se a pesquisa é um NIF válido (9 dígitos)
        nif_clean = re.sub(r'[^\d]', '', search)
        search_conditions = [
            name_filter,
            {"contacto.email": simple_regex},
        ]

        # Se parece um NIF, pesquisar também por blind index
        if len(nif_clean) == 9:
            nif_hash = generate_nif_hash(nif_clean)
            if nif_hash:
                search_conditions.append({"dados_pessoais.nif_hash": nif_hash})
            # Manter pesquisa em plain text para dados antigos não migrados
            search_conditions.append({"dados_pessoais.nif": simple_regex})
        else:
            # Não é um NIF válido, pesquisar apenas nome e email
            search_conditions.append({"dados_pessoais.nif": simple_regex})

        query["$or"] = search_conditions
    
    # Filtro por ter processo + lead_status (triagem manual)
    # Por defeito (has_process=false), mostrar apenas leads pendentes (lead_status="new" ou sem lead_status)
    # Leads convertidos (lead_status="converted") com processo NÃO aparecem por defeito
    #
    # PACOTE BN — triage_mode: alarga a query para incluir também clientes com
    # processo em pre_registo ou sem indexador atribuído (Sala de Triagem).
    if triage_mode:
        # Em triage_mode, incluímos:
        # (a) Leads sem processo (lead_status="new" ou ausente, sem process_ids)
        # (b) Clientes cujo ID está no triage_client_map (processo triável)
        query["$and"] = query.get("$and", [])
        triage_client_ids = list(triage_client_map.keys()) if triage_client_map else []
        triage_or_conditions = [
            # (a) Lead sem processo + lead_status pendente
            {
                "$and": [
                    {"$or": [
                        {"process_ids": {"$exists": False}},
                        {"process_ids": []},
                        {"process_ids": None}
                    ]},
                    {"$or": [
                        {"lead_status": {"$exists": False}},
                        {"lead_status": "new"},
                    ]}
                ]
            }
        ]
        # (b) Cliente com processo triável (pre_registo ou sem indexador)
        if triage_client_ids:
            triage_or_conditions.append({"id": {"$in": triage_client_ids}})
        query["$and"].append({"$or": triage_or_conditions})
    elif has_process is not None:
        if has_process:
            query["process_ids"] = {"$exists": True, "$ne": []}
        else:
            query["$and"] = query.get("$and", [])
            process_filter = {
                "$or": [
                    {"process_ids": {"$exists": False}},
                    {"process_ids": []},
                    {"process_ids": None}
                ]
            }
            # Também excluir leads convertidos (lead_status="converted")
            lead_filter = {
                "$or": [
                    {"lead_status": {"$exists": False}},  # Retro-compatibilidade
                    {"lead_status": "new"},
                ]
            }
            query["$and"].extend([process_filter, lead_filter])
    
    # Filtro para assigned_to_me - opcional para qualquer role
    if assigned_to_me:
        query["assigned_to"] = user_id
    
    # Construir ordenação
    sort_order_int = -1 if sort_order.lower() == "desc" else 1
    valid_sort_fields = ["created_at", "updated_at", "nome"]
    if sort_field not in valid_sort_fields:
        sort_field = "created_at"
    
    # O10 - Cursor pagination: se cursor fornecido, usa cursor em vez de skip
    if cursor is not None and cursor_id:
        cursor_op = "$gt" if sort_order_int == 1 else "$lt"
        query["$or"] = query.get("$or", []) if "$or" not in query else query.pop("$or")
        
        # Construir condição de cursor com desempate pelo id
        cursor_condition = {
            "$or": [
                {sort_field: {cursor_op: cursor}},
                {sort_field: cursor, "id": {"$gt" if sort_order_int == 1 else "$lt": cursor_id}}
            ]
        }
        
        # Merge com query existente usando $and
        if query.get("$or"):
            existing_or = query.pop("$or")
            query = {"$and": [{**query, "$or": existing_or}, cursor_condition]}
        else:
            query = {"$and": [{**query}, cursor_condition]}
    
    # Buscar clientes
    clients = await db.clients.find(
        query,
        {"_id": 0}
    ).sort([(sort_field, sort_order_int), ("id", sort_order_int)]).skip(skip if cursor is None else 0).limit(limit).to_list(length=limit)
    
    # Contar total
    total = await db.clients.count_documents(query)
    
    # Buscar nomes dos utilizadores atribuídos
    assigned_user_ids = list(set(c.get("assigned_to") for c in clients if c.get("assigned_to")))
    assigned_users = {}
    if assigned_user_ids:
        users = await db.users.find(
            {"id": {"$in": assigned_user_ids}},
            {"_id": 0, "id": 1, "name": 1}
        ).to_list(length=50)
        assigned_users = {u["id"]: u["name"] for u in users}
    
    # Enriquecer dados dos clientes
    enriched_clients = []
    primary_ids_set = set(primary_client_ids) if primary_client_ids else None
    for c in clients:
        # Verificar se tem processos
        process_ids = c.get("process_ids", [])
        has_process_flag = bool(process_ids)
        
        # Determinar se o cliente é "fantasma"
        # Fantasma = tem process_ids preenchido MAS o seu ID nunca aparece
        # como client_id (titular principal) em NENHUM processo (activo ou não)
        # Nota: Se FOI 1º titular em qualquer processo (mesmo cancelado), NÃO é fantasma
        client_id_val = c.get("id")
        is_ghost = False
        if primary_ids_set is not None and client_id_val:
            is_ghost = (
                client_id_val not in primary_ids_set
                and bool(process_ids)  # Tem processos, mas só como 2º titular
            )
        
        # Buscar informação dos processos
        processes_info = []
        should_exclude = False
        if process_ids:
            processes = await db.processes.find(
                {"id": {"$in": process_ids}},
                {"_id": 0, "id": 1, "process_number": 1, "status": 1}
            ).to_list(length=10)

            for p in processes:
                # PACOTE CK — REGRA estrita: Se tem um processo que já passou
                # da fase inicial, desaparece dos Registos (Leads)
                # PACOTE DB — None (Lead) também conta como fase inicial.
                if p.get("status") not in ["pre_registo", None, "clientes_espera", "eliminado"]:
                    should_exclude = True
                    break
                processes_info.append(p)

        if should_exclude:
            continue  # Salta este cliente, não o mostra na tabela de Leads

        # ==================================================================
        # PACOTE BN — triage_status (Sala de Triagem)
        # ==================================================================
        # Determina o estado de triagem do cliente para o frontend renderizar
        # a badge correta. Valores possíveis:
        # - "pre_registo": cliente tem processo em status "pre_registo" ou vazio
        #   (Lead, ainda a preencher no Portal) → Badge amarela
        # - "ready_for_indexing": cliente tem processo sem assigned_indexacao_id
        #   (na fila de espera para indexação) → Badge azul/verde
        # - "new_lead": lead pendente sem processo (lead_status="new") → sem badge
        #   específica (comportamento existente)
        # - "converted": lead já convertido em processo fora da triagem → sem badge
        # ==================================================================
        triage_status = None
        if triage_mode and client_id_val:
            triage_info = triage_client_map.get(client_id_val)
            if triage_info:
                # PACOTE DB — aceita pre_registo OU None (Lead)
                if triage_info.get("status") in ("pre_registo", None):
                    triage_status = "pre_registo"
                elif not triage_info.get("has_indexador"):
                    triage_status = "ready_for_indexing"

        enriched_clients.append({
            "id": c.get("id"),
            "nome": c.get("nome"),
            "contacto": c.get("contacto", {}),
            "dados_pessoais": c.get("dados_pessoais", {}),
            "nif": c.get("dados_pessoais", {}).get("nif"),
            "is_active": c.get("is_active", True),
            "is_ghost": is_ghost,  # Cliente fantasma (apenas 2º titular)
            "has_process": has_process_flag,
            "process_count": len(process_ids),
            "processes": processes_info,
            "assigned_to": c.get("assigned_to"),
            "assigned_to_name": assigned_users.get(c.get("assigned_to")),
            "assigned_at": c.get("assigned_at"),
            "created_at": c.get("created_at"),
            "updated_at": c.get("updated_at"),
            "fonte": c.get("fonte"),
            "has_property": c.get("has_property"),
            "idade_menos_35": c.get("idade_menos_35"),
            "lead_status": c.get("lead_status", "new"),  # "new" = pendente, "converted" = com processo
            # PACOTE BN — estado de triagem para badges no frontend
            "triage_status": triage_status,
        })
    
    # Desencriptar dados sensíveis
    enriched_clients = decrypt_clients_list(enriched_clients)
    
    # Cursor info para próxima página
    next_cursor = None
    next_cursor_id = None
    if enriched_clients:
        last = enriched_clients[-1]
        next_cursor = last.get(sort_field, "")
        next_cursor_id = last.get("id", "")
    
    return {
        "clients": enriched_clients,
        "total": total,
        "has_process_filter": has_process,
        "assigned_to_me": assigned_to_me,
        "include_ghosts": include_ghosts,
        "ghost_count": sum(1 for c in enriched_clients if c.get("is_ghost")),
        "sort_field": sort_field,
        "sort_order": sort_order,
        "next_cursor": next_cursor,
        "next_cursor_id": next_cursor_id,
        "has_more": len(enriched_clients) == limit
    }

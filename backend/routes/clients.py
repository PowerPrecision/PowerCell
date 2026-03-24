"""
Rotas para gestão de Clientes

Permite gerir clientes de forma independente dos processos.
Um cliente pode ter múltiplos processos de compra/financiamento.

FLUXO:
1. Formulário público cria ficha de cliente na tabela 'clients'
2. Quando o cliente é atribuído a um utilizador, cria-se o processo
3. Um cliente pode ter vários processos

SEGURANÇA:
- Campos sensíveis (NIFs, telefones) são encriptados automaticamente
"""

import uuid
import logging
from typing import List, Optional
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends, Query

from database import db
from models.client import (
    Client, ClientCreate, ClientUpdate, 
    ClientContact, ClientPersonalData, ClientFinancialData,
    find_or_create_client_key
)
from services.auth import get_current_user, require_roles
from models.auth import UserRole
from services.encryption import encryption_service
from services.process_service import get_next_process_number

router = APIRouter(prefix="/clients", tags=["Clients"])
logger = logging.getLogger(__name__)


def encrypt_client_data(data: dict) -> dict:
    """Encripta campos sensíveis de um cliente."""
    if not encryption_service.is_available() or not data:
        return data
    
    result = data.copy()
    
    # Encriptar dados_pessoais
    if "dados_pessoais" in result and isinstance(result["dados_pessoais"], dict):
        fields = ["nif", "documento_id", "morada_fiscal", "phone", "telefone"]
        for field in fields:
            if field in result["dados_pessoais"] and result["dados_pessoais"][field]:
                result["dados_pessoais"][field] = encryption_service.encrypt(str(result["dados_pessoais"][field]))
    
    # Encriptar contacto
    if "contacto" in result and isinstance(result["contacto"], dict):
        fields = ["telefone", "telefone_secundario", "phone"]
        for field in fields:
            if field in result["contacto"] and result["contacto"][field]:
                result["contacto"][field] = encryption_service.encrypt(str(result["contacto"][field]))
    
    return result


def decrypt_client_data(data: dict) -> dict:
    """Desencripta campos sensíveis de um cliente."""
    if not encryption_service.is_available() or not data:
        return data
    
    result = data.copy()
    
    # Desencriptar dados_pessoais
    if "dados_pessoais" in result and isinstance(result["dados_pessoais"], dict):
        fields = ["nif", "documento_id", "morada_fiscal", "phone", "telefone"]
        for field in fields:
            if field in result["dados_pessoais"] and result["dados_pessoais"][field]:
                result["dados_pessoais"][field] = encryption_service.decrypt(str(result["dados_pessoais"][field]))
    
    # Desencriptar contacto
    if "contacto" in result and isinstance(result["contacto"], dict):
        fields = ["telefone", "telefone_secundario", "phone"]
        for field in fields:
            if field in result["contacto"] and result["contacto"][field]:
                result["contacto"][field] = encryption_service.decrypt(str(result["contacto"][field]))
    
    return result


def decrypt_clients_list(clients: list) -> list:
    """Desencripta uma lista de clientes."""
    return [decrypt_client_data(c) for c in clients]


# ==============================================================================
# ENDPOINT: LISTAR CLIENTES REGISTADOS (PÁGINA REGISTO DE CLIENTE)
# ==============================================================================

@router.get("/registered")
async def list_registered_clients(
    search: Optional[str] = Query(None, description="Pesquisar por nome, email ou NIF"),
    has_process: Optional[bool] = Query(None, description="Filtrar por ter processo criado"),
    assigned_to_me: bool = Query(False, description="Mostrar apenas clientes atribuídos ao utilizador atual"),
    sort_field: str = Query("nome", description="Campo de ordenação"),
    sort_order: str = Query("asc", description="Ordem: asc ou desc"),
    limit: int = Query(50, le=200),
    skip: int = Query(0),
    cursor: Optional[str] = Query(None, description="Cursor para paginação (valor do campo de ordenação do último item)"),
    cursor_id: Optional[str] = Query(None, description="ID do último item (para desempate na paginação por cursor)"),
    user: dict = Depends(get_current_user)
):
    """
    Listar clientes registados via formulário público.
    
    PÁGINA: Registo de Cliente
    ACESSO: Todos os utilizadores
    
    Filtros disponíveis:
    - search: Pesquisar por nome, email ou NIF
    - has_process: True = com processo, False = sem processo
    - assigned_to_me: Mostrar apenas clientes atribuídos ao utilizador atual (para INDEXACAO)
    
    Ordenação por defeito: data de registo (mais recentes primeiro)
    """
    user_role = user.get("role", "")
    user_id = user.get("id", "")
    
    # Construir query
    query = {"registration_completed": True}
    
    # Filtro de pesquisa
    if search:
        search_regex = {"$regex": search, "$options": "i"}
        query["$or"] = [
            {"nome": search_regex},
            {"contacto.email": search_regex},
            {"dados_pessoais.nif": search_regex}
        ]
    
    # Filtro por ter processo
    if has_process is not None:
        if has_process:
            query["process_ids"] = {"$exists": True, "$ne": []}
        else:
            query["$or"] = [
                {"process_ids": {"$exists": False}},
                {"process_ids": []},
                {"process_ids": None}
            ]
    
    # Filtro para INDEXACAO - ver apenas clientes atribuídos a ele
    if assigned_to_me or user_role == "indexacao":
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
    for c in clients:
        # Verificar se tem processos
        process_ids = c.get("process_ids", [])
        has_process_flag = bool(process_ids)
        
        # Buscar informação dos processos
        processes_info = []
        if process_ids:
            processes = await db.processes.find(
                {"id": {"$in": process_ids}},
                {"_id": 0, "id": 1, "process_number": 1, "status": 1, "assigned_consultor_id": 1, "assigned_mediador_id": 1}
            ).to_list(length=10)
            
            for p in processes:
                processes_info.append({
                    "id": p.get("id"),
                    "process_number": p.get("process_number"),
                    "status": p.get("status")
                })
        
        enriched_clients.append({
            "id": c.get("id"),
            "nome": c.get("nome"),
            "contacto": c.get("contacto", {}),
            "dados_pessoais": c.get("dados_pessoais", {}),
            "nif": c.get("dados_pessoais", {}).get("nif"),
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
            "idade_menos_35": c.get("idade_menos_35")
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
        "sort_field": sort_field,
        "sort_order": sort_order,
        "next_cursor": next_cursor,
        "next_cursor_id": next_cursor_id,
        "has_more": len(enriched_clients) == limit
    }


@router.post("/{client_id}/assign")
async def assign_client_to_user(
    client_id: str,
    assign_to_user_id: Optional[str] = Query(None, description="ID do utilizador a atribuir (vazio = atribuir a si próprio)"),
    create_process: bool = Query(True, description="Criar processo automaticamente"),
    process_type: str = Query("credito_habitacao", description="Tipo de processo a criar"),
    user: dict = Depends(get_current_user)
):
    """
    Atribuir um cliente a um utilizador.
    
    FLUXO:
    1. Atribui o cliente ao utilizador
    2. Se create_process=True, cria automaticamente um processo
    
    Permissões:
    - Admin/CEO/Diretor: Podem atribuir a qualquer utilizador
    - Consultor/Intermediario: Atribuem a si próprios
    - Gestor de Documentos: Não pode atribuir clientes
    """
    # Verificar permissões
    user_role = user.get("role", "")
    user_id = user.get("id", "")
    
    if user_role == "gestor_documentos":
        raise HTTPException(status_code=403, detail="Gestor de Documentos não pode atribuir clientes")
    
    # Determinar utilizador de destino
    if user_role in ["admin", "ceo", "diretor"]:
        target_user_id = assign_to_user_id or user_id
    else:
        target_user_id = user_id  # Apenas a si próprio
    
    # Buscar cliente
    client = await db.clients.find_one({"id": client_id})
    if not client:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    
    # Buscar utilizador de destino
    target_user = await db.users.find_one({"id": target_user_id})
    if not target_user:
        raise HTTPException(status_code=404, detail="Utilizador não encontrado")
    
    now = datetime.now(timezone.utc).isoformat()
    process_id = None
    process_number = None
    
    # Criar processo se solicitado
    if create_process:
        # Obter próximo número de processo
        process_number = await get_next_process_number()
        process_id = str(uuid.uuid4())
        
        # Obter estado inicial
        first_status = await db.workflow_statuses.find_one({}, {"_id": 0}, sort=[("order", 1)])
        initial_status = first_status["name"] if first_status else "clientes_espera"
        
        # Preparar dados do processo
        client_email = client.get("contacto", {}).get("email", "")
        client_phone = client.get("contacto", {}).get("telefone", "")
        client_name = client.get("nome", "")
        
        personal_data = client.get("dados_pessoais", {}) or {}
        if client_email and not personal_data.get("email"):
            personal_data["email"] = client_email
        if client_phone and not personal_data.get("telefone"):
            personal_data["telefone"] = client_phone
        if client_name and not personal_data.get("nome"):
            personal_data["nome"] = client_name
        
        # Criar documento do processo
        # Gerar link S3 com nome do cliente (espaços substituídos por underscores)
        safe_name = "_".join(w.capitalize() for w in client_name.strip().split()) if client_name else process_id[:8]
        s3_folder = f"s3://powerprecision-docs-storage/Documentação Clientes/{safe_name}/"
        
        process_doc = {
            "id": process_id,
            "process_number": process_number,
            "client_ids": [client_id],
            "client_id": client_id,
            "client_name": client_name,
            "client_email": client_email,
            "client_phone": client_phone,
            "client_nif": client.get("dados_pessoais", {}).get("nif"),
            "process_type": process_type,
            "status": initial_status,
            "is_active": True,
            "personal_data": personal_data,
            "financial_data": client.get("dados_financeiros", {}),
            "real_estate_data": client.get("dados_imobiliarios", {}),
            "titular2_data": client.get("titular2_data"),
            "credit_data": None,
            "has_property": client.get("has_property", False),
            "idade_menos_35": client.get("idade_menos_35", False),
            "s3_folder": s3_folder,
            "source": "client_assignment",
            "created_at": now,
            "updated_at": now,
            "created_by": user.get("email")
        }
        
        # Atribuir automaticamente baseado no papel do utilizador de destino
        target_role = target_user.get("role", "")
        if target_role in ["intermediario", "mediador"]:
            process_doc["assigned_mediador_id"] = target_user_id
            process_doc["mediador_name"] = target_user.get("name")
        elif target_role == "consultor":
            process_doc["assigned_consultor_id"] = target_user_id
            process_doc["consultor_name"] = target_user.get("name")
        elif target_role == "indexacao":
            process_doc["assigned_indexacao_id"] = target_user_id
        
        # Inserir processo
        await db.processes.insert_one(process_doc)
    
    # Atualizar cliente
    if process_id:
        await db.clients.update_one(
            {"id": client_id},
            {
                "$set": {"assigned_to": target_user_id, "assigned_at": now, "updated_at": now},
                "$addToSet": {"process_ids": process_id}
            }
        )
    else:
        await db.clients.update_one(
            {"id": client_id},
            {"$set": {"assigned_to": target_user_id, "assigned_at": now, "updated_at": now}}
        )
    
    logger.info(f"Cliente {client_id} atribuído a {target_user_id} por {user.get('email')}")
    
    return {
        "success": True,
        "message": f"Cliente atribuído a {target_user.get('name')}",
        "client_id": client_id,
        "assigned_to": target_user_id,
        "assigned_to_name": target_user.get("name"),
        "process_created": create_process,
        "process_id": process_id,
        "process_number": process_number
    }


@router.get("")
async def list_clients(
    search: Optional[str] = Query(None, description="Pesquisar por nome, email ou NIF"),
    has_active_process: Optional[bool] = Query(None, description="Filtrar por ter processo activo"),
    show_all: bool = Query(True, description="Se True, mostra todos os clientes da empresa. Se False, apenas os do utilizador"),
    status_filter: Optional[str] = Query(None, description="Filtrar por fase do processo"),
    assignment_filter: Optional[str] = Query(None, description="Filtrar por tipo de atribuição: 'both', 'consultor', 'intermediario', 'none'"),
    limit: int = Query(100, le=500),
    skip: int = Query(0),
    user: dict = Depends(get_current_user)
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
    user_role = user.get("role", "")
    user_id = user.get("id", "")
    user_email = user.get("email", "")
    
    # Buscar workflow statuses para labels
    workflow_statuses = await db.workflow_statuses.find({}, {"_id": 0}).sort("order", 1).to_list(100)
    status_map = {s["name"]: s for s in workflow_statuses}
    
    # Se show_all=True OU é admin/ceo/diretor, mostrar todos
    if show_all or user_role in ["admin", "ceo", "diretor"]:
        # Mostrar todos os clientes da empresa
        process_query = {}
        
        if search:
            process_query = {
                "$or": [
                    {"client_name": {"$regex": search, "$options": "i"}},
                    {"client_email": {"$regex": search, "$options": "i"}},
                    {"personal_data.nif": {"$regex": search, "$options": "i"}}
                ]
            }
        
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
        
        # Buscar todos os processos (clientes únicos)
        processes = await db.processes.find(
            process_query,
            {"_id": 0, "id": 1, "client_name": 1, "client_email": 1, "client_phone": 1, 
             "personal_data": 1, "status": 1, "process_number": 1, "client_id": 1,
             "assigned_consultor_id": 1, "assigned_mediador_id": 1,
             "consultor_name": 1, "mediador_name": 1, "is_active": 1}
        ).sort("client_name", 1).skip(skip).limit(limit).to_list(length=limit)
        
        # Agrupar por cliente
        clients_map = {}
        for proc in processes:
            key = proc.get("client_id") or proc.get("client_name", "").lower().strip()
            if not key:
                continue
            
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
                    "processes": []  # Lista de processos com fase
                }
            
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
                "mediador_name": proc.get("mediador_name")
            }
            clients_map[key]["processes"].append(process_info)
            clients_map[key]["process_ids"].append(proc.get("id"))
            
            # Determinar fase principal (primeiro processo ativo ou primeiro processo)
            if not clients_map[key].get("fase_principal"):
                clients_map[key]["fase_principal"] = process_info
            
            if proc.get("is_active", True) and proc.get("status") not in ["desistencias", "concluidos", "arquivado", "perdido", "concluido"]:
                clients_map[key]["active_processes_count"] += 1
        
        clients = list(clients_map.values())
        
        # M5 - Ordenar por nome alfabeticamente (padrão)
        clients.sort(key=lambda c: (c.get("nome") or "").lower())
        
        # Filtrar por ter processo activo
        if has_active_process is not None:
            clients = [c for c in clients if (c["active_processes_count"] > 0) == has_active_process]
        
        # Desencriptar dados sensíveis
        clients = decrypt_clients_list(clients)
        
        # Adicionar lista de fases disponíveis para o filtro
        available_statuses = [{"name": s["name"], "label": s.get("label", s["name"])} for s in workflow_statuses]
        
        return {
            "clients": clients,
            "total": len(clients),
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
    elif user_role in ["mediador", "intermediario"]:
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
        search_filter = {
            "$or": [
                {"client_name": {"$regex": search, "$options": "i"}},
                {"client_email": {"$regex": search, "$options": "i"}},
                {"personal_data.nif": {"$regex": search, "$options": "i"}}
            ]
        }
        process_query = {"$and": [process_query, search_filter]}
    
    # Buscar processos e transformar em "clientes"
    processes = await db.processes.find(
        process_query,
        {"_id": 0, "id": 1, "client_name": 1, "client_email": 1, "client_phone": 1, 
         "personal_data": 1, "status": 1, "process_number": 1, "client_id": 1}
    ).sort("client_name", 1).skip(skip).limit(limit).to_list(length=limit)
    
    # Agrupar por cliente (usando client_id ou client_name como chave)
    clients_map = {}
    for proc in processes:
        key = proc.get("client_id") or proc.get("client_name", "").lower().strip()
        if not key:
            continue
        
        if key not in clients_map:
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
                "active_processes_count": 0
            }
        
        clients_map[key]["process_ids"].append(proc.get("id"))
        
        if proc.get("status") not in ["arquivado", "perdido", "concluido"]:
            clients_map[key]["active_processes_count"] += 1
    
    clients = list(clients_map.values())
    
    # M5 - Ordenar por nome alfabeticamente (padrão)
    clients.sort(key=lambda c: (c.get("nome") or "").lower())
    
    # Filtrar por ter processo activo
    if has_active_process is not None:
        clients = [c for c in clients if (c["active_processes_count"] > 0) == has_active_process]
    
    # Desencriptar dados sensíveis
    clients = decrypt_clients_list(clients)
    
    return {
        "clients": clients,
        "total": len(clients),
        "showing_all": False
    }


@router.get("/{client_id}")
async def get_client(
    client_id: str,
    user: dict = Depends(get_current_user)
):
    """Obter detalhes de um cliente."""
    client = await db.clients.find_one({"id": client_id}, {"_id": 0})
    
    if not client:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    
    # Carregar detalhes dos processos
    processes = []
    if client.get("process_ids"):
        processes = await db.processes.find(
            {"id": {"$in": client["process_ids"]}},
            {"_id": 0, "id": 1, "process_number": 1, "status": 1, "process_type": 1, "created_at": 1}
        ).to_list(length=50)
    
    client["processes"] = processes
    
    # Desencriptar dados sensíveis
    client = decrypt_client_data(client)
    
    return client


@router.post("", response_model=Client)
async def create_client(
    client_data: ClientCreate,
    user: dict = Depends(get_current_user)
):
    """Criar um novo cliente."""
    # Gestor de Documentos não pode criar clientes
    if user.get("role") == "gestor_documentos":
        raise HTTPException(status_code=403, detail="Gestor de Documentos não pode criar clientes. Apenas gerir documentos.")
    
    # Verificar se já existe cliente com mesmo NIF ou email
    existing_query = []
    if client_data.nif:
        existing_query.append({"dados_pessoais.nif": client_data.nif})
    if client_data.email:
        existing_query.append({"contacto.email": client_data.email.lower()})
    
    if existing_query:
        existing = await db.clients.find_one({"$or": existing_query})
        if existing:
            raise HTTPException(
                status_code=400,
                detail=f"Já existe um cliente com este NIF ou email: {existing.get('nome')}"
            )
    
    now = datetime.now(timezone.utc).isoformat()
    
    client = Client(
        id=str(uuid.uuid4()),
        nome=client_data.nome,
        contacto=ClientContact(
            email=client_data.email.lower() if client_data.email else None,
            telefone=client_data.telefone
        ),
        dados_pessoais=ClientPersonalData(
            nif=client_data.nif
        ),
        fonte=client_data.fonte,
        notas=client_data.notas,
        created_at=now,
        updated_at=now,
        created_by=user.get("email")
    )
    
    # Encriptar campos sensíveis antes de guardar
    client_dict = client.model_dump()
    client_dict = encrypt_client_data(client_dict)
    
    await db.clients.insert_one(client_dict)
    
    logger.info(f"Cliente criado: {client.id} - {client.nome} por {user.get('email')}")
    
    # Desencriptar para a resposta
    client_dict = decrypt_client_data(client_dict)
    return Client(**client_dict)


@router.put("/{client_id}")
async def update_client(
    client_id: str,
    client_data: ClientUpdate,
    user: dict = Depends(get_current_user)
):
    """Actualizar dados de um cliente."""
    client = await db.clients.find_one({"id": client_id})
    
    if not client:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    
    update_dict = {"updated_at": datetime.now(timezone.utc).isoformat()}
    
    if client_data.nome:
        update_dict["nome"] = client_data.nome
    if client_data.contacto:
        update_dict["contacto"] = client_data.contacto.model_dump(exclude_unset=True)
    if client_data.dados_pessoais:
        update_dict["dados_pessoais"] = client_data.dados_pessoais.model_dump(exclude_unset=True)
    if client_data.dados_financeiros:
        update_dict["dados_financeiros"] = client_data.dados_financeiros.model_dump(exclude_unset=True)
    if client_data.tags is not None:
        update_dict["tags"] = client_data.tags
    if client_data.notas is not None:
        update_dict["notas"] = client_data.notas
    
    await db.clients.update_one(
        {"id": client_id},
        {"$set": update_dict}
    )
    
    logger.info(f"Cliente {client_id} actualizado por {user.get('email')}")
    
    return {"success": True, "message": "Cliente actualizado"}


@router.post("/{client_id}/link-process")
async def link_process_to_client(
    client_id: str,
    process_id: str,
    user: dict = Depends(get_current_user)
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


@router.delete("/{client_id}/unlink-process/{process_id}")
async def unlink_process_from_client(
    client_id: str,
    process_id: str,
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO, UserRole.ADMINISTRATIVO]))
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


@router.post("/{client_id}/create-process")
async def create_process_for_client(
    client_id: str,
    process_type: str = Query("credito_habitacao", description="Tipo de processo"),
    description: Optional[str] = Query(None, description="Descrição do processo"),
    user: dict = Depends(get_current_user)
):
    """
    Criar um novo processo para um cliente existente.
    
    Isto permite que o mesmo cliente tenha múltiplos processos de compra.
    O client_id pode ser:
    - Um ID real de cliente na colecção clients
    - Um ID de processo (quando o cliente é virtual/agregado de processos)
    """
    # Gestor de Documentos não pode criar processos
    if user.get("role") == "gestor_documentos":
        raise HTTPException(status_code=403, detail="Gestor de Documentos não pode criar processos. Apenas gerir documentos.")
    
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
    
    # Criar novo processo com dados do cliente
    new_process = {
        "id": process_id,
        "process_number": next_number,
        "client_id": client_id,
        "client_name": client_name,
        "client_email": client_email,
        "client_phone": client_phone,
        "process_type": process_type,
        "status": "novo",
        "description": description,
        # Dados pessoais e financeiros com campos consistentes
        "personal_data": personal_data,
        "financial_data": client.get("dados_financeiros", {}),
        "real_estate_data": {},
        "credit_data": {},
        # Co-compradores herdados do cliente
        "co_buyers": client.get("co_buyers", []),
        "co_applicants": client.get("co_applicants", []),
        # Metadados
        "created_at": now,
        "updated_at": now,
        "created_by": user.get("email"),
        "source": "client_portal"
    }
    
    await db.processes.insert_one(new_process)
    
    # Se temos um cliente real, atualizar a lista de processos
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


@router.get("/{client_id}/processes")
async def get_client_processes(
    client_id: str,
    include_archived: bool = Query(False),
    user: dict = Depends(get_current_user)
):
    """Obter todos os processos de um cliente."""
    client = await db.clients.find_one({"id": client_id})
    
    if not client:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    
    process_ids = client.get("process_ids", [])
    
    if not process_ids:
        return {
            "client_name": client.get("nome"),
            "processes": [],
            "total": 0
        }
    
    query = {"id": {"$in": process_ids}}
    if not include_archived:
        query["status"] = {"$nin": ["arquivado", "cancelado"]}
    
    processes = await db.processes.find(
        query,
        {"_id": 0}
    ).sort("created_at", -1).to_list(length=50)
    
    return {
        "client_name": client.get("nome"),
        "processes": processes,
        "total": len(processes)
    }


@router.post("/find-or-create")
async def find_or_create_client(
    nome: str,
    email: Optional[str] = None,
    nif: Optional[str] = None,
    telefone: Optional[str] = None,
    user: dict = Depends(get_current_user)
):
    """
    Encontrar cliente existente ou criar novo.
    
    Procura por NIF, email ou nome similar.
    Se não encontrar, cria um novo cliente.
    """
    # Tentar encontrar por NIF
    if nif:
        existing = await db.clients.find_one({"dados_pessoais.nif": nif})
        if existing:
            return {
                "found": True,
                "client": existing,
                "match_type": "nif"
            }
    
    # Tentar encontrar por email
    if email:
        existing = await db.clients.find_one({"contacto.email": email.lower()})
        if existing:
            return {
                "found": True,
                "client": existing,
                "match_type": "email"
            }
    
    # Tentar encontrar por nome similar
    if nome:
        # Pesquisa fuzzy pelo nome
        from routes.ai_bulk import normalize_text_for_matching
        nome_norm = normalize_text_for_matching(nome)
        
        # Buscar candidatos
        candidates = await db.clients.find(
            {},
            {"_id": 0, "id": 1, "nome": 1}
        ).to_list(length=1000)
        
        for candidate in candidates:
            candidate_norm = normalize_text_for_matching(candidate.get("nome", ""))
            # Match exacto após normalização
            if nome_norm == candidate_norm:
                full_client = await db.clients.find_one({"id": candidate["id"]}, {"_id": 0})
                return {
                    "found": True,
                    "client": full_client,
                    "match_type": "nome"
                }
    
    # Não encontrou - criar novo cliente
    client_data = ClientCreate(
        nome=nome,
        email=email,
        telefone=telefone,
        nif=nif,
        fonte="auto_created"
    )
    
    new_client = await create_client(client_data, user)
    
    return {
        "found": False,
        "client": new_client.model_dump(),
        "match_type": "created"
    }


@router.delete("/{client_id}")
async def delete_client(
    client_id: str,
    hard_delete: bool = False,
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO, UserRole.DIRETOR, UserRole.ADMINISTRATIVO]))
):
    """
    Eliminar um cliente/processo (soft delete por defeito).
    
    Nota: Neste sistema, clientes e processos são a mesma entidade.
    Esta função procura primeiro na colecção 'processes' e depois em 'clients'.
    
    Por defeito, usa soft delete (status='eliminado') para permitir undo.
    Com hard_delete=True, elimina permanentemente.
    
    Apenas Admin, CEO, Diretor e Administrativo podem eliminar.
    """
    # Verificar também se é diretor ou administrativo
    if user.get("role") not in ["admin", "ceo", "diretor", "administrativo"]:
        raise HTTPException(status_code=403, detail="Sem permissão para eliminar clientes")
    
    now = datetime.now(timezone.utc).isoformat()
    
    # Procurar primeiro em processes (tabela principal)
    process = await db.processes.find_one({"id": client_id})
    
    if process:
        # Verificar se o processo está activo
        active_statuses = ["arquivado", "cancelado", "concluido", "desistencias"]
        if process.get("status") not in active_statuses:
            # Permitir eliminar mas avisar
            logger.warning(f"Processo {client_id} eliminado com status activo: {process.get('status')}")
        
        if hard_delete:
            # Eliminação permanente
            await db.documents.delete_many({"process_id": client_id})
            await db.tasks.delete_many({"process_id": client_id})
            await db.history.delete_many({"process_id": client_id})
            await db.processes.delete_one({"id": client_id})
            
            logger.info(f"Processo/Cliente {client_id} ({process.get('client_name')}) eliminado permanentemente por {user.get('email')}")
            
            return {"success": True, "message": f"Cliente '{process.get('client_name')}' eliminado permanentemente"}
        else:
            # Soft delete - permite undo
            await db.processes.update_one(
                {"id": client_id},
                {"$set": {
                    "status": "eliminado",
                    "is_active": False,
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
                    "deleted_at": now,
                    "deleted_by": user["id"]
                }}
            )
            
            # Marcar tarefas como eliminadas (soft delete)
            await db.tasks.update_many(
                {"process_id": client_id},
                {"$set": {
                    "deleted": True,
                    "deleted_at": now,
                    "deleted_by": user["id"]
                }}
            )
            
            logger.info(f"Processo/Cliente {client_id} ({process.get('client_name')}) movido para lixo por {user.get('email')}")
            
            return {
                "success": True, 
                "message": f"Cliente '{process.get('client_name')}' movido para o lixo",
                "can_undo": True,
                "restore_endpoint": f"/api/processes/{client_id}/restore"
            }
    
    # Se não encontrou em processes, procurar em clients (compatibilidade)
    client = await db.clients.find_one({"id": client_id})
    
    if not client:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    
    # Verificar se tem processos activos
    if client.get("process_ids"):
        active_count = await db.processes.count_documents({
            "id": {"$in": client["process_ids"]},
            "status": {"$nin": ["arquivado", "cancelado", "concluido", "eliminado"]}
        })
        if active_count > 0:
            raise HTTPException(
                status_code=400,
                detail=f"Cliente tem {active_count} processo(s) activo(s). Archive-os primeiro."
            )
    
    if hard_delete:
        await db.clients.delete_one({"id": client_id})
        logger.info(f"Cliente {client_id} eliminado permanentemente por {user.get('email')}")
        return {"success": True, "message": "Cliente eliminado permanentemente"}
    else:
        # Soft delete para cliente na coleção clients
        await db.clients.update_one(
            {"id": client_id},
            {"$set": {
                "deleted": True,
                "deleted_at": now,
                "deleted_by": user["id"]
            }}
        )
        
        logger.info(f"Cliente {client_id} movido para lixo por {user.get('email')}")
        
        return {
            "success": True, 
            "message": "Cliente movido para o lixo",
            "can_undo": True,
            "restore_endpoint": f"/api/clients/{client_id}/restore"
        }

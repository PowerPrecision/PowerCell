"""
Rotas para gestão de Clientes

Permite gerir clientes de forma independente dos processos.
Um cliente pode ter múltiplos processos de compra/financiamento.
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

router = APIRouter(prefix="/clients", tags=["Clients"])
logger = logging.getLogger(__name__)


@router.get("")
async def list_clients(
    search: Optional[str] = Query(None, description="Pesquisar por nome, email ou NIF"),
    has_active_process: Optional[bool] = Query(None, description="Filtrar por ter processo activo"),
    show_all: bool = Query(True, description="Se True, mostra todos os clientes da empresa. Se False, apenas os do utilizador"),
    limit: int = Query(100, le=500),
    skip: int = Query(0),
    user: dict = Depends(get_current_user)
):
    """
    Listar clientes.
    - show_all=True: Todos os utilizadores vêem todos os clientes da empresa
    - show_all=False: Utilizadores vêem apenas os seus clientes (atribuídos)
    
    Nota: Todos podem ver a lista de clientes para referência,
    mas apenas têm acesso total a processos que lhes estão atribuídos.
    """
    user_role = user.get("role", "")
    user_id = user.get("id", "")
    user_email = user.get("email", "")
    
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
        
        # Buscar todos os processos (clientes únicos)
        processes = await db.processes.find(
            process_query,
            {"_id": 0, "id": 1, "client_name": 1, "client_email": 1, "client_phone": 1, 
             "personal_data": 1, "status": 1, "process_number": 1, "client_id": 1,
             "assigned_consultor_id": 1, "assigned_mediador_id": 1}
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
                    "active_processes_count": 0
                }
            
            clients_map[key]["process_ids"].append(proc.get("id"))
            
            if proc.get("status") not in ["arquivado", "perdido", "concluido"]:
                clients_map[key]["active_processes_count"] += 1
        
        clients = list(clients_map.values())
        
        # Filtrar por ter processo activo
        if has_active_process is not None:
            clients = [c for c in clients if (c["active_processes_count"] > 0) == has_active_process]
        
        return {
            "clients": clients,
            "total": len(clients),
            "showing_all": True
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
    
    # Filtrar por ter processo activo
    if has_active_process is not None:
        clients = [c for c in clients if (c["active_processes_count"] > 0) == has_active_process]
    
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
    
    await db.clients.insert_one(client.model_dump())
    
    logger.info(f"Cliente criado: {client.id} - {client.nome} por {user.get('email')}")
    
    return client


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
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
):
    """Desvincular um processo de um cliente (apenas admin/CEO)."""
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
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
):
    """
    Eliminar um cliente/processo.
    
    Nota: Neste sistema, clientes e processos são a mesma entidade.
    Esta função procura primeiro na colecção 'processes' e depois em 'clients'.
    
    Apenas Admin, CEO e Diretor podem eliminar.
    """
    # Verificar também se é diretor
    if user.get("role") not in ["admin", "ceo", "diretor"]:
        raise HTTPException(status_code=403, detail="Sem permissão para eliminar clientes")
    
    # Procurar primeiro em processes (tabela principal)
    process = await db.processes.find_one({"id": client_id})
    
    if process:
        # Verificar se o processo está activo
        active_statuses = ["arquivado", "cancelado", "concluido", "desistencias"]
        if process.get("status") not in active_statuses:
            # Permitir eliminar mas avisar
            logger.warning(f"Processo {client_id} eliminado com status activo: {process.get('status')}")
        
        # Eliminar documentos associados
        await db.documents.delete_many({"process_id": client_id})
        
        # Eliminar tarefas associadas
        await db.tasks.delete_many({"process_id": client_id})
        
        # Eliminar histórico associado
        await db.history.delete_many({"process_id": client_id})
        
        # Eliminar o processo
        await db.processes.delete_one({"id": client_id})
        
        logger.info(f"Processo/Cliente {client_id} ({process.get('client_name')}) eliminado por {user.get('email')}")
        
        return {"success": True, "message": f"Cliente '{process.get('client_name')}' eliminado com sucesso"}
    
    # Se não encontrou em processes, procurar em clients (compatibilidade)
    client = await db.clients.find_one({"id": client_id})
    
    if not client:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    
    # Verificar se tem processos activos
    if client.get("process_ids"):
        active_count = await db.processes.count_documents({
            "id": {"$in": client["process_ids"]},
            "status": {"$nin": ["arquivado", "cancelado", "concluido"]}
        })
        if active_count > 0:
            raise HTTPException(
                status_code=400,
                detail=f"Cliente tem {active_count} processo(s) activo(s). Archive-os primeiro."
            )
    
    await db.clients.delete_one({"id": client_id})
    
    logger.info(f"Cliente {client_id} eliminado por {user.get('email')}")
    
    return {"success": True, "message": "Cliente eliminado"}

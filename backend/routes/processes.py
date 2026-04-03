"""
====================================================================
ROTAS DE GESTÃO DE PROCESSOS - CREDITOIMO
====================================================================
Endpoints REST para gestão de processos de crédito habitação
e transações imobiliárias.

A lógica de negócio está separada em serviços:
- services/process_service.py - Lógica principal
- services/process_assignment.py - Atribuições
- services/process_kanban.py - Kanban

WORKFLOW DE 14 FASES:
1. Clientes em Espera → 14. Desistências

Autor: PowerCell Development Team
====================================================================
"""
import uuid
import logging
import re
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query

from database import db
from models.auth import UserRole
from models.process import (
    ProcessType, ProcessCreate, ProcessUpdate, ProcessResponse
)
from services.auth import get_current_user, require_roles, require_staff
from fastapi import Request
from services.notification_service import (
    send_notification_with_preference_check,
    send_status_change_notification,
    send_new_process_notification,
    send_to_admins
)
from services.history import log_history, log_data_changes
from services.audit_trail_service import log_audit_event
from services.alerts import (
    get_process_alerts,
    check_property_documents,
    create_deed_reminder,
    notify_pre_approval_countdown,
    notify_cpcv_or_deed_document_check
)
from services.realtime_notifications import notify_process_status_change
from services.trello import trello_service, status_to_trello_list, build_card_description

# Importar serviços refatorados
from services.process_service import (
    get_next_process_number,
    can_view_process,
    build_query_filter,
    create_process_document,
    update_process_document,
    get_process_by_id,
    get_processes_for_user,
    get_user_name,
    encrypt_sensitive_data,
    decrypt_sensitive_data,
    decrypt_processes_list
)
from services.process_assignment import (
    assign_both_to_process,
    assign_self_to_process,
    unassign_self_from_process,
    get_users_for_assignment
)
from services.process_kanban import (
    get_kanban_response,
    move_process as move_process_kanban_service,
    KANBAN_COLUMNS,
    is_valid_status
)
from utils.input_sanitization import (
    sanitize_email, sanitize_name, sanitize_phone, sanitize_nif,
    sanitize_string, sanitize_url, log_sanitization_rejection
)

logger = logging.getLogger(__name__)


def _sanitize_dict_names(d: dict):
    """Sanitiza campos de nome/email/telefone num dicionário genérico (vendedor, mediador, etc.)."""
    name_fields = ["nome", "name", "nome_completo", "full_name"]
    email_fields = ["email", "e_mail"]
    phone_fields = ["telefone", "phone", "telemovel", "mobile"]
    url_fields = ["url", "website", "link"]
    for key in list(d.keys()):
        if key in name_fields and d[key] is not None:
            d[key] = sanitize_name(str(d[key]))
        elif key in email_fields and d[key] is not None:
            d[key] = sanitize_email(str(d[key]))
        elif key in phone_fields and d[key] is not None:
            d[key] = sanitize_phone(str(d[key]))
        elif key in url_fields and d[key] is not None:
            d[key] = sanitize_url(str(d[key]))
        elif isinstance(d[key], str) and d[key]:
            d[key] = sanitize_string(d[key], max_length=500)


def create_accent_insensitive_regex(search_term: str) -> dict:
    """
    Cria um regex MongoDB que ignora acentos.
    
    Exemplo: pesquisar 'jose' encontra 'José', 'JOSE', 'josé', 'JÓSÉ'
    """
    if not search_term:
        return {"$regex": "", "$options": "i"}
    
    # Mapeamento de caracteres base para todas as suas variantes acentuadas
    accent_map = {
        'a': '[aàáâãäåAÀÁÂÃÄÅ]',
        'e': '[eèéêëEÈÉÊË]',
        'i': '[iìíîïIÌÍÎÏ]',
        'o': '[oòóôõöOÒÓÔÕÖ]',
        'u': '[uùúûüUÙÚÛÜ]',
        'c': '[cçCÇ]',
        'n': '[nñNÑ]',
        'y': '[yýÿYÝŸ]',
    }
    
    # Construir padrão regex caractere a caractere
    pattern_parts = []
    for char in search_term.lower():
        if char in accent_map:
            pattern_parts.append(accent_map[char])
        elif char.isalpha():
            pattern_parts.append(f'[{char}{char.upper()}]')
        elif char.isalnum():
            pattern_parts.append(char)
        else:
            pattern_parts.append(re.escape(char))
    
    pattern = ''.join(pattern_parts)
    return {"$regex": pattern, "$options": ""}


async def sync_process_to_trello(process: dict):
    """Sincronizar processo com o Trello (nome e descrição do card)."""
    if not process.get("trello_card_id") or not trello_service.api_key:
        return False
    
    try:
        description = build_card_description(process)
        await trello_service.update_card(
            process["trello_card_id"],
            name=process.get("client_name", "Sem nome"),
            desc=description
        )
        logger.info(f"Card {process['trello_card_id']} atualizado no Trello: {process.get('client_name')}")
        return True
    except Exception as e:
        logger.error(f"Erro ao sincronizar com Trello: {e}")
        return False


# ====================================================================
# CONFIGURAÇÃO DO ROUTER
# ====================================================================
router = APIRouter(prefix="/processes", tags=["Processes"])


# ====================================================================
# ENDPOINTS DE CRIAÇÃO
# ====================================================================

@router.post("", response_model=ProcessResponse)
async def create_process(data: ProcessCreate, user: dict = Depends(get_current_user)):
    """
    Criar um novo processo.
    
    Este endpoint é utilizado quando um cliente autenticado
    submete um novo pedido de crédito/imobiliário.
    
    NOTA: Para registos públicos (sem autenticação),
    utilize o endpoint /api/public/register
    
    Args:
        data: Dados do processo (tipo, dados pessoais, financeiros)
        user: Utilizador autenticado (deve ser cliente)
    
    Returns:
        ProcessResponse: Processo criado
    
    Raises:
        HTTPException 403: Se não for cliente
    """
    # Apenas clientes podem criar processos por este endpoint
    if user["role"] != UserRole.CLIENTE:
        raise HTTPException(status_code=403, detail="Apenas clientes podem criar processos")
    
    # Obter o primeiro estado do workflow (Clientes em Espera)
    first_status = await db.workflow_statuses.find_one({}, {"_id": 0}, sort=[("order", 1)])
    initial_status = first_status["name"] if first_status else "clientes_espera"
    
    # Gerar ID único, número sequencial e timestamp
    process_id = str(uuid.uuid4())
    process_number = await get_next_process_number()
    now = datetime.now(timezone.utc).isoformat()
    
    # Processar personal_data e garantir que email está incluído
    personal_data = data.personal_data.model_dump() if data.personal_data else {}
    if user.get("email") and not personal_data.get("email"):
        personal_data["email"] = sanitize_email(user["email"])
    if user.get("name") and not personal_data.get("nome"):
        personal_data["nome"] = sanitize_name(user["name"])
    if user.get("phone") and not personal_data.get("telefone"):
        sanitized_phone = sanitize_phone(user.get("phone"))
        if sanitized_phone:
            personal_data["telefone"] = sanitized_phone
    
    # Construir documento do processo
    sanitized_client_name = sanitize_name(user["name"])
    sanitized_client_email = sanitize_email(user["email"])
    process_doc = {
        "id": process_id,
        "process_number": process_number,
        "client_id": user["id"],
        "client_name": sanitized_client_name,
        "client_email": sanitized_client_email,
        "process_type": data.process_type,
        "status": initial_status,
        "is_active": True,  # Novos processos são ativos por defeito
        "personal_data": personal_data,
        "financial_data": data.financial_data.model_dump() if data.financial_data else None,
        "real_estate_data": None,
        "credit_data": None,
        "assigned_consultor_id": None,
        "assigned_mediador_id": None,
        "created_at": now,
        "updated_at": now
    }
    
    # Encriptar campos sensíveis antes de guardar
    process_doc = encrypt_sensitive_data(process_doc)
    
    # Inserir na base de dados
    await db.processes.insert_one(process_doc)
    
    # Registar no histórico
    await log_history(process_id, user, "Criou processo")
    
    # Notificar administradores e CEO (com verificação de preferências)
    await send_to_admins(
        "Novo Processo Criado",
        f"O cliente {user['name']} criou um novo processo de {data.process_type}.",
        notification_type="new_process"
    )
    
    # Desencriptar para a resposta
    response_doc = decrypt_sensitive_data(process_doc)
    return ProcessResponse(**{k: v for k, v in response_doc.items() if k != "_id"})


@router.post("/create-client", response_model=ProcessResponse)
async def create_client_process(data: ProcessCreate, user: dict = Depends(get_current_user)):
    """
    Criar um novo processo/cliente.
    
    Este endpoint permite que Intermediários de Crédito criem 
    processos para os seus clientes. O processo é automaticamente
    atribuído ao intermediário que o criou.
    
    RELAÇÃO CLIENTE-PROCESSO (N:M):
    - Um cliente pode ter vários processos
    - Um processo pode ter vários clientes (titulares)
    - Se o cliente já existir (por NIF ou email), usa o existente
    - Se não existir, cria um novo cliente
    
    Permissões:
    - Admin, CEO, Consultor, Intermediário: Podem criar
    
    Args:
        data: Dados do processo
        user: Utilizador autenticado
    
    Returns:
        ProcessResponse: Processo criado
    """
    allowed_roles = [UserRole.ADMIN, UserRole.CEO, UserRole.CONSULTOR, UserRole.INTERMEDIARIO, UserRole.MEDIADOR, UserRole.ADMINISTRATIVO, UserRole.DIRETOR]
    
    if user["role"] not in allowed_roles:
        raise HTTPException(
            status_code=403, 
            detail="Não tem permissão para criar clientes/processos."
        )
    
    # Obter o primeiro estado do workflow
    first_status = await db.workflow_statuses.find_one({}, {"_id": 0}, sort=[("order", 1)])
    initial_status = first_status["name"] if first_status else "clientes_espera"
    
    # Gerar ID único e número sequencial
    process_id = str(uuid.uuid4())
    process_number = await get_next_process_number()
    now = datetime.now(timezone.utc).isoformat()
    
    # Extrair nome e email dos dados pessoais - garantir que o nome é sempre preenchido
    personal = data.personal_data.model_dump() if data.personal_data else {}
    # Tentar várias fontes para o nome do cliente
    raw_client_name = (
        personal.get("nome_completo") or 
        personal.get("nome") or 
        data.client_name or 
        personal.get("name") or
        None  # Se não houver nome, vamos extrair do email
    )
    # Se ainda não temos nome, extrair do email (parte antes do @)
    client_email = sanitize_email(personal.get("email") or data.client_email or "")
    client_name = None
    if raw_client_name:
        client_name = sanitize_name(raw_client_name)
    if not client_name and client_email:
        # Extrair nome do email: "joao.silva@example.com" -> "Joao Silva"
        email_name = client_email.split("@")[0]
        # Converter separadores comuns em espaços e capitalizar
        client_name = email_name.replace(".", " ").replace("_", " ").replace("-", " ").title()
    elif not client_name:
        # Último recurso: usar "Cliente" com timestamp para evitar duplicados
        client_name = f"Cliente {datetime.now().strftime('%Y%m%d%H%M%S')}"
    
    raw_phone = personal.get("telefone") or personal.get("phone") or ""
    client_phone = sanitize_phone(raw_phone)
    raw_nif = personal.get("nif")
    client_nif = sanitize_nif(raw_nif)
    
    # ============================================================
    # VERIFICAR/CRIAR CLIENTE NA TABELA CLIENTS
    # ============================================================
    existing_client = None
    client_id = None
    
    # Procurar cliente existente por NIF ou email
    if client_nif or client_email:
        query = []
        if client_nif:
            query.append({"dados_pessoais.nif": client_nif})
        if client_email:
            query.append({"contacto.email": client_email.lower()})
        
        existing_client = await db.clients.find_one({"$or": query})
    
    if existing_client:
        # Cliente já existe - usar o ID existente
        client_id = existing_client["id"]
        logger.info(f"Cliente existente encontrado: {client_id} - {existing_client.get('nome')}")
    else:
        # Criar novo cliente
        from models.client import Client, ClientContact, ClientPersonalData
        
        client_id = str(uuid.uuid4())
        new_client = {
            "id": client_id,
            "nome": client_name,
            "contacto": {
                "email": client_email.lower() if client_email else None,
                "telefone": client_phone
            },
            "dados_pessoais": {
                "nif": client_nif,
                "nome_completo": sanitize_name(client_name),
                **{k: v for k, v in personal.items() if k not in ["nif", "email", "telefone", "phone"]}
            },
            "process_ids": [],  # Será atualizado após criar o processo
            "fonte": "staff_created",
            "created_at": now,
            "updated_at": now,
            "created_by": user.get("email")
        }
        
        await db.clients.insert_one(new_client)
        logger.info(f"Novo cliente criado: {client_id} - {client_name}")
    
    # ============================================================
    # CONSTRUIR DOCUMENTO DO PROCESSO
    # ============================================================
    process_doc = {
        "id": process_id,
        "process_number": process_number,
        # Suporte a múltiplos clientes (N:M)
        "client_ids": [client_id] if client_id else [],
        "client_id": client_id,  # Mantém compatibilidade
        "client_name": client_name,
        "client_email": client_email,
        "client_phone": client_phone,
        "client_nif": client_nif,
        "process_type": data.process_type,
        "status": initial_status,
        "is_active": True,  # Novos processos são ativos por defeito
        "personal_data": personal,
        "financial_data": data.financial_data.model_dump() if data.financial_data else None,
        "real_estate_data": None,
        "credit_data": None,
        "created_at": now,
        "updated_at": now,
        "source": "staff_created"
    }
    
    # Atribuir automaticamente ao criador baseado no seu papel
    if user["role"] in [UserRole.INTERMEDIARIO, UserRole.MEDIADOR]:
        process_doc["assigned_mediador_id"] = user["id"]
        process_doc["mediador_name"] = user["name"]
    elif user["role"] in [UserRole.CONSULTOR, UserRole.DIRETOR]:
        process_doc["assigned_consultor_id"] = user["id"]
        process_doc["consultor_name"] = user["name"]
    
    # Encriptar campos sensíveis antes de guardar
    process_doc = encrypt_sensitive_data(process_doc)
    
    # Inserir na base de dados
    await db.processes.insert_one(process_doc)
    
    # Atualizar process_ids do cliente
    if client_id:
        await db.clients.update_one(
            {"id": client_id},
            {
                "$addToSet": {"process_ids": process_id},
                "$set": {"updated_at": now}
            }
        )
    
    # Registar no histórico
    await log_history(process_id, user, f"Criou processo para cliente {client_name}")
    
    # Sincronizar com Trello (criar cartão)
    try:
        await sync_process_to_trello(process_doc)
    except Exception as e:
        logger.warning(f"Erro ao sincronizar com Trello: {e}")
    
    # Desencriptar para a resposta
    response_doc = decrypt_sensitive_data(process_doc)
    return ProcessResponse(**{k: v for k, v in response_doc.items() if k != "_id"})


# ====================================================================
# ENDPOINTS DE LISTAGEM
# ====================================================================

@router.get("", response_model=List[ProcessResponse])
async def get_processes(user: dict = Depends(get_current_user)):
    """
    Listar processos com base no papel do utilizador.
    
    FILTRAGEM AUTOMÁTICA:
    - Admin/CEO: Todos os processos
    - Cliente: Apenas os próprios processos
    - Consultor: Processos atribuídos como consultor
    - Intermediário: Processos atribuídos como intermediário
    - Misto: Ambos os tipos de atribuição
    
    Returns:
        Lista de ProcessResponse
    """
    role = user["role"]
    query = {}

    # Construir query baseada no papel
    if role == UserRole.CLIENTE:
        query["client_id"] = user["id"]
    elif role in [UserRole.ADMIN, UserRole.CEO, UserRole.ADMINISTRATIVO, UserRole.DIRETOR]:
        # Admin, CEO, Administrativo e Diretor vêem todos os processos
        pass
    elif role == UserRole.INDEXACAO:
        # Indexação vê APENAS os processos que lhe estão atribuídos
        query["assigned_indexacao_id"] = user["id"]
    elif role == UserRole.CONSULTOR:
        # Suporte a múltiplos consultores: verificar no array ou campo único
        query["$or"] = [
            {"assigned_consultor_ids": user["id"]},
            {"assigned_consultor_id": user["id"]}
        ]
    elif role in [UserRole.MEDIADOR, UserRole.INTERMEDIARIO]:
        # Suporte a múltiplos intermediários: verificar no array ou campo único
        query["$or"] = [
            {"assigned_mediador_ids": user["id"]},
            {"assigned_mediador_id": user["id"]}
        ]

    processes = await db.processes.find(query, {"_id": 0}).sort("client_name", 1).to_list(1000)
    # Desencriptar dados sensíveis
    processes = decrypt_processes_list(processes)
    return [ProcessResponse(**p) for p in processes]


@router.get("/paginated")
async def get_processes_paginated(
    limit: int = Query(20, ge=1, le=100),
    cursor: Optional[str] = None,
    sort_field: str = Query("client_name", description="Campo de ordenação"),
    sort_order: str = Query("asc", description="Ordem: asc ou desc"),
    status: Optional[str] = None,
    search: Optional[str] = None,
    user: dict = Depends(get_current_user)
):
    """
    Listar processos com paginação cursor-based (mais eficiente para grandes datasets).
    
    Args:
        limit: Número de processos por página (máximo 100)
        cursor: Cursor da página anterior
        sort_field: Campo de ordenação (created_at, updated_at, client_name)
        sort_order: Direção (asc ou desc)
        status: Filtrar por status
        search: Pesquisar por nome/email
    
    Returns:
        {processes, next_cursor, has_more}
    """
    from services.cursor_pagination import CursorPaginator

    role = user["role"]
    query = {}

    # Construir query baseada no papel
    if role == UserRole.CLIENTE:
        query["client_id"] = user["id"]
    elif role in [UserRole.ADMIN, UserRole.CEO, UserRole.ADMINISTRATIVO, UserRole.DIRETOR]:
        # Admin, CEO, Administrativo e Diretor vêem todos os processos
        pass
    elif role == UserRole.INDEXACAO:
        # Indexação vê APENAS os processos que lhe estão atribuídos
        query["assigned_indexacao_id"] = user["id"]
    elif role == UserRole.CONSULTOR:
        # Suporte a múltiplos consultores
        query["$or"] = [
            {"assigned_consultor_ids": user["id"]},
            {"assigned_consultor_id": user["id"]}
        ]
    elif role in [UserRole.MEDIADOR, UserRole.INTERMEDIARIO]:
        # Suporte a múltiplos intermediários
        query["$or"] = [
            {"assigned_mediador_ids": user["id"]},
            {"assigned_mediador_id": user["id"]}
        ]

    # Adicionar filtros opcionais
    if status:
        query["status"] = status
    
    if search:
        name_regex = create_accent_insensitive_regex(search)
        simple_regex = {"$regex": re.escape(search), "$options": "i"}
        search_condition = {
            "$or": [
                {"client_name": name_regex},
                {"client_email": simple_regex}
            ]
        }
        if "$and" not in query:
            query = {"$and": [query, search_condition]} if query else search_condition
        else:
            query["$and"].append(search_condition)
    
    # Converter sort_order para int
    order = -1 if sort_order.lower() == "desc" else 1
    
    # Usar paginador
    paginator = CursorPaginator(
        collection=db.processes,
        default_limit=20,
        max_limit=100,
        default_sort_field="client_name",
        default_sort_order=1  # Ordem ascendente (A-Z)
    )
    
    result = await paginator.paginate(
        query=query,
        limit=limit,
        cursor=cursor,
        sort_field=sort_field,
        sort_order=order
    )
    
    # Desencriptar dados sensíveis
    result["items"] = decrypt_processes_list(result["items"])
    
    return {
        "processes": result["items"],
        "next_cursor": result["next_cursor"],
        "has_more": result["has_more"],
        "limit": result["limit"]
    }


@router.get("/kanban")
async def get_kanban_board(
    consultor_id: Optional[str] = None,
    mediador_id: Optional[str] = None,
    user: dict = Depends(require_staff())
):
    """
    Get processes organized by status for Kanban board.
    Admin/CEO see all, others see only their assigned processes.
    Supports filtering by consultor_id and mediador_id.
    Supports multiple consultants and intermediaries per process.
    """
    role = user["role"]
    user_id = user["id"]
    query = {}
    
    # Filter by role (base visibility) - suporte a múltiplos
    if role == UserRole.CONSULTOR:
        query["$or"] = [
            {"assigned_consultor_ids": user_id},
            {"assigned_consultor_id": user_id}
        ]
    elif role in [UserRole.MEDIADOR, UserRole.INTERMEDIARIO]:
        query["$or"] = [
            {"assigned_mediador_ids": user_id},
            {"assigned_mediador_id": user_id}
        ]
    elif role == UserRole.INDEXACAO:
        # Indexação vê APENAS os processos que lhe estão atribuídos
        query["assigned_indexacao_id"] = user["id"]
    # Admin, CEO, Administrativo e Diretor see all (no base filter)

    # Apply additional filters (only for roles that can see all)
    if role in [UserRole.ADMIN, UserRole.CEO, UserRole.ADMINISTRATIVO, UserRole.DIRETOR]:
        if consultor_id:
            if consultor_id == "none":
                # Sem consultor atribuído
                query["$and"] = query.get("$and", [])
                query["$and"].append({
                    "$or": [
                        {"assigned_consultor_ids": {"$in": [None, [], ""]}},
                        {"assigned_consultor_ids": {"$exists": False}},
                        {"assigned_consultor_id": None},
                        {"assigned_consultor_id": ""},
                        {"assigned_consultor_id": {"$exists": False}}
                    ]
                })
            else:
                # Filtro por consultor específico - verificar no array ou campo único
                query["$or"] = [
                    {"assigned_consultor_ids": consultor_id},
                    {"assigned_consultor_id": consultor_id}
                ]
        
        if mediador_id:
            if mediador_id == "none":
                # Sem mediador atribuído
                if "$and" not in query:
                    query["$and"] = []
                query["$and"].append({
                    "$or": [
                        {"assigned_mediador_ids": {"$in": [None, [], ""]}},
                        {"assigned_mediador_ids": {"$exists": False}},
                        {"assigned_mediador_id": None},
                        {"assigned_mediador_id": ""},
                        {"assigned_mediador_id": {"$exists": False}}
                    ]
                })
            else:
                # Filtro por mediador específico - verificar no array ou campo único
                if "$or" in query and "assigned_consultor" in str(query["$or"]):
                    # Já tem filtro de consultor, combinar com AND
                    query = {
                        "$and": [
                            query,
                            {"$or": [
                                {"assigned_mediador_ids": mediador_id},
                                {"assigned_mediador_id": mediador_id}
                            ]}
                        ]
                    }
                else:
                    query["$or"] = [
                        {"assigned_mediador_ids": mediador_id},
                        {"assigned_mediador_id": mediador_id}
                    ]
    
    # Get all workflow statuses ordered
    statuses = await db.workflow_statuses.find({}, {"_id": 0}).sort("order", 1).to_list(100)
    
    # Get processes
    processes = await db.processes.find(query, {"_id": 0}).to_list(1000)
    
    # Desencriptar dados sensíveis
    processes = decrypt_processes_list(processes)
    
    # Get all users for name lookup
    users = await db.users.find({}, {"_id": 0, "id": 1, "name": 1, "role": 1}).to_list(1000)
    user_map = {u["id"]: u for u in users}
    
    # Organize by status
    kanban = []
    for status in statuses:
        status_processes = [p for p in processes if p.get("status") == status["name"]]
        
        # Enrich with user names and assignment info
        enriched_processes = []
        for p in status_processes:
            consultor = user_map.get(p.get("assigned_consultor_id"), {})
            mediador = user_map.get(p.get("assigned_mediador_id"), {})
            
            # Verificar se o utilizador actual está atribuído
            is_my_consultor = p.get("assigned_consultor_id") == user_id
            is_my_mediador = p.get("assigned_mediador_id") == user_id
            
            enriched_processes.append({
                **p,
                "consultor_name": consultor.get("name", ""),
                "mediador_name": mediador.get("name", ""),
                "is_assigned_to_me": is_my_consultor or is_my_mediador,
                "my_role_in_process": "consultor" if is_my_consultor else ("mediador" if is_my_mediador else None)
            })
        
        kanban.append({
            "id": status["id"],
            "name": status["name"],
            "label": status["label"],
            "color": status["color"],
            "order": status["order"],
            "processes": enriched_processes,
            "count": len(enriched_processes)
        })
    
    # Excluir processos concluídos e desistências da contagem total
    active_processes = [p for p in processes if p.get("status") not in ["concluidos", "desistencias"]]
    inactive_processes = [p for p in processes if p.get("status") in ["concluidos", "desistencias"]]

    return {
        "columns": kanban,
        "total_processes": len(active_processes),
        "total_inactive": len(inactive_processes),
        "user_role": role,
        "current_user_id": user_id
    }


@router.get("/my-clients")
async def get_my_clients(user: dict = Depends(require_roles([
    UserRole.CONSULTOR, UserRole.MEDIADOR, UserRole.INTERMEDIARIO, 
    UserRole.ADMIN, UserRole.CEO, UserRole.DIRETOR, UserRole.ADMINISTRATIVO,
    UserRole.INDEXACAO
]))):
    """
    Obter lista de clientes atribuídos ao utilizador atual.
    
    Retorna uma lista com:
    - Nome do cliente
    - Fase do processo
    - Ações pendentes (tarefas, documentos a atualizar)
    
    Permissões:
    - Consultor: Apenas os seus clientes (assigned_consultor_ids ou assigned_consultor_id)
    - Intermediário/Mediador: Apenas os seus clientes (assigned_mediador_ids ou criados por eles)
    - Admin/CEO: Todos os clientes (para supervisão)
    
    Suporta múltiplos consultores e intermediários por processo.
    """
    user_id = user["id"]
    user_email = user.get("email", "")
    role = user["role"]
    
    # Construir query baseada no papel do utilizador
    if role == UserRole.CONSULTOR:
        # Suporte a múltiplos consultores
        query = {
            "$or": [
                {"assigned_consultor_ids": user_id},
                {"assigned_consultor_id": user_id}
            ]
        }
    elif role in [UserRole.MEDIADOR, UserRole.INTERMEDIARIO]:
        # Intermediários vêem processos atribuídos a eles OU criados por eles
        query = {
            "$or": [
                {"assigned_mediador_ids": user_id},
                {"assigned_mediador_id": user_id},
                {"created_by": user_email}
            ]
        }
    elif role == UserRole.INDEXACAO:
        # Indexação vê APENAS os processos que lhe estão atribuídos
        query = {"assigned_indexacao_id": user["id"]}
    else:
        # Admin/CEO/Diretor/Administrativo vêem todos
        query = {}
    
    # Buscar processos com campos necessários
    processes = await db.processes.find(
        query,
        {
            "_id": 0, 
            "id": 1, 
            "process_number": 1,
            "client_name": 1, 
            "client_email": 1,
            "client_phone": 1,
            "status": 1, 
            "process_type": 1,
            "assigned_consultor_id": 1,
            "assigned_mediador_id": 1,
            "created_at": 1,
            "updated_at": 1,
            "deed_date": 1,
            "property_id": 1
        }
    ).sort("client_name", 1).to_list(500)
    
    # Obter labels das fases do workflow ordenadas
    statuses = await db.workflow_statuses.find({}, {"_id": 0}).sort("order", 1).to_list(100)
    status_map = {s["name"]: s for s in statuses}
    
    # Ordenar processos por fase (order do status) e depois por nome
    def get_sort_key(p):
        status_info = status_map.get(p.get("status"), {})
        phase_order = status_info.get("order", 999)
        client_name = p.get("client_name", "").lower()
        return (phase_order, client_name)
    
    processes = sorted(processes, key=get_sort_key)
    
    # Obter tarefas pendentes por processo
    process_ids = [p["id"] for p in processes]
    tasks = await db.tasks.find(
        {
            "process_id": {"$in": process_ids},
            "completed": {"$ne": True}
        },
        {"_id": 0, "id": 1, "process_id": 1, "title": 1, "priority": 1, "due_date": 1}
    ).to_list(1000)
    
    # Agrupar tarefas por processo
    tasks_by_process = {}
    for task in tasks:
        pid = task["process_id"]
        if pid not in tasks_by_process:
            tasks_by_process[pid] = []
        tasks_by_process[pid].append(task)
    
    # Buscar nomes dos consultores
    consultor_ids = list(set(p.get("assigned_consultor_id") for p in processes if p.get("assigned_consultor_id")))
    consultores = await db.users.find(
        {"id": {"$in": consultor_ids}},
        {"_id": 0, "id": 1, "name": 1}
    ).to_list(100)
    consultor_map = {c["id"]: c["name"] for c in consultores}
    
    # Construir lista de clientes com informações enriquecidas
    clients_list = []
    for p in processes:
        status_info = status_map.get(p.get("status"), {})
        pending_tasks = tasks_by_process.get(p["id"], [])
        
        # Determinar ações pendentes
        pending_actions = []
        
        # Adicionar tarefas pendentes
        for task in pending_tasks[:3]:  # Limitar a 3 tarefas
            pending_actions.append({
                "type": "task",
                "title": task.get("title", "Tarefa"),
                "priority": task.get("priority", "normal"),
                "due_date": task.get("due_date")
            })
        
        # Verificar se há mais tarefas
        if len(pending_tasks) > 3:
            pending_actions.append({
                "type": "info",
                "title": f"+{len(pending_tasks) - 3} tarefas adicionais",
                "priority": "normal"
            })
        
        # Verificar documentos em falta baseado na fase
        fase = p.get("status", "")
        if fase in ["fase_documental", "fase_documental_ii"]:
            pending_actions.append({
                "type": "document",
                "title": "Verificar documentos em falta",
                "priority": "high"
            })
        
        clients_list.append({
            "id": p["id"],
            "process_number": p.get("process_number"),
            "client_name": p.get("client_name", "Sem nome"),
            "client_email": p.get("client_email"),
            "client_phone": p.get("client_phone"),
            "status": p.get("status"),
            "status_label": status_info.get("label", p.get("status", "Desconhecido")),
            "status_color": status_info.get("color", "#6B7280"),
            "process_type": p.get("process_type"),
            "consultor_name": consultor_map.get(p.get("assigned_consultor_id"), ""),
            "pending_actions": pending_actions,
            "pending_count": len(pending_tasks),
            "created_at": p.get("created_at"),
            "updated_at": p.get("updated_at"),
            "deed_date": p.get("deed_date"),
            "has_property": bool(p.get("property_id"))
        })
    
    return {
        "clients": clients_list,
        "total": len(clients_list),
        "user_id": user_id,
        "user_role": role
    }


@router.put("/kanban/{process_id}/move")
async def move_process_kanban(
    process_id: str,
    new_status: str = Query(..., description="New status name"),
    deed_date: Optional[str] = Query(None, description="Data da escritura (YYYY-MM-DD)"),
    user: dict = Depends(require_staff())
):
    """
    Move a process to a different status column in Kanban.
    
    ALERTAS AUTOMÁTICOS:
    - Ao mover para "ch_aprovado": Inicia countdown de 90 dias, verifica docs do imóvel
    - Ao mover para "escritura_agendada": Cria lembrete 15 dias antes
    """
    process = await db.processes.find_one({"id": process_id}, {"_id": 0})
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")
    
    # Check permission
    if not can_view_process(user, process):
        raise HTTPException(status_code=403, detail="Sem permissão para mover este processo")
    
    # Validate new status
    status_exists = await db.workflow_statuses.find_one({"name": new_status})
    if not status_exists:
        raise HTTPException(status_code=400, detail="Estado inválido")
    
    old_status = process.get("status", "")
    alerts_generated = []
    
    # Determinar se o processo deve estar ativo ou inativo
    # Processos em Desistências ou Concluídos são marcados como inativos
    inactive_statuses = ["desistencias", "concluidos"]
    is_active = new_status not in inactive_statuses
    
    # Update process
    await db.processes.update_one(
        {"id": process_id},
        {"$set": {
            "status": new_status, 
            "is_active": is_active,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }}
    )
    
    # Log history
    await log_history(process_id, user, "Moveu processo", "status", old_status, new_status)
    
    # === ALERTAS AUTOMÁTICOS BASEADOS NA MUDANÇA DE ESTADO ===
    
    # 1. Ao mover para CH Aprovado - Verificar documentos do imóvel
    if new_status in ["ch_aprovado", "fase_escritura"]:
        property_check = await check_property_documents(process)
        if property_check.get("active"):
            alerts_generated.append({
                "type": "property_docs",
                "message": property_check.get("message"),
                "details": property_check.get("details")
            })
    
    # 1.1 Alerta de verificação de documentos para CPCV/Escritura
    if new_status in ["ch_aprovado", "fase_escritura", "escritura_agendada"]:
        await notify_cpcv_or_deed_document_check(process, new_status)
        alerts_generated.append({
            "type": "document_verification_alert",
            "message": "Alerta enviado aos envolvidos para verificação de documentos"
        })
    
    # 2. Ao mover para pré-aprovação - Iniciar countdown de 90 dias
    if new_status == "fase_bancaria" and old_status != "fase_bancaria":
        # Guardar data de aprovação se ainda não existir
        if not process.get("credit_data", {}).get("bank_approval_date"):
            await db.processes.update_one(
                {"id": process_id},
                {"$set": {"credit_data.bank_approval_date": datetime.now().strftime("%Y-%m-%d")}}
            )
        # Notificar sobre o countdown
        updated_process = await db.processes.find_one({"id": process_id}, {"_id": 0})
        await notify_pre_approval_countdown(updated_process)
        alerts_generated.append({
            "type": "countdown_started",
            "message": "Countdown de 90 dias iniciado para pré-aprovação"
        })
    
    # 3. Ao mover para escritura agendada - Criar lembrete 15 dias antes
    if new_status == "escritura_agendada":
        if deed_date:
            deadline_id = await create_deed_reminder(process, deed_date, user)
            if deadline_id:
                alerts_generated.append({
                    "type": "deed_reminder",
                    "message": f"Lembrete de escritura criado para 15 dias antes de {deed_date}"
                })
        else:
            alerts_generated.append({
                "type": "deed_date_needed",
                "message": "Escritura agendada sem data. Defina a data para criar lembrete automático."
            })
    
    # Send email notification if client has email (com verificação de preferências)
    if process.get("client_email"):
        status_doc = await db.workflow_statuses.find_one({"name": new_status}, {"_id": 0})
        status_label = status_doc.get("label", new_status) if status_doc else new_status
        await send_notification_with_preference_check(
            process["client_email"],
            "Atualização do seu processo",
            f"O estado do seu processo foi atualizado para: {status_label}",
            notification_type="status_change"
        )
    
    # === CRIAR NOTIFICAÇÃO NA BASE DE DADOS ===
    status_doc = await db.workflow_statuses.find_one({"name": new_status}, {"_id": 0})
    status_label = status_doc.get("label", new_status) if status_doc else new_status
    
    await notify_process_status_change(
        process=process,
        old_status=old_status,
        new_status=new_status,
        new_status_label=status_label,
        changed_by=user
    )
    
    # === SINCRONIZAR COM TRELLO ===
    if process.get("trello_card_id") and trello_service.api_key:
        try:
            trello_list_name = status_to_trello_list(new_status)
            if trello_list_name:
                # Encontrar a lista do Trello pelo nome
                trello_list = await trello_service.get_list_by_name(trello_list_name)
                if trello_list:
                    await trello_service.move_card(process["trello_card_id"], trello_list["id"])
                    logger.info(f"Card {process['trello_card_id']} movido para {trello_list_name} no Trello")
        except Exception as e:
            logger.error(f"Erro ao sincronizar com Trello: {e}")
            # Não falhar a operação por erro no Trello
    
    return {
        "message": "Processo movido com sucesso", 
        "new_status": new_status,
        "alerts": alerts_generated
    }


# ==== DSTI AUTOMÁTICO (antes de /{process_id}) ====

@router.get("/dsti/{process_id}")
async def get_process_dsti(
    process_id: str,
    user: dict = Depends(get_current_user)
):
    """
    Calcula o DSTI automático de um processo.
    
    Usa dados extraídos pela IA (rendimento_liquido e mapa_responsabilidades)
    para calcular automaticamente a taxa de esforço e sinalizar risco.
    
    Retorna:
    - dsti_pct: DSTI em percentagem
    - effort_rate_pct: Taxa de esforço global
    - risk_level: baixo, moderado, elevado, critico, sem_dados
    - components: breakdown dos valores
    """
    # Verificar se funcionalidade está activada
    from services.system_config import get_system_config
    config = await get_system_config()
    if not config.dsti_analysis.enabled:
        raise HTTPException(status_code=403, detail="Análise DSTI automática desactivada pelo administrador")
    
    process = await db.processes.find_one({"id": process_id}, {"_id": 0})
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")
    
    if not can_view_process(user, process):
        raise HTTPException(status_code=403, detail="Acesso negado")
    
    from services.dsti_service import calculate_dsti, get_risk_label
    
    result = calculate_dsti(process)
    result["process_id"] = process_id
    result["process_number"] = process.get("process_number")
    result["client_name"] = process.get("client_name")
    result["high_risk_threshold"] = config.dsti_analysis.high_risk_threshold
    result["critical_risk_threshold"] = config.dsti_analysis.critical_risk_threshold
    result["risk_label"] = get_risk_label(result["risk_level"])
    
    return result


@router.get("/dsti-alerts")
async def get_dsti_high_risk_processes(
    user: dict = Depends(get_current_user)
):
    """
    Lista processos com DSTI de alto risco.
    
    Retorna todos os processos onde o DSTI ultrapassa o limiar
    configurado pelo administrador (default: 40%).
    """
    from services.system_config import get_system_config
    config = await get_system_config()
    if not config.dsti_analysis.enabled:
        return {"enabled": False, "processes": [], "total": 0}
    
    threshold = config.dsti_analysis.high_risk_threshold
    processes = await db.processes.find(
        {"financial_data.rendimento_bruto_mensal": {"$gt": 0}},
        {"_id": 0, "id": 1, "process_number": 1, "client_name": 1, 
         "financial_data": 1, "personal_data": 1, "status": 1}
    ).to_list(length=500)
    
    from services.dsti_service import calculate_dsti, is_high_risk
    
    high_risk = []
    for proc in processes:
        dsti_result = calculate_dsti(proc)
        if is_high_risk(dsti_result, threshold):
            high_risk.append({
                "process_id": proc.get("id"),
                "process_number": proc.get("process_number"),
                "client_name": proc.get("client_name"),
                "status": proc.get("status"),
                "dsti_pct": dsti_result["dsti_pct"],
                "effort_rate_pct": dsti_result["effort_rate_pct"],
                "risk_level": dsti_result["risk_level"],
                "risk_color": dsti_result["risk_color"],
                "prestacao_creditos": dsti_result["components"]["prestacao_creditos_mensal"],
                "rendimento_bruto": dsti_result["components"]["rendimento_bruto_total"],
            })
    
    # Ordenar por DSTI descendente (mais grave primeiro)
    high_risk.sort(key=lambda x: x["dsti_pct"], reverse=True)
    
    return {
        "enabled": True,
        "threshold": threshold,
        "processes": high_risk,
        "total": len(high_risk),
    }


@router.get("/{process_id}", response_model=ProcessResponse)
async def get_process(process_id: str, user: dict = Depends(get_current_user)):
    process = await db.processes.find_one({"id": process_id}, {"_id": 0})
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")
    
    if not can_view_process(user, process):
        raise HTTPException(status_code=403, detail="Acesso negado")
    
    # Desencriptar dados sensíveis
    process = decrypt_sensitive_data(process)
    
    return ProcessResponse(**process)


@router.get("/{process_id}/alerts")
async def get_process_alerts_endpoint(process_id: str, user: dict = Depends(get_current_user)):
    """
    Obter todos os alertas ativos para um processo.
    
    Retorna alertas de:
    - Idade < 35 anos (Apoio ao Estado)
    - Countdown de 90 dias (pré-aprovação)
    - Documentos a expirar em 15 dias
    - Documentos do imóvel em falta
    """
    process = await db.processes.find_one({"id": process_id}, {"_id": 0})
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")
    
    if not can_view_process(user, process):
        raise HTTPException(status_code=403, detail="Acesso negado")
    
    alerts = await get_process_alerts(process)
    
    return {
        "process_id": process_id,
        "client_name": process.get("client_name"),
        "alerts": alerts,
        "total": len(alerts),
        "has_critical": any(a.get("priority") == "critical" for a in alerts),
        "has_high": any(a.get("priority") == "high" for a in alerts)
    }


@router.put("/{process_id}", response_model=ProcessResponse)
async def update_process(process_id: str, data: ProcessUpdate, request: Request, user: dict = Depends(get_current_user)):
    process = await db.processes.find_one({"id": process_id}, {"_id": 0})
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")
    
    role = user["role"]
    
    # Extrair campos opcionais do body para auditoria (não são parte do modelo ProcessUpdate)
    audit_reason = None
    ai_suggested = False
    try:
        body = await request.json()
        audit_reason = body.get("audit_reason")
        ai_suggested = bool(body.get("ai_suggested", False))
    except Exception:
        pass
    
    # Indexação não pode actualizar dados do processo
    if role == UserRole.INDEXACAO:
        raise HTTPException(status_code=403, detail="Indexação não pode alterar dados do processo. Apenas visualizar e gerir documentos.")
    
    update_data = {"updated_at": datetime.now(timezone.utc).isoformat()}
    
    valid_statuses = [s["name"] for s in await db.workflow_statuses.find({}, {"name": 1, "_id": 0}).to_list(100)]
    
    # Check role-based permissions
    can_update_personal = role in [UserRole.ADMIN, UserRole.CEO, UserRole.CONSULTOR, UserRole.DIRETOR, UserRole.ADMINISTRATIVO]
    can_update_financial = role in [UserRole.ADMIN, UserRole.CEO, UserRole.CONSULTOR, UserRole.MEDIADOR, UserRole.DIRETOR, UserRole.ADMINISTRATIVO]
    can_update_real_estate = UserRole.can_act_as_consultor(role)
    can_update_credit = UserRole.can_act_as_mediador(role)
    can_update_status = role in [UserRole.ADMIN, UserRole.CEO, UserRole.CONSULTOR, UserRole.MEDIADOR, UserRole.DIRETOR, UserRole.ADMINISTRATIVO]
    
    if role == UserRole.CLIENTE:
        if process.get("client_id") != user["id"]:
            raise HTTPException(status_code=403, detail="Acesso negado")
        if data.personal_data:
            await log_data_changes(process_id, user, process.get("personal_data"), data.personal_data.model_dump(), "dados pessoais")
            # Registar no audit trail enriquecido
            await log_audit_event(process_id, user, "Alterou dados pessoais", request=request, source="web", audit_reason=audit_reason, ai_suggested=ai_suggested, ai_approved_by=user.get("id") if ai_suggested else None)
            update_data["personal_data"] = data.personal_data.model_dump()
        if data.financial_data:
            await log_data_changes(process_id, user, process.get("financial_data"), data.financial_data.model_dump(), "dados financeiros")
            await log_audit_event(process_id, user, "Alterou dados financeiros", request=request, source="web", audit_reason=audit_reason, ai_suggested=ai_suggested, ai_approved_by=user.get("id") if ai_suggested else None)
            update_data["financial_data"] = data.financial_data.model_dump()
    else:
        # Staff updates
        if data.personal_data and can_update_personal:
            await log_data_changes(process_id, user, process.get("personal_data"), data.personal_data.model_dump(), "dados pessoais")
            await log_audit_event(process_id, user, "Alterou dados pessoais", request=request, source="web", audit_reason=audit_reason, ai_suggested=ai_suggested, ai_approved_by=user.get("id") if ai_suggested else None)
            update_data["personal_data"] = data.personal_data.model_dump()
            
            # Atualizar client_name se nome_completo ou nome for fornecido
            personal_dict = data.personal_data.model_dump()
            new_name = personal_dict.get("nome_completo") or personal_dict.get("nome")
            if new_name:
                sanitized_name = sanitize_name(new_name)
                if not sanitized_name:
                    raise HTTPException(status_code=400, detail="Nome do cliente inválido após sanitização")
                update_data["client_name"] = sanitized_name
        
        if data.financial_data and can_update_financial:
            await log_data_changes(process_id, user, process.get("financial_data"), data.financial_data.model_dump(), "dados financeiros")
            await log_audit_event(process_id, user, "Alterou dados financeiros", request=request, source="web", audit_reason=audit_reason, ai_suggested=ai_suggested, ai_approved_by=user.get("id") if ai_suggested else None)
            update_data["financial_data"] = data.financial_data.model_dump()
        
        if data.real_estate_data and can_update_real_estate:
            await log_data_changes(process_id, user, process.get("real_estate_data"), data.real_estate_data.model_dump(), "dados imobiliários")
            await log_audit_event(process_id, user, "Alterou dados imobiliários", request=request, source="web", audit_reason=audit_reason, ai_suggested=ai_suggested, ai_approved_by=user.get("id") if ai_suggested else None)
            update_data["real_estate_data"] = data.real_estate_data.model_dump()
        
        if data.credit_data and can_update_credit:
            await log_data_changes(process_id, user, process.get("credit_data"), data.credit_data.model_dump(), "dados de crédito")
            await log_audit_event(process_id, user, "Alterou dados de crédito", request=request, source="web", audit_reason=audit_reason, ai_suggested=ai_suggested, ai_approved_by=user.get("id") if ai_suggested else None)
            update_data["credit_data"] = data.credit_data.model_dump()
        
        # Atualizar email e telefone do cliente
        if data.client_email is not None:
            update_data["client_email"] = sanitize_email(data.client_email)
        if data.client_phone is not None:
            update_data["client_phone"] = sanitize_phone(data.client_phone)
        
        # Campos adicionais do CPCV
        if data.co_buyers is not None:
            update_data["co_buyers"] = data.co_buyers
        if data.co_applicants is not None:
            update_data["co_applicants"] = data.co_applicants
        if data.vendedor is not None:
            _sanitize_dict_names(data.vendedor)
            update_data["vendedor"] = data.vendedor
        if data.mediador is not None:
            _sanitize_dict_names(data.mediador)
            update_data["mediador"] = data.mediador
        
        if data.status and can_update_status and (data.status in valid_statuses or not valid_statuses):
            await log_history(process_id, user, "Alterou estado", "status", process["status"], data.status)
            await log_audit_event(process_id, user, "Alterou estado", field="status", old_value=process["status"], new_value=data.status, request=request, source="web", audit_reason=audit_reason, ai_suggested=ai_suggested, ai_approved_by=user.get("id") if ai_suggested else None)
            update_data["status"] = data.status
            
            # Send email notification (com verificação de preferências)
            if process.get("client_email"):
                await send_notification_with_preference_check(
                    process["client_email"],
                    "Estado do Processo Atualizado",
                    f"O estado do seu processo foi atualizado para: {data.status}",
                    notification_type="status_change"
                )
    
    # Encriptar campos sensíveis antes de guardar
    update_data = encrypt_sensitive_data(update_data)
    
    await db.processes.update_one({"id": process_id}, {"$set": update_data})
    updated = await db.processes.find_one({"id": process_id}, {"_id": 0})
    
    # O22 - Executar regras de automação após atualização
    if data.status and can_update_status:
        try:
            from services.workflow_engine import process_trigger
            await process_trigger("process_status_changed", {
                "process_id": process_id,
                "old_status": process.get("status"),
                "new_status": data.status,
                "client_name": process.get("client_name", ""),
            })
        except Exception as e:
            logger.warning(f"Erro ao processar automações: {e}")
    
    # Desencriptar dados para a resposta
    updated = decrypt_sensitive_data(updated)
    
    # Sincronizar com Trello (nome e descrição do card)
    await sync_process_to_trello(updated)
    
    return ProcessResponse(**updated)


@router.post("/{process_id}/assign")
async def assign_process(
    process_id: str, 
    consultor_ids: Optional[str] = None,  # String separada por vírgulas ou ID único
    mediador_ids: Optional[str] = None,   # String separada por vírgulas ou ID único
    indexacao_id: Optional[str] = None,
    # Parâmetros de compatibilidade (deprecated)
    consultor_id: Optional[str] = None,
    mediador_id: Optional[str] = None,
    user: dict = Depends(require_staff())
):
    """
    Atribuir consultores, intermediários e/ou utilizador de indexação a um processo.
    
    Suporta múltiplos consultores e intermediários:
    - consultor_ids: String com IDs separados por vírgula (ex: "id1,id2,id3")
    - mediador_ids: String com IDs separados por vírgula (ex: "id1,id2,id3")
    
    Mantém compatibilidade com os parâmetros antigos (consultor_id, mediador_id).
    Qualquer utilizador staff pode atribuir.
    """
    process = await db.processes.find_one({"id": process_id})
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")
    
    update_data = {"updated_at": datetime.now(timezone.utc).isoformat()}
    
    # Obter listas atuais
    old_consultor_ids = process.get("assigned_consultor_ids") or []
    old_mediador_ids = process.get("assigned_mediador_ids") or []
    old_indexacao = process.get("assigned_indexacao_id")
    
    # Compatibilidade: se consultor_id foi passado, usar como consultor_ids
    if consultor_id and not consultor_ids:
        consultor_ids = consultor_id
    if mediador_id and not mediador_ids:
        mediador_ids = mediador_id
    
    # Processar consultores (suporta múltiplos)
    if consultor_ids is not None:
        if consultor_ids == "" or consultor_ids == "null":
            # Remover todos os consultores
            update_data["assigned_consultor_ids"] = []
            update_data["consultor_names"] = []
            update_data["assigned_consultor_id"] = None
            update_data["consultor_name"] = None
            if old_consultor_ids:
                old_names = []
                for old_id in old_consultor_ids:
                    old_user = await db.users.find_one({"id": old_id}, {"name": 1})
                    if old_user:
                        old_names.append(old_user.get("name", ""))
                await log_history(process_id, user, "Removeu todos os consultores", "assigned_consultor_ids", ", ".join(old_names), None)
        else:
            # Converter para lista
            new_consultor_ids = [id.strip() for id in consultor_ids.split(",") if id.strip()]
            
            # Validar e obter nomes
            consultor_names = []
            for cid in new_consultor_ids:
                consultor = await db.users.find_one({"id": cid})
                if consultor:
                    consultor_names.append(consultor["name"])
            
            if consultor_names:
                update_data["assigned_consultor_ids"] = new_consultor_ids
                update_data["consultor_names"] = consultor_names
                # Compatibilidade
                update_data["assigned_consultor_id"] = new_consultor_ids[0]
                update_data["consultor_name"] = consultor_names[0]
                
                # Log das mudanças
                old_names = []
                for old_id in old_consultor_ids:
                    old_user = await db.users.find_one({"id": old_id}, {"name": 1})
                    if old_user:
                        old_names.append(old_user.get("name", ""))
                
                added = [n for n in consultor_names if n not in old_names]
                removed = [n for n in old_names if n not in consultor_names]
                
                changes = []
                if added:
                    changes.append(f"Adicionou: {', '.join(added)}")
                if removed:
                    changes.append(f"Removeu: {', '.join(removed)}")
                
                if changes:
                    await log_history(process_id, user, "Actualizou consultores", "assigned_consultor_ids", ", ".join(old_names), ", ".join(consultor_names))
    
    # Processar intermediários (suporta múltiplos)
    if mediador_ids is not None:
        if mediador_ids == "" or mediador_ids == "null":
            # Remover todos os intermediários
            update_data["assigned_mediador_ids"] = []
            update_data["mediador_names"] = []
            update_data["assigned_mediador_id"] = None
            update_data["mediador_name"] = None
            if old_mediador_ids:
                old_names = []
                for old_id in old_mediador_ids:
                    old_user = await db.users.find_one({"id": old_id}, {"name": 1})
                    if old_user:
                        old_names.append(old_user.get("name", ""))
                await log_history(process_id, user, "Removeu todos os intermediários", "assigned_mediador_ids", ", ".join(old_names), None)
        else:
            # Converter para lista
            new_mediador_ids = [id.strip() for id in mediador_ids.split(",") if id.strip()]
            
            # Validar e obter nomes
            mediador_names = []
            for mid in new_mediador_ids:
                mediador = await db.users.find_one({"id": mid})
                if mediador:
                    mediador_names.append(mediador["name"])
            
            if mediador_names:
                update_data["assigned_mediador_ids"] = new_mediador_ids
                update_data["mediador_names"] = mediador_names
                # Compatibilidade
                update_data["assigned_mediador_id"] = new_mediador_ids[0]
                update_data["mediador_name"] = mediador_names[0]
                
                # Log das mudanças
                old_names = []
                for old_id in old_mediador_ids:
                    old_user = await db.users.find_one({"id": old_id}, {"name": 1})
                    if old_user:
                        old_names.append(old_user.get("name", ""))
                
                added = [n for n in mediador_names if n not in old_names]
                removed = [n for n in old_names if n not in mediador_names]
                
                changes = []
                if added:
                    changes.append(f"Adicionou: {', '.join(added)}")
                if removed:
                    changes.append(f"Removeu: {', '.join(removed)}")
                
                if changes:
                    await log_history(process_id, user, "Actualizou intermediários", "assigned_mediador_ids", ", ".join(old_names), ", ".join(mediador_names))
    
    # Atribuir utilizador de indexação (mantém single)
    if indexacao_id is not None:
        if indexacao_id == "" or indexacao_id == "null":
            # Remover indexação
            update_data["assigned_indexacao_id"] = None
            update_data["indexacao_name"] = None
            if old_indexacao:
                old_user = await db.users.find_one({"id": old_indexacao}, {"name": 1})
                await log_history(process_id, user, "Removeu indexação", "assigned_indexacao_id", old_user.get("name") if old_user else old_indexacao, None)
        else:
            indexacao_user = await db.users.find_one({"id": indexacao_id})
            if indexacao_user:
                update_data["assigned_indexacao_id"] = indexacao_id
                update_data["indexacao_name"] = indexacao_user["name"]
                old_name = None
                if old_indexacao:
                    old_user = await db.users.find_one({"id": old_indexacao}, {"name": 1})
                    old_name = old_user.get("name") if old_user else None
                await log_history(process_id, user, "Atribuiu indexação", "assigned_indexacao_id", old_name, indexacao_user["name"])
    
    await db.processes.update_one({"id": process_id}, {"$set": update_data})
    return {"success": True, "message": "Atribuições actualizadas com sucesso"}


@router.post("/{process_id}/assign-me")
async def assign_me_to_process(
    process_id: str,
    user: dict = Depends(require_staff())
):
    """
    Permite ao utilizador atribuir-se a um processo.
    O utilizador será atribuído como consultor ou mediador dependendo do seu papel.
    Suporta múltiplos consultores e intermediários.
    """
    process = await db.processes.find_one({"id": process_id}, {"_id": 0})
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")
    
    user_role = user.get("role", "")
    user_id = user["id"]
    user_name = user["name"]
    
    update_data = {"updated_at": datetime.now(timezone.utc).isoformat()}
    assignment_type = None
    
    # Obter listas atuais
    current_consultor_ids = process.get("assigned_consultor_ids") or []
    current_mediador_ids = process.get("assigned_mediador_ids") or []
    current_consultor_names = process.get("consultor_names") or []
    current_mediador_names = process.get("mediador_names") or []
    
    # Determinar tipo de atribuição baseado no papel
    if UserRole.can_act_as_consultor(user_role):
        # Verificar se já está atribuído como consultor
        if user_id in current_consultor_ids:
            raise HTTPException(status_code=400, detail="Já está atribuído como consultor a este processo")
        
        # Adicionar à lista de consultores
        new_consultor_ids = current_consultor_ids + [user_id]
        new_consultor_names = current_consultor_names + [user_name]
        
        update_data["assigned_consultor_ids"] = new_consultor_ids
        update_data["consultor_names"] = new_consultor_names
        # Compatibilidade
        update_data["assigned_consultor_id"] = new_consultor_ids[0]
        update_data["consultor_name"] = new_consultor_names[0]
        
        assignment_type = "consultor"
    elif UserRole.can_act_as_mediador(user_role):
        # Verificar se já está atribuído como mediador
        if user_id in current_mediador_ids:
            raise HTTPException(status_code=400, detail="Já está atribuído como intermediário a este processo")
        
        # Adicionar à lista de intermediários
        new_mediador_ids = current_mediador_ids + [user_id]
        new_mediador_names = current_mediador_names + [user_name]
        
        update_data["assigned_mediador_ids"] = new_mediador_ids
        update_data["mediador_names"] = new_mediador_names
        # Compatibilidade
        update_data["assigned_mediador_id"] = new_mediador_ids[0]
        update_data["mediador_name"] = new_mediador_names[0]
        
        assignment_type = "mediador"
    else:
        raise HTTPException(status_code=403, detail="O seu papel não permite atribuir-se a processos")
    
    await db.processes.update_one({"id": process_id}, {"$set": update_data})
    await log_history(process_id, user, f"Atribuiu-se como {assignment_type}", f"assigned_{assignment_type}_ids", None, user_name)
    
    return {
        "success": True,
        "message": f"Atribuído como {assignment_type}",
        "assignment_type": assignment_type
    }


@router.post("/{process_id}/unassign-me")
async def unassign_me_from_process(
    process_id: str,
    user: dict = Depends(require_staff())
):
    """
    Permite ao utilizador remover-se de um processo.
    Suporta múltiplos consultores e intermediários.
    """
    process = await db.processes.find_one({"id": process_id}, {"_id": 0})
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")
    
    user_id = user["id"]
    user_name = user["name"]
    
    update_data = {"updated_at": datetime.now(timezone.utc).isoformat()}
    removed_from = []
    
    # Obter listas atuais
    current_consultor_ids = process.get("assigned_consultor_ids") or []
    current_mediador_ids = process.get("assigned_mediador_ids") or []
    current_consultor_names = process.get("consultor_names") or []
    current_mediador_names = process.get("mediador_names") or []
    
    # Verificar se está atribuído como consultor
    if user_id in current_consultor_ids:
        # Remover da lista
        idx = current_consultor_ids.index(user_id)
        new_consultor_ids = current_consultor_ids[:idx] + current_consultor_ids[idx+1:]
        new_consultor_names = current_consultor_names[:idx] + current_consultor_names[idx+1:]
        
        update_data["assigned_consultor_ids"] = new_consultor_ids
        update_data["consultor_names"] = new_consultor_names
        # Compatibilidade
        update_data["assigned_consultor_id"] = new_consultor_ids[0] if new_consultor_ids else None
        update_data["consultor_name"] = new_consultor_names[0] if new_consultor_names else None
        
        removed_from.append("consultor")
        await log_history(process_id, user, "Removeu-se como consultor", "assigned_consultor_ids", user_name, None)
    
    # Verificar se está atribuído como mediador
    if user_id in current_mediador_ids:
        # Remover da lista
        idx = current_mediador_ids.index(user_id)
        new_mediador_ids = current_mediador_ids[:idx] + current_mediador_ids[idx+1:]
        new_mediador_names = current_mediador_names[:idx] + current_mediador_names[idx+1:]
        
        update_data["assigned_mediador_ids"] = new_mediador_ids
        update_data["mediador_names"] = new_mediador_names
        # Compatibilidade
        update_data["assigned_mediador_id"] = new_mediador_ids[0] if new_mediador_ids else None
        update_data["mediador_name"] = new_mediador_names[0] if new_mediador_names else None
        
        removed_from.append("mediador")
        await log_history(process_id, user, "Removeu-se como mediador", "assigned_mediador_ids", user_name, None)
    
    if not removed_from:
        raise HTTPException(status_code=400, detail="Não está atribuído a este processo")
    
    await db.processes.update_one({"id": process_id}, {"$set": update_data})
    
    return {
        "success": True,
        "message": f"Removido como {', '.join(removed_from)}",
        "removed_from": removed_from
    }


@router.post("/{process_id}/resolve-conflict")
async def resolve_data_conflict(
    process_id: str,
    data: dict,
    user: dict = Depends(get_current_user)
):
    """
    TAREFA 2: Resolver conflito de dados extraídos pela IA.
    
    Quando a IA extrai dados de um documento e o campo já tem valor,
    é criada uma sugestão em ai_suggestions. Este endpoint permite
    ao utilizador escolher qual valor manter.
    
    Body:
    {
        "field": "nif",  # Campo em conflito
        "choice": "ai" | "current",  # Qual valor manter
        "suggestion_id": "uuid da sugestão"  # Opcional, para identificar sugestão específica
    }
    """
    field = data.get("field")
    choice = data.get("choice")
    suggestion_id = data.get("suggestion_id")
    
    if not field or choice not in ["ai", "current"]:
        raise HTTPException(status_code=400, detail="field e choice ('ai' ou 'current') são obrigatórios")
    
    process = await db.processes.find_one({"id": process_id}, {"_id": 0})
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")
    
    ai_suggestions = process.get("ai_suggestions", [])
    
    # Encontrar a sugestão para este campo
    suggestion = None
    suggestion_index = -1
    
    for i, s in enumerate(ai_suggestions):
        if s.get("field") == field:
            if suggestion_id and s.get("id") != suggestion_id:
                continue
            suggestion = s
            suggestion_index = i
            break
    
    if not suggestion:
        raise HTTPException(status_code=404, detail=f"Nenhuma sugestão encontrada para o campo '{field}'")
    
    now = datetime.now(timezone.utc).isoformat()
    update_data = {"updated_at": now}
    
    if choice == "ai":
        # Aceitar valor sugerido pela IA
        suggested_value = suggestion.get("suggested")
        field_path = suggestion.get("field_path", field)
        
        # Sanitizar o valor sugerido antes de guardar
        if suggested_value is not None and isinstance(suggested_value, str):
            if field in ["nif", "documento_id"]:
                sanitized_val = sanitize_nif(suggested_value)
                if sanitized_val is None and suggested_value:
                    log_sanitization_rejection(field, str(suggested_value), "NIF inválido")
                suggested_value = sanitized_val
            elif field in ["email", "client_email"]:
                suggested_value = sanitize_email(suggested_value)
            elif field in ["telefone", "phone", "client_phone"]:
                suggested_value = sanitize_phone(suggested_value)
            elif field in ["nome_completo", "nome", "name", "nome_pai", "nome_mae"]:
                suggested_value = sanitize_name(suggested_value)
            elif field in ["morada_fiscal"]:
                suggested_value = sanitize_string(suggested_value, max_length=500)
            else:
                suggested_value = sanitize_string(suggested_value, max_length=500)
        
        # Determinar onde actualizar (personal_data, financial_data, etc.)
        if "." in field_path:
            section, actual_field = field_path.split(".", 1)
            update_data[f"{section}.{actual_field}"] = suggested_value
        else:
            # Tentar determinar a secção automaticamente
            if field in ["nif", "documento_id", "naturalidade", "nacionalidade", "morada_fiscal", 
                        "birth_date", "data_nascimento", "estado_civil", "data_validade_cc", 
                        "sexo", "altura", "nome_pai", "nome_mae"]:
                update_data[f"personal_data.{field}"] = suggested_value
            elif field in ["salario_bruto", "salario_liquido", "rendimento_anual", 
                          "acesso_portal_financas", "capital_proprio"]:
                update_data[f"financial_data.{field}"] = suggested_value
            else:
                update_data[field] = suggested_value
        
        # Registar no histórico
        await log_history(
            process_id, user,
            f"Aceitou sugestão IA para '{field}'",
            field, suggestion.get("current"), suggested_value
        )
    else:
        # Manter valor actual - apenas registar no histórico
        await log_history(
            process_id, user,
            f"Manteve valor actual para '{field}'",
            field, suggestion.get("suggested"), suggestion.get("current")
        )
    
    # Remover a sugestão resolvida da lista
    ai_suggestions.pop(suggestion_index)
    update_data["ai_suggestions"] = ai_suggestions
    
    await db.processes.update_one({"id": process_id}, {"$set": update_data})
    
    return {
        "success": True,
        "message": f"Conflito resolvido: {'valor IA aceite' if choice == 'ai' else 'valor actual mantido'}",
        "field": field,
        "remaining_conflicts": len(ai_suggestions)
    }


@router.post("/{process_id}/confirm-data")
async def confirm_client_data(
    process_id: str,
    data: dict,
    user: dict = Depends(get_current_user)
):
    """
    TAREFA 2: Confirmar dados do cliente e bloquear actualizações automáticas da IA.
    
    Quando is_data_confirmed=True, a IA continua a classificar documentos
    mas não extrai dados de perfil automaticamente.
    
    Body:
    {
        "confirmed": true | false
    }
    """
    confirmed = data.get("confirmed", True)
    
    process = await db.processes.find_one({"id": process_id}, {"_id": 0})
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")
    
    # Verificar se há conflitos pendentes antes de confirmar
    ai_suggestions = process.get("ai_suggestions", [])
    if confirmed and len(ai_suggestions) > 0:
        raise HTTPException(
            status_code=400, 
            detail=f"Existem {len(ai_suggestions)} conflitos pendentes. Resolva-os antes de confirmar os dados."
        )
    
    now = datetime.now(timezone.utc).isoformat()
    await db.processes.update_one(
        {"id": process_id},
        {"$set": {
            "is_data_confirmed": confirmed,
            "data_confirmed_at": now if confirmed else None,
            "data_confirmed_by": user["id"] if confirmed else None,
            "updated_at": now
        }}
    )
    
    action = "confirmou" if confirmed else "desbloqueou"
    await log_history(process_id, user, f"{action} os dados do cliente", "is_data_confirmed", not confirmed, confirmed)
    
    return {
        "success": True,
        "message": f"Dados do cliente {'confirmados e bloqueados' if confirmed else 'desbloqueados'}",
        "is_data_confirmed": confirmed
    }


# ====================================================================
# ENDPOINTS DE GESTÃO DE CLIENTES DO PROCESSO (N:M)
# ====================================================================

@router.post("/{process_id}/add-client")
async def add_client_to_process(
    process_id: str,
    client_id: str = Query(..., description="ID do cliente a adicionar"),
    as_co_titular: bool = Query(False, description="Se True, adiciona como co-titular"),
    user: dict = Depends(require_staff())
):
    """
    Adicionar um cliente existente a um processo.
    
    Isto permite que um processo tenha múltiplos clientes (titulares).
    Por exemplo, um processo de crédito com dois titulares.
    
    Args:
        process_id: ID do processo
        client_id: ID do cliente a adicionar
        as_co_titular: Se True, adiciona como co-titular (co_buyer)
    
    Returns:
        Success message
    """
    process = await db.processes.find_one({"id": process_id})
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")
    
    client = await db.clients.find_one({"id": client_id})
    if not client:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    
    # Verificar se já está associado
    current_client_ids = process.get("client_ids", [])
    if client_id in current_client_ids:
        raise HTTPException(status_code=400, detail="Cliente já está associado a este processo")
    
    now = datetime.now(timezone.utc).isoformat()
    
    # Adicionar cliente ao processo
    update_data = {
        "updated_at": now
    }
    
    # Adicionar à lista de client_ids
    current_client_ids.append(client_id)
    update_data["client_ids"] = current_client_ids
    
    # Se for co-titular, adicionar aos co_buyers
    if as_co_titular:
        co_buyers = process.get("co_buyers", [])
        co_buyers.append({
            "name": client.get("nome"),
            "email": client.get("contacto", {}).get("email"),
            "nif": client.get("dados_pessoais", {}).get("nif"),
            "phone": client.get("contacto", {}).get("telefone"),
            "client_id": client_id,
            "relacao": "co-titular"
        })
        update_data["co_buyers"] = co_buyers
        
        # Adicionar também ao titular2_data se for o primeiro co-titular
        if len(co_buyers) == 1:
            update_data["titular2_data"] = {
                "name": client.get("nome"),
                "email": client.get("contacto", {}).get("email"),
                "nif": client.get("dados_pessoais", {}).get("nif"),
                "phone": client.get("contacto", {}).get("telefone")
            }
    
    await db.processes.update_one({"id": process_id}, {"$set": update_data})
    
    # Atualizar process_ids do cliente
    await db.clients.update_one(
        {"id": client_id},
        {
            "$addToSet": {"process_ids": process_id},
            "$set": {"updated_at": now}
        }
    )
    
    await log_history(
        process_id, user, 
        f"Adicionou cliente {client.get('nome')} ao processo" + (" como co-titular" if as_co_titular else "")
    )
    
    return {
        "success": True,
        "message": f"Cliente {client.get('nome')} adicionado ao processo",
        "total_clients": len(current_client_ids)
    }


@router.post("/{process_id}/remove-client")
async def remove_client_from_process(
    process_id: str,
    client_id: str = Query(..., description="ID do cliente a remover"),
    user: dict = Depends(require_staff())
):
    """
    Remover um cliente de um processo.
    
    Nota: Não é possível remover o cliente principal (titular).
    Apenas co-titulares podem ser removidos.
    
    Args:
        process_id: ID do processo
        client_id: ID do cliente a remover
    
    Returns:
        Success message
    """
    process = await db.processes.find_one({"id": process_id})
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")
    
    current_client_ids = process.get("client_ids", [])
    
    # Verificar se está associado
    if client_id not in current_client_ids:
        raise HTTPException(status_code=400, detail="Cliente não está associado a este processo")
    
    # Não permitir remover o cliente principal
    if client_id == process.get("client_id"):
        raise HTTPException(
            status_code=400, 
            detail="Não é possível remover o cliente principal. Apenas co-titulares podem ser removidos."
        )
    
    now = datetime.now(timezone.utc).isoformat()
    
    # Remover cliente da lista
    current_client_ids.remove(client_id)
    
    # Remover dos co_buyers
    co_buyers = process.get("co_buyers", [])
    co_buyers = [cb for cb in co_buyers if cb.get("client_id") != client_id]
    
    update_data = {
        "client_ids": current_client_ids,
        "co_buyers": co_buyers if co_buyers else None,
        "updated_at": now
    }
    
    # Atualizar titular2_data se necessário
    if co_buyers:
        update_data["titular2_data"] = {
            "name": co_buyers[0].get("name"),
            "email": co_buyers[0].get("email"),
            "nif": co_buyers[0].get("nif"),
            "phone": co_buyers[0].get("phone")
        }
    else:
        update_data["titular2_data"] = None
    
    await db.processes.update_one({"id": process_id}, {"$set": update_data})
    
    # Remover process_ids do cliente
    await db.clients.update_one(
        {"id": client_id},
        {
            "$pull": {"process_ids": process_id},
            "$set": {"updated_at": now}
        }
    )
    
    client = await db.clients.find_one({"id": client_id})
    client_name = client.get("nome") if client else client_id
    
    await log_history(process_id, user, f"Removeu cliente {client_name} do processo")
    
    return {
        "success": True,
        "message": f"Cliente {client_name} removido do processo",
        "total_clients": len(current_client_ids)
    }


@router.get("/{process_id}/clients")
async def get_process_clients(
    process_id: str,
    user: dict = Depends(get_current_user)
):
    """
    Obter todos os clientes associados a um processo.
    
    Returns:
        Lista de clientes com seus dados básicos
    """
    process = await db.processes.find_one({"id": process_id})
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")
    
    client_ids = process.get("client_ids", [])
    if not client_ids:
        # Compatibilidade com processos antigos
        if process.get("client_id"):
            client_ids = [process.get("client_id")]
        else:
            return {"clients": [], "total": 0}
    
    clients = await db.clients.find(
        {"id": {"$in": client_ids}},
        {"_id": 0}
    ).to_list(length=10)
    
    # Enriquecer com informação de relação
    co_buyers = process.get("co_buyers", [])
    co_buyer_ids = {cb.get("client_id") for cb in co_buyers if cb.get("client_id")}
    
    result = []
    for c in clients:
        client_info = {
            "id": c.get("id"),
            "nome": c.get("nome"),
            "email": c.get("contacto", {}).get("email"),
            "telefone": c.get("contacto", {}).get("telefone"),
            "nif": c.get("dados_pessoais", {}).get("nif"),
            "is_main": c.get("id") == process.get("client_id"),
            "relacao": "co-titular" if c.get("id") in co_buyer_ids else "titular"
        }
        result.append(client_info)
    
    return {
        "clients": result,
        "total": len(result),
        "process_id": process_id,
        "process_number": process.get("process_number")
    }


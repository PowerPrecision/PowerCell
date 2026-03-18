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
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query

from database import db
from models.auth import UserRole
from models.process import (
    ProcessType, ProcessCreate, ProcessUpdate, ProcessResponse
)
from services.auth import get_current_user, require_roles, require_staff
from services.notification_service import (
    send_notification_with_preference_check,
    send_status_change_notification,
    send_new_process_notification,
    send_to_admins
)
from services.history import log_history, log_data_changes
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
    sanitize_email,
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

logger = logging.getLogger(__name__)


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
        personal_data["email"] = user["email"]
    if user.get("name") and not personal_data.get("nome"):
        personal_data["nome"] = user["name"]
    if user.get("phone") and not personal_data.get("telefone"):
        personal_data["telefone"] = user.get("phone")
    
    # Construir documento do processo
    process_doc = {
        "id": process_id,
        "process_number": process_number,
        "client_id": user["id"],
        "client_name": user["name"],
        "client_email": user["email"],
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
    client_name = (
        personal.get("nome_completo") or 
        personal.get("nome") or 
        data.client_name or 
        personal.get("name") or
        None  # Se não houver nome, vamos extrair do email
    )
    # Se ainda não temos nome, extrair do email (parte antes do @)
    client_email = sanitize_email(personal.get("email") or data.client_email or "")
    if not client_name and client_email:
        # Extrair nome do email: "joao.silva@example.com" -> "Joao Silva"
        email_name = client_email.split("@")[0]
        # Converter separadores comuns em espaços e capitalizar
        client_name = email_name.replace(".", " ").replace("_", " ").replace("-", " ").title()
    elif not client_name:
        # Último recurso: usar "Cliente" com timestamp para evitar duplicados
        client_name = f"Cliente {datetime.now().strftime('%Y%m%d%H%M%S')}"
    
    client_phone = personal.get("telefone") or personal.get("phone") or ""
    
    # Construir documento do processo
    process_doc = {
        "id": process_id,
        "process_number": process_number,
        "client_id": None,  # Não há utilizador cliente associado
        "client_name": client_name,
        "client_email": client_email,
        "client_phone": client_phone,
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
    elif user["role"] == UserRole.CONSULTOR:
        process_doc["assigned_consultor_id"] = user["id"]
        process_doc["consultor_name"] = user["name"]
    
    # Encriptar campos sensíveis antes de guardar
    process_doc = encrypt_sensitive_data(process_doc)
    
    # Inserir na base de dados
    await db.processes.insert_one(process_doc)
    
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
    elif role in [UserRole.ADMIN, UserRole.CEO, UserRole.ADMINISTRATIVO]:
        # Admin, CEO e Administrativo vêem todos os processos
        pass
    elif role == UserRole.CONSULTOR:
        query["assigned_consultor_id"] = user["id"]
    elif role in [UserRole.MEDIADOR, UserRole.INTERMEDIARIO]:
        query["assigned_mediador_id"] = user["id"]
    elif role == UserRole.DIRETOR:
        query["$or"] = [
            {"assigned_consultor_id": user["id"]},
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
    elif role in [UserRole.ADMIN, UserRole.CEO, UserRole.ADMINISTRATIVO]:
        pass
    elif role == UserRole.CONSULTOR:
        query["assigned_consultor_id"] = user["id"]
    elif role in [UserRole.MEDIADOR, UserRole.INTERMEDIARIO]:
        query["assigned_mediador_id"] = user["id"]
    elif role == UserRole.DIRETOR:
        query["$or"] = [
            {"assigned_consultor_id": user["id"]},
            {"assigned_mediador_id": user["id"]}
        ]
    
    # Adicionar filtros opcionais
    if status:
        query["status"] = status
    
    if search:
        search_condition = {
            "$or": [
                {"client_name": {"$regex": search, "$options": "i"}},
                {"client_email": {"$regex": search, "$options": "i"}}
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
    """
    role = user["role"]
    user_id = user["id"]
    query = {}
    
    # Filter by role (base visibility)
    if role == UserRole.CONSULTOR:
        query["assigned_consultor_id"] = user["id"]
    elif role in [UserRole.MEDIADOR, UserRole.INTERMEDIARIO]:
        query["assigned_mediador_id"] = user["id"]
    elif role == UserRole.DIRETOR:
        query["$or"] = [
            {"assigned_consultor_id": user["id"]},
            {"assigned_mediador_id": user["id"]}
        ]
    # Admin, CEO e Administrativo see all (no base filter)
    
    # Apply additional filters (only for roles that can see all)
    if role in [UserRole.ADMIN, UserRole.CEO, UserRole.ADMINISTRATIVO]:
        if consultor_id:
            if consultor_id == "none":
                # Sem consultor atribuído = null, undefined, ou string vazia
                query["$or"] = [
                    {"assigned_consultor_id": None},
                    {"assigned_consultor_id": ""},
                    {"assigned_consultor_id": {"$exists": False}}
                ]
            else:
                query["assigned_consultor_id"] = consultor_id
        
        if mediador_id:
            if mediador_id == "none":
                # Sem mediador atribuído
                if "assigned_consultor_id" in query:
                    # Se já há filtro de consultor, usar $and
                    query = {
                        "$and": [
                            query,
                            {"$or": [
                                {"assigned_mediador_id": None},
                                {"assigned_mediador_id": ""},
                                {"assigned_mediador_id": {"$exists": False}}
                            ]}
                        ]
                    }
                else:
                    query["$or"] = [
                        {"assigned_mediador_id": None},
                        {"assigned_mediador_id": ""},
                        {"assigned_mediador_id": {"$exists": False}}
                    ]
            else:
                query["assigned_mediador_id"] = mediador_id
    
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
    
    return {
        "columns": kanban,
        "total_processes": len(processes),
        "user_role": role,
        "current_user_id": user_id
    }


@router.get("/my-clients")
async def get_my_clients(user: dict = Depends(require_roles([
    UserRole.CONSULTOR, UserRole.MEDIADOR, UserRole.INTERMEDIARIO, 
    UserRole.ADMIN, UserRole.CEO
]))):
    """
    Obter lista de clientes atribuídos ao utilizador atual.
    
    Retorna uma lista com:
    - Nome do cliente
    - Fase do processo
    - Ações pendentes (tarefas, documentos a atualizar)
    
    Permissões:
    - Consultor: Apenas os seus clientes (assigned_consultor_id)
    - Intermediário/Mediador: Apenas os seus clientes (assigned_mediador_id ou criados por eles)
    - Admin/CEO: Todos os clientes (para supervisão)
    """
    user_id = user["id"]
    user_email = user.get("email", "")
    role = user["role"]
    
    # Construir query baseada no papel do utilizador
    if role == UserRole.CONSULTOR:
        query = {"assigned_consultor_id": user_id}
    elif role in [UserRole.MEDIADOR, UserRole.INTERMEDIARIO]:
        # Intermediários vêem processos atribuídos a eles OU criados por eles
        query = {
            "$or": [
                {"assigned_mediador_id": user_id},
                {"created_by": user_email}
            ]
        }
    else:
        # Admin/CEO vêem todos
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
async def update_process(process_id: str, data: ProcessUpdate, user: dict = Depends(get_current_user)):
    process = await db.processes.find_one({"id": process_id}, {"_id": 0})
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")
    
    role = user["role"]
    
    # Gestor de Documentos e Indexação não podem actualizar dados do processo
    if role == UserRole.GESTOR_DOCUMENTOS:
        raise HTTPException(status_code=403, detail="Gestor de Documentos não pode alterar dados do processo. Apenas documentos.")
    
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
            update_data["personal_data"] = data.personal_data.model_dump()
        if data.financial_data:
            await log_data_changes(process_id, user, process.get("financial_data"), data.financial_data.model_dump(), "dados financeiros")
            update_data["financial_data"] = data.financial_data.model_dump()
    else:
        # Staff updates
        if data.personal_data and can_update_personal:
            await log_data_changes(process_id, user, process.get("personal_data"), data.personal_data.model_dump(), "dados pessoais")
            update_data["personal_data"] = data.personal_data.model_dump()
        
        if data.financial_data and can_update_financial:
            await log_data_changes(process_id, user, process.get("financial_data"), data.financial_data.model_dump(), "dados financeiros")
            update_data["financial_data"] = data.financial_data.model_dump()
        
        if data.real_estate_data and can_update_real_estate:
            await log_data_changes(process_id, user, process.get("real_estate_data"), data.real_estate_data.model_dump(), "dados imobiliários")
            update_data["real_estate_data"] = data.real_estate_data.model_dump()
        
        if data.credit_data and can_update_credit:
            await log_data_changes(process_id, user, process.get("credit_data"), data.credit_data.model_dump(), "dados de crédito")
            update_data["credit_data"] = data.credit_data.model_dump()
        
        # Atualizar email e telefone do cliente
        if data.client_email is not None:
            update_data["client_email"] = sanitize_email(data.client_email)
        if data.client_phone is not None:
            update_data["client_phone"] = data.client_phone
        
        # Campos adicionais do CPCV
        if data.co_buyers is not None:
            update_data["co_buyers"] = data.co_buyers
        if data.co_applicants is not None:
            update_data["co_applicants"] = data.co_applicants
        if data.vendedor is not None:
            update_data["vendedor"] = data.vendedor
        if data.mediador is not None:
            update_data["mediador"] = data.mediador
        
        if data.status and can_update_status and (data.status in valid_statuses or not valid_statuses):
            await log_history(process_id, user, "Alterou estado", "status", process["status"], data.status)
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
    
    # Desencriptar dados para a resposta
    updated = decrypt_sensitive_data(updated)
    
    # Sincronizar com Trello (nome e descrição do card)
    await sync_process_to_trello(updated)
    
    return ProcessResponse(**updated)


@router.post("/{process_id}/assign")
async def assign_process(
    process_id: str, 
    consultor_id: Optional[str] = None,
    mediador_id: Optional[str] = None,
    user: dict = Depends(require_staff())
):
    """
    Atribuir consultor e/ou mediador a um processo.
    Qualquer utilizador staff pode atribuir.
    """
    process = await db.processes.find_one({"id": process_id})
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")
    
    update_data = {"updated_at": datetime.now(timezone.utc).isoformat()}
    old_consultor = process.get("assigned_consultor_id")
    old_mediador = process.get("assigned_mediador_id")
    
    # Atribuir consultor
    if consultor_id is not None:
        if consultor_id == "" or consultor_id == "null":
            # Remover consultor
            update_data["assigned_consultor_id"] = None
            update_data["consultor_name"] = None
            if old_consultor:
                old_user = await db.users.find_one({"id": old_consultor}, {"name": 1})
                await log_history(process_id, user, "Removeu consultor", "assigned_consultor_id", old_user.get("name") if old_user else old_consultor, None)
        else:
            consultor = await db.users.find_one({"id": consultor_id})
            if consultor:
                update_data["assigned_consultor_id"] = consultor_id
                update_data["consultor_name"] = consultor["name"]
                old_name = None
                if old_consultor:
                    old_user = await db.users.find_one({"id": old_consultor}, {"name": 1})
                    old_name = old_user.get("name") if old_user else None
                await log_history(process_id, user, "Atribuiu consultor", "assigned_consultor_id", old_name, consultor["name"])
    
    # Atribuir mediador
    if mediador_id is not None:
        if mediador_id == "" or mediador_id == "null":
            # Remover mediador
            update_data["assigned_mediador_id"] = None
            update_data["mediador_name"] = None
            if old_mediador:
                old_user = await db.users.find_one({"id": old_mediador}, {"name": 1})
                await log_history(process_id, user, "Removeu mediador", "assigned_mediador_id", old_user.get("name") if old_user else old_mediador, None)
        else:
            mediador = await db.users.find_one({"id": mediador_id})
            if mediador:
                update_data["assigned_mediador_id"] = mediador_id
                update_data["mediador_name"] = mediador["name"]
                old_name = None
                if old_mediador:
                    old_user = await db.users.find_one({"id": old_mediador}, {"name": 1})
                    old_name = old_user.get("name") if old_user else None
                await log_history(process_id, user, "Atribuiu mediador", "assigned_mediador_id", old_name, mediador["name"])
    
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
    """
    process = await db.processes.find_one({"id": process_id}, {"_id": 0})
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")
    
    user_role = user.get("role", "")
    user_id = user["id"]
    user_name = user["name"]
    
    update_data = {"updated_at": datetime.now(timezone.utc).isoformat()}
    assignment_type = None
    
    # Determinar tipo de atribuição baseado no papel
    if UserRole.can_act_as_consultor(user_role):
        # Verificar se já tem consultor atribuído
        if process.get("assigned_consultor_id") and process["assigned_consultor_id"] != user_id:
            # Já tem outro consultor, mas pode adicionar como mediador se aplicável
            if UserRole.can_act_as_mediador(user_role) and not process.get("assigned_mediador_id"):
                update_data["assigned_mediador_id"] = user_id
                update_data["mediador_name"] = user_name
                assignment_type = "mediador"
            else:
                raise HTTPException(status_code=400, detail="Este processo já tem um consultor atribuído")
        else:
            update_data["assigned_consultor_id"] = user_id
            update_data["consultor_name"] = user_name
            assignment_type = "consultor"
    elif UserRole.can_act_as_mediador(user_role):
        if process.get("assigned_mediador_id") and process["assigned_mediador_id"] != user_id:
            raise HTTPException(status_code=400, detail="Este processo já tem um mediador atribuído")
        update_data["assigned_mediador_id"] = user_id
        update_data["mediador_name"] = user_name
        assignment_type = "mediador"
    else:
        raise HTTPException(status_code=403, detail="O seu papel não permite atribuir-se a processos")
    
    await db.processes.update_one({"id": process_id}, {"$set": update_data})
    await log_history(process_id, user, f"Atribuiu-se como {assignment_type}", f"assigned_{assignment_type}_id", None, user_name)
    
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
    """
    process = await db.processes.find_one({"id": process_id}, {"_id": 0})
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")
    
    user_id = user["id"]
    user_name = user["name"]
    
    update_data = {"updated_at": datetime.now(timezone.utc).isoformat()}
    removed_from = []
    
    # Verificar se está atribuído como consultor
    if process.get("assigned_consultor_id") == user_id:
        update_data["assigned_consultor_id"] = None
        update_data["consultor_name"] = None
        removed_from.append("consultor")
        await log_history(process_id, user, "Removeu-se como consultor", "assigned_consultor_id", user_name, None)
    
    # Verificar se está atribuído como mediador
    if process.get("assigned_mediador_id") == user_id:
        update_data["assigned_mediador_id"] = None
        update_data["mediador_name"] = None
        removed_from.append("mediador")
        await log_history(process_id, user, "Removeu-se como mediador", "assigned_mediador_id", user_name, None)
    
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


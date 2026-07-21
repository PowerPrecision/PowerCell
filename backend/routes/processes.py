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
import os
import uuid
import logging
import re
import asyncio
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query

from database import db
from models.auth import UserRole
from models.process import (
    ProcessCreate, ProcessUpdate, ProcessResponse
)
from services.auth import get_current_user, require_roles, require_staff, get_effective_role, get_all_user_roles
from fastapi import Request
from services.notification_service import (
    send_notification_with_preference_check,
    send_status_change_notification,
    send_new_process_notification,
    send_to_admins
)
from services.history import log_history, log_data_changes
from services.audit_trail_service import log_audit_event
from services.audit_cdc import inject_cdc_context
from services.alerts import (
    get_process_alerts,
    check_property_documents,
    create_deed_reminder,
    notify_pre_approval_countdown,
    notify_cpcv_or_deed_document_check
)
from services.realtime_notifications import notify_process_status_change
from services.encryption import decrypt_client_data
# PACOTE CW — Trello Mirror Service (sync unidirecional CRM → Trello)
from services.trello_service import sync_process_to_trello

# Importar serviços refatorados
from services.process_service import (
    get_next_process_number,
    can_view_process,
    can_edit_process_data,
    build_query_filter,
    create_process_document,
    update_process_document,
    get_process_by_id,
    get_processes_for_user,
    get_user_name,
    encrypt_sensitive_data,
    decrypt_sensitive_data,
    decrypt_processes_list,
    populate_client_data,
    extract_client_updates_from_body,
    PROCESS_LIST_PROJECTION,
    PROCESS_KANBAN_PROJECTION,
    PROCESS_MY_CLIENTS_PROJECTION,
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
from services.process_finance import (
    create_finance_snapshot as _create_finance_snapshot,
    ensure_finance_snapshot as _ensure_finance_snapshot,
)
from services.process_list_filters import (
    build_process_list_query,
    build_kanban_query,
    build_my_clients_process_query,
    build_my_clients_leads_query,
)
from services.process_my_clients import (
    my_clients_sort_key,
    fetch_unread_messages_map,
    fetch_new_documents_map,
    fetch_latest_activity_notes_map,
    fetch_orphan_leads_for_my_clients,
    fetch_pending_tasks_by_process,
    fetch_consultor_name_map,
    assemble_my_clients_rows,
    build_my_clients_response,
    process_ids_from_my_clients_page,
)
from services.process_indexing import (
    compute_next_workflow_status,
    build_indexacao_update_set,
    assert_mark_indexed_permission,
    load_workflow_status_pipeline,
    run_mark_indexed_side_effects,
)
from services.process_create import (
    resolve_initial_workflow_status,
    create_default_portal_documents,
    link_clients_after_process_create,
    maybe_auto_assign_indexer_on_create,
    build_create_broadcast_names,
    assert_is_cliente_role,
    load_client_doc_or_404,
    build_client_self_process_doc,
    link_single_client_to_process,
    assemble_staff_create_bundle,
    send_portal_welcome_email_from_process,
)
from services.process_detail import (
    load_process_doc_or_404,
    assert_can_view_process_or_403,
    attach_latest_activity,
    attach_portal_access,
    ensure_client_id_default,
    serialize_process_detail_response,
)
from services.process_clients_nm import (
    build_add_client_update,
    build_remove_client_update,
    format_add_client_response,
    format_remove_client_response,
)
from services.process_portal_messages import (
    load_process_for_portal_or_404,
    validate_staff_portal_message_content,
    build_staff_portal_message_doc,
    staff_portal_message_response,
    count_unread_client_portal_messages,
    list_portal_messages_for_staff,
    insert_staff_portal_message,
    notify_team_email_portal_message,
    notify_assigned_realtime_portal_message,
    broadcast_staff_portal_message_ws,
)
from services.process_ai_conflict import apply_ai_conflict_choice
from services.process_update import (
    prepare_encrypted_client_updates,
    apply_client_personal_updates_from_process_put,
    build_role_update_permissions,
    assert_process_editable_for_role,
    seed_update_data,
    apply_staff_business_updates,
    encrypt_process_update_payload,
    attach_field_metadata_if_present,
    run_process_update_side_effects,
    parse_update_request_meta,
    assert_cliente_owns_process,
    decrypt_process_doc_or_500,
    build_process_response_or_500,
    load_valid_workflow_status_names,
    maybe_reassign_primary_client_with_audit,
    decrypt_and_populate_updated_process,
)
from services.process_broadcast import broadcast_process_delta
from services.process_kanban_enrichment import (
    group_processes_by_status,
    sort_all_kanban_columns,
    fill_missing_process_client_contacts,
    count_kanban_active_inactive,
    safe_build_kanban_columns,
    build_kanban_board_payload,
)
from services.process_kanban_diagnose import run_kanban_diagnose
from services.process_kanban_move import (
    resolve_workflow_purpose_flags,
    build_kanban_move_update,
    run_kanban_move_side_effects,
)
from services.process_list_enrichment import (
    enrich_processes_assignee_names,
    enrich_processes_portal_flags,
    enrich_processes_latest_notes,
    enrich_processes_latest_activity,
    sort_process_list,
    slice_page,
    build_process_list_response,
    build_process_cursor_list_response,
    load_workflow_status_order,
    load_workflow_status_map,
)
from services.process_staff_assignment import (
    build_staff_assign_update,
    build_assign_me_update,
    build_unassign_me_update,
    schedule_assignment_emails,
)
from services.websocket_manager import WSEventType
from services.redis_cache import invalidate_stats_cache

# Portal imports
from services.portal_security import PORTAL_TOKEN_VALIDITY_DAYS
from services.portal_magic_link import (
    issue_portal_magic_link,
    load_active_process_or_404,
    build_generate_magic_link_response,
    send_magic_link_to_client,
)

logger = logging.getLogger(__name__)


# ====================================================================
# CONFIGURAÇÃO DO ROUTER
# ====================================================================
router = APIRouter(prefix="/processes", tags=["Processes"])


# ====================================================================
# ENDPOINTS DE CRIAÇÃO
# ====================================================================

@router.post("/{process_id}/generate-magic-link")
async def generate_magic_link(
    process_id: str,
    request: Request,
    user: dict = Depends(require_staff())
):
    """
    Gera um Magic Link para o Portal do Cliente.

    Permite que um consultor/admin gere um link seguro para o cliente
    acompanhar o seu processo e submeter documentos, sem necessidade
    de registo ou password.

    O link usa um short_id (8 caracteres) guardado na BD que resolve
    para o JWT completo. Exemplo:
    {FRONTEND_URL}/portal/xK9mQ2pL

    Returns:
    - magic_link: URL curta para enviar ao cliente
    - short_id: ID curto do token
    - token: JWT token completo (para debug)
    - expires_in_days: Validade do link
    """
    process = await load_active_process_or_404(process_id)
    issued = await issue_portal_magic_link(
        process_id=process_id,
        process=process,
        user=user,
        request=request,
    )
    logger.info(
        f"Magic link gerado por {user.get('email')} para processo {process_id} "
        f"(cliente: {process.get('client_name', 'N/A')}, short_id: {issued['short_id']})"
    )
    return build_generate_magic_link_response(
        process_id=process_id,
        process=process,
        issued=issued,
        expires_in_days=PORTAL_TOKEN_VALIDITY_DAYS,
    )


@router.post("/{process_id}/generate-magic-link/send")
async def send_magic_link_email(
    process_id: str,
    request: Request,
    user: dict = Depends(require_staff())
):
    """
    Gera um Magic Link e envia-o por email ao cliente.

    O email contém o link curto (short_id) para o cliente aceder
    ao portal do seu processo.
    """
    process = await load_active_process_or_404(process_id)
    return await send_magic_link_to_client(
        process_id=process_id,
        process=process,
        user=user,
        request=request,
    )


@router.post("", response_model=ProcessResponse)
async def create_process(data: ProcessCreate, user: dict = Depends(get_current_user)):
    """
    Criar um novo processo (endpoint para clientes autenticados).

    FASE 2 — Refatoração relacional:
    - Recebe client_id em vez de dados pessoais embutidos
    - Valida que o cliente existe na coleção `clients` (HTTP 404 se não)
    - Após criar o processo, atualiza o array process_ids do cliente

    NOTA: Para registos públicos (sem autenticação),
    utilize o endpoint /api/public/register

    Args:
        data: Dados do processo (process_type + client_id obrigatório)
        user: Utilizador autenticado (deve ser cliente)

    Returns:
        ProcessResponse: Processo criado com dados do cliente populados
    """
    assert_is_cliente_role(user["role"])

    client_doc = await load_client_doc_or_404(data.client_id)
    initial_status, _ = await resolve_initial_workflow_status(is_lead=False)

    process_id = str(uuid.uuid4())
    process_number = await get_next_process_number()
    now = datetime.now(timezone.utc).isoformat()

    decrypted_client = decrypt_client_data(client_doc)
    client_name = decrypted_client.get("nome", "")

    process_doc = build_client_self_process_doc(
        process_id=process_id,
        process_number=process_number,
        client_id=data.client_id,
        process_type=data.process_type,
        initial_status=initial_status,
        now=now,
    )
    process_doc = encrypt_sensitive_data(process_doc)
    await db.processes.insert_one(process_doc)

    await link_single_client_to_process(process_id, data.client_id, now=now)

    asyncio.create_task(sync_process_to_trello(process_doc, action="create"))
    await invalidate_stats_cache(user_id=user["id"])
    await log_history(process_id, user, "Criou processo")

    await broadcast_process_delta(
        event_type=WSEventType.PROCESS_CREATED,
        process_id=process_id,
        process_number=process_number,
        client_name=client_name,
        status=initial_status,
        process_type=data.process_type,
        updated_at=now,
    )

    await send_to_admins(
        "Novo Processo Criado",
        f"O cliente {client_name} criou um novo processo de {data.process_type}.",
        notification_type="new_process",
    )

    response_doc = decrypt_sensitive_data(process_doc)
    response_doc = await populate_client_data(response_doc)
    return ProcessResponse(**{k: v for k, v in response_doc.items() if k != "_id"})


@router.post("/create-client", response_model=ProcessResponse)
async def create_client_process(data: ProcessCreate, user: dict = Depends(get_current_user)):
    """
    Criar um novo processo/cliente.
    
    REGRA DE NEGÓCIO (ESTRITA):
    - É PROIBIDO criar um processo sem associar a um cliente existente.
    - O campo client_id é OBRIGATÓRIO. Se não for fornecido, retorna erro 400.
    - Se o cliente não existir na base de dados, retorna erro 404.
    
    Um cliente pode existir sem processo, mas um processo NUNCA existe sem cliente.
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
    bundle = await assemble_staff_create_bundle(data, user)
    process_id = bundle["process_id"]
    process_number = bundle["process_number"]
    now = bundle["now"]
    is_lead = bundle["is_lead"]
    initial_status = bundle["initial_status"]
    client_id = bundle["client_id"]
    client_name = bundle["client_name"]
    client_email = bundle["client_email"]
    process_doc = bundle["process_doc"]
    second_client_id_for_process = bundle["second_client_id"]

    process_doc = encrypt_sensitive_data(process_doc)
    await db.processes.insert_one(process_doc)

    await maybe_auto_assign_indexer_on_create(
        process_id,
        process_doc,
        is_lead=is_lead,
        initial_status=initial_status,
    )

    await create_default_portal_documents(process_id, user)
    await invalidate_stats_cache(user_id=user["id"])
    await link_clients_after_process_create(
        process_id,
        client_id,
        second_client_id_for_process,
        is_lead=is_lead,
        now=now,
    )

    await log_history(process_id, user, f"Criou processo para cliente {client_name}")
    asyncio.create_task(sync_process_to_trello(process_doc, action="create"))

    if client_email:
        asyncio.create_task(send_portal_welcome_email_from_process(
            client_id=client_id,
            client_email=client_email,
            client_name=client_name,
        ))

    consultor_names, mediador_names = build_create_broadcast_names(user)
    await broadcast_process_delta(
        event_type=WSEventType.PROCESS_CREATED,
        process_id=process_id,
        process_number=process_number,
        client_name=client_name,
        status=initial_status,
        process_type=bundle["process_type"],
        assigned_consultor_ids=process_doc.get("assigned_consultor_ids", []),
        assigned_mediador_ids=process_doc.get("assigned_mediador_ids", []),
        consultor_names=consultor_names,
        mediador_names=mediador_names,
        updated_at=now,
    )

    response_doc = decrypt_sensitive_data(process_doc)
    return ProcessResponse(**{k: v for k, v in response_doc.items() if k != "_id"})


# ====================================================================
# ENDPOINTS DE LISTAGEM - OTIMIZADOS COM PROJEÇÃO E PAGINAÇÃO
# NOTA: as constantes de estado (INACTIVE_STATUSES, ARCHIVED_STATUSES,
# PRE_REGISTO_STATUS, LEAD_STATUS_VALUES, PRE_REGISTO_BYPASS_ROLES) e a função
# _should_hide_pre_registo foram movidas para services/process_status.py
# (importadas no topo deste módulo).


@router.get("")
async def get_processes(
    request: Request,
    page: int = Query(1, ge=1, description="Número da página"),
    size: int = Query(20, ge=1, le=100, description="Itens por página"),
    status: Optional[str] = Query(None, description="Filtrar por status"),
    search: Optional[str] = Query(None, description="Pesquisar por nome/email"),
    view_mode: Optional[str] = Query("active_only", description="Modo de visualização: active_only, all, historical"),
    sort_field: Optional[str] = Query(None, description="Campo de ordenação: client_name, status, created_at, updated_at, priority, property_value, property_location"),
    sort_order: Optional[str] = Query("asc", description="Ordem: asc ou desc"),
    show_all: Optional[bool] = Query(False, description="Visão global: ignorar filtro de utilizador e mostrar todos os processos"),
    # PACOTE BZ: filtro de estado de indexação passado como query param
    # (antes era filtrado localmente no frontend, causando tamanhos de página irregulares)
    is_indexed: Optional[bool] = Query(None, description="PACOTE BZ — Filtrar por estado de indexação: true=indexados, false=pendentes"),
    user: dict = Depends(get_current_user)
):
    """
    Listar processos com paginação e projeção otimizada.
    
    OTIMIZAÇÕES APLICADAS:
    - MongoDB Projection: Apenas campos necessários para a listagem
    - Paginação nativa: Não carrega todos os documentos de uma vez
    - Desencriptação seletiva: Só desencripta client_phone e client_nif
    - Contagem otimizada: count_documents em vez de len(list)
    
    FILTRO DE ESTADO ATIVO (view_mode):
    - 'active_only' (DEFAULT): Apenas processos em curso (exclui concluídos, desistências, eliminados)
    - 'all': Todos os processos ativos e inativos (exceto is_deleted=True)
    - 'historical': Apenas processos concluídos e desistências (para arquivo)
    
    FILTRAGEM AUTOMÁTICA:
    - Admin/CEO: Todos os processos
    - Cliente: Apenas os próprios processos
    - Consultor: Processos atribuídos como consultor
    - Intermediário: Processos atribuídos como intermediário
    
    SEGURANÇA:
    - Processos com is_deleted=True NUNCA aparecem (exceto para admins com view_mode explícito)
    
    Returns:
        {
            "items": [...],
            "total": 150,
            "page": 1,
            "size": 20,
            "pages": 8,
            "view_mode": "active_only"
        }
    """
    role = get_effective_role(request, user)

    query = build_process_list_query(
        user,
        role,
        status=status,
        search=search,
        view_mode=view_mode,
        show_all=bool(show_all),
        is_indexed=is_indexed,
        all_roles=get_all_user_roles(user) if role == "__all_roles__" else None,
        search_mode="accent",
    )

    status_order = await load_workflow_status_order()
    processes = await db.processes.find(
        query,
        PROCESS_LIST_PROJECTION,
    ).to_list(5000)
    processes = decrypt_processes_list(
        processes, fields_to_decrypt=["client_phone", "client_nif"],
    )

    await enrich_processes_assignee_names(processes)
    sort_process_list(
        processes,
        sort_field=sort_field,
        sort_order=sort_order or "asc",
        status_order=status_order,
    )

    page_items, total, pages = slice_page(processes, page, size)
    await enrich_processes_portal_flags(page_items)
    await enrich_processes_latest_notes(page_items)

    return build_process_list_response(
        items=page_items,
        total=total,
        page=page,
        size=size,
        pages=pages,
        view_mode=view_mode,
    )


@router.get("/paginated")
async def get_processes_paginated(
    limit: int = Query(20, ge=1, le=100),
    cursor: Optional[str] = None,
    sort_field: str = Query("client_name", description="Campo de ordenação"),
    sort_order: str = Query("asc", description="Ordem: asc ou desc"),
    status: Optional[str] = None,
    search: Optional[str] = None,
    view_mode: Optional[str] = Query("active_only", description="Modo de visualização: active_only, all, historical"),
    user: dict = Depends(get_current_user)
):
    """
    Listar processos com paginação cursor-based (mais eficiente para grandes datasets).
    
    OTIMIZAÇÕES:
    - Projeção MongoDB: Apenas campos necessários
    - Desencriptação seletiva: Só campos sensíveis projetados
    
    FILTRO DE ESTADO ATIVO (view_mode):
    - 'active_only' (DEFAULT): Apenas processos em curso
    - 'all': Todos os processos ativos e inativos
    - 'historical': Apenas processos concluídos e desistências
    
    Args:
        limit: Número de processos por página (máximo 100)
        cursor: Cursor da página anterior
        sort_field: Campo de ordenação (created_at, updated_at, client_name)
        sort_order: Direção (asc ou desc)
        status: Filtrar por status
        search: Pesquisar por nome/email
        view_mode: Modo de visualização
    
    Returns:
        {processes, next_cursor, has_more, view_mode}
    """
    from services.cursor_pagination import CursorPaginator

    role = user["role"]

    query = build_process_list_query(
        user,
        role,
        status=status,
        search=search,
        view_mode=view_mode,
        search_mode="multiword",
    )

    order = -1 if sort_order.lower() == "desc" else 1

    paginator = CursorPaginator(
        collection=db.processes,
        default_limit=20,
        max_limit=100,
        default_sort_field="client_name",
        default_sort_order=1,
    )

    result = await paginator.paginate(
        query=query,
        limit=limit,
        cursor=cursor,
        sort_field=sort_field,
        sort_order=order,
        projection=PROCESS_LIST_PROJECTION,
    )

    result["items"] = decrypt_processes_list(
        result["items"],
        fields_to_decrypt=["client_phone", "client_nif"],
    )

    await enrich_processes_portal_flags(result["items"])
    await enrich_processes_latest_notes(result["items"])

    return build_process_cursor_list_response(result=result, view_mode=view_mode)


@router.get("/kanban/diagnose")
async def diagnose_kanban(
    user: dict = Depends(require_staff())
):
    """
    Diagnosticar problemas no endpoint do Kanban.

    Verifica cada componente que o endpoint /kanban usa:
    1. workflow_statuses (campos obrigatórios: name, id, label, color, order)
    2. processos (query base, projections)
    3. users (user_map para nomes)
    4. portal_messages (agregação unread)
    5. documents (agregação new docs)

    Retorna um relatório estruturado para diagnóstico.
    """
    return await run_kanban_diagnose()


@router.get("/kanban")
async def get_kanban_board(
    consultor_id: Optional[str] = None,
    mediador_id: Optional[str] = None,
    indexacao_id: Optional[str] = None,
    parceiro_id: Optional[str] = None,
    view_mode: Optional[str] = Query("all", description="Modo de visualização: active_only, all"),
    show_all: Optional[bool] = Query(False, description="Visão global: ignorar filtro de utilizador"),
    completed_days: Optional[int] = Query(30, description="Limitar concluídos/desistências aos últimos N dias (0 = sem limite)"),
    user: dict = Depends(require_staff())
):
    """
    Get processes organized by status for Kanban board.
    Admin/CEO see all, others see only their assigned processes.
    Supports filtering by consultor_id, mediador_id, indexacao_id, and parceiro_id.
    Supports multiple consultants and intermediaries per process.
    
    FILTRO DE ESTADO ATIVO (view_mode):
    - 'active_only': Apenas processos em curso (exclui concluídos, desistências)
    - 'all' (DEFAULT): Todos os processos (incluindo arquivo)
    
    FILTRO DE DATAS (completed_days):
    - Limita processos concluídos/desistências aos últimos N dias
    - Default: 30 dias. Use 0 para sem limite.
    """
    role = user["role"]
    user_id = user["id"]

    query = build_kanban_query(
        user,
        role,
        show_all=bool(show_all),
        consultor_id=consultor_id,
        mediador_id=mediador_id,
        indexacao_id=indexacao_id,
        parceiro_id=parceiro_id,
        view_mode=view_mode,
        completed_days=completed_days,
    )
    if role == UserRole.INDEXACAO:
        logger.info(
            f"[KANBAN-BQ] Indexacao {user_id} — vista scoped global: "
            f"atribuídos a si OU em fila_espera"
        )

    statuses = await db.workflow_statuses.find({}, {"_id": 0}).sort("order", 1).to_list(100)
    processes = await db.processes.find(query, PROCESS_KANBAN_PROJECTION).to_list(1000)
    processes = decrypt_processes_list(
        processes,
        fields_to_decrypt=["client_phone", "client_nif"],
    )

    await fill_missing_process_client_contacts(processes)
    await enrich_processes_portal_flags(processes)
    await enrich_processes_latest_activity(processes)

    users = await db.users.find({}, {"_id": 0, "id": 1, "name": 1, "role": 1}).to_list(1000)
    user_map = {u["id"]: u for u in users}

    indexacao_count = sum(1 for p in processes if p.get("assigned_indexacao_id"))
    parceiro_count = sum(1 for p in processes if p.get("assigned_parceiro_id"))
    logger.info(
        f"[Kanban Export] {len(processes)} processos: "
        f"{indexacao_count} com indexação, {parceiro_count} com parceiro"
    )

    processes_by_status = group_processes_by_status(processes)
    active_count, inactive_count = await count_kanban_active_inactive(query)
    sort_all_kanban_columns(processes_by_status)
    kanban = safe_build_kanban_columns(statuses, processes_by_status, user_map, user_id)

    return build_kanban_board_payload(
        columns=kanban,
        active_count=active_count,
        inactive_count=inactive_count,
        role=role,
        user_id=user_id,
        view_mode=view_mode,
        completed_days=completed_days,
    )


@router.get("/my-clients")
async def get_my_clients(
    request: Request,
    page: int = Query(1, ge=1, description="Número da página"),
    size: int = Query(50, ge=1, le=100, description="Itens por página"),
    user: dict = Depends(require_roles([
    UserRole.CONSULTOR, UserRole.INTERMEDIARIO, 
    UserRole.ADMIN, UserRole.CEO, UserRole.DIRETOR, UserRole.ADMINISTRATIVO,
    UserRole.INDEXACAO
]))):
    """
    Obter lista de clientes atribuídos ao utilizador atual.
    
    OTIMIZAÇÕES APLICADAS:
    - MongoDB Projection: Apenas campos necessários
    - Paginação: Não carrega todos os clientes de uma vez
    - Desencriptação seletiva: Só client_phone e client_nif
    
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
    role = get_effective_role(request, user)

    query = build_my_clients_process_query(user_id, user_email, role)

    processes = await db.processes.find(
        query,
        PROCESS_MY_CLIENTS_PROJECTION,
    ).to_list(5000)
    processes = decrypt_processes_list(
        processes,
        fields_to_decrypt=["client_phone", "client_nif"],
    )

    leads = await fetch_orphan_leads_for_my_clients(
        db, user_id, role, build_my_clients_leads_query,
    )
    status_map = await load_workflow_status_map()

    all_items = sorted(processes + leads, key=my_clients_sort_key(status_map))
    paginated_items, total, pages = slice_page(all_items, page, size)

    process_ids = process_ids_from_my_clients_page(paginated_items)
    tasks_by_process = await fetch_pending_tasks_by_process(db, process_ids)
    consultor_map = await fetch_consultor_name_map(db, paginated_items)
    unread_map = await fetch_unread_messages_map(db, process_ids)
    new_docs_map = await fetch_new_documents_map(db, process_ids)
    notes_map = await fetch_latest_activity_notes_map(db, process_ids)

    clients_list = assemble_my_clients_rows(
        paginated_items,
        status_map=status_map,
        tasks_by_process=tasks_by_process,
        consultor_map=consultor_map,
        unread_map=unread_map,
        new_docs_map=new_docs_map,
        notes_map=notes_map,
    )

    return build_my_clients_response(
        clients=clients_list,
        total=total,
        page=page,
        size=size,
        pages=pages,
        user_id=user_id,
        user_role=role,
        leads_count=len(leads),
    )


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

    if not can_view_process(user, process):
        raise HTTPException(status_code=403, detail="Sem permissão para mover este processo")

    status_exists = await db.workflow_statuses.find_one({"name": new_status})
    if not status_exists:
        raise HTTPException(status_code=400, detail="Estado inválido")

    old_status = process.get("status", "")
    flags = resolve_workflow_purpose_flags(status_exists, new_status)

    logger.info(
        f"[KANBAN-MOVE-BR] Processo {process_id} → '{new_status}'. "
        f"Flags dinâmicas: trigger_finance={flags['trigger_finance']}, "
        f"trigger_countdown={flags['trigger_countdown']}, "
        f"trigger_property_check={flags['trigger_property_check']}, "
        f"trigger_deed_reminder={flags['trigger_deed_reminder']}, "
        f"is_active={flags['is_active']}"
    )

    move_update_data = build_kanban_move_update(new_status, flags["is_active"])
    inject_cdc_context(move_update_data, user)
    await db.processes.update_one(
        {"id": process_id},
        {"$set": move_update_data},
    )

    return await run_kanban_move_side_effects(
        process=process,
        process_id=process_id,
        user=user,
        old_status=old_status,
        new_status=new_status,
        flags=flags,
        deed_date=deed_date,
        broadcast_fn=broadcast_process_delta,
        create_finance_snapshot_fn=_create_finance_snapshot,
        inject_cdc_fn=inject_cdc_context,
    )


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
    """Obtém os detalhes completos de um processo.

    FASE 2 — Refatoração relacional:
    - Lê o processo da coleção `processes`
    - Via client_id, busca os dados pessoais na coleção `clients`
    - Junta (popula) personal_data, titular2_data, financial_data
      dinamicamente na resposta para retrocompatibilidade com o Frontend

    Verifica permissões de visualização (can_view_process) antes de
    devolver os dados. Dados sensíveis (NIF, telefone, email do cliente)
    são desencriptados antes da resposta.

    Args:
        process_id: ID do processo.
        user: Utilizador autenticado (injetado).

    Returns:
        ProcessResponse: Dados completos do processo (desencriptados + cliente populado).

    Raises:
        HTTPException(404): Se processo não encontrado.
        HTTPException(403): Se utilizador não tem permissão para ver.
    """
    process = await load_process_doc_or_404(process_id)
    assert_can_view_process_or_403(user, process, can_view_process)

    process = decrypt_sensitive_data(process)
    process = await populate_client_data(process)
    ensure_client_id_default(process)
    await attach_latest_activity(process, process_id)
    await attach_portal_access(process, process_id)
    return serialize_process_detail_response(process, process_id)


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


# ====================================================================
# MARCAÇÃO DE INDEXAÇÃO CONCLUÍDA — PATCH /processes/{id}/mark-indexed
# ====================================================================

@router.post("/{process_id}/mark-indexed")
@router.patch("/{process_id}/mark-indexed")
async def mark_process_indexed(
    process_id: str,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """
    Marca o processo como tendo a indexação documental concluída (is_indexed=true).
    
    Utilizadores com role 'indexacao', 'admin' ou 'ceo' podem marcar a indexação.
    Usa o effectiveRole (X-Active-Role header) para suportar utilizadores
    com múltiplos perfis (additional_roles).
    Quando is_indexed passa a true, dispara automaticamente uma notificação
    para todos os utilizadores atribuídos ao processo (assigned_users).
    
    Body (opcional):
    - is_indexed: boolean (default true)
    """
    user_role = get_effective_role(request, user).lower()
    all_roles = get_all_user_roles(user)
    assert_mark_indexed_permission(user_role, all_roles)

    process = await db.processes.find_one(
        {"id": process_id, "is_deleted": {"$ne": True}},
        {"_id": 0},
    )
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")

    if process.get("is_indexed") is True:
        return {
            "success": True,
            "message": "Este processo já estava marcado como indexado.",
            "process_id": process_id,
            "is_indexed": True,
        }

    current_status = process.get("status", "clientes_espera")
    status_pipeline = await load_workflow_status_pipeline()
    next_status = compute_next_workflow_status(current_status, status_pipeline)

    now = datetime.now(timezone.utc).isoformat()
    update_set = build_indexacao_update_set(user, now, next_status)

    result = await db.processes.update_one(
        {"id": process_id},
        {"$set": update_set},
    )

    if result.matched_count == 0:
        logger.error(
            f"[INDEXACAO] update_one matched 0 documents para processo {process_id}"
        )
        raise HTTPException(
            status_code=404,
            detail=(
                "Processo não encontrado durante atualização. "
                "A indexação pode não ter sido persistida."
            ),
        )
    if result.modified_count == 0 and not process.get("is_indexed"):
        logger.warning(
            f"[INDEXACAO] update_one modified 0 documents para processo "
            f"{process_id} (já estava indexado?)"
        )

    return await run_mark_indexed_side_effects(
        process=process,
        process_id=process_id,
        user=user,
        current_status=current_status,
        next_status=next_status,
        now=now,
        broadcast_fn=broadcast_process_delta,
    )


@router.delete("/{process_id}")
async def delete_process(
    process_id: str,
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO, UserRole.DIRETOR, UserRole.ADMINISTRATIVO]))
):
    """Soft delete a process. Does NOT affect the client document."""
    # Find the process
    process = await db.processes.find_one(
        {"id": process_id, "is_deleted": {"$ne": True}},
        {"_id": 0}
    )
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")
    
    now = datetime.now(timezone.utc)
    
    # Soft delete the process
    # FIX (Pacote K): guardar previous_status para o endpoint de restore poder
    # recuperar o status original em vez de forçar "clientes_espera".
    await db.processes.update_one(
        {"id": process_id},
        {"$set": {
            "is_deleted": True,
            "status": "eliminado",
            "is_active": False,
            "previous_status": process.get("status"),  # para restore
            "deleted_at": now,
            "deleted_by": user.get("id", ""),
            "updated_at": now,
        }}
    )
    
    # Cascade: soft-delete documents and tasks for this process
    await db.documents.update_many(
        {"process_id": process_id, "is_deleted": {"$ne": True}},
        {"$set": {
            "deleted": True,
            "is_deleted": True,
            "deleted_at": now,
        }}
    )
    await db.tasks.update_many(
        {"process_id": process_id, "is_deleted": {"$ne": True}},
        {"$set": {
            "deleted": True,
            "is_deleted": True,
            "deleted_at": now,
        }}
    )
    
    # IMPORTANT: Do NOT touch the client document. Process deletion must be independent.
    
    # Log activity
    await db.process_activities.insert_one({
        "id": str(uuid.uuid4()),
        "process_id": process_id,
        "type": "process_deleted",
        "description": f"Processo eliminado (soft delete) por {user.get('name', 'Utilizador')}",
        "created_at": now,
        "user_id": user.get("id", ""),
        "user_name": user.get("name", ""),
    })
    
    return {"message": "Processo eliminado com sucesso", "id": process_id}


@router.put("/{process_id}", response_model=ProcessResponse)
async def update_process(process_id: str, data: ProcessUpdate, request: Request, user: dict = Depends(get_current_user)):
    """Atualiza os dados de um processo existente com controlo de acesso por role.

    FASE 2 — Refatoração relacional:
    - Dados de NEGÓCIO (status, imobiliário, crédito, atribuições) → coleção `processes`
    - Dados PESSOAIS (personal_data, titular2_data) → coleção `clients`
    - Se o Frontend envia dados pessoais no body, são extraídos e aplicados
      ao cliente via `extract_client_updates_from_body()`
    - A resposta final é populada com dados do cliente (retrocompatibilidade)

    Este endpoint implementa controlo granular de edição por role:
    - **Admin/CEO**: Podem editar todos os campos.
    - **Consultor/Diretor**: Podem editar dados pessoais, imóvel e crédito.
    - **Intermediário**: Pode editar dados financeiros e de crédito.
    - **Indexação**: Pode editar APENAS dados financeiros.
    - **Clientes**: Não podem editar processos por este endpoint.

    Processos em estados terminais (eliminados, desistências, concluídos)
    não podem ser editados.

    Regista alterações no histórico (CDC — Change Data Capture) para
    auditoria completa de quem mudou o quê e quando.

    Args:
        process_id: ID do processo.
        data: Campos a atualizar (ProcessUpdate).
        request: Objeto Request do FastAPI (para ler body raw).
        user: Utilizador autenticado (injetado).

    Returns:
        ProcessResponse: Processo atualizado (desencriptado + cliente populado).

    Raises:
        HTTPException(404): Se processo não encontrado.
        HTTPException(403): Se processo em estado terminal ou sem permissão.
    """
    process = await db.processes.find_one({"id": process_id}, {"_id": 0})
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")

    process = decrypt_process_doc_or_500(process, process_id, decrypt_sensitive_data)
    role = user["role"]

    raw_body = {}
    try:
        raw_body = await request.json()
    except Exception:
        pass
    raw_body, audit_reason, ai_suggested = parse_update_request_meta(raw_body)

    client_id = process.get("client_id")
    client_updates = extract_client_updates_from_body(raw_body)
    raw_client_email = raw_body.get("client_email")
    raw_client_phone = raw_body.get("client_phone")

    if client_updates and client_id:
        client_updates = prepare_encrypted_client_updates(client_updates)
        await apply_client_personal_updates_from_process_put(
            client_id, client_updates, process_id,
        )

    new_client_id = raw_body.get("client_id")
    await maybe_reassign_primary_client_with_audit(
        process=process,
        process_id=process_id,
        new_client_id=new_client_id,
        role=role,
        user=user,
        request=request,
        log_history_fn=log_history,
        log_audit_event_fn=log_audit_event,
    )

    assert_process_editable_for_role(process.get("status"), role)
    update_data = seed_update_data(
        process=process,
        client_id_before=client_id,
        new_client_id=new_client_id,
        raw_client_email=raw_client_email,
        raw_client_phone=raw_client_phone,
    )

    valid_statuses = await load_valid_workflow_status_names()
    perms = build_role_update_permissions(role)
    can_update_status = perms["can_update_status"]

    assert_cliente_owns_process(process, user)
    if role != UserRole.CLIENTE:
        await apply_staff_business_updates(
            process=process,
            process_id=process_id,
            data=data,
            raw_body=raw_body,
            update_data=update_data,
            user=user,
            request=request,
            audit_reason=audit_reason,
            ai_suggested=ai_suggested,
            perms=perms,
            valid_statuses=valid_statuses,
        )

    update_data = encrypt_process_update_payload(update_data, process_id)
    inject_cdc_context(update_data, user)
    attach_field_metadata_if_present(update_data, process, raw_body)

    await db.processes.update_one({"id": process_id}, {"$set": update_data})
    updated = await db.processes.find_one({"id": process_id}, {"_id": 0})

    await run_process_update_side_effects(
        process=process,
        process_id=process_id,
        data=data,
        updated=updated,
        user=user,
        can_update_status=can_update_status,
        broadcast_fn=broadcast_process_delta,
        ensure_finance_snapshot_fn=_ensure_finance_snapshot,
        decrypt_fn=decrypt_sensitive_data,
    )

    updated = await decrypt_and_populate_updated_process(
        updated,
        process_id,
        decrypt_fn=decrypt_sensitive_data,
        populate_fn=populate_client_data,
    )
    return build_process_response_or_500(updated, process_id)


# ====================================================================
# EMAIL AUTOMÁTICO — Atribuição de Processos
# (implementação em services/process_staff_assignment.send_assignment_email)
# ====================================================================

@router.post("/{process_id}/assign")
async def assign_process(
    process_id: str, 
    consultor_ids: Optional[str] = None,  # String separada por vírgulas ou ID único
    mediador_ids: Optional[str] = None,   # String separada por vírgulas ou ID único
    indexacao_id: Optional[str] = None,
    parceiro_id: Optional[str] = None,   # Parceiro (utilizador fantasma)
    # Parâmetros de compatibilidade (deprecated)
    consultor_id: Optional[str] = None,
    mediador_id: Optional[str] = None,
    user: dict = Depends(require_staff())
):
    """
    Atribuir consultores, intermediários, utilizador de indexação e/ou parceiro a um processo.
    
    Suporta múltiplos consultores e intermediários:
    - consultor_ids: String com IDs separados por vírgula (ex: "id1,id2,id3")
    - mediador_ids: String com IDs separados por vírgula (ex: "id1,id2,id3")
    
    O parceiro é um utilizador fantasma (sem acesso ao sistema) para fins de tracking.
    
    Mantém compatibilidade com os parâmetros antigos (consultor_id, mediador_id).
    Qualquer utilizador staff pode atribuir.
    """
    process = await db.processes.find_one({"id": process_id})
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")

    update_data, newly = await build_staff_assign_update(
        process=process,
        process_id=process_id,
        user=user,
        consultor_ids=consultor_ids,
        mediador_ids=mediador_ids,
        indexacao_id=indexacao_id,
        parceiro_id=parceiro_id,
        consultor_id=consultor_id,
        mediador_id=mediador_id,
    )

    inject_cdc_context(update_data, user)
    await db.processes.update_one({"id": process_id}, {"$set": update_data})

    await invalidate_stats_cache(user_id=user.get("id"))

    updated_process = await db.processes.find_one({"id": process_id}, {"_id": 0})
    await broadcast_process_delta(
        event_type=WSEventType.PROCESS_ASSIGNED,
        process_id=process_id,
        process_number=updated_process.get("process_number"),
        client_name=updated_process.get("client_name"),
        status=updated_process.get("status"),
        assigned_consultor_ids=updated_process.get("assigned_consultor_ids", []),
        assigned_mediador_ids=updated_process.get("assigned_mediador_ids", []),
        consultor_names=updated_process.get("consultor_names", []),
        mediador_names=updated_process.get("mediador_names", []),
        prioridade=updated_process.get("prioridade"),
        updated_at=updated_process.get("updated_at"),
    )

    client_name = process.get("client_name", "Cliente")
    process_number = process.get("process_number", "")
    schedule_assignment_emails(
        newly,
        process_id=process_id,
        client_name=client_name,
        process_number=process_number,
    )

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

    update_data, assignment_type = build_assign_me_update(process, user)
    inject_cdc_context(update_data, user)
    await db.processes.update_one({"id": process_id}, {"$set": update_data})
    await log_history(
        process_id, user, f"Atribuiu-se como {assignment_type}",
        f"assigned_{assignment_type}_ids", None, user["name"],
    )

    return {
        "success": True,
        "message": f"Atribuído como {assignment_type}",
        "assignment_type": assignment_type,
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

    update_data, removed_from = build_unassign_me_update(process, user)
    if "consultor" in removed_from:
        await log_history(
            process_id, user, "Removeu-se como consultor",
            "assigned_consultor_ids", user["name"], None,
        )
    if "intermediario" in removed_from:
        await log_history(
            process_id, user, "Removeu-se como intermediário",
            "assigned_mediador_ids", user["name"], None,
        )

    inject_cdc_context(update_data, user)
    await db.processes.update_one({"id": process_id}, {"$set": update_data})

    return {
        "success": True,
        "message": f"Removido como {', '.join(removed_from)}",
        "removed_from": removed_from,
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
        raise HTTPException(
            status_code=400,
            detail="field e choice ('ai' ou 'current') são obrigatórios",
        )

    process = await db.processes.find_one({"id": process_id}, {"_id": 0})
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")

    can_edit, reason = can_edit_process_data(user, process)
    if not can_edit:
        logger.warning(
            f"IDOR attempt: User {user.get('id')} ({user.get('role')}) "
            f"tried to resolve conflict on process {process_id}: {reason}"
        )
        raise HTTPException(
            status_code=403,
            detail=f"Não tem permissões para alterar este processo. {reason}",
        )

    now = datetime.now(timezone.utc).isoformat()
    update_data, suggestion, resolved_value = apply_ai_conflict_choice(
        ai_suggestions=process.get("ai_suggestions", []),
        field=field,
        choice=choice,
        suggestion_id=suggestion_id,
        now=now,
    )

    if choice == "ai":
        await log_history(
            process_id, user,
            f"Aceitou sugestão IA para '{field}'",
            field, suggestion.get("current"), resolved_value,
        )
    else:
        await log_history(
            process_id, user,
            f"Manteve valor actual para '{field}'",
            field, suggestion.get("suggested"), suggestion.get("current"),
        )

    inject_cdc_context(update_data, user)
    await db.processes.update_one({"id": process_id}, {"$set": update_data})

    remaining = update_data.get("ai_suggestions", [])
    return {
        "success": True,
        "message": (
            f"Conflito resolvido: "
            f"{'valor IA aceite' if choice == 'ai' else 'valor actual mantido'}"
        ),
        "field": field,
        "remaining_conflicts": len(remaining),
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
    
    # SECURITY: Verificar permissão de edição antes de processar
    can_edit, reason = can_edit_process_data(user, process)
    if not can_edit:
        logger.warning(f"IDOR attempt: User {user.get('id')} ({user.get('role')}) tried to confirm data on process {process_id}: {reason}")
        raise HTTPException(status_code=403, detail=f"Não tem permissões para alterar este processo. {reason}")
    
    # Verificar se há conflitos pendentes antes de confirmar
    ai_suggestions = process.get("ai_suggestions", [])
    if confirmed and len(ai_suggestions) > 0:
        raise HTTPException(
            status_code=400, 
            detail=f"Existem {len(ai_suggestions)} conflitos pendentes. Resolva-os antes de confirmar os dados."
        )
    
    now = datetime.now(timezone.utc).isoformat()
    confirm_update_data = {
        "is_data_confirmed": confirmed,
        "data_confirmed_at": now if confirmed else None,
        "data_confirmed_by": user["id"] if confirmed else None,
        "updated_at": now
    }
    inject_cdc_context(confirm_update_data, user)
    await db.processes.update_one(
        {"id": process_id},
        {"$set": confirm_update_data}
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

    now = datetime.now(timezone.utc).isoformat()
    update_data, current_client_ids = build_add_client_update(
        process, client, client_id, as_co_titular=as_co_titular, now=now,
    )

    inject_cdc_context(update_data, user)
    await db.processes.update_one({"id": process_id}, {"$set": update_data})

    await db.clients.update_one(
        {"id": client_id},
        {
            "$addToSet": {"process_ids": process_id},
            "$set": {"updated_at": now},
        },
    )

    await log_history(
        process_id, user,
        f"Adicionou cliente {client.get('nome')} ao processo"
        + (" como co-titular" if as_co_titular else ""),
    )

    return format_add_client_response(
        client.get("nome"),
        as_co_titular=as_co_titular,
        total_clients=len(current_client_ids),
    )


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

    now = datetime.now(timezone.utc).isoformat()
    update_data, current_client_ids = build_remove_client_update(
        process, client_id, now=now,
    )

    inject_cdc_context(update_data, user)
    await db.processes.update_one({"id": process_id}, {"$set": update_data})

    await db.clients.update_one(
        {"id": client_id},
        {
            "$pull": {"process_ids": process_id},
            "$set": {"updated_at": now},
        },
    )

    client = await db.clients.find_one({"id": client_id})
    client_name = client.get("nome") if client else client_id

    await log_history(process_id, user, f"Removeu cliente {client_name} do processo")

    return format_remove_client_response(
        client_name, total_clients=len(current_client_ids),
    )


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


# ====================================================================
# PORTAL MESSAGES — Mensagens do portal (staff side)
# ====================================================================

@router.get("/{process_id}/portal-messages/unread")
async def get_portal_messages_unread_staff(
    process_id: str,
    user: dict = Depends(get_current_user),
):
    """
    Conta mensagens não lidas do cliente para este processo (vista staff).

    Retorna o número de mensagens enviadas pelo cliente que o staff
    ainda não leu (read_by_staff=False).
    """
    await load_process_for_portal_or_404(process_id)
    count = await count_unread_client_portal_messages(process_id)
    return {"unread_count": count}


@router.get("/{process_id}/portal-messages")
async def get_portal_messages_staff(
    process_id: str,
    user: dict = Depends(get_current_user),
):
    """
    Lista mensagens do portal para este processo (vista staff).

    Retorna as últimas 100 mensagens ordenadas por data de criação
    ascendente (mais antigas primeiro). Ao listar, marca automaticamente
    as mensagens do cliente como lidas pelo staff (read_by_staff=True).
    """
    await load_process_for_portal_or_404(process_id)
    return await list_portal_messages_for_staff(process_id)


@router.post("/{process_id}/portal-messages")
async def send_portal_message_staff(
    process_id: str,
    data: dict,
    user: dict = Depends(get_current_user),
):
    """
    Envia uma mensagem do staff para o cliente via portal.

    Body:
    - content: Texto da mensagem (obrigatório)
    """
    process = await load_process_for_portal_or_404(process_id)
    content = validate_staff_portal_message_content(data.get("content", ""))
    now = datetime.now(timezone.utc).isoformat()
    message_doc = build_staff_portal_message_doc(
        process_id=process_id,
        user=user,
        content=content,
        now=now,
    )
    await insert_staff_portal_message(
        message_doc, user_email=user.get("email", ""),
    )

    await notify_team_email_portal_message(process, user, process_id)
    await notify_assigned_realtime_portal_message(process, user, process_id)
    await broadcast_staff_portal_message_ws(
        process_id=process_id,
        message_doc=message_doc,
        content=content,
        exclude_user_id=user.get("id"),
    )
    return staff_portal_message_response(message_doc)


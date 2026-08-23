"""
====================================================================
ROTAS DE GESTÃO DE PROCESSOS - CREDITOIMO
====================================================================
Endpoints REST para gestão de processos de crédito habitação
e transações imobiliárias.

A lógica de negócio está separada em serviços (process_*).

Autor: PowerCell Development Team
====================================================================
"""
import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, Query, Request

from database import db
from models.auth import UserRole
from models.process import (
    ProcessCreate, ProcessUpdate, ProcessResponse
)
from services.auth import get_current_user, require_roles, require_staff, get_effective_role, get_all_user_roles, get_active_company_id_async
from services.notification_service import send_to_admins
from services.history import log_history
from services.audit_trail_service import log_audit_event
from services.audit_cdc import inject_cdc_context
from services.alerts import get_process_alerts
from services.encryption import decrypt_client_data

from services.process_service import (
    can_view_process,
    can_edit_process_data,
    encrypt_sensitive_data,
    decrypt_sensitive_data,
    decrypt_processes_list,
    populate_client_data,
    extract_client_updates_from_body,
    PROCESS_LIST_PROJECTION,
    PROCESS_KANBAN_PROJECTION,
    PROCESS_MY_CLIENTS_PROJECTION,
)
from services.process_finance import (
    create_finance_snapshot as _create_finance_snapshot,
    ensure_finance_snapshot as _ensure_finance_snapshot,
)
from services.process_list_filters import (
    build_my_clients_process_query,
    build_my_clients_leads_query,
)
from services.process_my_clients import (
    run_get_my_clients,
)
from services.process_indexing import (
    run_mark_process_indexed,
)
from services.process_create import (
    assemble_staff_create_bundle,
    persist_and_finalize_staff_create,
    persist_and_finalize_client_self_create,
)
from services.process_detail import (
    run_get_process_detail,
    run_get_process_alerts,
)
from services.process_timeline import run_get_process_timeline
from services.process_observation_notes import (
    ObservationNoteCreate,
    run_add_observation_note,
)
from services.process_clients_nm import (
    run_add_client_to_process,
    run_remove_client_from_process,
    run_get_process_clients,
)
from services.process_portal_messages import (
    load_process_for_portal_or_404,
    count_unread_client_portal_messages,
    list_portal_messages_for_staff,
    run_send_portal_message_staff,
)
from services.process_ai_conflict import (
    resolve_ai_data_conflict,
    confirm_process_client_data,
)
from services.process_delete import soft_delete_process
from services.process_update import (
    run_update_process,
)
from services.process_broadcast import broadcast_process_delta
from services.process_kanban_enrichment import (
    run_get_kanban_board,
)
from services.process_kanban_diagnose import run_kanban_diagnose
from services.process_kanban_move import (
    run_move_process_kanban,
)
from services.process_dsti import (
    run_get_process_dsti,
    run_get_dsti_high_risk_processes,
)
from services.process_list_enrichment import (
    run_get_processes,
    run_get_processes_paginated,
    load_workflow_status_map,
    slice_page,
)
from services.process_staff_assignment import (
    run_staff_assign_process,
    run_assign_me_to_process,
    run_unassign_me_from_process,
)
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
    """Criar processo (self-service) para cliente autenticado."""
    return await persist_and_finalize_client_self_create(
        data,
        user,
        encrypt_fn=encrypt_sensitive_data,
        decrypt_fn=decrypt_sensitive_data,
        decrypt_client_fn=decrypt_client_data,
        populate_fn=populate_client_data,
        log_history_fn=log_history,
        broadcast_fn=broadcast_process_delta,
        send_to_admins_fn=send_to_admins,
        invalidate_stats_fn=invalidate_stats_cache,
        response_cls=ProcessResponse,
    )


@router.post("/create-client", response_model=ProcessResponse)
async def create_client_process(data: ProcessCreate, user: dict = Depends(get_current_user)):
    """
    Criar processo staff associado a cliente existente (client_id obrigatório).
    Intermediário fica automaticamente atribuído quando é o criador.
    """
    bundle = await assemble_staff_create_bundle(data, user)
    return await persist_and_finalize_staff_create(
        bundle,
        user,
        encrypt_fn=encrypt_sensitive_data,
        decrypt_fn=decrypt_sensitive_data,
        log_history_fn=log_history,
        broadcast_fn=broadcast_process_delta,
        response_cls=ProcessResponse,
    )

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
    is_indexed: Optional[bool] = Query(None, description="PACOTE BZ — Filtrar por estado de indexação: true=indexados, false=pendentes"),
    assigned_user_id: Optional[str] = Query(None, description="PACOTE FK — Filtrar por utilizador atribuído (legado, um ID)"),
    assigned_user_ids: Optional[List[str]] = Query(None, description="PACOTE FL — Filtrar por um ou mais utilizadores atribuídos"),
    assigned_logic: Optional[str] = Query("OR", description="PACOTE FL — AND ou OR (default OR)"),
    process_type: Optional[str] = Query(None, description="PACOTE FK — Filtrar por tipo de processo"),
    user: dict = Depends(get_current_user)
):
    """Listar processos com paginação, projeção e enriquecimento."""
    role = get_effective_role(request, user)
    return await run_get_processes(
        user=user,
        role=role,
        page=page,
        size=size,
        status=status,
        search=search,
        view_mode=view_mode,
        sort_field=sort_field,
        sort_order=sort_order,
        show_all=bool(show_all),
        is_indexed=is_indexed,
        all_roles=get_all_user_roles(user) if role == "__all_roles__" else None,
        decrypt_list_fn=decrypt_processes_list,
        list_projection=PROCESS_LIST_PROJECTION,
        assigned_user_id=assigned_user_id,
        assigned_user_ids=assigned_user_ids,
        assigned_logic=assigned_logic,
        process_type=process_type,
    )


@router.get("/me")
async def get_my_processes(
    request: Request,
    page: int = Query(1, ge=1, description="Número da página"),
    size: int = Query(20, ge=1, le=100, description="Itens por página"),
    status: Optional[str] = Query(None, description="Filtrar por status"),
    search: Optional[str] = Query(None, description="Pesquisar por nome/email"),
    view_mode: Optional[str] = Query("active_only", description="Modo de visualização: active_only, all, historical"),
    sort_field: Optional[str] = Query(None, description="Campo de ordenação"),
    sort_order: Optional[str] = Query("asc", description="Ordem: asc ou desc"),
    is_indexed: Optional[bool] = Query(None, description="Filtrar por estado de indexação"),
    assigned_user_id: Optional[str] = Query(None, description="PACOTE FK — Filtrar por utilizador atribuído"),
    assigned_user_ids: Optional[List[str]] = Query(None, description="PACOTE FL — Filtrar por um ou mais utilizadores atribuídos"),
    assigned_logic: Optional[str] = Query("OR", description="PACOTE FL — AND ou OR (default OR)"),
    process_type: Optional[str] = Query(None, description="PACOTE FK — Filtrar por tipo de processo"),
    user: dict = Depends(get_current_user),
):
    """
    PACOTE DU / DV — Os Meus Processos.

    Filtro estrito: assigned_to / assigned_* == user_id E
    company_id == active_company_id, mesmo quando a role activa é
    diretor (ou admin/ceo). A visão global continua em
    GET /processes?show_all=true.
    """
    role = get_effective_role(request, user)
    try:
        active_company_id = await get_active_company_id_async(request, user)
    except Exception:
        active_company_id = user.get("company")
    return await run_get_processes(
        user=user,
        role=role,
        page=page,
        size=size,
        status=status,
        search=search,
        view_mode=view_mode,
        sort_field=sort_field,
        sort_order=sort_order,
        show_all=False,
        is_indexed=is_indexed,
        all_roles=None,
        decrypt_list_fn=decrypt_processes_list,
        list_projection=PROCESS_LIST_PROJECTION,
        mine_only=True,
        company_id=active_company_id,
        assigned_user_id=assigned_user_id,
        assigned_user_ids=assigned_user_ids,
        assigned_logic=assigned_logic,
        process_type=process_type,
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
    assigned_user_id: Optional[str] = Query(None, description="PACOTE FK — Filtrar por utilizador atribuído"),
    assigned_user_ids: Optional[List[str]] = Query(None, description="PACOTE FL — Filtrar por um ou mais utilizadores atribuídos"),
    assigned_logic: Optional[str] = Query("OR", description="PACOTE FL — AND ou OR (default OR)"),
    process_type: Optional[str] = Query(None, description="PACOTE FK — Filtrar por tipo de processo"),
    user: dict = Depends(get_current_user)
):
    """Listar processos com paginação cursor-based."""
    return await run_get_processes_paginated(
        user=user,
        role=user["role"],
        limit=limit,
        cursor=cursor,
        sort_field=sort_field,
        sort_order=sort_order,
        status=status,
        search=search,
        view_mode=view_mode,
        decrypt_list_fn=decrypt_processes_list,
        list_projection=PROCESS_LIST_PROJECTION,
        assigned_user_id=assigned_user_id,
        assigned_user_ids=assigned_user_ids,
        assigned_logic=assigned_logic,
        process_type=process_type,
    )


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
    """Kanban por status com filtros de assignee / view_mode / completed_days."""
    return await run_get_kanban_board(
        user=user,
        role=user["role"],
        show_all=bool(show_all),
        consultor_id=consultor_id,
        mediador_id=mediador_id,
        indexacao_id=indexacao_id,
        parceiro_id=parceiro_id,
        view_mode=view_mode,
        completed_days=completed_days,
        decrypt_list_fn=decrypt_processes_list,
        kanban_projection=PROCESS_KANBAN_PROJECTION,
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
    """Lista clientes/processos atribuídos ao utilizador (com leads órfãos)."""
    return await run_get_my_clients(
        db=db,
        user=user,
        role=get_effective_role(request, user),
        page=page,
        size=size,
        decrypt_list_fn=decrypt_processes_list,
        my_clients_projection=PROCESS_MY_CLIENTS_PROJECTION,
        build_process_query_fn=build_my_clients_process_query,
        build_leads_query_fn=build_my_clients_leads_query,
        slice_page_fn=slice_page,
        load_status_map_fn=load_workflow_status_map,
    )


@router.put("/kanban/{process_id}/move")
async def move_process_kanban(
    process_id: str,
    new_status: str = Query(..., description="New status name"),
    deed_date: Optional[str] = Query(None, description="Data da escritura (YYYY-MM-DD)"),
    user: dict = Depends(require_staff())
):
    """Move processo no Kanban e dispara alertas/side-effects."""
    return await run_move_process_kanban(
        process_id,
        new_status,
        user,
        deed_date=deed_date,
        can_view_fn=can_view_process,
        inject_cdc_fn=inject_cdc_context,
        broadcast_fn=broadcast_process_delta,
        create_finance_snapshot_fn=_create_finance_snapshot,
    )


@router.get("/dsti/{process_id}")
async def get_process_dsti(
    process_id: str,
    user: dict = Depends(get_current_user)
):
    """Calcula DSTI automático de um processo."""
    return await run_get_process_dsti(
        process_id, user, can_view_fn=can_view_process,
    )


@router.get("/dsti-alerts")
async def get_dsti_high_risk_processes(
    user: dict = Depends(get_current_user)
):
    """Lista processos com DSTI acima do limiar configurado."""
    return await run_get_dsti_high_risk_processes()


@router.get("/{process_id}", response_model=ProcessResponse)
async def get_process(process_id: str, user: dict = Depends(get_current_user)):
    """Detalhe do processo (desencriptado + cliente + portal_access)."""
    return await run_get_process_detail(
        process_id,
        user,
        can_view_fn=can_view_process,
        decrypt_fn=decrypt_sensitive_data,
        populate_fn=populate_client_data,
    )


@router.post("/{process_id}/observation-notes")
async def add_observation_note(
    process_id: str,
    data: ObservationNoteCreate,
    user: dict = Depends(require_staff()),
):
    """PACOTE DU — acrescenta uma nota ao feed de Observações."""
    return await run_add_observation_note(
        process_id,
        data,
        user,
        can_view_fn=can_view_process,
        can_edit_fn=can_edit_process_data,
        log_history_fn=log_history,
        populate_fn=populate_client_data,
        decrypt_fn=decrypt_sensitive_data,
    )


@router.get("/{process_id}/alerts")
async def get_process_alerts_endpoint(process_id: str, user: dict = Depends(get_current_user)):
    """Alertas activos do processo (idade, countdown, docs)."""
    return await run_get_process_alerts(
        process_id,
        user,
        can_view_fn=can_view_process,
        get_alerts_fn=get_process_alerts,
    )


@router.get("/{process_id}/timeline")
async def get_process_timeline(
    process_id: str,
    limit: int = Query(40, ge=1, le=100),
    user: dict = Depends(get_current_user),
):
    """PACOTE DO.1 — Timeline compacta (criação + mudanças de fase + eventos)."""
    return await run_get_process_timeline(
        process_id,
        user,
        can_view_fn=can_view_process,
        limit=limit,
    )


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
    """Marca indexação documental concluída (is_indexed=true) e dispara side-effects."""
    return await run_mark_process_indexed(
        process_id,
        user,
        user_role=get_effective_role(request, user).lower(),
        all_roles=get_all_user_roles(user),
        broadcast_fn=broadcast_process_delta,
    )

@router.delete("/{process_id}")
async def delete_process(
    process_id: str,
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO, UserRole.DIRETOR, UserRole.ADMINISTRATIVO]))
):
    """Soft delete a process. Does NOT affect the client document."""
    return await soft_delete_process(process_id, user)


@router.put("/{process_id}", response_model=ProcessResponse)
async def update_process(process_id: str, data: ProcessUpdate, request: Request, user: dict = Depends(get_current_user)):
    """Atualiza processo (negócio em `processes`, pessoais em `clients`) com ACL por role + CDC."""
    return await run_update_process(
        process_id,
        data,
        request,
        user,
        decrypt_fn=decrypt_sensitive_data,
        populate_fn=populate_client_data,
        extract_client_updates_fn=extract_client_updates_from_body,
        inject_cdc_fn=inject_cdc_context,
        broadcast_fn=broadcast_process_delta,
        ensure_finance_snapshot_fn=_ensure_finance_snapshot,
        log_history_fn=log_history,
        log_audit_event_fn=log_audit_event,
        cliente_role=UserRole.CLIENTE,
    )


# ====================================================================
# EMAIL AUTOMÁTICO — Atribuição de Processos
# (implementação em services/process_staff_assignment.send_assignment_email)
# ====================================================================

@router.post("/{process_id}/assign")
async def assign_process(
    process_id: str, 
    consultor_ids: Optional[str] = None,
    mediador_ids: Optional[str] = None,
    indexacao_id: Optional[str] = None,
    parceiro_id: Optional[str] = None,
    consultor_id: Optional[str] = None,
    mediador_id: Optional[str] = None,
    user: dict = Depends(require_staff())
):
    """Atribuir consultores/intermediários/indexação/parceiro (multi-assignee)."""
    return await run_staff_assign_process(
        process_id,
        user,
        consultor_ids=consultor_ids,
        mediador_ids=mediador_ids,
        indexacao_id=indexacao_id,
        parceiro_id=parceiro_id,
        consultor_id=consultor_id,
        mediador_id=mediador_id,
        inject_cdc_fn=inject_cdc_context,
        invalidate_stats_fn=invalidate_stats_cache,
        broadcast_fn=broadcast_process_delta,
    )


@router.post("/{process_id}/assign-me")
async def assign_me_to_process(
    process_id: str,
    user: dict = Depends(require_staff())
):
    """Atribuir o utilizador actual ao processo (consultor ou mediador)."""
    return await run_assign_me_to_process(
        process_id,
        user,
        inject_cdc_fn=inject_cdc_context,
        log_history_fn=log_history,
    )


@router.post("/{process_id}/unassign-me")
async def unassign_me_from_process(
    process_id: str,
    user: dict = Depends(require_staff())
):
    """Remover o utilizador actual do processo."""
    return await run_unassign_me_from_process(
        process_id,
        user,
        inject_cdc_fn=inject_cdc_context,
        log_history_fn=log_history,
    )


@router.post("/{process_id}/resolve-conflict")
async def resolve_data_conflict(
    process_id: str,
    data: dict,
    user: dict = Depends(get_current_user)
):
    """Resolver conflito de dados extraídos pela IA (choice: ai | current)."""
    return await resolve_ai_data_conflict(
        process_id,
        data,
        user,
        can_edit_fn=can_edit_process_data,
        log_history_fn=log_history,
    )


@router.post("/{process_id}/confirm-data")
async def confirm_client_data(
    process_id: str,
    data: dict,
    user: dict = Depends(get_current_user)
):
    """Confirmar dados do cliente e bloquear extracoes automaticas de perfil pela IA."""
    return await confirm_process_client_data(
        process_id,
        data,
        user,
        can_edit_fn=can_edit_process_data,
        log_history_fn=log_history,
    )


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
    """Adicionar cliente existente ao processo (N:M)."""
    return await run_add_client_to_process(
        process_id,
        client_id,
        user,
        as_co_titular=as_co_titular,
        inject_cdc_fn=inject_cdc_context,
        log_history_fn=log_history,
    )


@router.post("/{process_id}/remove-client")
async def remove_client_from_process(
    process_id: str,
    client_id: str = Query(..., description="ID do cliente a remover"),
    user: dict = Depends(require_staff())
):
    """Remover co-titular do processo (não remove titular principal)."""
    return await run_remove_client_from_process(
        process_id,
        client_id,
        user,
        inject_cdc_fn=inject_cdc_context,
        log_history_fn=log_history,
    )


@router.get("/{process_id}/clients")
async def get_process_clients(
    process_id: str,
    user: dict = Depends(get_current_user)
):
    """Listar clientes associados ao processo."""
    return await run_get_process_clients(process_id)


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
    """Envia mensagem staff → cliente via portal."""
    return await run_send_portal_message_staff(process_id, data, user)


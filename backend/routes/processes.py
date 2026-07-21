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
    resolve_initial_workflow_status,
    assert_is_cliente_role,
    load_client_doc_or_404,
    build_client_self_process_doc,
    link_single_client_to_process,
    assemble_staff_create_bundle,
    persist_and_finalize_staff_create,
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
    resolve_workflow_purpose_flags,
    build_kanban_move_update,
    run_kanban_move_side_effects,
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


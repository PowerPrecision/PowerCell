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
from services.encryption import (
    encrypt_client_data,
    generate_nif_hash,
    generate_email_hash,
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
    LEAD_CLIENTS_PROJECTION,
    format_lead_as_my_client_row,
    finalize_lead_row,
    my_clients_sort_key,
    group_tasks_by_process,
    build_my_clients_process_row,
    fetch_unread_messages_map,
    fetch_new_documents_map,
    fetch_latest_activity_notes_map,
)
from services.process_indexing import (
    compute_next_workflow_status,
    build_indexacao_update_set,
    collect_assigned_user_ids,
)
from services.process_create import (
    resolve_initial_workflow_status,
    load_existing_client_for_process,
    build_staff_process_doc,
    apply_creator_role_assignment,
    attach_second_client_on_create,
    create_default_portal_documents,
    link_clients_after_process_create,
)
from services.process_update import (
    prepare_encrypted_client_updates,
    apply_client_personal_updates_from_process_put,
    build_role_update_permissions,
    reassign_process_primary_client,
    assert_process_editable_for_role,
    seed_update_data,
    apply_staff_business_updates,
    encrypt_process_update_payload,
    attach_field_metadata_if_present,
    run_process_update_side_effects,
)
from services.process_kanban_enrichment import (
    group_processes_by_status,
    sort_all_kanban_columns,
    build_kanban_columns,
)
from services.process_list_enrichment import (
    enrich_processes_assignee_names,
    enrich_processes_portal_flags,
    enrich_processes_latest_notes,
    enrich_processes_latest_activity,
    sort_process_list,
)
from services.process_staff_assignment import (
    build_staff_assign_update,
    build_assign_me_update,
    build_unassign_me_update,
)
from services.websocket_manager import manager, WSEventType, create_ws_message
from services.redis_cache import invalidate_stats_cache

# Portal imports
from services.portal_security import PORTAL_TOKEN_VALIDITY_DAYS
from services.portal_magic_link import (
    issue_portal_magic_link,
    ensure_portal_access_code,
    build_magic_link_email_bodies,
)

logger = logging.getLogger(__name__)


# ====================================================================
# WEBSOCKET BROADCAST HELPERS
# ====================================================================

async def broadcast_process_delta(
    event_type: str,
    process_id: str,
    process_number: int = None,
    client_name: str = None,
    status: str = None,
    old_status: str = None,
    assigned_consultor_ids: list = None,
    assigned_mediador_ids: list = None,
    consultor_names: list = None,
    mediador_names: list = None,
    priority: str = None,
    prioridade: str = None,
    process_type: str = None,
    updated_at: str = None
):
    """
    Broadcast a lightweight process delta to all connected WebSocket clients.
    
    Only sends essential fields needed for Kanban update - no heavy arrays or sensitive data.
    """
    try:
        delta = {
            "process_id": process_id,
        }
        
        # Only include non-None fields
        if process_number is not None:
            delta["process_number"] = process_number
        if client_name is not None:
            delta["client_name"] = client_name
        if status is not None:
            delta["status"] = status
        if old_status is not None:
            delta["old_status"] = old_status
        if assigned_consultor_ids is not None:
            delta["assigned_consultor_ids"] = assigned_consultor_ids
        if assigned_mediador_ids is not None:
            delta["assigned_mediador_ids"] = assigned_mediador_ids
        if consultor_names is not None:
            delta["consultor_names"] = consultor_names
        if mediador_names is not None:
            delta["mediador_names"] = mediador_names
        if priority is not None:
            delta["priority"] = priority
        if prioridade is not None:
            delta["prioridade"] = prioridade
        if process_type is not None:
            delta["process_type"] = process_type
        if updated_at is not None:
            delta["updated_at"] = updated_at
        
        message = create_ws_message(event_type, delta)
        await manager.broadcast(message)
        logger.debug(f"Broadcast {event_type} for process {process_id}")
    except Exception as e:
        logger.error(f"Error broadcasting process delta: {e}")


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


# NOTA: create_accent_insensitive_regex e build_multiword_search_filter foram
# movidas para utils/search_filters.py (importadas no topo deste módulo) para
# eliminar duplicação com routes/clients.py e routes/search.py.


# ====================================================================
# CONFIGURAÇÃO DO ROUTER
# ====================================================================
router = APIRouter(prefix="/processes", tags=["Processes"])


# ============================================================
# PACOTE CY — Helper para enviar email do Portal em background
# ============================================================
# Fire-and-forget: busca/gera portal_access_code e envia email de
# boas-vindas. Falhas são LOGADAS (logger.error) mas não propagadas.
# ============================================================
async def _send_portal_welcome_email_from_process(
    client_id: str,
    client_email: str,
    client_name: str,
) -> None:
    """Envia email de boas-vindas do Portal após criar um processo."""
    try:
        # Buscar ou gerar portal_access_code
        portal_access_code = None
        try:
            client_doc = await db.clients.find_one({"id": client_id}, {"portal_access_code": 1, "_id": 0})
            if client_doc:
                portal_access_code = client_doc.get("portal_access_code")
                if not portal_access_code:
                    from models.client import generate_portal_access_code as _gen_code
                    portal_access_code = _gen_code()
                    await db.clients.update_one(
                        {"id": client_id},
                        {"$set": {"portal_access_code": portal_access_code}}
                    )
        except Exception as e:
            logger.warning(f"[PORTAL-EMAIL] Erro ao obter/gerar portal_access_code para {client_id}: {e}")

        # Enviar email via task_queue (fallback: directo)
        from services.task_queue import task_queue
        from services.email import send_registration_confirmation

        job_id = None
        try:
            job_id = await task_queue.send_registration_email(
                client_email=client_email,
                client_name=client_name,
                portal_access_code=portal_access_code,
            )
        except Exception as tq_err:
            logger.warning(f"[PORTAL-EMAIL] Task Queue indisponível para cliente {client_id}: {tq_err}")

        if not job_id:
            logger.info(f"[PORTAL-EMAIL] A enviar email diretamente para {client_email} (client_id={client_id})")
            try:
                await send_registration_confirmation(
                    client_email=client_email,
                    client_name=client_name,
                    portal_access_code=portal_access_code,
                )
                logger.info(f"[PORTAL-EMAIL] Email enviado com sucesso para {client_email} (client_id={client_id})")
            except Exception as direct_err:
                logger.error(f"[PORTAL-EMAIL] Falha ao enviar email diretamente para {client_email} "
                             f"(client_id={client_id}): {direct_err}", exc_info=True)
    except Exception as e:
        logger.error(f"[PORTAL-EMAIL] Erro inesperado no envio do email de boas-vindas "
                     f"para {client_email} (client_id={client_id}): {e}", exc_info=True)


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
    process = await db.processes.find_one(
        {"id": process_id, "is_deleted": {"$ne": True}},
        {"_id": 0}
    )
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")

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

    return {
        "magic_link": issued["magic_link"],
        "short_id": issued["short_id"],
        "token": issued["token"],
        "process_id": process_id,
        "client_name": process.get("client_name", ""),
        "client_email": process.get("client_email", ""),
        "expires_in_days": PORTAL_TOKEN_VALIDITY_DAYS,
    }


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
    from services.email_service import send_email

    process = await db.processes.find_one(
        {"id": process_id, "is_deleted": {"$ne": True}},
        {"_id": 0}
    )
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")

    client_email = process.get("client_email", "")
    client_name = process.get("client_name", "Cliente")
    client_id = process.get("client_id", "")

    if not client_email:
        raise HTTPException(status_code=400, detail="Cliente não tem email associado")

    portal_access_code = await ensure_portal_access_code(client_id)

    issued = await issue_portal_magic_link(
        process_id=process_id,
        process=process,
        user=user,
        request=request,
    )
    magic_link = issued["magic_link"]
    short_id = issued["short_id"]

    text_body, html_body = build_magic_link_email_bodies(
        client_name=client_name,
        client_email=client_email,
        magic_link=magic_link,
        portal_access_code=portal_access_code,
    )

    try:
        await send_email(
            account_name="power",
            to_emails=[client_email],
            subject=f"Portal do Cliente — Acompanhe o seu processo ({client_name})",
            body=text_body,
            body_html=html_body,
            force_system=True,
            system_purpose="NOTIFICATIONS",
        )
    except Exception as e:
        logger.error(f"Erro ao enviar magic link email: {e}")
        raise HTTPException(status_code=500, detail="Erro ao enviar email. Tente copiar o link manualmente.")

    logger.info(
        f"Magic link enviado por email para {client_email} "
        f"(processo {process_id}, short_id: {short_id})"
    )

    return {
        "success": True,
        "message": f"Email enviado para {client_email}",
        "magic_link": magic_link,
        "short_id": short_id,
        # PACOTE DC — incluir portal_access_code no retorno para que o
        # endpoint /clients/{id}/resend-portal-access o possa devolver.
        "portal_access_code": portal_access_code,
    }


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
    # Apenas clientes podem criar processos por este endpoint
    if user["role"] != UserRole.CLIENTE:
        raise HTTPException(status_code=403, detail="Apenas clientes podem criar processos")
    
    # ── FASE 2: Validar que o client_id existe ──────────────────────────
    client_doc = await db.clients.find_one({"id": data.client_id})
    if not client_doc:
        raise HTTPException(
            status_code=404,
            detail=f"Cliente com ID '{data.client_id}' não encontrado. "
                   "O processo deve estar associado a um cliente existente."
        )
    
    # Obter o primeiro estado do workflow (Clientes em Espera)
    # PACOTE DB — Se não houver workflow_statuses, deixa vazio (None) em vez
    # de inventar "clientes_espera". Não inventar nomes de fases no código.
    first_status = await db.workflow_statuses.find_one({}, {"_id": 0}, sort=[("order", 1)])
    initial_status = first_status["name"] if first_status else None
    
    # Gerar ID único, número sequencial e timestamp
    process_id = str(uuid.uuid4())
    process_number = await get_next_process_number()
    now = datetime.now(timezone.utc).isoformat()
    
    # Desencriptar dados do cliente para popular o processo
    decrypted_client = decrypt_client_data(client_doc)
    client_name = decrypted_client.get("nome", "")
    client_email = decrypted_client.get("contacto", {}).get("email", "")
    
    # Construir documento do processo — SEM dados pessoais do cliente
    process_doc = {
        "id": process_id,
        "process_number": process_number,
        "client_id": data.client_id,
        "process_type": data.process_type,
        "status": initial_status,
        "is_active": True,
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
    
    # ── FASE 2: Atualizar process_ids do cliente ($push) ────────────────
    await db.clients.update_one(
        {"id": data.client_id},
        {
            "$addToSet": {"process_ids": process_id},
            "$set": {"updated_at": now}
        }
    )
    logger.info(f"Processo {process_id} criado e associado ao cliente {data.client_id}")

    # === PACOTE CW — Trello Mirror: criar cartão em background ===
    asyncio.create_task(sync_process_to_trello(process_doc, action="create"))

    # === CACHE INVALIDATION: Novo processo afecta KPIs ===
    await invalidate_stats_cache(user_id=user["id"])
    
    # Registar no histórico
    await log_history(process_id, user, "Criou processo")
    
    # === WEBSOCKET BROADCAST: Novo processo criado ===
    await broadcast_process_delta(
        event_type=WSEventType.PROCESS_CREATED,
        process_id=process_id,
        process_number=process_number,
        client_name=client_name,
        status=initial_status,
        process_type=data.process_type,
        updated_at=now
    )
    
    # Notificar administradores e CEO (com verificação de preferências)
    await send_to_admins(
        "Novo Processo Criado",
        f"O cliente {client_name} criou um novo processo de {data.process_type}.",
        notification_type="new_process"
    )
    
    # Desencriptar para a resposta e popular com dados do cliente (retrocompatibilidade)
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
    allowed_roles = [UserRole.ADMIN, UserRole.CEO, UserRole.CONSULTOR, UserRole.INTERMEDIARIO, UserRole.ADMINISTRATIVO, UserRole.DIRETOR]
    
    if user["role"] not in allowed_roles:
        raise HTTPException(
            status_code=403, 
            detail="Não tem permissão para criar clientes/processos."
        )
    
    # ====================================================================
    # REGRA DE NEGÓCIO: client_id é OBRIGATÓRIO
    # É proibido criar um processo sem associar a um cliente existente.
    # ====================================================================
    if not data.client_id:
        raise HTTPException(
            status_code=400,
            detail="É obrigatório associar um cliente existente para criar um processo. "
                   "Selecione um cliente na listagem antes de criar o processo."
        )

    is_lead = bool(getattr(data, 'is_lead', False))
    initial_status, _default_status = await resolve_initial_workflow_status(is_lead=is_lead)

    process_id = str(uuid.uuid4())
    process_number = await get_next_process_number()
    now = datetime.now(timezone.utc).isoformat()

    client_fields = await load_existing_client_for_process(data.client_id)
    client_id = client_fields["client_id"]
    client_name = client_fields["client_name"]
    client_email = client_fields["client_email"]
    client_phone = client_fields["client_phone"]
    client_nif = client_fields["client_nif"]

    # Dead path preserved: NIF/email create-on-fly never runs after required client_id
    existing_client = None
    if not client_id and (client_nif or client_email):
        query = []
        if client_nif:
            nif_hash = generate_nif_hash(client_nif)
            if nif_hash:
                query.append({"dados_pessoais.nif_hash": nif_hash})
            query.append({"dados_pessoais.nif": client_nif})
        if client_email:
            email_hash = generate_email_hash(client_email)
            if email_hash:
                query.append({"contacto.email_hash": email_hash})
            query.append({"contacto.email": client_email.lower()})
        existing_client = await db.clients.find_one({"$or": query})

    if existing_client:
        client_id = existing_client["id"]
        logger.info(f"Cliente existente encontrado: {client_id} - {existing_client.get('nome')}")
    elif not client_id:
        from models.client import Client, ClientContact, ClientPersonalData  # noqa: F401
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
            },
            "process_ids": [],
            "fonte": "staff_created",
            "created_at": now,
            "updated_at": now,
            "created_by": user.get("email")
        }
        new_client = encrypt_client_data(new_client)
        await db.clients.insert_one(new_client)
        logger.info(f"Novo cliente criado: {client_id} - {client_name}")

    process_doc = build_staff_process_doc(
        process_id=process_id,
        process_number=process_number,
        now=now,
        client_id=client_id,
        client_name=client_name,
        client_email=client_email,
        client_phone=client_phone,
        client_nif=client_nif,
        process_type=data.process_type,
        initial_status=initial_status,
        is_lead=is_lead,
    )

    second_client_id_for_process = await attach_second_client_on_create(
        process_doc,
        getattr(data, "second_client_id", None),
        client_id,
    )
    apply_creator_role_assignment(process_doc, user)

    process_doc = encrypt_sensitive_data(process_doc)
    await db.processes.insert_one(process_doc)

    try:
        if is_lead:
            logger.info(f"[CREATE-PROCESS] is_lead=True — a saltar auto-atribuição de indexador para processo {process_id} (Lead)")
        else:
            from services.process_assignment import assign_to_indexer
            assign_success, assign_data, assign_msg = await assign_to_indexer(process_id, update_status=False)
            if assign_success and assign_data.get("assigned"):
                logger.info(
                    f"[CREATE-PROCESS] Indexador auto-atribuído: {assign_data.get('indexacao_name')} "
                    f"para processo {process_id} (status mantém: {initial_status})"
                )
                process_doc["assigned_indexacao_id"] = assign_data.get("assigned_indexacao_id")
                process_doc["indexacao_name"] = assign_data.get("indexacao_name")
            else:
                logger.warning(
                    f"[CREATE-PROCESS] Sem indexador disponível para processo {process_id}: {assign_msg} "
                    f"(status mantém: {initial_status})"
                )
    except Exception as e:
        logger.warning(f"[CREATE-PROCESS] Erro na auto-atribuição de indexador para processo {process_id}: {e}")

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
        asyncio.create_task(_send_portal_welcome_email_from_process(
            client_id=client_id,
            client_email=client_email,
            client_name=client_name,
        ))

    await broadcast_process_delta(
        event_type=WSEventType.PROCESS_CREATED,
        process_id=process_id,
        process_number=process_number,
        client_name=client_name,
        status=initial_status,
        process_type=data.process_type,
        assigned_consultor_ids=process_doc.get("assigned_consultor_ids", []),
        assigned_mediador_ids=process_doc.get("assigned_mediador_ids", []),
        consultor_names=[user["name"]] if user["role"] in [UserRole.CONSULTOR, UserRole.DIRETOR] else [],
        mediador_names=[user["name"]] if user["role"] == UserRole.INTERMEDIARIO else [],
        updated_at=now
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

    # Query MongoDB partilhada (services/process_list_filters.py)
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

    # Calcular offset
    skip = (page - 1) * size
    
    # Buscar ordem das fases do workflow para ordenação composta
    statuses = await db.workflow_statuses.find({}, {"_id": 0}).sort("order", 1).to_list(100)
    status_order = {s["name"]: idx for idx, s in enumerate(statuses)}
    
    # BUSCAR COM PROJEÇÃO OTIMIZADA (até 5000 para ordenação Python-side)
    # Apenas campos necessários para a tabela de listagem
    processes = await db.processes.find(
        query, 
        PROCESS_LIST_PROJECTION
    ).to_list(5000)
    
    # Desencriptar apenas campos sensíveis necessários (client_phone, client_nif)
    # NOTA: personal_data e financial_data NÃO são projetados, então não precisam de desencriptação
    processes = decrypt_processes_list(processes, fields_to_decrypt=["client_phone", "client_nif"])

    await enrich_processes_assignee_names(processes)
    sort_process_list(
        processes,
        sort_field=sort_field,
        sort_order=sort_order or "asc",
        status_order=status_order,
    )

    # Total e paginação (após ordenação)
    total = len(processes)
    processes = processes[skip:skip + size]

    await enrich_processes_portal_flags(processes)
    await enrich_processes_latest_notes(processes)

    # Calcular total de páginas
    pages = (total + size - 1) // size if size > 0 else 0

    # PACOTE CZ — Removido o bloco PACOTE CJ (dead code): fazia find_one por
    # "action" field que não existe na coleção activities. A enrichação real
    # já é feita pelo batch aggregation PACOTE BT acima (latest_note +
    # latest_activity_preview alias).

    return {
        "items": processes,
        "total": total,
        "page": page,
        "size": size,
        "pages": pages,
        "view_mode": view_mode
    }


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

    # Query MongoDB partilhada (services/process_list_filters.py)
    # search_mode="multiword" preserva o comportamento anterior deste endpoint.
    query = build_process_list_query(
        user,
        role,
        status=status,
        search=search,
        view_mode=view_mode,
        search_mode="multiword",
    )

    # Converter sort_order para int
    order = -1 if sort_order.lower() == "desc" else 1
    
    # Usar paginador COM PROJEÇÃO OTIMIZADA
    paginator = CursorPaginator(
        collection=db.processes,
        default_limit=20,
        max_limit=100,
        default_sort_field="client_name",
        default_sort_order=1
    )
    
    result = await paginator.paginate(
        query=query,
        limit=limit,
        cursor=cursor,
        sort_field=sort_field,
        sort_order=order,
        projection=PROCESS_LIST_PROJECTION  # PROJEÇÃO OTIMIZADA
    )
    
    # Desencriptar APENAS campos sensíveis projetados (não todo o documento)
    result["items"] = decrypt_processes_list(
        result["items"], 
        fields_to_decrypt=["client_phone", "client_nif"]
    )

    await enrich_processes_portal_flags(result["items"])
    await enrich_processes_latest_notes(result["items"])

    return {
        "processes": result["items"],
        "next_cursor": result["next_cursor"],
        "has_more": result["has_more"],
        "limit": result["limit"],
        "view_mode": view_mode
    }


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
    import traceback
    report = {"checks": {}, "can_load": False, "blocking_issue": None}

    # ── 1. workflow_statuses ──
    try:
        statuses = await db.workflow_statuses.find({}, {"_id": 0}).sort("order", 1).to_list(100)
        report["checks"]["workflow_statuses"] = {
            "count": len(statuses),
            "items": [],
        }
        required_fields = ["name", "id", "label", "color", "order"]
        for s in statuses:
            missing = [f for f in required_fields if f not in s or s.get(f) is None]
            report["checks"]["workflow_statuses"]["items"].append({
                "name": s.get("name"),
                "id": s.get("id"),
                "has_all_fields": len(missing) == 0,
                "missing_fields": missing,
            })
        if not statuses:
            report["blocking_issue"] = "workflow_statuses está vazia — o kanban não tem colunas."
    except Exception as e:
        report["checks"]["workflow_statuses"] = {"error": str(e), "traceback": traceback.format_exc()}
        report["blocking_issue"] = f"Erro ao ler workflow_statuses: {e}"

    # ── 2. processes (contagem básica) ──
    try:
        total_processes = await db.processes.count_documents({"is_deleted": {"$ne": True}})
        active_processes = await db.processes.count_documents({
            "is_deleted": {"$ne": True},
            "status": {"$nin": ["concluidos", "desistencias", "eliminados"]},
        })
        report["checks"]["processes"] = {
            "total": total_processes,
            "active": active_processes,
        }
    except Exception as e:
        report["checks"]["processes"] = {"error": str(e)}
        if not report["blocking_issue"]:
            report["blocking_issue"] = f"Erro ao ler processes: {e}"

    # ── 3. users ──
    try:
        total_users = await db.users.count_documents({})
        report["checks"]["users"] = {"total": total_users}
    except Exception as e:
        report["checks"]["users"] = {"error": str(e)}

    # ── 4. portal_messages (testar agregação) ──
    try:
        unread_pipeline = [
            {"$match": {"sender_type": "client", "read_by_staff": False}},
            {"$group": {"_id": "$process_id", "unread_count": {"$sum": 1}}}
        ]
        unread_results = await db.portal_messages.aggregate(unread_pipeline).to_list(10)
        report["checks"]["portal_messages"] = {
            "aggregation_works": True,
            "sample_count": len(unread_results),
        }
    except Exception as e:
        report["checks"]["portal_messages"] = {"error": str(e)}

    # ── 5. documents (testar agregação) ──
    try:
        new_docs_pipeline = [
            {"$match": {"status": "uploaded"}},
            {"$group": {"_id": "$process_id", "new_count": {"$sum": 1}}}
        ]
        new_docs_results = await db.documents.aggregate(new_docs_pipeline).to_list(10)
        report["checks"]["documents"] = {
            "aggregation_works": True,
            "sample_count": len(new_docs_results),
        }
    except Exception as e:
        report["checks"]["documents"] = {"error": str(e)}

    # ── 6. Tentar executar a query do kanban isoladamente ──
    try:
        query = {"is_deleted": {"$ne": True}}
        kanban_projection = {
            "_id": 0, "id": 1, "status": 1, "client_name": 1,
            "assigned_consultor_id": 1, "updated_at": 1,
        }
        sample = await db.processes.find(query, kanban_projection).to_list(5)
        report["checks"]["kanban_query"] = {
            "works": True,
            "sample_count": len(sample),
            "sample_statuses": [p.get("status") for p in sample],
        }
    except Exception as e:
        report["checks"]["kanban_query"] = {"error": str(e), "traceback": traceback.format_exc()}
        if not report["blocking_issue"]:
            report["blocking_issue"] = f"Erro na query do kanban: {e}"

    # ── Determinar can_load ──
    ws_ok = report["checks"].get("workflow_statuses", {}).get("count", 0) > 0
    proc_ok = "error" not in report["checks"].get("processes", {})
    query_ok = report["checks"].get("kanban_query", {}).get("works", False)

    if ws_ok and proc_ok and query_ok and not report["blocking_issue"]:
        report["can_load"] = True
    elif not report["blocking_issue"]:
        report["blocking_issue"] = "Problema desconhecido — verifique os checks individuais."

    return report


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

    # Get all workflow statuses ordered
    statuses = await db.workflow_statuses.find({}, {"_id": 0}).sort("order", 1).to_list(100)
    
    # PROJEÇÃO OTIMIZADA: apenas campos necessários para o Kanban
    # Evita transferir documentos inteiros, histórico, dados financeiros, etc.
    kanban_projection = {
        "_id": 0,
        "id": 1,
        "process_number": 1,
        "client_id": 1,
        "client_name": 1,
        "client_email": 1,
        "client_phone": 1,
        "client_nif": 1,
        "status": 1,
        "priority": 1,
        "prioridade": 1,
        "under_35": 1,
        "process_type": 1,
        "property_value": 1,
        "is_indexed": 1,
        "assigned_consultor_id": 1,
        "assigned_consultor_ids": 1,
        "assigned_mediador_id": 1,
        "assigned_mediador_ids": 1,
        "assigned_indexacao_id": 1,
        "assigned_parceiro_id": 1,
        "indexacao_name": 1,
        "parceiro_name": 1,
        "consultor_name": 1,
        "mediador_name": 1,
        "created_at": 1,
        "updated_at": 1,
        "notes": 1,
        "tags": 1,
        "labels": 1,
        "co_buyers": 1,
        "compradores": 1,
    }
    processes = await db.processes.find(query, kanban_projection).to_list(1000)
    
    # Desencriptar campos sensíveis que estão na projeção (client_phone)
    # A projeção exclui personal_data, financial_data, etc. mas inclui client_phone
    processes = decrypt_processes_list(
        processes, 
        fields_to_decrypt=["client_phone", "client_nif"]
    )

    # ====================================================================
    # ENRIQUECIMENTO BATCH: client_name/client_email/client_phone
    # Processos criados no paradigma relacional (Fase 3) NÃO guardam
    # dados pessoais no documento do processo — estão na coleção clients.
    # Este passo preenche os campos em falta via batch lookup.
    # ====================================================================
    client_ids_to_fetch = set()
    for p in processes:
        if p.get("client_id") and not p.get("client_name"):
            client_ids_to_fetch.add(p["client_id"])

    client_map = {}
    if client_ids_to_fetch:
        client_docs = await db.clients.find(
            {"id": {"$in": list(client_ids_to_fetch)}},
            {"_id": 0, "id": 1, "nome": 1, "contacto": 1, "dados_pessoais": 1}
        ).to_list(len(client_ids_to_fetch))
        # Desencriptar dados dos clientes
        try:
            from services.encryption import decrypt_client_data
            client_docs = [decrypt_client_data(c) for c in client_docs]
        except Exception:
            pass  # Se não houver encriptação, dados já estão legíveis
        for c in client_docs:
            contacto = c.get("contacto") or {}
            dados_pessoais = c.get("dados_pessoais") or {}
            client_map[c["id"]] = {
                "nome": c.get("nome", ""),
                "email": contacto.get("email", ""),
                "telefone": contacto.get("telefone", ""),
                "nif": dados_pessoais.get("nif", c.get("nif", "")),
            }

    # Preencher campos em falta com setdefault (não sobrescreve valores existentes)
    for p in processes:
        cid = p.get("client_id")
        if cid and cid in client_map:
            cinfo = client_map[cid]
            p.setdefault("client_name", cinfo["nome"])
            p.setdefault("client_email", cinfo["email"])
            p.setdefault("client_phone", cinfo["telefone"])
            p.setdefault("client_nif", cinfo["nif"])

    await enrich_processes_portal_flags(processes)
    await enrich_processes_latest_activity(processes)

    users = await db.users.find({}, {"_id": 0, "id": 1, "name": 1, "role": 1}).to_list(1000)
    user_map = {u["id"]: u for u in users}

    indexacao_count = sum(1 for p in processes if p.get("assigned_indexacao_id"))
    parceiro_count = sum(1 for p in processes if p.get("assigned_parceiro_id"))
    logger.info(f"[Kanban Export] {len(processes)} processos: {indexacao_count} com indexação, {parceiro_count} com parceiro")

    processes_by_status = group_processes_by_status(processes)

    concluded_statuses = ["concluidos"]
    dropped_statuses = ["desistencias"]
    active_count_query = dict(query) if query else {}
    active_count_query["status"] = {"$nin": concluded_statuses + dropped_statuses}
    inactive_count_query = dict(query) if query else {}
    inactive_count_query["status"] = {"$in": concluded_statuses + dropped_statuses}

    import asyncio
    active_count, inactive_count = await asyncio.gather(
        db.processes.count_documents(active_count_query),
        db.processes.count_documents(inactive_count_query),
    )

    sort_all_kanban_columns(processes_by_status)

    try:
        kanban = build_kanban_columns(statuses, processes_by_status, user_map, user_id)
    except Exception as e:
        # PACOTE AY: NUCLEAR FAILSAFE — a rota do Kanban NUNCA devolve 500.
        # Em caso de qualquer exceção (KeyError, TypeError, AttributeError, etc.),
        # logar o erro mas devolver o que já foi processado (kanban parcial)
        # ou um array vazio. O frontend mostra colunas vazias em vez de erro.
        logger.exception(f"[KANBAN] Exceção capturada (failsafe): {type(e).__name__}: {e}. Devolvendo {len(kanban)} colunas processadas.")
        # NÃO fazer raise HTTPException — devolver silenciosamente

    return {
        "columns": kanban if kanban else [],
        "total_processes": active_count if 'active_count' in dir() else 0,
        "total_inactive": inactive_count if 'inactive_count' in dir() else 0,
        "user_role": role,
        "current_user_id": user_id,
        "view_mode": view_mode,
        "completed_days": completed_days
    }


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
    skip = (page - 1) * size

    processes = await db.processes.find(
        query,
        PROCESS_MY_CLIENTS_PROJECTION,
    ).to_list(5000)
    processes = decrypt_processes_list(
        processes,
        fields_to_decrypt=["client_phone", "client_nif"],
    )

    # Leads órfãos criados pelo utilizador (só consultor/intermediário)
    leads = []
    if role in [UserRole.CONSULTOR, UserRole.INTERMEDIARIO]:
        from services.encryption import decrypt_clients_list
        leads_cursor = await db.clients.find(
            build_my_clients_leads_query(user_id),
            LEAD_CLIENTS_PROJECTION,
        ).to_list(500)
        leads_cursor = decrypt_clients_list(leads_cursor)
        leads = [format_lead_as_my_client_row(lead) for lead in leads_cursor]

    statuses = await db.workflow_statuses.find({}, {"_id": 0}).sort("order", 1).to_list(100)
    status_map = {s["name"]: s for s in statuses}

    all_items = sorted(processes + leads, key=my_clients_sort_key(status_map))
    total = len(all_items)
    paginated_items = all_items[skip:skip + size]

    process_ids = [p["id"] for p in paginated_items if not p.get("is_lead")]
    tasks = await db.tasks.find(
        {"process_id": {"$in": process_ids}, "completed": {"$ne": True}},
        {"_id": 0, "id": 1, "process_id": 1, "title": 1, "priority": 1, "due_date": 1},
    ).to_list(500)
    tasks_by_process = group_tasks_by_process(tasks)

    consultor_ids = list({
        p.get("assigned_consultor_id")
        for p in paginated_items
        if p.get("assigned_consultor_id")
    })
    consultores = await db.users.find(
        {"id": {"$in": consultor_ids}},
        {"_id": 0, "id": 1, "name": 1},
    ).to_list(100)
    consultor_map = {c["id"]: c["name"] for c in consultores}

    bi_process_ids = [
        p["id"] for p in paginated_items if p.get("id") and not p.get("is_lead")
    ]
    unread_map = await fetch_unread_messages_map(db, bi_process_ids)
    new_docs_map = await fetch_new_documents_map(db, bi_process_ids)
    notes_map = await fetch_latest_activity_notes_map(db, bi_process_ids)

    clients_list = []
    for p in paginated_items:
        if p.get("is_lead"):
            clients_list.append(finalize_lead_row(p))
            continue
        clients_list.append(build_my_clients_process_row(
            p,
            status_map=status_map,
            tasks_by_process=tasks_by_process,
            consultor_map=consultor_map,
            unread_map=unread_map,
            new_docs_map=new_docs_map,
            notes_map=notes_map,
        ))

    pages = (total + size - 1) // size if size > 0 else 0
    return {
        "clients": clients_list,
        "total": total,
        "page": page,
        "size": size,
        "pages": pages,
        "user_id": user_id,
        "user_role": role,
        "leads_count": len(leads),
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

    # ==================================================================
    # PACOTE BR — DYNAMIC WORKFLOW PURPOSE FLAGS
    # ==================================================================
    # Em vez de hardcoded status strings, lemos as flags de comportamento
    # configuradas na coleção workflow_statuses. Isto dá flexibilidade total
    # ao negócio: o admin pode configurar quais estados disparam cada
    # automação sem alterar código.
    #
    # FALLBACK RETROCOMPATÍVEL: se a flag não existir no documento (instalações
    # existentes que ainda não migraram), usamos o comportamento hardcoded
    # atual para não quebrar nada. À medida que o admin configura as flags
    # no WorkflowEditor, o fallback deixa de ser usado.
    # ==================================================================
    # trigger_finance: cria snapshot financeiro (era: new_status == "concluidos")
    trigger_finance = status_exists.get("trigger_finance")
    if trigger_finance is None:
        trigger_finance = (new_status == "concluidos")

    # trigger_countdown: inicia countdown de 90 dias (era: new_status == "fase_bancaria")
    trigger_countdown = status_exists.get("trigger_countdown")
    if trigger_countdown is None:
        trigger_countdown = (new_status == "fase_bancaria")

    # trigger_property_check: verifica docs do imóvel + alerta CPCV/Escritura
    # (era: new_status in ["ch_aprovado", "fase_escritura", "escritura_agendada"])
    trigger_property_check = status_exists.get("trigger_property_check")
    if trigger_property_check is None:
        trigger_property_check = new_status in ["ch_aprovado", "fase_escritura", "escritura_agendada"]

    # trigger_deed_reminder: cria lembrete 15 dias antes da escritura
    # (era: new_status == "escritura_agendada")
    trigger_deed_reminder = status_exists.get("trigger_deed_reminder")
    if trigger_deed_reminder is None:
        trigger_deed_reminder = (new_status == "escritura_agendada")

    # is_active: determina se o processo fica ativo ou inativo
    # (era: new_status not in ["desistencias", "concluidos"])
    is_active = status_exists.get("is_active")
    if is_active is None:
        is_active = new_status not in ["desistencias", "concluidos"]

    logger.info(
        f"[KANBAN-MOVE-BR] Processo {process_id} → '{new_status}'. "
        f"Flags dinâmicas: trigger_finance={trigger_finance}, "
        f"trigger_countdown={trigger_countdown}, "
        f"trigger_property_check={trigger_property_check}, "
        f"trigger_deed_reminder={trigger_deed_reminder}, "
        f"is_active={is_active}"
    )

    # Update process — is_active dinâmico (sem lista fixa inactive_statuses)
    move_update_data = {
        "status": new_status,
        "is_active": is_active,
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    inject_cdc_context(move_update_data, user)
    await db.processes.update_one(
        {"id": process_id},
        {"$set": move_update_data}
    )

    # === PACOTE CW — Trello Mirror: mover cartão em background ===
    # O cartão é movido para a coluna correspondente ao new_status.
    # Busca o processo atualizado (tem trello_card_id) e dispara em background.
    _trello_move_proc = {**process, "status": new_status, "trello_card_id": process.get("trello_card_id")}
    asyncio.create_task(sync_process_to_trello(_trello_move_proc, action="move", new_status=new_status))

    # === CACHE INVALIDATION: Mover processo altera KPIs (concluídos/ativos/desistências) ===
    await invalidate_stats_cache(user_id=user.get("id"))
    
    # Log history
    await log_history(process_id, user, "Moveu processo", "status", old_status, new_status)
    
    # === WEBSOCKET BROADCAST: Processo movido no Kanban ===
    await broadcast_process_delta(
        event_type=WSEventType.PROCESS_STATUS_CHANGED,
        process_id=process_id,
        process_number=process.get("process_number"),
        client_name=process.get("client_name"),
        status=new_status,
        old_status=old_status,
        updated_at=datetime.now(timezone.utc).isoformat()
    )
    
    # Broadcast granular move event (for real-time Kanban sync)
    moved_message = create_ws_message(
        WSEventType.PROCESS_MOVED,
        {
            "process_id": str(process_id),
            "process_number": process.get("process_number"),
            "client_name": process.get("client_name"),
            "new_status": new_status,
            "old_status": old_status,
            "user_id": str(user.get("id", "")),
            "user_name": user.get("name", "Unknown"),
        }
    )
    # Exclude the user who made the move to avoid duplicate updates
    await manager.broadcast(moved_message, exclude_user=str(user.get("id", "")))
    
    # === SNAPSHOT FINANCEIRO: trigger_finance dinâmico (era: new_status == "concluidos") ===
    if trigger_finance:
        try:
            await _create_finance_snapshot(process, user)
        except Exception as snap_err:
            # Falha no snapshot não deve impedir a mudança de estado
            import logging as _log
            _log.getLogger(__name__).warning(
                f"Falha ao criar snapshot financeiro para processo {process_id}: {snap_err}"
            )

    # === ALERTAS AUTOMÁTICOS BASEADOS NAS FLAGS DINÂMICAS (PACOTE BR) ===

    # 1. trigger_property_check — Verificar documentos do imóvel + alerta CPCV/Escritura
    # (era: new_status in ["ch_aprovado", "fase_escritura", "escritura_agendada"])
    if trigger_property_check:
        # 1a. Verificação de docs do imóvel (era: new_status in ["ch_aprovado", "fase_escritura"])
        property_check = await check_property_documents(process)
        if property_check.get("active"):
            alerts_generated.append({
                "type": "property_docs",
                "message": property_check.get("message"),
                "details": property_check.get("details")
            })

        # 1b. Alerta de verificação de documentos para CPCV/Escritura
        await notify_cpcv_or_deed_document_check(process, new_status)
        alerts_generated.append({
            "type": "document_verification_alert",
            "message": "Alerta enviado aos envolvidos para verificação de documentos"
        })

    # 2. trigger_countdown — Iniciar countdown de 90 dias
    # (era: new_status == "fase_bancaria" and old_status != "fase_bancaria")
    if trigger_countdown and old_status != new_status:
        # Guardar data de aprovação se ainda não existir
        if not process.get("credit_data", {}).get("bank_approval_date"):
            bank_approval_data = {"credit_data.bank_approval_date": datetime.now().strftime("%Y-%m-%d")}
            inject_cdc_context(bank_approval_data, user)
            await db.processes.update_one(
                {"id": process_id},
                {"$set": bank_approval_data}
            )
        # Notificar sobre o countdown
        updated_process = await db.processes.find_one({"id": process_id}, {"_id": 0})
        await notify_pre_approval_countdown(updated_process)
        alerts_generated.append({
            "type": "countdown_started",
            "message": "Countdown de 90 dias iniciado para pré-aprovação"
        })

    # 3. trigger_deed_reminder — Criar lembrete 15 dias antes da escritura
    # (era: new_status == "escritura_agendada")
    if trigger_deed_reminder:
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
    
    # === GATILHO: Fila de espera ao mover para estado inativo (PACOTE BR) ===
    # Se o processo foi atribuído a um indexador e moveu para um estado inativo
    # (is_active == False, definido dinamicamente pela flag do workflow_status),
    # o indexador libertou um slot — verificar se há processos na fila_espera.
    # (era: new_status in ["concluidos", "desistencias"])
    if not is_active:
        try:
            from services.process_assignment import check_waitlist_for_indexer
            import asyncio as _asyncio
            assigned_indexer_id = process.get("assigned_indexacao_id")
            if assigned_indexer_id:
                _asyncio.create_task(check_waitlist_for_indexer(assigned_indexer_id))
                logger.info(
                    f"[KANBAN-MOVE-BR] Gatilho de fila de espera disparado para "
                    f"indexador {assigned_indexer_id} (processo {process_id} → {new_status}, "
                    f"is_active=False dinâmico)"
                )
        except Exception as waitlist_err:
            logger.warning(f"[KANBAN-MOVE] Erro ao verificar fila de espera: {waitlist_err}")
    
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
    process = await db.processes.find_one({"id": process_id}, {"_id": 0})
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")
    
    if not can_view_process(user, process):
        raise HTTPException(status_code=403, detail="Acesso negado")
    
    # Desencriptar dados sensíveis do processo
    process = decrypt_sensitive_data(process)
    
    # ── FASE 2: Popular dados do cliente (retrocompatibilidade) ──────────
    # Buscar cliente na coleção clients via client_id e injetar
    # personal_data, titular2_data, financial_data na resposta
    process = await populate_client_data(process)
    
    # Garantir campos obrigatórios para ProcessResponse (processos antigos
    # podem não ter client_id após a refatoração Fase 1→2)
    process.setdefault("client_id", process.get("client_id") or "")

    # ============================================================
    # PACOTE DA —latest_activity: atividade/nota mais recente do processo
    # ============================================================
    # Busca a última entrada da coleção activities ligada a este process_id.
    # O Frontend (ProcessDetailsModal) mostra isto na tab "Observações e IA"
    # para que o consultor veja a última interação registada.
    # ============================================================
    try:
        latest_act = await db.activities.find_one(
            {"process_id": process_id, "comment": {"$exists": True, "$ne": ""}},
            {"_id": 0},
            sort=[("created_at", -1)]
        )
        process["latest_activity"] = latest_act
    except Exception as e:
        logger.warning(f"[GET-PROCESS] Erro ao buscar latest_activity para {process_id}: {e}")
        process["latest_activity"] = None

    # ============================================================
    # PACOTE DC — portal_access: Código de Acesso + magic link ativo
    # ============================================================
    try:
        portal_access_code = None
        _client_id_dc = process.get("client_id")
        if _client_id_dc:
            _client_doc_dc = await db.clients.find_one(
                {"id": _client_id_dc}, {"portal_access_code": 1, "_id": 0}
            )
            if _client_doc_dc:
                portal_access_code = _client_doc_dc.get("portal_access_code")

        active_short_id = None
        active_magic_link = None
        token_doc = await db.portal_tokens.find_one(
            {"process_id": process_id},
            {"_id": 0, "short_id": 1, "created_at": 1}
        )
        if token_doc and token_doc.get("short_id"):
            active_short_id = token_doc["short_id"]
            _fe_url = os.environ.get("FRONTEND_URL", "").rstrip("/")
            if _fe_url:
                active_magic_link = f"{_fe_url}/portal/{active_short_id}"

        process["portal_access"] = {
            "portal_access_code": portal_access_code,
            "short_id": active_short_id,
            "magic_link": active_magic_link,
            "has_active_token": active_short_id is not None,
        }
    except Exception as e:
        logger.warning(f"[GET-PROCESS] Erro ao buscar portal_access para {process_id}: {e}")
        process["portal_access"] = None

    try:
        return ProcessResponse(**process)
    except Exception as e:
        logger.warning(f"Erro de validação ProcessResponse para processo {process_id}: {e}")
        # Fallback: retornar o dict diretamente (ignora response_model)
        return process


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
    # Verificar permissão — roles indexacao, admin, ceo (usar effectiveRole)
    user_role = get_effective_role(request, user).lower()
    all_roles = get_all_user_roles(user)
    if user_role not in ["indexacao", "admin", "ceo"] and not any(r in all_roles for r in ["indexacao", "admin", "ceo"]):
        raise HTTPException(
            status_code=403,
            detail="Apenas utilizadores com perfil de Indexação, Admin ou CEO podem marcar a indexação como concluída."
        )
    
    # Buscar processo
    process = await db.processes.find_one(
        {"id": process_id, "is_deleted": {"$ne": True}},
        {"_id": 0}
    )
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")
    
    # Se já está indexado, informar
    if process.get("is_indexed") is True:
        return {
            "success": True,
            "message": "Este processo já estava marcado como indexado.",
            "process_id": process_id,
            "is_indexed": True,
        }
    
    current_status = process.get("status", "clientes_espera")
    all_statuses = await db.workflow_statuses.find(
        {}, {"_id": 0}
    ).sort("order", 1).to_list(100)
    status_pipeline = [s["name"] for s in all_statuses]
    next_status = compute_next_workflow_status(current_status, status_pipeline)

    now = datetime.now(timezone.utc).isoformat()
    update_set = build_indexacao_update_set(user, now, next_status)

    result = await db.processes.update_one(
        {"id": process_id},
        {"$set": update_set}
    )
    
    # Verificar se a atualização foi persistida
    if result.matched_count == 0:
        logger.error(f"[INDEXACAO] update_one matched 0 documents para processo {process_id}")
        raise HTTPException(
            status_code=404,
            detail="Processo não encontrado durante atualização. A indexação pode não ter sido persistida."
        )
    if result.modified_count == 0 and not process.get("is_indexed"):
        logger.warning(f"[INDEXACAO] update_one modified 0 documents para processo {process_id} (já estava indexado?)")
    
    # ── Registar no histórico — Indexação concluída ──
    try:
        await log_history(
            process_id,
            user=user,
            action="INDEXACAO_CONCLUIDA",
            field="is_indexed",
            old_value="false",
            new_value="true"
        )
        # PACOTE BM — Registar também o congelamento dos dados do cliente
        await log_history(
            process_id,
            user=user,
            action="DADOS_CONFIRMADOS_INDEXACAO",
            field="is_data_confirmed",
            old_value="false",
            new_value="true"
        )
    except Exception as e:
        logger.warning(f"Erro ao registar histórico de indexação: {e}")

    # ── Registar no histórico — Salto dinâmico de estado ──
    if next_status and next_status != current_status:
        try:
            system_user = {"id": "system", "name": "Sistema", "role": "admin"}
            await log_history(
                process_id,
                user=system_user,
                action=f"Salto dinâmico: {current_status} → {next_status} (indexação concluída)",
                field="status",
                old_value=current_status,
                new_value=next_status,
            )
        except Exception as e:
            logger.warning(f"Erro ao registar histórico de salto de estado: {e}")

    # ── Registar no histórico — Limpeza do indexador ──
    if process.get("assigned_indexacao_id"):
        try:
            system_user = {"id": "system", "name": "Sistema", "role": "admin"}
            await log_history(
                process_id,
                user=system_user,
                action="Responsabilidade do indexador removida (indexação concluída)",
                field="assigned_indexacao_id",
                old_value=process.get("indexacao_name") or process.get("assigned_indexacao_id"),
                new_value=None,
            )
        except Exception as e:
            logger.warning(f"Erro ao registar histórico de limpeza do indexador: {e}")
    
    # ── Disparar notificação para utilizadores atribuídos ──
    client_name = process.get("client_name", "Cliente")
    process_number = process.get("process_number", "")
    process_ref = f"#{process_number}" if process_number else process_id[:8]
    
    # Recolher todos os IDs de utilizadores atribuídos
    assigned_ids = collect_assigned_user_ids(process)
    
    notification_message = f"A Indexação concluiu o tratamento documental do processo {process_ref} — {client_name}"
    
    for uid in assigned_ids:
        try:
            user_doc = await db.users.find_one({"id": uid}, {"name": 1, "email": 1})
            if user_doc:
                # Notificação por email (com verificação de preferências)
                await send_notification_with_preference_check(
                    user_doc.get("email"),
                    "Indexação Concluída",
                    notification_message,
                    notification_type="indexing_complete"
                )
                # Notificação in-app em tempo real
                try:
                    from services.realtime_notifications import send_realtime_notification
                    await send_realtime_notification(
                        user_id=uid,
                        title="Indexação Concluída",
                        message=notification_message,
                        notification_type="indexing_complete",
                        link=f"/process/${process_id}",
                        process_id=process_id,
                    )
                except Exception as notif_err:
                    logger.debug(f"Erro ao enviar notificação in-app para {uid}: {notif_err}")
        except Exception as e:
            logger.warning(f"Erro ao notificar utilizador {uid} sobre indexação concluída: {e}")
    
    # ── Broadcast WebSocket ──
    try:
        await broadcast_process_delta(
            event_type=WSEventType.PROCESS_UPDATED,
            process_id=process_id,
            client_name=client_name,
            status=next_status or current_status,
            old_status=current_status,
            updated_at=now,
        )
    except Exception as ws_err:
        logger.debug(f"Erro ao broadcast indexação concluída via WS: {ws_err}")
    
    logger.info(
        f"[INDEXACAO] Processo {process_ref} marcado como indexado por {user.get('email')}. "
        f"Estado: {current_status} → {next_status or current_status}. "
        f"Indexador limpo: {process.get('assigned_indexacao_id') is not None}. "
        f"Notificações enviadas para {len(assigned_ids)} utilizadores."
    )
    
    # ── Gatilho: Verificar fila de espera para o indexador ──
    # Quando o indexador marca is_indexed=true, liberta um slot na sua lista.
    # Verificar se há processos na fila_espera que possam ser atribuídos.
    try:
        from services.process_assignment import check_waitlist_for_indexer
        import asyncio
        assigned_indexer_id = process.get("assigned_indexacao_id")
        if assigned_indexer_id:
            asyncio.create_task(check_waitlist_for_indexer(assigned_indexer_id))
            logger.info(
                f"[INDEXACAO] Gatilho de fila de espera disparado para indexador {assigned_indexer_id}"
            )
        else:
            # Se não havia indexador atribuído, verificar todos os indexadores
            # (pode haver fila e algum indexador com vaga agora)
            from services.process_assignment import process_queue_for_freed_indexer
            from services.role_query import build_deep_role_query
            indexers_cursor = db.users.find(
                build_deep_role_query({"is_active": True}, role="indexacao"),
                {"_id": 0, "id": 1}
            )
            indexers = await indexers_cursor.to_list(length=100)
            for idx in indexers:
                asyncio.create_task(process_queue_for_freed_indexer(idx["id"]))
    except Exception as waitlist_err:
        logger.warning(f"[INDEXACAO] Erro ao verificar fila de espera: {waitlist_err}")

    # ==================================================================
    # DUPLA AUTO-ATRIBUIÇÃO (Conversão Pré-Registo/Lead → Pipeline)
    # ==================================================================
    # Se o processo transitou de pre_registo (ou status vazio/Lead), dispara
    # a dupla auto-atribuição (consultor + intermediário em simultâneo).
    # Caso contrário, usa a lógica de auto-atribuição de consultor apenas.
    # PACOTE DB — aceita também current_status=None (novos registos).
    consultant_result = None
    is_pre_registo_transition = (current_status in ("pre_registo", None))

    if is_pre_registo_transition:
        try:
            from services.process_assignment import dual_auto_assign_on_pre_registo_transition
            company_id = process.get("company_id")
            dual_result = await dual_auto_assign_on_pre_registo_transition(
                process_id=process_id,
                company_id=company_id,
                indexador_user_id=user.get("id"),
            )
            consultant_result = dual_result
            logger.info(
                f"[INDEXACAO-DUAL] Dupla auto-atribuição disparada (pre_registo → pipeline): "
                f"consultor={dual_result.get('consultant_name', 'N/A')}, "
                f"intermediario={dual_result.get('mediador_name', 'N/A')}"
            )
        except Exception as dual_err:
            logger.warning(
                f"[INDEXACAO-DUAL] Erro na dupla auto-atribuição: {dual_err}"
            )
    else:
        # Lógica original: auto-atribuição de consultor apenas (fallback)
        try:
            from services.process_assignment import assign_to_least_busy_consultant

            existing_consultor = (
                process.get("assigned_consultor_id")
                or process.get("consultant_id")
            )
            if not existing_consultor:
                logger.info(
                    f"[INDEXACAO-AUTOASSIGN] Processo {process_ref} sem consultor. "
                    f"A invocar auto-atribuição..."
                )
                success, data, msg = await assign_to_least_busy_consultant(process_id)
                if success:
                    consultant_result = data
                    logger.info(
                        f"[INDEXACAO-AUTOASSIGN] Auto-atribuição concluída: {msg}"
                    )
                else:
                    logger.warning(
                        f"[INDEXACAO-AUTOASSIGN] Falha na auto-atribuição: {msg}"
                    )
            else:
                logger.info(
                    f"[INDEXACAO-AUTOASSIGN] Processo {process_ref} já tem consultor "
                    f"({process.get('consultor_name') or existing_consultor}). "
                    f"A manter atribuição existente."
                )
        except Exception as assign_err:
            logger.warning(
                f"[INDEXACAO-AUTOASSIGN] Erro na auto-atribuição de consultor: {assign_err}"
            )

    return {
        "success": True,
        "message": f"Indexação do processo {process_ref} marcada como concluída.",
        "process_id": process_id,
        "is_indexed": True,
        "notified_users": len(assigned_ids),
        # Novos campos — Progressão Dinâmica
        "status_transition": {
            "from": current_status,
            "to": next_status,
        } if next_status and next_status != current_status else None,
        "indexer_cleared": process.get("assigned_indexacao_id") is not None,
        "consultant_auto_assigned": consultant_result,
        # Dupla auto-atribuição (pre_registo → pipeline)
        "dual_auto_assigned": is_pre_registo_transition,
        "assignment": consultant_result if is_pre_registo_transition else None,
        # PACOTE BM — Dados do cliente confirmados/congelados pela Indexação.
        # O Portal do Cliente lê esta flag via GET /portal/me e bloqueia a edição.
        "is_data_confirmed": True,
    }


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
    
    # Desencriptar dados existentes antes de fazer merge com dados novos
    # (sem isto, campos encriptados do DB seriam misturados com dados em claro e
    # re-encriptados na guarda, causando dupla encriptação e corrupção de dados)
    try:
        process = decrypt_sensitive_data(process)
    except Exception as e:
        logger.error(f"Erro ao desencriptar processo {process_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Erro interno ao desencriptar dados do processo: {type(e).__name__}")
    
    role = user["role"]
    
    # Extrair campos opcionais do body para auditoria (não são parte do modelo ProcessUpdate)
    audit_reason = None
    ai_suggested = False
    raw_body = {}
    try:
        raw_body = await request.json()
        audit_reason = raw_body.get("audit_reason")
        ai_suggested = bool(raw_body.get("ai_suggested", False))
    except Exception:
        pass
    
    # ── FASE 2: Extrair dados pessoais do body e aplicar ao cliente ──────
    # O Frontend ainda envia personal_data/titular2_data no PUT.
    # Extraímos esses campos e atualizamos a coleção `clients` em vez de `processes`.
    client_id = process.get("client_id")
    client_updates = extract_client_updates_from_body(raw_body)
    
    # ── Sincronizar client_email/client_phone para o processo ──
    # O Frontend envia estes campos directamente no body do PUT do processo.
    # Precisamos guardá-los no documento do processo (além de sincronizar com o cliente).
    raw_client_email = raw_body.get("client_email")
    raw_client_phone = raw_body.get("client_phone")
    
    if client_updates and client_id:
        client_updates = prepare_encrypted_client_updates(client_updates)
        await apply_client_personal_updates_from_process_put(
            client_id, client_updates, process_id,
        )
    # ── REATRIBUIÇÃO DE CLIENTE: Se o body inclui client_id diferente do actual ──
    new_client_id = raw_body.get("client_id")
    if new_client_id and new_client_id != process.get("client_id"):
        if role not in [UserRole.ADMIN, UserRole.CEO, UserRole.DIRETOR]:
            raise HTTPException(
                status_code=403,
                detail="Apenas administradores, CEO ou directores podem reatribuir o cliente de um processo."
            )

        reassign_info = await reassign_process_primary_client(
            process, process_id, new_client_id,
        )
        await log_history(
            process_id, user,
            f"Reatribuiu cliente de '{reassign_info['old_client_name']}' "
            f"para '{reassign_info['new_client_name']}'"
        )
        await log_audit_event(
            process_id, user,
            f"Reatribuiu cliente de '{reassign_info['old_client_name']}' "
            f"para '{reassign_info['new_client_name']}'",
            request=request, source="web"
        )
        logger.info(
            f"Processo {process_id} reatribuído de cliente "
            f"{reassign_info['old_client_id']} ({reassign_info['old_client_name']}) "
            f"para cliente {reassign_info['new_client_id']} "
            f"({reassign_info['new_client_name']}) por {user.get('email')}"
        )
    
    # Bloquear edição em estados terminais (admin/CEO podem corrigir concluídos).
    assert_process_editable_for_role(process.get("status"), role)

    update_data = seed_update_data(
        process=process,
        client_id_before=client_id,
        new_client_id=new_client_id,
        raw_client_email=raw_client_email,
        raw_client_phone=raw_client_phone,
    )

    valid_statuses = [
        s["name"]
        for s in await db.workflow_statuses.find({}, {"name": 1, "_id": 0}).to_list(100)
    ]
    perms = build_role_update_permissions(role)
    can_update_status = perms["can_update_status"]

    if role == UserRole.CLIENTE:
        if process.get("client_id") != user["id"]:
            raise HTTPException(status_code=403, detail="Acesso negado")
    else:
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

    try:
        updated = decrypt_sensitive_data(updated)
    except Exception as e:
        logger.error(f"Erro ao desencriptar dados do processo {process_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail="Erro interno ao desencriptar dados do processo",
        )

    updated = await populate_client_data(updated)

    try:
        return ProcessResponse(**updated)
    except Exception as e:
        logger.error(f"Erro ao serializar resposta do processo {process_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Erro interno ao serializar dados do processo: {str(e)[:200]}",
        )


# ====================================================================
# EMAIL AUTOMÁTICO — Atribuição de Processos
# ====================================================================

async def _send_assignment_email(
    newly_assigned_ids: list,
    process_id: str,
    client_name: str,
    process_number: str,
    role_label: str,
):
    """
    Envia email de notificação aos utilizadores recém-atribuídos a um processo.
    Executa de forma assíncrona e silenciosa (não bloqueia a resposta da API).
    """
    from services.email import get_base_template

    frontend_url = os.environ.get("FRONTEND_URL", "")
    process_link = f"{frontend_url}/processo/{process_id}" if frontend_url else ""

    for uid in newly_assigned_ids:
        try:
            target_user = await db.users.find_one({"id": uid}, {"email": 1, "name": 1})
            if not target_user or not target_user.get("email"):
                continue

            user_email = target_user["email"]
            user_name = target_user.get("name", "Utilizador")

            subject = f"Novo Processo Atribuído: {client_name}"

            # Corpo em texto simples (fallback)
            body_text = (
                f"Olá {user_name},\n\n"
                f"Foi-lhe atribuído um novo processo como {role_label}.\n\n"
                f"Cliente: {client_name}\n"
                f"Processo: {process_number or process_id[:8]}\n"
            )
            if process_link:
                body_text += f"\nAceda ao processo em: {process_link}\n"

            # Corpo em HTML
            link_html = ""
            if process_link:
                link_html = f"""
                <tr>
                    <td style="padding: 15px 30px; text-align: center;">
                        <a href="{process_link}" style="
                            display: inline-block;
                            background: linear-gradient(135deg, #1e3a5f, #2d5a87);
                            color: #ffffff;
                            padding: 12px 30px;
                            border-radius: 8px;
                            text-decoration: none;
                            font-weight: 600;
                            font-size: 14px;
                        ">Abrir Processo no CRM</a>
                    </td>
                </tr>"""

            content_html = f"""
            <table width="100%" cellpadding="0" cellspacing="0" style="padding: 20px 0;">
                <tr>
                    <td style="padding: 10px 30px;">
                        <p style="margin: 0 0 10px 0; font-size: 16px;">Olá <strong>{user_name}</strong>,</p>
                        <p style="margin: 0 0 20px 0; font-size: 15px; color: #555;">
                            Foi-lhe atribuído um novo processo como <strong>{role_label}</strong>.
                        </p>
                    </td>
                </tr>
                <tr>
                    <td style="padding: 15px 30px; background: #f8f9fa; border-radius: 8px;">
                        <table width="100%" cellpadding="0" cellspacing="0">
                            <tr>
                                <td style="padding: 8px 0; font-size: 14px; color: #666; width: 120px;"><strong>Cliente:</strong></td>
                                <td style="padding: 8px 0; font-size: 14px;">{client_name}</td>
                            </tr>
                            <tr>
                                <td style="padding: 8px 0; font-size: 14px; color: #666;"><strong>Processo:</strong></td>
                                <td style="padding: 8px 0; font-size: 14px;">{process_number or process_id[:8]}</td>
                            </tr>
                        </table>
                    </td>
                </tr>
                {link_html}
            </table>"""

            html_body = get_base_template(content_html, title=subject)

            await send_notification_with_preference_check(
                to_email=user_email,
                subject=subject,
                body=body_text,
                html_body=html_body,
                notification_type="process_assigned",
            )

            logger.info(f"[ASSIGN-EMAIL] Email enviado para {user_email} ({role_label}) — processo {process_id}")

        except Exception as e:
            logger.warning(f"[ASSIGN-EMAIL] Erro ao enviar email de atribuição para {uid}: {e}")


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
    if newly["consultores"]:
        asyncio.create_task(_send_assignment_email(
            newly["consultores"], process_id, client_name, process_number, "Consultor"
        ))
    if newly["mediadores"]:
        asyncio.create_task(_send_assignment_email(
            newly["mediadores"], process_id, client_name, process_number, "Intermediário"
        ))
    if newly["indexacao"]:
        asyncio.create_task(_send_assignment_email(
            newly["indexacao"], process_id, client_name, process_number, "Indexação"
        ))
    if newly["parceiro"]:
        asyncio.create_task(_send_assignment_email(
            newly["parceiro"], process_id, client_name, process_number, "Parceiro"
        ))

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
        raise HTTPException(status_code=400, detail="field e choice ('ai' ou 'current') são obrigatórios")
    
    process = await db.processes.find_one({"id": process_id}, {"_id": 0})
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")
    
    # SECURITY: Verificar permissão de edição antes de processar
    can_edit, reason = can_edit_process_data(user, process)
    if not can_edit:
        logger.warning(f"IDOR attempt: User {user.get('id')} ({user.get('role')}) tried to resolve conflict on process {process_id}: {reason}")
        raise HTTPException(status_code=403, detail=f"Não tem permissões para alterar este processo. {reason}")
    
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
    
    inject_cdc_context(update_data, user)
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
    
    inject_cdc_context(update_data, user)
    await db.processes.update_one({"id": process_id}, {"$set": update_data})
    
    # Actualizar process_ids do cliente
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

    # PACOTE BP — Se o cliente removido era o second_client_id (2º titular
    # ligado via backend), limpar também second_client_id e second_client_name
    # para manter consistência. Sem isto, o processo ficava com second_client_id
    # apontando para um cliente que já não está associado.
    if process.get("second_client_id") == client_id:
        update_data["second_client_id"] = None
        update_data["second_client_name"] = None

    # Actualizar titular2_data se necessário
    if co_buyers:
        update_data["titular2_data"] = {
            "name": co_buyers[0].get("name"),
            "email": co_buyers[0].get("email"),
            "nif": co_buyers[0].get("nif"),
            "phone": co_buyers[0].get("phone")
        }
    else:
        update_data["titular2_data"] = None
    
    inject_cdc_context(update_data, user)
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
    # Validate process exists and user has access
    process = await db.processes.find_one(
        {"id": process_id, "is_deleted": {"$ne": True}},
        {"_id": 0}
    )
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")

    try:
        count = await db.portal_messages.count_documents({
            "process_id": process_id,
            "sender_type": "client",
            "read_by_staff": False,
        })
        return {"unread_count": count}
    except Exception as e:
        logger.error(f"[PROCESS] Erro ao contar mensagens não lidas do portal: {e}")
        return {"unread_count": 0}


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
    # Validate process exists
    process = await db.processes.find_one(
        {"id": process_id, "is_deleted": {"$ne": True}},
        {"_id": 0}
    )
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")

    try:
        # Buscar últimas 100 mensagens
        messages = await db.portal_messages.find(
            {"process_id": process_id},
            {"_id": 0}
        ).sort("created_at", 1).limit(100).to_list(100)

        # Marcar mensagens do cliente como lidas pelo staff
        try:
            await db.portal_messages.update_many(
                {
                    "process_id": process_id,
                    "sender_type": "client",
                    "read_by_staff": False,
                },
                {"$set": {"read_by_staff": True}}
            )
        except Exception as e:
            logger.warning(f"[PROCESS] Erro ao marcar mensagens do portal como lidas: {e}")

        return {
            "messages": messages,
            "total": len(messages),
            "process_id": process_id,
        }
    except Exception as e:
        logger.error(f"[PROCESS] Erro ao listar mensagens do portal: {e}")
        raise HTTPException(
            status_code=500,
            detail="Erro ao carregar mensagens do portal."
        )


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
    import uuid as _uuid

    # Validate process exists
    process = await db.processes.find_one(
        {"id": process_id, "is_deleted": {"$ne": True}},
        {"_id": 0}
    )
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")

    content = data.get("content", "").strip()
    if not content:
        raise HTTPException(status_code=400, detail="A mensagem não pode estar vazia.")
    if len(content) > 5000:
        raise HTTPException(status_code=400, detail="A mensagem não pode exceder 5000 caracteres.")

    now = datetime.now(timezone.utc).isoformat()
    message_id = str(_uuid.uuid4())

    message_doc = {
        "id": message_id,
        "process_id": process_id,
        "sender_type": "staff",
        "sender_id": user.get("id", ""),
        "sender_name": user.get("name", "Staff"),
        "content": content,
        "created_at": now,
        "read_by_client": False,
        "read_by_staff": True,
    }

    try:
        await db.portal_messages.insert_one(message_doc)
        logger.info(
            f"[PROCESS] Mensagem do portal enviada por {user.get('email')} "
            f"para processo {process_id}"
        )
    except Exception as e:
        logger.error(f"[PROCESS] Erro ao enviar mensagem do portal: {e}")
        raise HTTPException(
            status_code=500,
            detail="Erro ao enviar mensagem. Tente novamente."
        )

    # ── Notificar outros membros da equipa (excluindo o remetente) ──
    await _notify_team_portal_message(process, user, process_id)

    # ── In-app notification para membros da equipa atribuídos ──
    try:
        from routes.portal import _get_all_assigned_user_ids
        assigned_ids = _get_all_assigned_user_ids(process)
        sender_id = user.get("id", "")
        process_number = process.get("process_number", "")
        process_ref = f"#{process_number}" if process_number else process_id[:8]
        
        for uid in assigned_ids:
            if uid == sender_id:
                continue  # Não notificar o remetente
            try:
                from services.realtime_notifications import send_realtime_notification
                await send_realtime_notification(
                    user_id=uid,
                    title="Nova Mensagem Interna",
                    message=f"{user.get('name', 'Staff')} enviou uma mensagem no processo {process_ref}.",
                    notification_type="portal_message",
                    link=f"/processes/{process_id}",
                    process_id=process_id,
                )
            except Exception as notif_err:
                logger.debug(f"Erro ao notificar membro {uid} sobre mensagem interna: {notif_err}")
    except Exception as e:
        logger.warning(f"Erro ao notificar equipa sobre mensagem do portal: {e}")

    # ── Broadcast para a sala WebSocket do processo ──
    try:
        ws_message = create_ws_message(WSEventType.PORTAL_MESSAGE, {
            "id": message_id,
            "process_id": process_id,
            "sender_type": "staff",
            "sender_id": user.get("id", ""),
            "sender_name": user.get("name", "Staff"),
            "content": content[:200],
            "created_at": now,
        })
        await manager.broadcast_to_room(f"process_{process_id}", ws_message, exclude_user=user.get("id"))
    except Exception as ws_err:
        logger.debug(f"Erro ao broadcast mensagem staff via WebSocket: {ws_err}")

    # Return without MongoDB _id
    return {
        "id": message_id,
        "process_id": process_id,
        "sender_type": "staff",
        "sender_id": user.get("id", ""),
        "sender_name": user.get("name", "Staff"),
        "content": content,
        "created_at": now,
        "read_by_client": False,
        "read_by_staff": True,
    }


async def _notify_team_portal_message(process: dict, sender: dict, process_id: str):
    """Notifica outros membros da equipa atribuída quando um membro envia mensagem ao cliente.
    
    O remetente NÃO recebe notificação. Apenas os outros utilizadores atribuídos.
    """
    from routes.portal import _get_all_assigned_user_ids
    
    assigned_ids = _get_all_assigned_user_ids(process)
    sender_id = sender.get("id", "")
    process_ref = process.get("process_number", process_id)
    sender_name = sender.get("name", "Membro da equipa")
    client_name = process.get("client_name", "Cliente")
    
    for uid in assigned_ids:
        if uid == sender_id:
            continue  # Não notificar o remetente
        try:
            team_user = await db.users.find_one({"id": uid}, {"name": 1, "email": 1})
            if team_user and team_user.get("email"):
                await send_notification_with_preference_check(
                    team_user["email"],
                    "Nova Mensagem no Processo",
                    f"{sender_name} enviou uma mensagem ao cliente {client_name} no processo #{process_ref}.",
                    notification_type="portal_message"
                )
        except Exception as e:
            logger.warning(f"Erro ao notificar membro {uid} sobre mensagem do portal: {e}")


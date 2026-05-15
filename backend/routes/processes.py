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
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query

from database import db
from models.auth import UserRole
from models.process import (
    ProcessType, ProcessCreate, ProcessUpdate, ProcessResponse
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
from services.trello import trello_service, status_to_trello_list, build_card_description
from services.encryption import decrypt_client_data

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
from services.websocket_manager import manager, WSEventType, create_ws_message
from services.redis_cache import invalidate_stats_cache

# Portal imports
from services.portal_security import create_client_magic_token, PORTAL_TOKEN_VALIDITY_DAYS

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

def _get_frontend_url(request: Request) -> str:
    """
    Obtém a URL base do frontend para construir links públicos.

    Prioridade:
    1. Header Referer (vem do browser do staff — é sempre o domínio correto)
    2. Env var FRONTEND_URL (configurada no deploy)
    3. Sem fallback hardcoded — levanta erro se não for possível determinar

    Isto garante que os links do portal funcionem independentemente
    do domínio onde a app está deployada (Vercel, Netlify, custom domain).
    """
    referer = request.headers.get("referer") or request.headers.get("origin")
    if referer:
        # Extrair scheme + host (ex: "https://app.powercell.pt" de "https://app.powercell.pt/processes/...")
        from urllib.parse import urlparse
        parsed = urlparse(referer)
        if parsed.scheme and parsed.netloc:
            return f"{parsed.scheme}://{parsed.netloc}"

    # Fallback para env var (sem domínio hardcoded)
    frontend_url = os.environ.get("FRONTEND_URL")
    if frontend_url:
        return frontend_url.rstrip("/")

    # Último recurso: não podemos gerar links válidos sem saber o domínio
    logger.warning(
        "[MAGIC LINK] FRONTEND_URL não configurada e sem Referer header. "
        "Configure a env var FRONTEND_URL no backend."
    )
    return ""


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
    import secrets

    process = await db.processes.find_one(
        {"id": process_id, "is_deleted": {"$ne": True}},
        {"_id": 0}
    )
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")

    # Gerar magic link JWT
    token = create_client_magic_token(process_id)

    # Gerar short_id único (8 caracteres URL-safe)
    short_id = secrets.token_urlsafe(6)[:8]

    # Guardar short_id → JWT na BD (upsert por process_id)
    await db.portal_tokens.update_one(
        {"process_id": process_id},
        {
            "$set": {
                "short_id": short_id,
                "jwt_token": token,
                "process_id": process_id,
                "created_by": user.get("email", ""),
                "updated_at": datetime.now(timezone.utc),
            },
            "$setOnInsert": {
                "created_at": datetime.now(timezone.utc),
            },
        },
        upsert=True,
    )

    # Construir URL curta (usa Referer header ou FRONTEND_URL env var)
    frontend_url = _get_frontend_url(request)
    magic_link = f"{frontend_url}/portal/{short_id}"

    logger.info(
        f"Magic link gerado por {user.get('email')} para processo {process_id} "
        f"(cliente: {process.get('client_name', 'N/A')}, short_id: {short_id})"
    )

    return {
        "magic_link": magic_link,
        "short_id": short_id,
        "token": token,
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
    import secrets
    from services.email_service import send_email

    process = await db.processes.find_one(
        {"id": process_id, "is_deleted": {"$ne": True}},
        {"_id": 0}
    )
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")

    client_email = process.get("client_email", "")
    client_name = process.get("client_name", "Cliente")

    if not client_email:
        raise HTTPException(status_code=400, detail="Cliente não tem email associado")

    # Gerar magic link JWT
    token = create_client_magic_token(process_id)

    # Gerar short_id
    short_id = secrets.token_urlsafe(6)[:8]

    # Guardar na BD
    await db.portal_tokens.update_one(
        {"process_id": process_id},
        {
            "$set": {
                "short_id": short_id,
                "jwt_token": token,
                "process_id": process_id,
                "created_by": user.get("email", ""),
                "updated_at": datetime.now(timezone.utc),
            },
            "$setOnInsert": {
                "created_at": datetime.now(timezone.utc),
            },
        },
        upsert=True,
    )

    # Construir URL curta (usa Referer header ou FRONTEND_URL env var)
    frontend_url = _get_frontend_url(request)
    magic_link = f"{frontend_url}/portal/{short_id}"

    # Enviar email ao cliente
    html_body = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
        <div style="background: #0F766E; color: white; padding: 20px; border-radius: 8px 8px 0 0;">
            <h1 style="margin: 0; font-size: 20px;">Power Precision · Crédito Habitação</h1>
        </div>
        <div style="padding: 30px; border: 1px solid #e2e8f0; border-top: none; border-radius: 0 0 8px 8px;">
            <p style="font-size: 16px; color: #1e293b;">Olá {client_name},</p>
            <p style="font-size: 14px; color: #475569;">
                O seu consultor preparou o seu portal pessoal para acompanhar o seu processo de crédito habitação.
            </p>
            <div style="text-align: center; margin: 30px 0;">
                <a href="{magic_link}" style="display: inline-block; background: #0F766E; color: white; padding: 14px 28px; border-radius: 8px; text-decoration: none; font-weight: bold; font-size: 16px;">
                    Aceder ao meu Portal
                </a>
            </div>
            <p style="font-size: 12px; color: #94a3b8; text-align: center;">
                Ou copie este link no seu navegador:<br>
                <span style="color: #64748b;">{magic_link}</span>
            </p>
            <p style="font-size: 12px; color: #94a3b8; margin-top: 20px;">
                Este link é válido por 90 dias. Se precisar de um novo link, contacte o seu consultor.
            </p>
        </div>
    </div>
    """

    text_body = (
        f"Olá {client_name},\n\n"
        f"O seu consultor preparou o seu portal pessoal para acompanhar o seu processo de crédito habitação.\n\n"
        f"Aceda ao portal através deste link:\n{magic_link}\n\n"
        f"Este link é válido por 90 dias.\n"
        f"Se precisar de um novo link, contacte o seu consultor.\n\n"
        f"Power Precision · Crédito Habitação"
    )

    try:
        await send_email(
            account_name="power",
            to_emails=[client_email],
            subject=f"Portal do Cliente — Acompanhe o seu processo ({client_name})",
            body=text_body,
            body_html=html_body,
            force_system=True,
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
    }


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
    
    # === CACHE INVALIDATION: Novo processo afecta KPIs ===
    await invalidate_stats_cache(user_id=user["id"])
    
    # Registar no histórico
    await log_history(process_id, user, "Criou processo")
    
    # === WEBSOCKET BROADCAST: Novo processo criado ===
    await broadcast_process_delta(
        event_type=WSEventType.PROCESS_CREATED,
        process_id=process_id,
        process_number=process_number,
        client_name=sanitized_client_name,
        status=initial_status,
        process_type=data.process_type,
        updated_at=now
    )
    
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
    
    # Obter o primeiro estado do workflow
    first_status = await db.workflow_statuses.find_one({}, {"_id": 0}, sort=[("order", 1)])
    initial_status = first_status["name"] if first_status else "clientes_espera"
    
    # Gerar ID único e número sequencial
    process_id = str(uuid.uuid4())
    process_number = await get_next_process_number()
    now = datetime.now(timezone.utc).isoformat()
    
    # Inicializar dados do cliente (serão preenchidos a partir do registo do cliente)
    client_name = ""
    client_email = ""
    client_phone = ""
    client_nif = None
    
    # ============================================================
    # VERIFICAR/CRIAR CLIENTE NA TABELA CLIENTS
    # Usar blind indexes para pesquisa de dados encriptados
    # ============================================================
    existing_client = None
    client_id = None

    # Se recebeu client_id, usar diretamente
    if data.client_id:
        existing_client = await db.clients.find_one({"id": data.client_id})
        if not existing_client:
            raise HTTPException(
                status_code=404,
                detail=f"Cliente com ID '{data.client_id}' não encontrado. "
                       "Verifique se o cliente existe na base de dados."
            )
        client_id = existing_client["id"]
        # Desencriptar dados do cliente existente para usar no processo
        decrypted = decrypt_client_data(existing_client)
        client_name = decrypted.get("nome", client_name)
        client_email = decrypted.get("contacto", {}).get("email", client_email) or client_email
        client_phone = decrypted.get("contacto", {}).get("telefone", client_phone) or client_phone
        nif_val = decrypted.get("dados_pessoais", {}).get("nif", "")
        if nif_val:
            client_nif = nif_val
        logger.info(f"Cliente existente usado via client_id: {client_id}")
    else:
        # Esta ramificação não deve ser alcançada devido à validação acima,
        # mas mantemos como salvaguarda.
        raise HTTPException(
            status_code=400,
            detail="É obrigatório associar um cliente existente para criar um processo."
        )

    # Se não encontrou por client_id, procurar por NIF ou email (deduplicação)
    if not client_id and (client_nif or client_email):
        query = []
        if client_nif:
            nif_hash = generate_nif_hash(client_nif)
            if nif_hash:
                query.append({"dados_pessoais.nif_hash": nif_hash})
            # Fallback para dados antigos não migrados
            query.append({"dados_pessoais.nif": client_nif})
        if client_email:
            email_hash = generate_email_hash(client_email)
            if email_hash:
                query.append({"contacto.email_hash": email_hash})
            # Fallback para dados antigos não migrados
            query.append({"contacto.email": client_email.lower()})

        existing_client = await db.clients.find_one({"$or": query})
    
    if existing_client:
        # Cliente já existe - usar o ID existente
        client_id = existing_client["id"]
        logger.info(f"Cliente existente encontrado: {client_id} - {existing_client.get('nome')}")
    else:
        # Criar novo cliente
        # RGPD: Encriptar dados sensíveis ANTES de inserir
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
            },
            "process_ids": [],  # Será atualizado após criar o processo
            "fonte": "staff_created",
            "created_at": now,
            "updated_at": now,
            "created_by": user.get("email")
        }

        # RGPD: Encriptar dados sensíveis antes de inserir
        new_client = encrypt_client_data(new_client)
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
        "real_estate_data": None,
        "credit_data": None,
        "created_at": now,
        "updated_at": now,
        "source": "staff_created"
    }
    
    # Atribuir automaticamente ao criador baseado no seu papel
    if user["role"] == UserRole.INTERMEDIARIO:
        process_doc["assigned_mediador_id"] = user["id"]
        process_doc["mediador_name"] = user["name"]
    elif user["role"] in [UserRole.CONSULTOR, UserRole.DIRETOR]:
        process_doc["assigned_consultor_id"] = user["id"]
        process_doc["consultor_name"] = user["name"]
    
    # Encriptar campos sensíveis antes de guardar
    process_doc = encrypt_sensitive_data(process_doc)
    
    # Inserir na base de dados
    await db.processes.insert_one(process_doc)
    
    # === AUTO-CRIAR DOCUMENTOS PORTAL POR DEFEITO ===
    # Criar pedidos de documentos padrão para o portal do cliente,
    # garantindo consistência entre o que o cliente vê no portal
    # e o que o staff vê nos detalhes do processo.
    try:
        from routes.portal import DEFAULT_PENDING_CATEGORIES, DOCUMENT_CATEGORY_MAP
        now_iso = datetime.now(timezone.utc).isoformat()
        default_docs = []
        for cat_key in DEFAULT_PENDING_CATEGORIES:
            default_docs.append({
                "id": str(uuid.uuid4()),
                "process_id": process_id,
                "category": cat_key,
                "label": DOCUMENT_CATEGORY_MAP.get(cat_key, {}).get("label", cat_key),
                "filename": None,
                "original_filename": None,
                "s3_key": None,
                "status": "REQUESTED",
                "notes": "",
                "source": "auto_default",
                "requested_by": user["id"],
                "requested_by_name": user.get("name", "Sistema"),
                "created_at": now_iso,
                "updated_at": now_iso,
            })
        if default_docs:
            await db.documents.insert_many(default_docs)
            logger.info(f"Criados {len(default_docs)} documentos padrão para processo {process_id}")
    except Exception as e:
        logger.warning(f"Erro ao criar documentos padrão para processo {process_id}: {e}")
    
    # === CACHE INVALIDATION: Novo processo criado por staff afecta KPIs ===
    await invalidate_stats_cache(user_id=user["id"])
    
    # Actualizar process_ids do cliente
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
    
    # === WEBSOCKET BROADCAST: Novo processo criado por staff ===
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
    
    # Sincronizar com Trello (criar cartão)
    try:
        await sync_process_to_trello(process_doc)
    except Exception as e:
        logger.warning(f"Erro ao sincronizar com Trello: {e}")
    
    # Desencriptar para a resposta
    response_doc = decrypt_sensitive_data(process_doc)
    return ProcessResponse(**{k: v for k, v in response_doc.items() if k != "_id"})


# ====================================================================
# ENDPOINTS DE LISTAGEM - OTIMIZADOS COM PROJEÇÃO E PAGINAÇÃO
# ====================================================================
# CONSTANTES DE FILTRO DE ESTADO ATIVO
# ====================================================================
# Status que representam processos terminados (não ativos)
INACTIVE_STATUSES = ["concluidos", "desistencias", "eliminados"]
# Status de processos arquivados (para histórico)
ARCHIVED_STATUSES = ["concluidos", "desistencias"]


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
    query = {}
    
    # ====================================================================
    # FILTRO DE INTEGRIDADE: is_deleted
    # Processos eliminados NUNCA aparecem nas listagens normais
    # ====================================================================
    is_admin = role in [UserRole.ADMIN, UserRole.CEO]
    if not is_admin:
        query["is_deleted"] = {"$ne": True}
    else:
        # Admins também não vêem eliminados por defeito (a menos que view_mode='deleted')
        if view_mode != "deleted":
            query["is_deleted"] = {"$ne": True}

    # Construir query baseada no papel
    # Se show_all=True (visão global), ignorar filtro por utilizador
    if show_all:
        pass  # Visão global absoluta — todos os processos para todos os roles
    elif role == "__all_roles__":
        # Context Isolation: modo "all" — combinar queries de TODOS os cargos do utilizador
        all_roles = get_all_user_roles(user)
        role_conditions = []
        for r in all_roles:
            if r == UserRole.CONSULTOR:
                role_conditions.extend([
                    {"assigned_consultor_ids": user["id"]},
                    {"assigned_consultor_id": user["id"]}
                ])
            elif r == UserRole.INTERMEDIARIO:
                role_conditions.extend([
                    {"assigned_mediador_ids": user["id"]},
                    {"assigned_mediador_id": user["id"]}
                ])
            elif r == UserRole.INDEXACAO:
                role_conditions.extend([
                    {"assigned_indexacao_id": user["id"]},
                    {"created_by": user.get("email", "")}
                ])
            elif r in [UserRole.ADMIN, UserRole.CEO, UserRole.ADMINISTRATIVO, UserRole.DIRETOR]:
                # Cargos que vêem tudo — sem condição específica
                role_conditions = []  # Reset — estes cargos não precisam de $or
                break
        if role_conditions:
            query["$or"] = role_conditions
    elif role == UserRole.CLIENTE:
        query["client_id"] = user["id"]
    elif role == UserRole.INDEXACAO:
        query["$or"] = [
            {"assigned_indexacao_id": user["id"]},
            {"created_by": user.get("email", "")}
        ]
    elif role in [UserRole.ADMIN, UserRole.CEO, UserRole.ADMINISTRATIVO, UserRole.DIRETOR]:
        pass  # Vêem todos
    elif role == UserRole.CONSULTOR:
        query["$or"] = [
            {"assigned_consultor_ids": user["id"]},
            {"assigned_consultor_id": user["id"]}
        ]
    elif role == UserRole.INTERMEDIARIO:
        query["$or"] = [
            {"assigned_mediador_ids": user["id"]},
            {"assigned_mediador_id": user["id"]}
        ]

    # ====================================================================
    # FILTRO DE ESTADO ATIVO (view_mode)
    # ====================================================================
    if view_mode == "active_only":
        # DEFAULT: Apenas processos em curso
        query["status"] = {"$nin": INACTIVE_STATUSES}
    elif view_mode == "historical":
        # Apenas processos arquivados (concluídos e desistências)
        query["status"] = {"$in": ARCHIVED_STATUSES}
    # view_mode == 'all': Não aplica filtro de status (mostra tudo exceto eliminados)

    # Adicionar filtro de status explícito (sobrepõe-se ao view_mode)
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
        if query:
            query = {"$and": [query, search_condition]}
        else:
            query = search_condition

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

    # Enriquecer com nomes de utilizadores (consultor, mediador, indexacao, parceiro)
    # Coletar todos os IDs únicos de utilizadores atribuídos (incluindo arrays)
    user_ids_to_resolve = set()
    for p in processes:
        # Single IDs
        if p.get("assigned_consultor_id"):
            user_ids_to_resolve.add(p["assigned_consultor_id"])
        if p.get("assigned_mediador_id"):
            user_ids_to_resolve.add(p["assigned_mediador_id"])
        if p.get("assigned_indexacao_id"):
            user_ids_to_resolve.add(p["assigned_indexacao_id"])
        if p.get("assigned_parceiro_id"):
            user_ids_to_resolve.add(p["assigned_parceiro_id"])
        # Array IDs (multiple consultants, mediadores)
        for cid in (p.get("assigned_consultor_ids") or []):
            user_ids_to_resolve.add(cid)
        for mid in (p.get("assigned_mediador_ids") or []):
            user_ids_to_resolve.add(mid)
    
    if user_ids_to_resolve:
        user_docs = await db.users.find(
            {"id": {"$in": list(user_ids_to_resolve)}},
            {"_id": 0, "id": 1, "name": 1}
        ).to_list(len(user_ids_to_resolve))
        user_map = {u["id"]: u.get("name", "") for u in user_docs}
        
        for p in processes:
            # Resolve consultor names — single or multiple
            if not p.get("consultor_name"):
                c_ids = list(set(
                    ([p["assigned_consultor_id"]] if p.get("assigned_consultor_id") else []) + 
                    (p.get("assigned_consultor_ids") or [])
                ))
                names = [user_map[cid] for cid in c_ids if user_map.get(cid)]
                if names:
                    p["consultor_name"] = ", ".join(names)
            
            # Resolve mediador names — single or multiple
            if not p.get("mediador_name"):
                m_ids = list(set(
                    ([p["assigned_mediador_id"]] if p.get("assigned_mediador_id") else []) + 
                    (p.get("assigned_mediador_ids") or [])
                ))
                names = [user_map[mid] for mid in m_ids if user_map.get(mid)]
                if names:
                    p["mediador_name"] = ", ".join(names)
            
            # Resolve indexacao (single only)
            if not p.get("indexacao_name") and p.get("assigned_indexacao_id"):
                p["indexacao_name"] = user_map.get(p["assigned_indexacao_id"], "")
            
            # Resolve parceiro (single only)
            if not p.get("parceiro_name") and p.get("assigned_parceiro_id"):
                p["parceiro_name"] = user_map.get(p["assigned_parceiro_id"], "")
    
    # Ordenação: usar sort_field/sort_order se fornecidos, senão ordenação padrão por workflow
    # Mapear pesos de prioridade — suporta ambos os campos (prioridade PT + priority EN)
    _priority_map = {
        "alta": 3, "high": 3,
        "media": 2, "medium": 2,
        "baixa": 1, "low": 1,
    }

    def _get_priority_weight(p):
        """Obtém o peso de prioridade de um processo (suporta campo PT e EN)."""
        return _priority_map.get(p.get("prioridade") or p.get("priority"), 0)

    if sort_field and sort_field in ("client_name", "status", "created_at", "updated_at",
                                       "priority", "property_value", "property_location",
                                       "contacto"):
        reverse = sort_order.lower() == "desc"

        if sort_field == "priority":
            # Ordenação por prioridade: apenas por peso de prioridade
            def _sort_key(p):
                return _get_priority_weight(p)
            try:
                processes.sort(key=_sort_key, reverse=reverse)
            except TypeError:
                processes.sort(key=lambda p: str(_sort_key(p)), reverse=reverse)
        else:
            # Qualquer outro campo: prioridade alta SEMPRE no topo como ordenação secundária
            # Usa ordenação estável (2 passes): 1º pelo campo principal, 2º por prioridade
            def _primary_key(p):
                if sort_field == "client_name":
                    return (p.get("client_name") or "").lower()
                elif sort_field == "status":
                    return (p.get("status") or "").lower()
                elif sort_field in ("created_at", "updated_at"):
                    return p.get(sort_field) or ""
                elif sort_field == "contacto":
                    return (p.get("client_email") or p.get("client_phone") or "").lower()
                else:
                    return p.get(sort_field) or ""

            # Passo 1: ordenar pelo campo principal (sort estável preserva ordem relativa)
            try:
                processes.sort(key=_primary_key, reverse=reverse)
            except TypeError:
                processes.sort(key=lambda p: str(_primary_key(p)), reverse=reverse)

            # Passo 2: ordenar por prioridade descendente (alta primeiro)
            # Como sort é estável, processos com mesma prioridade mantêm a ordem do passo 1
            processes.sort(key=lambda p: -_get_priority_weight(p))
    else:
        # Ordenação padrão: 1ª por prioridade (Alta>Média>Baixa), 2ª por fase do workflow, 3ª por nome
        processes.sort(key=lambda p: (
            -_get_priority_weight(p),
            status_order.get(p.get("status"), 999),
            (p.get("client_name") or "").lower()
        ))
    
    # Total e paginação (após ordenação)
    total = len(processes)
    processes = processes[skip:skip + size]
    
    # Calcular total de páginas
    pages = (total + size - 1) // size if size > 0 else 0
    
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
    query = {}
    
    # ====================================================================
    # FILTRO DE INTEGRIDADE: is_deleted
    # ====================================================================
    is_admin = role in [UserRole.ADMIN, UserRole.CEO]
    if not is_admin:
        query["is_deleted"] = {"$ne": True}
    else:
        if view_mode != "deleted":
            query["is_deleted"] = {"$ne": True}

    # Construir query baseada no papel
    if role == UserRole.CLIENTE:
        query["client_id"] = user["id"]
    elif role == UserRole.INDEXACAO:
        query["$or"] = [
            {"assigned_indexacao_id": user["id"]},
            {"created_by": user.get("email", "")}
        ]
    elif role in [UserRole.ADMIN, UserRole.CEO, UserRole.ADMINISTRATIVO, UserRole.DIRETOR]:
        pass
    elif role == UserRole.CONSULTOR:
        query["$or"] = [
            {"assigned_consultor_ids": user["id"]},
            {"assigned_consultor_id": user["id"]}
        ]
    elif role == UserRole.INTERMEDIARIO:
        query["$or"] = [
            {"assigned_mediador_ids": user["id"]},
            {"assigned_mediador_id": user["id"]}
        ]

    # ====================================================================
    # FILTRO DE ESTADO ATIVO (view_mode)
    # ====================================================================
    if view_mode == "active_only":
        query["status"] = {"$nin": INACTIVE_STATUSES}
    elif view_mode == "historical":
        query["status"] = {"$in": ARCHIVED_STATUSES}

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
    
    return {
        "processes": result["items"],
        "next_cursor": result["next_cursor"],
        "has_more": result["has_more"],
        "limit": result["limit"],
        "view_mode": view_mode
    }


@router.get("/kanban")
async def get_kanban_board(
    consultor_id: Optional[str] = None,
    mediador_id: Optional[str] = None,
    indexacao_id: Optional[str] = None,
    parceiro_id: Optional[str] = None,
    view_mode: Optional[str] = Query("active_only", description="Modo de visualização: active_only, all"),
    show_all: Optional[bool] = Query(False, description="Visão global: ignorar filtro de utilizador"),
    user: dict = Depends(require_staff())
):
    """
    Get processes organized by status for Kanban board.
    Admin/CEO see all, others see only their assigned processes.
    Supports filtering by consultor_id, mediador_id, indexacao_id, and parceiro_id.
    Supports multiple consultants and intermediaries per process.
    
    FILTRO DE ESTADO ATIVO (view_mode):
    - 'active_only' (DEFAULT): Apenas processos em curso (exclui concluídos, desistências)
    - 'all': Todos os processos (incluindo arquivo)
    """
    role = user["role"]
    user_id = user["id"]
    query = {}
    
    # ====================================================================
    # FILTRO DE INTEGRIDADE: is_deleted
    # ====================================================================
    query["is_deleted"] = {"$ne": True}
    
    # Filter by role (base visibility) - suporte a múltiplos
    # Se show_all=True (visão global), ignorar filtro por utilizador
    if not show_all:
        if role == UserRole.CONSULTOR:
            query["$or"] = [
                {"assigned_consultor_ids": user_id},
                {"assigned_consultor_id": user_id}
            ]
        elif role == UserRole.INTERMEDIARIO:
            query["$or"] = [
                {"assigned_mediador_ids": user_id},
                {"assigned_mediador_id": user_id}
            ]
        # Admin, CEO, Administrativo, Diretor, Indexação see all (no base filter)

    # Apply additional filters for ALL staff roles
    # Consultor/Mediador filters within their assigned processes; others filter globally
    filter_conditions = []
    
    if consultor_id:
        if consultor_id == "none":
            # Sem consultor atribuído
            filter_conditions.append({
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
            filter_conditions.append({
                "$or": [
                    {"assigned_consultor_ids": consultor_id},
                    {"assigned_consultor_id": consultor_id}
                ]
            })

    if mediador_id:
        if mediador_id == "none":
            # Sem mediador atribuído
            filter_conditions.append({
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
            filter_conditions.append({
                "$or": [
                    {"assigned_mediador_ids": mediador_id},
                    {"assigned_mediador_id": mediador_id}
                ]
            })

    if indexacao_id:
        if indexacao_id == "none":
            # Sem indexação atribuído
            filter_conditions.append({
                "$or": [
                    {"assigned_indexacao_id": {"$in": [None, ""]}},
                    {"assigned_indexacao_id": {"$exists": False}}
                ]
            })
        else:
            # Filtro por indexação específico
            filter_conditions.append({"assigned_indexacao_id": indexacao_id})

    if parceiro_id:
        if parceiro_id == "none":
            # Sem parceiro atribuído
            filter_conditions.append({
                "$or": [
                    {"assigned_parceiro_id": {"$in": [None, ""]}},
                    {"assigned_parceiro_id": {"$exists": False}}
                ]
            })
        else:
            # Filtro por parceiro específico
            filter_conditions.append({"assigned_parceiro_id": parceiro_id})

    # Combinar todas as condições com AND
    if filter_conditions:
        if query:
            # Se já existe uma query base (por role), combinar com os filtros
            query = {"$and": [query] + filter_conditions}
        else:
            # Se não há query base, usar os filtros diretamente
            if len(filter_conditions) == 1:
                query = filter_conditions[0]
            else:
                query = {"$and": filter_conditions}
    
    # ====================================================================
    # FILTRO DE ESTADO ATIVO (view_mode) para Kanban
    # Por defeito, o Kanban mostra apenas processos ativos (não arquivados)
    # ====================================================================
    if view_mode == "active_only":
        # Excluir concluídos e desistências do Kanban normal
        active_filter = {"status": {"$nin": INACTIVE_STATUSES}}
        if "$and" in query:
            query["$and"].append(active_filter)
        elif query:
            query = {"$and": [query, active_filter]}
        else:
            query = active_filter
    # view_mode == 'all': Mostra todos os processos (incluindo arquivo)
    
    # Get all workflow statuses ordered
    statuses = await db.workflow_statuses.find({}, {"_id": 0}).sort("order", 1).to_list(100)
    
    # PROJEÇÃO OTIMIZADA: apenas campos necessários para o Kanban
    # Evita transferir documentos inteiros, histórico, dados financeiros, etc.
    kanban_projection = {
        "_id": 0,
        "id": 1,
        "process_number": 1,
        "client_name": 1,
        "client_email": 1,
        "client_phone": 1,
        "status": 1,
        "priority": 1,
        "prioridade": 1,
        "under_35": 1,
        "process_type": 1,
        "property_value": 1,
        "assigned_consultor_id": 1,
        "assigned_consultor_ids": 1,
        "assigned_mediador_id": 1,
        "assigned_mediador_ids": 1,
        "assigned_indexacao_id": 1,
        "assigned_parceiro_id": 1,
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
        fields_to_decrypt=["client_phone"]
    )
    
    # Get all users for name lookup (projection mínima)
    users = await db.users.find({}, {"_id": 0, "id": 1, "name": 1, "role": 1}).to_list(1000)
    user_map = {u["id"]: u for u in users}
    
    # Organize by status - usando dict para lookup O(1) em vez de O(n) por coluna
    processes_by_status = {}
    for p in processes:
        s = p.get("status", "")
        if s not in processes_by_status:
            processes_by_status[s] = []
        processes_by_status[s].append(p)
    
    # Contagens otimizadas com count_documents em vez de len(list)
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
    
    # Ordenar processos dentro de cada coluna: 1ª por prioridade (Alta>Média>Baixa), 2ª por updated_at
    PRIORITY_WEIGHT = {"alta": 3, "media": 2, "baixa": 1}
    for status_key in processes_by_status:
        # Two-step stable sort: first by updated_at DESC, then by priority DESC
        # This ensures processes with same priority are sorted by most recent first
        processes_by_status[status_key].sort(key=lambda p: p.get("updated_at") or "", reverse=True)
        processes_by_status[status_key].sort(key=lambda p: -PRIORITY_WEIGHT.get(p.get("prioridade") or p.get("priority"), 0))
    
    kanban = []
    for status in statuses:
        status_processes = processes_by_status.get(status["name"], [])
        
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
                "my_role_in_process": "consultor" if is_my_consultor else ("intermediario" if is_my_mediador else None)
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
        "total_processes": active_count,
        "total_inactive": inactive_count,
        "user_role": role,
        "current_user_id": user_id
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
    
    # Construir query baseada no papel do utilizador
    if role == UserRole.CONSULTOR:
        query = {
            "$or": [
                {"assigned_consultor_ids": user_id},
                {"assigned_consultor_id": user_id}
            ]
        }
    elif role == UserRole.INTERMEDIARIO:
        query = {
            "$or": [
                {"assigned_mediador_ids": user_id},
                {"assigned_mediador_id": user_id},
                {"created_by": user_email}
            ]
        }
    elif role == UserRole.INDEXACAO:
        query = {
            "$or": [
                {"assigned_indexacao_id": user_id},
                {"created_by": user_email}
            ]
        }
    else:
        query = {}
    
    # Calcular offset
    skip = (page - 1) * size
    
    # Buscar processos COM PROJEÇÃO OTIMIZADA (até 5000 para ordenação Python-side)
    processes = await db.processes.find(
        query,
        PROCESS_MY_CLIENTS_PROJECTION
    ).to_list(5000)
    
    # Desencriptar APENAS campos sensíveis projetados
    processes = decrypt_processes_list(
        processes, 
        fields_to_decrypt=["client_phone", "client_nif"]
    )
    
    # Obter labels das fases do workflow ordenadas
    statuses = await db.workflow_statuses.find({}, {"_id": 0}).sort("order", 1).to_list(100)
    status_map = {s["name"]: s for s in statuses}
    
    # Ordenar processos por fase (order do status) e depois por nome
    def get_sort_key(p):
        """Gera chave de ordenação para processos.

        Ordena primeiro pela ordem da fase no workflow (phase_order),
        depois por nome do cliente em ordem alfabética. Isto garante
        que processos na mesma fase apareçam ordenados por nome.

        Args:
            p: Dicionário do processo.

        Returns:
            tuple: (phase_order, client_name_lower).
        """
        status_info = status_map.get(p.get("status"), {})
        phase_order = status_info.get("order", 999)
        client_name = p.get("client_name", "").lower()
        return (phase_order, client_name)
    
    processes = sorted(processes, key=get_sort_key)
    
    # Total e paginação (após ordenação)
    total = len(processes)
    processes = processes[skip:skip + size]
    
    # Obter tarefas pendentes por processo (apenas IDs necessários)
    process_ids = [p["id"] for p in processes]
    tasks = await db.tasks.find(
        {
            "process_id": {"$in": process_ids},
            "completed": {"$ne": True}
        },
        {"_id": 0, "id": 1, "process_id": 1, "title": 1, "priority": 1, "due_date": 1}
    ).to_list(500)  # Reduzido de 1000 para 500
    
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
    
    # Calcular total de páginas
    pages = (total + size - 1) // size if size > 0 else 0
    
    return {
        "clients": clients_list,
        "total": total,
        "page": page,
        "size": size,
        "pages": pages,
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
    """Obtém os detalhes completos de um processo.

    Verifica permissões de visualização (can_view_process) antes de
    devolver os dados. Dados sensíveis (NIF, telefone, email do cliente)
    são desencriptados antes da resposta.

    Porquê a verificação de permissões: um intermediário só pode ver
    processos que lhe estão atribuídos, enquanto um admin pode ver
    todos os processos.

    Args:
        process_id: ID do processo.
        user: Utilizador autenticado (injetado).

    Returns:
        ProcessResponse: Dados completos do processo (desencriptados).

    Raises:
        HTTPException(404): Se processo não encontrado.
        HTTPException(403): Se utilizador não tem permissão para ver.
    """
    process = await db.processes.find_one({"id": process_id}, {"_id": 0})
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")
    
    if not can_view_process(user, process):
        raise HTTPException(status_code=403, detail="Acesso negado")
    
    # Desencriptar dados sensíveis
    process = decrypt_sensitive_data(process)
    
    # Auto-sync: se personal_data.email existe mas client_email está vazio, sincronizar
    pd = process.get("personal_data") or {}
    pd_email = pd.get("email", "").strip() if pd.get("email") else ""
    current_client_email = process.get("client_email", "").strip() if process.get("client_email") else ""
    if pd_email and not current_client_email:
        sanitized = sanitize_email(pd_email)
        if sanitized:
            await db.processes.update_one(
                {"id": process_id},
                {"$set": {"client_email": sanitized}}
            )
            process["client_email"] = sanitized
            logger.info(f"Auto-sync: client_email atualizado para '{sanitized}' no processo {process_id}")
    
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
    """Atualiza os dados de um processo existente com controlo de acesso por role.

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
        ProcessResponse: Processo atualizado (desencriptado).

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
    try:
        body = await request.json()
        audit_reason = body.get("audit_reason")
        ai_suggested = bool(body.get("ai_suggested", False))
    except Exception:
        pass
    
    # Indexação só pode actualizar dados financeiros (restante é bloqueado mais abaixo)
    is_indexacao = role == UserRole.INDEXACAO
    
    # Bloquear edição de processos em status terminal (eliminados, desistências, concluídos)
    BLOCKED_STATUSES = ["eliminados", "desistencias", "concluidos"]
    if process.get("status") in BLOCKED_STATUSES:
        raise HTTPException(
            status_code=403,
            detail=f"Não é possível editar um processo em estado terminal ({process.get('status')})."
        )
    
    update_data = {"updated_at": datetime.now(timezone.utc).isoformat()}
    
    valid_statuses = [s["name"] for s in await db.workflow_statuses.find({}, {"name": 1, "_id": 0}).to_list(100)]
    
    # Check role-based permissions
    can_update_personal = role in [UserRole.ADMIN, UserRole.CEO, UserRole.CONSULTOR, UserRole.DIRETOR, UserRole.ADMINISTRATIVO]
    can_update_financial = role in [UserRole.ADMIN, UserRole.CEO, UserRole.CONSULTOR, UserRole.INTERMEDIARIO, UserRole.DIRETOR, UserRole.ADMINISTRATIVO, UserRole.INDEXACAO]
    can_update_real_estate = UserRole.can_act_as_consultor(role)
    can_update_credit = UserRole.can_act_as_intermediario(role)
    can_update_status = role in [UserRole.ADMIN, UserRole.CEO, UserRole.CONSULTOR, UserRole.INTERMEDIARIO, UserRole.DIRETOR, UserRole.ADMINISTRATIVO]
    
    if role == UserRole.CLIENTE:
        if process.get("client_id") != user["id"]:
            raise HTTPException(status_code=403, detail="Acesso negado")
    else:
        # Staff updates
        if data.real_estate_data and can_update_real_estate:
            incoming_re = data.real_estate_data.model_dump(exclude_unset=True, exclude_none=True)
            _re = process.get("real_estate_data")
            existing_re = _re if isinstance(_re, dict) else {}
            merged_re = {**existing_re, **incoming_re}
            await log_data_changes(process_id, user, existing_re, incoming_re, "dados imobiliários")
            await log_audit_event(process_id, user, "Alterou dados imobiliários", request=request, source="web", audit_reason=audit_reason, ai_suggested=ai_suggested, ai_approved_by=user.get("id") if ai_suggested else None)
            update_data["real_estate_data"] = merged_re
        
        # Sync proprietario/owner -> vendedor if vendedor.nome is empty AND no explicit vendedor update
        merged_re = update_data.get("real_estate_data")
        _vd = process.get("vendedor")
        existing_vendedor = _vd if isinstance(_vd, dict) else {}
        if merged_re and not existing_vendedor.get("nome") and data.vendedor is None:
            owner_name = merged_re.get("proprietario_nome") or merged_re.get("owner_name") or ""
            owner_contact = merged_re.get("proprietario_contacto") or merged_re.get("owner_phone") or ""
            if owner_name:
                update_data["vendedor"] = {
                    **existing_vendedor,
                    "nome": owner_name,
                    "contacto": owner_contact,
                }
        
        if data.credit_data and can_update_credit:
            incoming_credit = data.credit_data.model_dump(exclude_unset=True, exclude_none=True)
            _cd = process.get("credit_data")
            existing_credit = _cd if isinstance(_cd, dict) else {}
            merged_credit = {**existing_credit, **incoming_credit}
            await log_data_changes(process_id, user, existing_credit, incoming_credit, "dados de crédito")
            await log_audit_event(process_id, user, "Alterou dados de crédito", request=request, source="web", audit_reason=audit_reason, ai_suggested=ai_suggested, ai_approved_by=user.get("id") if ai_suggested else None)
            update_data["credit_data"] = merged_credit
        
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
        if data.monitored_emails is not None:
            update_data["monitored_emails"] = data.monitored_emails
        
        # Metadados do processo (Fase 3)
        if data.notes is not None:
            update_data["notes"] = data.notes
        if data.prioridade is not None:
            if data.prioridade not in ["baixa", "media", "alta"]:
                raise HTTPException(status_code=400, detail="Prioridade inválida. Valores aceites: baixa, media, alta")
            update_data["prioridade"] = data.prioridade
        if data.labels is not None:
            update_data["labels"] = data.labels
        
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
    try:
        update_data = encrypt_sensitive_data(update_data)
    except TypeError as e:
        import traceback
        tb = traceback.format_exc()
        logger.error(f"TypeError em encrypt_sensitive_data para processo {process_id}: {e}\n{tb}")
        # Diagnóstico: log das chaves/tipos em update_data que podem causar o erro
        for k, v in update_data.items():
            if isinstance(v, dict):
                for sk, sv in v.items():
                    if not isinstance(sv, (str, int, float, bool, type(None), list)):
                        logger.error(f"  Suspeito: update_data[{k}][{sk}] = {type(sv).__name__}: {repr(sv)[:100]}")
            elif not isinstance(v, (str, int, float, bool, type(None), list, dict)):
                logger.error(f"  Suspeito root: update_data[{k}] = {type(v).__name__}: {repr(v)[:100]}")
        raise HTTPException(status_code=500, detail=f"TypeError em encrypt: {e} | {tb.split(chr(10))[-3] if tb else 'no traceback'}")
    inject_cdc_context(update_data, user)
    await db.processes.update_one({"id": process_id}, {"$set": update_data})
    updated = await db.processes.find_one({"id": process_id}, {"_id": 0})
    
    # === SYNC CLIENT DATA: Email/Phone/NIF changes must propagate to clients collection ===
    client_id = process.get("client_id")
    if client_id and (update_data.get("client_nif") is not None):
        client_update = {}
        # NIF sync: se client_nif foi atualizado, propagar para clients
        if update_data.get("client_nif") is not None:
            # Obter valor desencriptado (update_data já pode estar encriptado neste ponto,
            # mas client_nif no update vem de sanitize_nif que retorna plaintext)
            # O client_nif em update_data ainda é plaintext aqui porque encrypt_sensitive_data
            # já foi chamado, mas vamos usar o valor que sabemos estar correto
            nif_val = update_data.get("client_nif")
            # Se está encriptado, desencriptar; caso contrário usar diretamente
            if isinstance(nif_val, str) and nif_val.startswith("ENC:"):
                from services.encryption import encryption_service
                try:
                    nif_val = encryption_service.decrypt(nif_val)
                except Exception:
                    nif_val = None
            if nif_val:
                client_update["dados_pessoais.nif"] = nif_val
                from services.encryption import generate_nif_hash
                nif_hash = generate_nif_hash(nif_val)
                if nif_hash:
                    client_update["dados_pessoais.nif_hash"] = nif_hash
        
        if client_update:
            await db.clients.update_one(
                {"id": client_id},
                {"$set": client_update}
            )
            logger.info(f"Sincronizados dados de contacto para cliente {client_id}: {list(client_update.keys())}")
    
    # === CACHE INVALIDATION: Actualização de processo pode alterar KPIs ===
    # Invalidar apenas se houve mudança de status (afeta contadores)
    if data.status:
        await invalidate_stats_cache(user_id=user.get("id"))
    
    # === WEBSOCKET BROADCAST: Processo actualizado ===
    await broadcast_process_delta(
        event_type=WSEventType.PROCESS_UPDATED,
        process_id=process_id,
        process_number=updated.get("process_number"),
        client_name=updated.get("client_name"),
        status=updated.get("status"),
        old_status=process.get("status") if data.status else None,
        priority=updated.get("prioridade") or updated.get("priority"),
        prioridade=updated.get("prioridade"),
        updated_at=updated.get("updated_at")
    )
    
    # O22 - Executar regras de automação após actualização
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
    try:
        updated = decrypt_sensitive_data(updated)
    except Exception as e:
        logger.error(f"Erro ao desencriptar dados do processo {process_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Erro interno ao desencriptar dados do processo")
    
    # Sincronizar com Trello (nome e descrição do card)
    await sync_process_to_trello(updated)
    
    try:
        return ProcessResponse(**updated)
    except Exception as e:
        logger.error(f"Erro ao serializar resposta do processo {process_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Erro interno ao serializar dados do processo: {str(e)[:200]}")


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
    
    update_data = {"updated_at": datetime.now(timezone.utc).isoformat()}
    
    # Obter listas atuais
    old_consultor_ids = process.get("assigned_consultor_ids") or []
    old_mediador_ids = process.get("assigned_mediador_ids") or []
    old_indexacao = process.get("assigned_indexacao_id")
    old_parceiro = process.get("assigned_parceiro_id")
    
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
    
    # Atribuir parceiro (utilizador fantasma para tracking)
    if parceiro_id is not None:
        if parceiro_id == "" or parceiro_id == "null":
            # Remover parceiro
            update_data["assigned_parceiro_id"] = None
            update_data["parceiro_name"] = None
            if old_parceiro:
                old_user = await db.users.find_one({"id": old_parceiro}, {"name": 1})
                await log_history(process_id, user, "Removeu parceiro", "assigned_parceiro_id", old_user.get("name") if old_user else old_parceiro, None)
        else:
            parceiro_user = await db.users.find_one({"id": parceiro_id})
            if parceiro_user:
                update_data["assigned_parceiro_id"] = parceiro_id
                update_data["parceiro_name"] = parceiro_user["name"]
                old_name = None
                if old_parceiro:
                    old_user = await db.users.find_one({"id": old_parceiro}, {"name": 1})
                    old_name = old_user.get("name") if old_user else None
                await log_history(process_id, user, "Atribuiu parceiro", "assigned_parceiro_id", old_name, parceiro_user["name"])
    
    inject_cdc_context(update_data, user)
    await db.processes.update_one({"id": process_id}, {"$set": update_data})
    
    # === CACHE INVALIDATION: Atribuição altera KPIs dos users envolvidos ===
    await invalidate_stats_cache(user_id=user.get("id"))
    
    # === WEBSOCKET BROADCAST: Atribuições actualizadas ===
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
        updated_at=updated_process.get("updated_at")
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
    elif UserRole.can_act_as_intermediario(user_role):
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
        
        assignment_type = "intermediario"
    else:
        raise HTTPException(status_code=403, detail="O seu papel não permite atribuir-se a processos")
    
    inject_cdc_context(update_data, user)
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
        
        removed_from.append("intermediario")
        await log_history(process_id, user, "Removeu-se como intermediário", "assigned_mediador_ids", user_name, None)
    
    if not removed_from:
        raise HTTPException(status_code=400, detail="Não está atribuído a este processo")
    
    inject_cdc_context(update_data, user)
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


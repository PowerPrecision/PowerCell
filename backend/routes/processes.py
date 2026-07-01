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
from services.websocket_manager import manager, WSEventType, create_ws_message
from services.redis_cache import invalidate_stats_cache

# Portal imports
from services.portal_security import create_client_magic_token, PORTAL_TOKEN_VALIDITY_DAYS

logger = logging.getLogger(__name__)


# ====================================================================
# FINANCE SNAPSHOT HELPER — Criar ProcessFinance ao fechar processo
# ====================================================================

async def _create_finance_snapshot(process: dict, user: dict):
    """
    Cria um snapshot financeiro (ProcessFinance) quando um processo é concluído.

    Lê dados de real_estate_data (valor_imovel) e credit_data (loan_amount)
    para calcular comissões duais (Imobiliária + Crédito) de forma independente.

    Usa a FinanceConfig da empresa para determinar fee_type/fee_value.
    Se a empresa tiver configs separadas para imobiliária e crédito, usa-as;
    caso contrário, usa a mesma config para ambas.

    Compatibilidade retroactiva:
    - Se não houver FinanceConfig para a empresa, usa os campos legacy
      (base_business_value + applied_fee_type/value) se disponíveis.
    - Se já existir um registo financeiro para este processo, ignora silenciosamente.
    """
    from models.finance import FeeType, FinanceStatus

    process_id = process.get("id", "")
    company_id = process.get("company_id", "")
    client_id = process.get("client_id", "")

    # Evitar duplicados: se já existe registo, não criar outro
    existing = await db.process_finances.find_one({
        "process_id": process_id,
        "company_id": company_id,
    })
    if existing:
        logger.info(f"Snapshot financeiro já existe para processo {process_id}, a ignorar")
        return

    # Obter dados do processo
    real_estate_data = process.get("real_estate_data") or {}
    credit_data = process.get("credit_data") or {}
    financial_data = process.get("financial_data") or {}

    # Ler valores base
    valor_imovel = real_estate_data.get("valor_imovel")
    loan_amount = credit_data.get("loan_amount") or credit_data.get("requested_amount")

    # Tentar obter FinanceConfig da empresa
    # A config pode ter campos separados para imobiliária e crédito
    config_doc = await db.finance_configs.find_one({"company_id": company_id})

    # Defaults para campos legacy (compatibilidade)
    base_business_value = 0.0
    applied_fee_type = None
    applied_fee_value = None

    # Comissão imobiliária
    re_base_value = float(valor_imovel) if valor_imovel else 0.0
    re_fee_type = None
    re_fee_value = None

    # Comissão de crédito
    cr_base_value = float(loan_amount) if loan_amount else 0.0
    cr_fee_type = None
    cr_fee_value = None

    tax_rate = 23.0  # IVA português por defeito

    if config_doc:
        # FinanceConfig encontrada — usar para ambas as áreas
        fee_type = config_doc.get("fee_type", "percentage")
        default_value = config_doc.get("default_value", 0.0)
        tax_rate = config_doc.get("tax_rate", 23.0)

        # Verificar se existem configs separadas para imobiliária e crédito
        re_fee_type = config_doc.get("real_estate_fee_type") or fee_type
        re_fee_value = config_doc.get("real_estate_fee_value") or config_doc.get("real_estate_default_value") or default_value
        cr_fee_type = config_doc.get("credit_fee_type") or fee_type
        cr_fee_value = config_doc.get("credit_fee_value") or config_doc.get("credit_default_value") or default_value

        # Campos legacy para compatibilidade
        applied_fee_type = fee_type
        applied_fee_value = default_value
        base_business_value = cr_base_value or re_base_value
    else:
        # Sem FinanceConfig: tentar usar campos do processo (financial_data)
        comissao_mediacao = financial_data.get("comissao_mediacao")
        if comissao_mediacao:
            # Se já temos comissão, usar como comissão total (credit_commission por defeito)
            cr_base_value = float(comissao_mediacao)
            cr_fee_type = "fixed"
            cr_fee_value = float(comissao_mediacao)
            applied_fee_type = "fixed"
            applied_fee_value = float(comissao_mediacao)
            base_business_value = float(comissao_mediacao)
        else:
            # Sem config e sem comissão: criar registo com zeros
            logger.info(
                f"Sem FinanceConfig nem comissão para processo {process_id}. "
                f"Snapshot criado com valores zero."
            )

    # Calcular comissões
    # Comissão imobiliária
    if re_fee_type == FeeType.PERCENTAGE.value:
        re_commission = round(re_base_value * (re_fee_value / 100), 2) if re_base_value and re_fee_value else 0.0
    elif re_fee_type == FeeType.FIXED.value:
        re_commission = re_fee_value or 0.0
    else:
        re_commission = 0.0

    # Comissão de crédito
    if cr_fee_type == FeeType.PERCENTAGE.value:
        cr_commission = round(cr_base_value * (cr_fee_value / 100), 2) if cr_base_value and cr_fee_value else 0.0
    elif cr_fee_type == FeeType.FIXED.value:
        cr_commission = cr_fee_value or 0.0
    else:
        cr_commission = 0.0

    # Comissão total
    expected_commission = round(re_commission + cr_commission, 2)
    tax_amount = round(expected_commission * (tax_rate / 100), 2)
    total_with_tax = round(expected_commission + tax_amount, 2)

    # Criar documento
    finance_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    doc = {
        "id": finance_id,
        "process_id": process_id,
        "client_id": client_id,
        "company_id": company_id,
        # Campos legacy (compatibilidade retroactiva)
        "base_business_value": base_business_value,
        "applied_fee_type": applied_fee_type,
        "applied_fee_value": applied_fee_value,
        # Comissão Imobiliária (Real Estate)
        "real_estate_base_value": re_base_value,
        "real_estate_fee_type": re_fee_type,
        "real_estate_fee_value": re_fee_value,
        "real_estate_commission": re_commission,
        # Comissão de Crédito (Credit)
        "credit_base_value": cr_base_value,
        "credit_fee_type": cr_fee_type,
        "credit_fee_value": cr_fee_value,
        "credit_commission": cr_commission,
        # Totais
        "expected_commission": expected_commission,
        "tax_amount": tax_amount,
        "total_with_tax": total_with_tax,
        "status": FinanceStatus.PENDING.value,
        "invoice_link": None,
        "created_at": now,
        "updated_at": now,
    }

    await db.process_finances.insert_one(doc)

    logger.info(
        f"Snapshot financeiro criado: id={finance_id}, process_id={process_id}, "
        f"re_commission={re_commission}, cr_commission={cr_commission}, "
        f"total={expected_commission}"
    )


async def _ensure_finance_snapshot(process: dict, user: dict):
    """
    Garante que existe um snapshot financeiro (ProcessFinance) para o processo,
    criando um novo se não existir ou atualizando os valores base se já existir.

    Usado na Sincronização Financeira Retroativa: quando um admin/CEO edita
    um processo concluído/escritura, os valores financeiros (valor_imovel,
    loan_amount) podem ter mudado, e o snapshot precisa de ser recalculado.

    Lógica:
    1. Procura registo existente em process_finances pelo process_id + company_id
    2. Se NÃO existe → chama _create_finance_snapshot() para criar do zero
    3. Se JÁ existe → recalcula as comissões com base nos novos valores do
       processo e nas configurações atuais da empresa, e atualiza o registo
    """
    from models.finance import FeeType, FinanceStatus

    process_id = process.get("id", "")
    company_id = process.get("company_id", "")

    existing = await db.process_finances.find_one({
        "process_id": process_id,
        "company_id": company_id,
    })

    # Se não existe, criar novo snapshot
    if not existing:
        logger.info(f"Nenhum snapshot financeiro encontrado para processo {process_id}. A criar novo.")
        await _create_finance_snapshot(process, user)
        return

    # Já existe — recalcular comissões com base nos valores atualizados do processo
    real_estate_data = process.get("real_estate_data") or {}
    credit_data = process.get("credit_data") or {}
    financial_data = process.get("financial_data") or {}

    valor_imovel = real_estate_data.get("valor_imovel")
    loan_amount = credit_data.get("loan_amount") or credit_data.get("requested_amount")

    # Obter FinanceConfig da empresa
    config_doc = await db.finance_configs.find_one({"company_id": company_id})

    # Defaults
    re_base_value = float(valor_imovel) if valor_imovel else 0.0
    cr_base_value = float(loan_amount) if loan_amount else 0.0
    re_fee_type = None
    re_fee_value = None
    cr_fee_type = None
    cr_fee_value = None
    base_business_value = 0.0
    applied_fee_type = None
    applied_fee_value = None
    tax_rate = 23.0

    if config_doc:
        fee_type = config_doc.get("fee_type", "percentage")
        default_value = config_doc.get("default_value", 0.0)
        tax_rate = config_doc.get("tax_rate", 23.0)

        re_fee_type = config_doc.get("real_estate_fee_type") or fee_type
        re_fee_value = config_doc.get("real_estate_fee_value") or config_doc.get("real_estate_default_value") or default_value
        cr_fee_type = config_doc.get("credit_fee_type") or fee_type
        cr_fee_value = config_doc.get("credit_fee_value") or config_doc.get("credit_default_value") or default_value

        applied_fee_type = fee_type
        applied_fee_value = default_value
        base_business_value = cr_base_value or re_base_value
    else:
        comissao_mediacao = financial_data.get("comissao_mediacao")
        if comissao_mediacao:
            cr_base_value = float(comissao_mediacao)
            cr_fee_type = "fixed"
            cr_fee_value = float(comissao_mediacao)
            applied_fee_type = "fixed"
            applied_fee_value = float(comissao_mediacao)
            base_business_value = float(comissao_mediacao)

    # Calcular comissões
    if re_fee_type == FeeType.PERCENTAGE.value:
        re_commission = round(re_base_value * (re_fee_value / 100), 2) if re_base_value and re_fee_value else 0.0
    elif re_fee_type == FeeType.FIXED.value:
        re_commission = re_fee_value or 0.0
    else:
        re_commission = 0.0

    if cr_fee_type == FeeType.PERCENTAGE.value:
        cr_commission = round(cr_base_value * (cr_fee_value / 100), 2) if cr_base_value and cr_fee_value else 0.0
    elif cr_fee_type == FeeType.FIXED.value:
        cr_commission = cr_fee_value or 0.0
    else:
        cr_commission = 0.0

    expected_commission = round(re_commission + cr_commission, 2)
    tax_amount = round(expected_commission * (tax_rate / 100), 2)
    total_with_tax = round(expected_commission + tax_amount, 2)

    # Atualizar registo existente
    update_fields = {
        "real_estate_base_value": re_base_value,
        "real_estate_fee_type": re_fee_type,
        "real_estate_fee_value": re_fee_value,
        "real_estate_commission": re_commission,
        "credit_base_value": cr_base_value,
        "credit_fee_type": cr_fee_type,
        "credit_fee_value": cr_fee_value,
        "credit_commission": cr_commission,
        "expected_commission": expected_commission,
        "tax_amount": tax_amount,
        "total_with_tax": total_with_tax,
        "base_business_value": base_business_value,
        "applied_fee_type": applied_fee_type,
        "applied_fee_value": applied_fee_value,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    await db.process_finances.update_one(
        {"id": existing["id"]},
        {"$set": update_fields}
    )

    logger.info(
        f"Snapshot financeiro atualizado retroativamente: process_id={process_id}, "
        f"re_commission={re_commission}, cr_commission={cr_commission}, "
        f"total={expected_commission}, updated_by={user.get('email', 'unknown')}"
    )


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


def build_multiword_search_filter(search_term: str, name_field: str) -> dict:
    """
    Constrói filtro de pesquisa que suporta múltiplas palavras.
    
    Se o termo contém espaços, divide em palavras e exige que TODAS
    apareçam em qualquer ordem no campo de nome (AND lógico).
    
    Exemplo: 'vera teixeira' encontra 'Vera Lucia Da Costa Teixeira'
    porque 'vera' E 'teixeira' existem no nome.
    
    Se o termo não tem espaços, comporta-se como create_accent_insensitive_regex.
    """
    if not search_term:
        return {}
    
    words = search_term.strip().split()
    
    if len(words) <= 1:
        return {name_field: create_accent_insensitive_regex(search_term.strip())}
    
    word_filters = []
    for word in words:
        if len(word.strip()) >= 1:
            word_filters.append({name_field: create_accent_insensitive_regex(word.strip())})
    
    if len(word_filters) == 1:
        return word_filters[0]
    
    return {"$and": word_filters}



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
                "client_id": process.get("client_id", ""),
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
    client_id = process.get("client_id", "")

    if not client_email:
        raise HTTPException(status_code=400, detail="Cliente não tem email associado")

    # Buscar portal_access_code do cliente para incluir no email
    portal_access_code = None
    if client_id:
        client_doc = await db.clients.find_one(
            {"id": client_id},
            {"_id": 0, "portal_access_code": 1}
        )
        if client_doc:
            portal_access_code = client_doc.get("portal_access_code")
    
    # Se não tem access code, gerar um e guardar no cliente
    if not portal_access_code and client_id:
        from models.client import generate_portal_access_code
        portal_access_code = generate_portal_access_code()
        await db.clients.update_one(
            {"id": client_id},
            {"$set": {"portal_access_code": portal_access_code}}
        )

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
                "client_id": process.get("client_id", ""),
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
    # Bloco opcional com credenciais de acesso ao portal
    portal_credentials_html = ""
    portal_credentials_text = ""
    if portal_access_code:
        portal_credentials_html = f"""
            <div style="background: #f0fdfa; border: 1px solid #0d9488; border-radius: 8px; padding: 20px; margin: 20px 0;">
                <h3 style="color: #0f766e; margin: 0 0 12px 0; font-size: 15px;">As suas credenciais de acesso</h3>
                <p style="margin: 5px 0; color: #1e293b;"><strong>Email:</strong> {client_email}</p>
                <p style="margin: 5px 0; color: #1e293b;"><strong>Código de Acesso:</strong> <span style="font-family: 'Courier New', monospace; font-size: 18px; font-weight: bold; color: #0f766e; letter-spacing: 3px;">{portal_access_code}</span></p>
                <p style="font-size: 12px; color: #64748b; margin-top: 10px;">Guarde este código em segurança. Precisará dele para aceder ao portal sempre que quiser consultar o seu processo.</p>
            </div>
        """
        portal_credentials_text = f"""

As suas credenciais de acesso ao Portal:
- Email: {client_email}
- Código de Acesso: {portal_access_code}

Guarde este código em segurança. Precisará dele para aceder ao portal sempre que quiser consultar o seu processo.
"""

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
            {portal_credentials_html}
            <p style="font-size: 12px; color: #94a3b8; margin-top: 20px;">
                Este link é válido por 90 dias. Se precisar de um novo link, contacte o seu consultor.
            </p>
        </div>
    </div>
    """

    text_body = (
        f"Olá {client_name},\n\n"
        f"O seu consultor preparou o seu portal pessoal para acompanhar o seu processo de crédito habitação.\n\n"
        f"Aceda ao portal através deste link:\n{magic_link}\n"
        f"{portal_credentials_text}\n"
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
    first_status = await db.workflow_statuses.find_one({}, {"_id": 0}, sort=[("order", 1)])
    initial_status = first_status["name"] if first_status else "clientes_espera"
    
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
        
        # VALIDAÇÃO: E-mail obrigatório para acesso ao Portal do Cliente
        if not client_email or not client_email.strip():
            raise HTTPException(
                status_code=400,
                detail="O e-mail é obrigatório para a criação do Portal do Cliente. "
                       "Adicione um e-mail de contacto ao cliente antes de criar o processo."
            )
        
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
    # REGRA: consultor_id = quem cria o processo (consultor)
    #         assigned_indexacao_id = atribuído pelo algoritmo de auto-atribuição (NÃO o consultor)
    if user["role"] == UserRole.INTERMEDIARIO:
        process_doc["assigned_mediador_id"] = user["id"]
        process_doc["mediador_name"] = user["name"]
    elif user["role"] in [UserRole.CONSULTOR, UserRole.DIRETOR]:
        process_doc["assigned_consultor_id"] = user["id"]
        process_doc["consultor_name"] = user["name"]
        process_doc["consultor_id"] = user["id"]  # Consultor que criou o processo
    
    # Encriptar campos sensíveis antes de guardar
    process_doc = encrypt_sensitive_data(process_doc)
    
    # Inserir na base de dados
    await db.processes.insert_one(process_doc)
    
    # ============================================================
    # AUTO-ATRIBUIÇÃO DE INDEXADOR
    # Após criar o processo, invocar assign_to_indexer() para:
    # 1. Encontrar o indexador com menor carga (< 15 processos ativos)
    # 2. Atribuir o processo ao indexador (assigned_indexacao_id)
    # 3. Se nenhum indexador disponível → status = fila_espera
    # ============================================================
    try:
        from services.process_assignment import assign_to_indexer
        assign_success, assign_data, assign_msg = await assign_to_indexer(process_id)
        if assign_success and assign_data.get("assigned"):
            logger.info(
                f"[CREATE-PROCESS] Indexador auto-atribuído: {assign_data.get('indexacao_name')} "
                f"para processo {process_id}"
            )
            # Atualizar o process_doc local para a resposta (já foi atualizado na BD por assign_to_indexer)
            process_doc["assigned_indexacao_id"] = assign_data.get("assigned_indexacao_id")
            process_doc["indexacao_name"] = assign_data.get("indexacao_name")
            if assign_data.get("status"):
                process_doc["status"] = assign_data["status"]
        else:
            logger.warning(
                f"[CREATE-PROCESS] Sem indexador disponível para processo {process_id}: {assign_msg}"
            )
            if assign_data.get("status"):
                process_doc["status"] = assign_data["status"]
    except Exception as e:
        logger.warning(f"[CREATE-PROCESS] Erro na auto-atribuição de indexador para processo {process_id}: {e}")
    
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
    
    # Actualizar process_ids do cliente + marcar lead como convertido
    if client_id:
        await db.clients.update_one(
            {"id": client_id},
            {
                "$addToSet": {"process_ids": process_id},
                "$set": {
                    "updated_at": now,
                    "lead_status": "converted"  # Lead já não aparece na página de Registos
                }
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
    
    # ====================================================================
    # CONSTRUÇÃO ROBUSTA DA QUERY MONGODB
    # Regra: TODOS os filtros são combinados com $and — nunca se anulam
    # Estrutura: { $and: [filtro_is_deleted, filtro_role, filtro_status, filtro_search] }
    # ====================================================================
    and_conditions = []
    
    # ====================================================================
    # FILTRO DE INTEGRIDADE: is_deleted
    # Regra base: is_deleted != True (sempre, a menos que explicitamente pedido)
    # EXCEÇÃO: status="eliminados" ou view_mode="deleted" → inverter lógica
    # ====================================================================
    is_admin = role in [UserRole.ADMIN, UserRole.CEO]
    is_deleted_filter = None
    
    # Verificar se o utilizador quer VER eliminados
    wants_deleted = (status == "eliminados" or view_mode == "deleted")
    
    if wants_deleted and is_admin:
        # Admin quer ver eliminados → mostrar APENAS os eliminados
        is_deleted_filter = {"is_deleted": True}
    elif wants_deleted:
        # Non-admin quer ver eliminados → mostrar eliminados do seu escopo
        is_deleted_filter = {"is_deleted": True}
    else:
        # Comportamento normal: excluir eliminados
        is_deleted_filter = {"is_deleted": {"$ne": True}}
    
    and_conditions.append(is_deleted_filter)
    
    # ====================================================================
    # FILTRO DE ROLE (quem pode ver quê)
    # ====================================================================
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
            and_conditions.append({"$or": role_conditions})
    elif role == UserRole.CLIENTE:
        and_conditions.append({"client_id": user["id"]})
    elif role == UserRole.INDEXACAO:
        and_conditions.append({"$or": [
            {"assigned_indexacao_id": user["id"]},
            {"created_by": user.get("email", "")}
        ]})
    elif role in [UserRole.ADMIN, UserRole.CEO, UserRole.ADMINISTRATIVO, UserRole.DIRETOR]:
        pass  # Vêem todos
    elif role == UserRole.CONSULTOR:
        and_conditions.append({"$or": [
            {"assigned_consultor_ids": user["id"]},
            {"assigned_consultor_id": user["id"]}
        ]})
    elif role == UserRole.INTERMEDIARIO:
        and_conditions.append({"$or": [
            {"assigned_mediador_ids": user["id"]},
            {"assigned_mediador_id": user["id"]}
        ]})

    # ====================================================================
    # FILTRO DE ESTADO ATIVO (view_mode)
    # ====================================================================
    # Se o utilizador pediu status="eliminados", NÃO aplicar filtro de view_mode
    if status == "eliminados":
        # Já tratado pelo is_deleted_filter acima
        pass
    elif view_mode == "active_only":
        # DEFAULT: Apenas processos em curso
        and_conditions.append({"status": {"$nin": INACTIVE_STATUSES}})
    elif view_mode == "historical":
        # Apenas processos arquivados (concluídos e desistências)
        and_conditions.append({"status": {"$in": ARCHIVED_STATUSES}})
    # view_mode == 'all': Não aplica filtro de status (mostra tudo exceto eliminados)
    
    # Adicionar filtro de status explícito (sobrepõe-se ao view_mode, exceto "eliminados")
    if status and status != "eliminados":
        and_conditions.append({"status": status})
    
    # ====================================================================
    # PESQUISA DE TEXTO (expandida)
    # Campos: client_name, client_email, client_nif, client_phone, process_number (ref)
    # Sempre combinada com $and — NUNCA anula os filtros
    # ====================================================================
    if search:
        name_regex = create_accent_insensitive_regex(search)
        simple_regex = {"$regex": re.escape(search), "$options": "i"}
        
        search_or_conditions = [
            {"client_name": name_regex},
            {"client_email": simple_regex},
            {"client_nif": simple_regex},
            {"client_phone": simple_regex},
            {"process_number": simple_regex},
        ]
        
        # Pesquisar também no campo "ref" (alias para process_number)
        # e em personal_data aninhado (para NIF/telefone que podem estar encriptados)
        search_condition = {"$or": search_or_conditions}
        and_conditions.append(search_condition)
    
    # ====================================================================
    # MONTAR QUERY FINAL COM $and
    # Se há apenas 1 condição, não precisa de $and (otimização)
    # ====================================================================
    if len(and_conditions) == 1:
        query = and_conditions[0]
    elif len(and_conditions) > 1:
        query = {"$and": and_conditions}
    else:
        query = {}

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
    
    # ====================================================================
    # CONSTRUÇÃO ROBUSTA DA QUERY MONGODB (igual ao GET /processes)
    # Regra: TODOS os filtros são combinados com $and — nunca se anulam
    # ====================================================================
    and_conditions = []
    
    # ====================================================================
    # FILTRO DE INTEGRIDADE: is_deleted
    # ====================================================================
    is_admin = role in [UserRole.ADMIN, UserRole.CEO]
    wants_deleted = (status == "eliminados" or view_mode == "deleted")
    
    if wants_deleted:
        is_deleted_filter = {"is_deleted": True}
    else:
        is_deleted_filter = {"is_deleted": {"$ne": True}}
    
    and_conditions.append(is_deleted_filter)

    # Construir query baseada no papel
    if role == UserRole.CLIENTE:
        and_conditions.append({"client_id": user["id"]})
    elif role == UserRole.INDEXACAO:
        and_conditions.append({"$or": [
            {"assigned_indexacao_id": user["id"]},
            {"created_by": user.get("email", "")}
        ]})
    elif role in [UserRole.ADMIN, UserRole.CEO, UserRole.ADMINISTRATIVO, UserRole.DIRETOR]:
        pass
    elif role == UserRole.CONSULTOR:
        and_conditions.append({"$or": [
            {"assigned_consultor_ids": user["id"]},
            {"assigned_consultor_id": user["id"]}
        ]})
    elif role == UserRole.INTERMEDIARIO:
        and_conditions.append({"$or": [
            {"assigned_mediador_ids": user["id"]},
            {"assigned_mediador_id": user["id"]}
        ]})

    # ====================================================================
    # FILTRO DE ESTADO ATIVO (view_mode)
    # ====================================================================
    if status == "eliminados":
        pass  # Já tratado pelo is_deleted_filter
    elif view_mode == "active_only":
        and_conditions.append({"status": {"$nin": INACTIVE_STATUSES}})
    elif view_mode == "historical":
        and_conditions.append({"status": {"$in": ARCHIVED_STATUSES}})

    # Adicionar filtros opcionais de status (exceto "eliminados")
    if status and status != "eliminados":
        and_conditions.append({"status": status})
    
    # ====================================================================
    # PESQUISA DE TEXTO (expandida — mesmo campos que GET /processes)
    # Campos: client_name, client_email, client_nif, client_phone, process_number
    # ====================================================================
    if search:
        name_filter = build_multiword_search_filter(search, "client_name")
        simple_regex = {"$regex": re.escape(search), "$options": "i"}
        
        search_or_conditions = []
        # Adicionar filtro de nome (pode ser $and se multi-word)
        if "$and" in name_filter:
            search_or_conditions.append(name_filter)
        elif name_filter:
            search_or_conditions.append(name_filter)
        search_or_conditions.append({"client_email": simple_regex})
        search_or_conditions.append({"client_nif": simple_regex})
        search_or_conditions.append({"client_phone": simple_regex})
        search_or_conditions.append({"process_number": simple_regex})
        
        search_condition = {"$or": search_or_conditions}
        and_conditions.append(search_condition)
    
    # Montar query final
    if len(and_conditions) == 1:
        query = and_conditions[0]
    elif len(and_conditions) > 1:
        query = {"$and": and_conditions}
    else:
        query = {}
    
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
    # - active_only: Apenas processos em curso
    # - all (DEFAULT): Processos ativos + concluídos/desistências (com filtro de datas)
    # ====================================================================
    if view_mode == "active_only":
        # Excluir concluídos e desistências do Kanban
        active_filter = {"status": {"$nin": INACTIVE_STATUSES}}
        if "$and" in query:
            query["$and"].append(active_filter)
        elif query:
            query = {"$and": [query, active_filter]}
        else:
            query = active_filter
    else:
        # view_mode == 'all': Mostrar ativos + concluídos/desistências
        # Se completed_days > 0, limitar processos inactivos aos últimos N dias
        if completed_days and completed_days > 0:
            from datetime import timedelta
            cutoff_date = (datetime.now(timezone.utc) - timedelta(days=completed_days)).isoformat()
            # Processos ativos (sem restrição) OU inactivos dentro do período
            inactive_within_period = {
                "$and": [
                    {"status": {"$in": ARCHIVED_STATUSES}},
                    {"updated_at": {"$gte": cutoff_date}}
                ]
            }
            active_or_recent = {
                "$or": [
                    {"status": {"$nin": INACTIVE_STATUSES}},
                    inactive_within_period
                ]
            }
            if "$and" in query:
                query["$and"].append(active_or_recent)
            elif query:
                query = {"$and": [query, active_or_recent]}
            else:
                query = active_or_recent
        # Se completed_days == 0, sem limite de datas (mostra tudo)
    
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

    # ====================================================================
    # BATCH ENRIQUECIMENTO: has_unread_messages & has_new_documents
    # Pistas visuais silenciosas para interações do cliente no portal.
    # Evita fadiga de notificações — apenas dots coloridos no cartão.
    # ====================================================================
    process_ids = [p["id"] for p in processes]

    # 1) Mensagens não lidas do cliente (portal_messages)
    unread_pipeline = [
        {"$match": {
            "process_id": {"$in": process_ids},
            "sender_type": "client",
            "read_by_staff": False
        }},
        {"$group": {"_id": "$process_id", "unread_count": {"$sum": 1}}}
    ]
    unread_results = await db.portal_messages.aggregate(unread_pipeline).to_list(1000)
    unread_map = {r["_id"]: r["unread_count"] > 0 for r in unread_results}

    # 2) Novos documentos enviados pelo cliente (status "uploaded" = pendente de revisão)
    new_docs_pipeline = [
        {"$match": {
            "process_id": {"$in": process_ids},
            "status": "uploaded"
        }},
        {"$group": {"_id": "$process_id", "new_count": {"$sum": 1}}}
    ]
    new_docs_results = await db.documents.aggregate(new_docs_pipeline).to_list(1000)
    new_docs_map = {r["_id"]: r["new_count"] > 0 for r in new_docs_results}

    # Inject computed boolean flags into each process
    for p in processes:
        p["has_unread_messages"] = unread_map.get(p["id"], False)
        p["has_new_documents"] = new_docs_map.get(p["id"], False)

    # Get all users for name lookup (projection mínima)
    users = await db.users.find({}, {"_id": 0, "id": 1, "name": 1, "role": 1}).to_list(1000)
    user_map = {u["id"]: u for u in users}
    
    # Debug: verificar se há processos com indexação/parceiro atribuído
    indexacao_count = sum(1 for p in processes if p.get("assigned_indexacao_id"))
    parceiro_count = sum(1 for p in processes if p.get("assigned_parceiro_id"))
    logger.info(f"[Kanban Export] {len(processes)} processos: {indexacao_count} com indexação, {parceiro_count} com parceiro")
    if indexacao_count > 0:
        sample_ids = [p.get("assigned_indexacao_id") for p in processes if p.get("assigned_indexacao_id")][:3]
        logger.info(f"[Kanban Export] Sample indexacao IDs: {sample_ids}")
        logger.info(f"[Kanban Export] User map has keys: {list(user_map.keys())[:5]}...")
    
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
    try:
        for status in statuses:
            # CORREÇÃO (Pacote AE): usar .get() com defaults em vez de status["..."]
            # Se um workflow_status tiver campos em falta (label, color, order),
            # o bracket notation lança KeyError → 500. O .get() degrada graciosamente.
            status_name = status.get("name") or ""
            status_processes = processes_by_status.get(status_name, [])

            # Enrich with user names and assignment info
            enriched_processes = []
            for p in status_processes:
                # === Múltiplos Consultores ===
                consultor_ids = p.get("assigned_consultor_ids") or []
                if p.get("assigned_consultor_id") and p["assigned_consultor_id"] not in consultor_ids:
                    consultor_ids.append(p["assigned_consultor_id"])
                consultor_names = [user_map.get(cid, {}).get("name", "") for cid in consultor_ids if user_map.get(cid)]

                # === Múltiplos Mediadores ===
                mediador_ids = p.get("assigned_mediador_ids") or []
                if p.get("assigned_mediador_id") and p["assigned_mediador_id"] not in mediador_ids:
                    mediador_ids.append(p["assigned_mediador_id"])
                mediador_names = [user_map.get(mid, {}).get("name", "") for mid in mediador_ids if user_map.get(mid)]

                # === Indexação (usar nome da BD com fallback para user_map) ===
                indexacao_name = p.get("indexacao_name") or user_map.get(p.get("assigned_indexacao_id"), {}).get("name", "")

                # === Parceiro (usar nome da BD com fallback para user_map) ===
                parceiro_name = p.get("parceiro_name") or user_map.get(p.get("assigned_parceiro_id"), {}).get("name", "")

                # Verificar se o utilizador actual está atribuído
                is_my_consultor = p.get("assigned_consultor_id") == user_id or user_id in (p.get("assigned_consultor_ids") or [])
                is_my_mediador = p.get("assigned_mediador_id") == user_id or user_id in (p.get("assigned_mediador_ids") or [])

                enriched_processes.append({
                    **p,
                    "consultor_name": ", ".join(consultor_names) if consultor_names else (p.get("consultor_name") or ""),
                    "mediador_name": ", ".join(mediador_names) if mediador_names else (p.get("mediador_name") or ""),
                    "indexacao_name": indexacao_name,
                    "parceiro_name": parceiro_name,
                    "is_assigned_to_me": is_my_consultor or is_my_mediador,
                    "my_role_in_process": "consultor" if is_my_consultor else ("intermediario" if is_my_mediador else None)
                })

            kanban.append({
                "id": status.get("id") or status_name,
                "name": status_name,
                "label": status.get("label") or status_name.replace("_", " ").title(),
                "color": status.get("color") or "#6B7280",
                "order": status.get("order", 0),
                "processes": enriched_processes,
                "count": len(enriched_processes)
            })
    except KeyError as e:
        logger.error(f"[KANBAN] KeyError ao iterar workflow_statuses: {e}. Statuses: {statuses}")
        raise HTTPException(status_code=500, detail=f"Erro de configuração de estados do workflow: campo '{e.args[0]}' em falta. Verifique a configuração em /workflow-estados.")
    except Exception as e:
        logger.exception(f"[KANBAN] Erro inesperado ao construir kanban: {e}")
        raise HTTPException(status_code=500, detail=f"Erro ao carregar kanban: {type(e).__name__}: {e}")

    return {
        "columns": kanban,
        "total_processes": active_count,
        "total_inactive": inactive_count,
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
    
    # Construir query baseada no papel do utilizador
    #
    # SINCRONIZAÇÃO COM "OS Meus Processos":
    # A query de my-clients deve usar EXATAMENTE o mesmo critério base que
    # my-processes (assigned_consultor_ids + is_active + status), para que
    # os clientes listados correspondam aos processos visíveis.
    # A estes somam-se os Leads (clientes sem processo) criados pelo utilizador.
    if role == UserRole.CONSULTOR:
        query = {
            "$and": [
                {"$or": [
                    {"assigned_consultor_ids": user_id},
                    {"assigned_consultor_id": user_id}
                ]},
                # Mesmo filtro de activos que my-processes (view_mode="active_only")
                {"is_active": {"$ne": False}},
                {"status": {"$nin": INACTIVE_STATUSES}},
                {"is_deleted": {"$ne": True}}
            ]
        }
    elif role == UserRole.INTERMEDIARIO:
        query = {
            "$and": [
                {"$or": [
                    {"assigned_mediador_ids": user_id},
                    {"assigned_mediador_id": user_id},
                    {"created_by": user_email}
                ]},
                {"is_active": {"$ne": False}},
                {"status": {"$nin": INACTIVE_STATUSES}},
                {"is_deleted": {"$ne": True}}
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
    
    # ── BUSCAR LEADS (clientes sem processo) criados pelo utilizador ──
    # Leads são clientes na tabela 'clients' que NÃO têm processo associado
    # e foram criados pelo utilizador actual. Estes devem aparecer em
    # "Os Meus Clientes" juntamente com os clientes dos processos activos.
    leads = []
    if role in [UserRole.CONSULTOR, UserRole.INTERMEDIARIO]:
        leads_query = {
            "$and": [
                {"created_by": user_id},
                {"is_deleted": {"$ne": True}},
                # Sem processo associado (Lead puro)
                {"$or": [
                    {"process_ids": {"$exists": False}},
                    {"process_ids": []},
                    {"process_ids": None}
                ]},
                # Apenas leads pendentes (não convertidos)
                {"$or": [
                    {"lead_status": {"$exists": False}},
                    {"lead_status": "new"}
                ]}
            ]
        }
        leads_cursor = await db.clients.find(
            leads_query,
            {
                "_id": 0, "id": 1, "nome": 1, "contacto": 1,
                "created_at": 1, "updated_at": 1, "fonte": 1,
                "assigned_to": 1, "lead_status": 1
            }
        ).to_list(500)
        
        # Desencriptar dados sensíveis dos leads
        from services.encryption import decrypt_clients_list
        leads_cursor = decrypt_clients_list(leads_cursor)
        
        # Converter leads para o mesmo formato dos clientes de processo
        for lead in leads_cursor:
            contacto = lead.get("contacto", {})
            leads.append({
                "id": lead.get("id"),
                "client_id": lead.get("id"),
                "process_number": None,
                "client_name": lead.get("nome", "Sem nome"),
                "client_email": contacto.get("email", ""),
                "client_phone": contacto.get("telefone", ""),
                "status": "lead",
                "status_label": "Lead",
                "status_color": "#8B5CF6",  # Roxo para distinguir leads
                "process_type": "lead",
                "consultor_name": "",
                "pending_actions": [],
                "pending_count": 0,
                "created_at": lead.get("created_at"),
                "updated_at": lead.get("updated_at"),
                "deed_date": None,
                "has_property": False,
                "is_lead": True  # Flag para identificar leads no frontend
            })
    
    # Obter labels das fases do workflow ordenadas
    statuses = await db.workflow_statuses.find({}, {"_id": 0}).sort("order", 1).to_list(100)
    status_map = {s["name"]: s for s in statuses}
    
    # Ordenar processos por fase (order do status) e depois por nome
    def get_sort_key(p):
        """Gera chave de ordenação para processos e leads.

        Ordena primeiro pela ordem da fase no workflow (phase_order),
        depois por nome do cliente em ordem alfabética. Leads ficam no
        início (order=0) para destaque.

        Args:
            p: Dicionário do processo ou lead.

        Returns:
            tuple: (phase_order, client_name_lower).
        """
        if p.get("is_lead"):
            return (0, p.get("client_name", "").lower())  # Leads no topo
        status_info = status_map.get(p.get("status"), {})
        phase_order = status_info.get("order", 999)
        client_name = p.get("client_name", "").lower()
        return (phase_order, client_name)
    
    # Combinar processos + leads, ordenar e paginar
    all_items = processes + leads
    all_items = sorted(all_items, key=get_sort_key)
    
    # Total e paginação (após ordenação)
    total = len(all_items)
    paginated_items = all_items[skip:skip + size]
    
    # Obter tarefas pendentes por processo (apenas IDs necessários)
    # Leads não têm tarefas, pelo que apenas processos com id são pesquisados
    process_ids = [p["id"] for p in paginated_items if not p.get("is_lead")]
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
    consultor_ids = list(set(p.get("assigned_consultor_id") for p in paginated_items if p.get("assigned_consultor_id")))
    consultores = await db.users.find(
        {"id": {"$in": consultor_ids}},
        {"_id": 0, "id": 1, "name": 1}
    ).to_list(100)
    consultor_map = {c["id"]: c["name"] for c in consultores}
    
    # Construir lista de clientes com informações enriquecidas
    clients_list = []
    for p in paginated_items:
        # Leads já vêm formatados — adicionar directamente
        if p.get("is_lead"):
            clients_list.append(p)
            continue
        
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
            "client_id": p.get("client_id"),
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
        "user_role": role,
        "leads_count": len(leads)
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
    
    # === SNAPSHOT FINANCEIRO: Criar ProcessFinance ao mover para Concluídos ===
    if new_status == "concluidos":
        try:
            await _create_finance_snapshot(process, user)
        except Exception as snap_err:
            # Falha no snapshot não deve impedir a mudança de estado
            import logging as _log
            _log.getLogger(__name__).warning(
                f"Falha ao criar snapshot financeiro para processo {process_id}: {snap_err}"
            )
    
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
    
    # === GATILHO: Fila de espera ao mover para estado terminal ===
    # Se o processo foi atribuído a um indexador e moveu para concluídos/desistências,
    # o indexador libertou um slot — verificar se há processos na fila_espera.
    if new_status in ["concluidos", "desistencias"]:
        try:
            from services.process_assignment import check_waitlist_for_indexer
            import asyncio as _asyncio
            assigned_indexer_id = process.get("assigned_indexacao_id")
            if assigned_indexer_id:
                _asyncio.create_task(check_waitlist_for_indexer(assigned_indexer_id))
                logger.info(
                    f"[KANBAN-MOVE] Gatilho de fila de espera disparado para "
                    f"indexador {assigned_indexer_id} (processo {process_id} → {new_status})"
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
    
    # ==================================================================
    # SALTO DINÂMICO DE ESTADO — Consultar pipeline de workflow_statuses
    # ==================================================================
    # Em vez de hardcode do ID do estado seguinte (ex: status_id = 4),
    # consultamos a ordem dos estados configurados na BD, identificamos
    # a posição actual do processo e fazemos next_status = current + 1.
    current_status = process.get("status", "clientes_espera")
    next_status = None  # Inicializar — pode ficar None se for o último estado

    # Buscar todos os workflow_statuses ordenados por 'order'
    all_statuses = await db.workflow_statuses.find(
        {}, {"_id": 0}
    ).sort("order", 1).to_list(100)

    # Montar lista ordenada de nomes de estado
    status_pipeline = [s["name"] for s in all_statuses]

    # Encontrar a posição actual e calcular o próximo estado
    if current_status in status_pipeline:
        current_idx = status_pipeline.index(current_status)
        if current_idx < len(status_pipeline) - 1:
            next_status = status_pipeline[current_idx + 1]
            logger.info(
                f"[INDEXACAO-DYNAMIC] Salto dinâmico: '{current_status}' (pos {current_idx}) "
                f"→ '{next_status}' (pos {current_idx + 1})"
            )
        else:
            logger.info(
                f"[INDEXACAO-DYNAMIC] Processo já está no último estado da pipeline "
                f"('{current_status}'). Sem salto automático."
            )
    else:
        # Status actual não está na pipeline — avançar para o 1º estado
        # (fallback seguro — processo não fica órfão)
        if status_pipeline:
            next_status = status_pipeline[0]
            logger.warning(
                f"[INDEXACAO-DYNAMIC] Status actual '{current_status}' não encontrado "
                f"na pipeline. Fallback para o 1º estado: '{next_status}'"
            )

    # ==================================================================
    # LIMPEZA E TRANSIÇÃO DE RESPONSABILIDADE
    # ==================================================================
    # Após calcular o próximo estado, o campo assigned_indexacao_id é limpo
    # (null), pois o trabalho de indexação/triagem acabou.
    now = datetime.now(timezone.utc).isoformat()
    update_set = {
        "is_indexed": True,
        "indexed_at": now,
        "indexed_by": user.get("id"),
        "indexed_by_name": user.get("name", ""),
        "assigned_indexacao_id": None,   # Limpar — trabalho de indexação concluído
        "indexacao_name": None,          # Limpar nome do indexador
        "updated_at": now,
    }

    # Se conseguimos calcular o próximo estado, adicioná-lo ao update
    if next_status:
        update_set["status"] = next_status

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
    assigned_ids = list(set(filter(None, (
        (process.get("assigned_consultor_ids") or []) +
        ([process["assigned_consultor_id"]] if process.get("assigned_consultor_id") else []) +
        (process.get("assigned_mediador_ids") or []) +
        ([process["assigned_mediador_id"]] if process.get("assigned_mediador_id") else []) +
        ([process["assigned_indexacao_id"]] if process.get("assigned_indexacao_id") else [])
    ))))
    
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
    # DUPLA AUTO-ATRIBUIÇÃO (Conversão Pré-Registo → Pipeline)
    # ==================================================================
    # Se o processo transitou de pre_registo, dispara a dupla
    # auto-atribuição (consultor + intermediário em simultâneo).
    # Caso contrário, usa a lógica de auto-atribuição de consultor apenas.
    consultant_result = None
    is_pre_registo_transition = (current_status == "pre_registo")

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
        # Gerar blind indexes para NIF/email se foram atualizados
        if "dados_pessoais.nif" in client_updates:
            nif_val = client_updates["dados_pessoais.nif"]
            nif_hash = generate_nif_hash(nif_val)
            if nif_hash:
                client_updates["dados_pessoais.nif_hash"] = nif_hash
        if "contacto.email" in client_updates:
            email_val = client_updates["contacto.email"]
            email_hash = generate_email_hash(email_val)
            if email_hash:
                client_updates["contacto.email_hash"] = email_hash
        
        # Encriptar dados sensíveis do cliente antes de guardar
        try:
            from services.encryption import encrypt_client_data
            # Construir doc temporário para encriptação seletiva
            temp_client_update = {}
            for k, v in client_updates.items():
                if k.startswith("dados_pessoais."):
                    if "dados_pessoais" not in temp_client_update:
                        temp_client_update["dados_pessoais"] = {}
                    temp_client_update["dados_pessoais"][k.replace("dados_pessoais.", "")] = v
                elif k.startswith("contacto."):
                    if "contacto" not in temp_client_update:
                        temp_client_update["contacto"] = {}
                    temp_client_update["contacto"][k.replace("contacto.", "")] = v
                else:
                    temp_client_update[k] = v
            
            encrypted = encrypt_client_data(temp_client_update)
            # Reconverter para formato dot-notation
            final_client_updates = {}
            for k, v in client_updates.items():
                if k.startswith("dados_pessoais.") and "dados_pessoais" in encrypted:
                    field = k.replace("dados_pessoais.", "")
                    if field in encrypted["dados_pessoais"]:
                        final_client_updates[k] = encrypted["dados_pessoais"][field]
                    else:
                        final_client_updates[k] = v
                elif k.startswith("contacto.") and "contacto" in encrypted:
                    field = k.replace("contacto.", "")
                    if field in encrypted["contacto"]:
                        final_client_updates[k] = encrypted["contacto"][field]
                    else:
                        final_client_updates[k] = v
                elif k in encrypted:
                    final_client_updates[k] = encrypted[k]
                else:
                    final_client_updates[k] = v
            
            # Adicionar hash indexes que não precisam de encriptação
            if "dados_pessoais.nif_hash" in client_updates:
                final_client_updates["dados_pessoais.nif_hash"] = client_updates["dados_pessoais.nif_hash"]
            if "contacto.email_hash" in client_updates:
                final_client_updates["contacto.email_hash"] = client_updates["contacto.email_hash"]
            
            client_updates = final_client_updates
        except Exception as e:
            logger.warning(f"Erro ao encriptar dados do cliente: {e}")
        
        now_iso = datetime.now(timezone.utc).isoformat()
        client_updates["updated_at"] = now_iso
        await db.clients.update_one(
            {"id": client_id},
            {"$set": client_updates}
        )
        logger.info(f"Dados pessoais do cliente {client_id} atualizados via PUT processo: {list(client_updates.keys())}")

        # ── SINCRONIZAÇÃO INVERSA: Se o nome do cliente mudou, propagar para todos os processos ──
        # Quando o utilizador edita o nome dentro do processo, atualizamos o cliente
        # e precisamos de propagar o novo nome para os restantes processos desse cliente.
        updated_client_name = client_updates.get("nome")
        if updated_client_name:
            # Obter todos os process_ids do cliente
            updated_client = await db.clients.find_one({"id": client_id}, {"process_ids": 1})
            all_process_ids = updated_client.get("process_ids", []) if updated_client else []
            # Filtrar o processo atual para não fazer update desnecessário
            other_process_ids = [pid for pid in all_process_ids if pid != process_id]
            if other_process_ids:
                cascade_sync = {
                    "client_name": updated_client_name,
                    "personal_data.nome": updated_client_name,
                    "personal_data.name": updated_client_name,
                }
                await db.processes.update_many(
                    {"id": {"$in": other_process_ids}},
                    {"$set": cascade_sync}
                )
                logger.info(f"Sincronização inversa: nome '{updated_client_name}' propagado para {len(other_process_ids)} processos do cliente {client_id}")
    
    # ── REATRIBUIÇÃO DE CLIENTE: Se o body inclui client_id diferente do actual ──
    new_client_id = raw_body.get("client_id")
    if new_client_id and new_client_id != process.get("client_id"):
        # Apenas admin, ceo e diretor podem reatribuir clientes
        if role not in [UserRole.ADMIN, UserRole.CEO, UserRole.DIRETOR]:
            raise HTTPException(
                status_code=403,
                detail="Apenas administradores, CEO ou directores podem reatribuir o cliente de um processo."
            )
        
        # Validar que o novo cliente existe
        new_client_doc = await db.clients.find_one({"id": new_client_id})
        if not new_client_doc:
            raise HTTPException(
                status_code=404,
                detail=f"Cliente com ID '{new_client_id}' não encontrado."
            )
        
        # Desencriptar dados do novo cliente
        decrypted_new_client = decrypt_client_data(new_client_doc)
        new_client_name = decrypted_new_client.get("nome", "")
        new_client_email = decrypted_new_client.get("contacto", {}).get("email", "")
        new_client_phone = decrypted_new_client.get("contacto", {}).get("telefone", "")
        
        old_client_id = process.get("client_id")
        old_client_name = process.get("client_name", "")
        
        now_reassign = datetime.now(timezone.utc).isoformat()
        
        # Remover processo do cliente antigo (process_ids)
        if old_client_id:
            await db.clients.update_one(
                {"id": old_client_id},
                {
                    "$pull": {"process_ids": process_id},
                    "$set": {"updated_at": now_reassign}
                }
            )
        
        # Adicionar processo ao novo cliente (process_ids)
        await db.clients.update_one(
            {"id": new_client_id},
            {
                "$addToSet": {"process_ids": process_id},
                "$set": {"updated_at": now_reassign}
            }
        )
        
        # Actualizar dados do processo com novo cliente
        # Actualizar client_ids também (suporte N:M)
        current_client_ids = process.get("client_ids", [])
        if old_client_id and old_client_id in current_client_ids:
            current_client_ids = [cid for cid in current_client_ids if cid != old_client_id]
        if new_client_id not in current_client_ids:
            current_client_ids.insert(0, new_client_id)  # Novo cliente principal no início
        
        # Os campos client_name, client_email, client_phone serão adicionados ao update_data
        # Mas como serão encriptados mais abaixo, adicionamos ao raw update
        process["client_id"] = new_client_id
        process["client_name"] = new_client_name
        process["client_email"] = new_client_email
        process["client_phone"] = new_client_phone
        process["client_ids"] = current_client_ids
        
        # Registar no histórico
        await log_history(
            process_id, user,
            f"Reatribuiu cliente de '{old_client_name}' para '{new_client_name}'"
        )
        await log_audit_event(
            process_id, user,
            f"Reatribuiu cliente de '{old_client_name}' para '{new_client_name}'",
            request=request, source="web"
        )
        logger.info(
            f"Processo {process_id} reatribuído de cliente {old_client_id} ({old_client_name}) "
            f"para cliente {new_client_id} ({new_client_name}) por {user.get('email')}"
        )
    
    # Indexação só pode actualizar dados financeiros (restante é bloqueado mais abaixo)
    is_indexacao = role == UserRole.INDEXACAO
    
    # Bloquear edição de processos em status terminal (eliminados, desistências, concluídos)
    # EXCEPÇÃO: admin e CEO podem editar processos concluídos para correção retroativa
    # de valores financeiros (sincronização financeira retroativa).
    BLOCKED_STATUSES = ["eliminados", "desistencias", "concluidos"]
    is_admin_or_ceo = role in [UserRole.ADMIN, UserRole.CEO]
    if process.get("status") in BLOCKED_STATUSES and not is_admin_or_ceo:
        raise HTTPException(
            status_code=403,
            detail=f"Não é possível editar um processo em estado terminal ({process.get('status')})."
        )
    
    update_data = {"updated_at": datetime.now(timezone.utc).isoformat()}
    
    # ── Incluir client_email/client_phone do raw body (enviados pelo Frontend) ──
    # Estes campos são guardados directamente no documento do processo.
    # A sincronização para o cliente e para personal_data.email é feita
    # pelo mecanismo de client_updates (extract_client_updates_from_body)
    # e pelo sync do client update (clients.py:1295-1314).
    if raw_client_email is not None:
        update_data["client_email"] = raw_client_email
    if raw_client_phone is not None:
        update_data["client_phone"] = raw_client_phone
    
    # ── Incluir dados de reatribuição no update_data (se houve reatribuição) ──
    if new_client_id and new_client_id != client_id:
        # client_id já foi actualizado no process dict acima
        update_data["client_id"] = process["client_id"]
        update_data["client_name"] = process["client_name"]
        update_data["client_email"] = process["client_email"]
        update_data["client_phone"] = process["client_phone"]
        update_data["client_ids"] = process["client_ids"]
    
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
        # Staff updates — APENAS dados de negócio (não dados pessoais)
        if data.real_estate_data and can_update_real_estate:
            incoming_re = data.real_estate_data.model_dump(exclude_unset=True)
            _re = process.get("real_estate_data")
            existing_re = _re if isinstance(_re, dict) else {}
            merged_re = {**existing_re, **incoming_re}
            # Remover campos com valor None (utilizador limpou o campo)
            merged_re = {k: v for k, v in merged_re.items() if v is not None}
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
            incoming_credit = data.credit_data.model_dump(exclude_unset=True)
            _cd = process.get("credit_data")
            existing_credit = _cd if isinstance(_cd, dict) else {}
            merged_credit = {**existing_credit, **incoming_credit}
            # Remover campos com valor None (utilizador limpou o campo)
            merged_credit = {k: v for k, v in merged_credit.items() if v is not None}
            await log_data_changes(process_id, user, existing_credit, incoming_credit, "dados de crédito")
            await log_audit_event(process_id, user, "Alterou dados de crédito", request=request, source="web", audit_reason=audit_reason, ai_suggested=ai_suggested, ai_approved_by=user.get("id") if ai_suggested else None)
            update_data["credit_data"] = merged_credit

        # ── Dados financeiros (financial_data) ──
        # O frontend envia financial_data no body do PUT, mas ProcessUpdate
        # não inclui este campo (é schemaless dict no MongoDB).
        # Extraímos do raw_body e fazemos merge com os dados existentes.
        if can_update_financial:
            incoming_fd = raw_body.get("financial_data")
            if isinstance(incoming_fd, dict):
                _fd = process.get("financial_data")
                existing_fd = _fd if isinstance(_fd, dict) else {}
                merged_fd = {**existing_fd, **incoming_fd}
                # Remover campos com valor None (utilizador limpou o campo)
                merged_fd = {k: v for k, v in merged_fd.items() if v is not None and v != ""}
                await log_data_changes(process_id, user, existing_fd, incoming_fd, "dados financeiros")
                await log_audit_event(process_id, user, "Alterou dados financeiros", request=request, source="web", audit_reason=audit_reason, ai_suggested=ai_suggested, ai_approved_by=user.get("id") if ai_suggested else None)
                update_data["financial_data"] = merged_fd

        # Campos adicionais do CPCV
        # ── second_client_id (2º titular ligado a cliente existente) ──
        if data.second_client_id is not None:
            new_second_id = data.second_client_id.strip() if data.second_client_id else None
            # Validar que o cliente existe (se foi fornecido um ID)
            if new_second_id:
                second_client = await db.clients.find_one({"id": new_second_id})
                if not second_client:
                    raise HTTPException(status_code=400, detail=f"Cliente com ID {new_second_id} não encontrado")
                # Não permitir que o 2º titular seja o mesmo que o titular principal
                if new_second_id == process.get("client_id"):
                    raise HTTPException(status_code=400, detail="O 2º titular não pode ser o mesmo cliente que o titular principal")
            update_data["second_client_id"] = new_second_id
            # Se removeu o 2º titular, limpar dados associados
            if not new_second_id:
                update_data["second_client_name"] = None
                # Não limpar titular2_data — pode ter dados preenchidos manualmente
            else:
                update_data["second_client_name"] = second_client.get("nome", "")

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
        
        # Metadados do processo
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
    
    # === SINCRONIZAÇÃO FINANCEIRA RETROATIVA ===
    # Se o processo está num status de ganho (concluído/escritura), garantir que
    # o snapshot financeiro (process_finances) existe e está atualizado com os
    # valores mais recentes de real_estate_data e credit_data.
    # Isto assegura que expected_commission, real_estate_base_value e
    # credit_base_value refletem sempre os dados submetidos pelo utilizador.
    current_status = updated.get("status", "")
    finance_relevant_statuses = ["concluidos", "escritura", "escritura_agendada"]
    if current_status in finance_relevant_statuses:
        # Desencriptar updated para obter valores reais antes do snapshot
        try:
            decrypted_for_finance = decrypt_sensitive_data(updated)
        except Exception:
            decrypted_for_finance = updated
        try:
            await _ensure_finance_snapshot(decrypted_for_finance, user)
        except Exception as snap_err:
            logger.warning(
                f"Falha na sincronização financeira retroativa para processo {process_id}: {snap_err}"
            )
    
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
    
    # ── FASE 2: Popular dados do cliente na resposta (retrocompatibilidade) ──
    updated = await populate_client_data(updated)
    
    try:
        return ProcessResponse(**updated)
    except Exception as e:
        logger.error(f"Erro ao serializar resposta do processo {process_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Erro interno ao serializar dados do processo: {str(e)[:200]}")


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

    # ── Deteção de novos utilizadores atribuídos (para email automático) ──
    newly_assigned_consultores = []
    newly_assigned_mediadores = []
    newly_assigned_indexacao = []
    newly_assigned_parceiro = []

    # Consultores recém-atribuídos
    new_consultor_list = update_data.get("assigned_consultor_ids")
    if new_consultor_list:
        old_set = set(old_consultor_ids or [])
        newly_assigned_consultores = [cid for cid in new_consultor_list if cid not in old_set]

    # Mediadores recém-atribuídos
    new_mediador_list = update_data.get("assigned_mediador_ids")
    if new_mediador_list:
        old_set = set(old_mediador_ids or [])
        newly_assigned_mediadores = [mid for mid in new_mediador_list if mid not in old_set]

    # Indexação recém-atribuída
    new_indexacao = update_data.get("assigned_indexacao_id")
    if new_indexacao and new_indexacao != old_indexacao:
        newly_assigned_indexacao = [new_indexacao]

    # Parceiro recém-atribuído
    new_parceiro = update_data.get("assigned_parceiro_id")
    if new_parceiro and new_parceiro != old_parceiro:
        newly_assigned_parceiro = [new_parceiro]

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

    # === EMAIL AUTOMÁTICO: Notificar utilizadores recém-atribuídos ===
    client_name = process.get("client_name", "Cliente")
    process_number = process.get("process_number", "")
    if newly_assigned_consultores:
        asyncio.create_task(_send_assignment_email(
            newly_assigned_consultores, process_id, client_name, process_number, "Consultor"
        ))
    if newly_assigned_mediadores:
        asyncio.create_task(_send_assignment_email(
            newly_assigned_mediadores, process_id, client_name, process_number, "Intermediário"
        ))
    if newly_assigned_indexacao:
        asyncio.create_task(_send_assignment_email(
            newly_assigned_indexacao, process_id, client_name, process_number, "Indexação"
        ))
    if newly_assigned_parceiro:
        asyncio.create_task(_send_assignment_email(
            newly_assigned_parceiro, process_id, client_name, process_number, "Parceiro"
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


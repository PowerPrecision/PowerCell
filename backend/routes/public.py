"""
====================================================================
ROTAS PÚBLICAS - CREDITOIMO
====================================================================
Endpoints públicos (sem autenticação).

FLUXO DE REGISTO:
1. Formulário público cria ficha de cliente na tabela 'clients'
2. Quando o cliente é atribuído a um utilizador, cria-se o processo
3. Um cliente pode ter vários processos

SEGURANÇA: Rate limiting aplicado para prevenir abusos.
====================================================================
"""
import re
import uuid
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Request, BackgroundTasks
from fastapi.responses import JSONResponse

from slowapi import Limiter
from slowapi.util import get_remote_address

logger = logging.getLogger(__name__)

from database import db
from services.s3_storage import s3_service
from models.auth import UserRole
from models.process import PublicClientRegistration
from services.email import send_registration_confirmation, send_new_client_notification
from services.alerts import notify_new_client_registration
from services.process_service import get_next_process_number
from services.encryption import (
    encrypt_client_data,
    decrypt_client_data,
    generate_nif_hash,
    generate_email_hash,
)
from utils.input_sanitization import (
    sanitize_email, sanitize_name, sanitize_phone, sanitize_nif,
    sanitize_string, log_sanitization_rejection
)
from routes.form_config import DEFAULT_FORM_CONFIG, DEFAULT_STEP_CONFIG

limiter = Limiter(key_func=get_remote_address)

router = APIRouter(prefix="/public", tags=["Public"])


@router.post("/client-registration")
@limiter.limit("5/hour")  # Rate limit restritivo para prevenir spam de registos
async def public_client_registration(request: Request, data: PublicClientRegistration):
    """
    Endpoint público para registo de clientes - sem autenticação.
    
    FLUXO:
    1. Verifica se email ou NIF já existem (bloqueia duplicados)
    2. Cria ficha de cliente na tabela 'clients' (NÃO cria processo)
    3. Envia email de confirmação ao cliente
    4. Notifica administradores/staff
    5. Gera alertas no sistema
    
    O processo é criado quando o cliente é atribuído a um utilizador.
    """
    
    # Sanitizar inputs
    clean_email = sanitize_email(data.email)
    if not clean_email:
        log_sanitization_rejection("email", data.email, "email inválido no registo público")
        return JSONResponse(status_code=400, content={"success": False, "detail": "Email inválido"})
    
    clean_name = sanitize_name(data.name) if data.name else ""
    clean_phone = sanitize_phone(data.phone) if data.phone else None
    
    # =========================================
    # VERIFICAR DUPLICADOS (EMAIL E NIF)
    # Usar blind indexes para pesquisa de dados encriptados
    # =========================================

    # Verificar se já existe cliente com o mesmo email
    # Usar blind index (email_hash) para dados encriptados, fallback para plain text
    email_hash = generate_email_hash(clean_email)
    existing_by_email = None
    if email_hash:
        existing_by_email = await db.clients.find_one({"contacto.email_hash": email_hash})
    if not existing_by_email:
        # Fallback para dados antigos não migrados
        existing_by_email = await db.clients.find_one({"contacto.email": clean_email.lower()})

    if existing_by_email:
        # Registar duplicado no system_error_logger para monitoring
        try:
            from services.system_error_logger import system_error_logger
            await system_error_logger.log_error(
                error_type="duplicate_registration",
                message=f"Registo duplicado (email): {clean_email}",
                component="public_form",
                details={"reason": "email", "email": clean_email, "existing_client_id": existing_by_email.get("id")},
                severity="info",
                request_path="/api/public/client-registration"
            )
        except Exception:
            pass
        return JSONResponse(
            status_code=200,
            content={
                "success": False,
                "blocked": True,
                "reason": "email",
                "message": "Já existe um registo com este email. A nossa equipa entrará em contacto consigo em breve."
            }
        )

    # Verificar se já existe cliente com o mesmo NIF
    # NOTA: NIF já não vem no PublicClientRegistration (removido na Fase 1)
    # O NIF será recolhido depois pelo consultor durante o processo
    clean_nif = None
    if clean_nif:
        # Usar blind index (nif_hash) para dados encriptados, fallback para plain text
        nif_hash = generate_nif_hash(clean_nif)
        existing_by_nif = None
        if nif_hash:
            existing_by_nif = await db.clients.find_one({"dados_pessoais.nif_hash": nif_hash})
        if not existing_by_nif:
            # Fallback para dados antigos não migrados
            existing_by_nif = await db.clients.find_one({"dados_pessoais.nif": clean_nif})

        if existing_by_nif:
            # Registar duplicado no system_error_logger para monitoring
            try:
                from services.system_error_logger import system_error_logger
                await system_error_logger.log_error(
                    error_type="duplicate_registration",
                    message=f"Registo duplicado (NIF): {clean_nif}",
                    component="public_form",
                    details={"reason": "nif", "nif": clean_nif, "existing_client_id": existing_by_nif.get("id")},
                    severity="info",
                    request_path="/api/public/client-registration"
                )
            except Exception:
                pass
            return JSONResponse(
                status_code=200,
                content={
                    "success": False,
                    "blocked": True,
                    "reason": "nif",
                    "message": "Já existe um registo com este NIF. A nossa equipa entrará em contacto consigo em breve."
                }
            )
    
    client_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    
    # Processar dados do formulário
    has_property = data.has_property or False
    
    personal_data = {
        "nome": clean_name,
        "email": clean_email,
        "telefone": clean_phone,
    }
    
    birth_date = None  # Não recolhido no formulário público
    idade_menos_35 = False
    
    # Segundo titular já não vem no formulário (removido Titular2Data)
    second_client_name = None
    
    # =========================================
    # CRIAR FICHA DE CLIENTE (tabela clients)
    # RGPD: Encriptar dados sensíveis ANTES de inserir
    # =========================================
    client_doc = {
        "id": client_id,
        "nome": clean_name,
        "contacto": {
            "email": clean_email.lower(),
            "telefone": clean_phone
        },
        "dados_pessoais": personal_data,
        "dados_financeiros": {},  # Dados financeiros pertencem ao Processo
        "dados_imobiliarios": {},  # Dados do imóvel recolhidos depois
        "process_ids": [],  # Vazio até ser criado o processo
        "fonte": "public_form",
        "has_property": has_property,
        "idade_menos_35": idade_menos_35,
        "created_at": now,
        "updated_at": now,
        "registration_completed": True,  # Marcar que completou o registo
        "assigned_to": None,  # Atribuído a nenhum utilizador inicialmente
        "assigned_at": None,
        "custom_fields": data.custom_fields if data.custom_fields else {},
    }

    # RGPD: Encriptar dados sensíveis ANTES de inserir na BD
    # Isto garante que NIFs, telefones e outros dados sensíveis
    # nunca são guardados em plain text
    try:
        client_doc = encrypt_client_data(client_doc)
        logger.info(f"Dados do cliente {client_id} encriptados com sucesso (blind indexes incluídos)")
    except Exception as e:
        logger.warning(f"Falha ao encriptar dados do cliente {client_id}: {e}")
        try:
            from services.system_error_logger import system_error_logger
            await system_error_logger.log_error(
                error_type="encryption_failure",
                message=f"Falha ao encriptar dados do cliente {client_id}: {e}",
                component="public_form",
                details={"client_id": client_id, "error": str(e)},
                severity="warning",
                request_path="/api/public/client-registration"
            )
        except Exception:
            pass

    await db.clients.insert_one(client_doc)
    
    # =========================================
    # M3 - CRIAR PASTA S3 PARA O CLIENTE
    # =========================================
    try:
        import asyncio
        result = await asyncio.to_thread(
            s3_service.initialize_client_folders,
            client_id,
            clean_name,
            second_client_name
        )
        # initialize_client_folders retorna (success, folder_path)
        if result and len(result) == 2:
            success, s3_folder_name = result
            if success and s3_folder_name:
                await db.clients.update_one(
                    {"id": client_id},
                    {"$set": {"s3_folder": s3_folder_name}}
                )
                logger.info(f"Pasta S3 criada para cliente {client_id}: {s3_folder_name}")
    except Exception as e:
        logger.warning(f"Não foi possível criar pasta S3 para cliente {client_id}: {e}")
        try:
            from services.system_error_logger import system_error_logger
            await system_error_logger.log_error(
                error_type="s3_folder_failure",
                message=f"Falha ao criar pasta S3 para cliente {client_id}: {e}",
                component="public_form",
                details={"client_id": client_id, "error": str(e)},
                severity="warning",
                request_path="/api/public/client-registration"
            )
        except Exception:
            pass
    
    # =========================================
    # ENVIAR EMAIL DE CONFIRMAÇÃO AO CLIENTE
    # Usa Task Queue para não bloquear a resposta
    # =========================================
    from services.task_queue import task_queue
    
    # Tentar enfileirar (se Redis disponível)
    job_id = await task_queue.send_registration_email(
        client_email=clean_email,
        client_name=clean_name
    )
    
    # Se Task Queue não disponível, enviar directamente
    if not job_id:
        logger.info("Task Queue não disponível, enviando email directamente")
        await send_registration_confirmation(
            client_email=clean_email,
            client_name=clean_name
        )
    
    # =========================================
    # NOTIFICAR STAFF SOBRE NOVO REGISTO
    # =========================================
    
    # Criar alertas no sistema de notificações
    await notify_new_client_registration(client_doc, has_property)
    
    # =========================================
    # ENVIAR PUSH NOTIFICATIONS PARA STAFF
    # =========================================
    try:
        from services.push_notifications import send_push_notification, broadcast_push_notification
        
        # Notificar todos os admins, CEOs e directores via push
        from services.role_query import deep_role_in_filter
        staff_for_push = await db.users.find(
            {"$and": [deep_role_in_filter([UserRole.ADMIN, UserRole.CEO, UserRole.DIRETOR]), {"is_active": True}]},
            {"_id": 0, "id": 1}
        ).to_list(20)
        
        for staff_member in staff_for_push:
            await send_push_notification(
                user_id=staff_member["id"],
                title="Novo Cliente Registado",
                body=f"{clean_name} registou-se via formulário",
                tag="new_client",
                url="/clientes",  # Link para página de registos
                data={
                    "type": "new_client",
                    "client_id": client_id,
                    "client_name": clean_name
                }
            )
        
        logger.info(f"Push notifications enviadas para {len(staff_for_push)} membros do staff")
    except Exception as e:
        logger.warning(f"Erro ao enviar push notifications: {e}")
        # Não falhar o registo se push notifications falharem
    
    # Enviar email apenas para o PRIMEIRO admin/CEO (evitar spam)
    # Os outros são notificados via sistema de alertas interno
    from services.role_query import deep_role_in_filter
    staff = await db.users.find(
        deep_role_in_filter([UserRole.ADMIN, UserRole.CEO, UserRole.DIRETOR]),
        {"_id": 0}
    ).to_list(100)
    
    # Enviar email apenas para o primeiro membro (reduz spam)
    if staff:
        first_admin = staff[0]
        staff_job = await task_queue.send_email(
            to=first_admin["email"],
            subject=f"Novo Cliente Registado: {clean_name}",
            body=f"Foi registado um novo cliente via formulário público:\n\nNome: {clean_name}\nEmail: {clean_email}\nTelefone: {clean_phone or 'N/A'}\n\nO cliente aguarda atribuição."
        )
        
        # Fallback se Task Queue não disponível
        if not staff_job:
            await send_new_client_notification(
                client_name=clean_name,
                client_email=clean_email,
                client_phone=clean_phone or "N/A",
                process_type=data.process_type,
                staff_email=first_admin["email"],
                staff_name=first_admin["name"]
            )
    
    # Retornar JSONResponse explicitamente para compatibilidade com slowapi rate limiter
    return JSONResponse(
        status_code=200,
        content={
            "success": True,
            "message": "Registo criado com sucesso. Verifique o seu email.",
            "client_id": client_id,
            "has_property": has_property,
            "idade_menos_35": idade_menos_35,
            "email_queued": bool(job_id)
        }
    )


@router.get("/health")
@limiter.limit("30/minute")
async def public_health(request: Request):
    """Health check público."""
    return JSONResponse(status_code=200, content={"status": "ok", "public": True})


@router.get("/form-config")
@limiter.limit("60/minute")
async def get_public_form_config(request: Request):
    """Obter configuração do formulário público (todos os campos visíveis, ordenados).

    Retorna dois conjuntos:
    - custom_fields: apenas campos personalizados (compatibilidade com versões anteriores)
    - all_fields: todos os campos visíveis ordenados por step + order (nativos + custom)
    """
    config = await db.form_config.find_one({"type": "public_form"}, {"_id": 0})
    if not config:
        # Sem config na DB — retornar defaults (all_fields para o frontend usar)
        visible_defaults = [f for f in DEFAULT_FORM_CONFIG if f.get("is_visible")]
        visible_defaults.sort(key=lambda f: (f.get("step", 0), f.get("order", 0)))
        return JSONResponse(status_code=200, content={"custom_fields": [], "all_fields": visible_defaults, "step_config": DEFAULT_STEP_CONFIG})
    
    saved_fields = config.get("fields", [])
    
    # Merge com DEFAULT para garantir campos novos aparecem
    saved_map = {f["field_key"]: f for f in saved_fields}
    merged = []
    added_keys = set()
    for default_field in DEFAULT_FORM_CONFIG:
        key = default_field["field_key"]
        if key in saved_map:
            # Merge: DB wins for admin-editable fields, but fall back to DEFAULT
            # for fields the admin can't edit (e.g. options, data_path, field_type)
            db_field = saved_map[key]
            merged_field = {**default_field, **db_field}
            # Preserve DEFAULT options if DB is missing them (native select/checkbox fields)
            if not db_field.get("options") and default_field.get("options"):
                merged_field["options"] = default_field["options"]
            if not db_field.get("field_type") and default_field.get("field_type"):
                merged_field["field_type"] = default_field["field_type"]
            merged.append(merged_field)
        else:
            merged.append(default_field)
        added_keys.add(key)
    # Preservar campos customizados do admin
    for saved_field in saved_fields:
        if saved_field["field_key"] not in added_keys:
            merged.append(saved_field)
    merged.sort(key=lambda f: (f.get("step", 0), f.get("order", 0)))
    
    fields = merged
    
    # Compatibilidade: custom_fields (só campos personalizados visíveis)
    custom_fields = [
        f for f in fields 
        if f.get("is_custom") and f.get("is_visible")
    ]
    
    # NOVO: all_fields — todos os campos visíveis ordenados por step + order
    # O frontend usa isto para renderizar campos na ordem configurada pelo admin
    all_fields = [
        f for f in fields
        if f.get("is_visible")
    ]
    all_fields.sort(key=lambda f: (f.get("step", 0), f.get("order_index", f.get("order", 0))))
    
    step_config = config.get("step_config", DEFAULT_STEP_CONFIG)
    step_labels = config.get("step_labels", {})
    
    # Deep merge: ensure DEFAULT_STEP_CONFIG depends_on is preserved if DB lacks it
    # The DB may store display labels (e.g. "Com outra pessoa") instead of
    # internal value keys (e.g. "outra_pessoa") in depends_on.value.
    # Always prefer the DEFAULT's value since it's the correct internal key.
    merged_step_config = {}
    all_step_keys = set(list(DEFAULT_STEP_CONFIG.keys()) + list(step_config.keys()))
    for step_key in all_step_keys:
        default_entry = DEFAULT_STEP_CONFIG.get(step_key)
        db_entry = step_config.get(step_key)
        if default_entry and db_entry:
            merged_step_config[step_key] = {**default_entry, **db_entry}
            # If DB has no depends_on but default does, preserve default
            if not db_entry.get("depends_on") and default_entry.get("depends_on"):
                merged_step_config[step_key]["depends_on"] = default_entry["depends_on"]
            # Deep merge depends_on: always prefer DEFAULT value over DB
            if db_entry.get("depends_on") and default_entry.get("depends_on"):
                merged_dep = {**default_entry["depends_on"], **db_entry["depends_on"]}
                # CRITICAL: Always prefer DEFAULT depends_on value — DB may have
                # display labels (e.g. "Com outra pessoa") instead of internal
                # value keys (e.g. "outra_pessoa") that match form field values
                if default_entry["depends_on"].get("value") is not None:
                    merged_dep["value"] = default_entry["depends_on"]["value"]
                # Remove value_in if it's null/empty but value exists
                if not db_entry["depends_on"].get("value_in") and default_entry["depends_on"].get("value"):
                    merged_dep.pop("value_in", None)
                merged_step_config[step_key]["depends_on"] = merged_dep
        else:
            merged_step_config[step_key] = db_entry or default_entry

    return JSONResponse(status_code=200, content={
        "custom_fields": custom_fields,
        "all_fields": all_fields,
        "step_config": merged_step_config,
        "step_labels": step_labels
    })

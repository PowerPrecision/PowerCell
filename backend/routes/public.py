"""
====================================================================
ROTAS PÚBLICAS - CREDITOIMO
====================================================================
Endpoints públicos (sem autenticação).

FLUXO DE REGISTO (Triagem Manual):
1. Formulário público cria/atualiza ficha de cliente (Upsert por NIF/Email)
2. Cliente fica com lead_status="new" → aparece na página de Registos
3. Consultor/Admin faz triagem → clica "Criar Processo" → processo é criado
4. lead_status muda para "converted" → cliente desaparece dos Registos

REGRAS DE NEGÓCIO:
- NÃO se cria processo na submissão pública (triagem manual obrigatória)
- Um cliente pode ter vários processos
- O processo só existe após aprovação manual pelo staff

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
# NOTA: get_next_process_number removido — processo NÃO é criado na submissão pública
from services.encryption import (
    encrypt_client_data,
    decrypt_client_data,
    generate_nif_hash,
    generate_email_hash,
)
from models.client import generate_portal_access_code
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
    
    FLUXO DE TRIAGEM MANUAL:
    1. Anti-Duplicação: Procura cliente por email/NIF → upsert se existe, cria se não
    2. Marcação: Cliente fica com lead_status="new" para triagem na página de Registos
    3. SEM CRIAÇÃO DE PROCESSO — o processo só é criado quando o staff aprova
    
    SEGURANÇA: Rate limiting, sanitização de inputs, encriptação RGPD.
    """
    
    # Sanitizar inputs
    clean_email = sanitize_email(data.email)
    if not clean_email:
        log_sanitization_rejection("email", data.email, "email inválido no registo público")
        return JSONResponse(status_code=400, content={"success": False, "detail": "Email inválido"})
    
    clean_name = sanitize_name(data.name) if data.name else ""
    clean_phone = sanitize_phone(data.phone) if data.phone else None
    
    # Processar dados do formulário
    has_property = data.has_property or False
    process_type = data.process_type or "credito_habitacao"
    now = datetime.now(timezone.utc).isoformat()

    # =========================================
    # PASSO 1: ANTI-DUPLICAÇÃO (Upsert de Cliente)
    # Procurar por email (blind index) ou NIF.
    # Se existe → atualizar dados novos e reutilizar client_id
    # Se NÃO existe → criar novo documento de cliente
    # =========================================
    
    email_hash = generate_email_hash(clean_email)
    existing_client = None
    
    # Procurar por email (blind index para dados encriptados, fallback plain text)
    if email_hash:
        existing_client = await db.clients.find_one({"contacto.email_hash": email_hash})
    if not existing_client:
        existing_client = await db.clients.find_one({"contacto.email": clean_email.lower()})
    
    # Procurar por NIF (se disponível no payload — atualmente não vem no formulário público)
    clean_nif = None
    if not existing_client and clean_nif:
        nif_hash = generate_nif_hash(clean_nif)
        if nif_hash:
            existing_client = await db.clients.find_one({"dados_pessoais.nif_hash": nif_hash})
        if not existing_client:
            existing_client = await db.clients.find_one({"dados_pessoais.nif": clean_nif})
    
    if existing_client:
        # ── CLIENTE JÁ EXISTE: Atualizar dados novos (upsert parcial) ──
        client_id = existing_client["id"]
        
        # Desencriptar para comparar dados
        try:
            decrypted_existing = decrypt_client_data(existing_client)
        except Exception:
            decrypted_existing = existing_client
        
        # Atualizar campos que possam ter mudado ou sido adicionados
        client_updates = {
            "updated_at": now,
            # Re-marcar como lead pendente se já tinha sido convertido
            # (novo registo = nova submissão que precisa de triagem)
            "lead_status": "new",
        }
        
        # Atualizar telefone se novo ou vazio
        existing_phone = (decrypted_existing.get("contacto") or {}).get("telefone", "")
        if clean_phone and not existing_phone:
            client_updates["contacto.telefone"] = clean_phone
        
        # Atualizar nome se existente está vazio
        existing_name = decrypted_existing.get("nome", "")
        if not existing_name and clean_name:
            client_updates["nome"] = clean_name
        
        # Atualizar has_property se o cliente indicou ter imóvel agora
        if has_property and not existing_client.get("has_property"):
            client_updates["has_property"] = True
        
        # Mesclar custom_fields
        existing_custom = existing_client.get("custom_fields") or {}
        new_custom = data.custom_fields or {}
        if new_custom:
            merged_custom = {**existing_custom, **new_custom}
            client_updates["custom_fields"] = merged_custom
        
        # Re-encriptar dados atualizados
        try:
            # Construir doc temporário para encriptação seletiva
            temp_update = {}
            for k, v in client_updates.items():
                if k.startswith("contacto."):
                    if "contacto" not in temp_update:
                        temp_update["contacto"] = {}
                    temp_update["contacto"][k.replace("contacto.", "")] = v
                elif k.startswith("dados_pessoais."):
                    if "dados_pessoais" not in temp_update:
                        temp_update["dados_pessoais"] = {}
                    temp_update["dados_pessoais"][k.replace("dados_pessoais.", "")] = v
                else:
                    temp_update[k] = v
            
            encrypted_updates = encrypt_client_data(temp_update)
            
            # Reconverter para dot-notation
            final_updates = {}
            for k, v in client_updates.items():
                if k.startswith("contacto.") and "contacto" in encrypted_updates:
                    field = k.replace("contacto.", "")
                    final_updates[k] = encrypted_updates["contacto"].get(field, v)
                elif k.startswith("dados_pessoais.") and "dados_pessoais" in encrypted_updates:
                    field = k.replace("dados_pessoais.", "")
                    final_updates[k] = encrypted_updates["dados_pessoais"].get(field, v)
                elif k in encrypted_updates:
                    final_updates[k] = encrypted_updates[k]
                else:
                    final_updates[k] = v
            
            # Preservar blind indexes que não precisam de encriptação
            if "contacto.email_hash" in client_updates:
                final_updates["contacto.email_hash"] = client_updates["contacto.email_hash"]
            
            client_updates = final_updates
        except Exception as e:
            logger.warning(f"Falha ao encriptar updates do cliente existente {client_id}: {e}")
        
        await db.clients.update_one({"id": client_id}, {"$set": client_updates})
        logger.info(f"Cliente existente atualizado via formulário público: {client_id}")
    else:
        # ── NOVO CLIENTE: Criar documento isolado na coleção clients ──
        client_id = str(uuid.uuid4())
        
        personal_data = {
            "nome": clean_name,
            "email": clean_email,
            "telefone": clean_phone,
        }
        
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
            "process_ids": [],  # Será preenchido quando o staff criar o processo
            "portal_access_code": generate_portal_access_code(),  # Código de acesso ao Portal
            "fonte": "public_form",
            "has_property": has_property,
            "idade_menos_35": False,
            "created_at": now,
            "updated_at": now,
            "registration_completed": True,
            "assigned_to": None,
            "assigned_at": None,
            "lead_status": "new",  # Pendente de triagem — sem processo associado
            "custom_fields": data.custom_fields if data.custom_fields else {},
        }
        
        # RGPD: Encriptar dados sensíveis ANTES de inserir na BD
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
        
        # M3 - Criar pasta S3 para o cliente
        try:
            import asyncio
            result = await asyncio.to_thread(
                s3_service.initialize_client_folders,
                client_id,
                clean_name,
                None  # Sem segundo titular no formulário público
            )
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
    
    # =========================================
    # NOTA: NÃO se cria processo nesta fase.
    # O processo só é criado quando o staff aprova
    # o registo na página de "Registos de Clientes".
    # Isto garante triagem manual antes de criar
    # documentos na coleção `processes`.
    # =========================================
    
    # =========================================
    # PÓS-REGISTO: Email, Notificações, Alertas
    # =========================================
    
    # Obter o código de acesso ao portal do cliente (para incluir no email)
    portal_access_code = None
    try:
        client_doc = await db.clients.find_one({"id": client_id}, {"portal_access_code": 1, "_id": 0})
        if client_doc:
            portal_access_code = client_doc.get("portal_access_code")
            # Se o cliente existente não tem código (caso raro), gerar um
            if not portal_access_code:
                from models.client import generate_portal_access_code as _gen_code
                portal_access_code = _gen_code()
                await db.clients.update_one(
                    {"id": client_id},
                    {"$set": {"portal_access_code": portal_access_code}}
                )
    except Exception as e:
        logger.warning(f"Erro ao obter/gerar portal_access_code para {client_id}: {e}")
    
    # Enviar email de confirmação ao cliente
    from services.task_queue import task_queue
    job_id = await task_queue.send_registration_email(
        client_email=clean_email,
        client_name=clean_name,
        portal_access_code=portal_access_code
    )
    if not job_id:
        logger.info("Task Queue não disponível, enviando email directamente")
        await send_registration_confirmation(
            client_email=clean_email,
            client_name=clean_name,
            portal_access_code=portal_access_code
        )
    
    # Criar alertas no sistema de notificações (passar dados do cliente — SEM processo)
    client_notification_data = {
        "id": client_id,
        "client_id": client_id,
        "client_name": clean_name,
        "client_email": clean_email,
        "client_phone": clean_phone,
        "nome": clean_name,
        "contacto": {"email": clean_email, "telefone": clean_phone},
        "process_type": process_type,
    }
    await notify_new_client_registration(client_notification_data, has_property)
    
    # Enviar push notifications para staff
    try:
        from services.push_notifications import send_push_notification
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
                url="/registos-clientes",  # Link para página de registos de clientes
                data={
                    "type": "new_client",
                    "client_id": client_id,
                    "client_name": clean_name
                }
            )
        
        logger.info(f"Push notifications enviadas para {len(staff_for_push)} membros do staff")
    except Exception as e:
        logger.warning(f"Erro ao enviar push notifications: {e}")
    
    # Email para o primeiro admin/CEO/diretor
    from services.role_query import deep_role_in_filter
    staff = await db.users.find(
        deep_role_in_filter([UserRole.ADMIN, UserRole.CEO, UserRole.DIRETOR]),
        {"_id": 0}
    ).to_list(100)
    
    if staff:
        first_admin = staff[0]
        staff_job = await task_queue.send_email(
            to=first_admin["email"],
            subject=f"Novo Cliente Registado: {clean_name}",
            body=f"Foi registado um novo cliente via formulário público:\n\nNome: {clean_name}\nEmail: {clean_email}\nTelefone: {clean_phone or 'N/A'}\nTipo pretendido: {process_type}\n\nO registo aguarda triagem na página de Registos de Clientes."
        )
        
        if not staff_job:
            await send_new_client_notification(
                client_name=clean_name,
                client_email=clean_email,
                client_phone=clean_phone or "N/A",
                process_type=process_type,
                staff_email=first_admin["email"],
                staff_name=first_admin["name"]
            )
    
    is_new_client = existing_client is None
    
    return JSONResponse(
        status_code=200,
        content={
            "success": True,
            "message": "Registo criado com sucesso. A equipa entrará em contacto.",
            "client_id": client_id,
            "lead_status": "new",  # Pendente de triagem
            "is_new_client": is_new_client,
            "has_property": has_property,
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

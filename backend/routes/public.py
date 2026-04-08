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
from utils.input_sanitization import (
    sanitize_email, sanitize_name, sanitize_phone, sanitize_nif,
    sanitize_string, log_sanitization_rejection
)

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
    # =========================================
    
    # Verificar se já existe cliente com o mesmo email
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
    raw_nif = data.personal_data.nif if data.personal_data else None
    clean_nif = sanitize_nif(raw_nif) if raw_nif else None
    if clean_nif:
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
    real_estate_data = data.real_estate_data.model_dump() if data.real_estate_data else {}
    has_property = bool(real_estate_data.get("ja_tem_imovel") or real_estate_data.get("has_property"))
    
    personal_data = data.personal_data.model_dump() if data.personal_data else {}
    
    # Garantir que campos críticos ficam também em personal_data para consistência
    if clean_email and not personal_data.get("email"):
        personal_data["email"] = clean_email
    if clean_name and not personal_data.get("nome"):
        personal_data["nome"] = clean_name
    if clean_phone and not personal_data.get("telefone"):
        personal_data["telefone"] = clean_phone
    
    # Sanitizar campos de texto no personal_data
    for text_field in ["nome", "naturalidade", "nacionalidade", "profissao", "empresa"]:
        if personal_data.get(text_field):
            personal_data[text_field] = sanitize_string(personal_data[text_field], max_length=200)
    
    birth_date = personal_data.get("birth_date")
    idade_menos_35 = False
    
    if birth_date:
        try:
            birth = datetime.strptime(birth_date, "%Y-%m-%d")
            age = (datetime.now() - birth).days // 365
            idade_menos_35 = age < 35
        except (ValueError, TypeError):
            pass
    
    # Verificar se checkbox menor_35_anos foi marcado
    if personal_data.get("menor_35_anos"):
        idade_menos_35 = True
    
    # Obter nome do segundo titular se existir
    titular2_data_dict = data.titular2_data.model_dump() if data.titular2_data else None
    second_client_name = None
    if titular2_data_dict:
        second_client_name = titular2_data_dict.get("nome") or titular2_data_dict.get("name")
        # Sanitizar nome do segundo titular
        if second_client_name:
            second_client_name = sanitize_name(second_client_name)
    
    # =========================================
    # CRIAR FICHA DE CLIENTE (tabela clients)
    # =========================================
    client_doc = {
        "id": client_id,
        "nome": clean_name,
        "contacto": {
            "email": clean_email.lower(),
            "telefone": clean_phone
        },
        "dados_pessoais": personal_data,
        "dados_financeiros": data.financial_data.model_dump() if data.financial_data else {},
        "dados_imobiliarios": real_estate_data,  # Novo campo para dados do imóvel
        "titular2_data": titular2_data_dict,
        "process_ids": [],  # Vazio até ser criado o processo
        "fonte": "public_form",
        "has_property": has_property,
        "idade_menos_35": idade_menos_35,
        "second_client_name": second_client_name,
        "created_at": now,
        "updated_at": now,
        "registration_completed": True,  # Marcar que completou o registo
        "assigned_to": None,  # Atribuído a nenhum utilizador inicialmente
        "assigned_at": None,
        "custom_fields": data.custom_fields if data.custom_fields else {},
    }
    
    await db.clients.insert_one(client_doc)
    
    # O5 - Encriptar dados sensíveis do cliente após inserção
    try:
        from services.encryption import encrypt_sensitive_data
        encrypted = encrypt_sensitive_data(client_doc)
        if encrypted != client_doc:
            await db.clients.update_one({"id": client_id}, {"$set": encrypted})
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
        staff_for_push = await db.users.find(
            {"role": {"$in": [UserRole.ADMIN, UserRole.CEO, UserRole.DIRETOR]}, "is_active": True}, 
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
    staff = await db.users.find(
        {"role": {"$in": [UserRole.ADMIN, UserRole.CEO, UserRole.DIRETOR]}}, 
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
    """Obter configuração do formulário público (campos personalizados incluídos)."""
    config = await db.form_config.find_one({"type": "public_form"}, {"_id": 0})
    if not config:
        return JSONResponse(status_code=200, content={"custom_fields": []})
    
    # Retornar apenas campos personalizados e visíveis
    fields = config.get("fields", [])
    custom_fields = [
        f for f in fields 
        if f.get("is_custom") and f.get("is_visible")
    ]
    
    return JSONResponse(status_code=200, content={"custom_fields": custom_fields})

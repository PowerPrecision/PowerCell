"""
====================================================================
ROTAS PÚBLICAS - CREDITOIMO
====================================================================
Endpoints públicos (sem autenticação).

IMPORTANTE: O cliente NÃO é um utilizador do sistema.
O registo público cria apenas um documento na colecção Processes.
Os dados do cliente (email, telefone) ficam guardados no Process.

SEGURANÇA: Rate limiting aplicado para prevenir abusos.
====================================================================
"""
import re
import uuid
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Request, BackgroundTasks

from slowapi import Limiter
from slowapi.util import get_remote_address

logger = logging.getLogger(__name__)

from database import db
from models.auth import UserRole
from models.process import PublicClientRegistration
from services.email import send_registration_confirmation, send_new_client_notification
from services.alerts import notify_new_client_registration
from services.process_service import get_next_process_number
from services.s3_storage import s3_service

limiter = Limiter(key_func=get_remote_address)

router = APIRouter(prefix="/public", tags=["Public"])


def sanitize_email(email: str) -> str:
    """
    Limpa emails com formatação markdown ou outros artefactos.
    Extrai o email puro de strings como '[email](mailto:email)' ou 'mailto:email'.
    """
    if not email:
        return ""
    
    email = email.strip()
    
    # Padrão: [texto](mailto:email) ou [email](mailto:email)
    markdown_link = re.search(r'\[.*?\]\(mailto:([^)]+)\)', email)
    if markdown_link:
        email = markdown_link.group(1)
    
    # Padrão: mailto:email
    if email.startswith('mailto:'):
        email = email.replace('mailto:', '')
    
    # Padrão: <email>
    angle_brackets = re.search(r'<([^>]+@[^>]+)>', email)
    if angle_brackets:
        email = angle_brackets.group(1)
    
    # Remover quaisquer caracteres markdown restantes
    email = re.sub(r'[\[\]\(\)]', '', email)
    
    # Limpar e normalizar
    email = email.strip().lower()
    
    return email


@router.post("/client-registration")
@limiter.limit("5/hour")  # Rate limit restritivo para prevenir spam de registos
async def public_client_registration(request: Request, data: PublicClientRegistration):
    """
    Endpoint público para registo de clientes - sem autenticação.
    
    FLUXO:
    1. Verifica se email ou NIF já existem (bloqueia duplicados)
    2. Cria documento na colecção Processes (NÃO cria utilizador)
    3. Envia email de confirmação ao cliente
    4. Notifica administradores/staff
    5. Gera alertas no sistema
    
    O cliente é apenas um "conjunto de dados" dentro do Processo,
    não um utilizador com credenciais de login.
    """
    
    # Sanitizar email logo no início
    clean_email = sanitize_email(data.email)
    
    # =========================================
    # VERIFICAR DUPLICADOS (EMAIL E NIF)
    # =========================================
    
    # Verificar se já existe processo com o mesmo email
    existing_by_email = await db.processes.find_one({"client_email": clean_email})
    if existing_by_email:
        return {
            "success": False,
            "blocked": True,
            "reason": "email",
            "message": "Já existe um processo com este email. A nossa equipa entrará em contacto consigo em breve."
        }
    
    # Verificar se já existe processo com o mesmo NIF
    nif = None
    if data.personal_data:
        nif = data.personal_data.nif
    
    if nif:
        existing_by_nif = await db.processes.find_one({"personal_data.nif": nif})
        if existing_by_nif:
            return {
                "success": False,
                "blocked": True,
                "reason": "nif",
                "message": "Já existe um processo com este NIF. A nossa equipa entrará em contacto consigo em breve."
            }
    
    first_status = await db.workflow_statuses.find_one({}, {"_id": 0}, sort=[("order", 1)])
    initial_status = first_status["name"] if first_status else "clientes_espera"
    
    process_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    
    # Gerar número sequencial do processo
    process_number = await get_next_process_number()
    
    # Processar dados do formulário
    real_estate_data = data.real_estate_data.model_dump() if data.real_estate_data else {}
    has_property = bool(real_estate_data.get("ja_tem_imovel") or real_estate_data.get("has_property"))
    
    personal_data = data.personal_data.model_dump() if data.personal_data else {}
    
    # Garantir que campos críticos ficam também em personal_data para consistência
    if clean_email and not personal_data.get("email"):
        personal_data["email"] = clean_email
    if data.name and not personal_data.get("nome"):
        personal_data["nome"] = data.name
    if data.phone and not personal_data.get("telefone"):
        personal_data["telefone"] = data.phone
    
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
    
    # Criar documento do processo (SEM criar utilizador)
    process_doc = {
        "id": process_id,
        "process_number": process_number,  # Número sequencial único
        # Dados do cliente guardados directamente no processo
        "client_id": None,  # Não há utilizador associado
        "client_name": data.name,
        "client_email": clean_email,  # Email já sanitizado
        "client_phone": data.phone,
        "second_client_name": second_client_name,  # Nome do 2º titular para pastas
        # Tipo e estado
        "process_type": data.process_type,
        "status": initial_status,
        # Dados estruturados
        "personal_data": personal_data,
        "titular2_data": titular2_data_dict,
        "financial_data": data.financial_data.model_dump() if data.financial_data else None,
        "real_estate_data": real_estate_data,
        "credit_data": None,
        # Atribuições (a ser preenchido pelo staff)
        "assigned_consultor_id": None,
        "assigned_mediador_id": None,
        "consultor_id": None,
        "consultor_name": None,
        "intermediario_id": None,
        "mediador_id": None,
        "mediador_name": None,
        # Flags
        "source": "public_form",
        "has_property": has_property,
        "idade_menos_35": idade_menos_35,
        # Documentos e histórico
        "documents": [],
        "notes": None,
        # Timestamps
        "created_at": now,
        "updated_at": now
    }
    
    await db.processes.insert_one(process_doc)
    
    # =========================================
    # CRIAR PASTAS S3 PARA O NOVO CLIENTE
    # =========================================
    s3_folder_path = None
    try:
        if s3_service.is_configured():
            success, s3_folder_path = s3_service.initialize_client_folders(
                process_id, 
                data.name,
                second_client_name=second_client_name
            )
            if success and s3_folder_path:
                # Guardar mapeamento no processo
                await db.processes.update_one(
                    {"id": process_id},
                    {"$set": {"s3_folder": s3_folder_path}}
                )
                logger.info(f"Pastas S3 criadas e mapeadas para novo cliente: {data.name} -> {s3_folder_path}")
    except Exception as e:
        logger.warning(f"Erro ao criar pastas S3 para cliente {data.name}: {e}")
        # Não falhar o registo se as pastas S3 não forem criadas
    
    # Registar no histórico
    await db.history.insert_one({
        "id": str(uuid.uuid4()),
        "process_id": process_id,
        "user_id": None,
        "user_name": data.name,
        "action": "Cliente registou-se via formulário público",
        "field": None,
        "old_value": None,
        "new_value": None,
        "created_at": now
    })
    
    # =========================================
    # ENVIAR EMAIL DE CONFIRMAÇÃO AO CLIENTE
    # Usa Task Queue para não bloquear a resposta
    # =========================================
    from services.task_queue import task_queue
    
    # Tentar enfileirar (se Redis disponível)
    job_id = await task_queue.send_registration_email(
        client_email=clean_email,
        client_name=data.name
    )
    
    # Se Task Queue não disponível, enviar directamente
    if not job_id:
        logger.info("Task Queue não disponível, enviando email directamente")
        await send_registration_confirmation(
            client_email=clean_email,
            client_name=data.name
        )
    
    # =========================================
    # NOTIFICAR STAFF SOBRE NOVO REGISTO
    # =========================================
    
    # Criar alertas no sistema de notificações
    await notify_new_client_registration(process_doc, has_property)
    
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
                body=f"{data.name} registou-se via formulário",
                tag="new_client",
                url=f"/processo/{process_id}",
                data={
                    "type": "new_client",
                    "process_id": process_id,
                    "client_name": data.name
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
            subject=f"Novo Cliente: {data.name}",
            body=f"Foi registado um novo cliente:\n\nNome: {data.name}\nEmail: {clean_email}\nTelefone: {data.phone}\nTipo: {data.process_type}"
        )
        
        # Fallback se Task Queue não disponível
        if not staff_job:
            await send_new_client_notification(
                client_name=data.name,
                client_email=clean_email,
                client_phone=data.phone,
                process_type=data.process_type,
                staff_email=first_admin["email"],
                staff_name=first_admin["name"]
            )
    
    return {
        "success": True,
        "message": "Registo criado com sucesso. Verifique o seu email.",
        "process_id": process_id,
        "has_property": has_property,
        "idade_menos_35": idade_menos_35,
        "email_queued": bool(job_id)
    }


@router.get("/health")
@limiter.limit("30/minute")
async def public_health(request: Request):
    """Health check público."""
    return {"status": "ok", "public": True}

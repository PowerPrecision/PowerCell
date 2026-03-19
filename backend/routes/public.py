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
    2. Cria ficha de cliente na tabela 'clients' (NÃO cria processo)
    3. Envia email de confirmação ao cliente
    4. Notifica administradores/staff
    5. Gera alertas no sistema
    
    O processo é criado quando o cliente é atribuído a um utilizador.
    """
    
    # Sanitizar email logo no início
    clean_email = sanitize_email(data.email)
    
    # =========================================
    # VERIFICAR DUPLICADOS (EMAIL E NIF)
    # =========================================
    
    # Verificar se já existe cliente com o mesmo email
    existing_by_email = await db.clients.find_one({"contacto.email": clean_email.lower()})
    if existing_by_email:
        return {
            "success": False,
            "blocked": True,
            "reason": "email",
            "message": "Já existe um registo com este email. A nossa equipa entrará em contacto consigo em breve."
        }
    
    # Verificar se já existe cliente com o mesmo NIF
    nif = None
    if data.personal_data:
        nif = data.personal_data.nif
    
    if nif:
        existing_by_nif = await db.clients.find_one({"dados_pessoais.nif": nif})
        if existing_by_nif:
            return {
                "success": False,
                "blocked": True,
                "reason": "nif",
                "message": "Já existe um registo com este NIF. A nossa equipa entrará em contacto consigo em breve."
            }
    
    client_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    
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
    
    # =========================================
    # CRIAR FICHA DE CLIENTE (tabela clients)
    # =========================================
    client_doc = {
        "id": client_id,
        "nome": data.name,
        "contacto": {
            "email": clean_email.lower(),
            "telefone": data.phone
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
        "assigned_at": None
    }
    
    await db.clients.insert_one(client_doc)
    
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
                body=f"{data.name} registou-se via formulário",
                tag="new_client",
                url=f"/clientes",  # Link para página de registos
                data={
                    "type": "new_client",
                    "client_id": client_id,
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
            subject=f"Novo Cliente Registado: {data.name}",
            body=f"Foi registado um novo cliente via formulário público:\n\nNome: {data.name}\nEmail: {clean_email}\nTelefone: {data.phone}\n\nO cliente aguarda atribuição."
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
        "client_id": client_id,
        "has_property": has_property,
        "idade_menos_35": idade_menos_35,
        "email_queued": bool(job_id)
    }


@router.get("/health")
@limiter.limit("30/minute")
async def public_health(request: Request):
    """Health check público."""
    return {"status": "ok", "public": True}

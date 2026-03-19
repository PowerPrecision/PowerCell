"""
Serviço RGPD - Gestão de consentimentos e tokens temporários

Este módulo implementa:
- Criação de pedidos de consentimento
- Validação de tokens temporários
- Processamento de assinaturas
- Geração de PDF do RGPD assinado
- Envio de emails
"""
import uuid
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any
from database import db
from services.email_service import send_email
from services.history import log_history

logger = logging.getLogger(__name__)

# Configurações
TOKEN_EXPIRY_HOURS = 24
RGPD_REQUESTS_COLLECTION = "rgpd_requests"


async def create_rgpd_request(
    process_id: str,
    client_name: str,
    client_email: str,
    user: dict
) -> Dict[str, Any]:
    """
    Cria um novo pedido de consentimento RGPD.
    
    Args:
        process_id: ID do processo
        client_name: Nome do cliente
        client_email: Email do cliente
        user: Utilizador que está a solicitar
    
    Returns:
        Dicionário com o pedido criado
    """
    # Verificar se já existe um pedido ativo
    existing = await db[RGPD_REQUESTS_COLLECTION].find_one({
        "process_id": process_id,
        "status": {"$in": ["pending", "signed"]}
    })
    
    if existing:
        # Se já está assinado, retornar o existente
        if existing["status"] == "signed":
            return {
                "success": True,
                "existing": True,
                "status": "signed",
                "signed_at": existing.get("signed_at"),
                "request_id": existing["id"]
            }
        # Se está pendente e não expirou, retornar o existente
        if existing["status"] == "pending":
            expires = datetime.fromisoformat(existing["token_expires_at"].replace("Z", "+00:00"))
            if expires > datetime.now(timezone.utc):
                return {
                    "success": True,
                    "existing": True,
                    "status": "pending",
                    "expires_at": existing["token_expires_at"],
                    "request_id": existing["id"]
                }
    
    # Gerar token único
    request_id = str(uuid.uuid4())
    token = f"{uuid.uuid4().hex}{uuid.uuid4().hex}"  # Token longo para segurança
    
    # Calcular expiração (24h)
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(hours=TOKEN_EXPIRY_HOURS)
    
    # Criar pedido
    request_doc = {
        "id": request_id,
        "process_id": process_id,
        "client_name": client_name,
        "client_email": client_email,
        "token": token,
        "token_expires_at": expires_at.isoformat(),
        "status": "pending",
        "consent_data": None,
        "created_at": now.isoformat(),
        "created_by": user["id"],
        "created_by_email": user["email"],
        "created_by_name": user.get("name", ""),
        "signed_at": None,
        "pdf_url": None
    }
    
    await db[RGPD_REQUESTS_COLLECTION].insert_one(request_doc)
    
    # Adicionar comentário nas atividades do processo
    await log_history(
        process_id,
        user,
        f"RGPD solicitado - Email enviado para {client_email}"
    )
    
    logger.info(f"RGPD request created: {request_id} for process {process_id}")
    
    return {
        "success": True,
        "existing": False,
        "request_id": request_id,
        "token": token,
        "expires_at": expires_at.isoformat()
    }


async def validate_token(token: str) -> Optional[Dict[str, Any]]:
    """
    Valida um token de RGPD.
    
    Args:
        token: Token a validar
    
    Returns:
        Dados do pedido se válido, None caso contrário
    """
    request = await db[RGPD_REQUESTS_COLLECTION].find_one({"token": token})
    
    if not request:
        return None
    
    # Verificar expiração
    expires_at = datetime.fromisoformat(request["token_expires_at"].replace("Z", "+00:00"))
    
    if expires_at < datetime.now(timezone.utc):
        # Marcar como expirado
        await db[RGPD_REQUESTS_COLLECTION].update_one(
            {"id": request["id"]},
            {"$set": {"status": "expired"}}
        )
        return None
    
    # Verificar se já foi assinado
    if request["status"] == "signed":
        return None
    
    return request


async def get_rgpd_by_process(process_id: str) -> Optional[Dict[str, Any]]:
    """
    Obtém o estado do RGPD para um processo.
    
    Args:
        process_id: ID do processo
    
    Returns:
        Dados do RGPD ou None
    """
    try:
        # Procurar o mais recente assinado
        requests = await db[RGPD_REQUESTS_COLLECTION].find(
            {"process_id": process_id, "status": "signed"}
        ).sort("signed_at", -1).limit(1).to_list(1)
        
        if requests:
            request = requests[0]
            return {
                "has_rgpd": True,
                "status": "signed",
                "signed_at": request.get("signed_at"),
                "pdf_url": request.get("pdf_url"),
                "request_id": request.get("id")
            }
        
        # Verificar se há pendente
        pending_requests = await db[RGPD_REQUESTS_COLLECTION].find(
            {"process_id": process_id, "status": "pending"}
        ).sort("created_at", -1).limit(1).to_list(1)
        
        if pending_requests:
            pending = pending_requests[0]
            try:
                expires_str = pending.get("token_expires_at")
                if expires_str:
                    expires = datetime.fromisoformat(expires_str.replace("Z", "+00:00"))
                    if expires > datetime.now(timezone.utc):
                        return {
                            "has_rgpd": False,
                            "status": "pending",
                            "expires_at": expires_str,
                            "request_id": pending.get("id")
                        }
            except (KeyError, ValueError, AttributeError) as e:
                logger.warning(f"Error parsing token expiry: {e}")
        
        return {"has_rgpd": False, "status": None}
    except Exception as e:
        logger.error(f"Error in get_rgpd_by_process for {process_id}: {e}")
        return {"has_rgpd": False, "status": None}


async def sign_rgpd(
    token: str,
    consent_data: dict
) -> Dict[str, Any]:
    """
    Processa a assinatura do RGPD.
    
    Args:
        token: Token do pedido
        consent_data: Dados preenchidos pelo cliente
    
    Returns:
        Resultado da operação
    """
    # Validar token
    request = await validate_token(token)
    
    if not request:
        return {
            "success": False,
            "error": "Token inválido ou expirado"
        }
    
    # Adicionar data da assinatura
    now = datetime.now(timezone.utc)
    consent_data["data_assinatura"] = now.strftime("%d/%m/%Y às %H:%M")
    
    # Atualizar pedido
    await db[RGPD_REQUESTS_COLLECTION].update_one(
        {"id": request["id"]},
        {
            "$set": {
                "status": "signed",
                "consent_data": consent_data,
                "signed_at": now.isoformat()
            }
        }
    )
    
    # Adicionar atividade ao processo
    await log_history(
        request["process_id"],
        {"id": request["id"], "name": consent_data.get("nome", "Cliente"), "role": "cliente"},
        "RGPD enviado e assinado"
    )
    
    # Enviar email com o RGPD assinado para o utilizador
    user_email = request.get("created_by_email")
    user_name = request.get("created_by_name", "")
    client_name = consent_data.get("nome", request.get("client_name", ""))
    
    if user_email:
        await send_rgpd_signed_email(
            to_email=user_email,
            user_name=user_name,
            client_name=client_name,
            consent_data=consent_data,
            process_id=request["process_id"]
        )
    
    logger.info(f"RGPD signed: {request['id']} for process {request['process_id']}")
    
    return {
        "success": True,
        "request_id": request["id"],
        "process_id": request["process_id"]
    }


async def send_rgpd_email(
    client_email: str,
    client_name: str,
    token: str,
    request_id: str,
    user_email: str,
    base_url: str = None
) -> bool:
    """
    Envia email de RGPD para o cliente.
    
    Args:
        client_email: Email do cliente
        client_name: Nome do cliente
        token: Token de validação
        request_id: ID do pedido
        user_email: Email do utilizador que solicitou
        base_url: URL base para o link (default: variável de ambiente ou www.powercell.pt)
    
    Returns:
        True se enviado com sucesso
    """
    import os
    # Usar variável de ambiente ou URL de produção
    if base_url is None:
        base_url = os.environ.get("FRONTEND_URL", "https://www.powercell.pt")
    
    # Construir link temporário
    rgpd_link = f"{base_url}/rgpd/{token}"
    
    # Template do email
    subject = "RGPD - Regulamento Geral sobre a Proteção de Dados"
    
    body_text = f"""Estimado(a) {client_name},

Gostaríamos de solicitar a sua assinatura do documento Regulamento Geral de Proteção de Dados (RGPD), que é um requisito legal para a prestação dos nossos serviços enquanto Intermediários de Crédito.

O documento RGPD explica como recolhemos, utilizamos e partilhamos os seus dados pessoais. Ele também descreve os seus direitos como titular dos dados.

Para assinar o documento, basta clicar no link abaixo e preencher os campos com as suas informações.

Atenção: Deverá assinar o RGPD num espaço máximo de 24h por motivos de segurança.

PREENCHER RGPD: {rgpd_link}

Atenciosamente,
Equipa Precision Crédito
"""
    
    body_html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
</head>
<body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
    <div style="background-color: #f8f9fa; padding: 20px; border-radius: 8px; margin-bottom: 20px;">
        <img src="https://5af40e69fb2205f1674bdd6edbe227cd.cdn.bubble.io/cdn-cgi/image/w=,h=,f=auto,dpr=1,fit=contain/f1744120174601x242645494868973340/logo-transp-crm-ok-300x90%20%281%29.png" alt="Precision Crédito" style="max-width: 200px; margin-bottom: 15px;">
    </div>
    
    <p>Estimado(a) <strong>{client_name}</strong>,</p>
    
    <p>Gostaríamos de solicitar a sua assinatura do documento <strong>Regulamento Geral de Proteção de Dados (RGPD)</strong>, que é um requisito legal para a prestação dos nossos serviços enquanto Intermediários de Crédito.</p>
    
    <p>O documento RGPD explica como recolhemos, utilizamos e partilhamos os seus dados pessoais. Ele também descreve os seus direitos como titular dos dados.</p>
    
    <p>Para assinar o documento, basta clicar no link abaixo e preencher os campos com as suas informações.</p>
    
    <div style="background-color: #fff3cd; border: 1px solid #ffc107; padding: 15px; border-radius: 5px; margin: 20px 0;">
        <strong>⚠️ Atenção:</strong> Deverá assinar o RGPD num espaço máximo de 24h por motivos de segurança.
    </div>
    
    <div style="text-align: center; margin: 30px 0;">
        <a href="{rgpd_link}" style="background-color: #2563eb; color: white; padding: 15px 30px; text-decoration: none; border-radius: 5px; font-weight: bold; display: inline-block;">PREENCHER RGPD</a>
    </div>
    
    <p style="color: #666; font-size: 12px;">Se não conseguir clicar no botão, copie e cole o seguinte link no seu navegador:<br>
    <a href="{rgpd_link}" style="color: #2563eb; word-break: break-all;">{rgpd_link}</a></p>
    
    <hr style="border: none; border-top: 1px solid #ddd; margin: 30px 0;">
    
    <p>Atenciosamente,<br>
    <strong>Equipa Precision Crédito</strong></p>
</body>
</html>
"""
    
    try:
        # Determinar conta de email (precision ou power)
        account = "precision"  # Default
        
        result = await send_email(
            account_name=account,
            to_emails=[client_email],
            subject=subject,
            body=body_text,
            body_html=body_html,
            created_by=user_email
        )
        
        logger.info(f"RGPD email sent to {client_email}")
        return result.get("success", False)
        
    except Exception as e:
        logger.error(f"Failed to send RGPD email: {e}")
        return False


async def send_rgpd_signed_email(
    to_email: str,
    user_name: str,
    client_name: str,
    consent_data: dict,
    process_id: str
) -> bool:
    """
    Envia email com o RGPD assinado para o utilizador.
    
    Args:
        to_email: Email do utilizador
        user_name: Nome do utilizador
        client_name: Nome do cliente
        consent_data: Dados do consentimento
        process_id: ID do processo
    
    Returns:
        True se enviado com sucesso
    """
    subject = f"RGPD Assinado - {client_name}"
    
    body_text = f"""Olá {user_name},

O cliente {client_name} assinou o documento RGPD com os seguintes dados:

Nome: {consent_data.get('nome', 'N/A')}
Contribuinte: {consent_data.get('contribuinte', 'N/A')}
Tipo de Documento: {consent_data.get('tipo_documento', 'N/A')}
Número do Documento: {consent_data.get('numero_documento', 'N/A')}
Morada: {consent_data.get('morada', 'N/A')}
Data da Assinatura: {consent_data.get('data_assinatura', 'N/A')}

O processo foi atualizado com esta informação.

Atenciosamente,
Sistema CRM
"""
    
    body_html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
</head>
<body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
    <p>Olá <strong>{user_name}</strong>,</p>
    
    <p>O cliente <strong>{client_name}</strong> assinou o documento RGPD.</p>
    
    <div style="background-color: #d4edda; border: 1px solid #28a745; padding: 15px; border-radius: 5px; margin: 20px 0;">
        <h3 style="margin-top: 0; color: #28a745;">✅ RGPD Assinado</h3>
        <p><strong>Nome:</strong> {consent_data.get('nome', 'N/A')}</p>
        <p><strong>Contribuinte:</strong> {consent_data.get('contribuinte', 'N/A')}</p>
        <p><strong>Tipo de Documento:</strong> {consent_data.get('tipo_documento', 'N/A')}</p>
        <p><strong>Número do Documento:</strong> {consent_data.get('numero_documento', 'N/A')}</p>
        <p><strong>Morada:</strong> {consent_data.get('morada', 'N/A')}</p>
        <p><strong>Data da Assinatura:</strong> {consent_data.get('data_assinatura', 'N/A')}</p>
    </div>
    
    <p>O processo foi atualizado com esta informação.</p>
    
    <hr style="border: none; border-top: 1px solid #ddd; margin: 30px 0;">
    
    <p style="color: #666; font-size: 12px;">Esta é uma mensagem automática do sistema CRM.</p>
</body>
</html>
"""
    
    try:
        result = await send_email(
            account_name="precision",
            to_emails=[to_email],
            subject=subject,
            body=body_text,
            body_html=body_html
        )
        
        logger.info(f"RGPD signed notification sent to {to_email}")
        return result.get("success", False)
        
    except Exception as e:
        logger.error(f"Failed to send RGPD signed notification: {e}")
        return False

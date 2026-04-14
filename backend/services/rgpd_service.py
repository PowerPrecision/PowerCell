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
import io
import base64
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

# Mapeamento de tipos de documento para exibição legível
TIPOS_DOCUMENTO_LABELS = {
    "bilhete_de_identidade": "Bilhete de Identidade",
    "cartao_de_cidadao": "Cartão de Cidadão",
    "passaporte": "Passaporte",
    "carta_de_conducao": "Carta de Condução",
    "autorizacao_de_residencia": "Autorização de Residência"
}


def get_tipo_documento_label(tipo_documento: str) -> str:
    """
    Converte o valor do enum tipo_documento para um formato legível.
    
    Args:
        tipo_documento: Valor do enum (ex: "cartao_de_cidadao")
    
    Returns:
        Label formatado (ex: "Cartão de Cidadão")
    """
    if not tipo_documento:
        return "N/A"
    return TIPOS_DOCUMENTO_LABELS.get(tipo_documento, tipo_documento)


async def create_rgpd_request(
    process_id: str,
    client_name: str,
    client_email: str,
    user: dict
) -> Dict[str, Any]:
    """
    Cria um pedido de consentimento RGPD e envia email com link temporário ao cliente.

    Este fluxo é um requisito legal para intermediação de crédito habitação: antes de
    processar dados pessoais, o cliente deve dar consentimento explícito (Art. 6º, n.º 1, alínea a) do RGPD.

    A função implementa deduplicação: se já existir um pedido ativo (pending ou signed)
    para o mesmo processo, reutiliza-o em vez de criar duplicado. O token tem
    validade de 24h por segurança — após expirar, o cliente deve solicitar novo consentimento.

    Args:
        process_id: ID do processo de crédito habitação.
        client_name: Nome completo do cliente (aparece no documento RGPD).
        client_email: Email do cliente para receber o link de assinatura.
        user: Dicionário do utilizador autenticado que solicita o consentimento.

    Returns:
        dict: Resultado com chaves:
            - success (bool): True se o pedido foi criado ou reutilizado.
            - existing (bool): True se um pedido ativo já existia.
            - request_id (str): ID do pedido RGPD.
            - token (str): Token de assinatura (só se novo pedido).
            - expires_at (str): Data/hora de expiração ISO 8601.
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
    Valida um token de consentimento RGPD verificando existência, expiração e estado.

    O token é o mecanismo de segurança que impede que terceiros acedam ao
    formulário de consentimento: sem um token válido (não expirado, não
    já utilizado), o cliente não pode preencher o RGPD. A validação marca
    automaticamente tokens expirados como ``status=expired`` para auditoria.

    Args:
        token: Cadeia hexagonal gerada pelo ``create_rgpd_request``.

    Returns:
        dict: Documento completo do pedido RGPD se o token for válido, ou
            ``None`` se o token não existir, estiver expirado ou já tiver
            sido utilizado (``status=signed``).
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
    Consulta o estado do consentimento RGPD de um processo.

    Utilizado pela UI para apresentar o badge de estado (pendente, assinado,
    ausente) sem expor dados sensíveis do consentimento. A pesquisa prioriza
    registos assinados (``status=signed``) sobre pendentes, garantindo que
    um processo com RGPD completo não é marcado como pendente por causa de
    um pedido anterior não expirado.

    Args:
        process_id: Identificador único do processo de crédito habitação.

    Returns:
        dict: Estado do RGPD com as chaves:
            - has_rgpd (bool): True se existe consentimento assinado.
            - status (str | None): "signed", "pending" ou None.
            - signed_at (str | None): Data/hora da assinatura (se signed).
            - pdf_url (str | None): URL do PDF assinado no S3 (se signed).
            - request_id (str | None): ID do pedido RGPD.
            - expires_at (str | None): Data/hora de expiração (se pending).
        Em caso de erro de BD, retorna ``{"has_rgpd": False, "status": None}``.
    """
    try:
        # Validar entrada
        if not process_id:
            return {"has_rgpd": False, "status": None}
            
        # Procurar o mais recente assinado
        try:
            requests = await db[RGPD_REQUESTS_COLLECTION].find(
                {"process_id": process_id, "status": "signed"}
            ).sort("signed_at", -1).limit(1).to_list(1)
        except Exception as db_err:
            logger.error(f"Erro ao buscar RGPD assinados: {db_err}")
            requests = []
        
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
        try:
            pending_requests = await db[RGPD_REQUESTS_COLLECTION].find(
                {"process_id": process_id, "status": "pending"}
            ).sort("created_at", -1).limit(1).to_list(1)
        except Exception as db_err:
            logger.error(f"Erro ao buscar RGPD pendentes: {db_err}")
            pending_requests = []
        
        if pending_requests:
            pending = pending_requests[0]
            try:
                expires_str = pending.get("token_expires_at")
                if expires_str:
                    # Tratar diferentes formatos de data
                    if expires_str.endswith('Z'):
                        expires_str = expires_str[:-1] + '+00:00'
                    expires = datetime.fromisoformat(expires_str.replace("Z", "+00:00"))
                    if expires > datetime.now(timezone.utc):
                        return {
                            "has_rgpd": False,
                            "status": "pending",
                            "expires_at": pending.get("token_expires_at"),
                            "request_id": pending.get("id")
                        }
            except (KeyError, ValueError, AttributeError, TypeError) as e:
                logger.warning(f"Error parsing token expiry: {e}")
        
        return {"has_rgpd": False, "status": None}
    except Exception as e:
        logger.error(f"Error in get_rgpd_by_process for {process_id}: {e}", exc_info=True)
        return {"has_rgpd": False, "status": None}


async def sign_rgpd(
    token: str,
    consent_data: dict
) -> Dict[str, Any]:
    """
    Processa a assinatura do RGPD e gera PDF assinado.

    Valida o token, regista os dados de consentimento e gera um PDF legal
    do RGPD assinado que é guardado nos documentos do cliente no S3. Este PDF
    serve como prova legal do consentimento dado pelo cliente.

    Após a assinatura, notifica o consultor por email e regista a atividade
    no histórico do processo para auditoria.

    O PDF é gerado em background — se falhar, a assinatura NÃO é revertida.

    Args:
        token: Token de validação do pedido (gerado pelo create_rgpd_request).
        consent_data: Dicionário com dados preenchidos pelo cliente, incluindo
            nome, contribuinte, tipo de documento, número, morada e assinatura (base64).

    Returns:
        dict: Resultado com chaves success, request_id e process_id.
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
    
    # Actualizar pedido
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
    
    # Gerar PDF do RGPD assinado e guardar nos docs do cliente
    try:
        await _save_signed_rgpd_pdf(request["process_id"], request, consent_data)
    except Exception as e:
        logger.error(f"Erro ao guardar RGPD assinado nos docs: {e}", exc_info=True)
        # Não falha a assinatura — o PDF é um extra
    
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
    # Formatar tipo de documento para exibição legível
    tipo_documento_label = get_tipo_documento_label(consent_data.get('tipo_documento'))
    
    subject = f"RGPD Assinado - {client_name}"
    
    body_text = f"""Olá {user_name},

O cliente {client_name} assinou o documento RGPD com os seguintes dados:

Nome: {consent_data.get('nome', 'N/A')}
Contribuinte: {consent_data.get('contribuinte', 'N/A')}
Tipo de Documento: {tipo_documento_label}
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
        <p><strong>Tipo de Documento:</strong> {tipo_documento_label}</p>
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


# ====================================================================
# GERAÇÃO DE PDF DO RGPD ASSINADO
# ====================================================================

async def _save_signed_rgpd_pdf(
    process_id: str,
    rgpd_request: dict,
    consent_data: dict
):
    """
    Gera um PDF do RGPD assinado e guarda-o nos documentos do cliente (S3).
    
    O PDF inclui:
    - Template RGPD renderizado com variáveis dinâmicas
    - Dados preenchidos pelo cliente
    - Imagem da assinatura digital
    
    Args:
        process_id: ID do processo
        rgpd_request: Documento do pedido RGPD
        consent_data: Dados de consentimento preenchidos
    """
    import io
    import asyncio
    import base64
    from services.s3_storage import s3_service
    
    if not s3_service.is_configured():
        logger.warning("S3 não configurado — RGPD PDF não guardado nos docs")
        return
    
    # Buscar processo para obter client_name e dados
    process = await db.processes.find_one({"id": process_id})
    if not process:
        logger.warning(f"Processo {process_id} não encontrado — RGPD PDF não guardado")
        return
    
    client_name = process.get("client_name", rgpd_request.get("client_name", "Cliente"))
    
    # Buscar template RGPD renderizado
    rgpd_text = await _get_rendered_rgpd_text(process_id, rgpd_request, consent_data)
    
    # Gerar PDF
    pdf_bytes = _generate_rgpd_pdf(rgpd_text, consent_data)
    if not pdf_bytes:
        logger.error("Falha ao gerar PDF do RGPD")
        return
    
    # Upload para S3 na pasta "RGPD"
    filename = f"RGPD_{client_name.replace(' ', '_')}_{rgpd_request['id'][:8]}.pdf"
    file_buffer = io.BytesIO(pdf_bytes)
    
    loop = asyncio.get_event_loop()
    s3_path = await loop.run_in_executor(
        None,
        lambda: s3_service.upload_file(
            file_buffer,
            process_id,
            client_name,
            "RGPD",
            filename,
            content_type="application/pdf"
        )
    )
    
    if s3_path:
        logger.info(f"RGPD PDF guardado nos docs: {s3_path}")
        
        # Registar no histórico do processo
        await log_history(
            process_id,
            {"id": rgpd_request["id"], "name": consent_data.get("nome", "Cliente"), "role": "cliente"},
            "RGPD assinado guardado como PDF",
            field="documento",
            new_value=filename
        )
    else:
        logger.error("Falha ao fazer upload do RGPD PDF para S3")


async def _get_rendered_rgpd_text(
    process_id: str,
    rgpd_request: dict,
    consent_data: dict
) -> str:
    """
    Obtém o template RGPD renderizado com as variáveis dinâmicas substituídas.
    
    Reutiliza a mesma lógica do endpoint GET /api/rgpd/data/{token}
    """
    from routes.rgpd import _get_active_rgpd_template
    
    # Buscar dados do processo (desencriptados)
    process = await db.processes.find_one({"id": process_id})
    if process:
        from services.process_service import decrypt_sensitive_data
        process = decrypt_sensitive_data(process)
    
    personal_data = process.get("personal_data", {}) if process else {}
    
    # Template
    template_text = await _get_active_rgpd_template()
    if not template_text:
        template_text = "DOCUMENTO DE CONSENTIMENTO RGPD\n" + "=" * 50 + "\n\n"
    
    # Substituir variáveis
    rendered = template_text
    client_name = consent_data.get("nome", rgpd_request.get("client_name", ""))
    rendered = rendered.replace("{{NOME_CLIENTE}}", client_name)
    rendered = rendered.replace("{{NOME}}", client_name)
    rendered = rendered.replace("{{CONTRIBUINTE}}", consent_data.get("contribuinte", personal_data.get("nif", "")))
    rendered = rendered.replace("{{MORADA}}", consent_data.get("morada", personal_data.get("morada_fiscal", "")))
    rendered = rendered.replace("{{CODIGO_POSTAL}}", consent_data.get("codigo_postal", ""))
    # Formatar tipo de documento para exibição legível
    tipo_documento_label = get_tipo_documento_label(consent_data.get("tipo_documento"))
    rendered = rendered.replace("{{TIPO_DOCUMENTO}}", tipo_documento_label)
    rendered = rendered.replace("{{NUMERO_DOCUMENTO}}", consent_data.get("numero_documento", ""))
    rendered = rendered.replace("{{VALIDADE_DOCUMENTO}}", consent_data.get("validade_documento", personal_data.get("data_validade_cc", "")))
    rendered = rendered.replace("{{DATA_ASSINATURA}}", consent_data.get("data_assinatura", ""))
    
    return rendered


def _generate_rgpd_pdf(rgpd_text: str, consent_data: dict) -> bytes:
    """
    Gera um PDF com o texto do RGPD e a assinatura do cliente.
    
    Uses reportlab to create a properly formatted PDF with:
    - RGPD template text
    - Signature image (if provided)
    - Signing metadata at the bottom
    
    Args:
        rgpd_text: Texto do RGPD renderizado
        consent_data: Dados de consentimento (inclui assinatura base64)
        
    Returns:
        PDF bytes ou None se falhar
    """
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import inch, cm
        from reportlab.pdfgen import canvas
        from reportlab.lib.utils import ImageReader
        from reportlab.lib.colors import black, grey
    except ImportError:
        logger.error("reportlab não disponível para gerar PDF do RGPD")
        return None
    
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    page_width, page_height = A4
    
    # Margens
    margin_left = 2 * cm
    margin_right = 2 * cm
    margin_top = 2 * cm
    margin_bottom = 2.5 * cm
    
    # Configurar fonte
    font_name = "Helvetica"
    font_size = 9
    title_size = 11
    line_height = font_size + 3
    
    # === HEADER ===
    c.setFont(font_name, title_size)
    y = page_height - margin_top
    
    # === RGPD TEXT ===
    c.setFont(font_name, font_size)
    max_width = page_width - margin_left - margin_right
    max_chars = int(max_width / (font_size * 0.48))
    
    for line in rgpd_text.split('\n'):
        # Skip template variables that weren't replaced
        if "{{" in line:
            continue
        
        # Handle long lines by word-wrapping
        words = line.split(' ')
        current_line = ""
        
        for word in words:
            test_line = f"{current_line} {word}".strip()
            if len(test_line) > max_chars and current_line:
                # Draw current line
                try:
                    c.drawString(margin_left, y, current_line)
                except Exception:
                    current_line = current_line.encode('latin-1', errors='replace').decode('latin-1')
                    c.drawString(margin_left, y, current_line)
                
                y -= line_height
                current_line = word
            else:
                current_line = test_line
        
        # Draw remaining
        if current_line.strip():
            try:
                c.drawString(margin_left, y, current_line)
            except Exception:
                current_line = current_line.encode('latin-1', errors='replace').decode('latin-1')
                c.drawString(margin_left, y, current_line)
        
        y -= line_height
        
        # New page if needed
        if y < margin_bottom + 5 * cm:  # Reserve space for signature
            c.showPage()
            c.setFont(font_name, font_size)
            y = page_height - margin_top
    
    # === SIGNATURE SECTION ===
    y = max(y - 2 * cm, margin_bottom + 4 * cm)
    
    # Separator line
    c.setStrokeColor(grey)
    c.setLineWidth(0.5)
    c.line(margin_left, y + 0.5 * cm, page_width - margin_right, y + 0.5 * cm)
    
    # Signing metadata
    y -= 0.5 * cm
    c.setFont(font_name, font_size)
    
    data_assinatura = consent_data.get("data_assinatura", "")
    nome = consent_data.get("nome", "")
    contribuinte = consent_data.get("contribuinte", "")
    morada = consent_data.get("morada", "")
    
    # Signature info
    info_lines = [
        f"Assinado por: {nome}",
        f"Contribuinte: {contribuinte}",
        f"Morada: {morada}",
        f"Data: {data_assinatura}",
    ]
    
    for info_line in info_lines:
        if info_line.strip():
            try:
                c.drawString(margin_left, y, info_line)
            except Exception:
                info_line = info_line.encode('latin-1', errors='replace').decode('latin-1')
                c.drawString(margin_left, y, info_line)
            y -= line_height
    
    # Signature image (base64)
    assinatura_b64 = consent_data.get("assinatura", "")
    if assinatura_b64 and "," in assinatura_b64:
        try:
            img_data = base64.b64decode(assinatura_b64.split(",")[1])
            img_buffer = io.BytesIO(img_data)
            img_reader = ImageReader(img_buffer)
            
            # Scale signature to reasonable size (max 6cm wide)
            img_w, img_h = img_reader.getSize()
            max_sig_width = 6 * cm
            if img_w > max_sig_width:
                scale = max_sig_width / img_w
                img_w = max_sig_width
                img_h = img_h * scale
            
            # Draw signature
            sig_y = max(y - 1.5 * cm, margin_bottom)
            c.drawImage(img_reader, margin_left, sig_y, width=img_w, height=img_h, mask='auto')
        except Exception as e:
            logger.warning(f"Não foi possível incluir assinatura no PDF: {e}")
    
    c.save()
    return buffer.getvalue()

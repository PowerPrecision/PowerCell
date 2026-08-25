"""
Serviço RGPD - Gestão de consentimentos e tokens temporários

Este módulo implementa:
- Criação de pedidos de consentimento
- Validação de tokens temporários
- Processamento de assinaturas
- Geração de PDF do RGPD assinado
- Envio de emails
"""
import re
import uuid
import io
import base64
import logging
import smtplib
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any
from database import db
from services.email_service import send_email, EmailAccount
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
    # PACOTE DG — não retornar "N/A" para campo vazio; retornar "" para que o
    # template RGPD mostre a linha em branco "_____" (definida em consent_data),
    # em vez de "Titular do N/A n.o ..." no PDF pré-preenchido para assinatura manual.
    if not tipo_documento:
        return ""
    return TIPOS_DOCUMENTO_LABELS.get(tipo_documento, tipo_documento)


# ====================================================================
# PACOTE FR-4 — Empresa real associada ao pedido de RGPD (emissão + envio)
# ====================================================================

async def _resolve_rgpd_company(
    process_id: Optional[str] = None,
    user: Optional[dict] = None,
    user_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Resolve a Company (``db.companies``) real associada a um pedido de RGPD.

    Substitui o emissor fixo ("Precision Crédito, Lda.") por uma resolução
    dinâmica que respeita a Empresa efetivamente associada ao processo ou
    ao utilizador que iniciou o pedido — usado tanto na emissão do PDF
    (nome/NIF da empresa) como no envio de email (credenciais SMTP).

    Prioridade de resolução:
        1. ``company_id`` / ``company_name`` / ``company`` do processo
           (``process_id``).
        2. ``active_company_id`` / ``company_id`` / ``company`` do
           utilizador que solicitou o RGPD (``user`` — dict completo, ou
           ``user_id`` para consultar ``db.users`` quando só temos o id,
           ex.: a partir de ``rgpd_request["created_by"]``).

    Cada candidato pode ser um ``id`` (UUID) ou o ``name`` da empresa
    (case-insensitive) — o mesmo padrão de correspondência usado por
    ``_find_ucr`` (``services/auth.py``).

    Devolve ``None`` (nunca levanta excepção) se não encontrar nenhuma
    empresa correspondente — os chamadores devem manter o fallback fixo
    (``RGPD_ISSUER_NAME``/``RGPD_ISSUER_NIF``, ou a config SMTP default
    do sistema).
    """
    candidates: list = []

    if process_id:
        try:
            process = await db.processes.find_one(
                {"id": process_id},
                {"_id": 0, "company_id": 1, "company_name": 1, "company": 1},
            )
        except Exception as e:
            logger.warning(f"[RGPD] Erro ao buscar processo {process_id} para resolver empresa: {e}")
            process = None
        if process:
            for key in ("company_id", "company_name", "company"):
                value = process.get(key)
                if value:
                    candidates.append(str(value))

    resolved_user = user
    if resolved_user is None and user_id:
        try:
            resolved_user = await db.users.find_one(
                {"id": user_id},
                {"_id": 0, "company": 1, "active_company_id": 1, "company_id": 1},
            )
        except Exception as e:
            logger.warning(f"[RGPD] Erro ao buscar utilizador {user_id} para resolver empresa: {e}")
            resolved_user = None

    if resolved_user:
        for key in ("active_company_id", "company_id", "company"):
            value = resolved_user.get(key)
            if value:
                candidates.append(str(value))

    for candidate in candidates:
        candidate = candidate.strip()
        if not candidate or candidate.lower() == "default":
            continue
        try:
            company = await db.companies.find_one({"id": candidate}, {"_id": 0})
            if not company:
                company = await db.companies.find_one(
                    {"name": {"$regex": f"^{re.escape(candidate)}$", "$options": "i"}},
                    {"_id": 0},
                )
        except Exception as e:
            logger.warning(f"[RGPD] Erro ao buscar empresa '{candidate}': {e}")
            company = None
        if company:
            return company

    return None


def _build_company_smtp_account(company: Optional[Dict[str, Any]]) -> Optional[EmailAccount]:
    """
    Constrói um ``EmailAccount`` a partir das credenciais SMTP da Empresa
    (``smtp_email``/``smtp_password``/``smtp_host``/``smtp_port``), para
    ser usado como ``account_override`` em ``send_email`` — a conta SMTP
    da empresa tem prioridade sobre a configuração SMTP default do sistema.

    Devolve ``None`` se a empresa não existir ou não tiver as 4
    credenciais SMTP preenchidas — nesse caso, o chamador mantém o
    comportamento anterior (fallback silencioso para ``system_purpose="RGPD"``).
    """
    if not company:
        return None
    smtp_email = company.get("smtp_email")
    smtp_password = company.get("smtp_password")
    smtp_host = company.get("smtp_host")
    smtp_port = company.get("smtp_port")
    if not (smtp_email and smtp_password and smtp_host and smtp_port):
        return None
    try:
        smtp_port = int(smtp_port)
    except (TypeError, ValueError):
        logger.warning(f"[RGPD] smtp_port inválido na empresa '{company.get('name')}': {smtp_port!r}")
        return None
    return EmailAccount(
        name=f"company_{company.get('id') or company.get('name') or 'smtp'}",
        imap_server=smtp_host,
        imap_port=smtp_port,
        smtp_server=smtp_host,
        smtp_port=smtp_port,
        email=smtp_email,
        password=smtp_password,
    )


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
    Processa a assinatura do RGPD e gera 2 PDFs (RGPD + Minuta).

    Valida o token, regista os dados de consentimento e gera PDFs legais
    que são guardados nos documentos do cliente no S3 e enviados por email.

    Após a assinatura, notifica o consultor e o cliente por email e regista
    a atividade no histórico do processo para auditoria.
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
    # [Pacote X] Guardar IP do cliente para auditoria e PDF
    client_ip = consent_data.get("client_ip", "unknown")
    consent_data["client_ip"] = client_ip
    
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
    
    # Gerar 2 PDFs (RGPD + Minuta) e guardar nos docs do cliente
    rgpd_pdf_bytes = None
    minuta_pdf_bytes = None
    try:
        rgpd_pdf_bytes = await _generate_rgpd_pdf_bytes(request["process_id"], request, consent_data)
        minuta_pdf_bytes = await _generate_minuta_pdf_bytes(request["process_id"], request, consent_data)
        
        # Upload para S3
        client_name = consent_data.get("nome", request.get("client_name", "Cliente"))
        if rgpd_pdf_bytes:
            await _upload_pdf_to_s3(
                request["process_id"], client_name, rgpd_pdf_bytes,
                f"RGPD_{client_name.replace(' ', '_')}_{request['id'][:8]}.pdf", "RGPD"
            )
        if minuta_pdf_bytes:
            await _upload_pdf_to_s3(
                request["process_id"], client_name, minuta_pdf_bytes,
                f"Minuta_Exclusividade_{client_name.replace(' ', '_')}_{request['id'][:8]}.pdf", "RGPD"
            )
    except Exception as e:
        logger.error(f"Erro ao gerar/fazer upload dos PDFs: {e}", exc_info=True)
        # Não falha a assinatura — os PDFs são um extra
    
    # Adicionar atividade ao processo
    await log_history(
        request["process_id"],
        {"id": request["id"], "name": consent_data.get("nome", "Cliente"), "role": "cliente"},
        "RGPD + Minuta de Exclusividade assinados pelo cliente"
    )
    
    # Enviar email ao consultor
    # [Pacote X] Incluir PDFs como anexo no email de notificação ao staff
    user_email = request.get("created_by_email")
    user_name = request.get("created_by_name", "")
    client_name = consent_data.get("nome", request.get("client_name", ""))
    
    if user_email:
        await send_rgpd_signed_email(
            to_email=user_email,
            user_name=user_name,
            client_name=client_name,
            consent_data=consent_data,
            process_id=request["process_id"],
            rgpd_pdf_bytes=rgpd_pdf_bytes,
            minuta_pdf_bytes=minuta_pdf_bytes,
            client_ip=client_ip,
        )
    
    # Enviar email ao cliente com 2 PDFs em anexo
    client_email = request.get("client_email")
    if client_email and (rgpd_pdf_bytes or minuta_pdf_bytes):
        try:
            await _send_client_confirmation_email(
                client_email=client_email,
                client_name=client_name,
                rgpd_pdf_bytes=rgpd_pdf_bytes,
                minuta_pdf_bytes=minuta_pdf_bytes,
                consent_data=consent_data,
                process_id=request["process_id"]
            )
        except Exception as e:
            logger.error(f"Erro ao enviar email de confirmação ao cliente: {e}", exc_info=True)
    
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
    custom_message: str = None,
    base_url: str = None,
    raise_on_error: bool = False,
    process_id: str = None,
    user_id: str = None,
) -> bool:
    """
    Envia email de RGPD para o cliente.
    
    Args:
        client_email: Email do cliente
        client_name: Nome do cliente
        token: Token de validação
        request_id: ID do pedido
        user_email: Email do utilizador que solicitou
        custom_message: Mensagem personalizada a incluir no email
        base_url: URL base para o link (default: variável de ambiente ou www.powercell.pt)
        raise_on_error: Pacote FQ-4 — se True, propaga smtplib.SMTPAuthenticationError
            (ou smtplib.SMTPException genérico) em vez de engolir o erro e devolver
            False. Usado pelo endpoint de reenvio (`/admin/{id}/resend`) para poder
            distinguir uma falha de credenciais SMTP (400) de um erro genérico (500).
            O comportamento por omissão (False) mantém-se inalterado para não afetar
            o fluxo de criação de pedidos RGPD (`run_request_rgpd`), que tolera envio
            de email falhado sem bloquear a criação do pedido.
        process_id: Pacote FR-4 — ID do processo, usado para resolver a Empresa
            real (``db.companies``) e, se tiver SMTP configurado, enviar através
            dessa conta em vez da configuração SMTP default do sistema.
        user_id: Pacote FR-4 — ID do utilizador que solicitou o RGPD, usado como
            fallback de resolução da Empresa quando o processo não tem
            ``company_id``/``company`` associado.
    
    Returns:
        True se enviado com sucesso
    """
    import os
    # PACOTE DI — URL de produção actualizada para Precision Crédito.
    if base_url is None:
        base_url = os.environ.get("FRONTEND_URL", "https://www.precisioncredito.pt")
    
    # Construir link temporário
    rgpd_link = f"{base_url}/rgpd/{token}"
    
    # PACOTE DI — marca client-facing actualizada para Precision Crédito.
    subject = "Solicitação de Assinatura RGPD - Precision Crédito"
    
    # Custom message from staff
    custom_section = ""
    if custom_message:
        custom_section = f"\n{custom_message}\n"
    
    body_text = f"""Estimado(a) {client_name},

Gostaríamos de solicitar a sua assinatura do documento RGPD.
{custom_section}
Atenção: deverá assinar num máximo de 24h.

PREENCHER RGPD: {rgpd_link}

Atenciosamente,
Equipa Precision Crédito
"""
    
    # Custom message section for HTML
    custom_section_html = ""
    if custom_message:
        custom_section_html = f"""
    <div style="background-color: #e8f4fd; border-left: 4px solid #2563eb; padding: 15px; margin: 20px 0; border-radius: 0 5px 5px 0;">
        <p style="margin: 0;">{custom_message}</p>
    </div>
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
    
    <p>Gostaríamos de solicitar a sua assinatura do documento <strong>RGPD</strong>.</p>
    {custom_section_html}
    <div style="background-color: #fff3cd; border: 1px solid #ffc107; padding: 15px; border-radius: 5px; margin: 20px 0;">
        <strong>⚠️ Atenção:</strong> Deverá assinar num máximo de 24h.
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

        # Pacote FR-4 — a conta SMTP a usar respeita a Empresa real associada
        # ao processo (ou, em fallback, ao utilizador que solicitou o RGPD).
        # Se a empresa tiver as 4 credenciais SMTP preenchidas
        # (smtp_email/smtp_password/smtp_host/smtp_port), usa-as em vez da
        # configuração SMTP default do sistema (system_purpose="RGPD").
        company = await _resolve_rgpd_company(process_id=process_id, user_id=user_id)
        account_override = _build_company_smtp_account(company)

        result = await send_email(
            account_name=account,
            to_emails=[client_email],
            subject=subject,
            body=body_text,
            body_html=body_html,
            created_by=user_email,
            force_system=True,
            system_purpose="RGPD",
            account_override=account_override,
        )
        
        if not result.get("success", False):
            error_msg = result.get("error") or "Erro ao enviar email RGPD"
            logger.error(f"Failed to send RGPD email: {error_msg}")
            if raise_on_error:
                if "autenticação" in error_msg.lower() or "authentication" in error_msg.lower():
                    raise smtplib.SMTPAuthenticationError(535, error_msg)
                raise smtplib.SMTPException(error_msg)
            return False
        
        logger.info(f"RGPD email sent to {client_email}")
        return True
        
    except smtplib.SMTPException:
        # Pacote FQ-4 — propagar tal como está para o chamador poder
        # devolver um erro 400 elegante em vez de um 500 genérico.
        raise
    except Exception as e:
        logger.error(f"Failed to send RGPD email: {e}")
        if raise_on_error:
            raise smtplib.SMTPException(str(e))
        return False


async def send_rgpd_signed_email(
    to_email: str,
    user_name: str,
    client_name: str,
    consent_data: dict,
    process_id: str,
    rgpd_pdf_bytes: bytes = None,
    minuta_pdf_bytes: bytes = None,
    client_ip: str = "unknown",
) -> bool:
    """
    Envia email com o RGPD assinado para o utilizador.
    
    [Pacote X] Agora inclui os PDFs (RGPD + Minuta) como anexos,
    permitindo ao staff aceder imediatamente aos documentos sem
    necessidade de os ir buscar ao processo.
    
    Args:
        to_email: Email do utilizador
        user_name: Nome do utilizador
        client_name: Nome do cliente
        consent_data: Dados do consentimento
        process_id: ID do processo
        rgpd_pdf_bytes: PDF do RGPD assinado (bytes)
        minuta_pdf_bytes: PDF da Minuta assinada (bytes)
        client_ip: IP do cliente no momento da assinatura
    
    Returns:
        True se enviado com sucesso
    """
    # Formatar tipo de documento para exibição legível
    tipo_documento_label = get_tipo_documento_label(consent_data.get('tipo_documento'))
    
    # [Pacote X] Construir anexos com os PDFs gerados
    attachments = []
    safe_name = client_name.replace(' ', '_')
    if rgpd_pdf_bytes:
        attachments.append({
            "filename": f"RGPD_{safe_name}.pdf",
            "content_bytes": rgpd_pdf_bytes,
            "content_type": "application/pdf"
        })
    if minuta_pdf_bytes:
        attachments.append({
            "filename": f"Minuta_Exclusividade_{safe_name}.pdf",
            "content_bytes": minuta_pdf_bytes,
            "content_type": "application/pdf"
        })
    
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
        <p><strong>IP do Cliente:</strong> {client_ip}</p>
    </div>
    
    <p>O processo foi atualizado com esta informação.</p>
    
    <hr style="border: none; border-top: 1px solid #ddd; margin: 30px 0;">
    
    <p style="color: #666; font-size: 12px;">Esta é uma mensagem automática do sistema CRM.</p>
</body>
</html>
"""
    
    try:
        # Pacote FR-4 — usar a conta SMTP da Empresa real do processo, se
        # configurada (ver `send_rgpd_email` para detalhes da prioridade).
        company = await _resolve_rgpd_company(process_id=process_id)
        account_override = _build_company_smtp_account(company)

        result = await send_email(
            account_name="precision",
            to_emails=[to_email],
            subject=subject,
            body=body_text,
            body_html=body_html,
            attachments=attachments if attachments else None,
            force_system=True,
            system_purpose="RGPD",
            account_override=account_override,
        )
        
        logger.info(f"RGPD signed notification sent to {to_email}")
        return result.get("success", False)
        
    except Exception as e:
        logger.error(f"Failed to send RGPD signed notification: {e}")
        return False


# ====================================================================
# GERAÇÃO DE PDFs DO RGPD ASSINADO E MINUTA
# ====================================================================

async def _upload_pdf_to_s3(process_id: str, client_name: str, pdf_bytes: bytes, filename: str, category: str):
    """Upload PDF bytes to S3 and register in documents collection.
    
    [Pacote X] Agora cria também uma entrada na coleção 'documents' associada
    ao process_id, para que o documento apareça na secção de documentos do
    processo no frontend.
    """
    import asyncio
    from services.s3_storage import s3_service
    
    if not s3_service.is_configured():
        logger.warning("S3 não configurado — PDF não guardado nos docs")
        return
    
    file_buffer = io.BytesIO(pdf_bytes)
    loop = asyncio.get_event_loop()
    s3_path = await loop.run_in_executor(
        None,
        lambda: s3_service.upload_file(
            file_buffer,
            process_id,
            client_name,
            category,
            filename,
            content_type="application/pdf"
        )
    )
    
    if s3_path:
        logger.info(f"PDF guardado nos docs: {s3_path}")
        
        # [Pacote X] Criar entrada na coleção documents para o processo
        try:
            now_iso = datetime.now(timezone.utc).isoformat()
            # Determinar client_id a partir do processo
            process = await db.processes.find_one(
                {"id": process_id},
                {"_id": 0, "client_id": 1}
            )
            doc_entry = {
                "id": str(uuid.uuid4()),
                "process_id": process_id,
                "client_id": process.get("client_id") if process else None,
                "category": category.lower() if category else "rgpd",
                "filename": s3_path,
                "original_filename": filename,
                "status": "VALIDATED",
                "file_url": s3_path,
                "file_size": len(pdf_bytes),
                "content_type": "application/pdf",
                "uploaded_at": now_iso,
                "created_at": now_iso,
                "updated_at": now_iso,
                "requested_by": "system",
                "requested_by_name": "Sistema (RGPD)",
                "source": "rgpd_sign",
                "notes": f"Documento gerado automaticamente aquando da assinatura do RGPD: {filename}",
            }
            await db.documents.insert_one(doc_entry)
            logger.info(f"[RGPD] Entrada criada em documents para {process_id}: {filename}")
        except Exception as e:
            logger.error(f"[RGPD] Erro ao criar entrada em documents: {e}", exc_info=True)
    else:
        logger.error("Falha ao fazer upload do PDF para S3")


async def _get_rendered_rgpd_text(
    process_id: str,
    rgpd_request: dict,
    consent_data: dict
) -> str:
    """Obtém o template RGPD renderizado com as variáveis dinâmicas substituídas."""
    from services.rgpd_templates import _get_active_rgpd_template
    
    process = await db.processes.find_one({"id": process_id})
    if process:
        from services.process_service import decrypt_sensitive_data
        process = decrypt_sensitive_data(process)
    
    personal_data = process.get("personal_data", {}) if process else {}
    
    template_text = await _get_active_rgpd_template()
    if not template_text:
        template_text = "DOCUMENTO DE CONSENTIMENTO RGPD\n" + "=" * 50 + "\n\n"
    
    rendered = template_text
    client_name = consent_data.get("nome", rgpd_request.get("client_name", ""))
    localidade = consent_data.get("localidade", "")
    
    # Pacote FR-4 — o emissor/responsável pelo tratamento do RGPD passa a
    # respeitar a Empresa real associada ao processo (ou, em fallback, ao
    # utilizador que solicitou o RGPD), em vez de estar sempre fixo na
    # Precision Crédito (Pacote FQ-4). RGPD_ISSUER_NAME/NIF mantêm-se como
    # fallback quando não é possível resolver nenhuma Company.
    from services.rgpd_templates import RGPD_ISSUER_NAME, RGPD_ISSUER_NIF
    empresa_nome = RGPD_ISSUER_NAME
    empresa_nif = RGPD_ISSUER_NIF
    empresa_morada = ""
    empresa_contacto = ""

    company = await _resolve_rgpd_company(
        process_id=process_id, user_id=rgpd_request.get("created_by")
    )
    if company:
        if company.get("name"):
            empresa_nome = company["name"]
        if company.get("nif"):
            empresa_nif = company["nif"]
        if company.get("address"):
            empresa_morada = company["address"]
        if company.get("phone"):
            empresa_contacto = company["phone"]

    # Morada/Contacto continuam a ter fallback em system_config (dados de
    # correio) quando a Company resolvida não os tiver preenchidos.
    try:
        config = await db.system_config.find_one(
            {"_id": "main"},
            {"_id": 0, "settings.company_address": 1, "settings.company_phone": 1}
        )
        if config:
            settings = config.get("settings", {})
            if not empresa_morada and settings.get("company_address"):
                empresa_morada = settings["company_address"]
            if not empresa_contacto and settings.get("company_phone"):
                empresa_contacto = settings["company_phone"]
    except Exception:
        pass

    rendered = rendered.replace("{{NOME_CLIENTE}}", client_name)
    rendered = rendered.replace("{{NOME}}", client_name)
    # PACOTE DG — NOME_EMPRESA / MORADA_EMPRESA / CONTACTO_EMPRESA agora
    # substituídos (antes ficavam literais no template RGPD).
    rendered = rendered.replace("{{NOME_EMPRESA}}", empresa_nome)
    rendered = rendered.replace("{{NIF_EMPRESA}}", empresa_nif)
    rendered = rendered.replace("{{MORADA_EMPRESA}}", empresa_morada)
    rendered = rendered.replace("{{CONTACTO_EMPRESA}}", empresa_contacto)
    rendered = rendered.replace("{{CONTRIBUINTE}}", consent_data.get("contribuinte", personal_data.get("nif", "")))
    rendered = rendered.replace("{{MORADA}}", consent_data.get("morada", personal_data.get("morada_fiscal", "")))
    rendered = rendered.replace("{{LOCALIDADE}}", localidade)
    rendered = rendered.replace("{{CODIGO_POSTAL}}", consent_data.get("codigo_postal", ""))
    tipo_documento_label = get_tipo_documento_label(consent_data.get("tipo_documento"))
    rendered = rendered.replace("{{TIPO_DOCUMENTO}}", tipo_documento_label)
    rendered = rendered.replace("{{NUMERO_DOCUMENTO}}", consent_data.get("numero_documento", ""))
    rendered = rendered.replace("{{VALIDADE_DOCUMENTO}}", consent_data.get("validade_documento", personal_data.get("data_validade_cc", "")))
    rendered = rendered.replace("{{DATA_ASSINATURA}}", consent_data.get("data_assinatura", ""))
    
    return rendered


async def _get_rendered_minuta_text(
    process_id: str,
    rgpd_request: dict,
    consent_data: dict
) -> str:
    """Obtém o template Minuta renderizado com as variáveis dinâmicas substituídas."""
    from services.rgpd_minutas import _get_active_minuta_template
    
    process = await db.processes.find_one({"id": process_id})
    if process:
        from services.process_service import decrypt_sensitive_data
        process = decrypt_sensitive_data(process)
    
    personal_data = process.get("personal_data", {}) if process else {}
    
    template_text = await _get_active_minuta_template()
    if not template_text:
        template_text = "MINUTA DE EXCLUSIVIDADE\n"
    
    rendered = template_text
    client_name = consent_data.get("nome", rgpd_request.get("client_name", ""))
    localidade = consent_data.get("localidade", "")
    
    # Pacote FR-4 — emissor/responsável passa a respeitar a Empresa real
    # associada ao processo (ou ao utilizador solicitante), tal como em
    # `_get_rendered_rgpd_text`. RGPD_ISSUER_NAME/NIF mantêm-se como
    # fallback quando não é possível resolver nenhuma Company.
    from services.rgpd_templates import RGPD_ISSUER_NAME, RGPD_ISSUER_NIF
    empresa_nome = RGPD_ISSUER_NAME
    empresa_nif = RGPD_ISSUER_NIF
    empresa_morada = ""
    empresa_contacto = ""

    company = await _resolve_rgpd_company(
        process_id=process_id, user_id=rgpd_request.get("created_by")
    )
    if company:
        if company.get("name"):
            empresa_nome = company["name"]
        if company.get("nif"):
            empresa_nif = company["nif"]
        if company.get("address"):
            empresa_morada = company["address"]
        if company.get("phone"):
            empresa_contacto = company["phone"]

    try:
        config = await db.system_config.find_one(
            {"_id": "main"},
            {"_id": 0, "settings.company_address": 1, "settings.company_phone": 1}
        )
        if config:
            settings = config.get("settings", {})
            if not empresa_morada and settings.get("company_address"):
                empresa_morada = settings["company_address"]
            if not empresa_contacto and settings.get("company_phone"):
                empresa_contacto = settings["company_phone"]
    except Exception:
        pass

    rendered = rendered.replace("{{NOME_CLIENTE}}", client_name)
    rendered = rendered.replace("{{NOME}}", client_name)
    rendered = rendered.replace("{{NOME_EMPRESA}}", empresa_nome)
    rendered = rendered.replace("{{NIF_EMPRESA}}", empresa_nif)
    rendered = rendered.replace("{{CONTRIBUINTE}}", consent_data.get("contribuinte", personal_data.get("nif", "")))
    rendered = rendered.replace("{{MORADA}}", consent_data.get("morada", personal_data.get("morada_fiscal", "")))
    rendered = rendered.replace("{{LOCALIDADE}}", localidade)
    rendered = rendered.replace("{{CODIGO_POSTAL}}", consent_data.get("codigo_postal", ""))
    rendered = rendered.replace("{{TIPO_DOCUMENTO}}", get_tipo_documento_label(consent_data.get("tipo_documento")))
    rendered = rendered.replace("{{NUMERO_DOCUMENTO}}", consent_data.get("numero_documento", ""))
    rendered = rendered.replace("{{VALIDADE_DOCUMENTO}}", consent_data.get("validade_documento", personal_data.get("data_validade_cc", "")))
    rendered = rendered.replace("{{DATA_ASSINATURA}}", consent_data.get("data_assinatura", ""))
    rendered = rendered.replace("{{MORADA_EMPRESA}}", empresa_morada)
    rendered = rendered.replace("{{CONTACTO_EMPRESA}}", empresa_contacto)
    
    return rendered


async def _generate_rgpd_pdf_bytes(process_id: str, rgpd_request: dict, consent_data: dict) -> bytes:
    """Generate RGPD PDF bytes with professional A4 layout."""
    import asyncio
    
    rgpd_text = await _get_rendered_rgpd_text(process_id, rgpd_request, consent_data)
    
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _build_rgpd_pdf, rgpd_text, consent_data)


async def _generate_minuta_pdf_bytes(process_id: str, rgpd_request: dict, consent_data: dict) -> bytes:
    """Generate Minuta PDF bytes with professional A4 layout."""
    import asyncio
    
    minuta_text = await _get_rendered_minuta_text(process_id, rgpd_request, consent_data)
    
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _build_minuta_pdf, minuta_text, consent_data)


def _build_rgpd_pdf(rgpd_text: str, consent_data: dict) -> bytes:
    """Build professional RGPD PDF with reportlab."""
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import cm
        from reportlab.pdfgen import canvas
        from reportlab.lib.utils import ImageReader
        from reportlab.lib.colors import HexColor, black, grey
    except ImportError:
        logger.error("reportlab não disponível")
        return b""
    
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    page_width, page_height = A4
    
    margin_left = 2 * cm
    margin_right = 2 * cm
    margin_top = 2 * cm
    margin_bottom = 2 * cm
    
    font_name = "Helvetica"
    font_size = 9
    title_size = 12
    subtitle_size = 10
    line_height = font_size + 4
    
    y = page_height - margin_top
    
    # === HEADER ===
    # Title
    c.setFont("Helvetica-Bold", title_size)
    c.drawCentredString(page_width / 2, y, "RGPD - Regulamento Geral sobre a Proteção de Dados")
    y -= line_height + 4
    
    # Separator
    c.setStrokeColor(HexColor("#333333"))
    c.setLineWidth(0.5)
    c.line(margin_left, y, page_width - margin_right, y)
    y -= line_height + 4
    
    # === CONSENTIMENTO SECTION ===
    c.setFont("Helvetica-Bold", subtitle_size)
    c.drawString(margin_left, y, "Consentimento")
    y -= line_height + 2
    
    # Client info paragraph
    c.setFont(font_name, font_size)
    nome = consent_data.get("nome", "")
    contribuinte = consent_data.get("contribuinte", "")
    tipo_doc = get_tipo_documento_label(consent_data.get("tipo_documento", ""))
    num_doc = consent_data.get("numero_documento", "")
    validade = consent_data.get("validade_documento", "")
    morada = consent_data.get("morada", "")
    localidade = consent_data.get("localidade", "")
    cod_postal = consent_data.get("codigo_postal", "")
    
    consent_text = (
        f"Eu, {nome}, titular do {tipo_doc} n.o {num_doc}, "
        f"valido ate {validade} com o n.o de contribuinte {contribuinte}, "
        f"residente na {morada}, {localidade}, "
        f"codigo postal: {cod_postal}, tendo tomado conhecimento da "
        f"Politica de Privacidade, declaro que:"
    )
    
    max_width = page_width - margin_left - margin_right
    max_chars = int(max_width / (font_size * 0.48))
    
    for line in consent_text.split('\n'):
        words = line.split(' ')
        current_line = ""
        for word in words:
            test_line = f"{current_line} {word}".strip()
            if len(test_line) > max_chars and current_line:
                try:
                    c.drawString(margin_left, y, current_line)
                except Exception:
                    current_line = current_line.encode('latin-1', errors='replace').decode('latin-1')
                    c.drawString(margin_left, y, current_line)
                y -= line_height
                current_line = word
            else:
                current_line = test_line
        if current_line.strip():
            try:
                c.drawString(margin_left, y, current_line)
            except Exception:
                current_line = current_line.encode('latin-1', errors='replace').decode('latin-1')
                c.drawString(margin_left, y, current_line)
            y -= line_height
    
    y -= line_height
    
    # === 4 CONSENT OPTIONS ===
    consent_options = [
        ("A", consent_data.get("consent_a", ""), 
         "Quanto a transmissao dos meus dados pessoais a entidade vinculada, "
         "encontrando-se obrigado a fornecer-lhe os meus dados identificados "
         "no ponto 2. da Politica de Privacidade:"),
        ("B", consent_data.get("consent_b", ""),
         "Quanto ao tratamento dos meus dados pessoais para efeitos de "
         "divulgacao de produtos, servicos e campanhas:"),
        ("C", consent_data.get("consent_c", ""),
         "Quanto a possibilidade de as instituicoes financeiras consultarem "
         "informacao na Central de Responsabilidades de Credito:"),
        ("D", consent_data.get("consent_d", ""),
         "Autorizo a transmissao dos meus dados pessoais a instituicoes "
         "financeiras com o objetivo de me apresentarem uma proposta de financiamento:"),
    ]
    
    for letter, choice, description in consent_options:
        if y < margin_bottom + 6 * cm:
            c.showPage()
            c.setFont(font_name, font_size)
            y = page_height - margin_top
        
        # Option letter and description
        c.setFont("Helvetica-Bold", font_size)
        option_header = f"{letter}) {description}"
        
        # Word wrap the header
        words = option_header.split(' ')
        current_line = ""
        for word in words:
            test_line = f"{current_line} {word}".strip()
            if len(test_line) > max_chars and current_line:
                try:
                    c.drawString(margin_left, y, current_line)
                except Exception:
                    pass
                y -= line_height
                current_line = word
            else:
                current_line = test_line
        if current_line.strip():
            try:
                c.drawString(margin_left, y, current_line)
            except Exception:
                pass
            y -= line_height
        
        # Autorizo / Não Autorizo
        is_autorizo = choice == "autorizo"
        y += 2  # slight indent
        
        if is_autorizo:
            c.setFont("Helvetica-Bold", font_size)
            # Draw checked circle
            c.circle(margin_left + 6, y + 3, 4, fill=1)
            c.setFont(font_name, font_size)
            c.drawString(margin_left + 14, y, "Autorizo")
            # Draw unchecked circle for Não Autorizo
            c.circle(margin_left + 76, y + 3, 4, fill=0)
            c.drawString(margin_left + 84, y, "Nao Autorizo")
        else:
            c.setFont(font_name, font_size)
            c.circle(margin_left + 6, y + 3, 4, fill=0)
            c.drawString(margin_left + 14, y, "Autorizo")
            c.circle(margin_left + 76, y + 3, 4, fill=1)
            c.setFont("Helvetica-Bold", font_size)
            c.drawString(margin_left + 84, y, "Nao Autorizo")
        
        y -= line_height + 6
    
    # === SIGNATURE SECTION ===
    y -= line_height
    
    if y < margin_bottom + 5 * cm:
        c.showPage()
        c.setFont(font_name, font_size)
        y = page_height - margin_top
    
    # Separator
    c.setStrokeColor(grey)
    c.setLineWidth(0.5)
    c.line(margin_left, y, page_width - margin_right, y)
    y -= line_height + 4
    
    # Date and location (PACOTE DI — Endereço IP removido do PDF;
    # mantém-se no email staff `send_rgpd_signed_email` para auditoria).
    data_assinatura = consent_data.get("data_assinatura", "")
    loc = consent_data.get("localidade", "")
    if loc and data_assinatura:
        # Format: "Lisboa, 24/04/2026"
        date_only = data_assinatura.split(" ")[0] if " " in data_assinatura else data_assinatura
        c.setFont(font_name, font_size)
        try:
            c.drawString(margin_left, y, f"{loc}, {date_only}")
        except Exception:
            pass
        y -= line_height
    y += 4  # Compensar o espaço extra adicionado
    
    # Signature label
    c.setFont("Helvetica-Bold", font_size)
    c.drawString(margin_left, y, "Assinatura do Cliente")
    y -= line_height
    c.setFont(font_name, font_size - 1)
    c.drawString(margin_left, y, "Titular dos Dados")
    y -= line_height
    c.setFont("Helvetica-Oblique", font_size - 2)
    c.drawString(margin_left, y, "Por favor assine conforme o seu cartao de identificacao.")
    y -= line_height + 4
    
    # Signature image
    assinatura_b64 = consent_data.get("assinatura", "")
    if assinatura_b64 and "," in assinatura_b64:
        try:
            img_data = base64.b64decode(assinatura_b64.split(",")[1])
            img_buffer = io.BytesIO(img_data)
            img_reader = ImageReader(img_buffer)
            
            img_w, img_h = img_reader.getSize()
            max_sig_width = 8 * cm
            max_sig_height = 4 * cm
            if img_w > max_sig_width:
                scale = max_sig_width / img_w
                img_w = max_sig_width
                img_h = img_h * scale
            if img_h > max_sig_height:
                scale = max_sig_height / img_h
                img_h = max_sig_height
                img_w = img_w * scale
            
            c.drawImage(img_reader, margin_left, y - max_sig_height, width=img_w, height=img_h, mask='auto')
        except Exception as e:
            logger.warning(f"Não foi possível incluir assinatura no PDF RGPD: {e}")
    
    c.save()
    return buffer.getvalue()


def _build_minuta_pdf(minuta_text: str, consent_data: dict) -> bytes:
    """Build professional Minuta de Exclusividade PDF."""
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import cm
        from reportlab.pdfgen import canvas
        from reportlab.lib.utils import ImageReader
        from reportlab.lib.colors import HexColor, black, grey
    except ImportError:
        logger.error("reportlab não disponível")
        return b""
    
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    page_width, page_height = A4
    
    margin_left = 2 * cm
    margin_right = 2 * cm
    margin_top = 2 * cm
    margin_bottom = 2 * cm
    
    font_name = "Helvetica"
    font_size = 11
    title_size = 14
    line_height = font_size + 5
    
    y = page_height - margin_top
    
    # === TITLE ===
    c.setFont("Helvetica-Bold", title_size)
    c.drawCentredString(page_width / 2, y, "MINUTA DE EXCLUSIVIDADE")
    y -= line_height + 4
    
    # Separator
    c.setStrokeColor(HexColor("#333333"))
    c.setLineWidth(0.5)
    c.line(margin_left, y, page_width - margin_right, y)
    y -= line_height + 8
    
    # === BODY TEXT ===
    c.setFont(font_name, font_size)
    max_width = page_width - margin_left - margin_right
    max_chars = int(max_width / (font_size * 0.48))
    
    for line in minuta_text.split('\n'):
        if "{{" in line:
            continue
        
        words = line.split(' ')
        current_line = ""
        for word in words:
            test_line = f"{current_line} {word}".strip()
            if len(test_line) > max_chars and current_line:
                try:
                    c.drawString(margin_left, y, current_line)
                except Exception:
                    current_line = current_line.encode('latin-1', errors='replace').decode('latin-1')
                    c.drawString(margin_left, y, current_line)
                y -= line_height
                current_line = word
            else:
                current_line = test_line
        if current_line.strip():
            try:
                c.drawString(margin_left, y, current_line)
            except Exception:
                current_line = current_line.encode('latin-1', errors='replace').decode('latin-1')
                c.drawString(margin_left, y, current_line)
            y -= line_height
        
        if y < margin_bottom + 6 * cm:
            c.showPage()
            c.setFont(font_name, font_size)
            y = page_height - margin_top
    
    y -= line_height
    
    # === SIGNATURE SECTION ===
    c.setStrokeColor(grey)
    c.setLineWidth(0.5)
    c.line(margin_left, y, page_width - margin_right, y)
    y -= line_height + 4
    
    # Date and location
    data_assinatura = consent_data.get("data_assinatura", "")
    loc = consent_data.get("localidade", "")
    if loc and data_assinatura:
        date_only = data_assinatura.split(" ")[0] if " " in data_assinatura else data_assinatura
        c.setFont(font_name, font_size)
        try:
            c.drawString(margin_left, y, f"{loc}, {date_only}")
        except Exception:
            pass
        y -= line_height + 10
    
    # Signature label
    c.setFont("Helvetica-Bold", font_size)
    c.drawString(margin_left, y, "Assinatura do Cliente")
    y -= line_height
    c.setFont(font_name, font_size - 1)
    c.drawString(margin_left, y, "Titular dos Dados")
    y -= line_height
    c.setFont("Helvetica-Oblique", font_size - 2)
    c.drawString(margin_left, y, "Por favor assine conforme o seu cartao de identificacao.")
    y -= line_height + 4
    
    # Signature image
    assinatura_b64 = consent_data.get("assinatura", "")
    if assinatura_b64 and "," in assinatura_b64:
        try:
            img_data = base64.b64decode(assinatura_b64.split(",")[1])
            img_buffer = io.BytesIO(img_data)
            img_reader = ImageReader(img_buffer)
            
            img_w, img_h = img_reader.getSize()
            max_sig_width = 8 * cm
            max_sig_height = 4 * cm
            if img_w > max_sig_width:
                scale = max_sig_width / img_w
                img_w = max_sig_width
                img_h = img_h * scale
            if img_h > max_sig_height:
                scale = max_sig_height / img_h
                img_h = max_sig_height
                img_w = img_w * scale
            
            c.drawImage(img_reader, margin_left, y - max_sig_height, width=img_w, height=img_h, mask='auto')
        except Exception as e:
            logger.warning(f"Não foi possível incluir assinatura no PDF Minuta: {e}")
    
    c.save()
    return buffer.getvalue()


async def _send_client_confirmation_email(
    client_email: str,
    client_name: str,
    rgpd_pdf_bytes: bytes,
    minuta_pdf_bytes: bytes,
    consent_data: dict,
    process_id: str
):
    """Send confirmation email to client with 2 PDF attachments."""
    from services.email_service import send_email
    
    # Build attachments
    attachments = []
    safe_name = client_name.replace(' ', '_')
    
    if rgpd_pdf_bytes:
        attachments.append({
            "filename": f"RGPD_{safe_name}.pdf",
            "content_bytes": rgpd_pdf_bytes,
            "content_type": "application/pdf"
        })
    
    if minuta_pdf_bytes:
        attachments.append({
            "filename": f"Minuta_Exclusividade_{safe_name}.pdf",
            "content_bytes": minuta_pdf_bytes,
            "content_type": "application/pdf"
        })
    
    # Email body text (exactly as specified by the user)
    body_text = f"""Estimado(a) {client_name},

Gostaríamos de confirmar que recebemos a sua assinatura do Regulamento Geral sobre a Proteção de Dados (RGPD). Agradecemos a sua colaboração no cumprimento deste importante requisito legal.

A sua confiança e segurança são fundamentais para nós. Assim, gostaríamos de assegurar que os seus dados pessoais estão a ser tratados de acordo com as diretrizes estabelecidas no RGPD. Esta assinatura permite-nos continuar a oferecer-lhe os nossos serviços de forma segura e transparente.

Caso tenha alguma dúvida ou necessite de mais informações, não hesite em contactar-nos.

Mais uma vez, obrigado(a) pela sua colaboração."""
    
    # HTML body
    body_html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
</head>
<body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
    <p>Estimado(a) <strong>{client_name}</strong>,</p>
    
    <p>Gostaríamos de confirmar que recebemos a sua assinatura do <strong>Regulamento Geral sobre a Proteção de Dados (RGPD)</strong>. Agradecemos a sua colaboração no cumprimento deste importante requisito legal.</p>
    
    <p>A sua confiança e segurança são fundamentais para nós. Assim, gostaríamos de assegurar que os seus dados pessoais estão a ser tratados de acordo com as diretrizes estabelecidas no RGPD. Esta assinatura permite-nos continuar a oferecer-lhe os nossos serviços de forma segura e transparente.</p>
    
    <p>Caso tenha alguma dúvida ou necessite de mais informações, não hesite em contactar-nos.</p>
    
    <p>Mais uma vez, obrigado(a) pela sua colaboração.</p>
</body>
</html>"""
    
    # Append user's email signature if configured
    # Prioridade: users.email_signature (global) > UCR.signature (empresa default) > UCR.signature (qualquer empresa)
    try:
        sender_user = await db.users.find_one(
            {"email": consent_data.get("created_by_email", "")},
            {"email_signature": 1, "company": 1, "id": 1, "_id": 0}
        )
        sig = sender_user.get("email_signature") if sender_user else None
        # Fallback 1: UCR da empresa default
        if not sig and sender_user:
            default_company = sender_user.get("company")
            if default_company:
                ucr = await db.user_company_roles.find_one(
                    {"user_id": sender_user.get("id"), "company_id": default_company},
                    {"signature": 1, "_id": 0}
                )
                if ucr and ucr.get("signature"):
                    sig = ucr["signature"]
        # Fallback 2: UCR de qualquer empresa
        if not sig and sender_user:
            ucr_any = await db.user_company_roles.find_one(
                {"user_id": sender_user.get("id"), "signature": {"$exists": True, "$ne": None, "$ne": ""}},
                {"signature": 1, "_id": 0}
            )
            if ucr_any and ucr_any.get("signature"):
                sig = ucr_any["signature"]
        if sig:
            body_html += f"<br/><hr/>{sig}"
    except Exception:
        pass
    
    # Pacote FR-4 — usar a conta SMTP da Empresa real do processo, se
    # configurada (ver `send_rgpd_email` para detalhes da prioridade).
    company = await _resolve_rgpd_company(process_id=process_id)
    account_override = _build_company_smtp_account(company)

    result = await send_email(
        account_name="precision",
        to_emails=[client_email],
        subject="Confirmação de Assinatura RGPD - Cópia dos Documentos",
        body=body_text,
        body_html=body_html,
        attachments=attachments,
        force_system=True,
        created_by="rgpd_system",
        system_purpose="RGPD",
        account_override=account_override,
    )
    
    if result.get("success"):
        logger.info(f"Email de confirmação enviado para {client_email} com {len(attachments)} anexo(s)")
        # Audit trail — regista o envio do email no histórico do processo
        try:
            await log_history(
                process_id=process_id,
                user={"id": "rgpd_system", "name": "Sistema"},
                action="Email de confirmação com cópia do RGPD enviado ao cliente com sucesso."
            )
        except Exception as e:
            logger.warning(f"Erro ao registar audit trail do email RGPD: {e}")
    else:
        logger.error(f"Falha ao enviar email de confirmação para {client_email}: {result.get('error')}")


# Keep backward compatibility with old function
async def _save_signed_rgpd_pdf(process_id, rgpd_request, consent_data):
    """Legacy function - now delegates to new PDF generation."""
    rgpd_pdf_bytes = await _generate_rgpd_pdf_bytes(process_id, rgpd_request, consent_data)
    if rgpd_pdf_bytes:
        client_name = consent_data.get("nome", rgpd_request.get("client_name", "Cliente"))
        await _upload_pdf_to_s3(
            process_id, client_name, rgpd_pdf_bytes,
            f"RGPD_{client_name.replace(' ', '_')}_{rgpd_request['id'][:8]}.pdf", "RGPD"
        )

"""
====================================================================
SERVIÇO DE EMAIL - CREDITOIMO
====================================================================
Serviço para enviar e receber emails via SMTP/IMAP.
Suporta dois servidores: Precision Crédito e Power Real Estate.
====================================================================
"""

import logging
import os
import email
import traceback
import imaplib
import smtplib
import ssl
import asyncio
from concurrent.futures import ThreadPoolExecutor
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.application import MIMEApplication
from email import encoders as email_encoders
import mimetypes
from email.header import decode_header
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone, timedelta
import uuid
import re

from database import db

logger = logging.getLogger(__name__)

# Thread pool para operações IMAP/SMTP bloqueantes
_email_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="email_")


class EmailAccount:
    """Configuração de uma conta de email."""
    def __init__(self, name: str, imap_server: str, imap_port: int, 
                 smtp_server: str, smtp_port: int, email: str, password: str):
        self.name = name
        self.imap_server = imap_server
        self.imap_port = imap_port
        self.smtp_server = smtp_server
        self.smtp_port = smtp_port
        self.email = email
        self.password = password


# Configuração das contas de email
def get_email_accounts() -> List[EmailAccount]:
    """Obter configuração das contas de email do ambiente (variáveis de ambiente)."""
    accounts = []
    
    # Precision Crédito
    if os.environ.get("PRECISION_EMAIL"):
        accounts.append(EmailAccount(
            name="precision",
            imap_server=os.environ.get("PRECISION_IMAP_SERVER", "mail.precisioncredito.pt"),
            imap_port=int(os.environ.get("PRECISION_IMAP_PORT", 993)),
            smtp_server=os.environ.get("PRECISION_SMTP_SERVER", "mail.precisioncredito.pt"),
            smtp_port=int(os.environ.get("PRECISION_SMTP_PORT", 465)),
            email=os.environ.get("PRECISION_EMAIL"),
            password=os.environ.get("PRECISION_PASSWORD")
        ))
    
    # Power Real Estate
    if os.environ.get("POWER_EMAIL"):
        accounts.append(EmailAccount(
            name="power",
            imap_server=os.environ.get("POWER_IMAP_SERVER", "webmail2.hcpro.pt"),
            imap_port=int(os.environ.get("POWER_IMAP_PORT", 993)),
            smtp_server=os.environ.get("POWER_SMTP_SERVER", "webmail2.hcpro.pt"),
            smtp_port=int(os.environ.get("POWER_SMTP_PORT", 465)),
            email=os.environ.get("POWER_EMAIL"),
            password=os.environ.get("POWER_PASSWORD")
        ))
    
    return accounts


async def get_email_accounts_async() -> List[EmailAccount]:
    """
    Obter configuração das contas de email.
    Busca primeiro nas variáveis de ambiente, depois na base de dados (system_config).
    Suporta até 2 contas: Power Real Estate e Precision Crédito.
    """
    accounts = get_email_accounts()
    
    # Se já encontrou nas variáveis de ambiente, retornar
    if accounts:
        return accounts
    
    # Tentar buscar da base de dados (system_config)
    try:
        config = await db.system_config.find_one({"_id": "main"}, {"_id": 0})
        if config and config.get("email"):
            email_config = config["email"]
            provider = email_config.get("provider", "none")
            
            # Só criar contas se provider for SMTP
            if provider == "smtp":
                # === CONTA 1: Power Real Estate ===
                # Prioridade: campos IMAP dedicados > campos SMTP
                smtp_user = email_config.get("imap_user") or email_config.get("smtp_user")
                smtp_password = email_config.get("imap_password") or email_config.get("smtp_password")
                smtp_server = email_config.get("smtp_server")
                imap_server = email_config.get("imap_server")
                
                if smtp_user and smtp_password and (smtp_server or imap_server):
                    accounts.append(EmailAccount(
                        name="power",
                        imap_server=imap_server or smtp_server,
                        imap_port=int(email_config.get("imap_port", 993)),
                        smtp_server=smtp_server or imap_server,
                        smtp_port=int(email_config.get("smtp_port", 465)),
                        email=smtp_user,
                        password=smtp_password
                    ))
                    logger.info(f"Conta Power carregada da DB: {smtp_user}")
                else:
                    logger.warning(f"Conta Power incompleta: user={bool(smtp_user)}, pass={bool(smtp_password)}, server={bool(smtp_server or imap_server)}")
                
                # === CONTA 2: Precision Crédito ===
                smtp_user_2 = email_config.get("imap_user_2") or email_config.get("smtp_user_2")
                smtp_password_2 = email_config.get("imap_password_2") or email_config.get("smtp_password_2")
                smtp_server_2 = email_config.get("smtp_server_2")
                imap_server_2 = email_config.get("imap_server_2")
                
                if smtp_user_2 and smtp_password_2 and (smtp_server_2 or imap_server_2):
                    accounts.append(EmailAccount(
                        name="precision",
                        imap_server=imap_server_2 or smtp_server_2,
                        imap_port=int(email_config.get("imap_port_2", 993)),
                        smtp_server=smtp_server_2 or imap_server_2,
                        smtp_port=int(email_config.get("smtp_port_2", 465)),
                        email=smtp_user_2,
                        password=smtp_password_2
                    ))
                    logger.info(f"Conta Precision carregada da DB: {smtp_user_2}")
                else:
                    logger.warning(f"Conta Precision incompleta: user={bool(smtp_user_2)}, pass={bool(smtp_password_2)}, server={bool(smtp_server_2 or imap_server_2)}")
                    
    except Exception as e:
        logger.warning(f"Erro ao carregar configuração de email da DB: {e}")
    
    return accounts


def decode_email_header(header: str) -> str:
    """Descodificar header de email."""
    if not header:
        return ""
    decoded_parts = decode_header(header)
    result = []
    for content, charset in decoded_parts:
        if isinstance(content, bytes):
            try:
                result.append(content.decode(charset or 'utf-8', errors='replace'))
            except:
                result.append(content.decode('utf-8', errors='replace'))
        else:
            result.append(content)
    return ' '.join(result)


def extract_email_address(header: str) -> str:
    """Extrair endereço de email de um header."""
    if not header:
        return ""
    # Procurar padrão <email@domain.com>
    match = re.search(r'<([^>]+)>', header)
    if match:
        return match.group(1).lower()
    # Se não encontrar, devolver o header limpo
    return header.strip().lower()


def get_email_body_with_embedded_images(msg) -> tuple:
    """
    Extrair corpo do email (texto e HTML) com suporte a imagens embutidas (cid:).
    Converte referências cid: para data URLs base64.
    
    Returns:
        tuple: (body_text, body_html, embedded_images_dict)
    """
    import base64
    
    body_text = ""
    body_html = ""
    embedded_images = {}  # cid -> base64 data URL
    
    if msg.is_multipart():
        # Primeiro pass: extrair imagens embutidas
        for part in msg.walk():
            content_type = part.get_content_type()
            content_id = part.get("Content-ID")
            
            # Verificar se é uma imagem embutida
            if content_type.startswith("image/") and content_id:
                try:
                    payload = part.get_payload(decode=True)
                    if payload:
                        # Remover < > do Content-ID
                        cid = content_id.strip("<>")
                        # Converter para base64
                        b64_data = base64.b64encode(payload).decode('utf-8')
                        embedded_images[cid] = f"data:{content_type};base64,{b64_data}"
                except Exception as e:
                    logger.warning(f"Erro ao extrair imagem embutida: {e}")
        
        # Segundo pass: extrair corpo do email
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition"))
            
            if "attachment" not in content_disposition:
                try:
                    payload = part.get_payload(decode=True)
                    if payload:
                        charset = part.get_content_charset() or 'utf-8'
                        text = payload.decode(charset, errors='replace')
                        if content_type == "text/plain":
                            body_text = text
                        elif content_type == "text/html":
                            body_html = text
                except Exception as e:
                    logger.warning(f"Erro ao extrair corpo: {e}")
    else:
        try:
            payload = msg.get_payload(decode=True)
            if payload:
                charset = msg.get_content_charset() or 'utf-8'
                body_text = payload.decode(charset, errors='replace')
        except Exception as e:
            logger.warning(f"Erro ao extrair corpo simples: {e}")
    
    # Substituir referências cid: no HTML por data URLs
    if body_html and embedded_images:
        for cid, data_url in embedded_images.items():
            # Substituir várias formas de referência cid:
            body_html = body_html.replace(f'cid:{cid}', data_url)
            body_html = body_html.replace(f'CID:{cid}', data_url)
            body_html = body_html.replace(f'"cid:{cid}"', f'"{data_url}"')
            body_html = body_html.replace(f"'cid:{cid}'", f"'{data_url}'")
    
    return body_text, body_html, embedded_images


def _extract_email_bytes_from_fetch(fetch_result) -> Optional[bytes]:
    """
    Extrair bytes de um email de forma segura a partir do resultado de mail.fetch().
    
    O formato do resultado varia entre servidores IMAP:
    - ('OK', [(b'1 (RFC822 {size}', b'...email...'), b')'])
    - ('OK', [(b'1 (RFC822 {size}', email_bytes)])
    
    Returns:
        bytes do email ou None se não conseguir extrair
    """
    if not fetch_result or len(fetch_result) < 2:
        return None
    
    msg_data = fetch_result[1]
    if not msg_data:
        return None
    
    if isinstance(msg_data, list) and len(msg_data) > 0:
        item = msg_data[0]
        if isinstance(item, tuple) and len(item) >= 2:
            return item[1]
        elif isinstance(item, bytes):
            return item
    
    return None


def _fetch_and_parse_email(mail, num):
    """
    Buscar e parsear um email de forma segura.
    
    Returns:
        tuple: (msg, msg_id) ou (None, None) se falhar
    """
    fetch_result = mail.fetch(num, "(RFC822)")
    email_bytes = _extract_email_bytes_from_fetch(fetch_result)
    if not email_bytes:
        return None, None
    
    msg = email.message_from_bytes(email_bytes)
    msg_id = msg.get("Message-ID", "")
    if not msg_id:
        return None, None
    
    return msg, msg_id



def _safe_search_result(mail_result):
    """Extrair message_numbers de mail.search() de forma segura."""
    if not mail_result or len(mail_result) < 2:
        return [b'']
    return mail_result[1]


def get_email_body(msg) -> tuple:
    """Extrair corpo do email (texto e HTML) com suporte a imagens embutidas."""
    body_text, body_html, _ = get_email_body_with_embedded_images(msg)
    return body_text, body_html



async def sync_emails_for_process(process_id: str, days: int = 30, user_email: str = None) -> Dict[str, Any]:
    """
    Sincronizar emails para um processo específico.
    
    DEPRECATED: A associação de emails a processos é agora feita automaticamente por:
    1. Smart Threading (herança de process_id via In-Reply-To / References)
    2. Tag Mágica [Proc-{id}] no assunto
    3. Associação manual pelo utilizador (botão Ligar a Processo)
    
    Esta função é mantida por compatibilidade mas não faz mais IMAP search.
    """
    logger.info(f"[sync_emails_for_process] Chamada obsoleta para processo {process_id}. "
                f"A associação é agora automática via Smart Threading + Tag Mágica.")
    return {
        "success": True,
        "message": "Associação de emails agora é automática via Smart Threading e Tag Mágica. Use a sincronização global do Webmail.",
        "synced": 0,
        "method": "smart_threading"
    }

async def send_email(
    account_name: str,
    to_emails: List[str],
    subject: str,
    body: str,
    body_html: Optional[str] = None,
    cc_emails: Optional[List[str]] = None,
    bcc_emails: Optional[List[str]] = None,
    process_id: Optional[str] = None,
    created_by: Optional[str] = None,
    attachments: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """
    Envia um email através de uma das contas SMTP configuradas (Precision Crédito
    ou Power Real Estate) e regista automaticamente a comunicação no histórico
    do processo.

    Esta função é o ponto central de saída de emails do CRM. É utilizada por
    todos os módulos que necessitam de enviar comunicações (RGPD, pedidos de
    documentos, rascunhos automáticos, notificações). O registo automático no
    histórico do processo garante auditoria completa de todas as comunicações
    enviadas — requisito legal para intermediários de crédito (BdP).

    Se a conta solicitada não estiver configurada, a função tenta usar a
    primeira conta disponível como fallback. O envio é feito via SMTP_SSL
    com TLS para garantir a confidencialidade das comunicações.

    Args:
        account_name: Nome da conta de email ("precision" ou "power").
        to_emails: Lista de endereços de email dos destinatários.
        subject: Assunto do email.
        body: Corpo do email em texto simples (obrigatório).
        body_html: Corpo do email em HTML (opcional — se fornecido, o email
            é enviado como multipart/alternative).
        cc_emails: Lista de endereços para envio em cópia (CC).
        bcc_emails: Lista de endereços para envio em cópia oculta (BCC).
        process_id: ID do processo para registo no histórico. Se fornecido,
            o email é guardado na coleção ``emails`` da BD.
        created_by: Email ou ID do utilizador que originou o envio.
        attachments: Lista de anexos, cada um com:
            - filename (str): Nome do ficheiro.
            - content_bytes (bytes): Conteúdo binário.
            - content_type (str): Tipo MIME (ex: "application/pdf").

    Returns:
        dict: Resultado da operação:
            - success (bool): True se o email foi enviado com sucesso.
            - account (str): Nome da conta utilizada (se sucesso).
            - error (str): Mensagem de erro (se falha).

    Raises:
        smtplib.SMTPException: Se a autenticação ou o envio SMTP falharem.
    """
    accounts = get_email_accounts()
    account = next((a for a in accounts if a.name == account_name), None)
    
    # Se a conta pedida é "personal", ir diretamente para a config do utilizador
    # sem nunca cair nas contas globais (isolamento de remetente)
    if account_name == "personal" and created_by:
        from services.encryption import encryption_service
        user = await db.users.find_one(
            {"id": created_by},
            {"_id": 0, "email_config": 1}
        )
        if user and user.get("email_config", {}).get("is_configured"):
            cfg = user["email_config"]
            encrypted_password = cfg.get("encrypted_password", "")
            if encrypted_password:
                try:
                    password = encryption_service.decrypt(encrypted_password)
                    account = EmailAccount(
                        name="personal",
                        imap_server=cfg.get("smtp_server", ""),
                        imap_port=int(cfg.get("smtp_port", 465)),
                        smtp_server=cfg.get("smtp_server", ""),
                        smtp_port=int(cfg.get("smtp_port", 465)),
                        email=cfg.get("email_address", ""),
                        password=password,
                    )
                    logger.info(f"[Send Email] Conta pessoal do utilizador {created_by}: {cfg.get('email_address', '')}")
                except Exception as e:
                    logger.warning(f"[Send Email] Erro ao desencriptar password pessoal: {e}")
    
    if not account:
        # Usar primeira conta disponível
        if accounts:
            account = accounts[0]
        else:
            # If no global account matches, try user's personal email config
            if created_by:
                from services.encryption import encryption_service
                user = await db.users.find_one(
                    {"id": created_by},
                    {"_id": 0, "email_config": 1}
                )
                if user and user.get("email_config", {}).get("is_configured"):
                    cfg = user["email_config"]
                    encrypted_password = cfg.get("encrypted_password", "")
                    if encrypted_password:
                        try:
                            password = encryption_service.decrypt(encrypted_password)
                            account = EmailAccount(
                                name="personal",
                                imap_server=cfg.get("smtp_server", ""),
                                imap_port=int(cfg.get("smtp_port", 465)),
                                smtp_server=cfg.get("smtp_server", ""),
                                smtp_port=int(cfg.get("smtp_port", 465)),
                                email=cfg.get("email_address", ""),
                                password=password,
                            )
                            logger.info(f"[Send Email] Usando conta pessoal do utilizador {created_by}: {cfg.get('email_address', '')}")
                        except Exception as e:
                            logger.warning(f"[Send Email] Erro ao desencriptar password pessoal: {e}")
            if not account:
                return {"success": False, "error": "Nenhuma conta de email configurada"}
    
    try:
        # === TAG MÁGICA: Injetar [Proc-{id}] no assunto ===
        # Se o email está associado a um processo e o assunto ainda não tem a tag
        if process_id:
            tag = f"[Proc-{process_id}]"
            if tag not in subject:
                subject = f"{subject} {tag}"
                logger.info(f"[Tag Mágica] Injetada tag {tag} no assunto do email")
        
        has_attachments = attachments and len(attachments) > 0
        
        if has_attachments:
            # MIMEMultipart("mixed") permite corpo + anexos
            msg = MIMEMultipart("mixed")
            # Sub-mensagem para corpo (alternative = plain + html)
            body_part = MIMEMultipart("alternative")
            body_part.attach(MIMEText(body, "plain", "utf-8"))
            if body_html:
                body_part.attach(MIMEText(body_html, "html", "utf-8"))
            msg.attach(body_part)
            
            # Adicionar anexos
            for att in attachments:
                filename = att.get("filename", "documento")
                content_bytes = att.get("content_bytes")
                content_type = att.get("content_type") or mimetypes.guess_type(filename)[0] or "application/octet-stream"
                
                if not content_bytes:
                    logger.warning(f"Anexo sem conteúdo: {filename}")
                    continue
                
                # Se for PDF, usar MIMEApplication; senão MIMEBase
                maintype, subtype = content_type.split("/", 1) if "/" in content_type else ("application", "octet-stream")
                
                if maintype == "application":
                    att_part = MIMEApplication(content_bytes, _subtype=subtype)
                else:
                    att_part = MIMEBase(maintype, subtype)
                    att_part.set_payload(content_bytes)
                    email_encoders.encode_base64(att_part)
                
                att_part.add_header("Content-Disposition", "attachment", filename=filename)
                msg.attach(att_part)
                logger.info(f"Anexo adicionado: {filename} ({len(content_bytes)} bytes, {content_type})")
        else:
            # Sem anexos — usar "alternative" (plain + html)
            msg = MIMEMultipart("alternative")
            msg.attach(MIMEText(body, "plain", "utf-8"))
            if body_html:
                msg.attach(MIMEText(body_html, "html", "utf-8"))
        
        msg["Subject"] = subject
        msg["From"] = account.email
        msg["To"] = ", ".join(to_emails)
        
        if cc_emails:
            msg["Cc"] = ", ".join(cc_emails)
        
        # Enviar
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(account.smtp_server, account.smtp_port, context=context) as server:
            server.login(account.email, account.password)
            
            all_recipients = to_emails + (cc_emails or []) + (bcc_emails or [])
            server.sendmail(account.email, all_recipients, msg.as_string())
        
        logger.info(f"Email enviado via {account.name} para {to_emails} ({len(attachments or [])} anexos)")
        
        # Guardar no histórico
        attachment_records = []
        if attachments:
            for att in attachments:
                attachment_records.append({
                    "filename": att.get("filename", "documento"),
                    "content_type": att.get("content_type", "application/octet-stream"),
                    "size": len(att.get("content_bytes", b""))
                })
        
        if process_id:
            email_doc = {
                "id": str(uuid.uuid4()),
                "process_id": process_id,
                "direction": "sent",
                "from_email": account.email,
                "to_emails": to_emails,
                "cc_emails": cc_emails or [],
                "bcc_emails": bcc_emails or [],
                "subject": subject,
                "body": body,
                "body_html": body_html,
                "attachments": attachment_records,
                "status": "sent",
                "sent_at": datetime.now(timezone.utc).isoformat(),
                "created_at": datetime.now(timezone.utc).isoformat(),
                "created_by": created_by,
                "notes": f"Enviado via {account.name}" + (f" com {len(attachment_records)} anexo(s)" if attachment_records else ""),
                "synced": False,
                "account": account.name
            }
            await db.emails.insert_one(email_doc)
        
        return {"success": True, "account": account.name}
        
    except Exception as e:
        logger.error(f"Erro ao enviar email via {account.name}: {e}")
        return {"success": False, "error": str(e)}


async def test_email_connection(account_name: str = None) -> Dict[str, Any]:
    """Testar ligação com as contas de email."""
    accounts = await get_email_accounts_async()
    
    if account_name:
        accounts = [a for a in accounts if a.name == account_name]
    
    if not accounts:
        return {"error": "Nenhuma conta de email configurada"}
    
    results = {}
    
    for account in accounts:
        result = {"imap": False, "smtp": False, "error": None}
        
        # Garantir que as credenciais são strings UTF-8
        email = account.email if account.email else ""
        password = account.password if account.password else ""
        
        # Testar IMAP
        try:
            context = ssl.create_default_context()
            mail = imaplib.IMAP4_SSL(account.imap_server, account.imap_port, ssl_context=context)
            # Usar encode UTF-8 para suportar caracteres especiais na password
            mail.login(email, password)
            mail.logout()
            result["imap"] = True
        except Exception as e:
            error_msg = str(e)
            # Traduzir erros comuns
            if "authentication failed" in error_msg.lower():
                error_msg = "Autenticação falhou - verifique email/password"
            elif "connection refused" in error_msg.lower():
                error_msg = "Conexão recusada - verifique servidor/porta"
            result["error"] = f"IMAP: {error_msg}"
        
        # Testar SMTP
        try:
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(account.smtp_server, account.smtp_port, context=context) as server:
                # SMTP.login aceita strings UTF-8 directamente
                server.login(email, password)
            result["smtp"] = True
        except Exception as e:
            error_msg = str(e)
            if "authentication" in error_msg.lower():
                error_msg = "Autenticação falhou - verifique email/password"
            elif "connection refused" in error_msg.lower():
                error_msg = "Conexão recusada - verifique servidor/porta"
            
            if result["error"]:
                result["error"] += f"; SMTP: {error_msg}"
            else:
                result["error"] = f"SMTP: {error_msg}"
        
        results[account.name] = result
    
    return results


# =====================================================================
# SYNC GLOBAL PARA WEBMAIL (sem filtro de processo)
# =====================================================================

def _fetch_all_from_folder_sync(
    account: EmailAccount,
    folder: str = "INBOX",
    since_days: int = 7,
    max_emails: int = 100
) -> Dict[str, Any]:
    """
    Buscar TODOS os emails de uma pasta IMAP (sem filtro de processo).
    Versão síncrona para execução em thread.
    
    Returns:
        Dict with 'emails' (list) and 'connection_error' (str or None).
    """
    emails_found = []
    connection_error = None
    
    try:
        context = ssl.create_default_context()
        mail = imaplib.IMAP4_SSL(account.imap_server, account.imap_port, ssl_context=context)
        mail.login(account.email, account.password)
        
        since_date = (datetime.now() - timedelta(days=since_days)).strftime("%d-%b-%Y")
        logger.info(f"[Webmail Sync] Buscando emails em {folder} ({account.name}) desde {since_date}")
        
        result, data = mail.select(folder)
        if result != 'OK':
            logger.debug(f"[Webmail Sync] Pasta não encontrada: {folder} ({result})")
            mail.logout()
            return emails_found
        
        message_numbers = _safe_search_result(mail.search(None, f'(SINCE {since_date})'))
        nums = message_numbers[0].split()
        
        # Limitar aos mais recentes (do fim para o início)
        if len(nums) > max_emails:
            nums = nums[-max_emails:]
        
        logger.info(f"[Webmail Sync] {len(nums)} emails para processar em {folder}")
        logger.info(f"[Webmail Sync] Code version: 086c502-fixed")
        
        for num in nums:
            try:
                fetch_result = mail.fetch(num, "(RFC822)")
                email_bytes = _extract_email_bytes_from_fetch(fetch_result)
                if not email_bytes:
                    continue
                
                msg = email.message_from_bytes(email_bytes)
                
                msg_id = msg.get("Message-ID", "")
                if not msg_id:
                    continue
                
                from_email = extract_email_address(msg.get("From", ""))
                to_emails = [extract_email_address(e) for e in (msg.get("To", "")).split(",") if e.strip()]
                cc_emails = [extract_email_address(e) for e in (msg.get("Cc", "") or "").split(",") if e.strip()]
                subject = decode_email_header(msg.get("Subject", ""))
                date_str = msg.get("Date", "")
                body_text, body_html, _ = get_email_body_with_embedded_images(msg)
                
                # === SMART THREADING: Extrair cabeçalhos de rastreio ===
                in_reply_to = msg.get("In-Reply-To", "")
                if in_reply_to:
                    in_reply_to = in_reply_to.strip()
                
                references_raw = msg.get("References", "")
                references_list = []
                if references_raw:
                    # References header contém Message-IDs separados por espaços
                    references_list = [ref.strip() for ref in references_raw.split() if ref.strip()]
                
                direction = "sent" if from_email.lower() == account.email.lower() else "received"
                
                email_date = None
                if date_str:
                    try:
                        email_date = email.utils.parsedate_to_datetime(date_str)
                    except Exception:
                        email_date = datetime.now()
                
                # Extrair anexos
                attachments = []
                for part in msg.walk():
                    content_disposition = str(part.get("Content-Disposition", ""))
                    if "attachment" in content_disposition:
                        filename = part.get_filename() or "anexo"
                        filename = decode_email_header(filename)
                        size = len(part.get_payload(decode=True) or b"")
                        attachments.append({
                            "filename": filename,
                            "content_type": part.get_content_type(),
                            "size": size
                        })
                
                emails_found.append({
                    "message_id": msg_id,
                    "from_email": from_email,
                    "to_emails": to_emails,
                    "cc_emails": cc_emails,
                    "subject": subject,
                    "body": body_text or "",
                    "body_html": body_html or "",
                    "attachments": attachments,
                    "date": email_date.isoformat() if email_date else datetime.now().isoformat(),
                    "direction": direction,
                    "source": "webmail_sync",
                    "account": account.name,
                    "in_reply_to": in_reply_to or None,
                    "references": references_list,
                })
                
            except Exception as e:
                logger.warning(f"[Webmail Sync] Erro ao processar email: {e}")
                logger.warning(f"[Webmail Sync] Traceback: {traceback.format_exc()}")
                continue
        
        mail.logout()
        logger.info(f"[Webmail Sync] {len(emails_found)} emails extraídos de {folder} ({account.name})")
        
    except Exception as e:
        error_msg = str(e)
        logger.error(f"[Webmail Sync] Erro ao conectar IMAP {account.name}: {error_msg}")
        # Detectar erros de autenticação para mensagem mais clara
        if "login failed" in error_msg.lower() or "authentication failed" in error_msg.lower() or "invalid username or password" in error_msg.lower():
            connection_error = f"Autenticação IMAP falhou para {account.email} — verifique email/password nas Configurações do Perfil"
        elif "connection refused" in error_msg.lower() or "timed out" in error_msg.lower():
            connection_error = f"Ligação IMAP falhou para {account.email} — servidor inatingível ({account.imap_server}:{account.imap_port})"
        else:
            connection_error = f"Erro IMAP para {account.email}: {error_msg}"
    
    return {"emails": emails_found, "connection_error": connection_error}


async def sync_webmail_emails(
    account_name: str = None,
    days: int = 7,
    max_emails: int = 100
) -> Dict[str, Any]:
    """
    Sincronizar TODOS os emails recentes do IMAP para o webmail.
    Sem filtro de processo — guarda todos os emails recebidos e enviados.
    
    Args:
        account_name: "precision" ou "power" (None = todas as contas)
        days: Dias para sincronizar (default 7)
        max_emails: Máximo de emails por pasta (default 100)
    
    Returns:
        Dict com resultado da sincronização
    """
    accounts = await get_email_accounts_async()
    if not accounts:
        return {"success": False, "error": "Nenhuma conta de email configurada"}
    
    if account_name:
        accounts = [a for a in accounts if a.name == account_name]
        if not accounts:
            return {"success": False, "error": f"Conta '{account_name}' não encontrada"}
    
    total_synced = 0
    total_duplicates = 0
    total_errors = 0
    results = {}
    
    for account in accounts:
        try:
            all_emails = []
            
            # Buscar da INBOX
            loop = asyncio.get_event_loop()
            inbox_result = await loop.run_in_executor(
                _email_executor,
                lambda: _fetch_all_from_folder_sync(account, "INBOX", days, max_emails)
            )
            
            # Verificar erro de conexão IMAP
            if inbox_result.get("connection_error"):
                logger.warning(f"[Webmail Sync] Erro IMAP para {account.name}: {inbox_result['connection_error']}")
                results[account.name] = {"error": inbox_result["connection_error"], "synced": 0, "duplicates": 0, "total_fetched": 0}
                total_errors += 1
                continue
            
            all_emails.extend(inbox_result.get("emails", []))
            
            # Buscar da pasta de Enviados (tentar vários nomes)
            for sent_folder in ["Sent", "INBOX.Sent", "Sent Items", "Enviados", "INBOX.Enviados"]:
                try:
                    sent_result = await loop.run_in_executor(
                        _email_executor,
                        lambda f=sent_folder: _fetch_all_from_folder_sync(account, f, days, max_emails)
                    )
                    sent_list = sent_result.get("emails", []) if sent_result else []
                    if sent_list:
                        all_emails.extend(sent_list)
                        break
                except Exception:
                    continue
            
            # Guardar emails na DB (deduplicação por message_id + account)
            synced = 0
            duplicates = 0
            
            for em in all_emails:
                try:
                    msg_id = em.get("message_id", "")
                    if not msg_id:
                        continue
                    
                    # Verificar se já existe
                    existing = await db.emails.find_one({
                        "message_id": msg_id,
                        "account": account.name
                    })
                    
                    if existing:
                        duplicates += 1
                        continue
                    
                    # Parsear data
                    sent_at = em.get("date")
                    try:
                        if sent_at:
                            sent_at = datetime.fromisoformat(sent_at.replace("Z", "+00:00")).isoformat()
                        else:
                            sent_at = datetime.now(timezone.utc).isoformat()
                    except Exception:
                        sent_at = datetime.now(timezone.utc).isoformat()
                    
                    # === SMART THREADING: Herdar process_id do email "pai" ===
                    resolved_process_id = None
                    in_reply_to = em.get("in_reply_to")
                    references = em.get("references", [])
                    
                    # Coletar todos os Message-IDs parentes para buscar
                    parent_msg_ids = []
                    if in_reply_to:
                        parent_msg_ids.append(in_reply_to)
                    if references:
                        parent_msg_ids.extend(references)
                    
                    if parent_msg_ids:
                        # Buscar qualquer email pai que tenha process_id
                        parent_email = await db.emails.find_one(
                            {
                                "message_id": {"$in": parent_msg_ids},
                                "process_id": {"$ne": None, "$exists": True},
                            },
                            {"_id": 0, "process_id": 1, "message_id": 1}
                        )
                        if parent_email:
                            resolved_process_id = parent_email["process_id"]
                            logger.info(f"[Smart Threading] Email {msg_id[:30]} herdou process_id={resolved_process_id} do pai {parent_email.get('message_id', '?')[:30]}")
                    
                    # === TAG MÁGICA: Parsear [Proc-{id}] do assunto ===
                    subject = em.get("subject", "")
                    if not resolved_process_id and subject:
                        tag_match = re.search(r'\[Proc-([^\]]+)\]', subject)
                        if tag_match:
                            tag_process_id = tag_match.group(1).strip()
                            # Validar que o processo existe
                            proc_exists = await db.processes.find_one(
                                {"id": tag_process_id},
                                {"_id": 0, "id": 1}
                            )
                            if proc_exists:
                                resolved_process_id = tag_process_id
                                logger.info(f"[Tag Mágica] Email {msg_id[:30]} associado ao processo {tag_process_id} via tag no assunto")
                    
                    email_doc = {
                        "id": str(uuid.uuid4()),
                        "process_id": resolved_process_id,
                        "direction": em.get("direction", "received"),
                        "from_email": em.get("from_email", ""),
                        "to_emails": [str(e) for e in (em.get("to_emails") or []) if e],
                        "cc_emails": [str(e) for e in (em.get("cc_emails") or []) if e],
                        "bcc_emails": [],
                        "subject": subject,
                        "body": em.get("body", ""),
                        "body_html": em.get("body_html", ""),
                        "attachments": em.get("attachments", []),
                        "status": "synced",
                        "sent_at": sent_at,
                        "created_at": datetime.now(timezone.utc).isoformat(),
                        "created_by": None,
                        "notes": f"Webmail sync - {account.name}",
                        "synced": True,
                        "account": account.name,
                        "message_id": msg_id,
                        "is_read": em.get("direction") == "sent",
                        "is_starred": False,
                        "is_archived": False,
                        "source": "webmail_sync",
                        "in_reply_to": in_reply_to or None,
                        "references": references or [],
                    }
                    
                    await db.emails.insert_one(email_doc)
                    synced += 1
                    
                except Exception as e:
                    logger.warning(f"[Webmail Sync] Erro ao guardar email: {e}")
                    total_errors += 1
            
            total_synced += synced
            total_duplicates += duplicates
            results[account.name] = {
                "synced": synced,
                "duplicates": duplicates,
                "total_fetched": len(all_emails),
            }
            
            logger.info(f"[Webmail Sync] Conta {account.name}: {synced} novos, {duplicates} duplicados")
            
        except Exception as e:
            logger.error(f"[Webmail Sync] Erro ao sincronizar conta {account.name}: {e}")
            results[account.name] = {"error": str(e)}
            total_errors += 1
    
    return {
        "success": total_errors == 0 or total_synced > 0,
        "total_synced": total_synced,
        "total_duplicates": total_duplicates,
        "total_errors": total_errors,
        "accounts": results,
    }


async def sync_user_emails(user_id: str, days: int = 7, max_emails: int = 100) -> Dict[str, Any]:
    """
    Sincronizar emails para um utilizador específico usando a sua configuração pessoal.
    
    Args:
        user_id: ID do utilizador
        days: Dias para sincronizar
        max_emails: Máximo de emails por pasta
    
    Returns:
        Dict com resultado da sincronização
    """
    from services.encryption import encryption_service
    
    user = await db.users.find_one(
        {"id": user_id},
        {"_id": 0, "email_config": 1}
    )
    
    if not user or not user.get("email_config"):
        return {"success": False, "error": "Utilizador sem configuração de email"}
    
    config = user["email_config"]
    if not config.get("is_configured"):
        return {"success": False, "error": "Configuração de email não ativa"}
    
    encrypted_password = config.get("encrypted_password", "")
    if not encrypted_password:
        return {"success": False, "error": "Password não configurada"}
    
    # Desencriptar password apenas no motor de sincronização
    password = encryption_service.decrypt(encrypted_password)
    
    # Criar EmailAccount temporária com as credenciais do utilizador
    account = EmailAccount(
        name=f"user_{user_id[:8]}",
        imap_server=config.get("imap_server", ""),
        imap_port=int(config.get("imap_port", 993)),
        smtp_server=config.get("smtp_server", ""),
        smtp_port=int(config.get("smtp_port", 465)),
        email=config.get("email_address", ""),
        password=password,
    )
    
    total_synced = 0
    total_duplicates = 0
    total_errors = 0
    
    try:
        loop = asyncio.get_event_loop()
        
        # Buscar da INBOX
        inbox_result = await loop.run_in_executor(
            _email_executor,
            lambda: _fetch_all_from_folder_sync(account, "INBOX", days, max_emails)
        )
        
        # Verificar erro de conexão IMAP
        if inbox_result.get("connection_error"):
            logger.error(f"[User Email Sync] Erro IMAP: {inbox_result['connection_error']}")
            return {
                "success": False,
                "total_synced": 0,
                "total_duplicates": 0,
                "total_errors": 1,
                "user_id": user_id,
                "error": inbox_result["connection_error"],
            }
        
        inbox_emails = inbox_result.get("emails", [])
        
        # Buscar da pasta de Enviados
        sent_emails = []
        for sent_folder in ["Sent", "INBOX.Sent", "Sent Items", "Enviados"]:
            try:
                sent_result = await loop.run_in_executor(
                    _email_executor,
                    lambda f=sent_folder: _fetch_all_from_folder_sync(account, f, days, max_emails)
                )
                sent_emails_list = sent_result.get("emails", []) if sent_result else []
                if sent_emails_list:
                    sent_emails = sent_emails_list
                    break
            except Exception:
                continue
        
        all_emails = inbox_emails + sent_emails
        
        for em in all_emails:
            try:
                msg_id = em.get("message_id", "")
                if not msg_id:
                    continue
                
                # Verificar se já existe (por message_id + user_id para isolamento)
                existing = await db.emails.find_one({
                    "message_id": msg_id,
                    "synced_for_user": user_id,
                })
                
                if existing:
                    total_duplicates += 1
                    continue
                
                # Parsear data
                sent_at = em.get("date")
                try:
                    if sent_at:
                        sent_at = datetime.fromisoformat(sent_at.replace("Z", "+00:00")).isoformat()
                    else:
                        sent_at = datetime.now(timezone.utc).isoformat()
                except Exception:
                    sent_at = datetime.now(timezone.utc).isoformat()
                
                # === SMART THREADING: Herdar process_id do email "pai" ===
                resolved_process_id = None
                in_reply_to = em.get("in_reply_to")
                references = em.get("references", [])
                
                parent_msg_ids = []
                if in_reply_to:
                    parent_msg_ids.append(in_reply_to)
                if references:
                    parent_msg_ids.extend(references)
                
                if parent_msg_ids:
                    parent_email = await db.emails.find_one(
                        {
                            "message_id": {"$in": parent_msg_ids},
                            "process_id": {"$ne": None, "$exists": True},
                        },
                        {"_id": 0, "process_id": 1, "message_id": 1}
                    )
                    if parent_email:
                        resolved_process_id = parent_email["process_id"]
                        logger.info(f"[Smart Threading] Email {msg_id[:30]} herdou process_id={resolved_process_id} do pai")
                
                # === TAG MÁGICA: Parsear [Proc-{id}] do assunto ===
                subject = em.get("subject", "")
                if not resolved_process_id and subject:
                    tag_match = re.search(r'\[Proc-([^\]]+)\]', subject)
                    if tag_match:
                        tag_process_id = tag_match.group(1).strip()
                        proc_exists = await db.processes.find_one(
                            {"id": tag_process_id},
                            {"_id": 0, "id": 1}
                        )
                        if proc_exists:
                            resolved_process_id = tag_process_id
                            logger.info(f"[Tag Mágica] Email {msg_id[:30]} associado ao processo {tag_process_id}")
                
                email_doc = {
                    "id": str(uuid.uuid4()),
                    "process_id": resolved_process_id,
                    "direction": em.get("direction", "received"),
                    "from_email": em.get("from_email", ""),
                    "to_emails": [str(e) for e in (em.get("to_emails") or []) if e],
                    "cc_emails": [str(e) for e in (em.get("cc_emails") or []) if e],
                    "bcc_emails": [],
                    "subject": subject,
                    "body": em.get("body", ""),
                    "body_html": em.get("body_html", ""),
                    "attachments": em.get("attachments", []),
                    "status": "synced",
                    "sent_at": sent_at,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "created_by": user_id,
                    "notes": f"User webmail sync - {config.get('email_address', '')}",
                    "synced": True,
                    "account": config.get("email_address", ""),
                    "synced_for_user": user_id,
                    "message_id": msg_id,
                    "is_read": em.get("direction") == "sent",
                    "is_starred": False,
                    "is_archived": False,
                    "source": "user_webmail_sync",
                    "in_reply_to": in_reply_to or None,
                    "references": references or [],
                }
                
                await db.emails.insert_one(email_doc)
                total_synced += 1
                
            except Exception as e:
                logger.warning(f"[User Email Sync] Erro ao guardar email: {e}")
                total_errors += 1
        
        logger.info(f"[User Email Sync] User {user_id}: {total_synced} novos, {total_duplicates} duplicados")
        
    except Exception as e:
        logger.error(f"[User Email Sync] Erro: {e}")
        total_errors += 1
    
    return {
        "success": total_errors == 0 or total_synced > 0,
        "total_synced": total_synced,
        "total_duplicates": total_duplicates,
        "total_errors": total_errors,
        "user_id": user_id,
    }


async def sync_all_user_emails(days: int = 7) -> Dict[str, Any]:
    """
    Sincronizar emails para TODOS os utilizadores com configuração ativa.
    Usa asyncio.gather para execução concorrente.
    
    Returns:
        Dict com resumo global da sincronização
    """
    # Query: utilizadores com email_config.is_configured == True
    users_with_config = await db.users.find(
        {"email_config.is_configured": True},
        {"_id": 0, "id": 1}
    ).to_list(200)
    
    if not users_with_config:
        return {"success": True, "message": "Nenhum utilizador com email configurado", "users_synced": 0}
    
    # Criar tasks para cada utilizador
    tasks = [
        sync_user_emails(user["id"], days=days)
        for user in users_with_config
    ]
    
    # Executar concorrentemente
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    total_synced = 0
    total_errors = 0
    user_results = {}
    
    for i, result in enumerate(results):
        user_id = users_with_config[i]["id"]
        if isinstance(result, Exception):
            logger.error(f"[All User Sync] User {user_id}: {result}")
            user_results[user_id] = {"error": str(result)}
            total_errors += 1
        else:
            user_results[user_id] = result
            total_synced += result.get("total_synced", 0)
            total_errors += result.get("total_errors", 0)
    
    return {
        "success": total_errors == 0,
        "users_synced": len(users_with_config),
        "total_synced": total_synced,
        "total_errors": total_errors,
        "users": user_results,
    }

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


async def fetch_emails_by_name(
    account: EmailAccount,
    client_name: str,
    since_days: int = 30,
    folder: str = "INBOX"
) -> List[Dict[str, Any]]:
    """
    Buscar emails do cliente de duas formas:
    1. Por nome no assunto
    2. Em subpastas que correspondam ao nome do cliente
    
    Args:
        account: Configuração da conta
        client_name: Nome do cliente para buscar
        since_days: Buscar emails dos últimos X dias
        folder: Pasta IMAP base
    
    Returns:
        Lista de emails encontrados
    """
    if not client_name or len(client_name) < 3:
        return []
    
    # Executar operação IMAP em thread separada para não bloquear o event loop
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        _email_executor,
        lambda: _fetch_emails_by_name_sync(account, client_name, since_days, folder)
    )


def _fetch_emails_by_name_sync(
    account: EmailAccount,
    client_name: str,
    since_days: int = 30,
    folder: str = "INBOX"
) -> List[Dict[str, Any]]:
    """Versão síncrona de fetch_emails_by_name para ser executada em thread."""
    emails_found = []
    search_name = client_name.strip()
    # Extrair partes do nome para matching de subpastas
    name_parts = [p.lower() for p in search_name.split() if len(p) >= 3]
    
    try:
        context = ssl.create_default_context()
        mail = imaplib.IMAP4_SSL(account.imap_server, account.imap_port, ssl_context=context)
        mail.login(account.email, account.password)
        
        logger.info(f"Buscando emails para '{search_name}' em {account.name}")
        
        seen_ids = set()
        since_date = (datetime.now() - timedelta(days=since_days)).strftime("%d-%b-%Y")
        
        # 1. Procurar em subpastas que correspondam ao nome do cliente
        list_result = mail.list()
        folders = list_result[1] if list_result and len(list_result) >= 2 else []
        matching_folders = []
        
        for folder_info in folders:
            try:
                # folder_info pode ser bytes ou str
                if isinstance(folder_info, bytes):
                    folder_str = folder_info.decode('utf-8', errors='replace')
                else:
                    folder_str = str(folder_info)
                # Extrair nome da pasta (está entre aspas ou após o último /)
                if '"' in folder_str:
                    folder_name = folder_str.split('"')[-2]
                else:
                    folder_name = folder_str.split('/')[-1]
                
                folder_name_lower = folder_name.lower()
                
                # Verificar se alguma parte do nome está no nome da pasta
                for part in name_parts:
                    if part in folder_name_lower:
                        # Extrair o nome completo da pasta para seleção
                        if '"' in folder_str:
                            full_folder = '"' + folder_str.split('"')[-2] + '"'
                        else:
                            parts = folder_str.split(' ')[-1]
                            full_folder = parts
                        matching_folders.append(full_folder)
                        logger.info(f"Pasta encontrada para '{search_name}': {full_folder}")
                        break
            except Exception:
                continue
        
        # 2. Buscar emails nas pastas encontradas
        for folder_name in matching_folders:
            try:
                result, _ = mail.select(folder_name)
                if result != 'OK':
                    continue
                
                message_numbers = _safe_search_result(mail.search(None, 'ALL'))
                
                for num in message_numbers[0].split():
                    try:
                        fetch_result = mail.fetch(num, "(RFC822)")
                        email_bytes = _extract_email_bytes_from_fetch(fetch_result)
                        if not email_bytes:
                            continue
                        msg = email.message_from_bytes(email_bytes)
                        
                        msg_id = msg.get("Message-ID", "")
                        if msg_id in seen_ids:
                            continue
                        seen_ids.add(msg_id)
                        
                        from_email = extract_email_address(msg.get("From", ""))
                        to_emails = [extract_email_address(e) for e in (msg.get("To", "")).split(",")]
                        cc_emails = [extract_email_address(e) for e in (msg.get("Cc", "") or "").split(",") if e.strip()]
                        subject = decode_email_header(msg.get("Subject", ""))
                        date_str = msg.get("Date", "")
                        body_text, body_html = get_email_body(msg)
                        
                        direction = "sent" if from_email.lower() == account.email.lower() else "received"
                        
                        email_date = None
                        if date_str:
                            try:
                                email_date = email.utils.parsedate_to_datetime(date_str)
                            except:
                                email_date = datetime.now()
                        
                        emails_found.append({
                            "message_id": msg_id,
                            "from_email": from_email,
                            "to_emails": to_emails,
                            "cc_emails": cc_emails,
                            "subject": subject,
                            "body": body_text or body_html or "",
                            "date": email_date.isoformat() if email_date else datetime.now().isoformat(),
                            "direction": direction,
                            "source": "imap_sync",
                            "account": account.name,
                            "matched_by": "client_folder"
                        })
                        
                    except Exception as e:
                        logger.warning(f"Erro ao processar email: {e}")
                        continue
                        
            except Exception as e:
                logger.warning(f"Erro ao aceder pasta {folder_name}: {e}")
        
        # 3. Também buscar na INBOX/base folder por nome no assunto
        try:
            # Garantir que seleccionamos a pasta antes de fazer SEARCH
            result, _ = mail.select(folder)
            if result != 'OK':
                logger.warning(f"Não foi possível seleccionar pasta {folder}")
            else:
                # Encoding UTF-8 para suportar caracteres especiais (ç, á, é, etc.)
                # Usar charset UTF-8 na busca IMAP
                try:
                    # Tentar busca com UTF-8
                    search_query = f'(SUBJECT "{search_name}" SINCE {since_date})'
                    message_numbers = _safe_search_result(mail.search('UTF-8', search_query.encode('utf-8')))
                except:
                    # Fallback: buscar sem charset específico (pode não encontrar alguns resultados)
                    try:
                        # Remover caracteres especiais para busca básica
                        import unicodedata
                        search_name_ascii = unicodedata.normalize('NFKD', search_name).encode('ASCII', 'ignore').decode('ASCII')
                        message_numbers = _safe_search_result(mail.search(None, f'(SUBJECT "{search_name_ascii}" SINCE {since_date})'))
                    except:
                        message_numbers = [b'']
                
                for num in message_numbers[0].split():
                    try:
                        fetch_result = mail.fetch(num, "(RFC822)")
                        email_bytes = _extract_email_bytes_from_fetch(fetch_result)
                        if not email_bytes:
                            continue
                        msg = email.message_from_bytes(email_bytes)
                        
                        msg_id = msg.get("Message-ID", "")
                        if msg_id in seen_ids:
                            continue
                        seen_ids.add(msg_id)
                        
                        from_email = extract_email_address(msg.get("From", ""))
                        to_emails = [extract_email_address(e) for e in (msg.get("To", "")).split(",")]
                        cc_emails = [extract_email_address(e) for e in (msg.get("Cc", "") or "").split(",") if e.strip()]
                        subject = decode_email_header(msg.get("Subject", ""))
                        date_str = msg.get("Date", "")
                        body_text, body_html = get_email_body(msg)
                        
                        direction = "sent" if from_email.lower() == account.email.lower() else "received"
                        
                        email_date = None
                        if date_str:
                            try:
                                email_date = email.utils.parsedate_to_datetime(date_str)
                            except:
                                email_date = datetime.now()
                        
                        emails_found.append({
                            "message_id": msg_id,
                            "from_email": from_email,
                            "to_emails": to_emails,
                            "cc_emails": cc_emails,
                            "subject": subject,
                            "body": body_text or body_html or "",
                            "date": email_date.isoformat() if email_date else datetime.now().isoformat(),
                            "direction": direction,
                            "source": "imap_sync",
                            "account": account.name,
                            "matched_by": "client_name_subject"
                        })
                        
                    except Exception as e:
                        logger.warning(f"Erro ao processar email: {e}")
                        continue
                    
        except Exception as e:
            logger.warning(f"Erro na busca por assunto: {e}")
        
        # 4. Buscar por nome no CORPO do email (emails recentes e filtrar localmente)
        try:
            # Garantir que seleccionamos a pasta antes de fazer SEARCH
            result, _ = mail.select(folder)
            if result != 'OK':
                logger.warning(f"Não foi possível seleccionar pasta {folder} para busca por corpo")
                raise Exception(f"SELECT failed: {result}")
            
            message_numbers = _safe_search_result(mail.search(None, f'(SINCE {since_date})'))
            
            # Limitar a 200 emails mais recentes para performance
            nums = message_numbers[0].split()[-200:] if message_numbers[0] else []
            
            for num in nums:
                try:
                    fetch_result = mail.fetch(num, "(RFC822)")
                    email_bytes = _extract_email_bytes_from_fetch(fetch_result)
                    if not email_bytes:
                        continue
                    msg = email.message_from_bytes(email_bytes)
                    
                    msg_id = msg.get("Message-ID", "")
                    if msg_id in seen_ids:
                        continue
                    
                    body_text, body_html = get_email_body(msg)
                    body_content = (body_text or body_html or "").lower()
                    
                    # Verificar se o nome do cliente aparece no corpo
                    name_in_body = any(part in body_content for part in name_parts)
                    if not name_in_body:
                        continue
                    
                    seen_ids.add(msg_id)
                    
                    from_email = extract_email_address(msg.get("From", ""))
                    to_emails = [extract_email_address(e) for e in (msg.get("To", "")).split(",")]
                    cc_emails = [extract_email_address(e) for e in (msg.get("Cc", "") or "").split(",") if e.strip()]
                    subject = decode_email_header(msg.get("Subject", ""))
                    date_str = msg.get("Date", "")
                    
                    direction = "sent" if from_email.lower() == account.email.lower() else "received"
                    
                    email_date = None
                    if date_str:
                        try:
                            email_date = email.utils.parsedate_to_datetime(date_str)
                        except:
                            email_date = datetime.now()
                    
                    emails_found.append({
                        "message_id": msg_id,
                        "from_email": from_email,
                        "to_emails": to_emails,
                        "cc_emails": cc_emails,
                        "subject": subject,
                        "body": body_text or body_html or "",
                        "date": email_date.isoformat() if email_date else datetime.now().isoformat(),
                        "direction": direction,
                        "source": "imap_sync",
                        "account": account.name,
                        "matched_by": "client_name_body"
                    })
                    
                except Exception:
                    continue
                    
        except Exception as e:
            logger.warning(f"Erro na busca por corpo: {e}")
        
        mail.logout()
        logger.info(f"Encontrados {len(emails_found)} emails para '{search_name}' em {account.name}")
        
    except Exception as e:
        logger.error(f"Erro ao buscar emails por nome em {account.name}: {e}")
    
    return emails_found


async def fetch_emails_from_account(
    account: EmailAccount,
    client_emails: List[str],
    since_days: int = 30,
    folder: str = "INBOX"
) -> List[Dict[str, Any]]:
    """
    Buscar emails de uma conta IMAP relacionados com clientes.
    
    Args:
        account: Configuração da conta
        client_emails: Lista de emails de clientes para filtrar
        since_days: Buscar emails dos últimos X dias
        folder: Pasta IMAP (INBOX, Sent, etc.)
    
    Returns:
        Lista de emails encontrados
    """
    # Executar operação IMAP em thread separada para não bloquear o event loop
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        _email_executor,
        lambda: _fetch_emails_from_account_sync(account, client_emails, since_days, folder)
    )


def _fetch_emails_from_account_sync(
    account: EmailAccount,
    client_emails: List[str],
    since_days: int = 30,
    folder: str = "INBOX"
) -> List[Dict[str, Any]]:
    """Versão síncrona de fetch_emails_from_account para ser executada em thread."""
    emails_found = []
    
    try:
        # Conectar ao servidor IMAP
        context = ssl.create_default_context()
        mail = imaplib.IMAP4_SSL(account.imap_server, account.imap_port, ssl_context=context)
        mail.login(account.email, account.password)
        
        logger.info(f"Conectado a {account.name} ({account.email})")
        
        # Selecionar pasta - verificar sucesso
        result, _ = mail.select(folder)
        if result != 'OK':
            logger.warning(f"Não foi possível seleccionar pasta {folder}")
            mail.logout()
            return emails_found
        
        # Calcular data de início
        since_date = (datetime.now() - timedelta(days=since_days)).strftime("%d-%b-%Y")
        
        # Buscar emails
        for client_email in client_emails:
            if not client_email:
                continue
                
            # Buscar emails de/para/cc este cliente
            for search_type in ["FROM", "TO", "CC"]:
                try:
                    # Tentar busca com UTF-8 para suportar caracteres especiais
                    try:
                        search_query = f'({search_type} "{client_email}" SINCE {since_date})'
                        message_numbers = _safe_search_result(mail.search('UTF-8', search_query.encode('utf-8')))
                    except:
                        # Fallback para busca sem charset
                        message_numbers = _safe_search_result(mail.search(None, f'({search_type} "{client_email}" SINCE {since_date})'))
                    
                    for num in message_numbers[0].split():
                        try:
                            fetch_result = mail.fetch(num, "(RFC822)")
                            email_bytes = _extract_email_bytes_from_fetch(fetch_result)
                            if not email_bytes:
                                continue
                            msg = email.message_from_bytes(email_bytes)
                            
                            # Extrair informações
                            from_email = extract_email_address(msg.get("From", ""))
                            to_emails = [extract_email_address(e) for e in (msg.get("To", "")).split(",")]
                            cc_emails = [extract_email_address(e) for e in (msg.get("Cc", "")).split(",") if e]
                            subject = decode_email_header(msg.get("Subject", ""))
                            date_str = msg.get("Date", "")
                            body_text, body_html = get_email_body(msg)
                            
                            # Determinar direcção
                            direction = "received" if from_email == client_email else "sent"
                            
                            # Parsear data
                            try:
                                from email.utils import parsedate_to_datetime
                                sent_at = parsedate_to_datetime(date_str).isoformat()
                            except:
                                sent_at = datetime.now(timezone.utc).isoformat()
                            
                            email_data = {
                                "account": account.name,
                                "direction": direction,
                                "from_email": from_email,
                                "to_emails": to_emails,
                                "cc_emails": cc_emails,
                                "subject": subject,
                                "body": body_text or body_html,
                                "body_html": body_html,
                                "sent_at": sent_at,
                                "client_email": client_email,
                                "message_id": msg.get("Message-ID", "")
                            }
                            
                            emails_found.append(email_data)
                            
                        except Exception as e:
                            logger.warning(f"Erro ao processar email {num}: {e}")
                            
                except Exception as e:
                    logger.warning(f"Erro na pesquisa {search_type} para {client_email}: {e}")
        
        mail.close()
        mail.logout()
        
        logger.info(f"Encontrados {len(emails_found)} emails em {account.name}")
        
    except Exception as e:
        logger.error(f"Erro ao conectar a {account.name}: {e}")
    
    return emails_found



async def sync_emails_for_process(process_id: str, days: int = 30, user_email: str = None) -> Dict[str, Any]:
    """
    Sincronizar emails para um processo específico.
    
    NOVAS REGRAS DE FILTRAGEM (3 regras):
    =====================================
    Regra A — Comunicação com Atores Específicos (Comercial / Cliente):
      FROM ou TO/CC cruza com email do Cliente OU Comercial Angariador.
      Se for exclusivo com o Comercial (sem Cliente no FROM/TO/CC), exige
      validação extra: Nome do Cliente ou NIF no Subject/Body.
    
    Regra B — Identificação Forte / Absoluta:
      Assunto OU Corpo contém NIF do Cliente OU Referência do Processo (#1234).
      Independentemente de quem envia/recebe.
    
    Regra C — Comunicação Geral B2B:
      Email entre contas internas da equipa e contas gerais externas.
      CONDIÇÃO OBRIGATÓRIA: Nome do Cliente OU NIF no Subject/Body.
    
    Args:
        process_id: ID do processo
        days: Número de dias para sincronizar (default 30)
        user_email: Email do utilizador logado (consultor/funcionário)
    """
    # Obter processo
    process = await db.processes.find_one({"id": process_id}, {"_id": 0})
    if not process:
        return {"success": False, "error": "Processo não encontrado"}
    
    # ===== VARIÁVEIS DO PROCESSO =====
    client_name = process.get("client_name", "")
    client_name_parts = [p.lower() for p in client_name.split() if len(p) >= 3] if client_name else []
    
    # NIF do cliente
    personal_data = process.get("personal_data", {}) or {}
    client_nif = (personal_data.get("nif") or "").strip()
    client_nif_normalized = re.sub(r'[^\d]', '', client_nif) if client_nif else ""
    client_nif_forms = set()
    if client_nif_normalized:
        client_nif_forms.add(client_nif_normalized)
        if len(client_nif_normalized) == 9:
            client_nif_forms.add(f"{client_nif_normalized[:3]}.{client_nif_normalized[3:6]}.{client_nif_normalized[6:]}")
        client_nif_forms.add(client_nif.lower())
    
    # Referência do processo (ex: #1234)
    process_number = process.get("process_number")
    process_ref = f"#{process_number}" if process_number else None
    
    # Emails do Cliente (suporta múltiplos)
    raw_client_email = personal_data.get("email") or process.get("client_email")
    client_emails = []
    if raw_client_email:
        cleaned = raw_client_email
        if "[" in cleaned and "]" in cleaned:
            cleaned_emails = re.findall(r'[\w\.-]+@[\w\.-]+', cleaned)
        else:
            cleaned_emails = re.split(r'[,;\s]+', cleaned)
        seen = set()
        for email in cleaned_emails:
            email = email.strip().lower()
            if email and "@" in email and email not in seen:
                seen.add(email)
                client_emails.append(email)
    client_email = client_emails[0] if client_emails else None
    
    # Email do Comercial Angariador (owner_email)
    real_estate_data = process.get("real_estate_data", {}) or {}
    owner_email = real_estate_data.get("owner_email")
    if owner_email:
        owner_email = owner_email.lower().strip()
    
    # Email do Utilizador Logado
    user_email_lower = user_email.lower().strip() if user_email else None
    
    # Emails monitorizados
    monitored_emails = process.get("monitored_emails", [])
    monitored_emails = [e.lower().strip() for e in (monitored_emails or []) if e and "@" in e]
    
    # Destinatários de documentação (configurações do sistema)
    doc_recipient_to_emails = []
    try:
        from services.system_config import get_system_config
        sys_config = await get_system_config()
        doc_rec_config = sys_config.document_recipients
        if doc_rec_config.default_to_emails:
            import json as _json
            try:
                parsed = _json.loads(doc_rec_config.default_to_emails)
                if isinstance(parsed, list):
                    doc_recipient_to_emails = [e.lower().strip() for e in parsed if e and "@" in str(e)]
            except (_json.JSONDecodeError, TypeError):
                pass
        if not doc_recipient_to_emails and doc_rec_config.default_to and "@" in str(doc_rec_config.default_to):
            doc_recipient_to_emails = [doc_rec_config.default_to.lower().strip()]
    except Exception as e:
        logger.warning(f"Não foi possível carregar destinatários de documentação: {e}")
    
    # Contas de email IMAP para busca
    accounts = await get_email_accounts_async()
    if not accounts:
        return {"success": False, "error": "Nenhuma conta de email configurada. Configure IMAP/SMTP nas Configurações do Sistema."}
    
    # Contas internas da equipa (para identificação em Regra C)
    internal_emails = set()
    if user_email_lower:
        internal_emails.add(user_email_lower)
    for acc in accounts:
        # EmailAccount é uma classe com atributo 'email', não um dicionário
        acc_user = (acc.email or "").lower().strip() if hasattr(acc, 'email') else ""
        if acc_user and "@" in acc_user:
            internal_emails.add(acc_user)
    for de in doc_recipient_to_emails:
        internal_emails.add(de)
    
    # Emails relevantes para busca IMAP (todos os associados ao processo)
    assigned_emails = set()
    if user_email_lower:
        assigned_emails.add(user_email_lower)
    assigned_emails.update(client_emails)
    if owner_email:
        assigned_emails.add(owner_email)
    assigned_emails.update(monitored_emails)
    assigned_emails.update(doc_recipient_to_emails)
    
    logger.info(f"Sincronizando emails para processo {process_id}")
    logger.info(f"  - Cliente: {client_name} | NIF: {client_nif or 'N/A'} | Ref: {process_ref or 'N/A'}")
    logger.info(f"  - Email(s) cliente: {client_emails}")
    logger.info(f"  - Email comercial (owner): {owner_email}")
    logger.info(f"  - Email utilizador logado: {user_email_lower}")
    logger.info(f"  - Emails monitorizados: {monitored_emails}")
    logger.info(f"  - Destinatários doc TO: {doc_recipient_to_emails}")
    logger.info(f"  - Contas internas (Regra C): {internal_emails}")
    
    all_emails = []
    
    # Buscar emails de todas as contas IMAP
    for account in accounts:
        search_list = list(assigned_emails)
        
        # 1. Buscar por NOME DO CLIENTE no assunto/corpo
        if client_name:
            try:
                inbox_by_name = await fetch_emails_by_name(account, client_name, days, "INBOX")
                all_emails.extend(inbox_by_name)
                for sent_folder in ["Sent", "INBOX.Sent", "Sent Items", "Enviados"]:
                    try:
                        sent_by_name = await fetch_emails_by_name(account, client_name, days, sent_folder)
                        all_emails.extend(sent_by_name)
                        break
                    except:
                        continue
            except Exception as e:
                logger.warning(f"Erro ao buscar por nome na conta {account.name if hasattr(account, 'name') else '?'}: {e}")
        
        # 2. Buscar por endereços de email relevantes
        if search_list:
            try:
                inbox_emails = await fetch_emails_from_account(account, search_list, days, "INBOX")
                all_emails.extend(inbox_emails)
                for sent_folder in ["Sent", "INBOX.Sent", "Sent Items", "Enviados"]:
                    try:
                        sent_emails = await fetch_emails_from_account(account, search_list, days, sent_folder)
                        all_emails.extend(sent_emails)
                        break
                    except:
                        continue
            except Exception as e:
                logger.warning(f"Erro ao buscar por emails na conta {account.name if hasattr(account, 'name') else '?'}: {e}")
    
    # ====================================================================
    # NOVAS REGRAS DE FILTRAGEM (3 regras de negócio)
    # ====================================================================
    
    def get_email_content(em: Dict) -> str:
        """Extrair conteúdo combinado (subject + body + body_html) do email em minúsculas."""
        subject = (em.get("subject") or "").lower()
        body = (em.get("body") or "").lower()
        body_html = (em.get("body_html") or "").lower()
        return subject + " " + body + " " + body_html
    
    def has_client_name_or_nif(em: Dict) -> bool:
        """
        Verifica se o NOME DO CLIENTE ou o NIF aparece no conteúdo do email.
        Nome: partes >= 3 caracteres.
        NIF: múltiplos formatos (123456789, 123.456.789).
        """
        content = get_email_content(em)
        if client_name_parts and any(part in content for part in client_name_parts):
            return True
        if client_nif_forms:
            for nif_form in client_nif_forms:
                if nif_form and nif_form.lower() in content:
                    return True
        return False
    
    def has_process_reference(em: Dict) -> bool:
        """
        Verifica se o NIF do Cliente OU a Referência do Processo (#1234)
        aparecem no conteúdo do email.
        """
        content = get_email_content(em)
        if client_nif_forms:
            for nif_form in client_nif_forms:
                if nif_form and nif_form.lower() in content:
                    return True
        if process_ref and process_ref.lower() in content:
            return True
        return False
    
    def get_all_participants(em: Dict) -> set:
        """Retorna todos os participantes do email (from + to + cc) em lowercase."""
        participants = set()
        from_email = (em.get("from_email") or "").lower().strip()
        if from_email:
            participants.add(from_email)
        for e in (em.get("to_emails") or []):
            e = e.lower().strip()
            if e:
                participants.add(e)
        for e in (em.get("cc_emails") or []):
            e = e.lower().strip()
            if e:
                participants.add(e)
        return participants
    
    def email_matches_rule_a(em: Dict) -> bool:
        """
        REGRA A: Comunicação com Atores Específicos (Comercial / Cliente)
        
        FROM ou TO/CC cruza com email do Cliente OU Comercial Angariador.
        Segurança extra: se comunicação for EXCLUSIVA com o Comercial
        (sem participação direta do Cliente no FROM/TO/CC),
        exige Nome do Cliente ou NIF no Subject/Body.
        """
        participants = get_all_participants(em)
        
        has_client = bool(client_emails and participants.intersection(client_emails))
        has_comercial = bool(owner_email and owner_email in participants)
        
        if not (has_client or has_comercial):
            return False
        
        if has_client:
            logger.debug(f"Regra A: email com cliente direto (participantes incluem email cliente)")
            return True
        
        if has_comercial and not has_client:
            if has_client_name_or_nif(em):
                logger.debug(f"Regra A: email com comercial exclusivo + identificador cliente ✓")
                return True
            else:
                logger.debug(f"Regra A: email com comercial exclusivo SEM identificador cliente ✗ → descartado")
                return False
        
        return False
    
    def email_matches_rule_b(em: Dict) -> bool:
        """
        REGRA B: Identificação Forte / Absoluta
        
        Assunto OU Corpo contém NIF do Cliente OU Referência do Processo (#1234).
        Independentemente de quem envia/recebe.
        """
        if has_process_reference(em):
            logger.debug(f"Regra B: identificação forte (NIF ou referência processo) ✓")
            return True
        return False
    
    def email_matches_rule_c(em: Dict) -> bool:
        """
        REGRA C: Comunicação Geral B2B
        
        Email entre contas internas da equipa e contas gerais externas.
        CONDIÇÃO OBRIGATÓRIA: Nome do Cliente OU NIF no Subject/Body.
        """
        participants = get_all_participants(em)
        
        has_internal = bool(participants.intersection(internal_emails))
        if not has_internal:
            return False
        
        if has_client_name_or_nif(em):
            logger.debug(f"Regra C: B2B com conta interna + identificador cliente ✓")
            return True
        else:
            logger.debug(f"Regra C: B2B com conta interna SEM identificador cliente ✗ → descartado")
            return False
    
    def email_matches_rules(em: Dict) -> bool:
        """
        Aplica as 3 regras de filtragem de negócio.
        Um email SÓ É associado se cumprir pelo menos UMA regra.
        """
        if email_matches_rule_a(em):
            return True
        if email_matches_rule_b(em):
            return True
        if email_matches_rule_c(em):
            return True
        return False
    
    # Filtrar emails pelas 3 regras
    filtered_emails = [em for em in all_emails if email_matches_rules(em)]
    
    # Remover duplicados por Message-ID
    seen_ids = set()
    unique_emails = []
    for em in filtered_emails:
        msg_id = em.get("message_id", "")
        if msg_id and msg_id in seen_ids:
            continue
        if msg_id:
            seen_ids.add(msg_id)
        unique_emails.append(em)
    
    logger.info(f"Emails encontrados: {len(all_emails)}, após filtro: {len(unique_emails)}")


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
) -> List[Dict[str, Any]]:
    """
    Buscar TODOS os emails de uma pasta IMAP (sem filtro de processo).
    Versão síncrona para execução em thread.
    """
    emails_found = []
    
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
                })
                
            except Exception as e:
                logger.warning(f"[Webmail Sync] Erro ao processar email: {e}")
                logger.warning(f"[Webmail Sync] Traceback: {traceback.format_exc()}")
                continue
        
        mail.logout()
        logger.info(f"[Webmail Sync] {len(emails_found)} emails extraídos de {folder} ({account.name})")
        
    except Exception as e:
        logger.error(f"[Webmail Sync] Erro ao conectar IMAP {account.name}: {e}")
    
    return emails_found


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
            inbox_emails = await loop.run_in_executor(
                _email_executor,
                lambda: _fetch_all_from_folder_sync(account, "INBOX", days, max_emails)
            )
            all_emails.extend(inbox_emails)
            
            # Buscar da pasta de Enviados (tentar vários nomes)
            for sent_folder in ["Sent", "INBOX.Sent", "Sent Items", "Enviados", "INBOX.Enviados"]:
                try:
                    sent_emails = await loop.run_in_executor(
                        _email_executor,
                        lambda f=sent_folder: _fetch_all_from_folder_sync(account, f, days, max_emails)
                    )
                    if sent_emails:
                        all_emails.extend(sent_emails)
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
                    
                    email_doc = {
                        "id": str(uuid.uuid4()),
                        "process_id": None,
                        "direction": em.get("direction", "received"),
                        "from_email": em.get("from_email", ""),
                        "to_emails": [str(e) for e in (em.get("to_emails") or []) if e],
                        "cc_emails": [str(e) for e in (em.get("cc_emails") or []) if e],
                        "bcc_emails": [],
                        "subject": em.get("subject", ""),
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
        inbox_emails = await loop.run_in_executor(
            _email_executor,
            lambda: _fetch_all_from_folder_sync(account, "INBOX", days, max_emails)
        )
        
        # Buscar da pasta de Enviados
        sent_emails = []
        for sent_folder in ["Sent", "INBOX.Sent", "Sent Items", "Enviados"]:
            try:
                emails = await loop.run_in_executor(
                    _email_executor,
                    lambda f=sent_folder: _fetch_all_from_folder_sync(account, f, days, max_emails)
                )
                if emails:
                    sent_emails = emails
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
                
                email_doc = {
                    "id": str(uuid.uuid4()),
                    "process_id": None,
                    "direction": em.get("direction", "received"),
                    "from_email": em.get("from_email", ""),
                    "to_emails": [str(e) for e in (em.get("to_emails") or []) if e],
                    "cc_emails": [str(e) for e in (em.get("cc_emails") or []) if e],
                    "bcc_emails": [],
                    "subject": em.get("subject", ""),
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

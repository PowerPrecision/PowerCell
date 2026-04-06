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
import imaplib
import smtplib
import ssl
import asyncio
from concurrent.futures import ThreadPoolExecutor
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
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
                smtp_user = email_config.get("smtp_user")
                smtp_password = email_config.get("smtp_password")
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
                
                # === CONTA 2: Precision Crédito ===
                smtp_user_2 = email_config.get("smtp_user_2")
                smtp_password_2 = email_config.get("smtp_password_2")
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
        _, folders = mail.list()
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
                
                _, message_numbers = mail.search(None, 'ALL')
                
                for num in message_numbers[0].split():
                    try:
                        _, msg_data = mail.fetch(num, "(RFC822)")
                        email_body = msg_data[0][1]
                        msg = email.message_from_bytes(email_body)
                        
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
                    _, message_numbers = mail.search('UTF-8', search_query.encode('utf-8'))
                except:
                    # Fallback: buscar sem charset específico (pode não encontrar alguns resultados)
                    try:
                        # Remover caracteres especiais para busca básica
                        import unicodedata
                        search_name_ascii = unicodedata.normalize('NFKD', search_name).encode('ASCII', 'ignore').decode('ASCII')
                        _, message_numbers = mail.search(None, f'(SUBJECT "{search_name_ascii}" SINCE {since_date})')
                    except:
                        message_numbers = [b'']
                
                for num in message_numbers[0].split():
                    try:
                        _, msg_data = mail.fetch(num, "(RFC822)")
                        email_body = msg_data[0][1]
                        msg = email.message_from_bytes(email_body)
                        
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
            
            _, message_numbers = mail.search(None, f'(SINCE {since_date})')
            
            # Limitar a 200 emails mais recentes para performance
            nums = message_numbers[0].split()[-200:] if message_numbers[0] else []
            
            for num in nums:
                try:
                    _, msg_data = mail.fetch(num, "(RFC822)")
                    email_body = msg_data[0][1]
                    msg = email.message_from_bytes(email_body)
                    
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
                        _, message_numbers = mail.search('UTF-8', search_query.encode('utf-8'))
                    except:
                        # Fallback para busca sem charset
                        _, message_numbers = mail.search(None, f'({search_type} "{client_email}" SINCE {since_date})')
                    
                    for num in message_numbers[0].split():
                        try:
                            _, msg_data = mail.fetch(num, "(RFC822)")
                            email_body = msg_data[0][1]
                            msg = email.message_from_bytes(email_body)
                            
                            # Extrair informações
                            from_email = extract_email_address(msg.get("From", ""))
                            to_emails = [extract_email_address(e) for e in (msg.get("To", "")).split(",")]
                            cc_emails = [extract_email_address(e) for e in (msg.get("Cc", "")).split(",") if e]
                            subject = decode_email_header(msg.get("Subject", ""))
                            date_str = msg.get("Date", "")
                            body_text, body_html = get_email_body(msg)
                            
                            # Determinar direção
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
    
    REGRAS DE FILTRAGEM ESTRITAS:
    =============================
    O sistema APENAS guarda emails que cumpram UMA destas 5 condições:
    
    1. Emails trocados entre o Utilizador Logado e o Comercial (owner_email).
    2. Emails trocados entre o Utilizador Logado e QUALQUER EMAIL do Cliente.
       CONDIÇÃO DUPLA: O nome do cliente deve aparecer no assunto ou corpo.
       (Elimina falsos positivos — email trocado mas sem referência ao cliente)
    3. Emails trocados entre o Comercial (owner_email) e geral@powerealestate.pt.
    4. Emails trocados entre o Comercial (owner_email) e geral@precisioncredito.pt.
    5. Qualquer email onde o NOME DO CLIENTE apareça no Assunto ou Corpo.
    
    SUPORTE A MÚLTIPLOS EMAILS:
    O campo "Email Principal" pode conter múltiplos emails (separados por vírgula,
    ponto-e-vírgula ou espaço). O sistema itera sobre todos eles.
    
    Args:
        process_id: ID do processo
        days: Número de dias para sincronizar (default 30)
        user_email: Email do utilizador logado (consultor/funcionário)
    """
    # Obter processo
    process = await db.processes.find_one({"id": process_id}, {"_id": 0})
    if not process:
        return {"success": False, "error": "Processo não encontrado"}
    
    # Nome do cliente para busca por assunto/corpo (regra 5)
    client_name = process.get("client_name", "")
    client_name_parts = [p.lower() for p in client_name.split() if len(p) >= 3] if client_name else []
    
    # Emails gerais da empresa (usados nas regras 3 e 4)
    company_emails = [
        "geral@powerealestate.pt",
        "geral@precisioncredito.pt"
    ]
    
    # ===== EXTRAÇÃO DE VARIÁVEIS DO PROCESSO =====
    
    # Email do Cliente — suporta múltiplos emails (string separada por vírgula/ponto-e-vírgula ou lista)
    personal_data = process.get("personal_data", {}) or {}
    raw_client_email = personal_data.get("email") or process.get("client_email")
    client_emails = []  # Lista de emails do cliente
    
    if raw_client_email:
        # Limpar emails com formatação markdown do Trello (ex: [text](mailto:email))
        cleaned = raw_client_email
        if "[" in cleaned and "]" in cleaned:
            # Extrair todos os emails de links mailto: 
            cleaned_emails = re.findall(r'[\w\.-]+@[\w\.-]+', cleaned)
        else:
            # Separar por vírgula, ponto-e-vírgula, ou ponto (comum em emails copiados)
            cleaned_emails = re.split(r'[,;\s]+', cleaned)
        
        for email in cleaned_emails:
            email = email.strip().lower()
            if email and "@" in email:
                client_emails.append(email)
        
        # Remover duplicados preservando ordem
        seen = set()
        unique_emails = []
        for e in client_emails:
            if e not in seen:
                seen.add(e)
                unique_emails.append(e)
        client_emails = unique_emails
    
    # Para compatibilidade com código existente, manter client_email como primeiro da lista
    client_email = client_emails[0] if client_emails else None
    
    # Email do Comercial (owner_email) — agente imobiliário que fez a angariação
    real_estate_data = process.get("real_estate_data", {}) or {}
    owner_email = real_estate_data.get("owner_email")
    if owner_email:
        owner_email = owner_email.lower().strip()
    
    # Email do Utilizador Logado — consultor/funcionário a usar o sistema
    user_email_lower = user_email.lower().strip() if user_email else None
    
    # Emails monitorizados adicionados manualmente (apenas para busca IMAP, não para filtragem)
    monitored_emails = process.get("monitored_emails", [])
    monitored_emails = [e.lower().strip() for e in (monitored_emails or []) if e and "@" in e]
    
    logger.info(f"Sincronizando emails para processo {process_id}")
    logger.info(f"  - Cliente: {client_name}")
    logger.info(f"  - Email(s) cliente: {client_emails}")
    logger.info(f"  - Email comercial (owner): {owner_email}")
    logger.info(f"  - Email utilizador logado: {user_email_lower}")
    logger.info(f"  - Emails monitorizados (IMAP only): {monitored_emails}")
    
    # Usar versão async para buscar contas (inclui DB)
    accounts = await get_email_accounts_async()
    if not accounts:
        return {"success": False, "error": "Nenhuma conta de email configurada. Configure IMAP/SMTP nas Configurações do Sistema."}
    
    all_emails = []
    
    # Buscar emails de todas as contas
    for account in accounts:
        # 1. Buscar por NOME DO CLIENTE no assunto/corpo (regra 5)
        if client_name:
            inbox_by_name = await fetch_emails_by_name(account, client_name, days, "INBOX")
            all_emails.extend(inbox_by_name)
            
            # Tentar buscar nos enviados por nome
            for sent_folder in ["Sent", "INBOX.Sent", "Sent Items", "Enviados"]:
                try:
                    sent_by_name = await fetch_emails_by_name(account, client_name, days, sent_folder)
                    all_emails.extend(sent_by_name)
                    break
                except:
                    continue
        
        # 2. Buscar por endereços de email relevantes (para regras 1-4)
        # Montar lista de emails para busca IMAP: todos os participantes possíveis
        emails_to_search = []
        if user_email_lower:
            emails_to_search.append(user_email_lower)
        # Incluir TODOS os emails do cliente (suporte a múltiplos)
        emails_to_search.extend(client_emails)
        if owner_email:
            emails_to_search.append(owner_email)
        # Incluir emails gerais da empresa para capturar regras 3 e 4
        emails_to_search.extend(company_emails)
        # Incluir monitorizados para busca (a filtragem rigorosa decide o que entra)
        emails_to_search.extend(monitored_emails)
        
        if emails_to_search:
            inbox_emails = await fetch_emails_from_account(
                account, emails_to_search, days, "INBOX"
            )
            all_emails.extend(inbox_emails)
            
            for sent_folder in ["Sent", "INBOX.Sent", "Sent Items", "Enviados"]:
                try:
                    sent_emails = await fetch_emails_from_account(
                        account, emails_to_search, days, sent_folder
                    )
                    all_emails.extend(sent_emails)
                    break
                except:
                    continue
    
    # ====================================================================
    # REGRAS DE FILTRAGEM ESTRITAS (5 regras de negócio)
    # ====================================================================
    
    def client_name_in_email(em: Dict) -> bool:
        """
        Verifica se o NOME DO CLIENTE aparece explicitamente no assunto ou corpo.
        Usa partes >= 3 caracteres para evitar falsos positivos.
        Case-insensitive via .lower() em client_name_parts (já preparado).
        """
        if not client_name_parts:
            return False
        subject = (em.get("subject") or "").lower()
        body = (em.get("body") or "").lower()
        body_html = (em.get("body_html") or "").lower()
        content = subject + " " + body + " " + body_html
        return any(part in content for part in client_name_parts)
    
    def exchanged_between_any(account_emails: list, em: Dict) -> tuple:
        """
        Verifica se houve troca de emails ENTRE o utilizador logado e QUALQUER UM
        dos emails da lista account_emails.
        
        Returns:
            tuple: (matched: bool, matched_email: str|None) — qual email fez match
        """
        if not account_emails:
            return (False, None)
        from_email = (em.get("from_email") or "").lower()
        to_emails = [e.lower() for e in (em.get("to_emails") or [])]
        cc_emails = [e.lower() for e in (em.get("cc_emails") or [])]
        all_recipients = to_emails + cc_emails
        
        for acc_email in account_emails:
            if not acc_email:
                continue
            # Utilizador logado enviou para este email do cliente
            if from_email == user_email_lower and acc_email in all_recipients:
                return (True, acc_email)
            # Este email do cliente enviou para o utilizador logado
            if from_email == acc_email and user_email_lower in all_recipients:
                return (True, acc_email)
        
        return (False, None)
    
    def exchanged_between(email_a: str, email_b: str, em: Dict) -> bool:
        """
        Verifica se houve troca de emails ENTRE email_a e email_b.
        "Troca" significa: um é remetente E o outro está em To/CC.
        Não basta ambos aparecerem — um deve ter enviado e o outro recebido.
        """
        if not email_a or not email_b:
            return False
        from_email = (em.get("from_email") or "").lower()
        to_emails = [e.lower() for e in (em.get("to_emails") or [])]
        cc_emails = [e.lower() for e in (em.get("cc_emails") or [])]
        all_recipients = to_emails + cc_emails
        
        # email_a enviou para email_b
        if from_email == email_a and email_b in all_recipients:
            return True
        # email_b enviou para email_a
        if from_email == email_b and email_a in all_recipients:
            return True
        return False
    
    def email_matches_rules(em: Dict) -> bool:
        """
        Aplica as regras de filtragem ESTRITAS de negócio.
        
        REGRAS ATUALIZADAS:
        1. Emails trocados entre Utilizador Logado e Comercial (owner_email).
        2. Emails trocados entre Utilizador Logado e QUALQUER EMAIL do Cliente
           + CONDIÇÃO OBRIGATÓRIA: nome do cliente deve aparecer no assunto ou corpo.
           (Verificação dupla para eliminar falsos positivos)
        3. Emails trocados entre Comercial (owner_email) e geral@powerealestate.pt.
        4. Emails trocados entre Comercial (owner_email) e geral@precisioncredito.pt.
        5. Qualquer email onde o NOME DO CLIENTE apareça no Assunto ou Corpo.
        
        Returns:
            True se o email deve ser incluído, False caso contrário.
        """
        # REGRA 5 (primeiro — sem dependência de variáveis de email):
        # Qualquer email onde o nome do cliente apareça no assunto ou corpo
        if client_name_in_email(em):
            return True
        
        # REGRA 1: Emails trocados entre Utilizador Logado e Comercial
        if exchanged_between(user_email_lower, owner_email, em):
            return True
        
        # REGRA 2: Emails trocados entre Utilizador Logado e QUALQUER EMAIL do Cliente
        # CONDIÇÃO DUPLA: match de email + verificação do nome no assunto/corpo
        match_result = exchanged_between_any(client_emails, em)
        if match_result[0]:
            # Match por email encontrado — agora verificar o NOME DO CLIENTE
            if client_name_in_email(em):
                logger.debug(f"Regra 2 (dupla verificação): email matched={match_result[1]}, nome encontrado ✓")
                return True
            else:
                # Email trocado com cliente mas NOME não encontrado no conteúdo
                # → Falso positivo provável, descartar
                logger.debug(f"Regra 2 (dupla verificação): email matched={match_result[1]}, nome NÃO encontrado ✗ → descartado")
                return False
        
        # REGRA 3: Emails trocados entre Comercial e geral@powerealestate.pt
        if exchanged_between(owner_email, "geral@powerealestate.pt", em):
            return True
        
        # REGRA 4: Emails trocados entre Comercial e geral@precisioncredito.pt
        if exchanged_between(owner_email, "geral@precisioncredito.pt", em):
            return True
        
        # Nenhuma regra satisfeita → excluir
        return False
    
    # Filtrar emails pelas 5 regras estritas
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
    
    # Guardar na base de dados
    new_count = 0
    for em in unique_emails:
        # Verificar se já existe (usar date como sent_at)
        sent_at = em.get("date") or em.get("sent_at")
        existing = await db.emails.find_one({
            "process_id": process_id,
            "subject": em["subject"],
            "sent_at": sent_at,
            "from_email": em["from_email"]
        })
        
        if not existing:
            email_doc = {
                "id": str(uuid.uuid4()),
                "process_id": process_id,
                "direction": em["direction"],
                "from_email": em["from_email"],
                "to_emails": em["to_emails"],
                "cc_emails": em.get("cc_emails", []),
                "bcc_emails": em.get("bcc_emails", []),
                "subject": em["subject"],
                "body": em["body"],
                "body_html": em.get("body_html"),
                "attachments": [],
                "status": "sent",
                "sent_at": sent_at,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "created_by": None,
                "notes": f"Sincronizado de {em.get('account', 'desconhecido')}",
                "synced": True,
                "account": em["account"],
                "matched_by": em.get("matched_by", "filter_rules")
            }
            await db.emails.insert_one(email_doc)
            new_count += 1
    
    logger.info(f"Sincronizados {new_count} novos emails para processo {process_id}")
    
    return {
        "success": True,
        "total_found": len(all_emails),
        "filtered_count": len(unique_emails),
        "new_imported": new_count,
        "process_id": process_id
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
    created_by: Optional[str] = None
) -> Dict[str, Any]:
    """
    Enviar email através de uma das contas configuradas.
    
    Args:
        account_name: "precision" ou "power"
        to_emails: Lista de destinatários
        subject: Assunto
        body: Corpo do email (texto)
        body_html: Corpo do email (HTML)
        cc_emails: CC
        bcc_emails: BCC
        process_id: ID do processo (para guardar no histórico)
        created_by: ID do utilizador que enviou
    """
    accounts = get_email_accounts()
    account = next((a for a in accounts if a.name == account_name), None)
    
    if not account:
        # Usar primeira conta disponível
        if accounts:
            account = accounts[0]
        else:
            return {"success": False, "error": "Nenhuma conta de email configurada"}
    
    try:
        # Criar mensagem
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = account.email
        msg["To"] = ", ".join(to_emails)
        
        if cc_emails:
            msg["Cc"] = ", ".join(cc_emails)
        
        # Adicionar corpo
        msg.attach(MIMEText(body, "plain", "utf-8"))
        if body_html:
            msg.attach(MIMEText(body_html, "html", "utf-8"))
        
        # Enviar
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(account.smtp_server, account.smtp_port, context=context) as server:
            server.login(account.email, account.password)
            
            all_recipients = to_emails + (cc_emails or []) + (bcc_emails or [])
            server.sendmail(account.email, all_recipients, msg.as_string())
        
        logger.info(f"Email enviado via {account.name} para {to_emails}")
        
        # Guardar no histórico
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
                "attachments": [],
                "status": "sent",
                "sent_at": datetime.now(timezone.utc).isoformat(),
                "created_at": datetime.now(timezone.utc).isoformat(),
                "created_by": created_by,
                "notes": f"Enviado via {account.name}",
                "synced": False,
                "account": account.name
            }
            await db.emails.insert_one(email_doc)
        
        return {"success": True, "account": account.name}
        
    except Exception as e:
        logger.error(f"Erro ao enviar email via {account.name}: {e}")
        return {"success": False, "error": str(e)}


async def test_email_connection(account_name: str = None) -> Dict[str, Any]:
    """Testar conexão com as contas de email."""
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

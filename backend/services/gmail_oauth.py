"""
====================================================================
SMART EMAIL ENGINE V2 — GMAIL API + IMAP/SMTP FALLBACK
====================================================================
Motor de email "Smart" que escolhe automaticamente o método de acesso:

1. Se a configuração tiver um google_refresh_token → usa Gmail API
   via google-api-python-client (OAuth 2.0).

2. Se não tiver token mas tiver password → usa método clássico
   IMAP/SMTP (para emails que não sejam da Google).

ESTRATÉGIA DE REFRESH DE TOKENS:
- O refresh_token nunca expira (a menos que o utilizador revogue).
- O access_token expira em ~1 hora.
- Esta camada gere o refresh automático e guarda o novo access_token.
====================================================================
"""
import logging
import base64
import email
import traceback
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import decode_header
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor

from database import db

logger = logging.getLogger(__name__)

# Thread pool para operações bloqueantes (IMAP/SMTP legacy)
_legacy_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="email_legacy_")


# =====================================================================
# GMAIL API HELPERS
# =====================================================================

def _build_gmail_credentials(encrypted_refresh_token: str):
    """
    Cria credenciais OAuth a partir do refresh_token encriptado.

    Returns:
        google.oauth2.credentials.Credentials com refresh_token

    Raises:
        ValueError: Se o refresh_token não puder ser desencriptado.
        ImportError: Se as bibliotecas Google não estiverem instaladas.
    """
    from services.encryption import encryption_service
    from google.oauth2.credentials import Credentials
    from config import GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET

    refresh_token = encryption_service.decrypt(encrypted_refresh_token)

    if not refresh_token or refresh_token.startswith("ENC:"):
        raise ValueError(
            "Refresh token não desencriptado correctamente. "
            "Pode ser necessário re-autenticar."
        )

    return Credentials(
        token=None,  # Será obtido via refresh
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=GOOGLE_CLIENT_ID,
        client_secret=GOOGLE_CLIENT_SECRET,
        scopes=[
            'https://mail.google.com/',
            'https://www.googleapis.com/auth/gmail.readonly',
            'https://www.googleapis.com/auth/gmail.compose',
            'https://www.googleapis.com/auth/gmail.modify',
        ],
    )


def _get_gmail_service(credentials):
    """Cria o serviço Gmail API."""
    from googleapiclient.discovery import build
    return build("gmail", "v1", credentials=credentials)


def _refresh_credentials_if_needed(
    credentials,
    user_id: str = None,
) -> bool:
    """
    Verifica se o access_token expirou e faz refresh.
    Guarda o novo access_token na DB.

    Returns:
        True se o token foi refreshed, False se ainda era válido.
    """
    from google.auth.transport.requests import Request

    if credentials.valid:
        return False

    if not credentials.expired:
        return False

    if not credentials.refresh_token:
        logger.warning("[Gmail API] Credentials expiradas sem refresh_token")
        return False

    try:
        credentials.refresh(Request())

        # Guardar o novo access_token encriptado na DB
        if user_id:
            from services.encryption import encryption_service
            encrypted_access = encryption_service.encrypt(credentials.token)
            await_safe = db.users.update_one(
                {"id": user_id},
                {"$set": {"email_config.google_access_token": encrypted_access}}
            )
            logger.info(f"[Gmail API] Access token refreshed para user {user_id}")

        return True

    except Exception as e:
        logger.error(f"[Gmail API] Erro ao fazer refresh do token: {e}")
        return False


def _refresh_credentials_sync(credentials) -> bool:
    """Versão síncrona do refresh (para uso em threads)."""
    from google.auth.transport.requests import Request

    if credentials.valid:
        return False

    if not credentials.refresh_token:
        logger.warning("[Gmail API] Credentials expiradas sem refresh_token")
        return False

    try:
        credentials.refresh(Request())
        return True
    except Exception as e:
        logger.error(f"[Gmail API] Erro ao fazer refresh do token: {e}")
        return False


# =====================================================================
# EMAIL BODY PARSING
# =====================================================================

def _decode_header_value(header: str) -> str:
    """Decode email header value."""
    if not header:
        return ""
    decoded_parts = decode_header(header)
    result = []
    for content, charset in decoded_parts:
        if isinstance(content, bytes):
            try:
                result.append(content.decode(charset or 'utf-8', errors='replace'))
            except Exception:
                result.append(content.decode('utf-8', errors='replace'))
        else:
            result.append(str(content))
    return ' '.join(result)


def _extract_email_address(header: str) -> str:
    """Extrair endereço de email de um header."""
    if not header:
        return ""
    import re
    match = re.search(r'<([^>]+)>', header)
    if match:
        return match.group(1).lower()
    return header.strip().lower()


def _parse_gmail_message(msg_data: dict, account_email: str, account_name: str = "gmail") -> dict:
    """
    Converte uma mensagem da Gmail API para o formato interno do CRM.

    Args:
        msg_data: Mensagem da Gmail API (formato JSON).
        account_email: Email da conta Gmail.
        account_name: Nome da conta (para o campo "account").

    Returns:
        dict no formato interno do email_service.
    """
    headers = {h["name"]: h["value"] for h in msg_data.get("payload", {}).get("headers", [])}

    from_email = _extract_email_address(headers.get("From", ""))
    to_raw = headers.get("To", "")
    to_emails = [_extract_email_address(e) for e in to_raw.split(",") if e.strip()]
    cc_raw = headers.get("Cc", "")
    cc_emails = [_extract_email_address(e) for e in cc_raw.split(",") if e.strip()] if cc_raw else []
    subject = _decode_header_value(headers.get("Subject", ""))
    date_str = headers.get("Date", "")

    # Direção
    direction = "sent" if from_email.lower() == account_email.lower() else "received"

    # Parsear data
    try:
        if date_str:
            import email.utils
            email_date = email.utils.parsedate_to_datetime(date_str)
        else:
            # Usar timestamp interno do Gmail
            epoch_ms = int(msg_data.get("internalDate", 0))
            email_date = datetime.fromtimestamp(epoch_ms / 1000, tz=timezone.utc)
    except Exception:
        email_date = datetime.now(timezone.utc)

    # Extrair corpo
    body_text = ""
    body_html = ""

    payload = msg_data.get("payload", {})
    _extract_gmail_body(payload, body_text_buf=[], body_html_buf=[])

    # Buscar anexos
    attachments = []
    _extract_gmail_attachments(payload, attachments)

    return {
        "message_id": headers.get("Message-ID", msg_data.get("id", "")),
        "gmail_message_id": msg_data.get("id", ""),
        "from_email": from_email,
        "to_emails": to_emails,
        "cc_emails": cc_emails,
        "subject": subject,
        "body": body_text,
        "body_html": body_html,
        "attachments": attachments,
        "date": email_date.isoformat(),
        "direction": direction,
        "source": "gmail_api",
        "account": account_name,
    }


def _extract_gmail_body(payload: dict, body_text_buf: list, body_html_buf: list):
    """Recursivamente extrai corpo (texto e HTML) de uma mensagem Gmail."""
    mime_type = payload.get("mimeType", "")

    if "parts" in payload:
        for part in payload["parts"]:
            _extract_gmail_body(part, body_text_buf, body_html_buf)
        return

    body_data = payload.get("body", {}).get("data", "")

    if not body_data:
        return

    decoded = base64.urlsafe_b64decode(body_data).decode("utf-8", errors="replace")

    if mime_type == "text/plain":
        body_text_buf.append(decoded)
    elif mime_type == "text/html":
        body_html_buf.append(decoded)


def _extract_gmail_attachments(payload: dict, attachments: list):
    """Recursivamente extrai metadados de anexos de uma mensagem Gmail."""
    if "parts" in payload:
        for part in payload["parts"]:
            _extract_gmail_attachments(part, attachments)
        return

    # Verificar se é anexo
    filename = payload.get("filename", "")
    body = payload.get("body", {})

    if filename and body.get("attachmentId"):
        attachments.append({
            "filename": filename,
            "content_type": payload.get("mimeType", "application/octet-stream"),
            "size": body.get("size", 0),
            "gmail_attachment_id": body.get("attachmentId"),
        })


# =====================================================================
# SMART EMAIL SERVICE — INTERFACE PÚBLICA
# =====================================================================

def has_google_oauth(email_config: dict) -> bool:
    """
    Verifica se a configuração de email tem Google OAuth configurado.

    Args:
        email_config: Dicionário com a configuração de email do utilizador.

    Returns:
        True se tem google_refresh_token, False caso contrário.
    """
    return bool(email_config and email_config.get("google_refresh_token"))


def get_auth_method(email_config: dict) -> str:
    """
    Determina o método de autenticação da configuração.

    Returns:
        "google_oauth" se tem refresh_token,
        "imap_smtp" se tem password mas não refresh_token,
        "none" se não tem nenhum.
    """
    if has_google_oauth(email_config):
        return "google_oauth"
    if email_config and email_config.get("encrypted_password"):
        return "imap_smtp"
    return "none"


async def fetch_emails_smart(
    email_config: dict,
    user_id: str,
    since_days: int = 7,
    max_emails: int = 100,
    folders: List[str] = None,
) -> Tuple[List[Dict[str, Any]], str]:
    """
    Busca emails usando o método mais adequado (Gmail API ou IMAP).

    Args:
        email_config: Configuração de email do utilizador.
        user_id: ID do utilizador (para refresh de tokens).
        since_days: Dias para buscar.
        max_emails: Máximo de emails por pasta.
        folders: Lista de pastas ("INBOX", "Sent", etc.).

    Returns:
        Tuple de (lista de emails, método usado).
    """
    if not folders:
        folders = ["INBOX", "Sent", "INBOX.Sent", "Sent Items", "Enviados"]

    if has_google_oauth(email_config):
        emails = await fetch_emails_gmail(
            email_config, user_id, since_days, max_emails
        )
        return emails, "google_oauth"
    else:
        emails = await fetch_emails_imap_legacy(
            email_config, since_days, max_emails, folders
        )
        return emails, "imap_smtp"


async def fetch_emails_gmail(
    email_config: dict,
    user_id: str,
    since_days: int = 7,
    max_emails: int = 100,
) -> List[Dict[str, Any]]:
    """
    Busca emails usando a Gmail API (OAuth 2.0).

    Usa o refresh_token para obter um access_token válido,
    depois lista emails da INBOX e Sent.

    Args:
        email_config: Configuração com google_refresh_token.
        user_id: ID do utilizador.
        since_days: Dias para buscar.
        max_emails: Máximo de emails.

    Returns:
        Lista de emails no formato interno.
    """
    import asyncio

    try:
        # Construir credenciais
        credentials = _build_gmail_credentials(email_config["google_refresh_token"])

        # Refresh do token se necessário
        refreshed = _refresh_credentials_if_needed(credentials, user_id)
        if refreshed:
            logger.info(f"[Gmail API] Token refreshed para user {user_id}")

        # Buscar emails em thread separada (API calls são bloqueantes)
        loop = asyncio.get_event_loop()

        try:
            emails = await loop.run_in_executor(
                _legacy_executor,
                lambda: _fetch_emails_gmail_sync(
                    credentials,
                    email_config.get("email_address", ""),
                    email_config.get("account_name", "gmail"),
                    since_days,
                    max_emails,
                )
            )
            return emails
        except Exception as e:
            logger.error(f"[Gmail API] Erro ao buscar emails: {e}")
            return []

    except ValueError as e:
        logger.error(f"[Gmail API] Erro de credenciais: {e}")
        return []
    except ImportError:
        logger.error("[Gmail API] Bibliotecas Google não instaladas")
        return []
    except Exception as e:
        logger.error(f"[Gmail API] Erro inesperado: {e}")
        logger.debug(f"[Gmail API] Traceback: {traceback.format_exc()}")
        return []


def _fetch_emails_gmail_sync(
    credentials,
    account_email: str,
    account_name: str,
    since_days: int,
    max_emails: int,
) -> List[Dict[str, Any]]:
    """Versão síncrona de fetch_emails_gmail."""
    service = _get_gmail_service(credentials)
    all_emails = []

    # Calcular data de filtro
    after_date = (datetime.now(timezone.utc) - timedelta(days=since_days)).strftime("%Y/%m/%d")

    # Buscar da INBOX
    try:
        inbox_results = service.users().messages().list(
            userId="me",
            q=f"after:{after_date}",
            maxResults=max_emails,
        ).execute()

        messages = inbox_results.get("messages", [])
        logger.info(f"[Gmail API] {len(messages)} emails na INBOX")

        for msg_ref in messages:
            try:
                msg_data = service.users().messages().get(
                    userId="me",
                    id=msg_ref["id"],
                    format="full",
                ).execute()
                parsed = _parse_gmail_message(msg_data, account_email, account_name)
                all_emails.append(parsed)
            except Exception as e:
                logger.warning(f"[Gmail API] Erro ao ler mensagem {msg_ref.get('id')}: {e}")

    except Exception as e:
        logger.error(f"[Gmail API] Erro ao listar INBOX: {e}")

    # Buscar dos Enviados
    try:
        sent_results = service.users().messages().list(
            userId="me",
            q=f"after:{after_date} in:sent",
            maxResults=max_emails,
        ).execute()

        sent_messages = sent_results.get("messages", [])
        logger.info(f"[Gmail API] {len(sent_messages)} emails em Enviados")

        seen_ids = {em.get("message_id") for em in all_emails}

        for msg_ref in sent_messages:
            try:
                msg_data = service.users().messages().get(
                    userId="me",
                    id=msg_ref["id"],
                    format="full",
                ).execute()
                parsed = _parse_gmail_message(msg_data, account_email, account_name)

                # Deduplicação
                if parsed.get("message_id") not in seen_ids:
                    all_emails.append(parsed)
                    seen_ids.add(parsed.get("message_id"))
            except Exception as e:
                logger.warning(f"[Gmail API] Erro ao ler mensagem enviada {msg_ref.get('id')}: {e}")

    except Exception as e:
        logger.error(f"[Gmail API] Erro ao listar Enviados: {e}")

    logger.info(f"[Gmail API] Total: {len(all_emails)} emails extraídos")
    return all_emails


async def send_email_gmail(
    email_config: dict,
    user_id: str,
    to_emails: List[str],
    subject: str,
    body_text: str,
    body_html: str = None,
    cc_emails: List[str] = None,
    reply_to_message_id: str = None,
) -> Dict[str, Any]:
    """
    Envia um email usando a Gmail API.

    Args:
        email_config: Configuração com google_refresh_token.
        user_id: ID do utilizador.
        to_emails: Lista de destinatários.
        subject: Assunto do email.
        body_text: Corpo em texto plano.
        body_html: Corpo em HTML (opcional).
        cc_emails: Lista de CC (opcional).
        reply_to_message_id: Message-ID para responder (In-Reply-To).

    Returns:
        Dict com resultado (success, message_id, etc.)
    """
    import asyncio

    try:
        credentials = _build_gmail_credentials(email_config["google_refresh_token"])
        _refresh_credentials_if_needed(credentials, user_id)

        loop = asyncio.get_event_loop()

        result = await loop.run_in_executor(
            _legacy_executor,
            lambda: _send_email_gmail_sync(
                credentials,
                email_config.get("email_address", ""),
                to_emails,
                subject,
                body_text,
                body_html,
                cc_emails,
                reply_to_message_id,
            )
        )
        return result

    except Exception as e:
        logger.error(f"[Gmail API] Erro ao enviar email: {e}")
        return {"success": False, "error": str(e)}


def _send_email_gmail_sync(
    credentials,
    from_email: str,
    to_emails: List[str],
    subject: str,
    body_text: str,
    body_html: str = None,
    cc_emails: List[str] = None,
    reply_to_message_id: str = None,
) -> Dict[str, Any]:
    """Versão síncrona de send_email_gmail."""
    service = _get_gmail_service(credentials)

    # Criar mensagem MIME
    if body_html:
        msg = MIMEMultipart("alternative")
        msg.attach(MIMEText(body_text, "plain", "utf-8"))
        msg.attach(MIMEText(body_html, "html", "utf-8"))
    else:
        msg = MIMEText(body_text, "plain", "utf-8")

    msg["To"] = ", ".join(to_emails)
    msg["From"] = from_email
    msg["Subject"] = subject

    if cc_emails:
        msg["Cc"] = ", ".join(cc_emails)

    if reply_to_message_id:
        msg["In-Reply-To"] = reply_to_message_id
        msg["References"] = reply_to_message_id

    # Encode para base64url (formato Gmail API)
    raw_message = base64.urlsafe_b64encode(msg.as_bytes()).decode()

    # Enviar via Gmail API
    send_body = {"raw": raw_message}
    result = service.users().messages().send(userId="me", body=send_body).execute()

    return {
        "success": True,
        "message_id": result.get("id"),
        "thread_id": result.get("threadId"),
        "label_ids": result.get("labelIds", []),
    }


# =====================================================================
# IMAP/SMTP FALLBACK (LEGADO)
# =====================================================================

async def fetch_emails_imap_legacy(
    email_config: dict,
    since_days: int = 7,
    max_emails: int = 100,
    folders: List[str] = None,
) -> List[Dict[str, Any]]:
    """
    Busca emails usando IMAP clássico (fallback para não-Gmail).

    Re-delegar para o email_service original.
    """
    from services.encryption import encryption_service
    import imaplib
    import ssl
    import certifi
    import asyncio

    if not folders:
        folders = ["INBOX", "Sent", "INBOX.Sent", "Sent Items", "Enviados"]

    encrypted_password = email_config.get("encrypted_password", "")
    if not encrypted_password:
        logger.warning("[Email V2] IMAP fallback sem password configurada")
        return []

    password = encryption_service.decrypt(encrypted_password)
    if not password or password.startswith("ENC:"):
        logger.error("[Email V2] Falha ao desencriptar password para IMAP")
        return []

    imap_server = email_config.get("imap_server", "")
    imap_port = email_config.get("imap_port", 993)
    account_email = email_config.get("email_address", "")

    if not imap_server or not account_email:
        logger.warning("[Email V2] IMAP fallback sem servidor ou email configurados")
        return []

    try:
        loop = asyncio.get_event_loop()
        emails = await loop.run_in_executor(
            _legacy_executor,
            lambda: _fetch_imap_sync(
                imap_server, imap_port, account_email, password,
                since_days, max_emails, folders,
            )
        )
        return emails
    except Exception as e:
        logger.error(f"[Email V2] Erro no IMAP fallback: {e}")
        return []


def _fetch_imap_sync(
    imap_server: str,
    imap_port: int,
    account_email: str,
    password: str,
    since_days: int,
    max_emails: int,
    folders: List[str],
) -> List[Dict[str, Any]]:
    """Versão síncrona do fetch IMAP fallback."""
    import imaplib
    import ssl
    import certifi
    import email as email_lib
    from email.utils import parsedate_to_datetime

    emails_found = []
    seen_msg_ids = set()

    try:
        ssl_context = ssl.create_default_context(cafile=certifi.where())
        mail = imaplib.IMAP4_SSL(imap_server, int(imap_port), ssl_context=ssl_context, timeout=30)
        mail.login(account_email, password)

        since_date = (datetime.now() - timedelta(days=since_days)).strftime("%d-%b-%Y")

        for folder in folders:
            try:
                result, _ = mail.select(folder)
                if result != 'OK':
                    continue

                search_result = mail.search(None, f'(SINCE {since_date})')
                nums = (search_result[1][0] if search_result[1] else b'').split()

                if len(nums) > max_emails:
                    nums = nums[-max_emails:]

                for num in nums:
                    try:
                        fetch_result = mail.fetch(num, "(RFC822)")
                        if not fetch_result or len(fetch_result) < 2:
                            continue

                        msg_data = fetch_result[1]
                        if not msg_data:
                            continue

                        if isinstance(msg_data, list) and len(msg_data) > 0:
                            item = msg_data[0]
                            if isinstance(item, tuple) and len(item) >= 2:
                                email_bytes = item[1]
                            elif isinstance(item, bytes):
                                email_bytes = item
                            else:
                                continue
                        else:
                            continue

                        msg = email_lib.message_from_bytes(email_bytes)
                        msg_id = msg.get("Message-ID", "")

                        if not msg_id or msg_id in seen_msg_ids:
                            continue
                        seen_msg_ids.add(msg_id)

                        from_email = _extract_email_address(msg.get("From", ""))
                        to_emails = [_extract_email_address(e) for e in (msg.get("To", "")).split(",") if e.strip()]
                        cc_raw = msg.get("Cc", "")
                        cc_emails = [_extract_email_address(e) for e in cc_raw.split(",") if e.strip()] if cc_raw else []
                        subject = _decode_header_value(msg.get("Subject", ""))
                        date_str = msg.get("Date", "")

                        direction = "sent" if from_email.lower() == account_email.lower() else "received"

                        email_date = None
                        if date_str:
                            try:
                                email_date = parsedate_to_datetime(date_str)
                            except Exception:
                                email_date = datetime.now(timezone.utc)

                        emails_found.append({
                            "message_id": msg_id,
                            "from_email": from_email,
                            "to_emails": to_emails,
                            "cc_emails": cc_emails,
                            "subject": subject,
                            "body": "",
                            "body_html": "",
                            "attachments": [],
                            "date": email_date.isoformat() if email_date else datetime.now(timezone.utc).isoformat(),
                            "direction": direction,
                            "source": "imap_fallback",
                            "account": "legacy",
                        })

                    except Exception as e:
                        logger.warning(f"[Email V2] Erro ao processar email IMAP: {e}")

                # Só processar a primeira pasta INBOX e a primeira pasta de enviados
                if folder == "INBOX":
                    continue
                else:
                    break  # Parar depois da primeira pasta Sent encontrada

            except Exception as e:
                logger.debug(f"[Email V2] Pasta {folder} não encontrada: {e}")
                continue

        mail.logout()

    except Exception as e:
        logger.error(f"[Email V2] Erro IMAP: {e}")

    return emails_found


# =====================================================================
# TEST CONNECTION (Smart)
# =====================================================================

async def test_connection_smart(email_config: dict, user_id: str = None) -> Dict[str, Any]:
    """
    Testa a ligação de email usando o método mais adequado.

    Se tem refresh_token → testa Gmail API.
    Se tem password → testa IMAP/SMTP.

    Returns:
        Dict com resultado do teste (success, auth_method, etc.)
    """
    auth_method = get_auth_method(email_config)

    if auth_method == "google_oauth":
        return await test_gmail_connection(email_config, user_id)
    elif auth_method == "imap_smtp":
        return await test_imap_connection(email_config)
    else:
        return {
            "success": False,
            "auth_method": "none",
            "error": "Nenhuma credencial configurada (sem Google OAuth e sem password IMAP)",
        }


async def test_gmail_connection(email_config: dict, user_id: str = None) -> Dict[str, Any]:
    """Testa a ligação à Gmail API."""
    import asyncio

    try:
        credentials = _build_gmail_credentials(email_config["google_refresh_token"])
        _refresh_credentials_if_needed(credentials, user_id)

        loop = asyncio.get_event_loop()

        result = await loop.run_in_executor(
            _legacy_executor,
            lambda: _test_gmail_sync(credentials, email_config.get("email_address", "")),
        )
        return result

    except ValueError as e:
        return {
            "success": False,
            "auth_method": "google_oauth",
            "gmail_api_connected": False,
            "error": str(e),
        }
    except Exception as e:
        return {
            "success": False,
            "auth_method": "google_oauth",
            "gmail_api_connected": False,
            "error": str(e),
        }


def _test_gmail_sync(credentials, account_email: str) -> Dict[str, Any]:
    """Versão síncrona do teste Gmail API."""
    try:
        service = _get_gmail_service(credentials)

        # Testar com getProfile (endpoint mais leve)
        profile = service.users().getProfile(userId="me").execute()

        verified_email = profile.get("emailAddress", account_email)

        return {
            "success": True,
            "auth_method": "google_oauth",
            "gmail_api_connected": True,
            "imap_connected": False,
            "smtp_connected": False,
            "verified_email": verified_email,
            "messages_total": profile.get("messagesTotal", 0),
            "error": None,
        }

    except Exception as e:
        return {
            "success": False,
            "auth_method": "google_oauth",
            "gmail_api_connected": False,
            "imap_connected": False,
            "smtp_connected": False,
            "error": f"Erro ao conectar à Gmail API: {str(e)}",
        }


async def test_imap_connection(email_config: dict) -> Dict[str, Any]:
    """Testa a ligação IMAP/SMTP clássica."""
    from services.encryption import encryption_service
    import imaplib
    import smtplib
    import ssl
    import certifi
    import asyncio

    encrypted_password = email_config.get("encrypted_password", "")
    if not encrypted_password:
        return {
            "success": False,
            "auth_method": "imap_smtp",
            "error": "Password não configurada",
        }

    # Validar campos obrigatórios antes de tentar a ligação
    email_addr = email_config.get("email_address", "")
    imap_server = email_config.get("imap_server", "")
    smtp_server = email_config.get("smtp_server", "")
    missing = []
    if not email_addr:
        missing.append("endereço de email")
    if not imap_server:
        missing.append("servidor IMAP")
    if not smtp_server:
        missing.append("servidor SMTP")
    if missing:
        logger.warning(f"[EMAIL-TEST] Campos em falta para teste: {', '.join(missing)}")
        return {
            "success": False,
            "auth_method": "imap_smtp",
            "error": f"Campos obrigatórios em falta: {', '.join(missing)}. Preencha a configuração de email antes de testar.",
        }

    password = encryption_service.decrypt(encrypted_password)
    if not password or password.startswith("ENC:"):
        return {
            "success": False,
            "auth_method": "imap_smtp",
            "error": "Falha ao desencriptar a password",
        }

    def _parse_error(raw_err: str, protocol: str) -> str:
        """Convert raw IMAP/SMTP error strings to user-friendly Portuguese messages."""
        err_lower = raw_err.lower()
        if "authenticationfailed" in err_lower or "incorrect authentication" in err_lower or "auth" in err_lower and "fail" in err_lower:
            return f"{protocol}: Credenciais inválidas. Verifique o email e a password da conta de email."
        if "connection refused" in err_lower:
            return f"{protocol}: Servidor não acessível. Verifique o endereço do servidor."
        if "connection timed out" in err_lower or "timeout" in err_lower:
            return f"{protocol}: Tempo de conexão esgotado. Verifique a rede e as portas ({'IMAP: 993' if protocol == 'IMAP' else 'SMTP: 465'})."
        if "ssl" in err_lower or "certificate" in err_lower:
            return f"{protocol}: Erro de certificado SSL/TLS. Verifique a configuração de segurança."
        if "too many" in err_lower or "rate limit" in err_lower:
            return f"{protocol}: Limite de tentativas excedido. Aguarde alguns minutos e tente novamente."
        if "not found" in err_lower or "name resolution" in err_lower:
            return f"{protocol}: Servidor não encontrado. Verifique o endereço do servidor."
        if "network is unreachable" in err_lower or "unreachable" in err_lower:
            return f"{protocol}: Rede inacessível. Verifique a ligação à internet."
        return f"{protocol}: Não foi possível conectar. Verifique as configurações e tente novamente."

    def _test():
        imap_ok = False
        smtp_ok = False
        error = None
        email_addr = email_config.get("email_address", "")
        imap_host = email_config.get("imap_server", "")
        smtp_host = email_config.get("smtp_server", "")

        logger.info(f"[EMAIL-TEST] A testar IMAP {imap_host}:{email_config.get('imap_port', 993)} para {email_addr}")

        # Test IMAP (timeout de 25s)
        try:
            ssl_context = ssl.create_default_context(cafile=certifi.where())
            imap_port = email_config.get("imap_port", 993) or 993
            mail = imaplib.IMAP4_SSL(
                imap_host,
                int(imap_port),
                ssl_context=ssl_context,
                timeout=25,
            )
            mail.login(email_addr, password)
            mail.logout()
            imap_ok = True
            logger.info(f"[EMAIL-TEST] IMAP OK para {email_addr}")
        except Exception as e:
            error = _parse_error(str(e), "IMAP")
            logger.warning(f"[EMAIL-TEST] IMAP FALHOU para {email_addr}: {e}")

        # Test SMTP (timeout de 25s)
        try:
            ssl_context = ssl.create_default_context(cafile=certifi.where())
            smtp_port = email_config.get("smtp_port", 465) or 465
            logger.info(f"[EMAIL-TEST] A testar SMTP {smtp_host}:{smtp_port} para {email_addr}")
            smtp_server = smtplib.SMTP_SSL(
                smtp_host,
                int(smtp_port),
                context=ssl_context,
                timeout=25,
            )
            smtp_server.login(email_addr, password)
            smtp_server.quit()
            smtp_ok = True
            logger.info(f"[EMAIL-TEST] SMTP OK para {email_addr}")
        except Exception as e:
            smtp_err = _parse_error(str(e), "SMTP")
            error = f"{error}. {smtp_err}" if error else smtp_err
            logger.warning(f"[EMAIL-TEST] SMTP FALHOU para {email_addr}: {e}")

        return {
            "success": imap_ok and smtp_ok,
            "auth_method": "imap_smtp",
            "imap_connected": imap_ok,
            "smtp_connected": smtp_ok,
            "gmail_api_connected": False,
            "error": error if not (imap_ok and smtp_ok) else None,
        }

    loop = asyncio.get_event_loop()
    try:
        return await asyncio.wait_for(
            loop.run_in_executor(_legacy_executor, _test),
            timeout=60.0,  # 60s total para IMAP + SMTP
        )
    except asyncio.TimeoutError:
        logger.error("[EMAIL-TEST] Timeout (60s) a testar ligação IMAP/SMTP")
        return {
            "success": False,
            "auth_method": "imap_smtp",
            "imap_connected": False,
            "smtp_connected": False,
            "gmail_api_connected": False,
            "error": "Tempo de conexão esgotado (60s). O servidor pode estar inacessível a partir desta infraestrutura. Verifique se as portas IMAP (993) e SMTP (465) estão abertas.",
        }

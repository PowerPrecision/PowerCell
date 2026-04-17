"""
====================================================================
GMAIL API SERVICE - Motor de Leitura/Envio via Google OAuth
====================================================================
Serviço para ler e enviar emails usando a Gmail API oficial
(_google-api-python-client_) com refresh_token OAuth 2.0.

UTILIZAÇÃO:
- Worker: Descarregar emails da caixa partilhada de um departamento
- Endpoint POST /emails/send: Enviar emails como a conta partilhada
- Webmail: Listar emails da caixa partilhada

PRÉ-REQUISITOS:
- GOOGLE_CLIENT_ID e GOOGLE_CLIENT_SECRET no .env
- google_refresh_token encriptado na DB (obtido via fluxo OAuth)
- Scopes: mail.google.com/, gmail.readonly, gmail.compose, gmail.modify

SEGURANÇA:
- O refresh_token é desencriptado apenas no momento do uso
- O access_token é obtido automaticamente via refresh (expira em ~1h)
- As credenciais não são guardadas em memória entre pedidos
====================================================================
"""

import logging
import base64
import email
import re
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders as email_encoders

from database import db
from services.encryption import encryption_service

logger = logging.getLogger(__name__)


class GmailAPIError(Exception):
    """Erro específico do Gmail API Service."""
    pass


def _get_google_oauth_config() -> Dict[str, str]:
    """Lê a config OAuth do ambiente. Levanta ValueError se não configurada."""
    from config import GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET

    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        raise ValueError(
            "Google OAuth não configurado. Defina GOOGLE_CLIENT_ID e "
            "GOOGLE_CLIENT_SECRET nas variáveis de ambiente."
        )

    return {
        "client_id": GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
    }


def _build_credentials(refresh_token: str) -> Any:
    """
    Constrói credenciais OAuth2 a partir de um refresh_token.

    O access_token é obtido automaticamente pelo Google Auth library
    quando a credencial é usada pela primeira vez (auto-refresh).

    Args:
        refresh_token: Refresh token do Google OAuth (plain-text).

    Returns:
        Credentials object do google.oauth2.

    Raises:
        ImportError: Se as bibliotecas Google não estiverem instaladas.
    """
    try:
        from google.oauth2.credentials import Credentials
    except ImportError:
        raise ImportError(
            "Bibliotecas Google OAuth não instaladas. "
            "Execute: pip install google-auth-oauthlib google-api-python-client"
        )

    google_cfg = _get_google_oauth_config()

    return Credentials(
        token=None,  # Será obtido via refresh
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=google_cfg["client_id"],
        client_secret=google_cfg["client_secret"],
        scopes=[
            "https://mail.google.com/",
            "https://www.googleapis.com/auth/gmail.readonly",
            "https://www.googleapis.com/auth/gmail.compose",
            "https://www.googleapis.com/auth/gmail.modify",
        ],
    )


def _build_gmail_service(refresh_token: str):
    """
    Constrói o serviço Gmail API v1.

    Args:
        refresh_token: Refresh token do Google OAuth (plain-text).

    Returns:
        Resource object do Gmail API v1.

    Raises:
        GmailAPIError: Se não conseguir autenticar.
    """
    try:
        from googleapiclient.discovery import build
        from googleapiclient.errors import HttpError
    except ImportError:
        raise ImportError("google-api-python-client não instalado")

    try:
        creds = _build_credentials(refresh_token)
        service = build("gmail", "v1", credentials=creds)
        return service
    except Exception as e:
        logger.error(f"[Gmail API] Erro ao construir serviço: {e}")
        raise GmailAPIError(f"Erro ao autenticar com Google: {e}")


def _parse_gmail_message(msg_data: Dict, account_email: str) -> Dict[str, Any]:
    """
    Parseia uma mensagem do formato Gmail API para o formato interno do CRM.

    Args:
        msg_data: Dicionário da mensagem Gmail API (com 'id', 'payload', etc.)
        account_email: Email da conta (para determinar direction).

    Returns:
        Dict compatível com o schema de EmailMessage do CRM.
    """
    headers = {h["name"].lower(): h["value"] for h in msg_data.get("payload", {}).get("headers", [])}

    from_email_raw = headers.get("from", "")
    to_emails_raw = headers.get("to", "")
    cc_emails_raw = headers.get("cc", "")
    subject = headers.get("subject", "(Sem assunto)")
    date_str = headers.get("date", "")
    message_id = headers.get("message-id", "")

    # Extrair endereço de email limpo
    from_email = re.search(r'<([^>]+)>', from_email_raw)
    from_email = (from_email.group(1).lower() if from_email else from_email_raw.strip().lower())

    to_emails = []
    for addr in to_emails_raw.split(","):
        match = re.search(r'<([^>]+)>', addr.strip())
        if match:
            to_emails.append(match.group(1).lower())
        elif "@" in addr:
            to_emails.append(addr.strip().lower())

    cc_emails = []
    if cc_emails_raw:
        for addr in cc_emails_raw.split(","):
            match = re.search(r'<([^>]+)>', addr.strip())
            if match:
                cc_emails.append(match.group(1).lower())
            elif "@" in addr:
                cc_emails.append(addr.strip().lower())

    # Decodificar subject
    subject = _decode_header_value(subject)

    # Extrair corpo
    body_text, body_html = _extract_body_from_payload(msg_data.get("payload", {}))

    # Direção
    direction = "sent" if from_email == account_email.lower() else "received"

    # Parsear data
    sent_at = None
    if date_str:
        try:
            from email.utils import parsedate_to_datetime
            parsed = parsedate_to_datetime(date_str)
            sent_at = parsed.isoformat()
        except Exception:
            sent_at = datetime.now(timezone.utc).isoformat()
    else:
        sent_at = datetime.now(timezone.utc).isoformat()

    # Anexos
    attachments = []
    for part in msg_data.get("payload", {}).get("parts", []):
        if part.get("filename") and part.get("body", {}).get("attachmentId"):
            attachments.append({
                "filename": part["filename"],
                "content_type": part.get("mimeType", "application/octet-stream"),
                "size": part.get("body", {}).get("size", 0),
                "gmail_attachment_id": part["body"]["attachmentId"],
            })

    return {
        "message_id": message_id,
        "gmail_message_id": msg_data.get("id", ""),
        "from_email": from_email,
        "to_emails": to_emails,
        "cc_emails": cc_emails,
        "subject": subject,
        "body": body_text,
        "body_html": body_html,
        "attachments": attachments,
        "date": sent_at,
        "direction": direction,
        "source": "gmail_api",
    }


def _decode_header_value(value: str) -> str:
    """Decodifica um header MIME (RFC 2047)."""
    if not value:
        return ""
    try:
        from email.header import decode_header
        decoded_parts = decode_header(value)
        result = []
        for content, charset in decoded_parts:
            if isinstance(content, bytes):
                try:
                    result.append(content.decode(charset or "utf-8", errors="replace"))
                except Exception:
                    result.append(content.decode("utf-8", errors="replace"))
            else:
                result.append(str(content))
        return " ".join(result)
    except Exception:
        return value


def _extract_body_from_payload(payload: Dict) -> tuple:
    """
    Extrai texto e HTML do payload Gmail API.

    Args:
        payload: Dicionário payload da mensagem Gmail API.

    Returns:
        tuple: (body_text, body_html)
    """
    body_text = ""
    body_html = ""
    mime_type = payload.get("mimeType", "")

    if mime_type.startswith("multipart/"):
        parts = payload.get("parts", [])
        for part in parts:
            sub_mime = part.get("mimeType", "")
            if sub_mime == "text/plain" and not body_text:
                data = part.get("body", {}).get("data", "")
                if data:
                    body_text = base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
            elif sub_mime == "text/html" and not body_html:
                data = part.get("body", {}).get("data", "")
                if data:
                    body_html = base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
            elif sub_mime.startswith("multipart/"):
                # Recursão para multipart aninhado (ex: multipart/alternative)
                sub_text, sub_html = _extract_body_from_payload(part)
                if sub_text and not body_text:
                    body_text = sub_text
                if sub_html and not body_html:
                    body_html = sub_html
    elif mime_type == "text/plain":
        data = payload.get("body", {}).get("data", "")
        if data:
            body_text = base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
    elif mime_type == "text/html":
        data = payload.get("body", {}).get("data", "")
        if data:
            body_html = base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")

    return body_text, body_html


# ====================================================================
# FUNÇÕES PÚBLICAS
# ====================================================================

async def get_shared_email_config(role: str) -> Optional[Dict]:
    """
    Obtém a config de email partilhado para um role.

    Args:
        role: Role do departamento (ex: 'indexacao').

    Returns:
        Dict com a config, ou None se não existir.
    """
    config = await db.shared_role_email_configs.find_one(
        {"role": role},
        {"_id": 0},
    )
    return config


async def gmail_api_list_messages(
    role: str,
    query: str = "",
    max_results: int = 50,
    page_token: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Lista mensagens da caixa Gmail via API.

    Args:
        role: Role do departamento.
        query: Query Gmail (ex: 'is:unread', 'after:2024/01/01').
        max_results: Máximo de mensagens (default 50, max 500).
        page_token: Token de paginação.

    Returns:
        Dict com 'messages' (lista), 'next_page_token', 'result_size_estimate'.

    Raises:
        GmailAPIError: Se a config não existir ou OAuth falhar.
    """
    config = await get_shared_email_config(role)
    if not config:
        raise GmailAPIError(f"Config de email partilhado não encontrada para role '{role}'")

    encrypted_rt = config.get("google_refresh_token", "")
    if not encrypted_rt:
        raise GmailAPIError(f"Google OAuth não configurado para role '{role}'")

    refresh_token = encryption_service.decrypt(encrypted_rt)
    if not refresh_token or refresh_token == encrypted_rt:
        raise GmailAPIError(f"Erro ao desencriptar refresh_token para role '{role}'")

    account_email = config.get("email_address", "")

    try:
        service = _build_gmail_service(refresh_token)

        # Listar IDs de mensagens
        list_kwargs = {
            "userId": "me",
            "maxResults": min(max_results, 500),
        }
        if query:
            list_kwargs["q"] = query
        if page_token:
            list_kwargs["pageToken"] = page_token

        result = service.users().messages().list(**list_kwargs).execute()

        messages = result.get("messages", [])
        next_page_token = result.get("nextPageToken")
        result_size = result.get("resultSizeEstimate", 0)

        # Buscar detalhes de cada mensagem
        detailed_messages = []
        for msg_ref in messages:
            try:
                msg_data = service.users().messages().get(
                    userId="me",
                    id=msg_ref["id"],
                    format="metadata",
                    metadataHeaders=["From", "To", "Cc", "Subject", "Date", "Message-ID"],
                ).execute()
                parsed = _parse_gmail_message(msg_data, account_email)
                detailed_messages.append(parsed)
            except Exception as e:
                logger.warning(f"[Gmail API] Erro ao buscar mensagem {msg_ref['id']}: {e}")

        # Atualizar last_sync_at
        await db.shared_role_email_configs.update_one(
            {"role": role},
            {"$set": {"last_sync_at": datetime.now(timezone.utc).isoformat()}},
        )

        return {
            "messages": detailed_messages,
            "next_page_token": next_page_token,
            "result_size_estimate": result_size,
            "account_email": account_email,
        }

    except Exception as e:
        if "GmailAPIError" in type(e).__name__ or "ImportError" in type(e).__name__:
            raise
        logger.error(f"[Gmail API] Erro ao listar mensagens: {e}")
        raise GmailAPIError(f"Erro Gmail API: {e}")


async def gmail_api_get_message(role: str, gmail_message_id: str) -> Dict[str, Any]:
    """
    Obtém uma mensagem completa da Gmail API (incluindo corpo).

    Args:
        role: Role do departamento.
        gmail_message_id: ID da mensagem no Gmail.

    Returns:
        Dict com a mensagem completa.

    Raises:
        GmailAPIError: Se a config não existir ou OAuth falhar.
    """
    config = await get_shared_email_config(role)
    if not config:
        raise GmailAPIError(f"Config não encontrada para role '{role}'")

    encrypted_rt = config.get("google_refresh_token", "")
    if not encrypted_rt:
        raise GmailAPIError(f"Google OAuth não configurado para role '{role}'")

    refresh_token = encryption_service.decrypt(encrypted_rt)
    if not refresh_token or refresh_token == encrypted_rt:
        raise GmailAPIError(f"Erro ao desencriptar refresh_token para role '{role}'")

    account_email = config.get("email_address", "")

    try:
        service = _build_gmail_service(refresh_token)

        msg_data = service.users().messages().get(
            userId="me",
            id=gmail_message_id,
            format="full",
        ).execute()

        parsed = _parse_gmail_message(msg_data, account_email)
        return parsed

    except Exception as e:
        if "GmailAPIError" in type(e).__name__ or "ImportError" in type(e).__name__:
            raise
        logger.error(f"[Gmail API] Erro ao buscar mensagem {gmail_message_id}: {e}")
        raise GmailAPIError(f"Erro Gmail API: {e}")


async def gmail_api_send_message(
    role: str,
    to_emails: List[str],
    subject: str,
    body_text: str,
    body_html: Optional[str] = None,
    cc_emails: Optional[List[str]] = None,
    bcc_emails: Optional[List[str]] = None,
    reply_to_message_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Envia um email via Gmail API.

    Args:
        role: Role do departamento.
        to_emails: Lista de destinatários.
        subject: Assunto.
        body_text: Corpo em texto simples.
        body_html: Corpo em HTML (opcional).
        cc_emails: Lista de CC (opcional).
        bcc_emails: Lista de BCC (opcional).
        reply_to_message_id: ID da mensagem a responder (opcional, para threading).

    Returns:
        Dict com 'success', 'message_id', 'thread_id'.

    Raises:
        GmailAPIError: Se a config não existir ou OAuth falhar.
    """
    config = await get_shared_email_config(role)
    if not config:
        raise GmailAPIError(f"Config não encontrada para role '{role}'")

    encrypted_rt = config.get("google_refresh_token", "")
    if not encrypted_rt:
        raise GmailAPIError(f"Google OAuth não configurado para role '{role}'")

    refresh_token = encryption_service.decrypt(encrypted_rt)
    if not refresh_token or refresh_token == encrypted_rt:
        raise GmailAPIError(f"Erro ao desencriptar refresh_token para role '{role}'")

    account_email = config.get("email_address", "")

    try:
        service = _build_gmail_service(refresh_token)

        # Construir mensagem MIME
        if body_html:
            msg = MIMEMultipart("alternative")
            msg.attach(MIMEText(body_text, "plain", "utf-8"))
            msg.attach(MIMEText(body_html, "html", "utf-8"))
        else:
            msg = MIMEText(body_text, "plain", "utf-8")

        msg["To"] = ", ".join(to_emails)
        msg["From"] = account_email
        msg["Subject"] = subject

        if cc_emails:
            msg["Cc"] = ", ".join(cc_emails)

        # Thread headers para resposta
        if reply_to_message_id:
            msg["In-Reply-To"] = reply_to_message_id
            msg["References"] = reply_to_message_id

        # Encode e enviar via Gmail API
        raw_message = base64.urlsafe_b64encode(msg.as_bytes()).decode()

        send_kwargs = {
            "userId": "me",
            "body": {"raw": raw_message},
        }

        result = service.users().messages().send(**send_kwargs).execute()

        gmail_msg_id = result.get("id", "")
        thread_id = result.get("threadId", "")

        logger.info(
            f"[Gmail API] Email enviado via role '{role}': "
            f"to={to_emails}, subject='{subject}', msg_id={gmail_msg_id}"
        )

        return {
            "success": True,
            "message_id": gmail_msg_id,
            "thread_id": thread_id,
            "account_email": account_email,
        }

    except Exception as e:
        if "GmailAPIError" in type(e).__name__ or "ImportError" in type(e).__name__:
            raise
        logger.error(f"[Gmail API] Erro ao enviar email: {e}")
        raise GmailAPIError(f"Erro Gmail API ao enviar: {e}")


async def gmail_api_sync_to_db(
    role: str,
    days: int = 3,
    max_emails: int = 100,
) -> Dict[str, Any]:
    """
    Sincroniza emails da Gmail API para a coleção `emails` do CRM.

    Esta função é chamada pelo worker para manter a caixa partilhada
    do departamento sincronizada com a base de dados.

    Args:
        role: Role do departamento.
        days: Dias para retroceder (default 3).
        max_emails: Máximo de emails a processar (default 100).

    Returns:
        Dict com 'success', 'total_synced', 'total_duplicates', 'errors'.
    """
    import uuid

    config = await get_shared_email_config(role)
    if not config:
        return {"success": False, "error": f"Config não encontrada para role '{role}'"}

    encrypted_rt = config.get("google_refresh_token", "")
    if not encrypted_rt:
        return {"success": False, "error": f"Google OAuth não configurado para role '{role}'"}

    refresh_token = encryption_service.decrypt(encrypted_rt)
    if not refresh_token or refresh_token == encrypted_rt:
        return {"success": False, "error": f"Erro ao desencriptar refresh_token"}

    account_email = config.get("email_address", "")

    try:
        from datetime import timedelta
        service = _build_gmail_service(refresh_token)

        # Calcular data de início
        after_date = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y/%m/%d")
        query = f"after:{after_date}"

        # Listar mensagens
        list_result = service.users().messages().list(
            userId="me",
            q=query,
            maxResults=min(max_emails, 500),
        ).execute()

        message_refs = list_result.get("messages", [])
        total_synced = 0
        total_duplicates = 0
        total_errors = 0

        logger.info(
            f"[Gmail Sync] Role '{role}': {len(message_refs)} mensagens encontradas "
            f"(desde {after_date})"
        )

        for msg_ref in message_refs:
            try:
                msg_data = service.users().messages().get(
                    userId="me",
                    id=msg_ref["id"],
                    format="full",
                ).execute()

                parsed = _parse_gmail_message(msg_data, account_email)
                internal_msg_id = parsed.get("message_id", "")

                if not internal_msg_id:
                    continue

                # Verificar duplicado
                existing = await db.emails.find_one({
                    "message_id": internal_msg_id,
                    "source": "gmail_api",
                    "shared_role": role,
                })

                if existing:
                    total_duplicates += 1
                    continue

                # Guardar na DB
                email_doc = {
                    "id": str(uuid.uuid4()),
                    "process_id": None,
                    "direction": parsed.get("direction", "received"),
                    "from_email": parsed.get("from_email", ""),
                    "to_emails": parsed.get("to_emails", []),
                    "cc_emails": parsed.get("cc_emails", []),
                    "bcc_emails": [],
                    "subject": parsed.get("subject", ""),
                    "body": parsed.get("body", ""),
                    "body_html": parsed.get("body_html", ""),
                    "attachments": parsed.get("attachments", []),
                    "status": "synced",
                    "sent_at": parsed.get("date", ""),
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "created_by": None,
                    "notes": f"Gmail API sync - role:{role}",
                    "synced": True,
                    "account": f"gmail_{role}",
                    "message_id": internal_msg_id,
                    "gmail_message_id": parsed.get("gmail_message_id", ""),
                    "shared_role": role,
                    "is_read": parsed.get("direction") == "sent",
                    "is_starred": False,
                    "is_archived": False,
                    "source": "gmail_api",
                }

                await db.emails.insert_one(email_doc)
                total_synced += 1

            except Exception as e:
                logger.warning(f"[Gmail Sync] Erro ao processar mensagem {msg_ref['id']}: {e}")
                total_errors += 1

        # Atualizar estatísticas
        await db.shared_role_email_configs.update_one(
            {"role": role},
            {
                "$set": {
                    "last_sync_at": datetime.now(timezone.utc).isoformat(),
                    "total_emails_synced": (config.get("total_emails_synced", 0) + total_synced),
                }
            },
        )

        logger.info(
            f"[Gmail Sync] Role '{role}' concluído: "
            f"{total_synced} novos, {total_duplicates} duplicados, {total_errors} erros"
        )

        return {
            "success": True,
            "total_synced": total_synced,
            "total_duplicates": total_duplicates,
            "total_errors": total_errors,
            "role": role,
            "account_email": account_email,
        }

    except Exception as e:
        if "GmailAPIError" in type(e).__name__ or "ImportError" in type(e).__name__:
            return {"success": False, "error": str(e)}
        logger.error(f"[Gmail Sync] Erro ao sincronizar role '{role}': {e}")
        return {"success": False, "error": str(e)}

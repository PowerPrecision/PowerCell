"""
====================================================================
EMAIL SERVICE - CREDITOIMO (v2.0 - API TRANSACIONAL)
====================================================================
Sistema moderno de envio de emails usando APIs transacionais.

ARQUITETURA:
- EmailProvider (classe abstrata) - interface para providers
- SendGridProvider - implementação SendGrid
- ResendProvider - implementação Resend (alternativa)
- SMTPProvider - fallback legado

VANTAGENS sobre SMTP:
- Não-bloqueante (async/await)
- Melhor deliverability (IPs com boa reputação)
- Analytics e tracking integrados
- Rate limiting automático
- Retry automático

CONFIGURAÇÃO:
- EMAIL_PROVIDER: "sendgrid" | "resend" | "smtp"
- EMAIL_API_KEY: API key do provider
- EMAIL_FROM: Endereço de envio
- SMTP_* variáveis mantidas como fallback

====================================================================
"""
import os
import ssl
import smtplib
import logging
import asyncio
from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dataclasses import dataclass
from enum import Enum

import aiohttp

logger = logging.getLogger(__name__)


# ====================================================================
# CONFIGURAÇÃO
# ====================================================================
class EmailProviderType(str, Enum):
    SENDGRID = "sendgrid"
    RESEND = "resend"
    SMTP = "smtp"


# Configuração do Provider
EMAIL_PROVIDER = os.environ.get("EMAIL_PROVIDER", "sendgrid").lower()
EMAIL_API_KEY = os.environ.get("EMAIL_API_KEY", "")
EMAIL_FROM = os.environ.get("EMAIL_FROM", "noreply@powerealestate.pt")
EMAIL_FROM_NAME = os.environ.get("EMAIL_FROM_NAME", "Power Real Estate & Precision Crédito")

# SMTP Fallback
SMTP_SERVER = os.environ.get("SMTP_SERVER", "")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "465"))
SMTP_EMAIL = os.environ.get("SMTP_EMAIL", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")

# Configurações gerais
COMPANY_NAME = "Power Real Estate & Precision Crédito"
COMPANY_WEBSITE = "https://powerealestate.pt"
COMPANY_PHONE = "+351 XXX XXX XXX"

# Timeout para requests HTTP
HTTP_TIMEOUT = aiohttp.ClientTimeout(total=30)


# ====================================================================
# DATA CLASSES
# ====================================================================
@dataclass
class EmailMessage:
    """Estrutura de uma mensagem de email."""
    to: str
    subject: str
    text_body: str
    html_body: Optional[str] = None
    from_email: Optional[str] = None
    from_name: Optional[str] = None
    reply_to: Optional[str] = None
    cc: Optional[List[str]] = None
    bcc: Optional[List[str]] = None
    tags: Optional[List[str]] = None
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class EmailResult:
    """Resultado do envio de email."""
    success: bool
    message_id: Optional[str] = None
    provider: Optional[str] = None
    error: Optional[str] = None
    raw_response: Optional[Dict] = None


# ====================================================================
# CLASSE ABSTRATA - EMAIL PROVIDER
# ====================================================================
class EmailProvider(ABC):
    """
    Interface abstrata para providers de email.
    Todas as implementações devem herdar desta classe.
    """
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Nome do provider."""
        pass
    
    @abstractmethod
    async def send(self, message: EmailMessage) -> EmailResult:
        """Envia um email."""
        pass
    
    @abstractmethod
    def is_configured(self) -> bool:
        """Verifica se o provider está configurado."""
        pass
    
    async def send_batch(self, messages: List[EmailMessage]) -> List[EmailResult]:
        """Envia múltiplos emails (implementação default sequencial)."""
        results = []
        for msg in messages:
            result = await self.send(msg)
            results.append(result)
        return results


# ====================================================================
# SENDGRID PROVIDER
# ====================================================================
class SendGridProvider(EmailProvider):
    """
    Provider SendGrid usando API v3.
    Documentação: https://docs.sendgrid.com/api-reference/mail-send
    """
    
    API_URL = "https://api.sendgrid.com/v3/mail/send"
    
    def __init__(self, api_key: str):
        self.api_key = api_key
    
    @property
    def name(self) -> str:
        return "sendgrid"
    
    def is_configured(self) -> bool:
        return bool(self.api_key)
    
    async def send(self, message: EmailMessage) -> EmailResult:
        """Envia email via SendGrid API."""
        if not self.is_configured():
            return EmailResult(
                success=False,
                provider=self.name,
                error="SendGrid API key not configured"
            )
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        # Construir payload SendGrid
        payload = {
            "personalizations": [{
                "to": [{"email": message.to}]
            }],
            "from": {
                "email": message.from_email or EMAIL_FROM,
                "name": message.from_name or EMAIL_FROM_NAME
            },
            "subject": message.subject,
            "content": []
        }
        
        # Adicionar conteúdo
        payload["content"].append({
            "type": "text/plain",
            "value": message.text_body
        })
        
        if message.html_body:
            payload["content"].append({
                "type": "text/html",
                "value": message.html_body
            })
        
        # Campos opcionais
        if message.reply_to:
            payload["reply_to"] = {"email": message.reply_to}
        
        if message.cc:
            payload["personalizations"][0]["cc"] = [{"email": e} for e in message.cc]
        
        if message.bcc:
            payload["personalizations"][0]["bcc"] = [{"email": e} for e in message.bcc]
        
        if message.tags:
            payload["categories"] = message.tags[:10]  # SendGrid limita a 10 categorias
        
        try:
            async with aiohttp.ClientSession(timeout=HTTP_TIMEOUT) as session:
                async with session.post(self.API_URL, headers=headers, json=payload) as response:
                    
                    if response.status in (200, 201, 202):
                        message_id = response.headers.get("X-Message-Id", "")
                        logger.info(f"[EMAIL:{self.name}] Sent to {message.to}, ID: {message_id}")
                        return EmailResult(
                            success=True,
                            message_id=message_id,
                            provider=self.name
                        )
                    else:
                        error_body = await response.text()
                        logger.error(f"[EMAIL:{self.name}] Failed: {response.status} - {error_body}")
                        return EmailResult(
                            success=False,
                            provider=self.name,
                            error=f"HTTP {response.status}: {error_body}"
                        )
                        
        except asyncio.TimeoutError:
            logger.error(f"[EMAIL:{self.name}] Timeout sending to {message.to}")
            return EmailResult(success=False, provider=self.name, error="Request timeout")
        except Exception as e:
            logger.error(f"[EMAIL:{self.name}] Exception: {str(e)}")
            return EmailResult(success=False, provider=self.name, error=str(e))


# ====================================================================
# RESEND PROVIDER (Alternativa moderna)
# ====================================================================
class ResendProvider(EmailProvider):
    """
    Provider Resend - alternativa moderna ao SendGrid.
    Documentação: https://resend.com/docs/api-reference
    """
    
    API_URL = "https://api.resend.com/emails"
    
    def __init__(self, api_key: str):
        self.api_key = api_key
    
    @property
    def name(self) -> str:
        return "resend"
    
    def is_configured(self) -> bool:
        return bool(self.api_key)
    
    async def send(self, message: EmailMessage) -> EmailResult:
        """Envia email via Resend API."""
        if not self.is_configured():
            return EmailResult(
                success=False,
                provider=self.name,
                error="Resend API key not configured"
            )
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        from_address = f"{message.from_name or EMAIL_FROM_NAME} <{message.from_email or EMAIL_FROM}>"
        
        payload = {
            "from": from_address,
            "to": [message.to],
            "subject": message.subject,
            "text": message.text_body
        }
        
        if message.html_body:
            payload["html"] = message.html_body
        
        if message.reply_to:
            payload["reply_to"] = message.reply_to
        
        if message.cc:
            payload["cc"] = message.cc
        
        if message.bcc:
            payload["bcc"] = message.bcc
        
        if message.tags:
            payload["tags"] = [{"name": tag} for tag in message.tags[:5]]
        
        try:
            async with aiohttp.ClientSession(timeout=HTTP_TIMEOUT) as session:
                async with session.post(self.API_URL, headers=headers, json=payload) as response:
                    response_data = await response.json()
                    
                    if response.status == 200:
                        message_id = response_data.get("id", "")
                        logger.info(f"[EMAIL:{self.name}] Sent to {message.to}, ID: {message_id}")
                        return EmailResult(
                            success=True,
                            message_id=message_id,
                            provider=self.name,
                            raw_response=response_data
                        )
                    else:
                        error = response_data.get("message", str(response_data))
                        logger.error(f"[EMAIL:{self.name}] Failed: {error}")
                        return EmailResult(
                            success=False,
                            provider=self.name,
                            error=error,
                            raw_response=response_data
                        )
                        
        except asyncio.TimeoutError:
            logger.error(f"[EMAIL:{self.name}] Timeout sending to {message.to}")
            return EmailResult(success=False, provider=self.name, error="Request timeout")
        except Exception as e:
            logger.error(f"[EMAIL:{self.name}] Exception: {str(e)}")
            return EmailResult(success=False, provider=self.name, error=str(e))


# ====================================================================
# SMTP PROVIDER (FALLBACK LEGADO)
# ====================================================================
class SMTPProvider(EmailProvider):
    """
    Provider SMTP legado - usado como fallback.
    NOTA: Este provider é bloqueante e roda num executor.
    """
    
    def __init__(self, server: str, port: int, email: str, password: str):
        self.server = server
        self.port = port
        self.email = email
        self.password = password
    
    @property
    def name(self) -> str:
        return "smtp"
    
    def is_configured(self) -> bool:
        return all([self.server, self.port, self.email, self.password])
    
    def _send_sync(self, message: EmailMessage) -> EmailResult:
        """Envio síncrono via SMTP (roda em thread pool)."""
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = message.subject
            msg["From"] = f"{message.from_name or EMAIL_FROM_NAME} <{message.from_email or self.email}>"
            msg["To"] = message.to
            
            if message.reply_to:
                msg["Reply-To"] = message.reply_to
            
            # Texto simples
            part1 = MIMEText(message.text_body, "plain", "utf-8")
            msg.attach(part1)
            
            # HTML
            if message.html_body:
                part2 = MIMEText(message.html_body, "html", "utf-8")
                msg.attach(part2)
            
            context = ssl.create_default_context()
            
            with smtplib.SMTP_SSL(self.server, self.port, context=context, timeout=30) as server:
                server.login(self.email, self.password)
                server.sendmail(self.email, message.to, msg.as_bytes())
            
            logger.info(f"[EMAIL:{self.name}] Sent to {message.to}")
            return EmailResult(success=True, provider=self.name)
            
        except Exception as e:
            logger.error(f"[EMAIL:{self.name}] Failed: {str(e)}")
            return EmailResult(success=False, provider=self.name, error=str(e))
    
    async def send(self, message: EmailMessage) -> EmailResult:
        """Envia email via SMTP (em thread pool para não bloquear)."""
        if not self.is_configured():
            return EmailResult(
                success=False,
                provider=self.name,
                error="SMTP not configured"
            )
        
        # Executar em thread pool para não bloquear o event loop
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._send_sync, message)


# ====================================================================
# EMAIL SERVICE (FACADE)
# ====================================================================
class EmailService:
    """
    Serviço de email com fallback automático.
    
    Ordem de prioridade:
    1. Provider configurado (SendGrid/Resend)
    2. SMTP como fallback
    3. Simulação (log only)
    """
    
    def __init__(self):
        self._primary_provider: Optional[EmailProvider] = None
        self._fallback_provider: Optional[EmailProvider] = None
        self._initialize_providers()
    
    def _initialize_providers(self):
        """Inicializa providers baseado na configuração."""
        
        # Provider primário
        if EMAIL_API_KEY:
            if EMAIL_PROVIDER == EmailProviderType.SENDGRID:
                self._primary_provider = SendGridProvider(EMAIL_API_KEY)
                logger.info("[EMAIL] Primary provider: SendGrid")
            elif EMAIL_PROVIDER == EmailProviderType.RESEND:
                self._primary_provider = ResendProvider(EMAIL_API_KEY)
                logger.info("[EMAIL] Primary provider: Resend")
        
        # Fallback SMTP
        if SMTP_SERVER and SMTP_EMAIL and SMTP_PASSWORD:
            self._fallback_provider = SMTPProvider(
                SMTP_SERVER, SMTP_PORT, SMTP_EMAIL, SMTP_PASSWORD
            )
            logger.info("[EMAIL] Fallback provider: SMTP")
        
        if not self._primary_provider and not self._fallback_provider:
            logger.warning("[EMAIL] No email provider configured - emails will be simulated")
    
    async def send(self, message: EmailMessage) -> EmailResult:
        """
        Envia email com fallback automático.
        
        1. Tenta provider primário (API)
        2. Se falhar, tenta SMTP
        3. Se tudo falhar, simula e loga
        """
        # Tentar provider primário
        if self._primary_provider and self._primary_provider.is_configured():
            result = await self._primary_provider.send(message)
            if result.success:
                return result
            logger.warning(f"[EMAIL] Primary provider failed: {result.error}")
        
        # Tentar fallback SMTP
        if self._fallback_provider and self._fallback_provider.is_configured():
            logger.info("[EMAIL] Trying SMTP fallback...")
            result = await self._fallback_provider.send(message)
            if result.success:
                return result
            logger.warning(f"[EMAIL] Fallback SMTP failed: {result.error}")
        
        # Simulação (nenhum provider disponível)
        logger.warning(f"[EMAIL SIMULATED] To: {message.to}, Subject: {message.subject}")
        return EmailResult(
            success=False,
            provider="simulated",
            error="No email provider configured"
        )
    
    async def send_batch(self, messages: List[EmailMessage]) -> List[EmailResult]:
        """Envia múltiplos emails em paralelo."""
        tasks = [self.send(msg) for msg in messages]
        return await asyncio.gather(*tasks)
    
    def is_configured(self) -> bool:
        """Verifica se algum provider está configurado."""
        return (
            (self._primary_provider and self._primary_provider.is_configured()) or
            (self._fallback_provider and self._fallback_provider.is_configured())
        )
    
    @property
    def active_provider(self) -> Optional[str]:
        """Retorna nome do provider activo."""
        if self._primary_provider and self._primary_provider.is_configured():
            return self._primary_provider.name
        if self._fallback_provider and self._fallback_provider.is_configured():
            return self._fallback_provider.name
        return None


# ====================================================================
# INSTÂNCIA GLOBAL
# ====================================================================
email_service = EmailService()


# ====================================================================
# FUNÇÕES DE CONVENIÊNCIA (Retrocompatibilidade)
# ====================================================================
async def send_email_notification(
    to_email: str, 
    subject: str, 
    body: str, 
    html_body: str = None,
    notification_type: str = "general",
    check_preferences: bool = True
) -> bool:
    """
    Função de conveniência para enviar emails.
    Mantém compatibilidade com código existente.
    
    Args:
        to_email: Email de destino
        subject: Assunto do email
        body: Corpo em texto
        html_body: Corpo em HTML (opcional)
        notification_type: Tipo de notificação para verificar preferências
        check_preferences: Se deve verificar preferências (default: True)
    """
    # Verificar preferências de notificação
    if check_preferences:
        should_send = await _check_email_preference(to_email, notification_type)
        if not should_send:
            logger.info(f"[EMAIL] Skipped (preference disabled) to {to_email}, type: {notification_type}")
            return True  # Retorna True para não causar erros no código chamador
    
    message = EmailMessage(
        to=to_email,
        subject=subject,
        text_body=body,
        html_body=html_body
    )
    result = await email_service.send(message)
    return result.success


async def _check_email_preference(email: str, notification_type: str) -> bool:
    """
    Verifica se o utilizador quer receber este tipo de email.
    
    Args:
        email: Email do utilizador
        notification_type: Tipo de notificação (new_process, status_change, etc.)
        
    Returns:
        True se deve enviar, False se não deve
    """
    try:
        from database import db
        
        # Encontrar utilizador pelo email
        user = await db.users.find_one({"email": email}, {"id": 1})
        if not user:
            # Utilizador não encontrado - pode ser cliente externo, enviar
            return True
        
        # Buscar preferências
        prefs = await db.notification_preferences.find_one(
            {"user_id": user["id"]}, 
            {"_id": 0}
        )
        
        if not prefs:
            # Sem preferências definidas - usar defaults (não enviar a maioria)
            # Por default, só enviamos emails importantes
            important_types = ["deadline_reminder", "urgent", "daily_summary", "weekly_report"]
            return notification_type in important_types
        
        # Se é utilizador de teste, não enviar emails
        if prefs.get("is_test_user", False):
            return False
        
        # Mapear tipo de notificação para preferência
        type_to_pref = {
            "new_process": "email_new_process",
            "status_change": "email_status_change",
            "document_upload": "email_document_upload",
            "task_assigned": "email_task_assigned",
            "deadline_reminder": "email_deadline_reminder",
            "daily_summary": "email_daily_summary",
            "weekly_report": "email_weekly_report",
            "urgent": "email_urgent_only",
        }
        
        pref_key = type_to_pref.get(notification_type, None)
        
        if pref_key:
            return prefs.get(pref_key, False)
        
        # Para tipos não mapeados, verificar se só quer urgentes
        if prefs.get("email_urgent_only", True):
            return notification_type == "urgent"
        
        return True
        
    except Exception as e:
        logger.error(f"Error checking email preference: {e}")
        # Em caso de erro, enviar para não perder emails importantes
        return True


def is_email_configured() -> bool:
    """Verifica se o serviço de email está configurado."""
    return email_service.is_configured()

"""
====================================================================
MODELOS DE EMAILS - CREDITOIMO
====================================================================
Modelos Pydantic para o sistema de histórico de emails.
====================================================================
"""

from pydantic import BaseModel, EmailStr
from typing import Optional, List
from datetime import datetime
from enum import Enum


class EmailDirection(str, Enum):
    SENT = "sent"
    RECEIVED = "received"


class EmailStatus(str, Enum):
    SENT = "sent"
    FAILED = "failed"
    PENDING = "pending"
    DRAFT = "draft"


class EmailAttachment(BaseModel):
    """Anexo de email."""
    filename: str
    size: Optional[int] = None
    content_type: Optional[str] = None
    url: Optional[str] = None


class EmailCreate(BaseModel):
    """Criar registo de email."""
    process_id: str
    direction: EmailDirection
    from_email: str
    to_emails: List[str]
    cc_emails: Optional[List[str]] = []
    bcc_emails: Optional[List[str]] = []
    subject: str
    body: str
    body_html: Optional[str] = None
    attachments: Optional[List[EmailAttachment]] = []
    status: EmailStatus = EmailStatus.SENT
    sent_at: Optional[str] = None
    notes: Optional[str] = None


class EmailUpdate(BaseModel):
    """Atualizar registo de email."""
    subject: Optional[str] = None
    body: Optional[str] = None
    notes: Optional[str] = None
    status: Optional[EmailStatus] = None


class EmailResponse(BaseModel):
    """Resposta de email."""
    id: str
    process_id: str
    client_name: Optional[str] = None
    direction: EmailDirection
    from_email: str
    to_emails: List[str]
    cc_emails: Optional[List[str]] = []
    bcc_emails: Optional[List[str]] = []
    subject: str
    body: str
    body_html: Optional[str] = None
    attachments: Optional[List[EmailAttachment]] = []
    status: EmailStatus
    sent_at: Optional[str] = None
    created_at: str
    created_by: Optional[str] = None
    created_by_name: Optional[str] = None
    notes: Optional[str] = None

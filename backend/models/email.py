"""
====================================================================
MODELOS DE EMAILS - POWERCELL
====================================================================
Modelos Pydantic para o sistema de histórico de emails.
Inclui suporte para marcações, anexos avançados e templates.
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


class EmailMarkType(str, Enum):
    """Tipos de marcação de email."""
    IMPORTANT = "important"
    READ = "read"
    UNREAD = "unread"
    STARRED = "starred"
    ARCHIVED = "archived"
    SPAM = "spam"


class EmailAttachment(BaseModel):
    """Anexo de email."""
    id: Optional[str] = None
    filename: str
    size: Optional[int] = None
    content_type: Optional[str] = None
    url: Optional[str] = None
    content_id: Optional[str] = None  # Para imagens embutidas
    is_inline: bool = False
    preview_url: Optional[str] = None  # URL para preview (imagens, PDFs)
    downloaded: bool = False


class EmailMark(BaseModel):
    """Marcação de email."""
    type: EmailMarkType
    marked_at: str
    marked_by: str


class EmailTemplate(BaseModel):
    """Template de resposta rápida."""
    id: str
    name: str
    subject: Optional[str] = None
    body: str
    category: Optional[str] = None  # "resposta", "follow-up", "agradecimento", etc.
    created_by: Optional[str] = None
    is_default: bool = False


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
    """Actualizar registo de email."""
    subject: Optional[str] = None
    body: Optional[str] = None
    notes: Optional[str] = None
    status: Optional[EmailStatus] = None
    is_important: Optional[bool] = None
    is_read: Optional[bool] = None
    is_starred: Optional[bool] = None
    is_archived: Optional[bool] = None
    labels: Optional[List[str]] = None


class EmailResponse(BaseModel):
    """Resposta de email."""
    id: str
    process_id: Optional[str] = None
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
    # Novos campos de marcação
    is_important: bool = False
    is_read: bool = False
    is_starred: bool = False
    is_archived: bool = False
    labels: Optional[List[str]] = []
    account: Optional[str] = None


class EmailFilter(BaseModel):
    """Filtros avançados para pesquisa de emails."""
    process_id: Optional[str] = None
    direction: Optional[EmailDirection] = None
    account: Optional[str] = None  # "precision" ou "power"
    is_important: Optional[bool] = None
    is_read: Optional[bool] = None
    is_starred: Optional[bool] = None
    is_archived: Optional[bool] = None
    has_attachments: Optional[bool] = None
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    search_term: Optional[str] = None
    labels: Optional[List[str]] = []


class EmailTemplateCreate(BaseModel):
    """Criar template de email."""
    name: str
    subject: Optional[str] = None
    body: str
    category: Optional[str] = None
    is_default: bool = False


class EmailTemplateResponse(BaseModel):
    """Resposta de template de email."""
    id: str
    name: str
    subject: Optional[str] = None
    body: str
    category: Optional[str] = None
    created_by: Optional[str] = None
    created_at: str
    is_default: bool = False
    usage_count: int = 0


class EmailSendRequest(BaseModel):
    """Payload para envio de email via webmail."""
    to_emails: List[str]
    subject: str
    body: str = ""
    body_html: Optional[str] = None
    cc_emails: Optional[List[str]] = None
    process_id: Optional[str] = None
    attachment_ids: Optional[List[str]] = None


class LabelCreateRequest(BaseModel):
    """Payload para criar uma label."""
    name: str
    color: str


class LabelUpdateRequest(BaseModel):
    """Payload para atualizar uma label."""
    name: Optional[str] = None
    color: Optional[str] = None

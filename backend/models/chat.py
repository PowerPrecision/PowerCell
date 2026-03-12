"""
====================================================================
MODELOS DE CHAT - CREDITOIMO
====================================================================
Modelos Pydantic para o sistema de chat interno.
====================================================================
"""

from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime


# ============= MENSAGENS =============

class ChatMessageCreate(BaseModel):
    """Criar nova mensagem."""
    receiver_id: Optional[str] = None  # Para chat direto
    group_id: Optional[str] = None     # Para chat em grupo
    content: str
    process_id: Optional[str] = None   # Opcional: associar a um processo
    reply_to: Optional[str] = None     # ID da mensagem à qual se está a responder


class ChatMessageReaction(BaseModel):
    """Reação a uma mensagem."""
    message_id: str
    reaction: str  # Emoji ou código de reação


class ChatMessageEdit(BaseModel):
    """Editar mensagem."""
    message_id: str
    content: str


# ============= GRUPOS =============

class ChatGroupCreate(BaseModel):
    """Criar novo grupo."""
    name: str
    description: Optional[str] = None
    members: List[str] = []  # Lista de user_ids


class ChatGroupUpdate(BaseModel):
    """Atualizar grupo."""
    name: Optional[str] = None
    description: Optional[str] = None
    add_members: Optional[List[str]] = None
    remove_members: Optional[List[str]] = None


# ============= PESQUISA =============

class ChatSearchQuery(BaseModel):
    """Pesquisa de mensagens."""
    query: str
    user_id: Optional[str] = None      # Filtrar por utilizador
    group_id: Optional[str] = None     # Filtrar por grupo
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    limit: int = 50


# ============= TYPING =============

class TypingIndicator(BaseModel):
    """Indicador de digitação."""
    receiver_id: Optional[str] = None
    group_id: Optional[str] = None
    is_typing: bool


# ============= RESPOSTAS =============

class ChatConversation(BaseModel):
    """Resumo de uma conversa."""
    user_id: Optional[str] = None
    user_name: Optional[str] = None
    user_role: Optional[str] = None
    group_id: Optional[str] = None
    group_name: Optional[str] = None
    last_message: str
    last_message_time: str
    unread_count: int
    is_group: bool = False
    members: Optional[List[dict]] = None


class ChatGroupInfo(BaseModel):
    """Informações de um grupo."""
    id: str
    name: str
    description: Optional[str]
    created_by: str
    created_at: str
    members: List[dict]
    is_member: bool = True


class ChatMessageResponse(BaseModel):
    """Resposta de mensagem."""
    id: str
    sender_id: str
    sender_name: str
    receiver_id: Optional[str]
    group_id: Optional[str]
    content: str
    reply_to: Optional[dict] = None
    reactions: List[dict] = []
    attachments: List[dict] = []
    edited: bool = False
    edited_at: Optional[str] = None
    read: bool = False
    created_at: str

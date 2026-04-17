"""
<<<<<<< HEAD
====================================================================
MODELOS DE ANÚNCIOS - MURAL DA EQUIPA
====================================================================
Pydantic models para criação e resposta de anúncios.

Autor: PowerCell Development Team
====================================================================
"""

from pydantic import BaseModel, Field
from typing import Optional


class AnnouncementCreate(BaseModel):
    """Modelo para criação de um novo anúncio."""
    content: str = Field(
        ...,
        max_length=2000,
        description="Conteúdo do anúncio (máximo 2000 caracteres)"
    )


class AnnouncementResponse(BaseModel):
    """Modelo de resposta de um anúncio."""
    id: str = Field(..., description="Identificador único do anúncio")
    content: str = Field(..., description="Conteúdo do anúncio")
    author_id: str = Field(..., description="ID do autor do anúncio")
    author_name: str = Field(..., description="Nome do autor do anúncio")
    author_role: Optional[str] = Field(None, description="Cargo do autor do anúncio")
    created_at: str = Field(..., description="Data de criação (ISO 8601)")
=======
Modelo de Anúncios — Mural da Equipa (Feed Interno)

PORQUÊ: Permite comunicação interna entre membros da equipa.
Qualquer utilizador autenticado pode publicar mensagens visíveis a toda a equipa.

CAMPOS:
- id: Identificador único (UUID)
- content: Conteúdo da mensagem (texto)
- author_id: ID do utilizador que publicou
- author_name: Nome do utilizador que publicou
- created_at: Data de criação (ISO 8601)
- likes: Lista de IDs dos utilizadores que deram "Gosto"
- read_by: Lista de IDs dos utilizadores que visualizaram a mensagem
"""
from pydantic import BaseModel, Field
from typing import List, Optional


class AnnouncementCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=2000, description="Conteúdo da mensagem")


class AnnouncementResponse(BaseModel):
    id: str
    content: str
    author_id: str
    author_name: str
    created_at: str
    likes: List[str] = Field(default_factory=list, description="IDs dos utilizadores que deram gosto")
    read_by: List[str] = Field(default_factory=list, description="IDs dos utilizadores que leram")
>>>>>>> 0e005d2 (feat: add likes and read receipts to team mural)

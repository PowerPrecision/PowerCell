"""
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

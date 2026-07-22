"""Pydantic models for minutas API.

Extraído de `routes/minutas.py`.
Do **not** overwrite services/rgpd_minutas.py.
"""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel


class MinutaCreate(BaseModel):
    """Dados para criar uma minuta."""
    titulo: str
    categoria: str = "contrato"
    descricao: Optional[str] = None
    conteudo: str
    tags: Optional[List[str]] = []


class MinutaUpdate(BaseModel):
    """Dados para actualizar uma minuta."""
    titulo: Optional[str] = None
    categoria: Optional[str] = None
    descricao: Optional[str] = None
    conteudo: Optional[str] = None
    tags: Optional[List[str]] = None

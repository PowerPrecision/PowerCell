"""
====================================================================
MODELO DE LINKS TEMPORÁRIOS - CREDITOIMO
====================================================================
Links temporários para:
- Clientes carregarem documentação
- Clientes receberem documentação
====================================================================
"""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum


class TempLinkType(str, Enum):
    """Tipo de link temporário."""
    UPLOAD = "upload"      # Cliente carrega documentos
    DOWNLOAD = "download"  # Cliente recebe documentos


class TempLinkStatus(str, Enum):
    """Estado do link temporário."""
    PENDING = "pending"      # Ainda não usado
    USED = "used"            # Já foi usado
    EXPIRED = "expired"      # Expirou
    CANCELLED = "cancelled"  # Cancelado manualmente


class TempLinkCreate(BaseModel):
    """Dados para criar um link temporário."""
    process_id: str
    link_type: TempLinkType
    expires_in_hours: int = Field(default=72, ge=1, le=168)  # 1h a 7 dias
    max_uses: int = Field(default=1, ge=1, le=10)  # Máximo de utilizações
    description: Optional[str] = None
    file_paths: Optional[List[str]] = None  # Para links de download
    notify_email: bool = True  # Enviar email ao cliente


class TempLinkResponse(BaseModel):
    """Resposta com dados do link temporário."""
    id: str
    token: str
    process_id: str
    client_name: str
    client_email: Optional[str]
    link_type: TempLinkType
    status: TempLinkStatus
    url: str
    expires_at: str
    created_at: str
    created_by: str
    max_uses: int
    current_uses: int
    description: Optional[str] = None
    file_paths: Optional[List[str]] = None
    used_at: Optional[str] = None
    uploaded_files: Optional[List[dict]] = None  # Ficheiros carregados pelo cliente


class TempLinkUseRequest(BaseModel):
    """Request para usar um link temporário."""
    token: str
    files: Optional[List[dict]] = None  # Para upload: lista de ficheiros

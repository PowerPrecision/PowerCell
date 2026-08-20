"""
====================================================================
MODELO: Company (Multi-Tenant)
====================================================================
Entidade de negócio "Empresa" — dados base, branding e configurações.

COLEÇÃO MONGODB: companies
INDEX: { name: 1 } (unique)
====================================================================
"""

from pydantic import BaseModel, ConfigDict, Field
from typing import Optional, List


class CompanyCreate(BaseModel):
    """Payload para criar uma empresa."""
    name: str = Field(..., min_length=1, max_length=200, description="Nome da empresa")
    nif: Optional[str] = Field(None, max_length=20, description="NIF da empresa")
    address: Optional[str] = Field(None, max_length=500, description="Morada")
    phone: Optional[str] = Field(None, max_length=30, description="Telefone principal")
    email: Optional[str] = Field(None, max_length=200, description="Email de contacto")
    website: Optional[str] = Field(None, max_length=300, description="Website")
    logo_url: Optional[str] = Field(None, description="URL do logótipo (S3)")
    email_sync_enabled: bool = Field(False, description="Ativar sincronização de e-mail")
    is_active: bool = Field(True, description="Estado da empresa (activa / inactiva)")


class CompanyUpdate(BaseModel):
    """Payload para atualizar uma empresa (todos os campos opcionais)."""
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    nif: Optional[str] = Field(None, max_length=20)
    address: Optional[str] = Field(None, max_length=500)
    phone: Optional[str] = Field(None, max_length=30)
    email: Optional[str] = Field(None, max_length=200)
    website: Optional[str] = Field(None, max_length=300)
    logo_url: Optional[str] = None
    email_sync_enabled: Optional[bool] = None
    is_active: Optional[bool] = None


class CompanyResponse(BaseModel):
    """Resposta GET — campos visíveis no frontend."""
    model_config = ConfigDict(extra="allow")

    id: str
    name: str
    nif: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    website: Optional[str] = None
    logo_url: Optional[str] = None
    email_sync_enabled: bool = False
    is_active: bool = True
    total_users: int = 0
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class CompanyListResponse(BaseModel):
    """Lista de empresas com total."""
    companies: List[CompanyResponse]
    total: int
"""
====================================================================
MODELO: Company (Multi-Tenant)
====================================================================
Entidade de negócio "Empresa" — dados base, branding e configurações.

COLEÇÃO MONGODB: companies
INDEX: { name: 1 } (unique)
====================================================================
"""

from pydantic import BaseModel, ConfigDict, Field, field_validator
from typing import Optional, List
import re

from utils.validation import validate_nif


def _validate_optional_company_nif(value: Optional[str]) -> Optional[str]:
    """NIF/NIPC opcional com checksum módulo 11 (não confiar só no frontend)."""
    if value is None:
        return None
    cleaned = str(value).strip()
    if not cleaned:
        return None
    is_valid, error = validate_nif(cleaned)
    if not is_valid:
        raise ValueError(error)
    return re.sub(r"\D", "", cleaned)


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
    smtp_email: Optional[str] = Field(None, max_length=200, description="Email SMTP da empresa (envio em nome da empresa)")
    smtp_password: Optional[str] = Field(None, max_length=500, description="Password SMTP da empresa")
    smtp_host: Optional[str] = Field(None, max_length=200, description="Servidor SMTP da empresa")
    smtp_port: Optional[int] = Field(None, description="Porto SMTP da empresa")
    imap_email: Optional[str] = Field(None, max_length=200, description="Email IMAP da empresa (leitura de Webmail)")
    imap_password: Optional[str] = Field(None, max_length=500, description="Password IMAP da empresa")
    imap_host: Optional[str] = Field(None, max_length=200, description="Servidor IMAP da empresa")
    imap_port: Optional[int] = Field(None, description="Porto IMAP da empresa")

    @field_validator("nif")
    @classmethod
    def validate_nif_field(cls, v):
        return _validate_optional_company_nif(v)


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
    smtp_email: Optional[str] = Field(None, max_length=200, description="Email SMTP da empresa (envio em nome da empresa)")
    smtp_password: Optional[str] = Field(None, max_length=500, description="Password SMTP da empresa")
    smtp_host: Optional[str] = Field(None, max_length=200, description="Servidor SMTP da empresa")
    smtp_port: Optional[int] = Field(None, description="Porto SMTP da empresa")
    imap_email: Optional[str] = Field(None, max_length=200, description="Email IMAP da empresa (leitura de Webmail)")
    imap_password: Optional[str] = Field(None, max_length=500, description="Password IMAP da empresa")
    imap_host: Optional[str] = Field(None, max_length=200, description="Servidor IMAP da empresa")
    imap_port: Optional[int] = Field(None, description="Porto IMAP da empresa")

    @field_validator("nif")
    @classmethod
    def validate_nif_field(cls, v):
        return _validate_optional_company_nif(v)


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
    smtp_email: Optional[str] = None
    smtp_host: Optional[str] = None
    smtp_port: Optional[int] = None
    imap_email: Optional[str] = None
    imap_host: Optional[str] = None
    imap_port: Optional[int] = None
    total_users: int = 0
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class CompanyListResponse(BaseModel):
    """Lista de empresas com total."""
    companies: List[CompanyResponse]
    total: int


class CompanyEmailConnectionTest(BaseModel):
    """
    Payload para testar a ligação SMTP e/ou IMAP com os valores atuais do
    formulário de configuração de email de uma Empresa, sem gravar nada.
    SMTP e IMAP são testados de forma independente (podem ter contas diferentes).
    """
    company_id: Optional[str] = None  # BUGFIX (Fev 2026): resolve password guardada quando o formulário a deixa em branco
    smtp_email: Optional[str] = Field(None, max_length=200)
    smtp_password: Optional[str] = Field(None, max_length=500)
    smtp_host: Optional[str] = Field(None, max_length=200)
    smtp_port: Optional[int] = None
    imap_email: Optional[str] = Field(None, max_length=200)
    imap_password: Optional[str] = Field(None, max_length=500)
    imap_host: Optional[str] = Field(None, max_length=200)
    imap_port: Optional[int] = None

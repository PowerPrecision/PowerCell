"""
Modelos RGPD - Regulamento Geral sobre a Proteção de Dados

Este módulo contém os modelos para gestão de consentimentos RGPD,
incluindo tokens temporários para assinatura e histórico de consentimentos.
"""
from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import Optional, List
from enum import Enum
from datetime import datetime
import re


class DocumentTypeEnum(str, Enum):
    """Tipos de documento de identificação aceites."""
    BILHETE_IDENTIDADE = "bilhete_de_identidade"
    CARTAO_CIDADAO = "cartao_de_cidadao"
    PASSAPORTE = "passaporte"
    CARTA_CONDUCAO = "carta_de_conducao"
    AUTORIZACAO_RESIDENCIA = "autorizacao_de_residencia"


class RGPDStatusEnum(str, Enum):
    """Estados do consentimento RGPD."""
    PENDING = "pending"           # Enviado mas não assinado
    SIGNED = "signed"             # Assinado pelo cliente
    EXPIRED = "expired"           # Token expirado (24h)
    CANCELLED = "cancelled"       # Cancelado pelo utilizador


class RGPDConsentData(BaseModel):
    """
    Dados preenchidos pelo cliente no formulário RGPD.
    
    Estes dados são recolhidos quando o cliente assina o RGPD.
    """
    nome: str = Field(..., min_length=2, max_length=200, description="Nome completo")
    contribuinte: str = Field(..., min_length=9, max_length=9, description="NIF - 9 dígitos")
    tipo_documento: DocumentTypeEnum = Field(..., description="Tipo de documento de identificação")
    numero_documento: str = Field(..., min_length=1, max_length=30, description="Número do documento")
    validade_documento: Optional[str] = Field(None, max_length=20, description="Validade do documento")
    morada: str = Field(..., min_length=5, max_length=500, description="Morada completa")
    concelho: Optional[str] = Field(None, max_length=100, description="Concelho")
    codigo_postal: Optional[str] = Field(None, max_length=8, description="Código postal")
    assinatura: Optional[str] = Field(None, description="Assinatura em base64")
    data_assinatura: Optional[str] = Field(None, description="Data da assinatura")
    
    @field_validator('contribuinte', mode='before')
    @classmethod
    def validate_nif(cls, v):
        """Valida NIF português."""
        if not v:
            raise ValueError("Contribuinte é obrigatório")
        
        # Limpar espaços e caracteres especiais
        v_clean = re.sub(r'[^\d]', '', str(v))
        
        if len(v_clean) != 9:
            raise ValueError("NIF deve ter 9 dígitos")
        
        if not v_clean.isdigit():
            raise ValueError("NIF deve conter apenas dígitos")
        
        # Validar checksum
        digits = [int(d) for d in v_clean]
        weights = [9, 8, 7, 6, 5, 4, 3, 2]
        total_sum = sum(d * w for d, w in zip(digits[:8], weights))
        remainder = total_sum % 11
        check_digit = 11 - remainder if remainder > 1 else 0
        
        if check_digit != digits[8]:
            raise ValueError("NIF inválido")
        
        return v_clean
    
    @field_validator('nome', 'morada', mode='before')
    @classmethod
    def sanitize_text(cls, v):
        """Sanitiza campos de texto."""
        if not v:
            return v
        # Remover HTML
        v = re.sub(r'<[^>]+>', '', str(v))
        return v.strip()


class RGPDCreate(BaseModel):
    """Modelo para criar um novo pedido de consentimento RGPD."""
    process_id: str = Field(..., description="ID do processo associado")
    client_name: str = Field(..., description="Nome do cliente")
    client_email: EmailStr = Field(..., description="Email do cliente para envio")


class RGPDRequest(BaseModel):
    """
    Pedido de consentimento RGPD.
    
    Contém o token temporário para validação do link.
    """
    id: str
    process_id: str
    client_name: str
    client_email: str
    token: str                               # Token único para validação
    token_expires_at: str                    # Expira em 24h
    status: RGPDStatusEnum = RGPDStatusEnum.PENDING
    consent_data: Optional[RGPDConsentData] = None
    created_at: str
    created_by: str                          # ID do utilizador que solicitou
    created_by_email: str                    # Email do utilizador (para enviar resposta)
    created_by_name: str                     # Nome do utilizador
    signed_at: Optional[str] = None
    pdf_url: Optional[str] = None            # URL do PDF assinado


class RGPDResponse(BaseModel):
    """Resposta do endpoint de RGPD."""
    id: str
    process_id: str
    client_name: str
    client_email: str
    status: RGPDStatusEnum
    token_expires_at: Optional[str] = None
    consent_data: Optional[dict] = None
    created_at: str
    created_by_name: str
    signed_at: Optional[str] = None
    pdf_url: Optional[str] = None


class RGPDPublicView(BaseModel):
    """
    Dados públicos para a página de RGPD.
    
    Não expõe informações sensíveis como o email do utilizador.
    """
    id: str
    client_name: str
    status: RGPDStatusEnum
    created_at: str
    expires_at: str
    valid: bool                              # Se o token ainda é válido


class RGPDStatusResponse(BaseModel):
    """Resposta para verificação de estado do RGPD."""
    has_rgpd: bool
    status: Optional[RGPDStatusEnum] = None
    signed_at: Optional[str] = None
    pdf_url: Optional[str] = None
    request_id: Optional[str] = None

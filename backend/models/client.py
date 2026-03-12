"""
Modelo de Cliente

Um cliente pode ter múltiplos processos de compra/financiamento.
Isto permite acompanhar diferentes negócios para o mesmo cliente.
"""

from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
import re


def validate_nif(nif: str) -> str:
    """Validar NIF português (9 dígitos numéricos)."""
    if not nif:
        return nif
    nif_clean = re.sub(r'[^\d]', '', nif)
    if len(nif_clean) != 9:
        raise ValueError(f"NIF deve ter 9 dígitos (recebido: {len(nif_clean)})")
    if not nif_clean.isdigit():
        raise ValueError("NIF deve conter apenas dígitos")
    return nif_clean


class ClientPersonalData(BaseModel):
    """Dados pessoais do cliente (imutáveis entre processos)."""
    nif: Optional[str] = None
    documento_id: Optional[str] = None
    data_nascimento: Optional[str] = None
    naturalidade: Optional[str] = None
    nacionalidade: Optional[str] = None
    morada_fiscal: Optional[str] = None
    estado_civil: Optional[str] = None
    profissao: Optional[str] = None
    nome_pai: Optional[str] = None
    nome_mae: Optional[str] = None
    
    @field_validator('nif', mode='before')
    @classmethod
    def validate_nif_field(cls, v):
        if v is None or v == '':
            return None
        return validate_nif(v)


class ClientFinancialData(BaseModel):
    """Dados financeiros do cliente (podem variar ao longo do tempo)."""
    rendimento_mensal: Optional[float] = None
    rendimento_bruto: Optional[float] = None
    rendimento_anual: Optional[float] = None
    outros_rendimentos: Optional[float] = None
    despesas_mensais: Optional[float] = None
    tipo_contrato: Optional[str] = None
    empresa: Optional[str] = None
    antiguidade_emprego: Optional[str] = None
    # Informação de crédito
    tem_creditos_activos: Optional[bool] = None
    valor_creditos_activos: Optional[float] = None
    # Última actualização
    data_actualizacao: Optional[str] = None


class ClientContact(BaseModel):
    """Informação de contacto."""
    email: Optional[str] = None
    email_secundario: Optional[str] = None
    telefone: Optional[str] = None
    telefone_secundario: Optional[str] = None


class Client(BaseModel):
    """
    Modelo de Cliente.
    
    Um cliente é uma entidade única identificada pelo NIF ou email.
    Pode ter múltiplos processos de compra/financiamento associados.
    """
    id: str
    nome: str
    contacto: ClientContact = Field(default_factory=ClientContact)
    dados_pessoais: ClientPersonalData = Field(default_factory=ClientPersonalData)
    dados_financeiros: ClientFinancialData = Field(default_factory=ClientFinancialData)
    
    # IDs dos processos associados
    process_ids: List[str] = Field(default_factory=list)
    
    # Co-compradores/cônjuges (para compras conjuntas)
    co_buyers: List[Dict[str, Any]] = Field(default_factory=list)
    co_applicants: List[Dict[str, Any]] = Field(default_factory=list)
    
    # Metadados
    fonte: Optional[str] = None  # origem do cliente (trello, manual, website, etc)
    tags: List[str] = Field(default_factory=list)
    notas: Optional[str] = None
    
    # Timestamps
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    created_by: Optional[str] = None


class ClientCreate(BaseModel):
    """Schema para criar um novo cliente."""
    nome: str
    email: Optional[str] = None
    telefone: Optional[str] = None
    nif: Optional[str] = None
    fonte: Optional[str] = None
    notas: Optional[str] = None
    
    @field_validator('nif', mode='before')
    @classmethod
    def validate_nif_field(cls, v):
        if v is None or v == '':
            return None
        return validate_nif(v)


class ClientUpdate(BaseModel):
    """Schema para actualizar um cliente."""
    nome: Optional[str] = None
    contacto: Optional[ClientContact] = None
    dados_pessoais: Optional[ClientPersonalData] = None
    dados_financeiros: Optional[ClientFinancialData] = None
    tags: Optional[List[str]] = None
    notas: Optional[str] = None


class ClientProcessLink(BaseModel):
    """Modelo para vincular um processo a um cliente existente."""
    client_id: str
    process_id: str
    relacao: str = "titular"  # titular, co-titular, representante


# Funções utilitárias

def find_or_create_client_key(email: str = None, nif: str = None, nome: str = None) -> str:
    """
    Gerar uma chave única para identificar um cliente.
    Prioridade: NIF > Email > Nome normalizado
    """
    if nif:
        return f"nif:{nif}"
    if email:
        return f"email:{email.lower().strip()}"
    if nome:
        # Normalizar nome
        nome_norm = nome.lower().strip()
        nome_norm = re.sub(r'[^\w\s]', '', nome_norm)
        nome_norm = re.sub(r'\s+', '_', nome_norm)
        return f"nome:{nome_norm}"
    return None

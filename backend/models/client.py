"""
Modelo de Cliente

O Cliente representa apenas a entidade pessoa/fiscal — dados pessoais e de contacto.
Dados financeiros e de negócio (2º Titular / Fiador, co-applicants, dados financeiros)
pertencem à entidade Processo, não ao Cliente.

Um cliente pode ter múltiplos processos de compra/financiamento.
Isto permite acompanhar diferentes negócios para o mesmo cliente.
"""

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
import re
import secrets
import string


# ---------------------------------------------------------------------------
# Validadores
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Modelos de dados incorporados
# ---------------------------------------------------------------------------

class ClientPersonalData(BaseModel):
    """
    Dados pessoais e de identificação fiscal do cliente.
    Dados financeiros e de negócio pertencem à entidade Processo.
    """
    model_config = ConfigDict(extra="allow")

    nif: Optional[str] = None
    documento_id: Optional[str] = None
    data_validade_cc: Optional[str] = None
    data_nascimento: Optional[str] = None
    birth_date: Optional[str] = None           # Alias para data_nascimento
    naturalidade: Optional[str] = None
    nacionalidade: Optional[str] = None
    morada_fiscal: Optional[str] = None
    estado_civil: Optional[str] = None
    profissao: Optional[str] = None
    nome_pai: Optional[str] = None
    nome_mae: Optional[str] = None
    sexo: Optional[str] = None                   # M ou F
    compra_tipo: Optional[str] = None            # [DEPRECATED] Campo de negócio — migrar para Processo na Fase 2
    menor_35_anos: Optional[bool] = None         # [DEPRECATED] Campo de negócio — migrar para Processo na Fase 2
    altura: Optional[str] = None                 # Altura em metros

    @field_validator('nif', mode='before')
    @classmethod
    def validate_nif_field(cls, v):
        if v is None or v == '':
            return None
        return validate_nif(v)


class ClientContact(BaseModel):
    """Informação de contacto do cliente."""
    email: Optional[str] = None
    email_secundario: Optional[str] = None
    telefone: Optional[str] = None
    telefone_secundario: Optional[str] = None


# ---------------------------------------------------------------------------
# Modelo principal
# ---------------------------------------------------------------------------

class Client(BaseModel):
    """
    Modelo de Cliente — entidade pessoa/fiscal.

    O cliente representa apenas a pessoa física e os seus dados de identificação.
    Dados financeiros e de negócio (2º Titular / Fiador, dados financeiros) pertencem
    ao Processo associado, não ao Cliente.
    """
    id: str
    nome: str
    contacto: ClientContact = Field(default_factory=ClientContact)
    dados_pessoais: ClientPersonalData = Field(default_factory=ClientPersonalData)

    # IDs dos processos associados
    process_ids: List[str] = Field(default_factory=list)

    # Portal de Cliente
    portal_access_code: Optional[str] = None  # Código de acesso fixo para login no portal (ex: A4B-9X2)

    # Metadados
    fonte: Optional[str] = None  # origem do cliente (trello, manual, website, etc)
    tags: List[str] = Field(default_factory=list)
    notas: Optional[str] = None

    # Timestamps
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    created_by: Optional[str] = None


# ---------------------------------------------------------------------------
# Schemas de entrada
# ---------------------------------------------------------------------------

class ClientCreate(BaseModel):
    """Schema para criar um novo cliente (apenas dados pessoais e de contacto)."""
    nome: str
    email: Optional[str] = None
    telefone: Optional[str] = None
    nif: Optional[str] = None
    fonte: Optional[str] = None
    notas: Optional[str] = None
    estado_civil: Optional[str] = None
    profissao: Optional[str] = None
    morada_fiscal: Optional[str] = None
    data_nascimento: Optional[str] = None

    @field_validator('nif', mode='before')
    @classmethod
    def validate_nif_field(cls, v):
        if v is None or v == '':
            return None
        return validate_nif(v)


class ClientUpdate(BaseModel):
    """Schema para actualizar um cliente (sem dados financeiros).
    
    NOTA: Campos como financial_data, titular2_data, personal_data, etc.
    enviados pelo frontend são ignorados silenciosamente (extra="ignore"),
    pois pertencem ao endpoint de Processos, não ao de Clientes.
    """
    model_config = ConfigDict(extra="ignore")
    nome: Optional[str] = None
    contacto: Optional[ClientContact] = None
    dados_pessoais: Optional[ClientPersonalData] = None
    tags: Optional[List[str]] = None
    notas: Optional[str] = None


# ---------------------------------------------------------------------------
# Schema de resposta
# ---------------------------------------------------------------------------

class ClientResponse(BaseModel):
    """Modelo de resposta para dados de cliente (sem dados financeiros)."""
    model_config = ConfigDict(extra="ignore")
    id: str
    nome: Optional[str] = None
    contacto: Optional[dict] = None
    dados_pessoais: Optional[dict] = None
    process_ids: Optional[List[str]] = None
    fonte: Optional[str] = None
    tags: Optional[List[str]] = None
    notas: Optional[str] = None
    portal_access_code: Optional[str] = None
    assigned_to: Optional[str] = None
    assigned_at: Optional[str] = None
    registration_completed: Optional[bool] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    created_by: Optional[str] = None


# ---------------------------------------------------------------------------
# Modelo de ligação
# ---------------------------------------------------------------------------

class ClientProcessLink(BaseModel):
    """Modelo para vincular um processo a um cliente existente."""
    client_id: str
    process_id: str
    relacao: str = "titular"  # titular, co-titular, representante


# ---------------------------------------------------------------------------
# Funções utilitárias
# ---------------------------------------------------------------------------

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


def generate_portal_access_code() -> str:
    """
    Gera um código alfanumérico amigável de 6 caracteres para acesso ao Portal.
    
    Formato: XXX-XXX (ex: A4B-9X2), usando letras maiúsculas e dígitos.
    Caracteres ambíguos são excluídos para evitar confusão:
    - Sem O/0, I/1, L/l (parecem iguais em muitos tipos de letra)
    
    O código tem 6 caracteres de entropia (aprox. 34 bits), o que oferece
    mais de 1.8 bilhões de combinações — suficiente para resistir a
    brute-force online quando combinado com rate limiting.
    
    Returns:
        str: Código no formato XXX-XXX (7 caracteres com hífen)
    """
    # Caracteres seguros: sem O/0 (confunde com zero), sem I/1/L (confunde com um)
    chars = string.ascii_uppercase.replace('O', '').replace('I', '').replace('L', '') + \
            string.digits.replace('0', '').replace('1', '')
    
    part1 = ''.join(secrets.choice(chars) for _ in range(3))
    part2 = ''.join(secrets.choice(chars) for _ in range(3))
    
    return f"{part1}-{part2}"


# NOTA: ClientFinancialData foi removido. Dados financeiros pertencem ao Processo.

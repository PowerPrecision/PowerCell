"""
Modelo de Processo — Entidade de Negócio / Dossier

LIMPEZA PROFUNDA (Fase 1 — separação definitiva):
O Processo representa APENAS o negócio/dossier. Não contém dados pessoais
do cliente (nome, NIF, email, telefone, morada, etc.). Todos os dados
pessoais pertencem exclusivamente à entidade Cliente, referenciada via
client_id (foreign key obrigatória).

Sub-modelos removidos:
- PersonalData       → pertence ao Cliente (models/client.py)
- Titular2Data       → pertence ao Cliente como co-titular
- FinancialData      → mistura de dados pessoais + processo; campos de
                       negócio promovidos ao nível raiz
- RealEstateData     → dados detalhados persistem no MongoDB (schemaless),
                       campos-chave promovidos ao nível raiz
- CreditData         → dados de aprovação bancária promovidos ao nível raiz

Validadores de NIF removidos → pertencem ao modelo de Cliente.

Um cliente pode ter múltiplos processos de compra/financiamento.
"""

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator
from typing import Optional, List
from datetime import datetime, timezone
from enum import Enum


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class ProcessType(str, Enum):
    """Tipo de processo — categoriza a natureza do negócio."""
    CREDITO_HABITACAO = "credito_habitacao"
    CREDITO_PESSOAL = "credito_pessoal"
    REFINANCIAMENTO = "refinanciamento"
    COMPRA_DIRETA = "compra_direta"
    ARRENDAMENTO = "arrendamento"
    CONSULTORIA = "consultoria"
    SEGUROS = "seguros"
    OUTRO = "outro"

    @classmethod
    def all_values(cls) -> list:
        return [t.value for t in cls]


class ProcessStatus(str, Enum):
    """Status do processo no workflow Kanban."""
    CLIENTES_ESPERA = "clientes_espera"
    DOCUMENTACAO = "documentacao"
    ANALISE = "analise"
    PRE_APROVACAO = "pre_aprovacao"
    CREDITO_APROVADO = "credito_aprovado"
    PEDIDO_AVALIACAO = "pedido_avaliacao"
    AVALIACAO = "avaliacao"
    CPCV = "cpcv"
    MINUTA = "minuta"
    ESCRITURA = "escritura"
    CONCLUIDO = "concluido"
    ARQUIVO = "arquivo"
    PERDIDO = "perdido"
    DESISTENCIAS = "desistencias"

    @classmethod
    def active_statuses(cls) -> list:
        return [s.value for s in cls if s.value not in ("concluido", "arquivo", "perdido", "desistencias")]


# ---------------------------------------------------------------------------
# Validadores internos (coerção de tipos, NÃO validação de NIF)
# ---------------------------------------------------------------------------

def _coerce_float(v):
    """Converte strings/ints para float graciosamente."""
    if v is None or v == '':
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        try:
            return float(v.replace(',', '.').strip())
        except (ValueError, TypeError):
            return None
    return v


def _coerce_int(v):
    """Converte strings/floats para int graciosamente."""
    if v is None or v == '':
        return None
    if isinstance(v, int):
        return v
    if isinstance(v, float):
        return int(v)
    if isinstance(v, str):
        try:
            return int(float(v))
        except (ValueError, TypeError):
            return None
    return v


def _coerce_bool(v):
    """Converte strings/ints para bool graciosamente."""
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        if v.lower() in ('true', '1', 'yes', 'sim'):
            return True
        if v.lower() in ('false', '0', 'no', 'nao', 'não', ''):
            return False
        return None
    if isinstance(v, (int, float)):
        return bool(v)
    return v


# ---------------------------------------------------------------------------
# Modelo principal
# ---------------------------------------------------------------------------

class Process(BaseModel):
    """
    Processo — Entidade de Negócio / Dossier.

    NÃO contém dados pessoais do cliente (nome, NIF, email, telefone, etc.).
    A referência ao cliente é feita via client_id (obrigatório).
    Para obter dados pessoais, consultar a coleção `clients` pelo client_id.

    Campos adicionais do MongoDB (ex: real_estate_data, financial_data antigos)
    são aceites via extra="allow" mas NÃO são validados nem expostos
    nos schemas de resposta.
    """
    model_config = ConfigDict(extra="allow")

    id: str
    process_number: Optional[int] = None

    # ── Referência ao Cliente (OBRIGATÓRIA) ──────────────────────────
    client_id: str = Field(..., description="ID do cliente associado (obrigatório — FK para clients)")
    client_ids: Optional[List[str]] = None  # Suporte N:M

    # ── Classificação ────────────────────────────────────────────────
    type: Optional[str] = None              # CH, Pessoal, Seguros, etc.
    process_type: Optional[str] = None      # Alias para type
    service_type: Optional[str] = None      # credito_apenas, imobiliario, completo
    status: Optional[str] = None            # Coluna do Kanban

    # ── Valores do Negócio ───────────────────────────────────────────
    value: Optional[float] = None           # Valor do imóvel / negócio
    loan_amount: Optional[float] = None     # Valor financiado
    interest_rate: Optional[float] = None   # Taxa de juro
    monthly_payment: Optional[float] = None # Prestação mensal
    loan_term_years: Optional[int] = None   # Prazo em anos
    bank_assigned: Optional[str] = None     # Banco atribuído
    honorarios: Optional[float] = None      # Honorários da intermediação
    comissao_banco: Optional[float] = None  # Comissão do banco
    capital_proprio: Optional[float] = None # Capital próprio do cliente

    # ── Aprovação / Avaliação Bancária ───────────────────────────────
    bank_approval_date: Optional[str] = None
    bank_approval_notes: Optional[str] = None
    valuation_value: Optional[float] = None
    valuation_date: Optional[str] = None
    valuation_bank: Optional[str] = None

    # ── Atribuições ──────────────────────────────────────────────────
    assigned_consultor_id: Optional[str] = None
    assigned_mediador_id: Optional[str] = None
    assigned_indexacao_id: Optional[str] = None
    assigned_parceiro_id: Optional[str] = None
    consultor_name: Optional[str] = None
    mediador_name: Optional[str] = None

    # ── Co-compradores e contrapartes (específicos do processo) ──────
    co_buyers: Optional[List[dict]] = None
    co_applicants: Optional[List[dict]] = None
    vendedor: Optional[dict] = None
    mediador: Optional[dict] = None

    # ── Imóvel ───────────────────────────────────────────────────────
    has_property: Optional[bool] = None

    # ── Documentos e Armazenamento ───────────────────────────────────
    documents: Optional[List[dict]] = None
    s3_folder: Optional[str] = None
    onedrive_links: Optional[List[dict]] = None

    # ── Metadados ────────────────────────────────────────────────────
    notes: Optional[str] = None
    prioridade: Optional[str] = None
    labels: Optional[List[str]] = None
    is_active: Optional[bool] = True
    source: Optional[str] = None
    monitored_emails: Optional[List[str]] = None
    trello_card_id: Optional[str] = None
    trello_list_id: Optional[str] = None
    is_data_confirmed: Optional[bool] = None
    ai_suggestions: Optional[List[dict]] = None

    # ── Datas ────────────────────────────────────────────────────────
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    created_by: Optional[str] = None

    # ── Validadores ──────────────────────────────────────────────────
    @field_validator('value', 'loan_amount', 'interest_rate', 'monthly_payment',
                     'honorarios', 'comissao_banco', 'capital_proprio',
                     'valuation_value', mode='before')
    @classmethod
    def coerce_float_fields(cls, v):
        return _coerce_float(v)

    @field_validator('loan_term_years', 'process_number', mode='before')
    @classmethod
    def coerce_int_fields(cls, v):
        return _coerce_int(v)

    @field_validator('has_property', 'is_active', 'is_data_confirmed', mode='before')
    @classmethod
    def coerce_bool_fields(cls, v):
        return _coerce_bool(v)


# ---------------------------------------------------------------------------
# Schemas de entrada
# ---------------------------------------------------------------------------

class ProcessCreate(BaseModel):
    """
    Schema para criar um novo processo.

    client_id é OBRIGATÓRIO — o cliente deve existir antes de criar o processo.
    NÃO contém dados pessoais do cliente.
    """
    client_id: str = Field(..., description="ID do cliente (obrigatório — referência à entidade Cliente)")
    process_type: str = Field(..., description="Tipo de processo (credito_habitacao, credito_pessoal, etc.)")
    service_type: Optional[str] = None
    value: Optional[float] = None
    loan_amount: Optional[float] = None
    notes: Optional[str] = None

    @field_validator('value', 'loan_amount', mode='before')
    @classmethod
    def coerce_float_fields(cls, v):
        return _coerce_float(v)


class ProcessUpdate(BaseModel):
    """
    Schema para actualizar um processo — APENAS dados de negócio.

    Dados pessoais do cliente NÃO são actualizados aqui.
    Usar o endpoint de clientes (PUT /api/clients/{id}).
    """
    # Classificação
    type: Optional[str] = None
    process_type: Optional[str] = None
    service_type: Optional[str] = None
    status: Optional[str] = None

    # Valores do Negócio
    value: Optional[float] = None
    loan_amount: Optional[float] = None
    interest_rate: Optional[float] = None
    monthly_payment: Optional[float] = None
    loan_term_years: Optional[int] = None
    bank_assigned: Optional[str] = None
    honorarios: Optional[float] = None
    comissao_banco: Optional[float] = None
    capital_proprio: Optional[float] = None

    # Aprovação bancária
    bank_approval_date: Optional[str] = None
    bank_approval_notes: Optional[str] = None
    valuation_value: Optional[float] = None
    valuation_date: Optional[str] = None
    valuation_bank: Optional[str] = None

    # Atribuições
    assigned_consultor_id: Optional[str] = None
    assigned_mediador_id: Optional[str] = None
    assigned_indexacao_id: Optional[str] = None
    assigned_parceiro_id: Optional[str] = None

    # Co-compradores e contrapartes
    co_buyers: Optional[List[dict]] = None
    co_applicants: Optional[List[dict]] = None
    vendedor: Optional[dict] = None
    mediador: Optional[dict] = None

    # Imóvel
    has_property: Optional[bool] = None

    # Documentos
    documents: Optional[List[dict]] = None
    s3_folder: Optional[str] = None
    onedrive_links: Optional[List[dict]] = None

    # Metadados
    notes: Optional[str] = None
    prioridade: Optional[str] = None
    labels: Optional[List[str]] = None
    is_active: Optional[bool] = None
    source: Optional[str] = None
    monitored_emails: Optional[List[str]] = None

    # Validadores
    @field_validator('value', 'loan_amount', 'interest_rate', 'monthly_payment',
                     'honorarios', 'comissao_banco', 'capital_proprio',
                     'valuation_value', mode='before')
    @classmethod
    def coerce_float_fields(cls, v):
        return _coerce_float(v)

    @field_validator('loan_term_years', mode='before')
    @classmethod
    def coerce_int_fields(cls, v):
        return _coerce_int(v)

    @field_validator('has_property', 'is_active', mode='before')
    @classmethod
    def coerce_bool_fields(cls, v):
        return _coerce_bool(v)


# ---------------------------------------------------------------------------
# Schema de resposta
# ---------------------------------------------------------------------------

class ProcessResponse(BaseModel):
    """
    Modelo de resposta para dados de processo.

    NÃO inclui dados pessoais do cliente (nome, NIF, email, telefone).
    O frontend deve obter dados do cliente via GET /api/clients/{client_id}
    ou o backend deve fazer o join internamente antes de enviar.

    Campos extra no MongoDB (ex: personal_data, financial_data antigos)
    são IGNORADOS via ConfigDict(extra="ignore").
    """
    model_config = ConfigDict(extra="ignore")

    id: str
    process_number: Optional[int] = None

    # ── Referência ao Cliente ────────────────────────────────────────
    client_id: str
    client_ids: Optional[List[str]] = None

    # ── Classificação ────────────────────────────────────────────────
    type: Optional[str] = None
    process_type: Optional[str] = None
    service_type: Optional[str] = None
    status: Optional[str] = None

    # ── Valores do Negócio ───────────────────────────────────────────
    value: Optional[float] = None
    loan_amount: Optional[float] = None
    interest_rate: Optional[float] = None
    monthly_payment: Optional[float] = None
    loan_term_years: Optional[int] = None
    bank_assigned: Optional[str] = None
    honorarios: Optional[float] = None
    comissao_banco: Optional[float] = None
    capital_proprio: Optional[float] = None

    # ── Aprovação / Avaliação Bancária ───────────────────────────────
    bank_approval_date: Optional[str] = None
    bank_approval_notes: Optional[str] = None
    valuation_value: Optional[float] = None
    valuation_date: Optional[str] = None
    valuation_bank: Optional[str] = None

    # ── Atribuições ──────────────────────────────────────────────────
    assigned_consultor_id: Optional[str] = None
    assigned_mediador_id: Optional[str] = None
    assigned_indexacao_id: Optional[str] = None
    assigned_parceiro_id: Optional[str] = None
    consultor_name: Optional[str] = None
    mediador_name: Optional[str] = None

    # ── Co-compradores e contrapartes ────────────────────────────────
    co_buyers: Optional[List[dict]] = None
    co_applicants: Optional[List[dict]] = None
    vendedor: Optional[dict] = None
    mediador: Optional[dict] = None

    # ── Imóvel ───────────────────────────────────────────────────────
    has_property: Optional[bool] = None

    # ── Documentos ───────────────────────────────────────────────────
    documents: Optional[List[dict]] = None
    s3_folder: Optional[str] = None
    onedrive_links: Optional[List[dict]] = None

    # ── Metadados ────────────────────────────────────────────────────
    notes: Optional[str] = None
    prioridade: Optional[str] = None
    labels: Optional[List[str]] = None
    is_active: Optional[bool] = None
    source: Optional[str] = None
    monitored_emails: Optional[List[str]] = None
    trello_card_id: Optional[str] = None
    trello_list_id: Optional[str] = None
    is_data_confirmed: Optional[bool] = None
    ai_suggestions: Optional[List[dict]] = None

    # ── Datas ────────────────────────────────────────────────────────
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    created_by: Optional[str] = None

    # ── Validadores ──────────────────────────────────────────────────
    @field_validator('has_property', 'is_active', 'is_data_confirmed', mode='before')
    @classmethod
    def coerce_bool_fields(cls, v):
        return _coerce_bool(v)

    @field_validator('value', 'loan_amount', 'interest_rate', 'monthly_payment',
                     'honorarios', 'comissao_banco', 'capital_proprio',
                     'valuation_value', mode='before')
    @classmethod
    def coerce_float_fields(cls, v):
        return _coerce_float(v)


# ---------------------------------------------------------------------------
# Schema para registo público (cria Cliente + Processo em simultâneo)
# ---------------------------------------------------------------------------

class PublicClientRegistration(BaseModel):
    """
    Modelo para registo público de clientes.

    Cria simultaneamente o Cliente e o Processo associado.
    Os campos pessoais (name, email, phone) são usados para criar o Cliente.
    Os campos de processo (process_type, etc.) são usados para criar o Processo.

    Este schema é a EXCEPÇÃO que contém dados pessoais — serve apenas como
    DTO (Data Transfer Object) para o formulário público. Os dados pessoais
    são encaminhados para a coleção `clients`, não para `processes`.
    """
    # Dados do Cliente (vão para a coleção `clients`)
    name: str = Field(..., min_length=2, max_length=200, description="Nome completo do cliente")
    email: EmailStr = Field(..., max_length=100, description="Email do cliente")
    phone: str = Field(..., min_length=9, max_length=20, description="Telefone do cliente")

    # Dados do Processo (vão para a coleção `processes`)
    process_type: str = Field(..., max_length=50, description="Tipo de processo")
    service_type: Optional[str] = None
    value: Optional[float] = None
    loan_amount: Optional[float] = None
    has_property: Optional[bool] = None

    # Dados adicionais (opcionais)
    custom_fields: Optional[dict] = None

    @field_validator('name', mode='before')
    @classmethod
    def sanitize_name(cls, v):
        if not v:
            return v
        try:
            from utils.input_sanitization import sanitize_name
            return sanitize_name(v, max_length=200)
        except ImportError:
            import re
            v = re.sub(r'<[^>]+>', '', str(v))
            return v.strip()[:200]

    @field_validator('phone', mode='before')
    @classmethod
    def sanitize_phone(cls, v):
        if not v:
            return v
        try:
            from utils.input_sanitization import sanitize_phone
            return sanitize_phone(v)
        except ImportError:
            import re
            return re.sub(r'[^\d+]', '', str(v))[:20]

    @field_validator('value', 'loan_amount', mode='before')
    @classmethod
    def coerce_float_fields(cls, v):
        return _coerce_float(v)

    @field_validator('has_property', mode='before')
    @classmethod
    def coerce_bool_fields(cls, v):
        return _coerce_bool(v)

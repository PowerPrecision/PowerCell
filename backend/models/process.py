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
from typing import Optional, List, Any
from enum import Enum

class ServiceTypeEnum(str, Enum):
    """Tipo de serviço do processo."""
    CREDITO_APENAS = "credito_apenas"       
    IMOBILIARIO_APENAS = "imobiliario_apenas"  
    COMPLETO = "completo"                   

class ProcessCategory:
    """Categoria do processo: crédito, imobiliário ou ambos."""
    CREDITO = "credito"
    IMOBILIARIA = "imobiliaria"
    AMBOS = "ambos"

class RealEstateData(BaseModel):
    """Dados imobiliários focados apenas no negócio."""
    model_config = ConfigDict(extra="allow")
    
    tipo_imovel: Optional[str] = None
    num_quartos: Optional[str] = None
    localizacao: Optional[str] = None
    caracteristicas: Optional[List[str]] = None
    outras_caracteristicas: Optional[str] = None
    outras_informacoes: Optional[str] = None
    ja_tem_imovel: Optional[bool] = None  
    has_property: Optional[bool] = None   
    area_pretendida: Optional[float] = None           
    valor_maximo_imovel: Optional[float] = None       
    finalidade: Optional[str] = None                
    ja_tem_casa_escolhida: Optional[bool] = None    
    caracteristicas_imovel: Optional[str] = None    
    
    # Dados do CPCV
    valor_imovel: Optional[float] = None
    codigo_postal: Optional[str] = None
    localidade: Optional[str] = None
    freguesia: Optional[str] = None
    concelho: Optional[str] = None
    tipologia: Optional[str] = None
    area_bruta: Optional[str] = None
    area_util: Optional[str] = None
    fracao: Optional[str] = None
    artigo_matricial: Optional[str] = None
    conservatoria: Optional[str] = None
    numero_predial: Optional[str] = None
    certificado_energetico: Optional[str] = None
    estacionamento: Optional[str] = None
    arrecadacao: Optional[str] = None
    descricao_imovel: Optional[str] = None
    valor_patrimonial: Optional[float] = None
    
    # Datas do CPCV
    data_cpcv: Optional[str] = None
    data_escritura_prevista: Optional[str] = None
    prazo_escritura_dias: Optional[int] = None
    data_entrega_chaves: Optional[str] = None
    
    # Condições
    condicao_suspensiva: Optional[str] = None
    observacoes_cpcv: Optional[str] = None

    @field_validator('valor_imovel', 'valor_patrimonial', 'area_pretendida',
                     'valor_maximo_imovel', mode='before')
    @classmethod
    def coerce_float_fields(cls, v):
        if v is None or v == '': return None
        if isinstance(v, (int, float)): return float(v)
        if isinstance(v, str):
            try: return float(v.replace(',', '.').strip())
            except (ValueError, TypeError): return None
        return v

    @field_validator('prazo_escritura_dias', mode='before')
    @classmethod
    def coerce_int_fields(cls, v):
        if v is None or v == '': return None
        if isinstance(v, int): return v
        if isinstance(v, float): return int(v)
        if isinstance(v, str):
            try: return int(float(v))
            except (ValueError, TypeError): return None
        return v

    @field_validator('ja_tem_imovel', 'has_property', 'ja_tem_casa_escolhida', mode='before')
    @classmethod
    def coerce_bool_fields(cls, v):
        if v is None or v == '': return None
        if isinstance(v, bool): return v
        if isinstance(v, str):
            if v.lower() in ('true', '1', 'yes', 'sim'): return True
            if v.lower() in ('false', '0', 'no', 'nao', 'não'): return False
            return None
        if isinstance(v, (int, float)): return bool(v)
        return None

class CreditData(BaseModel):
    """Dados de crédito e aprovação bancária."""
    model_config = ConfigDict(extra="allow")
    
    requested_amount: Optional[float] = None
    loan_term_years: Optional[int] = None
    interest_rate: Optional[float] = None
    monthly_payment: Optional[float] = None
    bank_name: Optional[str] = None
    bank_branch: Optional[str] = None
    bank_approval_date: Optional[str] = None
    bank_approval_notes: Optional[str] = None
    
    valuation_value: Optional[float] = None        
    valuation_date: Optional[str] = None           
    valuation_bank: Optional[str] = None           
    valuation_notes: Optional[str] = None          

    # ── Compliance & Perfil de Risco (Pacote AC) ──
    # Campos para gestão de compliance regulamentar (Banco de Portugal)
    # e perfil de risco do proponente. Editáveis no cartão "Compliance &
    # Perfil de Risco" da tab Crédito nos Detalhes do Processo.
    admission_year: Optional[int] = Field(None, description="Ano de admissão no emprego atual")
    is_ppe: Optional[bool] = Field(None, description="Pessoa Politicamente Exposta (PPE)")
    is_fpe: Optional[bool] = Field(None, description="Pessoa Fiscalmente Exposta (FPE) — incumprimento fiscal")
    credit_incidents: Optional[str] = Field(None, description="Incidentes de crédito (texto livre)")

    @field_validator('admission_year', mode='before')
    @classmethod
    def coerce_admission_year(cls, v):
        if v is None or v == '': return None
        if isinstance(v, int): return v
        if isinstance(v, float): return int(v)
        if isinstance(v, str):
            try: return int(float(v))
            except (ValueError, TypeError): return None
        return v

    @field_validator('is_ppe', 'is_fpe', mode='before')
    @classmethod
    def coerce_compliance_bool_fields(cls, v):
        if v is None or v == '': return None
        if isinstance(v, bool): return v
        if isinstance(v, str):
            if v.lower() in ('true', '1', 'yes', 'sim'): return True
            if v.lower() in ('false', '0', 'no', 'nao', 'não'): return False
            return None
        if isinstance(v, (int, float)): return bool(v)
        return None

    @field_validator('requested_amount', 'interest_rate', 'monthly_payment',
                     'valuation_value', mode='before')
    @classmethod
    def coerce_float_fields(cls, v):
        if v is None or v == '': return None
        if isinstance(v, (int, float)): return float(v)
        if isinstance(v, str):
            try: return float(v.replace(',', '.').strip())
            except (ValueError, TypeError): return None
        return v

    @field_validator('loan_term_years', mode='before')
    @classmethod
    def coerce_int_fields(cls, v):
        if v is None or v == '': return None
        if isinstance(v, int): return v
        if isinstance(v, float): return int(v)
        if isinstance(v, str):
            try: return int(float(v))
            except (ValueError, TypeError): return None
        return v
    
    @property
    def has_valuation_alert(self) -> bool:
        return False

# ==========================================
# NOVOS MODELOS DE PROCESSO - FASE 1.5
# ==========================================

class ProcessCreate(BaseModel):
    process_type: str
    client_id: str = Field(..., description="ID obrigatório do cliente ligado a este processo")
    second_client_id: Optional[str] = Field(None, description="ID do 2º titular/Fiador (cliente existente)")
    # PACOTE CY — is_lead=True envia o processo para a caixa "Registos de Clientes"
    # (status pre_registo) em vez do Kanban ativo (clientes_espera).
    is_lead: Optional[bool] = Field(False, description="Se True, cria como Lead (pre_registo) em vez de processo ativo")

class ProcessUpdate(BaseModel):
    real_estate_data: Optional[RealEstateData] = None
    credit_data: Optional[CreditData] = None
    status: Optional[str] = None
    second_client_id: Optional[str] = Field(None, description="ID do 2º titular/Fiador (cliente existente). Enviar null/string vazia para remover.")
    co_buyers: Optional[List[dict]] = None  
    co_applicants: Optional[List[dict]] = None 
    vendedor: Optional[dict] = None  
    mediador: Optional[dict] = None  
    monitored_emails: Optional[List[str]] = None  
    notes: Optional[str] = None
    observations: Optional[str] = Field(
        None,
        description="PACOTE DO.1 — Observações de fácil acesso no Resumo do Processo",
    )
    observation_notes: Optional[List[dict]] = Field(
        None,
        description="PACOTE DU — Feed de notas [{text, created_at, user_id, user_name}]",
    )
    prioridade: Optional[str] = None  
    labels: Optional[List[str]] = None
    is_indexed: Optional[bool] = None  # Marcação de conclusão da indexação documental  

class ProcessResponse(BaseModel):
    """Modelo de resposta para dados de processo.
    
    NOTA: extra="allow" é necessário porque populate_client_data() injeta
    campos dinâmicos (second_client_data, personal_data, titular2_data,
    financial_data, client_name, client_email, etc.) que o Frontend espera.
    Com extra="ignore", estes campos eram removidos na serialização, causando
    bugs como o 2º Titular não aparecer após associação (Bloco B).
    """
    model_config = ConfigDict(extra="allow")
    id: str
    process_number: Optional[int] = None  
    client_id: Optional[str] = Field(None, description="Referência para a pessoa fiscal (pode estar em falta em processos antigos)")
    client_ids: Optional[List[str]] = None  
    second_client_id: Optional[str] = Field(None, description="ID do 2º titular/Fiador ligado a este processo")
    process_type: Optional[str] = None
    type: Optional[str] = None  
    status: Optional[str] = None  
    
    real_estate_data: Optional[dict] = None
    credit_data: Optional[dict] = None
    
    assigned_consultor_ids: Optional[List[str]] = None  
    assigned_mediador_ids: Optional[List[str]] = None  
    assigned_consultor_id: Optional[str] = None  
    assigned_mediador_id: Optional[str] = None  
    consultor_names: Optional[List[str]] = None  
    mediador_names: Optional[List[str]] = None  
    consultor_name: Optional[str] = None  
    mediador_name: Optional[str] = None  
    assigned_indexacao_id: Optional[str] = None  
    indexacao_name: Optional[str] = None  
    assigned_parceiro_id: Optional[str] = None  
    parceiro_name: Optional[str] = None  
    
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    notes: Optional[str] = None
    observations: Optional[str] = Field(
        None,
        description="PACOTE DO.1 — Observações livres no Resumo do Processo",
    )
    observation_notes: Optional[List[dict]] = Field(
        None,
        description="PACOTE DU — Feed de notas [{text, created_at, user_id, user_name}]",
    )
    prioridade: Optional[str] = None  
    labels: Optional[List[str]] = None
    onedrive_links: Optional[List[dict]] = None
    
    source: Optional[str] = None  
    monitored_emails: Optional[List[str]] = None  
    
    co_buyers: Optional[List[dict]] = None  
    co_applicants: Optional[List[dict]] = None  
    vendedor: Optional[dict] = None  
    mediador: Optional[dict] = None
    is_indexed: Optional[bool] = None  # Indica se a indexação documental está concluída


class PublicClientRegistration(BaseModel):
    """
    DTO para registo público de clientes (sem autenticação).

    Contém dados pessoais mínimos (name, email, phone) para criar o Cliente,
    e dados de processo (process_type, has_property) para o futuro Processo.
    Os dados pessoais são encaminhados para a coleção `clients`, NÃO para `processes`.

    O processo só é criado depois dos documentos obrigatórios (SystemConfig).
    `titular2_data` fica no cliente até essa criação e é copiado para o processo.
    """
    name: str = Field(..., min_length=2, max_length=200, description="Nome completo do cliente")
    email: EmailStr = Field(..., max_length=100, description="Email do cliente")
    phone: str = Field(..., min_length=9, max_length=20, description="Telefone do cliente")
    process_type: str = Field(..., max_length=50, description="Tipo de processo")
    has_property: Optional[bool] = None
    custom_fields: Optional[dict] = None
    personal_data: Optional[dict] = None
    real_estate_data: Optional[dict] = None
    titular2_data: Optional[dict] = None

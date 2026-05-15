"""
Modelo de Processo — Entidade de Negócio / Dossier

O Processo representa o negócio (intermediação de crédito, compra imobiliária, etc.).
Contém TODOS os dados de negócio: financeiros, imobiliários, de crédito e atribuições.

REFATORAÇÃO FASE 1:
- client_id passa a ser OBRIGATÓRIO (referência ao Cliente)
- Dados pessoais do cliente NÃO são duplicados aqui — ficam na entidade Cliente
- personal_data mantém-se como SNAPSHOT/denormalização para compatibilidade,
  mas a fonte de verdade é a coleção `clients`
- co_buyers e co_applicants pertencem ao Processo (são específicos do negócio)
- Adicionados campos de negócio ao nível raiz: property_value, loan_value,
  bank_assigned, honorarios, comissao_banco
"""

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator
from typing import Optional, List, Any
from enum import Enum
import re


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class ServiceTypeEnum(str, Enum):
    """
    Tipo de serviço do processo.
    Define quais serviços estão incluídos no processo.
    """
    CREDITO_APENAS = "credito_apenas"       # Apenas intermediação de crédito
    IMOBILIARIO_APENAS = "imobiliario_apenas"  # Apenas mediação imobiliária
    COMPLETO = "completo"                   # Ambos os serviços


class ProcessType(str, Enum):
    """
    Tipo de processo — categoriza a natureza do negócio.
    """
    CREDITO_HABITACAO = "credito_habitacao"     # Crédito Habitação (CH)
    CREDITO_PESSOAL = "credito_pessoal"         # Crédito Pessoal
    REFINANCIAMENTO = "refinanciamento"         # Refinanciamento
    COMPRA_DIRETA = "compra_direta"             # Compra Direta
    ARRENDAMENTO = "arrendamento"               # Arrendamento
    CONSULTORIA = "consultoria"                 # Consultoria
    SEGUROS = "seguros"                         # Seguros
    OUTRO = "outro"                             # Outro

    @classmethod
    def all_values(cls) -> list:
        return [t.value for t in cls]


class ProcessStatusEnum(str, Enum):
    """
    Status do processo no workflow de 14 fases.
    Valores correspondem aos nomes das colunas do Kanban.
    """
    # Fase 1-3: Início
    CLIENTES_ESPERA = "clientes_espera"
    DOCUMENTACAO = "documentacao"
    ANALISE = "analise"
    
    # Fase 4-7: Aprovação
    PRE_APROVACAO = "pre_aprovacao"
    CREDITO_APROVADO = "credito_aprovado"
    PEDIDO_AVALIACAO = "pedido_avaliacao"
    AVALIACAO = "avaliacao"
    
    # Fase 8-10: Contrato
    CPCV = "cpcv"
    MINUTA = "minuta"
    ESCRITURA = "escritura"
    
    # Fase 11-14: Conclusão
    CONCLUIDO = "concluido"
    ARQUIVO = "arquivo"
    PERDIDO = "perdido"
    DESISTENCIAS = "desistencias"

    @classmethod
    def active_statuses(cls) -> list:
        return [s.value for s in cls if s.value not in ("concluido", "arquivo", "perdido", "desistencias")]


# ---------------------------------------------------------------------------
# Validadores
# ---------------------------------------------------------------------------

def validate_nif_checksum(nif: str) -> bool:
    """
    Valida o checksum (dígito de controlo) de um NIF português.
    """
    if not nif or len(nif) != 9 or not nif.isdigit():
        return False
    
    digits = [int(d) for d in nif]
    weights = [9, 8, 7, 6, 5, 4, 3, 2]
    total_sum = sum(d * w for d, w in zip(digits[:8], weights))
    remainder = total_sum % 11
    check_digit = 11 - remainder if remainder > 1 else 0
    return check_digit == digits[8]


def validate_nif(nif: str, allow_company: bool = False, validate_checksum: bool = True) -> str:
    """
    Validar NIF português (9 dígitos numéricos) com checksum.
    """
    if not nif:
        return nif
    nif_clean = re.sub(r'[^\d]', '', nif)
    if len(nif_clean) != 9:
        raise ValueError(f"NIF deve ter 9 dígitos (recebido: {len(nif_clean)})")
    if not nif_clean.isdigit():
        raise ValueError("NIF deve conter apenas dígitos")
    first_digit = nif_clean[0]
    valid_prefixes = ['1', '2', '3', '5', '6', '7', '8', '9']
    if first_digit not in valid_prefixes:
        raise ValueError(f"NIF com prefixo inválido: {first_digit}")
    if not allow_company and nif_clean.startswith('5'):
        raise ValueError("NIF de empresa (começado por 5) não é permitido para clientes particulares")
    if validate_checksum and not validate_nif_checksum(nif_clean):
        raise ValueError("NIF inválido: dígito de controlo incorreto")
    return nif_clean


# ---------------------------------------------------------------------------
# Sub-modelos de dados do Processo
# ---------------------------------------------------------------------------

class PersonalData(BaseModel):
    """
    SNAPSHOT dos dados pessoais do titular no momento do processo.
    
    A FONTE DE VERDADE é a coleção `clients`. Este sub-modelo existe para:
    1. Backward compatibility com dados existentes no MongoDB
    2. Permitir que dados pessoais possam divergir entre processos
       (ex: cliente mudou de morada entre dois processos)
    
    Na Fase 2, estes campos serão apenas leitura (preenchidos a partir do Cliente).
    """
    model_config = ConfigDict(extra="allow")
    
    # Nome completo (denormalizado do Cliente para quick access)
    nome_completo: Optional[str] = Field(None, max_length=200, description="Nome completo do cliente")
    nome: Optional[str] = Field(None, max_length=200, description="Nome completo (alias)")
    # Dados básicos com constraints
    nif: Optional[str] = Field(None, max_length=9, description="NIF - 9 dígitos")
    niss: Optional[str] = Field(None, max_length=11, description="NISS - Nº Segurança Social")
    documento_id: Optional[str] = Field(None, max_length=30, description="Número do documento de ID")
    naturalidade: Optional[str] = Field(None, max_length=100, description="Local de nascimento")
    nacionalidade: Optional[str] = Field(None, max_length=50, description="Nacionalidade")
    morada_fiscal: Optional[str] = Field(None, max_length=500, description="Morada fiscal completa")
    birth_date: Optional[str] = Field(None, max_length=20, description="Data de nascimento")
    data_nascimento: Optional[str] = Field(None, max_length=20, description="Data de nascimento (alias)")
    estado_civil: Optional[str] = Field(None, max_length=30, description="Estado civil")
    compra_tipo: Optional[str] = Field(None, max_length=50, description="Tipo de compra")
    menor_35_anos: Optional[bool] = None
    data_validade_cc: Optional[str] = Field(None, max_length=20, description="Validade do CC")
    sexo: Optional[str] = Field(None, max_length=1, description="M ou F")
    altura: Optional[str] = Field(None, max_length=10, description="Altura em metros")
    nome_pai: Optional[str] = Field(None, max_length=200, description="Nome do pai")
    nome_mae: Optional[str] = Field(None, max_length=200, description="Nome da mãe")
    # Campos extraídos por IA / usados em formulários
    email: Optional[str] = Field(None, max_length=200, description="Email")
    phone: Optional[str] = Field(None, max_length=20, description="Telefone")
    profissao: Optional[str] = Field(None, max_length=200, description="Profissão")
    morada: Optional[str] = Field(None, max_length=500, description="Morada completa")
    codigo_postal: Optional[str] = Field(None, max_length=20, description="Código postal")
    
    @field_validator('nif', mode='before')
    @classmethod
    def validate_nif_field(cls, v):
        if v is None or v == '':
            return None
        if isinstance(v, (int, float)):
            v = str(int(v))
        try:
            return validate_nif(v, validate_checksum=False)
        except ValueError:
            import logging
            logging.getLogger(__name__).warning(f"NIF inválido ignorado em PersonalData: {v}")
            return None
    
    @field_validator('nome_completo', 'nome', 'naturalidade', 'nacionalidade', 'nome_pai', 'nome_mae', mode='before')
    @classmethod
    def sanitize_text_fields(cls, v):
        """Sanitiza campos de texto."""
        if v is None or v == '':
            return None
        try:
            from utils.input_sanitization import sanitize_string
            return sanitize_string(str(v), max_length=200)
        except ImportError:
            import re
            v = re.sub(r'<[^>]+>', '', str(v))
            return v.strip()[:200]
    
    @field_validator('morada_fiscal', mode='before')
    @classmethod
    def sanitize_morada(cls, v):
        """Sanitiza morada com limite maior."""
        if v is None or v == '':
            return None
        try:
            from utils.input_sanitization import sanitize_string
            return sanitize_string(str(v), max_length=500)
        except ImportError:
            import re
            v = re.sub(r'<[^>]+>', '', str(v))
            return v.strip()[:500]
    
    @field_validator('data_nascimento', mode='before')
    @classmethod
    def sync_birth_date(cls, v, info):
        """Sincroniza data_nascimento com birth_date se não fornecido."""
        if v is None and info.data.get('birth_date'):
            return info.data.get('birth_date')
        return v
    
    @field_validator('birth_date', mode='before')
    @classmethod
    def sync_data_nascimento(cls, v, info):
        """Sincroniza birth_date com data_nascimento se não fornecido."""
        if v is None and info.data.get('data_nascimento'):
            return info.data.get('data_nascimento')
        return v


class Titular2Data(BaseModel):
    """Dados do segundo titular (co-titular do processo)."""
    model_config = ConfigDict(extra="allow")
    name: Optional[str] = None
    email: Optional[str] = None
    nif: Optional[str] = None
    documento_id: Optional[str] = None
    naturalidade: Optional[str] = None
    nacionalidade: Optional[str] = None
    phone: Optional[str] = None
    morada_fiscal: Optional[str] = None
    birth_date: Optional[str] = None
    estado_civil: Optional[str] = None
    # Credenciais dos Portais Oficiais (AT/SS) para o 2º Proponente
    portal_financas_utilizador: Optional[str] = Field(None, max_length=100, description="Utilizador do Portal das Finanças (2º Proponente)")
    portal_financas_senha: Optional[str] = Field(None, max_length=100, description="Senha de acesso ao Portal das Finanças (2º Proponente)")
    seg_social_utilizador: Optional[str] = Field(None, max_length=100, description="Utilizador da Segurança Social Direta (2º Proponente)")
    seg_social_senha: Optional[str] = Field(None, max_length=100, description="Senha de acesso à Segurança Social Direta (2º Proponente)")
    
    @field_validator('nif', mode='before')
    @classmethod
    def validate_nif_field(cls, v):
        if v is None or v == '':
            return None
        if isinstance(v, (int, float)):
            v = str(int(v))
        try:
            return validate_nif(v, validate_checksum=False)
        except ValueError:
            import logging
            logging.getLogger(__name__).warning(f"NIF inválido ignorado em Titular2Data: {v}")
            return None


class RealEstateData(BaseModel):
    """
    Dados imobiliários do processo.
    """
    model_config = ConfigDict(extra="allow")
    
    tipo_imovel: Optional[str] = None
    num_quartos: Optional[str] = None
    localizacao: Optional[str] = None
    caracteristicas: Optional[List[str]] = None
    outras_caracteristicas: Optional[str] = None
    outras_informacoes: Optional[str] = None
    ja_tem_imovel: Optional[bool] = None
    has_property: Optional[bool] = None   # Alias para ja_tem_imovel
    area_pretendida: Optional[float] = None
    valor_maximo_imovel: Optional[float] = None
    finalidade: Optional[str] = None
    ja_tem_casa_escolhida: Optional[bool] = None
    proprietario_nome: Optional[str] = None
    proprietario_contacto: Optional[str] = None
    caracteristicas_imovel: Optional[str] = None
    owner_name: Optional[str] = None
    owner_email: Optional[str] = None
    owner_phone: Optional[str] = None
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
    data_cpcv: Optional[str] = None
    data_escritura_prevista: Optional[str] = None
    prazo_escritura_dias: Optional[int] = None
    data_entrega_chaves: Optional[str] = None
    condicao_suspensiva: Optional[str] = None
    observacoes_cpcv: Optional[str] = None

    @field_validator('valor_imovel', 'valor_patrimonial', 'area_pretendida',
                     'valor_maximo_imovel', mode='before')
    @classmethod
    def coerce_float_fields(cls, v):
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

    @field_validator('prazo_escritura_dias', mode='before')
    @classmethod
    def coerce_int_fields(cls, v):
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

    @field_validator('ja_tem_imovel', 'has_property', 'ja_tem_casa_escolhida', mode='before')
    @classmethod
    def coerce_bool_fields(cls, v):
        if v is None or v == '':
            return None
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            if v.lower() in ('true', '1', 'yes', 'sim'):
                return True
            if v.lower() in ('false', '0', 'no', 'nao', 'não'):
                return False
            return None
        if isinstance(v, (int, float)):
            return bool(v)
        return None


class FinancialData(BaseModel):
    """
    Dados financeiros do PROCESSO (não do cliente).
    
    Cada processo pode ter dados financeiros diferentes para o mesmo cliente,
    pois cada negociação é distinta (diferentes montantes, bancos, condições).
    """
    model_config = ConfigDict(extra="allow")
    
    acesso_portal_financas: Optional[str] = None
    chave_movel_digital: Optional[str] = None
    renda_habitacao_atual: Optional[float] = None
    precisa_vender_casa: Optional[str] = None
    efetivo: Optional[str] = None
    fiador: Optional[str] = None
    bancos_creditos: Optional[List[Any]] = None
    bancos_simulacoes: Optional[List[str]] = None
    tempo_restante_credito: Optional[str] = None
    capital_proprio: Optional[float] = None
    valor_financiado: Optional[str] = None
    # Situação Profissional
    employment_type: Optional[str] = None
    employment_duration: Optional[str] = None
    employer_name: Optional[str] = None
    employer_nif: Optional[str] = None
    trabalha_estrangeiro: Optional[str] = None
    monthly_income: Optional[float] = None
    # Dados do CPCV - Valores
    valor_pretendido: Optional[float] = None
    valor_entrada: Optional[float] = None
    data_sinal: Optional[str] = None
    reforco_sinal: Optional[float] = None
    comissao_mediacao: Optional[float] = None
    # Credenciais de Portais Oficiais
    portal_financas_utilizador: Optional[str] = Field(None, max_length=100, description="Utilizador do Portal das Finanças")
    portal_financas_senha: Optional[str] = Field(None, max_length=100, description="Senha de acesso ao Portal das Finanças")
    seg_social_utilizador: Optional[str] = Field(None, max_length=100, description="Utilizador da Segurança Social Direta")
    seg_social_senha: Optional[str] = Field(None, max_length=100, description="Senha de acesso à Segurança Social Direta")
    # Campos extraídos por IA / recibos de vencimento
    rendimento_mensal: Optional[float] = None
    rendimento_bruto: Optional[float] = None
    rendimento_agregado: Optional[float] = None
    salario_liquido: Optional[float] = None
    salario_bruto: Optional[float] = None
    empresa: Optional[str] = None
    tipo_contrato: Optional[str] = None
    categoria_profissional: Optional[str] = None
    subsidiario_alimentacao: Optional[float] = None
    data_referencia: Optional[str] = None
    nr_dependentes: Optional[int] = None
    number_of_dependents: Optional[int] = None
    rendimento_co_titular: Optional[float] = None
    creditos_existentes: Optional[float] = None
    prestacao_creditos_mensal: Optional[float] = None
    tem_creditos_activos: Optional[List[str]] = None
    valor_creditos_activos: Optional[float] = None     # [Deprecated] — backward compat
    outros_rendimentos: Optional[float] = None
    despesas_mensais: Optional[float] = None
    rendimento_anual: Optional[float] = None
    antiguidade_emprego: Optional[str] = None

    @field_validator('renda_habitacao_atual', 'capital_proprio', 'monthly_income',
                     'valor_pretendido', 'valor_entrada', 'reforco_sinal', 'comissao_mediacao',
                     'rendimento_mensal', 'rendimento_bruto', 'rendimento_agregado',
                     'salario_liquido', 'salario_bruto', 'subsidiario_alimentacao',
                     'rendimento_co_titular', 'creditos_existentes', 'prestacao_creditos_mensal',
                     'valor_creditos_activos', 'outros_rendimentos', 'despesas_mensais',
                     'rendimento_anual', mode='before')
    @classmethod
    def coerce_float_fields(cls, v):
        if v is None or v == '':
            return None
        if isinstance(v, (int, float)):
            return float(v)
        if isinstance(v, str):
            try:
                cleaned = v.replace(',', '.').strip()
                return float(cleaned)
            except (ValueError, TypeError):
                return None
        return v

    @field_validator('nr_dependentes', 'number_of_dependents', mode='before')
    @classmethod
    def coerce_int_fields(cls, v):
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


class CreditData(BaseModel):
    """
    Dados de crédito e aprovação bancária do processo.
    """
    model_config = ConfigDict(extra="allow")
    
    requested_amount: Optional[float] = None
    loan_term_years: Optional[int] = None
    interest_rate: Optional[float] = None
    monthly_payment: Optional[float] = None
    bank_name: Optional[str] = None
    bank_approval_date: Optional[str] = None
    bank_approval_notes: Optional[str] = None
    # Campos de avaliação bancária
    valuation_value: Optional[float] = None
    valuation_date: Optional[str] = None
    valuation_bank: Optional[str] = None
    valuation_notes: Optional[str] = None

    @field_validator('requested_amount', 'interest_rate', 'monthly_payment',
                     'valuation_value', mode='before')
    @classmethod
    def coerce_float_fields(cls, v):
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

    @field_validator('loan_term_years', mode='before')
    @classmethod
    def coerce_int_fields(cls, v):
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
    
    @property
    def has_valuation_alert(self) -> bool:
        return False


# ---------------------------------------------------------------------------
# Schemas de entrada
# ---------------------------------------------------------------------------

class ProcessCreate(BaseModel):
    """
    Schema para criar um novo processo.
    
    client_id é OBRIGATÓRIO — o cliente deve existir antes de criar o processo.
    """
    process_type: str = Field(..., description="Tipo de processo (credito_habitacao, credito_pessoal, etc.)")
    client_id: str = Field(..., description="ID do cliente (obrigatório — referência à entidade Cliente)")
    client_name: Optional[str] = Field(None, description="Nome do cliente (denormalizado, preenchido automaticamente)")
    client_email: Optional[str] = Field(None, description="Email do cliente (denormalizado)")
    personal_data: Optional[PersonalData] = None
    financial_data: Optional[FinancialData] = None


class PublicClientRegistration(BaseModel):
    """
    Modelo para registo público de clientes.
    
    Cria simultaneamente o Cliente e o Processo associado.
    """
    name: str = Field(
        ...,
        min_length=2,
        max_length=200,
        description="Nome completo do cliente"
    )
    email: EmailStr = Field(
        ...,
        max_length=100,
        description="Email do cliente"
    )
    phone: str = Field(
        ...,
        min_length=9,
        max_length=20,
        description="Telefone do cliente"
    )
    process_type: str = Field(
        ...,
        max_length=50,
        description="Tipo de processo"
    )
    personal_data: Optional[PersonalData] = None
    titular2_data: Optional[Titular2Data] = None
    real_estate_data: Optional[RealEstateData] = None
    financial_data: Optional[FinancialData] = None
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


class ProcessUpdate(BaseModel):
    """
    Schema para actualizar um processo.
    
    Dados pessoais do cliente NÃO devem ser actualizados aqui — usar o endpoint
    de clientes. Este schema actualiza apenas dados de negócio do processo.
    """
    personal_data: Optional[PersonalData] = None  # [DEPRECATED] Usar endpoint de clientes na Fase 2
    titular2_data: Optional[Titular2Data] = None
    financial_data: Optional[FinancialData] = None
    real_estate_data: Optional[RealEstateData] = None
    credit_data: Optional[CreditData] = None
    status: Optional[str] = None
    # Campos de negócio (nível raiz)
    property_value: Optional[float] = None
    loan_value: Optional[float] = None
    bank_assigned: Optional[str] = None
    honorarios: Optional[float] = None
    comissao_banco: Optional[float] = None
    # Contacto do cliente (denormalizado)
    client_email: Optional[str] = None
    client_phone: Optional[str] = None
    # Co-compradores e co-proponentes (pertencem ao processo)
    co_buyers: Optional[List[dict]] = None
    co_applicants: Optional[List[dict]] = None
    vendedor: Optional[dict] = None
    mediador: Optional[dict] = None
    monitored_emails: Optional[List[str]] = None
    # Metadados do processo
    notes: Optional[str] = None
    prioridade: Optional[str] = None
    labels: Optional[List[str]] = None
    
    @field_validator('client_email', 'client_phone', mode='before')
    @classmethod
    def coerce_to_string(cls, v):
        if v is None:
            return None
        return str(v)

    @field_validator('property_value', 'loan_value', 'honorarios', 'comissao_banco', mode='before')
    @classmethod
    def coerce_float_fields(cls, v):
        """Converte strings para float graciosamente."""
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


# ---------------------------------------------------------------------------
# Schema de resposta
# ---------------------------------------------------------------------------

class ProcessResponse(BaseModel):
    """
    Modelo de resposta para dados de processo.
    
    REFATORAÇÃO FASE 1:
    - client_id é OBRIGATÓRIO (referência ao Cliente)
    - Adicionados campos de negócio ao nível raiz
    - personal_data continua como snapshot/denormalização

    NOTA: ConfigDict(extra="ignore") garante que campos extra no MongoDB
    não causam 422 ao serializar a resposta.
    """
    model_config = ConfigDict(extra="ignore")
    id: str
    process_number: Optional[int] = None
    
    # ── Referência ao Cliente (OBRIGATÓRIA) ──────────────────────────
    client_id: str = Field(..., description="ID do cliente associado (obrigatório)")
    client_ids: Optional[List[str]] = None  # Suporte a múltiplos clientes (N:M)
    client_name: Optional[str] = None       # Denormalizado para quick access
    client_email: Optional[str] = None
    client_phone: Optional[str] = None
    client_nif: Optional[str] = None
    
    # ── Dados de Negócio (nível raiz) ────────────────────────────────
    process_type: Optional[str] = None      # CH, Pessoal, Seguros, etc.
    type: Optional[str] = None              # Alias for process_type
    status: Optional[str] = None            # Coluna do Kanban
    property_value: Optional[float] = None  # Valor do imóvel
    loan_value: Optional[float] = None      # Valor do empréstimo
    bank_assigned: Optional[str] = None     # Banco atribuído
    honorarios: Optional[float] = None      # Honorários da intermediação
    comissao_banco: Optional[float] = None  # Comissão do banco
    
    # ── Sub-modelos de dados ─────────────────────────────────────────
    personal_data: Optional[dict] = None    # Snapshot dos dados pessoais
    titular2_data: Optional[dict] = None
    financial_data: Optional[dict] = None
    real_estate_data: Optional[dict] = None
    credit_data: Optional[dict] = None
    
    # ── Atribuições ──────────────────────────────────────────────────
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
    
    # ── Co-compradores e co-proponentes (do processo) ────────────────
    co_buyers: Optional[List[dict]] = None
    co_applicants: Optional[List[dict]] = None
    vendedor: Optional[dict] = None
    mediador: Optional[dict] = None
    
    # ── Documentos e referências ─────────────────────────────────────
    documents: Optional[List[dict]] = None  # Referências a documentos do processo
    s3_folder: Optional[str] = None
    
    # ── Metadados ────────────────────────────────────────────────────
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    notes: Optional[str] = None
    valor_financiado: Optional[str] = None
    idade_menos_35: Optional[bool] = None
    has_property: Optional[bool] = None
    prioridade: Optional[str] = None
    labels: Optional[List[str]] = None
    onedrive_links: Optional[List[dict]] = None
    trello_card_id: Optional[str] = None
    trello_list_id: Optional[str] = None
    source: Optional[str] = None
    monitored_emails: Optional[List[str]] = None
    is_data_confirmed: Optional[bool] = None
    ai_suggestions: Optional[List[dict]] = None

    @field_validator('idade_menos_35', 'has_property', 'is_data_confirmed', mode='before')
    @classmethod
    def coerce_bool_fields(cls, v):
        if v is None:
            return None
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            if v.lower() in ('true', '1', 'yes'):
                return True
            if v.lower() in ('false', '0', 'no', ''):
                return False
        return v

    @field_validator('property_value', 'loan_value', 'honorarios', 'comissao_banco', mode='before')
    @classmethod
    def coerce_float_fields(cls, v):
        """Converte strings para float graciosamente."""
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

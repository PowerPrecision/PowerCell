from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import Optional, List, Any
from enum import Enum
import re


class ServiceTypeEnum(str, Enum):
    """
    Tipo de serviço do processo.
    Define quais serviços estão incluídos no processo.
    """
    CREDITO_APENAS = "credito_apenas"       # Apenas intermediação de crédito
    IMOBILIARIO_APENAS = "imobiliario_apenas"  # Apenas mediação imobiliária
    COMPLETO = "completo"                   # Ambos os serviços


class ProcessType:
    CREDITO = "credito"
    IMOBILIARIA = "imobiliaria"
    AMBOS = "ambos"


def validate_nif_checksum(nif: str) -> bool:
    """
    Valida o checksum (dígito de controlo) de um NIF português.
    
    Algoritmo:
    1. Multiplicar os 8 primeiros dígitos por 9,8,7,6,5,4,3,2 respectivamente
    2. Somar todos os produtos
    3. Calcular resto da divisão por 11
    4. Dígito de controlo = 11 - resto (se >= 10, usar 0)
    5. Comparar com o 9º dígito
    
    Returns:
        True se o checksum for válido, False caso contrário
    """
    if not nif or len(nif) != 9 or not nif.isdigit():
        return False
    
    digits = [int(d) for d in nif]
    
    # Calcular soma ponderada dos primeiros 8 dígitos
    weights = [9, 8, 7, 6, 5, 4, 3, 2]
    total_sum = sum(d * w for d, w in zip(digits[:8], weights))
    
    # Calcular dígito de controlo
    remainder = total_sum % 11
    check_digit = 11 - remainder if remainder > 1 else 0
    
    return check_digit == digits[8]


def validate_nif(nif: str, allow_company: bool = False, validate_checksum: bool = True) -> str:
    """
    Validar NIF português (9 dígitos numéricos) com checksum.
    Por defeito, não permite NIFs de empresas (começam por 5).
    
    Args:
        nif: O NIF a validar
        allow_company: Se True, permite NIFs de empresas (5xxxxxxxx)
        validate_checksum: Se True, valida o dígito de controlo
    
    Returns:
        O NIF limpo se válido
        
    Raises:
        ValueError: Se o NIF for inválido
    """
    if not nif:
        return nif
    
    # Remover espaços e caracteres especiais
    nif_clean = re.sub(r'[^\d]', '', nif)
    
    if len(nif_clean) != 9:
        raise ValueError(f"NIF deve ter 9 dígitos (recebido: {len(nif_clean)})")
    
    if not nif_clean.isdigit():
        raise ValueError("NIF deve conter apenas dígitos")
    
    # Validar primeiro dígito - prefixos válidos para NIF português
    first_digit = nif_clean[0]
    valid_prefixes = ['1', '2', '3', '5', '6', '7', '8', '9']
    if first_digit not in valid_prefixes:
        raise ValueError(f"NIF com prefixo inválido: {first_digit}")
    
    # NIFs que começam com 5 são de empresas
    if not allow_company and nif_clean.startswith('5'):
        raise ValueError("NIF de empresa (começado por 5) não é permitido para clientes particulares")
    
    # Validar checksum (dígito de controlo)
    if validate_checksum and not validate_nif_checksum(nif_clean):
        raise ValueError("NIF inválido: dígito de controlo incorreto")
    
    return nif_clean


class PersonalData(BaseModel):
    """
    Dados pessoais do titular.
    
    Campos activos:
    - nif (validado: 9 dígitos), documento_id, naturalidade, nacionalidade, morada_fiscal
    - birth_date/data_nascimento, estado_civil, compra_tipo, menor_35_anos
    - data_validade_cc, sexo, altura, nome_pai, nome_mae
    """
    # Dados básicos (activos) com constraints
    nif: Optional[str] = Field(None, max_length=9, description="NIF - 9 dígitos")
    documento_id: Optional[str] = Field(None, max_length=30, description="Número do documento de ID")
    naturalidade: Optional[str] = Field(None, max_length=100, description="Local de nascimento")
    nacionalidade: Optional[str] = Field(None, max_length=50, description="Nacionalidade")
    morada_fiscal: Optional[str] = Field(None, max_length=500, description="Morada fiscal completa")
    birth_date: Optional[str] = Field(None, max_length=20, description="Data de nascimento")
    data_nascimento: Optional[str] = Field(None, max_length=20, description="Data de nascimento (alias)")
    estado_civil: Optional[str] = Field(None, max_length=30, description="Estado civil")
    compra_tipo: Optional[str] = Field(None, max_length=50, description="Tipo de compra")
    menor_35_anos: Optional[bool] = None  # Checkbox apoio ao estado
    # Novos campos - Identificação completa
    data_validade_cc: Optional[str] = Field(None, max_length=20, description="Validade do CC")
    sexo: Optional[str] = Field(None, max_length=1, description="M ou F")
    altura: Optional[str] = Field(None, max_length=10, description="Altura em metros")
    # Filiação
    nome_pai: Optional[str] = Field(None, max_length=200, description="Nome do pai")
    nome_mae: Optional[str] = Field(None, max_length=200, description="Nome da mãe")
    
    @field_validator('nif', mode='before')
    @classmethod
    def validate_nif_field(cls, v):
        if v is None or v == '':
            return None
        # Converter para string se for número
        if isinstance(v, (int, float)):
            v = str(int(v))
        return validate_nif(v)
    
    @field_validator('naturalidade', 'nacionalidade', 'nome_pai', 'nome_mae', mode='before')
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
        # Se data_nascimento não foi fornecido, usar birth_date
        if v is None and info.data.get('birth_date'):
            return info.data.get('birth_date')
        return v
    
    @field_validator('birth_date', mode='before')
    @classmethod
    def sync_data_nascimento(cls, v, info):
        """Sincroniza birth_date com data_nascimento se não fornecido."""
        # Se birth_date não foi fornecido, usar data_nascimento
        if v is None and info.data.get('data_nascimento'):
            return info.data.get('data_nascimento')
        return v


class Titular2Data(BaseModel):
    """Dados do segundo titular."""
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
    
    @field_validator('nif', mode='before')
    @classmethod
    def validate_nif_field(cls, v):
        if v is None or v == '':
            return None
        # Converter para string se for número
        if isinstance(v, (int, float)):
            v = str(int(v))
        return validate_nif(v)


class RealEstateData(BaseModel):
    """
    Dados imobiliários.
    
    Campos activos:
    - tipo_imovel, num_quartos, localizacao, caracteristicas
    - outras_caracteristicas, outras_informacoes
    - ja_tem_imovel (indica se o cliente já tem imóvel identificado)
    - Dados do proprietário: owner_name, owner_email, owner_phone
    - Dados do CPCV: valor_imovel, datas, etc.
    """
    tipo_imovel: Optional[str] = None
    num_quartos: Optional[str] = None
    localizacao: Optional[str] = None
    caracteristicas: Optional[List[str]] = None
    outras_caracteristicas: Optional[str] = None
    outras_informacoes: Optional[str] = None
    ja_tem_imovel: Optional[bool] = None  # Indica se cliente já tem imóvel identificado
    has_property: Optional[bool] = None   # Alias para ja_tem_imovel
    # Novos campos - área, valor e finalidade
    area_pretendida: Optional[str] = None           # Área pretendida em m²
    valor_maximo_imovel: Optional[str] = None       # Valor máximo do imóvel em euros
    finalidade: Optional[str] = None                # compra_imovel, refinanciamento
    ja_tem_casa_escolhida: Optional[bool] = None    # Se já tem casa escolhida
    proprietario_nome: Optional[str] = None         # Nome do proprietário (se já tem casa)
    proprietario_contacto: Optional[str] = None     # Contacto do proprietário
    caracteristicas_imovel: Optional[str] = None    # Características básicas do imóvel escolhido
    # Dados do proprietário do imóvel (antigos)
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
    # Datas do CPCV
    data_cpcv: Optional[str] = None
    data_escritura_prevista: Optional[str] = None
    prazo_escritura_dias: Optional[int] = None
    data_entrega_chaves: Optional[str] = None
    # Condições
    condicao_suspensiva: Optional[str] = None
    observacoes_cpcv: Optional[str] = None


class FinancialData(BaseModel):
    """
    Dados financeiros.
    
    Campos activos:
    - acesso_portal_financas, chave_movel_digital, renda_habitacao_atual
    - precisa_vender_casa, efetivo, fiador, bancos_creditos
    - capital_proprio, valor_financiado
    - Dados do CPCV: valor_entrada, valor_pretendido, etc.
    - Situação profissional: employment_type, employment_duration, employer_name
    - Credenciais de portais: portal_financas_utilizador, portal_financas_senha, etc.
    """
    acesso_portal_financas: Optional[str] = None
    chave_movel_digital: Optional[str] = None
    renda_habitacao_atual: Optional[float] = None
    precisa_vender_casa: Optional[str] = None
    efetivo: Optional[str] = None
    fiador: Optional[str] = None
    bancos_creditos: Optional[List[str]] = None
    capital_proprio: Optional[float] = None
    valor_financiado: Optional[str] = None
    # Situação Profissional
    employment_type: Optional[str] = None  # efetivo, termo, independente, empresario, reformado, desempregado
    employment_duration: Optional[str] = None  # Tempo de emprego
    employer_name: Optional[str] = None  # Entidade empregadora
    employer_nif: Optional[str] = None  # NIF da entidade empregadora
    monthly_income: Optional[float] = None  # Rendimento mensal
    # Dados do CPCV - Valores
    valor_pretendido: Optional[float] = None
    valor_entrada: Optional[float] = None
    data_sinal: Optional[str] = None
    reforco_sinal: Optional[float] = None
    comissao_mediacao: Optional[float] = None
    # Credenciais de Portais Oficiais (preenchidos posteriormente pelo utilizador)
    portal_financas_utilizador: Optional[str] = Field(None, max_length=100, description="Utilizador do Portal das Finanças")
    portal_financas_senha: Optional[str] = Field(None, max_length=100, description="Senha de acesso ao Portal das Finanças")
    seg_social_utilizador: Optional[str] = Field(None, max_length=100, description="Utilizador da Segurança Social Direta")
    seg_social_senha: Optional[str] = Field(None, max_length=100, description="Senha de acesso à Segurança Social Direta")


class CreditData(BaseModel):
    """
    Dados de crédito e aprovação bancária.
    
    Inclui campos de avaliação bancária para alertas automáticos
    quando valor de avaliação < valor de compra.
    """
    requested_amount: Optional[float] = None
    loan_term_years: Optional[int] = None
    interest_rate: Optional[float] = None
    monthly_payment: Optional[float] = None
    bank_name: Optional[str] = None
    bank_approval_date: Optional[str] = None
    bank_approval_notes: Optional[str] = None
    
    # Campos de avaliação bancária (novos)
    valuation_value: Optional[float] = None        # Valor da avaliação bancária
    valuation_date: Optional[str] = None           # Data da avaliação
    valuation_bank: Optional[str] = None           # Banco que fez a avaliação
    valuation_notes: Optional[str] = None          # Observações da avaliação
    
    # Campo calculado para alerta
    @property
    def has_valuation_alert(self) -> bool:
        """
        Verifica se há alerta de avaliação (valor avaliação < valor compra).
        Nota: Este é um property calculado, precisa de acesso ao valor de compra externamente.
        """
        return False  # Implementação real feita no serviço de alertas


class ProcessCreate(BaseModel):
    process_type: str
    client_name: Optional[str] = None
    client_email: Optional[str] = None
    personal_data: Optional[PersonalData] = None
    financial_data: Optional[FinancialData] = None


class PublicClientRegistration(BaseModel):
    """
    Modelo para registo público de clientes.
    
    Inclui validação e sanitização de inputs para segurança.
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
    
    @field_validator('name', mode='before')
    @classmethod
    def sanitize_name(cls, v):
        """Sanitiza o nome removendo HTML e caracteres perigosos."""
        if not v:
            return v
        try:
            from utils.input_sanitization import sanitize_name
            return sanitize_name(v, max_length=200)
        except ImportError:
            # Fallback básico se módulo não disponível
            import re
            v = re.sub(r'<[^>]+>', '', str(v))
            return v.strip()[:200]
    
    @field_validator('phone', mode='before')
    @classmethod
    def sanitize_phone(cls, v):
        """Sanitiza o telefone."""
        if not v:
            return v
        try:
            from utils.input_sanitization import sanitize_phone
            return sanitize_phone(v)
        except ImportError:
            import re
            return re.sub(r'[^\d+]', '', str(v))[:20]


class ProcessUpdate(BaseModel):
    personal_data: Optional[PersonalData] = None
    titular2_data: Optional[Titular2Data] = None
    financial_data: Optional[FinancialData] = None
    real_estate_data: Optional[RealEstateData] = None
    credit_data: Optional[CreditData] = None
    status: Optional[str] = None
    client_email: Optional[str] = None
    client_phone: Optional[str] = None
    # Campos adicionais para CPCV e documentos com múltiplos compradores
    co_buyers: Optional[List[dict]] = None  # Co-compradores do CPCV
    co_applicants: Optional[List[dict]] = None  # Co-proponentes de simulação/IRS
    vendedor: Optional[dict] = None  # Dados do vendedor do CPCV
    mediador: Optional[dict] = None  # Dados do mediador imobiliário
    
    @field_validator('client_email', 'client_phone', mode='before')
    @classmethod
    def coerce_to_string(cls, v):
        """Converter valores para string para evitar erros de validação."""
        if v is None:
            return None
        return str(v)


class ProcessResponse(BaseModel):
    id: str
    process_number: Optional[int] = None  # Número sequencial único do processo
    # Suporte a múltiplos clientes por processo (relação N:M)
    client_ids: Optional[List[str]] = None  # Lista de IDs de clientes associados
    client_id: Optional[str] = None  # ID do cliente principal (compatibilidade)
    client_name: str
    client_email: Optional[str] = None
    client_phone: Optional[str] = None
    client_nif: Optional[str] = None
    process_type: Optional[str] = None
    type: Optional[str] = None  # Alias for process_type (from Trello import)
    status: str
    personal_data: Optional[dict] = None
    titular2_data: Optional[dict] = None
    financial_data: Optional[dict] = None
    real_estate_data: Optional[dict] = None
    credit_data: Optional[dict] = None
    assigned_consultor_id: Optional[str] = None
    assigned_mediador_id: Optional[str] = None
    assigned_indexacao_id: Optional[str] = None  # Utilizador responsável pela indexação de documentos
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    notes: Optional[str] = None
    valor_financiado: Optional[str] = None
    idade_menos_35: Optional[bool] = None
    prioridade: Optional[bool] = None
    labels: Optional[List[str]] = None
    onedrive_links: Optional[List[dict]] = None
    has_property: Optional[bool] = None  # Flag para indicar se cliente já tem imóvel
    trello_card_id: Optional[str] = None  # ID do card no Trello
    trello_list_id: Optional[str] = None  # ID da lista no Trello
    source: Optional[str] = None  # Origem do processo (trello_import, web_form, etc.)
    monitored_emails: Optional[List[str]] = None  # Emails adicionais para monitorizar
    # Campos do CPCV
    co_buyers: Optional[List[dict]] = None  # Co-compradores
    co_applicants: Optional[List[dict]] = None  # Co-proponentes
    vendedor: Optional[dict] = None  # Dados do vendedor
    mediador: Optional[dict] = None  # Dados do mediador imobiliário
    # TAREFA 2: Conflitos de Dados IA
    is_data_confirmed: Optional[bool] = None  # Se True, IA não sobrepõe dados de perfil
    ai_suggestions: Optional[List[dict]] = None  # Sugestões de dados extraídos pela IA em conflito

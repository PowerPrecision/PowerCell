"""
Modelos do Módulo Financeiro — CREDITOIMO

Este módulo gere dois conceitos isolados:

1. FinanceConfig  — Configuração financeira da empresa (comissões/honorários).
    Define se a empresa cobra valor fixo ou percentagem, o valor por omissão,
    e a taxa de imposto (IVA) a aplicar. Uma configuração por empresa (multi-tenant).

2. ProcessFinance — Dados financeiros isolados de um Processo.
    Snapshot imutável da comissão no momento do fecho, garantindo que alterações
    na configuração da empresa NÃO afectam processos já fechados.
    Suporta DUAS comissões independentes:
    - Comissão Imobiliária (Real Estate): sobre o valor do imóvel
    - Comissão de Crédito (Credit): sobre o valor do crédito/loan_amount
    A comissão total (expected_commission) = real_estate_commission + credit_commission

Convenções:
- IDs são str (UUID gerado na camada de serviço, não ObjectId).
- Timestamps em formato ISO 8601 string.
- Enums herdam de (str, Enum) para serialização JSON.
- Validadores Pydantic v2 (@field_validator, mode='before') para coerção.
"""

from pydantic import BaseModel, ConfigDict, Field, field_validator, ValidationInfo
from typing import Optional, List
from enum import Enum
from datetime import datetime, timezone


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class FeeType(str, Enum):
    """
    Tipo de comissão/honorário.
    - 'fixed': valor fixo em euros (ex: 5000.0 = 5000€)
    - 'percentage': percentagem sobre o valor base (ex: 5.0 = 5%)
    """
    FIXED = "fixed"
    PERCENTAGE = "percentage"

    @classmethod
    def all_values(cls) -> List[str]:
        return [t.value for t in cls]


class FinanceStatus(str, Enum):
    """
    Status do registo financeiro do processo.
    """
    PENDING = "pending"          # Pendente — aguarda faturação
    INVOICED = "invoiced"        # Faturado — fatura emitida
    PAID = "paid"                # Pago — pagamento recebido
    CANCELLED = "cancelled"      # Cancelado — processo desistido/perdido

    @classmethod
    def active_statuses(cls) -> List[str]:
        """Status que representam registos activos (não cancelados)."""
        return [cls.PENDING.value, cls.INVOICED.value, cls.PAID.value]

    @classmethod
    def completed_statuses(cls) -> List[str]:
        """Status que representam registos finalizados."""
        return [cls.PAID.value, cls.CANCELLED.value]

    @classmethod
    def all_values(cls) -> List[str]:
        return [s.value for s in cls]


# ---------------------------------------------------------------------------
# Validadores auxiliares
# ---------------------------------------------------------------------------

def _coerce_to_float(v) -> Optional[float]:
    """
    Coerce valor para float, lidando com:
    - None / string vazia → None
    - Vírgulas decimais europeias (ex: '5,5' → 5.5)
    - Tipos int/float nativos
    """
    if v is None or v == '':
        return None
    if isinstance(v, bool):
        return None  # booleans não são valores financeiros válidos
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        try:
            return float(v.replace(',', '.').strip())
        except (ValueError, TypeError):
            return None
    return None


def _coerce_to_non_negative_float(v) -> Optional[float]:
    """Coerce para float e garante valor não-negativo."""
    result = _coerce_to_float(v)
    if result is not None and result < 0:
        raise ValueError("O valor não pode ser negativo")
    return result


# ---------------------------------------------------------------------------
# Modelo 1: FinanceConfig (Configuração da Empresa)
# ---------------------------------------------------------------------------

class FinanceConfig(BaseModel):
    """
    Configuração financeira de uma empresa (multi-tenant).

    Define as regras de comissão/honorário e IVA que a empresa aplica.
    Uma configuração por company_id.
    """
    id: str
    company_id: str = Field(..., description="Referência obrigatória à empresa (multi-tenant)")
    fee_type: str = Field(
        ...,
        description="Tipo de comissão: 'fixed' (valor fixo em €) ou 'percentage' (%)"
    )
    default_value: float = Field(
        ...,
        description="Valor por omissão: montante em € (fixed) ou percentagem (percentage)"
    )
    tax_rate: float = Field(
        default=23.0,
        description="Taxa de imposto (ex: 23.0 = IVA a 23%)"
    )
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @field_validator('fee_type', mode='before')
    @classmethod
    def validate_fee_type(cls, v):
        """Garantir que o fee_type é um valor válido do enum."""
        if v is None or v == '':
            raise ValueError("fee_type é obrigatório")
        v_lower = str(v).lower().strip()
        valid = FeeType.all_values()
        if v_lower not in valid:
            raise ValueError(f"fee_type inválido: '{v}'. Valores permitidos: {valid}")
        return v_lower

    @field_validator('default_value', mode='before')
    @classmethod
    def coerce_default_value(cls, v, info: ValidationInfo):
        """Coerção para float, não-negativo. Valida range se fee_type já disponível."""
        result = _coerce_to_non_negative_float(v)
        if result is None:
            raise ValueError("default_value é obrigatório e deve ser um número válido")
        # Validação cruzada: se fee_type='percentage', valor ≤ 100
        fee_type = info.data.get('fee_type', '')
        if fee_type == FeeType.PERCENTAGE.value and result > 100:
            raise ValueError(
                "Com percentagem, default_value não pode ultrapassar 100 "
                f"(recebido: {result})"
            )
        return result

    @field_validator('tax_rate', mode='before')
    @classmethod
    def coerce_tax_rate(cls, v):
        """Coerção para float, garantindo percentagem válida (0-100)."""
        result = _coerce_to_float(v)
        if result is None:
            return 23.0  # valor por omissão: IVA português
        if result < 0:
            raise ValueError("tax_rate não pode ser negativa")
        if result > 100:
            raise ValueError("tax_rate não pode ultrapassar 100%")
        return result


class FinanceConfigCreate(BaseModel):
    """Schema para criar uma configuração financeira."""
    company_id: str = Field(..., description="Referência obrigatória à empresa")
    fee_type: str = Field(..., description="Tipo de comissão: 'fixed' ou 'percentage'")
    default_value: float = Field(..., description="Valor por omissão (€ ou %)")
    tax_rate: Optional[float] = Field(default=23.0, description="Taxa de IVA (ex: 23.0)")

    @field_validator('fee_type', mode='before')
    @classmethod
    def validate_fee_type(cls, v):
        if v is None or v == '':
            raise ValueError("fee_type é obrigatório")
        v_lower = str(v).lower().strip()
        if v_lower not in FeeType.all_values():
            raise ValueError(f"fee_type inválido: '{v}'. Valores permitidos: {FeeType.all_values()}")
        return v_lower

    @field_validator('default_value', mode='before')
    @classmethod
    def coerce_default_value(cls, v, info: ValidationInfo):
        result = _coerce_to_non_negative_float(v)
        if result is None:
            raise ValueError("default_value é obrigatório e deve ser um número válido")
        # Validação cruzada: se fee_type='percentage', valor ≤ 100
        fee_type = info.data.get('fee_type', '')
        if fee_type == FeeType.PERCENTAGE.value and result > 100:
            raise ValueError(
                f"Com percentagem, default_value não pode ultrapassar 100 "
                f"(recebido: {result})"
            )
        return result

    @field_validator('tax_rate', mode='before')
    @classmethod
    def coerce_tax_rate(cls, v):
        result = _coerce_to_float(v)
        if result is None:
            return 23.0
        if result < 0:
            raise ValueError("tax_rate não pode ser negativa")
        if result > 100:
            raise ValueError("tax_rate não pode ultrapassar 100%")
        return result


class FinanceConfigUpdate(BaseModel):
    """Schema para actualizar uma configuração financeira."""
    fee_type: Optional[str] = None
    default_value: Optional[float] = None
    tax_rate: Optional[float] = None

    @field_validator('fee_type', mode='before')
    @classmethod
    def validate_fee_type(cls, v):
        if v is None or v == '':
            return None
        v_lower = str(v).lower().strip()
        if v_lower not in FeeType.all_values():
            raise ValueError(f"fee_type inválido: '{v}'. Valores permitidos: {FeeType.all_values()}")
        return v_lower

    @field_validator('default_value', mode='before')
    @classmethod
    def coerce_default_value(cls, v, info: ValidationInfo):
        if v is None or v == '':
            return None
        result = _coerce_to_non_negative_float(v)
        # Validação cruzada: se fee_type='percentage', valor ≤ 100
        fee_type = info.data.get('fee_type', '')
        if fee_type == FeeType.PERCENTAGE.value and result is not None and result > 100:
            raise ValueError(
                f"Com percentagem, default_value não pode ultrapassar 100 "
                f"(recebido: {result})"
            )
        return result

    @field_validator('tax_rate', mode='before')
    @classmethod
    def coerce_tax_rate(cls, v):
        if v is None or v == '':
            return None
        result = _coerce_to_float(v)
        if result is not None:
            if result < 0:
                raise ValueError("tax_rate não pode ser negativa")
            if result > 100:
                raise ValueError("tax_rate não pode ultrapassar 100%")
        return result


class FinanceConfigResponse(BaseModel):
    """Modelo de resposta para configuração financeira."""
    model_config = ConfigDict(extra="ignore")
    id: str
    company_id: str
    fee_type: str
    default_value: float
    tax_rate: float
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


# ---------------------------------------------------------------------------
# Modelo 2: ProcessFinance (Dados Financeiros do Processo)
# ---------------------------------------------------------------------------

class ProcessFinance(BaseModel):
    """
    Dados financeiros isolados de um Processo.

    Snapshot imutável: no momento do fecho, copia-se a configuração da empresa
    (fee_type + valor) para este registo. Alterações futuras na FinanceConfig
    NÃO afectam processos já fechados — princípio de imutabilidade histórica.

    Suporta DUPLA comissão (Real Estate + Credit):
    - Comissão Imobiliária: sobre o valor do imóvel (real_estate_base_value)
    - Comissão de Crédito: sobre o valor do crédito (credit_base_value)
    - expected_commission = real_estate_commission + credit_commission

    Cálculos automáticos:
    - real_estate_commission = real_estate_base_value * (real_estate_fee_value / 100)  [se percentage]
                               ou real_estate_fee_value [se fixed]
    - credit_commission = credit_base_value * (credit_fee_value / 100)  [se percentage]
                          ou credit_fee_value [se fixed]
    - expected_commission = real_estate_commission + credit_commission
    - tax_amount = expected_commission * (tax_rate / 100)
    - total_with_tax = expected_commission + tax_amount

    Compatibilidade retroactiva:
    - Os campos base_business_value, applied_fee_type, applied_fee_value são mantidos
      para processos existentes que usam o modelo de comissão única.
    """
    id: str
    process_id: str = Field(..., description="Referência ao ProcessModel")
    client_id: str = Field(..., description="Referência ao ClientModel")
    company_id: str = Field(..., description="Empresa para segurança e filtros multi-tenant")

    # --- Comissão única (legacy / compatibilidade retroactiva) ---
    base_business_value: float = Field(
        default=0.0,
        description="Valor do imóvel ou crédito (base de cálculo) — legacy, mantido para compatibilidade"
    )
    applied_fee_type: Optional[str] = Field(
        default=None,
        description="Tipo de comissão aplicado: 'fixed' ou 'percentage' "
                    "(copiado da config no momento da criação/fecho) — legacy"
    )
    applied_fee_value: Optional[float] = Field(
        default=None,
        description="Valor ou % acordado neste processo — legacy"
    )

    # --- Bloco Comissão Imobiliária (Real Estate) ---
    real_estate_base_value: float = Field(
        default=0.0,
        description="Valor do imóvel (snapshot) — base de cálculo da comissão imobiliária"
    )
    real_estate_fee_type: Optional[str] = Field(
        default=None,
        description="Tipo de comissão imobiliária: 'fixed' ou 'percentage'"
    )
    real_estate_fee_value: Optional[float] = Field(
        default=None,
        description="Valor da comissão imobiliária (€ ou %)"
    )
    real_estate_commission: float = Field(
        default=0.0,
        description="Comissão imobiliária calculada"
    )

    # --- Bloco Comissão de Crédito (Credit) ---
    credit_base_value: float = Field(
        default=0.0,
        description="Valor do crédito/loan_amount (snapshot) — base de cálculo da comissão de crédito"
    )
    credit_fee_type: Optional[str] = Field(
        default=None,
        description="Tipo de comissão de crédito: 'fixed' ou 'percentage'"
    )
    credit_fee_value: Optional[float] = Field(
        default=None,
        description="Valor da comissão de crédito (€ ou %)"
    )
    credit_commission: float = Field(
        default=0.0,
        description="Comissão de crédito calculada"
    )

    # --- Totais ---
    expected_commission: float = Field(
        ..., description="Comissão esperada antes de impostos (real_estate_commission + credit_commission)"
    )
    tax_amount: float = Field(
        ..., description="Valor do imposto (IVA)"
    )
    total_with_tax: float = Field(
        ..., description="Valor total a faturar (comissão + impostos)"
    )
    status: str = Field(
        default=FinanceStatus.PENDING.value,
        description="Status financeiro: pending | invoiced | paid | cancelled"
    )
    invoice_link: Optional[str] = Field(
        default=None, description="Link para o PDF da fatura"
    )

    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @field_validator('applied_fee_type', mode='before')
    @classmethod
    def validate_applied_fee_type(cls, v):
        """Garantir que o applied_fee_type é válido (legacy)."""
        if v is None or v == '':
            return None
        v_lower = str(v).lower().strip()
        if v_lower not in FeeType.all_values():
            raise ValueError(
                f"applied_fee_type inválido: '{v}'. Valores permitidos: {FeeType.all_values()}"
            )
        return v_lower

    @field_validator('real_estate_fee_type', mode='before')
    @classmethod
    def validate_real_estate_fee_type(cls, v):
        """Garantir que o real_estate_fee_type é válido."""
        if v is None or v == '':
            return None
        v_lower = str(v).lower().strip()
        if v_lower not in FeeType.all_values():
            raise ValueError(
                f"real_estate_fee_type inválido: '{v}'. Valores permitidos: {FeeType.all_values()}"
            )
        return v_lower

    @field_validator('credit_fee_type', mode='before')
    @classmethod
    def validate_credit_fee_type(cls, v):
        """Garantir que o credit_fee_type é válido."""
        if v is None or v == '':
            return None
        v_lower = str(v).lower().strip()
        if v_lower not in FeeType.all_values():
            raise ValueError(
                f"credit_fee_type inválido: '{v}'. Valores permitidos: {FeeType.all_values()}"
            )
        return v_lower

    @field_validator('base_business_value', mode='before')
    @classmethod
    def coerce_base_business_value(cls, v):
        """Coerção para float, não-negativo (legacy)."""
        result = _coerce_to_non_negative_float(v)
        if result is None:
            return 0.0
        return result

    @field_validator('applied_fee_value', mode='before')
    @classmethod
    def coerce_applied_fee_value(cls, v, info: ValidationInfo):
        """Coerção para float, não-negativo. Valida range se applied_fee_type disponível (legacy)."""
        result = _coerce_to_non_negative_float(v)
        if result is None:
            return None
        # Validação cruzada: se applied_fee_type='percentage', valor ≤ 100
        fee_type = info.data.get('applied_fee_type', '')
        if fee_type == FeeType.PERCENTAGE.value and result > 100:
            raise ValueError(
                f"Com percentagem, applied_fee_value não pode ultrapassar 100 "
                f"(recebido: {result})"
            )
        return result

    @field_validator(
        'real_estate_base_value', 'credit_base_value',
        'real_estate_commission', 'credit_commission',
        mode='before'
    )
    @classmethod
    def coerce_non_negative_base_values(cls, v):
        """Coerção para float não-negativo dos valores base e comissões calculadas."""
        result = _coerce_to_non_negative_float(v)
        if result is None:
            return 0.0
        return result

    @field_validator('real_estate_fee_value', 'credit_fee_value', mode='before')
    @classmethod
    def coerce_fee_values(cls, v, info: ValidationInfo):
        """Coerção para float não-negativo dos valores de comissão. Valida range se fee_type disponível."""
        result = _coerce_to_non_negative_float(v)
        if result is None:
            return None
        # Validação cruzada: se fee_type='percentage', valor ≤ 100
        fee_type_field = 'real_estate_fee_type' if info.field_name == 'real_estate_fee_value' else 'credit_fee_type'
        fee_type = info.data.get(fee_type_field, '')
        if fee_type == FeeType.PERCENTAGE.value and result > 100:
            raise ValueError(
                f"Com percentagem, {info.field_name} não pode ultrapassar 100 "
                f"(recebido: {result})"
            )
        return result

    @field_validator('expected_commission', 'tax_amount', 'total_with_tax', mode='before')
    @classmethod
    def coerce_financial_fields(cls, v):
        """Coerção para float dos campos calculados."""
        result = _coerce_to_float(v)
        if result is None:
            return 0.0
        return result

    @field_validator('status', mode='before')
    @classmethod
    def validate_status(cls, v):
        """Garantir que o status é um valor válido."""
        if v is None or v == '':
            return FinanceStatus.PENDING.value
        v_lower = str(v).lower().strip()
        if v_lower not in FinanceStatus.all_values():
            raise ValueError(
                f"status inválido: '{v}'. Valores permitidos: {FinanceStatus.all_values()}"
            )
        return v_lower


class ProcessFinanceCreate(BaseModel):
    """
    Schema para criar os dados financeiros de um processo.

    Suporta DUPLA comissão (Real Estate + Credit):
    - Comissão Imobiliária: real_estate_base_value, real_estate_fee_type, real_estate_fee_value
    - Comissão de Crédito: credit_base_value, credit_fee_type, credit_fee_value

    O expected_commission, tax_amount e total_with_tax podem ser fornecidos
    explicitamente OU calculados automaticamente via compute_finance().

    Compatibilidade retroactiva:
    - Se os campos legacy (base_business_value, applied_fee_type, applied_fee_value)
      forem usados sem os novos campos de crédito, o cálculo é feito como antes
      e o resultado é armazenado em credit_commission.
    """
    process_id: str = Field(..., description="Referência ao ProcessModel")
    client_id: str = Field(..., description="Referência ao ClientModel")
    company_id: str = Field(..., description="Empresa para segurança e filtros")

    # --- Campos legacy (comissão única) ---
    base_business_value: float = Field(
        default=0.0,
        description="Valor base (imóvel ou crédito) — legacy, mantido para compatibilidade"
    )
    applied_fee_type: Optional[str] = Field(
        default=None,
        description="'fixed' ou 'percentage' — legacy"
    )
    applied_fee_value: Optional[float] = Field(
        default=None,
        description="Valor da comissão (€ ou %) — legacy"
    )

    # --- Bloco Comissão Imobiliária (Real Estate) ---
    real_estate_base_value: float = Field(
        default=0.0,
        description="Valor do imóvel (snapshot) — base de cálculo da comissão imobiliária"
    )
    real_estate_fee_type: Optional[str] = Field(
        default=None,
        description="Tipo de comissão imobiliária: 'fixed' ou 'percentage'"
    )
    real_estate_fee_value: Optional[float] = Field(
        default=None,
        description="Valor da comissão imobiliária (€ ou %)"
    )

    # --- Bloco Comissão de Crédito (Credit) ---
    credit_base_value: float = Field(
        default=0.0,
        description="Valor do crédito/loan_amount (snapshot) — base de cálculo da comissão de crédito"
    )
    credit_fee_type: Optional[str] = Field(
        default=None,
        description="Tipo de comissão de crédito: 'fixed' ou 'percentage'"
    )
    credit_fee_value: Optional[float] = Field(
        default=None,
        description="Valor da comissão de crédito (€ ou %)"
    )

    # --- Taxa de IVA ---
    tax_rate: Optional[float] = Field(
        default=23.0,
        description="Taxa de IVA a aplicar (ex: 23.0). Usado para cálculo automático."
    )

    # --- Campos calculados (podem sobrepor o cálculo automático) ---
    expected_commission: Optional[float] = Field(
        default=None,
        description="Se fornecido, sobrepõe o cálculo automático"
    )
    tax_amount: Optional[float] = Field(
        default=None,
        description="Se fornecido, sobrepõe o cálculo automático"
    )
    total_with_tax: Optional[float] = Field(
        default=None,
        description="Se fornecido, sobrepõe o cálculo automático"
    )
    status: Optional[str] = Field(default=FinanceStatus.PENDING.value)
    invoice_link: Optional[str] = None

    @field_validator('applied_fee_type', mode='before')
    @classmethod
    def validate_applied_fee_type(cls, v):
        """Validar applied_fee_type (legacy)."""
        if v is None or v == '':
            return None
        v_lower = str(v).lower().strip()
        if v_lower not in FeeType.all_values():
            raise ValueError(f"applied_fee_type inválido: '{v}'. Valores: {FeeType.all_values()}")
        return v_lower

    @field_validator('real_estate_fee_type', mode='before')
    @classmethod
    def validate_real_estate_fee_type(cls, v):
        """Garantir que o real_estate_fee_type é válido."""
        if v is None or v == '':
            return None
        v_lower = str(v).lower().strip()
        if v_lower not in FeeType.all_values():
            raise ValueError(
                f"real_estate_fee_type inválido: '{v}'. Valores permitidos: {FeeType.all_values()}"
            )
        return v_lower

    @field_validator('credit_fee_type', mode='before')
    @classmethod
    def validate_credit_fee_type(cls, v):
        """Garantir que o credit_fee_type é válido."""
        if v is None or v == '':
            return None
        v_lower = str(v).lower().strip()
        if v_lower not in FeeType.all_values():
            raise ValueError(
                f"credit_fee_type inválido: '{v}'. Valores permitidos: {FeeType.all_values()}"
            )
        return v_lower

    @field_validator('base_business_value', 'applied_fee_value', mode='before')
    @classmethod
    def coerce_legacy_non_negative_floats(cls, v, info: ValidationInfo):
        """Coerção para float não-negativo dos campos legacy."""
        result = _coerce_to_non_negative_float(v)
        if result is None:
            # Campos legacy são opcionais no novo modelo — permitir None
            return None
        # Validação cruzada: se applied_fee_type='percentage' e campo é applied_fee_value
        if info.field_name == 'applied_fee_value':
            fee_type = info.data.get('applied_fee_type', '')
            if fee_type == FeeType.PERCENTAGE.value and result > 100:
                raise ValueError(
                    f"Com percentagem, applied_fee_value não pode ultrapassar 100 "
                    f"(recebido: {result})"
                )
        return result

    @field_validator(
        'real_estate_base_value', 'credit_base_value',
        mode='before'
    )
    @classmethod
    def coerce_non_negative_base_values(cls, v):
        """Coerção para float não-negativo dos valores base."""
        result = _coerce_to_non_negative_float(v)
        if result is None:
            return 0.0
        return result

    @field_validator('real_estate_fee_value', 'credit_fee_value', mode='before')
    @classmethod
    def coerce_fee_values(cls, v, info: ValidationInfo):
        """Coerção para float não-negativo dos valores de comissão. Valida range se fee_type disponível."""
        result = _coerce_to_non_negative_float(v)
        if result is None:
            return None
        # Validação cruzada: se fee_type='percentage', valor ≤ 100
        fee_type_field = 'real_estate_fee_type' if info.field_name == 'real_estate_fee_value' else 'credit_fee_type'
        fee_type = info.data.get(fee_type_field, '')
        if fee_type == FeeType.PERCENTAGE.value and result > 100:
            raise ValueError(
                f"Com percentagem, {info.field_name} não pode ultrapassar 100 "
                f"(recebido: {result})"
            )
        return result

    @field_validator('tax_rate', mode='before')
    @classmethod
    def coerce_tax_rate(cls, v):
        result = _coerce_to_float(v)
        if result is None:
            return 23.0
        if result < 0:
            raise ValueError("tax_rate não pode ser negativa")
        if result > 100:
            raise ValueError("tax_rate não pode ultrapassar 100%")
        return result

    @field_validator('expected_commission', 'tax_amount', 'total_with_tax', mode='before')
    @classmethod
    def coerce_optional_floats(cls, v):
        if v is None or v == '':
            return None
        return _coerce_to_float(v)

    @field_validator('status', mode='before')
    @classmethod
    def validate_status(cls, v):
        if v is None or v == '':
            return FinanceStatus.PENDING.value
        v_lower = str(v).lower().strip()
        if v_lower not in FinanceStatus.all_values():
            raise ValueError(f"status inválido: '{v}'. Valores: {FinanceStatus.all_values()}")
        return v_lower

    def compute_finance(self) -> dict:
        """
        Calcular comissões (Real Estate + Credit), expected_commission, tax_amount e total_with_tax.

        Retorna um dict com os valores calculados que a camada de serviço
        deve usar para construir o ProcessFinance completo.

        Lógica:
        1. Comissão Imobiliária (real_estate_commission):
           - Se real_estate_fee_type='percentage': real_estate_base_value * (real_estate_fee_value / 100)
           - Se real_estate_fee_type='fixed': real_estate_fee_value
        2. Comissão de Crédito (credit_commission):
           - Se credit_fee_type='percentage': credit_base_value * (credit_fee_value / 100)
           - Se credit_fee_type='fixed': credit_fee_value
        3. expected_commission = real_estate_commission + credit_commission
        4. tax_amount = expected_commission * (tax_rate / 100)
        5. total_with_tax = expected_commission + tax_amount

        Compatibilidade retroactiva:
        - Se os campos legacy (base_business_value, applied_fee_type, applied_fee_value)
          forem usados sem os novos campos de crédito, o cálculo legacy é aplicado
          e o resultado é armazenado em credit_commission.
        - Se expected_commission/tax_amount/total_with_tax foram fornecidos
          explicitamente, usa esses valores (sobrepõe o cálculo).
        """
        # --- Calcular comissão imobiliária ---
        if self.real_estate_fee_type is not None and self.real_estate_fee_value is not None:
            if self.real_estate_fee_type == FeeType.PERCENTAGE.value:
                re_commission = round(
                    self.real_estate_base_value * (self.real_estate_fee_value / 100), 2
                )
            else:  # fixed
                re_commission = self.real_estate_fee_value
        else:
            re_commission = 0.0

        # --- Calcular comissão de crédito ---
        if self.credit_fee_type is not None and self.credit_fee_value is not None:
            if self.credit_fee_type == FeeType.PERCENTAGE.value:
                cr_commission = round(
                    self.credit_base_value * (self.credit_fee_value / 100), 2
                )
            else:  # fixed
                cr_commission = self.credit_fee_value
        elif self.applied_fee_type is not None and self.applied_fee_value is not None:
            # Compatibilidade retroactiva: usar campos legacy se novos campos de crédito não forem fornecidos
            if self.applied_fee_type == FeeType.PERCENTAGE.value:
                cr_commission = round(
                    self.base_business_value * (self.applied_fee_value / 100), 2
                )
            else:  # fixed
                cr_commission = self.applied_fee_value
        else:
            cr_commission = 0.0

        # --- Comissão total ---
        ec = re_commission + cr_commission

        # Se expected_commission foi fornecido explicitamente, sobrepor
        if self.expected_commission is not None:
            ec = self.expected_commission

        # --- Imposto ---
        ta = self.tax_amount if self.tax_amount is not None else round(ec * (self.tax_rate / 100), 2)

        # --- Total com imposto ---
        twt = self.total_with_tax if self.total_with_tax is not None else round(ec + ta, 2)

        return {
            'real_estate_commission': re_commission,
            'credit_commission': cr_commission,
            'expected_commission': ec,
            'tax_amount': ta,
            'total_with_tax': twt,
        }


class ProcessFinanceUpdate(BaseModel):
    """
    Schema para actualizar dados financeiros de um processo.

    Suporta actualização dos campos de dupla comissão (Real Estate + Credit).
    """
    # --- Campos legacy ---
    base_business_value: Optional[float] = None
    applied_fee_type: Optional[str] = None
    applied_fee_value: Optional[float] = None

    # --- Bloco Comissão Imobiliária (Real Estate) ---
    real_estate_base_value: Optional[float] = None
    real_estate_fee_type: Optional[str] = None
    real_estate_fee_value: Optional[float] = None
    real_estate_commission: Optional[float] = None

    # --- Bloco Comissão de Crédito (Credit) ---
    credit_base_value: Optional[float] = None
    credit_fee_type: Optional[str] = None
    credit_fee_value: Optional[float] = None
    credit_commission: Optional[float] = None

    # --- Totais ---
    expected_commission: Optional[float] = None
    tax_amount: Optional[float] = None
    total_with_tax: Optional[float] = None
    status: Optional[str] = None
    invoice_link: Optional[str] = None

    @field_validator('applied_fee_type', mode='before')
    @classmethod
    def validate_applied_fee_type(cls, v):
        if v is None or v == '':
            return None
        v_lower = str(v).lower().strip()
        if v_lower not in FeeType.all_values():
            raise ValueError(f"applied_fee_type inválido: '{v}'. Valores: {FeeType.all_values()}")
        return v_lower

    @field_validator('real_estate_fee_type', mode='before')
    @classmethod
    def validate_real_estate_fee_type(cls, v):
        """Garantir que o real_estate_fee_type é válido."""
        if v is None or v == '':
            return None
        v_lower = str(v).lower().strip()
        if v_lower not in FeeType.all_values():
            raise ValueError(
                f"real_estate_fee_type inválido: '{v}'. Valores permitidos: {FeeType.all_values()}"
            )
        return v_lower

    @field_validator('credit_fee_type', mode='before')
    @classmethod
    def validate_credit_fee_type(cls, v):
        """Garantir que o credit_fee_type é válido."""
        if v is None or v == '':
            return None
        v_lower = str(v).lower().strip()
        if v_lower not in FeeType.all_values():
            raise ValueError(
                f"credit_fee_type inválido: '{v}'. Valores permitidos: {FeeType.all_values()}"
            )
        return v_lower

    @field_validator(
        'base_business_value', 'applied_fee_value',
        'real_estate_base_value', 'real_estate_fee_value', 'real_estate_commission',
        'credit_base_value', 'credit_fee_value', 'credit_commission',
        'expected_commission', 'tax_amount', 'total_with_tax',
        mode='before'
    )
    @classmethod
    def coerce_optional_floats(cls, v):
        if v is None or v == '':
            return None
        return _coerce_to_float(v)

    @field_validator('status', mode='before')
    @classmethod
    def validate_status(cls, v):
        if v is None or v == '':
            return None
        v_lower = str(v).lower().strip()
        if v_lower not in FinanceStatus.all_values():
            raise ValueError(f"status inválido: '{v}'. Valores: {FinanceStatus.all_values()}")
        return v_lower


class ProcessFinanceResponse(BaseModel):
    """
    Modelo de resposta para dados financeiros de um processo.

    Inclui todos os campos de dupla comissão (Real Estate + Credit).
    """
    model_config = ConfigDict(extra="ignore")
    id: str
    process_id: str
    client_id: str
    company_id: str

    # --- Campos legacy ---
    base_business_value: float = 0.0
    applied_fee_type: Optional[str] = None
    applied_fee_value: Optional[float] = None

    # --- Bloco Comissão Imobiliária (Real Estate) ---
    real_estate_base_value: float = 0.0
    real_estate_fee_type: Optional[str] = None
    real_estate_fee_value: Optional[float] = None
    real_estate_commission: float = 0.0

    # --- Bloco Comissão de Crédito (Credit) ---
    credit_base_value: float = 0.0
    credit_fee_type: Optional[str] = None
    credit_fee_value: Optional[float] = None
    credit_commission: float = 0.0

    # --- Totais ---
    expected_commission: float
    tax_amount: float
    total_with_tax: float
    status: str
    invoice_link: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class ProcessFinanceSummary(BaseModel):
    """
    Resumo financeiro agregado (útil para dashboards).

    Agrega totais por status para uma empresa ou processo.
    Inclui totais separados para comissão imobiliária e de crédito.
    """
    total_pending: float = 0.0
    total_invoiced: float = 0.0
    total_paid: float = 0.0
    total_cancelled: float = 0.0
    total_expected: float = 0.0      # soma de todas as comissões esperadas (activas)
    total_with_tax: float = 0.0      # soma total a faturar (activos)
    total_real_estate_commission: float = 0.0  # soma das comissões imobiliárias
    total_credit_commission: float = 0.0       # soma das comissões de crédito
    count_pending: int = 0
    count_invoiced: int = 0
    count_paid: int = 0
    count_cancelled: int = 0

"""
Modelos do Módulo Financeiro — CREDITOIMO

Este módulo gere dois conceitos isolados:

1. FinanceConfig  — Configuração financeira da empresa (comissões/honorários).
    Define se a empresa cobra valor fixo ou percentagem, o valor por omissão,
    e a taxa de imposto (IVA) a aplicar. Uma configuração por empresa (multi-tenant).

2. ProcessFinance — Dados financeiros isolados de um Processo.
    Snapshot imutável da comissão no momento do fecho, garantindo que alterações
    na configuração da empresa NÃO afectam processos já fechados.
    Inclui cálculos automáticos de impostos e total a faturar.

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

    Cálculos automáticos:
    - expected_commission = base_business_value * (applied_fee_value / 100)  [se percentage]
                           ou applied_fee_value [se fixed]
    - tax_amount = expected_commission * (tax_rate / 100)
    - total_with_tax = expected_commission + tax_amount
    """
    id: str
    process_id: str = Field(..., description="Referência ao ProcessModel")
    client_id: str = Field(..., description="Referência ao ClientModel")
    company_id: str = Field(..., description="Empresa para segurança e filtros multi-tenant")

    base_business_value: float = Field(
        ..., description="Valor do imóvel ou crédito (base de cálculo)"
    )
    applied_fee_type: str = Field(
        ...,
        description="Tipo de comissão aplicado: 'fixed' ou 'percentage' "
                    "(copiado da config no momento da criação/fecho)"
    )
    applied_fee_value: float = Field(
        ...,
        description="Valor ou % acordado neste processo "
                    "(copiado da config ou sobreposto manualmente)"
    )
    expected_commission: float = Field(
        ..., description="Comissão esperada antes de impostos"
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
        """Garantir que o applied_fee_type é válido."""
        if v is None or v == '':
            raise ValueError("applied_fee_type é obrigatório")
        v_lower = str(v).lower().strip()
        if v_lower not in FeeType.all_values():
            raise ValueError(
                f"applied_fee_type inválido: '{v}'. Valores permitidos: {FeeType.all_values()}"
            )
        return v_lower

    @field_validator('base_business_value', mode='before')
    @classmethod
    def coerce_base_business_value(cls, v):
        """Coerção para float, não-negativo."""
        result = _coerce_to_non_negative_float(v)
        if result is None:
            raise ValueError("base_business_value é obrigatório e deve ser um número válido")
        return result

    @field_validator('applied_fee_value', mode='before')
    @classmethod
    def coerce_applied_fee_value(cls, v, info: ValidationInfo):
        """Coerção para float, não-negativo. Valida range se applied_fee_type disponível."""
        result = _coerce_to_non_negative_float(v)
        if result is None:
            raise ValueError("applied_fee_value é obrigatório e deve ser um número válido")
        # Validação cruzada: se applied_fee_type='percentage', valor ≤ 100
        fee_type = info.data.get('applied_fee_type', '')
        if fee_type == FeeType.PERCENTAGE.value and result > 100:
            raise ValueError(
                f"Com percentagem, applied_fee_value não pode ultrapassar 100 "
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

    O expected_commission, tax_amount e total_with_tax podem ser fornecidos
    explicitamente OU calculados automaticamente via compute_finance().

    O cálculo automático é feito pelo método compute_finance() que deve ser
    chamado pela camada de serviço após instanciação.
    """
    process_id: str = Field(..., description="Referência ao ProcessModel")
    client_id: str = Field(..., description="Referência ao ClientModel")
    company_id: str = Field(..., description="Empresa para segurança e filtros")
    base_business_value: float = Field(..., description="Valor base (imóvel ou crédito)")
    applied_fee_type: str = Field(..., description="'fixed' ou 'percentage'")
    applied_fee_value: float = Field(..., description="Valor da comissão (€ ou %)")
    tax_rate: Optional[float] = Field(
        default=23.0,
        description="Taxa de IVA a aplicar (ex: 23.0). Usado para cálculo automático."
    )
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
        if v is None or v == '':
            raise ValueError("applied_fee_type é obrigatório")
        v_lower = str(v).lower().strip()
        if v_lower not in FeeType.all_values():
            raise ValueError(f"applied_fee_type inválido: '{v}'. Valores: {FeeType.all_values()}")
        return v_lower

    @field_validator('base_business_value', 'applied_fee_value', mode='before')
    @classmethod
    def coerce_non_negative_floats(cls, v, info: ValidationInfo):
        result = _coerce_to_non_negative_float(v)
        if result is None:
            raise ValueError("Valor obrigatório e deve ser um número não-negativo")
        # Validação cruzada: se applied_fee_type='percentage' e campo é applied_fee_value
        if info.field_name == 'applied_fee_value':
            fee_type = info.data.get('applied_fee_type', '')
            if fee_type == FeeType.PERCENTAGE.value and result > 100:
                raise ValueError(
                    f"Com percentagem, applied_fee_value não pode ultrapassar 100 "
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
        Calcular expected_commission, tax_amount e total_with_tax.

        Retorna um dict com os valores calculados que a camada de serviço
        deve usar para construir o ProcessFinance completo.

        Se expected_commission/tax_amount/total_with_tax foram fornecidos
        explicitamente, usa esses valores (sobrepõe o cálculo).
        """
        # Calcular expected_commission
        if self.expected_commission is not None:
            ec = self.expected_commission
        elif self.applied_fee_type == FeeType.PERCENTAGE.value:
            ec = round(self.base_business_value * (self.applied_fee_value / 100), 2)
        else:  # fixed
            ec = self.applied_fee_value

        # Calcular tax_amount
        ta = self.tax_amount if self.tax_amount is not None else round(ec * (self.tax_rate / 100), 2)

        # Calcular total_with_tax
        twt = self.total_with_tax if self.total_with_tax is not None else round(ec + ta, 2)

        return {
            'expected_commission': ec,
            'tax_amount': ta,
            'total_with_tax': twt,
        }


class ProcessFinanceUpdate(BaseModel):
    """Schema para actualizar dados financeiros de um processo."""
    base_business_value: Optional[float] = None
    applied_fee_type: Optional[str] = None
    applied_fee_value: Optional[float] = None
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

    @field_validator(
        'base_business_value', 'applied_fee_value',
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
    """Modelo de resposta para dados financeiros de um processo."""
    model_config = ConfigDict(extra="ignore")
    id: str
    process_id: str
    client_id: str
    company_id: str
    base_business_value: float
    applied_fee_type: str
    applied_fee_value: float
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
    """
    total_pending: float = 0.0
    total_invoiced: float = 0.0
    total_paid: float = 0.0
    total_cancelled: float = 0.0
    total_expected: float = 0.0      # soma de todas as comissões esperadas (activas)
    total_with_tax: float = 0.0      # soma total a faturar (activos)
    count_pending: int = 0
    count_invoiced: int = 0
    count_paid: int = 0
    count_cancelled: int = 0

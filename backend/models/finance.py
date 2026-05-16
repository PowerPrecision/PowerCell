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

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

# ==========================================
# MODELO: CONFIGURAÇÕES FINANCEIRAS DA EMPRESA
# ==========================================
class FinanceConfig(BaseModel):
    id: Optional[str] = Field(default=None, alias="_id")
    company_id: str = Field(..., description="ID da empresa (Multi-Tenant)")
    fee_type: str = Field(..., description="Tipo de cobrança: 'fixed' ou 'percentage'")
    default_value: float = Field(..., description="Valor fixo ou percentagem (ex: 5.0 para 5%)")
    tax_rate: float = Field(default=23.0, description="Taxa de imposto (ex: 23.0 para IVA)")
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

# ==========================================
# MODELO: DADOS FINANCEIROS DO PROCESSO (SNAPSHOT)
# ==========================================
class ProcessFinance(BaseModel):
    id: Optional[str] = Field(default=None, alias="_id")
    process_id: str = Field(..., description="Referência ao Processo")
    client_id: str = Field(..., description="Referência ao Cliente")
    company_id: str = Field(..., description="ID da empresa para segurança e filtros")
    
    # Valores Base e Snapshot
    base_business_value: float = Field(default=0.0, description="Valor do negócio que serve de base")
    applied_fee_type: str = Field(..., description="Cópia do fee_type no momento do fecho ('fixed' ou 'percentage')")
    applied_fee_value: float = Field(..., description="Cópia do valor acordado no momento do fecho")
    
    # Valores Calculados
    expected_commission: float = Field(default=0.0, description="Valor calculado da comissão sem IVA")
    tax_amount: float = Field(default=0.0, description="Valor do imposto/IVA")
    total_with_tax: float = Field(default=0.0, description="Valor total a faturar")
    
    # Estado da Faturação
    status: str = Field(default="pending", description="Estados: pending, invoiced, paid, cancelled")
    invoice_link: Optional[str] = Field(default=None, description="Link para o PDF da Fatura (S3 ou OneDrive)")
    
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

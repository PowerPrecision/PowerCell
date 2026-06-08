"""
Serviço de Cálculo Automático DSTI (Debt-Service to Income Ratio)

Calcula automaticamente a taxa de esforço a partir dos dados extraídos pela IA:
- Rendimento líquido (de recibos de vencimento e IRS)
- Mapa de Responsabilidades / CRC (créditos ativos e prestações)

Fórmulas:
- DSTI = (Prestações de crédito) / (Rendimento bruto total) × 100
- Taxa de Esforço Global = (Todas as despesas) / (Rendimento bruto total) × 100

Classificação de risco (Banco de Portugal):
- ≤30%: Baixo risco
- 30-40%: Risco moderado
- 40-50%: Risco elevado
- >50%: Ultrapassa o limite do BdP para novos créditos
"""
import logging
from typing import Dict, Any, Optional
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def calculate_dsti(process: Dict[str, Any]) -> Dict[str, Any]:
    """
    Calcula o DSTI automático a partir dos dados do processo.
    
    Args:
        process: Documento do processo da BD (com personal_data, financial_data, etc.)
            Se existir second_client_data (populado por populate_client_data),
            os rendimentos e despesas do 2º titular são somados automaticamente.
    
    Returns:
        Dict com:
        - dsti_pct: DSTI em percentagem
        - effort_rate_pct: Taxa de esforço global em percentagem
        - risk_level: "baixo", "moderado", "elevado", "critico", "sem_dados"
        - risk_color: cor hexadecimal
        - components: breakdown dos valores usados
        - available_income: rendimento disponível após despesas
        - max_installment: prestação máxima permitida (50% do rendimento)
        - is_calculable: se há dados suficientes para calcular
        - calculated_at: timestamp ISO
    """
    financial = process.get("financial_data") or {}
    personal = process.get("personal_data") or {}
    second_client_data = process.get("second_client_data") or {}
    second_financial = second_client_data.get("financial_data") if second_client_data else {}
    
    # === RENDIMENTOS DO TITULAR PRINCIPAL ===
    # Prioridade: rendimento_liquido_total (agregado de todos os recibos)
    # Fallback: rendimento_mensal (recibo único) ou monthly_income
    rendimento_bruto = _safe_float(financial.get("rendimento_bruto_mensal"))
    rendimento_liquido = _safe_float(financial.get("rendimento_liquido_total")) or \
                        _safe_float(financial.get("rendimento_mensal")) or \
                        _safe_float(financial.get("monthly_income")) or \
                        _safe_float(financial.get("rendimento_mensal_irs"))
    
    # Se só temos o líquido, estimar bruto (aprox +33%)
    if rendimento_bruto <= 0 and rendimento_liquido > 0:
        rendimento_bruto = rendimento_liquido * 1.333
    elif rendimento_bruto > 0 and rendimento_liquido <= 0:
        rendimento_liquido = rendimento_bruto * 0.75
    
    # === RENDIMENTOS DO 2º TITULAR (via second_client_id) ===
    # Se o processo tem second_client_id, os rendimentos vêm do financial_data
    # desse cliente (populado por populate_client_data → second_client_data).
    # Prioridade: second_client_data.financial_data (dados do cliente ligado)
    # Fallback: financial_data.rendimento_co_titular (campo legacy no processo)
    rendimento_co_titular = 0.0
    despesas_co_titular = 0.0
    
    if second_financial:
        # 2º titular ligado via second_client_id — somar rendimentos da ficha dele
        rendimento_co_titular = (
            _safe_float(second_financial.get("rendimento_liquido_total")) or
            _safe_float(second_financial.get("rendimento_mensal")) or
            _safe_float(second_financial.get("monthly_income")) or
            _safe_float(second_financial.get("rendimento_mensal_irs"))
        )
        despesas_co_titular = (
            _safe_float(second_financial.get("despesas_mensais")) +
            _safe_float(second_financial.get("prestacao_creditos_mensal")) +
            _safe_float(second_financial.get("renda_habitacao_atual"))
        )
    
    # Fallback: campo legacy rendimento_co_titular no financial_data do processo
    if rendimento_co_titular <= 0:
        rendimento_co_titular = _safe_float(financial.get("rendimento_co_titular"))
    
    rendimento_bruto_co = rendimento_co_titular * 1.333 if rendimento_co_titular > 0 else 0
    rendimento_liquido_co = rendimento_co_titular if rendimento_co_titular > 0 else 0
    
    # Totais
    rendimento_bruto_total = rendimento_bruto + rendimento_bruto_co
    rendimento_liquido_total = rendimento_liquido + rendimento_liquido_co
    
    # === DESPESAS DE CRÉDITO ===
    # Do mapa de responsabilidades (CRC)
    prestacao_creditos = _safe_float(financial.get("prestacao_creditos_mensal"))
    divida_total_crc = _safe_float(financial.get("divida_total_crc"))
    numero_creditos = _safe_float(financial.get("numero_creditos_ativos"))
    
    # Se não tem prestação total mas tem lista de créditos, somar
    if prestacao_creditos <= 0:
        creditos_ativos = financial.get("creditos_ativos") or []
        if isinstance(creditos_ativos, list):
            prestacao_creditos = sum(
                _safe_float(c.get("prestacao") or c.get("prestacao_mensal"))
                for c in creditos_ativos
            )
    
    # Renda de habitação
    renda_habitacao = _safe_float(financial.get("renda_habitacao_atual"))
    
    # Somar despesas do 2º titular (se existirem)
    despesas_totais = prestacao_creditos + renda_habitacao + despesas_co_titular
    
    # === CÁLCULOS ===
    dsti = 0.0
    effort_rate = 0.0
    disponibilidade = 0.0
    max_installment = 0.0
    
    is_calculable = rendimento_bruto_total > 0
    
    if is_calculable:
        # DSTI = Prestações de crédito / Rendimento bruto total × 100
        dsti = (prestacao_creditos / rendimento_bruto_total) * 100
        
        # Taxa de esforço global = (créditos + renda + despesas_co) / Rendimento bruto × 100
        effort_rate = (despesas_totais / rendimento_bruto_total) * 100
        
        # Disponibilidade mensal (rendimento líquido - despesas totais)
        disponibilidade = rendimento_liquido_total - despesas_totais
        
        # Prestação máxima respeitando o limite de 50% do BdP
        max_installment = (rendimento_bruto_total * 0.50) - prestacao_creditos - renda_habitacao - despesas_co_titular
    
    # === CLASSIFICAÇÃO DE RISCO ===
    risk_level, risk_color = _classify_risk(dsti)
    
    # Se não há dados suficientes
    if not is_calculable:
        risk_level = "sem_dados"
        risk_color = "#94a3b8"  # slate-400
    
    return {
        "dsti_pct": round(dsti, 2),
        "effort_rate_pct": round(effort_rate, 2),
        "risk_level": risk_level,
        "risk_color": risk_color,
        "components": {
            "rendimento_bruto_titular": round(rendimento_bruto, 2),
            "rendimento_bruto_co_titular": round(rendimento_bruto_co, 2),
            "rendimento_bruto_total": round(rendimento_bruto_total, 2),
            "rendimento_liquido_total": round(rendimento_liquido_total, 2),
            "prestacao_creditos_mensal": round(prestacao_creditos, 2),
            "renda_habitacao": round(renda_habitacao, 2),
            "despesas_co_titular": round(despesas_co_titular, 2),
            "divida_total_crc": round(divida_total_crc, 2),
            "numero_creditos": int(numero_creditos),
        },
        "available_income": round(disponibilidade, 2),
        "max_installment": round(max_installment, 2),
        "is_calculable": is_calculable,
        "calculated_at": datetime.now(timezone.utc).isoformat(),
    }


def _safe_float(value) -> float:
    """Converte valor para float de forma segura."""
    if value is None:
        return 0.0
    try:
        result = float(value)
        return result if result > 0 else 0.0
    except (ValueError, TypeError):
        return 0.0


def _classify_risk(dsti: float) -> tuple:
    """
    Classifica o nível de risco baseado no DSTI.
    
    Returns:
        (risk_level, risk_color) tuple
    
    Limiares:
    - ≤30%: Baixo risco (verde)
    - 30-40%: Risco moderado (amarelo)
    - 40-50%: Risco elevado (laranja)
    - >50%: Risco crítico (vermelho) - ultrapassa limite BdP
    """
    if dsti <= 30:
        return "baixo", "#22c55e"  # green-500
    elif dsti <= 40:
        return "moderado", "#eab308"  # yellow-500
    elif dsti <= 50:
        return "elevado", "#f97316"  # orange-500
    else:
        return "critico", "#ef4444"  # red-500


def get_risk_label(risk_level: str) -> str:
    """Retorna label legível para o nível de risco."""
    labels = {
        "sem_dados": "Sem dados",
        "baixo": "Baixo Risco",
        "moderado": "Risco Moderado",
        "elevado": "Risco Elevado",
        "critico": "Risco Crítico",
    }
    return labels.get(risk_level, "Desconhecido")


def is_high_risk(dsti_result: Dict[str, Any], high_threshold: float = 40.0) -> bool:
    """
    Verifica se o resultado DSTI é de alto risco.
    Usado para alertas no dashboard.
    """
    return dsti_result.get("is_calculable", False) and dsti_result.get("dsti_pct", 0) >= high_threshold

"""
Motor de Simulação Financeira Automatizada — DSTI & Cenários de Crédito.

ÉPICO "Motor de Simulação Financeira": quando a Indexação valida os
documentos financeiros de um processo de Crédito Habitação (IRS, recibos de
vencimento), este módulo calcula automaticamente três cenários de
financiamento — **Taxa Fixa**, **Taxa Mista** e **Taxa Variável** — cruzando
os rendimentos extraídos com a Euribor em vigor e com o DSTI do processo.

FRONTEIRA DESTE MÓDULO (deliberada):
    Este ficheiro é **puro**: recebe dicionários, devolve dicionários e só
    faz I/O nas duas funções ``async`` do fundo (configuração + Euribor).
    Toda a orquestração com efeitos (extracção OCR, TaskLog, PDF, S3,
    persistência) vive em ``services/financial_engine.py``. É esta fronteira
    que torna o motor testável sem MongoDB (``tests/unit``).

REUTILIZAÇÃO (nada de matemática duplicada):
    - DSTI / classificação de risco / limiares do Banco de Portugal →
      ``services/dsti_service.py`` (``calculate_dsti``, ``_classify_risk``,
      ``get_risk_label``). É o motor DSTI canónico do produto.
    - Sistema Francês de amortização + TAEG por bisseção → porta fiel de
      ``frontend/src/utils/mortgageCalculations.js``
      (``calcularPrestacaoMensal`` / ``calcularTAEG``), o motor já usado pelo
      Simulador do Portal do Cliente e pelas Calculadoras do CRM. Manter as
      duas implementações alinhadas: mesmos nomes, mesma ordem de operações.
    - Conversão monetária tolerante → ``services/finance_helpers._safe_float``
      (família ``finance_*``).

ZERO HARDCODING:
    Spreads, índice Euribor, prémio da taxa fixa e período fixo da taxa
    mista vêm de ``SystemConfig.financial_simulator``. Prazo por defeito,
    LTV máximo e validade da proposta vêm de ``SystemConfig.credit_services``
    (já existentes — não duplicados). O limite DSTI vem de
    ``SystemConfig.dsti_analysis.critical_risk_threshold``.

DEGRADAÇÃO GRACIOSA:
    Sem rendimento legível (IRS ilegível, recibos sem valores) o motor NÃO
    levanta excepção nem inventa números: devolve
    ``{"success": False, "reason": ..., "missing": [...]}`` para que o
    orquestrador registe o pedido de revisão manual no processo.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from services.finance_helpers import _safe_float

logger = logging.getLogger(__name__)

# ====================================================================
# CONSTANTES DE DOMÍNIO
# ====================================================================

MONTHS_PER_YEAR = 12

SCENARIO_FIXA = "fixa"
SCENARIO_MISTA = "mista"
SCENARIO_VARIAVEL = "variavel"

# Ordem canónica de apresentação (PDF e API seguem esta ordem)
SCENARIO_ORDER = (SCENARIO_FIXA, SCENARIO_MISTA, SCENARIO_VARIAVEL)

SCENARIO_LABELS = {
    SCENARIO_FIXA: "Taxa Fixa",
    SCENARIO_MISTA: "Taxa Mista",
    SCENARIO_VARIAVEL: "Taxa Variável",
}

SCENARIO_DESCRIPTIONS = {
    SCENARIO_FIXA: (
        "Prestação constante durante todo o prazo. Protege de subidas da "
        "Euribor, mas não beneficia de descidas."
    ),
    SCENARIO_MISTA: (
        "Taxa fixa no período inicial e, findo esse período, taxa indexada "
        "à Euribor acrescida do spread."
    ),
    SCENARIO_VARIAVEL: (
        "Taxa indexada à Euribor acrescida do spread, revista a cada "
        "período de indexação. Prestação acompanha o mercado."
    ),
}

# Índices Euribor suportados (chaves de `euribor_service.get_euribor_rates`)
EURIBOR_INDEXES = ("1m", "3m", "6m", "12m")

# Motivos de indisponibilidade (contrato com `financial_engine`)
REASON_NO_INCOME = "sem_rendimento"
REASON_NO_CAPITAL = "sem_capital"

# Precisão da bisseção da TAEG (espelha o JS: 100 iterações / 1e-7)
_TAEG_MAX_ITERATIONS = 100
_TAEG_TOLERANCE = 0.0000001


# ====================================================================
# MATEMÁTICA PURA — Sistema Francês de Amortização
# (porta de frontend/src/utils/mortgageCalculations.js)
# ====================================================================


def calcular_prestacao_mensal(
    capital: Any,
    taxa_anual_pct: Any,
    num_meses: Any,
) -> float:
    """Prestação mensal do sistema francês (capital + juros, sem seguros).

    ``PMT = (M * r) / (1 - (1 + r)^-n)``, com ``r`` = taxa mensal.

    Args:
        capital: Capital em dívida no início do período (€).
        taxa_anual_pct: TAN anual em percentagem (ex.: ``3.5``).
        num_meses: Número total de prestações do período.

    Returns:
        Prestação mensal em euros; ``0.0`` se os parâmetros forem inválidos.
        Taxa nula (ou negativa) degrada para amortização linear ``M / n``,
        igual ao comportamento do simulador do frontend.
    """
    m = _safe_float(capital)
    n = int(_safe_float(num_meses))
    if m <= 0 or n <= 0:
        return 0.0

    r = _safe_float(taxa_anual_pct) / 100 / MONTHS_PER_YEAR
    if r <= 0:
        return m / n

    fator = (1 + r) ** (-n)
    return (m * r) / (1 - fator)


def calcular_capital_em_divida(
    capital: Any,
    taxa_anual_pct: Any,
    num_meses: Any,
    meses_pagos: Any,
) -> float:
    """Saldo devedor após ``meses_pagos`` prestações (sistema francês).

    Necessário para o cenário de **Taxa Mista**: findo o período de taxa
    fixa, a prestação é recalculada sobre o capital que ainda falta
    amortizar e sobre o prazo remanescente.

    ``saldo_k = M*(1+r)^k - PMT * (((1+r)^k - 1) / r)``
    """
    m = _safe_float(capital)
    n = int(_safe_float(num_meses))
    k = int(_safe_float(meses_pagos))
    if m <= 0 or n <= 0:
        return 0.0
    if k <= 0:
        return round(m, 2)
    if k >= n:
        return 0.0

    r = _safe_float(taxa_anual_pct) / 100 / MONTHS_PER_YEAR
    if r <= 0:
        # Amortização linear (coerente com `calcular_prestacao_mensal`)
        return round(m * (1 - k / n), 2)

    prestacao = calcular_prestacao_mensal(m, taxa_anual_pct, n)
    fator = (1 + r) ** k
    saldo = m * fator - prestacao * ((fator - 1) / r)
    return round(max(saldo, 0.0), 2)


def calcular_taeg_fluxos(capital_liquido: Any, fluxos_mensais: list) -> float:
    """TAEG (%) por bisseção sobre uma série arbitrária de fluxos mensais.

    Generaliza ``calcularTAEG`` do frontend (que assume prestação
    constante) para suportar o cenário de Taxa Mista, cujo fluxo muda no
    fim do período de taxa fixa.

    Args:
        capital_liquido: Capital efectivamente recebido pelo cliente
            (montante do empréstimo menos comissões iniciais).
        fluxos_mensais: Pagamentos mensais do cliente (prestação + seguros).

    Returns:
        TAEG anual em percentagem, ou ``0.0`` se os dados forem inválidos.
    """
    capital = _safe_float(capital_liquido)
    fluxos = [_safe_float(f) for f in (fluxos_mensais or [])]
    if capital <= 0 or not fluxos or sum(fluxos) <= 0:
        return 0.0

    lo = 0.000001   # 0,0001% mensal
    hi = 0.1        # 10% mensal (~120% anual) — limite superior generoso
    mid = 0.0

    for _ in range(_TAEG_MAX_ITERATIONS):
        mid = (lo + hi) / 2
        # Valor presente dos fluxos à taxa mensal `mid`
        vp = 0.0
        for periodo, fluxo in enumerate(fluxos, start=1):
            vp += fluxo / ((1 + mid) ** periodo)
        if vp > capital:
            lo = mid  # taxa demasiado baixa → VP alto → subir taxa
        else:
            hi = mid
        if hi - lo < _TAEG_TOLERANCE:
            break

    return mid * MONTHS_PER_YEAR * 100


def calcular_taeg(
    capital_liquido: Any,
    prestacao_base: Any,
    seguros_mensal: Any,
    num_meses: Any,
) -> float:
    """TAEG (%) para prestação constante — assinatura espelho do frontend."""
    n = int(_safe_float(num_meses))
    if n <= 0:
        return 0.0
    fluxo = _safe_float(prestacao_base) + _safe_float(seguros_mensal)
    return calcular_taeg_fluxos(capital_liquido, [fluxo] * n)


# ====================================================================
# RESOLUÇÃO DE TAXAS (Euribor + spreads configurados)
# ====================================================================


def resolve_euribor_index(euribor_rates: dict, index: Optional[str]) -> dict:
    """Escolhe o índice Euribor a usar, com fallback pelas maturidades.

    Args:
        euribor_rates: Payload de ``euribor_service.get_euribor_rates()``.
        index: Maturidade pedida na configuração ("1m"|"3m"|"6m"|"12m").

    Returns:
        ``{"index": str, "rate_pct": float, "is_fallback": bool,
        "source": str, "fetched_at": str|None}``. ``rate_pct`` é ``0.0`` e
        ``is_fallback`` é ``True`` quando não há qualquer taxa utilizável.
    """
    rates = euribor_rates or {}
    wanted = (index or "").strip().lower()
    candidates = [wanted] if wanted in EURIBOR_INDEXES else []
    # Fallback: 12m primeiro (a mais usada em CH), depois as restantes
    candidates += [i for i in ("12m", "6m", "3m", "1m") if i not in candidates]

    for candidate in candidates:
        value = rates.get(f"euribor_{candidate}")
        if value is None:
            continue
        rate = _safe_float(value)
        if rate <= 0:
            continue
        return {
            "index": candidate,
            "rate_pct": round(rate, 3),
            "is_fallback": bool(rates.get("is_fallback")) or candidate != wanted,
            "source": rates.get("source") or "desconhecida",
            "fetched_at": rates.get("fetched_at"),
        }

    logger.warning(
        "[SIMULADOR] Nenhuma taxa Euribor utilizável no payload "
        f"(índice pedido='{wanted}')"
    )
    return {
        "index": wanted or "12m",
        "rate_pct": 0.0,
        "is_fallback": True,
        "source": rates.get("source") or "indisponivel",
        "fetched_at": rates.get("fetched_at"),
    }


def build_scenario_definitions(
    *,
    euribor_pct: float,
    sim_config: Any,
    num_meses: int,
) -> list[dict]:
    """Define as taxas dos 3 cenários a partir do índice e da configuração.

    - **Fixa**: não indexada — ``índice + prémio de taxa fixa + spread fixa``
      durante todo o prazo (aproximação de preçário enquanto o sistema não
      tiver tabelas de banco carregadas; o PDF identifica-a como estimativa).
    - **Mista**: taxa fixa (mesmo prémio, spread da mista) nos primeiros
      ``periodo_fixo_mista_anos`` anos; depois ``índice + spread da mista``.
    - **Variável**: ``índice + spread variável`` durante todo o prazo.
    """
    base = _safe_float(euribor_pct)
    spread_fixa = _safe_float(getattr(sim_config, "spread_fixa", 0))
    spread_mista = _safe_float(getattr(sim_config, "spread_mista", 0))
    spread_variavel = _safe_float(getattr(sim_config, "spread_variavel", 0))
    premio = _safe_float(getattr(sim_config, "premio_taxa_fixa", 0))

    periodo_fixo_anos = int(
        _safe_float(getattr(sim_config, "periodo_fixo_mista_anos", 0))
    )
    periodo_fixo_meses = min(periodo_fixo_anos * MONTHS_PER_YEAR, num_meses)

    taxa_fixa = round(base + premio + spread_fixa, 3)
    taxa_mista_inicial = round(base + premio + spread_mista, 3)
    taxa_mista_posterior = round(base + spread_mista, 3)
    taxa_variavel = round(base + spread_variavel, 3)

    return [
        {
            "key": SCENARIO_FIXA,
            "label": SCENARIO_LABELS[SCENARIO_FIXA],
            "descricao": SCENARIO_DESCRIPTIONS[SCENARIO_FIXA],
            "indexado": False,
            "spread_pct": round(spread_fixa, 3),
            "taxa_inicial_pct": taxa_fixa,
            "taxa_posterior_pct": taxa_fixa,
            "periodo_fixo_meses": num_meses,
        },
        {
            "key": SCENARIO_MISTA,
            "label": SCENARIO_LABELS[SCENARIO_MISTA],
            "descricao": SCENARIO_DESCRIPTIONS[SCENARIO_MISTA],
            "indexado": True,
            "spread_pct": round(spread_mista, 3),
            "taxa_inicial_pct": taxa_mista_inicial,
            "taxa_posterior_pct": taxa_mista_posterior,
            "periodo_fixo_meses": periodo_fixo_meses,
        },
        {
            "key": SCENARIO_VARIAVEL,
            "label": SCENARIO_LABELS[SCENARIO_VARIAVEL],
            "descricao": SCENARIO_DESCRIPTIONS[SCENARIO_VARIAVEL],
            "indexado": True,
            "spread_pct": round(spread_variavel, 3),
            "taxa_inicial_pct": taxa_variavel,
            "taxa_posterior_pct": taxa_variavel,
            "periodo_fixo_meses": 0,
        },
    ]


# ====================================================================
# SIMULAÇÃO DE UM CENÁRIO
# ====================================================================


def simulate_scenario(
    *,
    definition: dict,
    capital: Any,
    num_meses: Any,
    seguros_mensal: Any = 0.0,
    comissoes_iniciais: Any = 0.0,
) -> dict:
    """Projecta prestações, juros e TAEG de um cenário.

    Suporta cenários de dois patamares (Taxa Mista): a prestação posterior
    é recalculada sobre o capital em dívida no fim do período fixo e sobre
    o prazo remanescente.

    Returns:
        Dict pronto para a API e para o PDF (valores já arredondados a
        2 casas decimais; taxas a 3).
    """
    m = _safe_float(capital)
    n = int(_safe_float(num_meses))
    seguros = _safe_float(seguros_mensal)
    comissoes = _safe_float(comissoes_iniciais)

    taxa_inicial = _safe_float(definition.get("taxa_inicial_pct"))
    taxa_posterior = _safe_float(definition.get("taxa_posterior_pct"))
    periodo_fixo = int(_safe_float(definition.get("periodo_fixo_meses")))
    periodo_fixo = max(0, min(periodo_fixo, n))

    prestacao_inicial = calcular_prestacao_mensal(m, taxa_inicial, n)

    tem_segundo_patamar = 0 < periodo_fixo < n and taxa_posterior != taxa_inicial
    if tem_segundo_patamar:
        capital_residual = calcular_capital_em_divida(
            m, taxa_inicial, n, periodo_fixo
        )
        meses_restantes = n - periodo_fixo
        prestacao_posterior = calcular_prestacao_mensal(
            capital_residual, taxa_posterior, meses_restantes
        )
        prestacoes = (
            [prestacao_inicial] * periodo_fixo
            + [prestacao_posterior] * meses_restantes
        )
    else:
        capital_residual = 0.0
        prestacao_posterior = prestacao_inicial
        prestacoes = [prestacao_inicial] * n

    fluxos = [p + seguros for p in prestacoes]
    total_prestacoes = sum(prestacoes)
    total_seguros = seguros * n
    total_pago = total_prestacoes + total_seguros + comissoes
    total_juros = total_prestacoes - m if m > 0 else 0.0
    taeg = calcular_taeg_fluxos(m - comissoes, fluxos)

    return {
        "key": definition.get("key"),
        "label": definition.get("label"),
        "descricao": definition.get("descricao"),
        "indexado": bool(definition.get("indexado")),
        "spread_pct": round(_safe_float(definition.get("spread_pct")), 3),
        "taxa_inicial_pct": round(taxa_inicial, 3),
        "taxa_posterior_pct": round(taxa_posterior, 3),
        "periodo_fixo_meses": periodo_fixo,
        "periodo_fixo_anos": round(periodo_fixo / MONTHS_PER_YEAR, 1),
        "tem_segundo_patamar": tem_segundo_patamar,
        "capital": round(m, 2),
        "num_meses": n,
        "prestacao_mensal": round(prestacao_inicial, 2),
        "prestacao_posterior": round(prestacao_posterior, 2),
        "capital_residual_pos_periodo_fixo": round(capital_residual, 2),
        "seguros_mensal": round(seguros, 2),
        "prestacao_total_mensal": round(prestacao_inicial + seguros, 2),
        "total_juros": round(total_juros, 2),
        "total_seguros": round(total_seguros, 2),
        "comissoes_iniciais": round(comissoes, 2),
        "total_pago": round(total_pago, 2),
        "taeg_pct": round(taeg, 2),
    }


# ====================================================================
# CRUZAMENTO COM O DSTI (motor canónico: services/dsti_service.py)
# ====================================================================


def project_dsti(
    dsti_base: dict,
    prestacao_mensal: Any,
    *,
    limite_pct: float,
) -> dict:
    """Projecta o DSTI do processo **com** a nova prestação simulada.

    Reutiliza o breakdown já calculado por ``dsti_service.calculate_dsti``
    (rendimento bruto agregado dos dois titulares, prestações de crédito
    do CRC, renda de habitação) e acrescenta a prestação do cenário.

    Args:
        dsti_base: Resultado de ``calculate_dsti(process)``.
        prestacao_mensal: Prestação do cenário (€).
        limite_pct: Limite DSTI (``dsti_analysis.critical_risk_threshold``).

    Returns:
        Dict com ``dsti_pct``/``effort_rate_pct`` projectados, nível de
        risco, folga mensal e se respeita o limite. ``is_calculable`` a
        ``False`` quando não há rendimento conhecido.
    """
    from services.dsti_service import _classify_risk, get_risk_label

    components = (dsti_base or {}).get("components") or {}
    rendimento_bruto = _safe_float(components.get("rendimento_bruto_total"))
    prestacao = _safe_float(prestacao_mensal)

    if not (dsti_base or {}).get("is_calculable") or rendimento_bruto <= 0:
        return {
            "is_calculable": False,
            "dsti_pct": 0.0,
            "effort_rate_pct": 0.0,
            "risk_level": "sem_dados",
            "risk_label": get_risk_label("sem_dados"),
            "risk_color": "#94a3b8",
            "limite_pct": round(_safe_float(limite_pct), 2),
            "dentro_limite": False,
            "folga_mensal": 0.0,
        }

    prestacoes_atuais = _safe_float(components.get("prestacao_creditos_mensal"))
    despesas_atuais = (
        prestacoes_atuais
        + _safe_float(components.get("renda_habitacao"))
        + _safe_float(components.get("despesas_co_titular"))
    )

    dsti_pct = ((prestacoes_atuais + prestacao) / rendimento_bruto) * 100
    effort_pct = ((despesas_atuais + prestacao) / rendimento_bruto) * 100
    risk_level, risk_color = _classify_risk(dsti_pct)
    folga = _safe_float(dsti_base.get("available_income")) - prestacao

    return {
        "is_calculable": True,
        "dsti_pct": round(dsti_pct, 2),
        "effort_rate_pct": round(effort_pct, 2),
        "risk_level": risk_level,
        "risk_label": get_risk_label(risk_level),
        "risk_color": risk_color,
        "limite_pct": round(_safe_float(limite_pct), 2),
        "dentro_limite": dsti_pct <= _safe_float(limite_pct),
        "folga_mensal": round(folga, 2),
    }


# ====================================================================
# RESOLUÇÃO DOS INPUTS DO PROCESSO (capital / prazo)
# ====================================================================


def _first_positive(*values) -> float:
    """Primeiro valor estritamente positivo da lista (senão ``0.0``)."""
    for value in values:
        number = _safe_float(value)
        if number > 0:
            return number
    return 0.0


def resolve_simulation_inputs(process: dict, *, credit_config: Any) -> dict:
    """Determina capital e prazo a simular a partir do processo.

    Prioridades (espelham ``frontend/src/utils/calculatorPrefill.js``, para
    que CRM e motor automático cheguem sempre aos mesmos números):

    - **Capital**: ``credit_data.requested_amount`` →
      ``credit_data.valor_emprestimo`` → ``financial_data.valor_financiamento``
      → ``financial_data.valor_pretendido`` → derivado do valor do imóvel.
    - **Prazo**: ``credit_data.loan_term_years`` → ``credit_data.prazo_anos``
      → ``financial_data.prazo_pretendido`` → ``financial_data.prazo_anos``
      → ``credit_services.default_term_years``.

    Derivação pelo imóvel: ``valor_imovel × max_loan_to_value``, limitado
    pelo valor do imóvel menos o capital próprio declarado (nunca financia
    a entrada já paga pelo cliente).

    Returns:
        ``{"capital", "prazo_anos", "num_meses", "capital_origem",
        "prazo_origem", "valor_imovel", "capital_proprio", "avisos"}``.
    """
    credit = process.get("credit_data") or {}
    financial = process.get("financial_data") or {}
    real_estate = process.get("real_estate_data") or {}
    avisos: list[str] = []

    capital = _first_positive(
        credit.get("requested_amount"),
        credit.get("valor_emprestimo"),
        financial.get("valor_financiamento"),
        financial.get("valor_pretendido"),
    )
    capital_origem = "processo"

    valor_imovel = _first_positive(
        real_estate.get("valor_imovel"),
        real_estate.get("valor"),
        process.get("property_value"),
    )
    capital_proprio = _first_positive(
        financial.get("valor_entrada"),
        financial.get("capital_proprio"),
    )

    if capital <= 0 and valor_imovel > 0:
        ltv = _safe_float(getattr(credit_config, "max_loan_to_value", 0))
        if ltv > 0:
            capital = valor_imovel * ltv / 100
            if capital_proprio > 0:
                capital = min(capital, max(valor_imovel - capital_proprio, 0.0))
            capital_origem = "ltv_valor_imovel"
            avisos.append(
                f"Montante estimado a {ltv:.0f}% do valor do imóvel "
                "(o processo não indica montante de financiamento)."
            )

    prazo_anos = _first_positive(
        credit.get("loan_term_years"),
        credit.get("prazo_anos"),
        financial.get("prazo_pretendido"),
        financial.get("prazo_anos"),
    )
    prazo_origem = "processo"
    if prazo_anos <= 0:
        prazo_anos = _safe_float(getattr(credit_config, "default_term_years", 0))
        prazo_origem = "configuracao"
        if prazo_anos > 0:
            avisos.append(
                f"Prazo estimado em {int(prazo_anos)} anos (valor por defeito "
                "da configuração — o processo não indica prazo)."
            )

    return {
        "capital": round(capital, 2),
        "prazo_anos": int(prazo_anos),
        "num_meses": int(prazo_anos) * MONTHS_PER_YEAR,
        "capital_origem": capital_origem,
        "prazo_origem": prazo_origem,
        "valor_imovel": round(valor_imovel, 2),
        "capital_proprio": round(capital_proprio, 2),
        "avisos": avisos,
    }


def build_income_summary(dsti_base: dict) -> dict:
    """Resumo dos rendimentos/encargos usados, para exibição na proposta."""
    components = (dsti_base or {}).get("components") or {}
    return {
        "rendimento_bruto_total": _safe_float(
            components.get("rendimento_bruto_total")
        ),
        "rendimento_liquido_total": _safe_float(
            components.get("rendimento_liquido_total")
        ),
        "prestacao_creditos_mensal": _safe_float(
            components.get("prestacao_creditos_mensal")
        ),
        "renda_habitacao": _safe_float(components.get("renda_habitacao")),
        "numero_creditos": int(_safe_float(components.get("numero_creditos"))),
        "dsti_atual_pct": _safe_float((dsti_base or {}).get("dsti_pct")),
        "taxa_esforco_atual_pct": _safe_float(
            (dsti_base or {}).get("effort_rate_pct")
        ),
        "disponibilidade_mensal": _safe_float(
            (dsti_base or {}).get("available_income")
        ),
    }


def build_simulation(
    *,
    process: dict,
    dsti_base: dict,
    euribor_rates: dict,
    sim_config: Any,
    credit_config: Any,
    dsti_config: Any,
) -> dict:
    """Núcleo síncrono do motor: dos dados brutos aos 3 cenários.

    Separado de ``run_financial_simulation`` para ser exercitável em testes
    unitários sem MongoDB nem rede (a Euribor e a configuração entram como
    argumentos).

    Returns:
        ``{"success": True, ...}`` com ``cenarios`` (3 entradas), ``dsti``,
        ``taxa_indexante`` e ``avisos``; ou ``{"success": False, "reason",
        "missing", "avisos"}`` quando faltam dados essenciais — o motor
        nunca inventa rendimentos nem montantes.
    """
    inputs = resolve_simulation_inputs(process, credit_config=credit_config)
    avisos = list(inputs["avisos"])
    missing: list[str] = []

    if not (dsti_base or {}).get("is_calculable"):
        missing.append("rendimento")
    if inputs["capital"] <= 0:
        missing.append("montante_financiamento")
    if inputs["num_meses"] <= 0:
        missing.append("prazo")

    if missing:
        reason = REASON_NO_INCOME if "rendimento" in missing else REASON_NO_CAPITAL
        logger.info(
            f"[SIMULADOR] Dados insuficientes para o processo "
            f"{process.get('id')}: {missing}"
        )
        return {
            "success": False,
            "reason": reason,
            "missing": missing,
            "avisos": avisos,
            "inputs": inputs,
        }

    indexante = resolve_euribor_index(
        euribor_rates, getattr(sim_config, "euribor_index", None)
    )
    if indexante["rate_pct"] <= 0:
        avisos.append(
            "Euribor indisponível no momento do cálculo — os cenários "
            "indexados usam apenas o spread contratado."
        )
    elif indexante["is_fallback"]:
        avisos.append(
            "Taxa Euribor obtida de valores estimados/cache — confirmar "
            "com o preçário do banco antes de apresentar ao cliente."
        )

    seguros = _safe_float(
        getattr(sim_config, "seguro_vida_mensal", 0)
    ) + _safe_float(getattr(sim_config, "seguro_multirriscos_mensal", 0))
    comissoes = _safe_float(getattr(sim_config, "comissoes_iniciais", 0))
    limite_dsti = _safe_float(
        getattr(dsti_config, "critical_risk_threshold", 0)
    )

    definitions = build_scenario_definitions(
        euribor_pct=indexante["rate_pct"],
        sim_config=sim_config,
        num_meses=inputs["num_meses"],
    )

    cenarios = []
    for definition in definitions:
        scenario = simulate_scenario(
            definition=definition,
            capital=inputs["capital"],
            num_meses=inputs["num_meses"],
            seguros_mensal=seguros,
            comissoes_iniciais=comissoes,
        )
        scenario["dsti"] = project_dsti(
            dsti_base,
            scenario["prestacao_total_mensal"],
            limite_pct=limite_dsti,
        )
        cenarios.append(scenario)

    if cenarios and not any(c["dsti"]["dentro_limite"] for c in cenarios):
        avisos.append(
            f"Nenhum cenário fica abaixo do limite de taxa de esforço de "
            f"{limite_dsti:.0f}% — rever montante, prazo ou incluir "
            "segundo titular."
        )

    now = datetime.now(timezone.utc)
    validade_dias = int(
        _safe_float(getattr(credit_config, "simulation_validity_days", 0))
    )

    return {
        "success": True,
        "reason": None,
        "missing": [],
        "process_id": process.get("id"),
        "process_number": process.get("process_number"),
        "client_name": process.get("client_name"),
        "inputs": inputs,
        "rendimentos": build_income_summary(dsti_base),
        "dsti_atual": {
            "dsti_pct": _safe_float(dsti_base.get("dsti_pct")),
            "effort_rate_pct": _safe_float(dsti_base.get("effort_rate_pct")),
            "risk_level": dsti_base.get("risk_level"),
            "risk_color": dsti_base.get("risk_color"),
            "max_installment": _safe_float(dsti_base.get("max_installment")),
        },
        "taxa_indexante": indexante,
        "limite_dsti_pct": round(limite_dsti, 2),
        "seguros_mensal": round(seguros, 2),
        "comissoes_iniciais": round(comissoes, 2),
        "cenarios": cenarios,
        "avisos": avisos,
        "calculated_at": now.isoformat(),
        "valido_ate": (
            (now + timedelta(days=validade_dias)).isoformat()
            if validade_dias > 0
            else None
        ),
    }


# ====================================================================
# ENTRADA ASSÍNCRONA (única fronteira de I/O deste módulo)
# ====================================================================


async def run_financial_simulation(
    process: dict,
    *,
    company_id: Optional[str] = None,
) -> dict:
    """Corre a simulação completa para um processo.

    Carrega a configuração do sistema (empresa do processo) e as taxas
    Euribor em vigor, delegando todo o cálculo em ``build_simulation``.

    A Euribor degrada graciosamente: se o serviço externo falhar,
    ``get_euribor_rates`` devolve cache/fallback e o resultado fica
    marcado com o aviso correspondente — a simulação nunca é abortada por
    causa da taxa.
    """
    from services.euribor_service import get_euribor_rates
    from services.system_config import get_system_config

    resolved_company = (
        company_id
        or process.get("company_id")
        or process.get("company")
        or "default"
    )
    config = await get_system_config(resolved_company)

    try:
        euribor_rates = await get_euribor_rates()
    except Exception as euribor_err:  # pragma: no cover — degradação graciosa
        logger.warning(
            f"[SIMULADOR] Euribor indisponível ({euribor_err}); a continuar "
            "apenas com o spread contratado."
        )
        euribor_rates = {}

    from services.dsti_service import calculate_dsti

    dsti_base = calculate_dsti(process)

    return build_simulation(
        process=process,
        dsti_base=dsti_base,
        euribor_rates=euribor_rates,
        sim_config=config.financial_simulator,
        credit_config=config.credit_services,
        dsti_config=config.dsti_analysis,
    )

"""Dashboard financeiro: config, summary, monthly, performance.

Extraído de `routes/finance.py`.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException

from database import db
from services.finance_helpers import (
    DEFAULT_CONFIG,
    FINANCE_CONFIG_KEY,
    DashboardFinanceConfigUpdate,
    _calc_area_metrics,
    _get_finance_config,
    _get_processes,
    _is_credito,
    _month_label,
    _safe_float,
)

logger = logging.getLogger(__name__)


async def run_get_finance_config(
    user: dict,
):
    """
    Obtém as configurações financeiras atuais.

    Retorna as percentagens configuradas para cada área de negócio:
    - comissao_consultor_pct: % da comissão que vai para o consultor
    - retida_agencia_pct: % da comissão retida pela agência
    - taxa_impostos_sobre_lucro: % de impostos sobre o lucro
    """
    config = await _get_finance_config()
    return {
        "config": config,
        "defaults": DEFAULT_CONFIG,
    }



async def run_update_finance_config(
    body: DashboardFinanceConfigUpdate,
    user: dict,
):
    """
    Atualiza as configurações financeiras.

    Permite ao Admin/CEO alterar as percentagens de comissão
    para as áreas de Imobiliária e Crédito.
    """
    current = await _get_finance_config()

    # Validar e aplicar actualizações
    for area in ["imobiliaria", "credito"]:
        update_data = getattr(body, area)
        if update_data is None:
            continue

        if area not in current:
            current[area] = DEFAULT_CONFIG[area].copy()

        for field, value in update_data.items():
            if field not in DEFAULT_CONFIG[area]:
                raise HTTPException(
                    status_code=400,
                    detail=f"Campo '{field}' inválido para a área '{area}'. "
                           f"Campos permitidos: {list(DEFAULT_CONFIG[area].keys())}"
                )
            if not isinstance(value, (int, float)):
                raise HTTPException(
                    status_code=400,
                    detail=f"O campo '{field}' deve ser um número."
                )
            if value < 0 or value > 100:
                raise HTTPException(
                    status_code=400,
                    detail=f"O campo '{field}' deve estar entre 0 e 100."
                )
            current[area][field] = float(value)

    # Guardar distribution_model se fornecido
    if body.distribution_model is not None:
        if body.distribution_model not in ("individual_split", "global_pool"):
            raise HTTPException(
                status_code=400,
                detail="distribution_model deve ser 'individual_split' ou 'global_pool'."
            )
        current["distribution_model"] = body.distribution_model

    # Guardar na DB
    from datetime import timezone as tz
    await db.system_config.update_one(
        {"_id": FINANCE_CONFIG_KEY},
        {
            "$set": {
                "value": current,
                "updated_by": user.get("email", ""),
                "updated_at": datetime.now(tz.utc).isoformat(),
            }
        },
        upsert=True,
    )

    logger.info(f"Configurações financeiras atualizadas por {user.get('email', 'unknown')}")

    return {
        "success": True,
        "config": current,
        "message": "Configurações financeiras atualizadas com sucesso.",
    }



async def run_get_finance_summary(
    year: Optional[int],
    user: dict,
):
    """
    Resumo financeiro geral, separado por áreas de negócio.

    Retorna dois blocos principais:
    - imobiliaria: métricas dos processos imobiliários
    - credito: métricas dos processos de crédito
    - global: totais consolidados
    """
    config = await _get_finance_config()
    processes = await _get_processes(year)

    # Calcular por área
    imob_data = _calc_area_metrics(processes, "imobiliaria", config)
    cred_data = _calc_area_metrics(processes, "credito", config)

    # Consolidar globais
    total_receita = imob_data["total_receita"] + cred_data["total_receita"]
    total_comissoes = imob_data["comissoes_pagas_consultores"] + cred_data["comissoes_pagas_consultores"]
    total_lucro = imob_data["lucro_liquido_agencia"] + cred_data["lucro_liquido_agencia"]
    total_impostos = imob_data["total_impostos"] + cred_data["total_impostos"]
    total_processos = imob_data["total_processos"] + cred_data["total_processos"]

    return {
        "year": year,
        "config": config,
        "global": {
            "total_receita": round(total_receita, 2),
            "total_comissoes_pagas": round(total_comissoes, 2),
            "total_impostos": round(total_impostos, 2),
            "total_lucro_liquido": round(total_lucro, 2),
            "taxa_margem": round((total_lucro / total_receita * 100), 1) if total_receita > 0 else 0,
            "total_processos": total_processos,
        },
        "imobiliaria": imob_data,
        "credito": cred_data,
    }



async def run_get_finance_monthly(
    year: Optional[int],
    user: dict,
):
    """
    Dados financeiros agrupados por mês, separados por área.
    """
    config = await _get_finance_config()

    if year is None:
        year = datetime.now(timezone.utc).year

    start_of_year = f"{year}-01-01T00:00:00.000Z"
    end_of_year = f"{year}-12-31T23:59:59.999Z"

    processes = await db.processes.find(
        {
            "status": {"$in": ["concluidos"]},
            "updated_at": {"$gte": start_of_year, "$lte": end_of_year}
        },
        {
            "_id": 0,
            "financial_data": 1,
            "real_estate_data": 1,
            "credit_data": 1,
            "process_type": 1,
            "updated_at": 1,
        }
    ).to_list(2000)

    # Inicializar dados mensais
    monthly_data = {}
    for month_num in range(1, 13):
        month_key = f"{year}-{month_num:02d}"
        monthly_data[month_key] = {
            "month": month_key,
            "month_label": _month_label(month_num),
            # Imobiliária
            "imob_receita": 0.0,
            "imob_valor_imoveis": 0.0,
            "imob_num_processos": 0,
            # Crédito
            "cred_receita": 0.0,
            "cred_montante": 0.0,
            "cred_num_processos": 0,
            # Globais
            "receita": 0.0,
            "num_processos": 0,
        }

    pct_consultor_imob = _safe_float(config.get("imobiliaria", {}).get("comissao_consultor_pct", 50))
    pct_agencia_imob = _safe_float(config.get("imobiliaria", {}).get("retida_agencia_pct", 50))
    pct_impostos_imob = _safe_float(config.get("imobiliaria", {}).get("taxa_impostos_sobre_lucro", 21))
    pct_consultor_cred = _safe_float(config.get("credito", {}).get("comissao_consultor_pct", 40))
    pct_agencia_cred = _safe_float(config.get("credito", {}).get("retida_agencia_pct", 60))
    pct_impostos_cred = _safe_float(config.get("credito", {}).get("taxa_impostos_sobre_lucro", 21))

    for p in processes:
        financial = p.get("financial_data") or {}
        real_estate = p.get("real_estate_data") or {}
        credit = p.get("credit_data") or {}
        pt = p.get("process_type", "")
        updated_at = p.get("updated_at", "")

        comissao = _safe_float(financial.get("comissao_mediacao"))
        valor_imovel = _safe_float(real_estate.get("valor_imovel"))
        montante = _safe_float(credit.get("requested_amount"))

        try:
            dt = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
            month_key = f"{dt.year}-{dt.month:02d}"
        except (ValueError, AttributeError):
            month_key = f"{year}-01"

        if month_key not in monthly_data:
            continue

        is_cred = _is_credito(pt)

        if is_cred:
            monthly_data[month_key]["cred_receita"] += comissao
            monthly_data[month_key]["cred_montante"] += montante
            monthly_data[month_key]["cred_num_processos"] += 1
        else:
            monthly_data[month_key]["imob_receita"] += comissao
            monthly_data[month_key]["imob_valor_imoveis"] += valor_imovel
            monthly_data[month_key]["imob_num_processos"] += 1

        monthly_data[month_key]["receita"] += comissao
        monthly_data[month_key]["num_processos"] += 1

    # Calcular despesas e lucro para cada mês
    for key in monthly_data:
        m = monthly_data[key]

        # Imobiliária
        imob_lucro_bruto = m["imob_receita"] * (pct_agencia_imob / 100)
        imob_comissoes = m["imob_receita"] * (pct_consultor_imob / 100)
        imob_impostos = imob_lucro_bruto * (pct_impostos_imob / 100)
        m["imob_comissoes"] = round(imob_comissoes, 2)
        m["imob_lucro_bruto"] = round(imob_lucro_bruto, 2)
        m["imob_impostos"] = round(imob_impostos, 2)
        m["imob_lucro_liquido"] = round(imob_lucro_bruto - imob_impostos, 2)
        m["imob_receita"] = round(m["imob_receita"], 2)
        m["imob_valor_imoveis"] = round(m["imob_valor_imoveis"], 2)

        # Crédito
        cred_lucro_bruto = m["cred_receita"] * (pct_agencia_cred / 100)
        cred_comissoes = m["cred_receita"] * (pct_consultor_cred / 100)
        cred_impostos = cred_lucro_bruto * (pct_impostos_cred / 100)
        m["cred_comissoes"] = round(cred_comissoes, 2)
        m["cred_lucro_bruto"] = round(cred_lucro_bruto, 2)
        m["cred_impostos"] = round(cred_impostos, 2)
        m["cred_lucro_liquido"] = round(cred_lucro_bruto - cred_impostos, 2)
        m["cred_receita"] = round(m["cred_receita"], 2)
        m["cred_montante"] = round(m["cred_montante"], 2)

        # Global
        m["receita"] = round(m["receita"], 2)

    monthly_list = list(monthly_data.values())

    return {
        "year": year,
        "monthly": monthly_list,
        "totals": {
            "total_receita": round(sum(m["receita"] for m in monthly_list), 2),
            "total_imob_receita": round(sum(m["imob_receita"] for m in monthly_list), 2),
            "total_cred_receita": round(sum(m["cred_receita"] for m in monthly_list), 2),
            "total_imob_lucro": round(sum(m["imob_lucro_liquido"] for m in monthly_list), 2),
            "total_cred_lucro": round(sum(m["cred_lucro_liquido"] for m in monthly_list), 2),
            "total_processos": sum(m["num_processos"] for m in monthly_list),
        },
    }



async def run_get_finance_performance(
    year: Optional[int],
    user: dict,
):
    """
    Indicadores de performance financeira, comparando ano atual com anterior.
    """
    current_year = year or datetime.now(timezone.utc).year
    previous_year = current_year - 1

    config = await _get_finance_config()

    async def _calc_year_metrics(yr: int) -> dict:
        """Calcula métricas financeiras agregadas para um ano.

        Busca processos do ano, calcula métricas de imobiliária e crédito
        separadamente, e agrega receita, lucro e valor de imóveis.

        Args:
            yr: Ano para calcular métricas.

        Returns:
            dict: Métricas do ano (receita, lucro, valor_imoveis,
                num_processos, receitas/lucros por área).
        """
        processes = await _get_processes(yr)
        imob = _calc_area_metrics(processes, "imobiliaria", config)
        cred = _calc_area_metrics(processes, "credito", config)
        return {
            "year": yr,
            "receita": imob["total_receita"] + cred["total_receita"],
            "lucro": imob["lucro_liquido_agencia"] + cred["lucro_liquido_agencia"],
            "valor_imoveis": imob["total_valor_imoveis"],
            "num_processos": imob["total_processos"] + cred["total_processos"],
            "imob_receita": imob["total_receita"],
            "cred_receita": cred["total_receita"],
            "imob_lucro": imob["lucro_liquido_agencia"],
            "cred_lucro": cred["lucro_liquido_agencia"],
        }

    current = await _calc_year_metrics(current_year)
    previous = await _calc_year_metrics(previous_year)

    def _calc_variation(current_val, previous_val) -> Optional[float]:
        """Calcula a variação percentual entre dois valores.

        Se o valor anterior for 0, retorna 100.0 (crescimento de 100%)
        ou None (ambos zero). Evita divisão por zero.

        Args:
            current_val: Valor atual.
            previous_val: Valor do período anterior.

        Returns:
            Optional[float]: Variação percentual (ex: 15.5), ou None
                se ambos os valores forem zero.
        """
        if previous_val == 0:
            return None if current_val == 0 else 100.0
        return round(((current_val - previous_val) / previous_val) * 100, 1)

    return {
        "current_year": current,
        "previous_year": previous,
        "variations": {
            "receita": _calc_variation(current["receita"], previous["receita"]),
            "lucro": _calc_variation(current["lucro"], previous["lucro"]),
            "valor_imoveis": _calc_variation(current["valor_imoveis"], previous["valor_imoveis"]),
            "num_processos": _calc_variation(current["num_processos"], previous["num_processos"]),
            "imob_receita": _calc_variation(current["imob_receita"], previous["imob_receita"]),
            "cred_receita": _calc_variation(current["cred_receita"], previous["cred_receita"]),
            "imob_lucro": _calc_variation(current["imob_lucro"], previous["imob_lucro"]),
            "cred_lucro": _calc_variation(current["cred_lucro"], previous["cred_lucro"]),
        },
    }


"""
Rotas de Finanças - PowerCell

Dashboard Financeiro exclusivo para Admin e CEO.
Calcula receitas, despesas e lucro líquido com base nos dados dos processos.
"""

from datetime import datetime, timezone, timedelta
from typing import Optional, List
from fastapi import APIRouter, Depends, Query, HTTPException

from database import db
from models.auth import UserRole
from services.auth import get_current_user, require_roles


router = APIRouter(tags=["Finance"])


def _safe_float(val) -> float:
    """Converte valor para float de forma segura."""
    if val is None:
        return 0.0
    try:
        return float(val)
    except (ValueError, TypeError):
        return 0.0


@router.get("/finance/summary")
async def get_finance_summary(
    year: Optional[int] = Query(None, description="Ano para filtrar (ex: 2025)"),
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
):
    """
    Resumo financeiro geral.

    Retorna:
    - total_receita: Soma de comissao_mediacao dos processos concluídos
    - total_despesas: Estimativa de despesas (comissões pagas a colaboradores)
    - lucro_liquido: receita - despesas
    - total_processos_concluidos: Nº de processos concluídos
    - valor_medio_comissao: Média de comissão por processo concluído
    - total_valor_imoveis: Soma do valor dos imóveis dos processos concluídos
    """
    # Status que representam processos concluídos/ganhos
    won_statuses = ["concluidos"]

    query = {"status": {"$in": won_statuses}}

    # Filtro por ano, se fornecido
    if year:
        start_of_year = f"{year}-01-01T00:00:00.000Z"
        end_of_year = f"{year}-12-31T23:59:59.999Z"
        query["updated_at"] = {"$gte": start_of_year, "$lte": end_of_year}

    # Buscar processos concluídos
    processes = await db.processes.find(
        query,
        {
            "_id": 0,
            "id": 1,
            "process_number": 1,
            "client_name": 1,
            "status": 1,
            "financial_data": 1,
            "real_estate_data": 1,
            "credit_data": 1,
            "updated_at": 1,
            "created_at": 1,
            "assigned_consultor_names": 1,
            "consultor_name": 1,
            "mediador_name": 1,
            "mediador_names": 1,
            "process_type": 1,
        }
    ).to_list(10000)

    # Calcular métricas
    total_receita = 0.0
    total_valor_imoveis = 0.0
    processos_com_comissao = 0

    process_details = []
    for p in processes:
        financial = p.get("financial_data") or {}
        real_estate = p.get("real_estate_data") or {}

        comissao = _safe_float(financial.get("comissao_mediacao"))
        valor_imovel = _safe_float(real_estate.get("valor_imovel"))

        total_receita += comissao
        total_valor_imoveis += valor_imovel

        if comissao > 0:
            processos_com_comissao += 1

        process_details.append({
            "id": p.get("id", ""),
            "process_number": p.get("process_number"),
            "client_name": p.get("client_name", ""),
            "process_type": p.get("process_type", ""),
            "comissao": comissao,
            "valor_imovel": valor_imovel,
            "consultor": (p.get("consultor_names") or [p.get("consultor_name")]),
            "mediador": (p.get("mediador_names") or [p.get("mediador_name")]),
            "updated_at": p.get("updated_at", ""),
        })

    # Despesas: estimativa baseada em percentagem de comissão
    # Por defeito, 50% da receita vai para comissões de colaboradores
    # (pode ser ajustado quando houver dados reais de salários)
    total_despesas = total_receita * 0.50
    lucro_liquido = total_receita - total_despesas

    total_processos = len(processes)
    valor_medio_comissao = total_receita / processos_com_comissao if processos_com_comissao > 0 else 0

    return {
        "total_receita": round(total_receita, 2),
        "total_despesas": round(total_despesas, 2),
        "lucro_liquido": round(lucro_liquido, 2),
        "taxa_margem": round((lucro_liquido / total_receita * 100), 1) if total_receita > 0 else 0,
        "total_processos_concluidos": total_processos,
        "processos_com_comissao": processos_com_comissao,
        "valor_medio_comissao": round(valor_medio_comissao, 2),
        "total_valor_imoveis": round(total_valor_imoveis, 2),
        "processos": sorted(process_details, key=lambda x: x["comissao"], reverse=True),
        "year": year,
    }


@router.get("/finance/monthly")
async def get_finance_monthly(
    year: Optional[int] = Query(None, description="Ano para filtrar"),
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
):
    """
    Dados financeiros agrupados por mês.

    Retorna array com dados de receita, despesas e lucro por mês.
    """
    won_statuses = ["concluidos"]

    if year is None:
        year = datetime.now(timezone.utc).year

    start_of_year = datetime(year, 1, 1, tzinfo=timezone.utc)
    end_of_year = datetime(year, 12, 31, 23, 59, 59, tzinfo=timezone.utc)

    processes = await db.processes.find(
        {
            "status": {"$in": won_statuses},
            "updated_at": {"$gte": start_of_year.isoformat(), "$lte": end_of_year.isoformat()}
        },
        {
            "_id": 0,
            "financial_data": 1,
            "real_estate_data": 1,
            "updated_at": 1,
        }
    ).to_list(10000)

    # Agrupar por mês
    monthly_data = {}
    for month_num in range(1, 13):
        month_key = f"{year}-{month_num:02d}"
        monthly_data[month_key] = {
            "month": month_key,
            "month_label": _month_label(month_num),
            "receita": 0.0,
            "despesas": 0.0,
            "lucro": 0.0,
            "num_processos": 0,
            "valor_imoveis": 0.0,
        }

    for p in processes:
        financial = p.get("financial_data") or {}
        real_estate = p.get("real_estate_data") or {}
        updated_at = p.get("updated_at", "")

        comissao = _safe_float(financial.get("comissao_mediacao"))
        valor_imovel = _safe_float(real_estate.get("valor_imovel"))

        # Determinar o mês a partir da data de atualização
        try:
            dt = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
            month_key = f"{dt.year}-{dt.month:02d}"
        except (ValueError, AttributeError):
            month_key = f"{year}-01"

        if month_key in monthly_data:
            monthly_data[month_key]["receita"] += comissao
            monthly_data[month_key]["valor_imoveis"] += valor_imovel
            monthly_data[month_key]["num_processos"] += 1

    # Calcular despesas e lucro para cada mês
    for key in monthly_data:
        receita = monthly_data[key]["receita"]
        despesas = receita * 0.50
        monthly_data[key]["despesas"] = round(despesas, 2)
        monthly_data[key]["lucro"] = round(receita - despesas, 2)
        monthly_data[key]["receita"] = round(receita, 2)
        monthly_data[key]["valor_imoveis"] = round(monthly_data[key]["valor_imoveis"], 2)

    return {
        "year": year,
        "monthly": list(monthly_data.values()),
        "total_receita": round(sum(m["receita"] for m in monthly_data.values()), 2),
        "total_despesas": round(sum(m["despesas"] for m in monthly_data.values()), 2),
        "total_lucro": round(sum(m["lucro"] for m in monthly_data.values()), 2),
        "total_processos": sum(m["num_processos"] for m in monthly_data.values()),
        "total_valor_imoveis": round(sum(m["valor_imoveis"] for m in monthly_data.values()), 2),
    }


@router.get("/finance/commissions")
async def get_finance_commissions(
    year: Optional[int] = Query(None, description="Ano para filtrar"),
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
):
    """
    Comissões por colaborador.

    Retorna ranking de consultores e intermediários por valor de comissão
    associado aos processos concluídos.
    """
    won_statuses = ["concluidos"]

    query = {"status": {"$in": won_statuses}}

    if year:
        start_of_year = f"{year}-01-01T00:00:00.000Z"
        end_of_year = f"{year}-12-31T23:59:59.999Z"
        query["updated_at"] = {"$gte": start_of_year, "$lte": end_of_year}

    processes = await db.processes.find(
        query,
        {
            "_id": 0,
            "financial_data": 1,
            "consultor_names": 1,
            "consultor_name": 1,
            "mediador_names": 1,
            "mediador_name": 1,
            "process_type": 1,
        }
    ).to_list(10000)

    # Agrupar comissões por colaborador
    collaborator_data = {}

    for p in processes:
        financial = p.get("financial_data") or {}
        comissao = _safe_float(financial.get("comissao_mediacao"))

        if comissao <= 0:
            continue

        # Dividir comissão pelos colaboradores atribuídos (partilha igual)
        consultores = p.get("consultor_names") or ([p.get("consultor_name")] if p.get("consultor_name") else [])
        mediadores = p.get("mediador_names") or ([p.get("mediador_name")] if p.get("mediador_name") else [])
        process_type = p.get("process_type", "habitação")

        # Consultor recebe 50% da comissão (estimativa)
        # Intermediário recebe 50% da comissão (estimativa)
        consultor_share = comissao * 0.50 / max(len(consultores), 1)
        mediador_share = comissao * 0.50 / max(len(mediadores), 1)

        for name in consultores:
            if not name:
                continue
            key = f"consultor:{name}"
            if key not in collaborator_data:
                collaborator_data[key] = {
                    "name": name,
                    "role": "consultor",
                    "total_comissao": 0.0,
                    "num_processos": 0,
                    "tipos_processo": set(),
                }
            collaborator_data[key]["total_comissao"] += consultor_share
            collaborator_data[key]["num_processos"] += 1
            collaborator_data[key]["tipos_processo"].add(process_type)

        for name in mediadores:
            if not name:
                continue
            key = f"mediador:{name}"
            if key not in collaborator_data:
                collaborator_data[key] = {
                    "name": name,
                    "role": "mediador",
                    "total_comissao": 0.0,
                    "num_processos": 0,
                    "tipos_processo": set(),
                }
            collaborator_data[key]["total_comissao"] += mediador_share
            collaborator_data[key]["num_processos"] += 1
            collaborator_data[key]["tipos_processo"].add(process_type)

    # Converter sets para lists e ordenar por comissão
    result = []
    for key in collaborator_data:
        data = collaborator_data[key]
        result.append({
            "name": data["name"],
            "role": data["role"],
            "total_comissao": round(data["total_comissao"], 2),
            "num_processos": data["num_processos"],
            "tipos_processo": list(data["tipos_processo"]),
        })

    result.sort(key=lambda x: x["total_comissao"], reverse=True)

    return {
        "year": year,
        "collaborators": result,
        "total_comissoes_pagas": round(sum(c["total_comissao"] for c in result), 2),
    }


@router.get("/finance/performance")
async def get_finance_performance(
    year: Optional[int] = Query(None, description="Ano para filtrar"),
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
):
    """
    Indicadores de performance financeira.

    Compara períodos e calcula tendências.
    """
    current_year = year or datetime.now(timezone.utc).year
    previous_year = current_year - 1

    won_statuses = ["concluidos"]

    def _calc_year_metrics(yr: int) -> dict:
        start = f"{yr}-01-01T00:00:00.000Z"
        end = f"{yr}-12-31T23:59:59.999Z"

        processes = await db.processes.find(
            {
                "status": {"$in": won_statuses},
                "updated_at": {"$gte": start, "$lte": end}
            },
            {"_id": 0, "financial_data": 1, "real_estate_data": 1}
        ).to_list(10000)

        receita = 0.0
        valor_imoveis = 0.0
        count = 0
        comissoes_count = 0

        for p in processes:
            financial = p.get("financial_data") or {}
            real_estate = p.get("real_estate_data") or {}
            comissao = _safe_float(financial.get("comissao_mediacao"))
            valor_imovel = _safe_float(real_estate.get("valor_imovel"))

            receita += comissao
            valor_imoveis += valor_imovel
            count += 1
            if comissao > 0:
                comissoes_count += 1

        return {
            "year": yr,
            "receita": round(receita, 2),
            "despesas": round(receita * 0.50, 2),
            "lucro": round(receita * 0.50, 2),
            "valor_imoveis": round(valor_imoveis, 2),
            "num_processos": count,
            "processos_com_comissao": comissoes_count,
        }

    current = await _calc_year_metrics(current_year)
    previous = await _calc_year_metrics(previous_year)

    # Calcular variações
    def _calc_variation(current_val, previous_val) -> Optional[float]:
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
        },
    }


def _month_label(month_num: int) -> str:
    """Retorna o nome do mês em português."""
    meses = [
        "Jan", "Fev", "Mar", "Abr", "Mai", "Jun",
        "Jul", "Ago", "Set", "Out", "Nov", "Dez"
    ]
    return meses[month_num - 1] if 1 <= month_num <= 12 else ""

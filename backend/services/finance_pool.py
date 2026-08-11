"""Pool distribution + export CSV.

Extraído de `routes/finance.py`.
"""
from __future__ import annotations

import csv
import io
import logging
from datetime import datetime, timezone

from fastapi.responses import StreamingResponse

from database import db
from models.finance import DistributionModel, FinanceStatus
from services.finance_helpers import _safe_float

logger = logging.getLogger(__name__)


async def run_get_pool_distribution(
    month: int,
    year: int,
    company_id: str,
    user: dict,
):
    """
    Calcula a distribuição do Pool Global para um mês/ano.

    Lógica:
    1. Soma as expected_commission de todos os processos com status
       'paid' ou 'invoiced' no mês/ano indicado, filtrando por company_id.
       Este é o total_pool.
    2. Conta quantos utilizadores ativos existem com a role
       'consultor' ou 'intermediario' nessa empresa.
       Este é o total_consultants.
    3. Retorna: pool_per_consultant = total_pool / total_consultants
       (com proteção de divisão por zero).

    Permissões: todos os roles de leitura financeira.
    """
    # --- Verificar se a empresa usa modelo global_pool ---
    config_doc = await db.finance_configs.find_one({"company_id": company_id})
    dist_model = config_doc.get("distribution_model", DistributionModel.INDIVIDUAL_SPLIT.value) if config_doc else DistributionModel.INDIVIDUAL_SPLIT.value

    # --- 1. Calcular total_pool ---
    start_of_month = f"{year}-{month:02d}-01T00:00:00.000Z"
    if month == 12:
        end_of_month = f"{year + 1}-01-01T00:00:00.000Z"
    else:
        end_of_month = f"{year}-{month + 1:02d}-01T00:00:00.000Z"

    pool_statuses = [FinanceStatus.PAID.value, FinanceStatus.INVOICED.value]

    pipeline = [
        {
            "$match": {
                "company_id": company_id,
                "status": {"$in": pool_statuses},
                "updated_at": {"$gte": start_of_month, "$lt": end_of_month},
            }
        },
        {
            "$group": {
                "_id": None,
                "total_pool": {"$sum": "$expected_commission"},
                "total_real_estate_commission": {"$sum": {"$ifNull": ["$real_estate_commission", 0]}},
                "total_credit_commission": {"$sum": {"$ifNull": ["$credit_commission", 0]}},
                "count": {"$sum": 1},
            }
        },
    ]

    pool_results = await db.process_finances.aggregate(pipeline).to_list(1)

    total_pool = _safe_float(pool_results[0].get("total_pool")) if pool_results else 0.0
    total_re_commission = _safe_float(pool_results[0].get("total_real_estate_commission")) if pool_results else 0.0
    total_cr_commission = _safe_float(pool_results[0].get("total_credit_commission")) if pool_results else 0.0
    count_processes = pool_results[0].get("count", 0) if pool_results else 0

    # --- 2. Contar consultores ativos ---
    consultant_roles = ["consultor", "intermediario"]

    primary_query = {
        "company": company_id,
        "role": {"$in": consultant_roles},
        "is_active": {"$ne": False},
    }

    additional_query = {
        "company": company_id,
        "additional_roles": {"$in": consultant_roles},
        "is_active": {"$ne": False},
    }

    primary_consultants = await db.users.find(primary_query, {"_id": 0, "id": 1, "name": 1, "role": 1, "base_salary": 1}).to_list(1000)
    additional_consultants = await db.users.find(additional_query, {"_id": 0, "id": 1, "name": 1, "role": 1, "base_salary": 1}).to_list(1000)

    # Combinar e desduplicar por id
    seen_ids = set()
    all_consultants = []
    for u in primary_consultants + additional_consultants:
        uid = u.get("id", "")
        if uid and uid not in seen_ids:
            seen_ids.add(uid)
            all_consultants.append({
                "id": uid,
                "name": u.get("name", ""),
                "role": u.get("role", ""),
                "base_salary": _safe_float(u.get("base_salary")),
            })

    total_consultants = len(all_consultants)

    # --- 3. Calcular pool_per_consultant ---
    pool_per_consultant = round(total_pool / total_consultants, 2) if total_consultants > 0 else 0.0

    # --- 4. Calcular breakdown por consultor: Fixo + Variável + Total ---
    total_base_salaries = 0.0
    total_variable = 0.0
    total_grand = 0.0
    for c in all_consultants:
        c["fixed_salary"] = round(c["base_salary"], 2)       # a) Vencimento Fixo
        c["variable_pay"] = round(pool_per_consultant, 2)     # b) Variável (Pool/Comissão)
        c["total_monthly"] = round(c["base_salary"] + pool_per_consultant, 2)  # c) Total a Pagar
        total_base_salaries += c["fixed_salary"]
        total_variable += c["variable_pay"]
        total_grand += c["total_monthly"]

    month_names = [
        "", "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
        "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"
    ]

    return {
        "month": month,
        "year": year,
        "month_label": month_names[month] if 1 <= month <= 12 else "",
        "company_id": company_id,
        "distribution_model": dist_model,
        "total_pool": round(total_pool, 2),
        "total_real_estate_commission": round(total_re_commission, 2),
        "total_credit_commission": round(total_cr_commission, 2),
        "total_consultants": total_consultants,
        "pool_per_consultant": pool_per_consultant,
        "count_processes": count_processes,
        "total_base_salaries": round(total_base_salaries, 2),
        "total_variable_pay": round(total_variable, 2),
        "total_grand_monthly": round(total_grand, 2),
        "consultants": all_consultants,
    }



async def run_export_pool_distribution_csv(
    month: int,
    year: int,
    company_id: str,
    user: dict,
):
    """
    Exporta a distribuição do Pool Global como ficheiro CSV para a Contabilidade.

    Executa a mesma lógica do endpoint GET /finance/pool-distribution (com
    Fixo + Variável + Total), mas devolve um ficheiro .csv formatado com:
      - Colunas: Nome do Consultor, Cargo, Salário Fixo (€), Comissões/Pool (€), Total a Receber (€)
      - Separador: vírgula
      - Codificação: UTF-8 com BOM (para Excel abrir correctamente acentos)
      - Rodapé com totais agregados

    Permissões: apenas Admin e CEO.
    """
    # --- Reutilizar toda a lógica de cálculo do pool-distribution ---

    # 1. Verificar modelo de distribuição
    config_doc = await db.finance_configs.find_one({"company_id": company_id})

    # 2. Calcular total_pool
    start_of_month = f"{year}-{month:02d}-01T00:00:00.000Z"
    if month == 12:
        end_of_month = f"{year + 1}-01-01T00:00:00.000Z"
    else:
        end_of_month = f"{year}-{month + 1:02d}-01T00:00:00.000Z"

    pool_statuses = [FinanceStatus.PAID.value, FinanceStatus.INVOICED.value]

    pipeline = [
        {
            "$match": {
                "company_id": company_id,
                "status": {"$in": pool_statuses},
                "updated_at": {"$gte": start_of_month, "$lt": end_of_month},
            }
        },
        {
            "$group": {
                "_id": None,
                "total_pool": {"$sum": "$expected_commission"},
                "count": {"$sum": 1},
            }
        },
    ]

    pool_results = await db.process_finances.aggregate(pipeline).to_list(1)
    total_pool = _safe_float(pool_results[0].get("total_pool")) if pool_results else 0.0

    # 3. Contar consultores ativos
    consultant_roles = ["consultor", "intermediario"]

    primary_query = {
        "company": company_id,
        "role": {"$in": consultant_roles},
        "is_active": {"$ne": False},
    }
    additional_query = {
        "company": company_id,
        "additional_roles": {"$in": consultant_roles},
        "is_active": {"$ne": False},
    }

    primary_consultants = await db.users.find(primary_query, {"_id": 0, "id": 1, "name": 1, "role": 1, "base_salary": 1}).to_list(1000)
    additional_consultants = await db.users.find(additional_query, {"_id": 0, "id": 1, "name": 1, "role": 1, "base_salary": 1}).to_list(1000)

    seen_ids = set()
    all_consultants = []
    for u in primary_consultants + additional_consultants:
        uid = u.get("id", "")
        if uid and uid not in seen_ids:
            seen_ids.add(uid)
            all_consultants.append({
                "id": uid,
                "name": u.get("name", ""),
                "role": u.get("role", ""),
                "base_salary": _safe_float(u.get("base_salary")),
            })

    total_consultants = len(all_consultants)

    # 4. Calcular pool_per_consultant + breakdown
    pool_per_consultant = round(total_pool / total_consultants, 2) if total_consultants > 0 else 0.0

    for c in all_consultants:
        c["fixed_salary"] = round(c["base_salary"], 2)
        c["variable_pay"] = round(pool_per_consultant, 2)
        c["total_monthly"] = round(c["base_salary"] + pool_per_consultant, 2)

    # --- Gerar CSV ---

    month_names = [
        "", "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
        "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"
    ]
    month_label = month_names[month] if 1 <= month <= 12 else str(month)

    # Obter nome da empresa para o cabeçalho
    company_name = "PowerCell"
    try:
        sys_cfg = await db.system_config.find_one(
            {"company_id": company_id},
            {"_id": 0, "config.company_name": 1}
        )
        if sys_cfg and sys_cfg.get("config", {}).get("company_name"):
            company_name = sys_cfg["config"]["company_name"]
    except Exception:
        pass

    output = io.StringIO()
    # BOM UTF-8 para Excel reconhecer acentos correctamente
    output.write("\ufeff")

    writer = csv.writer(output, delimiter=",", quoting=csv.QUOTE_MINIMAL)

    # Cabeçalho do documento
    writer.writerow([f"{company_name} — Fecho de {month_label} {year}"])
    writer.writerow([])

    # Cabeçalho da tabela
    writer.writerow([
        "Nome do Consultor",
        "Cargo",
        "Salário Fixo (€)",
        "Comissões/Pool (€)",
        "Total a Receber (€)"
    ])

    # Linhas dos consultores
    total_base = 0.0
    total_var = 0.0
    total_grand = 0.0

    for c in all_consultants:
        role_label = "Consultor" if c["role"] == "consultor" else "Intermediário"
        fixed = c["fixed_salary"]
        variable = c["variable_pay"]
        total = c["total_monthly"]

        writer.writerow([
            c["name"],
            role_label,
            f"{fixed:.2f}",
            f"{variable:.2f}",
            f"{total:.2f}",
        ])

        total_base += fixed
        total_var += variable
        total_grand += total

    # Rodapé com totais
    writer.writerow([])
    writer.writerow([
        "TOTAL",
        f"{total_consultants} consultores",
        f"{total_base:.2f}",
        f"{total_var:.2f}",
        f"{total_grand:.2f}",
    ])

    # Resumo do pool
    writer.writerow([])
    writer.writerow([f"Total Pool do Mês: {total_pool:.2f} €"])
    writer.writerow([f"Processos Faturados: {pool_results[0].get('count', 0) if pool_results else 0}"])
    writer.writerow([f"Valor por Consultor: {pool_per_consultant:.2f} €"])
    writer.writerow([f"Gerado em: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"])

    # Preparar resposta
    output.seek(0)
    filename = f"fecho_{month_label.lower()}_{year}.csv"

    headers = {
        "Content-Disposition": f'attachment; filename="{filename}"',
        "Content-Type": "text/csv; charset=utf-8",
    }

    return StreamingResponse(
        iter([output.getvalue()]),
        headers=headers,
        media_type="text/csv",
    )


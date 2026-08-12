"""Comissões financeiras + export CSV.

Extraído de `routes/finance.py`.
"""
from __future__ import annotations

import csv
import io
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi.responses import StreamingResponse

from database import db
from services.finance_helpers import (
    _get_finance_config,
    _get_processes,
    _is_credito,
    _safe_float,
)

logger = logging.getLogger(__name__)

async def _calc_commissions_data(year: Optional[int], company_id: Optional[str] = None):
    """
    Calcula comissões por colaborador, suportando ambos os modelos:
    - Tradicional (individual_split): cada consultor recebe % do que fechou
    - Pool Global (global_pool): soma todas as receitas, divide igualmente

    Retorna dict com collaborators, totais e distribution_model.
    """
    config = await _get_finance_config()
    processes = await _get_processes(year)

    # Determinar distribution_model a partir do _get_finance_config()
    distribution_model = config.get("distribution_model", "individual_split")
    if distribution_model not in ("individual_split", "global_pool"):
        distribution_model = "individual_split"

    pct_consultor_imob = _safe_float(config.get("imobiliaria", {}).get("comissao_consultor_pct", 50))
    pct_consultor_cred = _safe_float(config.get("credito", {}).get("comissao_consultor_pct", 40))

    collaborator_data = {}

    for p in processes:
        financial = p.get("financial_data") or {}
        comissao = _safe_float(financial.get("comissao_mediacao"))

        if comissao <= 0:
            continue

        pt = p.get("process_type", "")
        is_cred = _is_credito(pt)
        pct = pct_consultor_cred if is_cred else pct_consultor_imob

        consultores = p.get("consultor_names") or ([p.get("consultor_name")] if p.get("consultor_name") else [])
        mediadores = p.get("mediador_names") or ([p.get("mediador_name")] if p.get("mediador_name") else [])

        consultor_share = comissao * (pct / 100) / max(len(consultores), 1)
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
                    "areas": {"imobiliaria": 0, "credito": 0},
                    "tipos_processo": set(),
                    "user_id": None,
                }
            collaborator_data[key]["total_comissao"] += consultor_share
            collaborator_data[key]["num_processos"] += 1
            collaborator_data[key]["areas"]["credito" if is_cred else "imobiliaria"] += consultor_share
            collaborator_data[key]["tipos_processo"].add(pt)

        for name in mediadores:
            if not name:
                continue
            key = f"mediador:{name}"
            if key not in collaborator_data:
                collaborator_data[key] = {
                    "name": name,
                    "role": "intermediario",
                    "total_comissao": 0.0,
                    "num_processos": 0,
                    "areas": {"imobiliaria": 0, "credito": 0},
                    "tipos_processo": set(),
                    "user_id": None,
                }
            collaborator_data[key]["total_comissao"] += mediador_share
            collaborator_data[key]["num_processos"] += 1
            collaborator_data[key]["areas"]["credito" if is_cred else "imobiliaria"] += mediador_share
            collaborator_data[key]["tipos_processo"].add(pt)

    # --- Buscar base_salary dos utilizadores ---
    all_names = [d["name"] for d in collaborator_data.values()]
    name_to_salary = {}
    if all_names:
        salary_users = await db.users.find(
            {"name": {"$in": all_names}, "is_active": {"$ne": False}},
            {"_id": 0, "name": 1, "base_salary": 1, "id": 1}
        ).to_list(1000)
        for su in salary_users:
            name_to_salary[su["name"]] = {
                "base_salary": _safe_float(su.get("base_salary")),
                "user_id": su.get("id"),
            }

    # --- MODELO POOL GLOBAL: recalcular parte variável ---
    if distribution_model == "global_pool" and company_id:
        # Soma total das comissões do período
        total_commissions_pool = sum(d["total_comissao"] for d in collaborator_data.values())

        # Contar consultores ativos na empresa (não só os que fecharam processos)
        consultant_roles = ["consultor", "intermediario"]
        primary_q = {"company": company_id, "role": {"$in": consultant_roles}, "is_active": {"$ne": False}}
        additional_q = {"company": company_id, "additional_roles": {"$in": consultant_roles}, "is_active": {"$ne": False}}

        primary_cons = await db.users.find(primary_q, {"_id": 0, "id": 1, "name": 1, "role": 1, "base_salary": 1}).to_list(1000)
        additional_cons = await db.users.find(additional_q, {"_id": 0, "id": 1, "name": 1, "role": 1, "base_salary": 1}).to_list(1000)

        seen_ids = set()
        active_consultants = []
        for u in primary_cons + additional_cons:
            uid = u.get("id", "")
            if uid and uid not in seen_ids:
                seen_ids.add(uid)
                active_consultants.append(u)

        total_active = len(active_consultants)
        pool_share = round(total_commissions_pool / total_active, 2) if total_active > 0 else 0.0

        # Incluir TODOS os consultores ativos (mesmo os que não fecharam processos)
        existing_names = set(d["name"] for d in collaborator_data.values())
        for ac in active_consultants:
            ac_name = ac.get("name", "")
            if ac_name and ac_name not in existing_names:
                key = f"consultor:{ac_name}" if ac.get("role") == "consultor" else f"mediador:{ac_name}"
                collaborator_data[key] = {
                    "name": ac_name,
                    "role": ac.get("role", "consultor"),
                    "total_comissao": 0.0,
                    "num_processos": 0,
                    "areas": {"imobiliaria": 0, "credito": 0},
                    "tipos_processo": set(),
                    "user_id": ac.get("id"),
                }
                existing_names.add(ac_name)

        # No modelo Pool, a parte variável é igual para todos
        for key in collaborator_data:
            collaborator_data[key]["_pool_share"] = pool_share

    # --- Montar resultado final ---
    result = []
    total_base_salaries = 0.0
    total_variable = 0.0
    total_grand = 0.0

    for key in collaborator_data:
        data = collaborator_data[key]
        salary_info = name_to_salary.get(data["name"], {})
        fixed = salary_info.get("base_salary", 0.0)

        if distribution_model == "global_pool" and "_pool_share" in data:
            variable = data["_pool_share"]
        else:
            variable = round(data["total_comissao"], 2)

        total = round(fixed + variable, 2)
        total_base_salaries += fixed
        total_variable += variable
        total_grand += total

        result.append({
            "name": data["name"],
            "role": data["role"],
            "base_salary": round(fixed, 2),
            "commission_share": round(variable, 2),
            "total_comissao": round(data["total_comissao"], 2),  # Comissão individual real (para referência)
            "total_payout": total,
            "num_processos": data["num_processos"],
            "areas": {
                "imobiliaria": round(data["areas"]["imobiliaria"], 2),
                "credito": round(data["areas"]["credito"], 2),
            },
            "tipos_processo": list(data["tipos_processo"]),
        })

    result.sort(key=lambda x: x["total_payout"], reverse=True)

    return {
        "year": year,
        "distribution_model": distribution_model,
        "collaborators": result,
        "total_comissoes_pagas": round(sum(c["total_comissao"] for c in result), 2),
        "total_base_salaries": round(total_base_salaries, 2),
        "total_variable_pay": round(total_variable, 2),
        "total_grand_monthly": round(total_grand, 2),
    }



async def run_get_finance_commissions(
    year: Optional[int],
    company_id: Optional[str],
    user: dict,
):
    """
    Comissões por colaborador com suporte para modelos híbridos.

    Modelo Tradicional (individual_split):
    - Cada consultor recebe a % configurada do que fechou.

    Modelo Pool Global (global_pool):
    - Soma todas as comissões do mês/ano, divide igualmente pelos consultores ativos.
    - Cada consultor recebe: base_salary (Fixo) + pool_share (Variável) = total_payout

    Resposta por consultor inclui:
    - base_salary: Salário Fixo Mensal (€)
    - commission_share: Parte Variável — comissão individual ou quota do Pool (€)
    - total_payout: Total a Receber = Fixo + Variável (€)
    """
    return await _calc_commissions_data(year, company_id)



async def run_export_commissions_csv(
    year: Optional[int],
    company_id: str,
    user: dict,
):
    """
    Exporta as comissões como ficheiro CSV para a Contabilidade.

    Executa a mesma lógica do endpoint GET /finance/commissions (com
    Fixo + Variável + Total, suportando ambos os modelos de distribuição),
    mas devolve um ficheiro .csv formatado com:
      - Colunas: Nome do Consultor, Cargo, Salário Fixo (€), Comissões/Pool (€), Total a Receber (€)
      - Separador: vírgula
      - Codificação: UTF-8 com BOM (para Excel abrir correctamente acentos)
      - Rodapé com totais agregados

    Permissões: apenas Admin e CEO.
    """
    data = await _calc_commissions_data(year, company_id)

    distribution_model = data.get("distribution_model", "individual_split")
    model_label = "Pool Global" if distribution_model == "global_pool" else "Tradicional (Split Individual)"

    # Obter nome da empresa
    # PACOTE DI — fallback client-facing actualizado para "Precision Crédito".
    company_name = "Precision Crédito"
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
    output.write("\ufeff")  # BOM UTF-8

    writer = csv.writer(output, delimiter=",", quoting=csv.QUOTE_MINIMAL)

    # Cabeçalho do documento
    writer.writerow([f"{company_name} — Mapa de Comissões {year or 'Anual'}"])
    writer.writerow([f"Modelo de Distribuição: {model_label}"])
    writer.writerow([])

    # Cabeçalho da tabela — colunas exactas pedidas pela Contabilidade
    writer.writerow(["Nome", "Cargo", "Fixo", "Variavel", "Total"])

    # Linhas dos consultores
    collaborators = data.get("collaborators", [])
    for c in collaborators:
        role_label = "Consultor" if c["role"] == "consultor" else "Intermediário"
        writer.writerow([
            c["name"],
            role_label,
            f"{c.get('base_salary', 0):.2f}",
            f"{c.get('commission_share', 0):.2f}",
            f"{c.get('total_payout', 0):.2f}",
        ])

    # Rodapé com totais
    writer.writerow([])
    writer.writerow([
        "TOTAL",
        f"{len(collaborators)} consultores",
        f"{data.get('total_base_salaries', 0):.2f}",
        f"{data.get('total_variable_pay', 0):.2f}",
        f"{data.get('total_grand_monthly', 0):.2f}",
    ])

    # Resumo
    writer.writerow([])
    writer.writerow([f"Total Comissões Individuais: {data.get('total_comissoes_pagas', 0):.2f} €"])
    writer.writerow([f"Modelo: {model_label}"])
    writer.writerow([f"Gerado em: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"])

    # Preparar resposta
    output.seek(0)
    filename = f"comissoes_{year or 'anual'}_{company_id}.csv"

    headers = {
        "Content-Disposition": f'attachment; filename="{filename}"',
        "Content-Type": "text/csv; charset=utf-8",
    }

    return StreamingResponse(
        iter([output.getvalue()]),
        headers=headers,
        media_type="text/csv",
    )


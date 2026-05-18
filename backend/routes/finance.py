"""
Rotas de Finanças - PowerCell

Dashboard Financeiro acessível a toda a equipa interna.
Calcula receitas, despesas e lucro líquido com base nos dados dos processos,
separados por área de negócio (Imobiliária e Crédito) com configurações dinâmicas.

Permissões:
- GET (leitura): todos os roles de staff (excepto cliente e parceiro)
- PUT /finance/config (escrita): apenas Admin e CEO
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional, List
from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel, Field

from database import db
from models.auth import UserRole
from models.finance import (
    FinanceConfigCreate as FinanceConfigCreateSchema,
    FinanceConfigUpdate as FinanceConfigUpdateSchema,
    FinanceConfigResponse,
    ProcessFinanceCreate,
    ProcessFinanceUpdate,
    ProcessFinanceResponse,
    ProcessFinanceSummary,
    FeeType,
    FinanceStatus,
    DistributionModel,
)
from services.auth import get_current_user, require_roles


logger = logging.getLogger(__name__)

router = APIRouter(tags=["Finance"])


# Roles com acesso de leitura ao dashboard financeiro
# Alinhado com a sidebar do frontend (STAFF_ROLES)
FINANCE_READ_ROLES = [
    UserRole.ADMIN, UserRole.CEO, UserRole.DIRETOR,
    UserRole.CONSULTOR, UserRole.INTERMEDIARIO,
    UserRole.ADMINISTRATIVO, UserRole.INDEXACAO,
]


# ====================================================================
# DEFAULTS & HELPERS
# ====================================================================

FINANCE_CONFIG_KEY = "finance_config"

# Percentagens por defeito
DEFAULT_CONFIG = {
    "imobiliaria": {
        "comissao_consultor_pct": 50.0,     # % da comissão que vai para o consultor
        "retida_agencia_pct": 50.0,          # % da comissão retida pela agência (lucro bruto)
        "taxa_impostos_sobre_lucro": 21.0,   # % de impostos sobre o lucro da agência (IRC simplified)
    },
    "credito": {
        "comissao_consultor_pct": 40.0,      # % da comissão que vai para o consultor
        "retida_agencia_pct": 60.0,           # % da comissão retida pela agência
        "taxa_impostos_sobre_lucro": 21.0,    # % de impostos sobre o lucro da agência
    },
}

# Process types que pertencem a cada área de negócio
CREDITO_PROCESS_TYPES = [
    "crédito", "credito", "credit", "crédito habitação",
    "habitação crédito", "financiamento", "refinanciamento",
    "crédito automóvel", "credito automovel",
]


def _safe_float(val) -> float:
    """Converte valor para float de forma segura."""
    if val is None:
        return 0.0
    try:
        return float(val)
    except (ValueError, TypeError):
        return 0.0


def _is_credito(process_type: str) -> bool:
    """Determina se um processo é da área de Crédito."""
    if not process_type:
        return False
    pt_lower = process_type.strip().lower()
    for ct in CREDITO_PROCESS_TYPES:
        if ct in pt_lower or pt_lower in ct:
            return True
    # Se não é reconhecido como crédito, é imobiliária por defeito
    return False


def _month_label(month_num: int) -> str:
    """Retorna o nome do mês em português."""
    meses = [
        "Jan", "Fev", "Mar", "Abr", "Mai", "Jun",
        "Jul", "Ago", "Set", "Out", "Nov", "Dez"
    ]
    return meses[month_num - 1] if 1 <= month_num <= 12 else ""


async def _get_finance_config() -> dict:
    """Obtém configurações financeiras da DB (com defaults)."""
    doc = await db.system_config.find_one({"_id": FINANCE_CONFIG_KEY})
    if doc and doc.get("value"):
        return doc["value"]
    return DEFAULT_CONFIG.copy()


async def _get_pct(config: dict, area: str, field: str) -> float:
    """Obtém uma percentagem da config, com fallback para defaults."""
    try:
        val = config.get(area, {}).get(field, DEFAULT_CONFIG[area][field])
        return _safe_float(val)
    except (KeyError, TypeError):
        return _safe_float(DEFAULT_CONFIG.get(area, {}).get(field, 50.0))


async def _get_processes(year: Optional[int] = None) -> list:
    """Busca processos concluídos, opcionalmente filtrados por ano."""
    won_statuses = ["concluidos"]
    query = {"status": {"$in": won_statuses}}

    if year:
        start_of_year = f"{year}-01-01T00:00:00.000Z"
        end_of_year = f"{year}-12-31T23:59:59.999Z"
        query["updated_at"] = {"$gte": start_of_year, "$lte": end_of_year}

    return await db.processes.find(
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


def _calc_area_metrics(processes: list, area: str, config: dict) -> dict:
    """Calcula métricas financeiras para uma área de negócio."""
    is_cred = (area == "credito")

    pct_consultor = _safe_float(
        config.get(area, {}).get("comissao_consultor_pct", DEFAULT_CONFIG[area]["comissao_consultor_pct"])
    )
    pct_agencia = _safe_float(
        config.get(area, {}).get("retida_agencia_pct", DEFAULT_CONFIG[area]["retida_agencia_pct"])
    )
    pct_impostos = _safe_float(
        config.get(area, {}).get("taxa_impostos_sobre_lucro", DEFAULT_CONFIG[area]["taxa_impostos_sobre_lucro"])
    )

    total_receita = 0.0         # Comissões totais recebidas
    total_valor_imoveis = 0.0   # Valor dos imóveis (só imobiliária)
    total_credit_montante = 0.0 # Montante de crédito (só crédito)
    total_comissoes_pagas = 0.0 # Comissões pagas a consultores
    total_lucro_bruto = 0.0     # Lucro antes de impostos
    processos_com_comissao = 0
    count = 0

    process_details = []

    for p in processes:
        pt = p.get("process_type", "")
        # Filtrar por área
        if is_cred and not _is_credito(pt):
            continue
        if not is_cred and _is_credito(pt):
            continue

        count += 1
        financial = p.get("financial_data") or {}
        real_estate = p.get("real_estate_data") or {}
        credit = p.get("credit_data") or {}

        comissao = _safe_float(financial.get("comissao_mediacao"))
        valor_imovel = _safe_float(real_estate.get("valor_imovel"))
        montante_credito = _safe_float(credit.get("requested_amount"))

        # Receita = comissão total do processo
        total_receita += comissao

        # Comissões pagas = % configurada da comissão para o consultor
        comissao_consultor = comissao * (pct_consultor / 100)
        total_comissoes_pagas += comissao_consultor

        # Lucro bruto da agência = % retida pela agência
        lucro_bruto = comissao * (pct_agencia / 100)
        total_lucro_bruto += lucro_bruto

        if comissao > 0:
            processos_com_comissao += 1

        if not is_cred:
            total_valor_imoveis += valor_imovel
        else:
            total_credit_montante += montante_credito

        process_details.append({
            "id": p.get("id", ""),
            "process_number": p.get("process_number"),
            "client_name": p.get("client_name", ""),
            "process_type": pt,
            "comissao": round(comissao, 2),
            "comissao_consultor": round(comissao_consultor, 2),
            "lucro_agencia": round(lucro_bruto, 2),
            "valor_imovel": round(valor_imovel, 2) if not is_cred else 0,
            "montante_credito": round(montante_credito, 2) if is_cred else 0,
            "consultor": p.get("consultor_names") or ([p.get("consultor_name")] if p.get("consultor_name") else []),
            "mediador": p.get("mediador_names") or ([p.get("mediador_name")] if p.get("mediador_name") else []),
            "updated_at": p.get("updated_at", ""),
        })

    # Lucro líquido = lucro bruto - impostos
    total_impostos = total_lucro_bruto * (pct_impostos / 100)
    total_lucro_liquido = total_lucro_bruto - total_impostos
    valor_medio_comissao = total_receita / processos_com_comissao if processos_com_comissao > 0 else 0
    margem_pct = (total_lucro_liquido / total_receita * 100) if total_receita > 0 else 0

    return {
        "total_receita": round(total_receita, 2),
        "total_valor_imoveis": round(total_valor_imoveis, 2) if not is_cred else 0,
        "total_credit_montante": round(total_credit_montante, 2) if is_cred else 0,
        "comissoes_pagas_consultores": round(total_comissoes_pagas, 2),
        "lucro_bruto_agencia": round(total_lucro_bruto, 2),
        "total_impostos": round(total_impostos, 2),
        "lucro_liquido_agencia": round(total_lucro_liquido, 2),
        "taxa_margem": round(margem_pct, 1),
        "total_processos": count,
        "processos_com_comissao": processos_com_comissao,
        "valor_medio_comissao": round(valor_medio_comissao, 2),
        "pct_consultor": pct_consultor,
        "pct_agencia": pct_agencia,
        "pct_impostos": pct_impostos,
        "processos": sorted(process_details, key=lambda x: x["comissao"], reverse=True),
    }


# ====================================================================
# CONFIG ENDPOINTS
# ====================================================================

class DashboardFinanceConfigUpdate(BaseModel):
    """Schema para actualizar as configurações financeiras (dashboard legacy)."""
    imobiliaria: Optional[dict] = Field(None, description="Configurações da área de Imobiliária")
    credito: Optional[dict] = Field(None, description="Configurações da área de Crédito")


@router.get("/finance/config")
async def get_finance_config(
    user: dict = Depends(require_roles(FINANCE_READ_ROLES))
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


@router.put("/finance/config")
async def update_finance_config(
    body: DashboardFinanceConfigUpdate,
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
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


# ====================================================================
# SUMMARY ENDPOINT (separado por área)
# ====================================================================

@router.get("/finance/summary")
async def get_finance_summary(
    year: Optional[int] = Query(None, description="Ano para filtrar (ex: 2025)"),
    user: dict = Depends(require_roles(FINANCE_READ_ROLES))
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


# ====================================================================
# MONTHLY ENDPOINT
# ====================================================================

@router.get("/finance/monthly")
async def get_finance_monthly(
    year: Optional[int] = Query(None, description="Ano para filtrar"),
    user: dict = Depends(require_roles(FINANCE_READ_ROLES))
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
    ).to_list(10000)

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


# ====================================================================
# COMMISSIONS ENDPOINT (com % dinâmicas)
# ====================================================================

@router.get("/finance/commissions")
async def get_finance_commissions(
    year: Optional[int] = Query(None, description="Ano para filtrar"),
    user: dict = Depends(require_roles(FINANCE_READ_ROLES))
):
    """
    Comissões por colaborador, usando % dinâmicas da configuração.
    """
    config = await _get_finance_config()
    processes = await _get_processes(year)

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

        # Consultor recebe a % configurada (dividida por nº de consultores)
        consultor_share = comissao * (pct / 100) / max(len(consultores), 1)
        mediador_share = comissao * 0.50 / max(len(mediadores), 1)  # Intermediário fixo 50%

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

    # --- Buscar base_salary dos utilizadores para breakdown híbrido ---
    all_names = [d["name"] for d in collaborator_data.values()]
    name_to_salary = {}
    if all_names:
        # Procurar por nome para obter base_salary
        salary_users = await db.users.find(
            {"name": {"$in": all_names}, "is_active": {"$ne": False}},
            {"_id": 0, "name": 1, "base_salary": 1, "id": 1}
        ).to_list(1000)
        for su in salary_users:
            name_to_salary[su["name"]] = {
                "base_salary": _safe_float(su.get("base_salary")),
                "user_id": su.get("id"),
            }

    result = []
    total_base_salaries = 0.0
    total_variable = 0.0
    total_grand = 0.0
    for key in collaborator_data:
        data = collaborator_data[key]
        salary_info = name_to_salary.get(data["name"], {})
        fixed = salary_info.get("base_salary", 0.0)
        variable = round(data["total_comissao"], 2)
        total = round(fixed + variable, 2)
        total_base_salaries += fixed
        total_variable += variable
        total_grand += total
        result.append({
            "name": data["name"],
            "role": data["role"],
            "base_salary": round(fixed, 2),         # a) Vencimento Fixo
            "total_comissao": variable,               # b) Variável (Comissão/Pool)
            "total_monthly": total,                    # c) Total a Pagar (Fixo + Variável)
            "num_processos": data["num_processos"],
            "areas": {
                "imobiliaria": round(data["areas"]["imobiliaria"], 2),
                "credito": round(data["areas"]["credito"], 2),
            },
            "tipos_processo": list(data["tipos_processo"]),
        })

    result.sort(key=lambda x: x["total_monthly"], reverse=True)

    return {
        "year": year,
        "collaborators": result,
        "total_comissoes_pagas": round(sum(c["total_comissao"] for c in result), 2),
        "total_base_salaries": round(total_base_salaries, 2),
        "total_variable_pay": round(total_variable, 2),
        "total_grand_monthly": round(total_grand, 2),
    }


# ====================================================================
# PERFORMANCE ENDPOINT
# ====================================================================

@router.get("/finance/performance")
async def get_finance_performance(
    year: Optional[int] = Query(None, description="Ano para filtrar"),
    user: dict = Depends(require_roles(FINANCE_READ_ROLES))
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


# ====================================================================
# NEW CRUD: FinanceConfig (collection: finance_configs)
# ====================================================================

def _doc_to_config_response(doc: dict) -> dict:
    """Converte documento MongoDB para resposta FinanceConfig (remove _id)."""
    if doc is None:
        return {}
    doc.pop("_id", None)
    return doc


@router.post("/finance/configs")
async def create_finance_config(
    body: FinanceConfigCreateSchema,
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
):
    """
    Cria uma configuração financeira para uma empresa.

    Verifica se já existe uma configuração para o company_id fornecido
    antes de criar (uma config por empresa).

    Permissões: apenas Admin e CEO.
    """
    # Verificar duplicado: uma config por company_id
    existing = await db.finance_configs.find_one({"company_id": body.company_id})
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Já existe uma configuração financeira para a empresa '{body.company_id}'. "
                   f"Use PUT /finance/configs/{{config_id}} para actualizar.",
        )

    config_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    doc = {
        "id": config_id,
        "company_id": body.company_id,
        "fee_type": body.fee_type,
        "default_value": body.default_value,
        "tax_rate": body.tax_rate,
        "distribution_model": body.distribution_model or DistributionModel.INDIVIDUAL_SPLIT.value,
        "created_at": now,
        "updated_at": now,
    }

    await db.finance_configs.insert_one(doc)

    logger.info(
        f"FinanceConfig criada: id={config_id}, company_id={body.company_id}, "
        f"fee_type={body.fee_type}, por {user.get('email', 'unknown')}"
    )

    return _doc_to_config_response(doc)


@router.get("/finance/configs")
async def list_finance_configs(
    company_id: Optional[str] = Query(None, description="Filtrar por company_id"),
    user: dict = Depends(require_roles(FINANCE_READ_ROLES))
):
    """
    Lista configurações financeiras, opcionalmente filtradas por company_id.

    Permissões: todos os roles de leitura financeira.
    """
    query = {}
    if company_id:
        query["company_id"] = company_id

    configs = await db.finance_configs.find(query, {"_id": 0}).to_list(1000)
    return {"configs": configs, "total": len(configs)}


@router.get("/finance/configs/{config_id}")
async def get_finance_config_by_id(
    config_id: str,
    user: dict = Depends(require_roles(FINANCE_READ_ROLES))
):
    """
    Obtém uma configuração financeira específica por ID.

    Permissões: todos os roles de leitura financeira.
    """
    doc = await db.finance_configs.find_one({"id": config_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Configuração financeira não encontrada")
    return doc


@router.put("/finance/configs/{config_id}")
async def update_finance_config_by_id(
    config_id: str,
    body: FinanceConfigUpdateSchema,
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
):
    """
    Actualiza uma configuração financeira existente.

    Apenas os campos fornecidos no body serão actualizados.

    Permissões: apenas Admin e CEO.
    """
    existing = await db.finance_configs.find_one({"id": config_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Configuração financeira não encontrada")

    update_fields = body.model_dump(exclude_none=True)
    if not update_fields:
        raise HTTPException(status_code=400, detail="Nenhum campo fornecido para actualização")

    # Validação cruzada: se fee_type='percentage', default_value ≤ 100
    new_fee_type = update_fields.get("fee_type", existing.get("fee_type"))
    new_default_value = update_fields.get("default_value", existing.get("default_value"))
    if new_fee_type == FeeType.PERCENTAGE.value and new_default_value > 100:
        raise HTTPException(
            status_code=400,
            detail=f"Com percentagem, default_value não pode ultrapassar 100 (recebido: {new_default_value})",
        )

    update_fields["updated_at"] = datetime.now(timezone.utc).isoformat()

    await db.finance_configs.update_one(
        {"id": config_id},
        {"$set": update_fields},
    )

    # Buscar documento actualizado
    updated = await db.finance_configs.find_one({"id": config_id}, {"_id": 0})

    logger.info(
        f"FinanceConfig actualizada: id={config_id}, campos={list(update_fields.keys())}, "
        f"por {user.get('email', 'unknown')}"
    )

    return updated


@router.delete("/finance/configs/{config_id}")
async def delete_finance_config(
    config_id: str,
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
):
    """
    Elimina uma configuração financeira.

    Permissões: apenas Admin e CEO.
    """
    existing = await db.finance_configs.find_one({"id": config_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Configuração financeira não encontrada")

    await db.finance_configs.delete_one({"id": config_id})

    logger.info(
        f"FinanceConfig eliminada: id={config_id}, company_id={existing.get('company_id')}, "
        f"por {user.get('email', 'unknown')}"
    )

    return {"success": True, "message": "Configuração financeira eliminada com sucesso"}


# ====================================================================
# POOL DISTRIBUTION — Fecho de Mês (Modelo Global Pool)
# ====================================================================

@router.get("/finance/pool-distribution")
async def get_pool_distribution(
    month: int = Query(..., ge=1, le=12, description="Mês (1-12)"),
    year: int = Query(..., ge=2020, le=2100, description="Ano (ex: 2025)"),
    company_id: str = Query(..., description="Empresa para filtrar (obrigatório)"),
    user: dict = Depends(require_roles(FINANCE_READ_ROLES))
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


# ====================================================================
# NEW CRUD: ProcessFinance (collection: process_finances)
# ====================================================================

def _doc_to_process_finance_response(doc: dict) -> dict:
    """Converte documento MongoDB para resposta ProcessFinance (remove _id).

    Garante que os campos de comissão dual estão presentes, mesmo em
    documentos antigos que não os tinham (compatibilidade retroactiva).
    """
    if doc is None:
        return {}
    doc.pop("_id", None)
    # Garantir campos de comissão dual com defaults para documentos antigos
    doc.setdefault("real_estate_base_value", 0.0)
    doc.setdefault("real_estate_fee_type", None)
    doc.setdefault("real_estate_fee_value", None)
    doc.setdefault("real_estate_commission", 0.0)
    doc.setdefault("credit_base_value", 0.0)
    doc.setdefault("credit_fee_type", None)
    doc.setdefault("credit_fee_value", None)
    doc.setdefault("credit_commission", 0.0)
    return doc


# NOTA: /finance/processes/summary deve ser definido ANTES de
# /finance/processes/{finance_id} para evitar que "summary" seja
# interpretado como um finance_id pelo FastAPI.


@router.get("/finance/processes/summary")
async def get_process_finance_summary(
    company_id: str = Query(..., description="Empresa para filtrar (obrigatório)"),
    user: dict = Depends(require_roles(FINANCE_READ_ROLES))
):
    """
    Resumo financeiro agregado dos registos ProcessFinance.

    Agrega totais por status para uma empresa.

    Permissões: todos os roles de leitura financeira.
    """
    # Pipeline de agregação por status (inclui comissões duais)
    pipeline = [
        {"$match": {"company_id": company_id}},
        {"$group": {
            "_id": "$status",
            "total_commission": {"$sum": "$expected_commission"},
            "total_with_tax": {"$sum": "$total_with_tax"},
            "total_real_estate_commission": {"$sum": {"$ifNull": ["$real_estate_commission", 0]}},
            "total_credit_commission": {"$sum": {"$ifNull": ["$credit_commission", 0]}},
            "count": {"$sum": 1},
        }},
    ]

    results = await db.process_finances.aggregate(pipeline).to_list(100)

    # Inicializar resumo com zeros
    summary = ProcessFinanceSummary()

    status_map = {
        FinanceStatus.PENDING.value: "pending",
        FinanceStatus.INVOICED.value: "invoiced",
        FinanceStatus.PAID.value: "paid",
        FinanceStatus.CANCELLED.value: "cancelled",
    }

    for row in results:
        status_key = row["_id"]
        total_commission = _safe_float(row.get("total_commission"))
        total_tax = _safe_float(row.get("total_with_tax"))
        total_re_commission = _safe_float(row.get("total_real_estate_commission"))
        total_cr_commission = _safe_float(row.get("total_credit_commission"))
        count = row.get("count", 0)

        if status_key == FinanceStatus.PENDING.value:
            summary.total_pending = round(total_commission, 2)
            summary.count_pending = count
        elif status_key == FinanceStatus.INVOICED.value:
            summary.total_invoiced = round(total_commission, 2)
            summary.count_invoiced = count
        elif status_key == FinanceStatus.PAID.value:
            summary.total_paid = round(total_commission, 2)
            summary.count_paid = count
        elif status_key == FinanceStatus.CANCELLED.value:
            summary.total_cancelled = round(total_commission, 2)
            summary.count_cancelled = count

    # Totais de registos activos (não cancelados) — inclui comissões duais
    active_statuses = FinanceStatus.active_statuses()
    active_pipeline = [
        {"$match": {"company_id": company_id, "status": {"$in": active_statuses}}},
        {"$group": {
            "_id": None,
            "total_expected": {"$sum": "$expected_commission"},
            "total_with_tax": {"$sum": "$total_with_tax"},
            "total_real_estate_commission": {"$sum": {"$ifNull": ["$real_estate_commission", 0]}},
            "total_credit_commission": {"$sum": {"$ifNull": ["$credit_commission", 0]}},
        }},
    ]
    active_results = await db.process_finances.aggregate(active_pipeline).to_list(1)

    if active_results:
        summary.total_expected = round(_safe_float(active_results[0].get("total_expected")), 2)
        summary.total_with_tax = round(_safe_float(active_results[0].get("total_with_tax")), 2)
        summary.total_real_estate_commission = round(_safe_float(active_results[0].get("total_real_estate_commission")), 2)
        summary.total_credit_commission = round(_safe_float(active_results[0].get("total_credit_commission")), 2)

    return summary.model_dump()


@router.post("/finance/processes")
async def create_process_finance(
    body: ProcessFinanceCreate,
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO, UserRole.DIRETOR]))
):
    """
    Cria um registo financeiro para um processo.

    Calcula automaticamente expected_commission, tax_amount e total_with_tax
    usando ProcessFinanceCreate.compute_finance(), a menos que os valores
    sejam fornecidos explicitamente.

    Permissões: Admin, CEO e Diretor.
    """
    # Verificar se já existe registo financeiro para este processo
    existing = await db.process_finances.find_one({
        "process_id": body.process_id,
        "company_id": body.company_id,
    })
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Já existe um registo financeiro para o processo '{body.process_id}' "
                   f"na empresa '{body.company_id}'.",
        )

    # Calcular valores financeiros automáticos (inclui comissões duais)
    computed = body.compute_finance()

    finance_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    doc = {
        "id": finance_id,
        "process_id": body.process_id,
        "client_id": body.client_id,
        "company_id": body.company_id,
        # Campos legacy (comissão única — compatibilidade retroactiva)
        "base_business_value": body.base_business_value,
        "applied_fee_type": body.applied_fee_type,
        "applied_fee_value": body.applied_fee_value,
        # Comissão Imobiliária (Real Estate)
        "real_estate_base_value": body.real_estate_base_value or 0.0,
        "real_estate_fee_type": body.real_estate_fee_type,
        "real_estate_fee_value": body.real_estate_fee_value,
        "real_estate_commission": computed.get("real_estate_commission", 0.0),
        # Comissão de Crédito (Credit)
        "credit_base_value": body.credit_base_value or body.base_business_value or 0.0,
        "credit_fee_type": body.credit_fee_type or body.applied_fee_type,
        "credit_fee_value": body.credit_fee_value or body.applied_fee_value,
        "credit_commission": computed.get("credit_commission", 0.0),
        # Totais
        "expected_commission": computed["expected_commission"],
        "tax_amount": computed["tax_amount"],
        "total_with_tax": computed["total_with_tax"],
        "status": body.status or FinanceStatus.PENDING.value,
        "invoice_link": body.invoice_link,
        "created_at": now,
        "updated_at": now,
    }

    await db.process_finances.insert_one(doc)

    logger.info(
        f"ProcessFinance criado: id={finance_id}, process_id={body.process_id}, "
        f"company_id={body.company_id}, commission={computed['expected_commission']}, "
        f"re_commission={computed.get('real_estate_commission', 0.0)}, "
        f"cr_commission={computed.get('credit_commission', 0.0)}, "
        f"por {user.get('email', 'unknown')}"
    )

    return _doc_to_process_finance_response(doc)


@router.get("/finance/processes")
async def list_process_finances(
    company_id: Optional[str] = Query(None, description="Filtrar por company_id"),
    process_id: Optional[str] = Query(None, description="Filtrar por process_id"),
    client_id: Optional[str] = Query(None, description="Filtrar por client_id"),
    status: Optional[str] = Query(None, description="Filtrar por status (pending|invoiced|paid|cancelled)"),
    user: dict = Depends(require_roles(FINANCE_READ_ROLES))
):
    """
    Lista registos financeiros de processos, com filtros opcionais.

    Filtros disponíveis: company_id, process_id, client_id, status.

    Permissões: todos os roles de leitura financeira.
    """
    query = {}
    if company_id:
        query["company_id"] = company_id
    if process_id:
        query["process_id"] = process_id
    if client_id:
        query["client_id"] = client_id
    if status:
        if status not in FinanceStatus.all_values():
            raise HTTPException(
                status_code=400,
                detail=f"Status inválido: '{status}'. Valores permitidos: {FinanceStatus.all_values()}",
            )
        query["status"] = status

    finances = await db.process_finances.find(query, {"_id": 0}).to_list(1000)
    return {"finances": finances, "total": len(finances)}


@router.get("/finance/processes/{finance_id}")
async def get_process_finance_by_id(
    finance_id: str,
    user: dict = Depends(require_roles(FINANCE_READ_ROLES))
):
    """
    Obtém um registo financeiro de processo específico por ID.

    Permissões: todos os roles de leitura financeira.
    """
    doc = await db.process_finances.find_one({"id": finance_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Registo financeiro não encontrado")
    return doc


@router.put("/finance/processes/{finance_id}")
async def update_process_finance(
    finance_id: str,
    body: ProcessFinanceUpdate,
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO, UserRole.DIRETOR]))
):
    """
    Actualiza um registo financeiro de processo.

    Apenas os campos fornecidos no body serão actualizados.
    Se campos financeiros forem alterados, recalcular valores derivados.

    Permissões: Admin, CEO e Diretor.
    """
    existing = await db.process_finances.find_one({"id": finance_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Registo financeiro não encontrado")

    update_fields = body.model_dump(exclude_none=True)
    if not update_fields:
        raise HTTPException(status_code=400, detail="Nenhum campo fornecido para actualização")

    # Se campos de comissão dual foram alterados, recalcular comissão total e impostos
    dual_commission_fields_changed = any(
        f in update_fields
        for f in [
            "real_estate_base_value", "real_estate_fee_type", "real_estate_fee_value", "real_estate_commission",
            "credit_base_value", "credit_fee_type", "credit_fee_value", "credit_commission",
        ]
    )

    # Se campos financeiros legacy foram alterados, recalcular (compatibilidade retroactiva)
    financial_fields_changed = any(
        f in update_fields
        for f in ["base_business_value", "applied_fee_type", "applied_fee_value"]
    )

    if dual_commission_fields_changed:
        # Obter valores actuais + updates para recalcular comissão imobiliária
        re_base = _safe_float(update_fields.get("real_estate_base_value", existing.get("real_estate_base_value", 0.0)))
        re_fee_type = update_fields.get("real_estate_fee_type", existing.get("real_estate_fee_type"))
        re_fee_value = _safe_float(update_fields.get("real_estate_fee_value", existing.get("real_estate_fee_value", 0.0)))

        # Recalcular comissão imobiliária
        if "real_estate_commission" not in update_fields:
            if re_fee_type == FeeType.PERCENTAGE.value:
                update_fields["real_estate_commission"] = round(re_base * (re_fee_value / 100), 2)
            elif re_fee_type == FeeType.FIXED.value:
                update_fields["real_estate_commission"] = re_fee_value
            # Se não houver fee_type, manter o valor existente

        # Obter valores actuais + updates para recalcular comissão de crédito
        cr_base = _safe_float(update_fields.get("credit_base_value", existing.get("credit_base_value", 0.0)))
        cr_fee_type = update_fields.get("credit_fee_type", existing.get("credit_fee_type"))
        cr_fee_value = _safe_float(update_fields.get("credit_fee_value", existing.get("credit_fee_value", 0.0)))

        # Recalcular comissão de crédito
        if "credit_commission" not in update_fields:
            if cr_fee_type == FeeType.PERCENTAGE.value:
                update_fields["credit_commission"] = round(cr_base * (cr_fee_value / 100), 2)
            elif cr_fee_type == FeeType.FIXED.value:
                update_fields["credit_commission"] = cr_fee_value
            # Se não houver fee_type, manter o valor existente

        # Recalcular expected_commission = real_estate_commission + credit_commission
        re_commission = _safe_float(update_fields.get("real_estate_commission", existing.get("real_estate_commission", 0.0)))
        cr_commission = _safe_float(update_fields.get("credit_commission", existing.get("credit_commission", 0.0)))
        expected_commission = round(re_commission + cr_commission, 2)

        if "expected_commission" not in update_fields:
            update_fields["expected_commission"] = expected_commission

        # Recalcular tax_amount e total_with_tax
        tax_rate = _safe_float(existing.get("tax_rate", 23.0))
        ec = update_fields.get("expected_commission", expected_commission)
        if "tax_amount" not in update_fields:
            update_fields["tax_amount"] = round(_safe_float(ec) * (tax_rate / 100), 2)
        if "total_with_tax" not in update_fields:
            ta = update_fields.get("tax_amount", update_fields["tax_amount"])
            update_fields["total_with_tax"] = round(_safe_float(ec) + _safe_float(ta), 2)

    elif financial_fields_changed:
        # Compatibilidade retroactiva: recalcular usando lógica legacy
        base = _safe_float(update_fields.get("base_business_value", existing.get("base_business_value")))
        fee_type = update_fields.get("applied_fee_type", existing.get("applied_fee_type"))
        fee_value = _safe_float(update_fields.get("applied_fee_value", existing.get("applied_fee_value")))
        tax_rate = _safe_float(existing.get("tax_rate", 23.0))

        # Recalcular expected_commission
        if fee_type == FeeType.PERCENTAGE.value:
            expected_commission = round(base * (fee_value / 100), 2)
        else:
            expected_commission = fee_value

        # Recalcular tax_amount e total_with_tax (se não fornecidos explicitamente)
        if "expected_commission" not in update_fields:
            update_fields["expected_commission"] = expected_commission
        if "tax_amount" not in update_fields:
            update_fields["tax_amount"] = round(update_fields.get("expected_commission", expected_commission) * (tax_rate / 100), 2)
        if "total_with_tax" not in update_fields:
            ec = update_fields.get("expected_commission", expected_commission)
            ta = update_fields.get("tax_amount", update_fields["tax_amount"])
            update_fields["total_with_tax"] = round(ec + ta, 2)

    update_fields["updated_at"] = datetime.now(timezone.utc).isoformat()

    await db.process_finances.update_one(
        {"id": finance_id},
        {"$set": update_fields},
    )

    # Buscar documento actualizado
    updated = await db.process_finances.find_one({"id": finance_id}, {"_id": 0})

    logger.info(
        f"ProcessFinance actualizado: id={finance_id}, campos={list(update_fields.keys())}, "
        f"por {user.get('email', 'unknown')}"
    )

    return updated


@router.patch("/finance/processes/{finance_id}/status")
async def update_process_finance_status(
    finance_id: str,
    status: str = Query(..., description="Novo status: pending|invoiced|paid|cancelled"),
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO, UserRole.DIRETOR]))
):
    """
    Actualiza apenas o status de um registo financeiro.

    Útil para marcações rápidas (ex: marcar como pago).

    Permissões: Admin, CEO e Diretor.
    """
    if status not in FinanceStatus.all_values():
        raise HTTPException(
            status_code=400,
            detail=f"Status inválido: '{status}'. Valores permitidos: {FinanceStatus.all_values()}",
        )

    existing = await db.process_finances.find_one({"id": finance_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Registo financeiro não encontrado")

    now = datetime.now(timezone.utc).isoformat()
    await db.process_finances.update_one(
        {"id": finance_id},
        {"$set": {"status": status, "updated_at": now}},
    )

    logger.info(
        f"ProcessFinance status actualizado: id={finance_id}, "
        f"status={existing.get('status')} → {status}, "
        f"por {user.get('email', 'unknown')}"
    )

    return {
        "id": finance_id,
        "previous_status": existing.get("status"),
        "new_status": status,
        "updated_at": now,
    }


@router.delete("/finance/processes/{finance_id}")
async def delete_process_finance(
    finance_id: str,
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
):
    """
    Elimina um registo financeiro de processo.

    Permissões: apenas Admin e CEO.
    """
    existing = await db.process_finances.find_one({"id": finance_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Registo financeiro não encontrado")

    await db.process_finances.delete_one({"id": finance_id})

    logger.info(
        f"ProcessFinance eliminado: id={finance_id}, process_id={existing.get('process_id')}, "
        f"company_id={existing.get('company_id')}, por {user.get('email', 'unknown')}"
    )

    return {"success": True, "message": "Registo financeiro eliminado com sucesso"}

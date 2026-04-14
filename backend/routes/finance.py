"""
Rotas de Finanças - PowerCell

Dashboard Financeiro exclusivo para Admin e CEO.
Calcula receitas, despesas e lucro líquido com base nos dados dos processos,
separados por área de negócio (Imobiliária e Crédito) com configurações dinâmicas.
"""

import logging
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel, Field

from database import db
from models.auth import UserRole
from services.auth import get_current_user, require_roles


logger = logging.getLogger(__name__)

router = APIRouter(tags=["Finance"])


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

class FinanceConfigUpdate(BaseModel):
    """Schema para actualizar as configurações financeiras."""
    imobiliaria: Optional[dict] = Field(None, description="Configurações da área de Imobiliária")
    credito: Optional[dict] = Field(None, description="Configurações da área de Crédito")


@router.get("/finance/config")
async def get_finance_config(
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
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
    body: FinanceConfigUpdate,
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
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
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
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
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
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
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
                    "role": "mediador",
                    "total_comissao": 0.0,
                    "num_processos": 0,
                    "areas": {"imobiliaria": 0, "credito": 0},
                    "tipos_processo": set(),
                }
            collaborator_data[key]["total_comissao"] += mediador_share
            collaborator_data[key]["num_processos"] += 1
            collaborator_data[key]["areas"]["credito" if is_cred else "imobiliaria"] += mediador_share
            collaborator_data[key]["tipos_processo"].add(pt)

    result = []
    for key in collaborator_data:
        data = collaborator_data[key]
        result.append({
            "name": data["name"],
            "role": data["role"],
            "total_comissao": round(data["total_comissao"], 2),
            "num_processos": data["num_processos"],
            "areas": {
                "imobiliaria": round(data["areas"]["imobiliaria"], 2),
                "credito": round(data["areas"]["credito"], 2),
            },
            "tipos_processo": list(data["tipos_processo"]),
        })

    result.sort(key=lambda x: x["total_comissao"], reverse=True)

    return {
        "year": year,
        "collaborators": result,
        "total_comissoes_pagas": round(sum(c["total_comissao"] for c in result), 2),
    }


# ====================================================================
# PERFORMANCE ENDPOINT
# ====================================================================

@router.get("/finance/performance")
async def get_finance_performance(
    year: Optional[int] = Query(None, description="Ano para filtrar"),
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
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

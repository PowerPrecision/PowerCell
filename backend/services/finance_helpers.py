"""Helpers partilhados do dashboard financeiro.

Extraído de `routes/finance.py`.
Não confundir com `services/process_finance.py` (snapshots de processos).
"""
from __future__ import annotations

import logging
from typing import Optional

from pydantic import BaseModel, Field

from database import db
from models.auth import UserRole

logger = logging.getLogger(__name__)

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
    ).to_list(2000)


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


class DashboardFinanceConfigUpdate(BaseModel):
    """Schema para actualizar as configurações financeiras (dashboard legacy)."""
    imobiliaria: Optional[dict] = Field(None, description="Configurações da área de Imobiliária")
    credito: Optional[dict] = Field(None, description="Configurações da área de Crédito")
    distribution_model: Optional[str] = Field(None, description="Modelo de distribuição: 'individual_split' ou 'global_pool'")


"""CRUD de finance_configs (multi-empresa).

Extraído de `routes/finance.py`.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException

from database import db
from models.finance import (
    FinanceConfigCreate as FinanceConfigCreateSchema,
    FinanceConfigUpdate as FinanceConfigUpdateSchema,
    FeeType,
    DistributionModel,
)

from services.finance_scope import carregar_ambito_financeiro, exigir_empresa_no_ambito

logger = logging.getLogger(__name__)


async def _exigir_config_no_ambito(config: dict, user: dict) -> None:
    """404 se a configuração é de uma empresa fora da rede de quem actua.

    A configuração financeira (percentagens de comissão, modelo de
    distribuição) é de UMA empresa; ler, editar ou apagar a de outra por id
    é a escrita cruzada que `require_roles` (autoriza o verbo) não vê.
    """
    await exigir_empresa_no_ambito(config.get("company_id"), user=user)


def _doc_to_config_response(doc: dict) -> dict:
    """Converte documento MongoDB para resposta FinanceConfig (remove _id)."""
    if doc is None:
        return {}
    doc.pop("_id", None)
    return doc



async def run_create_finance_config(
    body: FinanceConfigCreateSchema,
    user: dict,
):
    """
    Cria uma configuração financeira para uma empresa.

    Verifica se já existe uma configuração para o company_id fornecido
    antes de criar (uma config por empresa).

    Permissões: apenas Admin e CEO.
    """
    await exigir_empresa_no_ambito(body.company_id, user=user)

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



async def run_list_finance_configs(
    company_id: Optional[str],
    user: dict,
):
    """
    Lista configurações financeiras, opcionalmente filtradas por company_id.

    Permissões: todos os roles de leitura financeira.
    """
    query = {}
    if company_id:
        await exigir_empresa_no_ambito(company_id, user=user)
        query["company_id"] = company_id
    else:
        # Sem filtro, só as configurações das empresas da rede de quem pede.
        ambito = await carregar_ambito_financeiro(user)
        if ambito.condicao:
            query["company_id"] = {"$in": sorted({str(e) for e in ambito.empresas})}

    configs = await db.finance_configs.find(query, {"_id": 0}).to_list(1000)
    return {"configs": configs, "total": len(configs)}



async def run_get_finance_config_by_id(
    config_id: str,
    user: dict,
):
    """
    Obtém uma configuração financeira específica por ID.

    Permissões: todos os roles de leitura financeira.
    """
    doc = await db.finance_configs.find_one({"id": config_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Configuração financeira não encontrada")
    await _exigir_config_no_ambito(doc, user)
    return doc



async def run_update_finance_config_by_id(
    config_id: str,
    body: FinanceConfigUpdateSchema,
    user: dict,
):
    """
    Actualiza uma configuração financeira existente.

    Apenas os campos fornecidos no body serão actualizados.

    Permissões: apenas Admin e CEO.
    """
    existing = await db.finance_configs.find_one({"id": config_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Configuração financeira não encontrada")
    await _exigir_config_no_ambito(existing, user)

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



async def run_delete_finance_config(
    config_id: str,
    user: dict,
):
    """
    Elimina uma configuração financeira.

    Permissões: apenas Admin e CEO.
    """
    existing = await db.finance_configs.find_one({"id": config_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Configuração financeira não encontrada")
    await _exigir_config_no_ambito(existing, user)

    await db.finance_configs.delete_one({"id": config_id})

    logger.info(
        f"FinanceConfig eliminada: id={config_id}, company_id={existing.get('company_id')}, "
        f"por {user.get('email', 'unknown')}"
    )

    return {"success": True, "message": "Configuração financeira eliminada com sucesso"}


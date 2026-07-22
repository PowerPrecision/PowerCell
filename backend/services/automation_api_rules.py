"""Automation rule models and CRUD handlers.

Extraído de `routes/automation.py`.
"""
from __future__ import annotations

from typing import Optional

from fastapi import HTTPException
from pydantic import BaseModel, Field

from services.workflow_engine import (
    list_rules, get_rule, create_rule, update_rule, delete_rule,
    VALID_TRIGGERS, VALID_ACTIONS
)


class RuleCreate(BaseModel):
    """Payload para criar uma nova regra de automação."""
    name: str = Field(..., min_length=1, max_length=200)
    description: str = ""
    trigger: str = Field(..., description="Tipo de trigger")
    trigger_config: dict = {}
    action: str = Field(..., description="Tipo de ação")
    action_config: dict = {}
    is_active: bool = True


class RuleUpdate(BaseModel):
    """Payload para atualizar uma regra de automação existente."""
    name: Optional[str] = None
    description: Optional[str] = None
    trigger: Optional[str] = None
    trigger_config: Optional[dict] = None
    action: Optional[str] = None
    action_config: Optional[dict] = None
    is_active: Optional[bool] = None


async def run_get_rules(active_only: bool = False):
    rules = await list_rules(active_only)
    return {"rules": rules, "total": len(rules)}


async def run_get_rule_by_id(rule_id: str):
    rule = await get_rule(rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Regra não encontrada")
    return rule


async def run_create_rule(data: RuleCreate, user: dict):
    if data.trigger not in VALID_TRIGGERS:
        raise HTTPException(status_code=400, detail=f"Trigger inválido. Válidos: {VALID_TRIGGERS}")
    if data.action not in VALID_ACTIONS:
        raise HTTPException(status_code=400, detail=f"Ação inválida. Válidas: {VALID_ACTIONS}")
    return await create_rule(data.model_dump(), user)


async def run_update_rule(rule_id: str, data: RuleUpdate):
    update_data = {k: v for k, v in data.model_dump().items() if v is not None}
    if "trigger" in update_data and update_data["trigger"] not in VALID_TRIGGERS:
        raise HTTPException(status_code=400, detail="Trigger inválido")
    if "action" in update_data and update_data["action"] not in VALID_ACTIONS:
        raise HTTPException(status_code=400, detail="Ação inválida")

    rule = await update_rule(rule_id, update_data)
    if not rule:
        raise HTTPException(status_code=404, detail="Regra não encontrada")
    return rule


async def run_delete_rule(rule_id: str):
    success = await delete_rule(rule_id)
    if not success:
        raise HTTPException(status_code=404, detail="Regra não encontrada")
    return {"success": True, "message": "Regra eliminada"}

"""Automation rule models and CRUD handlers.

Extraído de `routes/automation.py`.
"""
from __future__ import annotations

from typing import Optional

from fastapi import HTTPException
from pydantic import BaseModel, Field

from database import db
from services.tenant_network import (
    build_tenant_condition,
    resolve_tenant_stamp,
)
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


REGRA_NAO_ENCONTRADA = "Regra não encontrada"


async def _regra_no_ambito(rule_id: str, user: dict) -> dict:
    """A regra, mas só se pertencer à rede de quem pede.

    Devolve **404** e não 403 quando é de outra rede: confirmar que
    existe já diria à Domus que a Power tem uma regra com aquele id. É a
    mesma escolha do Lote 5, ponto 3 (notificações).
    """
    tenant_condition = await build_tenant_condition(user)
    regra = await db.automation_rules.find_one(
        {"$and": [{"id": rule_id}, tenant_condition]}, {"_id": 0}
    )
    if not regra:
        raise HTTPException(status_code=404, detail=REGRA_NAO_ENCONTRADA)
    return regra


async def run_get_rules(active_only: bool = False, user: Optional[dict] = None):
    """Regras visíveis a quem pede — filtradas pela REDE (ponto 13).

    As regras pertencem à rede, não ao sistema: ser "admin" é ser admin
    da SUA rede. E o efeito atravessa mesmo a fronteira, porque uma regra
    cria TAREFAS em processos.
    """
    tenant_condition = await build_tenant_condition(user or {})
    rules = await list_rules(active_only, tenant_condition=tenant_condition)
    return {"rules": rules, "total": len(rules)}


async def run_get_rule_by_id(rule_id: str, user: Optional[dict] = None):
    return await _regra_no_ambito(rule_id, user or {})


async def run_create_rule(data: RuleCreate, user: dict):
    if data.trigger not in VALID_TRIGGERS:
        raise HTTPException(status_code=400, detail=f"Trigger inválido. Válidos: {VALID_TRIGGERS}")
    if data.action not in VALID_ACTIONS:
        raise HTTPException(status_code=400, detail=f"Ação inválida. Válidas: {VALID_ACTIONS}")

    payload = data.model_dump()
    # Carimbo da rede (ponto 13). `None` quando não há contexto de
    # empresa: carimbar a rede errada é pior do que não carimbar, porque
    # a regra ficaria visível à rede errada para SEMPRE.
    carimbo = await resolve_tenant_stamp(user)
    if carimbo:
        payload.update(carimbo)
    return await create_rule(payload, user)


async def run_update_rule(rule_id: str, data: RuleUpdate, user: Optional[dict] = None):
    update_data = {k: v for k, v in data.model_dump().items() if v is not None}
    if "trigger" in update_data and update_data["trigger"] not in VALID_TRIGGERS:
        raise HTTPException(status_code=400, detail="Trigger inválido")
    if "action" in update_data and update_data["action"] not in VALID_ACTIONS:
        raise HTTPException(status_code=400, detail="Ação inválida")

    # O âmbito é verificado ANTES de escrever: sem isto, um `update_one`
    # por id sozinho deixava a Domus alterar uma regra da Power.
    await _regra_no_ambito(rule_id, user or {})

    rule = await update_rule(rule_id, update_data)
    if not rule:
        raise HTTPException(status_code=404, detail=REGRA_NAO_ENCONTRADA)
    return rule


async def run_delete_rule(rule_id: str, user: Optional[dict] = None):
    await _regra_no_ambito(rule_id, user or {})

    success = await delete_rule(rule_id)
    if not success:
        raise HTTPException(status_code=404, detail=REGRA_NAO_ENCONTRADA)
    return {"success": True, "message": "Regra eliminada"}

"""
O22 - API de Automação de Workflows
Endpoints CRUD para regras de automação "Se X, Então Y"
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Optional

from models.auth import UserRole
from services.auth import require_roles
from services.workflow_engine import (
    list_rules, get_rule, create_rule, update_rule, delete_rule,
    VALID_TRIGGERS, VALID_ACTIONS
)

router = APIRouter(prefix="/admin/automation", tags=["Automation"])


class RuleCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str = ""
    trigger: str = Field(..., description="Tipo de trigger")
    trigger_config: dict = {}
    action: str = Field(..., description="Tipo de ação")
    action_config: dict = {}
    is_active: bool = True


class RuleUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    trigger: Optional[str] = None
    trigger_config: Optional[dict] = None
    action: Optional[str] = None
    action_config: Optional[dict] = None
    is_active: Optional[bool] = None


@router.get("/rules")
async def get_rules(
    active_only: bool = False,
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
):
    """Listar todas as regras de automação."""
    rules = await list_rules(active_only)
    return {"rules": rules, "total": len(rules)}


@router.get("/rules/{rule_id}")
async def get_rule_by_id(
    rule_id: str,
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
):
    """Obter uma regra específica."""
    rule = await get_rule(rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Regra não encontrada")
    return rule


@router.post("/rules")
async def create_rule_endpoint(
    data: RuleCreate,
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
):
    """Criar nova regra de automação."""
    if data.trigger not in VALID_TRIGGERS:
        raise HTTPException(status_code=400, detail=f"Trigger inválido. Válidos: {VALID_TRIGGERS}")
    if data.action not in VALID_ACTIONS:
        raise HTTPException(status_code=400, detail=f"Ação inválida. Válidas: {VALID_ACTIONS}")
    
    rule = await create_rule(data.model_dump(), user)
    return rule


@router.put("/rules/{rule_id}")
async def update_rule_endpoint(
    rule_id: str,
    data: RuleUpdate,
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
):
    """Actualizar uma regra."""
    update_data = {k: v for k, v in data.model_dump().items() if v is not None}
    if "trigger" in update_data and update_data["trigger"] not in VALID_TRIGGERS:
        raise HTTPException(status_code=400, detail="Trigger inválido")
    if "action" in update_data and update_data["action"] not in VALID_ACTIONS:
        raise HTTPException(status_code=400, detail="Ação inválida")
    
    rule = await update_rule(rule_id, update_data)
    if not rule:
        raise HTTPException(status_code=404, detail="Regra não encontrada")
    return rule


@router.delete("/rules/{rule_id}")
async def delete_rule_endpoint(
    rule_id: str,
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
):
    """Eliminar uma regra."""
    success = await delete_rule(rule_id)
    if not success:
        raise HTTPException(status_code=404, detail="Regra não encontrada")
    return {"success": True, "message": "Regra eliminada"}


@router.get("/triggers")
async def list_triggers(
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
):
    """Listar triggers disponíveis com descrição."""
    return {
        "triggers": [
            {"id": "process_status_changed", "label": "Estado do processo alterado", "config_fields": [
                {"key": "from_status", "label": "De estado (opcional)", "type": "select_status"},
                {"key": "target_status", "label": "Para estado", "type": "select_status"},
            ]},
            {"id": "process_created", "label": "Novo processo criado", "config_fields": []},
            {"id": "document_uploaded", "label": "Documento carregado", "config_fields": [
                {"key": "document_category", "label": "Categoria do documento", "type": "text"},
            ]},
            {"id": "process_stale", "label": "Processo sem atualização", "config_fields": [
                {"key": "stale_days", "label": "Dias sem atualização", "type": "number", "default": 14},
            ]},
            {"id": "client_registered", "label": "Novo cliente registado", "config_fields": []},
        ]
    }


@router.get("/actions")
async def list_actions(
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
):
    """Listar ações disponíveis com descrição."""
    return {
        "actions": [
            {"id": "send_notification", "label": "Enviar notificação", "config_fields": [
                {"key": "target_role", "label": "Para role (ex: admin, consultor)", "type": "select_role"},
                {"key": "target_user_id", "label": "Ou para utilizador específico", "type": "select_user"},
                {"key": "message", "label": "Mensagem (usar {client_name}, {status})", "type": "textarea"},
            ]},
            {"id": "change_status", "label": "Alterar estado do processo", "config_fields": [
                {"key": "new_status", "label": "Novo estado", "type": "select_status"},
            ]},
            {"id": "assign_user", "label": "Atribuir utilizador", "config_fields": [
                {"key": "user_id", "label": "Utilizador", "type": "select_user"},
                {"key": "role_field", "label": "Campo (assigned_consultor_id ou assigned_mediador_id)", "type": "select", "options": ["assigned_consultor_id", "assigned_mediador_id"]},
            ]},
            {"id": "add_comment", "label": "Adicionar comentário", "config_fields": [
                {"key": "comment", "label": "Texto do comentário", "type": "textarea"},
            ]},
            {"id": "send_email", "label": "Enviar email (template)", "config_fields": [
                {"key": "template", "label": "Template do email", "type": "select_email_template"},
            ]},
        ]
    }

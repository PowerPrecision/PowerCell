"""
Rotas para configuração dinâmica do formulário público.
Permite ao admin gerir quais campos são visíveis/obrigatórios e criar campos personalizados.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from database import db
from services.auth import require_roles
from models.auth import UserRole
from datetime import datetime, timezone
import uuid

router = APIRouter(prefix="/admin/form-config", tags=["form-config"])


class FormFieldConfig(BaseModel):
    field_key: str
    label: str
    step: int
    is_visible: bool = True
    is_required: bool = False
    field_type: str = "text"
    options: Optional[list] = None
    order: int = 0
    is_custom: bool = False
    placeholder: Optional[str] = None
    hint: Optional[str] = None


class FormConfigUpdate(BaseModel):
    fields: list[dict]


class CustomFieldCreate(BaseModel):
    label: str
    step: int  # 1-6
    field_type: str  # text, select, checkbox, radio, date, number
    is_required: bool = False
    options: Optional[list] = None  # For select/checkbox/radio
    placeholder: Optional[str] = None
    hint: Optional[str] = None


# Configuração padrão do formulário
DEFAULT_FORM_CONFIG = [
    # Step 1 - Dados Pessoais
    {"field_key": "name", "label": "Nome completo", "step": 1, "is_visible": True, "is_required": True, "field_type": "text", "order": 1, "is_custom": False},
    {"field_key": "email", "label": "Email", "step": 1, "is_visible": True, "is_required": True, "field_type": "text", "order": 2, "is_custom": False},
    {"field_key": "phone", "label": "Telemóvel", "step": 1, "is_visible": True, "is_required": True, "field_type": "text", "order": 3, "is_custom": False},
    {"field_key": "nif", "label": "NIF", "step": 1, "is_visible": True, "is_required": True, "field_type": "text", "order": 4, "is_custom": False},
    {"field_key": "documento_id", "label": "Cartão de Cidadão/Passaporte", "step": 1, "is_visible": True, "is_required": True, "field_type": "text", "order": 5, "is_custom": False},
    {"field_key": "naturalidade", "label": "Naturalidade", "step": 1, "is_visible": True, "is_required": True, "field_type": "text", "order": 6, "is_custom": False},
    {"field_key": "nacionalidade", "label": "Nacionalidade", "step": 1, "is_visible": True, "is_required": True, "field_type": "text", "order": 7, "is_custom": False},
    {"field_key": "morada_fiscal", "label": "Morada Fiscal", "step": 1, "is_visible": True, "is_required": True, "field_type": "text", "order": 8, "is_custom": False},
    {"field_key": "birth_date", "label": "Data de Nascimento", "step": 1, "is_visible": True, "is_required": True, "field_type": "date", "order": 9, "is_custom": False},
    {"field_key": "estado_civil", "label": "Estado Civil", "step": 1, "is_visible": True, "is_required": True, "field_type": "select", "order": 10, "is_custom": False},
    # Step 2 - Segundo Titular
    {"field_key": "compra_com_outra_pessoa", "label": "Compra com outra pessoa?", "step": 2, "is_visible": True, "is_required": True, "field_type": "radio", "order": 1, "is_custom": False},
    {"field_key": "titular2_name", "label": "Nome do 2º Titular", "step": 2, "is_visible": True, "is_required": False, "field_type": "text", "order": 2, "is_custom": False},
    # Step 3 - Dados do Imóvel
    {"field_key": "finalidade", "label": "Finalidade do pedido", "step": 3, "is_visible": True, "is_required": True, "field_type": "select", "order": 1, "is_custom": False},
    {"field_key": "tipo_imovel", "label": "O que procura?", "step": 3, "is_visible": True, "is_required": True, "field_type": "select", "order": 2, "is_custom": False},
    {"field_key": "num_quartos", "label": "Número de quartos", "step": 3, "is_visible": True, "is_required": True, "field_type": "select", "order": 3, "is_custom": False},
    {"field_key": "localizacao", "label": "Localização/Zona preferida", "step": 3, "is_visible": True, "is_required": True, "field_type": "text", "order": 4, "is_custom": False},
    {"field_key": "caracteristicas", "label": "Características desejadas", "step": 3, "is_visible": True, "is_required": False, "field_type": "checkbox", "order": 5, "is_custom": False},
    # Step 4 - Situação Financeira
    {"field_key": "chave_movel_digital", "label": "Chave Móvel Digital", "step": 4, "is_visible": True, "is_required": True, "field_type": "radio", "order": 1, "is_custom": False},
    {"field_key": "employment_type", "label": "Tipo de Contrato de Trabalho", "step": 4, "is_visible": True, "is_required": True, "field_type": "select", "order": 2, "is_custom": False},
    {"field_key": "efetivo", "label": "Efetivo?", "step": 4, "is_visible": True, "is_required": False, "field_type": "radio", "order": 3, "is_custom": False},
    {"field_key": "trabalha_estrangeiro", "label": "Trabalha no estrangeiro?", "step": 4, "is_visible": True, "is_required": False, "field_type": "radio", "order": 4, "is_custom": False},
    {"field_key": "salario_liquido", "label": "Salário mensal líquido", "step": 4, "is_visible": True, "is_required": True, "field_type": "number", "order": 5, "is_custom": False},
    {"field_key": "capital_proprio", "label": "Capital próprio disponível", "step": 4, "is_visible": True, "is_required": False, "field_type": "number", "order": 6, "is_custom": False},
    {"field_key": "valor_financiado", "label": "Valor a financiar", "step": 4, "is_visible": True, "is_required": False, "field_type": "number", "order": 7, "is_custom": False},
    # Step 5 - Histórico Bancário
    {"field_key": "bancos_creditos", "label": "Bancos com créditos ativos", "step": 5, "is_visible": True, "is_required": True, "field_type": "checkbox", "order": 1, "is_custom": False},
    {"field_key": "bancos_simulacoes", "label": "Simulações efetuadas", "step": 5, "is_visible": True, "is_required": False, "field_type": "checkbox", "order": 2, "is_custom": False},
]


@router.get("/fields")
async def get_form_config(user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))):
    """Obter configuração atual do formulário."""
    config = await db.form_config.find_one({"type": "public_form"}, {"_id": 0})
    if not config:
        return {"fields": DEFAULT_FORM_CONFIG}
    return {"fields": config.get("fields", DEFAULT_FORM_CONFIG)}


@router.put("/fields")
async def update_form_config(
    data: FormConfigUpdate,
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
):
    """Atualizar configuração do formulário."""
    now = datetime.now(timezone.utc).isoformat()
    
    await db.form_config.update_one(
        {"type": "public_form"},
        {"$set": {
            "type": "public_form",
            "fields": data.fields,
            "updated_at": now,
            "updated_by": user.get("id"),
        }},
        upsert=True
    )
    
    return {"message": "Configuração atualizada com sucesso", "updated_at": now}


@router.post("/custom-field")
async def create_custom_field(
    data: CustomFieldCreate,
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
):
    """Criar um campo personalizado no formulário."""
    if data.step < 1 or data.step > 6:
        raise HTTPException(status_code=400, detail="Passo deve ser entre 1 e 6")
    
    if data.field_type not in ("text", "select", "checkbox", "radio", "date", "number"):
        raise HTTPException(status_code=400, detail="Tipo de campo inválido")
    
    if data.field_type in ("select", "checkbox", "radio") and not data.options:
        raise HTTPException(status_code=400, detail="Campos de seleção requerem opções")
    
    # Gerar key único a partir do label
    field_key = f"custom_{uuid.uuid4().hex[:8]}"
    
    # Obter config atual
    config = await db.form_config.find_one({"type": "public_form"}, {"_id": 0})
    fields = config.get("fields", DEFAULT_FORM_CONFIG.copy()) if config else DEFAULT_FORM_CONFIG.copy()
    
    # Calcular order (último do passo)
    step_fields = [f for f in fields if f.get("step") == data.step]
    max_order = max((f.get("order", 0) for f in step_fields), default=0)
    
    new_field = {
        "field_key": field_key,
        "label": data.label,
        "step": data.step,
        "is_visible": True,
        "is_required": data.is_required,
        "field_type": data.field_type,
        "options": data.options,
        "order": max_order + 1,
        "is_custom": True,
        "placeholder": data.placeholder,
        "hint": data.hint,
    }
    
    fields.append(new_field)
    
    now = datetime.now(timezone.utc).isoformat()
    await db.form_config.update_one(
        {"type": "public_form"},
        {"$set": {
            "type": "public_form",
            "fields": fields,
            "updated_at": now,
            "updated_by": user.get("id"),
        }},
        upsert=True
    )
    
    return {"message": "Campo personalizado criado", "field": new_field}


@router.delete("/custom-field/{field_key}")
async def delete_custom_field(
    field_key: str,
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
):
    """Eliminar campo personalizado do formulário."""
    config = await db.form_config.find_one({"type": "public_form"}, {"_id": 0})
    if not config:
        raise HTTPException(status_code=404, detail="Configuração não encontrada")
    
    fields = config.get("fields", [])
    
    target = next((f for f in fields if f.get("field_key") == field_key), None)
    if not target:
        raise HTTPException(status_code=404, detail="Campo não encontrado")
    
    if not target.get("is_custom"):
        raise HTTPException(status_code=400, detail="Não é possível eliminar campos padrão do sistema")
    
    fields = [f for f in fields if f.get("field_key") != field_key]
    
    now = datetime.now(timezone.utc).isoformat()
    await db.form_config.update_one(
        {"type": "public_form"},
        {"$set": {"fields": fields, "updated_at": now, "updated_by": user.get("id")}}
    )
    
    return {"message": "Campo personalizado eliminado"}


@router.post("/reset")
async def reset_form_config(user: dict = Depends(require_roles([UserRole.ADMIN]))):
    """Repor configuração padrão do formulário (remove campos personalizados)."""
    now = datetime.now(timezone.utc).isoformat()
    
    await db.form_config.update_one(
        {"type": "public_form"},
        {"$set": {
            "type": "public_form",
            "fields": DEFAULT_FORM_CONFIG,
            "updated_at": now,
            "updated_by": user.get("id"),
        }},
        upsert=True
    )
    
    return {"message": "Configuração reposta para valores padrão", "fields": DEFAULT_FORM_CONFIG}

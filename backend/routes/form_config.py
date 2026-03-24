"""
Rotas para configuração dinâmica do formulário público.
Permite ao admin gerir quais campos são visíveis/obrigatórios.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from database import db
from services.auth import require_roles
from models.auth import UserRole
from datetime import datetime, timezone

router = APIRouter(prefix="/admin/form-config", tags=["form-config"])


class FormFieldConfig(BaseModel):
    field_key: str
    label: str
    step: int
    is_visible: bool = True
    is_required: bool = False
    field_type: str = "text"  # text, select, checkbox, radio, date, number
    options: Optional[list] = None
    order: int = 0


class FormConfigUpdate(BaseModel):
    fields: list[dict]


# Configuração padrão do formulário
DEFAULT_FORM_CONFIG = [
    # Step 1 - Dados Pessoais
    {"field_key": "name", "label": "Nome completo", "step": 1, "is_visible": True, "is_required": True, "field_type": "text", "order": 1},
    {"field_key": "email", "label": "Email", "step": 1, "is_visible": True, "is_required": True, "field_type": "text", "order": 2},
    {"field_key": "phone", "label": "Telemóvel", "step": 1, "is_visible": True, "is_required": True, "field_type": "text", "order": 3},
    {"field_key": "nif", "label": "NIF", "step": 1, "is_visible": True, "is_required": True, "field_type": "text", "order": 4},
    {"field_key": "documento_id", "label": "Cartão de Cidadão/Passaporte", "step": 1, "is_visible": True, "is_required": True, "field_type": "text", "order": 5},
    {"field_key": "naturalidade", "label": "Naturalidade", "step": 1, "is_visible": True, "is_required": True, "field_type": "text", "order": 6},
    {"field_key": "nacionalidade", "label": "Nacionalidade", "step": 1, "is_visible": True, "is_required": True, "field_type": "text", "order": 7},
    {"field_key": "morada_fiscal", "label": "Morada Fiscal", "step": 1, "is_visible": True, "is_required": True, "field_type": "text", "order": 8},
    {"field_key": "birth_date", "label": "Data de Nascimento", "step": 1, "is_visible": True, "is_required": True, "field_type": "date", "order": 9},
    {"field_key": "estado_civil", "label": "Estado Civil", "step": 1, "is_visible": True, "is_required": True, "field_type": "select", "order": 10},
    # Step 2 - Segundo Titular
    {"field_key": "compra_com_outra_pessoa", "label": "Compra com outra pessoa?", "step": 2, "is_visible": True, "is_required": True, "field_type": "radio", "order": 1},
    {"field_key": "titular2_name", "label": "Nome do 2º Titular", "step": 2, "is_visible": True, "is_required": False, "field_type": "text", "order": 2},
    # Step 3 - Dados do Imóvel
    {"field_key": "finalidade", "label": "Finalidade do pedido", "step": 3, "is_visible": True, "is_required": True, "field_type": "select", "order": 1},
    {"field_key": "tipo_imovel", "label": "O que procura?", "step": 3, "is_visible": True, "is_required": True, "field_type": "select", "order": 2},
    {"field_key": "num_quartos", "label": "Número de quartos", "step": 3, "is_visible": True, "is_required": True, "field_type": "select", "order": 3},
    {"field_key": "localizacao", "label": "Localização/Zona preferida", "step": 3, "is_visible": True, "is_required": True, "field_type": "text", "order": 4},
    {"field_key": "caracteristicas", "label": "Características desejadas", "step": 3, "is_visible": True, "is_required": False, "field_type": "checkbox", "order": 5},
    # Step 4 - Situação Financeira
    {"field_key": "chave_movel_digital", "label": "Chave Móvel Digital", "step": 4, "is_visible": True, "is_required": True, "field_type": "radio", "order": 1},
    {"field_key": "employment_type", "label": "Tipo de Contrato de Trabalho", "step": 4, "is_visible": True, "is_required": True, "field_type": "select", "order": 2},
    {"field_key": "efetivo", "label": "Efetivo?", "step": 4, "is_visible": True, "is_required": False, "field_type": "radio", "order": 3},
    {"field_key": "trabalha_estrangeiro", "label": "Trabalha no estrangeiro?", "step": 4, "is_visible": True, "is_required": False, "field_type": "radio", "order": 4},
    {"field_key": "salario_liquido", "label": "Salário mensal líquido", "step": 4, "is_visible": True, "is_required": True, "field_type": "number", "order": 5},
    {"field_key": "capital_proprio", "label": "Capital próprio disponível", "step": 4, "is_visible": True, "is_required": False, "field_type": "number", "order": 6},
    {"field_key": "valor_financiado", "label": "Valor a financiar", "step": 4, "is_visible": True, "is_required": False, "field_type": "number", "order": 7},
    # Step 5 - Histórico Bancário
    {"field_key": "bancos_creditos", "label": "Bancos com créditos ativos", "step": 5, "is_visible": True, "is_required": True, "field_type": "checkbox", "order": 1},
    {"field_key": "bancos_simulacoes", "label": "Simulações efetuadas", "step": 5, "is_visible": True, "is_required": False, "field_type": "checkbox", "order": 2},
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


@router.post("/reset")
async def reset_form_config(user: dict = Depends(require_roles([UserRole.ADMIN]))):
    """Repor configuração padrão do formulário."""
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

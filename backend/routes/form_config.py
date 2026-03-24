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


class TemplateSave(BaseModel):
    name: str
    description: Optional[str] = None


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


# =============================================
# TEMPLATES DE FORMULÁRIO
# =============================================

# Template: Crédito Habitação - formulário completo
TEMPLATE_CREDITO_HABITACAO = {
    "name": "Crédito Habitação",
    "description": "Formulário completo para pedidos de crédito habitação. Inclui todos os campos padrão com dados do imóvel e histórico bancário.",
    "is_system": True,
    "fields": DEFAULT_FORM_CONFIG,  # Usa todos os campos padrão
}

# Template: Refinanciamento - sem dados de imóvel novo, foca em créditos existentes
_REFINANCIAMENTO_FIELDS = [f for f in DEFAULT_FORM_CONFIG if f["step"] != 3] + [
    {"field_key": "finalidade", "label": "Finalidade do refinanciamento", "step": 3, "is_visible": True, "is_required": True, "field_type": "select", "order": 1, "is_custom": False},
    {"field_key": "valor_transferencia", "label": "Valor a transferir/consolidar (€)", "step": 3, "is_visible": True, "is_required": True, "field_type": "number", "order": 2, "is_custom": False},
    {"field_key": "prazo_pretendido", "label": "Prazo pretendido (anos)", "step": 3, "is_visible": True, "is_required": True, "field_type": "number", "order": 3, "is_custom": False},
    {"field_key": "banco_atual", "label": "Banco do crédito atual", "step": 3, "is_visible": True, "is_required": True, "field_type": "text", "order": 4, "is_custom": False},
    {"field_key": "spread_atual", "label": "Spread atual (%)", "step": 3, "is_visible": True, "is_required": False, "field_type": "number", "order": 5, "is_custom": False},
]

TEMPLATE_REFINANCIAMENTO = {
    "name": "Refinanciamento",
    "description": "Formulário otimizado para pedidos de transferência/refinanciamento de crédito. Substitui dados do imóvel por dados do crédito existente.",
    "is_system": True,
    "fields": _REFINANCIAMENTO_FIELDS,
}

# Template: Crédito Pessoal - simplificado, sem dados imobiliários
_CREDITO_PESSOAL_FIELDS = [
    f for f in DEFAULT_FORM_CONFIG 
    if f["step"] in (1, 2, 4, 5) or f["field_key"] in ("compra_com_outra_pessoa", "titular2_name")
]
# Ajustar steps: remover step 3 (imóvel), renumerar
for f in _CREDITO_PESSOAL_FIELDS:
    if f["step"] == 4:
        f = {**f, "step": 3}
    elif f["step"] == 5:
        f = {**f, "step": 4}
# Rebuild with correct steps
_CP_REBUILT = []
for f in DEFAULT_FORM_CONFIG:
    if f["step"] == 1:
        _CP_REBUILT.append(f)
    elif f["step"] == 2:
        _CP_REBUILT.append(f)
    elif f["step"] == 4:
        _CP_REBUILT.append({**f, "step": 3})
    elif f["step"] == 5:
        _CP_REBUILT.append({**f, "step": 4})
# Add specific field for amount
_CP_REBUILT.append({"field_key": "montante_pretendido", "label": "Montante pretendido (€)", "step": 3, "is_visible": True, "is_required": True, "field_type": "number", "order": 0, "is_custom": False})
_CP_REBUILT.append({"field_key": "finalidade_credito", "label": "Finalidade do crédito", "step": 3, "is_visible": True, "is_required": True, "field_type": "text", "order": 0, "is_custom": False})

TEMPLATE_CREDITO_PESSOAL = {
    "name": "Crédito Pessoal",
    "description": "Formulário simplificado para crédito pessoal. Sem dados imobiliários, focado em situação financeira e montante pretendido.",
    "is_system": True,
    "fields": _CP_REBUILT,
}

SYSTEM_TEMPLATES = [TEMPLATE_CREDITO_HABITACAO, TEMPLATE_REFINANCIAMENTO, TEMPLATE_CREDITO_PESSOAL]


@router.get("/templates")
async def list_templates(user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))):
    """Listar todos os templates de formulário (sistema + personalizados)."""
    # Templates do sistema
    system = []
    for t in SYSTEM_TEMPLATES:
        system.append({
            "id": f"system_{t['name'].lower().replace(' ', '_')}",
            "name": t["name"],
            "description": t["description"],
            "is_system": True,
            "field_count": len(t["fields"]),
        })
    
    # Templates personalizados (guardados na DB)
    custom_templates = await db.form_templates.find(
        {}, {"_id": 0}
    ).to_list(100)
    
    for t in custom_templates:
        t["is_system"] = False
        t["field_count"] = len(t.get("fields", []))
    
    return {"templates": system + custom_templates}


@router.get("/templates/{template_id}/preview")
async def preview_template(
    template_id: str,
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
):
    """Obter campos de um template para pré-visualização (sem ativar)."""
    if template_id.startswith("system_"):
        system_name = template_id.replace("system_", "").replace("_", " ")
        template = next(
            (t for t in SYSTEM_TEMPLATES if t["name"].lower() == system_name),
            None
        )
        if not template:
            raise HTTPException(status_code=404, detail="Template não encontrado")
        return {
            "name": template["name"],
            "description": template["description"],
            "fields": template["fields"],
            "is_system": True,
        }
    
    tpl = await db.form_templates.find_one({"id": template_id}, {"_id": 0})
    if not tpl:
        raise HTTPException(status_code=404, detail="Template não encontrado")
    
    return {
        "name": tpl.get("name"),
        "description": tpl.get("description", ""),
        "fields": tpl.get("fields", []),
        "is_system": False,
    }


@router.post("/templates")
async def save_as_template(
    data: TemplateSave,
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
):
    """Guardar a configuração atual como template."""
    if not data.name.strip():
        raise HTTPException(status_code=400, detail="Nome do template é obrigatório")
    
    # Obter config atual
    config = await db.form_config.find_one({"type": "public_form"}, {"_id": 0})
    fields = config.get("fields", DEFAULT_FORM_CONFIG) if config else DEFAULT_FORM_CONFIG
    
    template_id = f"tpl_{uuid.uuid4().hex[:8]}"
    now = datetime.now(timezone.utc).isoformat()
    
    template_doc = {
        "id": template_id,
        "name": data.name.strip(),
        "description": (data.description or "").strip(),
        "fields": fields,
        "created_at": now,
        "created_by": user.get("id"),
    }
    
    await db.form_templates.insert_one(template_doc)
    
    return {
        "message": "Template guardado com sucesso",
        "template": {
            "id": template_id,
            "name": data.name.strip(),
            "description": (data.description or "").strip(),
            "field_count": len(fields),
            "created_at": now,
        }
    }


@router.post("/templates/{template_id}/activate")
async def activate_template(
    template_id: str,
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
):
    """Ativar um template, substituindo a configuração atual do formulário."""
    now = datetime.now(timezone.utc).isoformat()
    
    # Verificar se é template do sistema
    if template_id.startswith("system_"):
        system_name = template_id.replace("system_", "").replace("_", " ")
        template = next(
            (t for t in SYSTEM_TEMPLATES if t["name"].lower() == system_name),
            None
        )
        if not template:
            raise HTTPException(status_code=404, detail="Template do sistema não encontrado")
        fields = template["fields"]
    else:
        # Template personalizado
        tpl = await db.form_templates.find_one({"id": template_id}, {"_id": 0})
        if not tpl:
            raise HTTPException(status_code=404, detail="Template não encontrado")
        fields = tpl.get("fields", DEFAULT_FORM_CONFIG)
    
    # Aplicar ao formulário ativo
    await db.form_config.update_one(
        {"type": "public_form"},
        {"$set": {
            "type": "public_form",
            "fields": fields,
            "updated_at": now,
            "updated_by": user.get("id"),
            "active_template": template_id,
        }},
        upsert=True
    )
    
    return {"message": "Template ativado com sucesso", "field_count": len(fields)}


@router.post("/templates/{template_id}/duplicate")
async def duplicate_template(
    template_id: str,
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
):
    """Duplicar um template (sistema ou personalizado) como template personalizado."""
    now = datetime.now(timezone.utc).isoformat()
    
    # Obter fields do template original
    if template_id.startswith("system_"):
        system_name = template_id.replace("system_", "").replace("_", " ")
        template = next(
            (t for t in SYSTEM_TEMPLATES if t["name"].lower() == system_name),
            None
        )
        if not template:
            raise HTTPException(status_code=404, detail="Template não encontrado")
        fields = template["fields"]
        original_name = template["name"]
    else:
        tpl = await db.form_templates.find_one({"id": template_id}, {"_id": 0})
        if not tpl:
            raise HTTPException(status_code=404, detail="Template não encontrado")
        fields = tpl.get("fields", [])
        original_name = tpl.get("name", "Template")
    
    new_id = f"tpl_{uuid.uuid4().hex[:8]}"
    new_doc = {
        "id": new_id,
        "name": f"{original_name} (cópia)",
        "description": f"Cópia de {original_name}",
        "fields": fields,
        "created_at": now,
        "created_by": user.get("id"),
    }
    
    await db.form_templates.insert_one(new_doc)
    
    return {
        "message": "Template duplicado com sucesso",
        "template": {
            "id": new_id,
            "name": new_doc["name"],
            "field_count": len(fields),
        }
    }


@router.delete("/templates/{template_id}")
async def delete_template(
    template_id: str,
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """Eliminar template personalizado."""
    if template_id.startswith("system_"):
        raise HTTPException(status_code=400, detail="Não é possível eliminar templates do sistema")
    
    result = await db.form_templates.delete_one({"id": template_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Template não encontrado")
    
    return {"message": "Template eliminado"}

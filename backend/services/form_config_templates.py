"""Form template list/preview/save/activate/duplicate/delete handlers.

Extraído de `routes/form_config.py`.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException
from pydantic import BaseModel

from database import db
from utils.input_sanitization import sanitize_string
from services.form_config_defaults import DEFAULT_FORM_CONFIG


class TemplateSave(BaseModel):
    """Payload para guardar uma configuração de formulário como template.

    Permite ao admin guardar e reutilizar configurações do formulário.

    Attributes:
        name: Nome do template.
        description: Descrição opcional do template.
    """
    name: str
    description: Optional[str] = None


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



async def run_list_templates(user: dict):
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


async def run_preview_template(template_id: str, user: dict):
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


async def run_save_as_template(data: TemplateSave, user: dict):
    """Guardar a configuração atual como template."""
    if not data.name.strip():
        raise HTTPException(status_code=400, detail="Nome do template é obrigatório")
    
    # Sanitize user-provided text fields
    safe_name = sanitize_string(data.name, max_length=200)
    safe_description = sanitize_string(data.description, max_length=500) if data.description else ""
    
    # Obter config atual
    config = await db.form_config.find_one({"type": "public_form"}, {"_id": 0})
    fields = config.get("fields", DEFAULT_FORM_CONFIG) if config else DEFAULT_FORM_CONFIG
    
    template_id = f"tpl_{uuid.uuid4().hex[:8]}"
    now = datetime.now(timezone.utc).isoformat()
    
    template_doc = {
        "id": template_id,
        "name": safe_name,
        "description": safe_description,
        "fields": fields,
        "created_at": now,
        "created_by": user.get("id"),
    }
    
    await db.form_templates.insert_one(template_doc)
    
    return {
        "message": "Template guardado com sucesso",
        "template": {
            "id": template_id,
            "name": safe_name,
            "description": safe_description,
            "field_count": len(fields),
            "created_at": now,
        }
    }


async def run_activate_template(template_id: str, user: dict):
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


async def run_duplicate_template(template_id: str, user: dict):
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


async def run_delete_template(template_id: str, user: dict):
    """Eliminar template personalizado."""
    if template_id.startswith("system_"):
        raise HTTPException(status_code=400, detail="Não é possível eliminar templates do sistema")
    
    result = await db.form_templates.delete_one({"id": template_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Template não encontrado")
    
    return {"message": "Template eliminado"}

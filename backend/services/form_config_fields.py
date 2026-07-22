"""Form field config get/update/custom-field/reset handlers.

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
from services.form_config_defaults import DEFAULT_FORM_CONFIG, DEFAULT_STEP_CONFIG


class FormFieldConfig(BaseModel):
    """Configuração de um campo individual do formulário público.

    Cada instância define como um campo deve ser renderizado no
    formulário de registo público: visibilidade, obrigatoriedade,
    tipo de input, ordem, e opções (para selects/checkboxes).

    Attributes:
        field_key: Identificador único do campo (ex: "nome", "nif").
        label: Etiqueta visível para o utilizador.
        step: Número do passo do formulário (1-6).
        is_visible: Se o campo é mostrado no formulário.
        is_required: Se o campo é obrigatório para submissão.
        field_type: Tipo de input ("text", "select", "checkbox", etc.).
        options: Lista de opções para selects/checkboxes/radios.
        order: Ordem de apresentação dentro do passo.
        is_custom: Se o campo foi criado pelo admin (vs padrão).
        placeholder: Texto placeholder para o campo.
        hint: Texto de ajuda abaixo do campo.
    """
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
    """Payload para atualizar a configuração completa do formulário.

    Envia a lista completa de campos com as suas configurações.
    Os campos não incluídos são removidos da configuração.

    Attributes:
        fields: Lista de dicionários com a configuração de cada campo.
        step_config: Configuração de visibilidade condicional por passo.
            Ex: {"2": {"depends_on": {"field": "compra_tipo", "value": "outra_pessoa"}}}
        step_labels: Nomes personalizados para passos.
            Ex: {"7": "Documentação Adicional"}
    """
    fields: list[dict]
    step_config: Optional[dict] = None
    step_labels: Optional[dict] = None


class CustomFieldCreate(BaseModel):
    """Payload para criar um campo personalizado no formulário.

    Campos personalizados permitem ao admin recolher informações
    adicionais não previstas no formulário padrão.

    Attributes:
        label: Etiqueta visível do campo.
        step: Número do passo onde o campo aparece (1-6).
        field_type: Tipo de input ("text", "select", "checkbox", "radio", "date", "number").
        is_required: Se o campo é obrigatório.
        options: Lista de opções para selects/checkboxes/radios.
        placeholder: Texto placeholder.
        hint: Texto de ajuda.
    """
    label: str
    step: int  # 1-6
    field_type: str  # text, select, checkbox, radio, date, number
    is_required: bool = False
    options: Optional[list] = None  # For select/checkbox/radio
    placeholder: Optional[str] = None
    hint: Optional[str] = None


async def run_get_form_config(user: dict):
    """Obter configuração atual do formulário.

    Se existir config na DB, faz merge com DEFAULT_FORM_CONFIG para garantir
    que novos campos adicionados em actualizações aparecem automaticamente.
    Campos customizados (is_custom=True) existentes na DB são preservados.
    """
    config = await db.form_config.find_one({"type": "public_form"}, {"_id": 0})
    if not config:
        return {"fields": DEFAULT_FORM_CONFIG, "step_config": DEFAULT_STEP_CONFIG, "step_labels": {}}

    saved_fields = config.get("fields", [])
    # Construir mapa dos campos existentes (incluindo custom)
    saved_map = {f["field_key"]: f for f in saved_fields}
    merged = []

    # Primeiro: adicionar todos os campos do DEFAULT (nativos)
    added_keys = set()
    for default_field in DEFAULT_FORM_CONFIG:
        key = default_field["field_key"]
        if key in saved_map:
            # Campo existe — fazer merge: DB wins for admin-editable fields (label,
            # is_visible, is_required, order, step, placeholder, hint, depends_on),
            # but fall back to DEFAULT for fields that the admin can't edit and that
            # may be missing from the DB (e.g. options, data_path, field_type).
            db_field = saved_map[key]
            merged_field = {**default_field, **db_field}
            # Special handling: if DB has no options but DEFAULT does, keep DEFAULT options.
            # The admin UI only manages options for custom fields; native select/checkbox
            # fields get their options from the DEFAULT config (hardcoded in the frontend).
            if not db_field.get("options") and default_field.get("options"):
                merged_field["options"] = default_field["options"]
            # Same for field_type — DB should not lose this
            if not db_field.get("field_type") and default_field.get("field_type"):
                merged_field["field_type"] = default_field["field_type"]
            merged.append(merged_field)
        else:
            # Campo novo (adicionado em actualização) — usar default
            merged.append(default_field)
        added_keys.add(key)

    # Depois: adicionar campos customizados que não existem no default
    for saved_field in saved_fields:
        key = saved_field["field_key"]
        if key not in added_keys:
            merged.append(saved_field)

    # Ordenar por step + order
    merged.sort(key=lambda f: (f.get("step", 0), f.get("order_index", f.get("order", 0))))

    step_config = config.get("step_config", DEFAULT_STEP_CONFIG)
    step_labels = config.get("step_labels", {})
    
    # Deep merge: ensure DEFAULT_STEP_CONFIG depends_on is preserved if DB lacks it
    # The DB may store display labels (e.g. "Com outra pessoa") instead of
    # internal value keys (e.g. "outra_pessoa") in depends_on.value.
    # Always prefer the DEFAULT's value since it's the correct internal key.
    merged_step_config = {}
    all_step_keys = set(list(DEFAULT_STEP_CONFIG.keys()) + list(step_config.keys()))
    for step_key in all_step_keys:
        default_entry = DEFAULT_STEP_CONFIG.get(step_key)
        db_entry = step_config.get(step_key)
        if default_entry and db_entry:
            merged_step_config[step_key] = {**default_entry, **db_entry}
            if not db_entry.get("depends_on") and default_entry.get("depends_on"):
                merged_step_config[step_key]["depends_on"] = default_entry["depends_on"]
            # Deep merge depends_on: always prefer DEFAULT value over DB
            if db_entry.get("depends_on") and default_entry.get("depends_on"):
                merged_dep = {**default_entry["depends_on"], **db_entry["depends_on"]}
                # CRITICAL: Always prefer DEFAULT depends_on value — DB may have
                # display labels (e.g. "Com outra pessoa") instead of internal
                # value keys (e.g. "outra_pessoa") that match form field values
                if default_entry["depends_on"].get("value") is not None:
                    merged_dep["value"] = default_entry["depends_on"]["value"]
                # Remove value_in if it's null/empty but value exists
                if not db_entry["depends_on"].get("value_in") and default_entry["depends_on"].get("value"):
                    merged_dep.pop("value_in", None)
                merged_step_config[step_key]["depends_on"] = merged_dep
        else:
            merged_step_config[step_key] = db_entry or default_entry
    
    return {"fields": merged, "step_config": merged_step_config, "step_labels": step_labels}


async def run_update_form_config(data: FormConfigUpdate, user: dict):
    """Actualizar configuração do formulário."""
    now = datetime.now(timezone.utc).isoformat()
    
    # Sanitize field labels and options in incoming data
    for field in data.fields:
        if field.get("label"):
            field["label"] = sanitize_string(field["label"], max_length=200)
        if field.get("placeholder"):
            field["placeholder"] = sanitize_string(field["placeholder"], max_length=200)
        if field.get("hint"):
            field["hint"] = sanitize_string(field["hint"], max_length=200)
        if field.get("options") and isinstance(field["options"], list):
            field["options"] = [sanitize_string(opt, max_length=200) if isinstance(opt, str) else opt for opt in field["options"]]
    
    # Ensure step_config preserves DEFAULT_STEP_CONFIG depends_on for step 2
    # (prevents accidental removal of compra_tipo conditional visibility)
    step_config_to_save = data.step_config if data.step_config is not None else DEFAULT_STEP_CONFIG
    if "2" in DEFAULT_STEP_CONFIG:
        if "2" not in step_config_to_save:
            # Admin removed step 2 config — restore default depends_on
            step_config_to_save["2"] = DEFAULT_STEP_CONFIG["2"]
        elif not step_config_to_save["2"].get("depends_on") and DEFAULT_STEP_CONFIG["2"].get("depends_on"):
            # Admin saved step 2 config without depends_on — preserve default
            step_config_to_save["2"]["depends_on"] = DEFAULT_STEP_CONFIG["2"]["depends_on"]
    
    # CRITICAL: Ensure fields referenced in step_config depends_on cannot be hidden
    # If compra_tipo is hidden, step 2 conditional visibility breaks silently
    for step_key, step_cfg in step_config_to_save.items():
        dep = step_cfg.get("depends_on") if isinstance(step_cfg, dict) else None
        if dep and dep.get("field"):
            trigger_field_key = dep["field"]
            for field in data.fields:
                if field.get("field_key") == trigger_field_key and field.get("is_visible") is False:
                    field["is_visible"] = True  # Force visible — it controls step visibility
    
    await db.form_config.update_one(
        {"type": "public_form"},
        {"$set": {
            "type": "public_form",
            "fields": data.fields,
            "step_config": step_config_to_save,
            "step_labels": data.step_labels if data.step_labels is not None else {},
            "updated_at": now,
            "updated_by": user.get("id"),
        }},
        upsert=True
    )
    
    return {"message": "Configuração atualizada com sucesso", "updated_at": now}


async def run_create_custom_field(data: CustomFieldCreate, user: dict):
    """Criar um campo personalizado no formulário."""
    if data.step < 1 or data.step > 6:
        raise HTTPException(status_code=400, detail="Passo deve ser entre 1 e 6")
    
    if data.field_type not in ("text", "select", "checkbox", "radio", "date", "number"):
        raise HTTPException(status_code=400, detail="Tipo de campo inválido")
    
    if data.field_type in ("select", "checkbox", "radio") and not data.options:
        raise HTTPException(status_code=400, detail="Campos de seleção requerem opções")
    
    # Sanitize user-provided text fields
    safe_label = sanitize_string(data.label, max_length=200)
    safe_placeholder = sanitize_string(data.placeholder, max_length=200) if data.placeholder else None
    safe_hint = sanitize_string(data.hint, max_length=200) if data.hint else None
    safe_options = [sanitize_string(opt, max_length=200) if isinstance(opt, str) else opt for opt in (data.options or [])]
    
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
        "label": safe_label,
        "step": data.step,
        "is_visible": True,
        "is_required": data.is_required,
        "field_type": data.field_type,
        "options": safe_options,
        "order": max_order + 1,
        "order_index": max_order + 1,
        "is_custom": True,
        "placeholder": safe_placeholder,
        "hint": safe_hint,
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


async def run_delete_custom_field(field_key: str, user: dict):
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


async def run_reset_form_config(user: dict):
    """Repor configuração padrão do formulário (remove campos personalizados)."""
    now = datetime.now(timezone.utc).isoformat()
    
    await db.form_config.update_one(
        {"type": "public_form"},
        {"$set": {
            "type": "public_form",
            "fields": DEFAULT_FORM_CONFIG,
            "step_config": DEFAULT_STEP_CONFIG,
            "step_labels": {},
            "updated_at": now,
            "updated_by": user.get("id"),
        }},
        upsert=True
    )
    
    return {"message": "Configuração reposta para valores padrão", "fields": DEFAULT_FORM_CONFIG, "step_config": DEFAULT_STEP_CONFIG, "step_labels": {}}

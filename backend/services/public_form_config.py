"""Public form-config endpoint.

Extraído de `routes/public.py`.
Defaults from `services.form_config_defaults` (same source as routes.form_config re-export).
"""
from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse

from database import db
from services.form_config_defaults import DEFAULT_FORM_CONFIG, DEFAULT_STEP_CONFIG

async def run_get_public_form_config(request: Request):
    """Obter configuração do formulário público (todos os campos visíveis, ordenados).

    Retorna dois conjuntos:
    - custom_fields: apenas campos personalizados (compatibilidade com versões anteriores)
    - all_fields: todos os campos visíveis ordenados por step + order (nativos + custom)
    """
    config = await db.form_config.find_one({"type": "public_form"}, {"_id": 0})
    if not config:
        # Sem config na DB — retornar defaults (all_fields para o frontend usar)
        visible_defaults = [f for f in DEFAULT_FORM_CONFIG if f.get("is_visible")]
        visible_defaults.sort(key=lambda f: (f.get("step", 0), f.get("order", 0)))
        return JSONResponse(status_code=200, content={"custom_fields": [], "all_fields": visible_defaults, "step_config": DEFAULT_STEP_CONFIG})
    
    saved_fields = config.get("fields", [])
    
    # Merge com DEFAULT para garantir campos novos aparecem
    saved_map = {f["field_key"]: f for f in saved_fields}
    merged = []
    added_keys = set()
    for default_field in DEFAULT_FORM_CONFIG:
        key = default_field["field_key"]
        if key in saved_map:
            # Merge: DB wins for admin-editable fields, but fall back to DEFAULT
            # for fields the admin can't edit (e.g. options, data_path, field_type)
            db_field = saved_map[key]
            merged_field = {**default_field, **db_field}
            # Preserve DEFAULT options if DB is missing them (native select/checkbox fields)
            if not db_field.get("options") and default_field.get("options"):
                merged_field["options"] = default_field["options"]
            if not db_field.get("field_type") and default_field.get("field_type"):
                merged_field["field_type"] = default_field["field_type"]
            merged.append(merged_field)
        else:
            merged.append(default_field)
        added_keys.add(key)
    # Preservar campos customizados do admin
    for saved_field in saved_fields:
        if saved_field["field_key"] not in added_keys:
            merged.append(saved_field)
    merged.sort(key=lambda f: (f.get("step", 0), f.get("order", 0)))
    
    fields = merged
    
    # Compatibilidade: custom_fields (só campos personalizados visíveis)
    custom_fields = [
        f for f in fields 
        if f.get("is_custom") and f.get("is_visible")
    ]
    
    # NOVO: all_fields — todos os campos visíveis ordenados por step + order
    # O frontend usa isto para renderizar campos na ordem configurada pelo admin
    all_fields = [
        f for f in fields
        if f.get("is_visible")
    ]
    all_fields.sort(key=lambda f: (f.get("step", 0), f.get("order_index", f.get("order", 0))))
    
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
            # If DB has no depends_on but default does, preserve default
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

    return JSONResponse(status_code=200, content={
        "custom_fields": custom_fields,
        "all_fields": all_fields,
        "step_config": merged_step_config,
        "step_labels": step_labels
    })


# ====================================================================


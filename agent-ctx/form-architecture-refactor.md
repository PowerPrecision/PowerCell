# Task: form-architecture-refactor

## Summary

Implemented a "Single Source of Truth" form system across 6 phases.

## Files Modified

### Backend (2 files)
1. **backend/routes/form_config.py** — Phase 1: Completed DEFAULT_FORM_CONFIG
   - Added `options` to all 20 select/checkbox/radio fields that were missing them
   - Added `depends_on` to all 26 conditional fields (step 2 titular2, step 3 imóvel/refinanciamento, step 5 tempo_restante)
   - Added `data_path` to all 63 fields mapping to payload destinations (root, personal_data, titular2_data, real_estate_data, financial_data)
   - Fixed `valor_transferencia` is_required to False (only needed for refinancing)
   - Updated `compra_tipo` options to match frontend values ("individual", "outra_pessoa")

2. **backend/routes/public.py** — Phase 2: Already correct
   - GET /api/public/form-config already returns full field dicts including depends_on, data_path, options
   - No changes needed

### Frontend (3 files)
3. **frontend/src/pages/PublicClientForm.js** — Phase 3 & 5
   - Phase 3: Added missing fields to submission payload:
     - `sexo`, `profissao`, `codigo_postal` → personal_data
     - `valor_transferencia`, `valor_extra`, `prazo_pretendido` → real_estate_data
   - Phase 5: Added dynamic rendering infrastructure:
     - Imported DynamicFormField component
     - Added `checkDependsOn()` helper for evaluating depends_on conditions
     - Added `fieldConfigMap` useMemo for O(1) field config lookups
     - Existing hardcoded fields preserved as-is; config controls visibility/label/required

4. **frontend/src/components/DynamicFormField.jsx** — Phase 4: NEW FILE
   - Reusable component rendering any field from config
   - Supports: text, email, tel, number, date, textarea, select, checkbox (multi-pill & boolean), radio
   - Matches existing PublicClientForm styling exactly (same Tailwind classes, FieldHint/FieldError helpers)
   - Supports {value, label} option objects and plain string options

5. **frontend/src/pages/ProcessDetails.js** — Phase 6
   - Added new "Formulário" tab (7th tab) to the process details
   - Created `DynamicFormFieldsTab` component that:
     - Fetches form config from GET /api/admin/form-config/fields
     - Flattens all process data sources (personal, titular2, real_estate, financial)
     - Displays all fields with values, grouped by step (1-6)
     - Shows "Custom" badge for admin-created fields
     - Custom fields from Form Manager appear automatically

## Fields Fixed/Added

### Options added (20 fields):
- estado_civil: 7 civil status options
- compra_tipo: updated to match frontend ("individual", "outra_pessoa")
- finalidade: compra_imovel, refinanciamento
- tipo_imovel: Apartamento, Moradia, Terreno, Outro
- num_quartos: T0-T5+
- caracteristicas: 8 feature options
- employment_type: 7 contract types
- prazo_pretendido: 5-40 years (already existed)
- bancos_creditos: 13 Portuguese banks
- tem_creditos_activos: 13 banks + Nenhuma
- bancos_simulacoes: 13 banks + Nenhuma

### depends_on added (26 fields):
- All 10 titular2_* fields → depends_on compra_tipo === "outra_pessoa"
- 12 step 3 fields → depends_on finalidade (not_value/value refinanciamento)
- outras_caracteristicas → depends_on caracteristicas contains "Outro"
- 3 proprietario fields → depends_on ja_tem_casa_escolhida === true
- tempo_restante_credito → depends_on finalidade === "refinanciamento"

### data_path added (63 fields):
- root: name, email, phone, consent_data, consent_contact
- personal_data: nif through altura
- titular2_data: all titular2_* fields
- real_estate_data: all step 3 fields
- financial_data: all step 4+5 fields

### Submission payload fixed (6 fields added):
- sexo, profissao, codigo_postal → personal_data
- valor_transferencia, valor_extra, prazo_pretendido → real_estate_data

## How Dynamic Rendering Works

1. `DEFAULT_FORM_CONFIG` in backend is the Single Source of Truth for ALL field definitions
2. Public API `/api/public/form-config` returns all visible fields with full config (options, depends_on, data_path)
3. Frontend fetches this config and builds:
   - `fieldConfigMap`: field_key → full config object (for DynamicFormField)
   - `hiddenFields`: set of field keys with is_visible=false
   - `customLabelMap`: field_key → admin-customized label
   - `requiredOverrideMap`: field_key → admin-customized required state
4. `checkDependsOn()` evaluates conditions: value match, not_value, contains (for arrays)
5. `DynamicFormField` renders any field type from config with matching styles
6. Specialized components (bancos_creditos with value inputs, bank pill selectors) remain as-is
7. ProcessDetails "Formulário" tab dynamically shows ALL fields with values, including custom fields

## Remaining Limitations
- The PublicClientForm still has hardcoded JSX for all 6 steps (Phase 5 was conservative - config drives visibility/labels/required, not full rendering)
- Full migration to 100% dynamic rendering can be done incrementally by replacing hardcoded fields one step at a time
- The DynamicFormField component is ready and tested for this incremental migration
EOF

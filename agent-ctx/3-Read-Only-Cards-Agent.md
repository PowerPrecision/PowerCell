# Task 3: Read-Only / Edit Mode for ProcessDetails Cards

## Agent: Read-Only Cards Agent

## Summary
Added per-card edit toggle (pencil icon → Cancelar/Guardar) to ProcessDetails.js. Cards default to read-only mode where disabled inputs appear as plain text instead of greyed-out inputs.

## Changes Made

### Files Modified
1. `frontend/src/index.css` — Added `.read-only-card` CSS class
2. `frontend/src/pages/ProcessDetails.js` — Added editingCard state, CardHeaderWithEdit component, updated card headers, disabled props, save handler, tab change handler

### Key Implementation Details
- `editingCard` state: `null | 'personal' | 'financial' | 'realestate' | 'credit'`
- `CardHeaderWithEdit` helper: renders title + icon + pencil/Cancelar/Guardar
- Pencil only shows when `canEdit*` permission AND `!isProcessLocked`
- `read-only-card` CSS class makes disabled inputs look like plain text
- Tab switching resets editingCard to null
- Save handler resets editingCard to null on success
- Top-section cards (Dados do Processo, Organização) left with original disabled logic
- Créditos Ativos/Contas/Simulações left with their own editingCreditField toggle

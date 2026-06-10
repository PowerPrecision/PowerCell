# Task 3-4: Fix route confusion and React Error #31

## Agent: Code Agent

## Summary

Two bugs fixed across 3 frontend files:

### Task 1: S3NotConfiguredBanner Route Confusion
- **File**: `frontend/src/pages/FilesExplorerPage.jsx`
- **Problem**: Non-admin users clicking "Ir para Configurações" were sent to `/definicoes` (personal settings) instead of `/configuracoes` (system config). Non-admin users can't configure S3 at all.
- **Fix**: Admin users see both "Configurar Agora" and "Ir para Configurações" (→ `/configuracoes`). Non-admin users see a message: "Contacte um administrador para configurar o armazenamento S3."

### Task 2: React Minified Error #31 (Objects as React children)
- **Root Cause**: Backend sometimes returns values as objects `{value, label}` instead of plain strings. When rendered directly in JSX, this causes "Objects are not valid as a React child" error.
- **Files Fixed**:
  - `frontend/src/pages/ProcessDetails.js` (getBankColor + 10 render locations)
  - `frontend/src/components/kanban/ProcessDetailsModal.jsx` (6 render locations + visits tab)
  - `frontend/src/components/PortalDocumentRequests.js` (no changes needed — already protected)

### Key Changes

1. **`getBankColor()`** in ProcessDetails.js: Now handles object inputs by converting to string before `.toLowerCase()` and string matching
2. **ProcessDetails.js**: Wrapped 10+ locations with `safeString()` including:
   - Header title (client name, process number)
   - Process type label
   - Client email in reassign dialog
   - Bank name extraction from credit items
   - Activity user_name and comment
   - Deadline title
   - Reassign dialog client fields (nome, email, telefone, nif)
3. **ProcessDetailsModal.jsx**: Wrapped 6+ locations with `safeString()` including:
   - Process title and number
   - Process type and status display
   - Visit tab fields (title, typology, location, consultor_name, notes)
   - Visit detail modal fields

### PortalDocumentRequests.js
- Already has local `safeString` function and uses it correctly throughout
- No changes needed

---
Task ID: 1
Agent: Main Agent
Task: Correções Bloco C — Validação de E-mail e Atribuição de Indexador

Work Log:
- Explored codebase: React+Vite frontend at `frontend/`, FastAPI backend at `backend/`, MongoDB database
- Identified all files needing changes for email validation and indexer auto-assignment
- Made email field required in `CreateClientModal.jsx` and `CreateProcessModal.jsx` (frontend)
- Added backend email validation in `processes.py` create_client_process endpoint (400 error if no email)
- Added backend email validation in `clients.py` create_client endpoint (400 error if no email)
- Added backend email validation in `clients.py` assign_client_to_user endpoint (400 error if no email)
- Fixed auto-assignment: added `assign_to_indexer()` call in `processes.py` after process creation
- Fixed auto-assignment: added `assign_to_indexer()` call in `clients.py` after client assignment
- Added `consultor_id` field to process documents when consultant creates the process
- Confirmed client profile already shows all processes including 2º titular (backend `get_client` already queries by `second_client_id`)
- Confirmed date formatting utilities already handle null/undefined safely with `safeFormat()`

Stage Summary:
- Frontend: Email is now mandatory in both client creation modals with visual "Email * (obrigatório para o Portal do Cliente)" label
- Backend: Three endpoints now validate email presence with HTTP 400 "O e-mail é obrigatório para a criação do Portal do Cliente"
- Backend: Auto-assignment of indexer now works when processes are created via CRM (`assign_to_indexer()` called after insert)
- Backend: `consultor_id` field properly stored when consultant creates process; `assigned_indexacao_id` set by auto-assignment algorithm
- Backend: If no indexer available, process status goes to `fila_espera` automatically

---
Task ID: 1
Agent: Main Agent
Task: Fix date display bug (01/01/1970) when creating new clients

Work Log:
- Investigated entire data flow from client creation → storage → API response → frontend display
- Identified multiple bugs causing dates to appear as 01/01/1970 (Unix epoch)
- Fixed backend process_service.py: Changed date field defaults from empty string "" to None (data_nascimento, data_validade_cc, morada_fiscal, etc.)
- Fixed backend clients.py: Added `updated_at` to listing projection so it's returned by the API
- Fixed backend clients.py: Added safeguard on GET /clients/{client_id} to ensure created_at/updated_at are always valid ISO strings
- Fixed frontend MyClientsPage.js: Replaced `new Date(a[sortField] || 0)` epoch fallback with Infinity/-Infinity for null dates
- Fixed frontend ClientsPage.js: Replaced `: 0` epoch fallback with Infinity/-Infinity for null dates
- Verified email validation (Bloco C): Backend already returns 400 if email missing, Frontend already has required attribute
- Verified auto-assignment (Bloco C): Code already correctly stores consultor_id and calls assign_to_indexer()

Stage Summary:
- Fixed 5 date-related bugs across backend and frontend
- The 01/01/1970 epoch was caused by: (1) sorting fallback using `|| 0` which creates new Date(0), (2) missing updated_at in API responses, (3) empty string defaults for date fields instead of None
- All Bloco C items were already implemented in previous sessions

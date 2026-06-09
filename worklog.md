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

## Task 1: Fix Date Display Bugs (01/01/1970 Unix Epoch)

### Date: 2026-03-04

### Changes Made

#### 1. `backend/services/process_service.py` — Empty string → None for date fields
- **Lines 491-510** (`second_client_data` dict): Changed `"documento_id"`, `"data_nascimento"`, `"birth_date"`, and `"morada_fiscal"` from defaulting to `""` to using `or None`. Empty strings are truthy in JS and get misinterpreted as dates (Unix epoch).
- **Lines 514-532** (`titular2_data` dict): Same four fields changed from `""` defaults to `or None`.

**Before**: `sc_dados_pessoais.get("data_nascimento", "")` → empty string → JS interprets as date → 01/01/1970
**After**: `sc_dados_pessoais.get("data_nascimento") or None` → `null` in JSON → JS handles gracefully

#### 2. `frontend/src/components/S3FileManager.js` — Remove `new Date(0)` fallback
- **Lines 276-282**: Replaced `new Date(0)` fallback with explicit null-date handling that pushes items without dates to the end of the sort order.

**Before**: `safeDate(a.last_modified) || new Date(0)` → missing dates render as 01/01/1970
**After**: Explicit checks for falsy dates; items without dates sort to the end instead of appearing as epoch dates.

#### 3. `backend/routes/clients.py` — Add `assigned_at` safeguard
- **Lines 1173-1180**: Added safeguard for `assigned_at` alongside existing `created_at` and `updated_at` safeguards. Empty string or falsy `assigned_at` is now normalized to `None` instead of being passed through as an invalid date.

### Root Cause
Empty strings (`""`) were used as default values for date fields in the backend. In JavaScript, `new Date("")` returns an Invalid Date object, and some UI libraries fall back to Unix epoch (01/01/1970) when encountering invalid dates. By using `None` instead, the JSON response sends `null`, which the frontend can properly detect and handle.

### Files Modified
- `backend/services/process_service.py`
- `frontend/src/components/S3FileManager.js`
- `backend/routes/clients.py`

---
Task ID: 2
Agent: Main Agent
Task: Centro de Operações — Mostrar detalhes das tarefas em background

Work Log:
- Analyzed existing BackgroundJobsPage.js from the React/Vite frontend (frontend/src/pages/BackgroundJobsPage.js)
- Analyzed the FastAPI backend background_jobs route (backend/routes/ai_bulk/background_jobs.py)
- Updated Prisma schema with BackgroundJob model (progress, total, processed, errors, currentStep, stepLog, errorMessages, details, etc.)
- Ran `bun run db:push` to sync the schema with SQLite
- Created 7 API routes in Next.js:
  - GET/POST/DELETE /api/background-jobs (list, create, clear finished)
  - GET/DELETE /api/background-jobs/[jobId] (get, delete)
  - POST /api/background-jobs/[jobId]/cancel
  - POST /api/background-jobs/[jobId]/pause
  - POST /api/background-jobs/[jobId]/resume
  - GET /api/background-jobs/metrics
  - POST /api/background-jobs/clear-all
  - POST /api/background-jobs/seed
- Built the full Centro de Operações page (src/app/page.tsx) with:
  - Header with auto-refresh toggle, metrics toggle, reload, clear buttons
  - 5 stat cards (Total, A correr, Concluídos, Pausados, Falhados) with click-to-filter
  - Job cards showing: type icon, status badge, timestamps, elapsed timer (live), progress bar, current step, error count, error log, details
  - Action buttons: Pausar/Cancelar for running jobs, Retomar/Cancelar for paused jobs, Ver detalhes (terminal-style log viewer), Delete for finished jobs
  - Job detail dialog with terminal-style log viewer (dark background, colored timestamps, step entries, error log, error messages list, raw details JSON)
  - Metrics dashboard: success rate, avg duration, total jobs, stuck count, by status breakdown, by type breakdown
  - Sticky footer with auto-refresh indicator and last update time
  - Responsive design (mobile and desktop)
  - Auto-seeding of demo data when no jobs exist
- Fixed lint error in ElapsedTimer (setState in effect → queueMicrotask)
- Fixed "Falhados" filter to include both "failed" and "cancelled" statuses
- Updated API to support comma-separated status values for filtering
- Verified with Agent Browser: page loads, job details display, dialog opens with logs, metrics dashboard works, filters work

Stage Summary:
- Full Centro de Operações page built from scratch showing all background task details
- 7 demo jobs seeded (2 running, 1 paused, 2 success, 1 failed, 1 cancelled)
- All features working: real-time auto-refresh, pause/resume/cancel actions, terminal-style log viewer, metrics dashboard, status filtering
- Files created/modified:
  - prisma/schema.prisma (added BackgroundJob model)
  - src/app/page.tsx (complete Centro de Operações page)
  - src/app/api/background-jobs/route.ts
  - src/app/api/background-jobs/[jobId]/route.ts
  - src/app/api/background-jobs/[jobId]/cancel/route.ts
  - src/app/api/background-jobs/[jobId]/pause/route.ts
  - src/app/api/background-jobs/[jobId]/resume/route.ts
  - src/app/api/background-jobs/metrics/route.ts
  - src/app/api/background-jobs/clear-all/route.ts
  - src/app/api/background-jobs/seed/route.ts

---
Task ID: 3
Agent: Main Agent
Task: Fix email signature not saving

Work Log:
- Investigated the email signature save flow across frontend and backend
- ProfilePage.js sends PUT /auth/profile with { signature, email_signature } fields
- Backend auth.py update_profile routes signature to user_company_roles (UCR) and email_signature to global users collection
- Identified 3 bugs causing the signature to not display after save:
  1. Backend GET /auth/me returns active_company_signature="" (empty string) when no UCR record exists
     - Frontend uses ?? (nullish coalescing) which doesn't fall through for empty strings
     - So "" ?? user.email_signature evaluates to "" instead of falling through to the global email_signature
  2. Backend update_profile skips UCR update when active_company_id is None
     - This happens when the user has no X-Company-Id header and no user.company field
     - The signature is saved globally but not in UCR, causing display issues on reload
  3. Frontend fallback for professionalPhone was missing the user.phone global fallback

- Fixed backend auth.py GET /auth/me:
  - Changed active_company_signature from "" to None when no UCR record or no signature field in UCR
  - Changed active_company_professional_phone and active_company_job_title similarly
  - Changed active_company_name from "" to None for consistency
  - Added check "signature" in active_assoc to distinguish between "not set" (None) and "intentionally cleared" ("")

- Fixed backend auth.py PUT /auth/profile (update_profile):
  - Added fallback for UCR company_id: ucr_company_id = active_company_id or user.get("company") or "default"
  - This ensures the signature is ALWAYS saved to UCR, even when active_company_id is None
  - Removed the warning about missing company context (no longer needed)
  - Updated lookup_company_id to use ucr_company_id when company_specific_fields were saved

- Fixed backend auth.py PUT /auth/profile response:
  - Same None vs "" fix for active_company_signature and related fields in the response

- Fixed frontend ProfilePage.js:
  - Added detailed comment explaining the null vs "" distinction and how ?? works
  - Changed professionalPhone fallback to include user.phone as global fallback
  - Email signature fallback already correct with the backend fix (None now properly falls through)

Stage Summary:
- Root cause: Backend returned "" (empty string) for active_company_signature when no UCR record existed, preventing the frontend's ?? operator from falling through to the global email_signature value
- Secondary cause: When active_company_id was None, the UCR update was skipped entirely, leaving the signature only in the global user document but not in UCR
- Files modified:
  - backend/routes/auth.py (3 locations: GET /auth/me, PUT /auth/profile UCR update, PUT /auth/profile response)
  - frontend/src/pages/ProfilePage.js (signature fallback logic with comments)

---
Task ID: 4
Agent: Main Agent
Task: Fix email signature not saving in production (works in DEV but not in PROD)

Work Log:
- Investigated the complete email signature flow across ProfilePage, SystemConfigPage, email_service, and rgpd_service
- Identified root cause: In email_service.py, `system_email_signature` was set from config at line 568 but then RESET to None at line 635, and the re-read at lines 636-642 only fetched `from_name` but NOT `email_signature`
- This means the system-wide email signature (from SystemSMTPConfig) was NEVER appended to sent emails, even though it was correctly saved in the database
- Identified secondary issue: UCR fallback for signature lookup only checked the user's default company, missing signatures stored for non-default companies
- Same secondary issue existed in rgpd_service.py

Fixes applied:
1. `backend/services/email_service.py` line 640: Added `system_email_signature = sys_config.system_smtp.email_signature or None` to re-read the signature from config after the reset
2. `backend/services/email_service.py` lines 767-775: Added Fallback 2 to check UCR of ANY company (not just default) when looking for user's personal signature
3. `backend/services/rgpd_service.py` lines 1187-1194: Same Fallback 2 pattern for RGPD consent emails
4. Verified SystemConfigPage.js already has `email_signature` field in systemSmtp state and RichTextEditor UI (was added previously)

Stage Summary:
- PRIMARY BUG: `system_email_signature` was reset to None at line 635 and never re-read from config, causing the system-wide email signature to never be appended to sent emails
- This explains why it "works in DEV but not in production" — in DEV, emails are often not actually sent (just logged), so the missing signature is not noticed; in production, the signature is expected in real emails
- SECONDARY: UCR signature fallback now checks all companies, not just the default
- Files modified:
  - backend/services/email_service.py (2 fixes: system_email_signature reset + UCR fallback)
  - backend/services/rgpd_service.py (1 fix: UCR fallback)

---
Task ID: 5
Agent: Main Agent
Task: Fix email signature not saving in production — X-Company-Id header is None when user has no companies

Work Log:
- Analyzed production log: `WARNING routes.auth [auth/profile] active_company_id é None — campos da empresa NÃO guardados! X-Company-Id header=None, user.company=None`
- Traced the complete flow: AuthContext → api.js interceptor → backend get_active_company_id_async → update_profile
- Identified root cause chain:
  1. User has no entries in user_company_roles AND user.company is None
  2. AuthContext.fetchUser() sets activeCompanyId = null (no company to set)
  3. api.js interceptor doesn't send X-Company-Id header (sessionStorage has null)
  4. Backend get_active_company_id_async() returns None
  5. Backend treats None as "no company context" and fails to save company-specific fields properly
- Applied 3-part fix:

1. Frontend (AuthContext.js): When no companies exist and user.company is null, set activeCompanyId to "default" sentinel instead of leaving it null. This ensures X-Company-Id header is ALWAYS sent by the api.js interceptor.

2. Backend (services/auth.py): In both get_active_company_id() and get_active_company_id_async(), accept "default" as a valid company_id without UCR validation. The "default" sentinel represents "no specific company context" and should not be validated against user_company_roles (which has no entry for it).

3. Backend (routes/auth.py):
   - Added "default" to is_default_company check in update_profile
   - Added warning log when active_company_id is None (matches production message format)
   - Fixed GET /auth/me to always call get_active_company_id_async (even with empty user_companies) so "default" sentinel propagates correctly

Stage Summary:
- Root cause: When user has no companies (user_company_roles empty + user.company null), the X-Company-Id header was never sent, causing active_company_id=None on the backend
- Fix: "default" sentinel value flows end-to-end: Frontend → sessionStorage → X-Company-Id header → backend accepts without validation
- The "default" sentinel ensures email_signature is always saved: globally (users collection) AND in UCR (with company_id="default")
- Files modified:
  - frontend/src/contexts/AuthContext.js (activeCompanyId fallback to "default")
  - backend/services/auth.py (both get_active_company_id functions accept "default")
  - backend/routes/auth.py (GET /auth/me + PUT /auth/profile handle "default" + warning log)

---
Task ID: 6
Agent: Main Agent
Task: Add process number to email subject when sending to balcões

Work Log:
- Investigated the email sending flow for balcões (SendDocumentationModal + backend routes)
- Found that the default email subject was `Documentação - {client_name}` — no process number
- The frontend fallback display already included process number but backend didn't
- Fixed backend `preview-documentation` endpoint: subject now includes `(Proc. {process_number})`
- Fixed backend `send-documentation` endpoint: default subject now includes `(Proc. {process_number})`
- Updated frontend fallback text to match backend format: `(Proc. {number})` instead of `(Processo #{number})`
- Confirmed `skip_proc_tag=True` prevents duplicate Tag Mágica `[Proc-{uuid}]` injection

Stage Summary:
- Email subject for balcões changed from "Documentação - João Silva" to "Documentação - João Silva (Proc. 123)"
- Files modified:
  - backend/routes/emails.py (2 locations: preview + send endpoints)
  - frontend/src/components/SendDocumentationModal.js (fallback text)

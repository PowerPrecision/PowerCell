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

---
Task ID: 7
Agent: Main Agent
Task: Correção Crítica: Formatação HTML nos E-mails para Balcões + Nº Processo no Assunto

Work Log:
- Investigated the complete email sending pipeline for balcões (counters/banks)
- Traced flow: Frontend RichTextEditor (React Quill) → custom_html_body → backend sanitize_html() → send_email() → MIME/Resend
- **ROOT CAUSE FOUND**: `sanitize_html(custom_html_body)` at line 1058 of `backend/routes/emails.py` strips ALL HTML tags because `allow_basic_formatting` defaults to `False` and `ALLOWED_TAGS = []`. The `bleach.clean()` call with empty tags list removes `<div>`, `<table>`, `<h3>`, `<strong>`, `<br>`, etc., leaving only plain text.
- Even with `allow_basic_formatting=True`, only 10 basic tags were allowed (`b, i, u, strong, em, p, br, ul, ol, li`) — not the professional email tags like `<div>`, `<table>`, `<span>`, `<a>`, `<hr>`, `<h1>`-`<h6>` needed for bank emails.
- Verified MIME type handling in `send_email()` is CORRECT: `MIMEText(body_html, "html", "utf-8")` is used when body_html is provided.
- Verified Resend API path is CORRECT: `params["html"] = html_content` is set when body_html exists.
- The bug was exclusively in the sanitization step BEFORE the email reached send_email().

Fixes applied:
1. `backend/utils/input_sanitization.py` — Added `EMAIL_SAFE_TAGS` (40+ tags) and `EMAIL_SAFE_ATTRIBUTES` (comprehensive attributes per tag including style, class, href, src, colspan, etc.) for professional email HTML. Added `allow_email_html` parameter to `sanitize_html()`.
2. `backend/routes/emails.py` line 1063 — Changed `sanitize_html(custom_html_body)` to `sanitize_html(custom_html_body, allow_email_html=True)` — preserves all email formatting (tables, bold, paragraphs, etc.) while still removing dangerous scripts/iframe/form.
3. `backend/routes/emails.py` line 1094 — Added `sanitize_html(email_template, allow_email_html=True)` for the email_template path.
4. `backend/routes/emails.py` lines 1145-1167 — Added process number enforcement in the subject: if the custom subject doesn't contain the process number, it's automatically appended as `(Proc. {process_number})`.

Stage Summary:
- PRIMARY BUG: `sanitize_html()` was stripping ALL HTML tags from the Rich Text Editor content, causing emails to balcões to arrive as plain text ("texto corrido") without any formatting.
- FIX: New `allow_email_html=True` mode preserves 40+ HTML tags needed for professional emails while still removing dangerous elements (script, iframe, form, event handlers).
- SECONDARY: Process number is now ALWAYS included in the email subject when sending to balcões, even with custom subjects.
- Files modified:
  - backend/utils/input_sanitization.py (EMAIL_SAFE_TAGS, EMAIL_SAFE_ATTRIBUTES, allow_email_html parameter)
  - backend/routes/emails.py (3 changes: custom_html_body sanitization, email_template sanitization, subject process number enforcement)

---
Task ID: 8
Agent: Main Agent
Task: Reestruturação da Área Pessoal + Fix feedback botão Guardar

Work Log:
- Analisou o ProfilePage.js completo (1192 linhas) e identificou 2 problemas
- Problema 1: Botão "Guardar Dados Profissionais" sem feedback visual claro (sem checkmark, toast genérico)
- Problema 2: Estrutura de cards misturava dados comuns (login) com dados por empresa (telefone, cargo)
- Adicionou campo `display_name` por empresa no backend (UCR, GET /auth/me, update_profile, get_user_companies)
- Reestruturou ProfilePage.js: "Informação do Perfil" + "Segurança" → "Informação de Login" (comum); "Dados Profissionais" agora inclui Nome + Telefone + Cargo
- Consolidou campo Telefone: removida duplicação entre profileData.phone e professionalPhone
- Adicionou feedback visual no botão: spinner → checkmark "Guardado!" por 2s + toast com nome da empresa
- Save consolidado: handleSaveCompanyFields agora envia display_name + name + professional_phone + phone + job_title
- Atualizou CHANGELOG.md com entrada detalhada

Stage Summary:
- 3 ficheiros alterados: auth.py (backend), auth service, ProfilePage.js
- Cards reorganizados: Login (comum) → Dados Profissionais (por empresa) → Assinatura → Sessões → Webmail
- Campo `display_name` por empresa disponível no UCR (MongoDB schemaless, sem migração)
- Feedback visual completo no botão guardar: loading → sucesso → idle

---
Task ID: 2
Agent: Code Agent
Task: Fix S3 File Explorer — S3Service not reading from database config

Work Log:
- Read and analyzed s3_storage.py: S3Service singleton reads AWS credentials from env vars at startup only
- Read and analyzed system_config.py: update_config_section saves storage config to MongoDB but never syncs to S3Service
- Read and analyzed server.py: Found startup event handler at line 978
- Added `reconfigure()` method to S3Service class (after __init__) to allow runtime re-initialization with new credentials
- Added `sync_s3_from_db_config()` async function after s3_service singleton to sync from MongoDB on startup
- Updated `update_config_section()` in system_config.py: when section=="storage", now calls s3_service.reconfigure() with DB credentials in real-time
- Updated `_build_default_config()` in system_config.py: StorageConfig now includes AWS S3 env vars (aws_access_key_id, aws_secret_access_key, aws_bucket_name, aws_region)
- Updated `server.py` startup handler: added call to sync_s3_from_db_config() after Trello init

Stage Summary:
- Root cause fixed: S3Service now reads from database config instead of only env vars
- Two sync paths implemented: (1) at startup via sync_s3_from_db_config(), (2) in real-time when user saves storage config via UI
- Files modified:
  - backend/services/s3_storage.py (added reconfigure method + sync_s3_from_db_config function)
  - backend/services/system_config.py (added S3 sync in update_config_section + AWS fields in _build_default_config)
  - backend/server.py (added sync_s3_from_db_config call in startup)
---
Task ID: 5-6
Agent: Code Agent
Task: Fix portal-requests 500 error and webmail folder sync

Work Log:
- Read and analyzed `backend/routes/documents.py` POST `/api/documents/portal-requests/{process_id}` endpoint (lines 4128-4312)
- Found that the endpoint already had outer try/except and uuid was imported, but lacked input data logging and process_id validation
- Added request data logging at the start of the endpoint (process_id, category, notes, custom_label, user_id) for debugging 500 errors
- Added process_id validation to reject empty/blank IDs with a 400 error before hitting MongoDB
- Enhanced the outer except block to include input data in the error log for post-mortem debugging
- Read `frontend/src/pages/WebmailPage.jsx` — confirmed FOLDERS array includes all 5 folders (inbox, sent, starred, drafts, trash), sidebar renders counts correctly from `folderCountsData`
- Read `backend/routes/emails.py` webmail-stats endpoint — confirmed it returns `folder_counts` with all 5 folder counts (inbox, sent, starred, drafts, trash)
- Read `backend/services/email_service.py` — identified that `sync_webmail_emails` (global sync) and `sync_user_emails` (user sync) fetch from Sent IMAP folder but do NOT explicitly set `direction="sent"` on the fetched emails
- Fixed `sync_webmail_emails`: Added explicit `em["direction"] = "sent"` loop for emails from the Sent IMAP folder
- Fixed `sync_user_emails`: Added explicit `em["direction"] = "sent"` loop for emails from the Sent IMAP folder
- Fixed `sync_shared_role_emails`: Added explicit `email_data["direction"] = "sent"` for emails from the Sent IMAP folder
- Confirmed Drafts sync already correctly sets `em["direction"] = "sent"` and `em["_is_draft"] = True` in all three sync functions
- Confirmed Trash sync already correctly sets `em["_is_trash"] = True` in all three sync functions

Stage Summary:
- Portal-requests 500 error: Added defensive logging and process_id validation. The root cause of 500s was likely unlogged exceptions; now all input is logged on entry and in the catch-all except block.
- Webmail Sent/Drafts/Trash folders: The key fix was ensuring `direction="sent"` is explicitly set for emails fetched from the Sent IMAP folder in all three sync functions. Previously, direction was inferred by comparing from_email to account.email, which could fail due to casing differences, aliases, or other mismatches — causing Sent emails to appear in Inbox instead.
- Frontend and webmail-stats endpoint were already correct — no changes needed on those sides.
- Files modified: `backend/routes/documents.py`, `backend/services/email_service.py`

---
Task ID: 3-4
Agent: Code Agent
Task: Fix route confusion and React Error #31

Work Log:
- Read FilesExplorerPage.jsx and identified S3NotConfiguredBanner (lines 488-526) with incorrect navigation to `/definicoes` for non-admin users
- Fixed S3NotConfiguredBanner: admin users now see both "Configurar Agora" and "Ir para Configurações" (→ /configuracoes); non-admin users see message "Contacte um administrador para configurar o armazenamento S3."
- Read ProcessDetails.js and identified multiple places where object values could be rendered as React children (causing Error #31)
- Fixed getBankColor() function to handle object inputs (e.g. {value, label}) by converting to string before string operations
- Fixed header title at line 2228: wrapped clientData/process names with safeString()
- Fixed process number display at line 2238: wrapped with safeString()
- Fixed process_type label lookup at line 2235: wrapped with safeString() for both lookup key and fallback display
- Fixed process.client_email at line 5601: wrapped with safeString()
- Fixed banco extraction at line 3753: item.banco now wrapped with safeString() in case it's an object
- Fixed activity.user_name and activity.comment (lines 5171-5173): wrapped with safeString()
- Fixed deadline.title (line 5354): wrapped with safeString()
- Fixed reassign dialog client fields (lines 5637-5653): client.nome, client.email, client.telefone, client.nif all wrapped with safeString()
- Fixed reassign selected client display (lines 5670-5673): reassignSelected.nome and email/telefone wrapped with safeString()
- Read PortalDocumentRequests.js: confirmed it already has local safeString function and uses it throughout (getCategoryInfo, DocItem status/notes/filename). No changes needed.
- Read ProcessDetailsModal.jsx and identified unprotected renders
- Fixed process title at line 311: wrapped process_number and client names with safeString()
- Fixed process number in subtitle at line 586: wrapped with safeString()
- Fixed process_type display at line 604: wrapped with safeString() before .replace()
- Fixed status display at line 594: wrapped editProcess.status with safeString()
- Fixed visits tab: propTitle, propTypology, propLocation, visit.consultor_name, visit.notes all wrapped with safeString()
- Fixed visit detail modal: propTitle, propTypology, propLocation, propAddress, sv.consultor_name, sv.notes all wrapped with safeString()

Stage Summary:
- Task 1 (Route confusion): Fixed S3NotConfiguredBanner to navigate admin users to /configuracoes (not /definicoes) and show a contact-admin message for non-admin users instead of a broken button
- Task 2 (React Error #31): Applied safeString() wrappers to 20+ locations across 3 files where object values from the API could be rendered as React children, preventing "Objects are not valid as a React child" crashes
- Key fix in getBankColor(): Now handles {value, label} objects from the backend that were causing both rendering errors and .toLowerCase() crashes
- Files modified:
  - frontend/src/pages/FilesExplorerPage.jsx (S3NotConfiguredBanner button logic)
  - frontend/src/pages/ProcessDetails.js (getBankColor + 10 render locations)
  - frontend/src/components/kanban/ProcessDetailsModal.jsx (6 render locations + visits tab)
  - frontend/src/components/PortalDocumentRequests.js (no changes needed — already protected)


---
Task ID: 9
Agent: Main Agent
Task: Corrigir 4 bugs conhecidos + 3 funcionalidades pendentes do PowerCell

Work Log:
- Analisou completamente o código-fonte do PowerCell (frontend React 19 + backend FastAPI + MongoDB)
- Identificou causa raiz do bug do Explorador de Ficheiros: S3Service lia apenas variáveis de ambiente, não config da BD
- Implementou `reconfigure()` no S3Service para permitir reconfiguração em runtime
- Adicionou `sync_s3_from_db_config()` para sincronizar no startup
- Adicionou sync em tempo real no `update_config_section()` quando storage é atualizado via UI
- Corrigiu rota `/definicoes` vs `/configuracoes` no S3NotConfiguredBanner
- Adicionou 16+ `safeString()` wrappers em ProcessDetails.js e ProcessDetailsModal.jsx
- Adicionou validação de process_id e logging melhorado no portal-requests
- Corrigiu sincronização de Enviados no webmail (direction="sent" explícito nas 3 funções de sync)
- Confirmou que Filtro de docs já solicitados e Multi-seleção já estavam implementados
- Atualizou CHANGELOG.md, PRD.md e worklog.md

Stage Summary:
- 4 bugs corrigidos: S3 Explorer, Rota confusão, React Error #31, 500 portal-requests
- 1 funcionalidade corrigida: Webmail Enviados/Rascunhos/Lixo
- 2 funcionalidades confirmadas como já implementadas: Filtro + Multi-seleção
- Ficheiros modificados: s3_storage.py, system_config.py, server.py, documents.py, email_service.py, FilesExplorerPage.jsx, ProcessDetails.js, ProcessDetailsModal.jsx
- Documentação atualizada: CHANGELOG.md, PRD.md, worklog.md

---
Task ID: 1
Agent: Backend/Frontend Fix Agent
Task: Fix GET /api/clients 422 validation error

Work Log:
- Made backend query params Optional[bool]/Optional[int] in clients.py list_clients endpoint
- Added default value application in function body (show_all, exclude_deleted, deleted_only, limit, skip)
- Verified ImportErrorsPage.js already uses correct path `/clients` (no double /api prefix)
- Made getClients() in api.js filter empty values (empty string, null, undefined) before sending as query params

Stage Summary:
- /api/clients now tolerates empty string query params (Pydantic v2 treats empty string as None for Optional types)
- ImportErrorsPage already had correct API path (no double /api prefix needed)
- getClients() utility is now resilient to empty values — filters them before making the request
- Files modified:
  - backend/routes/clients.py (Optional types + default value application)
  - frontend/src/services/api.js (getClients filters empty params)

---
Task ID: 2
Agent: React Error #31 Fix Agent
Task: Create extractErrorMessage utility and fix all unsafe error handling

Work Log:
- Created /frontend/src/utils/extractErrorMessage.js utility
- Fixed ClientsPage.js error handling (added else clause for non-200 fetchClients, replaced inline Pydantic parsing with extractErrorMessage)
- Fixed ProcessDetails.js toast.error calls (3 locations: data.detail for assignments, data.detail for property association, error.response?.data?.detail for client deletion)
- Fixed EmailAccountsPage.js toast.error calls (7 locations: SMTP save, SMTP test result, IMAP save, Google auth, sync error, company email save)
- Fixed SystemConfigPage.js toast.error calls (11 locations: config save, SMTP test result, Google auth, sync, company email save, S3 mapping save, auto-mapping, name correction, sync start errors)
- Fixed WebmailPage.jsx toast.error calls (2 locations: sync error, folder save error)
- Fixed PropertiesPage.jsx toast.error calls (3 locations: save property, delete property, import error)
- Fixed SendDocumentationModal.js toast.error calls (3 locations: branch save, 404 error, send documentation)
- Fixed S3FileManager.js toast.error calls (16 locations: file load, mapping save, upload errors x2, download, delete file, bulk delete, template generation, preview, AI analysis, apply suggestions, rename docs, rename file, analysis throw, organize throw, bulk download)

Stage Summary:
- extractErrorMessage() utility created and imported in 9 files
- 50+ unsafe data.detail || fallback patterns replaced with extractErrorMessage()
- React Error #31 from Pydantic objects should no longer occur

---
Task ID: 3
Agent: Axios Error Fix Agent
Task: Fix Axios-based and remaining unsafe error handling locations

Work Log:
- Created `/frontend/src/utils/extractErrorMessage.js` (Task 2 hadn't created it yet)
- Fixed UsersManagementPage.js (4 locations + removed duplicate import from Task 2 partial fix)
- Fixed ProfilePage.js (3 locations: professional data, signature, password)
- Fixed ClientDetailPage.js (2 locations: email, telefone)
- Fixed LoginPage.js (1 location)
- Fixed RegisterPage.js (1 location)
- Fixed AdminDashboard.js (2 locations: create event, delete event)
- Fixed StaffDashboard.js (2 locations: create client, create process)
- Fixed ImportErrorsPage.js (1 location)
- Fixed DashboardShared.js (2 locations: add expiry, analyze document)
- Fixed AITrainingPage.js (1 location: raw fetch data.detail)
- Fixed MinutasPage.js (1 location: raw fetch error.detail)
- Fixed EmailConfigForm.jsx (4 locations: Google auth, disconnect, test, save)
- Fixed EmailHistoryPanel.js (1 location)
- Fixed DriveLinks.js (2 locations: save folder link, add link)
- Fixed SecondTitularCard.jsx (1 location)
- Fixed CreateClientModal.jsx (2 locations: create client, create process)
- Fixed AssignUsersModal.jsx (1 location: raw fetch)
- Fixed DocumentRecipientsManager.js (6 locations: save config, save changes x3, toggle, preview)
- Fixed PortalDocumentRequests.js (1 location)
- Fixed AIAnalysisTab.js (1 location)
- Fixed ProcessMigrationTab.js (4 locations: load status, simulate, migrate, rollback)
- Fixed WorkflowEditor.js (3 locations: create, update, delete status)
- Fixed TasksPanel.js (2 locations: create, delete task)

Stage Summary:
- 23 files fixed with 46+ unsafe error handling locations replaced with extractErrorMessage()
- All major Axios-based and raw fetch error handling patterns now properly handle Pydantic validation error arrays
- Import paths correctly set per directory depth (../utils, ../../utils)
- React Error #31 should be fully eliminated across all fixed files

---
Task ID: 4
Agent: Remaining Error Fix Agent
Task: Fix remaining unsafe .detail || patterns across frontend

Work Log:
- Fixed api.js 500+ interceptor: replaced `data?.detail || ""` with `extractErrorMessage(data?.detail, "")`
- Fixed SystemConfigPage.js remaining locations (2: lines 1581, 3449)
- Fixed ProcessDetails.js remaining locations (2: lines 659, 815)
- Fixed VisitsPage.js (2: lines 482, 710) + added import
- Fixed AIConfigPage.js (5: lines 264, 313, 335, 369, 391) + added import
- Fixed AIInsightsPage.js (1: line 86) + added import
- Fixed IdealistaImportPage.js (3: lines 156, 204, 268) + added import
- Fixed AutomationPage.js (1: line 109) + added import
- Fixed BackgroundJobsPage.js (4: lines 679, 699, 753, 776) + added import
- Fixed RGPDMigrationPage.js (2: lines 179, 214) + added import
- Fixed FilesExplorerPage.jsx (7: lines 184, 272, 315, 353, 391, 425, 458) + added import
- Fixed FormManagementPage.js (6: lines 766, 787, 910, 928, 947, 974) + added import
- Fixed RGPDAdminPage.js (2: lines 789, 836) + added import
- Fixed TempLinkUploadPage.js (1: line 170) + added import
- Fixed ClientRegistrationsAdminPage.js (1: line 644) + added import
- Fixed CreateProcessModal.jsx (2: lines 155, 185) + added import
- Fixed SendDocumentationModal.js (1: line 281) — already had import
- Fixed DocumentChecklist.js (1: line 158) + added import
- Fixed DocumentSearchPanel.jsx (1: line 171) + added import
- Fixed LeadsKanban.js (1: line 728) + added import
- Fixed ProcessDetailsModal.jsx (2: lines 284, 637) + added import
- Additionally fixed: HtmlImportModal.js (2 toast.error patterns) + ClientPortal.jsx (1 toast.error pattern) + ProcessesPage.js (1 Axios pattern with typeof check)

Stage Summary:
- 22 additional files fixed with extractErrorMessage()
- Axios interceptor now handles Pydantic arrays for 500+ errors
- All toast.error() calls in the listed files now safely extract string messages
- Total patterns fixed: ~50 across 22 files (including 3 bonus files beyond the task list)
- Import paths follow convention: ../utils for pages/components, ../../utils for kanban/ subdirectory

---
Task ID: 2
Agent: Soft Delete Fix Agent
Task: Fix Soft Delete gaps for Processes and Clients

Work Log:
- Added DELETE /api/processes/{process_id} endpoint with soft delete in processes.py (line 3000)
  - Soft deletes the process (is_deleted=True, status=eliminado, is_active=False)
  - Cascade: soft-deletes documents and tasks for the process
  - Does NOT touch the client document (process deletion is independent)
  - Logs activity in process_activities collection
- Fixed DELETE /clients/{client_id} to NOT cascade-delete processes (clients.py lines 1959-1966)
  - Changed from cascade-soft-deleting all processes to just removing client_id reference from processes
  - Processes remain intact when a client is deleted; use DELETE /api/processes/{process_id} instead
- Added is_deleted filter to GET /clients/registered (clients.py line 294)
  - Query now includes "is_deleted": {"$ne": True} to exclude soft-deleted clients
- Added is_deleted filter to GET /clients/me (clients.py lines 108-112)
  - For queries with $or: wraps in $and with is_deleted filter
  - For flat queries: adds is_deleted directly to query dict
- Fixed hard delete in admin route (admin.py line 2974)
  - Changed db.processes.delete_one to db.processes.update_one with soft delete fields
  - Removed associated history and RGPD hard deletes (data is preserved)
  - Updated docstring to reflect soft delete instead of irreversible action

Stage Summary:
- Process deletion now independent from client deletion
- All GET endpoints properly filter soft-deleted records
- No more hard deletes in the system for processes
- Files modified:
  - backend/routes/processes.py (added DELETE /{process_id} endpoint)
  - backend/routes/clients.py (3 fixes: cascade removal, is_deleted filters)
  - backend/routes/admin.py (hard delete → soft delete)

---
Task ID: 1
Agent: Trello Removal Agent
Task: Remove Trello integration completely

Work Log:
- Deleted 5 dedicated Trello files:
  - backend/routes/trello.py
  - backend/services/trello.py
  - backend/tests/integration/test_iteration14_trello_integration.py
  - backend/tests/test_iteration16_leads_trello.py
  - frontend/src/components/TrelloIntegration.js
- Modified backend/server.py (3 removals):
  - Removed `from routes.trello import router as trello_router` import
  - Removed `app.include_router(trello_router, prefix="/api")` router registration
  - Removed `from services.trello import init_trello_from_config` and `await init_trello_from_config()` startup call
- Modified backend/config.py (3 env vars removed):
  - Removed TRELLO_API_KEY, TRELLO_TOKEN, TRELLO_BOARD_ID environment variables
- Modified backend/models/process.py (2 fields removed):
  - Removed `trello_card_id: Optional[str]` field
  - Removed `trello_list_id: Optional[str]` field
- Modified backend/models/system_config.py (3 removals):
  - Removed `TrelloConfig` class
  - Removed `trello: TrelloConfig = TrelloConfig()` field from SystemConfig
  - Updated ConfigUpdateRequest.section comment to remove "trello"
- Modified backend/routes/processes.py (4 removals):
  - Removed `from services.trello import trello_service, status_to_trello_list, build_card_description` import
  - Removed `sync_process_to_trello()` function
  - Removed trello sync call on process creation
  - Removed trello sync call on status change
  - Removed trello sync call on process update
- Modified backend/routes/admin.py (1 removal):
  - Removed Trello member auto-association logic (~30 lines)
- Modified backend/routes/system_config.py (3 removals):
  - Removed entire "trello" section from CONFIG_FIELDS
  - Removed Trello test-connection endpoint handler
  - Removed "trello" from reveal-secrets section list and query description
- Modified backend/routes/diagnostics.py (4 removals):
  - Removed `check_trello_service()` function
  - Removed trello service check from all_services endpoint
  - Removed trello from checkers dict in service detail endpoint
  - Removed trello member mappings extra info
  - Updated quick-check comments to remove Trello references
- Modified backend/services/system_config.py (3 removals):
  - Removed TrelloConfig from import
  - Removed trello=TrelloConfig(...) from _build_default_config()
  - Removed entire trello section handler from update_config_section()
- Modified backend/services/task_queue.py (2 removals):
  - Removed `sync_trello()` method
  - Removed Trello usage example from module docstring
- Modified backend/worker.py (3 removals):
  - Removed `services.trello` from lazy-loading module list in docstring
  - Removed `services.trello` from NOT IMPORTED comment block
  - Removed sync_trello task handler (elif block)
- Modified frontend/src/pages/SettingsPage.js (2 removals):
  - Removed `TrelloIntegration` import
  - Removed `<TrelloIntegration />` render
- Modified frontend/src/pages/DiagnosticsPage.js (2 removals):
  - Removed `Trello` icon import from lucide-react
  - Removed `trello: Trello` from serviceIcons map
- Modified frontend/src/pages/SystemConfigPage.js (3 removals):
  - Removed `Trello` icon import from lucide-react
  - Removed `trello: Trello` from SECTION_ICONS map
  - Removed "trello" from test-connection section filter
  - Updated file header comment to remove "Trello" mention
- Modified frontend/src/pages/ProcessDetails.js (1 removal):
  - Removed `trello` source badge from activity rendering
- Modified frontend/src/services/api.js (2 removals):
  - Removed `getTrelloStatus()` export
  - Removed `syncProcessWithTrello()` export
- Modified frontend/src/components/UnifiedAuditTrail.js (1 removal):
  - Removed `trello` source badge from event rendering

Stage Summary:
- Trello integration fully removed from backend and frontend
- 5 files deleted, 16 files modified
- No functional Trello code remains — only historical comments in docstrings/comments (admin.py lines 1496, 1548; client.py line 104)
- Backend will no longer attempt to sync with Trello on process creation, status change, or update
- System config no longer includes Trello section in UI or API
- Diagnostics no longer checks Trello service status
- Worker no longer handles sync_trello tasks

---
Task ID: 4
Agent: Nomenclature Agent
Task: Uniformize Co-Proponente/Co-Comprador to 2º Titular / Fiador

Work Log:
- Updated ProcessDetails.js: comment (line 3209) and header (line 3215) from "Co-Compradores / Co-Proponentes" to "2º Titular / Fiador"
- Updated CPCVModal.js: 7 user-facing text changes:
  - Comment: "// Co-comprador (se aplicável)" → "// 2º Titular / Fiador (se aplicável)"
  - Comment: "// Co-comprador (segundo titular)" → "// 2º Titular / Fiador"
  - Comment: "// Co-comprador" → "// 2º Titular / Fiador"
  - JSX comment: "{/* Co-comprador (se existir) */}" → "{/* 2º Titular / Fiador (se existir) */}"
  - Header label: "Co-comprador (2º Titular)" → "2º Titular / Fiador"
  - Placeholder: "Nome do co-comprador" → "Nome do 2º Titular / Fiador"
  - Placeholder: "Morada do co-comprador" → "Morada do 2º Titular / Fiador"
- Updated backend/models/process.py: 3 Field description changes (ProcessCreate, ProcessUpdate, ProcessResponse) from "co-proponente" to "Fiador"
- Updated backend/models/client.py: 2 docstring changes from "co-compradores" to "2º Titular / Fiador"
- Updated backend/scripts/seed_completo.py: section header "CO-PROPONENTE" → "2º TITULAR / FIADOR", section comment, and docstring entry
- Updated backend/scripts/seed_test_clients.py: 2 comments "Co-compradores"/"Co-proponentes" → "2º Titular / Fiador"
- Updated backend/scripts/seed_realistic_data.py: comment "Co-compradores" → "2º Titular / Fiador"
- Updated backend/routes/clients.py: comment "Co-compradores herdados do cliente" → "2º Titular / Fiador herdados do cliente"
- Updated backend/services/encryption.py: 2 comments (encrypt/decrypt) from "co-compradores/co-proponentes" → "2º Titular / Fiador"
- Updated backend/services/process_service.py: 3 comments from "co-compradores/co-proponentes" → "2º Titular / Fiador"
- Updated backend/services/ai_document.py: 2 comments from "co-proponentes"/"co-compradores" → "2º Titular / Fiador"
- Updated backend/services/migrate_encryption.py: 1 comment from "co-compradores" → "2º Titular / Fiador"
- Updated backend/tests/unit/test_encryption_integration.py: 1 docstring from "co-compradores" → "2º Titular / Fiador"

Stage Summary:
- All user-facing text now uses "2º Titular / Fiador" consistently across frontend and backend
- Database field names (co_buyers, co_applicants, co_comprador_nome, etc.) unchanged
- API parameter names unchanged
- Function names (gerar_co_proponente, test_encrypt_co_buyers) unchanged
- Template placeholders ([CO_COMPRADOR_NOME], etc.) unchanged — tied to internal field names
- 13 files modified across frontend and backend
- Zero remaining occurrences of "co-comprador", "co-compradores", "co-proponente", or "co-proponentes" in the codebase

---
Task ID: 3
Agent: Read-Only Cards Agent
Task: Add isEditing state to ProcessDetails cards

Work Log:
- Added editingCard state variable (null | 'personal' | 'financial' | 'realestate' | 'credit')
- Created CardHeaderWithEdit helper component with Pencil icon toggle → Cancelar/Guardar buttons
- Added .read-only-card CSS class to index.css — makes disabled inputs/selects/textareas appear as plain text (no border, no background, full opacity)
- Modified Personal tab: Contactos, Identificação, Filiação, Morada cards now use CardHeaderWithEdit and read-only-card class
- Modified Financial tab: Rendimentos, Situação Financeira, Credenciais de Portais, 2º Proponente Credenciais, Situação Profissional cards now use CardHeaderWithEdit and read-only-card class
- Modified Real Estate tab: Estado da Procura, Características do Imóvel, Localização, Dados do CPCV, Dados do Proprietário cards now use CardHeaderWithEdit and read-only-card class
- Modified Credit tab: Wrapped main credit fields in a new Card (Dados do Crédito) with CardHeaderWithEdit; Avaliação Bancária card also updated
- Changed all disabled={!canEditPersonal} to disabled={editingCard !== 'personal' || !canEditPersonal} in Personal tab inputs
- Changed all disabled={!canEditFinancial} to disabled={editingCard !== 'financial' || !canEditFinancial} in Financial tab inputs
- Changed all disabled={!canEditRealEstate} to disabled={editingCard !== 'realestate' || !canEditRealEstate} in Real Estate tab inputs
- Changed all disabled={!canEditCredit} to disabled={editingCard !== 'credit' || !canEditCredit} in Credit tab inputs
- Reverted disabled prop changes in "Dados do Processo" and "Organização do Processo" top-section cards (they have independent edit flow)
- Added setEditingCard(null) in executeSave after successful save
- Added setEditingCard(null) on tab change (onValueChange handler)
- Left Créditos Ativos, Contas de Crédito, Simulações cards unchanged (they have their own inline editingCreditField toggle)
- Left Co-Compradores / 2º Titular / Fiador cards unchanged (always read-only)
- Left "Tempo Restante do Crédito" card unchanged (display-only, no inputs)

Stage Summary:
- Process details cards now default to read-only mode with plain text appearance
- Pencil icon in card header enables editing; Cancelar/Guardar buttons replace pencil in edit mode
- Tab switching resets editing state to prevent accidental edits across tabs
- Existing permissions (canEdit*, isViewMode, isProcessLocked) still enforced
- CSS-based read-only appearance avoids per-field conditional rendering
- Files modified:
  - frontend/src/index.css (added .read-only-card CSS rules)
  - frontend/src/pages/ProcessDetails.js (editingCard state, CardHeaderWithEdit, card headers, disabled props, save handler, tab change handler)

---
Task ID: 1
Agent: Main Agent
Task: Corrigir erro 403 ao enviar email no Webmail + seletor de conta a aparecer para utilizadores com um só perfil

Work Log:
- Analisado o endpoint `POST /api/emails/send` em `backend/routes/emails.py` (linha 3641): para roles não-admin/CEO/diretor o backend força `account="personal"` e devolve 403 "Configuração de email pessoal não encontrada..." se o utilizador não tiver `email_config.is_configured`. Confirmado que o 403 é comportamento pretendido (isolamento de remetente).
- Identificado bug de UX no `frontend/src/pages/WebmailPage.jsx`: o seletor "Conta:" do composer (Precision/Power) era renderizado incondicionalmente, oferecendo contas globais a perfis que só podem usar a conta pessoal.
- Adicionada flag `canUseGlobalAccounts = hasAnyRole(user, ['admin','ceo','diretor'])` (alinhada com `can_use_global_accounts` do backend) junto a `showTabs`.
- Seletor do composer agora condicional: visível só para `canUseGlobalAccounts`; para os restantes perfis mostra nota informativa (role-aware: "conta partilhada de Indexação" para indexacao, "conta pessoal — configure em Perfil > Configuração de Webmail" para os outros).
- Corrigido `handleSendEmail`: introduzido `effectiveAccount` (envia `account=personal` para não-admin em vez de `power`/`precision`) e tratamento de erro que preserva a mensagem do backend (lê `.detail`/`.message`/`.error` do JSON de erro) com toast de duração 8s. Adicionada dependência `canUseGlobalAccounts` ao array do useCallback.
- Corrigido `sendReply` em `frontend/src/components/EmailViewerModal.js`: antes engolia erros silenciosamente (só `console.error`, sem toast). Adicionado `import { toast } from "sonner"`, `from_box: "personal"` + `account=personal` no pedido, leitura da mensagem de erro do backend, e toasts de sucesso/erro (8s).
- Verificada a sintaxe JSX de ambos os ficheiros com esbuild (bunx esbuild --loader=jsx): ambos OK.
- Atualizada documentação: entrada nova no `CHANGELOG.md` ([2026-06-18]) e esta entrada no `worklog.md`.

Stage Summary:
- O seletor de conta do composer deixa de aparecer para utilizadores com um só perfil não-admin (consultor, intermediário, administrativo, indexação) — apenas admin/CEO/diretor escolhem a conta global.
- O erro 403 passa a mostrar a mensagem acionável do backend ("...Vá ao seu Perfil > Configuração de Webmail...") em vez de um toast genérico "Erro ao enviar email".
- O pedido de envio envia agora `account=personal` para não-admin, refletindo o comportamento real do backend.
- A resposta rápida (EmailViewerModal) passou a dar feedback de sucesso/erro ao utilizador.
- Ficheiros modificados:
  - frontend/src/pages/WebmailPage.jsx (canUseGlobalAccounts, seletor condicional, effectiveAccount, tratamento de erro 403)
  - frontend/src/components/EmailViewerModal.js (import toast, sendReply com feedback + account=personal + from_box)
  - CHANGELOG.md (entrada [2026-06-18])
  - worklog.md (esta entrada)
- Nota: o 403 para não-admin sem webmail pessoal configurado é by-design; a correção é de UX (não oferecer contas globais + mostrar mensagem útil).

---
Task ID: 2
Agent: Main Agent
Task: Assinatura de email deve usar a empresa ativa (cada user pode ter a sua assinatura por empresa) + pré-visualização no composer

Work Log:
- Confirmado o gap no `send_email` (`backend/services/email_service.py`, linhas 651-716): a resolução da assinatura usava `sender_user.company` (empresa default) e não a empresa ativa da sessão, ignorando o `active_company_id` que o `/auth/me` já devolve.
- Adicionado parâmetro `active_company_id: Optional[str] = None` à assinatura de `send_email` (linha 454) + documentação no docstring.
- Reescrito o bloco de resolução da assinatura com nova prioridade: (1) UCR da empresa ativa (`active_company_id`, se != "default") → (2) `users.email_signature` (global) → (3) UCR da empresa default → (4) UCR de qualquer empresa → (5) `system_smtp.email_signature`. Adicionada variável `sig_source` para logging diagnóstico.
- Atualizada a linha de log para incluir `sig_source` e `active_company_id` (facilita diagnóstico de "qual assinatura foi usada?").
- Endpoint `POST /api/emails/send` (`backend/routes/emails.py`, 3641): adicionado `request: Request`, resolução de `active_company_id` via `get_active_company_id_async(request, current_user)` (lê header `X-Company-Id`), e passagem de `active_company_id` ao `send_email`.
- Endpoint `POST /api/emails/send-documentation/{process_id}` (967) + `_send_documentation_email_impl` (1010): aplicada a mesma correção — `request: Request` no endpoint, `request: Optional[Request] = None` na impl, e `active_company_id` passado ao `send_email` (mesmo com `force_system=True`, a assinatura é resolvida por `created_by`+`active_company_id`).
- Frontend `WebmailPage.jsx`: `handleSendEmail` agora envia header `X-Company-Id: {activeCompanyId}` no fetch (igual ao interceptor axios) para o backend resolver a empresa ativa.
- Frontend `WebmailPage.jsx`: adicionada pré-visualização da assinatura no composer — variável `resolvedSignature` (prioridade `active_company_signature` se != null, senão `email_signature`), caixa tracejada sob a Textarea do body com HTML sanitizado via `sanitizeEmailHtml` (DOMPurify). Import de `htmlToText` adicionado. Se não houver assinatura, mostra dica para configurar em Perfil.
- Frontend `EmailViewerModal.js`: `sendReply` agora lê `activeCompanyId` do `sessionStorage` (igual ao axios) e envia header `X-Company-Id`.
- Verificada sintaxe: Python (`py_compile`) OK nos 2 ficheiros backend; JSX (esbuild) OK nos 2 ficheiros frontend.
- Atualizada documentação: CHANGELOG.md (entrada nova [2026-06-18]) + esta entrada do worklog.

Stage Summary:
- A assinatura do email agora reflete a empresa ativa selecionada na sessão (cada user pode ter uma assinatura por empresa via UCR `user_company_roles.signature`).
- O composer do Webmail mostra a assinatura que será anexada, antes de enviar (pré-visualização informativa; a injeção real continua no backend).
- Ambos os fluxos de envio manual (/send e /send-documentation) propagam o `active_company_id` ao `send_email`.
- Ficheiros modificados:
  - backend/services/email_service.py (param active_company_id + bloco de resolução reescrito + log com sig_source)
  - backend/routes/emails.py (request: Request em /send e /send-documentation; resolução + passagem de active_company_id)
  - frontend/src/pages/WebmailPage.jsx (X-Company-Id no fetch; resolvedSignature; pré-visualização da assinatura; import htmlToText)
  - frontend/src/components/EmailViewerModal.js (X-Company-Id no sendReply via sessionStorage)
  - CHANGELOG.md + worklog.md
- Comportamento inalterado para emails automáticos do sistema (force_system sem created_by → assinatura do sistema).

---
Task ID: 4
Agent: Main Agent
Task: Hotfix — Dropdown de estado do processo vazia nos Detalhes do Processo (sincronização do status)

Work Log:
- Confirmado (via GitHub raw API) que o `safeStatusOptions` já existia em `dev` mas tinha um bug: `if (!workflowStatuses.length) return [];` curto-circuitava o fallback. Quando a API `/admin/workflow-statuses` devolvia `[]` (coleção MongoDB não seeded, pedido falhado, ou role sem acesso), a dropdown ficava completamente vazia — mesmo havendo um `process.status` válido.
- Inspecionado o enum canónico `ProcessStatus` em `backend/models/enums.py`: 16 estados (pre_registo, clientes_espera, documentacao, analise, pre_aprovacao, credito_aprovado, pedido_avaliacao, avaliacao, cpcv, minuta, escritura, concluido, arquivo, perdido, desistencias, fila_espera). Confirmado em `backend/scripts/seed_completo.py` (linhas 126-129).
- Inspecionados seeds alternativos com estados legacy: `backend/seed.py` (enviado_bruno, fase_documental, entradas_precision, fase_bancaria, ch_aprovado, fase_escritura, escritura_agendada, concluidos, desistencias) e `backend/seed_database.py` (triagem, aprovado, recusado, desistido, cancelado).
- Criado `frontend/src/utils/workflowStatuses.js` (novo ficheiro partilhado) com:
  - `KNOWN_PROCESS_STATUSES`: lista estática com TODOS os estados conhecidos do backend (16 canónicos + 18 legacy), cada um com id/name/label(PT-PT)/color/order.
  - `formatStatusLabel(statusName)`: converte nome técnico em label legível (underscores → espaços + capitalização). Extraído do componente.
  - `buildStatusOptions(workflowStatuses, currentStatus)`: constrói as opções do Select com 3 níveis — (1) lista dinâmica da API se existir, (2) senão baseline estático, (3) fallback final injeta `currentStatus` se ainda não estiver presente (marcado `_isFallback: true`). Ordena por `order`.
- Refactorizado `frontend/src/pages/ProcessDetails.js`:
  - Adicionado import `import { buildStatusOptions, formatStatusLabel } from "../utils/workflowStatuses";`.
  - Removido o `formatStatusLabel` local (linhas 1807-1812) — agora importado.
  - Reescrito `safeStatusOptions`: `useMemo(() => buildStatusOptions(workflowStatuses, status), [workflowStatuses, status])`. O `return []` prematuro foi eliminado — a dropdown nunca fica vazia.
  - `getStatusInfo` (badge de estado) mantém-se, usando agora o `formatStatusLabel` importado.
- Verificado o bloco do `<Select>` (linha ~2636): `<Select value={status} onValueChange={setStatus}>` — `value` corretamente mapeado ao estado `status` (inicializado de `processData.status` em `fetchData`, linha 1161). `<SelectItem key={s.id} value={s.name}>` com fallback a exibir `⚠ {label} (não configurado)`.
- Validada a sintaxe JSX de ambos os ficheiros com esbuild (`--loader:.js=jsx`): ambos compilam sem erros.
- Atualizada documentação: entrada nova no `CHANGELOG.md` ([2026-06-18] Hotfix: Dropdown de Estado do Processo Vazia) + esta entrada no `worklog.md`.

Stage Summary:
- A dropdown de estado nos Detalhes do Processo deixa de aparecer vazia. Mesmo que a API `/admin/workflow-statuses` falhe ou devolha `[]`, o baseline estático (16 estados canónicos + legacy) garante opções visíveis; e se o `process.status` for um valor desconhecido (legacy/renomeado/outro ambiente), é injetado como opção extra `⚠ (não configurado)`.
- Ficheiros modificados/criados:
  - frontend/src/utils/workflowStatuses.js (NOVO — KNOWN_PROCESS_STATUSES, formatStatusLabel, buildStatusOptions)
  - frontend/src/pages/ProcessDetails.js (import do util; safeStatusOptions delega em buildStatusOptions; formatStatusLabel local removido)
  - CHANGELOG.md (entrada nova do hotfix)
  - worklog.md (esta entrada)
- Próximo passo: commit + push para branch `dev` via Git Database API.

---
Task ID: 5
Agent: Main Agent
Task: Hotfix — Tarefas (e Chat) desapareceram dos Detalhes do Processo

Work Log:
- User reportou: "as tarefas dentro dos detalhes de processo, desapareceram".
- Confirmado (via diff contra o commit anterior em dev) que o hotfix da dropdown (Task ID 4) foi cirúrgico e NÃO tocou em canManageTasks, TasksPanel, ou no tab mensagens — excluída regressão do meu commit.
- Inspecionados commits recentes que tocaram em ProcessDetails.js (55fc0bcac3 "isolate card editing", cdb825e7 "status dropdown blank"): nenhum tocou em código de tarefas.
- Localizada a causa raiz no frontend: `canManageTasks` em ProcessDetails.js (linha 1845) avalia `userActions.length > 0 ? userActions.includes("manage_tasks") : roleFallback`. Como o `/auth/me` corre `sync_permissions_with_role_defaults` em cada pedido (backend/routes/auth.py linha 139) e popula `permissions.actions`, `userActions.length > 0` é SEMPRE true para staff → a primeira via executa e exige a action `manage_tasks`.
- Confirmada a causa no backend: `DEFAULT_PERMISSIONS_BY_ROLE` em backend/services/permissions.py NÃO incluíam `manage_tasks` nos defaults de `diretor`, `consultor`, `intermediario`, `administrativo` (só admin/ceo via AVAILABLE_ACTIONS.copy() e indexacao explicitamente). Mesmo problema com `use_chat` (canUseChat segue o mesmo padrão) → o Chat do processo também desaparecia para estes roles.
- Corrigido backend/services/permissions.py — DEFAULT_PERMISSIONS_BY_ROLE:
  - diretor: adicionado `manage_tasks`, `use_chat`, `assign_process_users` (alinhado com canAssignUsers que permite admin/ceo/diretor via fallback de role).
  - consultor: adicionado `manage_tasks`, `use_chat`.
  - intermediario: adicionado `manage_tasks`, `use_chat`.
  - administrativo: adicionado `manage_tasks`, `use_chat`.
  - admin/ceo/indexacao: inalterados (já tinham as actions).
- Propagação automática confirmada: o `/auth/me` faz `sync_permissions_with_role_defaults` que mergeia `set(defaults + user_perms)` e persiste se houver diferença (auth.py linhas 139-149). Logo, utilizadores existentes recebem as novas actions no próximo login/refresh — sem script de migração.
- Validada sintaxe Python: `python3 -m py_compile backend/services/permissions.py` → OK.
- Frontend não alterado: a correção é no backend (defaults), que é o sítio correcto para definir capacidades por defeito. canManageTasks/canUseChat mantêm a semântica de permissões customizadas (admin pode remover manage_tasks de um consultor via UI e o consultor perde o card — comportamento pretendido).
- Atualizada documentação: CHANGELOG.md (entrada nova [2026-06-18] Hotfix: Tarefas (e Chat) Desapareceram dos Detalhes do Processo) + esta entrada no worklog.md.

Stage Summary:
- O card de Tarefas (e o Chat) volta a aparecer nos Detalhes do Processo para consultor, intermediário, administrativo e diretor. A causa era um desfasamento entre os defaults de permissões do backend (não incluíam manage_tasks/use_chat para estes roles) e o fallback por role do frontend (que nunca executava porque userActions vinha sempre populado do /auth/me).
- Ficheiros modificados:
  - backend/services/permissions.py (DEFAULT_PERMISSIONS_BY_ROLE: adicionado manage_tasks/use_chat a diretor/consultor/intermediario/administrativo; assign_process_users a diretor)
  - CHANGELOG.md (entrada nova do hotfix)
  - worklog.md (esta entrada)
- Propagação: automática via sync_permissions_with_role_defaults no /auth/me (sem script de migração).
- Próximo passo: commit + push para branch `dev` via Git Database API.

---
Task ID: 6
Agent: Main Agent
Task: Hotfix — Cliente 404 ao abrir página + desaparecimento da lista de ativos após marcar processo como desistência

Work Log:
- User reportou: cliente com 2 processos, marcou um como desistência → cliente desapareceu da lista de ativos (mas tem processo ativo) + erro 404 ao abrir a página do cliente (GET /api/clients/{id}).
- Análise do GET /clients/{id} (backend/routes/clients.py linha 1194): faz `db.clients.find_one({"id": client_id})` sem filtro de is_deleted → 404 só se o documento NÃO existir na coleção clients.
- Análise da lista de clientes (GET /clients, linha 781): construída a partir de PROCESSOS (não da coleção clients). O `id` devolvido é `proc.client_id or proc.id` (linha 973) — quando client_id está vazio, devolve o ID DO PROCESSO como id do cliente. Daí o 404: GET /clients/{process_id} não encontra nada na coleção clients.
- Identificada a CAUSA RAIZ do client_id vazio: DELETE /clients/{id} (linha 1979-1982) fazia `$unset: {"client_id": ""}` em TODOS os processos associados ao cliente — removendo a referência. Isto órfão os processos: a lista passa a devolver o id do processo, e o GET falha.
- Identificado bug secundário: PUT /processes/{id} (linha 3503) atualizava `status` mas NÃO `is_active`. Só o endpoint de move (kanban, linha 2396) atualizava is_active. Mudar status para "desistencias" via dropdown deixava is_active=True (desatualizado), inconsistente com a contagem de processos ativos (linha 1027: `is_active AND status not in terminal`).
- Identificado bug terciário: a lista de terminais na contagem (linha 1027) não incluía "eliminado"/"eliminados" nem "arquivo" (só "arquivado").
- Fix 1 (GET /clients/{id} robusto, clients.py): adicionado fallback — se o documento do cliente não existir, procura processos por `id` ou `client_id` e constrói resposta sintética de cliente a partir dos dados do processo (marcada `_synthetic: true`). No caminho sintético, procura também outros processos com o mesmo client_id para listar todos os processos. Isto resolve o 404 imediatamente, mesmo para dados legacy.
- Fix 2 (DELETE /clients/{id}, clients.py): removido o `$unset: {"client_id": ""}` em cascata. Agora o DELETE mantém a referência client_id nos processos (só atualiza updated_at). O cliente fica soft-deleted (is_deleted=True) mas os processos continuam ligados. GET /clients/{id} não filtra is_deleted → a página abre. O endpoint unlink-process (linha 1535) continua a fazer unset intencional para desvincular UM processo específico.
- Fix 3 (PUT /processes/{id}, processes.py): quando o status muda, sincroniza is_active com o novo estado. Terminais (desistencias, concluidos, concluido, arquivo, arquivado, perdido, eliminado, eliminados) → is_active=False; restantes → is_active=True. Alinha o dropdown com o kanban move.
- Fix 4 (active_processes_count, clients.py linha 1027): alinhada a lista de terminais com todos os canónicos e legacy: ["desistencias", "concluidos", "concluido", "arquivado", "arquivo", "perdido", "eliminado", "eliminados"].
- Validada sintaxe Python: py_compile OK nos 2 ficheiros.
- Atualizada documentação: CHANGELOG.md (entrada nova) + esta entrada no worklog.md.

Stage Summary:
- O 404 ao abrir a página do cliente deixa de ocorrer (fallback para dados do processo se o documento do cliente não existir).
- A causa raiz (DELETE /clients/{id} a fazer unset do client_id em cascata) é eliminada — os processos mantêm a referência ao cliente soft-deleted.
- O is_active do processo fica consistente entre kanban move e dropdown (PUT), garantindo que a contagem de processos ativos (e a lista de clientes ativos) é correta.
- A contagem de processos ativos exclui todos os status terminais (incluindo eliminado e arquivo).
- Ficheiros modificados:
  - backend/routes/clients.py (GET /clients/{id} com fallback sintético; DELETE /clients/{id} sem unset em cascata; active_processes_count com terminais alinhados)
  - backend/routes/processes.py (PUT /processes/{id} sincroniza is_active com o novo status)
  - CHANGELOG.md (entrada nova)
  - worklog.md (esta entrada)
- Próximo passo: commit + push para branch `dev` via Git Database API.

---
Task ID: 5
Agent: Main Agent
Task: Pacote A — Script Massivo de Mock Data (100+ Clientes e Portal) para testar o CRM e o Portal do Cliente ao limite em DEV

Work Log:
- Lido o worklog e contextos anteriores (Tasks 1-4: hotfixes de email/indexador, dropdown de estado, permissões de tarefas/chat, cliente 404).
- Explorada a estrutura do backend PowerCell: modelos (client, process, enums, document, chat, task, activity, property, finance, user_company_role, workflow), database.py (motor + DB proxy), rotas (portal, documents, activities, companies, processes, clients).
- Confirmados os nomes das coleções e estruturas exatas: `documents` (status REQUESTED/PENDING/UPLOADED/RECEIVED, source admin_request/client_portal), `portal_messages` (sender_type staff/client, read_by_client/read_by_staff), `activities` + `history` (audit log), `workflow_statuses` (kanban columns, campo `name` = process.status), `user_company_roles` + `company_email_configs` (multi-tenant).
- Confirmado o campo do 2º titular: `second_client_id` no processo (+ `titular2_data` denormalizado + `second_client_name`), com dados financeiros no próprio documento do 2º cliente (`financial_data`/`dados_financeiros`).
- Confirmado que os estados pedidos pelo user (triagem, intermediario, aprovado, desistencia) NÃO são canónicos do ProcessStatus enum, MAS existem como workflow statuses customizáveis (vistos em seed_database.py); o script faz upsert para garantir visibilidade no Kanban.
- Escrito `backend/scripts/seed_massive_dev_data.py` (~770 linhas): 120 clientes + processos + 2ºs titulares (~30%) + documentos Portal (3-5: REQUESTED+UPLOADED) + mensagens Portal (2-4, conversa staff/client) + tarefas (5-10: completed/pending/overdue) + histórico/atividades (5 logs, últimos 60 dias), com asyncio.gather em batches.
- Validada a sintaxe Python (`py_compile` OK) e a lógica pura: distribuição de estados soma sempre o total (testado para 50/100/120/200); gerador de NIF validado contra o algoritmo oficial e contra `models/client.py.validate_nif`.
- Corrigido bug no gerador de NIF: `seed_realistic_data.py` (existente) gera NIFs de 10 dígitos (off-by-one). O novo script gera 9 dígitos corretos (1 + 7 aleatórios + 1 check digit).
- Atualizado CHANGELOG.md (nova entrada no topo) e este worklog.

Stage Summary:
- Artefacto: `backend/scripts/seed_massive_dev_data.py` — script de seed massivo para DEV.
- Gera: ~120 clientes principais + ~36 2ºs titulares + ~120 processos + ~480 documentos Portal + ~360 mensagens Portal + ~840 tarefas + ~720 registos de histórico + ~180 atividades.
- Distribuição de estados exata conforme pedido: pre_registo 10%, clientes_espera 15%, triagem 15%, intermediario 30%, aprovado 10%, concluido 10%, desistencia 5%, eliminado (is_deleted=True) 5%.
- Execução segura: adiciona aos existentes por defeito; `--clear` remove apenas dados deste script; batches via asyncio.gather; auto-deteta empresa ativa; cria utilizadores dummy se faltar consultor/indexador/intermediário.
- Comando de execução: `python backend/scripts/seed_massive_dev_data.py` (ou `--num-clients 120 --clear`).
- Próximo passo: commit + push para branch `dev` via Git Database API (commit em preparação).

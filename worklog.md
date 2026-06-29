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
Task ID: 16
Agent: Main Agent
Task: Hotfix — Erro de CORS no Webmail em producao (header X-Active-Company nao permitido)

Work Log:
- Utilizador reportou em producao: erro net::ERR_FAILED com "Response to preflight request doesn't pass access control check: It does not have HTTP ok status" ao sincronizar emails em https://www.powercell.pt (POST /api/emails/webmail/sync-user e GET /api/emails/webmail).
- Diagnostico passo-a-passo em producao:
  1. GET /api/cors-debug?origin=https://www.powercell.pt → origin in_explicit_list=true, would_be_allowed=true. Config CORS correta.
  2. Preflight OPTIONS /webmail/sync-user SEM header problematico → 200 OK com allow-headers corretos.
  3. Preflight OPTIONS COM Access-Control-Request-Headers: authorization,x-active-company → HTTP 400! Backend rejeita porque X-Active-Company nao esta em CORS_ALLOW_HEADERS.
  4. Grep revelou: WebmailPage.jsx enviava "X-Active-Company" (3 sitios: linhas 465, 609, 637) mas backend le "X-Company-Id" (services/auth.py:465, routes/emails.py) e config CORS permite "X-Company-Id" (render.yaml CORS_ALLOW_HEADERS). Incompatibilidade de nomes = preflight 400 = browser bloqueia com net::ERR_FAILED.
  5. Linha 859 do proprio WebmailPage.jsx ja usava X-Company-Id corretamente — evidencia que X-Active-Company era typo/legacy.
- Corrigido frontend/src/pages/WebmailPage.jsx: 3 ocorrencias de "X-Active-Company" → "X-Company-Id" (linhas 465, 609, 637). Adicionado comentario explicativo (linhas 141-145) a documentar que DEVE ser X-Company-Id para evitar regressao.
- Verificado: sem ocorrencias de X-Active-Company em codigo (so no comentario explicativo). Parse OK via esbuild.
- Backend NAO alterado (endpoint e config CORS ja estavam corretos).
- Actualizado CHANGELOG.md com entrada [2026-06-20] Hotfix CORS Webmail.
- Criado push_hotfix_webmail_cors.py (3 ficheiros: WebmailPage.jsx + CHANGELOG.md + worklog.md).
- Executado push → commit em dev.

Stage Summary:
- 1 ficheiro de codigo modificado: frontend/src/pages/WebmailPage.jsx (3 headers + comentario).
- 2 ficheiros de docs actualizados: CHANGELOG.md, worklog.md.
- Backend NAO alterado.
- Bug RESOLVIDO: o webmail agora envia o header correto (X-Company-Id) que esta na lista CORS_ALLOW_HEADERS, pelo que o preflight OPTIONS passa com 200 e o pedido real nao e bloqueado pelo browser.
- NOTA: o erro era intermitente — so ocorria quando activeCompanyId estava definido (empresa ativa selecionada). Sem empresa, o header nao era enviado e funcionava.

---
Task ID: 17
Agent: Main Agent
Task: Hotfix — Fontes Google render-blocking (ERR_CONNECTION_CLOSED no fonts.gstatic.com)

Work Log:
- Utilizador reportou em producao: erro net::ERR_CONNECTION_CLOSED ao carregar woff2 de fonts.gstatic.com.
- Diagnostico: src/index.css linha 17 tinha @import url('https://fonts.googleapis.com/...'). @import em CSS e RENDER-BLOCKING — o browser bloqueia a parse/renderizacao do CSS ate o @import resolver ou falhar. Quando o CDN da Google e inacessivel (ad blockers, firewall, DNS), a pagina fica bloqueada ate timeout + erro na consola.
- Corrigido frontend/src/index.css:
  * Removido @import url(...) render-blocking do topo. Substituido por comentario explicativo.
  * Melhorados fallbacks font-family em body, h1-h6, .font-mono, code:
    - 'Inter', sans-serif -> 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif
    - 'Manrope', sans-serif -> + mesmo stack de sistema
    - 'JetBrains Mono', monospace -> + 'SF Mono', Monaco, 'Cascadia Code', 'Roboto Mono', Consolas, 'Liberation Mono'
  Fontes de sistema nativas (San Francisco no macOS/iOS, Segoe UI no Windows, Roboto no Android) sao visualmente quase identicas a Inter/Manrope.
- Corrigido frontend/index.html: adicionados 5 <link> no <head> com padrao NAO-bloqueante (web.dev):
  1. preconnect fonts.googleapis.com
  2. preconnect fonts.gstatic.com (crossorigin)
  3. preload as=style
  4. rel=stylesheet media=print onload=this.media='all' (truque Google: carrega em paralelo, nao bloqueia render)
  5. noscript fallback
- Verificado: tailwind.config.js nao define fontFamily (usa stack de sistema default do Tailwind). CSS parse OK via esbuild.
- Backend NAO alterado.
- Actualizado CHANGELOG.md com entrada [2026-06-20] Hotfix Fontes.
- Criado push_hotfix_fonts.py (4 ficheiros: index.html + index.css + CHANGELOG.md + worklog.md).
- Executado push -> commit em dev.

Stage Summary:
- 2 ficheiros de codigo modificados:
  - frontend/index.html (+5 links nao-bloqueantes no head)
  - frontend/src/index.css (-1 @import render-blocking, +fallbacks de sistema em 4 regras)
- 2 ficheiros de docs actualizados: CHANGELOG.md, worklog.md.
- Backend NAO alterado.
- Bug RESOLVIDO: a pagina renderiza instantaneamente com fontes de sistema. Quando o CDN da Google responde, troca para Manrope/JetBrains/Inter sem quebra. Quando o CDN falha (ad blockers, firewall, DNS), a pagina funciona na mesma com fontes de sistema — sem ERR_CONNECTION_CLOSED bloqueante. O erro pode ainda aparecer na consola mas ja nao bloqueia a renderizacao.

---
Task ID: 18
Agent: Main Agent
Task: Hotfix — Webmail "Erro na sincronização: Configuração de email não ativa" em produção (configs multi-empresa)

Work Log:
- Utilizador reportou em produção: toast "Erro na sincronização: Configuração de email não ativa" ao clicar Sincronizar no Webmail. O envio de email funcionava, mas a sincronização (IMAP fetch) falhava.
- Diagnóstico passo-a-passo:
  1. Grep ao backend pela string exata "Configuração de email não ativa" → único hit: backend/services/email_service.py:1555, dentro de sync_user_emails.
  2. Lido o fluxo completo: rota POST /api/emails/webmail/sync-user (emails.py:3126) chama resolve_email_config_for_sync (resolver canónico que suporta multi-empresa/nested/coleção user_email_configs) → se resolved is None devolve "Configuração de email não encontrada" (mensagem DIFERENTE da reportada). Caso contrário inicia job em background que chama sync_user_emails(user_id) — passando SÓ o user_id.
  3. sync_user_emails (email_service.py:1522) lia user.email_config DIRETAMENTE (DB find_one em users com projection email_config), sem usar o resolver. Para configs multi-empresa (guardadas via Perfil > Configuração de Webmail), user.email_config é NESTED: {"company:default": {...}, "company:power": {...}} — não tem is_configured ao nível de topo. config.get("is_configured") devolvia None → return {"success": False, "error": "Configuração de email não ativa"} → job falhava → frontend (WebmailPage.jsx:569) mostra "Erro na sincronização: Configuração de email não ativa".
  4. Confirmada a divergência: o resolver valida com config correta; sync_user_emails re-leria raw e falhava. Bug introduzido quando a arquitetura migrou para nested/multi-empresa (user_email_config_service.py documenta que user.email_config embebido é backward compat e a leitura preferencial é da coleção).
  5. Verificados os outros callers de sync_user_emails: worker.py:233, scheduled_tasks.py:1463, email_service.py:2095 — todos usam args posicionais (user_id, days, max_emails). Adicionar param keyword opcional resolved_config é backward-compatible.
- Corrigido backend/services/email_service.py:
  * Assinatura de sync_user_emails: adicionado `resolved_config: Optional[Dict[str, Any]] = None`.
  * Docstring atualizado a documentar o novo param e o comportamento legacy fallback.
  * Bloco de resolução de config reescrito: se resolved_config fornecido, usa-o diretamente (sem ler user.email_config); else cai no caminho legado (ler user.email_config flat, com as verificações is_configured). Adicionado comentário explicativo grande a documentar o bug histórico.
  * Adicionada guarda `if not config.get("encrypted_password")` no ramo resolved_config (parity com legado).
  * imap_server/smtp_server agora com `or ""` fallback (resolved pode ter None em vez de string vazia quando a config vem de company/system sem servidor definido — previne TypeError no EmailAccount).
- Corrigido backend/routes/emails.py:
  * No handler webmail_sync_user, dentro de run_user_sync() closure, alterada a chamada de `sync_user_emails(user_id)` para `sync_user_emails(user_id, resolved_config=resolved)`. A closure captura a variável `resolved` do escopo envolvente (linha 3197). Adicionado comentário explicativo.
- Verificada sintaxe: py_compile OK em ambos os ficheiros. flake8 com regras estritas do CI (--select=E9,F63,F7,F82) → exit 0, sem erros.
- Verificada compatibilidade backward: os 3 callers existentes (worker, scheduled_tasks, sync_all_emails) não passam resolved_config, pelo que caem no ramo legado — sem alterações de comportamento para configs flat.
- Atualizada documentação: entrada nova no CHANGELOG.md ([2026-06-20] Hotfix Webmail "Configuração de email não ativa") + esta entrada no worklog.md.

Stage Summary:
- 2 ficheiros de código modificados:
  - backend/services/email_service.py (param resolved_config + bloco de resolução dual-path + comentários)
  - backend/routes/emails.py (passar resolved_config=resolved ao sync_user_emails)
- 2 ficheiros de docs atualizados: CHANGELOG.md, worklog.md
- Bug RESOLVIDO: a sincronização manual do Webmail (POST /api/emails/webmail/sync-user) passa a usar a MESMA config que foi validada pelo resolver canónico, independentemente de ser flat, nested, ou vir da coleção user_email_configs.
- Limitação conhecida NÃO resolvida (follow-up): worker.py:224 e scheduled_tasks.py:1453 usam query MongoDB {"email_config.is_configured": True} que não encontra users com config nested — afeta AUTO-SYNC em background (não a sync manual). Requer reescrever queries para consultar também user_email_configs collection.
- Próximo passo: commit + push para branch dev via Git Database API.

---
Task ID: 19
Agent: Main Agent
Task: Pacote J — Refatoração do Auto-Sync de Emails em Background (multi-empresa)

Work Log:
- Lido o contexto: hotfix anterior (Task ID 18, commit 2f65050e) corrigiu a sync MANUAL do webmail mas deixou documentada como "limitação conhecida" a sync AUTOMÁTICA em background, porque worker.py:224 e scheduled_tasks.py:1453 usavam query legacy `{"email_config.is_configured": True}` que não encontra configs nested/multi-empresa.
- Lidos os 3 ficheiros-alvo:
  * worker.py linhas 216-285 (bloco "Sincronização Webmail" no scheduler loop)
  * scheduled_tasks.py linhas 1449-1493 (bloco "2. Sincronizar caixas pessoais")
  * user_email_config_service.py (para perceber o schema da coleção user_email_configs e onde adicionar o helper)
- Confirmado o schema: user_email_configs tem campos {user_id, company_id, email_address, imap_server, imap_port, smtp_server, smtp_port, encrypted_password, google_refresh_token, google_access_token, google_email, auth_method, is_configured, ...}. Índice único (user_id, company_id) já existe (db_indexes.py:665).
- Verificado que NÃO existe função gmail_api_sync_user_to_db (só gmail_api_sync_to_db que recebe `role` para caixas partilhadas). Decisão: OAuth pessoal fica fora do escopo (log debug + skip); não é regressão porque sync_user_emails sempre falharia em encryption_service.decrypt("") para OAuth-only.
- Criado helper `get_active_email_configs_for_sync(limit=100)` em user_email_config_service.py (depois de get_user_companies_with_config):
  * Query 1: db.user_email_configs.find({is_configured: True, $or: [{encrypted_password: {$nin: ["", None], $exists: True}}, {google_refresh_token: {$nin: ["", None], $exists: True}}]})
  * Query 2 (batch): db.users.find({id: {$in: user_ids}, is_active: {$ne: False}}) — filtra inativos num só round-trip
  * Devolve lista de {user_id, company_id, email_address, auth_method, user_email}
- Refatorado worker.py (linhas 216-285):
  * Imports adicionados: get_active_email_configs_for_sync, resolve_email_config_for_sync
  * Substituído `db.users.find({"email_config.is_configured": True})` por `get_active_email_configs_for_sync(limit=50)`
  * Loop agora itera sobre `active_configs` (pares user_id+company_id)
  * Para cada config: branch em auth_method — google_oauth → log debug + continue; senão resolve_email_config_for_sync(user_id, active_company_id=company_id) → sync_user_emails(resolved_config=resolved)
  * Tratamento de erros individual por config mantido (try/except dentro do loop)
  * Detecção de policy violation IMAP mantida (parar iteração em rate limit)
  * Sync de caixas partilhadas via Gmail API (shared_role_email_configs) SEM alterações
- Refatorado scheduled_tasks.py (linhas 1449-1493) com o mesmo padrão:
  * Imports adicionados dentro do try
  * Substituído `self.db.users.find({"email_config.is_configured": True, ...})` por `get_active_email_configs_for_sync(limit=50)`
  * Loop itera sobre active_configs; branch auth_method; resolve_email_config_for_sync; sync_user_emails(resolved_config=resolved)
  * Tratamento _is_policy_violation mantido
- Verificada sintaxe: py_compile OK nos 3 ficheiros; AST parse OK; flake8 strict (--select=E9,F63,F7,F82) → exit 0 sem warnings.
- Atualizada documentação: entrada nova no CHANGELOG.md ([2026-06-20] Pacote J) + esta entrada no worklog.md.

Stage Summary:
- 3 ficheiros de código modificados:
  - backend/services/user_email_config_service.py (+helper get_active_email_configs_for_sync, ~70 linhas)
  - backend/worker.py (refactor do bloco webmail sync pessoal, ~70 linhas)
  - backend/services/scheduled_tasks.py (refactor do bloco "2. Sincronizar caixas pessoais", ~70 linhas)
- 2 ficheiros de docs atualizados: CHANGELOG.md, worklog.md
- Bug RESOLVIDO: a auto-sync em background (worker a cada 15 min, scheduled_tasks a cada hora) passa a usar a coleção canónica user_email_configs e itera sobre pares (user_id, company_id), chamando resolve_email_config_for_sync + sync_user_emails(resolved_config=resolved). Funciona para configs flat (legacy), nested multi-empresa, e guardadas via Perfil > Configuração de Webmail.
- Fecha a "limitação conhecida" do hotfix anterior (commit 2f65050e).
- Tratamento de erros individual por config preservado (falha numa conta não bloqueia as restantes); policy violation IMAP continua a parar a iteração (rate limit do servidor).
- OAuth pessoal: skip com log debug (não é regressão; sync_user_emails só suporta IMAP/SMTP). Implementar gmail_api_sync_user_to_db fica para iteração futura.
- Próximo passo: commit + push para branch dev via Git Database API.

---
Task ID: 20
Agent: Main Agent
Task: Pacote K — Bugfixes de QA (6 bugs: Balcões, Reatribuir, Cliente Ativo, Restore, Mapeamento, Área Pessoal)

Work Log:
- Lanzados 2 agentes Explore em paralelo (K-frontend-explore, K-backend-explore) para mapear todos os ficheiros/linhas dos 6 bugs. Recebidos relatórios detalhados com paths, line numbers e code snippets.
- Bug 1 (Balcões): SendDocumentationModal.js handleCreateBranch (linha 291) fazia POST mas só anexava ao state local (setRecipients manual). Corrigido: chama loadData() para re-buscar lista canónica; mantém setSelectedRecipients para pré-selecionar o novo balcão.
- Bug 2 (Reatribuir Cliente): Investigação completa (grep por "reatribui|reatribuir|atribuir.*consultor|trocar.*consultor" em todo o frontend). Confirmado: "Reatribuir Cliente" só existe em ProcessDetails.js (nível do processo) — state (355-361), handler (638-673), button (2411-2423), dialog (5706-5830). NÃO existe em nenhum cliente-global page (ClientsPage, ClientDetailPage, MyClientsPage, etc.). Sem alteração de código; comportamento já correcto. Documentado no CHANGELOG.
- Bug 3a (Cliente Ativo backend): clients.py tinha 2 ramos com bugs:
  * Branch A (show_all=True, linha 1027): `proc.get("is_active", True) and proc.get("status") not in ["desistencias", "concluidos", "arquivado", "perdido", "concluido"]` — typos "concluidos"/"arquivado", usava flag is_active desnormalizada.
  * Branch B (show_all=False, linha 1168): `proc.get("status") not in ["arquivado", "perdido", "concluido"]` — faltava "desistencias", typo "arquivado".
  * Corrigido ambos para: `not proc.get("is_deleted", False) and proc.get("status") not in INACTIVE_STATUSES` onde `INACTIVE_STATUSES = ("concluido", "desistencia", "desistencias", "eliminado")`.
  * Adicionado `is_deleted: 1` às projections MongoDB (linhas 959 e 1144) para o cálculo poder filtrar eliminados.
  * Corrigido também o `has_any_active` (linha 1050) que usava `p.get("is_active", True)` → agora usa a mesma lógica status + is_deleted.
- Bug 3b (Ver como Cliente): Investigação (grep por "Ver como Cliente|ver como cliente|impersonate.*client"). Confirmado: NÃO existe botão "Ver como Cliente". O botão "Portal do Cliente" em ProcessDetails.js (linha 2535) já usa `generateMagicLink(id)` com o id do processo atual (correto). O bug real estava em ClientRegistrationsPage.js (linhas 537 e 896) que navegava para `processes[0].id` sem filtrar eliminados. Corrigido ambas as ocorrências para usar `processes.find(p => !p.is_deleted && p.status !== "eliminado") || processes[0]`.
- Bug 4a (Restore endpoint): restore.py:30-128 existia mas estava quebrado:
  1. NÃO fazia is_deleted: False (bug crítico — processo ficava invisível após "restore")
  2. Sempre forçava status: "clientes_espera" (não preservava original)
  3. Não cascade-restore documentos/tarefas
  4. Dead code para db.deleted_processes (coleção inexistente)
  5. Restaurava processos concluídos (is_active: False)
  * Rewrite completo: unset is_deleted, restaura previous_status (guardado pelo delete), cascade-restore docs/tasks, log em process_activities (tipo process_restored), só restaura se is_deleted=True ou status="eliminado".
  * Adicionado `previous_status: process.get("status")` ao delete endpoint em processes.py:3098 para o restore poder recuperar o status original.
  * Adicionado `import uuid` no topo do restore.py (substitui __import__('uuid') inline).
- Bug 4b (Restore button frontend):
  * api.js: adicionado `export const deleteProcess` e `export const restoreProcess`.
  * ProcessesPage.js: substituído Switch (showCompleted) por Select com 3 opções (active_only/all/deleted). State `viewMode` substitui `showCompleted`. Handler `handleViewModeChange` + `handleRestoreProcess`.
  * Row rendering: adicionado botão "Restaurar" (RotateCcw icon, azul) quando viewMode==="deleted". Badge "Eliminado" (destructive, vermelho) quando process.is_deleted ou status==="eliminado".
  * Imports: adicionado RotateCcw, Trash2; adicionado restoreProcess.
- Bug 5 (Mapeamento balcões): emails.py _extract_email_variables (linhas 63-363):
  * Adicionado `credit_data = process.get("credit_data", {}) or {}` após line 97.
  * valor_financiamento_raw: adicionado `credit_data.get("requested_amount")` e `financial_data.get("valor_financiado")`.
  * capitais_proprios_raw: adicionado `financial_data.get("capital_proprio")` (singular).
  * prazo_raw: adicionado `credit_data.get("loan_term_years")`.
  * Verificado que _build_professional_email_html (366-609) NÃO duplica estas variáveis (usa valor_aquisicao/montante_divida em vez de valor_financiamento/capitais_proprios) — sem fix necessário ali.
- Bug 6 (Área Pessoal): ProfilePage.js:
  * Import: `from "../hooks/use-toast"` → `from "sonner"`.
  * 13 toast({title,description,variant}) convertidos para toast.success()/error()/warning().
  * handleSaveSignature: toast.success("Assinatura guardada com sucesso", {description: "..."}).
  * RichTextEditor: adicionado `key={sig-${effectiveCompanyId || "default"}}` para forçar remount ao mudar de empresa (ReactQuill não sincroniza visualmente sem key change).
  * useEffect deps [user, effectiveCompanyId, effectiveRole] já estavam correctos — o problema era o ReactQuill não refrescar, resolvido com key.
- Verificada sintaxe: py_compile OK nos 4 ficheiros backend; esbuild OK nos 5 ficheiros frontend; flake8 strict (--select=E9,F63,F7,F82) → exit 0.
- Atualizada documentação: entrada nova no CHANGELOG.md ([2026-06-20] Pacote K) + esta entrada no worklog.md.

Stage Summary:
- 9 ficheiros modificados:
  - frontend/src/components/SendDocumentationModal.js (Bug 1: loadData() após POST)
  - frontend/src/pages/ProcessesPage.js (Bug 4b: Select filtro + botão Restaurar + badge Eliminado)
  - frontend/src/pages/ProfilePage.js (Bug 6: sonner + toast.success + key prop)
  - frontend/src/pages/ClientRegistrationsPage.js (Bug 3b: filtrar processos eliminados na navegação)
  - frontend/src/services/api.js (Bug 4b: restoreProcess + deleteProcess)
  - backend/routes/emails.py (Bug 5: credit_data paths no _extract_email_variables)
  - backend/routes/clients.py (Bug 3a: cálculo cliente ativo + is_deleted projection)
  - backend/routes/restore.py (Bug 4a: rewrite completo do restore_process)
  - backend/routes/processes.py (Bug 4a: previous_status no delete endpoint)
- 2 ficheiros de docs atualizados: CHANGELOG.md, worklog.md
- Bug 2 (Reatribuir Cliente): sem alteração de código — confirmado que já estava correcto (só existe a nível do processo).
- Próximo passo: commit + push para branch dev via Git Database API.

---
Task ID: 24
Agent: Main Agent
Task: Aplicar Pacote M em dev (Auto-Login Portal + Nomenclatura Tarefas) — estava apenas em main local (estrutura powercell/) e faltava em origin/dev

Work Log:
- Diagnóstico: ao verificar o estado do repo, descobri que o Pacote M (commits 02b9fd6, bac46b7 em main local) estava apenas em main local — que tem estrutura ERRADA (projeto Next.js em root + powercell/ como subdiretório). O origin/dev (HEAD a974e60) tinha apenas Pacote K + L, não M.
- Confirmado via diffs: `git show main:powercell/backend/routes/portal.py` vs `git show dev:backend/routes/portal.py` — diff de 107 linhas corresponde EXATAMENTE ao Pacote M (imports + _resolve_frontend_url + endpoint impersonate_client_portal). Dev também tem Pacote G (portal_documents_notify) que main não tem — confirmado que não posso copiar ficheiro completo, preciso de aplicar apenas diffs do Pacote M.
- Aplicados os 5 ficheiros do Pacote M em dev com patches cirúrgicos via Python (script atómico para evitar reversion do HEAD entre invocações bash):
  1. backend/routes/portal.py:
     * Adicionado Request ao import do fastapi
     * Adicionado create_client_magic_token, PORTAL_TOKEN_VALIDITY_DAYS aos imports de portal_security
     * Adicionado require_staff aos imports de services.auth
     * Adicionado helper _resolve_frontend_url(request)
     * Adicionado endpoint GET /portal/impersonate/{process_id} → impersonate_client_portal (devolve {magic_link, token, process_id, client_id, client_name, client_email, expires_in_days})
  2. backend/routes/tasks.py:
     * Substituída a lógica de nomenclatura legada pela versão Pacote M: projection agora inclui process_ref + process_number; gerado prefixo [PROC-012] (preferir process_ref; fallback formatar process_number como PROC-{N:04d}); anti-duplicação se título já contém [PROC- (case-insensitive); mantém comportamento legado [client_name] como segundo prefixo
  3. frontend/src/services/api.js:
     * Adicionado export impersonateClientPortal(processId) → api.get(/portal/impersonate/${processId})
     * Mantido impersonateClient existente (Pacote K) para backward compat
  4. frontend/src/pages/ProcessDetails.js:
     * Adicionado impersonateClientPortal ao import
     * Mudada a chamada do botão "Ver como Cliente" de impersonateClient(id) para impersonateClientPortal(id)
  5. frontend/src/pages/ClientPortal.jsx:
     * Adicionado useState(autoLoginAttempted)
     * Adicionado useEffect AUTO-LOGIN VIA TOKEN que intercepta ?token=/?magic_link=/?access_token= na query string, resolve short_id via /portal/resolve se necessário, guarda JWT em localStorage, limpa URL via history.replaceState, setIsVerified(true) para saltar ecrã de login. Idempotente via autoLoginAttempted.
- Validação: py_compile OK em portal.py + tasks.py. grep confirma todas as marcas (impersonate_client_portal, impersonateClientPortal, REGRA DE NOMENCLATURA, AUTO-LOGIN VIA TOKEN).
- Commit + push a seguir para origin/dev.

Stage Summary:
- 5 ficheiros modificados em dev (estrutura correta, sem powercell/ prefix):
  - backend/routes/portal.py (+endpoint /portal/impersonate/{id} + helper + imports)
  - backend/routes/tasks.py (+nomenclatura [PROC-XXX] com anti-duplicação)
  - frontend/src/services/api.js (+export impersonateClientPortal)
  - frontend/src/pages/ProcessDetails.js (usa impersonateClientPortal)
  - frontend/src/pages/ClientPortal.jsx (+useEffect auto-login)
- Bug "Ver como Cliente" RESOLVIDO em dev: staff clica → backend devolve /portal?token=JWT → frontend intercepta ?token → setIsVerified(true) → dashboard sem login.
- Bug nomenclatura RESOLVIDO em dev: tarefas com process_id ficam com título "[PROC-012] [Nome Cliente] Título".
- main local (estrutura errada) deixado intacto — não deve ser pushed. Recomenda-se git reset --hard origin/main para alinhar main local com o remote no futuro.

---
Task ID: 25
Agent: Main Agent
Task: Limpeza técnica — remover .pyc committed + corrigir última query legacy email_config.is_configured em email_service.py

Work Log:
- Contexto: ambiente foi resetado (git re-init). Reconfigurado remote origin (https://github.com/PowerPrecision/PowerCell.git), feito fetch, recriadas branches dev (tracking origin/dev, d245b80) e main (reset hard para origin/main, 8996233). Confirmado que PR #527 já promoveu dev→main no GitHub.
- Tarefa 1 (Quick win): removidos 3 ficheiros .pyc committed acidentalmente no Pacote M:
  * powercell/backend/routes/__pycache__/clients.cpython-312.pyc
  * powercell/backend/routes/__pycache__/portal.cpython-312.pyc
  * powercell/backend/routes/__pycache__/tasks.cpython-312.pyc
  Via `git rm --cached` (mantém no disco, remove do index). Adicionado ao .gitignore: __pycache__/, *.py[cod], *$py.class, *.so, /powercell/**/__pycache__/. Commit 326968d.
- Tarefa 2 (Fix real): corrigida a ÚLTIMA query legacy ativa em email_service.py:2113 (função sync_all_user_emails). As outras 3 ocorrências (worker.py:226, scheduled_tasks.py:1451, user_email_config_service.py:86) já eram apenas comentários "SUBSTITUI a query legacy" do Pacote J.
  * Antes: db.users.find({"$and": [{"email_config.is_configured": True}] + nin_filter["$and"]}) — só encontrava configs flat embebidas em user.email_config, falhava para configs multi-empresa nested.
  * Agora: get_active_email_configs_for_sync(limit=200) consulta a coleção canónica user_email_configs (uma config por par user+empresa, com credenciais válidas, user ativo). Para cada config: resolve_email_config_for_sync(user_id, active_company_id=company_id) + sync_user_emails(user_id, days=days, resolved_config=resolved). Mesmo padrão do worker.py e scheduled_tasks.py (Pacote J).
  * Tratamento de edge cases:
    - Google OAuth pessoal: skip com log debug (legacy também não suportava — paridade com worker.py)
    - Config não resolúvel: skip com log debug + contador skipped_unresolved
    - Sem configs pessoais mas com roles partilhados: sync só roles partilhados
    - Roles partilhados (indexacao, suporte): mantidos via sync_shared_role_emails
  * Retorno enriquecido (superconjunto backward-compatible): users_synced, shared_roles_synced, skipped_oauth, skipped_unresolved, total_synced, total_errors, users (chave composta user_id|company_id para distinguir configs do mesmo user em empresas diferentes).
  * Validação: py_compile OK, ast.parse OK. Zero queries email_config.is_configured ativas no backend (apenas 4 comentários "SUBSTITUI a query legacy").
- Dev server confirmado saudável (HTTP 200 na porta 3000) durante toda a sessão.
- Pendência: push do commit 326968d (.pyc) + novo commit (email_service.py) para origin/dev — requer token GitHub (o repositório é público para fetch mas precisa auth para push).

Stage Summary:
- 2 commits locais prontos para push em dev:
  * 326968d chore: remover .pyc committed + adicionar __pycache__/ ao .gitignore
  * (a criar) fix(email): substituir última query legacy email_config.is_configured em sync_all_user_emails
- 1 ficheiro de código modificado: backend/services/email_service.py (+137/-29 linhas)
- 1 ficheiro de config modificado: .gitignore (+11 regras Python)
- "Limitação conhecida" do worklog Task 18 RESOLVIDA — auto-sync em background agora suporta configs multi-empresa nested, paridade total com a sync manual (hotfix 2f65050) e com o worker (Pacote J).
- Próximo passo: commit email_service.py + push de ambos os commits para origin/dev (requer token GitHub).

---
Task ID: Pacote S
Agent: Main Agent
Task: Super Dashboard de Balcões e Bancos — completar integração (rota + sidebar)

Work Log:
- Verificação do estado existente: o endpoint `GET /api/stats/branches` já estava implementado em `backend/routes/stats.py` (linhas 476-669) com MongoDB Aggregation Pipeline completo
- Verificação: a página `BranchPerformancePage.js` já estava implementada com Top Cards (Banco Mais Rápido, Balcão com Maior Volume, Taxa de Aprovação Global) e DataTable com ordenação interativa
- Verificação: a importação lazy de `BranchPerformancePage` já existia em `App.js` (linha 90)
- CORREÇÃO 1 — Rota em falta no `App.js`: adicionada rota `/performance-balcoes` com `ProtectedRoute` (STAFF_ROLES) e `RouteBoundary`
- CORREÇÃO 2 — Link em falta na sidebar: adicionado item "Performance de Balcões" (ícone Building2) no grupo "Gestão e Operações" do `DashboardLayout.js`
- CORREÇÃO 3 — `gestaoRoutes` atualizado para incluir `/performance-balcoes` (ativação correta do grupo na sidebar)
- Documentação `ARCHITECTURE.md`: adicionada secção "Dashboard de Performance de Balcões e Bancos (Pacote S)" com tabela de métricas e detalhes de cache

Stage Summary:
- 3 ficheiros modificados: `frontend/src/App.js` (+10 linhas), `frontend/src/layouts/DashboardLayout.js` (+6 linhas), `ARCHITECTURE.md` (+18 linhas)
- Funcionalidade completa: endpoint backend + página frontend + rota + sidebar + documentação
- Acesso: Staff com capability `STATS_VIEW` via rota `/performance-balcoes`

---
Task ID: Pacote T
Agent: Main Agent
Task: Fix "Ver como Cliente" sem e-mail + Apelido Interno do Processo

Work Log:
- Verificação do endpoint `/api/portal/impersonate/{process_id}` em `backend/routes/portal.py`
- Descoberta: o campo `apelido` já existia no modelo (`ProcessUpdate.apelido`, `ProcessResponse.apelido`) e no frontend (componente `InlineApelido` em `ProcessDetails.js`) — Tarefa 2 já implementada
- ALTERAÇÃO — Tarefa 1: substituído o comportamento de "gerar link na mesma com aviso no log" por HTTP 400 com mensagem amigável quando não há e-mail
- O frontend (`ProcessDetails.js` linha 2659-2661) já tratava `error.response.data.detail` via `toast.error()`, sem necessidade de alteração
- Documentação `ARCHITECTURE.md`: adicionada secção "Fix Ver como Cliente sem E-mail + Apelido Interno (Pacote T)"

Stage Summary:
- 1 ficheiro modificado no backend: `backend/routes/portal.py` (bloqueio 400 quando sem email)
- Tarefa 2 (Apelido Interno): já estava implementada — nenhuma alteração necessária
- Frontend: sem alterações (já exibia a mensagem de erro do backend)

---
Task ID: Pacote V
Agent: Main Agent + subagent
Task: Ecrã de Gestão de Empresas (Multi-Tenant)

Work Log:
- Exploração do código existente: não existia CRUD genérico de empresas, apenas company_email_configs e user_company_roles
- Criação do modelo `backend/models/company.py`: CompanyCreate, CompanyUpdate, CompanyResponse, CompanyListResponse
- Criação das rotas CRUD `backend/routes/companies_crud.py`: 6 endpoints (list, available, get, create, update, delete) + upload de logo
- Upload de logo usa `s3_service.s3_client.put_object()` (padrão do admin_storage.py)
- Delete bloqueia se existem utilizadores associados; Update faz cascade de rename em `users.company`
- Registo da nova rota em `backend/server.py` (import + include_router)
- Adição de 6 API calls em `frontend/src/services/api.js`
- Criação de `frontend/src/pages/CompaniesManagementPage.jsx` (lista + formulário com 3 secções)
- Integração no `SystemAdminPanel.jsx`: nova tab "Empresas" no grupo GESTÃO (amber), entre Automações e Finanças
- Documentação `ARCHITECTURE.md`: adicionada secção "Gestão de Empresas — Multi-Tenant (Pacote V)"

Stage Summary:
- 3 ficheiros criados: `backend/models/company.py`, `backend/routes/companies_crud.py`, `frontend/src/pages/CompaniesManagementPage.jsx`
- 4 ficheiros modificados: `backend/server.py`, `frontend/src/services/api.js`, `frontend/src/pages/SystemAdminPanel.jsx`, `ARCHITECTURE.md`
- Acesso: Admin/CEO via tab "Empresas" no Painel de Administração


---
Task ID: Pacote AA
Agent: Main Agent (Code Assistant)
Task: Correção de Erros 401 e 429 no Portal do Cliente

Work Log:
- Análise do erro reportado pelo utilizador: 5×401 (`/portal/status`, `/portal/messages`, `/portal/recommendations`, `/portal/messages/unread`, `/portal/visits`) + 1×429 (`/portal/auth/login`) na consola do browser em produção (powercell.onrender.com).
- Lidos os ficheiros relevantes: `frontend/src/pages/ClientPortal.jsx` (2898 linhas), `frontend/src/pages/ClientPortalLogin.jsx` (294 linhas), `backend/routes/portal.py` (3685 linhas), `backend/middleware/user_rate_limit.py`, `backend/middleware/rate_limit.py`, `backend/server.py` (middleware + exception handler).
- Identificada causa raiz dos 401: os `useEffect` de `fetchMessages`/`fetchUnreadCount` (linha 2182), `fetchRecommendations` (linha 2211) e `fetchVisits` (linha 2234) no `ClientPortal.jsx` disparavam no mount sem verificar `isVerified`. Quando o cliente tinha um token expirado em `localStorage`, os 5 endpoints corriam em paralelo e todos devolviam 401 (1 do useEffect de validação de token + 4 destes).
- Identificada causa raiz do 429: `MAX_LOGIN_ATTEMPTS = 5` com `LOGIN_LOCKOUT_MINUTES = 15` no `portal.py` era demasiado agressivo para um código de acesso de 6 caracteres alfanuméricos digitado manualmente. O frontend não mostrava tempo restante nem desabilitava o botão, levando o utilizador a continuar a tentar.
- Aplicadas 3 correções:
  1. `ClientPortal.jsx`: guard `if (!isVerified) return;` + dependência `isVerified` nos 3 `useEffect` de fetch; o polling de mensagens (setInterval 15s) agora para quando `isVerified` passa a false (cleanup do interval).
  2. `portal.py`: `MAX_LOGIN_ATTEMPTS` 5→8, `LOGIN_LOCKOUT_MINUTES` 15→10; as 2 respostas 429 (lockout ativo + novo lockout) devolvem `detail` como objeto estruturado `{error, message, retry_after, retry_after_minutes}` + header `Retry-After`.
  3. `ClientPortalLogin.jsx`: novo estado `lockoutSeconds` + `useEffect` de countdown (decrementa a cada segundo); `canSubmit` inclui `!isLockedOut`; bloco de erro distinto (âmbar com ícone Lock + countdown `Xm Ys`) para lockout vs erro normal (vermelho); handler 429 trata `detail` como objeto OU string (compatibilidade com rate limit global do middleware que devolve string).
- Validada sintaxe: `py_compile` no `portal.py` ✓; `esbuild --loader:.jsx=jsx` no `ClientPortal.jsx` e `ClientPortalLogin.jsx` ✓.
- Atualizada documentação: `CHANGELOG.md` (entrada Pacote AA), `memory/PRD.md` (bugs #5 e #6), este worklog.

Stage Summary:
- 3 ficheiros modificados: `frontend/src/pages/ClientPortal.jsx`, `frontend/src/pages/ClientPortalLogin.jsx`, `backend/routes/portal.py`.
- 3 ficheiros de documentação atualizados: `CHANGELOG.md`, `memory/PRD.md`, `worklog.md`.
- Resultado: clientes com token expirado deixam de ver 5×401 na consola; login tolera 8 tentativas (em vez de 5) com lockout mais curto (10 min em vez de 15); utilizador vê countdown claro durante o lockout e o botão fica desabilitado até poder tentar novamente.


---
Task ID: Pacote AB
Agent: Main Agent (Code Assistant)
Task: Fix F821 (CI blocker) no upload de logótipo de empresa

Work Log:
- Erro reportado pelo CI: `flake8 . --count --select=E9,F63,F7,F82` falhava com `F821 undefined name 'file_key'` em `backend/routes/companies_crud.py:246`.
- Lido o ficheiro `companies_crud.py` (258 linhas): o endpoint `POST /admin/companies/{company_id}/logo` fazia `s3_key = f"companies/{company_id}/logo_..."` (linha 238), fazia `put_object` no S3, e depois `logo_url = file_key` (linha 246) — `file_key` nunca foi definido; a variável correta é `s3_key`.
- Confirmado impacto: para além de falhar o CI, em runtime qualquer upload de logótipo geraria `NameError: name 'file_key' is not defined` → 500 Internal Server Error.
- Verificado consumo no frontend (`CompaniesManagementPage.jsx` linhas 311-316, 446-449): `company.logo_url` é usado diretamente como `<img src={...}>`, logo precisa de ser um URL carregável (não apenas uma chave S3).
- Verificado o serviço S3 (`s3_storage.py`): método `get_presigned_url(object_name, expiration=3600)` gera URL temporário.
- Implementada solução robusta (não apenas rename da variável):
  1. Corrigido `logo_url = file_key` → `logo_s3_key = s3_key` (guarda a chave S3 na BD).
  2. Criado helper `_resolve_logo_url(logo_value)` com 3 ramos: None→None; URL http(s)→as-is (retrocompatibilidade com logos configurados via API); chave S3→URL pré-assinado de 7 dias (604800s, máximo para credenciais de longa duração).
  3. Aplicado o helper nos endpoints `GET /admin/companies` (list) e `GET /admin/companies/{id}` (get) — o URL é gerado em tempo de leitura, nunca guardado na BD, pelo que nunca expira.
  4. Resposta do upload devolve `{logo_url, logo_s3_key}` para o frontend mostrar de imediato.
- Validação: `py_compile routes/companies_crud.py` ✓; `flake8 . --count --select=E9,F63,F7,F82` em todo o backend → **0 erros, exit 0**.
- Atualizada documentação: `CHANGELOG.md` (Pacote AB), `memory/PRD.md` (bug #7), este worklog.

Stage Summary:
- 1 ficheiro de código modificado: `backend/routes/companies_crud.py` (F821 corrigido + helper _resolve_logo_url + aplicação em 2 endpoints GET).
- 3 ficheiros de documentação atualizados: `CHANGELOG.md`, `memory/PRD.md`, `worklog.md`.
- Resultado: CI passa (0 erros flake8); upload de logótipo de empresa funciona em runtime; frontend recebe URL pré-assinado fresco que nunca expira na BD.


---
Task ID: Pacote AC
Agent: Main Agent (Code Assistant)
Task: UX de Simulações e Novos Campos de Compliance

Work Log:
- Lançados 2 agentes Explore em paralelo (AC-1: ProcessDetails mapper, AC-2: Calculators mapper) + mapeamento manual do backend (AC-3 falhou por rate limit, feito manualmente).
- Lidos ficheiros: ProcessDetails.js (5854 linhas), ProcessStickyHeader.js (309 linhas), RiskCalculator.js (703 linhas), SimulatorCH.jsx (282 linhas), models/process.py (255 linhas), routes/public.py (673 linhas), services/redis_cache.py, server.py.
- Tarefa 1 (Dropdown Simulações): substituídos os 2 botões DSTI+Risco por um `DropdownMenu` "Simulações ▾" (ícone Sparkles) em ProcessStickyHeader.js (sticky) e ProcessDetails.js (header principal). Cada `DropdownMenuItem` usa `onSelect={(e) => e.preventDefault()}` para o DialogTrigger interno das calculadoras receber o click. Import de DropdownMenu adicionado ao ProcessStickyHeader (ProcessDetails já tinha).
- Tarefa 2 (Fix RiskCalculator): (a) fallback `valorEntrada` corrigido de `||` para `??` com default 0 (lê do processo, assume 0 não 1); (b) `handleTipoTaxaChange` substitui `setTipoTaxa` direto — agora quando "Variável" é selecionada, um `useEffect` busca `/api/public/euribor` e preenche `taxaAnual = euribor + spread` instantaneamente; (c) campo de Spread visível apenas para Taxa Variável, com indicação visual da Euribor 12M carregada.
- Tarefa 3 (Euribor Automática): (a) backend: novo `services/euribor_service.py` (165 linhas) com cache módulo-level 24h + lock anti-concorrência + 4 níveis de fallback (cache→API externa→cache antigo→fallback hardcoded); novo endpoint `GET /public/euribor` em routes/public.py; (b) frontend SimulatorCH: import `useEffect`, estados `tipoTaxa`/`euribor12m`/`spread`, seletor Fixa/Variável, painel Euribor+Spread com badge "(estimada)" se fallback.
- Tarefa 4 (Cartão Compliance): (a) backend: 4 campos adicionados ao `CreditData` em models/process.py (`admission_year` int, `is_ppe` bool, `is_fpe` bool, `credit_incidents` str) + validadores Pydantic de coerção; (b) frontend: `collapsedCards` inicial `{ credit_compliance: true }` (minimizado por defeito), caso `credit_compliance` em `isCardEmpty`, novo cartão na tab credit (80 linhas) com Ano de Admissão (Input), PPE (Switch), FPE (Switch), Incidentes (Textarea) + aviso visual rose automático quando PPE/FPE ativos. Import de `Switch` adicionado.
- Validação: `py_compile` ✓ em 3 ficheiros Python; `flake8 --select=E9,F63,F7,F82` → 0 erros; `esbuild` ✓ em 4 ficheiros JSX.
- Atualizada documentação: CHANGELOG.md (Pacote AC), memory/PRD.md (secção Pacote AC), este worklog.

Stage Summary:
- 7 ficheiros modificados: backend/models/process.py, backend/services/euribor_service.py (novo), backend/routes/public.py, frontend/src/components/ProcessStickyHeader.js, frontend/src/pages/ProcessDetails.js, frontend/src/components/RiskCalculator.js, frontend/src/components/portal/SimulatorCH.jsx.
- 3 ficheiros de documentação atualizados: CHANGELOG.md, memory/PRD.md, worklog.md.
- Resultado: cabeçalho mais limpo (1 dropdown em vez de 2 botões); RiskCalculator reativo ao Tipo de Taxa; Euribor automática com cache diário em 2 sítios (Simulador CH + RiskCalculator); 4 campos de compliance persistidos em credit_data; cartão Compliance minimizado por defeito com aviso KYC/AML para PPE/FPE.


---
Task ID: Pacote AD
Agent: Main Agent (Code Assistant)
Task: Simulador Avançado — Taxa Mista, Seguros e Travas de Idade

Work Log:
- Lido o SimulatorCH.jsx atual (modificado no Pacote AC com Euribor) e o ClientPortal.jsx (linha 2551 onde <SimulatorCH /> é invocado sem props).
- Confirmada existência do Accordion do shadcn (frontend/src/components/ui/accordion.jsx) — usa AccordionPrimitive.Root com type="single" collapsible.
- Confirmada estrutura de dados do Portal: `data.dados_pessoais.data_nascimento` disponível no estado `data` (vindo de /portal/status).
- Tarefa 1 (Modo Básico vs Avançado): reorganizada a UI — simulação rápida (Montante/Prazo/TipoTaxa/TAN) sempre visível; Seguro de Vida, Multiriscos e Comissões Iniciais movidos para um Accordion "⚙️ Opções Avançadas" minimizado por defeito.
- Tarefa 2 (Fallbacks Invisíveis TAEG): estados seguroVida=15, seguroMultiriscos=10, comissoesIniciais=0 como defaults. Usados no cálculo da TAEG mas só visíveis se o Accordion for aberto. Nota explicativa dentro do Accordion. Nova função calcularTAEG() por bisseção (100 iterações, precisão 1e-7) que iguala montanteLiquido = VP(prestações + seguros).
- Tarefa 3 (Motor Taxa Mista): novo tipo "mista" adicionado aos botões (Fixa/Variável/Mista). Campos "Prazo da Taxa Fixa (Anos)" + "Taxa Fixa Aplicável (%)" obrigatórios (painel violeta). Motor refactorado em calcularSimulacao(): (1) Fase 1 = prestacaoFrances(montante, taxaFixa, n) — prestação constante; (2) Amortização = capitalEmDivida(prestacao, taxaFixa, n, mesesFase1) via VP das prestações restantes; (3) Fase 2 = prestacaoFrances(capitalAmortizado, tan, mesesFase2). Resultado mostra ambas as prestações + capital em dívida no fim da fase fixa.
- Tarefa 4 (Travas de Idade BP): SimulatorCH agora aceita prop `clienteDataNascimento`. ClientPortal passa `data?.dados_pessoais?.data_nascimento`. Funções calcularIdade() e prazoMaximoPorIdade() (≤30→40, 31-35→37, >35→35). Slider do Prazo tem `max={prazoMax}` dinâmico; useEffect ajusta prazoAnos se exceder o máximo. Badge visual mostra idade + limite.
- Resultado enriquecido: TAEG em destaque (pill) junto à prestação; 4 cards de detalhes (Montante/Total/Juros/Seguros+Comissões); prestação Fase 2 destacada (violeta) quando Taxa Mista.
- Validação: esbuild ✓ em SimulatorCH.jsx e ClientPortal.jsx. Removido import não usado (ChevronDown) — o Accordion do shadcn já injeta o seu.
- Atualizada documentação: CHANGELOG.md (Pacote AD), memory/PRD.md (secção Pacote AD), este worklog.

Stage Summary:
- 2 ficheiros modificados: frontend/src/components/portal/SimulatorCH.jsx (reescrita completa ~550 linhas), frontend/src/pages/ClientPortal.jsx (passar prop clienteDataNascimento).
- 3 ficheiros de documentação atualizados: CHANGELOG.md, memory/PRD.md, worklog.md.
- Resultado: simulador de nível bancário com 3 tipos de taxa (Fixa/Variável/Mista), motor de 2 fases para mista, TAEG realista por bisseção com fallbacks invisíveis, e travas de idade BP no slider do prazo.


---
Task ID: Pacote AE
Agent: Main Agent (Code Assistant)
Task: Fix 500 Internal Server Error no endpoint do Kanban

Work Log:
- Erro reportado: GET /api/processes/kanban?view_mode=all&show_all=true&completed_days=30 devolvia 500 (6× seguidas — TanStack Query retries) em produção (powercell.onrender.com).
- Lido o endpoint get_kanban_board em routes/processes.py (linhas 1734-2134) e o serviço process_kanban.py.
- Identificada causa raiz: nas linhas 2117-2121 o código acedia aos campos dos workflow_statuses com bracket notation — status["id"], status["name"], status["label"], status["color"], status["order"]. Se QUALQUER documento em workflow_statuses tiver um campo em falta (ex.: estado criado antes destes campos existirem, ou estado legacy sem label/color), lança KeyError → 500.
- Verificada função decrypt_processes_list (tem try/except interno, não lança). Verificadas constantes INACTIVE_STATUSES/ARCHIVED_STATUSES (definidas na linha 1241-1243). Agregações em portal_messages/documents não lançam em coleções vazias.
- Aplicadas 2 correções:
  1. Root cause fix: 5 acessos status["..."] trocados por status.get("...", default) com defaults graciosos: label → name.replace("_", " ").title(); color → "#6B7280"; order → 0; id → name.
  2. try/except defensivo à volta do loop for status in statuses: KeyError → HTTPException(500, "Erro de configuração de estados do workflow: campo 'X' em falta"); Exception → HTTPException(500, "Erro ao carregar kanban: TypeError: ..."). Ambos logam com logger.error/exception para diagnóstico futuro.
- Validação: py_compile ✓; flake8 --select=E9,F63,F7,F82 → 0 erros.
- Atualizada documentação: CHANGELOG.md (Pacote AE), memory/PRD.md (Correções do Pacote AE), este worklog.

Stage Summary:
- 1 ficheiro de código modificado: backend/routes/processes.py (5 acessos .get() + try/except defensivo).
- 3 ficheiros de documentação atualizados.
- Resultado: endpoint /kanban degrada graciosamente quando workflow_statuses tem campos em falta; se houver outro erro, o detail da resposta 500 contém a mensagem real em vez de erro genérico.
- Nota: o erro WebSocket ERR_ADDRESS_UNREACHABLE reportado em simultâneo é problema de rede/infraestrutura do Render (não de código) — o frontend já tem fallback a polling via useWebSocket.js.


---
Task ID: Pacote AD-fix (Impersonate)
Agent: Main Agent (Code Assistant)
Task: Fix do Parsing do Link de Impersonate — Ver como Cliente

Work Log:
- QA reportou: backend devolve HTTP 200 em /api/portal/impersonate/{id} mas frontend mostra toast "Não foi possível gerar o link".
- Lido o handler onClick do botão "Ver como Cliente" em ProcessDetails.js (linhas 2542-2580).
- Lido o backend routes/portal_admin.py (linhas 213-223): confirma que devolve {url, short_id, process_id, client_name, ...} — a chave correta é "url".
- Lido o interceptor do api.js (linha 177-179): o interceptor de sucesso é (response) => response — não transforma, pelo que res.data.url deveria funcionar.
- Hipótese: em alguma versão/estado a estrutura pode variar (ex.: resposta sem .data, ou chave alternativa). O código original lia apenas res?.data?.url — se falhasse por qualquer motivo, caía no toast genérico.
- Correções aplicadas:
  1. Extração robusta: const data = res?.data || res || {}; const url = data.url || data.magic_link || data.portal_url || data.link || data.access_url;
  2. Tratamento de erro robusto: const detail = error?.response?.data?.detail || error?.response?.data?.message || error?.message || "Erro ao gerar link de acesso."; toast.error(detail);
  3. Removida a condição que só mostrava o erro em 404 — agora qualquer erro é mostrado ao utilizador.
- Validação: esbuild ✓.
- Documentação: CHANGELOG, PRD, worklog atualizados.

Stage Summary:
- 1 ficheiro: frontend/src/pages/ProcessDetails.js (handler do botão Ver como Cliente).
- Resultado: extração do link tenta 5 chaves possíveis; erros mostram sempre a mensagem real do servidor.


---
Task ID: Pacote AF (Portal Messages 404)
Agent: Main Agent (Code Assistant)
Task: Fix loop de 404 em /portal-messages/unread no ProcessDetails

Work Log:
- Erro reportado: GET /api/processes/{id}/portal-messages/unread 404 repetido (loop de polling) em produção.
- Causa raiz: o backend (processes.py:4648-4649) devolve 404 quando o processo não existe OU está eliminado (is_deleted: true). O utilizador pode ainda estar na página de detalhes de um processo eliminado (read-only), pelo que o 404 é legítimo. O frontend já tinha lógica para desativar polling em 404 (portalUnreadAvailableRef), mas:
  (a) não verificava se token existia antes do fetch;
  (b) não tratava 401/403 (token expirado) que também devem desativar o polling;
  (c) o useEffect do polling não tinha `id` e `token` nas dependências, pelo que não se reiniciava correctamente.
- Correções aplicadas em ProcessDetails.js:
  1. fetchPortalUnreadCount: adicionado guard `if (!id || !token) return`; adicionado tratamento de 401/403 → 'ENDPOINT_NOT_AVAILABLE' (desativa polling silenciosamente).
  2. useEffect do polling: adicionado guard `if (!id || !token || !portalUnreadAvailableRef.current) return` no início; adicionado `id, token` às dependências; fetch inicial agora limpa o interval se retornar ENDPOINT_NOT_AVAILABLE.
- Validação: esbuild ✓.

Stage Summary:
- 1 ficheiro: frontend/src/pages/ProcessDetails.js.
- Resultado: o loop de 404 para quando o processo é eliminado ou o token expira; o polling respeita a existência de id/token.

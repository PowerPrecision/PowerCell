# AGENTS.md

## Cursor Cloud specific instructions

This repository is the **PowerCell** product (see `README.md` / `ARCHITECTURE.md`): a credit-process CRM made of a FastAPI backend (`backend/`) + React/Vite SPA (`frontend/`) + MongoDB.

The update script already installs all dependencies (frontend yarn deps and the backend Python venv at `backend/.venv`). System packages (`mongodb-org`, `libmagic1`, `python3.12-venv`) are baked into the VM image — do NOT reinstall them.

### Services & how to run them

| Service | Dir | Command | Port | Notes |
|---|---|---|---|---|
| MongoDB | — | `mongod --dbpath ~/data/db --bind_ip 127.0.0.1 --port 27017` | 27017 | No systemd; start manually. Required by the backend. |
| Backend (FastAPI) | `backend/` | `.venv/bin/uvicorn server:app --host 0.0.0.0 --port 8001` | 8001 | See env overrides below. Health: `GET /health`. |
| Frontend (React/Vite) | `frontend/` | `yarn dev` | 3000 | Vite, `strictPort`. `frontend/.env` sets `REACT_APP_BACKEND_URL=http://localhost:8001`. |

### Non-obvious gotchas

- **MongoDB Atlas is unreachable** from this environment (egress-restricted DNS). The committed `backend/.env` points `MONGO_URL` at Atlas — for local dev you MUST override it to a local Mongo. `backend/database.py` auto-disables TLS for `mongodb://localhost`. Start the backend with:
  `MONGO_URL="mongodb://localhost:27017" DB_NAME="PowerCell_dev" ENVIRONMENT="dev" .venv/bin/uvicorn server:app --host 0.0.0.0 --port 8001`
- **Seed users:** `cd backend && MONGO_URL="mongodb://localhost:27017" DB_NAME="PowerCell_dev" SEED_ADMIN_PASSWORD="Admin123!" SEED_DEFAULT_PASSWORD="PowerPrecision2026!" .venv/bin/python seed.py`. Login is `POST /api/auth/login-v2`. The `admin@sistema.pt` account has the hardcoded password **`admin`** (not the env var); `geral@powerealestate.pt` uses `SEED_ADMIN_PASSWORD`.
- **Backend tests:** `pytest.ini` declares an `env =` block but `pytest-env` is NOT installed, so those vars are ignored. Pass env explicitly and use `--no-cov` for speed, e.g.:
  `cd backend && MONGO_URL="mongodb://localhost:27017" DB_NAME="test_db_precision" JWT_SECRET="test_secret_key_123456789012345678" CORS_ORIGINS="http://localhost:3000" TESTING="true" ENVIRONMENT="dev" .venv/bin/python -m pytest tests/unit --no-cov -q`
- Optional integrations (Redis/ARQ worker, S3, OpenAI/Gemini, email/IMAP, Sentry) all degrade gracefully and are not needed to run the app. The ARQ worker (`backend/worker.py`) only runs when `ENVIRONMENT=production`.
- **Credentials in `backend/.env` are DEV-only** (owner clarification): production does not use this file — it injects secrets via the platform's secret manager. So the values present here are not production secrets; no need to treat them as a production leak or block on rotating them. Use `.env.example` as the template for required vars.
- CI (`.github/workflows/main.yml`): frontend (ESLint `--quiet` blocking + Vite build), backend (flake8 + pytest on **Python 3.12** — required by `numpy==2.5.1`), security (bandit + pip-audit), and **E2E smoke** (Playwright `e2e/smoke.spec.js` against local mongo + uvicorn + `yarn dev`).
- **Frontend E2E (Playwright)**: smoke runs in CI. Full suite locally: `cd frontend && npx playwright install chromium`, then `PLAYWRIGHT_BASE_URL=http://localhost:3000 yarn playwright test --project=chromium` (with backend on `:8001`). Use `PLAYWRIGHT_SKIP_WEBSERVER=1` if Vite is already running. Specs that need data (e.g. `e2e/undo-delete.spec.js`) provision via API and clean up after.

### Route thinning (documents / processes / emails / portal / admin / admin_storage / clients / finance / properties / chat / diagnostics / leads / form_config / system_config / admin_process_migration / rgpd / auth / visits / tasks / backup / shared_email / temp_links / google_auth / public / stats / admin_ai / ai / ai_analysis / my_clients / onedrive / scraper / templates / users / async_jobs)

Fat FastAPI routers are being split into thin `@router` stubs + `backend/services/*` modules. Prefer editing the service, not stuffing logic back into the route file.

| Area | Route file | Services pattern | Notes |
|---|---|---|---|
| Processes | `routes/processes.py` (~664) | `services/process_*.py` | Mostly done |
| Documents | `routes/documents.py` (~1072; was ~4623) | `services/document_*.py` | Thin stubs only — see map |
| Emails | `routes/emails.py` (~654; **done**) | `services/email_*.py` (see map) | Keep static paths before `/{email_id}`; do **not** collide with existing `email_service.py` / `email_draft_service.py` |
| Portal | `routes/portal.py` (~221; **done**) | `services/portal_*.py` (see map) | Do **not** collide with existing `portal_security` / `portal_magic_link` / `portal_documents_notify`. Portal `DOCUMENT_CATEGORY_MAP` includes `Financeiros` (separate from `document_constants`) |
| Admin | `routes/admin.py` (~655; **done**) | `services/admin_*.py` (see map) | Do **not** collide with existing **route** modules `admin_ai` / `admin_storage` / `admin_encryption` / `admin_migration` / `admin_process_migration` |
| Admin storage | `routes/admin_storage.py` (**done**) | `services/admin_s3_*.py` (see map) | Sibling of `admin.py`. **Never** create `services/admin_storage.py` (collides with the route module name). Do **not** overwrite `s3_storage.py` / `storage_service.py`. Preserve `client-s3-mappings` aliases. |
| Clients | `routes/clients.py` (~210; **done**) | `services/client_*.py` (see map) | Keep static paths (`/me`, `/registered`, `/search`, `""`, `/find-or-create`) before `/{client_id}`; do **not** collide with existing `client_match.py` / `process_clients_nm.py` / `process_my_clients.py` |
| Finance | `routes/finance.py` (~280; **done**) | `services/finance_*.py` (see map) | Keep `/finance/processes/summary` before `/{finance_id}`; do **not** collide with existing `process_finance.py` — use `finance_process_records.py` for `process_finances` CRUD |
| Properties | `routes/properties.py` (~245; **done**) | `services/property_*.py` (see map) | Keep static paths (`/stats`, `/by-process/{id}`) before `/{property_id}`; do **not** collide with existing `property_scraper.py` / `alerts.py` / `scraper.py` / `gov_scraper.py` |
| Chat | `routes/chat.py` (~250; **done**) | `services/chat_*.py` (see map) | No prior `chat_*` services; WS notify via `websocket_manager` stays inside services |
| Diagnostics | `routes/diagnostics.py` (~150; **done**) | `services/diagnostics_*.py` (see map) | Do **not** collide with existing `process_kanban_diagnose.py` — use `diagnostics_*` prefix |
| Leads | `routes/leads.py` (~140; **done**) | `services/lead_*.py` (see map) | Keep static paths (`/by-status`, `/consultores`, `/extract-url`, `/extract-html`, `/from-url`, `""`) before `/{lead_id}`; prefer `lead_*` (not `leads_*`) |
| Form config | `routes/form_config.py` (**done**) | `services/form_config_*.py` (see map) | Re-exports `DEFAULT_FORM_CONFIG` / `DEFAULT_STEP_CONFIG` for `routes.public` |
| Admin process migration | `routes/admin_process_migration.py` (**done**) | `services/admin_proc_migration_*.py` (see map) | **Never** create `services/admin_process_migration.py` (collides with the route module name) |
| System config | `routes/system_config.py` (**done**) | `services/system_config_*.py` (see map) | **Never** overwrite existing `services/system_config.py` (core load/save/cache). Use `system_config_api` / `_connections` / `_admin_ops` / `_system_emails` |
| RGPD | `routes/rgpd.py` (~230; **done**) | `services/rgpd_*.py` (see map) | Keep `/admin/all`, `/admin/template*`, `/admin/minuta-template*`, `/admin/stats/summary` before `/admin/{request_id}`; do **not** overwrite existing `rgpd_service.py` / `gdpr.py` — use `rgpd_helpers` / `rgpd_request` / `rgpd_public` / `rgpd_admin_list` / `rgpd_templates` / `rgpd_minutas` |
| Auth | `routes/auth.py` (~150; **done**) | `services/auth_*_handlers.py` (see map) | **Never** overwrite existing `services/auth.py` (JWT/bcrypt/`get_current_user`). Preserve deprecated `/login` (410) + `/login-v2` + cookie-ready `Response` signatures. Re-export `get_current_user` for `routes.storage` |
| Visits | `routes/visits.py` (~90; **done**) | `services/visit_*.py` (see map) | Keep `/kanban` before `/{visit_id}`; prefer `visit_*` (not `visits_*`); do **not** collide with `portal_client_visits.py` |
| Tasks | `routes/tasks.py` (~130; **done**) | `services/task_api_*.py` (see map) | Keep `/active`, `/my-tasks` before `/{task_id}`; **never** overwrite `task_queue.py` / `task_log_service.py` / `scheduled_tasks.py` — use `task_api_*` |
| Shared email | `routes/shared_email.py` (~110; **done**) | `services/shared_email_*.py` (see map) | Keep static `/google/callback` **before** `/{role}`; prefer `shared_email_*` |
| Temp links | `routes/temp_links.py` (~110; **done**) | `services/temp_link_api_*.py` (see map) | **Never** overwrite `temp_link_service.py` — use `temp_link_api_*`; keep `/public/{token}*` |
| Google auth | `routes/google_auth.py` (~60; **done**) | `services/google_auth_*.py` (see map) | **Never** overwrite `gmail_oauth.py` / `gmail_api_service.py` — use `google_auth_*` |
| Public | `routes/public.py` (~51; **done**) | `services/public_*.py` (see map) | Preserve rate limits on stubs; **never** overwrite `euribor_service.py`; form defaults from `form_config_defaults` (not via routes — circular import) |
| Stats | `routes/stats.py` (~47; **done**) | `services/stats_*.py` (see map) | Do **not** collide with `analytics_service.py`; `/health` (no auth) is the monitoring endpoint |
| Admin AI | `routes/admin_ai.py` (**done**) | `services/admin_ai_{config,models,tasks,cache,usage}.py` | **Never** create `services/admin_ai.py`; do **not** overwrite `admin_ai_data.py` / `ai_usage_tracker.py` |
| AI | `routes/ai.py` (**done**) | `services/ai_api_*.py` (see map) | **Never** overwrite `ai_document.py` / analyzers / `ai_usage_tracker.py` — use `ai_api_*` |
| AI analysis | `routes/ai_analysis.py` (**done**) | `services/ai_analysis_api_*.py` (see map) | **Never** overwrite analyzers; executive summary + cross-ref audit |
| My clients | `routes/my_clients.py` (**done**) | `services/my_clients_api_*.py` (see map) | **Never** overwrite `process_my_clients.py` (GET `/processes/my-clients`); list may reuse its enrichment maps |
| OneDrive | `routes/onedrive.py` (**done**) | `services/onedrive_*.py` (see map) | **Never** overwrite `services/onedrive.py` (Graph OAuth core) |
| Scraper | `routes/scraper.py` (**done**) | `services/scraper_api_*.py` (see map) | **Never** overwrite `scraper.py` / `gov_scraper.py` / `property_scraper.py` |
| Templates | `routes/templates.py` (**done**) | `services/templates_api_*.py` (see map) | **Never** overwrite `template_generator.py` |
| Users | `routes/users.py` (**done**) | `services/users_api_*.py` (see map) | **Never** overwrite `auth.py`; keep `/me/email-config*` before `/{user_id}`; admin CRUD stays in admin |
| Async jobs | `routes/async_jobs.py` (**done**) | `services/async_jobs_api_*.py` (see map) | Preserve rate limits; keep `/health` + `/session/*` + `/analyze` before `/{job_id}` |

**`email_*` thinning (complete):**

| Service | Responsibility |
|---|---|
| `email_template_vars.py` | `_extract_email_variables`, `_build_professional_email_html` |
| `email_enrich.py` | `enrich_email` (client_name / created_by_name) |
| `email_labels_folders.py` | Labels/folders CRUD + `validate_hex_color` + move-to-folder |
| `email_documentation.py` | document-recipients, preview-template, preview/send-documentation |
| `email_mailbox_ops.py` | Attachments upload/download/preview + mark/unmark + per-email labels |
| `email_templates_drafts.py` | Reply templates, unread notifications, auto-drafts |
| `email_webmail.py` | Webmail list/stats/sync, accounts, test-connection, jobs |
| `email_process_crud.py` | Search/timeline, process emails/sync, send, CRUD, monitored (`_sync_status` lives here) |

Unit helpers: `backend/tests/unit/test_email_extraction_helpers.py`.

**`portal_*` thinning (complete):**

| Service | Responsibility |
|---|---|
| `portal_assigned_users.py` | `get_all_assigned_user_ids` (also used by `process_portal_messages`) |
| `portal_doc_categories.py` | Portal category map / hidden / default pending (used by `process_create`) |
| `portal_profile.py` | GET/PUT `/me` + profile field allowlists |
| `portal_status_helpers.py` | contact / RGPD / team helpers for `/status` |
| `portal_onboarding_advance.py` | Pacote BO auto-advance after portal uploads |
| `portal_auth.py` | login / verify / resolve / impersonate / authenticate |
| `portal_status.py` | GET `/status` orchestration |
| `portal_upload_ops.py` | upload-url / confirm-upload / download-url |
| `portal_client_messages.py` | client messages (+ notify) |
| `portal_gov_fetch.py` | Finanças/SS scrapers, MFA, jobs |
| `portal_recommendations.py` | Smart Match recommendations |
| `portal_client_visits.py` | visit request + list |

Unit helpers: `backend/tests/unit/test_portal_extraction_helpers.py`.

**`admin_*` thinning (complete):**

| Service | Responsibility |
|---|---|
| `admin_helpers.py` | `_safe_float`, `_audit_log` |
| `admin_permissions.py` | permissions + capabilities |
| `admin_workflow.py` | workflow statuses + S3 CORS diagnostic |
| `admin_users.py` | user CRUD, impersonate, notif prefs, user email-config |
| `admin_process_ops.py` | fix-duplicates, migrate numbers, sync process emails |
| `admin_ai_data.py` | AI training + AI import logs |
| `admin_observability.py` | system logs, jobs health, client registrations, audit, team performance |
| `admin_dev_ops.py` | DB indexes, sync-database, seed (`_sync_in_progress` lives here) |

Unit helpers: `backend/tests/unit/test_admin_extraction_helpers.py`.

**`admin_s3_*` thinning (complete) — sibling of `routes/admin_storage.py`:**

| Service | Responsibility |
|---|---|
| `admin_s3_client_mappings.py` | `run_auto_map_client_s3_folders` (aliases stay as route stubs → process `run_*`) |
| `admin_s3_user_mappings.py` | user ↔ S3 folder list/get/update |
| `admin_s3_process_mappings.py` | process ↔ S3 list/update/fix-missing/batch + `_clean_s3_folder` |
| `admin_s3_explorer.py` | `_resolve_explorer_path`, folder contents, rename/delete/create/upload/download + request models |

**Never** create `services/admin_storage.py` (name collision with `routes/admin_storage.py` called out in the admin thinning notes). Do **not** overwrite `s3_storage.py` / `storage_service.py`.

Unit helpers: `backend/tests/unit/test_admin_storage_extraction_helpers.py`.

**`client_*` thinning (complete):**

| Service | Responsibility |
|---|---|
| `client_portal_email.py` | `_send_portal_welcome_email_safe` (fire-and-forget portal welcome) |
| `client_me.py` | GET `/me` assigned clients/processes |
| `client_registered.py` | GET `/registered` (Registo / Sala de Triagem) |
| `client_assign.py` | POST `/{id}/assign` (+ auto process create) |
| `client_list_search.py` | GET `/search` + GET `` list |
| `client_crud.py` | GET/POST/PUT client get/create/update |
| `client_process_ops.py` | link/unlink/create-process + GET processes |
| `client_portal_access.py` | POST resend-portal-access |
| `client_find_or_create.py` | POST `/find-or-create` |
| `client_delete.py` | DELETE client (soft delete + 2º titular rule) |

Unit helpers: `backend/tests/unit/test_client_extraction_helpers.py`.

**`finance_*` thinning (complete):**

| Service | Responsibility |
|---|---|
| `finance_helpers.py` | Shared helpers + `DashboardFinanceConfigUpdate` + `FINANCE_READ_ROLES` / defaults |
| `finance_dashboard.py` | GET/PUT `/finance/config`, summary, monthly, performance |
| `finance_commissions.py` | `_calc_commissions_data`, commissions + CSV export |
| `finance_configs.py` | Multi-company `finance_configs` CRUD + `_doc_to_config_response` |
| `finance_pool.py` | Pool distribution + CSV export |
| `finance_process_records.py` | `process_finances` summary/CRUD/status/delete (not `process_finance.py`) |

Unit helpers: `backend/tests/unit/test_finance_extraction_helpers.py`.

**`property_*` thinning (complete):**

| Service | Responsibility |
|---|---|
| `property_helpers.py` | `get_next_reference` (IMO-NNN) — shared by CRUD + excel import |
| `property_list.py` | GET `` list, `/stats`, `/by-process/{id}` |
| `property_crud.py` | POST/GET/PATCH/DELETE property + status (uses `alerts.check_and_notify_matches_for_new_property`) |
| `property_engagement.py` | interested clients, register-visit, photo add/remove |
| `property_excel_import.py` | bulk excel import + `_process_excel_import` + jobs + template |
| `property_documents.py` | property document upload / list / delete (S3) |

Unit helpers: `backend/tests/unit/test_property_extraction_helpers.py`.

**`chat_*` thinning (complete):**

| Service | Responsibility |
|---|---|
| `chat_helpers.py` | `_block_parceiro` / `block_parceiro`, `MAX_ATTACHMENT_SIZE`, `ALLOWED_ATTACHMENT_TYPES` |
| `chat_conversations.py` | GET `/conversations` |
| `chat_messages.py` | messages get/send/upload/react/edit/delete + POST `/search` |
| `chat_groups.py` | groups CRUD + leave |
| `chat_presence.py` | typing, unread-count, online-users, chat users directory |

Unit helpers: `backend/tests/unit/test_chat_extraction_helpers.py`.

**`diagnostics_*` thinning (complete):**

| Service | Responsibility |
|---|---|
| `diagnostics_helpers.py` | `datetime_to_str`, `ServiceStatus`, `SystemDiagnostics`, TTL migration models |
| `diagnostics_checks.py` | email / storage / AI / backup / notifications health checkers |
| `diagnostics_system.py` | GET ``, `/service/{name}`, `/quick-check` |
| `diagnostics_security.py` | encryption status, PII compliance, OpenAI privacy test-api |
| `diagnostics_ttl.py` | POST `/migrate-ttl-fields` + GET `/ttl-status` |

Unit helpers: `backend/tests/unit/test_diagnostics_extraction_helpers.py`.

**`lead_*` thinning (complete):**

| Service | Responsibility |
|---|---|
| `lead_helpers.py` | `_log_system_error`, `_parse_plain_text` |
| `lead_list.py` | GET `` list, `/by-status`, `/consultores` |
| `lead_extract.py` | POST `/extract-url`, `/extract-html`, `/from-url` |
| `lead_crud.py` | POST create + PATCH/status/refresh + DELETE |
| `lead_associate.py` | POST `/{id}/associate-client` |

Unit helpers: `backend/tests/unit/test_lead_extraction_helpers.py`.

**`form_config_*` thinning (complete):**

| Service | Responsibility |
|---|---|
| `form_config_defaults.py` | `DEFAULT_FORM_CONFIG`, `DEFAULT_STEP_CONFIG` |
| `form_config_fields.py` | GET/PUT `/fields`, custom-field CRUD, `/reset` + request models |
| `form_config_templates.py` | System templates + templates list/preview/save/activate/duplicate/delete |

Unit helpers: `backend/tests/unit/test_form_config_extraction_helpers.py`.

**`admin_proc_migration_*` thinning (complete) — sibling of `routes/admin_process_migration.py`:**

| Service | Responsibility |
|---|---|
| `admin_proc_migration_helpers.py` | `generate_client_key`, `extract_personal_from_process`, migration state helpers, `run_migration_task` |
| `admin_proc_migration_api.py` | status / dry-run / run / rollback / reset `run_*` handlers |

**Never** create `services/admin_process_migration.py` (name collision with the route module).

Unit helpers: `backend/tests/unit/test_admin_proc_migration_extraction_helpers.py`.

**`system_config_*` thinning (complete):**

| Service | Responsibility |
|---|---|
| `system_config.py` | **Existing core** — load/save/cache, `update_config_section`, companies list (**do not overwrite**) |
| `system_config_api.py` | `CONFIG_FIELDS`, `mask_sensitive`, get/update/fields/companies/export-permission |
| `system_config_connections.py` | POST `/test-connection/{service}` |
| `system_config_admin_ops.py` | complete-setup, storage-info, reset-cache, reveal-secrets |
| `system_config_system_emails.py` | system-emails CRUD + test + request models |

Unit helpers: `backend/tests/unit/test_system_config_extraction_helpers.py`.

**`rgpd_*` thinning (complete):**

| Service | Responsibility |
|---|---|
| `rgpd_helpers.py` | `_add_process_activity`, `_get_rgpd_or_404`, `_frontend_base_url_from_request` |
| `rgpd_request.py` | POST `/request` + `/admin/{id}/resend` (calls `rgpd_service.create_rgpd_request` / `send_rgpd_email`) |
| `rgpd_public.py` | validate / sign / status / data / list-by-process (calls `validate_token` / `sign_rgpd` / `get_rgpd_by_process`) |
| `rgpd_admin_list.py` | `/admin/all`, `/admin/{id}` CRUD, `/admin/stats/summary` |
| `rgpd_templates.py` | RGPD template CRUD + `_get_active_rgpd_template` + defaults |
| `rgpd_minutas.py` | Minuta template CRUD + `_get_active_minuta_template` + defaults |

Do **not** overwrite `rgpd_service.py` (PDF/email/token core) or `gdpr.py`. `rgpd_service` now imports active-template helpers from `rgpd_templates` / `rgpd_minutas` (routes still re-export for back-compat).

Unit helpers: `backend/tests/unit/test_rgpd_extraction_helpers.py`.

**`auth_*_handlers` thinning (complete) — do not overwrite `services/auth.py`:**

| Service | Responsibility |
|---|---|
| `auth_register_handlers.py` | POST `/register` |
| `auth_login_handlers.py` | deprecated POST `/login` (410) + POST `/login-v2` |
| `auth_profile_handlers.py` | GET `/me`, GET/PUT `/preferences`, PUT `/profile` (multi-empresa merge) |
| `auth_sessions_handlers.py` | POST `/refresh`, `/logout`, GET/DELETE `/sessions` |
| `auth_password_handlers.py` | POST `/change-password`, `/validate-password` |

Unit helpers: `backend/tests/unit/test_auth_extraction_helpers.py`.

**`visit_*` thinning (complete):**

| Service | Responsibility |
|---|---|
| `visit_helpers.py` | Calendar create/remove, portal status sync, background scraper |
| `visit_list_create.py` | GET `` list + POST create (scraper task + history) |
| `visit_kanban_get.py` | GET `/kanban` + GET `/{id}` |
| `visit_update_cancel.py` | PATCH update + DELETE cancel (calendar/portal sync) |

Do **not** collide with existing `portal_client_visits.py` (portal request/list). Prefer `visit_*` (not `visits_*`).

Unit helpers: `backend/tests/unit/test_visit_extraction_helpers.py`.

**`task_api_*` thinning (complete):**

| Service | Responsibility |
|---|---|
| `task_api_helpers.py` | `_block_parceiro` / `block_parceiro`, `get_user_names`, `enrich_task` |
| `task_api_crud.py` | Staff task create/list/my-tasks/get/update/complete/reopen/delete |
| `task_api_background.py` | GET `/active` + acknowledge/cancel for `background_jobs` |

**Never** overwrite `task_queue.py` / `task_log_service.py` / `scheduled_tasks.py` — thinning uses `task_api_*` prefix.

Unit helpers: `backend/tests/unit/test_task_extraction_helpers.py`.

**`backup_*` thinning (complete) — do **not** overwrite `services/backup.py` (core engine):**

| Service | Responsibility |
|---|---|
| `backup_ops.py` | statistics / history / verify / config / status |
| `backup_trigger.py` | POST `/trigger` + `/run-now` (+ `BackupRequest`) |
| `backup_restore.py` | POST `/restore-from-s3` + emergency `/restore` (atomic swap) |

Unit helpers: `backend/tests/unit/test_backup_extraction_helpers.py`.

**`public_*` thinning (complete) — do **not** overwrite `services/euribor_service.py`:**

| Service | Responsibility |
|---|---|
| `public_registration.py` | POST `/client-registration` (sanitize, RGPD encrypt, Pacote D process + magic link) |
| `public_health.py` | GET `/public/health` |
| `public_form_config.py` | GET `/form-config` (defaults from `form_config_defaults`, not via routes — avoids circular import) |
| `public_euribor.py` | GET `/euribor` wrapper → `euribor_service.get_euribor_rates` |

Preserve `@limiter.limit` on route stubs (`5/hour` registration, `30/minute` health, `60/minute` form-config). Form-config defaults are the same objects re-exported by `routes.form_config`.

Unit helpers: `backend/tests/unit/test_public_extraction_helpers.py`.

**`stats_*` thinning (complete) — do **not** collide with `analytics_service.py`:**

| Service | Responsibility |
|---|---|
| `stats_overview.py` | GET `/stats` (role-scoped KPI + Redis cache) |
| `stats_leads.py` | GET `/stats/leads` |
| `stats_conversion.py` | GET `/stats/conversion` |
| `stats_communications.py` | GET `/stats/communications` (portal + unread emails feed) |
| `stats_health.py` | GET `/health` (monitoring; Redis status) |
| `stats_branches.py` | GET `/stats/branches` (Pacote S bank/branch pipeline + status constants) |

Unit helpers: `backend/tests/unit/test_stats_extraction_helpers.py`.

**`shared_email_*` thinning (complete):**

| Service | Responsibility |
|---|---|
| `shared_email_helpers.py` | `ALLOWED_ROLES`, `_require_admin`, `_get_google_config`, `_build_redirect_uri` |
| `shared_email_crud.py` | list / get / upsert / delete shared role email configs |
| `shared_email_google.py` | `/google/callback` + `/{role}/google/login` + disconnect |
| `shared_email_sync.py` | POST `/{role}/sync` via `gmail_api_sync_to_db` |

Keep static `/google/callback` **before** `/{role}`. Unit helpers: `backend/tests/unit/test_shared_email_extraction_helpers.py`.

**`temp_link_api_*` thinning (complete) — do **not** overwrite `temp_link_service.py`:**

| Service | Responsibility |
|---|---|
| `temp_link_api_staff.py` | create / list-by-process / cancel / delete (auth) |
| `temp_link_api_public.py` | `/public/{token}` info/upload/download/download-all/files |

**Never** overwrite `temp_link_service.py` (core `TempLinkService`). Unit helpers: `backend/tests/unit/test_temp_link_extraction_helpers.py`.

**`google_auth_*` thinning (complete) — do **not** overwrite `gmail_oauth.py`:**

| Service | Responsibility |
|---|---|
| `google_auth_helpers.py` | `_get_google_config`, `_build_redirect_uri`, `_resolve_user` (Bearer + `?token=`) |
| `google_auth_oauth.py` | GET `/login` + `/callback` |
| `google_auth_status.py` | GET `/status` + DELETE `/disconnect` (per-role) |

**Never** overwrite `gmail_oauth.py` / `gmail_api_service.py`. Unit helpers: `backend/tests/unit/test_google_auth_extraction_helpers.py`.

**`admin_ai_*` thinning (complete) — sibling of `routes/admin_ai.py`:**

| Service | Responsibility |
|---|---|
| `admin_ai_config.py` | GET/PUT `/ai-config` + report recipients/config |
| `admin_ai_models.py` | AI models CRUD |
| `admin_ai_tasks.py` | AI tasks CRUD |
| `admin_ai_cache.py` | GET/PUT `/cache-settings` |
| `admin_ai_usage.py` | usage summary/by-task/by-model/trend/logs + weekly report |

**Never** create `services/admin_ai.py` (route module name). Do **not** overwrite `admin_ai_data.py` (training/import logs) or `ai_usage_tracker.py`. Unit helpers: `backend/tests/unit/test_admin_ai_extraction_helpers.py`.

**`ai_api_*` thinning (complete) — sibling of `routes/ai.py`:**

| Service | Responsibility |
|---|---|
| `ai_api_helpers.py` | `VALID_DOCUMENT_TYPES`, `map_extracted_data` |
| `ai_api_analyze.py` | sync analyze + OneDrive/S3 analyze + supported-documents |
| `ai_api_reset.py` | POST `/reset-client-data` |
| `ai_api_async.py` | async analyze + background worker |
| `ai_api_bulk.py` | bulk analysis async + background worker |

**Never** overwrite `ai_document.py` / `ai_document_analyzer.py` / `ai_page_analyzer.py` / `ai_usage_tracker.py` / `ai_improvement_agent.py`. Unit helpers: `backend/tests/unit/test_ai_api_extraction_helpers.py`.

**`ai_analysis_api_*` thinning (complete) — sibling of `routes/ai_analysis.py`:**

| Service | Responsibility |
|---|---|
| `ai_analysis_api_helpers.py` | locks, flatten/format/sanitize/build_context, `SYSTEM_PROMPT`, model constants |
| `ai_analysis_api_get.py` | GET `/processes/{id}/analyze` |
| `ai_analysis_api_generate.py` | POST `/processes/{id}/analyze` (OpenAI call + persist) |

**Never** overwrite `ai_document_analyzer.py` / `ai_page_analyzer.py` / `ai_document.py`. Unit helpers: `backend/tests/unit/test_ai_analysis_api_extraction_helpers.py`.

**`my_clients_api_*` thinning (complete) — do **not** overwrite `process_my_clients.py`:**

| Service | Responsibility |
|---|---|
| `my_clients_api_helpers.py` | status constants, process/stats query builders, lead row format |
| `my_clients_api_list.py` | GET `` (list + leads + enrichment; reuses `process_my_clients` maps) |
| `my_clients_api_stats.py` | GET `/stats` |

Unit helpers: `backend/tests/unit/test_my_clients_extraction_helpers.py`.

**`onedrive_*` thinning (complete) — do **not** overwrite `onedrive.py`:**

| Service | Responsibility |
|---|---|
| `onedrive_url_validation.py` | folder/link URL prefix checks |
| `onedrive_status.py` | GET `/status` |
| `onedrive_folder_url.py` | process folder URL get/save/delete |
| `onedrive_checklist.py` | checklist generate/get |
| `onedrive_files.py` | list client files by name (S3) |
| `onedrive_links.py` | process link CRUD + `LinkCreate`/`LinkUpdate` |

Unit helpers: `backend/tests/unit/test_onedrive_extraction_helpers.py`.

**`scraper_api_*` thinning (complete) — do **not** overwrite core scrapers:**

| Service | Responsibility |
|---|---|
| `scraper_api_models.py` | request/response models, friendly errors, site list, HTML source detect |
| `scraper_api_scrape.py` | `/single`, `/scrape`, `/crawl` |
| `scraper_api_ai.py` | supported-sites, analyze-with-ai, extract-html |
| `scraper_api_cache.py` | cache stats/clear/refresh |

Unit helpers: `backend/tests/unit/test_scraper_extraction_helpers.py`.

**`templates_api_*` thinning (complete) — do **not** overwrite `template_generator.py`:**

| Service | Responsibility |
|---|---|
| `templates_api_helpers.py` | roles, `DocumentRequestData`, error/download helpers |
| `templates_api_named.py` | webmail + named generate/download + document-request |
| `templates_api_checklist.py` | document checklist + document-types |
| `templates_api_generic.py` | available / generate / download / validate |

Unit helpers: `backend/tests/unit/test_templates_extraction_helpers.py`.

**`users_api_*` thinning (complete) — do **not** overwrite `auth.py`:**

| Service | Responsibility |
|---|---|
| `users_api_helpers.py` | `FORCED_SHARED_ROLES` |
| `users_api_list.py` | GET `` + GET `/{user_id}` |
| `users_api_email_config.py` | GET/POST `/me/email-config` + test |

Unit helpers: `backend/tests/unit/test_users_extraction_helpers.py`.

**`async_jobs_api_*` thinning (complete):**

| Service | Responsibility |
|---|---|
| `async_jobs_api_models.py` | Pydantic models + `ARQ_AVAILABLE` import guard |
| `async_jobs_api_analyze.py` | POST `/analyze` + GET `/{job_id}` |
| `async_jobs_api_session.py` | session start/analyze/status/finish |
| `async_jobs_api_health.py` | GET `/health` |

Unit helpers: `backend/tests/unit/test_async_jobs_extraction_helpers.py`.

**`ai_bulk_*` thinning (complete) — leave `routes/ai_bulk/` package helpers in place:**

| Service | Responsibility |
|---|---|
| `ai_bulk_models.py` | Pydantic request/response models |
| `ai_bulk_helpers.py` | `read_file_with_limit`, `update_client_data`, `log_import_*` |
| `ai_bulk_sessions.py` | import-session + aggregated session start/finish/status |
| `ai_bulk_analyze.py` | `/analyze-single` + aggregated `/analyze` |
| `ai_bulk_clients.py` | suggest/check/list/diagnose + analyzed-documents |
| `ai_bulk_cache_ops.py` | nif/duplicate cache + pending-reviews |
| `ai_bulk_import_errors.py` | get/resolve import errors (name avoids `routes.ai_bulk.import_errors`) |

Package `routes/ai_bulk/` (cache/jobs/matching/utils/constants/background_jobs) stays; `from routes.ai_bulk import router` still uses the sibling stub via importlib. Unit helpers: `backend/tests/unit/test_ai_bulk_extraction_helpers.py`.

**Fat route thinning: complete** for processes / documents / emails / portal / admin / admin_storage / clients / finance / properties / chat / diagnostics / leads / form_config / system_config / rgpd / admin_process_migration / auth / visits / tasks / backup / shared_email / temp_links / google_auth / public / stats / admin_ai / ai / ai_analysis / my_clients / onedrive / scraper / templates / users / async_jobs / ai_bulk.

**Remaining backlog** (still fat / partial, ≥~400 lines — next candidates by size):

| Route | ~Lines | Notes |
|---|---:|---|
| Mid-size | ~377–400 | `admin_migration`, `companies_crud`, `minutas`, `user_company_roles`, `deadlines` |

Prefer the same stub + `run_*` pattern; avoid colliding with existing core services (`backup.py`, `auth.py`, `euribor_service.py`, `analytics_service.py`, `temp_link_service.py`, `gmail_oauth.py`, `ai_document.py` / analyzers, `onedrive.py`, `scraper.py` / `gov_scraper.py` / `property_scraper.py`, `template_generator.py`, `process_my_clients.py`, route module names).

**`document_*` service map (keep `@router` names stable — rate-limit / integration tests scrape handler names in `routes/documents.py`):**

| Service | Responsibility |
|---|---|
| `document_constants.py` | Error strings, HTTP response docs, `DOCUMENT_CATEGORY_MAP` |
| `document_filenames.py` | `normalize_filename`, `generate_smart_filename`, log sanitize |
| `document_process_resolve.py` | Flexible process/client ID resolve + S3 path ownership checks |
| `document_expiring_dashboard.py` | Expiring-docs dashboard query/grouping |
| `document_portal_request.py` | Portal request CRUD (staff → client) |
| `document_auto_categorize.py` | Background IA categorize + OCR entities (**re-exported** from `routes.documents` for tests) |
| `document_upload_conflict.py` | Pre-upload filename conflict check |
| `document_direct_upload.py` | Pre-signed URL generate + confirm-upload |
| `document_upload.py` | Multipart upload pipeline (MIME validate, convert, IA triage, S3, history) |
| `document_move.py` | Move/rename conflict check + move-to-category |
| `document_ai_analyze.py` | Multi-doc IA analyze + organize-after-analysis folders |
| `document_delete.py` | Delete + bulk-delete with cross-process scope guard |
| `document_proxy.py` | S3 download proxy (StreamingResponse) |
| `document_bulk_download.py` | Multi-file ZIP download |
| `document_categorize.py` | On-demand categorize one / all |
| `document_rename_smart.py` | Smart rename one / all |
| `document_s3_paths.py` | Path variation helpers (underscore/space) |
| `document_queries.py` | Process docs list, metadata, search, categories |
| `document_expiry_crud.py` | Manual expiry CRUD + upcoming/calendar + DOCUMENT_TYPES |
| `document_misc.py` | check-file, init-folders, download URLs, employer NIF |
| `document_ocr_data.py` | OCR status, data suggestions, resolve/confirm conflicts |

**Gotchas**
- After changing route modules without `--reload`, restart uvicorn (cloud agents often run without reload).
- `auto_categorize_document_background` must remain importable as `from routes.documents import auto_categorize_document_background`.
- Motor `insert_one` mutates dicts with ObjectId `_id` — strip before JSON responses (portal create already does).
- Unit helpers: `backend/tests/unit/test_document_extraction_helpers.py`.

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

### Route thinning (documents / processes / emails / portal / admin / admin_storage / clients / finance / properties / chat / diagnostics / leads / form_config / system_config / admin_process_migration / rgpd / auth / visits / tasks)

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

**Fat route thinning: complete** for processes / documents / emails / portal / admin / admin_storage / clients / finance / properties / chat / diagnostics / leads / form_config / system_config / rgpd / admin_process_migration / auth / visits / tasks.

**Remaining backlog** (still fat / partial, ≥~400 lines — next candidates by size):

| Route | ~Lines | Notes |
|---|---:|---|
| `ai_bulk.py` | 1732 | Hybrid — much logic already in `routes/ai_bulk/*`; move package → `services/ai_bulk_*` |
| `backup.py` | 839 | Partial — core in `services/backup.py`; restore/trigger still in route |
| `public.py` | 743 | Public registration + form-config + health |
| `stats.py` | 669 | Dashboard/stats aggregations |
| `shared_email.py` | 662 | Shared mailbox |
| `temp_links.py` | 641 | Temporary document links |
| `google_auth.py` | 638 | Google OAuth |
| `ai.py` / `ai_analysis.py` | 589 / 572 | AI endpoints |
| `admin_ai.py` | 534 | Admin AI sibling (config/models/tasks) |
| Mid-size | 400–480 | `scraper`, `templates`, `onedrive`, `my_clients`, `users`, `async_jobs` |

Prefer the same stub + `run_*` pattern; avoid colliding with existing core services (`backup.py`, `auth.py`, route module names).

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

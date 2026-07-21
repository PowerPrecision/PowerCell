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

### Route thinning (documents / processes / emails)

Fat FastAPI routers are being split into thin `@router` stubs + `backend/services/*` modules. Prefer editing the service, not stuffing logic back into the route file.

| Area | Route file | Services pattern | Notes |
|---|---|---|---|
| Processes | `routes/processes.py` (~664) | `services/process_*.py` | Mostly done |
| Documents | `routes/documents.py` (~1072; was ~4623) | `services/document_*.py` | Thin stubs only — see map |
| Emails | `routes/emails.py` (~2825; thinning in progress) | `services/email_*.py` (see map) | Keep static paths before `/{email_id}`; do **not** collide with existing `email_service.py` / `email_draft_service.py` |

**`email_*` thinning so far:**

| Service | Responsibility |
|---|---|
| `email_template_vars.py` | `_extract_email_variables`, `_build_professional_email_html` |
| `email_enrich.py` | `enrich_email` (client_name / created_by_name) |
| `email_labels_folders.py` | Labels/folders CRUD + `validate_hex_color` + move-to-folder |
| `email_documentation.py` | document-recipients, preview-template, preview/send-documentation |

Unit helpers: `backend/tests/unit/test_email_extraction_helpers.py`.

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

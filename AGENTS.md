# AGENTS.md

## Cursor Cloud specific instructions

This repository actually contains **two apps** that both default to **port 3000**, so their dev servers **cannot run at the same time** on the default port:

1. **PowerCell** — the main, documented product (see `README.md` / `ARCHITECTURE.md`). A FastAPI backend (`backend/`) + React/Vite SPA (`frontend/`) + MongoDB. This is a credit-process CRM.
2. **Centro de Operações** — the root Next.js 16 + Prisma + SQLite app (`src/`, `prisma/`, root `package.json`, driven by `.zscripts/`). A background-jobs monitoring dashboard.

The update script already installs all dependencies (bun deps + Prisma client, frontend yarn deps, and the backend Python venv at `backend/.venv`). System packages (`bun`, `mongodb-org`, `libmagic1`, `python3.12-venv`) are baked into the VM image — do NOT reinstall them.

### Services & how to run them

| Service | Dir | Command | Port | Notes |
|---|---|---|---|---|
| MongoDB | — | `mongod --dbpath ~/data/db --bind_ip 127.0.0.1 --port 27017` | 27017 | No systemd; start manually. Required by PowerCell backend. |
| PowerCell backend | `backend/` | `.venv/bin/uvicorn server:app --host 0.0.0.0 --port 8001` | 8001 | See env overrides below. Health: `GET /health`. |
| PowerCell frontend | `frontend/` | `yarn dev` | 3000 | Vite, `strictPort`. `frontend/.env` sets `REACT_APP_BACKEND_URL=http://localhost:8001`. |
| Centro de Operações (Next.js) | repo root | `bunx next dev -p 3001` (or `bun run dev` for default :3000) | 3001/3000 | Needs `DATABASE_URL`. Run on an alternate port when PowerCell frontend holds 3000. |

### Non-obvious gotchas

- **MongoDB Atlas is unreachable** from this environment (egress-restricted DNS). The committed `backend/.env` points `MONGO_URL` at Atlas — for local dev you MUST override it to a local Mongo. `backend/database.py` auto-disables TLS for `mongodb://localhost`. Start the backend with:
  `MONGO_URL="mongodb://localhost:27017" DB_NAME="PowerCell_dev" ENVIRONMENT="dev" .venv/bin/uvicorn server:app --host 0.0.0.0 --port 8001`
- **Seed users:** `cd backend && MONGO_URL="mongodb://localhost:27017" DB_NAME="PowerCell_dev" SEED_ADMIN_PASSWORD="Admin123!" SEED_DEFAULT_PASSWORD="PowerPrecision2026!" .venv/bin/python seed.py`. Login is `POST /api/auth/login-v2`. The `admin@sistema.pt` account has the hardcoded password **`admin`** (not the env var); `geral@powerealestate.pt` uses `SEED_ADMIN_PASSWORD`.
- **Backend tests:** `pytest.ini` declares an `env =` block but `pytest-env` is NOT installed, so those vars are ignored. Pass env explicitly and use `--no-cov` for speed, e.g.:
  `cd backend && MONGO_URL="mongodb://localhost:27017" DB_NAME="test_db_precision" JWT_SECRET="test_secret_key_123456789012345678" CORS_ORIGINS="http://localhost:3000" TESTING="true" ENVIRONMENT="dev" .venv/bin/python -m pytest tests/unit --no-cov -q`
- **Next.js `DATABASE_URL`:** Prisma resolves relative `file:` paths against `prisma/`, so a relative URL creates a stray `prisma/db/`. Use the committed DB via an absolute URL: `DATABASE_URL="file:/workspace/db/custom.db"`. The schema is already pushed into the committed `db/custom.db`, so `prisma db push` is not required for a fresh checkout.
- **Root lint (`bun run lint` = `eslint .`)** lints the whole repo (including `frontend/`) and currently reports many pre-existing errors/warnings — this is existing code state, not an environment problem.
- Optional integrations (Redis/ARQ worker, S3, OpenAI/Gemini, email/IMAP, Sentry) all degrade gracefully and are not needed to run the apps. The ARQ worker (`backend/worker.py`) only runs when `ENVIRONMENT=production`.

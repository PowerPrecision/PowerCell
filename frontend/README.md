# PowerCell Frontend

## Tech Stack

- **React 19** + **Vite 6** (build tool)
- **Tailwind CSS 4** + **shadcn/ui** (New York style)
- **TanStack Query v5** (server state cache + mutations)
- **@dnd-kit** (drag-drop Kanban)
- **React Router v6** (routing + code splitting)
- **Zustand** (client state)
- **Lucide React** (icons)
- **Sonner** (toast notifications)
- **Recharts** (charts)
- **React Quill** (rich text editor)
- **date-fns** (date formatting, pt locale)
- **Sentry** (error monitoring)
- **pdfjs-dist** (PDF viewer + annotations)

## Development

```bash
yarn install        # Install dependencies
yarn dev            # Start dev server (Vite)
yarn build          # Production build
yarn lint           # ESLint check
```

## Architecture

- **`src/App.js`** — Router principal com 50+ rotas lazy-loaded, providers, error boundaries
- **`src/pages/`** — ~50 páginas com lazy loading (`React.lazy()`)
- **`src/components/ui/`** — Componentes shadcn/ui
- **`src/components/`** — Componentes de negócio (Kanban, S3FileManager, etc.)
- **`src/contexts/`** — Auth, Tasks, Theme, UploadProgress providers
- **`src/hooks/`** — Custom hooks (WebSocket, TanStack Query hooks)
- **`src/services/api.js`** — Axios instance com interceptors (JWT, 429 retry, refresh)
- **`src/layouts/DashboardLayout.js`** — Layout principal (sidebar + header)

## Key Patterns

- **Code Splitting**: Todas as páginas usam `React.lazy()` + `Suspense` para reduzir bundle inicial
- **Chunk Error Recovery**: `LazyChunkErrorBoundary` deteta stale deployments e faz reload
- **429 Retry**: API interceptor com 3 retries (2s→4s→8s + jitter), respeita `Retry-After`
- **Polling Backoff**: Notifications polling escala 30s→5min em caso de rate limiting
- **WebSocket Singleton**: Uma ligação partilhada entre componentes com backoff exponencial

## Deploy

- **Vercel** — SPA rewrites com exclusão de `/assets/` para evitar MIME type errors
- `vercel.json` — Configuração de rewrites + security headers (HSTS, CSP, X-Frame)

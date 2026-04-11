# Worklog - PowerCell CRM

---
Task ID: 7
Agent: Main Agent
Task: Fix Vercel MIME type crash and MyClientsPage JSX errors

Work Log:
- **Vercel MIME type crash (`dbfab8a`)**: Analisado erro `'text/html' is not a valid JavaScript MIME type` no ProtectedRoute. Causa: `vercel.json` rewrite `"/(.*)"` interceptava pedidos a chunks JS (`/assets/StaffDashboard-*.js`) e retornava `index.html`. Corrigido com negative lookahead: `/((?!assets|_next|favicon\.ico|robots\.txt|manifest\.json|sw\.js|workbox-|icon-.*\.png).*)`.
- **LazyChunkErrorBoundary updated (`dbfab8a`)**: Adicionados 4 patterns ao error detector: `text/html`, `MIME type`, `Unexpected token`, `Script error`. Agora stale deployments causam reload automático em vez de crash.
- **MyClientsPage JSX error (`fd84f29`)**: Analisado Vercel build errors — 5 erros cascata de JSX tag mismatch. Causa: `</div>` orfão na linha 274 (dentro do Card de filtros). Removida a tag extra. Estrutura corrigida: `Card > CardContent > div.flex > conditional p > /CardContent > /Card`.
- Commits: `dbfab8a`, `fd84f29` (pushed to `dev`)

Stage Summary:
- 2 ficheiros alterados: `frontend/vercel.json`, `frontend/src/App.js`, `frontend/src/pages/MyClientsPage.js`
- Vercel build deve passar — rewrites não interceptam assets, JSX válido

---
Task ID: 6
Agent: Main Agent
Task: Fix 429 rate limiting cascade and StatisticsPage crash

Work Log:
- **API Interceptor retry (`4268eec`)**: Adicionado retry com exponential backoff no `api.js`:
  - 3 tentativas para 429 responses
  - Delays: 2s → 4s → 8s + jitter (±500ms)
  - Respeita header `Retry-After` se presente
  - Suprime toast de erro durante retries
  - Retry-ID header para tracking
- **NotificationsDropdown backoff (`4268eec`)**: Polling com backoff adaptativo:
  - 30s → 60s → 120s → 300s (max) em caso de 429
  - Reset após 3 sucessos consecutivos
- **StatisticsPage crash (`97bfed9`)**: `X.filter is not a function`:
  - API retorna `{'items': [], 'total': 0}` (paginado) mas frontend chamava `.filter()` no objeto
  - Adicionados `Array.isArray()` guards em `processes`, `leadsStats.funnel_data`, `leads_by_source`, `top_consultors`
  - `getStats()` faz fallback para `{}`
- Commits: `4268eec`, `97bfed9` (pushed to `dev`)

Stage Summary:
- 2 ficheiros alterados: `frontend/src/services/api.js`, `frontend/src/pages/StatisticsPage.js`
- Resiliência a 429 em 2 níveis (interceptor + polling)
- StatisticsPage defensivo contra respostas não-array

---
Task ID: 5
Agent: Main Agent
Task: 4 áreas de melhorias de UX no frontend

Work Log:
- **TASK 1a - AuditTrailPage DashboardLayout**: Adicionado import de DashboardLayout e envolvido o conteúdo com `<DashboardLayout title="Auditoria">`. Removido padding duplicado.
- **TASK 1b - Sidebar accordion fix**: Corrigido `onOpenChange` com `e.stopPropagation()`. Adicionadas rotas em falta ao `getInitialOpenSections()`.
- **TASK 2 - Rich Text Editor RGPD**: Substituído `<Textarea>` por `<RichTextEditor>` com `readOnly`. Pré-visualização com `RichTextViewer`.
- **TASK 3 - Kanban 2nd Proponent Indicator**: Detecção de 2º proponente, borda lateral, badge.
- **TASK 4a - Tasks Panel reposicionado**: Movido para coluna direita (sidebar).
- **TASK 4b - RGPD confirmation dialog**: `window.confirm()` antes de enviar email.
- **TASK 4c - Magic Link Portal Button**: Popover com copiar link / enviar por email.
- Commit: `abd988e`

Stage Summary:
- 7 ficheiros alterados, 147 inserções, 30 remoções
- Files: AuditTrailPage.js, DashboardLayout.js, SystemConfigPage.js, KanbanCard.jsx, ProcessDetails.js, api.js

---
Task ID: 4
Agent: Main Agent
Task: Fix CI pipeline issues (pytest, submodules, Node.js)

Work Log:
- **pytest.ini multiline**: Removida continuação com backslash que causava parsing error. Commit: `9de712b`
- **Ghost submodule**: Removido `PowerCell` submodule fantasma do git index. Commit: `2e232ad`
- **Node.js 24**: Re-habilitado nos GitHub Actions. Commit: `6c6cb65`
- **Backend tests**: Adaptados para resposta paginada `{'items': [], 'total': 0}`. Commit: `1e63fac`
- **Async loop**: Resolvido `Future attached to a different loop`. Commit: `f84765d`

Stage Summary:
- CI pipeline estável com Node.js 24 + Python 3.11
- Todos os testes passam sem MongoDB

---
Task ID: 3
Agent: Main Agent
Task: Implementar Pipeline CI/CD com GitHub Actions

Work Log:
- Criado `.github/workflows/ci.yml` com pipeline completo
- Job 1 - Frontend CI (React + Vite): ESLint + Vite build
- Job 2 - Backend CI (Python + FastAPI): Flake8 + Pytest
- Job 3 - Notify on Failure (preparado para Slack/Teams)
- Criado backend/.flake8 com configuração
- Atualizado conftest.py com DUMMY_ENV_VARS

Stage Summary:
- CI Pipeline: Proteção contra código partido em produção
- Frontend: Build Vite como gatekeeper rigoroso
- Backend: Linting + Testes com env vars dummy

---
Task ID: 2
Agent: Main Agent
Task: Refatoração para TanStack Query (React Query v5)

Work Log:
- Instalado @tanstack/react-query e @tanstack/react-query-devtools
- Criado `lib/queryClient.js` com configuração otimizada
- Criado sistema de Query Keys Factory
- Criados hooks de Queries (useKanbanQuery, useProcessQuery, etc.)
- Criados hooks de Mutations (useMoveProcessMutation com optimistic update)
- Criado useKanbanRealtime para WebSocket + React Query
- Atualizado App.js com QueryClientProvider
- Refatorado KanbanBoard.js: eliminado useEffect/useState esparguete

Stage Summary:
- TanStack Query configurado com padrões CRM
- Optimistic updates e invalidação automática
- WebSocket integrado com setQueryData

---
Task ID: 1
Agent: Main Agent
Task: Implementar Motor de Tarefas Assíncronas e Centro de Operações Global

Work Log:
- Criado modelo TaskLog no MongoDB
- Criado serviço de gestão de tarefas (CRUD completo)
- Criadas rotas API (5 endpoints REST)
- Refatorado endpoint de AI para análise assíncrona (202 Accepted)
- Criado contexto React (TasksContext) com polling inteligente
- Criado componente TasksDropdown com badge e drawer
- Integrado no App.js e DashboardLayout.js

Stage Summary:
- Backend: Motor de tarefas assíncronas completo
- Frontend: Centro de Operações com polling
- Build compilado com sucesso

---
Task ID: 2
Agent: Backend WebSocket Agent
Task: Add PROCESS_MOVED, PROCESS_LOCKED, PROCESS_UNLOCKED WebSocket events

Work Log:
- Added PROCESS_MOVED, PROCESS_LOCKED, PROCESS_UNLOCKED to WSEventType
- Added sender-excluded PROCESS_MOVED broadcast in kanban move endpoint
- Added inbound LOCK/UNLOCK message handling in websocket route

Stage Summary:
- Backend broadcasts granular move events with user info
- Frontend can send lock/unlock events via WebSocket

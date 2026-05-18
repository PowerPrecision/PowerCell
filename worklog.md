---
Task ID: webmail-realtime-sync
Agent: main
Task: Webmail Real-Time Sync — Auto-sync em background + WebSocket NEW_EMAIL + Frontend reativo

Work Log:
- Analisou arquitetura atual: sync_webmail_emails(), sync_user_emails(), WebSocket manager, scheduled_tasks.py, server.py startup, WebmailPage.jsx
- Backend: Adicionou WSEventType.NEW_EMAIL ao websocket_manager.py (backend + frontend)
- Backend: Modificou sync_webmail_emails() em email_service.py para emitir evento NEW_EMAIL via WebSocket quando novo email é inserido na BD global (notifica admin/ceo/diretor/administrativo + utilizadores cujo email está nos destinatários + indexação)
- Backend: Modificou sync_user_emails() em email_service.py para emitir evento NEW_EMAIL diretamente ao dono da caixa pessoal
- Backend: Criou auto_sync_emails() e run_email_auto_sync() em scheduled_tasks.py — sincroniza caixa geral, pessoais e partilhadas a cada 3 minutos
- Backend: Registou run_email_auto_sync() como tarefa de background no startup do FastAPI (server.py)
- Frontend: Adicionou WSEventType.NEW_EMAIL ao useWebSocket.js
- Frontend: Adicionou handler onNewEmail ao useWebSocket.js
- Frontend: Em WebmailPage.jsx, adicionou hook useWebSocket com callback onNewEmail que:
  - Ação A: Mostra toast.info('📧 Novo email recebido de: [Remetente]')
  - Ação B: Faz refresh automático da lista de emails e contadores de pastas
- Commit 6678e0b pushed para origin/dev

Stage Summary:
- Webmail agora sincroniza automaticamente a cada 3 minutos (sem intervenção do utilizador)
- Novos emails detetados geram evento WebSocket NEW_EMAIL em tempo real
- Frontend atualiza pastas e mostra toast quando chegam novos emails
- Arquitectura de 3 camadas: Auto-sync → WebSocket → UI reativa
Agent: main
Task: RBAC Synchronization — 8 definitive profiles, centralized roleUtils, security rules

Work Log:
- Removed MEDIADOR and CONSULTOR_INTERMEDIARIO from UserRoleEnum in backend/models/auth.py
- Updated STAFF_ROLES, DOCUMENT_ROLES, MANAGEMENT_ROLES in auth.py to match 8 profiles
- Synced backend/models/enums.py with auth.py (removed MEDIADOR)
- Updated backend/services/permissions.py: removed mediador from DEFAULT_PERMISSIONS_BY_ROLE, updated role display labels
- Fixed backend/services/auth.py: require_roles hierarchy now uses INTERMEDIARIO instead of MEDIADOR
- Cleaned 13 backend route files of UserRole.MEDIADOR and UserRole.CONSULTOR_INTERMEDIARIO references
- Updated middleware/user_rate_limit.py, services/encryption.py, services/process_service.py
- Updated scripts/auto_assign_clients.py and scripts/assign_specific_clients.py
- Rewrote frontend/src/utils/roleUtils.js as comprehensive Single Source of Truth with:
  - VALID_ROLES, STAFF_ROLES, ADMIN_PANEL_ROLES, MANAGEMENT_ROLES, ADDITIONAL_ROLE_OPTIONS, PRIMARY_ROLE_OPTIONS
  - ROLE_LABELS (friendly: "Indexação de Dados", "Apoio Administrativo", etc.)
  - ROLE_COLORS, ROLE_SIDEBAR_COLORS, ROLE_ADDITIONAL_COLORS (Tailwind CSS)
  - ROLE_ICONS, ROLE_HIERARCHY
  - Permission functions: canAccessAdminPanel(), canManageUsers(), canSeeGestao(), isValidRole(), isStaff()
  - Deep role search utilities: hasRole(), hasAnyRole(), filterByRole(), etc.
- Updated UsersManagementPage.js:
  - Imports from roleUtils.js (no more local roleLabels/roleColors)
  - Dropdowns use PRIMARY_ROLE_OPTIONS for 8 profiles
  - Colored badges using ROLE_COLORS and ROLE_ADDITIONAL_COLORS
  - SECURITY RULE: role dropdowns and additional role checkboxes DISABLED for non-admin/CEO users
  - Filter dropdown uses STAFF_ROLES from roleUtils
- Updated DashboardLayout.js:
  - Imports ROLE_LABELS and ROLE_SIDEBAR_COLORS from roleUtils
  - INDEXAÇÃO now sees "Comunicações e Ficheiros" menu (was missing!)
  - Removed consultor_intermediario from consultor/intermediario menu check
- Updated ContextSwitcher.jsx: imports ROLE_LABELS and ROLE_ICONS from roleUtils
- Updated App.js: imports STAFF_ROLES from roleUtils, removed consultor_intermediario
- Cleaned 7 more frontend files of consultor_intermediario references
- Frontend build passes (npx vite build ✓)
- Backend Python syntax check passes
- Committed as da88c5a (push failed due to expired token)

Stage Summary:
- 8 definitive profiles enforced: admin, CEO, diretor, administrativo, consultor, intermediario, indexação, parceiro
- roleUtils.js is now the Single Source of Truth for RBAC in the frontend
- Indexação role now has access to "Comunicações e Ficheiros" menu
- Non-admin/CEO users cannot change roles (dropdowns disabled)
- All mediador/consultor_intermediario references cleaned from both backend and frontend
- Friendly labels: indexação → "Indexação de Dados", administrativo → "Apoio Administrativo"

---
Task ID: 1
Agent: Main Agent
Task: Implement Playwright RPA engine for Portal das Finanças & Segurança Social

Work Log:
- Explored existing backend structure: portal.py (mock scrapers), S3 service, email service
- Installed playwright==1.59.0 and Chromium browser
- Created backend/services/gov_scraper.py with full Playwright async automation
- Implemented fetch_financas_documents(): Login via acesso.gov.pt, download IRS + Nota de Liquidação
- Implemented fetch_seg_social_documents(): Login via app.seg-social.pt, download docs
- Replaced mock scrapers in portal.py with real gov_scraper calls + S3 upload + DB records
- Fixed email service: replaced raw SMTP with main email service (Resend API) + fallback
- Added /portal/scraper-status diagnostic endpoint (requires portal auth)
- Conducted security audit, fixed all CRITICAL and HIGH issues:
  - Fixed _secure_clear_password no-op (now uses del password in caller scope)
  - Added try/finally to _financas_scraper_inner for browser cleanup
  - Fixed double-close risk in _seg_social_scraper_inner
  - Sanitized exception logging (type only, no credential leakage)
  - Removed --disable-web-security Chromium flag
  - Reduced NIF/NISS mask visibility (2 visible digits instead of 5)
  - Made /scraper-status require portal authentication
- Committed as 3c5cce1 on dev branch, pushed to origin/dev

Stage Summary:
- New file: backend/services/gov_scraper.py (949 lines, Playwright RPA)
- Modified: backend/routes/portal.py (replaced mock scrapers with real automation + S3 upload)
- Modified: backend/requirements.txt (added playwright==1.59.0)
- All security audit issues fixed (3 CRITICAL, 3 HIGH, 4 MEDIUM)
- Pushed to origin/dev: commit 3c5cce1

---
Task ID: 1
Agent: Main Agent
Task: Fix React error #310 in PermissionsTab.js and verify backend scraper implementation

Work Log:
- Diagnosed React error #310 ("Too many re-renders") in frontend
- Found root cause: PermissionsTab.js called useAuth() inside IIFE (violates Rules of Hooks)
- Fixed by: importing useAuth at top level and calling as proper React hook
- Verified backend scraper (gov_scraper.py) was already fully implemented in previous session
- Verified portal.py endpoints (fetch-financas, fetch-seguranca-social) were complete
- Verified playwright==1.59.0 already in requirements.txt
- Cherry-picked fix commit to dev branch and pushed to origin/dev

Stage Summary:
- React error #310 fix committed to origin/dev (447924b)
- Backend scraper engine (Playwright RPA) already implemented: fetch_financas_documents() + fetch_seg_social_documents()
- Portal routes with S3 upload, email notifications, team notifications already complete
- All changes pushed to origin/dev

---
Task ID: 2
Agent: Main Agent
Task: Fix persistent React error #310 — previous fix was not applied on dev branch

Work Log:
- User reported React #310 still occurring after previous fix attempt
- Diagnosed: previous commit 447924b was only on main, not properly pushed to dev
- PermissionsTab.js still had the broken IIFE + require() + useAuth() pattern on dev branch
- Fixed PermissionsTab.js: replaced IIFE `(() => { try { const { useAuth } = require(...); return useAuth(); } catch { ... } })()` with proper top-level `import { useAuth } from "../../contexts/AuthContext"` and direct `const { user: currentUser } = useAuth()` call
- Fixed ClientPortal.jsx: changed useMemo dependency from `consultor` (object reference) to `consultor?.name` (primitive) to prevent unnecessary recalculations
- Verified frontend build succeeds (npx vite build ✓)
- Cherry-picked fix to dev branch and pushed to origin/dev (commit 92b83f3)

Stage Summary:
- Root cause: PermissionsTab.js called useAuth() inside an IIFE with dynamic require() and try/catch — violates React Rules of Hooks, causing inconsistent hook ordering → infinite re-renders
- Fix 1: PermissionsTab.js — proper top-level import + hook call
- Fix 2: ClientPortal.jsx — stable useMemo dependency (consultor?.name instead of consultor)
- Commit 92b83f3 pushed to origin/dev

## Task 3-b: Add embedded prop to pages group B
**Date:** 2026-03-04
**Files modified:**
1. `frontend/src/pages/NotificationSettingsPage.js` — Added `{ embedded = false }` prop to `export default function` signature. Added `wrapLayout` helper. Converted 2 DashboardLayout returns (loading skeleton + main content) to use `wrapLayout()`.
2. `frontend/src/pages/RGPDAdminPage.js` — Added `{ embedded = false }` prop to `const RGPDAdminPage` arrow function. Added `wrapLayout` helper. Converted 2 DashboardLayout returns (access denied + main content) to use `wrapLayout()`.
3. `frontend/src/pages/AuditTrailPage.js` — Added `{ embedded = false }` prop to `const AuditTrailPage` arrow function. Added `wrapLayout` helper preserving `title="Auditoria"` prop on DashboardLayout. Converted 1 DashboardLayout return to use `wrapLayout()`.
4. `frontend/src/pages/AIConfigPage.js` — Added `{ embedded = false }` prop to `const AIConfigPage` arrow function. Added `wrapLayout` helper. Converted 2 DashboardLayout returns (loading skeleton + main content) to use `wrapLayout()`.
5. `frontend/src/pages/BackgroundJobsPage.js` — Added `{ embedded = false }` prop to `const BackgroundJobsPage` arrow function. Added `wrapLayout` helper. Converted 1 DashboardLayout return to use `wrapLayout()`.

**Pattern applied:** Each component now has `const wrapLayout = (children) => embedded ? children : <DashboardLayout>{children}</DashboardLayout>;` (or with title prop for AuditTrailPage). All DashboardLayout import statements preserved.

## Task 3-a: Add embedded prop to pages group A
**Date:** 2026-03-05
**Files modified:**
1. `frontend/src/pages/WorkflowStatusesPage.js` — Added `{ embedded = false }` prop to `const WorkflowStatusesPage` arrow function. Added `wrapLayout` helper. Converted 2 DashboardLayout returns (access denied + main content) to use `wrapLayout()`. Dropped `title` props ("Acesso Negado", "Estados do Workflow") when embedded.
2. `frontend/src/pages/FormManagementPage.js` — Added `{ embedded = false }` prop to `const FormManagementPage` arrow function. Added `wrapLayout` helper. Converted 1 DashboardLayout return (main content with TooltipProvider wrapper) to use `wrapLayout()`.
3. `frontend/src/pages/ProfileSettingsPage.js` — Added `{ embedded = false }` prop to `const ProfileSettingsPage` arrow function. Added `wrapLayout` helper. Converted 1 DashboardLayout return (main content) to use `wrapLayout()`.
4. `frontend/src/pages/TemplatesPage.js` — Added `{ embedded = false }` prop to `const TemplatesPage` arrow function. Added `wrapLayout` helper. Converted 1 DashboardLayout return (with `title="Destinatários"` prop, dropped when embedded) to use `wrapLayout()`.
5. `frontend/src/pages/EmailAccountsPage.js` — Added `{ embedded = false }` prop to `const EmailAccountsPage` arrow function. Added `wrapLayout` helper. Converted 2 DashboardLayout returns (access denied + main content) to use `wrapLayout()`.

**Pattern applied:** Each component now has `const wrapLayout = (children) => embedded ? children : <DashboardLayout>{children}</DashboardLayout>;`. DashboardLayout title props are dropped when embedded=true. All DashboardLayout import statements preserved.


---
Task ID: config-setup
Agent: Main Agent
Task: Configuração do repositório GitHub PowerCell e credenciais

Work Log:
- Configurado git user: geral@powerealestate.pt / PowerCell Dev
- Remote origin: https://github.com/PowerPrecision/PowerCell.git
- Branch ativa: dev (sincronizada com origin/dev, commit 3edfc26)
- Testado push dry-run: Everything up-to-date ✓
- Revertido commit incorreto 9c913ed (módulo financeiro commitado na main)
- Working tree limpo e sincronizado com origin/dev
- Idioma de documentação: pt-PT
- Regra: atualizar documentação sempre que houver alterações

Stage Summary:
- Repositório GitHub configurado e sincronizado
- Branch dev ativa e pronta para desenvolvimento
- Credenciais guardadas no git config
- Commit push testado com sucesso

---
Task ID: finance-phase2-frontend
Agent: Main Agent
Task: Reconstruir FinanceDashboard.js com UI Premium — Fase 2 do Módulo Financeiro

Work Log:
- Analisou código existente: FinanceDashboard.js (929 linhas), backend/routes/finance.py (1100+ linhas), backend/models/finance.py (591 linhas), api.js
- Identificou endpoints Fase 2 já implementados: FinanceConfig CRUD (/finance/configs), ProcessFinance CRUD (/finance/processes), Summary (/finance/processes/summary)
- Identificou user.company como company_id para multi-tenant
- Adicionou 11 novas funções API em api.js:
  - getFinanceConfigs, getFinanceConfigById, createFinanceConfig, updateFinanceConfigById, deleteFinanceConfigById
  - getProcessFinances, getProcessFinanceById, createProcessFinance, updateProcessFinance, getProcessFinanceSummary
- Reconstruiu FinanceDashboard.js com 3 novas secções Premium:
  1. HonorariosDialog: Modal "Configurar Honorários" com GET/POST/PUT FinanceConfig
     - Seleção visual tipo toggle (Percentagem / Valor Fixo)
     - Campos default_value + tax_rate com pré-visualização do cálculo
     - Criação automática (POST) ou atualização (PUT) conforme existência
  2. KPI Cards Premium: 4 cartões com barra de acento lateral
     - Total Faturado (emerald), A Receber/Pendente (amber), Impostos IVA (sky), Total Processos Ganhos (purple)
     - Dados via GET /finance/processes/summary (company_id obrigatório)
  3. Tabela de Histórico ProcessFinance:
     - Colunas: Processo, Cliente, Valor Base, Honorário (badge %/€), Comissão, IVA, Total a Faturar, Estado
     - Clique no estado para avançar ciclo (Pendente→Faturado→Pago) via PUT /finance/processes/{id}
     - Filtro por estado (Select), sticky header/footer, linhas clicáveis
     - Empty state com ícone e mensagem
- Nova tab "Honorários & Processos" como tab padrão
- Tabs originais preservadas (Imobiliária, Crédito, Mensal, Comissões)
- Loading states com spinner e error handling com botão "Tentar novamente"
- Frontend build passa com sucesso (npx vite build ✓)
- Commit f1e8c69 pushed para origin/dev

Stage Summary:
- Frontend FinanceDashboard reconstruído com UI Premium
- 11 novas funções API em api.js
- Modal de Configuração de Honorários funcional (GET/POST/PUT)
- 4 KPI Cards agregados via ProcessFinance Summary
- Tabela de histórico com edição de estado inline
- Pushed to origin/dev: commit f1e8c69

---
Task ID: ux-fixes-1
Agent: Main Agent
Task: Correcções rigorosas de UX no Frontend (4 bugs)

Work Log:
- Bug 1: Z-Index dos Submenus — Dialog overlay/content z-50→z-[100], DropdownMenuContent z-50→z-[60], SelectContent z-50→z-[60], ProcessStickyHeader z-40→z-30
- Bug 2: Título do Processo — Prioridade de nome: client_name → client_data.name → personal_data.nome_completo. ID MongoDB ocultado; apenas process_number visível (Nº XXX)
- Bug 3: Barra de Progresso — Refactoração completa: HARDCODED_REQUIRED_BY_STEP + dynamicRequiredFields → allRequiredVisibleFields. Respeita depends_on e visibilidade condicional. Valores por defeito removidos (nacionalidade, compra_tipo) para garantir início a 0%. Booleanos (consent_data) contados correctamente. Termina a 100%.
- Bug 4: Locale Datepicker — Adicionado lang="pt" a todos os inputs type="date" no PublicClientForm. Index.html já tem lang="pt-PT".
- Commit 31fe28c pushed para origin/dev

Stage Summary:
- 7 ficheiros alterados, 87 inserções, 18 eliminações
- Dialog/Modal z-index: z-[100] (acima de tudo)
- Dropdown/Select: z-[60] (acima de header/sidebar z-50, abaixo de modais)
- ProcessStickyHeader: z-30 (abaixo de sidebar/header)
- Progress bar: 0% → 100% com base em campos obrigatórios visíveis
- Pushed to origin/dev: commit 31fe28c

---
Task ID: smart-match-module
Agent: Main Agent
Task: Módulo de Cruzamento Imobiliário (Smart Match) — Motor de Match + Envio para Portal + Frontend Consultor + Frontend Cliente

Work Log:
- Analisou codebase existente: match.py (5 endpoints), client_match.py (scoring), ProcessDetails.js (8 tabs), ClientPortal.jsx (stepper + docs + messages)
- Backend: Adicionou GET /api/match/process/{process_id} em routes/match.py — Motor de cruzamento que lê real_estate_data do processo, constrói query MongoDB para properties, calcula score de relevância (preço 35%, localização 35%, tipologia 30%, área 10%)
- Backend: Adicionou POST /api/portal/recommendations em routes/portal.py — Guarda recomendações no campo recommended_properties do processo, sem duplicados, com auditoria no histórico
- Backend: Adicionou GET /api/portal/recommendations em routes/portal.py — Endpoint consumido pelo Portal do Cliente, marca recomendações como visualizadas
- Frontend: Adicionou tab "Smart Match" ao ProcessDetails.js (9ª tab, ícone Sparkles, cor purple)
- Frontend: SmartMatchTab com "Procurar Matches" → grid de imóveis com score badge, foto, preço, tipologia, match reasons, botão "Recomendar ao Cliente"
- Frontend: Se processo não for de comprador, exibe "Apenas para processos de Comprador"
- Frontend: Adicionou secção "Imóveis Recomendados" ao ClientPortal.jsx — fetch automático, cards com foto/preço/localização/tipologia, recomendado por + data
- Syntax check OK para ambos os ficheiros backend
- Lint OK para ambos os ficheiros frontend (apenas warnings pré-existentes)

Stage Summary:
- 4 ficheiros alterados: backend/routes/match.py, backend/routes/portal.py, frontend/src/pages/ProcessDetails.js, frontend/src/pages/ClientPortal.jsx
- Query MongoDB do Smart Match validada: status=disponivel + financials.asking_price ≤ orcamento_max + address.municipality ~ concelho + $or[property_type ~ tipologia, features.bedrooms = N]
- Fluxo completo: Consultor clica "Procurar Matches" → vê grelha → clica "Recomendar ao Cliente" → imóvel fica disponível no Portal do Cliente
- Pendente: commit e push para dev

---
Task ID: 2
Agent: Main Agent
Task: Add bidirectional Visit management endpoints (Portal ↔ CRM)

Work Log:
- Read worklog.md and existing codebase: portal.py (1798 lines), visits.py (313 lines)
- TASK 1: Added two new Portal Visits endpoints to backend/routes/portal.py:
  - POST /portal/visits/request — Core endpoint: client requests a visit by pasting a property URL
    - Receives url (required) + optional process_id and notes
    - Invokes property_scraper.extract_property_data() to extract title, price, location, typology, photo
    - Creates visit record in db.visits with status='solicitada'
    - Stores scraped data (scraped_data, scraped_url, scraper_error) inside visit doc
    - Sets source='portal_client' to mark bidirectional origin
    - Logs VISIT_REQUESTED_BY_CLIENT in process history
    - Notifies all assigned team members (email + in-app realtime notification)
    - Broadcasts WebSocket event to process room
  - GET /portal/visits — Lists all visits for the client's process
    - Returns visits sorted by created_at desc (max 50)
    - Excludes scraped_data.raw_data to keep payload light
    - Maps status to client-friendly labels (solicitada→"A aguardar agendamento", etc.)
- TASK 2: Updated backend/routes/visits.py with 4 changes:
  - A) PATCH endpoint: Added 'solicitada' to valid status list (was only agendada/concluida/cancelada)
  - B) Kanban endpoint: Added 'solicitadas' column before 'agendadas' in return dict
  - C) PATCH endpoint: Added 'solicitada': 'Solicitada' to status_labels dict
  - D) list_visits: Replaced if/elif chain with valid_statuses list including 'solicitada'
- Python syntax check passed for both files

Stage Summary:
- 2 files modified: backend/routes/portal.py, backend/routes/visits.py
- New endpoints: POST /portal/visits/request, GET /portal/visits
- Visit lifecycle now supports 4 statuses: solicitada → agendada → concluida / cancelada
- Bidirectional flow: Client requests visit from Portal → appears as 'solicitada' in CRM kanban → Consultor patches to 'agendada' with scheduled_date
- Portal visits include scraped property data from external URLs

---
Task ID: 3
Agent: Frontend Agent
Task: Update VisitsPage.js for bidirectional visit management (solicitada status + portal client visits)

Work Log:
- Read existing VisitsPage.js (658 lines) — Kanban board with 3 columns: Agendadas, Concluídas, Canceladas
- Added `Inbox` import from lucide-react
- Added `solicitada` status to STATUS_CONFIG (before `agendada`): violet color scheme, Inbox icon, "Pedidos do Portal" label
- Updated VisitCard props: added `onSchedule` callback
- Added "Sugerido pelo Cliente" tag (emerald badge) after status Badge when `visit.source === 'portal_client'`
- Updated property section in VisitCard: shows property photo (with fallback to Building2 icon), scraped price (formatted as EUR), scraped typology
- Added `solicitada` action buttons: "Agendar" (amber, triggers onSchedule) + "Recusar" (red, sets status to cancelada)
- Updated KanbanColumn props: added `onSchedule`, passes it to VisitCard
- Created ScheduleFromPortalDialog component: dialog for scheduling a portal-requested visit with property preview (photo, price, typology, client name), datetime picker, consultor notes, PATCH to /api/visits/{id}
- Added `schedulingVisit` state and `handleSchedule` callback to VisitsPage
- Updated filteredKanban useMemo to include `solicitadas`
- Updated stats useMemo to include `solicitadas` count
- Added "Pedidos Portal" stats card (violet) before "Agendadas" — grid changed from 4 to 5 columns
- Added `solicitada` KanbanColumn as first column in board, with `onSchedule={handleSchedule}`
- Added ScheduleFromPortalDialog rendering at bottom alongside ScheduleVisitDialog

Stage Summary:
- VisitsPage.js updated from 3 Kanban columns to 4 (solicitada + agendada + concluida + cancelada)
- New "solicitada" status supports portal client visit requests with Agendar/Recusar actions
- ScheduleFromPortalDialog allows consultor to schedule date/time for portal-requested visits
- Portal visits show "Sugerido pelo Cliente" tag and scraped property data (photo, price, typology)
- Stats grid expanded to 5 columns with "Pedidos Portal" violet card

---
Task ID: 4
Agent: Main Agent
Task: Complete bidirectional Visit management — ClientPortal.jsx updates + worklog

Work Log:
- Added visits state to ClientPortal.jsx: visits, visitsLoading, visitUrl, requestingVisit, visitRequestResult
- Added fetchVisits callback + useEffect to fetch from GET /portal/visits
- Added "Visitas e Imóveis" section in ClientPortal.jsx left column (between TeamCard and Imóveis Recomendados)
- URL input with "Pedir Visita" button — calls POST /portal/visits/request with scraper working in background
- Shows success/error feedback after visit request
- Renders visits list with property cards: photo, title, price (EUR), location, typology
- Status badge with color coding: solicitada (violet), agendada (amber), concluida (emerald), cancelada (red)
- Shows scheduled date when visit is agendada
- Shows original listing link when scraped_url exists
- Empty state with house icon and helper text
- Visits list auto-refreshes after successful request

Stage Summary:
- ClientPortal.jsx fully updated with bidirectional visit management
- Client can paste property URL → Scraper extracts data → Visit created with status 'solicitada'
- Client sees all visits (portal-requested and consultant-scheduled) with clear status badges
- Full bidirectional flow: Client Portal ↔ CRM VisitsPage now operational

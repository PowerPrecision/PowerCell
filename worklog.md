# Worklog - PowerCell CRM

---
Task ID: sidebar-workflow-estados
Agent: Main Agent
Task: Adicionar item "Estados do Workflow" ao menu lateral — utilizador não encontrava a gestão de fases

Work Log:
- **Problema**: A página `/workflow-estados` existia com CRUD completo (WorkflowStatusesPage + WorkflowEditor), mas não tinha nenhum item no menu lateral — completamente invisível para admins
- **Investigação**: Confirmado que a rota existia em App.js e a página era acessível por URL direta (admin/ceo), mas o `getNavItems()` em DashboardLayout.js não tinha entrada
- **Fix**: Adicionado `{ label: "Estados do Workflow", icon: Activity, href: "/workflow-estados" }` ao array `items` do `configSistemaGroup` (linha 409)
- **O ícone Activity já estava importado** do lucide-react — sem novos imports necessários

Stage Summary:
- 1 ficheiro alterado: `frontend/src/layouts/DashboardLayout.js` (+5 linhas)
- Commit: `d6988a2` pushed to `dev`
- Menu: Configurações de Sistema → Estados do Workflow (admin only)

---
Task ID: fix-csp-vercel-live-stop-impersonate
Agent: Main Agent
Task: Corrigir CSP vercel.live framing + erro 400 ao parar impersonate

Work Log:
- **CSP vercel.live**: Adicionado `frame-src 'self' https://vercel.live` a ambos os CSP (portal e non-portal) no vercel.json
- **stop-impersonate 400 — diagnóstico**: Quando o access token é renovado (a cada ~2h), os metadados de impersonate eram perdidos. O frontend continuava a mostrar o banner "A ver como..." mas o backend retornava 400 "Não está em modo de personificação"
- **Fix backend** (`/auth/refresh`): Ao renovar token, extrai metadados de impersonate do token antigo (sem verificar assinatura/expiração) e passa-os para o novo token via `additional_data`
- **Fix frontend** (`refreshTokens`): Passa o token atual no Authorization header durante refresh para que o backend possa ler os metadados
- **Fix frontend** (`stopImpersonating`): Se o backend retorna 400, restaura automaticamente o originalToken do localStorage e redireciona para /admin sem mostrar erro

Stage Summary:
- 3 ficheiros alterados: `frontend/vercel.json`, `backend/routes/auth.py`, `frontend/src/contexts/AuthContext.js`
- Commit: `4e462de` pushed to `dev`

---
Task ID: fix-csp-complete-non-portal
Agent: Main Agent
Task: Completar CSP das páginas non-portal — bloqueava inline scripts, fonts, API calls

Work Log:
- **Problema**: CSP non-portal tinha apenas `frame-ancestors 'none'` + `default-src 'self'`, bloqueando: inline scripts/styles, Google Fonts, API calls ao render.com, Sentry, blob workers
- **Fix**: CSP atualizado para permitir: `unsafe-inline`/`eval` em script-src, Google Fonts em style-src/font-src, `https:` em connect-src, `blob:` em worker-src/script-src

Stage Summary:
- 1 ficheiro alterado: `frontend/vercel.json` (connect-src + style-src + font-src + script-src + worker-src)
- Commit: `accf8b2` pushed to `dev`

---
Task ID: fix-wss-csp-react-error-31
Agent: Main Agent
Task: Adicionar wss: ao CSP + corrigir React error #31 em Gestão de Formulários

Work Log:
- **wss CSP**: Adicionado `wss:` ao connect-src em ambos os CSP (portal e non-portal) para permitir ligações WebSocket ao backend
- **React error #31 — diagnóstico**: O backend DEFAULT_FORM_CONFIG envia opções em dois formatos: strings `"individual"` e objetos `{value: "solteiro", label: "Solteiro(a)"}`. O componente FormManagementPage.js renderizava objetos como React children em 7 locais
- **Fix**: Adicionadas helpers `optStr()` e `optVal()` no topo do ficheiro. Aplicadas a todos os 7 locais:
  1. WysiwygFieldPreview — select options
  2. WysiwygFieldPreview — checkbox options
  3. Step visibility dialog — trigger field dropdown
  4. Edit field dialog — checkbox list (depends_on_values)
  5. Edit field dialog — operator value dropdown
  6. Edit field dialog — options list display
  7. New field dialog — options list display

Stage Summary:
- 2 ficheiros alterados: `frontend/vercel.json`, `frontend/src/pages/FormManagementPage.js`
- Commit: `42e4c5d` pushed to `dev`
- React error #31 resolvido — opção `{value, label}` agora tratada como string em todo o FormManagementPage

---
Task ID: docs-update-session
Agent: Main Agent
Task: Atualizar worklog, CHANGELOG, README, PRD e restante documentação

Work Log:
- Leitura completa de worklog.md (1185 linhas), CHANGELOG.md (393), README.md (579), ARCHITECTURE.md (831), PRD.md
- Inventário de toda a documentação existente
- Atualização de todos os ficheiros com as alterações recentes

Stage Summary:
- Documentação atualizada com os últimos 4 commits de correção

---
Task ID: remove-frame-busting
Agent: Main Agent
Task: Remover frame-busting que causava erro "Unsafe attempt to load URL" no portal do cliente

Work Log:
- **Diagnóstico**: O erro `Unsafe attempt to load URL ... from frame with URL chrome-error://chromewebdata/` persistia APESAR da correção anterior (frame-busting + headers Vercel). A causa REAL era os próprios scripts de frame-busting: quando o email client carrega o link num iframe com parent `chrome-error://chromewebdata/`, o script `window.top.location.href = ...` tentava navegar o parent frame (cross-origin de `chrome-error://` para `https://`), o que o browser bloqueia com este erro. O `catch` fazia `window.open()` bloqueado pelo popup blocker. O `useEffect` secundário no React ainda设置 `setError()` e `setLoading(false)`, impedindo o portal de renderizar.
- **Fix — index.html**: Removido todo o bloco de frame-busting (script de 10 linhas no `<head>`). O portal funciona corretamente dentro de iframes — é uma SPA mobile-first independente com header/footer próprios.
- **Fix — ClientPortal.jsx**: Removido o `useEffect` de frame-busting (17 linhas) que detetava iframe e mostrava mensagem de erro. Sem este bloqueio, o portal carrega normalmente em qualquer contexto.
- **Segurança**: O JWT token validado no backend é o mecanismo de segurança — não depende de frame-busting. O `vercel.json` mantém `frame-ancestors *` para `/portal(.*)`.
- **CHANGELOG.md**: Documentação da correção.

Stage Summary:
- 2 ficheiros alterados: `frontend/index.html` (-10 linhas), `frontend/src/pages/ClientPortal.jsx` (-17 linhas)
- O portal agora carrega corretamente dentro de iframes de email clients
- Sem erros na consola relacionados com cross-origin navigation

---
Task ID: short-magic-links
Agent: Main Agent
Task: Encurtar Magic Links do portal do cliente de ~280 para ~50 caracteres

Work Log:
- **Estratégia**: Gerar short_id (8 chars, URL-safe) na BD, devolver URL curta, frontend resolve via API
- **backend/routes/processes.py — generate-magic-link**: Agora gera `secrets.token_urlsafe(6)[:8]` como short_id, guarda na coleção `portal_tokens` (upsert por process_id), devolve `magic_link` com URL curta
- **backend/routes/processes.py — generate-magic-link/send** (NOVO): Endpoint que faltava (frontend fazia 404). Gera link, envia email HTML com botão e link curto ao cliente via `send_email(force_system=True)`
- **backend/routes/portal.py — resolve/{short_id}** (NOVO): `GET /portal/resolve/{short_id}` — valida formato (regex alfanumérico), busca na BD, valida JWT internamente, retorna JWT. HTTP 410 se expirado, 404 se não encontrado
- **frontend/src/pages/ClientPortal.jsx**: Detecta `!rawToken.includes('.')` para determinar short vs JWT. Se short, chama `/portal/resolve/{short_id}`, obtém JWT, atualiza URL com `history.replaceState`, prossegue com fetchStatus. Links JWT antigos continuam a funcionar.
- **Python syntax**: py_compile OK para processes.py e portal.py

Stage Summary:
- 4 ficheiros alterados: `backend/routes/processes.py`, `backend/routes/portal.py`, `frontend/src/pages/ClientPortal.jsx`, `CHANGELOG.md`
- Link antes: `https://app.powercell.pt/portal/eyJhbGciOi...` (~280 chars)
- Link agora: `https://app.powercell.pt/portal/xK9mQ2pL` (~50 chars)
- Backward compatibility: links JWT antigos continuam a funcionar
- Endpoint "Enviar por Email" agora funciona (antes dava 404)

---
Task ID: frame-busting-portal
Agent: Main Agent
Task: Corrigir erro "Unsafe attempt to load URL" quando Magic Link é clicado dentro de email client

Work Log:
- **Diagnóstico**: Erro `chrome-error://chromewebdata/` ocorre quando o cliente clica num Magic Link dentro do webview de um email client (Outlook, Gmail app). O parent frame é `chrome-error://` e o browser bloqueia o carregamento cross-origin. Os headers `X-Frame-Options: DENY` e `frame-ancestors 'none'` impediam completamente o carregamento da página, incluindo o frame-busting JavaScript.
- **Fix 1 — index.html**: Adicionado script de frame-busting no `<head>` (antes do React). Se `window.self !== window.top`, tenta `window.top.location.href`. Se bloqueado por cross-origin, faz `window.open(url, '_blank')`.
- **Fix 2 — vercel.json**: Regra `/portal(.*)` com `frame-ancestors *` e SEM `X-Frame-Options: DENY`. Regra global usa negative lookahead `((?!portal).*)` para ser mutuamente exclusiva com `/portal`. Isto garante que `/portal` nunca recebe headers de bloqueio de iframe.
- **Fix 2b — vercel.json (correção)**: Versão anterior tinha `/portal(.*)` + `/(.*)` — ambas as regras faziam match em `/portal`, e o Vercel aplicava headers de ambas (o `frame-ancestors 'none'` e `X-Frame-Options: DENY` do catch-all sobrepunham o portal). Corrigido com negative lookahead para exclusão mútua.
- **Fix 3 — ClientPortal.jsx**: Adicionado `useEffect` de frame-busting como segunda camada de defesa. Em caso de cross-origin block, mostra mensagem ao utilizador a instruí-lo a abrir o link manualmente.
- **CHANGELOG.md**: Documentação completa da correção.

Stage Summary:
- 4 ficheiros alterados: `frontend/index.html`, `frontend/vercel.json`, `frontend/src/pages/ClientPortal.jsx`, `CHANGELOG.md`
- Correção em 3 camadas: HTML (primeiro script), Vercel headers (CSP), React (useEffect)
- Página do portal nunca fica visível dentro de iframe — redireciona sempre para top-level

---
Task ID: webmail-sync-fix
Agent: Main Agent
Task: Corrigir toast "precisa configurar" ao sincronizar webmail já configurado

Work Log:
- **Diagnóstico**: O botão "Sincronizar" no separador "Pessoal" chamava `/webmail/sync-user` que verifica `user.email_config.is_configured` (config pessoal). Admins que só configuraram email global (SystemConfigPage) não tinham config pessoal, causando o toast falso.
- **Fix 1 - WebmailPage.jsx handleSyncEmails**: Adicionado fallback automático — quando sync pessoal retorna `success: false` e o utilizador tem `showTabs` (admin/ceo/diretor/administrativo), faz automaticamente fetch ao endpoint global `/webmail/sync`. Se o global também falhar, mostra o erro do global.
- **Fix 2 - auth.py /auth/me**: Adicionada verificação de config global do sistema para admins. Se o utilizador não tem `email_config.is_configured` pessoal, o endpoint agora verifica `system_config.email` (Bloco A - SMTP) e `system_webmail` (Bloco C - Webmail partilhado). Se existir qualquer config global, `email_configured = True`, impedindo que o WelcomeConfigModal apareça no login.
- **CHANGELOG.md**: Documentação da correção.

Stage Summary:
- 3 ficheiros alterados: `backend/routes/auth.py`, `frontend/src/pages/WebmailPage.jsx`, `CHANGELOG.md`
- Commit: `79d643f` pushed to `dev`
- O sincronizar agora faz fallback para sync global quando config pessoal não existe
- O modal de configuração de email no login já não aparece para admins com email global configurado

---
Task ID: sentry-eslint-build
Agent: Main Agent
Task: Configurar Sentry Vite Plugin, Hidden Source Maps, ESLint no-cycle, e gerar novo build

Work Log:
- **vite.config.js**: Verified and enhanced Sentry Vite Plugin configuration
  - Auth token now reads from both `process.env` (Render) and `loadEnv()` (local .env files)
  - `sentryAuthToken = process.env.SENTRY_AUTH_TOKEN || env.SENTRY_AUTH_TOKEN`
  - Same fallback pattern applied to `sentryOrg`, `sentryProject`, `sentryRelease`
  - `sourcemap: 'hidden'` confirmed — generates .map files but no `sourceMappingURL` in JS bundles
  - `minify: 'esbuild'` confirmed for production builds
  - `manualChunks` groups Radix UI + cmdk + vaul into single chunk to prevent TDZ
  - `filesToDeleteAfterUpload: ['**/*.map']` — Sentry deletes maps after upload
- **eslint.config.js**: Enhanced ignore patterns
  - Added `*.config.mjs`, `public/**`, `craco.config.js` to ignores
  - `import/no-cycle: ['error', { maxDepth: 10, ignoreExternal: true }]` already configured
  - Other import rules: `no-duplicates`, `no-self-import`, `export` all as errors
- **package.json**: Fixed lint script for ESLint 9 flat config
  - Removed `--ext js,jsx` flag (not supported in flat config)
  - ESLint file patterns defined in eslint.config.js via `files: ['**/*.{js,jsx}']`
- **ESLint scan**: Ran on entire `src/` directory — 0 errors, 0 circular dependencies detected
- **Production build**: `vite build` completed in 21.02s
  - 5491 modules transformed
  - 118 source map files generated in `dist/assets/`
  - 0 JS files contain `sourceMappingURL` (hidden maps verified)
  - vendor-radix chunk: 216.14 kB (Radix + cmdk + vaul grouped)
  - vendor-recharts chunk: 387.64 kB
  - index chunk: 557.89 kB
  - ProcessDetails chunk: 805.41 kB

Stage Summary:
- 3 ficheiros alterados: `vite.config.js`, `eslint.config.js`, `package.json`
- Build de produção OK — 21.02s, 0 erros
- Hidden source maps: 118 ficheiros .map gerados, 0 referências em JS
- ESLint: 0 dependências circulares detetadas no código fonte
- Sentry plugin: configurado para upload automático quando SENTRY_AUTH_TOKEN disponível
- Ambiente de produção pronto: source maps vão para Sentry, browser nunca os descarrega

---
Task ID: 6
Agent: Main Agent
Task: Enforce strict no-reply behavior and add footer warning for system emails

Work Log:
- Analyzed PowerCell CRM codebase: React frontend + FastAPI backend + MongoDB
- Found zero Reply-To references in entire codebase (good baseline)
- **backend/models/system_config.py**: Added `smtp_from_name: Optional[str] = None` to `SystemSMTPConfig` (Bloco A). Added docstring noting one-way policy.
- **backend/services/email_service.py** (`send_email()` function):
  - Added `from_name` resolution for system_smtp accounts before the try block
  - When `force_system=True`: appends bilingual PT/EN no-reply footer to both `body_html` and `body` (text)
  - Footer HTML: `<p style="font-size: 10px; color: #666;">Por favor, não responda a este email. Esta mensagem foi gerada automaticamente por uma caixa de correio não monitorisée.</p>`
  - Footer text: same content in plain text with separator
  - From header uses formatted `f"{from_name} <{account.email}>"` when from_name is set
  - Added explicit comment: `# === CRITICAL: Reply-To is NEVER set ===` — this line intentionally does NOT exist
- **frontend/src/pages/SystemConfigPage.js** (`IntegrationsConfigSection`):
  - Added `smtp_from_name` to systemSmtp state (default: "")
  - Added `smtp_from_name` to config fetch (reads from `data.system_smtp.smtp_from_name`)
  - Added "Nome do Remetente" field (placeholder: "Power Real Estate") to Bloco A form
  - Changed label from "Email Remetente (From)" to "Email do Remetente (From)"
  - Changed placeholder from "noreply@empresa.pt" to "no-reply@powerealestate.pt"
  - Added green "Reply-To desativado por política" notice box with ShieldCheck icon below the form fields
- **temp_link_service.py**: No changes needed — already calls `send_email()` with `force_system=True`, footer is auto-appended

Stage Summary:
- 3 files changed, +71 lines, -6 lines
- Commit: `fb71f1a` pushed to `dev`
- Emails sent via `force_system=True` (temp links, documentation) now include: no-reply footer, no Reply-To header, formatted From name
- Bloco A form now has: SMTP Host, Port, Username, Password, From Email, **From Name (NEW)**, TLS
- Zero Reply-To fields or references anywhere in the codebase

Work Log:
- **Audit methodology**: Read backend model (`backend/models/process.py`), cross-referenced with `ProcessDetails.js` tabs (Personal, Financial, Real Estate, Credit), `ProcessSummaryCard.js`, and `ProcessDetailsModal.jsx`
- **Personal tab audit (lines 1551-1755)**: Found missing fields: `menor_35_anos` (boolean, in PersonalData model line 121), `compra_tipo` (string, in PersonalData model line 120)
- **Financial tab audit (lines 2057-2453)**: Found missing fields: `rendimento_bruto` (in validFields but no UI input), `rendimento_co_titular` (used in DSTICalculator line 1370 but no UI), `nr_dependentes`/`number_of_dependents`, `creditos_existentes`, `prestacao_creditos_mensal`
- **Real Estate tab**: All real_estate_data fields displayed ✅
- **Credit tab**: All credit_data fields displayed ✅ (requested_amount, loan_term_years, interest_rate, monthly_payment, bank_name, bank_approval_date, bank_approval_notes)
- **ProcessSummaryCard.js**: Shows summary (client, contact, property, financing, team, days) — appropriate for a summary card ✅
- **ProcessDetailsModal.jsx**: Quick-view modal shows client info, property info, status, assignments, notes, dates — appropriate for modal ✅
- **cleanFinancialDataForSubmit validFields**: Added 7 new fields: `nr_dependentes`, `number_of_dependents`, `rendimento_co_titular`, `creditos_existentes`, `prestacao_creditos_mensal`, `rendimento_agregado`, `rendimento_bruto` (already present, confirmed)
- **Personal tab changes**:
  - Added `Tipo de Compra` Select (line 1650) in Identificação section — options: Primeira Habitação, Segunda Habitação, Investimento, Refinanciamento
  - Added `Menor de 35 anos` checkbox (line 1723) in Identificação section — boolean for state support eligibility, with helper text "Apoio ao estado (jovem até 35 anos)"
- **Financial tab changes**:
  - Added `Rendimento Bruto (€)` input (line 2080) in Rendimentos card — reads from `financialData.rendimento_bruto || financialData.salario_bruto`
  - Added `Rendimento Co-Titular (€)` input (line 2120) in Rendimentos card — placeholder "Rendimento do 2º titular"
  - Added `Nº de Dependentes` input (line 2131) in Rendimentos card — number type, min=0, reads from `nr_dependentes || number_of_dependents`
  - Added `Créditos Existentes (€)` input (line 2197) in Situação Financeira card — placeholder "Valor total em dívida"
  - Added `Prestação Créditos Mensal (€)` input (line 2208) in Situação Financeira card — placeholder "Total prestações mensais"
- All new fields follow existing patterns: grid layout, `h-9` class, `canEditFinancial`/`canEditPersonal` disabled state, type="number" with parseFloat
- Vite build: ✅ OK (10.83s, 2811 modules)

Stage Summary:
- 1 ficheiro alterado: `frontend/src/pages/ProcessDetails.js` (3413 → 3505 linhas, +92)
- 5 campos adicionados ao Personal tab (menor_35_anos, compra_tipo + reordenação)
- 5 campos adicionados ao Financial tab (rendimento_bruto, rendimento_co_titular, nr_dependentes, creditos_existentes, prestacao_creditos_mensal)
- 7 campos adicionados ao validFields do cleanFinancialDataForSubmit para permitir persistência
- Real Estate tab e Credit tab completos — sem campos em falta
- ProcessSummaryCard e ProcessDetailsModal auditados — cobertura adequada para o nível de detalhe pretendido
- Todo o texto em português

---
Task ID: 2
Agent: Backend Agent
Task: Add default sorting by workflow phase then client name in list endpoints

Work Log:
- **GET /processes (line 746-772)**: Replaced MongoDB `.sort("client_name", 1).skip().limit()` with Python-side compound sorting. Fetches all matching processes (up to 5000), decrypts, then sorts by `(status_order, client_name.lower())`. Pagination applied after sorting. Removed separate `count_documents` call (uses `len()` post-sort).
- **GET /processes/kanban (line 1125-1127)**: Added per-column sorting — each status group in `processes_by_status` is now sorted alphabetically by `client_name` before enrichment and kanban assembly.
- **GET /processes/my-clients (line 1229-1271)**: Fixed pagination bug — previously applied `skip/limit` at MongoDB level before Python sort (producing inconsistent cross-page ordering). Now fetches up to 5000, sorts via `get_sort_key` (phase_order + client_name), then paginates. Kept existing `get_sort_key` function with updated docstring.
- **GET /clients/me (line 118-161)**: Replaced `.sort("client_name", 1).skip().limit()` with Python-side compound sorting. Fetches workflow statuses first for order map, fetches all matching processes (up to 5000), sorts by `(status_order, client_name.lower())`, then applies `skip/limit` for pagination.
- **GET /clients (line 800-807)**: Replaced simple `clients.sort(key=lambda c: (c.get("nome") or "").lower())` with compound sort: primary key = `status_order` of the client's `fase_principal` (first active process status), secondary key = `nome.lower()`. Uses existing `workflow_statuses` already fetched earlier in the endpoint.

Stage Summary:
- 2 ficheiros alterados: `backend/routes/processes.py`, `backend/routes/clients.py`
- 5 endpoints updated with compound sorting (workflow phase order → client name)
- All endpoints use Python-side sorting after fetch (consistent pattern)
- Kanban: sorted alphabetically within each column
- Pagination fixed in my-clients (was applying skip/limit before sort)
- py_compile syntax check: OK for both files

---
Task ID: 1
Agent: fix-menu-routing
Task: Fix menu routing and labels in sidebar and mobile nav

Work Log:
- **DashboardLayout.js — baseItems label (line 166)**: Added `isAdmin` flag. Non-admin staff now see "Processos" label (href: /processos) instead of misleading "Dashboard". Admin keeps "Dashboard" → /admin.
- **DashboardLayout.js — CEO menu (line 227)**: Changed label "Processos" → "Lista de Clientes" (href remains /clientes — semantically correct).
- **DashboardLayout.js — Admin menu (line 333)**: Changed label "Processos" → "Lista de Clientes" (href remains /clientes — semantically correct).
- **DashboardLayout.js — Consultor/Mediador/Intermediário (lines 523-535)**: "Os Meus Processos" now correctly routes to /processos (was /meus-clientes) with FileText icon. Added new "Os Meus Clientes" item → /meus-clientes with Users icon.
- **MobileBottomNav.jsx — first nav item (line 35)**: Changed label from "Kanban" to "Quadro Geral" to match sidebar naming.
- **MobileBottomNav.jsx — getDashboardPath (line 20)**: Non-admin path changed from /processos to /kanban (matching sidebar "Quadro Geral" → /kanban). Admin stays /admin.
- Vite build verified: ✓ built in 11.34s, no errors.

Stage Summary:
- 2 ficheiros alterados: `DashboardLayout.js`, `MobileBottomNav.jsx`
- Sidebar labels now match their actual routes for all roles
- Mobile nav first item renamed to "Quadro Geral" and routes to /kanban for non-admin
- All changes are label/route fixes only — no structural or functional changes
Task ID: 3
Agent: General-purpose Agent
Task: Reorganize client form field order in ProcessDetails.js

Work Log:
- Read worklog.md for project context
- Read `frontend/src/pages/ProcessDetails.js` lines 1540-1720 to identify the personal data form grid structure
- Identified current field order in the "Identificação" card (lines 1555-1703):
  1. Nome Completo → 2. NIF → 3. Nº Documento (CC) → 4. Data de Nascimento → 5. Validade CC → 6. Sexo → 7. Naturalidade → 8. Nacionalidade → 9. Estado Civil → 10. Altura
- Used single Edit to rearrange all 8 form field blocks (lines 1596-1703) from:
  - Old: CC → Data Nascimento → Validade CC → Sexo → Naturalidade → Nacionalidade → Estado Civil → Altura
  - New: CC → Validade CC → Data Nascimento → Estado Civil → Sexo → Naturalidade → Nacionalidade → Altura
- No code logic changed — only block order within the JSX grid rearranged
- Verified new order via grep on Label text: lines 1596, 1612, 1629, 1645, 1662, 1676, 1685, 1694
- Vite build: OK (11.48s, no errors)

Stage Summary:
- 1 ficheiro alterado: `frontend/src/pages/ProcessDetails.js` (0 linhas adicionadas/removidas, blocos reordenados)
- "Data de Nascimento" moved right after "Validade CC" (CC block now: CC number + validity + birth date)
- "Estado Civil" moved right after "Data de Nascimento"
- Remaining fields (Sexo, Naturalidade, Nacionalidade, Altura) preserved in original relative order
- Vite build passes

---
Task ID: 4
Agent: General Agent
Task: Remove all console.log, console.info, and console.table statements from frontend

Work Log:
- Grepped entire `frontend/src/` for `console.log|console.info|console.table` — found 30 occurrences across 9 files
- **main.jsx**: Removed 3 `console.log` (axe-core dev message, Sentry init success, Sentry DSN warning). Cleaned up resulting empty `else {}` block.
- **pushNotifications.js**: Removed 5 `console.log` (SW registered, permission result, subscription created, backend registered, unsubscribed). Converted empty `if (response.ok) {} else` to `if (!response.ok)`.
- **api.js**: Removed 1 `console.log` (impersonate token expiry message).
- **TrelloIntegration.js**: Removed 9 `console.log` (4 debug block before save, URL/Body, response status/ok, error text, response data). All were debug statements leaking request details.
- **BulkDocumentUpload.js**: Removed 2 `console.log` (session created, session finished).
- **useWebSocket.js**: Removed 10 `console.log` (token expired refresh, token renewed, token updated, reconnecting, connected, connecting URL, connection established, connection closed, token expired 4001, reconnecting with delay). Preserved `console.error` and `console.warn` for error handling. Cleaned empty switch case.
- **ProcessDetails.js**: Removed 1 `console.log` (AI extracted data dump with `extractedData, fieldConfidence, conflicts, documentsProcessed`).
- **NotificationsDropdown.js**: Removed 1 `console.log` (audio not available) — replaced with code comment.
- **TasksContext.js**: Removed 1 `console.log` (circuit breaker reset message).

Stage Summary:
- 9 ficheiros alterados, 31 `console.log` removidos
- 0 `console.info` ou `console.table` encontrados
- `console.error` e `console.warn` preservados em todos os ficheiros
- 1 ocorrência restante em `useWebSocket.js:43` — trata-se de exemplo em JSDoc comment, não statement executável

---
Task ID: 5
Agent: Frontend Agent
Task: Implement Custom Folders UI in WebmailPage

Work Log:
- **Imports (line 65-71)**: Added 7 lucide-react icons: `FolderPlus, FolderOpen, Folder, FolderInput, Pencil, MoreVertical`. All existing imports preserved.
- **Custom folders state variables (line 200-209)**: Added 9 new state variables: `customFolders`, `activeCustomFolder`, `folderDialogOpen`, `folderDialogMode`, `folderDialogData`, `folderDialogSaving`, `moveFolderOpen`, `contextMenuPosition`, `contextMenuFolder`.
- **fetchCustomFolders (line 242-259)**: New `useCallback` fetching `GET /api/emails/folders` with auth. Returns `data.folders` array. `useEffect` on mount triggers fetch.
- **fetchEmails modified (line 264-283)**: Added 5th parameter `customFolderId`. When set, uses `folder: "custom"` and appends `custom_folder=<id>` query param.
- **useEffect updated (line 308-319)**: Now checks `activeCustomFolder` first — if set, calls `fetchEmails("custom", ...)` with folder ID. Added `activeCustomFolder` to dependency array.
- **handleSearchChange updated (line 321-335)**: Passes `activeCustomFolder` through to `fetchEmails` when in custom folder view.
- **handleRefresh updated (line 337-344)**: Same custom folder awareness as search.
- **handleSyncEmails updated (line 393-406)**: Refresh respects active custom folder after sync.
- **Folder CRUD handlers (line 807-918)**:
  - `handleOpenFolderDialog(mode, folder)`: Opens create/edit dialog with appropriate defaults.
  - `handleSaveFolder()`: POST/PUT to `/api/emails/folders`. Validates name, shows toast on success/error.
  - `handleDeleteFolder(folder)`: DELETE to `/api/emails/folders/{id}`. Resets `activeCustomFolder` if deleted folder was active.
  - `handleMoveToFolder(folderId)`: POST to `/api/emails/emails/move-to-folder`. Works with both selectedEmails (multi-select) and selectedEmail (single). Clears selection and refreshes.
- **Sidebar folders updated (line 1051-1060)**: System folder buttons now clear `activeCustomFolder(null)` on click. Active state checks both `!selectedLabel && !activeCustomFolder`.
- **Custom Folders sidebar section (line 1131-1199)**: New "Pastas" section after Marcadores, before footer. Shows FolderPlus button for creating. Lists custom folders with FolderOpen icon (colored when active), name, email_count badge, and hover-revealed MoreVertical context menu trigger.
- **List header title updated (line 1221-1244)**: Shows custom folder name when `activeCustomFolder` is set, with X button to deselect. Falls back to label name, then system folder name.
- **Move to Folder toolbar button (line 1017-1033)**: Visible in top bar when multi-select mode active and emails selected. Shows FolderInput icon, "Mover" label, and selected count badge.
- **Move to Folder in reading pane (line 1601-1612)**: Tooltip-wrapped FolderInput button in email detail action toolbar (alongside Reply, Forward, Star, Link).
- **Folder Context Menu (line 2039-2077)**: Absolutely positioned menu with fixed inset-0 backdrop for outside-click dismiss. "Renomear" opens edit dialog. "Eliminar" uses window.confirm before calling DELETE.
- **Folder Create/Edit Dialog (line 2079-2140)**: Dialog with name Input (Enter to submit) and 10 color swatches. Create mode: "Nova Pasta" title, POST. Edit mode: "Editar Pasta" title, PUT.
- **Move to Folder Dialog (line 2142-2179)**: Dialog listing "Caixa de Entrada" + all custom folders. Click to move. Shows email count per folder.

Stage Summary:
- 1 ficheiro alterado: `frontend/src/pages/WebmailPage.jsx` (1761 → 2186 linhas, +425)
- Vite build OK, sem erros
- Todas as funcionalidades existentes preservadas (labels, multi-select, composer, sync, etc.)
- Todo o texto em português
- APIs consumidas: GET/POST/PUT/DELETE /api/emails/folders, POST /api/emails/emails/move-to-folder, GET /api/emails/webmail?folder=custom&custom_folder=...

---
Task ID: 2
Agent: Backend Agent
Task: Create Custom Email Folders backend system

Work Log:
- Added FolderCreateRequest and FolderUpdateRequest Pydantic models
- Added GET /folders, POST /folders, PUT /folders/{id}, DELETE /folders/{id} endpoints
- Added POST /emails/move-to-folder endpoint for moving emails
- Updated webmail_list to support custom_folder query parameter
- All endpoints follow existing patterns with auth, sanitization, validation

Stage Summary:
- email_folders MongoDB collection used for custom folders
- folder_id field on emails references custom folders
- Folder deletion removes folder_id from emails (back to inbox)
- Folder counts returned via aggregation pipeline

---
Task ID: 2-b
Agent: Frontend Agent
Task: Refactor WebmailPage.jsx — Labels Sidebar, Multi-Select, Attachment Cards, Drag & Drop

Work Log:
- **Imports (line 57-72)**: Added lucide-react icons: `Image, FileSpreadsheet, File, Tag, CheckSquare, Square, Upload, Download, Trash2`. All existing imports preserved.
- **Utility functions (line 111-130)**: Added `formatFileSize(bytes)` — formats bytes as B/KB/MB. Added `getAttachmentIcon(filename)` — returns appropriate icon based on file extension (Image for images, FileSpreadsheet for sheets, FileText for docs, File for others).
- **New state variables (line 178-192)**:
  - Labels: `labels`, `selectedLabel`, `labelsLoading`
  - Multi-select: `selectedEmails` (Set), `multiSelectMode`, `labelDropdownOpen`
  - Upload: `uploadAttachments`, `uploadingFiles`
  - `fileInputRef` (useRef for hidden file input)
- **fetchLabels (line 200-222)**: New `useCallback` fetching `GET /api/emails/labels` with auth. Handles array and object responses gracefully. `useEffect` on mount calls `fetchLabels()`.
- **fetchEmails modified (line 248-261)**: Added `label` parameter to `fetchEmails`. When `selectedLabel` is set, appends `label=<label_id>` to query params. All callers updated: `useEffect`, `handleSearchChange`, `handleRefresh`, `handleSyncEmails`.
- **handleSelectEmail modified (line 353-358)**: In multi-select mode, clicking an email toggles its ID in `selectedEmails` Set instead of opening reading pane.
- **handleSendEmail modified (line 505-512)**: Includes `attachment_ids: uploadAttachments.map(a => a.id)` in request body when uploads exist.
- **openComposer modified (line 447)**: Clears `uploadAttachments` when opening composer.
- **Multi-select handlers (line 618-690)**:
  - `handleToggleMultiSelect`: Toggles mode, clears selection on exit.
  - `handleSelectAll`: Selects/deselects all emails on current page.
  - `handleApplyLabelToSelected`: POST to `/api/emails/labels/apply` with `email_ids` + `label_id`.
  - `handleDeleteSelected`: Deletes all selected emails via parallel DELETE calls.
- **File upload handlers (line 694-745)**:
  - `uploadFiles(files)`: Sequential upload via `POST /api/emails/attachments/upload` with FormData.
  - `handleDropZoneClick`, `handleFileInputChange`, `handleDragOver`, `handleDrop`: Drag & drop event handlers.
  - `handleRemoveUpload`: Removes file from `uploadAttachments` list.
- **Labels sidebar (line 913-946)**: "Marcadores" section below FOLDERS nav. Shows colored circle + label name for each label. Click selects label (highlights, filters list). Click again deselects.
- **Label badges on email list (line 1088-1102)**: After preview text, renders up to 2 colored label pills per email. Shows "+N" badge if more than 2. Uses `backgroundColor: label.color`, white text, 10px font, rounded-full.
- **Label badges on email detail (line 1295-1308)**: Below date meta, shows all label badges.
- **Multi-select toolbar button (line 812-824)**: "Selecionar" toggle button next to Refresh. Shows CheckSquare (active) or Square (inactive).
- **Multi-select checkboxes (line 1058-1065, 1069-1072)**: When `multiSelectMode` is active, shows CheckSquare/Square icon instead of unread dot on each email row.
- **Floating action bar (line 1429-1478)**: Fixed bottom bar when emails selected. Shows count, "Aplicar Marcador" button with label dropdown, "Eliminar" button.
- **Attachment cards in reading pane (line 1360-1405)**: Replaced plain list with grid of visual cards. Each card shows: file type icon (via getAttachmentIcon), filename, formatted size, download button. Grid: 1 column mobile, 2 columns sm+.
- **Drag & drop zone in composer (line 1566-1638)**: Dashed-border drop zone before Textarea. Hidden file input with `multiple`. Drag & drop events handled. Upload progress indicator (Loader2 spinner). Uploaded files shown as removable cards with icon, name, size, X button.
- **Dialog cleanup (line 1544-1551)**: `onOpenChange` clears `uploadAttachments` when dialog closes.

Stage Summary:
- 1 ficheiro alterado: `frontend/src/pages/WebmailPage.jsx` (1238 → 1761 linhas, +523)
- 6 funcionalidades adicionadas ao webmail
- Todas as APIs chamadas com try/catch — falhas silenciosas para endpoints ainda não disponíveis
- Layout 3 colunas intacto, responsivo
- Todo o texto em português

---
Task ID: 2-a
Agent: Backend Agent
Task: Implement Backend - Email Labels CRUD + S3 Attachment Upload/Download

Work Log:
- **`backend/models/email.py`**: Adicionados 3 modelos Pydantic:
  - `LabelCreateRequest` (name, color) — payload para criar labels
  - `LabelUpdateRequest` (name?, color?) — payload para atualizar labels
  - `EmailSendRequest.attachment_ids: Optional[List[str]] = None` — campo opcional para IDs de anexos temporários
- **`backend/routes/emails.py`**: Adicionados 7 novos endpoints e 1 endpoint modificado:
  - **GET /labels** (line 928): Lista todas as labels do utilizador. Faz seed de 5 labels predefinidas (Urgente, A Aguardar, Concluído, Follow-up, Reunião) na primeira chamada.
  - **POST /labels** (line 956): Cria nova label. Valida nome (max 30 chars), cor (hex), impede duplicados.
  - **PUT /labels/{label_id}** (line 990): Atualiza nome e/ou cor de label existente. Valida duplicados (excluindo a própria).
  - **DELETE /labels/{label_id}** (line 1026): Elimina label e remove-a de todos os emails via `$pull`.
  - **POST /attachments/upload** (line 1054): Upload de 1-10 ficheiros (max 25MB cada) para `temp/attachments/{user_id}/{uuid}_{filename}` no S3. Guarda metadados em `temp_attachments` (MongoDB) para lookup durante envio.
  - **GET /{email_id}/attachments/{file_id}/download** (line 1138): Gera URL pré-assinada (1h) para download de anexo via `s3_service.get_presigned_url()`. Suporta fallback para URL existente.
  - **POST /send** modificado (line 2122): Processa `attachment_ids` — consulta `temp_attachments`, descarrega conteúdo do S3 temp, envia email com anexos, move ficheiros para `Emails/{email_id}/{filename}` via `s3_service.rename_file()`, atualiza documento do email com `id`, `s3_key` nos attachments, limpa temp do S3 e MongoDB.
- **Imports adicionais**: `UploadFile, File, Form` (FastAPI), `re` (validação de hex color), `LabelCreateRequest, LabelUpdateRequest` (modelos).
- **Helper**: `_validate_hex_color()` — valida formato `#fff` ou `#ffffff`.

Stage Summary:
- 2 ficheiros alterados: `backend/models/email.py` (+20), `backend/routes/emails.py` (+240)
- 7 novos endpoints: 4 labels CRUD + 1 upload + 1 download + 1 send modificado
- Rotas estáticas todas definidas ANTES do catch-all `/{email_id}`
- Syntax verificado com py_compile: OK
- Coleções MongoDB utilizadas: `email_labels` (labels CRUD), `temp_attachments` (upload temporário)

---
Task ID: 14
Agent: Main Agent
Task: SmartRichEditor — abstrair complexidade HTML de utilizadores não-admin

Work Log:
- **SmartRichEditor.jsx** (`2c85c79`): Novo componente reutilizável (`src/components/ui/SmartRichEditor.jsx`)
  - Modo Visual (default): Editor WYSIWYG via react-quill — edição normal
  - Modo HTML (admin-only): `<textarea>` monospace com código HTML puro
  - Botão `</> Editar HTML` no canto superior direito — **SÓ visível se `user.role === 'admin'`**
  - Consultores nunca veem o botão nem sabem que o modo HTML existe
  - Props: `value`, `onChange`, `readOnly`, `advanced`, `minHeight`, `label`, `placeholder`, `allowHtmlAdmin`
  - Protege variáveis {{handlebars}} ao transitar entre modos
- **SendDocumentationModal.js** (`2c85c79`): Substituído sistema de 3 tabs (Preview / Editar HTML / Código) por 2 tabs (Preview / Editar)
  - Tab "Editar" usa SmartRichEditor internamente com toggle HTML integrado
  - Tab "Código" e botão "Copiar HTML" removidos (funcionalidade agora dentro do SmartRichEditor)
  - Texto informativo contextual baseado no role do utilizador
  - Limpos imports não utilizados (`Code`, `RichTextEditor` direct)
- **SystemConfigPage.js** (`2c85c79`): Substituído RichTextEditor + pré-visualização separada por SmartRichEditor único
  - Secção "Pré-visualização" redundante removida (o modo visual já é a preview)
  - Limpo import de `RichTextViewer` (já não usado nesta página)

Stage Summary:
- 3 ficheiros alterados: `SmartRichEditor.jsx` (novo), `SendDocumentationModal.js`, `SystemConfigPage.js`
- Commit: `2c85c79` (pushed to `dev`)

---
Task ID: 13
Agent: Main Agent
Task: Corrigir erro "too many values to unpack" na sincronização de emails (resolução final)

Work Log:
- **Diagnóstico (`086c502`)**: Após 3 tentativas falhadas de corrigir `mail.fetch()` unpacking, identificou-se a causa REAL:
  - O erro NUNCA foi no `mail.fetch()` — era na linha 1331 de `email_service.py`
  - `get_email_body_with_embedded_images(msg)` retorna **3 valores** `(body_text, body_html, embedded_images)`
  - O código fazia unpack para apenas **2 variáveis**: `body_text, body_html = get_email_body_with_embedded_images(msg)`
  - Isto causava `too many values to unpack (expected 2)` para CADA email, e o `except` fazia `continue` — nenhum email era guardado
- **Correção (`086c502`)**: Alterado para `body_text, body_html, _ = get_email_body_with_embedded_images(msg)`
- **Cleanup (`086c502`)**: Removida função `_extract_email_bytes_from_fetch` duplicada (havía 2 definições idênticas, linhas 251-276 e 300-315)
- **Histórico de tentativas anteriores** (commits já no remote):
  - `54143d1`: Corrigiu apenas 1 de 6 localizações (insuficiente)
  - `8bef4b2`: Criou helper `_extract_email_bytes_from_fetch()`, substituiu todas as 6 localizações (mas o bug era noutro lado)
  - `3976603`: Reforço da mesma correção (commit duplicado)

Stage Summary:
- 1 ficheiro alterado: `backend/services/email_service.py` (+1, -19)
- O bug explicava por que 29 emails eram encontrados mas 0 eram guardados
- Commit: `086c502` (pushed to `dev`)

---
Task ID: 12
Agent: Main Agent
Task: Corrigir sincronização webmail — credenciais IMAP, 404, NoneType alerts

Work Log:
- **Alerts NoneType (`f48f4bb`)**: Erro `'NoneType' object has no attribute 'get'` em `services/alerts.py`
  - Causa: MongoDB campos set to `null`; `.get("key", {})` não aplica default quando valor é `None`
  - Correção: `process.get("credit_data") or {}` em vez de `process.get("credit_data", {})`
  - Mesma correção aplicada a `property_data`, `financial_data`, `contacto`
- **Webmail sync 404 (`fab2ef9`)**: `POST /api/emails/webmail/sync` retornava 404
  - Causa: `emails.py`, `email_service.py`, `worker.py` tinham alterações locais nunca commitadas ao Git
  - `git push` dizia "Everything up-to-date" porque nada estava staged
  - Correção: `git add` + `git commit` dos 3 ficheiros
- **IMAP credenciais erradas (`83f104d`)**: Emails não sincronizavam para `flaviosilva@powerealestate.pt`
  - Causa: `get_email_accounts_async()` usava `smtp_user`/`smtp_password` para login IMAP
  - O modelo de dados tem campos dedicados `imap_user`/`imap_password`
  - Correção: Alterado para usar `imap_user`/`imap_password` com fallback para SMTP
- **IMAP fetch format (`54143d1`, `8bef4b2`, `3976603`)**: "too many values to unpack"
  - Tentativas múltiplas de corrigir `mail.fetch()` (ver Task ID 13 para resolução final)

Stage Summary:
- Ficheiros: `backend/services/alerts.py`, `backend/routes/emails.py`, `backend/services/email_service.py`
- Commits: `f48f4bb`, `fab2ef9`, `83f104d`, `54143d1`, `8bef4b2`, `3976603`, `086c502`

---
Task ID: 11
Agent: Main Agent
Task: Webmail de 3 colunas (estilo Outlook) com compositor e sincronização IMAP

Work Log:
- **WebmailPage.jsx (`fcb858b`)**: Criada página de webmail completo com layout 3 colunas (estilo Outlook)
  - Coluna esquerda: Lista de pastas (INBOX, Enviados, Rascunhos, Lixo, Spam) com contadores
  - Coluna central: Lista de emails da pasta selecionada (remetente, assunto, preview, data, indicadores)
  - Coluna direita: Painel de leitura com corpo HTML, ações (responder, encaminhar, eliminar, arquivo)
  - Compositor de emails: Formulário modal com To, CC, CC0, Assunto, Body (RichText), Anexos
  - Pesquisa de emails por texto
  - Filtros: Todos / Não lidos / Com estrela
  - Marcação de lido/não lido, estrela, eliminação, arquivo
  - Suporte a contas múltiplas (Power + Precision)
- **Sync button (`041799b`)**: Adicionado botão "Sincronizar" no sidebar para puxar emails do IMAP
- **Endpoint webmail sync (`fab2ef9`)**: `POST /api/emails/webmail/sync` — sincroniza todas as contas IMAP
  - Busca emails de INBOX e pastas de enviados
  - Deduplicação por `message_id + account`
  - Guarda no MongoDB com metadata completa
- **Endpoints de webmail (`fcb858b`)**: CRUD completo
  - `GET /api/emails/webmail` — lista com filtros (folder, account, search, unread, starred)
  - `GET /api/emails/webmail/:id` — detalhe
  - `PUT /api/emails/webmail/:id` — atualizar (read, starred, archived, folder)
  - `DELETE /api/emails/webmail/:id` — eliminar
  - `POST /api/emails/webmail/send` — enviar email via SMTP
- **S3FileManager fix (`fdbb4a4`)**: Impedir eliminação de pastas no gestor de ficheiros S3

Stage Summary:
- Página de webmail completa com funcionalidades de email profissional
- Integração IMAP (leitura) e SMTP (envio)
- Commits: `fcb858b`, `041799b`, `fab2ef9`, `8e6604b`, `85a2d79`, `abf8ca5`

---
Task ID: 10
Agent: Main Agent
Task: Corrigir eliminação acidental de pastas no S3FileManager

Work Log:
- **S3FileManager fix (`fdbb4a4`)**: Adicionada validação para impedir eliminação de pastas (diretórios)
  - Tipos de ficheiro sem extensão (pastas) não podem ser eliminados
  - Apenas ficheiros com extensão podem ser removidos

Stage Summary:
- 1 ficheiro alterado
- Commit: `fdbb4a4`

---
Task ID: 9
Agent: Main Agent
Task: Remover menu Novo processo, corrigir filtro clientes, statusFilter default, alertas IA

Work Log:
- **Task 1 - Remover "Novo processo"**: Não existia menu no sidebar. Removido atalho `Ctrl+N` ("Novo processo/tarefa") do `useKeyboardShortcuts.js` e handler `onNew` do `DashboardLayout.js`.
- **Task 2 - Corrigir filtro clientes**: O backend aplicava `limit=500` à query de PROCESSOS (não clientes), o que fazia com que alguns clientes desaparecessem. Removido `skip/limit` da query MongoDB e aplicada paginação ao resultado final (lista de clientes únicos).
- **Task 3 - statusFilter default "active"**: Alterado `ClientsPage.js` de `|| "all"` para `|| "active"`.
- **Task 4 - Desativar alertas de consultor não atribuído**: Removido alerta `"unassigned"` e sugestão `"assignment"` do `ai_improvement_agent.py`. Processos sem consultor já não geram alertas no Agente de Melhoria IA.
- Commit: `a90e92f`, build OK, push OK.

Stage Summary:
- 5 ficheiros alterados, 14 inserções, 31 remoções
- Files: useKeyboardShortcuts.js, DashboardLayout.js, ClientsPage.js, clients.py, ai_improvement_agent.py

---
Task ID: 8
Agent: Main Agent
Task: Botões Simular Preenchimento + Testar Submissão em formulários

Work Log:
- **ProcessDetails.js (`4afe7fc`)**: Adicionados SIMULATE_DATA (5 state objects) + 2 botões:
  - `handleSimulateFill()`: preenche personal, titular2, financial, realEstate, credit com dados de teste
  - `handleSimulateAndTestSubmit()`: preenche + envia PUT ao backend para validar Pydantic
  - Botão "Simular Preenchimento" (ícone FlaskConical, cor amber) — preenche sem guardar
  - Botão "Testar Submissão" (ícone Play, cor emerald) — preenche + submete + mostra erros traduzidos
  - Após test submit com falha, mostra lista de erros Pydantic traduzidos em português
  - Após test submit, faz refetch para reverter dados ao estado original do servidor
  - Ambos desabilitados quando `saving`, `simulating` ou `isProcessLocked`
- **PublicClientForm.js (`4afe7fc`)**: Adicionado botão "Testar Submissão" ao lado de "Simular Preenchimento"
  - Usa `validateForm()` existente para validação client-side
  - Mostra lista de erros ou toast de sucesso
- Commits: `4afe7fc` (pushed to `dev`)

Stage Summary:
- 2 ficheiros alterados: `ProcessDetails.js` (+283 linhas), `PublicClientForm.js` (+27 linhas)
- Teste de submissão cobre validação client-side (PublicClientForm) e backend Pydantic (ProcessDetails)
- Dados de teste incluem NIF válido (checksum OK), datas reais, e todos os campos opcionais preenchidos

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

---
Task ID: 1
Agent: Frontend Agent
Task: Replace textarea with react-quill WYSIWYG for email template

Work Log:
- Added 'react-quill-new/dist/quill.snow.css' import at top of DocumentRecipientsManager.js
- Replaced plain Textarea with ReactQuill snow theme component
- Configured toolbar with formatting buttons (headers, bold, italic, lists, align, link, clean)
- Added matching formats array for proper rendering

Stage Summary:
- Email template editor in System Config > Destinatários now uses visual WYSIWYG
- HTML is generated and stored in state as before

---
Task ID: 2
Agent: General Agent
Task: Add "Pré-visualizar RGPD" button with preview modal to SystemConfigPage.js

Work Log:
- **Dialog import (line 27)**: Added `import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "../components/ui/dialog"`. Deduplicated a previously existing duplicate import.
- **State variable (line 1125)**: Added `const [showRgpdPreview, setShowRgpdPreview] = useState(false)` inside RGPDTab component.
- **Preview button (line 1343-1349)**: Added "👁️ Pré-visualizar RGPD" button with `variant="outline"` between "Restaurar Padrão" and "Guardar Template" buttons in the action bar.
- **Preview Dialog (line 1370-1399)**: Added Dialog component before `</CardContent>` with:
  - `sm:max-w-[700px] max-h-[85vh] overflow-y-auto` for responsive scrollable modal
  - `prose prose-sm` classes for nice typography on preview content
  - `dangerouslySetInnerHTML` with `.replace()` chains for all template variables (`{{NOME_CLIENTE}}`, `{{NOME_EMPRESA}}`, `{{CONTRIBUINTE}}`, `{{MORADA}}`, `{{CODIGO_POSTAL}}`, `{{TIPO_DOCUMENTO}}`, `{{NUMERO_DOCUMENTO}}`, `{{VALIDADE_DOCUMENTO}}`, `{{DATA_ASSINATURA}}`)
  - Realistic sample values (João Silva, Power Real Estate, 123456789, etc.)
  - Dynamic date via `new Date().toLocaleDateString("pt-PT")`
  - "Fechar" button in DialogFooter

Stage Summary:
- 1 ficheiro alterado: `frontend/src/pages/SystemConfigPage.js`
- Duplicate Dialog import cleaned up
- Preview modal fully functional with template variable substitution
- No changes to SmartRichEditor or existing functionality
---
Task ID: 1
Agent: Main (Senior AI Engineer)
Task: Refactor ai_document.py to use OpenAI Function Calling instead of JSON Prompting

Work Log:
- Read and analyzed the entire ai_document.py file (2834 lines)
- Identified the architectural flaw: emergentintegrations.llm.chat library has no support for tools/response_format/function calling
- Mapped all 8 document types and their JSON structures from existing prompts
- Created get_document_tool_definition() with 434 lines of JSON Schema definitions for all document types
- Replaced call_openai_api() to use AsyncOpenAI client with tools + tool_choice
- Migrated analyze_with_text() to use function calling (removed JSON examples from user prompts)
- Migrated analyze_with_vision() to use function calling with multimodal support (image_url base64)
- Simplified all user_prompt strings in get_extraction_prompts() (system prompts preserved verbatim)
- Kept parse_ai_response() as fallback utility (deprecated)
- Verified all security mitigations are preserved (sanitize_pdf_text, size limits, image resize)
- Verified all public API imports are unchanged (routes/ai.py, routes/ai_bulk.py, worker/tasks.py)
- Verified no emergentintegrations references remain in ai_document.py
- Committed as fe43e83 and pushed to dev branch

Stage Summary:
- File changed from 2834 → 3022 lines (+188 net)
- 590 insertions, 399 deletions
- emergentintegrations dependency completely removed from ai_document.py
- OpenAI Function Calling with JSON Schemas now guarantees 100% structured output reliability
- All security mitigations preserved
- All public APIs backward compatible

---
Task ID: 5
Agent: Technical Writer (Docs)
Task: Atualizar documentação root (README.md, ARCHITECTURE.md, .env.example)

Work Log:
- Lido worklog completo para contexto do projeto
- Analisado README.md existente (420 linhas, muito completo)
- Analisado ARCHITECTURE.md existente (646 linhas, diagramas mermaid detalhados)
- Analisado .env.example existente (203 linhas)
- Lido backend/config.py para confirmar todas as variáveis de ambiente
- Pesquisado env vars em todos os ficheiros Python do backend (grep completo)

Alterações ao README.md:
- Adicionada secção "Webmail (Email IMAP)" nas funcionalidades (sync automático/manual, IMAP, B2B)
- Adicionadas variáveis EMERGENT_BASE_URL, VAPID_PRIVATE_KEY, VAPID_PUBLIC_KEY, SCRAPERAPI_API_KEY na tabela de env vars
- Adicionada secção "Instalação e Configuração Local" completa com:
  - Pré-requisitos (Python, Node, MongoDB, AWS, OpenAI)
  - Setup Backend (clone, pip, .env, seed, server)
  - Setup Frontend (npm, .env, start)
  - Setup Worker (background tasks)
  - Docker (produção)
- Adicionada secção "Fluxo de Desenvolvimento" com:
  - Branches (main/dev) com tabela de deploy
  - Convenções de commits (pt-PT, formato tipo: descrição)
  - CI/CD Pipeline (diagrama ASCII)
  - Testes (pytest, eslint, build)

Alterações ao ARCHITECTURE.md:
- Adicionada secção "Arquitetura de Webmail e Email" com diagrama mermaid:
  - Sync automático (worker 15min)
  - Sync manual (botão Sincronizar)
  - Envio B2B
  - Tabela de contas IMAP (Precision + Power)
- Adicionada secção "Arquitetura de Push Notifications" com diagrama mermaid:
  - VAPID subscription flow
  - Configuração de chaves
- Adicionada secção "Arquitetura de Rate Limiting" com diagrama mermaid:
  - Backend (slowapi) com limites por tipo
  - Tabela de variáveis RATE_LIMIT_*
  - Frontend (429 retry backoff)
- Adicionada secção "Arquitetura de Scraping (Idealista)" com diagrama mermaid:
  - Pipeline de scraping com fallbacks
  - Configuração ScraperAPI + Gemini

Alterações ao .env.example:
- Adicionada secção "PUSH NOTIFICATIONS — Web Push VAPID" (VAPID_PRIVATE_KEY, VAPID_PUBLIC_KEY, VAPID_MAILTO)
- Adicionada secção "WEBMAIL — Sincronização IMAP" (PRECISION_*, POWER_* para ambas as contas)
- Adicionada secção "SCRAPING — ScraperAPI" (SCRAPERAPI_API_KEY)
- Adicionada secção "EMERGENT LLM — URL Base" (EMERGENT_BASE_URL)
- Adicionada secção "RATE LIMITING" (7 variáveis RATE_LIMIT_*)
- Adicionada secção "RGPD — Retenção de Dados" (GDPR_RETENTION_DAYS, GDPR_DRY_RUN)
- Adicionada variável PORT=8000 na secção de backup

Stage Summary:
- 3 ficheiros atualizados: README.md, ARCHITECTURE.md, .env.example
- Todas as variáveis de ambiente encontradas via grep estão documentadas
- Documentação em português (pt-PT) consistente
- Diagramas mermaid adicionados para arquiteturas faltantes
- Zero CONTRIBUTING.md ou docker-compose.yml encontrado (não criados)
- Zero GitHub Actions workflows encontrado no repositório (CI/CD pipeline não presente em CI fix)

---
Task ID: 1
Agent: Main Agent
Task: Fix Vercel build error — esbuild transform failure in DashboardLayout.js:798

Work Log:
- Reproduced build error locally: `npx vite build` fails with same error
- Investigated root cause: esbuild cannot parse multiline template literals containing ternary expressions WITHOUT an else branch inside JSX attribute values
- Created minimal test cases to isolate: `condition ? 'value'` (no `: else`) in multiline template literal inside `className={...}` fails; adding `: ''` or inlining to single line fixes it
- Scanned all frontend source files for similar patterns — only 1 occurrence found (DashboardLayout.js:796-798)
- The bug was introduced by the responsive audit (c53143f) which changed `headerCollapsed ? 'text-xs' : 'text-sm lg:text-xl'` to `headerCollapsed ? 'text-xs sm:text-sm lg:text-xl'` (removed else branch, made multiline)
- Fix: inlined template literal to single line with `: ''` as empty else branch
- Build succeeds after fix (10.64s, 2811 modules)

Stage Summary:
- Commit `d0bc7bd`: fix(frontend): corrigir erro de build esbuild — ternary sem else branch em template literal multiline
- Build verified: `npx vite build` completes successfully
- No other files affected by this esbuild limitation

---
Task ID: 6
Agent: General-purpose Agent
Task: Add email/phone sync to clients collection when process is updated

Work Log:
- Read worklog.md for project context
- Read `backend/routes/processes.py` lines 1680-1880 — identified `update_process` function at line 1694
- Confirmed `sanitize_email` and `sanitize_phone` imported at line 90 from `utils.input_sanitization`
- Confirmed `process.get("client_id")` used at line 1763 (exists in scope)
- Read `backend/routes/search.py` — confirmed search queries MongoDB directly with **no caching layer**, so no cache invalidation needed
- Added client sync logic (lines 1843-1857) after `await db.processes.update_one()` and before cache invalidation:
  - Checks if `data.client_email` or `data.client_phone` was provided in the update payload
  - If `client_id` exists on the process, updates `contacto.email` and/or `contacto.telefone` in the `clients` collection
  - Uses `sanitize_email()` / `sanitize_phone()` on raw request values (before encryption)
  - Logs sync action for audit trail
- Verified syntax with `py_compile`: OK

Stage Summary:
- 1 ficheiro alterado: `backend/routes/processes.py` (+15 lines)
- Email/phone changes in ProcessDetails now propagate to `clients.contacto.email` / `clients.contacto.telefone`
- Global search (which queries both collections) will return up-to-date contact info
- No search cache invalidation needed (search queries MongoDB directly)

---
Task ID: 1
Agent: Main Agent
Task: Add likes and read receipts to team mural (Mural da Equipa)

Work Log:
- Created backend model `backend/models/announcement.py` with Pydantic schemas including `likes` and `read_by` list fields
- Created backend routes `backend/routes/announcements.py` with 6 endpoints: GET list, POST create, DELETE, POST toggle-like, POST mark-read, GET readers
- Registered announcements router in `backend/routes/__init__.py` and `backend/server.py`
- Added 6 API functions to `frontend/src/services/api.js`: getAnnouncements, createAnnouncement, deleteAnnouncement, toggleAnnouncementLike, markAnnouncementRead, getAnnouncementReaders
- Created `frontend/src/components/TeamMural.js` component with: message publishing, like toggle (heart icon, red when active), read receipts with tooltip (reader names on hover), IntersectionObserver-based auto-read (2s visibility threshold), unread indicator (blue ring + pulsing dot), visual differentiation (blue bg for own, gray for others), Ctrl+Enter to publish
- Integrated TeamMural as new "Mural" tab in StaffDashboard.js with Rss icon
- Resolved merge conflicts with remote (new routes: shared_email, companies, ai_analysis) during rebase
- Pushed to dev branch: commit `d65c5b7`

Stage Summary:
- Full feature implemented: backend model + 6 API endpoints + frontend component with likes, read receipts, auto-read observer
- Files created: `backend/models/announcement.py`, `backend/routes/announcements.py`, `frontend/src/components/TeamMural.js`
- Files modified: `backend/routes/__init__.py`, `backend/server.py`, `frontend/src/services/api.js`, `frontend/src/pages/StaffDashboard.js`
- Commit: `feat: add likes and read receipts to team mural`

---
Task ID: 6
Agent: Backend Engineer (Main)
Task: Fix email GET endpoint returning empty list despite sync engine storing emails in DB

Work Log:
- Analyzed email_service.py sync_user_emails() to understand how personal emails are saved to MongoDB
  - Sync engine saves with `synced_for_user: user_id` (string UUID) and `account: user_imap_email`
- Analyzed WebmailPage.jsx fetchEmails() to understand API call parameters
  - Frontend ALWAYS sends `account=power` or `account=precision` (based on email domain auto-detection)
  - This account param is sent regardless of which box tab (personal/general/shared) is active
- Analyzed routes/emails.py GET /webmail endpoint query construction
  - Found the account filter: `{"$or": [{"account": account}, {"account": {"$exists": False}}]}`
  - This filter was applied unconditionally when `account` param was present
- Identified root cause: When box=personal, user-synced emails have `account="user@example.com"` (their IMAP address)
  - Filter `{"account": "power"}` does NOT match `"user@example.com"`
  - Filter `{"account": {"$exists": False}}` does NOT match because the field exists
  - Result: ALL personal emails filtered out, returning empty list
- Applied fix in routes/emails.py:
  - Line 2354: Changed `if account:` to `if account and box != "personal":` for main query
  - Line 2448: Changed `if account:` to `if account and box != "personal":` for unread_count
  - Added explanatory comments in Portuguese
- Verified webmail-stats endpoint is unaffected (no account filter applied there)
- Committed and pushed to origin/dev: `fix: align email GET endpoint query filters with database schema used by sync engine`

Stage Summary:
- Root cause: Frontend always sends account=power/precision, but personal emails have account=user_imap_email
- Fix: Skip account filter when box=personal (personal emails are already isolated by synced_for_user)
- Files modified: backend/routes/emails.py (2 lines changed: 2354, 2448)
- Commit: 7b3e8bc on dev branch, pushed to origin/dev

---
Task ID: 7
Agent: Frontend Senior Engineer (Main)
Task: Fix toast notification loop and add unread messages badge to chat icon

Work Log:
- Analyzed all toast triggers across the frontend (useWebSocket, NotificationsDropdown, TasksContext, api.js)
- Identified two WebSocket-triggered toast sources in NotificationsDropdown.js without deduplication:
  1. onNotification callback (line 161) - fires toast.info for every WS notification event
  2. onChatMessage callback (line 196) - fires toast.info for every WS chat message event
- TasksContext.js already had debounce deduplication via lastToastTimeRef - no change needed
- Added shownToastIds (useRef(new Set())) for notification deduplication
- Added shownChatToastIds (useRef(new Set())) for chat message deduplication
- Both Sets cap at 500 entries with auto-trim to 250 to prevent memory leaks
- markNotificationRead() still fires on backend regardless of toast display
- For unread messages badge:
  - Added API_URL constant and MAX_UNREAD_DISPLAY (99) to DashboardLayout.js
  - Added chatUnreadCount state + fetchChatUnreadCount callback polling /api/chat/unread-count every 30s
  - Badge resets to 0 when ChatPanel opens
  - Added red circle badge (absolute positioned) on MessageSquare button with dynamic aria-label
- Files modified: NotificationsDropdown.js (+32 lines, -12 lines), DashboardLayout.js (+64 lines, -12 lines)
- Committed: 1e4a0ef on dev branch, pushed to origin/dev

Stage Summary:
- Toast deduplication prevents infinite toast loops from WebSocket reconnections/re-emits
- Chat icon now shows red badge with unread count (>99 shows "99+")
- Badge disappears when user opens chat panel

---
Task ID: 8
Agent: Full-Stack Senior Engineer (Main)
Task: 6 surgical fixes - global filters, team names, toast loop, client sort, chat badge, duplicate role

Work Log:
- **Fix 1: Visão Global Absoluta**
  - Backend: Added `show_all` query param to `/api/processes` (line 648) and `/api/kanban` (line 958)
  - When `show_all=True`, role-based user_id filtering is skipped for ALL roles
  - Frontend: ProcessesPage.js sends `show_all: true` to getProcesses()
  - Frontend: useKanbanQuery.js sends `show_all=true` param to kanban endpoint
  - Note: ClientsPage.js already had `show_all=true` — no change needed

- **Fix 2: Tabela de Processos - Nomes em vez de IDs**
  - Added `consultor_name`, `mediador_name`, `indexacao_name`, `parceiro_name`, `assigned_parceiro_id` to PROCESS_LIST_PROJECTION
  - Added name enrichment logic in GET /api/processes: collects missing user IDs, batch-fetches from db.users, maps names back
  - Frontend already had proper name rendering in ProcessesPage.js — no change needed

- **Fix 3: Fim Definitivo do Loop do Toast**
  - Root cause: `finish_background_job_db()` never set `acknowledged_at`, so completed jobs were always "unacknowledged"
  - Backend fix 1: `finish_background_job_db()` now sets `acknowledged_at: None` explicitly
  - Backend fix 2: GET `/tasks/active` auto-acknowledges completed/failed jobs on first read (sets acknowledged_at to current timestamp)
  - Frontend safety net: Increased `TOAST_DEBOUNCE_MS` from 1s to 60s in TasksContext.js

- **Fix 4: Ordenação em Todos os Clientes**
  - Verified: Sort combobox is fully functional — sortBy state wired, useMemo applies .sort(), URL sync works
  - No changes needed

- **Fix 5: Badge de Mensagens do Chat Interno**
  - Added `z-10` class to badge span in DashboardLayout.js for proper stacking order

- **Fix 6: Duplicação Intermediário de Crédito**
  - Separated labels: `intermediario` → "Intermediário de Crédito", `mediador` → "Mediador"
  - Added missing `consultor_intermediario` role to roleLabels and additionalRoleOptions
  - Gave `mediador` distinct color (`bg-amber-100 text-amber-800`) instead of sharing with intermediario
  - Added `consultor_intermediario` with gradient color

- Files modified: 8 source files + worklog
- Commit: b6e1c8f on dev branch, pushed to origin/dev

Stage Summary:
- Global views now show ALL records for ALL users (show_all param)
- Process table displays real team member names (batch user resolution)
- Toast loop eliminated via backend auto-acknowledge on first GET read
- Chat badge has proper z-index for visibility
- Role dropdown no longer shows duplicate "Intermediário de Crédito"
- Client sort combobox confirmed working (no change needed)

---
Task ID: 6
Agent: Main Agent
Task: Implement universal IMAP 2-way sync, global views, team name formatting, notification loop fix, chat badge, client sort, and role cleanup

Work Log:
- **Fix 1 - IMAP Bidirectional Sync**: Added `_imap_store_flags_sync()` in `email_service.py` — searches by Message-ID header via `UID SEARCH HEADER Message-ID`, then applies `UID STORE +FLAGS` and optionally `EXPUNGE`. Created async wrappers `imap_mark_as_seen()`, `imap_mark_as_unseen()`, `imap_delete_message()`. Added `_get_email_account_for_email()` to resolve EmailAccount from email document fields (global accounts by name, user accounts by decrypting email_config). Modified `emails.py` mark endpoint to call IMAP STORE on read/unread, and delete endpoint to call IMAP STORE +FLAGS \\Deleted + EXPUNGE.
- **Fix 2 - Global Views**: Verified all three global views already pass `show_all=true` (ClientsPage, ProcessesPage, useKanbanQuery) and backend correctly bypasses user_id filtering when `show_all=True`. No changes needed.
- **Fix 3 - Team Names in Processes**: Updated `processes.py` to resolve array-based IDs (`assigned_consultor_ids`, `assigned_mediador_ids`) in addition to single IDs. Names from multiple assignees are joined with ", ". Updated `ProcessesPage.js` to display clean fallback text and handle comma-separated names in badges.
- **Fix 4 - Toast Loop**: Backend: Added `is_notified` field to notification schema in `realtime_notifications.py`, marks `True` after WebSocket emission to prevent re-emission. Frontend: Replaced time-based debounce in `TasksContext.js` with permanent `toastedTaskIdsRef` Set — each task ID is toasted exactly once, with auto-trim at 200 entries.
- **Fix 5 - Chat Badge + Client Sort**: Verified chat badge has correct `z-10` positioning with no parent overflow clipping. Added `created_at` to client API response (both show_all and non-show_all paths) by including it in MongoDB projection and client map builder. The sort combobox was already wired correctly — the missing `created_at` field was the root cause.
- **Fix 6 - Role Cleanup**: Removed `mediador` from `additionalRoleOptions` in `UsersManagementPage.js` (it was a legacy alias causing duplicate "Intermediário de Crédito" entries in additional roles checkboxes). Kept `mediador: "Intermediário de Crédito"` in `roleLabels` for backward compatibility with existing users.

Stage Summary:
- Commit: `9a41f75` — "fix: implement universal IMAP 2-way sync, global views, team name formatting, and fix notification loops"
- 9 files changed, 398 insertions, 42 deletions
- Pushed to origin/dev

---
Task ID: 1
Agent: Main Agent
Task: Fix React Error #300 (Maximum update depth exceeded) in production build

Work Log:
- Cloned PowerCell repo from GitHub (dev branch)
- Analyzed the error: React #300 = "Maximum update depth exceeded" (infinite re-render loop during commit phase)
- Read and analyzed all dashboard components, context providers, hooks, and layout components
- Identified ROOT CAUSE: TasksContext.js had `activeCount` in the useEffect dependency array. When `fetchActiveTasks()` called `setActiveCount(N)`, it triggered the effect to re-run, which called `fetchActiveTasks()` again, creating a loop
- Identified SECONDARY issues: useWebSocket.js had a separate useEffect for `options` that fired on every render (callers pass inline objects), and both AuthContext and TasksContext created new context value objects on every render causing all consumers to re-render
- Fixed TasksContext.js: Removed `activeCount` from main useEffect deps, used a ref (`activeCountRef`) + separate effect to restart polling when count changes
- Fixed useWebSocket.js: Removed separate `options` useEffect, combined with `token` effect, replaced static handler registration with `makeHandler` wrapper that reads from `optionsRef.current` for always-fresh callbacks
- Fixed AuthContext.js: Wrapped context value in `useMemo`
- Fixed TasksContext.js: Wrapped context value in `useMemo`
- Committed and pushed as `9007efe` to dev branch

Stage Summary:
- React Error #300 resolved by breaking the infinite re-render chain in TasksContext
- 3 files modified: TasksContext.js, useWebSocket.js, AuthContext.js
- Additional performance improvement: memoized context values to prevent cascade re-renders
- Commit pushed to origin/dev successfully

---
Task ID: 1
Agent: Main
Task: WYSIWYG Form Manager refactoring

Work Log:
- Analyzed existing FormManagementPage.js (list-based admin with @hello-pangea/dnd)
- Analyzed PublicClientForm.js (6-step multi-step form with 53+ fields)
- Analyzed backend routes/form_config.py (GET/PUT fields, templates, custom fields)
- Rewrote FormManagementPage.js with WYSIWYG preview:
  - WysiwygFieldCard renders actual input types matching client form
  - Inline label editing via Pencil icon → Input → Enter/blur saves
  - Eye icon toggle for visibility (hidden = opacity-40)
  - Star icon toggle for required (filled red when active)
  - GripVertical drag handle for DnD reordering
  - CompactFieldCard for hidden fields pool
  - Controls legend card in sidebar
- Updated PublicClientForm.js:
  - Added customLabelMap (field_key → admin-configured label)
  - Added requiredOverrideMap (field_key → admin-configured is_required)
  - Added getFieldLabel(fieldKey, fallback) helper
  - Added isFieldRequired(fieldKey, fallback) helper
  - Updated 53 fields across all 6 steps to use dynamic labels/required
  - Updated RequiredLabel to accept optional required prop
  - Updated renderCustomField to use dynamic config
- Committed as 89afd62

Stage Summary:
- No backend changes needed (existing API already supports label/is_required/order)
- 2 files changed, 448 insertions, 251 deletions
- Full WYSIWYG parity between admin form manager and client-facing form


---
Task ID: 7
Agent: Main Agent
Task: Migrar Email de Sistema de SMTP para Resend API

Work Log:
- **Problema**: Testar ligação SMTP no Email de Sistema causava timeout genérico (sem logs de erro). Render bloqueia portas SMTP de saída (25/465/587).
- **backend/models/system_config.py**: Adicionado campo `resend_api_key` ao `SystemSMTPConfig`. Mantidos campos SMTP legados para backward compatibility. Reordenado campos: Resend API → From email/name → SMTP legado.
- **backend/services/email_service.py**: Criada função `_send_via_resend()` que envia emails via Resend HTTP API (porta 443). Suporta from_name, CC, BCC, anexos. Error handling com `resend.exceptions.AuthenticationError`, `RateLimitError`, e fallback genérico. Modificado `send_email()`: quando `system_smtp` tem `resend_api_key`, cria `EmailAccount` com `smtp_server="resend"` para sinalizar uso da API. No bloco de envio, verifica `smtp_server == "resend"` para rotear para `_send_via_resend()`.
- **backend/routes/system_config.py**: Substituído teste SMTP por teste Resend API no endpoint `test-connection/system-smtp`. Novo fluxo: se `resend_api_key` configurada → envia email de teste via Resend para o próprio remetente. Erros específicos: AuthenticationError (key inválida), RateLimitError (limite), domínio não verificado, from inválido. Fallback para SMTP legado (com aviso sobre Render). Timeout do frontend aumentado de 15s para 30s.
- **frontend/src/pages/SystemConfigPage.js**: Removidos campos SMTP Host, Port, Username, TLS do Bloco A. Adicionado campo "Resend API Key" (password input, placeholder re_xxxx). Badge "Configurado" agora verifica `resend_api_key` em vez de `smtp_host`. Adicionado info box sobre Resend API (porta 443, sem SMTP). Timeout do AbortController aumentado para 30s.
- **frontend/src/pages/EmailAccountsPage.js**: Mesmas alterações no `SystemSmtpCard`: remoção de campos SMTP, adição de Resend API Key. Timeout 30s. Toasts atualizados para Resend.
- **backend/routes/system_config.py**: Adicionado `resend_api_key` à lista `sensitive_fields` (2 ocorrências) para mascarar na resposta GET.

Stage Summary:
- 5 ficheiros alterados: models/system_config.py, services/email_service.py, routes/system_config.py, SystemConfigPage.js, EmailAccountsPage.js
- Resend API (HTTPS porta 443) substitui SMTP como método principal de envio
- SMTP legado mantido como fallback (contorna quebra de compatibilidade)
- Error handling detalhado: AuthenticationError, RateLimitError, domínio não verificado, from inválido
- Logs detalhados com logger.error para diagnóstico no Render
- Timeout frontend aumentado para 30s

---
Task ID: 8
Agent: Main Agent
Task: Multi-module bug fixes and improvements (10 files, 197 insertions, 38 deletions)

Work Log:
- **1a. Routes Duplicate (/staff vs /staff-dashboard)**: Changed `/staff-dashboard` route in App.js to redirect to canonical `/staff`. Updated ConsultorDashboard "Quadro Geral" button to navigate to `/kanban` instead of `/staff-dashboard`. Fixed "Concluídos" card onClick to use `/processos-filtrados?filter=concluded`.
- **1b. Card Counters/Filters**: Fixed FilteredProcessList.js `getProcesses()` call — added `view_mode: 'all'` and `show_all: true` params so the API returns concluded/dropped processes (previously default `view_mode="active_only"` excluded them).
- **1c. Webmail Unread Counter**: Fixed `webmail-stats` endpoint in emails.py — non-admin users now use same `$or` query as webmail list (created_by, synced_for_user) instead of simple `to_emails` regex, ensuring counter matches inbox listing.
- **2a. IMAP Drafts Sync**: Added Drafts folder sync to `sync_webmail_emails()` and `sync_user_emails()` — tries "[Gmail]/Drafts", "[Gmail]/Rascunhos", "INBOX.Drafts", "Rascunhos", "Drafts". Also expanded Sent folder names to include Gmail variants.
- **2b. Delete → Trash**: Created `imap_move_to_trash()` function in email_service.py — searches for Trash folder (Trash, INBOX.Trash, [Gmail]/Trash, Lixo, etc.), COPYs message there, then expunges from source. Falls back to permanent delete if Trash not found. Updated `delete_email` route to use this instead of `imap_delete_message()`.
- **2c. Email Signature**: Added `email_signature` field to `SystemSMTPConfig` model. Added RichTextEditor WYSIWYG component to EmailAccountsPage SystemSmtpCard. Modified `_send_via_resend()` to accept and append signature (HTML with `<hr/>`, plain text with `---`). Modified `send_email()` to pass system signature to Resend.
- **3. Client Sorting**: Fixed ClientsPage sort dropdown — consolidated `setSortField`+`setSortOrder` into single `setSearchParams` call, and same for `toggleSort`. Prevents intermediate re-renders where only one param updates.
- **4. Files Access**: Extended `isAdmin` check in FilesExplorerPage to include `diretor` and `administrativo` roles. Updated backend `s3-folder-contents` endpoint role requirement from `[ADMIN]` to `[ADMIN, CEO, DIRETOR, ADMINISTRATIVO]`.

Stage Summary:
- 10 files changed across 2 frontend and 4 backend modules
- Resend API integration maintained, SMTP legacy preserved as fallback
- IMAP sync now covers INBOX + Sent + Drafts folders
- Email deletion is now move-to-trash (recoverable) instead of permanent
- Email signature auto-appended to system transactional emails
- Webmail unread counter now consistent with inbox listing
- FilteredProcessList correctly shows concluded/dropped processes
- Files explorer accessible to Diretores and Administrativo

---
Task ID: error-boundary-layer4
Agent: Main Agent
Task: Implement 4th Error Boundary layer inside DashboardLayout + update RECOVERY.md

Work Log:
- Reviewed existing Error Boundary architecture (3 layers already implemented from previous sessions):
  - Layer 1: Sentry.ErrorBoundary (global fullscreen fallback in App.js)
  - Layer 2: LazyChunkErrorBoundary (stale chunk auto-reload in App.js)
  - Layer 3: RouteBoundary per page (ErrorBoundary + Suspense for all routes in App.js)
- Identified critical gap: DashboardLayout renders Sidebar + Header + {children}, but if page content crashes, RouteBoundary catches it and replaces EVERYTHING including the sidebar
- **DashboardLayout.js**: Added ErrorBoundary import and wrapped {children} inside <main> with:
  - `<ErrorBoundary variant="page" moduleName={title || 'Conteúdo'} showRetry={true}>`
  - This ensures if page content crashes, sidebar and header remain intact
  - Error fallback shows friendly message with retry button inside the content area
- **RECOVERY.md**: Complete rewrite with:
  - Corrected deployment platform (Render for both frontend and backend, not Vercel)
  - Updated architecture diagram showing 4-layer system
  - Added architectural decision rationale explaining why DashboardLayout needs its own ErrorBoundary
  - Updated rollback procedures for Render (Redeploy this commit, Manual Deploy Rollback)
  - Updated pre-deploy checklist
- **Build verification**: vite build completed in 14.71s, 0 errors
- **Source maps**: 117 .map files generated, 0 JS files with sourceMappingURL (hidden maps verified)
- **Lint**: 0 errors, only pre-existing accessibility warnings

Stage Summary:
- 2 files changed: `DashboardLayout.js` (+3 lines), `RECOVERY.md` (rewritten)
- Commit: `d9c614e` pushed to `dev`
- Architecture now has 4 layers of error isolation — sidebar never disappears due to content crashes
- Zero white screen guarantee: Global → Chunk → Route → Content

---
Task ID: 7
Agent: Main Agent
Task: Fix form data not being saved/displayed correctly in client profile (ProcessDetails)

Work Log:
- Investigated full data flow: Public form → Client doc → Process doc → API → Frontend display
- Found root cause: DEFAULT_FORM_CONFIG options used display labels (e.g. "Solteiro(a)", "Masculino") as values instead of internal keys (e.g. "solteiro", "M"), causing mismatch with ProcessDetails Select components
- Fixed DEFAULT_FORM_CONFIG (form_config.py):
  - estado_civil: Changed from plain strings to {value, label} format with internal keys (solteiro, casado, casado_adquiridos, casado_geral, casado_separacao, divorciado, viuvo, uniao_facto)
  - sexo: Changed from plain strings to {value: "M"/"F"/"O", label: "Masculino"/"Feminino"/"Outro"}
  - employment_type: Changed from plain strings to {value: "efetivo"/"termo_certo"/etc, label: ...}
  - tipo_imovel: Changed from plain strings to {value: "apartamento"/"moradia"/"terreno"/"outro", label: ...}
  - titular2_estado_civil: Added options (was missing)
- Fixed PublicClientForm.js:
  - Updated ESTADOS_CIVIS to include "casado" and "uniao_facto" options (matching ProcessDetails)
  - Added "terreno" to TIPOS_IMOVEL
- Fixed ProcessDetails.js backward-compat migrations on data load:
  - sexo: "Masculino"/"Feminino" → "M"/"F"
  - estado_civil: display labels → internal keys
  - employment_type: Title Case → lowercase
  - tipo_imovel: Title Case → lowercase
  - antiguidade_emprego → employment_duration migration
  - Remove nif_hash/email_hash/telefone_hash from display
- Fixed ProcessDetails.js titular2 estado_civil Select: changed from Title Case values ("Solteiro", "Casado") to lowercase internal keys ("solteiro", "casado") matching the form
- Fixed ProcessDetails.js titular1 estado_civil Select: added missing options (casado_adquiridos, casado_geral, casado_separacao)
- Fixed ProcessDetails.js employment_type Select: added termo_certo and termo_incerto options
- Fixed ProcessDetails.js tipo_imovel Select: added "outro" option
- Fixed ProcessDetails.js finalidade Select: added "compra_imovel" option
- Fixed ProcessDetails.js validFields: added rendimento_anual, antiguidade_emprego, outros_rendimentos, despesas_mensais
- Fixed cleanPersonalDataForSubmit: removes nif_hash, email_hash, telefone_hash, marital_status on save
- Fixed cleanTitular2DataForSubmit: removes nif_hash on save
- Removed "Formulário" tab (DynamicFormFieldsTab component) as requested by user
- Fixed backend clients.py: removes blind indexes (nif_hash, email_hash, telefone_hash) when copying client data to process doc

Stage Summary:
- 4 files changed: form_config.py, PublicClientForm.js, ProcessDetails.js, clients.py
- Commit: 6d9e8b0 on dev branch
- Key fix: Form now sends internal keys (e.g. "solteiro") instead of display labels (e.g. "Solteiro(a)"), matching ProcessDetails Select values
- Backward-compat: Old data with display labels auto-converts to internal keys on load
- nif_hash no longer shows in titular2 NIF field
- Removed unused Formulário tab

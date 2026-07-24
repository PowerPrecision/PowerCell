# Auditoria Frontend — PowerCell (React + Tailwind + Shadcn UI)

**Autor:** Staff Frontend Engineer / UX-UI Audit
**Âmbito:** `frontend/src` (React 18 + Vite + Tailwind CSS + Shadcn/Radix UI + TanStack Query)
**Objetivo:** Diagnosticar estabilidade, manutenibilidade e consistência visual **antes** de qualquer redesign. Nenhum ficheiro de código foi alterado nesta fase — auditoria só de leitura.

> Todos os números abaixo vêm de pesquisas `ripgrep`/leitura direta de ficheiros nesta base de código, nesta data. São contagens reais, não estimativas.

---

## Resumo Executivo

O projeto tem uma **fundação de design system sólida** (tokens Shadcn em `tailwind.config.js` + `index.css`, ~55 primitivas Shadcn instaladas, TanStack Query, um padrão "tabela desktop + card mobile" já validado em produção). O problema não é a fundação — é a **adoção inconsistente** dela:

- Quase **56% dos ficheiros** (143/256) usam classes de cor Tailwind "cruas" (`bg-blue-500`, `text-gray-500`, etc.) em vez dos tokens semânticos (`bg-primary`, `text-muted-foreground`), o que obriga a **~51 regras de "patch" `!important`** em `index.css` só para o dark mode não ficar ilegível.
- Existem **dois sistemas de toast em paralelo** (Sonner, ativo, e Radix `use-toast`, montado em lado nenhum) — 4 pontos do código (incluindo `services/api.js`, usado por praticamente todos os pedidos HTTP) mostram notificações que **nunca aparecem no ecrã**.
- **~5.000 linhas de código morto** em 9 páginas órfãs (nunca importadas em `App.js`), incluindo `StaffDashboard.js` (1022 linhas) e `MediadorDashboard.js` (470 linhas).
- **Nenhum padrão único de layout de página**: pelo menos 7 convenções diferentes de padding/max-width para o mesmo tipo de página, e 10+ combinações diferentes de breakpoints para a mesma UI de "linha de KPIs".
- Padrões de UI repetidos à mão em vez de reutilizados: `StatCard`/`StatusBadge` reimplementados em 4–7 sítios diferentes; `formatCurrency` definido em 7 ficheiros; nenhum `useDebounce` partilhado (3+ cópias quase idênticas); validação de NIF divergente entre formulários.

Nada disto é catastrófico isoladamente, mas em conjunto explica por que "mexer numa coisa parece partir outra" — o sistema de design existe, mas não está a ser aplicado como fonte única de verdade.

---

## 1. Design Tokens & CSS

**Ficheiros analisados:** `frontend/tailwind.config.js`, `frontend/src/index.css` (898 linhas), `frontend/src/App.css`, `frontend/components.json`, `frontend/src/contexts/ThemeContext.js`, `frontend/src/contexts/AuthContext.js`.

### 1.1 O que está bem feito

- `tailwind.config.js` segue a convenção Shadcn `new-york` corretamente: todas as cores (`background`, `foreground`, `card`, `primary`, `secondary`, `muted`, `accent`, `destructive`, `border`, `input`, `ring`, `chart-1..5`) são `hsl(var(--token))`, com um único ponto de definição.
- `index.css` define **um único** bloco `:root` (tema claro) + `.dark` (tema escuro) + `.theme-precision` (variante de marca por empresa, aplicada via `AuthContext.applyBrandTheme()`, **não morta**, ligada corretamente a `document.documentElement.classList`).
- `App.css` está vazio (comentário `/* Empty - all styles in index.css */`) — não há uma segunda fonte de tokens a competir com `index.css`. ✅ nenhuma duplicação de `:root`/`--primary` fora deste ficheiro.
- Existem boas práticas de acessibilidade já implementadas: `:focus-visible`, `prefers-reduced-motion`, `min-height/width: 44px` para touch targets, `@media print` dedicado.

### 1.2 Problemas encontrados

#### 🔴 Crítico — Cores "cruas" da paleta Tailwind competem com os tokens semânticos

| Métrica | Valor |
|---|---|
| Linhas com `bg-gray-*`, `text-gray-*`, `bg-blue-*`, `text-blue-*`, `bg-red-*`, `text-red-*`, `bg-green-*`, `text-green-*`, `bg-amber-*`, `text-amber-*`, `bg-yellow-*`, `text-yellow-*` | **2.292** em **143 ficheiros** (56%) |
| Linhas com tokens semânticos (`bg-primary`, `text-primary`, `bg-muted`, `text-muted-foreground`, `bg-card`, `border-border`) | **~2.621** em **177 ficheiros** (69%) |
| Rácio cru : semântico | **≈ 0,87 : 1** — mesma ordem de grandeza |

Piores ofensores: `pages/ClientPortal.jsx` (171 ocorrências), `components/S3FileManager.js` (98), `pages/BackgroundJobsPage.js` (64), `components/portal/SimulatorCH.jsx` (59), `components/PDFAnnotationViewer.js` (52).

**Consequência direta:** como estas classes cruas não seguem as variáveis CSS do tema, o dark mode teve de ser "remendado" com **~51 regras `!important`** em `index.css` (ex.: `.dark .bg-blue-100 { background-color: hsl(...) !important; }`, `.dark .text-gray-500 { color: ... !important; }`, `.dark [class*="bg-amber-50"] { ... !important; }`). Isto é frágil: qualquer nova classe `bg-blue-*`/`text-gray-*` introduzida no futuro **não terá dark mode correto** até alguém lembrar de adicionar mais uma regra a este ficheiro central.

#### 🟠 Alto — Duplicação literal dentro de `index.css`

Existem **dois blocos quase idênticos** de `::-webkit-scrollbar` / `::-webkit-scrollbar-track` / `::-webkit-scrollbar-thumb` no mesmo ficheiro (linhas ~308–325 e ~605–623), um dos quais sobrepõe-se ao outro sem necessidade.

#### 🟡 Médio — Tamanhos de fonte micro (`text-[9px]`, `text-[10px]`, `text-[11px]`)

**302 ocorrências em 68 ficheiros** de tamanhos de texto abaixo de 12px como valores arbitrários (não como escala do tema). Piores casos: `S3FileManager.js` (31), `VisitsPage.js` (17), `KanbanCard.jsx` (16), `ProcessDetailsModal.jsx` (15). Isto não é só uma questão de tokens — é diretamente relevante para a legibilidade em utilizadores com baixa literacia digital (identificado também no relatório de UX anterior).

#### 🟢 Baixo — Hex codes e `style={{}}`

- Hex arbitrário **dentro de `className`** (ex. `bg-[#123456]`): **0 ocorrências** — não é problema.
- Hex fora de className (mapas de cor de bancos, gráficos, canvas): **150 linhas**, sobretudo justificadas (`StatisticsPage.js` `COLORS = [...]`, `ProcessTimeline.js` paleta de labels, `PublicClientForm.js` cores de marca de bancos).
- `style={{...}}` inline: **101 ocorrências**, concentradas em `PDFAnnotationViewer.js` (18), `WebmailPage.jsx` (9), `ClientPortal.jsx` (9) — na maioria justificadas (cor dinâmica, canvas, progress bar), mas nenhuma convenção documentada de "quando é aceitável usar style inline".
- Espaçamento em pixels arbitrário (`mt-[17px]`, `w-[300px]`, etc.): **287 ocorrências** (214 fora de `components/ui/`) — na maioria são larguras de diálogo/scroll-area/touch-target justificáveis, não um problema sistémico.

---

## 2. Componentes Base (Shadcn UI vs. componentes à mão)

**Ficheiros analisados:** `frontend/src/components/ui/*` (55 ficheiros), `components/`, `components/admin/`, `components/dashboard/`, `components/kanban/`, `App.js`, `services/api.js`.

### 2.1 O que está bem feito

- Adoção **forte e real** das primitivas core do Shadcn: `Button` (138 ficheiros importadores), `Badge` (112), `Card` (111), `Input` (87), `Label` (74), `Dialog` (71), `Select` (67). A maioria dos "Modais" customizados (`CreateProcessModal`, `CPCVModal`, `kanban/*Modal`) usa corretamente `Dialog` por baixo — não há um segundo sistema de modais concorrente, exceto um caso isolado.

### 2.2 Problemas encontrados

#### 🔴 Crítico — Dois sistemas de toast em paralelo, um deles "morto" na prática

- **Sonner** (`sonner` npm package) é o sistema ativo: montado em `App.js` (`<Toaster>` de `components/ui/sonner`), usado em **108 ficheiros**.
- **Radix/Shadcn toast** (`components/ui/toast.jsx` + `toaster.jsx` + `hooks/use-toast.js`) continua a ser chamado em **4 pontos do código**: `services/api.js` (usado por praticamente todo o tratamento de erros HTTP da app), `pages/DiagnosticsPage.js`, `pages/AuditTrailPage.js`, `components/admin/ProcessMigrationTab.js`.
- **O componente `<Toaster>` do Radix (`toaster.jsx`) nunca é montado em lado nenhum da aplicação** (zero imports fora de si próprio). Isto significa que estes 4 pontos de código chamam `toast(...)` e **a notificação nunca é desenhada no ecrã** — falhas silenciosas de UX, incluindo em erros de API genéricos.

#### 🟠 Alto — Duplicação de padrões "StatCard" e "StatusBadge"

O mesmo conceito visual (cartão com ícone + valor + rótulo) está implementado de forma independente em pelo menos 4 sítios com APIs ligeiramente diferentes:

| Componente | Ficheiro | Assinatura |
|---|---|---|
| `StatCard` | `components/dashboard/DashboardShared.js` | `{ icon, iconColor, bgColor, value, label, onClick }` |
| `StatCard` | `components/admin/AdminPageShared.js` | `{ title, value, icon, color }` |
| `FinanceStatCard` / `KpiCard` | `pages/FinanceDashboard.js` | Duas variantes próprias |
| `MigrationStatCard` | `pages/RGPDMigrationPage.js` | Outra variante própria |

O mesmo acontece com `StatusBadge` (mapa estado → cor): reimplementado em `DashboardShared.js`, `RGPDAdminPage.js`, `ClientRegistrationsAdminPage.js`, `DocumentChecklist.js`, `TempLinksManager.js`, e em `FinanceDashboard.js` — este último nem sequer usa o componente `<Badge>` do Shadcn, usa um `<span>` à mão.

O badge de prioridade "Alta" (vermelho, com `Flame` e `animate-pulse`) está copiado quase byte-a-byte em `KanbanCard.jsx`, `ClientsPage.js` (duas vezes) e reaparece em `ProcessesPage.js`/`FilteredProcessList.js`.

#### 🟠 Alto — Sem componente `<Spinner>` partilhado

**119 ficheiros** usam `animate-spin` de forma independente (109 deles com `<Loader2 className="h-4 w-4 animate-spin" />` copiado à mão). Existem dois ajudantes parciais (`LoadingSpinner` em `DashboardShared.js`, `LoadingState` em `AdminPageShared.js`, este último nem usa o componente `Skeleton`), mas nenhum é a norma da aplicação.

#### 🟡 Médio — ~14 primitivas Shadcn instaladas e nunca usadas

`drawer.jsx`, `command.jsx`, `form.jsx`, `hover-card.jsx`, `menubar.jsx`, `navigation-menu.jsx`, `pagination.jsx`, `resizable.jsx`, `slider.jsx`, `toggle-group.jsx`, `aspect-ratio.jsx`, `carousel.jsx`, `context-menu.jsx`, `input-otp.jsx` têm **zero importadores** fora de si próprios. Não são "erros", mas são peso morto no bundle/manutenção — e nalguns casos (`drawer`, `command`, `context-menu`) são exatamente os componentes que o relatório de UX anterior recomendou para simplificar filtros e menus, portanto já estão instalados e prontos a usar.

#### 🟢 Baixo — `skeleton.jsx` vs `skeletons.jsx`

Não é um conflito técnico (nomes de ficheiro diferentes, ambos usados — `skeleton.jsx` por 4 ficheiros, `skeletons.jsx` por 9), mas o nome quase idêntico é uma armadilha fácil para novos membros da equipa confundirem qual importar.

---

## 3. Consistência de Layout

**Ficheiros analisados:** `frontend/src/layouts/DashboardLayout.js` (869 linhas), 15+ páginas representativas, `ClientPortal.jsx`, `PublicClientForm.js`, `components/admin/AdminPageShared.js`.

### 3.1 O que está bem feito

- Existe **uma única** shell autenticada (`DashboardLayout`) com sidebar + cabeçalho fixo + `<main>`, usada por todas as páginas internas do CRM — não há 5 layouts concorrentes para o mesmo caso de uso.
- O `<main>` da shell já define um padding-base consistente: `p-4 lg:p-6 pb-24 md:pb-6` (o `pb-24` no mobile existe de propósito para não ficar atrás do `MobileBottomNav`).

### 3.2 Problemas encontrados

#### 🔴 Crítico — Não existe um "PageHeader" padrão; ~50 páginas reinventam o título

- Existe um `PageHeader` reutilizável em `components/admin/AdminPageShared.js`, mas só é consumido por **3 páginas** (`RGPDAdminPage`, `RGPDMigrationPage`, `ClientRegistrationsAdminPage`).
- As restantes ~50 páginas fazem uma de quatro coisas diferentes: (a) só usam a prop `title` da `DashboardLayout` (aparece no cabeçalho fixo, pequeno); (b) criam o seu próprio `<h1 className="text-2xl font-bold ...">` dentro do conteúdo (duplicando o título); (c) usam `CardTitle` como título de página; (d) não têm título nenhum (`AdminDashboard`, `ConsultorDashboard` não passam `title` à layout).
- Variações encontradas na mesma "mesma coisa": `text-xl` vs `text-2xl`, `text-gray-900` vs `text-foreground`, `<h1>` vs `<h2>` (Leads usa `<h2>`).

#### 🔴 Crítico — Padding de página duplicado ("double padding")

Como o `<main>` da layout já aplica `p-4 lg:p-6`, páginas que voltam a aplicar padding próprio ficam com **padding a dobrar**:

- `SettingsPage.js` → wrapper `"p-4 md:p-6"` sobre o padding da layout.
- `StatisticsPage.js` → `"space-y-4 md:space-y-6 p-4 md:p-6"`.
- Outras páginas (`BranchPerformancePage`, `IdealistaImportPage`) têm o mesmo padrão.

Identificaram-se pelo menos **7 convenções diferentes** de wrapper de página logo a seguir a `<DashboardLayout>`: `"space-y-6"` (mais comum), `"space-y-4 md:space-y-6"`, `"p-4 md:p-6"`, `"space-y-4 md:space-y-6 p-4 md:p-6"`, `"w-full max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-6"` (Finance), sem wrapper nenhum (Leads/Templates/Properties), e `max-w-4xl mx-auto space-y-6` (Profile).

#### 🟠 Alto — Nenhuma política de largura máxima de conteúdo

`container mx-auto` só aparece em **3 páginas autenticadas** (praticamente não é convenção). Os `max-w-*` usados como "moldura" de página variam livremente: `max-w-7xl` (Finance, BranchPerformance), `max-w-5xl` (FinanceSettings — órfã), `max-w-4xl` (Profile, PendingItemsList, RGPD). A maioria das páginas de lista/dashboard não tem largura máxima nenhuma (conteúdo esticado a 100%). Não há uma decisão de produto documentada sobre quando o conteúdo deve ser "full-bleed" vs. "centrado com largura máxima".

#### 🟠 Alto — Grelhas de KPI/estatística com breakpoints inconsistentes

Mais de 10 padrões diferentes de grelha responsiva para o mesmo tipo de UI ("linha de cartões KPI"), por exemplo:

- `grid-cols-2 lg:grid-cols-4 gap-4` (AdminDashboard)
- `grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-3` (ConsultorDashboard)
- `grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-3` (StaffDashboard, *skeleton* — diferente da versão real da mesma página!)
- `grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4` vs `... gap-4 md:gap-6` (duas variantes na mesma `FinanceDashboard.js`)
- `grid-cols-2 sm:grid-cols-5 gap-3` (VisitsPage), `grid-cols-2 md:grid-cols-5 gap-4` (UnifiedLogsPage/ImportErrorsPage), `grid-cols-2 md:grid-cols-4 gap-4` (ExpiringDocumentsDashboard)...

Isto é o "cada página faz à sua maneira" mencionado no pedido de auditoria, confirmado com evidência concreta.

#### 🟡 Médio — Três sistemas de layout coexistem por desenho, mas sem partilha de convenções

`ClientPortal.jsx` e `PublicClientForm.js` não usam `DashboardLayout` (correto, são fluxos diferentes: portal de cliente e registo público) — mas cada um usa o seu próprio padding (`px-4 sm:px-6 lg:px-10 py-8` vs `container mx-auto px-4 py-8`) e cor de cabeçalho, sem nenhuma variável ou token partilhado entre os três "mundos" de layout.

---

## 4. Configurações Duplicadas & Código Morto

**Ficheiros analisados:** `App.js`, `hooks/`, `hooks/queries/`, `hooks/mutations/`, `contexts/`, `utils/`, `package.json`.

### 4.1 Páginas órfãs (nunca importadas em `App.js` nem em lado nenhum)

**~4.960 linhas de código morto** confirmadas com zero importadores em toda a `frontend/src`:

| Ficheiro | Linhas | Nota |
|---|---:|---|
| `pages/StaffDashboard.js` | 1022 | Substituída por `ConsultorDashboard` na rota `/staff` |
| `pages/IdealistaImportPage.js` | 699 | Substituída por `HtmlImportModal` dentro de `LeadsKanban` |
| `pages/FinanceSettingsPage.js` | 698 | Rota redireciona para `/system-admin`; lógica já vive em `components/admin/FinanceTab.jsx` |
| `pages/ClientRegistrationsAdminPage.js` | 764 | Substituída por `ClientRegistrationsPage` |
| `pages/EmailSearchPage.jsx` | 576 | Sem rota nem import |
| `pages/MediadorDashboard.js` | 470 | Sem rota |
| `pages/ImportErrorsPage.js` | 460 | Nunca ligada |
| `pages/RegisterPage.js` | 225 | Sem rota `/register` (login-only para staff) |
| `pages/DocumentsPage.js` | 48 | Stub, substituída por `FilesExplorerPage.jsx` |

### 4.2 Hooks e componentes mortos

| Ficheiro | Importadores externos | Estado |
|---|---:|---|
| `hooks/useOnClickOutside.js` | 0 | **Morto** |
| `hooks/useScrollToElement.js` | 0 | **Morto** |
| `hooks/useUndo.js` | 0 | **Morto** |
| `components/UndoToast.js` | 0 | **Morto** |
| `hooks/queries/useClientRegistrationsQuery` | 1 (só a página órfã `ClientRegistrationsAdminPage`) | **Morto em cascata** |

### 4.3 Lógica duplicada em vez de centralizada

| Conceito | Utilitário partilhado existe? | Cópias locais encontradas |
|---|---|---|
| `formatDate` | Sim, `lib/utils.js` | **13 ficheiros** com a sua própria versão local (`RGPDPage`, `FilesExplorerPage`, `NotificationsPage`, `MyClientsPage`, `ClientDetailPage`, `S3FileManager`, `CPCVModal`, `TeamFeed`, etc.) |
| `formatCurrency` (EUR) | **Não existe em `utils/`** | **7 definições nomeadas** (`FinanceDashboard`, `FinanceSettingsPage`*, `FinanceTab`, `BranchPerformancePage`, `FilteredProcessList`, `ProcessSummaryCard`, `ProcessDetailsModal`) + **18 ficheiros** com `Intl.NumberFormat(...EUR...)` inline |
| `useDebounce` | **Não existe** | Padrão `setTimeout`/`clearTimeout` de 300ms copiado quase igual em `SmartClientSearch.jsx`, `SecondTitularCard.jsx`, `admin/ClientSearchTab.js` |
| Validação de NIF | Sim, `utils/validateNIF.js` (mais fraca — sem checksum) | **4 cópias locais com checksum mais forte** (`PublicClientForm.js`, `CPCVModal.js`, `RGPDPage.jsx`, `ClientRegistrationsAdminPage.js`*) — risco real de inconsistência: o formulário interno (`ProcessDetails`) usa a validação mais fraca, os formulários públicos usam uma mais forte |

*(ficheiros marcados com `*` são também páginas órfãs — a duplicação "desaparece" ao limpar código morto)*

### 4.4 Dependências npm sobrepostas

| Sobreposição | Pacotes | Evidência |
|---|---|---|
| Drag-and-drop | `@dnd-kit/core`, `@dnd-kit/sortable`, `@dnd-kit/utilities` **vs.** `@hello-pangea/dnd` | `@dnd-kit/*` tem **zero** imports em `src/` — o Kanban usa DnD HTML5 nativo; só `FormManagementPage.js` usa `@hello-pangea/dnd`. `@dnd-kit/*` parece ser dependência morta. |
| Tema | `next-themes` **vs.** `ThemeContext` próprio | `next-themes` só é usado dentro de `components/ui/sonner.jsx` (`useTheme` importado de `"next-themes"`); não existe nenhum `<ThemeProvider>` do `next-themes` montado em `App.js` — o toggle de dark mode real vem do `ThemeContext` próprio. Isto significa que o Sonner **pode não estar a receber o tema correto**. |
| Toast | `sonner` **vs.** `@radix-ui/react-toast` (+ Shadcn `toast.jsx`/`toaster.jsx`) | Ver secção 2.2 — Radix nunca é montado. |

### 4.5 O que NÃO é um problema

- Todos os 4 Contexts (`AuthContext`, `ThemeContext`, `TasksContext`, `UploadProgressContext`) estão ativamente em uso — nenhum órfão.
- Não foram encontrados grandes blocos de código comentado "esquecido" dentro de páginas vivas (o único bloco relevante em `ClientPortal.jsx` está claramente documentado como funcionalidade temporariamente desativada, com nota de produto).
- `date-fns` + `react-day-picker` e `quill` + `react-quill-new` são sobreposições aparentes mas justificadas (peer dependencies / papéis complementares).

---

## 5. Tabela de Problemas Críticos (para triagem)

| # | Problema | Severidade | Área | Esforço de correção |
|---|---|---|---|---|
| 1 | Toasts do Radix (`use-toast`) nunca aparecem no ecrã, incluindo em `services/api.js` | 🔴 Crítico | Componentes | Baixo — migrar 4 ficheiros para `sonner` |
| 2 | Ausência de `PageHeader`/padding padrão → duplicação de título e "double padding" | 🔴 Crítico | Layout | Médio — criar 1 componente + aplicar em ~50 páginas |
| 3 | 56% do código usa cor "crua" em vez de tokens → obriga a 51 patches `!important` no CSS global | 🔴 Crítico | Tokens | Alto — é transversal a quase toda a app |
| 4 | ~5.000 linhas de páginas órfãs no bundle/manutenção | 🟠 Alto | Código morto | Baixo — apagar ficheiros (confirmar com produto antes) |
| 5 | `formatCurrency`/`formatDate`/`useDebounce`/`validateNIF` duplicados e divergentes | 🟠 Alto | Duplicação | Médio — centralizar em `utils/`/`hooks/` |
| 6 | Grelhas de KPI com 10+ combinações de breakpoints diferentes | 🟠 Alto | Layout | Médio |
| 7 | `StatCard`/`StatusBadge` reimplementados 4–7 vezes | 🟠 Alto | Componentes | Médio |
| 8 | Sem `<Spinner>` partilhado (119 ficheiros com `animate-spin` à mão) | 🟡 Médio | Componentes | Baixo |
| 9 | `@dnd-kit/*` morto, `next-themes` mal ligado ao tema real | 🟡 Médio | Dependências | Baixo |
| 10 | ~14 primitivas Shadcn instaladas e nunca usadas | 🟢 Baixo | Componentes | Baixo (ou aproveitar no redesign) |
| 11 | Duplicação literal do bloco `::-webkit-scrollbar` em `index.css` | 🟢 Baixo | CSS | Trivial |

---

## 6. Plano de Ação — "Limpar a Casa" Antes do Redesign

Ordem pensada para minimizar risco: primeiro o que é seguro/reversível e destrava o resto (código morto, toasts), depois centralização de lógica, só depois consistência visual transversal (tokens, layout) que toca em mais ficheiros.

### Fase 0 — Preparação (sem código)
1. Validar com produto/negócio que as 9 páginas identificadas como órfãs (secção 4.1) estão mesmo descontinuadas antes de apagar (algumas podem ter lógica de negócio a reaproveitar, ex. `FinanceSettingsPage` → já migrada para `FinanceTab`).

### Fase 1 — Remover código morto (baixo risco, alto retorno de clareza)
2. Apagar as 9 páginas órfãs confirmadas + os componentes/hooks mortos (`UndoToast.js`, `useOnClickOutside.js`, `useScrollToElement.js`, `useUndo.js`, e o hook de query órfão `useClientRegistrationsQuery` — ou associá-lo a `ClientRegistrationsPage` se fizer sentido).
3. Remover `@dnd-kit/core`/`sortable`/`utilities` do `package.json` (zero utilização real).
4. Remover a duplicação de `::-webkit-scrollbar` em `index.css`.

### Fase 2 — Unificar o sistema de notificações (baixo risco, corrige bug real)
5. Migrar os 4 pontos que ainda chamam `hooks/use-toast` (`services/api.js`, `DiagnosticsPage`, `AuditTrailPage`, `ProcessMigrationTab`) para `sonner`.
6. Remover `components/ui/toast.jsx`, `toaster.jsx`, `hooks/use-toast.js` e a dependência `@radix-ui/react-toast` depois de confirmar zero utilizadores.
7. Corrigir a ligação de tema do `sonner.jsx` (atualmente lê `next-themes`, que não está montado) para consumir o `ThemeContext` real do projeto.

### Fase 3 — Centralizar lógica duplicada (médio risco, testar bem)
8. Criar/consolidar `utils/formatCurrency.js` e substituir as 7 definições locais + 18 usos inline de `Intl.NumberFormat`.
9. Reforçar `utils/validateNIF.js` com o algoritmo de checksum (já existente em 4 cópias) e apontar todos os formulários para essa única fonte — isto é também uma correção de bug de validação, não só limpeza.
10. Substituir os `formatDate` locais (13 ficheiros) pelas funções já existentes em `lib/utils.js`.
11. Extrair um hook `useDebounce` partilhado e aplicá-lo em `SmartClientSearch`, `SecondTitularCard`, `admin/ClientSearchTab`.

### Fase 4 — Consolidar componentes base repetidos (médio risco) — **done** (PR #594)
12. ✅ Implementação canónica de `StatCard` / `StatusBadge` em `components/shared/`; consumidores principais migrados (`AdminPageShared`, `FinanceDashboard`, `RGPDMigrationPage`, `RGPDAdminPage`, `DocumentChecklist`). `TempLinksManager` / restantes podem seguir o mesmo padrão.
13. ✅ `<Spinner>` em `components/ui/Spinner.jsx`; substituído nas páginas principais (Dashboards, RGPD, Finance, Settings, Statistics, checklist). Restantes ~100 usos podem migrar progressivamente.
14. Decidir se as ~14 primitivas Shadcn não usadas ficam reservadas para o próximo redesign — **ainda em aberto**.

### Fase 5 — Padronizar layout de página — **done** (parcial, PR #594)
15. ✅ `PageHeader` canónico em `components/shared/PageHeader.jsx` (+ re-export em AdminPageShared). Política: preferir título de conteúdo via `PageHeader`; evitar duplicar o mesmo `h1` + `DashboardLayout title`.
16. ✅ Wrapper oficial: `"space-y-6"` (sem padding extra). Double padding removido em `SettingsPage`, `StatisticsPage`, `WorkflowStatusesPage`, `BranchPerformancePage`.
17. Receitas oficiais de grelha de KPIs — **ainda em aberto** (ConsultorDashboard deixou de depender da grelha de 7 KPIs).
18. Política de largura máxima — **ainda em aberto**.

### ConsultorDashboard redesign (Progressive Disclosure) — **done** (PR #594)
- Zona 1: card full-width “Tarefas Pendentes” (prazos + tarefas + rascunhos)
- Zona 2: funil recharts clicável (Novo / Em Análise / Aprovado / Concluído)
- Zona 3: Tabs (Clientes, Mural/Feed, Novidades; docs/IA atrás de tabs)

### Fase 6 — Reforçar os tokens de cor (o mais transversal — fazer com o redesign, não antes)
19. Como esta é a mudança de maior superfície (143 ficheiros), **não tentar corrigir tudo de uma vez**: à medida que cada ecrã for redesenhado (conforme o plano de UX/UI já aprovado), substituir as cores cruas (`bg-blue-*`, `text-gray-*`) pelos tokens semânticos ou por variantes de `Badge`/`Alert` já existentes, e remover a regra `!important` correspondente em `index.css` assim que deixar de ser necessária.
20. Definir uma regra de linting (ESLint) que avise sobre `text-gray-`, `bg-blue-`, etc. fora de `components/ui/`, para impedir que a dívida volte a crescer depois da limpeza.

---

## 7. Notas Finais

- Esta auditoria não alterou nenhum ficheiro — é só diagnóstico.
- Recomenda-se executar as Fases 1–3 **antes** de começar o redesign visual (são risco baixo e destravam trabalho futuro). As Fases 4–6 podem, e talvez devam, ser feitas **em conjunto** com o redesign de UX/UI já proposto anteriormente, porque tocam exatamente nos mesmos ficheiros (Kanban, Dashboards, listas) — fazê-las em separado duplicaria esforço de QA.
- Nenhum dos problemas encontrados é um bloqueador de produção atual — a aplicação funciona; isto é dívida técnica de manutenibilidade e consistência, não bugs funcionais (com exceção do ponto 1, os toasts silenciosos, que é um bug real de UX).

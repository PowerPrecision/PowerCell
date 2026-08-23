# PowerCell - Sistema de Gestão de Processos de Crédito

## Descrição

Sistema CRM completo para gestão de processos de crédito imobiliário, clientes, documentação e automação (**v2.0 em Produção**). Inclui formulário público dinâmico com campos personalizáveis, motor de automação "No-Code", gestão UCR multi-cargo (vários papéis por empresa), webmail em tempo real, calendário de precisão, análise de documentos por IA, e dashboard financeiro.

## Tecnologias

- **Backend**: FastAPI (Python 3.12) + Motor (async MongoDB)
- **Frontend**: React 19 + Vite + Tailwind CSS 4 + Shadcn UI (New York style) + @hello-pangea/dnd
- **Base de dados**: MongoDB Atlas (via Motor async driver)
- **Armazenamento**: AWS S3 (pre-signed URLs)
- **Armazenamento (Factory)**: AWS S3, Local (filesystem), OneDrive (placeholder) — agnóstico via `storage_service.py`
- **Cache**: Upstash Redis (REST API, degradação graciosa)
- **Filas**: ARQ (Redis-based background worker)
- **IA**: OpenAI GPT-4o + Gemini Flash (análise de documentos)
- **Email**: SMTP transacional (SystemConfig) + IMAP sync (per-user + shared Google OAuth)
- **Monitorização**: Sentry (frontend + backend)
- **Acessibilidade**: axe-core (testes automáticos em dev)
- **CI/CD**: GitHub Actions (Node.js 24 + Python 3.12)
- **Deploy**: Render (backend) + Vercel (frontend)

## Estrutura do Projeto

```
PowerCell/
├── backend/
│   ├── server.py              # Entry point FastAPI + middleware
│   ├── config.py              # Variáveis de ambiente e validação
│   ├── database.py            # Ligação MongoDB (Motor, singleton lazy)
│   ├── routes/                # ~45 rotas da API
│   │   ├── admin.py           # CRUD utilizadores, workflow, stats, impersonate
│   │   ├── auth.py            # Login, refresh token, registo
│   │   ├── automation.py      # Motor de automação (regras)
│   │   ├── clients.py         # CRUD clientes, cursor pagination
│   │   ├── documents.py       # Thin stubs: upload/download/portal/S3 (lógica em services/document_*.py)
│   │   ├── emails.py          # Gmail sync, send-to-banks, rascunhos IA
│   │   ├── finance.py         # Dashboard financeiro, comissões
│   │   ├── form_config.py     # Config formulário + templates
│   │   ├── public.py          # Formulário público, registo clientes
│   │   ├── rgpd.py            # Consentimento RGPD, anonimização
│   │   ├── stats.py           # Estatísticas (com Redis cache)
│   │   └── ...
│   ├── services/              # Lógica de negócio (preferir editar aqui vs. routes/)
│   │   ├── auth.py            # JWT, password hashing (passlib)
│   │   ├── encryption.py      # Encriptação AES (Fernet) + Blind Indexing
│   │   ├── redis_cache.py     # Cache Redis com fallback
│   │   ├── workflow_engine.py # Motor de regras de automação
│   │   ├── s3_storage.py      # Pre-signed URLs, organização automática
│   │   ├── storage_service.py  # Factory Pattern: Local/S3/OneDrive adapters
│   │   ├── document_*.py      # Documents: resolve, portal, upload, move, OCR, auto-cat…
│   │   ├── process_*.py       # Processes: list, kanban, update, assignment, DSTI…
│   │   ├── ai_document_analyzer.py  # Análise de documentos com confiança
│   │   └── ...
│   ├── models/                # Esquemas Pydantic + modelos de dados
│   ├── worker/                # ARQ background worker
│   ├── middleware/             # Rate limiting (slowapi)
│   ├── utils/                 # Validação, sanitização, MIME
│   └── tests/                 # Unit + Integration + E2E tests
├── frontend/
│   ├── src/
│   │   ├── App.js             # Router + providers + lazy loading
│   │   ├── components/
│   │   │   ├── ui/            # Componentes Shadcn UI
│   │   │   ├── KanbanBoard.js # Quadro Kanban com drag-drop (@dnd-kit)
│   │   │   ├── S3FileManager.js # Explorador de ficheiros + IA (Analisar/Renomear)
│   │   │   ├── NotificationsDropdown.js  # Polling com backoff
│   │   │   ├── ImpersonateBanner.js      # Barra de impersonate
│   │   │   ├── GlobalUploadProgress.js   # Progresso global de uploads
│   │   │   ├── TasksDropdown.js          # Centro de operações
│   │   │   ├── UnifiedAuditTrail.js      # "Filme da Lead"
│   │   │   └── processDetails/           # Tabs/dialogs extraídos de ProcessDetails
│   │   │       ├── ProcessAssignDialog.jsx
│   │   │       ├── ProcessPersonalTab.jsx
│   │   │       └── …
│   │   ├── pages/             # ~50 páginas (lazy loaded)
│   │   │   ├── PublicClientForm.js       # Formulário público dinâmico
│   │   │   ├── AdminDashboard.js         # Dashboard admin
│   │   │   ├── ProcessDetails.js         # Hub do processo (híbrido TanStack)
│   │   │   ├── processDetails/           # Hydration, cleaners, payload seguro
│   │   │   │   ├── processDetailsHydration.js
│   │   │   │   ├── processFormCleaners.js
│   │   │   │   └── processUpdatePayload.js  # Bloqueia arrays vazios / documents wipe
│   │   │   ├── StaffDashboard.js         # Dashboard staff (consultor)
│   │   │   ├── ProcessesPage.js          # Os Meus Processos (/processos) + visão global
│   │   │   ├── MyClientsPage.js          # Os Meus Clientes (/meus-clientes)
│   │   │   ├── FinanceDashboard.js       # Dashboard financeiro
│   │   │   ├── KanbanPage.js             # Quadro Kanban
│   │   │   ├── ProfileSettingsPage.js    # Gestão permissões
│   │   │   ├── FormManagementPage.js     # Gestão formulário
│   │   │   ├── AutomationPage.js         # Motor automação No-Code
│   │   │   ├── WorkflowStatusesPage.js   # Gestão estados workflow
│   │   │   ├── ClientPortal.js           # Portal do cliente (magic link)
│   │   │   ├── RGPDPage.js               # Página pública de consentimento
│   │   │   └── ...
│   │   ├── hooks/             # Custom hooks
│   │   │   ├── useWebSocket.js  # WebSocket singleton + backoff
│   │   │   ├── queries/         # TanStack Query (ex.: useProcessFullData)
│   │   │   └── mutations/       # TanStack Mutations (ex.: useProcessMutations)
│   │   ├── contexts/          # React Context providers
│   │   │   ├── AuthContext.js   # JWT + UCR (effectiveRole / company_id canónico)
│   │   │   ├── TasksContext.js  # BG jobs: sticky toasts + circuit breaker
│   │   │   ├── UploadProgressContext.js
│   │   │   └── ThemeContext.js  # Light/Dark mode
│   │   ├── services/
│   │   │   └── api.js          # Axios + interceptors (429, X-Active-Role / X-Company-Id)
│   │   ├── utils/
│   │   │   ├── roleUtils.js          # Helpers de roles/permissões
│   │   │   ├── userProfiles.js       # UCR → company_id canónico (não o nome)
│   │   │   └── workflowStatuses.js   # KNOWN_PROCESS_STATUSES + buildStatusOptions (baseline estático + fallback p/ dropdown de estado)
│   │   └── layouts/
│   │       └── DashboardLayout.js # Sidebar + header
│   ├── vercel.json            # SPA rewrite + security headers
│   └── public/
├── .github/workflows/
│   └── ci.yml                 # CI/CD pipeline (Node 24 + Python 3.12)
├── memory/
│   └── PRD.md                 # Product Requirements Document
├── ARCHITECTURE.md            # Diagramas e padrões de design
├── CHANGELOG.md               # Histórico de versões
└── worklog.md                 # Registo de desenvolvimento
```

## Funcionalidades Principais

### Core
- Gestão de Processos de Crédito (CRUD completo com paginação)
- Gestão de Clientes e Leads com cursor pagination
- Upload e Gestão de Documentação (Storage agnóstico: S3 / Local / OneDrive via Factory Pattern)
- Quadro Kanban com drag-drop (@dnd-kit) e filtros (data, urgência)
- **Calendário de precisão** (`/calendario`): eventos com hora exacta (início/fim), edição e eliminação; vista mensal/semanal
- Dashboard e Estatísticas (com cache Redis)
- Sistema de Notificações em tempo real (WebSocket + polling fallback)
- Tarefas assíncronas com centro de operações (ARQ worker)
- **Administração de plataforma** (`/admin/organizacao`): empresas + utilizadores/UCR, exclusiva para `admin`/`ceo`

### Inteligência Artificial
- **Análise de documentos**: Extração automática de dados do CC, IRS, recibos vencimento
- **Confiança por campo**: Score 0.0-1.0 por campo extraído, alertas visuais para < 0.8
- **Auto-fill**: Sugestões automáticas de preenchimento com conflitos detetados
- **Titular 1 vs 2**: match automático contra os dois titulares do processo; se ambíguo, dialog no CRM (“Este documento é de quem?”)
- **Analisar / Renomear IA** (S3FileManager): restrito a gestão (`admin` / `CEO` / `diretor`); docs já analisados ficam com badge e são saltados
- **Organização automática**: Categorização e movimentação de ficheiros no S3
- **Rascunhos de emails IA**: Geração automática de emails quando faltam documentos
- **DSTI automático**: Cálculo da taxa de esforço a partir de dados financeiros extraídos
- **Conformidade PII**: Opt-out de treino de dados OpenAI habilitado

### Formulário Público Dinâmico
- Formulário multi-step (6 passos) com validação
- **Pré-visualização para consultores** (`/formulario-consultor`): Navegação livre pelo formulário sem preencher
- **Campos personalizáveis**: Admin pode criar campos de 6 tipos (texto, dropdown, checkbox, número, data, sim/não)
- **Editor de opções inline**: Para dropdowns e checkboxes
- **Templates de formulário**: 3 pré-definidos (Crédito Habitação, Refinanciamento, Crédito Pessoal) + personalizados
- **Pré-visualização de templates**: Ver como o formulário ficará antes de ativar
- Campos obrigatórios com indicador visual (* vermelho + "obrigatório")
- Rascunho automático (localStorage)

### Tarefas em background (UX)
- Toasts sticky no canto inferior direito (`TasksContext` + Sonner): loading → success/error no mesmo `id`
- **Não desaparecem** ao mudar de página; fecho apenas pelo X do utilizador
- Polling de `GET /api/tasks/active` com circuit breaker

### Ficha do processo (`ProcessDetails`)
- **Leitura**: `useProcessFullData` / `useProcessQuery` (TanStack Query) + hydration helpers
- **Escrita**: `useProcessMutations` (update processo/cliente, assign, atividades, prazos)
- **Payload seguro**: `sanitizeProcessUpdatePayload` — nunca envia `documents` / `onedrive_links` / arrays vazios que esmagariam dados no Mongo
- Tabs e dialogs parcialmente extraídos (`components/processDetails/*`)
- **Separador Resumo limpo**: só dados críticos do processo (Cliente, Financeiros, Imóvel, Crédito, Prazos) — sem atividades/histórico (Progressive Disclosure, ver `FRONTEND_GUIDELINES.md`)
- **Prioridade compacta**: deixou de ter um `Card` isolado no Resumo — vive como `DropdownMenu` + `Badge` dentro do `AssignmentContextCard` (coluna direita)
- **Separador Histórico**: timeline de fases + "Atividades Recentes" (`ScrollArea` com altura fixa) + formulário "Registar Atividade" atrás de um `Dialog` + "Filme da Lead" (auditoria unificada)

### Calculadoras (`/calculadoras`)
- **Calculadora de Prestações (Crédito Habitação)**: `components/calculators/MortgageSimulator.jsx` — simula a prestação mensal (sistema francês de amortização) a partir de Capital, Prazo e Taxa de Juro/Spread, com toggle "Incluir Seguros" (`Switch`) que revela progressivamente Seguro de Vida e Multirriscos
- Motor de cálculo isolado em `utils/mortgageCalculations.js` (reutilizado do simulador do Portal do Cliente, `components/portal/SimulatorCH.jsx`)
- Layout 2 colunas (Inputs / Resultado em destaque), tokens Shadcn (`bg-primary`, `text-muted-foreground`, etc.), valores monetários via `formatCurrency`
- Acesso rápido a DSTI e Risco de Crédito (dialogs já existentes) na mesma página

### Registo de Clientes / Onboarding
- **Registo público** cria **cliente** (+ checklist `mandatory_documents` do SystemConfig) — **não** cria processo de imediato
- Processo é criado automaticamente quando a documentação obrigatória está completa; copia `titular2_data` e faz dual-assign (consultor + intermediário)
- Tabela de registos mostra leads / clientes a aguardar docs; filtro "Todos" / "Com Processo" / "Sem Processo"
- Quando o processo é criado manualmente no CRM, usa a **1ª fase real do `workflow_statuses`**
- Link S3 automático ao criar processo: `s3://…/Documentação Clientes/Nome_Do_Cliente/`

### Os Meus Processos (`/processos`)
- `ProcessesPage` + `GET /api/processes/me` — apenas processos **atribuídos** ao utilizador (`mine_only`)
- Isolamento por empresa activa: o header `X-Company-Id` é o **id** do UCR; o backend também aceita o nome de exibição (UCRs legados)
- `X-Active-Role` / `X-Company-Id` vêm do AuthContext (`syncAuthContextHeaders`), não de sentinels escritos pela página
- **Filtros por defeito**: `view_mode=active_only` (exclui arquivo / terminais); toggle para incluir concluídos
- Filtros de estado, tipo e "Atribuído a" (AND/OR) na query string
- `/lista-processos` é a visão global (`GET /processes?show_all=true`)

### Os Meus Clientes (`/meus-clientes`)
- `MyClientsPage` — clientes associados ao utilizador autenticado
- **Filtros por defeito**: exclui status terminais nos processos do cliente
- **Toggle "Mostrar Concluídos"**: incluir processos inativos do portefólio
- Pesquisa com normalização de acentos (NFD)

### Dashboard
- **StaffDashboard**: Vista do consultor com processos sem atualização
- **AdminDashboard**: KPIs, funnel de conversão, atividade recente
- **FinanceDashboard** (admin/CEO): Comissões, performance, separação por áreas
- **Alerta de processos sem atualização**: Exclui processos concluídos, desistências e arquivados

### Administração
- **Dashboard operacional** (`/admin`): KPIs, funil, calendário, documentos, leads — dia-a-dia da operação (admin/CEO)
- **Área de configuração de plataforma** (`/admin/organizacao`): Empresas (`is_active` / soft-delete) + Utilizadores e acessos UCR (vários cargos por empresa, proteção do último acesso, cargos oficiais Parceiro e Indexação). Exclusiva para perfil activo `admin` ou `ceo`
- **Gestão de Perfis e Permissões** (`/configuracoes-perfis`): Controlo granular de páginas e ações por utilizador
- **Gestão do Formulário** (`/gestao-formulario`): Ativar/desativar campos, criar campos personalizados, gerir templates
- **Motor de Automação** (`/automation`): Regras "Se X, Então Y" sem código
- **Gestão de Estados do Workflow** (`/workflow-estados`): Cores, labels, ordem
- **Configurações do Sistema** (`/configuracoes` / `/system-admin`): RGPD, DSTI, emails, backups, notificações, **Integrações (SMTP Sistema, Storage Provider, Webmail Partilhado)**

### RGPD
- **Página pública de consentimento** (`/rgpd/:token`): Assinatura digital do cliente
- **Gestor de RGPD** (admin): Templates editáveis, exportação de consentimentos
- **Anonimização de dados**: Eliminação de PII conforme GDPR
- **RGPD Migration**: Ferramenta de migração para processos legados

### Backup e Restauro Seguro (RGPD)
- **Backup automático diário**: Pipeline que corre às 03:00 UTC, cria ZIP JSON por coleção e faz upload para S3
- **Restauro seguro de Dev** (`restore_dev_from_backup.py`): Restaura a BD de Desenvolvimento a partir do backup mais recente de Produção no S3
- **Arquitetura fail-safe**: A BD de Dev **nunca é modificada** se o backup estiver corrompido (ZIP inválido, JSON inválido, validação de integridade falhar)
- **Fluxo**: S3 → Download ZIP → Extrair JSON → Importar para coleções `_restore_temp_*` → Sanitização RGPD → Validação de integridade → Swap atómico → Recriar índices → Cleanup
- **Disponível via API** (`/api/admin/sync-database`) e **CLI standalone**

### Pipeline de Sanitização de Dados (Prod → Dev)
- **Sincronização direta** (`sync_prod_to_dev.py`): Cópia de Produção para Dev com anonimização total de PII
- **Anonimização por coleção**:
  - **Clientes**: Nome (mantém primeiro nome, ofusca apelido), email (mascara para `@powercell.dev`), NIF (gera NIF falso com dígito de controlo válido), telefone (baralha mantendo prefixo)
  - **Utilizadores**: Mantém email e password para login, anonimiza telefone
  - **Processos**: Remove links S3, limpa campos financeiros ultra-sensíveis (IBAN, salários)
  - **Propriedades**: Arredonda coordenadas para ~1km de precisão
- **Metadados de rastreabilidade**: Cada documento recebe `_sanitized_at`, `_sanitized_source` e flags de anonimização
- **Disponível via API** e **CLI standalone** com suporte a `PROD_MONGO_URL`, `PROD_DB_NAME`, `DEV_MONGO_URL`, `DEV_DB_NAME`

### Webmail (Email IMAP)
- **Sincronização em tempo real (v2.0)**: o background sync IMAP corre **no processo da API a cada 60s** (não no ARQ Worker). Cada email novo emite WebSocket `new_email` para a room do utilizador; o React Query invalida a cache (`staleTime: 60s`) e actualiza a lista **sem skeleton nem reload**
- **Sincronização manual**: Botão "Sincronizar" no WebmailPage para FETCH imediato de todas as pastas
- **Múltiplas contas**: Suporte a Precision Crédito e Power Real Estate (IMAP separado)
- **Seletor de conta no composer (role-based)**: O seletor "Conta:" (Precision/Power) só aparece para admin/CEO/diretor (`canUseGlobalAccounts`). Os restantes perfis (consultor, intermediário, administrativo, indexação) enviam obrigatoriamente pela conta pessoal (ou partilhada, no caso de Indexação) — o seletor é ocultado e o pedido usa `account=personal`. Erros de envio (ex.: 403 por falta de config pessoal) mostram a mensagem acionável do backend num toast alargado (8s).
- **Pastas padrão e personalizadas**: 5 pastas padrão (Inbox, Sent, Starred, Drafts, Trash) + pastas personalizadas criadas pelo utilizador
- **Per-user personal config**: Cada utilizador configura o seu IMAP/SMTP em Perfil > Config Webmail
- **Assinatura por empresa (role-aware)**: Cada user pode ter uma assinatura diferente por empresa (`user_company_roles.signature`) e ainda uma global (`users.email_signature`). O `send_email` resolve a assinatura pela **empresa ativa** da sessão (header `X-Company-Id`). Prioridade: (1) UCR da empresa ativa → (2) assinatura global do user → (3) UCR da empresa default → (4) UCR de qualquer empresa → (5) assinatura do sistema. O composer do Webmail mostra uma pré-visualização da assinatura que será anexada no envio.
- **Shared role accounts**: Indexação/Suporte usam conta partilhada global (Google OAuth ou IMAP)
- **System SMTP (Bloco A)**: Emails transacionais do sistema (documentação, alertas) via SMTP global configurado pelo Admin
- **Smart Threading**: Threading automático por In-Reply-To/References + tag `[Proc-{id}]` no assunto
- **Envio de emails B2B**: Envio de documentação para bancos com editor rich text (WYSIWYG)
- **Rascunhos automáticos IA**: Geração automática de emails quando faltam documentos
- **Factory Pattern Storage**: `storage_service.py` com adapters para S3, Local e OneDrive

### Documentos
- **Explorador S3**: Vista lista/grelha, preview lateral, renomear, mover
- **Organização automática IA**: Categorização por tipo (Financeiros, Identificação, etc.)
- **Anotações contextuais em PDFs**: 5 tipos de anotação (Nota, Questão, Aviso, Financeiro, Aprovação) em documentos, com resolução e estatísticas por processo
- **Enviar Documentação para Balcões (Email B2B)**: Envio de documentação para bancos com editor de texto rico (HTML), templates de email personalizáveis, gestão de destinatários BCC, validação de bloqueio por banco, e anexação automática de documentos
- **Links temporários**: Upload/download seguro por link único (sem login)
- **Explorador de Ficheiros** (`/ficheiros`): Página dedicada para navegação global no S3, com breadcrumb, pesquisa, upload, download, renomear, eliminar e criação de pastas. Acesso para consultores e intermediários (leitura e download), admin/CEO/diretor/administrativo (acesso total)

### Portal do Cliente
- **Magic Link**: Acesso sem password via link curto (~50 chars, short_id)
- **Visualização do processo**: Stepper de fases com cores dinâmicas, estado atual, consultor e mediador
- **Upload de documentos**: Upload categorizado com multi-ficheiro → marca pedido como **RECEIVED** / “Enviado”
- **Pedido de documentos**: Staff solicita documentos → cliente vê lista e responde
- **Upload pela equipa no CRM**: também marca o pedido correspondente como recebido no portal (`document_portal_fulfill`)
- **Documentos carregados**: Cliente vê histórico (pendente vs recebidos)
- **Checklist obrigatória**: definida só em SystemConfig (`mandatory_documents`) — sem listas hardcoded
- **Mapeamento S3**: uploads portal → pasta Index / categorias S3
- **Estado do RGPD**: card verde “RGPD Assinado” ou amarelo “RGPD Pendente”

### Perfis de Utilizador e Permissões

O sistema suporta os seguintes perfis (roles), cada um com permissões específicas de páginas e ações. Na **v2.0** o mesmo utilizador pode ter **vários cargos na mesma empresa** (UCR: índice `{user_id, company_id, role}`):

| Perfil | Páginas Acedidas | Ações Permitidas |
|-------|-------------------|------------------|
| **Admin** | Todas | Todas |
| **CEO** | Todas | Todas |
| **Diretor** | Dashboard, Kanban, Processos, Clientes, Docs, Calendário, Notificações, Stats, Imóveis, Minutas, Leads | CRUD processos/clientes, upload/delete docs, financeiros |
| **Consultor** | Dashboard, Kanban, Processos, Clientes, Docs, Calendário, Notificações, AI Insights, Imóveis, Minutas, Leads, Ficheiros (Explorador) | CRUD processos/clientes, upload docs, financeiros, imóveis |
| **Mediador/Intermediário** | Dashboard, Kanban, Processos, Clientes, Docs, Calendário, Notificações, AI Insights, Minutas, Ficheiros (Explorador) | CRUD processos/clientes, upload docs, financeiros |
| **Administrativo** | Dashboard, Kanban, Processos, Clientes, Docs, Calendário, Notificações, Registos, Validades | CRUD processos/clientes, upload/delete docs |
| **Indexação** | Kanban, Processos, Clientes, Docs, Notificações, **Meus Clientes** | Upload/delete/download docs, atribuir clientes, gerir tarefas, chat |
| **Parceiro** | Nenhuma (utilizador fantasma) | Cargo oficial UCR — visível na gestão de acessos; sem login operacional típico |
| **Cliente** | Nenhuma (acesso externo via Magic Link) | Upload/download docs |

#### Perfil INDEXACAO - Detalhes

O perfil de **Indexação** foi projetado para operadores focados na organização documental:

- **Páginas**: Acede a Kanban, Processos, Clientes, Documentos, Notificações e "Meus Clientes"
- **Não tem acesso a**: Dashboard, criar/editar clientes ou processos (dados base são **read-only**)
- **Funcionalidades permitidas**:
  - Upload, delete e download de documentos
  - Gestão de tarefas (criar, editar, completar)
  - Chat interno
  - Atribuição de utilizadores a processos (consultores, intermediários, indexação)
  - Atribuição de clientes
- **Proteção de dados**: O backend retorna HTTP 403 se o utilizador tentar editar dados base via API

### Segurança
- JWT com access token (2h) + refresh token (7d) com rotação segura
- Rate limiting por role (admin: 1000/min, consultor: 200/min, cliente: 100/min)
- Encriptação AES-128-CBC (Fernet) para dados sensíveis
- **Blind Indexing**: Hashes determinísticos (HMAC-SHA256) para pesquisa de dados encriptados
- DOMPurify para sanitização XSS
- Validação MIME type (magic bytes)
- Password strength validation (passlib)
- Input sanitization em todas as rotas da API
- Security headers: HSTS, CSP, X-Frame-Options, X-Content-Type-Options
- CORS fail-secure (sem wildcards)
- OpenAI PII opt-out (sem treino com dados)
- Impersonate control com restauro automático de sessão

#### Context Switcher / Impersonate
- **Admin visualiza como qualquer utilizador**: Gera novo JWT com a role do utilizador-alvo
- **Restauro automático**: O token original do admin é guardado no `localStorage` (`originalToken`)
- **Barra visual**: `ImpersonateBanner` exibe permanentemente o modo de visualização ativo
- **Terminar sessão**: Parar impersonate restaura automaticamente a conta de admin (via `/api/admin/stop-impersonate`)
- **Fallback em token expirado**: Se o token de impersonate expirar (401), o sistema restaura automaticamente a sessão original

#### Blind Indexing (Pesquisa de Dados Encriptados)

Para cumprir o RGPD, dados sensíveis como NIF, email e telefone são encriptados com Fernet (AES-128-CBC). No entanto, dados encriptados não são pesquisáveis diretamente. A solução é **Blind Indexing**:

```
┌─────────────────┐    ┌──────────────────────┐
│   NIF Original  │───▶│   Fernet Encrypt     │───▶ Armazenado encriptado
│   "123456789"   │    │   "ENC:xxxx..."       │
└─────────────────┘    └──────────────────────┘
         │
         ▼
┌─────────────────┐    ┌──────────────────────┐
│  HMAC-SHA256    │───▶│  nif_hash (índice)   │───▶ Pesquisável!
│  "a1b2c3..."     │    │  Único por NIF       │
└─────────────────┘    └──────────────────────┘
```

**Implementação:**
- `services/encryption.py`: `generate_nif_hash()`, `generate_email_hash()`
- Campos de hash: `nif_hash`, `email_hash`, `telefone_hash`
- Índices MongoDB em `*_hash`, nunca em dados encriptados

**Exemplo de query:**
```python
# Pesquisa por NIF
nif_hash = generate_nif_hash(nif)
client = await db.clients.find_one({"dados_pessoais.nif_hash": nif_hash})
```

### Arquitectura de Dados

#### Dedicated Collection Pattern (Histórico)

O histórico de processos NÃO é guardado em arrays embebidos no documento principal. Em vez disso, usa uma **coleção dedicada** (`history`) com documentos independentes:

```
┌─────────────────────────────┐     ┌─────────────────────────────┐
│     Collection: processes   │     │     Collection: history     │
├─────────────────────────────┤     ├─────────────────────────────┤
│ id: "proc-001"              │     │ id: "hist-001"             │
│ client_name: "João Silva"   │     │ process_id: "proc-001"      │
│ status: "em_analise"        │     │ user_id: "user-123"         │
│ ... (sem array history!)    │     │ action: "Alterou estado"    │
│                             │     │ field: "status"             │
│                             │     │ old_value: "clientes_espera"│
│                             │     │ new_value: "em_analise"     │
│                             │     │ created_at: "2024-01-15..." │
└─────────────────────────────┘     └─────────────────────────────┘
```

**Vantagens:**
- Evita limite de 16MB do MongoDB
- I/O otimizado (sem reescrever documento inteiro)
- Queries instantâneas via índice `process_id + created_at`
- Memory bloat eliminado nas listagens

### Arquitetura Agnóstica de Provedores

O sistema é totalmente independente de provedores de serviços:

```mermaid
flowchart TD
    Route["Rota da API<br/>(upload/download)"] --> StorageSvc["storage_service.py<br/>(Factory)"]
    StorageSvc --> Config["Lê provider de<br/>system_settings"]
    Config -->|aws_s3| S3["S3StorageAdapter<br/>(wraps S3Service)"]
    Config -->|local| Local["LocalStorageAdapter<br/>(/tmp/powercell_uploads)"]
    Config -->|onedrive| OD["OneDriveAdapter<br/>(placeholder)"]
    S3 --> S3API["AWS S3 / R2 / MinIO"]
    Local --> FS["Filesystem"]
    
    subgraph BlocoA["Bloco A: SMTP Sistema"]
        EmailRoute["send_email(force_system=True)"] --> SysSMTP["SystemSMTPConfig<br/>(system_settings)"]
        SysSMTP --> SMTP["SMTP Server<br/>(noreply@empresa.pt)"]
    end
    
    subgraph BlocoC["Bloco C: Webmail Partilhado"]
        SyncRoute["sync_shared_role_emails()"] --> SharedCfg["shared_role_email_configs<br/>ou system_webmail fallback"]
        SharedCfg --> IMAP["IMAP Server<br/>(indexacao@empresa.pt)"]
    end
```

**Configuração no Admin** (Definições > Integrações):
- **Bloco A**: SMTP Host, Port, Username, Password, From Email, TLS
- **Bloco B**: Provider (Local/S3/OneDrive) + credenciais condicionais
- **Bloco C**: IMAP Host, Port, Email/User, App Password

### Observabilidade
- Sentry SDK (frontend + backend) para monitorização de erros
- Redis health check no endpoint /api/health
- Testes de acessibilidade com axe-core (dev only)
- Audit trail unificado ("Filme da Lead")
- CI/CD com GitHub Actions (lint, build, testes)

### Resiliência
- **429 Retry com backoff**: API interceptor com 3 retries (2s → 4s → 8s + jitter), respeita `Retry-After`
- **Polling backoff**: Notifications polling escala de 30s → 60s → 120s → 5min em 429
- **Chunk error recovery**: `LazyChunkErrorBoundary` deteta stale deployments e faz reload automático
- **Circuit breaker**: TasksContext para polling de tarefas com falhas consecutivas
- **WebSocket singleton**: Uma ligação partilhada entre componentes com backoff exponencial

## API Endpoints Principais

### Públicos (sem autenticação)
| Método | Endpoint | Descrição |
|--------|----------|-----------|
| POST | `/api/public/client-registration` | Registo de cliente |
| GET | `/api/public/form-config` | Campos personalizados do formulário |
| GET | `/api/rgpd/{token}` | Status de consentimento RGPD |
| POST | `/api/rgpd/{token}/sign` | Assinar consentimento RGPD |
| GET/POST | `/api/upload/{token}` | Upload de documentos via link temporário |
| GET | `/api/download/{token}` | Download de documentos via link temporário |
| GET | `/api/health` | Health check |

### Admin (autenticação + role admin/ceo)
| Método | Endpoint | Descrição |
|--------|----------|-----------|
| GET/PUT | `/api/admin/users` | Gestão de utilizadores |
| GET/POST/PUT | `/api/admin/companies` | Gestão de empresas (`is_active` = soft-delete) |
| POST/DELETE | `/api/admin/users/{id}/roles` | Acessos UCR (vários cargos por empresa; recusa apagar o último) |
| POST | `/api/admin/impersonate/{id}` | Impersonate utilizador |
| POST | `/api/admin/stop-impersonate` | Parar impersonate |
| GET/POST/PUT/DELETE | `/api/documents/portal-requests/*` | Gestão pedidos documentos portal |
| GET | `/api/admin/workflow-statuses` | Estados do workflow |
| POST/PUT/DELETE | `/api/admin/workflow-statuses/*` | CRUD estados do workflow |
| GET/PUT | `/api/admin/form-config/fields` | Configuração do formulário |
| POST/DELETE | `/api/admin/form-config/custom-field` | Campos personalizados |
| GET/POST/DELETE | `/api/admin/form-config/templates/*` | Templates de formulário |
| GET/POST | `/api/admin/automation/rules` | CRUD regras de automação |
| GET/PUT | `/api/system-config/*` | Configurações do sistema |
| GET | `/api/admin/ai-training/stats` | Estatísticas de chamadas IA |

### Processos (autenticação + staff)
| Método | Endpoint | Descrição |
|--------|----------|-----------|
| GET | `/api/processes/me` | Os Meus Processos — atribuição ao user + empresa activa (`company_id` **ou** nome) |
| GET | `/api/processes` | Lista (visão global com `show_all=true` em `/lista-processos`) |

Headers obrigatórios de contexto UCR em todos os pedidos autenticados: `X-Active-Role`, `X-Company-Id` (id canónico; o backend aceita também o nome de exibição).

## Rotas Principais (Frontend)

| Rota | Componente | Descrição |
|------|-----------|----------|
| `/` | StaffDashboard / AdminDashboard | Dashboard principal (conforme role) |
| `/admin` | AdminDashboard | Dashboard **operacional** (admin/CEO) — KPIs, funil, calendário |
| `/admin/organizacao` | OrganizationAdminPage | **Configuração de plataforma** (admin/CEO) — Empresas + Utilizadores/UCR |
| `/system-admin` | SystemAdminPanel | Configuração técnica do sistema (admin/CEO; tabs técnicas só admin) |
| `/kanban` | KanbanPage | Quadro Kanban com drag-drop |
| `/processos` | ProcessesPage | **Os Meus Processos** (`GET /processes/me`) |
| `/lista-processos` | ProcessesPage | Todos os Processos (visão global) |
| `/processo/:id` | ProcessDetails | Detalhes do processo |
| `/clientes` | ClientsPage | Gestão de clientes |
| `/docs` | DocumentsPage | Documentação |
| `/calendario` | CalendarPage | Calendário de precisão (hora exacta, editar/eliminar eventos) |
| `/notificacoes` | NotificationsPage | Notificações |
| `/imoveis` | PropertiesPage | Imóveis |
| `/minutas` | DraftsPage | Minutas |
| `/leads` | LeadsPage | Leads |
| `/meus-clientes` | MyClientsPage | Os Meus Clientes |
| `/financeiro` | FinanceDashboard | Dashboard financeiro |
| `/calculadoras` | CalculatorsPage | Calculadoras (Prestação de Crédito Habitação, DSTI, Risco) |
| `/automation` | AutomationPage | Motor de automação No-Code |
| `/gestao-formulario` | FormManagementPage | Gestão do formulário |
| `/workflow-estados` | WorkflowStatusesPage | Gestão de estados do workflow |
| `/configuracoes-perfis` | ProfileSettingsPage | Gestão de perfis e permissões |
| `/definicoes` | SettingsPage | Definições pessoais do utilizador |
| `/configuracoes` | SystemConfigPage | Configurações do sistema (admin) |
| `/ficheiros` | FilesExplorerPage | Explorador de ficheiros S3 |
| `/webmail` | WebmailPage | Cliente de email |
| `/rgpd/:token` | RGPDPage | Consentimento RGPD (público) |
| `/formulario-consultor` | PublicClientForm | Pré-visualização do formulário |

## Configuração

### Variáveis de Ambiente

> Consulte o ficheiro [`.env.example`](.env.example) para a lista completa e organizada por categoria.

#### Backend — Obrigatórias
| Variável | Descrição |
|----------|-----------|
| `MONGO_URL` | URL de conexão MongoDB |
| `DB_NAME` | Nome da base de dados |
| `JWT_SECRET` | Chave secreta para JWT (mín. 32 caracteres) |
| `CORS_ORIGINS` | Origens permitidas (vírgulas, sem wildcards) |
| `ENVIRONMENT` | Ambiente: `production` / `development` |

#### Backend — Opcional (mas recomendado)
| Variável | Descrição | Predefinição |
|----------|-----------|--------------|
| `DSN_SENTRY_BACKEND` | DSN do Sentry (backend) | — |
| `SENTRY_ENVIRONMENT` | Ambiente Sentry | `development` |
| `AWS_ACCESS_KEY_ID` | Chave de acesso AWS S3 | — |
| `AWS_SECRET_ACCESS_KEY` | Chave secreta AWS S3 | — |
| `AWS_REGION` | Região AWS | `eu-north-1` |
| `AWS_BUCKET_NAME` | Nome do bucket S3 | — |
| `REDIS_URL` | URL de conexão Redis | `redis://localhost:6379` |
| `EMAIL_PROVIDER` | Provedor: `sendgrid` / `resend` / `smtp` | `sendgrid` |
| `EMAIL_API_KEY` | API key do provedor de email | — |
| `EMAIL_FROM` | Endereço de remetente | `noreply@powerealestate.pt` |
| `EMAIL_FROM_NAME` | Nome do remetente | `Power Real Estate...` |
| `OPENAI_API_KEY` | Chave API OpenAI (legado) | — |
| `EMERGENT_LLM_KEY` | Chave API LLM (GPT-4o/4o-mini) | — |
| `EMERGENT_BASE_URL` | URL base LLM (emergent) | `https://api.emergent.ai/v1` |
| `GEMINI_API_KEY` | Chave API Gemini | — |
| `ONEDRIVE_TENANT_ID` | Tenant ID do OneDrive | — |
| `ONEDRIVE_CLIENT_ID` | Client ID do OneDrive | — |
| `ONEDRIVE_CLIENT_SECRET` | Client Secret do OneDrive | — |
| `VAPID_PRIVATE_KEY` | Chave privada VAPID (Push) | — |
| `VAPID_PUBLIC_KEY` | Chave pública VAPID (Push) | — |
| `TRELLO_API_KEY` | API Key do Trello | — |
| `TRELLO_TOKEN` | Token do Trello | — |
| `TRELLO_BOARD_ID` | Board ID do Trello | — |
| `SCRAPERAPI_API_KEY` | API Key do ScraperAPI (Idealista) | — |

#### Backend — Sincronização Prod ↔ Dev (pipelines)
| Variável | Descrição |
|----------|-----------|
| `PROD_MONGO_URL` | URL MongoDB de Produção (fallback: `MONGO_URL`) |
| `PROD_DB_NAME` | Nome da BD de Produção (fallback: `DB_NAME`) |
| `DEV_MONGO_URL` | URL MongoDB de Desenvolvimento |
| `DEV_DB_NAME` | Nome da BD de Desenvolvimento |

#### Frontend (`.env`)
| Variável | Descrição |
|----------|-----------|
| `REACT_APP_BACKEND_URL` | URL do backend API |
| `REACT_APP_ENVIRONMENT` | Ambiente: `production` / `development` |
| `REACT_APP_VAPID_PUBLIC_KEY` | Chave pública para Push Notifications |
| `VITE_DSN_SENTRY_FRONTEND` | DSN do Sentry (frontend, preferido) |
| `VITE_SENTRY_DSN` | DSN do Sentry (frontend, legado) |

## Instalação e Configuração Local

### Pré-requisitos

- **Python 3.12+** com pip
- **Node.js 18+** (recomendado 24) com npm/yarn
- **MongoDB Atlas** (ou instância local) — connection string SRV
- **Conta AWS** (para S3) — opcional mas recomendado
- **Conta OpenAI** (para análise de documentos) — opcional

### Backend

```bash
# 1. Clonar o repositório
git clone https://github.com/powercell/powercell-crm.git
cd powercell-crm

# 2. Instalar dependências Python
cd backend
pip install -r requirements.txt

# 3. Configurar variáveis de ambiente
cp ../.env.example .env
# Editar .env e preencher MONGO_URL, DB_NAME, JWT_SECRET, CORS_ORIGINS

# 4. Executar seeds (dados de teste)
python seed.py

# 5. Iniciar o servidor
python server.py
# O servidor arranca em http://localhost:8000
```

### Frontend

```bash
# 1. Instalar dependências
cd frontend
npm install

# 2. Configurar variáveis de ambiente
# Criar .env na pasta frontend/ com:
#   REACT_APP_BACKEND_URL=http://localhost:8000
#   REACT_APP_ENVIRONMENT=development

# 3. Iniciar em modo desenvolvimento
npm start
# O frontend arranca em http://localhost:3000
```

### Worker (Background Tasks)

```bash
cd backend
python worker.py
# O worker lê da mesma BD e Redis, processando tarefas em fila
```

### Docker (Produção)

```bash
# Backend
cd backend
docker build -t powercell-backend .
docker run -p 8000:8000 --env-file .env powercell-backend

# Frontend (Vercel faz deploy automático)
# Basta fazer push para a branch main
```

## Credenciais de Teste

- **Admin**: admin@sistema.pt / admin
- **CEO**: pedroborges@powerealestate.pt / power2026
- **Consultor**: tiagoborges@powerealestate.pt / power2026

## Fluxo de Desenvolvimento

### Branches

| Branch | Propósito | Deploy |
|--------|-----------|--------|
| `main` | Produção | Render (backend) + Vercel (frontend) |
| `dev` | Desenvolvimento | Render (preview) + Vercel (preview) |

### Commits

- Mensagens de commit em **português (pt-PT)**
- Formato: `tipo: descrição curta`
- Tipos: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`
- Exemplo: `feat: adicionar sincronização de webmail`

### CI/CD Pipeline

```
Push para branch → GitHub Actions
├── Frontend: ESLint + Vite build → Vercel deploy
├── Backend: Flake8 + Pytest → Render deploy
└── Testes E2E: Playwright (front-end)
```

### Testes

```bash
# Backend — Unit + Integration
cd backend
pytest tests/ -v

# Backend — com cobertura
pytest tests/ --cov=. --cov-report=html

# Frontend — lint
npm run lint

# Frontend — build de produção
npm run build
```

## Deploy

- **Backend**: Render (Docker) — porta via `PORT` env var
- **Frontend**: Vercel — SPA rewrite com exclusão de `/assets/`
- **CI/CD**: GitHub Actions — ESLint + Vite build + Flake8 + Pytest

## Branches

- `main` - Produção
- `dev` - Desenvolvimento

## Proteção DEV vs PROD (ENVIRONMENT)

O sistema distingue DEV de PROD através da variável `ENVIRONMENT`. Em DEV (Render free tier, 512MB RAM), os serviços pesados são desativados para evitar OOM:

### Serviços condicionados por `ENVIRONMENT`

| Serviço | DEV (`!= production`) | PROD (`== production`) |
|---------|----------------------|------------------------|
| **Email Auto-Sync** (IMAP no processo da API) | ❌ Desativado | ✅ Ativo (cada **60s** + jitter; emite `new_email` via WebSocket) |
| **Webmail Sync** (`sync_webmail_emails`) | ❌ Retorna mock | ✅ Ativo |
| **Gov Scraper** (Playwright/Chromium) | ❌ Retorna mock | ✅ Ativo |
| **Portal Scraper endpoints** (`/fetch-financas`, `/fetch-seguranca-social`) | ❌ Retorna mock JSON | ✅ Ativo |
| **Scraper status** (`/scraper-status`) | ❌ Retorna `available: false` | ✅ Verifica Playwright |
| **Worker** (background scheduler) | ❌ Não arranca | ✅ Ativo |
| **Job Monitor** | ✅ Ativo | ✅ Ativo |
| **Backup Scheduler** | ✅ Ativo | ✅ Ativo |
| **CDC Audit Listener** | ✅ Ativo | ✅ Ativo |

### Ficheiros com guards ENVIRONMENT

- `backend/server.py` — Startup: Email Sync só arranca se `ENVIRONMENT=production`
- `backend/services/gov_scraper.py` — Lazy Playwright imports + ENV guard nas funções principais
- `backend/services/email_service.py` — `sync_webmail_emails()` retorna mock em DEV
- `backend/services/scheduled_tasks.py` — `auto_sync_emails()` e `run_email_auto_sync()` bloqueados em DEV
- `backend/worker.py` — `run_scheduled_tasks()` e `scheduler_loop()` bloqueados em DEV
- `backend/routes/portal.py` — Rotas `/fetch-financas`, `/fetch-seguranca-social`, `/scraper-status` retornam mock em DEV

### Nota sobre `ENVIRONMENT`

**Obrigatório** configurar `ENVIRONMENT=production` no Render de PRODUÇÃO. Sem esta variável, o sistema assume DEV e desativa os serviços pesados. No Render DEV (preview), NÃO definir `ENVIRONMENT=production`.

## Problemas Conhecidos / Limitações

- **Render cold start**: O backend pode levar ~30s a responder no primeiro request após inatividade
- **Vercel preview CSP**: Headers CSP são configurados via vercel.json — mudanças requerem novo deploy
- **S3 CORS**: Configuração automática via endpoint, mas pode requerer verificação manual no bucket
- **Explorador de Ficheiros vazio**: Quando o S3 está configurado mas o `Base Path` ou as credenciais estão incorretos, o explorador mostra "Nenhum ficheiro encontrado" em vez de uma mensagem de erro detalhada. Verificar as configurações de armazenamento nas Configurações do Sistema (`/configuracoes`).

## Histórico de Correções Recentes (dev)

### 2026-08-23 — Pacote FN: `/processes/me` e UCR
- **Os Meus Processos** deixou de entrar em loop de `GET /processes/me` (filtro `assigned_user_ids` memoizado; a página já não escreve `"all"` no `sessionStorage`).
- `AuthContext` / `api.js` enviam `X-Company-Id` como **id** do UCR (nunca o nome de exibição) e `X-Active-Role` do perfil seleccionado.
- Backend: match UCR por `company_id` **ou** `company_name`; se o JWT já tem o cargo e o user pertence à empresa, o header é honrado. `/processes/me` filtra por atribuição + empresa (id ou nome).

### 2026-08 — v2.0 em Produção (Pacote FC — documentação)
- **UCR multi-cargo**: vários papéis por empresa (ex. Diretor e Consultor em simultâneo); proteção contra a eliminação do último acesso; cargos oficiais Parceiro e Indexação; `Company.is_active` (soft-delete).
- **Webmail em tempo real**: sync IMAP no processo da API a cada 60s + WebSocket `new_email` + React Query (`staleTime: 60s`) — sincronização instantânea sem interrupções de UI.
- **Calendário de precisão**: hora exacta + edição/eliminação de eventos (`CreateEventDialog`).
- **Administração**: `/admin` = dashboard operacional; `/admin/organizacao` = configuração de plataforma (Empresas + Utilizadores), exclusiva para `admin`/`ceo`.
- Documentação: `ARCHITECTURE.md`, `README.md`, `CHANGELOG.md` alinhados com o código.

### 2026-07 — Finalização UX (Prioridade, Resumo/Histórico), Calculadora de Prestações
- **Toast com botão X**: `<Toaster closeButton />` confirmado em `App.js` — todos os toasts (incluindo os "sticky" de tarefas em background) têm sempre uma forma manual de fechar.
- **Cartão "Prioridade" eliminado**: deixou de ocupar um `Card` isolado no separador Resumo do `ProcessDetails`; passou a um `DropdownMenu` + `Badge` compacto dentro do `AssignmentContextCard` (coluna direita) — ver `components/processDetails/AssignmentContextCard.jsx`.
- **Resumo limpo / Histórico consolidado**: confirmado que "Atividades Recentes" e o formulário "Registar Atividade" vivem exclusivamente no separador Histórico (`HistoryTab.jsx`), com o formulário atrás de um `Dialog` e a lista dentro de um `ScrollArea` de altura fixa (`h-[500px]`) — sem duplicação no Resumo.
- **Calculadora de Prestações no CRM**: nova secção `/calculadoras` (`CalculatorsPage.js`) com `MortgageSimulator.jsx` (Capital, Prazo, Taxa de Juro/Spread, toggle "Incluir Seguros" com Progressive Disclosure para Seguro de Vida/Multirriscos). Motor de cálculo extraído para `utils/mortgageCalculations.js` a partir do simulador do Portal do Cliente (`components/portal/SimulatorCH.jsx`). Inclui acesso rápido a DSTI e Risco de Crédito.
- **Documentação**: novo `FRONTEND_GUIDELINES.md` consolida as normas de UX/UI (Progressive Disclosure, layout 2/3+1/3, tokens Shadcn, `sonner`, ESLint `no-restricted-syntax`, utilitários centralizados); `ARCHITECTURE.md` documenta a regra de escrita `$set` no MongoDB e a proteção dos mapeamentos S3.

### 2026-07 — ProcessDetails TanStack, portal fulfill, toasts sticky, titular IA
- **ProcessDetails writes** via `useProcessMutations`; load já era `useProcessFullData`. Payload sanitizado (`processUpdatePayload.js`) para não esmagar `documents` / arrays vazios.
- **Toasts BG sticky**: não fazem dismiss ao mudar de página (`TasksContext`).
- **Portal**: upload do cliente **e** da equipa no CRM marcam pedidos REQUESTED → RECEIVED (`document_portal_fulfill`).
- **IA titular 1/2**: dialog no CRM quando o match é ambíguo; apply com `target_titular`.
- **Onboarding**: registo público não cria processo até checklist SystemConfig completa.
- Detalhe operacional para agentes: ver `AGENTS.md` (secção Cursor Cloud).

### Oom Fix — Render DEV (Lazy Loading + ENV Guards)
- **Lazy Loading do Playwright**: Removidos todos os imports top-level de `playwright` em `gov_scraper.py`. As importações estão apenas dentro das funções que as utilizam, evitando que o Chromium seja carregado na memória ao arrancar.
- **ENVIRONMENT guards**: Adicionadas verificações `if os.environ.get('ENVIRONMENT') != 'production'` no início de todas as funções pesadas (scraper, email sync, worker). Em DEV, retornam mock JSON em vez de executar as operações reais.
- **Mock routes no Portal**: Os endpoints `/fetch-financas`, `/fetch-seguranca-social` e `/scraper-status` retornam respostas simuladas em DEV, impedindo o Frontend de pendurar.
- **Startup cirúrgico em server.py**: Removido o `return` em bloco que bloqueava TODAS as tarefas de background em DEV. Agora, tarefas leves (Job Monitor, Backup, CDC) correm sempre; apenas o Email Sync (IMAP) é condicionado por `ENVIRONMENT=production`.
- **Remoção de Brute Force Kill Switches**: Substituídos os `return` forçados (que impediam execução mesmo em PROD) por guards `ENVIRONMENT != production` que permitem funcionamento normal em produção.

### Correções de Bugs
- **Rota /definicoes vs /configuracoes**: Corrigido — o File Explorer agora navega para `/configuracoes` (SystemConfigPage) em vez de `/definicoes` (SettingsPage pessoal) quando o utilizador clica em "Definições Gerais" ou "Ir para Definições Gerais".
- **React Minified Error #31**: Corrigido — adicionados helpers `safeString()` defensivos em PortalDocumentRequests.js para garantir que campos `category`, `status`, `notes`, `custom_label`, `original_filename` e `id` (usado como `key`) são sempre strings antes de serem renderizados como React children ou usados em comparações. Também adicionado `model_validator` no Pydantic `DocumentRequestCreate` para coagir objetos `{value, label}` em strings no backend.
- **500 error em POST /api/documents/portal-requests/{processId}**: Corrigido — adicionado `try/except` à volta da query de verificação de duplicados no MongoDB (previne crash se a query `$or` falhar), e adicionado `model_validator` no Pydantic para coagir automaticamente objetos em strings antes da validação.

### Funcionalidades Implementadas
- **RGPD assinado no portal**: O portal do cliente já mostra um card verde "RGPD Assinado" com a data quando o consentimento está assinado, e um card amarelo "RGPD Pendente" quando aguarda assinatura.
- **Filtro de documentos já solicitados**: Ao solicitar documentos ao cliente, as categorias já pedidas (REQUESTED/PENDING/UPLOADED/SUBMITTED) são filtradas da lista de seleção, impedindo duplicados.
- **Multi-seleção de documentos**: O dialog de solicitação de documentos permite selecionar múltiplas categorias simultaneamente com checkboxes, criando um pedido por categoria.
- **Contadores de pastas no Webmail**: Adicionados contadores para todas as pastas (Inbox, Enviados, Destacados, Rascunhos, Lixo) na sidebar do Webmail, obtidos via endpoint `/api/emails/webmail-stats` que agora retorna `folder_counts`.
- **Endpoints S3 para o Explorador de Ficheiros**: Adicionados 5 novos endpoints no backend:
  - `POST /api/admin/s3-rename` — Renomear ficheiros e pastas (copy + delete)
  - `POST /api/admin/s3-delete` — Eliminar ficheiros e pastas (com recursão)
  - `POST /api/admin/s3-create-folder` — Criar pastas (cria marcador `.keep`)
  - `POST /api/admin/s3-upload` — Upload de ficheiros para qualquer pasta S3
  - `GET /api/admin/s3-download` — Download de ficheiros (streaming response)
  - Acesso a consultores/intermediários: Leitura e download permitidos; Operações de escrita (upload, rename, delete, create folder) restritas a admin/CEO/diretor/administrativo.

## Licença

Privado - Power Real Estate

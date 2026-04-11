# PowerCell - Sistema de Gestão de Processos de Crédito

## Descrição

Sistema CRM completo para gestão de processos de crédito imobiliário, clientes, documentação e automação. Inclui formulário público dinâmico com campos personalizáveis, motor de automação "No-Code", gestão de permissões, templates de formulário, análise de documentos por IA, e dashboard financeiro.

## Tecnologias

- **Backend**: FastAPI (Python 3.11) + Motor (async MongoDB)
- **Frontend**: React 19 + Vite + Tailwind CSS 4 + Shadcn UI (New York style)
- **Base de dados**: MongoDB Atlas
- **Armazenamento**: AWS S3 (pre-signed URLs)
- **Cache**: Upstash Redis (REST API, degradação graciosa)
- **Filas**: ARQ (Redis-based background worker)
- **IA**: OpenAI GPT-4o + Gemini Flash (análise de documentos)
- **Email**: SendGrid / Resend (transacional + rascunhos automáticos IA)
- **Monitorização**: Sentry (frontend + backend)
- **Acessibilidade**: axe-core (testes automáticos em dev)
- **CI/CD**: GitHub Actions (Node.js 24 + Python 3.11)
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
│   │   ├── documents.py       # Upload/download docs, rate limiting, S3 proxy
│   │   ├── emails.py          # Gmail sync, send-to-banks, rascunhos IA
│   │   ├── finance.py         # Dashboard financeiro, comissões
│   │   ├── form_config.py     # Config formulário + templates
│   │   ├── public.py          # Formulário público, registo clientes
│   │   ├── rgpd.py            # Consentimento RGPD, anonimização
│   │   ├── stats.py           # Estatísticas (com Redis cache)
│   │   └── ...
│   ├── services/              # ~60 ficheiros de lógica de negócio
│   │   ├── auth.py            # JWT, password hashing (passlib)
│   │   ├── encryption.py      # Encriptação AES (Fernet) + Blind Indexing
│   │   ├── redis_cache.py     # Cache Redis com fallback
│   │   ├── workflow_engine.py # Motor de regras de automação
│   │   ├── s3_storage.py      # Pre-signed URLs, organização automática
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
│   │   │   ├── S3FileManager.js # Explorador de ficheiros + IA
│   │   │   ├── NotificationsDropdown.js  # Polling com backoff
│   │   │   ├── ImpersonateBanner.js      # Barra de impersonate
│   │   │   ├── GlobalUploadProgress.js   # Progresso global de uploads
│   │   │   ├── TasksDropdown.js          # Centro de operações
│   │   │   └── UnifiedAuditTrail.js      # "Filme da Lead"
│   │   ├── pages/             # ~50 páginas (lazy loaded)
│   │   │   ├── PublicClientForm.js       # Formulário público dinâmico
│   │   │   ├── AdminDashboard.js         # Dashboard admin
│   │   │   ├── ProcessDetails.js         # Detalhes do processo
│   │   │   ├── StaffDashboard.js         # Dashboard staff (consultor)
│   │   │   ├── MyClientsPage.js          # Os Meus Processos (filtros)
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
│   │   │   ├── queries/         # TanStack Query hooks
│   │   │   └── mutations/       # TanStack Mutation hooks
│   │   ├── contexts/          # React Context providers
│   │   │   ├── AuthContext.js   # Autenticação JWT + impersonate
│   │   │   ├── TasksContext.js  # Polling + circuit breaker
│   │   │   ├── UploadProgressContext.js
│   │   │   └── ThemeContext.js  # Light/Dark mode
│   │   ├── services/
│   │   │   └── api.js          # Axios + interceptors (429 retry)
│   │   └── layouts/
│   │       └── DashboardLayout.js # Sidebar + header
│   ├── vercel.json            # SPA rewrite + security headers
│   └── public/
├── .github/workflows/
│   └── ci.yml                 # CI/CD pipeline (Node 24 + Python 3.11)
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
- Upload e Gestão de Documentação (AWS S3 com pre-signed URLs)
- Quadro Kanban com drag-drop (@dnd-kit) e filtros (data, urgência)
- Dashboard e Estatísticas (com cache Redis)
- Sistema de Notificações em tempo real (WebSocket + polling fallback)
- Tarefas assíncronas com centro de operações (ARQ worker)

### Inteligência Artificial
- **Análise de documentos**: Extração automática de dados do CC, IRS, recibos vencimento
- **Confiança por campo**: Score 0.0-1.0 por campo extraído, alertas visuais para < 0.8
- **Auto-fill**: Sugestões automáticas de preenchimento com conflitos detetados
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

### Registo de Clientes
- Tabela mostra por defeito apenas clientes **sem processo atribuído**
- Quando o processo é criado, o cliente desaparece da vista principal
- Filtro disponível para ver "Todos", "Com Processo" ou "Sem Processo"
- Link S3 automático ao criar processo: `s3://powerprecision-docs-storage/Documentação Clientes/Nome_Do_Cliente/`

### Os Meus Processos (`/meus-clientes`)
- Vista personalizada por utilizador (apenas processos atribuídos)
- **Filtros por defeito**: Exclui status terminais (concluído, arquivo, perdido, desistências, cancelado)
- **Toggle "Mostrar Concluídos"**: Botão para incluir/excluir processos inativos
- 3 cards de estatísticas (Total, Com Tarefas Pendentes, Com Imóvel)
- Pesquisa com normalização de acentos (NFD)

### Dashboard
- **StaffDashboard**: Vista do consultor com processos sem atualização
- **AdminDashboard**: KPIs, funnel de conversão, atividade recente
- **FinanceDashboard** (admin/CEO): Comissões, performance, separação por áreas
- **Alerta de processos sem atualização**: Exclui processos concluídos, desistências e arquivados

### Administração
- **Gestão de Perfis e Permissões** (`/configuracoes-perfis`): Controlo granular de páginas e ações por utilizador
- **Gestão do Formulário** (`/gestao-formulario`): Ativar/desativar campos, criar campos personalizados, gerir templates
- **Motor de Automação** (`/automation`): Regras "Se X, Então Y" sem código
- **Gestão de Estados do Workflow** (`/workflow-estados`): Cores, labels, ordem
- **Configurações do Sistema** (`/configuracoes`): RGPD, DSTI, emails, backups, notificações

### RGPD
- **Página pública de consentimento** (`/rgpd/:token`): Assinatura digital do cliente
- **Gestor de RGPD** (admin): Templates editáveis, exportação de consentimentos
- **Anonimização de dados**: Eliminação de PII conforme GDPR
- **RGPD Migration**: Ferramenta de migração para processos legados

### Documentos
- **Explorador S3**: Vista lista/grelha, preview lateral, renomear, mover
- **Organização automática IA**: Categorização por tipo (Financeiros, Identificação, etc.)
- **Anotações contextuais**: Notas em PDFs com 5 tipos (Nota, Questão, Aviso, Financeiro, Aprovação)
- **Enviar para Balcões**: Envio de documentação para bancos com gestão de destinatários
- **Links temporários**: Upload/download seguro por link único (sem login)

### Portal do Cliente
- **Magic Link**: Acesso sem password via link único
- **Upload de documentos**: Cliente envia documentação diretamente
- **Visualização**: Download de documentos disponíveis

### Perfis de Utilizador e Permissões

O sistema suporta os seguintes perfis (roles), cada um com permissões específicas de páginas e ações:

| Perfil | Páginas Acedidas | Ações Permitidas |
|-------|-------------------|------------------|
| **Admin** | Todas | Todas |
| **CEO** | Todas | Todas |
| **Diretor** | Dashboard, Kanban, Processos, Clientes, Docs, Calendário, Notificações, Stats, Imóveis, Minutas, Leads | CRUD processos/clientes, upload/delete docs, financeiros |
| **Consultor** | Dashboard, Kanban, Processos, Clientes, Docs, Calendário, Notificações, AI Insights, Imóveis, Minutas, Leads | CRUD processos/clientes, upload docs, financeiros, imóveis |
| **Mediador/Intermediário** | Dashboard, Kanban, Processos, Clientes, Docs, Calendário, Notificações, AI Insights, Minutas | CRUD processos/clientes, upload docs, financeiros |
| **Administrativo** | Dashboard, Kanban, Processos, Clientes, Docs, Calendário, Notificações, Registos, Validades | CRUD processos/clientes, upload/delete docs |
| **Indexação** | Kanban, Processos, Clientes, Docs, Notificações, **Meus Clientes** | Upload/delete/download docs, atribuir clientes, gerir tarefas, chat |
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
- JWT com access token (24h) + refresh token (7d)
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
| POST | `/api/admin/impersonate/{id}` | Impersonate utilizador |
| POST | `/api/admin/stop-impersonate` | Parar impersonate |
| GET/PUT | `/api/admin/form-config/fields` | Configuração do formulário |
| POST/DELETE | `/api/admin/form-config/custom-field` | Campos personalizados |
| GET/POST/DELETE | `/api/admin/form-config/templates/*` | Templates de formulário |
| GET/POST | `/api/admin/automation/rules` | CRUD regras de automação |
| GET/PUT | `/api/system-config/*` | Configurações do sistema |
| GET | `/api/admin/ai-training/stats` | Estatísticas de chamadas IA |

## Configuração

### Variáveis de Ambiente

Backend (`.env`):
- `MONGO_URL` - URL de conexão MongoDB
- `DB_NAME` - Nome da base de dados
- `JWT_SECRET` - Chave secreta para JWT
- `CORS_ORIGINS` - Origens permitidas
- `SENTRY_DSN` - DSN do Sentry (opcional)
- `UPSTASH_REDIS_REST_URL` - URL Redis (opcional)
- `UPSTASH_REDIS_REST_TOKEN` - Token Redis (opcional)
- `AWS_ACCESS_KEY_ID` - Chave de acesso AWS S3
- `AWS_SECRET_ACCESS_KEY` - Chave secreta AWS S3
- `AWS_REGION` - Região AWS (default: eu-west-1)
- `S3_BUCKET_NAME` - Nome do bucket S3
- `OPENAI_API_KEY` - Chave API OpenAI (opcional)
- `SENDGRID_API_KEY` - Chave API SendGrid (opcional)

Frontend (`.env`):
- `VITE_BACKEND_URL` - URL do backend API
- `VITE_SENTRY_DSN` - DSN do Sentry (opcional)

## Credenciais de Teste

- **Admin**: admin@sistema.pt / admin
- **CEO**: pedroborges@powerealestate.pt / power2026
- **Consultor**: tiagoborges@powerealestate.pt / power2026

## Deploy

- **Backend**: Render (Docker) — porta via `PORT` env var
- **Frontend**: Vercel — SPA rewrite com exclusão de `/assets/`
- **CI/CD**: GitHub Actions — ESLint + Vite build + Flake8 + Pytest

## Branches

- `main` - Produção
- `dev` - Desenvolvimento

## Licença

Privado - Power Real Estate

# PowerCell - Sistema de Gestão de Processos de Crédito

## Descrição

Sistema CRM completo para gestão de processos de crédito imobiliário, clientes, documentação e automação. Inclui formulário público dinâmico com campos personalizáveis, motor de automação "No-Code", gestão de permissões e templates de formulário.

## Tecnologias

- **Backend**: FastAPI (Python 3.11)
- **Frontend**: React 18 + Vite + TailwindCSS + Shadcn UI
- **Base de dados**: MongoDB
- **Armazenamento**: AWS S3
- **Cache**: Upstash Redis (REST API, degradação graciosa)
- **Monitorização**: Sentry (frontend + backend)
- **Acessibilidade**: axe-core (testes automáticos em dev)
- **Deploy**: Render (backend) + Vercel (frontend)

## Estrutura do Projeto

```
PowerCell/
├── backend/
│   ├── routes/
│   │   ├── admin.py              # CRUD utilizadores, workflow, stats
│   │   ├── auth.py               # Login, refresh token, registo
│   │   ├── automation.py         # Motor de automação (regras)
│   │   ├── clients.py            # CRUD clientes, cursor pagination
│   │   ├── documents.py          # Upload/download docs, rate limiting
│   │   ├── form_config.py        # Config formulário + templates
│   │   ├── public.py             # Formulário público, registo clientes
│   │   └── stats.py              # Estatísticas (com Redis cache)
│   ├── services/
│   │   ├── auth.py               # JWT, password hashing
│   │   ├── encryption.py         # Encriptação AES (Fernet)
│   │   ├── redis_cache.py        # Cache Redis com fallback
│   │   └── workflow_engine.py    # Motor de regras de automação
│   ├── models/
│   │   ├── auth.py               # User, Role, Token models
│   │   └── process.py            # Process, Client, Registration models
│   └── tests/                    # Testes automatizados
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── ui/               # Componentes Shadcn UI
│   │   │   ├── KanbanBoard.js    # Quadro Kanban com filtros
│   │   │   ├── NotificationsDropdown.js
│   │   │   └── UnifiedAuditTrail.js  # "Filme da Lead"
│   │   ├── pages/
│   │   │   ├── PublicClientForm.js    # Formulário público dinâmico
│   │   │   ├── AdminDashboard.js      # Dashboard admin
│   │   │   ├── ProcessDetails.js      # Detalhes do processo
│   │   │   ├── ProfileSettingsPage.js # Gestão permissões utilizadores
│   │   │   ├── FormManagementPage.js  # Gestão formulário + templates
│   │   │   ├── AutomationPage.js      # Motor de automação No-Code
│   │   │   └── ...
│   │   ├── hooks/
│   │   │   └── useWebSocket.js   # WebSocket + fallback polling
│   │   ├── contexts/
│   │   │   └── AuthContext.js    # Autenticação JWT
│   │   └── layouts/
│   │       └── DashboardLayout.js # Sidebar + header
│   └── public/
└── memory/
    └── PRD.md                    # Product Requirements Document
```

## Funcionalidades Principais

### Core
- Gestão de Processos de Crédito (CRUD completo)
- Gestão de Clientes e Leads com cursor pagination
- Upload e Gestão de Documentação (AWS S3)
- Quadro Kanban com filtros (data, urgência)
- Dashboard e Estatísticas (com cache Redis)
- Sistema de Notificações em tempo real (WebSocket + polling fallback)

### Formulário Público Dinâmico
- Formulário multi-step (6 passos) com validação
- **Pré-visualização para consultores** (`/formulario-consultor`): Navegação livre pelo formulário sem preencher, para acompanhar o cliente
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

### Dashboard
- **Alerta de processos sem atualização**: Exclui processos concluídos, desistências e arquivados
- **Ver processos**: Lista detalhada expandível com link direto para cada processo

### Administração
- **Gestão de Perfis e Permissões** (`/configuracoes-perfis`): Controlo granular de páginas e ações por utilizador
- **Gestão do Formulário** (`/gestao-formulario`): Ativar/desativar campos, criar campos personalizados, gerir templates
- **Motor de Automação** (`/automation`): Regras "Se X, Então Y" sem código
- Gestão de Estados do Workflow

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
| **Indexação** | Dashboard, Kanban, Processos, Clientes, Docs, Notificações, **Meus Clientes** | Upload/delete/download docs, atribuir clientes, gerir tarefas, usar chat, atribuir utilizadores |
| **Cliente** | Nenhuma (acesso externo) | Nenhuma |

#### Perfil INDEXACAO - Detalhes

O perfil de **Indexação** foi projetado para operadores focados na organização documental:

- **Páginas**: Acede a Dashboard, Kanban, Processos, Clientes, Documentos, Notificações e "Meus Clientes"
- **Não tem acesso a**: Criar/editar clientes ou processos (dados base são **read-only**)
- **Funcionalidades permitidas**:
  - Upload, delete e download de documentos
  - Gestão de tarefas (criar, editar, completar)
  - Chat interno
  - Atribuição de utilizadores a processos (consultores, intermediários, indexação)
  - Atribuição de clientes
- **Proteção de dados**: O backend retorna HTTP 403 se o utilizador tentar editar dados base via API

#### "Meus Clientes"

- **Endpoint**: `GET /api/clients/me` e `GET /api/my-clients`
- **Frontend**: Rota `/meus-clientes` - apenas visível se o utilizador tiver a permissão `my_clients`
- Mostra apenas processos onde o utilizador está atribuído (por role)

### Segurança
- JWT com access token (24h) + refresh token (7d)
- Rate limiting (uploads, deletes, IA)
- Encriptação AES-128-CBC (Fernet) para dados sensíveis
- DOMPurify para sanitização
- Validação MIME type (magic bytes)
- Password strength validation

### Observabilidade
- Sentry SDK (frontend + backend) para monitorização de erros
- Redis health check no endpoint /api/health
- Testes de acessibilidade com axe-core (dev only)
- Audit trail unificado ("Filme da Lead")

## API Endpoints Principais

### Públicos (sem autenticação)
| Método | Endpoint | Descrição |
|--------|----------|-----------|
| POST | `/api/public/client-registration` | Registo de cliente |
| GET | `/api/public/form-config` | Campos personalizados do formulário |
| GET | `/api/health` | Health check |

### Admin (autenticação + role admin/ceo)
| Método | Endpoint | Descrição |
|--------|----------|-----------|
| GET | `/api/admin/form-config/fields` | Configuração do formulário |
| PUT | `/api/admin/form-config/fields` | Atualizar configuração |
| POST | `/api/admin/form-config/custom-field` | Criar campo personalizado |
| DELETE | `/api/admin/form-config/custom-field/{key}` | Eliminar campo personalizado |
| GET | `/api/admin/form-config/templates` | Listar templates |
| GET | `/api/admin/form-config/templates/{id}/preview` | Pré-visualizar template |
| POST | `/api/admin/form-config/templates` | Guardar como template |
| POST | `/api/admin/form-config/templates/{id}/activate` | Ativar template |
| POST | `/api/admin/form-config/templates/{id}/duplicate` | Duplicar template |
| DELETE | `/api/admin/form-config/templates/{id}` | Eliminar template |
| GET/POST | `/api/admin/automation/rules` | CRUD regras de automação |
| GET | `/api/admin/automation/triggers` | Triggers disponíveis |
| GET | `/api/admin/automation/actions` | Ações disponíveis |
| GET/PUT | `/api/admin/users` | Gestão de utilizadores |

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

Frontend (`.env`):
- `REACT_APP_BACKEND_URL` - URL do backend
- `VITE_SENTRY_DSN` - DSN do Sentry (opcional)

## Credenciais de Teste

- **Admin**: admin@sistema.pt / admin
- **CEO**: pedroborges@powerealestate.pt / power2026
- **Consultor**: tiagoborges@powerealestate.pt / power2026

## Deploy

- **Backend**: Render (Docker)
- **Frontend**: Vercel

## Branches

- `main` - Produção
- `dev` - Desenvolvimento

## Licença

Privado - Power Real Estate

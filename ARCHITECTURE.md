# Arquitetura do Sistema — PowerCell CRM

> Normas de UX/UI e convenções técnicas do frontend (Progressive Disclosure, layout 2/3+1/3, tokens Shadcn, `sonner`, ESLint `no-restricted-syntax`, utilitários centralizados): ver **`FRONTEND_GUIDELINES.md`**.

## Visão Geral

O PowerCell é um sistema de gestão de processos de crédito habitacional, concebido para a intermediação imobiliária e financeira em Portugal. A arquitetura segue o padrão **monolito modular** com separação clara entre frontend, backend API e serviços de infraestrutura.

---

## Diagrama de Arquitetura

```mermaid
graph TB
    subgraph Clientes["🖥️ Clientes (Browser)"]
        User["Utilizador"]
        Portal["Portal do Cliente<br/>(Magic Link)"]
        PublicForm["Formulário Público<br/>/registo"]
        RGPDForm["Página RGPD<br/>/rgpd/:token"]
    end

    subgraph Frontend["⚛️ Frontend — React 19 + Vite"]
        Router["React Router<br/>(Rotas protegidas por role)"]
        AuthCtx["AuthContext<br/>(JWT + Impersonate)"]
        TasksCtx["TasksContext<br/>(Polling + Circuit Breaker)"]
        UploadCtx["UploadProgressContext"]
        ThemeCtx["ThemeContext<br/>(Light/Dark)"]
        API_SVC["api.js<br/>(Axios + 429 Retry)"]
        WSClient["useWebSocket<br/>(Singleton + Backoff)"]
        TanStack["TanStack Query<br/>(Cache + Mutations)"]
        LazyChunk["LazyChunkErrorBoundary<br/>(Stale Deploy Recovery)"]
        Pages["Páginas<br/>(~50, Lazy Loaded)"]
    end

    subgraph API["🐍 Backend API — FastAPI (Python 3.12)"]
        CORS["CORS Middleware<br/>(Fail-Secure)"]
        RateLimit["Rate Limiting<br/>(Por role: slowapi)"]
        SecurityHeaders["Security Headers<br/>(HSTS, CSP, X-Frame)"]
        SentryMW["Sentry Integration"]
        InputSanitize["Input Sanitization"]

        subgraph Rotas["Rotas da API (/api) — thin stubs"]
            AuthR["/auth"]
            ProcessesR["/processes<br/>(→ services/process_*)"]
            DocumentsR["/documents<br/>(→ services/document_*)"]
            TasksR["/tasks<br/>(BG jobs + CRUD)"]
            ClientsR["/clients"]
            PortalR["/portal<br/>(cliente + fulfill)"]
            OtherR["+40 rotas (ver AGENTS.md)"]
        end

        subgraph Servicos["Camada de Serviços"]
            ProcessSvc["ProcessService"]
            AI_DocSvc["AIDocumentService<br/>(GPT-4o, Gemini)"]
            WSManager["WebSocketManager<br/>(ConnectionManager)"]
            RedisCache["RedisCache<br/>(Cache + Queue)"]
            EmailSvc["EmailService<br/>(SendGrid/Resend)"]
            EncryptionSvc["EncryptionService<br/>(Fernet + Blind Indexing)"]
            AuditCDC["AuditCDC<br/>(Change Data Capture)"]
            NotificationSvc["NotificationService"]
            TaskQueue["TaskQueue (ARQ)"]
            S3Storage["S3Storage<br/>(Pre-signed URLs)"]
            WorkflowEngine["WorkflowEngine"]
            ScraperSvc["PropertyScraper<br/>(Idealista)"]
            AIConfidence["Confidence Scorer<br/>(Score por campo)"]
            OrganizerSvc["Document Organizer<br/>(Categorização automática)"]
            EmailB2BSvc["EmailB2BService<br/>(Enviar p/ Balcões)"]
            ChangelogSvc["ChangelogService<br/>(Gerar notas IA)"]
            AnnotationSvc["AnnotationService<br/>(5 tipos de anotação)"]
            StorageFactory["StorageService<br/>(Factory: Local/S3/OneDrive)"]
            SystemSMTPSvc["SystemSMTPConfig<br/>(Bloco A - Email Transacional)"]
            SystemWebmail["SystemWebmailConfig<br/>(Bloco C - Webmail Partilhado)"]
            SharedEmailSync["SharedEmailSync<br/>(Role-based IMAP Sync)"]
        end

        subgraph Middleware_Backend["Middleware"]
            RateLimitMW["User Rate Limiter"]
            UserRL["user_rate_limit<br/>(admin: 1000, staff: 200)"]
        end
    end

    subgraph Infra["📦 Infraestrutura"]
        MongoDB[("MongoDB Atlas - Base de Dados")]
        Redis[("Redis (Upstash) - Cache + Task Queue")]
        S3[("AWS S3 - Armazenamento")]
        Sentry["Sentry<br/>(Observabilidade)"]
        SystemSMTP["System SMTP<br/>(Email Transacional via Bloco A)"]
        OpenAI["OpenAI GPT-4o<br/>(Análise de Documentos)"]
        Gemini["Gemini Flash<br/>(Análise de Documentos)"]
        TrelloAPI["Trello API<br/>(Integração)"]
        GmailAPI["Gmail API<br/>(Sincronização Email)"]
    end

    subgraph Worker["⚙️ Background Worker"]
        ARQWorker["ARQ Worker<br/>(async tasks)"]
        JobMonitor["Job Monitor<br/>(Stuck Detection)"]
        BackupSched["Backup Scheduler<br/>(Diário 03:00 UTC)"]
        RestorePipeline["restore_dev_from_backup<br/>(RGPD Fail-Safe)"]
        SyncPipeline["sync_prod_to_dev<br/>(Sanitização PII)"]
    end

    subgraph Deploy["🚀 Deploy"]
        Vercel["Vercel<br/>(Frontend CDN)"]
        Render["Render<br/>(Backend API)"]
        GHA["GitHub Actions<br/>(CI/CD Pipeline)"]
    end

    %% Clientes → Frontend
    User --> Router
    Portal --> Router
    PublicForm --> Router
    RGPDForm --> Router

    %% Frontend Interno
    Router --> AuthCtx
    Router --> Pages
    Pages --> API_SVC
    Pages --> TanStack
    Pages --> WSClient
    WSClient --> AuthCtx
    LazyChunk --> Pages

    %% Frontend → Backend
    API_SVC -->|HTTPS + JWT| CORS
    WSClient -->|WSS + JWT| OtherR

    %% Backend Pipeline
    CORS --> RateLimitMW
    RateLimitMW --> SecurityHeaders
    SecurityHeaders --> InputSanitize
    InputSanitize --> Rotas
    Rotas --> Servicos

    %% Serviços → Infraestrutura
    ProcessSvc --> MongoDB
    AI_DocSvc --> OpenAI
    AI_DocSvc --> Gemini
    AI_DocSvc --> MongoDB
    AIConfidence --> AI_DocSvc
    RedisCache --> Redis
    TaskQueue --> Redis
    EmailSvc --> SystemSMTP
    S3Storage --> S3
    OrganizerSvc --> S3Storage
    ScraperSvc -->|Scraping| ExternalSites["Sites Externos<br/>(Idealista)"]
    OtherR --> GmailAPI
    TrelloAPI -.->|Opcional| OtherR
    DocumentsR --> S3Storage
    PortalR --> DocumentsR
    TasksCtx --> TasksR
    Pages --> TasksCtx

    %% Background Worker
    TaskQueue -->|Enqueue| ARQWorker
    ARQWorker --> AI_DocSvc
    ARQWorker --> MongoDB
    ARQWorker --> Redis
    JobMonitor --> MongoDB
    BackupSched --> MongoDB
    BackupSched -->|Upload ZIP| S3
    RestorePipeline -->|Localizar backup| S3
    RestorePipeline -->|Download ZIP| S3
    RestorePipeline -->|Import temp + Swap| MongoDB
    SyncPipeline -->|Leitura| MongoDB
    SyncPipeline -->|Escrita sanitized| MongoDB

    %% Observabilidade
    SentryMW --> Sentry

    %% Deploy
    GHA -->|Deploy| Vercel
    GHA -->|Deploy| Render
    Vercel -->|CDN + SPA Rewrite| User
    Render -->|API| API_SVC

    %% Estilos
    classDef frontend fill:#0ea5e9,stroke:#0369a1,color:#fff,font-weight:bold
    classDef backend fill:#10b981,stroke:#047857,color:#fff,font-weight:bold
    classDef infra fill:#f59e0b,stroke:#b45309,color:#fff,font-weight:bold
    classDef worker fill:#8b5cf6,stroke:#6d28d9,color:#fff,font-weight:bold
    classDef deploy fill:#ef4444,stroke:#b91c1c,color:#fff,font-weight:bold

    class Frontend frontend
    class API,Middleware_Backend backend
    class Infra infra
    class Worker worker
    class Deploy deploy
```

---

## Fluxo de Dados Principal

```mermaid
sequenceDiagram
    actor U as Utilizador
    participant F as Frontend (React 19)
    participant A as API (FastAPI)
    participant S as Serviço
    participant DB as MongoDB
    participant WS as WebSocket
    participant AI as OpenAI/Gemini
    participant W as ARQ Worker

    %% Autenticação
    U->>F: Login (email + password)
    F->>A: POST /api/auth/login
    A->>DB: Verificar credenciais (passlib)
    DB-->>A: Utilizador + role
    A-->>F: JWT Token (24h) + Refresh (7d)
    F->>F: Guardar token (localStorage)
    F->>WS: Ligar WebSocket (token)
    WS-->>F: connection_status: connected

    %% Operação Principal — Kanban
    U->>F: Aceder ao Kanban
    F->>A: GET /api/processes/kanban
    A->>S: ProcessKanban.get_board(user)
    S->>DB: Pipeline queries (optimizadas)
    DB-->>S: Processos por coluna
    S-->>A: Board data
    A-->>F: Kanban board (JSON)
    F->>F: Render colunas + drag-drop (@dnd-kit)

    %% Mover Processo no Kanban
    U->>F: Drag processo para nova coluna
    F->>A: PUT /api/processes/kanban/:id/move
    A->>S: ProcessKanban.move(user, process, new_status)
    S->>DB: Actualizar status + histórico
    S->>WS: Broadcast process_moved
    WS-->>F: Notificar outros utilizadores
    WS-->>F: Atualizar board via TanStack Query setQueryData

    %% Upload e Análise de Documento com IA
    U->>F: Upload documento
    F->>A: POST /api/documents/generate-upload-url
    A->>S: S3Storage.generate_presigned_url()
    S-->>A: upload_url + file_key
    A-->>F: Pre-signed URL
    F->>S3: PUT directo (S3)
    S3-->>F: 200 OK
    F->>A: POST /api/documents/confirm-upload
    A->>S: S3Storage.confirm_upload()
    S->>DB: Guardar metadados do documento

    %% Análise AI (Background)
    A->>W: Enqueue analyze_document_task (ARQ)
    W->>AI: Enviar documento para análise
    AI-->>W: Dados extraídos + confiança por campo
    W->>DB: Actualizar processo com dados extraídos
    W->>WS: Notificar conclusão
    WS-->>F: document_uploaded + process_updated

    %% Notificações em Tempo Real
    par Broadcasting
        A->>WS: broadcast(notification)
        WS-->>F: new_notification
    and Email
        A->>S: EmailService.send()
        S->>SendGrid: Enviar email
    end
```

---

## Autenticação e Autorização

```mermaid
flowchart TD
    Login["POST /api/auth/login"]
    Login --> Validar["Validar credenciais<br/>(passlib bcrypt + MongoDB)"]
    Validar -->|Sucesso| GerarJWT["Gerar JWT<br/>(HS256, 24h)"]
    Validar -->|Falha| Erro401["401 Unauthorized"]
    GerarJWT --> RefreshToken["Gerar Refresh Token<br/>(7 dias, MongoDB)"]
    RefreshToken --> Response["Response: token + user"]

    subgraph Requests["Pedidos Autenticados"]
        Request["Request com Authorization header"]
        Request --> Extract["Middleware extrai user_id + role do JWT"]
        Extract --> RateCheck["Rate Limit<br/>(admin: 1000/min<br/>consultor: 200/min<br/>cliente: 100/min)"]
        RateCheck -->|Permitido| Route["Rota da API"]
        RateCheck -->|Excedido| RetryBackoff["429 → Retry com backoff<br/>(frontend: 3x, 2s→4s→8s)"]
        Route --> Sanitize["Input Sanitization"]
        Sanitize --> RoleCheck["Verificar role requerido"]
        RoleCheck -->|Autorizado| Exec["Executar handler"]
        RoleCheck -->|Não autorizado| Err403["403 Forbidden"]
    end

    subgraph Impersonate["Impersonate (Admin)"]
        ImpReq["POST /api/admin/impersonate/:id"]
        ImpReq --> GenToken["Gerar novo JWT<br/>com role do utilizador"]
        GenToken --> StoreOriginal["Guardar originalToken<br/>no localStorage"]
        StoreOriginal --> ImpAccess["Aceder como outro utilizador"]
        ImpAccess --> Stop["POST /api/admin/stop-impersonate"]
        Stop --> Restore["Restaurar token original"]
    end

    subgraph Refresh["Refresh Token Flow"]
        RefreshReq["POST /api/auth/refresh"]
        RefreshReq --> ValidateRT["Validar refresh token no MongoDB"]
        ValidateRT -->|Válido| NewTokens["Gerar novo JWT + refresh token"]
        ValidateRT -->|Inválido| ClearTokens["Limpar tokens"]
    end
```

---

## Modelos de Dados Principais

```mermaid
erDiagram
    USERS {
        string id PK
        string name
        string email
        string password_hash
        string role
        boolean active
        object permissions
        datetime created_at
        datetime updated_at
    }

    COMPANIES {
        string id PK
        string name
        string nif
        boolean is_active
        boolean email_sync_enabled
        string logo_url
        datetime created_at
        datetime updated_at
    }

    USER_COMPANY_ROLES {
        string id PK
        string user_id FK
        string company_id FK
        string company_name
        string role
        boolean is_default
        string signature
        object notification_preferences
        datetime created_at
        datetime updated_at
    }

    PROCESSES {
        string id PK
        string client_name
        string status
        string consultor_id FK
        string mediador_id FK
        string indexacao_id FK
        object personal_data
        object financial_data
        object real_estate_data
        array co_buyers
        string workflow_status
        string s3_folder
        datetime created_at
        datetime updated_at
    }

    DOCUMENTS {
        string id PK
        string process_id FK
        string filename
        string s3_path
        string category
        string content_type
        int file_size
        string ai_confidence
        datetime uploaded_at
        datetime expiry_date
    }

    TASKS {
        string id PK
        string title
        string description
        string process_id FK
        string assigned_to FK
        string status
        string priority
        datetime due_date
        datetime created_at
    }

    CLIENTS {
        string id PK
        string name
        string email
        string phone
        string nif
        string nif_hash
        string email_hash
        object address
        string source
        datetime created_at
    }

    LEADS {
        string id PK
        string name
        string email
        string phone
        string source
        string status
        object property_interest
        datetime created_at
    }

    ACTIVITIES {
        string id PK
        string process_id FK
        string user_id FK
        string type
        string content
        datetime created_at
    }

    HISTORY {
        string id PK
        string process_id FK
        string user_id FK
        string action
        string field
        string old_value
        string new_value
        datetime created_at
    }

    AUDIT_TRAIL {
        string id PK
        string process_id FK
        string user_id FK
        string action
        string origin
        string ip_address
        object changes
        datetime created_at
    }

    RGPD_CONSENTS {
        string id PK
        string process_id FK
        string client_name
        string client_email
        string token
        string status
        datetime signed_at
        string ip_address
    }

    EMAILS {
        string id PK
        string process_id FK
        string subject
        string direction
        string sender
        string recipients
        datetime date
        boolean monitored
    }

    AI_CONFIG {
        string id PK
        string default_model
        object confidence_thresholds
        int total_calls
        datetime last_execution
    }

    SYSTEM_CHANGELOGS {
        string id PK
        string version
        string content_markdown
        datetime published_at
        string generated_by
        string source_summary
    }

    PROCESSES ||--o{ DOCUMENTS : "tem"
    PROCESSES ||--o{ TASKS : "tem"
    PROCESSES ||--o{ ACTIVITIES : "tem"
    PROCESSES ||--o{ HISTORY : "registos"
    PROCESSES ||--o{ EMAILS : "tem"
    PROCESSES ||--o{ AUDIT_TRAIL : "auditado"
    PROCESSES ||--o| RGPD_CONSENTS : "consentimento"
    USERS ||--o{ PROCESSES : "consultor de"
    USERS ||--o{ TASKS : "responsável por"
    USERS ||--o{ ACTIVITIES : "criou"
    USERS ||--o{ USER_COMPANY_ROLES : "tem acessos"
    COMPANIES ||--o{ USER_COMPANY_ROLES : "concede cargos"
    CLIENTS ||--o{ PROCESSES : "dono de"
    LEADS ||--o{ CLIENTS : "converte-se em"
```

---

## Refatoração Fase 1: Separação Cliente ↔ Processo

### Princípio

A entidade **Cliente** representa a pessoa/fiscal entity — dados que são intrínsecos à pessoa e não mudam entre processos (nome, NIF, email, telefone, estado civil, etc.).

A entidade **Processo** representa o negócio/dossier — dados específicos de cada operação de crédito ou intermediação (valores, banco atribuído, dados financeiros, imobiliários, etc.).

### Diagrama da Nova Arquitetura

```mermaid
erDiagram
    CLIENTS {
        string id PK
        string nome
        object contacto
        object dados_pessoais
        list process_ids FK
        string fonte
        list tags
        string notas
        datetime created_at
        datetime updated_at
    }

    PROCESSES {
        string id PK
        string client_id FK "OBRIGATÓRIO"
        int process_number
        string process_type "CH, Pessoal, Seguros..."
        string status "Coluna Kanban"
        float property_value
        float loan_value
        string bank_assigned
        float honorarios
        float comissao_banco
        object personal_data "SNAPSHOT (denormalizado)"
        object titular2_data
        object financial_data
        object real_estate_data
        object credit_data
        string consultor_id FK
        string mediador_id FK
        list co_buyers
        list co_applicants
        string s3_folder
        datetime created_at
        datetime updated_at
    }

    DOCUMENTS {
        string id PK
        string process_id FK
        string client_id FK
        string filename
        string category
    }

    TASKS {
        string id PK
        string process_id FK
        string assigned_to FK
        string status
    }

    CLIENTS ||--o{ PROCESSES : "tem"
    PROCESSES ||--o{ DOCUMENTS : "tem"
    PROCESSES ||--o{ TASKS : "tem"
```

### O que mudou

| Antes (misturado) | Depois (separado) |
|---|---|
| Cliente tinha `dados_financeiros` | ❌ Removido — financeiros pertencem ao Processo |
| Cliente tinha `co_buyers`, `co_applicants` | ❌ Removido — pertencem ao Processo |
| Processo tinha `client_id` opcional | ✅ `client_id` agora é **OBRIGATÓRIO** |
| Processo sem campos de negócio raiz | ✅ Adicionados: `property_value`, `loan_value`, `bank_assigned`, `honorarios`, `comissao_banco` |
| `ClientFinancialData` existia | ❌ Removido — financeiros estão em `Process.financial_data` |
| `personal_data` no Processo era fonte de verdade | ⚠️ Agora é SNAPSHOT (denormalizado) — fonte de verdade é `clients.dados_pessoais` |

### Sincronização Bidirecional (Pacote P)

Para garantir a integridade do SNAPSHOT denormalizado, o sistema implementa sincronização bidirecional:

```mermaid
graph LR
    Client["Coleção clients<br/>(Fonte de Verdade)"] -->|"PUT /clients/{id}<br/>update_many"| Process["Coleção processes<br/>(SNAPSHOT)"]
    Process -->|"PUT /processes/{id}<br/>cascade sync"| Client
```

**Cliente → Processos (PUT /clients/{id})**: Quando o cliente é editado, o endpoint propaga automaticamente:
- `nome` → `client_name`, `personal_data.nome`, `personal_data.name` (update_many em todos os process_ids)
- `contacto.email/telefone` → `client_email/client_phone` + `personal_data.*`
- `dados_pessoais.*` → `personal_data.*` correspondente (NIF, morada, estado civil, etc.)
- Blind indexes (`nif_hash`, `email_hash`) são regenerados quando necessário

**Processo → Cliente → Restantes Processos (PUT /processes/{id})**: Quando o nome é editado dentro do processo:
1. `extract_client_updates_from_body()` extrai campos pessoais do body
2. Atualiza o documento do cliente na coleção `clients`
3. **Cascade sync**: Propaga o novo nome para todos os restantes processos do mesmo cliente

### Script de Migração

O script `backend/scripts/migrate_clients_to_processes.py` executa a migração segura:

1. **Backup** automático das coleções originais (`clients_legacy`, `processes_legacy`)
2. **Deduplicação** de clientes por NIF/Email/Nome
3. **Extração** de dados pessoais dos processos → criar/encontrar Clientes
4. **client_id** obrigatório adicionado a todos os processos
5. **Campos de negócio** extraídos para o nível raiz do processo
6. **Validação** de integridade pós-migração
7. **Rollback** disponível com `--rollback`

### Fases Futuras

| Fase | Descrição | Estado |
|------|-----------|--------|
| **Fase 1** | Modelos + Migração | ✅ Concluída |
| **Fase 2** | Adaptar rotas backend + remover campos deprecados | 🔜 Pendente |
| **Fase 3** | Remover `personal_data` do Processo (apenas referência) | 🔜 Pendente |

---

## Componentes e Tecnologias

| Camada | Tecnologia | Finalidade |
|--------|-----------|------------|
| **Frontend** | React 19 + Vite 6 | SPA com code splitting e lazy loading |
| **Estado Cliente** | Zustand | Estado local leve |
| **Estado Servidor** | TanStack Query v5 | Cache, mutations, optimistic updates |
| **UI** | shadcn/ui (New York) + Tailwind CSS 4 | Componentes e estilização |
| **Drag-Drop** | @dnd-kit/core | Kanban board interativo |
| **Backend** | FastAPI (Python 3.12) | API REST async com Pydantic |
| **Base de Dados** | MongoDB Atlas | Persistência de dados (Motor async) |
| **Cache** | Upstash Redis | Cache de sessões e fila de tarefas |
| **Armazenamento** | AWS S3 | Ficheiros com pre-signed URLs |
| **Filas** | ARQ (Redis-based) | Tarefas em background (análise IA) |
| **WebSocket** | FastAPI WebSocket | Notificações em tempo real |
| **IA** | OpenAI GPT-4o + Gemini Flash | Análise de documentos e extração |
| **Email** | SendGrid / Resend | Email transacional e rascunhos automáticos |
| **Observabilidade** | Sentry | Monitoring de erros e performance |
| **CI/CD** | GitHub Actions | Pipeline de testes e deploy |
| **Hosting FE** | Vercel | CDN + SPA rewrites |
| **Hosting BE** | Render | Docker container + auto-deploy |

---

## Padrões de Design Utilizados

| Padrão | Onde é aplicado |
|--------|----------------|
| **Singleton** | `DatabaseProxy` (MongoDB), `WebSocketManager`, `useWebSocket` (frontend) |
| **Circuit Breaker** | `TasksContext` — polling de tarefas com falhas consecutivas |
| **Reference Counting** | `useWebSocket` — uma ligação partilhada entre componentes |
| **Exponential Backoff** | `useWebSocket` (1s→30s), API interceptor 429 retry (2s→4s→8s), Notifications polling (30s→5min) |
| **Retry with Jitter** | API interceptor — 3 retries com jitter ±500ms para evitar thundering herd |
| **Lazy Loading** | 50+ páginas com `React.lazy()` + `Suspense` |
| **Chunk Error Recovery** | `LazyChunkErrorBoundary` — deteta stale deployments e faz reload automático |
| **Proxy (Lazy)** | `DatabaseProxy`, `ClientProxy` — ligação on-demand |
| **Repository** | `services/*` — abstracção sobre acesso à base de dados |
| **Middleware Chain** | CORS → Rate Limiting → Security Headers → Input Sanitization → Route Handler |
| **Observer (Pub/Sub)** | WebSocket events — `broadcast()` para notificações em tempo real |
| **Change Data Capture** | `AuditCDC` — monitoriza alterações via MongoDB Change Stream |
| **Strategy** | `AI_CONFIG_DEFAULTS` — seleção de modelo IA por tipo de tarefa |
| **Pre-signed URL** | `S3Storage` — upload directo do frontend para S3 sem passar pelo backend |
| **Blind Indexing** | `EncryptionService` — HMAC-SHA256 para pesquisa em campos encriptados |
| **Dedicated Collection** | `history`, `audit_trail` — colecções separadas para evitar 16MB limit |
| **Confidence Scoring** | `AIDocumentService` — score 0.0-1.0 por campo extraído, alertas para < 0.8 |
| **Fail-Safe Swap** | `restore_dev_from_backup.py` — BD de Dev não é modificada se o backup estiver corrompido |
| **Temporary Collection** | `_restore_temp_*` — coleções temporárias para migração atómica de dados |
| **RGPD Sanitization Pipeline** | `sync_prod_to_dev.py`, `restore_dev_from_backup.py` — anonimização determinística de PII (nome, NIF, email, telefone, IBAN) |
| **Factory (Storage)** | `storage_service.py` — `get_storage_adapter()` retorna adapter correto (Local, S3, OneDrive) baseado em `system_settings.storage.provider` |
| **Strategy (Email)** | `send_email(force_system=True)` — tenta contas nomeadas, depois SystemSMTP (Bloco A), depois erro |
| **Fallback Chain (Webmail)** | `sync_shared_role_emails()` — tenta `shared_role_email_configs`, depois `system_webmail` (Bloco C), depois erro |
| **Provider-Agnostic** | Storage, Email, Webmail configuráveis via Admin Settings sem alteração de código |
| **Thin Route + Service** | `routes/documents.py` / `routes/processes.py` — stubs FastAPI; lógica em `services/document_*.py` e `services/process_*.py` (ver `AGENTS.md`) |
| **Safe Partial Update** | `sanitizeProcessUpdatePayload` (frontend) — omite arrays vazios / `documents` / `onedrive_links` no PUT processo |
| **Sticky Toast** | `TasksContext` — `toast.loading` com `duration: Infinity` e id estável; sem auto-dismiss na navegação |
| **Passive Cache Invalidation** | Webmail — WS `new_email` → `invalidateQueries(['emails'])` com `staleTime: 60s`; refetch silencioso sem skeleton |
| **Last-Access Guard** | UCR — `run_delete_user_company_role` recusa HTTP 400 se for o único acesso do utilizador |
| **Portal Checklist Fulfill** | `document_portal_fulfill` — upload staff CRM satisfaz REQUESTED do portal |
| **MongoDB `$set` Partial Write** | Todas as escritas em `services/*.py` usam `update_one({...}, {"$set": {...}})` — nunca substituem o documento inteiro. Preserva campos não incluídos no payload (ex: `document_metadata.ai_analyzed`, mapeamentos S3, timestamps de outros subsistemas) |

### Regra: escrita em MongoDB com `$set`

Todo o código em `backend/services/*.py` que atualiza um documento existente **deve** usar `update_one`/`update_many` com o operador `$set` sobre os campos alterados, nunca `replace_one` ou um `update_one` sem `$set` (que substitui o documento inteiro e apaga silenciosamente metadados não incluídos no payload).

```python
# ✅ Correto — só os campos passados são escritos, o resto do documento sobrevive
await db.documents.update_one({"id": document_id}, {"$set": {"category": nova_categoria}})

# ❌ Errado — substitui o documento inteiro, perde document_metadata.ai_analyzed,
#    mapeamentos S3, e qualquer campo não incluído no payload
await db.documents.update_one({"id": document_id}, {"category": nova_categoria})
```

Isto é particularmente crítico em coleções com metadados gerados por subsistemas diferentes ao longo do tempo (`documents.document_metadata`, `processes.s3_folder` / mapeamentos S3, `clients.dados_pessoais`) — uma escrita parcial mal feita apaga silenciosamente trabalho de outro fluxo (ex: uma categorização manual apagar o flag `ai_analyzed`, ou um `PUT /processes/{id}` apagar o `s3_folder` calculado pelo `admin_s3_process_mappings`).

### Proteção de mapeamentos S3

Os mapeamentos S3 (`admin_s3_client_mappings.py`, `admin_s3_process_mappings.py`, `admin_s3_user_mappings.py`) são tratados como dados sensíveis a preservar:

- Nunca reescrever `services/admin_storage.py` — o nome colide com a rota `routes/admin_storage.py` (ver `AGENTS.md`); os serviços vivem em `services/admin_s3_*.py`.
- Endpoints de atualização de mapeamentos usam `$set` sobre os campos específicos (`s3_folder`, `client_folder_id`, etc.), nunca substituem o documento do processo/cliente.
- Aliases legados (`client-s3-mappings`) mantêm-se como stubs de compatibilidade — não remover sem migração explícita.

Ver `AGENTS.md` (secção "Route thinning") para o mapa completo `routes/* ↔ services/*` e as colisões de nomes a evitar.

---

## Estratégia de Resiliência

```mermaid
flowchart TD
    Error["Erro na API"] --> TypeCheck{"Tipo de erro?"}

    TypeCheck -->|"429 Rate Limit"| Retry["API Interceptor Retry<br/>(3x, backoff 2s→8s+jitter)"]
    Retry -->|Tentativas esgotadas| Toast429["Toast de erro"]

    TypeCheck -->|"Chunk Load Error"| ChunkEB["LazyChunkErrorBoundary"]
    ChunkEB --> Reload["Reload automático"]
    Reload --> Success["Página carregada"]

    TypeCheck -->|"401 Unauthorized"| Refresh["Tentar refresh token"]
    Refresh -->|Sucesso| RetryRequest["Repetir pedido original"]
    Refresh -->|Falha| Logout["Redirect para login"]

    TypeCheck -->|"Network Error"| TanStackRetry["TanStack Query<br/>(3 retries, exponential backoff)"]

    TypeCheck -->|"Outro erro"| Sentry["Reportar ao Sentry"]

    subgraph Polling["Polling Resiliência"]
        NotifPoll["Notifications Polling"] --> Poll429["429 detetado"]
        Poll429 --> Backoff["Backoff: 30s→60s→120s→300s"]
        Backoff --> PollSuccess["3 sucessos → reset"]
    end

    subgraph WebSocketRes["WebSocket Resiliência"]
        WSConn["WebSocket Connection"] --> WSError["Erro de ligação"]
        WSError --> WSBackoff["Backoff: 1s→2s→4s→...→30s"]
        WSBackoff --> WSPoll["Fallback: HTTP Polling"]
        WSPoll --> WSReconnect["Reconexão automática"]
    end
```

---

## Fluxo de Restauro Seguro (Dev ← S3 Backup)

```mermaid
sequenceDiagram
    actor Admin as Admin (API/CLI)
    participant Restore as restore_dev_from_backup
    participant S3 as AWS S3
    participant ProdDB as MongoDB Prod<br/>(backup_history)
    participant DevDB as MongoDB Dev
    participant TempCol as Coleções _restore_temp_*
    participant RealCol as Coleções Reais (Dev)

    Admin->>Restore: Trigger restauro<br/>(API: /admin/sync-database ou CLI)

    %% Passo 1: Localizar backup
    Restore->>ProdDB: Consultar backup_history<br/>(último com status=completed)
    alt Encontrado via backup_history
        ProdDB-->>Restore: s3_url do último backup
    else Fallback
        Restore->>S3: Listar objetos<br/>com prefix "backups/"
        S3-->>Restore: Lista de ZIPs ordenada por data
        Restore->>Restore: Selecionar mais recente
    end

    %% Passo 2: Download
    Restore->>S3: GET backup ZIP
    S3-->>Restore: Ficheiro ZIP (JSON por coleção)

    %% Passo 3: Extrair e validar
    Restore->>Restore: Extrair ZIP → Validar JSON
    alt ZIP corrompido ou sem JSON
        Restore-->>Admin: ❌ ERRO: Backup corrompido<br/>Dev DB NÃO foi modificada
    end

    %% Passo 4: Importar para temp
    loop Para cada coleção
        Restore->>Restore: Sanitização RGPD<br/>(anonimizar PII)
        Restore->>TempCol: INSERT em _restore_temp_*
    end

    %% Passo 5: Validar integridade
    Restore->>TempCol: count_documents (validação)
    alt Inconsistência detetada
        Restore->>TempCol: DROP _restore_temp_* (cleanup)
        Restore-->>Admin: ❌ ERRO: Validação falhou<br/>Dev DB NÃO foi modificada
    end

    %% Passo 6: Swap atómico
    loop Para cada coleção
        Restore->>RealCol: DROP coleção real
        Restore->>TempCol: RENAME _restore_temp_X → X
    end

    %% Passo 7: Pós-swap
    Restore->>RealCol: Recriar índices<br/>(email, nif, status)
    Restore->>DevDB: Cleanup de _restore_temp_* residuais
    Restore->>Restore: Remover ficheiros temporários

    Restore-->>Admin: ✅ Restauro concluído com sucesso
```

**Propriedades de segurança do pipeline:**

| Propriedade | Descrição |
|-------------|-----------|
| **Fail-Safe** | A BD de Dev **nunca** é modificada se qualquer passo falhar |
| **Não toca em Prod** | Não acede ao MongoDB de Produção diretamente (apenas S3) |
| **Atomicidade** | Swap por rename garante consistência |
| **Rastreabilidade** | Cada documento recebe `_sanitized_at` e `_sanitized_source` |
| **Cleanup automático** | Coleções temporárias são removidas em caso de sucesso ou erro |

---

## Navegação e Controlo de Acessos (RBAC)

### Separação das áreas de Administração (v2.0)

A Administração deixou de ser um único hub. Existem **duas superfícies distintas**, ambas restritas aos perfis activos `admin` e `ceo` (`canAccessOrgAdmin` / `ADMIN_PANEL_ROLES`):

```mermaid
flowchart LR
    Sidebar["Sidebar — perfil activo admin/ceo"] --> Ops["/admin<br/>Dashboard operacional"]
    Sidebar --> Org["/admin/organizacao<br/>Configuração de plataforma"]
    Sidebar --> Sys["/system-admin<br/>Configuração técnica"]
    Ops --> KPIs["KPIs, funil, calendário,<br/>documentos, leads, tarefas"]
    Org --> Empresas["Tab Empresas<br/>(CRUD + is_active)"]
    Org --> Users["Tab Utilizadores<br/>(contas + acessos UCR)"]
    Sys --> Tech["SMTP, Storage, Workflow,<br/>Backups, Logs, IA"]
```

| Rota | Superfície | Quem acede | Conteúdo |
|------|------------|------------|----------|
| **`/admin`** | Dashboard **operacional** | admin, ceo | KPIs, funil de conversão, calendário, documentos a expirar, pesquisa, tarefas, leads — o dia-a-dia da operação |
| **`/admin/organizacao`** | Área de **configuração de plataforma** | **apenas** perfil activo `admin` ou `ceo` | Tab **Empresas** + tab **Utilizadores** (contas, cargos UCR, Parceiro/Indexação). Substitui `/utilizadores` (redirect) |
| **`/system-admin`** | Painel técnico / sistema | admin, ceo (tabs técnicas só admin) | Configurações, automações, permissões, backups, logs, IA, RGPD |

O gate usa o **perfil activo** (`effectiveRole` / `X-Active-Role`), não só o `user.role` do JWT: um CEO que muda o ContextSwitcher para Consultor deixa de ver Administração.

**Dashboard operacional (`/admin`) — tabs de negócio:**

| Tab | Visível para | Descrição |
|-----|-------------|-----------|
| Visão Geral | admin, CEO | Quadro Kanban de processos com filtros |
| Calendário | admin, CEO | Prazos e eventos do pipeline |
| Documentos | admin, CEO | Documentos com validades próximas |
| Análise IA | admin, CEO | Análise inteligente de documentos |
| Pesquisar | admin, CEO | Pesquisa global de clientes |
| Tarefas | admin, CEO | Gestão de tarefas assíncronas |
| Leads | admin, CEO | Pipeline de leads |

**Área de configuração de plataforma (`/admin/organizacao`):**

| Tab | Visível para | Descrição |
|-----|-------------|-----------|
| **Empresas** | admin, ceo | CRUD de empresas do grupo; `is_active` (soft-delete) em vez de eliminar o documento |
| **Utilizadores** | admin, ceo | Contas + acessos UCR (vários cargos por empresa, proteção do último acesso, cargos oficiais Parceiro e Indexação) |

**Painel técnico (`/system-admin`) — tabs de sistema:**

| Tab | Visível para | Descrição |
|-----|-------------|-----------|
| **Configurações** | admin, CEO | Configurações gerais do sistema (SystemConfigPage) |
| **Automações** | admin, CEO | Regras de automação "Se X, Então Y" |
| **Permissões** | admin, CEO | Capabilities por utilizador / role |
| **Segurança & Backups** | **apenas admin** | Backups da BD e verificação de integridade |
| **Logs & Diagnósticos** | **apenas admin** | Logs do sistema, importação IA e diagnósticos |

### Sidebar Principal por Role

| Role | Menu Visível | Observações |
|------|-------------|-------------|
| **indexação** | Listas de Trabalho (Registos, Processos, Doc. Pendentes) | SEM Dashboard, SEM Estatísticas, SEM Configuração |
| **consultor/mediador/intermediário** | Dashboard + O Meu Negócio + Visão Global + Comunicações | Acesso operacional standard |
| **diretor** | Dashboard + O Meu Negócio + Visão Global + Comunicações + Gestão e Operações | Vê Estatísticas e Rascunhos; sem Painel Admin |
| **administrativo** | Dashboard + O Meu Negócio + Visão Global + Comunicações + Gestão (com RGPD) | Vê RGPD; sem Painel Admin |
| **CEO** | Dashboard + O Meu Negócio + Visão Global + Comunicações + Gestão + ⚙️ Administração (`/admin/organizacao`) + Painel operacional (`/admin`) | Acesso total ao negócio; tabs técnicas de `/system-admin` escondidas |
| **admin** | Dashboard + O Meu Negócio + Visão Global + Comunicações + Gestão + ⚙️ Administração (`/admin/organizacao`) + Painel operacional (`/admin`) | Acesso total incluindo tabs técnicas |

### Rotas Obsoletas na Sidebar

As rotas `/rgpd-admin` e `/templates` foram removidas da navegação principal da Sidebar. As páginas continuam acessíveis via URLs diretas e através do Painel de Administração (Tabs de Configurações e Utilizadores).

`/utilizadores` redirecciona para `/admin/organizacao?tab=utilizadores` (Pacote DY).

### Arquitetura de Páginas Embedded

As páginas integradas como Tabs no Painel de Administração suportam um modo `embedded` que omite o wrapper `<DashboardLayout>`, permitindo que o conteúdo seja renderizado dentro das Tabs sem duplicar a sidebar e o header.

Componentes com suporte `embedded`:
- `UsersAccessAdminTab` — Gestão de utilizadores e acessos UCR (`/admin/organizacao`)
- `UsersManagementPage` — Gestão de utilizadores (legado / atalho técnico)
- `SystemConfigPage` — Configurações do sistema
- `AutomationPage` — Automações de workflow
- `BackupsPage` — Backups da base de dados
- `UnifiedLogsPage` — Logs unificados
- `DiagnosticsPage` — Diagnósticos do sistema
- `ProcessMigrationTab` — Migração Fase 1 (Separação Cliente ↔ Processo)

### Dashboard de Performance de Balcões e Bancos (Pacote S)

**Endpoint**: `GET /api/stats/branches`
**Rota Frontend**: `/performance-balcoes` (sidebar: Gestão e Operações)
**Acesso**: Staff com capability `STATS_VIEW`

Utiliza MongoDB Aggregation Pipeline na coleção `processes` para calcular métricas por balcão bancário:

| Métrica | Cálculo |
|---------|---------|
| `total_processes` | Total de processos associados ao balcão |
| `active_processes` | Processos em fases ativas do workflow |
| `approval_rate` (%) | Processos que atingiram `credito_aprovado` ou fase posterior / total |
| `avg_closing_time_days` | Tempo médio (created_at → updated_at) para processos concluídos/arquivados |
| `total_volume` (€) | Soma de `credit_data.requested_amount` |

**Top Cards**: Banco Mais Rápido, Balcão com Maior Volume, Taxa de Aprovação Global.
**Cache**: Redis com TTL de 1 hora. Pipeline com `allowDiskUse=True`.

### Fix "Ver como Cliente" sem E-mail + Apelido Interno (Pacote T)

#### Tarefa 1 — Impersonate com validação de e-mail

**Endpoint**: `GET /api/portal/impersonate/{process_id}`
**Alteração**: Quando o processo não tem e-mail associado (nem no processo nem no cliente ligado), o endpoint devolve agora **HTTP 400** com a mensagem amigável:

> "Para usar esta função, o cliente precisa de ter um e-mail configurado."

Anteriormente gerava o link na mesma, mas o Portal do Cliente poderia ter funcionalidades limitadas sem e-mail. O frontend (`ProcessDetails.js`) já exibe o `detail` do erro via `toast.error()`, pelo que a mensagem chega ao utilizador sem alterações no frontend.

#### Tarefa 2 — Campo "Apelido Interno / Título"

**Modelo**: `ProcessUpdate.apelido` (string, max 120 chars) e `ProcessResponse.apelido` — já existiam no `backend/models/process.py`.
**Frontend**: Componente `InlineApelido` em `ProcessDetails.js` — edição rápida no cabeçalho do processo com ícone de lápis, visível apenas para staff (não para clientes). Guarda via `PUT /api/processes/{id}` com `{ apelido: "valor" }`.

### Gestão de Empresas — Multi-Tenant (Pacote V)

**Novo backend CRUD** para a entidade "Empresa" (não existia anteriormente — as empresas eram derivadas implicitamente da coleção `system_config`).

**Coleção MongoDB**: `companies` | **Modelo**: `backend/models/company.py`

| Endpoint | Método | Descrição |
|----------|--------|-----------|
| `/admin/companies` | GET | Lista empresas (com `?search=` por nome/NIF) |
| `/admin/companies/available` | GET | Lista id+name para dropdowns |
| `/admin/companies/{id}` | GET | Detalhe de uma empresa |
| `/admin/companies` | POST | Criar empresa |
| `/admin/companies/{id}` | PUT | Atualizar empresa (cascade: renomeia `user.company` se o nome mudar) |
| `/admin/companies/{id}` | DELETE | Eliminar empresa (bloqueia se tem utilizadores associados) |
| `/admin/companies/{id}/logo` | POST | Upload de logótipo para S3 (max 2MB, PNG/JPEG/GIF/WebP/SVG) |

**Campos**: name, nif, address, phone, email, website, logo_url, email_sync_enabled, **`is_active`** (default `true`), total_users (computado).

**Soft-delete (`is_active`)**: o modelo `Company` passou a suportar `is_active`. A UI de Administração (`CompaniesAdminTab`) **não apaga** a empresa — o Switch Activa/Inactiva faz `PUT` com `is_active: false`. Empresas inactivas deixam de aparecer no Select de "Novo acesso" UCR (`companiesForNewAccess` filtra `is_active !== false`). O endpoint `DELETE /admin/companies/{id}` continua a existir para limpeza administrativa (bloqueia se há utilizadores cuja única empresa é esta).

**Frontend**: rota canónica **`/admin/organizacao`** (tab Empresas). Página `OrganizationAdminPage.jsx` + `CompaniesAdminTab.jsx`. A tab "Empresas" no SystemAdminPanel permanece como atalho técnico.

**Acesso**: perfil activo admin ou ceo (`canAccessOrgAdmin`).

---

## Gestão UCR (User-Company-Role) — v2.0

A plataforma deixa de ter **um único cargo por empresa**. A coleção `user_company_roles` é a fonte de verdade dos acessos: um utilizador pode ter **vários cargos na mesma empresa em simultâneo** (ex.: Diretor **e** Consultor na "Empresa A") e cargos diferentes em empresas diferentes.

```mermaid
erDiagram
    USERS ||--o{ USER_COMPANY_ROLES : "n acessos"
    COMPANIES ||--o{ USER_COMPANY_ROLES : "n cargos"
    USER_COMPANY_ROLES {
        string user_id FK
        string company_id FK
        string role
        boolean is_default
    }
```

### Índice único composto

| Antes (v1) | Depois (v2.0) |
|---|---|
| Unique `{ user_id, company_id }` — um cargo por empresa | Unique `{ user_id, company_id, role }` — vários cargos por empresa |
| Select de "Novo acesso" excluía empresas já atribuídas | Select lista **todas** as empresas activas; só bloqueia a combinação exacta Empresa+Cargo (`isUcrComboTaken`) |

Modelo: `backend/models/user_company_role.py` (`CompanyRoleEnum`). Serviço: `services/user_company_roles_api_crud.py`. Helper de UI: `frontend/src/utils/organizationAdmin.js`.

### Cargos oficiais

`CompanyRoleEnum` / `UCR_ASSIGNABLE_ROLES` incluem os cargos oficiais de sistema:

| Cargo | Notas |
|-------|-------|
| `admin` | Administrador do sistema |
| `ceo` | CEO |
| `diretor` | Diretor(a) |
| `administrativo` | Apoio Administrativo |
| `consultor` | Consultor(a) |
| `intermediario` | Intermediário(a) de Crédito |
| **`indexacao`** | Indexação de Dados — cargo oficial (não é um "extra") |
| **`parceiro`** | Parceiro — utilizador fantasma (sem login operacional típico; visível na gestão de acessos) |

O perfil legado `mediador` continua mapeado para `intermediario` (`normalizeRole`).

### Proteção contra a eliminação do último acesso

Remover um UCR **não** pode deixar o utilizador sem nenhum acesso:

```python
# services/user_company_roles_api_crud.py — run_delete_user_company_role
LAST_UCR_DELETE_DETAIL = (
    "Não é possível remover o único acesso deste utilizador. "
    "Um utilizador tem de ter pelo menos um acesso UCR."
)
# HTTP 400 se count_documents({user_id}) <= 1
```

A UI (`UsersAccessAdminTab` / `LAST_UCR_DELETE_MESSAGE`) mostra a mesma mensagem. Para revogar o acesso total, desactivar a conta (`users.is_active = false`) em vez de apagar o último UCR.

### Empresa activa vs. inactiva

Novos acessos UCR só podem ser criados contra empresas com `is_active !== false`. Uma empresa inactivada deixa de ser oferecida no formulário de novo acesso, mas os UCRs já existentes **não** são apagados automaticamente (soft-delete da empresa, não cascade).

---

## Segurança

- **CORS Fail-Secure**: A aplicação arranca apenas com origens explicitamente configuradas (sem wildcards)
- **JWT com Validação Robusta**: Secret validado para entropia mínima, tokens com 24h de validade
- **Refresh Tokens**: Tokens de refresh de 7 dias, revogáveis via MongoDB
- **Rate Limiting por Role**: Limites diferenciados (admin: 1000, consultor: 200, cliente: 100 req/min)
- **Security Headers**: HSTS, CSP, X-Frame-Options, X-Content-Type-Options, Referrer-Policy em todas as respostas
- **Encriptação de Campos**: Campos sensíveis (NIF, rendimentos) encriptados com Fernet (AES-128-CBC)
- **Blind Indexing**: Hashes HMAC-SHA256 para pesquisa em campos encriptados
- **Input Sanitization**: Todas as rotas da API sanitizam inputs (strings, emails, nomes)
- **MIME Validation**: Validação por magic bytes para uploads de documentos
- **DOMPurify**: Sanitização XSS no frontend para rich text
- **Password Strength**: Validação com passlib bcrypt
- **Impersonate Control**: Admin pode visualizar como outro utilizador, com restauro automático
- **OpenAI PII Opt-out**: Configuração de opt-out de treino de dados na conta OpenAI
- **Prompt Injection Protection**: Mitigação de prompt injection em análise de PDFs
- **SPA Rewrite Security**: Vercel rewrites excluem `/assets/` para evitar MIME type attacks

---

## Arquitetura de Webmail e Email

```mermaid
sequenceDiagram
    actor User as Consultor
    participant WP as WebmailPage
    participant RQ as React Query
    participant API as FastAPI
    participant IMAP as IMAP Servers
    participant DB as MongoDB
    participant WS as WebSocket

    %% Sync automático híbrido (Pacote EC) — corre no processo da API
    loop A cada 60s (+ jitter curto)
        API->>IMAP: FETCH emails (IMAP pessoal + partilhado)
        IMAP-->>API: Lista de mensagens
        API->>DB: Upsert emails (dedup por message_id)
        API->>WS: new_email na room user_{id}
        WS-->>User: Evento new_email (sem reload)
        WS-->>RQ: invalidateQueries emails
        RQ-->>WP: refetch silencioso (staleTime 60s)
    end

    %% Sync manual (botão)
    User->>WP: Clicar "Sincronizar"
    WP->>API: POST /api/emails/webmail/sync
    API->>IMAP: FETCH todos os emails de todas as pastas
    IMAP-->>API: Lista de mensagens
    API->>DB: Upsert (dedup)
    API-->>WP: {new: N, duplicates: D, errors: E}

    %% Envio B2B
    User->>WP: Compor email para banco
    WP->>API: POST /api/emails/send-to-bank
    API->>DB: Guardar email (direção: outbound)
    API->>S3: Anexar documentos selecionados
    API->>SMTP: Enviar via SendGrid/Resend/SMTP
    API-->>WP: Email enviado
```

### Motor Real-Time do Webmail (v2.0 — Pacote EC)

O sync IMAP **já não corre no ARQ Worker a cada 15 minutos**. O `ConnectionManager` WebSocket vive **em memória no processo da API** (`uvicorn`); um worker separado não consegue emitir eventos para os clientes ligados. Por isso o loop de auto-sync passou a correr **no próprio processo da API**.

```mermaid
flowchart TD
    Start["server.py startup"] --> Loop["run_email_auto_sync()<br/>intervalo 60s + jitter ≤15s"]
    Loop --> IMAP["IMAP FETCH<br/>pessoal + partilhado + Gmail"]
    IMAP -->|insert novo| WS["email_realtime.notify_new_email"]
    WS --> Room["broadcast_to_room(user_{id})"]
    Room --> FE["useNewEmailRealtime"]
    FE --> Inv["invalidateQueries(['emails'])"]
    Inv --> RQ["React Query<br/>staleTime: 60s"]
    RQ -->|"cache ainda fresh"| Instant["Lista actualiza em fundo<br/>sem skeleton / sem reload"]
```

| Peça | Onde | Comportamento |
|------|------|----------------|
| Loop IMAP | `scheduled_tasks.run_email_auto_sync` no processo FastAPI | Default **60s** (`EMAIL_AUTO_SYNC_INTERVAL_SECONDS`, clamp 30–300). Sleep **depois** do sync + jitter curto |
| Evento | `services/email_realtime.py` | `new_email` (`WSEventType.NEW_EMAIL`) para a room `user_{id}` (e rooms de mailbox global / role partilhado) |
| Join da room | WebSocket connect | `join_user_email_room(user_id)` para o broadcast chegar ao cliente |
| Frontend | `useNewEmailRealtime` + `useWebmailEmails` | Listener WS → `invalidateQueries({ queryKey: queryKeys.emails.all })`. `staleTime: 60s` + `keepPreviousData` — a lista **não** mostra skeleton no refetch |
| Kill switch | `ENVIRONMENT=production` **ou** `EMAIL_SYNC_ENABLED=true` | Em DEV o loop não arranca (evita OOM no Render free) |
| Sync manual | Botão "Sincronizar" | Continua a existir (`POST /api/emails/webmail/sync`) para FETCH imediato de todas as pastas |

O resultado: a caixa de correio **sincroniza em tempo real** sem interrupções de UI — o utilizador continua a ler/compor enquanto a cache é invalidada em background.

**Contas de email suportadas:**

| Conta | Variáveis de Configuração | Servidor IMAP |
|-------|--------------------------|---------------|
| Precision Crédito | `PRECISION_EMAIL`, `PRECISION_PASSWORD`, `PRECISION_IMAP_SERVER/PORT` | `mail.precisioncredito.pt:993` |
| Power Real Estate | `POWER_EMAIL`, `POWER_PASSWORD`, `POWER_IMAP_SERVER/PORT` | `webmail2.hcpro.pt:993` |

**Email Transacional do Sistema (Bloco A):**

Quando `send_email(force_system=True)` é chamado (ex: alertas de sistema):

```mermaid
flowchart TD
    Route["send_email(force_system=True)"] --> TryNamed["Tentar conta nomeada<br/>(power/precision)"]
    TryNamed -->|Encontrada| UseNamed["Usar conta existente"]
    TryNamed -->|Não encontrada| TrySystemSMTP["Ler SystemSMTPConfig<br/>(system_settings)"]
    TrySystemSMTP -->|Configurado| UseSystemSMTP["Usar Bloco A<br/>(noreply@empresa.pt)"]
    TrySystemSMTP -->|Não configurado| Error["Erro: SMTP não configurado"]
```

O envio de documentação para balcões **não** usa `force_system` + `DOCUMENTS`: resolve primeiro o SMTP do perfil UCR activo (password desencriptada) e cai na Caixa Geral.

**Webmail Partilhado por Role (Bloco C):**

```mermaid
flowchart TD
    Sync["sync_shared_role_emails(indexacao)"] --> TryShared["Tentar shared_role_email_configs<br/>(coleção MongoDB)"]
    TryShared -->|Encontrada| UseShared["Usar credenciais<br/>partilhadas + Google OAuth"]
    TryShared -->|Não encontrada| TrySystemWebmail["Ler SystemWebmailConfig<br/>(system_settings)"]
    TrySystemWebmail -->|Configurado| UseSystemWM["Usar Bloco C<br/>(IMAP partilhado)"]
    TrySystemWebmail -->|Não configurado| Error["Erro: Email partilhado<br/>não configurado"]
```

**Isolamento por perfil activo (Pacote DN.1+2):**

O Webmail respeita o UCR escolhido no Header (`ContextSwitcher`):

1. O frontend envia `X-Company-Id` e `X-Active-Role` em **todos** os `fetch` do Webmail (não só via interceptor Axios).
2. Listagem (`GET /api/emails/webmail`) e stats filtram pela mailbox da UCR activa: `company_id` **ou** `account` = endereço IMAP dessa config. Emails globais / de outros perfis do mesmo user **não** entram.
3. Sync pessoal (`POST /api/emails/webmail/sync-user`) resolve `user_email_configs` com a empresa activa (e `account_id` / `mailbox` se o utilizador escolheu uma conta) e grava `company_id` em cada email sincronizado.
4. Anexos: `GET /api/webmail/attachments/{id}` (auth JWT) devolve `StreamingResponse` com `Content-Disposition: attachment`. Fonte: S3 (`s3_key`) → conteúdo na BD → IMAP on-demand. 404 se o anexo não existir.
5. **Pacote DN.4:** um perfil pode ter várias contas (`user_email_configs` único em `{user_id, company_id, email_address}`). A Área Pessoal lista-as e o Webmail troca com um Select (`mailbox=`). `is_primary` é a conta por omissão (dual-write no `user.email_config` embebido).
6. **Pacote DO.3:** se o cargo activo do UCR for `diretor`, `GET /users/me/email-accounts` injeta a **Caixa Geral** da empresa (`system_config.email` / contas globais) na lista, com `is_caixa_geral=true`, sem exigir password pessoal. A conta virtual `id=caixa-geral` é só de leitura.

**Emails do processo (Pacote DN.3):** `GET /api/emails/process/{id}` devolve mensagens com `process_id` **ou** sem processo ligado cujo `from_email` / `to_emails` / `cc_emails` corresponde ao email do cliente (processo, 2º titular, emails monitorizados, `clients.contacto.email`). Clicar na linha abre o `EmailViewerModal`.

**Envio para balcões (Pacote DO.4):** `POST /api/emails/send-documentation/{id}` autentica SMTP com a password desencriptada do **perfil de email activo**; se não houver, usa a Caixa Geral. Já não usa o transporter `system_purpose=DOCUMENTS` por omissão. Falhas de autenticação são logadas (host/user, sem password) e o cliente recebe uma mensagem genérica — sem stack trace.

```mermaid
flowchart TD
    Header["ContextSwitcher<br/>perfil + empresa"] --> WP["WebmailPage"]
    WP -->|"X-Company-Id<br/>X-Active-Role"| List["GET /emails/webmail"]
    WP -->|"mesmo contexto"| Sync["POST /emails/webmail/sync-user"]
    WP -->|"JWT + company"| Att["GET /webmail/attachments/id"]
    List --> Filter["Filtro UCR:<br/>company_id OU account=mailbox"]
    Sync --> Resolver["resolve_email_config_for_sync<br/>(user + company)"]
    Resolver --> IMAP["IMAP da conta do perfil"]
    IMAP --> DB["emails.company_id = UCR"]
    Att --> S3["S3 / BD / IMAP"]
```

**Storage Factory Pattern:**

```mermaid
flowchart TD
    API["Rota API<br/>(upload/download)"] --> Factory["get_storage_adapter()"]
    Factory --> ReadConfig["Ler system_settings<br/>.storage.provider"]
    ReadConfig -->|aws_s3| S3["S3StorageAdapter"]
    ReadConfig -->|local| Local["LocalStorageAdapter"]
    ReadConfig -->|onedrive| OneDrive["OneDriveAdapter<br/>(placeholder)"]
    ReadConfig|unknown| LocalFallback["LocalAdapter<br/>(fallback)"]
    S3 --> S3Client["AWS S3 Client"]
    Local --> FileSystem["/tmp/powercell_uploads"]
```

---

## Arquitetura de Push Notifications

```mermaid
flowchart LR
    subgraph Frontend
        SW["Service Worker<br/>(sw-push.js)"]
        Reg["Navigator.pushManager<br/>subscribe()"]
    end

    subgraph Backend
        Sub["POST /api/push/subscribe"]
        Send["Push Service<br/>(push_notifications.py)"]
    end

    subgraph Browser
        PushAPI["Web Push API<br/>(VAPID)"]
    end

    Reg -->|VAPID Public Key| Sub
    Sub -->|Guardar subscription| DB[(MongoDB<br/>push_subscriptions)]
    Send -->|VAPID Private Key| PushAPI
    PushAPI -->|Notificação| SW
```

**Configuração VAPID:**
- `VAPID_PRIVATE_KEY` — Chave privada para assinar notificações (backend)
- `VAPID_PUBLIC_KEY` — Chave pública para subscrição (frontend via `REACT_APP_VAPID_PUBLIC_KEY`)
- `VAPID_MAILTO` — Contacto admin para VAPID (`mailto:admin@creditoimo.pt`)

---

## Arquitetura de Rate Limiting

O sistema utiliza rate limiting em duas camadas:

### Backend (slowapi)

```mermaid
flowchart TD
    Request["Request HTTP"] --> GlobalRL["Rate Limit Global<br/>(200/min por defeito)"]
    GlobalRL -->|Permitido| TypeRL["Rate Limit por Tipo"]
    TypeRL --> AuthRL["auth: 10/min"]
    TypeRL --> ReadRL["read: 120/min"]
    TypeRL --> WriteRL["write: 60/min"]
    TypeRL --> UploadRL["upload: 20/min"]
    TypeRL --> ExportRL["export: 10/min"]
    TypeRL --> AIRL["ai: 20/min"]
    TypeRL -->|Excedido| Error429["429 Too Many Requests"]
```

**Variáveis de ambiente:**

| Variável | Predefinição | Descrição |
|----------|-------------|-----------|
| `RATE_LIMIT_AUTH` | `10/minute` | Login e registo |
| `RATE_LIMIT_READ` | `120/minute` | GET requests |
| `RATE_LIMIT_WRITE` | `60/minute` | POST/PUT/PATCH |
| `RATE_LIMIT_UPLOAD` | `20/minute` | Uploads de ficheiros |
| `RATE_LIMIT_EXPORT` | `10/minute` | Exportações (CSV, ZIP) |
| `RATE_LIMIT_AI` | `20/minute` | Chamadas à API de IA |
| `RATE_LIMIT_DEFAULT` | `200/minute` | Qualquer outro endpoint |

### Frontend (429 Retry)

- **API Interceptor**: 3 retries com exponential backoff (2s → 4s → 8s + jitter ±500ms)
- Respeita header `Retry-After` quando presente
- Suprime toast de erro durante retries para evitar spam
- **Notifications Polling**: Backoff em 429 (30s → 60s → 120s → 5min), reset após 3 sucessos

---

## ProcessDetails + Documentos + Portal (estado actual)

```mermaid
flowchart LR
  subgraph FE["Frontend"]
    PD["ProcessDetails"]
    Q["useProcessFullData<br/>TanStack Query"]
    M["useProcessMutations"]
    Safe["sanitizeProcessUpdatePayload"]
    Toast["TasksContext<br/>sticky toasts"]
  end

  subgraph BE["Backend services"]
    PU["process_update"]
    DAI["document_ai_analyze<br/>+ titular_match"]
    DPF["document_portal_fulfill"]
    DU["document_upload / confirm"]
  end

  PD --> Q
  PD --> M
  M --> Safe --> PU
  PD -->|Analisar IA"| DAI
  DU -->|staff ou cliente| DPF
  Toast -->|GET /tasks/active| BE
```

| Fluxo | Comportamento |
|-------|----------------|
| Load ficha | Query → hydration (`processDetailsHydration.js`) → state local editável |
| Save ficha | Mutation + sanitize (sem `documents` / arrays vazios) → invalidação TanStack |
| IA ambígua | Dialog titular 1/2; apply com `target_titular` → `titular2_data` |
| Upload portal cliente | `confirm-upload` → REQUESTED→RECEIVED |
| Upload staff CRM | `document_portal_fulfill` após upload / auto-cat → mesmo efeito no portal |
| Onboarding | Registo = cliente + checklist SystemConfig; processo só após docs obrigatórios |

Detalhe operacional e mapa `document_*` / `process_*`: **`AGENTS.md`**.

---

## Arquitetura de Scraping (Idealista)

```mermaid
flowchart TD
    Admin["Admin Dashboard"] -->|"Importar Imóvel"| API["POST /api/scraper/scrape"]
    API --> ScraperSvc["PropertyScraper"]
    ScraperSvc -->|"Tentativa 1"| Direct["HTTP Request direta"]
    Direct -->|Bloqueado| ScraperAPI["ScraperAPI<br/>(premium+render)"]
    ScraperSvc -->|"Tentativa 2"| ScraperAPI
    ScraperAPI -->|Sucesso| Parse["Parse HTML"]
    Parse -->|"Extração"| Gemini["Gemini Flash<br/>(AI extraction)"]
    Gemini -->|"Dados estruturados"| DB[(MongoDB<br/>properties)]
```

**Configuração:**
- `SCRAPERAPI_API_KEY` — API key do ScraperAPI (para sites protegidos)
- `GEMINI_API_KEY` — Gemini Flash para extração de dados de páginas
- Fallback: HTTP direto → ScraperAPI basic → ScraperAPI premium → ScraperAPI premium+render

---

## Pipeline de IA — Extração de Dados e Validade de Documentos (Pacote DD)

A IA extrai dados estruturados de documentos PDF em dois passos complementares. Ambos persistem em `document_metadata`:

```mermaid
flowchart TD
    Upload["Upload de documento<br/>(staff ou portal)"] --> AutoCat["auto_categorize_document_background"]
    AutoCat -->|"1. Extrair texto PDF"| CatAI["categorize_document_with_ai<br/>(GPT-4o-mini)"]
    CatAI -->|"category, subcategory,<br/>tags, summary, expiry_date"| Meta1["document_metadata"]
    AutoCat -->|"2. Se categoria = Identificação"| OCR["analyze_document_from_base64<br/>(OCR GPT-4o vision)"]
    OCR -->|"validade → cc_validity<br/>nome, nif, morada, …"| Extracted["extracted_data"]
    Extracted --> Meta2["document_metadata.extracted_data"]
    Extracted -->|"se is_data_confirmed = false"| Conflict["data_conflict<br/>(sugestões de preenchimento)"]
    Meta1 --> Dashboard["Dashboard Documentos a Expirar<br/>(lê document_metadata.expiry_date)"]
    Meta2 -.->|"PACOTE DD — fallback"| Meta1
```

### Extração da data de validade (`expiry_date`)

O dashboard **"Documentos a Expirar (Próximos 60 dias)"** lê `document_metadata.expiry_date`. A data é preenchida por:

1. **Categorização IA** (`categorize_document_with_ai`): o prompt pede à IA para extrair `expiry_date` no formato `YYYY-MM-DD` do texto do PDF. Funciona para documentos com texto extraível (declarações IRS, extratos, certidões com texto).
2. **OCR de visão** (`analyze_document_from_base64`): para CC/Passaporte (PDFs de imagem sem texto extraível), o OCR extrai `validade` → mapeado para `cc_validity` no `extracted_data`.

**PACOTE DD — Fallback de validade**: `build_auto_cat_metadata` em `document_auto_categorize.py` agora usa fallback encadeado quando `categorize_document_with_ai` não devolve `expiry_date`:

```
expiry_date = result.expiry_date
           || _extract_validade_from_ocr(extracted_data)   # cc_validity / validade / data_validade / expiry_date / validity_date
```

O helper `_extract_validade_from_ocr()` valida o formato `YYYY-MM-DD` via `datetime.strptime` e devolve a primeira data válida encontrada. Isto garante que CCs analisados por OCR (sem texto extraível) também alimentam o dashboard de documentos a expirar.

### Persistência e encriptação de dados IA

Quando o utilizador aplica sugestões de IA (`run_apply_ai_suggestions` em `document_ai_analyze.py`), os campos sensíveis (`personal_data.nif`, `personal_data.documento_id`) são encriptados antes de `$set` no MongoDB via `_encrypt_mongo_update_paths()` (Pacote DD). Isto garante que dados PII extraídos pela IA ficam protegidos em repouso, consistentes com o resto da camada de encriptação (`encrypt_sensitive_data`).

### Campos encriptados (Pacote DD)

`financial_data.iban` e `financial_data.conta_bancaria` foram adicionados à lista de campos sensíveis em `encrypt_sensitive_data` / `decrypt_sensitive_data` (`process_service.py`) e em `SENSITIVE_FIELDS` (`encryption.py`). IBANs existentes em plain text passam through `decrypt_sensitive_data` sem alteração (não há migração); novos writes são encriptados.


---

## Portal do Cliente — Upload Múltiplo com Append (Pacote DE)

O Portal do Cliente permite uploads faseados por categoria. Cada categoria (Recibos de Vencimento, Extratos Bancários, IRS, Identificação, etc.) mantém um array `attached_files` que cresce com cada upload — **nunca** se substitui ficheiros anteriores.

```mermaid
flowchart TD
    Client["Cliente no Portal"] -->|"1. POST /portal/upload-url"| Backend1["run_generate_portal_upload_url<br/>(presigned S3 PUT URL)"]
    Backend1 -->|"upload_url + file_key"| Client
    Client -->|"2. PUT direto para S3"| S3["AWS S3<br/>(pasta Index)"]
    Client -->|"3. POST /portal/confirm-upload<br/>{file_key, category, document_id}"| Backend2["run_confirm_portal_upload"]
    Backend2 -->|"verifica S3 file_exists"| S3
    Backend2 -->|"$set: status=RECEIVED<br/>$push: attached_files[+file_entry]"| DB[(MongoDB<br/>documents)]
    DB -->|"attached_files[]"| PortalStatus["GET /portal/status<br/>→ frontend mostra lista"]
```

### Lógica de Append (`attached_files`)

Cada documento pedido (REQUESTED) tem um array `attached_files` que acumula todos os ficheiros carregados pelo cliente para essa categoria:

```python
# services/portal_upload_ops.py — run_confirm_portal_upload
file_entry = {
    "file_id": str(uuid.uuid4()),
    "filename": original_filename,
    "s3_path": file_key,
    "file_size": file_size,
    "content_type": content_type,
    "uploaded_at": now,
    "uploaded_by": "portal_client",
}
await db.documents.update_one(match_q, {
    "$set": {"status": "RECEIVED", ...},  # status + top-level fields (backward compat)
    "$push": {"attached_files": file_entry},  # APPEND — nunca replace
})
```

Os campos top-level (`filename`, `s3_path`, `file_size`) são atualizados para refletir o upload mais recente (backward compat com serializers que leem estes campos), mas o array `attached_files` preserva o histórico completo de todos os uploads. O mesmo padrão aplica-se a `fulfill_portal_requests_on_staff_upload` (`document_portal_fulfill.py`) para uploads do staff.

### Presigned URLs (não List[UploadFile])

O upload usa o padrão presigned S3: o backend gera uma URL de upload assinada (5 min de validade), o cliente faz PUT direto para S3, depois confirma com o backend. O backend **nunca** recebe bytes de ficheiros — isto evita gargalos de bandwidth e limites de body do FastAPI. **Não** usar `List[UploadFile]` (regressão arquitetural).

---

## Documentos Legais Gerados — RGPD PDF Pré-preenchido (Pacote DE)

Documentos legais gerados pelo sistema (RGPD, Minuta, CPCV) são sempre pré-preenchidos no backend com os dados reais do cliente/processo. O frontend não pré-preenche — apenas descarrega o PDF pronto.

### Endpoint `GET /api/rgpd/pdf/{process_id}`

Gera um PDF do RGPD com o template ativo, substituindo placeholders (`{{NOME}}`, `{{CONTRIBUINTE}}`, `{{MORADA}}`, etc.) pelos dados desencriptados do cliente:

```mermaid
flowchart LR
    Endpoint["GET /rgpd/pdf/{process_id}"] --> Service["services/rgpd_pdf.py<br/>run_generate_prefilled_rgpd_pdf"]
    Service -->|"fetch + decrypt_sensitive_data"| Process["process.personal_data<br/>{nif, morada_fiscal, documento_id}"]
    Service -->|"build consent_data"| Consent["{nome, contribuinte,<br/>morada, ...}"]
    Consent --> Render["_get_rendered_rgpd_text<br/>(template + placeholders)"]
    Render --> PDF["_generate_rgpd_pdf_bytes<br/>(reportlab Canvas A4)"]
    PDF --> Response["StreamingResponse<br/>application/pdf"]
    Service -.->|"audit"| Activity["activities<br/>'RGPD descarregado'"]
```

- **Reutilização**: usa `_get_rendered_rgpd_text` e `_generate_rgpd_pdf_bytes` de `services/rgpd_service.py` (mesma pipeline dos PDFs assinados digitalmente).
- **Dados**: `consent_data` é construído a partir de `process.personal_data` (desencriptado via `decrypt_sensitive_data`), com fallback para strings vazias quando campos não existem.
- **Auth**: `require_staff()` — o PDF expõe PII do cliente.
- **Filename**: `RGPD_{safe_client_name}.pdf` (normalizado, sem acentos/caracteres especiais).

---

## Separação Estrita: User (Global) vs Role/Perfil (Local) — Pacote DF

A Área Pessoal (`ProfilePage`) segue uma separação estrita entre o que pertence à **pessoa** (global) e o que pertence a cada **perfil/role** (local por `user_company_role`). Isto evita perfis fantasma, mistura de contextos e a falsa noção de "conta principal".

```mermaid
flowchart LR
    subgraph Global["User (Global — pessoa)"]
        Auth["Informação de Login<br/>(email, password)"]
        Sessions["Sessões Ativas<br/>(JWT tokens)"]
    end
    subgraph UCR1a["UCR: Diretor @ Power RE"]
        Sig1a["Assinatura / Telefone / Cargo"]
    end
    subgraph UCR1b["UCR: Consultor @ Power RE"]
        Sig1b["Assinatura / Telefone / Cargo"]
        Mail1["Config Webmail (IMAP/SMTP)"]
    end
    subgraph UCR2["UCR: Intermediário @ Precision"]
        Sig2["Assinatura de Email"]
        Phone2["Telefone Profissional"]
        Job2["Cargo"]
        Mail2["Config Webmail"]
        Google2["Google OAuth"]
        Notif2["Preferências de<br/>Notificação"]
    end
    User["Utilador"] --> Global
    User -->|"UCR Diretor + Consultor<br/>na mesma empresa"| UCR1a
    User --> UCR1b
    User -->|"user.companies[]"| UCR2
```

### User (Global) — pertence à pessoa

| Campo | Coleção | Notas |
|---|---|---|
| `email` | `users` | Identidade de login |
| `password_hash` | `users` | Autenticação |
| `role` | `users` | Role primária (JWT) — apenas para fallback |
| `created_at` | `users` | "Membro desde" |
| `additional_roles` | `users` | Array de roles (legacy) — não usado para renderizar perfis |
| Sessões | `refresh_tokens` | JWT refresh tokens ativos |

A aba "Conta Global" da Área Pessoal contém APENAS estes cartões: Informação de Login + Sessões Ativas.

### Role/Perfil (Local) — pertence ao `user_company_role`

Cada UCR (`user_company_roles` collection, chave única `{user_id, company_id, role}` — v2.0 permite **vários cargos na mesma empresa**) tem os seus próprios:

| Campo | Coleção | Scoping |
|---|---|---|
| `signature` | `user_company_roles` | Assinatura de email para esta empresa |
| `professional_phone` | `user_company_roles` | Telefone profissional para esta empresa |
| `job_title` | `user_company_roles` | Cargo para esta empresa |
| `display_name` | `user_company_roles` | Nome de exibição para esta empresa |
| `notification_preferences` | `user_company_roles` | Preferências de notificação (14 bools) — **PACOTE DF** |
| Webmail IMAP/SMTP | `user_email_configs` | Keyed by `{user_id, company_id, email_address}` — várias contas por perfil (`is_primary`) |
| Google OAuth tokens | `user_email_configs` + `users.email_config["company:<id>"]` | Dual-write per-UCR |

A Área Pessoal gera **uma aba dinâmica por UCR real** (iterando `user.companies` / `user_company_roles`), cada uma com os cartões: Dados Profissionais + Assinatura + Webmail. **Sem hardcode de roles** — só perfis que o utilizador realmente tem aparecem. Na v2.0, o mesmo utilizador pode ter **duas abas para a mesma empresa** (ex.: Diretor e Consultor).

### `X-Company-Id` header — o mecanismo de scoping

O backend recebe o contexto de UCR ativo via header `X-Company-Id` (e `X-Active-Role`), injetado automaticamente pelo interceptor do `api.js` no frontend. **Pacote DM:** o interceptor **não sobrescreve** estes headers se o pedido já os definiu (tabs da Área Pessoal). `POST /users/me/email-config` resolve `company_id` por ordem: body → query → header.

```python
# services/auth.py
async def get_active_company_id_async(request, user):
    company_id = request.headers.get("X-Company-Id")
    # valida que o user tem um UCR para esta company_id
    # retorna company_id ou fallback
```

### Assinatura de email (Pacote DM)

A assinatura por UCR (`user_company_roles.signature`) é HTML. A Área Pessoal pré-visualiza com `RichTextViewer`; o compositor do Webmail usa `sanitizeEmailHtml` (DOMPurify, tags `<p>`, `<br>`, `<img>` com `data:`/`https`/`cid`). HTML gravado como entidades é desescapado uma vez antes de sanitizar.

### Impersonate e navegação (Pacote DM)

Ao iniciar impersonate, `AuthContext.applyUserContext` redefine `activeRole` / `activeCompanyId` para o utilizador alvo. O `DashboardLayout` constrói o menu a partir de `user.role` (não do `effectiveRole` residual do admin). Menus de Administração só aparecem se o impersonado for `admin` ou `ceo`.

### Perfil Mediador removido

O role `mediador` não é um perfil de sistema. `normalizeRole` mapeia legado → `intermediario`. Campos de processo `assigned_mediador_id(s)` mantêm-se (atribuição de intermediários). A dropbox extra de empresa no Header para Diretor foi removida — a empresa está no selector de perfil.

### Preferências de Notificação — per-UCR com fallback (PACOTE DF)

As preferências de notificação (14 campos booleanos: `email_*`, `inapp_*`) são agora persistidas no UCR (`user_company_roles.notification_preferences`) com fallback gracioso ao store global (`db.notification_preferences`):

- **Write** (`PUT /auth/preferences`): escreve no UCR ativo (via `X-Company-Id`); dual-write no global para backward compat.
- **Read** (`GET /auth/preferences`): lê do UCR ativo primeiro; se vazio/None, fall back ao global.
- **Consumers** (`notification_service.py`, `email_v2.py`): aceitam `company_id=None` opcional; quando fornecido, procuram o UCR primeiro com fallback global.

Isto permite que um consultor tenha notificações de email ativas para a Power Real Estate mas desativadas para a Precision, por exemplo.

### O que NÃO é per-UCR (tech debt)

- **OneDrive**: system-level apenas (env var `ONEDRIVE_SHARED_LINK`), sem store per-user. Defer para futuro.

---

## PDFs Gerados para Assinatura Manual (Pacote DG)

Documentos legais gerados para assinatura manual (RGPD, Minuta, CPCV) seguem regras estritas para serem imprimíveis e preenchíveis à caneta:

### Template dinâmico + paginação automática

O template do RGPD é **dinâmico** (editado pelo admin via `SmartRichEditor` em `RGPDAdminPage`, armazenado em `rgpd_template_versions` ou cache em `system_config`). Pode ser plain text ou HTML/Rich Text. O gerador de PDF lê o template ativo via `_get_active_rgpd_template()` e substitui os placeholders (`{{NOME}}`, `{{CONTRIBUINTE}}`, `{{MORADA}}`, etc.) pelos dados do cliente.

O PDF é gerado com `reportlab.platypus` (`SimpleDocTemplate` + `Paragraph` + `Spacer` + `HRFlowable`), que suporta **quebras de página automáticas** — quando um Flowable não cabe na página atual, uma nova página é criada. Isto é essencial porque o RGPD tem 11 secções e pode ocupar várias páginas.

```python
# services/rgpd_pdf.py — _build_prefilled_rgpd_pdf
doc = SimpleDocTemplate(buffer, pagesize=A4, ...)
story = []
for line in rgpd_text.split("\n"):
    story.append(Paragraph(line, body_style))  # auto-paginates
doc.build(story)  # SimpleDocTemplate handles page breaks
```

A fonte **DejaVuSans** (TTF) é registada para suportar acentos portugueses (ã, ç, é) e o caractere Unicode `☐` (U+2610, checkbox vazia). Fallback para Helvetica se a fonte não estiver disponível.

### Fallbacks para campos nulos — linhas em branco

Quando um dado do cliente falta (ex: morada, NIF, código postal), o PDF **não** imprime "N/A". Em vez disso, imprime uma linha em branco contínua (`___________________`) para o cliente preencher à caneta:

```python
# services/rgpd_pdf.py
def _blank_line(width: int = 30) -> str:
    return "_" * width

consent_data = {
    "nome": process.get("client_name") or _blank_line(50),
    "contribuinte": personal.get("nif") or _blank_line(15),
    "morada": personal.get("morada_fiscal") or _blank_line(60),
    ...
}
```

### Data e Local em branco

A data e o local de assinatura **não** são pré-preenchidos. O placeholder `{{DATA_ASSINATURA}}` é substituído por `___/___/______` e o local por `___________________` — o cliente preenche à caneta no momento da assinatura.

### Checkboxes vazias

Os 4 pontos de consentimento (A/B/C/D) usam checkboxes **vazias** (`☐`) para o cliente picar fisicamente:

```
A) Autorizo o tratamento dos meus dados pessoais...
   ☐ Autorizo     ☐ Não Autorizo
```

O caractere `☐` (U+2610) é suportado pela fonte DejaVuSans. No fluxo de assinatura digital (`sign_rgpd`), a checkbox escolhida torna-se `☑` (U+2611) — mas no PDF pré-preenchido para assinatura manual, ambas ficam vazias.

---

## Entidade "Cliente" — sem lifecycle (Pacote DG)

A entidade **Cliente** **não possui estado de ciclo de vida** (Ativo/Concluído/Inativo). O conceito de fases/status pertence apenas aos **Processos**. Um cliente é sempre um "Cliente Registado" — o que muda é o número e estado dos seus processos.

| Entidade | Tem `status`? | Tem `fase`? | Lifecycle |
|---|---|---|---|
| **Cliente** | ❌ Não | ❌ Não | Apenas `is_deleted` (soft delete) |
| **Processo** | ✅ Sim (16 fases) | ✅ Sim (`workflow_statuses`) | `pre_registo` → `clientes_espera` → ... → `concluido` |

### Listagem de Clientes

O ecrã de Clientes é uma **lista unificada de "Clientes Registados"** — sem tabs/filtros de Ativos/Concluídos. A métrica útil exibida por cliente é o **número de processos associados** (`client.process_ids.length`), não uma fase.

```jsx
// ClientsPage.js — coluna "Processos" (Pacote DG)
<Badge variant="secondary" className="gap-1">
  <FileText className="h-3 w-3" />
  {client.process_ids?.length || 0} Processos
</Badge>
```

### Soft-delete de Clientes

Todas as queries de listagem/pesquisa de clientes filtram ativamente `is_deleted: {"$ne": True}` (defense-in-depth com `status: {"$ne": "eliminado"}`). O soft-delete (`client_delete.py`) define `is_deleted: True`, `deleted_at: <timestamp>`, `is_active: False`, `status: "eliminado"` — todos os 4 campos para compatibilidade.

---

## Agenda — Dualidade Prazo/Evento (Pacote DH)

O modelo de **Agenda** (coleção `deadlines`) evoluiu para suportar dois tipos de entradas com comportamentos distintos: **prazos limite** (deadlines) e **marcações** (events). Esta dualidade reflete a realidade do negócio — nem tudo no calendário é um prazo; muitas vezes é uma marcação (ex: Escritura, reunião com banco).

### Modelo de dados

```python
# models/deadline.py
class DeadlineCreate(BaseModel):
    title: str
    description: Optional[str]
    due_date: str  # ISO "yyyy-MM-dd"
    priority: str = "medium"
    type: Literal["deadline", "event"] = "deadline"       # PACOTE DH
    visible_to_client: bool = False                        # PACOTE DH
    reminder_time: Optional[List[str]] = None              # PACOTE DH — ["1h","3h","1d","3d","7d"]
```

| Campo | Tipo | Descrição |
|---|---|---|
| `type` | `"deadline"` \| `"event"` | Distingue prazos limite de marcações |
| `visible_to_client` | `bool` | Se `True`, o evento aparece na agenda do Portal do Cliente |
| `reminder_time` | `List[str]` | Configurações de lembrete: `"1h"`, `"3h"`, `"1d"`, `"3d"`, `"7d"` (multi-select) |

### Lógica de alertas baseada no tipo

O cron `check_upcoming_deadlines` (`services/scheduled_tasks.py`, corre a cada 1h em PROD) comporta-se de forma diferente conforme o `type`:

| Type | Comportamento | Defaults `reminder_time` |
|---|---|---|
| **`deadline`** | Dispara `DEADLINE_APPROACHING` (urgência) nos dias configurados + `DEADLINE_MISSED` se atrasado | `["1d", "3d"]` |
| **`event`** | Dispara `EVENT_REMINDER` (lembrete) respeitando `reminder_time` | `["1h", "1d"]` |

Ambos usam `notification_service.send_notification_with_preference_check` para email + `realtime_notifications.notify_deadline_reminder` para in-app/WebSocket. A idempotência é garantida por um array `sent_reminders` no documento da deadline — cada lembrete só é enviado uma vez por janela.

### Portal do Cliente — eventos visíveis

O endpoint `GET /api/portal/events` retorna apenas eventos onde `visible_to_client == True`, `completed != True`, e `due_date >= today`. O frontend (`ClientPortal.jsx`) mostra uma secção "Próximos Eventos" na TOP SECTION — oculta quando vazia, com `EmptyState` quando não há eventos.

```mermaid
flowchart LR
    Staff["Staff cria entrada na Agenda"] -->|"type: deadline/event"| DB[(deadlines)]
    DB -->|"cron 1h"| Cron["check_upcoming_deadlines"]
    Cron -->|"type=deadline"| Alert["DEADLINE_APPROACHING/MISS<br/>(urgência)"]
    Cron -->|"type=event"| Reminder["EVENT_REMINDER<br/>(lembrete)"]
    Alert --> Notif["notification_service"]
    Reminder --> Notif
    Notif --> Consultor["Consultor (email + in-app)"]
    DB -->|"visible_to_client=true"| Portal["GET /portal/events"]
    Portal --> ClientUI["ClientPortal — Próximos Eventos + Calendário (DO.2)"]
```

---

## Resumo do Processo e Calendário Visual (Pacote DO.1 + DO.2)

### DO.1 — Observações + Timeline no Resumo

O modelo de Processo tem o campo `observations` (string). Na persistência (`apply_cpcv_and_metadata_fields`) o valor sincroniza com `notes` quando só um dos dois é enviado — `notes` continua a alimentar o Kanban / "Notas do Consultor".

O histórico de estados **já existia** (`GET /api/history`, coleção `history` via `log_history`). O Pacote DO.1 acrescenta um endpoint compacto para o Resumo:

- `GET /api/processes/{id}/timeline` → `{ events, total }` com criação, mudanças de fase e restantes eventos, ordenados do mais recente para o mais antigo.
- UI: `ProcessObservationsCard` (Textarea Shadcn, guardar no botão e no `onBlur`) + `ProcessSummaryTimeline` (linha vertical + nós) no separador Resumo. O histórico completo permanece no tab Histórico.

### DO.2 — Calendário visual (Dashboard + Portal)

`AgendaCalendar` (Shadcn `Calendar` + vista semanal) consome os prazos/eventos da Agenda (Pacote DH, `GET /deadlines/calendar`).

| Superfície | Fonte | Filtro |
|---|---|---|
| Dashboard do Consultor | `getCalendarDeadlines()` | Processos/prazos do utilizador (já scoped no backend) |
| Portal do Cliente | `GET /portal/events?include_past=true` | Apenas `visible_to_client=true` e não concluídos |

Dias com agendamentos mostram um ponto; o dia seleccionado lista os títulos. O calendário vive numa tab (Progressive Disclosure), não no fluxo principal.

### Calendário de precisão (v2.0 — Pacote FA)

A página `/calendario` (`CalendarPage.jsx`) passou a ser um calendário de **hora exacta**, não só de dia civil:

| Capacidade | Implementação |
|------------|----------------|
| **Hora de início/fim** | Inputs `type="time"` em `CreateEventDialog` (`start_time` / `end_time`). Persistidos em `due_date` / `end_date` como ISO local `YYYY-MM-DDTHH:mm:00` via `combineDateAndTime` (`utils/agendaCalendar.js`). Default 09:00–10:00 |
| **Dia inteiro** | Switch `all_day` — omite a hora (ausências/férias forçam dia inteiro) |
| **Edição** | Clique no evento abre o mesmo dialog em modo edição (`editingEvent`); `PUT /deadlines/{id}` |
| **Eliminação** | Botão eliminar no dialog de edição (`Trash2`) → `DELETE /deadlines/{id}` |
| **Vista** | Chip no calendário mostra o intervalo (`formatEventClockRange`, ex.: `09:00–10:30`) |

`due_date` continua a aceitar `YYYY-MM-DD` (legado, dia inteiro). Eventos novos com hora usam datetime ISO sem `Z` (hora local, evita o salto UTC).

```mermaid
flowchart LR
    DH["Agenda DH<br/>deadlines"] --> CalAPI["GET /deadlines/calendar"]
    DH -->|"visible_to_client"| PortalAPI["GET /portal/events"]
    CalAPI --> Dash["ConsultorDashboard<br/>tab Calendário"]
    PortalAPI --> PortalCal["ClientPortal<br/>tab Agenda"]
```

---

## IA Híbrida — Sistema de Confiança para Documentos (Pacote DJ)

A IA analisa documentos e aplica um **Sistema Híbrido baseado em Confiança**: confiança alta (≥85%) resulta em auto-aprovação (Zero-Touch); confiança baixa (<85%) entra em Human-in-the-Loop (revisão manual).

```mermaid
flowchart TD
    Trigger["Consultor clica BrainCircuit<br/>num documento"] -->|"POST /documents/{doc_id}/ai-analyze-review"| Backend["document_review.py<br/>run_analyze_document_for_review"]
    Backend -->|"categorize_document_with_ai<br/>+ OCR"| LLM["GPT-4o-mini"]
    LLM -->|"JSON: categoria, validade,<br/>nome, confidence"| Backend
    Backend -->|"confidence_score = int(confidence * 100)"| Check{"confidence_score >= 85?"}
    Check -->|"Sim — Alta confiança"| Auto["AUTO_APPROVED (Zero-Touch)<br/>escreve em suggested_* E ai_*<br/>ai_review_status=auto_approved"]
    Check -->|"Não — Baixa confiança"| Pending["PENDING_REVIEW (HITL)<br/>escreve apenas em suggested_*<br/>ai_review_status=pending_review"]
    Auto --> DB[(document_metadata)]
    Pending --> DB
    DB -->|"GET /client/{id}/files"| Frontend["S3FileManager badges"]
    Frontend -->|"auto_approved: ✨ Auto-Aprovado (verde)"| AutoBadge["Badge verde informativo"]
    Frontend -->|"pending_review: ⚠️ Revisão Necessária (âmbar)"| ReviewBadge["Badge âmbar clickable"]
    ReviewBadge -->|"click"| Modal["DocumentReviewModal<br/>Atual vs Sugerido<br/>+ Aprovar/Rejeitar"]
    Modal -->|"POST /apply-ai-review"| Apply["copia suggested_* → ai_*<br/>status=approved/edited"]
    Modal -->|"POST /reject-ai-review"| Reject["status=rejected"]
```

### Lógica de Threshold (Limiar de Confiança)

```python
# services/document_review.py
AI_CONFIDENCE_THRESHOLD = 85

# Na análise:
confidence_score = int(round(raw_confidence * 100))  # 0.0-1.0 → 0-100

if confidence_score >= AI_CONFIDENCE_THRESHOLD:
    # AUTO_APPROVED: IA aplica directamente em ai_* (Zero-Touch)
    ai_review_status = "auto_approved"
else:
    # PENDING_REVIEW: IA sugere em suggested_* (HITL)
    ai_review_status = "pending_review"
```

### Modelo de dados — `suggested_*` vs `ai_*`

A coleção `document_metadata` tem dois conjuntos de campos:

| Campo `suggested_*` (IA sugere) | Campo `ai_*` (aplicado) | Quando é escrito |
|---|---|---|
| `suggested_category` | `ai_category` | `suggested_*` sempre; `ai_*` se auto_approved ou consultor aprova |
| `suggested_subcategory` | `ai_subcategory` | mesmo padrão |
| `suggested_confidence` | `ai_confidence` | mesmo padrão |
| `suggested_expiry_date` | `expiry_date` | mesmo padrão |
| `suggested_filename` | `filename` | mesmo padrão |
| `suggested_nome` | `extracted_data.nome` | mesmo padrão |

O campo `ai_review_status` controla o estado: `auto_approved` | `pending_review` → `approved` | `rejected` | `edited`.

### Endpoints do fluxo HITL

| Endpoint | Método | Descrição |
|---|---|---|
| `/documents/{doc_id}/ai-analyze-review` | POST | Triggera IA, aplica threshold (auto_approved ou pending_review) |
| `/documents/{doc_id}/apply-ai-review` | POST | Aplica sugestões selecionadas (`suggested_*` → `ai_*`) |
| `/documents/{doc_id}/reject-ai-review` | POST | Rejeita sugestões |
| `/documents/process/{process_id}/pending-review` | GET | Lista documentos pendentes de revisão (`pending_review`) |

### Estados visuais no frontend (S3FileManager)

| `ai_review_status` | Badge | Cor | Clickable? |
|---|---|---|---|
| `auto_approved` | ✨ Auto-Aprovado | verde (`bg-primary/10`) | Não (informativo) |
| `pending_review` | ⚠️ Revisão Necessária | âmbar (`bg-accent/15`) | Sim (abre modal) |
| `approved` | Aprovado | verde (`variant=secondary`) | Não |
| `rejected` | Rejeitado | muted (`variant=outline`) | Não |
| `edited` | Editado | azul | Não |
| (analisando) | A analisar... | roxo com spinner | Não |

### Fluxo paralelo — auto-categorização em background

A auto-categorização em background (`document_auto_categorize.py`) continua a escrever **diretamente** em `ai_*` (sem HITL) para uploads novos. O fluxo HITL é **paralelo** — accionado on-demand pelo consultor quando quer rever/refinar os metadados de um documento específico.

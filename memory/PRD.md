# PowerCell CRM - PRD

## Problema Original
CRM para gestão de processos de crédito imobiliário com formulário público dinâmico, gestão de clientes/processos/documentos, automação e monitorização.

## Stack Tecnológica
- **Backend**: FastAPI, MongoDB, Pydantic, JWT Auth, AWS S3, slowapi, sentry-sdk, upstash-redis
- **Frontend**: React 18, Vite, TailwindCSS, Shadcn UI, Sonner, Lucide Icons, @sentry/react, @axe-core/react
- **DB**: MongoDB (via MONGO_URL)
- **Observabilidade**: Sentry (backend + frontend)
- **Cache**: Upstash Redis (REST API, degradação graciosa)

## Estado de Implementação — COMPLETO

### Core CRM
- CRUD completo de processos, clientes, documentos
- Quadro Kanban com filtros (data, urgência)
- Dashboard admin/staff com estatísticas
- Sistema de notificações (WebSocket + polling fallback)
- Cursor pagination, rate limiting, JWT lifecycle

### Formulário Público
- Multi-step (6 passos) com validação e rascunho automático
- Campos obrigatórios com `*` vermelho + "(obrigatório)"
- Campo "Trabalha no estrangeiro?" (Step 4)
- Opção "Nenhuma" nos bancos (Step 5)
- Campos personalizados dinâmicos (6 tipos)
- Editor de opções inline para dropdowns/checkboxes
- 3 templates de sistema + templates personalizados
- Pré-visualização de templates antes de ativar

### Administração
- Configurações de Perfis (`/configuracoes-perfis`): Permissões por utilizador
- Gestão do Formulário (`/gestao-formulario`): Campos + templates
- Motor de Automação No-Code (`/automation`): Regras "Se X, Então Y"
- Gestão de Estados do Workflow

### Segurança e Observabilidade
- Encriptação AES (Fernet), DOMPurify, MIME validation
- Sentry, Redis cache, axe-core, audit trail unificado
- Todos os bugs (E#), melhorias (M#) e outras (O#) do documento original implementados

## Tarefas Pendentes
- Nenhuma tarefa prioritária pendente (P1/P2 removidos por opção do utilizador)

## Correções Recentes
- **2026-03-24**: Corrigido Dockerfile + requirements.txt para build de produção. Adicionada pré-visualização de formulário para consultores (`/formulario-consultor`). Filtro por defeito na tabela de registos mostra apenas clientes sem processo. Lista expandível de processos sem atualização no Dashboard. Link S3 automático ao criar processo. Estados finais corrigidos no alerta de processos stale.

## Credenciais de Teste
- Admin: admin@sistema.pt / admin
- CEO: pedroborges@powerealestate.pt / power2026
- Consultor: tiagoborges@powerealestate.pt / power2026

## Rotas Principais
- Formulário público: `/` (raiz)
- Form config público: `GET /api/public/form-config`
- Form config admin: `/api/admin/form-config/*`
- Templates: `/api/admin/form-config/templates/*`
- Automação: `/api/admin/automation/*`
- Perfis: `/configuracoes-perfis`
- Gestão formulário: `/gestao-formulario`

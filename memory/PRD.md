# PowerCell CRM - PRD

## Problema Original
CRM para gestão de processos de crédito imobiliário com formulário público dinâmico, gestão de clientes/processos/documentos, automação e monitorização.

## Stack Tecnológica
- **Backend**: FastAPI, MongoDB, Pydantic, JWT Auth, AWS S3, slowapi, sentry-sdk, upstash-redis
- **Frontend**: React 19, Vite, TailwindCSS 4, Shadcn UI, Sonner, Lucide Icons, @sentry/react, @axe-core/react, @hello-pangea/dnd
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
- Gestão de Estados do Workflow (`/workflow-estados`): Cores, labels, ordem, portal labels
- **Portal do Cliente**: Magic links curtos, stepper visual, upload categorizado, pedidos de documentos
- **Notificações WebSocket**: Notificações em tempo real com fallback polling

### Segurança e Observabilidade
- Encriptação AES (Fernet), DOMPurify, MIME validation
- Sentry, Redis cache, axe-core, audit trail unificado
- Todos os bugs (E#), melhorias (M#) e outras (O#) do documento original implementados

## Tarefas Pendentes
- Nenhuma tarefa prioritária pendente (P1/P2 removidos por opção do utilizador)

## Correções Recentes
- **2026-07-04**: Documentação atualizada com issues conhecidos, funcionalidades pendentes e referência de rotas. Identificados 4 bugs e 3 pedidos de funcionalidade pendentes.
- **2026-07-03**: Correções de CSP (vercel.live frame-src, wss: connect-src, non-portal completo), React error #31 na gestão de formulários ({value, label} objects como React children), stop-impersonate 400 (metadados de impersonate perdidos no refresh), menu lateral "Estados do Workflow" adicionado
- **2026-06-29**: Portal do cliente redesenho completo (layout 2 colunas, stepper vertical, upload categorizado, pedidos de documentos), S3 CORS auto-config, mapeamento de categorias portal→S3, show mediador no portal
- **2026-03-24**: Corrigido Dockerfile + requirements.txt para build de produção. Adicionada pré-visualização de formulário para consultores (`/formulario-consultor`). Filtro por defeito na tabela de registos mostra apenas clientes sem processo. Lista expandível de processos sem atualização no Dashboard. Link S3 automático ao criar processo. Estados finais corrigidos no alerta de processos stale.

## Credenciais de Teste
- Admin: admin@sistema.pt / admin
- CEO: pedroborges@powerealestate.pt / power2026
- Consultor: tiagoborges@powerealestate.pt / power2026

## Rotas Principais
- Formulário público: `/` (raiz)
- Portal do cliente: `/portal/:token` (magic link)
- Gestão fases: `/workflow-estados`
- Form config público: `GET /api/public/form-config`
- Form config admin: `/api/admin/form-config/*`
- Portal requests: `/api/documents/portal-requests/*`
- Templates: `/api/admin/form-config/templates/*`
- Automação: `/api/admin/automation/*`
- Perfis: `/configuracoes-perfis`
- Gestão formulário: `/gestao-formulario`

## Issues Conhecidos e Bugs (2026-07-04)

### Bugs Reportados
1. **Explorador de Ficheiros não mostra ficheiros**: O S3 está configurado mas o explorador mostra "Nenhum ficheiro encontrado". Causas possíveis: Base Path incorreto, credenciais S3 inválidas, ou permissões insuficientes. Os consultores e intermediários têm acesso de leitura/download ao explorador (`canViewExplorer`).
2. **Rota /definicoes incorreta para "Definições Gerais"**: Ao clicar para aceder às definições gerais, alguns elementos da UI navegam para `/definicoes` (SettingsPage - definições pessoais do utilizador) em vez de `/configuracoes` (SystemConfigPage - configurações do sistema). Estas são páginas diferentes.
3. **React Minified Error #31**: Em ProcessDetails, objetos `{value, label}` são renderizados como React children. Já corrigido em FormManagementPage com helpers `optStr()` e `optVal()`, mas pode persistir noutros componentes.
4. **500 Internal Server Error em POST /api/documents/portal-requests/{processId}**: O endpoint para criar pedidos de documentos via portal do cliente retorna erro 500 em determinados cenários.

### Funcionalidades Pedidas (Pending)
1. **Filtro de documentos já solicitados**: Ao pedir documentos ao cliente, filtrar da lista de seleção os tipos de documento que já foram solicitados (evitar pedidos duplicados).
2. **Multi-seleção de tipos de documento**: Permitir selecionar múltiplos tipos de documento ao mesmo tempo ao solicitar documentos ao cliente (atualmente só permite um de cada vez).
3. **Pastas do Webmail - Enviados/Rascunhos/Lixo**: As pastas de Enviados, Rascunhos e Lixo devem aparecer e ser corretamente sincronizadas no webmail. O frontend já define 5 pastas (inbox, sent, starred, drafts, trash) mas a sincronização IMAP pode não estar a popular estas pastas corretamente.

## Rotas Importantes (Referência Rápida)

| Rota | Página | Descrição |
|------|--------|-----------|
| `/configuracoes` | SystemConfigPage | Configurações do sistema (admin) |
| `/definicoes` | SettingsPage | Definições pessoais do utilizador |
| `/ficheiros` | FilesExplorerPage | Explorador de ficheiros S3 |
| `/webmail` | WebmailPage | Cliente de email IMAP |
| `/perfil` | ProfilePage | Perfil do utilizador |
| `/configuracoes-perfis` | ProfileSettingsPage | Gestão de permissões por utilizador |
| `/gestao-formulario` | FormManagementPage | Gestão do formulário público |
| `/workflow-estados` | WorkflowStatusesPage | Gestão de estados do workflow |
| `/rgpd-admin` | RGPDAdminPage | Administração RGPD |
| `/automation` | AutomationPage | Motor de automação No-Code |

**Nota**: `/configuracoes` e `/definicoes` são rotas DIFERENTES. A primeira é para admin configurar o sistema (SMTP, storage, RGPD, etc.), a segunda é para o utilizador gerir as suas definições pessoais.
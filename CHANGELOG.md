# Changelog

Todas as mudanças notáveis neste projeto serão documentadas neste arquivo.
O formato é baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.0.0/).

## [2026-06-28] - Correção de Frame-Busting no Portal do Cliente

### Corrigido
- **Magic Link bloqueado dentro de iframe de email client** (`fix`): Quando um cliente clica num Magic Link a partir de um email client (Outlook, Gmail app, etc.), o browser bloqueava o carregamento com erro `Unsafe attempt to load URL ... from frame with URL chrome-error://chromewebdata/`. Isto acontecia porque os headers `X-Frame-Options: DENY` e `frame-ancestors 'none'` impediam completamente o carregamento da página dentro de qualquer frame, incluindo o webview dos email clients.
- **Frame-busting script em index.html** (`fix`): Adicionado script de frame-busting no `<head>` do `index.html` (executa antes do React). Se a página está dentro de um iframe (`window.self !== window.top`), tenta redirecionar para o top-level. Se bloqueado por cross-origin, abre numa nova aba com `window.open()`.
- **Headers mutuamente exclusivos no vercel.json** (`fix`): A regra `/portal(.*)` tem os mesmos headers de segurança das restantes rotas **exceto** `X-Frame-Options: DENY` e com `frame-ancestors *` (permite iframe temporário para o frame-busting script executar). A regra global usa negative lookahead `((?!portal).*)` para garantir que `/portal` nunca recebe `X-Frame-Options: DENY` ou `frame-ancestors 'none'`. As duas regras são mutuamente exclusivas — sem conflitos.
- **Verificação secundária no ClientPortal.jsx** (`fix`): Adicionado `useEffect` de frame-busting no componente React como segunda camada de defesa. Se detetado frame, tenta `window.top.location.href`; em caso de erro cross-origin, chama `window.open()` e mostra mensagem ao utilizador.

## [2026-06-27] - Emails do Sistema (Arquitetura por Propósito)

### Adicionado
- **SystemEmailConfig — CRUD para emails do sistema** (`feat`): Nova coleção MongoDB `system_email_configs` para guardar configurações SMTP isoladas por propósito (DOCUMENTS, RGPD, SYSTEM_ALERTS, NOTIFICATIONS, CUSTOM). Cada config tem: host, port, user, password (encriptada), from_name, from_email, use_ssl, use_tls, is_active.
- **Rotas CRUD** em `system_config.py`: GET /system-emails, GET /system-emails/{purpose}, POST /system-emails, PUT /system-emails/{purpose}, DELETE /system-emails/{purpose}, POST /system-emails/{purpose}/test.
- **`get_system_transporter(purpose)`** em `email.py`: Função utilitária que obtém config SMTP para um propósito específico. Prioridade 1: DB (system_email_configs), Prioridade 2: Fallback para env vars (POWER_EMAIL, etc.) — Zero Downtime garantido.
- **`system_purpose` no `send_email()`**: Novo parâmetro opcional em `email_service.py`. Quando `force_system=True` e `system_purpose` fornecido, tenta o transporter específico antes do fallback.
- **Atualização dos callers**: `temp_link_service.py` usa `system_purpose="DOCUMENTS"`, `rgpd_service.py` usa `system_purpose="RGPD"`, `routes/emails.py` (envio de documentação) usa `system_purpose="DOCUMENTS"`.
- **UI "Emails do Sistema"** no SystemConfigPage: Novo separador com Cards independentes para cada propósito. Cada Card mostra config atual, botões Editar/Testar/Eliminar, e aviso "Se não configurado, o sistema usará o email principal". Formulário inline com Host, Porta, User, Password, Nome/Email Remetente, SSL/TLS.
- **Segurança**: Passwords encriptadas com `encryption_service.encrypt()` (Fernet AES-128-CBC). GET endpoints devolvem `has_password: true/false` em vez da password.

## [2026-06-27] - Correção de Sincronização Webmail

### Corrigido
- **Sincronização webmail mostra toast "não configurado" incorretamente** (`fix`): Ao clicar "Sincronizar" no separador "Pessoal", se o utilizador não tinha email pessoal configurado mas existia config global (SystemConfigPage), o sync falhava com mensagem de "não configurado". Agora o `handleSyncEmails` faz fallback automático para o endpoint de sincronização global (`/webmail/sync`) quando o sync pessoal falha e o utilizador tem privilégios de admin.
- **WelcomeConfigModal aparece para admins com email global configurado** (`fix`): O endpoint `/auth/me` agora verifica não só a config pessoal do utilizador (`email_config.is_configured`), mas também a config global do sistema (`system_config.email` e `system_webmail`) para admins/ceo/diretor/administrativo. Se existir config global, `email_configured` é `true` e o modal não aparece.

## [2026-06-26] - Correções de Webmail e UX

### Corrigido
- **email_configured sempre false no /auth/me** (`fix`): O endpoint `/auth/me` verificava `user.email_config.is_configured` no topo, mas a config é armazenada em estrutura nested por role (`email_config.default.is_configured`). Agora usa `_is_nested_email_config` e `_extract_role_email_config` do `email_config_resolver` para verificar corretamente qualquer sub-config.
- **WelcomeConfigModal aparece sempre no login** (`fix`): Consequência do bug acima — como `email_configured` era sempre `false`, o modal de configuração de email era exibido em cada login mesmo com email já configurado. Adicionado `refreshUser` ao `AuthContext` para atualizar `user.email_configured` após guardar a configuração.
- **ProfilePage não atualizava email_configured** (`fix`): `EmailConfigForm` agora recebe `onSuccess={refreshUser}` para refazer fetch do `/auth/me` após guardar, atualizando a flag `email_configured` no contexto.

### Melhorado
- **EmailConfigForm — Campos protegidos quando configurado** (`feat`): Quando o email já está configurado, todos os campos do formulário ficam disabled (readOnly) com visual `bg-muted`. Um botão com ícone de lápis (`Pencil`) permite ativar o modo de edição. O modo de edição pode ser cancelado, revertendo alterações não guardadas. Os botões "Testar" e "Guardar" só aparecem quando se está a editar ou quando ainda não está configurado.

## [2026-04-22] - Arquitetura Agnóstica de Provedores e Correções de UI

### Adicionado
- **Arquitetura Agnóstica de Provedores** (`1dd33f6`): Sistema totalmente independente de provedores:
  - **SystemSMTPConfig (Bloco A)**: Configuração SMTP transacional global para emails do sistema (documentação, convites, alertas) — nunca usa credenciais pessoais
  - **SystemWebmailConfig (Bloco C)**: Conta IMAP partilhada para sincronização de email do departamento de indexação
  - **storage_service.py**: Factory Pattern com `StorageAdapter` ABC, `LocalStorageAdapter`, `S3StorageAdapter`, `OneDriveAdapter` (placeholder) — `get_storage_adapter()` lê provider de `system_settings`
  - **Painel de Integrações** no SystemConfigPage: Novo tab com 3 formulários (SMTP Sistema, Storage Provider, Webmail Partilhado)

### Corrigido
- **Form field sorting** (`9289f3f`): `PublicClientForm.js` e `FormManagementPage.js` agora usam `order_index ?? order ?? 0` antes de `.map()` para respeitar ordem DnD
- **ClientsPage combobox** (`9289f3f`): Adicionada opção "Última Atualização" (updated_at_desc) ao Select de ordenação
- **Indexacao webmail bypass** (`9289f3f`):
  - `routes/emails.py`: `/webmail/sync-user` faz fallback para `system_webmail` (Bloco C) quando `shared_role_email_configs` não existe
  - `email_service.py`: `sync_all_user_emails()` exclui indexacao/suporte do sync pessoal e adiciona `sync_shared_role_emails()` com fallback
- **CI: `_save_email_to_db` undefined** (`2e4eb44`): Substituídas 2 chamadas à função inexistente por lógica inline completa (dedup, smart threading, tag parsing, insert) no sync de webmail partilhado
- **CI: package-lock.json** (`e2ff165`): Regenerado lock file para sincronizar com `package.json` (dnd-kit + outras deps)

## [2026-04-22] - Correções de Badges, Parceiros, Search e Formulário

### Corrigido
- **Header badges** (`9ea2bc1`): Chat badge faz re-fetch ao fechar (não ao abrir), elimina flicker. Notificações usa `count_documents()` para count >100. Chat badge skip polling para parceiro
- **Parceiro role restrictions** (`9ea2bc1`, `bef386f`):
  - Frontend: hide Chat/Tasks/Notifications para parceiro
  - Backend: `is_staff()` usa `STAFF_ROLES` em vez de `!= CLIENTE` (parceiro passava em 15+ endpoints)
  - Backend: `_block_parceiro()` em todos os endpoints de chat e tasks (leitura + escrita)
- **Search indexation bidirecional** (`bef386f`): Client → Process propaga email/phone com `email_hash`, Process → Client regenera hash
- **Public form ordering** (`9ea2bc1`): Campos ordenados por `.sort((a, b) => (a.order || 0) - (b.order || 0))`
- **Temp-links upload** (`9a65467`): Erro 500 → 400 com per-file error reporting
- **Finance 403** (`9a65467`, `bef386f`): Adicionado `INDEXACAO` a `FINANCE_READ_ROLES`
- **Drag & Drop form fields** (`b4f6e8b`): Integração @dnd-kit para reordenação de campos no FormManagementPage

## [2026-04-21] - Webmail Universal, Dashboards e Notificações

### Adicionado
- **Webmail universal IMAP 2-way sync** (`9a41f75`): Sync bidirecional para qualquer conta IMAP, views globais, formatação de equipa
- **Notificação toast deduplication** (`1e4a0ef`): Badge unread messages + eliminação de loops de toast
- **Context Switcher** (`a3df182`, `b584925`): Multi-role switching para utilizadores com dupla função
- **Dashboard cards clicáveis** (`214277c`): Todos os 4 dashboards (Admin, Staff, Consultor, Mediador) com `cursor-pointer`, `hover:shadow-md` e `onClick={() => navigate(...)}`
- **File Explorer** (`5abead7`): UI completa de exploração de ficheiros conectada às APIs de storage
- **Google OAuth 2.0** (`0f95b29`, `72488b2`): Fluxo OAuth completo para conta partilhada de indexação via Gmail API

### Corrigido
- **Notificação loops** (`f4d553f`, `b6e1c8f`): Eliminados loops infinitos de toast e polling de notificações
- **Email isolation** (`a075253`): Removido sync global 'geral', enforced user_id filtering
- **Client sort** (`3287a91`): Corrigida lógica de ordenação na lista de clientes

## [2026-04-20] - UX, Permissões e Estabilidade

### Adicionado
- **Email template preview** (`bab14f5`): Pré-visualização de templates de email + company email config UI
- **Cascade soft delete** (`bab14f5`): Regras de eliminação em cascata para processos
- **SmartRichEditor** (`2c85c79`): Componente abstrato para simplificar complexidade HTML para não-admins
- **AI Executive Summary** (`b051c2f`): Resumo executivo IA com auditoria cross-reference entre formulário e documentos
- **Credit cards editáveis** (`c888b61`, `85a40c2`): Créditos Ativos e Simulações editáveis inline
- **Data sanitization pipeline** (`a794ae0`): Pipeline Prod→Dev com anonimização completa de PII

### Corrigido
- **OAuth redirect 401 loop** (`23c3e93`): Corrigido loop infinito no redirect OAuth
- **Webmail database querying** (`23c3e93`): Fix de queries IMAP pessoal e geral
- **Chart -1 dimension errors** (`65515db`, `4150cd8`, `ab7c8f5`): Proteção contra dimensões -1 em Recharts
- **Multiple JSX/build fixes** (`ac47811`, `7f2e380`, `92d983f`): Comentários JSX não fechados, imports em falta, literais `\n`
- **Router mismatches** (`9b1fed5`, `f0bb046`): Corrigidas rotas, links da sidebar e permissões
- **Importações duplicadas** (`f4433df`): Removido import duplicado Plus e Trash2

## [2026-04-19] - Webmail, Permissões e Financeiro

### Adicionado
- **Webmail tabbed interface** (`673e6d0`): Separação entre inbox pessoal e geral por role
- **Strict user isolation** (`c5b73ad`): Isolamento completo de emails por utilizador
- **Manual process association** (`c5b73ad`): UI para associação manual de emails a processos
- **Financeiro restrito** (`be76d5c`): Financeiro acessível apenas a Admin/CEO

### Corrigido
- **Google OAuth redirect_uri** (`28f11f5`): URL de redirect corrigida para shared email
- **IMAP connection errors** (`1eee03b`): Erros propagados ao utilizador em vez de silencioso sucesso
- **Smart threading** (`a819d23`): Threading por In-Reply-To/References + tag `[Proc-{id}]` no assunto

## [2026-04-18] - Filtros, Rotas e Segurança

### Corrigido
- **Filters/sort** (`1000728`, `436cef9`): Botões de filtro e ordenação corrigidos em clientes e processos
- **Missing route** (`9c38a1a`): Adicionado alias `/lista-processos` à sidebar
- **Google OAuth 500** (`265c934`, `5fd3704`): Corrigidos erros no login e callback OAuth

## [2026-04-17] - Grande Sprint de Funcionalidades

### Adicionado
- **Smart email threading** (`a819d23`): Thread por In-Reply-To/References + tags `[Proc-{id}]`
- **Custom email folders** (`5740800`): Sistema de pastas personalizadas (backend + frontend)
- **Webmail Pro** (`80601e9`): Labels, S3 attachments, multi-select, drag-and-drop
- **Multi-role context switching** (`a3df182`): Troca de contexto para utilizadores com múltiplos roles
- **Settings inheritance** (`f553c23`): Herança de IMAP/SMTP do admin para utilizadores, bloqueado para indexacao
- **AI Summary** (`b051c2f`): Resumo executivo com auditoria
- **Field editing** (`85a40c2`): Créditos Ativos e Simulações editáveis inline
- **Team mural likes** (`d65c5b7`): Likes e receipts no mural de equipa
- **General info board** (`54809e5`): Quadro informativo para todos os utilizadores
- **RGPD encryption** (`efb6e4b`, `2826cdd`): Encriptação Fernet + Blind Indexing para clientes
- **Pipeline restauro seguro** (`ad53622`, `a794ae0`): S3 → Dev com sanitização RGPD
- **Dedicated Collection Pattern** (`d8f6355`): Histórico em coleção separada (evita 16MB)
- **Performance optimization** (`4c5425d`): Endpoints de listagem otimizados
- **IDOR protection** (`8efa4b8`): Proteção em endpoint de AI suggestions
- **Blind indexes** (`3f7b681`): Índices MongoDB para hashes de email, NIF, telefone

### Corrigido
- **Login SHA-256** (`bed2397`, `4693030`): Login aceita SHA-256 + auto-migração para bcrypt
- **Password defaults** (`bcb9161`, `ef6e4fb`): Password default e fix-passwords endpoints
- **MongoDB projection error** (`fe0f8fb`): Corrigido mix de exclusão/inclusão
- **Kanban filters** (`fae6a52`): Filtros do Kanban agora atualizam corretamente
- **Sidebar menus** (`34ba0d7`, `d10d79d`): Menus reestruturados por role
- **20+ JSX/build fixes**: Comentários JSX, imports React, literais template, erros Vercel

## [2026-04-14] - CI/CD, Documentação e Resiliência

### Adicionado
- **CI/CD Pipeline** (`05bb918`): GitHub Actions com frontend CI (ESLint + Vite build) e backend CI (Flake8 + Pytest)
- **Documentation** (`75acd7e`, `31d629e`, `fb9bbc8`, `4e33ebc`): JSDoc (pt-PT) em componentes, docstrings Google-style em serviços e rotas
- **429 Retry** (`800a5a6`): Exponential backoff (3 tentativas) + jitter
- **Chunk Error Recovery** (`dbfab8a`): LazyChunkErrorBoundary para stale deployments
- **ARQ Worker** (`6d51c43`): Motor de tarefas assíncronas com centro de operações
- **TanStack Query** (`2a4b6b0`): Migração de estado para TanStack Query v5
- **Direct S3 Upload** (`ad0f30f`): Pre-signed URLs para upload directo ao S3
- **Diagnostics page** (`8c017ec`): Página de diagnóstico do sistema
- **Security headers** (`1be514e`): HSTS, CSP, X-Frame-Options no Vercel
- **Function Calling IA** (`fe43e83`): Migração de JSON prompting para OpenAI Function Calling

### Corrigido
- **Test async loop** (`f84765d`, `176ee0e`): Resolvido Future attached to different loop
- **Node.js 24 CI** (`6c6cb65`, `eec4587`): Re-habilitado com ghost submodule removido
- **pytest compatibility** (`c45f09d`): Pin pytest==8.3.5 para resolver conflito com pytest-asyncio
- **React 19 compatibility** (`875098e`, `c3d4bf0`): react-day-picker upgrade, date-fns downgrade

## [2026-04-13] - Webmail Avançado

### Adicionado
- **Webmail 3 colunas** (`fcb858b`): Interface estilo Outlook com compositor de emails
- **Email sync background** (`fab2ef9`, `041799b`): Sync via POST + ARQ worker em background
- **S3 attachments** (`80601e9`): Anexos de emails guardados no S3
- **Smart threading** (`a819d23`): Threading por In-Reply-To + tag `[Proc-{id}]`
- **IMAP fetch fixes** (`8bef4b2`, `581feea`, `83f104d`): 5+ correções em fetch response format e login credentials

## [2026-04-12] - Gestão de Processos e IA

### Adicionado
- **Smart process creation** (`c226fdf`): Pesquisa inteligente de clientes com deduplicação
- **AI Executive Summary** (`b051c2f`): Resumo executivo com cross-reference audit
- **AI Confidence scoring** (vários): Score 0.0-1.0 por campo, alertas visuais

### Corrigido
- **Workflow states** (`350b24f`): Removido nomes internos dos estados da UI
- **Sidebar Novo Processo** (`95da0ee`, `a90e92f`): Removido botão (processos criados via Kanban/Client)
- **AI suggestions endpoint** (`ea57bd0`): Corrigido receive body correctly
- **Import decrypt** (`e4d5979`): Corrigido import de decrypt_client_data

## [2026-04-11] - Plataforma Estável

### Adicionado
- **CI Pipeline** (`05bb918`): GitHub Actions completo
- **Dashboard reestruturado** (`ec4c8f6`): KPI cards, funnel, feed atividade
- **WebSocket singleton** (`c70419a`): Uma ligação partilhada entre componentes
- **Real-time Kanban** (`54e9d31`): Colaboração multiplayer em tempo real
- **Client Portal** (`4eccc0b`): Magic Link passwordless
- **CDC Audit** (`4b4e906`): Change Data Capture com Ghost Mode para indexacao
- **Surgical cache invalidation** (`df38ac2`): Invalidação precisa de cache TanStack Query

### Corrigido
- **React Error #300** (`9007efe`): Infinite re-render loops resolvidos
- **Multiple build/test fixes** (20+ commits): JSX, imports, projections, async loops
- **Kanban board modularity** (`0b758a1`): Refatorado de monolito para componentes SRP
- **Performance** (`98ae95d`): Resolvido Unbounded Arrays & I/O Degradation

## [2025-06-27] - Correções de Build e Resiliência (Vercel + Rate Limiting)

### Corrigido
- **Vercel MIME type crash (`dbfab8a`)**: O rewrite `"/(.*)"` no `vercel.json` interceptava pedidos a chunks JS em `/assets/`, retornando `index.html` (text/html) em vez do ficheiro JS. Corrigido com negative lookahead: `/((?!assets|_next|favicon\.ico|robots\.txt|manifest\.json|sw\.js|workbox-|icon-.*\.png).*)`.
- **LazyChunkErrorBoundary(`dbfab8a`)**: Adicionados 4 novos padrões de deteção (`text/html`, `MIME type`, `Unexpected token`, `Script error`) para capturar erros de stale deployments que antes causavam crash na ErrorBoundary do Sentry.
- **MyClientsPage JSX crash (`fd84f29`)**: Removido `</div>` orfão na secção de filtros que causava 4 erros cascata de mismatch de tags no Vercel build.
- **429 Rate Limit cascade (`4268eec`)**: 
  - **API Interceptor**: Adicionado retry com exponential backoff (3 tentativas: 2s → 4s → 8s + jitter), respeita header `Retry-After`, suprime toast durante retries para evitar spam de erros.
  - **NotificationsDropdown**: Polling com exponential backoff em 429 (30s → 60s → 120s → 5min max), reset após 3 sucessos consecutivos.
- **StatisticsPage crash (`97bfed9`)**: `X.filter is not a function` — a API retorna resposta paginada `{'items': [], 'total': 0}` mas o frontend chamava `.filter()` diretamente no objeto. Adicionados guards `Array.isArray()` em `processes`, `leadsStats.funnel_data`, `leads_by_source`, `top_consultors`.
- **Os Meus Processos - Filtros estritos (`ec4c8f6`)**: Exclusão por defeito de status terminais (concluido, arquivo, perdido, desistencias, cancelado) com toggle "Mostrar Concluídos".

### Alterado
- **AdminDashboard reestruturado (`ec4c8f6`)**: 4 KPI cards (Processos Ativos, Valor Portfolio, Taxa Conversão, Novos Hoje), gráfico funnel (Lead → Submetido → Aprovado → Escriturado), feed de atividade recente.
- **Impersonate bar layout (`ec4c8f6`)**: Corrigido z-index e margin-top para não sobrepor header/sidebar.

## [2025-06-26] - CI, UX e Qualidade

### Adicionado
- **UX v2 (`fa28564`)**: Credenciais do 2º proponente na tab Financeiros, badge forte no Kanban, fix preview RGPD, editor RichText avançado com prop `advanced`.

### Corrigido
- **SystemConfigPage JSX (`1b91454`)**: Comentário JSX `{/* ... */}` não fechado na secção de Pré-visualização.
- **KanbanCard template literal (`7d99aca`)**: Backtick não fechado na deteção de 2º proponente.
- **Quill bullet format (`6265964`)**: Removido `'bullet'` inválido da config de formats do Quill (é um valor de `'list'`, não um format independente).
- **CI Node.js 24 (`6c6cb65`)**: Re-habilitado Node.js 24 no GitHub Actions (ghost submodule já removido em commit anterior).
- **Backend tests (`1e63fac`)**: Adaptados testes de processos para resposta paginada da API (`{'items': [...], 'total': N}`) e relaxada assertion de status default no delete.
- **Test async loop (`f84765d`)**: Resolvido `Future attached to a different loop` errors nos testes backend.

## [2025-06-25] - Melhorias de UX, Sidebar e Editor HTML

### Adicionado
- **AuditTrailPage DashboardLayout**: Envolvido conteúdo com `DashboardLayout` para consistência visual.
- **Sidebar accordion fix**: Corrigido `onOpenChange` com `e.stopPropagation()` nos links internos. Adicionadas rotas em falta ao `getInitialOpenSections()`.
- **Rich Text Editor RGPD**: Substituído `<Textarea>` por `<RichTextEditor>` com `readOnly` baseado em permissões. Pré-visualização com `RichTextViewer`.
- **Kanban 2nd Proponent Indicator**: Detecção de 2º proponente, borda lateral indigo, badge "2º Proponente".
- **Tasks Panel reposicionado**: Movido para coluna direita (sidebar) nos detalhes do processo.
- **RGPD confirmation dialog**: Confirmação `window.confirm()` antes de enviar email de RGPD.
- **Magic Link Portal Button**: Botão "Portal do Cliente" com opções copiar link / enviar por email.
- **CI Pipeline**: GitHub Actions com frontend CI (ESLint + Vite build) e backend CI (Flake8 + Pytest).

### Corrigido
- **CI ghost submodule**: Removido `PowerCell` submodule fantasma do git index (`2e232ad`).
- **pytest.ini multiline**: Removida continuação de linha com backslash que causava parsing error (`9de712b`).
- **DashboardShared unsafe**: Corrigido padrão unsafe para `client_name`/`client_email` potencialmente undefined.

## [2026-04-02] - Correções de Bugs

### Corrigido
- **Erro 500 em PATCH /system-config/dsti_analysis**: A secção `dsti_analysis` estava definida em CONFIG_FIELDS mas não tinha handler na função `update_config_section()`. Adicionado handler e import de `DSTIConfig`.
- **AWS Secret Key - Olho de revelação**: `aws_secret_access_key` não estava na lista de campos reveláveis no endpoint `/reveal-secrets`.
- **Auto-fill CC - 5 bugs corrigidos end-to-end**: Fluxo de extração de dados do CC por IA:
  - `cc_validity` era extraído mas fazia drop silencioso no frontend.
  - Dados divergentes (CC renovado) com `type="override"`.
  - Callback `onAIDataExtracted` agora guarda na BD automaticamente.
  - Conflitos usam `comparison.different` em vez de `auto_fill_suggestions`.
  - Campos em falta no endpoint `apply_ai_suggestions`: `entidade_empregadora`, `categoria_profissional`, `subsidiario_alimentacao`, `artigo_matricial`.
- **Perfil Indexação**: Permissões refinadas — vê APENAS processos atribuídos.
- **Mapeamento automático de pastas**: Ficheiros agora movem-se no S3 (antes só criava pastas).
- **Métrica de confiança da IA por campo**: Sistema 0.0-1.0 por campo, alertas visuais para < 0.8.

## [2026-04-01] - Funcionalidades e Correções

### Adicionado
- **Auto-Rascunhos de E-mails por IA**: Toggle on/off, 6 endpoints REST, tab no StaffDashboard.
- **Sistema de Anotações Contextuais em Documentos**: 5 tipos, backend + frontend completo.
- **Trilhas de Auditoria (Audit Trails)**: Colecção dedicada, IP tracking, 4 origens, exportação CSV.

## [2026-04-01] - Correções e Melhorias

### Corrigido
- **AWS Secret Access Key visível na UI**: Adicionado à lista de campos sensíveis.
- **Campos de password**: Todos os campos password adicionados à lista de mascaragem.

## [2026-03-24] - Pré-visualização para Consultores e Correções de Build

### Adicionado
- **Pré-visualização do Formulário para Consultores**: Botão na página de Registos, rota `/formulario-consultor`.
- **Ver processos sem atualização**: Lista detalhada expandível no Dashboard.
- **Link S3 automático**: Gerado ao criar processo.

### Corrigido
- **Build de produção**: Separada instalação em 2 passos (PyPI público + índice privado).
- **Processos sem atualização**: Lista de estados finais corrigida.

## [2026-03-24] - Templates e Campos Personalizados

### Adicionado
- **Templates de Formulário**: 3 pré-definidos + duplicar + ativar.
- **Campos Personalizados Dinâmicos**: 6 tipos, editor de opções inline.
- **Página Configurações de Perfis**: Gestão de permissões por utilizador.
- **Página Gestão do Formulário**: Ativar/desativar campos, templates.

## [2026-03-24] - Backlog P2 Completo

### Adicionado
- **Motor de Automação No-Code**: CRUD de regras "Se X, Então Y".
- **WebSocket Fallback**: Polling HTTP automático (MAX_WS_FAILS=3).
- **Testes Acessibilidade**: axe-core em dev.
- **Encriptação**: Fernet AES-128-CBC no formulário público.

## [2026-03-23] - Integrações e Cache

### Adicionado
- **Sentry**: SDK frontend + backend.
- **Redis Cache**: Cache com Upstash Redis (TTL 60-300s).
- **Notificações de Processos Parados**: Tarefa agendada (>7d, >14d, >21d).
- **Audit Trail Unificado**: Componente "Filme da Lead".

## [2026-03-23] - Correções em Lote (P0/P1)

### Adicionado
- **Skeletons**: Loading skeletons em 18+ páginas.
- **Filtros Kanban**: Por data e urgência.
- **Undo Toast**: Ação de desfazer em operações destrutivas.
- **Card View Mobile**: Vista de cards para 3 páginas.
- **Cursor Pagination**: No endpoint de clientes.
- **Rate Limiting**: Uploads (30/min), deletes (20/min), IA (10/min).
- **JWT Lifecycle**: Access token 24h + refresh token 7d.

### Corrigido
- E1.2 a E2 - Vários bugs de UI e validação.
- M1-M9 - Todas as melhorias solicitadas.

## [2026-03-20] - Correções de Bugs

### Corrigido
- **RGPD Status Endpoint**: Validação UUID, tratamento de erros.
- **Temp Links Create**: Validação de `process_id` vazio.
- **RGPD Service**: Validação de entrada, parsing de datas.

### Documentação
- Criado README.md e CHANGELOG.md.

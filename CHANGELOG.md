# Changelog

Todas as mudanças notáveis neste projeto serão documentadas neste arquivo.
O formato é baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.0.0/).

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

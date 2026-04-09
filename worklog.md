---
Task ID: 13
Agent: Main Agent (Frontend Architect)
Task: Resolver violação CRÍTICA do paradigma declarativo do React (Manipulação Direta da DOM)

Problem Statement:
Em várias partes do frontend, o código estava a usar manipulação direta da DOM:
- document.getElementById() para capturar elementos
- document.querySelector() para busca de campos
- element.style.display = "none" para esconder elementos
- element.classList.add/remove() para classes
- innerHTML para overlays

Isto viola o paradigma declarativo do React, podendo causar:
- Estados inconsistentes entre Virtual DOM e Real DOM
- Memory leaks quando referências ficam órfãs
- Crashes quando a árvore DOM muda externamente

Solution: React Way Refactoring

Work Log:
- Scan completo ao frontend/src com grep para identificar violações
- Encontrados 6 ficheiros com violações legítimas + 4 com uso intencional

Ficheiros Refatorados (6):
1. KanbanBoard.js - document.getElementById → useRef + useCallback
   - Adicionado scrollContainerRef para container de scroll
   - Função scrollContainer agora usa ref.current em vez de DOM query
   
2. PublicClientForm.js - document.querySelector → useRef + scoped query
   - Criado fieldRefs e formContainerRef para gestão de refs
   - Criado registerFieldRef callback e findFieldElement helper
   - Validação agora usa refs em vez de querySelector global
   - Adicionado forwardRef ao ValidatedInput
   
3. DocumentChecklist.js - document.getElementById → useRef
   - Adicionado folderInputRef para input de pasta
   - Botão agora usa ref.current?.click() em vez de DOM query
   
4. TempLinkUploadPage.js - document.getElementById → useRef
   - Adicionado fileInputRef para input de ficheiros
   - Drop zone agora usa ref.current?.click()
   
5. ThemeContext.js - Documentado como CORRETO
   - classList no document.documentElement é a API do Tailwind para dark mode
   - Adicionada documentação a explicar que é intencional
   
6. ClientPropertyMatch.js - style.display → useState
   - Adicionado estado imageError ao componente MatchCard
   - onError agora usa setState em vez de style.display
   - Renderização condicional em vez de CSS manipulation

Ficheiros Documentados como Intencionais (4):
- main.jsx - document.getElementById("root") é o mount point do React
- PDFAnnotationViewer.js - innerHTML/style necessários para PDF.js canvas
- IdealistaImportPage.js - innerHTML em bookmarklet (corre noutros sites)
- HtmlImportModal.js - innerHTML em bookmarklet (corre noutros sites)

Custom Hooks Criados (2):
- useScrollToElement.js - Hook para scroll automático com refs
- useOnClickOutside.js - Hook para detetar cliques fora com cleanup

Stage Summary:
- 10 ficheiros modificados + 2 novos hooks
- Violações de paradigma resolvidas com padrões React corretos
- Casos legítimos documentados (PDF.js, Tailwind dark mode, bookmarklets)
- Custom hooks criados para reutilização futura
- Código agora adere estritamente aos Hooks do React

---
Task ID: 12
Agent: Main Agent
Task: Refatoração KanbanBoard - SRP & Performance (Tech Debt)

Problem Statement:
O ficheiro `frontend/src/components/KanbanBoard.js` transformou-se num monolito de ~1336 linhas:
- Geria estados de Drag & Drop, renderização de colunas, cartões, e múltiplos Modals tudo num só sítio
- Causava re-renders desnecessários em toda a grelha ao digitar em formulários de modals
- Violação do Princípio de Responsabilidade Única (SRP)
- Manutenção impossível

Solution: Componentização Restrita
- Criada estrutura `frontend/src/components/kanban/` com submódulos dedicados
- Estado dos formulários ISOLADO nos modais (não no componente pai)
- React.memo nos cartões para prevenir re-renders

Work Log:
- Criada pasta `frontend/src/components/kanban/`
- Extraído `KanbanCard.jsx` com React.memo e comparador customizado de props
- Extraído `KanbanColumn.jsx` com lógica de drop e renderização de cartões
- Extraído `KanbanHeader.jsx` com filtros e indicador de WebSocket
- Extraído `KanbanSkeleton.jsx` para estado de loading
- Extraído `SearchResultsList.jsx` para vista de lista
- Extraído `ProcessDetailsModal.jsx` com estado isolado
- Extraído `CreateClientModal.jsx` com estado de formulário local
- Extraído `AssignUsersModal.jsx` com gestão de utilizadores
- Extraído `constants.js` com cores de status
- Criado `index.js` como export central
- Refatorado `KanbanBoard.js` de 1336 linhas para 486 linhas (~64% redução)
- KanbanBoard agora é apenas ORQUESTRADOR: fetch de dados, estado global, contexto de D&D
- Build validado com sucesso

Stage Summary:
- Ficheiros criados: 10
  - frontend/src/components/kanban/index.js
  - frontend/src/components/kanban/constants.js
  - frontend/src/components/kanban/KanbanCard.jsx
  - frontend/src/components/kanban/KanbanColumn.jsx
  - frontend/src/components/kanban/KanbanHeader.jsx
  - frontend/src/components/kanban/KanbanSkeleton.jsx
  - frontend/src/components/kanban/SearchResultsList.jsx
  - frontend/src/components/kanban/ProcessDetailsModal.jsx
  - frontend/src/components/kanban/CreateClientModal.jsx
  - frontend/src/components/kanban/AssignUsersModal.jsx
- Ficheiros modificados: 1
  - frontend/src/components/KanbanBoard.js (1336 → 486 linhas)
- Performance: React.memo nos cartões previne re-renders quando inputs de modals mudam
- Arquitetura: SRP respeitado - cada componente tem uma única responsabilidade
- Drag & Drop: Funcionalidade preservada com callbacks passados como props

---
Task ID: 11
Agent: Main Agent
Task: Atualização de Documentação - Blind Indexing & Dedicated Collection Pattern

Problem Statement:
Documentar as implementações de segurança e arquitetura:
1. Blind Indexing para dados encriptados (RGPD)
2. Dedicated Collection Pattern para histórico

Architecture Analysis:
**Blind Indexing (Deterministic Hashing)**
- Campos encriptados (NIF, email, telefone) são pesquisáveis via hashes SHA-256
- Implementação: services/encryption.py - generate_nif_hash(), generate_email_hash()
- Índices MongoDB apontam para *_hash, NUNCA para dados encriptados
- Coleções: clients (nif_hash, email_hash, telefone_hash), processes (nif_hash)
- db_indexes.py linhas 413-480: índices blind indexes criados

**Dedicated Collection Pattern (Histórico)**
- Histórico NÃO é guardado em arrays embebidos no documento principal
- Coleção dedicada: `history` com documentos independentes
- Cada entrada: id, process_id, user_id, action, field, old_value, new_value, created_at
- Endpoint dedicado: GET /history?process_id=xxx (routes/activities.py:92-103)
- Modelo: HistoryResponse (models/activity.py:20-29)
- Índices críticos: idx_history_process_time, idx_history_user_time, idx_history_action_time

Work Log:
- Clonado repositório PowerCell do GitHub (branch: dev)
- Analisado services/history.py: log_history() usa coleção dedicada ✓
- Analisado routes/activities.py: endpoint GET /history dedicado ✓
- Analisado db_indexes.py: índices blind indexes + history ✓
- Analisado process_service.py: history REMOVIDO de create_process_document ✓
- Analisado ProcessResponse: SEM campo history embutido ✓
- Confirmado: arquitetura já corretamente implementada

Stage Summary:
- Ficheiros analisados: 8
  - backend/services/history.py
  - backend/services/process_service.py
  - backend/services/db_indexes.py
  - backend/services/encryption.py
  - backend/routes/activities.py
  - backend/routes/processes.py
  - backend/models/activity.py
  - backend/models/process.py
- Architecture Patterns: Dedicated Collection + Blind Indexing
- Conformidade RGPD: dados encriptados pesquisáveis via hashes determinísticos
- Performance: queries de timeline instantâneas via índices compostos

---
Task ID: 10
Agent: Main Agent
Task: Resolver falha arquitetural CRÍTICA - Unbounded Arrays & I/O Degradation

Problem Statement:
O sistema estava a guardar histórico em arrays embebidos no documento principal (`"history": [...]` usando `$push`). Com o tempo, este array cresce infinitamente, causando:
- MongoDB 16MB document limit crash
- I/O degradation (reescrita de documento inteiro a cada alteração)
- Memory bloat nas listagens
- Performance degradation em operações de update

Solution: Dedicated Collection Pattern
- Histórico movido para coleção dedicada `history`
- Cada entrada é um documento independente
- Queries usam índice process_id + timestamp (instantâneas)
- Documentos de processo mantêm-se pequenos e rápidos

Work Log:
- Analisado process_service.py: linha 266-272 criava array history embebido
- Analisado process_kanban.py: linha 200 usava $push para history
- Analisado services/history.py: já usava coleção dedicada (bom!)
- Identificados outros locais com problema: leads.py, properties.py, ai_bulk.py
- Removido array history embebido de process_service.py
- Corrigido process_kanban.py para usar log_history (coleção dedicada)
- Adicionados índices críticos em db_indexes.py:
  - idx_history_process_time (process_id + created_at desc)
  - idx_history_user_time (user_id + created_at desc)
  - idx_history_action_time (action + created_at desc)
  - idx_history_created_desc
  - idx_history_field
- Adicionado 'history' ao get_index_stats

Stage Summary:
- Ficheiros modificados: 3
  - backend/services/process_service.py
  - backend/services/process_kanban.py
  - backend/services/db_indexes.py
- Architecture Pattern: Dedicated Collection Pattern
- Índices críticos para timeline queries instantâneas
- Documentos de processo agora livres de arrays não limitados

NOTA: Outros arrays embebidos em leads.py e properties.py ainda precisam de refatoração similar.

---
Task ID: 9
Agent: Main Agent
Task: Implementar templates HTML personalizados com todas as variáveis disponíveis

Work Log:
- Criada função _extract_email_variables() para extrair todas as variáveis do processo
- Atualizado processamento do template para usar todas as variáveis disponíveis
- Adicionado template HTML profissional como predefinição no frontend
- Criada lista completa de variáveis organizadas por categoria (1º Proponente, 2º Proponente, Crédito, Transferência, Remetente)
- Variáveis agora são clicáveis para copiar (UX melhorada)
- Template suporta HTML completo com estilos inline

Stage Summary:
- Commit 5a7a6bd: Implementar templates HTML personalizados com todas as variáveis disponíveis
- Ficheiros: backend/routes/emails.py, frontend/src/components/DocumentRecipientsManager.js
- 323 linhas adicionadas, 48 removidas
- 37 variáveis disponíveis para uso em templates personalizados
- Template predefinido inclui todas as secções (1º Proponente, 2º Proponente, Crédito Atual, Transferência Pretendida)

---
Task ID: 8
Agent: Main Agent
Task: Corrigir bug na eliminação de destinatários BCC nas configurações do sistema

Work Log:
- Analisado DocumentRecipientsManager.js - função handleDeleteRecipient apenas removia localmente
- Identificado que as alterações não eram guardadas automaticamente após eliminar
- Utilizador precisava de clicar em "Guardar Configuração" manualmente
- Corrigido handleDeleteRecipient para guardar automaticamente no servidor
- Corrigido handleSaveRecipient para guardar automaticamente após adicionar/editar
- Corrigido toggleActive para guardar automaticamente após activar/desactivar
- Adicionadas mensagens de feedback adequadas (sucesso/erro)
- Adicionada reversão local em caso de erro no servidor

Stage Summary:
- Commit bb273b5: Corrigir eliminação de destinatários BCC - guardar automaticamente após cada operação
- Ficheiro: frontend/src/components/DocumentRecipientsManager.js
- 106 linhas adicionadas, 11 removidas
- Agora todas as operações (adicionar, editar, eliminar, toggle) guardam automaticamente
- Melhoria significativa na UX - utilizador já não precisa de clicar em "Guardar"

---
Task ID: 7
Agent: Main Agent
Task: Corrigir erro 404 em POST /api/emails/send-documentation/{process_id} + bugs relacionados

Work Log:
- Analisado SendDocumentationModal.js (frontend) - URL e payload corretos
- Analisado backend/routes/emails.py - rota send-documentation EXISTE (linha 146)
- Analisado server.py - router montado corretamente, doc_router removido
- Verificado ordem de rotas - send-documentation antes de /{email_id}, sem conflito
- Identificado bug AttributeError: acc.get('imap_user') em email_service.py linha 774
- Identificado bug funcional: documentos NÃO eram anexados ao email enviado
- Identificado bug: registo duplicado no histórico de emails (send_email + rota)
- Corrigido acc.get() → acc.email (EmailAccount é objeto, não dict)
- Adicionado suporte a attachments em send_email() (MIMEMultipart mixed + MIMEApplication/MIMEBase)
- Rota send-documentation agora descarrega documentos do S3 e anexa ao email
- Removido registo duplicado, adicionada label "documentação" ao registo existente

Stage Summary:
- Commit c2752d1: fix send-documentation (3 bugs corrigidos)
- Ficheiros: backend/services/email_service.py, backend/routes/emails.py
- 404: rota já existia, código precisa ser deployado no Render
- Novos imports: MIMEBase, MIMEApplication, email_encoders, mimetypes

---
Task ID: 1
Agent: Super Z (main)
Task: Implementar funcionalidade Auto-Rascunho de E-mails

Work Log:
- Analisado código existente: routes/emails.py, models/system_config.py, services/ai_document_analyzer.py, services/system_config.py, StaffDashboard.js, SystemConfigPage.js, api.js
- Verificado que a implementação anterior não foi persistida (commit f99b9eb não existe)
- Criado backend/services/email_draft_service.py (serviço completo de geração de rascunhos por IA)
- Adicionado AutoDraftConfig ao modelo system_config.py
- Adicionados 6 endpoints de rascunhos em routes/emails.py (GET drafts, GET stats, PUT edit, POST send, DELETE discard, POST create)
- Integrado com ai_document_analyzer.py (analyze_multiple_documents chama create_missing_doc_draft)
- Adicionada secção "auto_draft" às CONFIG_FIELDS em routes/system_config.py
- Adicionado handler para secção "auto_draft" em services/system_config.py (update_config_section)
- Adicionadas 7 funções API em api.js (getAutoDrafts, getAutoDraftStats, editAutoDraft, sendAutoDraft, deleteAutoDraft, createAutoDraft)
- Adicionada tab "Rascunhos Pendentes" ao StaffDashboard.js com preview expandível e ações
- Atualizado SystemConfigPage.js com ícone FileEdit para secção auto_draft
- Todas as validações de sintaxe Python passam

Stage Summary:
- Funcionalidade Auto-Rascunho implementada em 8 ficheiros (1 novo + 7 modificados)
- 426 linhas adicionadas, 6 removidas
- Deduplicação de rascunhos, toggle on/off via config, integração com análise de documentos

---
## Task ID: 2 - main
### Work Task
Implementar sistema de Audit Trail completo para o PowerCell.

### Work Summary
Criado sistema de auditoria completo com 3 novos ficheiros e 8 ficheiros modificados:

**Ficheiros Criados (3):**
- `backend/services/audit_trail_service.py` (414 linhas) — Serviço completo com: log_audit_event (IP, origem, IA tracking), log_ai_approval, get_audit_trail (filtros + paginação), get_audit_stats (dashboard agregado), export_audit_trail (CSV), cleanup_old_records, check_audit_enabled
- `backend/routes/audit.py` (129 linhas) — 4 endpoints REST: GET /audit/trail (paginação + filtros), GET /audit/stats, GET /audit/export (CSV download), POST /audit/cleanup (admin only)
- `frontend/src/pages/AuditTrailPage.js` (511 linhas) — Página admin profissional com: cards de estatísticas (hoje, semana, aprovações IA, críticas), filtros avançados (processo, origem, datas, acção), tabela paginada com badges coloridos por origem, indicadores de IA, exportação CSV, botão de limpeza

**Ficheiros Modificados (8):**
- `backend/models/system_config.py` — Adicionado AuditTrailConfig (enabled, log_ip_address, log_ai_approvals, require_reason_for_critical_fields, critical_fields, retention_days)
- `backend/services/system_config.py` — Handler para secção "audit_trail" em update_config_section com parse de critical_fields JSON
- `backend/routes/system_config.py` — Secção "audit_trail" em CONFIG_FIELDS com 6 campos configuráveis
- `backend/routes/processes.py` — Integração de log_audit_event em todas as secções de update (personal_data, financial_data, real_estate_data, credit_data, status) com suporte a audit_reason e ai_suggested do request body
- `backend/server.py` — Registo do audit_router no api_router
- `frontend/src/services/api.js` — 4 funções API: getAuditTrail, getAuditStats, exportAuditTrail, cleanupAuditTrail
- `frontend/src/App.js` — Rota /auditoria com lazy loading, protegida para admin e CEO
- `frontend/src/layouts/DashboardLayout.js` — Link "Auditoria" com ícone ClipboardList no sidebar para admin e CEO

**Características principais:**
- Colecção MongoDB separada (audit_trail) para backward compatibility com history
- IP tracking via X-Forwarded-For / X-Real-IP / client.host
- Suporte a 4 origens: web, api, ai_automation, email
- Acompanhamento de aprovações/rejeições de sugestões de IA
- Configuração activável/desactivável via SystemConfig
- Retenção configurável com cleanup automático
- Badges coloridos por origem (purple=web, blue=api, orange=ai_automation, green=email)
- Toda a documentação e comentários em Português (pt-PT)
- Validação de sintaxe Python passou com sucesso

---
Task ID: 3
Agent: Super Z (main)
Task: Análise RGPD + Fix email bug + Barras de navegação em emails

Work Log:
- Análise completa do sistema RGPD/GDPR do PowerCell (2 camadas)
- Identificado bug nas Regras 3 e 4 de associação de emails: não verificavam nome do cliente
- Corrigido email_service.py: Regras 3 e 4 agora têm verificação dupla (nome no assunto/corpo)
- Reescrito EmailSearchPage.jsx: barra de navegação prev/next, breadcrumb, atalhos teclado, HTML sanitizado
- Melhorado EmailViewerModal.js: breadcrumb de contexto com nome do cliente/processo
- Atualizado EmailHistoryPanel.js: passa clientName/processId para EmailViewerModal
- Corrigido import em falta (Tag) em EmailViewerModal.js

Stage Summary:
- RGPD: sistema completo com consentimento (token 24h, assinatura canvas, template legal 11 secções) + GDPR (anonimização 30+ campos, direito esquecimento, portabilidade, auditoria)
- Bug: email silvamiranda→geral@precisioncredito.pt aparecia para cliente Nelson Lopes Leite via Regra 4 (sem verificação de nome). Corrigido com verificação dupla em Regras 3 e 4
- Navegação: EmailSearchPage agora tem barra prev/next + breadcrumb + ←/→/Esc. EmailViewerModal mostra contexto do processo/cliente
- Commits: d84c083, 65ad8db (branch dev)

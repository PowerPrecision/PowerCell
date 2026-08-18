# Changelog

Todas as mudanças notáveis neste projeto serão documentadas neste arquivo.
O formato é baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.0.0/).

## [2026-08-18] — Pacote DO.1+2: Observações, Timeline no Resumo e Calendário Visual

### Adicionado
- **Observações no Resumo** (`observations` no modelo de Processo, sincronizado com `notes`): Textarea Shadcn com guardar no botão e no `onBlur`.
- **Timeline compacta** no Resumo (linha vertical + nós) a partir do histórico existente; `GET /processes/{id}/timeline` normaliza criação + mudanças de fase. Histórico completo continua no tab Histórico.
- **Calendário visual** (mensal/semanal, pontos nos dias com eventos) no Dashboard do Consultor e no Portal do Cliente. Consome a Agenda DH; o Portal só mostra `visible_to_client=true` (`GET /portal/events?include_past=true`).

---

## [2026-08-18] — Pacote DN.3+4: Emails do processo e contas múltiplas

### Corrigido
- **Separador Emails do processo**: a listagem (`GET /api/emails/process/{id}`) passa a incluir CC e a procurar no motor todas as mensagens em que De, Para ou CC correspondem ao email do cliente (e 2º titular / emails monitorizados). Mensagens ainda não ligadas a um processo aparecem no histórico; clique abre o leitor. Documentos incompletos (sem `status`/`created_at`) são normalizados para não devolver 500.

### Adicionado
- **Várias contas de email por perfil**: `user_email_configs` deixa de ser 1:1 por empresa. Índice único `{user_id, company_id, email_address}`; campo `is_primary`. Endpoints `GET/POST /users/me/email-accounts` e `PUT/DELETE /users/me/email-accounts/{id}` (+ `set-primary`).
- Área Pessoal: lista de contas no cartão Webmail e botão **+ Adicionar Conta de Email** (IMAP/SMTP ou OAuth) num Dialog Shadcn.
- Webmail: Select no topo para alternar entre as contas do perfil activo (`mailbox=` na listagem/sync).

---

### Corrigido
- **Webmail misturava emails de vários perfis**: a página usava `user.company_id` e `fetch` sem `X-Active-Role`/`X-Company-Id` do Header. Passa a usar `activeCompanyId` do AuthContext e envia o contexto UCR em todos os pedidos. Backend filtra listagem/stats/sync pela mailbox da UCR activa (não inclui emails sem empresa de outras contas).
- **Anexos de emails recebidos não descarregavam**: o botão só aparecia se existisse `attachment.url` (IMAP não gravava URL). Novo `GET /api/webmail/attachments/{id}` devolve stream binário (`Content-Disposition: attachment`) a partir de S3, BD ou IMAP; 404 se o anexo não existir.

### Adicionado
- IDs de anexo na sync IMAP; `company_id` nos emails sincronizados para o perfil activo.
- UI de anexos no painel de leitura: nome, tamanho e botão de download (tokens Shadcn).

---
## [2026-08-18] — Pacote DM: Área Pessoal, Rascunhos e UX Base

### Corrigido
- **Configuração de email multi-perfil**: o interceptor Axios já não sobrescreve `X-Company-Id`/`X-Active-Role` definidos no pedido. `EmailConfigForm` grava IMAP/SMTP isolado por `company_id` (body + query + header da tab). Backend resolve na mesma ordem, com logs e tratamento de erros.
- **Assinatura de email**: HTML (`<p>`, `<br>`, `<img>`) sanitizado com DOMPurify; imagens `data:`/`cid:`/`https`; unescape se estiver gravado como entidades. Pré-visualização na Área Pessoal e no compositor.
- **Rascunhos no Dashboard**: o clique já não envia emails/leads para ProcessDetails. Emails abrem `/webmail?folder=drafts&id=`; pré-registo vai para Registos de Clientes; processos usam `/processo/:id`.

### Alterado
- Perfil **Mediador** removido da UI (`normalizeRole` → Intermediário). Dropbox extra de empresa no Diretor oculta — o contexto vem do perfil no Header.
- **Impersonate**: menus de Administração só se o utilizador impersonado for admin/CEO; `activeRole` é redefinido para o alvo.

---
## [2026-07-25] — Pacote DJ (Híbrido): Sistema de Confiança — Zero-Touch + HITL

### Alterado
- **Sistema Híbrido de Confiança**: o `run_analyze_document_for_review` agora aplica um threshold de confiança em vez de guardar sempre em `suggested_*`:
  - `AI_CONFIDENCE_THRESHOLD = 85` (constante em `document_review.py`).
  - `confidence_score = int(round(confidence * 100))` — converte 0.0-1.0 → 0-100 inteiro.
  - **Se `confidence_score >= 85`**: auto-aplica (Zero-Touch) — escreve em BOTH `suggested_*` E `ai_*`, marca `ai_review_status = "auto_approved"`.
  - **Se `confidence_score < 85`**: guarda apenas em `suggested_*` (HITL), marca `ai_review_status = "pending_review"`.
- **Status values atualizados**: `"pending"` → `"pending_review"` (mais semântico); novo `"auto_approved"` para docs auto-aplicados.
- **Badges no S3FileManager** atualizados em 3 sites (list, grid Todos, grid per-category):
  - `auto_approved` → "✨ Auto-Aprovado" (verde, `bg-primary/10`, informativo).
  - `pending_review` → "⚠️ Revisão Necessária" (âmbar, `bg-accent/15`, clickable — abre modal).
  - Estados `approved`/`rejected`/`edited` e spinner `analyzing` mantidos.
- **Botão global** renomeado de "Analisar IA" para "🧠 Analisar Documentos".
- **`run_get_pending_reviews`** query atualizada de `"pending"` para `"pending_review"`.
- **Resposta da API** agora inclui `confidence_score` (0-100), `auto_approved` (bool), e `ai_review_status`.

### Documentação
- **`ARCHITECTURE.md`**: secção "IA Híbrida" completamente reescrita com diagrama Mermaid do fluxo de threshold (confidence_score → auto_approved vs pending_review), tabela de estados visuais, e código do threshold.

### Técnico
- **Backend modificado** (1 ficheiro): `services/document_review.py` (AI_CONFIDENCE_THRESHOLD + lógica auto-approve + status values + confidence_score na resposta).
- **Frontend modificado** (1 ficheiro): `components/S3FileManager.js` (3 sites de badges atualizados + botão global renomeado).
- **Validação**: `py_compile` ✓; `flake8 --select=E9,F63,F7,F82` → 0 erros; `bun build --no-bundle` ✓ (0 erros); `eslint --quiet` ✓ (0 erros).

## [2026-07-25] — Pacote DJ: IA Human-in-the-Loop — Revisão de Documentos

### Adicionado
- **Fluxo Human-in-the-Loop para IA de documentos**: a IA agora **sugere** metadados (categoria, validade, nome) em vez de os aplicar diretamente. O consultor revê as sugestões num modal e decide quais aceitar ou rejeitar.
- **Novo modelo de dados `suggested_*`**: `document_metadata` ganhou 10 campos: `ai_review_status` (pending|approved|rejected|edited), `ai_reviewed_at`, `ai_reviewed_by`, `ai_applied_fields`, `suggested_category`, `suggested_subcategory`, `suggested_confidence`, `suggested_expiry_date`, `suggested_filename`, `suggested_nome`. A IA escreve em `suggested_*`; `ai_*` só é atualizado quando o consultor aprova.
- **4 novos endpoints**: `POST /documents/{doc_id}/ai-analyze-review` (trigger), `POST /documents/{doc_id}/apply-ai-review` (aplicar), `POST /documents/{doc_id}/reject-ai-review` (rejeitar), `GET /documents/process/{process_id}/pending-review` (listar pendentes). Novo serviço `services/document_review.py`.
- **Botão per-document "Analisar com IA"** (BrainCircuit icon) na lista de ficheiros do S3FileManager — list view + grid view. Gated by `canUseAIDocumentTools`.
- **Badges de estado de revisão** por ficheiro: "A analisar..." (spinner), "Sugestões IA" (clickable, abre modal), "Aprovado", "Rejeitado", "Editado". Em 3 sítios (list, grid Todos, grid per-category).
- **Novo componente `DocumentReviewModal.jsx`**: modal de revisão com grid 3-colunas (Atual → Sugerido) por campo (Nome, Categoria, Validade, Filename), Badge de confiança, toggle selecionar/ignorar por campo, botões "Aplicar Selecionadas" + "Rejeitar Tudo".

### Alterado
- **Projeção do file listing expandida**: `GET /documents/client/{process_id}/files` agora inclui `ai_review_status`, `suggested_*`, `ai_confidence`, `expiry_date`, `ai_subcategory` (antes só 4 campos).
- **4 novos helpers em api.js**: `analyzeDocumentForReview`, `applyAIReview`, `rejectAIReview`, `getPendingReviews`.

### Documentação
- **`ARCHITECTURE.md`**: nova secção "IA Human-in-the-Loop" com diagrama Mermaid do fluxo (trigger → IA → suggested_* → frontend badge → modal → apply/reject → ai_*), tabela `suggested_*` vs `ai_*`, e nota sobre o fluxo paralelo de auto-categorização.

### Técnico
- **Backend modificado** (4 ficheiros): `models/document.py` (10 campos), `services/document_review.py` (NOVO, 4 funções), `routes/documents.py` (4 endpoints + projeção), `services/document_categorization.py` (comentário).
- **Frontend modificado** (3 ficheiros): `services/api.js` (4 helpers), `components/DocumentReviewModal.jsx` (NOVO), `components/S3FileManager.js` (state + handlers + badges + modal mount).
- **Validação**: `py_compile` ✓ (4 backend); `flake8 --select=E9,F63,F7,F82` → 0 erros; `bun build --no-bundle` ✓ (3 frontend, 0 erros); `eslint --quiet` ✓ (0 erros); `vite build` ✓ (0 erros).
- **Dependências**: Nenhuma nova — `BrainCircuit`, `Dialog`, `ScrollArea`, `Badge`, `ArrowRight` já existem em Shadcn/lucide-react.
- **Princípio chave**: a IA escreve SEMPRE em `suggested_*`; `ai_*` só é atualizado quando o consultor aprova. A auto-categorização em background (uploads novos) continua a escrever diretamente em `ai_*` — o HITL é um fluxo paralelo accionado on-demand.

## [2026-07-25] — Pacote DI: Session Clash Fix + PDF HTML/Minuta + Rebranding

### Corrigido
- **Bug crítico: choque de sessões em links públicos de RGPD**: quando um consultor com sessão ativa clicava num link público `/rgpd/:token` recebido por email, a página redirecionava para `/login`. Causa raiz: `AuthContext.js` e `api.js` só isentavam `/portal` do `fetchUser()` mount-time e do redirect 401 — `/rgpd`, `/upload`, `/download` não eram isentados. Criado helper `utils/publicRoutes.js` com `isPublicRoute()` que cobre todas as rotas públicas. `AuthContext` e `api.js` agora usam `isPublicRoute()` em vez de `startsWith('/portal')`.
- **PDF do RGPD desformatado**: o `_build_prefilled_rgpd_pdf` escapava TODO o HTML (`<p>`, `<br>`, `<strong>` apareciam como `&lt;p&gt;` literal). Novo helper `_html_to_flowables` usa `lxml.html` + `bleach` para fazer parse do HTML do `SmartRichEditor` e converter para Flowables do platypus (`<p>` → `Paragraph`, `<strong>` → `<b>`, `<ul>` → `ListFlowable`, etc.). Fallback para plain text (template default) mantido.
- **Minuta de Exclusividade em falta no PDF**: o documento legal é composto por RGPD + Minuta, mas o PDF só gerava a primeira parte. Agora `run_generate_prefilled_rgpd_pdf` busca também o texto da Minuta via `_get_rendered_minuta_text` e o builder insere um `PageBreak()` + título "MINUTA DE EXCLUSIVIDADE" + corpo + secção de assinatura (linhas em branco para caneta).
- **"Endereço IP" no PDF**: removido o bloco que desenhava `Endereco IP: {client_ip}` no PDF legacy (`_build_rgpd_pdf` em `rgpd_service.py`). O email de auditoria ao staff mantém o IP (não é client-facing).

### Alterado
- **Rebranding "PowerCell" → "Precision Crédito"**: substituição em ~30 pontos client-facing (emails, PDFs, notificações, seeds) em 13 ficheiros backend. Inclui: assuntos de email, assinaturas ("Equipa PowerCell" → "Equipa Precision Crédito"), URLs (`www.powercell.pt/portal` → `www.precisioncredito.pt/portal`), rodapés de PDF, `empresa_nome` fallback, `company_name` no seeder. Referências internas (JSDoc, GitHub repo, dev DBs, test passwords, logo assets, Sentry) mantidas como "PowerCell".

### Técnico
- **Backend modificado** (14 ficheiros): `services/rgpd_pdf.py` (HTML→Flowables + Minuta), `services/rgpd_service.py` (IP removido + rebranding), `services/rgpd_public.py`, `services/email.py`, `services/admin_users.py`, `services/notification_service.py`, `services/portal_documents_notify.py`, `services/temp_link_service.py`, `services/portal_magic_link.py`, `services/public_registration.py`, `services/template_generator.py`, `services/finance_pool.py`, `services/finance_commissions.py`, `seed_database.py`.
- **Frontend modificado** (3 ficheiros): `utils/publicRoutes.js` (NOVO), `contexts/AuthContext.js` (isPublicRoute + guard 401), `services/api.js` (isPublicRoute em 3 sítios do 401 handler).
- **Validação**: `py_compile` ✓ (14 backend); `flake8 --select=E9,F63,F7,F82` → 0 erros; `bun build --no-bundle` ✓ (3 frontend, 0 erros); smoke test confirma PDF com 2 páginas (RGPD + Minuta), HTML parsed (sem `&lt;p&gt;` literal), sem "Endereço IP".
- **Dependências**: Nenhuma nova — `lxml` e `bleach` já instalados.

## [2026-07-25] — Pacote DH: Progressive Disclosure + Agenda (Prazo/Evento) + Portal Events

### Adicionado
- **Modelo de Agenda dual (Prazo/Evento)**: o modelo `Deadline` (`models/deadline.py`) ganhou 3 campos: `type` (`"deadline"` | `"event"`), `visible_to_client` (bool, default False), `reminder_time` (`List[str]` com valores `"1h"`, `"3h"`, `"1d"`, `"3d"`, `"7d"`). Validadores Pydantic para dedup e rejeição de valores inválidos.
- **Novo tipo de notificação `EVENT_REMINDER`** em `NotificationType` (`models/enums.py`).
- **Endpoint `GET /api/portal/events`**: retorna eventos visíveis ao cliente (`visible_to_client=True`, não concluídos, `due_date >= hoje`), ordenados por data. Novo serviço `services/portal_events.py`.
- **Secção "Próximos Eventos" no Portal do Cliente** (`ClientPortal.jsx`): card na TOP SECTION que lista eventos visíveis com Badge (Prazo/Evento) e data. Oculta quando vazia; `EmptyState` quando não há eventos.
- **Calculadora de Prestações no menu Simulações** (`ProcessDetails.js`): novo item "Simulação de Crédito Habitação" no dropdown de Simulações que abre um `Sheet` lateral com o `MortgageSimulator`.

### Corrigido
- **Cron de deadlines SILENTIOSAMENTE BROKEN**: `check_upcoming_deadlines` (`scheduled_tasks.py`) queries `{"date": ...}` (campo inexistente — deveria ser `due_date`) e itera `deadline.get("participants", [])` (campo inexistente — deveria ser `assigned_user_ids`). O cron encontrava 0 deadlines e notificava 0 utilizadores. Reescrito com: query correta `due_date`, iteração `assigned_user_ids`, branching por `type` (deadline → `DEADLINE_APPROACHING`/`DEADLINE_MISSED`; event → `EVENT_REMINDER`), respeito por `reminder_time`, idempotência via `sent_reminders` array.
- **`notify_deadline_reminder`** (`realtime_notifications.py`): lia `participants` (inexistente) — corrigido para `assigned_user_ids`.
- **`assigned_user_ids` não persistido em update**: `DeadlineUpdate` declarava o campo mas `run_update_deadline` nunca o processava. Agora processado.
- **Mapeamentos de notificação**: `NOTIFICATION_TYPE_MAP` (`notification_service.py`) e `NOTIFICATION_TYPE_TO_PREF_KEY` (`realtime_notifications.py`) não mapeavam `deadline_approaching`, `deadline_missed`, `event_reminder` — agora mapeados.

### Alterado
- **Progressive Disclosure em 7 cartões vazios**: cartões que não tinham dados ficavam abertos a ocupar ecrã. Agora recolhem por omissão quando vazios (mostrando apenas o cabeçalho + "Sem dados preenchidos"):
  - FinancialTab: "Situação Financeira" + "Situação Profissional"
  - RealEstateTab: "Características do Imóvel" + "Localização" + "Dados do CPCV" + "Dados do Vendedor"
  - CreditTab: "Avaliação Bancária"
  - Usa o pattern inline existente (`collapsible` prop + `isCardEmpty` + `shouldCardBeCollapsed`) — 7 novos cases em `isCardEmpty`.
- **DeadlinesTab → "Agenda"**: renomeada de "Prazos" para "Agenda". Formulário de criação estendido com: Select de tipo (Prazo Limite vs Marcação), Select de lembrete (1h/1d/3d/7d antes), Switch "Visível no Portal do Cliente" com description de ajuda. Listagem mostra Badge (Prazo/Evento), ícone Sino (se tem alerta), ícone Olho (se partilhado com cliente). `EmptyState` canónico substitui o `<p>Sem prazos</p>` ad-hoc.

### Documentação
- **`ARCHITECTURE.md`**: nova secção "Agenda — Dualidade Prazo/Evento" com modelo de dados, tabela de comportamento por tipo, diagrama Mermaid do fluxo (staff → cron → notificações + portal → cliente).

### Técnico
- **Backend modificado** (8 ficheiros): `models/deadline.py` (3 campos + validadores), `models/enums.py` (EVENT_REMINDER), `services/deadlines_api_crud.py` (persistência + bugfix assigned_user_ids), `services/scheduled_tasks.py` (cron reescrito), `services/notification_service.py` (mapeamentos), `services/realtime_notifications.py` (mapeamentos + bugfix participants), `services/portal_events.py` (NOVO), `routes/portal.py` (novo endpoint).
- **Frontend modificado** (6 ficheiros): `pages/ProcessDetails.js` (7 isCardEmpty cases + deadlineForm + Agenda label + MortgageSimulator Sheet), `tabs/FinancialTab.jsx` (2 cartões collapsible), `tabs/RealEstateTab.jsx` (4 cartões collapsible + Badge import fix), `tabs/CreditTab.jsx` (1 cartão collapsible), `tabs/DeadlinesTab.jsx` (Agenda evolution), `pages/ClientPortal.jsx` (Próximos Eventos).
- **Documentação** (1 ficheiro): `ARCHITECTURE.md`.
- **Validação**: `py_compile` ✓ (8 backend); `flake8 --select=E9,F63,F7,F82` → 0 erros; `bun build --no-bundle` ✓ (6 frontend, 0 erros).
- **Dependências**: Nenhuma nova — `Collapsible`, `Switch`, `Sheet`, `EmptyState`, `Badge`, `Bell`, `Eye`, `CalendarClock` já existem em Shadcn/lucide-react.

## [2026-07-25] — Pacote DG: RGPD PDF Multi-página + Clientes Sem Lifecycle

### Corrigido
- **RGPD PDF cortava texto e desformatava**: o endpoint `GET /api/rgpd/pdf/{process_id}` usava `reportlab Canvas` (baixo nível) que não paginava automaticamente e **ignorava o template dinâmico** (usava texto hardcoded). Novo builder `_build_prefilled_rgpd_pdf` em `services/rgpd_pdf.py` usa `reportlab.platypus` (`SimpleDocTemplate` + `Paragraph` + `Spacer` + `HRFlowable`) com **paginação automática** — o template de 11 secções ocupa agora 2+ páginas sem cortes. Fonte **DejaVuSans** (TTF) registada para suportar acentos portugueses e `☐` (Unicode).
- **"N/A" em campos nulos**: quando um dado do cliente falta (morada, NIF, etc.), o PDF imprime agora uma **linha em branco contínua** (`___________________`) para preenchimento à caneta, em vez de "N/A" ou string vazia. `get_tipo_documento_label` retorna `""` (em vez de "N/A") para campos vazios.
- **Data e Local pré-preenchidos**: `{{DATA_ASSINATURA}}` substituído por `___/___/______` e o local por `___________________` — o cliente preenche à caneta.
- **Checkboxes pré-picas**: os 4 pontos de consentimento (A/B/C/D) usam agora checkboxes **vazias** `☐` (U+2610) para o cliente picar fisicamente. Antes, o `consent_data` sintético (sem `consent_a/b/c/d`) fazia com que "Não Autorizo" ficasse picado em todas as opções.
- **Placeholders `{{MORADA_EMPRESA}}`/`{{CONTACTO_EMPRESA}}` não substituídos**: `_get_rendered_rgpd_text` agora substitui estes placeholders (antes só o fazia o renderer da Minuta). `{{NOME_EMPRESA}}` também substituído a partir de `system_config`.
- **Clientes eliminados apareciam na listagem**: 6 serviços de listagem/pesquisa não filtravam `is_deleted`. Adicionado `"is_deleted": {"$ne": True}` (defense-in-depth com `status: {"$ne": "eliminado"}`) em: `client_list_search.py` (search + list), `search_api_global.py`, `process_my_clients.py`, `process_kanban_enrichment.py`, `process_clients_nm.py`.

### Alterado
- **ClientsPage — sem tabs de Ativos/Concluídos**: removidos o Status Select (Todos/Ativos/Inativos/Eliminados) e o Phase Select (fases do workflow). Clientes não têm lifecycle — apenas Processos têm. O ecrã é agora uma **lista unificada de "Clientes Registados"**.
- **Coluna "Fase" removida**: a tabela deixou de mostrar `client.fase_principal.status_label` (que era uma fase de processo apresentada como atributo do cliente). Substituída por uma coluna **"Processos"** com `<Badge variant="secondary">{process_ids.length} Processos</Badge>`.
- **Badges "Inativo" removidos** (mobile + desktop) — o conceito não se aplica a clientes.
- **Stat card renomeado**: "Com Processos Activos" → "Total de Processos" (soma de `process_ids.length` de todos os clientes).
- **Sort option `fase_asc` removida**; `getSortValue` para `process_count` agora usa `process_ids.length` (total, não só ativos).
- `ClientsPage.js` reduzida de 997 → 855 linhas (remoção de dropdowns, estado, e helpers não usados).

### Documentação
- **`ARCHITECTURE.md`**: 2 novas secções: (1) "PDFs Gerados para Assinatura Manual" — template dinâmico + paginação automática (platypus), fallbacks de linhas em branco, checkboxes vazias `☐`, fonte DejaVuSans; (2) "Entidade Cliente — sem lifecycle" — tabela Cliente vs Processo (lifecycle), listagem unificada, soft-delete.

### Técnico
- **Backend modificado** (8 ficheiros): `services/rgpd_pdf.py` (novo builder platypus + helpers), `services/rgpd_service.py` (get_tipo_documento_label + placeholders empresa), `services/client_list_search.py` (is_deleted filter), `services/search_api_global.py`, `services/process_my_clients.py`, `services/process_kanban_enrichment.py`, `services/process_clients_nm.py`, `services/my_clients_api_list.py` (verificado).
- **Frontend modificado** (1 ficheiro): `pages/ClientsPage.js` (remoção tabs/fase + coluna Processos).
- **Documentação** (1 ficheiro): `ARCHITECTURE.md`.
- **Validação**: `py_compile` ✓ (8 backend); `flake8 --select=E9,F63,F7,F82` → 0 erros; `bun build --no-bundle` ✓ (1 frontend, 0 erros); smoke test do novo builder confirma **paginação em 2 páginas** com template longo.
- **Dependências**: Nenhuma nova — `reportlab.platypus` já faz parte de `reportlab==4.2.5`; DejaVuSans disponível na Docker image Playwright.
- **Backward compat**: o antigo `_build_rgpd_pdf` (Canvas) foi mantido intacto — continua a ser usado pelo fluxo de assinatura digital (`sign_rgpd`). O novo `_build_prefilled_rgpd_pdf` é usado apenas pelo endpoint de PDF pré-preenchido para assinatura manual.

## [2026-07-25] — Pacote DF: Área Pessoal — User Global vs Role/Perfil

### Corrigido
- **Perfis fantasma na Área Pessoal**: a `ProfilePage` renderiza agora tabs/secções de perfil **100% dinamicamente** a partir de `user.companies` (UCRs reais), sem qualquer hardcode de roles. Removida a função local `getRoleLabel` (substituída por `ROLE_LABELS` de `roleUtils.js`). Removidas comparações `effectiveRole === "suporte"` (role inexistente). Perfis que o utilizador não tem deixam de aparecer.
- **"Conta principal" fantasma**: removido o fallback sintético `company_id === "default"` que criava uma "conta principal" inexistente. O `AuthContext` agora usa `null` em vez de `"default"` quando não há UCRs. O `ContextSwitcher` mostra "Padrão" apenas quando `is_default: true` (não "Principal").

### Alterado
- **Reestruturação da Área Pessoal com Shadcn Tabs**: a `ProfilePage` (antes uma pilha plana de 5 Cards) passou a usar `<Tabs>` do Shadcn com:
  - **Aba "Conta Global"** (sempre presente): contém APENAS cartões transversais à pessoa — Informação de Login (email, password, role badge, "Membro desde") + Sessões Ativas.
  - **Uma aba por UCR real** (gerada dinamicamente de `user.companies`): cada aba contém os cartões de perfil — Dados Profissionais + Assinatura de Email + Configuração de Webmail. O label de cada aba é `{ROLE_LABELS[role]} @ {company_name}` com o ícone da role.
- **Novo componente `ProfileRoleTab.jsx`**: encapsula os 3 cartões de perfil (Dados Profissionais, Assinatura, Webmail) e faz scoping via header `X-Company-Id` override por request (`api.put(url, data, { headers: { "X-Company-Id": companyId } })`). Cada aba carrega e guarda os seus dados de forma isolada — sem misturar contextos entre perfis.
- **`ProfilePage.js` reduzida de 1081 → 658 linhas** (lógica de per-UCR movida para `ProfileRoleTab.jsx`).

### Adicionado
- **Preferências de notificação per-UCR**: o campo `notification_preferences` (14 bools) foi adicionado ao modelo `UserCompanyRole` (`models/user_company_role.py`). `PUT /auth/preferences` e `GET /auth/preferences` agora usam `X-Company-Id` para scope ao UCR ativo, com dual-write no global para backward compat. Os consumers (`notification_service.py`, `email_v2.py`) aceitam `company_id=None` opcional: quando fornecido, procuram o UCR primeiro com fallback ao store global. Endpoints admin (`/admin/notification-preferences/{user_id}`) aceitam `?company_id=` query param.
- **`display_name` no modelo UCR**: adicionado aos pydantic `UserCompanyRoleCreate/Update/Response` (era escrito via dict mas não estava no modelo).

### Documentação
- **`ARCHITECTURE.md`**: nova secção "Separação Estrita: User (Global) vs Role/Perfil (Local)" com diagrama Mermaid, tabela de campos por coleção, mecanismo `X-Company-Id`, e notas sobre preferências de notificação per-UCR com fallback.
- **`FRONTEND_GUIDELINES.md`**: nova secção 10 "Área Pessoal — separação User (Global) vs Role/Perfil" com regras: renderização 100% dinâmica de `user.companies`; estrutura "Conta Global" + uma aba por UCR; sem "conta principal"; settings sempre pré-preenchidas do backend com scoping por `X-Company-Id`.

### Técnico
- **Backend modificado** (7 ficheiros): `models/user_company_role.py` (notification_preferences + display_name), `services/auth_profile_handlers.py` (preferences per-UCR), `services/notification_service.py` (company_id kwarg), `services/email_v2.py` (company_id kwarg), `services/admin_users.py` (admin preferences per-UCR), `routes/auth.py` (request param), `routes/admin.py` (company_id query param).
- **Frontend modificado** (4 ficheiros): `pages/ProfilePage.js` (reestruturação Tabs), `components/ProfileRoleTab.jsx` (NOVO), `contexts/AuthContext.js` (null fallback), `components/layout/ContextSwitcher.jsx` ("Padrão" label).
- **Documentação** (2 ficheiros): `ARCHITECTURE.md`, `FRONTEND_GUIDELINES.md`.
- **Validação**: `py_compile` ✓ (7 backend); `flake8 --select=E9,F63,F7,F82` → 0 erros; `bun build --no-bundle` ✓ (4 frontend, 0 erros).
- **Dependências**: Nenhuma nova — `Tabs`, `ROLE_LABELS`, `ROLE_ICONS` já existem em Shadcn/roleUtils.
- **Tech debt (defer)**: OneDrive permanece system-level (env var) — fazer per-UCR seria um novo feature. `realtime_notifications.py:_get_user_prefs` não foi modificado (in-app WebSocket prefs continuam globais — follow-up opcional).

## [2026-07-25] — Pacote DE: Download RGPD PDF + Upload Múltiplo Portal

### Adicionado
- **Download do RGPD em PDF pré-preenchido**: novo endpoint `GET /api/rgpd/pdf/{process_id}` que gera um PDF do RGPD com o template ativo, substituindo placeholders (`{{NOME}}`, `{{CONTRIBUINTE}}`, `{{MORADA}}`, etc.) pelos dados reais desencriptados do cliente. Reutiliza `_get_rendered_rgpd_text` + `_generate_rgpd_pdf_bytes` (reportlab) de `services/rgpd_service.py`. Novo serviço `services/rgpd_pdf.py` (`run_generate_prefilled_rgpd_pdf`). Response: `StreamingResponse` (`application/pdf`, `Content-Disposition: attachment`). Audit: regista atividade "RGPD pré-preenchido descarregado".
- **Upload Múltiplo Global no Portal do Cliente**: o cliente pode carregar múltiplos ficheiros para qualquer categoria, de forma faseada (1 hoje, 2 amanhã), sem perder os anteriores.

### Corrigido
- **Bug REPLACE em uploads do Portal**: `run_confirm_portal_upload` (`portal_upload_ops.py`) fazia `$set` que sobrescrevia os metadados do ficheiro anterior quando o cliente carregava um 2º ficheiro para a mesma categoria — o 1º ficheiro ficava órfão no S3. Agora faz `$set` (status → RECEIVED + campos top-level para backward compat) + `$push` (novo `file_entry` para array `attached_files`). Mesma correção em `fulfill_portal_requests_on_staff_upload` (`document_portal_fulfill.py`).

### Alterado
- **Botão RGPD → DropdownMenu**: o botão de RGPD no `PageHeader` do `ProcessDetails` passou a um `DropdownMenu` com 2 opções: "Solicitar Consentimento" (envia email — comportamento anterior) e "Descarregar PDF (Assinatura Manual)" (download do PDF pré-preenchido). Padrão blob (`responseType: "blob"` + `createObjectURL` + `link.click()`).
- **UI de upload do Portal**: o input de ficheiro (`multiple={true}`) está **sempre visível** (não se esconde após o primeiro upload — o label muda para "➕ Adicionar ficheiros"). Adicionada `ScrollArea` com `Badge`s mostrando a lista de ficheiros anexados por categoria (filename + tamanho + botão de download por ficheiro). O badge de contagem lê `doc.attached_files.length` do backend (persistente após refetch).
- **Serializers**: `run_get_portal_status` (`portal_status.py`) e `serialize_portal_document` (`document_portal_request.py`) agora incluem `attached_files` no payload — o frontend e o CRM podem listar todos os ficheiros por categoria.

### Documentação
- **`FRONTEND_GUIDELINES.md`**: nova secção 9 "Portal do Cliente e Documentos Legais (Pacote DE)" — regras: Portal usa sempre lógica de append em arrays de documentos (múltiplos uploads por categoria); documentos legais gerados vêm sempre pré-preenchidos do backend; presigned URLs (não List[UploadFile]).
- **`ARCHITECTURE.md`**: novas secções "Portal do Cliente — Upload Múltiplo com Append (Pacote DE)" (diagrama do fluxo presigned URL + lógica `$push attached_files`) e "Documentos Legais Gerados — RGPD PDF Pré-preenchido (Pacote DE)" (diagrama do endpoint + reutilização da pipeline de PDF).

### Técnico
- **Backend modificado** (6 ficheiros): `services/rgpd_pdf.py` (novo), `routes/rgpd.py` (novo endpoint), `services/portal_upload_ops.py` (APPEND), `services/document_portal_fulfill.py` (APPEND), `services/portal_status.py` (attached_files no payload), `services/document_portal_request.py` (attached_files no serializer).
- **Frontend modificado** (3 ficheiros): `services/api.js` (helper `downloadRGPDF`), `pages/ProcessDetails.js` (DropdownMenu RGPD + handler download), `pages/ClientPortal.jsx` (botão sempre visível + ScrollArea de ficheiros anexados).
- **Documentação** (2 ficheiros): `FRONTEND_GUIDELINES.md`, `ARCHITECTURE.md`.
- **Validação**: `py_compile` ✓ (6 backend); `flake8 --select=E9,F63,F7,F82` → 0 erros; `bun build --no-bundle` ✓ (3 frontend, 0 erros).
- **Dependências**: Nenhuma nova — `reportlab` já estava instalado; `ScrollArea`, `Badge`, `FileDown`, `Download`, `FileText` já existem em Shadcn/lucide-react.

## [2026-07-25] — Pacote DD: Limpeza de UI, Desencriptação de Dados e Preparação de IA

### Corrigido
- **Dados encriptados vazavam para o frontend** em 4 endpoints que não chamavam `decrypt_*` antes de devolver clientes/processos: pesquisa global (`search_api_global.py`), clientes do processo (`process_clients_nm.py`), processos do cliente (`client_process_ops.py`) e restauro de processo (`restore_api_process.py`). Agora todos aplicam `decrypt_client_data` / `decrypt_sensitive_data`.
- **Security gap**: `run_apply_ai_suggestions` guardava NIF/CC extraídos pela IA em plain text (sem encriptar). Adicionado `_encrypt_mongo_update_paths()` que encripta dot-paths Mongo sensíveis antes de `$set`.
- **IBAN não estava encriptado em repouso**: adicionado `iban` e `conta_bancaria` a `financial_data` em `encrypt_sensitive_data`/`decrypt_sensitive_data` (`process_service.py`) e `SENSITIVE_FIELDS` (`encryption.py`).
- **Pipeline de IA não alimentava o dashboard de documentos a expirar para CCs por OCR**: `build_auto_cat_metadata` agora faz fallback de `expiry_date` a partir de `cc_validity`/`validade`/`data_validade` extraídos pelo OCR (via helper `_extract_validade_from_ocr`).

### Alterado
- **Calculadoras movidas para Sheet global**: removida a rota `/calculadoras` e o link na sidebar. Adicionado ícone de `Calculator` no `TopNav` do `DashboardLayout` que abre um `Sheet` (lado direito) com o `MortgageSimulator`. Acessível a partir de qualquer ecrã.
- **Scroll nas Tarefas**: `TasksPanel` envolvido em `ScrollArea` com `h-fit max-h-[400px]` para criar scroll interno e impedir que a página estique.
- **"N/A" oculto no PageHeader**: `AutoDSTIBadge` em modo `compact` retorna `null` quando o DSTI não é calculável (em vez de mostrar "N/A" entre os botões de ação).
- **Etiquetas movidas para o PageHeader**: removido o cartão gigante de Etiquetas do separador Resumo. As etiquetas são agora `<Badge variant="secondary">` compactos na `description` do `PageHeader`, a seguir ao tipo de processo / número.
- **Cartões de 2º Titular consolidados**: eliminada a duplicação entre `SecondTitularCard` (gere `titular2_data`) e o cartão "2º Titular / Fiador" (mostrava `co_buyers`/`co_applicants`). A secção `CoBuyersSection` foi movida para dentro do `SecondTitularCard`, preservando a lógica de gravação.
- **Toasts de background com closeButton**: adicionado `closeButton: true` aos 3 toasts sticky do `TasksContext` (`loading`, `success`, `error`).

### Documentação
- **`FRONTEND_GUIDELINES.md`**: nova secção 8 "Padrões consolidados (Pacote DD)" com regras: calculadoras em Sheets globais; listas com `max-height` + `ScrollArea`; metadados curtos no header sem fallbacks "N/A"; sem cartões de UI duplicados; toasts de background com `closeButton`.
- **`ARCHITECTURE.md`**: nova secção "Pipeline de IA — Extração de Dados e Validade de Documentos (Pacote DD)" com diagrama do fluxo de categorização + OCR, explicação do fallback de `expiry_date`, persistência/encriptação de dados IA, e campos encriptados atualizados (IBAN).

### Técnico
- **Backend modificado** (8 ficheiros): `services/search_api_global.py`, `services/process_clients_nm.py`, `services/client_process_ops.py`, `services/restore_api_process.py`, `services/document_ai_analyze.py`, `services/process_service.py`, `services/encryption.py`, `services/document_auto_categorize.py`.
- **Frontend modificado** (7 ficheiros): `App.js`, `layouts/DashboardLayout.js`, `pages/ProcessDetails.js`, `components/AutoDSTIBadge.js`, `components/processDetails/tabs/PersonalInfoTab.jsx`, `components/SecondTitularCard.jsx`, `contexts/TasksContext.js`.
- **Documentação** (2 ficheiros): `FRONTEND_GUIDELINES.md`, `ARCHITECTURE.md`.
- **Validação**: `py_compile` ✓ (8 backend); `flake8 --select=E9,F63,F7,F82` → 0 erros; `bun build --no-bundle` ✓ (7 frontend, 0 erros).
- **Dependências**: Nenhuma nova — `Sheet`, `ScrollArea`, `Badge`, `Calculator` já existem em Shadcn/lucide-react.

## [2026-07-25] — Auditoria UX/UI (Fases 1–6), redesign ProcessDetails/ConsultorDashboard, Calculadora de Prestações

### Adicionado
- **ESLint safety net contra cores Tailwind cruas (Fase 6, #596)**: nova regra `no-restricted-syntax` (nível `warn`, gate do CI apenas em `error`) em `frontend/eslint.config.js` que deteta utilities de cor crua do Tailwind (`bg-gray-*`, `text-blue-*`, `bg-red-*`, etc.) em `className`/`class` e em `cn()`/`clsx()`/`classnames()`/`cva()`, forçando o uso de tokens semânticos do Shadcn (`bg-primary`, `text-muted-foreground`, `bg-destructive`, …) que respeitam o Dark Mode. Código legado não foi alterado (~2700 avisos intencionais).
- **`FRONTEND_GUIDELINES.md`**: novo documento que consolida as normas de UX/UI do frontend — Progressive Disclosure, layout 2/3+1/3, eliminação de cartões redundantes para metadados simples, formulários secundários em `Dialog`/`Sheet`, `EmptyState`/`PageHeader` canónicos, regra ESLint de cores, e utilitários centralizados (`formatCurrency`, `validateNIF`, `mortgageCalculations`).
- **Calculadora de Prestações no CRM (`/calculadoras`, #601)**: nova secção `CalculatorsPage.js` com `components/calculators/MortgageSimulator.jsx` — simula a prestação mensal (sistema francês de amortização) a partir de Capital, Prazo e Taxa de Juro/Spread, com toggle `Switch` "Incluir Seguros" que revela progressivamente Seguro de Vida e Multirriscos. Motor de cálculo extraído para `utils/mortgageCalculations.js` (`calcularPrestacaoMensal`, `calcularTAEG`, `simularCreditoHabitacao`) a partir do simulador do Portal do Cliente (`components/portal/SimulatorCH.jsx`), reutilizável fora do Portal. Inclui acesso rápido a DSTI e Risco de Crédito (dialogs já existentes).
- **Componentes partilhados canónicos (Fases 4–5, #594)**: `StatCard`, `StatusBadge`, `Spinner`, `EmptyState`, `PageHeader` promovidos para `components/shared/`; migração de Dashboards/RGPD/Finance para os usar; `PageHeader` estendido com slot opcional `titleBadge`.

### Alterado
- **Redesign `ProcessDetails` com Progressive Disclosure (#597, #599)**: título manual substituído pelo `PageHeader` partilhado (com `StatusBadge` junto ao título); conteúdo reestruturado num grid `grid-cols-1 lg:grid-cols-3` — 2/3 esquerda: Tabs "Resumo"/"Documentos"/"Histórico"; 1/3 direita: novos `ClientContextCard` (titular/NIF/contactos) e `AssignmentContextCard` (consultor/mediador + prazos críticos + botão "Gerir"), seguidos de Tarefas e Imóveis Compatíveis. `ProcessStickyHeader` removido (substituído pelo cabeçalho + cartões de contexto).
- **Separador Histórico consolidado**: formulário "Registar Atividade" movido para dentro de um `Dialog` (antes inline); timeline de atividades compactada num `ScrollArea` de altura fixa (`h-[500px]`); "Filme da Lead" mantido no mesmo separador.
- **Cartão "Prioridade" eliminado do Resumo**: deixou de ocupar um `Card` isolado; passou a `DropdownMenu` + `Badge` compacto dentro do `AssignmentContextCard` (coluna direita).
- **Redesign `ConsultorDashboard` (#594)**: 3 zonas (foco, funil, tabs), progressive disclosure; remove double padding herdado do layout antigo.

### Corrigido
- Race condition em `handleSaveOrganization` (`ProcessDetails`): aceitar overrides explícitos evita enviar valores antigos de prioridade/etiquetas ao backend quando o save é disparado no mesmo handler que o `setState`.

### Técnico
- Documentação sincronizada: `AGENTS.md` (bullets de gotchas + tabela "Frontend UX Audit + Calculadoras"), `README.md`, `FRONTEND_GUIDELINES.md` (novo), `CHANGELOG.md`.
- PRs: #590 (Fase 0/auditoria), #592 (Fases 1–3), #594 (Fases 4–5 + ConsultorDashboard), #596 (Fase 6 ESLint), #597/#598 (ProcessDetails redesign), #599/#600 (Activity Dialog), #601/#602 (Prioridade + Calculadora + docs).

---

## [2026-07-22] — ProcessDetails mutations, portal fulfill, toasts sticky, titular IA

### Adicionado
- **`useProcessMutations` ligado ao ProcessDetails**: update processo/cliente, assign multi-assignee, atividades e prazos via TanStack Query (em vez de `api.put` soltos).
- **`sanitizeProcessUpdatePayload` / `sanitizeClientUpdatePayload`**: bloqueiam `documents`, `onedrive_links` e arrays vazios que esmagariam dados no Mongo; `labels:[]` só no save de organização.
- **`document_portal_fulfill`**: upload da equipa no CRM marca pedidos portal REQUESTED→RECEIVED (além do upload do cliente).
- **Dialog titular 1/2** quando a IA devolve `needs_titular_choice`; apply com `target_titular`.
- **`ProcessAssignDialog`**: UI de atribuições extraída do monolito ProcessDetails.

### Alterado
- **Toasts de background**: sticky (`duration: Infinity`); **não** auto-dismiss ao mudar de página / ao sair de `/tasks/active`.
- **Onboarding público**: registo cria cliente + checklist SystemConfig; processo só após documentação obrigatória; dual-assign pós-criação.
- **Analisar/Renomear IA**: RBAC gestão; badge `ai_analyzed`; skip re-análise.
- Documentação: `AGENTS.md`, `README.md`, `ARCHITECTURE.md` alinhados com estes fluxos.

### Corrigido
- Args invertidos em várias rotas admin thinned (stale-processes, team-performance, logs) que causavam 500.

---

## [2026-07-16] — Pacote DC: Fix Portal Access Email Template and Expose Code in CRM UI

### Corrigido
- **Template de email de acesso ao Portal** enviava apenas o Magic Link sem destacar o Código de Acesso explícito, gerando confusão nos clientes. Além disso, os operadores do CRM não conseguiam ver qual era o código do cliente pela interface.

### 1. Correção do Template de Email (Backend)
- Adicionado bloco "Código de Acesso" **explícito e incondicional** abaixo do botão "Aceder ao meu Portal" em **todos** os emails de acesso ao Portal:
  > Se o link não funcionar, aceda a **www.powercell.pt/portal** e insira o seguinte Código de Acesso:
  > **[CÓDIGO]**
- O `portal_access_code` (formato XXX-XXX, stored no cliente) é injetado corretamente no HTML com styling teal destacado (Courier New, 22px, letter-spacing 3px).
- **`backend/routes/public.py`** (formulário público): buscado `portal_access_code` do cliente (gerado na criação) e adicionado o bloco ao template HTML + text body.
- **`backend/routes/processes.py`** (`send_magic_link_email`): bloco `portal_credentials_html` tornado **incondicional** (antes era opcional via `if portal_access_code`). Novo formato com a referência a www.powercell.pt/portal. `portal_access_code` adicionado ao retorno da função.
- **Compatibilidade**: o bloco só é omitido se `portal_access_code` for genuinamente `None` (mostra "—" como fallback).

### 2. Expor o Código no Perfil do Cliente (Frontend + Backend)

#### 2a. Backend — devolver token ativo
- **`GET /clients/{id}`** (`clients.py`): adicionado bloco `portal_access` com lookup em `portal_tokens` (por `process_id`) para devolver `{portal_access_code, short_id, magic_link, has_active_token}`. O `portal_access_code` vem do próprio cliente; o `short_id`/`magic_link` vêm do token ativo mais recente.
- **`GET /processes/{id}`** (`processes.py`): adicionado o mesmo bloco `portal_access` — busca `portal_access_code` do cliente via `client_id` + lookup em `portal_tokens` por `process_id`.

#### 2b. Backend — endpoint de reenvio
- **Novo endpoint `POST /clients/{client_id}/resend-portal-access`** (`clients.py`): resolve o `process_id` ativo do cliente (primeiro não eliminado) e delega para `send_magic_link_email` (`processes.py`) — reutiliza toda a lógica de geração de `short_id` + JWT + envio de email. Devolve `{success, process_id, portal_access_code, magic_link, short_id, message}`. Validações: cliente existe (404), tem email (400), tem processo (400), tem processo ativo (404).

#### 2c. Frontend — secção "Acesso ao Portal do Cliente"
- **`ClientDetailsModal.jsx`**: nova secção visual (cartão teal com `KeyRound`) mostrando **Código de Acesso** (font-mono bold) + **Link ativo** (clicável). Botão **"Reenviar Acesso ao Portal"** que chama `resendPortalAccess(clientId)` → atualiza `portal_access` localmente com os novos dados. Estado `resendingPortal` com spinner. Imports: `KeyRound`, `toast`, `resendPortalAccess`.
- **`ProcessDetailsModal.jsx`**: mesma secção entre o `</Tabs>` e o footer. Botão "Reenviar" chama `sendMagicLinkEmail(process.id)` (API helper existente) → atualiza via `onProcessUpdate`. Imports: `KeyRound`, `Send`, `sendMagicLinkEmail`. Estado `resendingPortal`.
- **`api.js`**: adicionado helper `resendPortalAccess(clientId)` → `POST /clients/{clientId}/resend-portal-access`.

### Técnico
- **Backend modificado** (3 ficheiros): `routes/public.py` (template + portal_access_code lookup), `routes/processes.py` (template incondicional + portal_access no GET /{id} + portal_access_code no retorno), `routes/clients.py` (import os + portal_access no GET /{id} + novo endpoint resend-portal-access).
- **Frontend modificado** (3 ficheiros): `services/api.js` (helper resendPortalAccess), `components/ClientDetailsModal.jsx` (secção + botão + estado), `components/kanban/ProcessDetailsModal.jsx` (secção + botão + estado + imports).
- **Novo endpoint**: `POST /api/clients/{client_id}/resend-portal-access`.
- **Novo campo de resposta**: `portal_access` em `GET /clients/{id}` e `GET /processes/{id}`.
- **Validação**: `py_compile` ✓; `flake8 --select=E9,F63,F7,F82` → 0 erros; `bun build --no-bundle` ✓ (0 erros).
- **Dependências**: Nenhuma nova — `KeyRound`, `Send`, `Mail`, `Loader2` já existem em `lucide-react`; `toast` em `sonner`.

## [2026-07-16] — Pacote DB: UAT Refinements (Leads Flow, Kanban Reactivity, UI Cleanup)

### Alterado
- **Refinamentos cirúrgicos da sessão de UAT** — 5 alterações de lógica e usabilidade no fluxo de Leads, reatividade do Kanban e limpeza de UI.

### 1. Novo Fluxo de Leads e Menu (Visão Global)
- **Menu**: A página "Registos de Clientes" foi movida do grupo "O Meu Negócio" para o grupo **"Visão Global"** na barra lateral (`DashboardLayout.js`). Atualizadas as rotas de expansão automática de secções (`meuNegocioRoutes` / `visaoGlobalRoutes`). A restrição do perfil **Indexação** (não vê Registos de Clientes) foi mantida via filtragem do `visaoGlobalGroup`.
- **Criação**: Novos registos do formulário público entram agora com `status = None` e `workflow_step = None` (Lead) — **não entram no Kanban ativo**. Anteriormente entravam em `"pre_registo"`.
  - `backend/routes/public.py`: `process_doc.status` passa a `None`.
  - `backend/services/onboarding_service.py`: `new_process.status` passa a `None`.
- **Gatilho de Transição**: Quando o sistema deteta que o cliente submeteu os **Documentos Obrigatórios** via Portal, o processo transita automaticamente para a **1ª fase real do Kanban** (1º status do `workflow_statuses` que não seja `pre_registo`, `fila_espera` nem terminal).
  - `backend/routes/portal.py` `_check_and_advance_existing_pre_registo`: query passa a procurar `{"status": {"$in": ["pre_registo", None]}}` (cobre legacy + novos).
  - `backend/routes/portal.py` `_auto_advance_from_pre_registo`: aceita `pre_registo` OU `None`; calcula a 1ª fase REAL do Kanban (em vez do "próximo estado" da pipeline); define também `workflow_step`; invoca `assign_to_indexer(update_status=False)`.
- **Consistência em todo o backend**: queries de exclusão de leads atualizadas de `{"$ne": "pre_registo"}` para `{"$nin": ["pre_registo", None]}` (via constante `LEAD_STATUS_VALUES`):
  - `backend/routes/processes.py` (4 queries: GET /processes, GET /paginated, Kanban, my-clients paginated) + `update_process` (`is_pre_registo_transition` aceita `None`).
  - `backend/routes/my_clients.py` (1 query).
  - `backend/routes/clients.py` (triagem: query `$or` inclui `None`; `triage_status = "pre_registo"` retornado para ambos os casos; regra de exclusão de Registos inclui `None`).
  - `backend/routes/portal.py` (2 queries de lock de perfil: `$nin` inclui `None`).

### 2. Eliminar Criação de Fases Fantasma
- Ao criar um processo manualmente via CRM (`POST /processes/create-client` e `POST /processes`), o sistema **não força mais fases hardcoded** (`fila_espera` / `fase_documental` / `clientes_espera`).
  - `backend/services/process_assignment.py` `assign_to_indexer`: novo parâmetro `update_status: bool = True`. Quando `False`, **não altera o status em nenhum cenário** (sem indexadores / todos no limite / indexador disponível) — apenas atribui o indexador se disponível.
  - `backend/routes/processes.py` `create-client`: chama `assign_to_indexer(process_id, update_status=False)`. O processo mantém o `initial_status` = 1ª fase real do `workflow_statuses`.
  - Fallback quando `workflow_statuses` está vazio: `initial_status = None` (antes: `"clientes_espera"`). **Não se inventam nomes de fases no código.**

### 3. Reatividade Imediata do Kanban
- O drag-and-drop passou a atualizar **instantaneamente** via duas camadas de optimistic update:
  - **Hook** (`frontend/src/hooks/mutations/useProcessMutations.js` `useMoveProcessMutation`): `onMutate` reescrito — `setQueryData` executa **síncrono e primeiro** (antes do `cancelQueries` com `await`, que passou a fire-and-forget). Adicionado suporte para callback `onSettled` nas options.
  - **Componente** (`frontend/src/components/KanbanBoard.js`): nova camada de estado local `localMoves` (mapa `processId → newStatus`) aplicada sobre `columns` via `optimisticColumns` (`useMemo`). No `handleDrop`, `setLocalMoves` é despachado **imediatamente** antes de `mutate`. Limpo no `onSettled` do mutation. O `filteredColumns` passa a derivar de `optimisticColumns`.

### 4. Limpeza de UI (Documentos)
- Botões de IA temporariamente ocultos (via `style={{ display: 'none' }}` — código mantido para reativação futura):
  - **"Analisar IA"**, **"Renomear IA"** e **"Organizar"** no `frontend/src/components/S3FileManager.js` (barra de ações).
  - **Card "Resumo Executivo IA"** no `frontend/src/pages/ProcessDetails.js` (condição `&& false` + `display: none`).
- Separador **"Links"** temporariamente oculto no `frontend/src/components/UnifiedDocumentsPanel.js` (`TabsList` e `TabsContent` com `display: none`). O `DriveLinks` continua importado para reativação futura.

### 5. Botão de Expansão na Modal
- **`ProcessDetailsModal.jsx`**: o botão "Página Completa" foi renomeado para **"Abrir Processo Completo"** e tornado mais visível (variante `secondary` + cor azul `bg-blue-600`, no header). Mantém a navegação para `/process/${process.id}`.
- **`ClientDetailsModal.jsx`**: o botão "Ver Processo" foi renomeado para **"Abrir Processo Completo"**, com ícone `ExternalLink` e cor azul destacada (`bg-blue-600`) no rodapé. Import `ExternalLink` adicionado.

### Técnico
- **Backend modificado** (7 ficheiros): `routes/public.py`, `services/onboarding_service.py`, `routes/portal.py`, `services/process_assignment.py`, `routes/processes.py`, `routes/clients.py`, `routes/my_clients.py`.
- **Frontend modificado** (8 ficheiros): `layouts/DashboardLayout.js`, `hooks/mutations/useProcessMutations.js`, `components/KanbanBoard.js`, `components/UnifiedDocumentsPanel.js`, `components/S3FileManager.js`, `pages/ProcessDetails.js`, `components/kanban/ProcessDetailsModal.jsx`, `components/ClientDetailsModal.jsx`. (Comentários atualizados em `components/CreateProcessModal.jsx` e `pages/StaffDashboard.js`.)
- **Constantes novas**: `LEAD_STATUS_VALUES = ["pre_registo", None]` em `routes/processes.py` e `routes/my_clients.py`.
- **Parâmetro novo**: `update_status: bool = True` em `services/process_assignment.py::assign_to_indexer`.
- **Validação**: `py_compile` ✓; `flake8 --select=E9,F63,F7,F82` → 0 erros; `bun build --no-bundle` ✓ (0 erros de sintaxe em todos os ficheiros frontend).
- **Dependências**: Nenhuma nova — `ExternalLink` já existia em `lucide-react`.

## [2026-07-16] — Pacote DA: Always Show Notes Section & Aggregate Sources

### Corrigido
- **Secção de Observações só aparecia para alguns clientes/processos** — agora é **sempre visível** e **agrega todas as fontes de notas** disponíveis (IA + manuais + atividade recente).

### 1. Visibilidade Incondicional (Frontend)
- **`ProcessDetailsModal.jsx`**: A tab "Obs. e IA" (4ª tab, adicionada no Pacote CZ) agora usa uma IIFE que renderiza **sempre**. Se houver conteúdo, mostra os blocos relevantes; se TODOS os campos estiverem vazios, mostra um fallback em itálico cinza: *"Nenhuma observação, nota da IA ou atividade recente registada."*
- **`ClientDetailsModal.jsx`**: Mesma lógica — a secção renderiza incondicionalmente com o mesmo fallback all-empty.

### 2. Agregação de Fontes (3 blocos)
Dentro da secção, cada bloco só aparece se tiver conteúdo (não mostra blocos vazios com "Sem ..."):
1. **Notas da IA** (`ai_extracted_notes`) — roxo + `Sparkles` + badge "Automático"
2. **Observações manuais** (`notas` / `notes`) — âmbar + `StickyNote` (editável no ProcessDetailsModal)
3. **Atividade Recente** (`latest_activity`) — azul + `MessageSquare` + autor + data (NOVO)

**CRÍTICO**: Se TODOS os 3 campos estiverem vazios/null → fallback itálico cinza: *"Nenhuma observação, nota da IA ou atividade recente registada."*

### 3. Agregação no Backend (Garantia de Dados)
- **`GET /processes/{id}`** (`processes.py`): Adicionado `db.activities.find_one({"process_id": process_id}, sort=[("created_at", -1)])` → popula `process.latest_activity` com `{comment, user_name, user_role, created_at}`.
- **`GET /clients/{id}`** (`clients.py`): Adicionado `db.activities.find_one({"process_id": {"$in": all_process_ids}}, sort=[("created_at", -1)])` → popula `client.latest_activity` com a atividade mais recente de qualquer processo do cliente.
- **`GET /processes/kanban`** (`processes.py`): Adicionado batch aggregation PACOTE DA (mesmo pattern do PACOTE BT/CZ) → popula `latest_activity` em todos os processos do kanban. **CRÍTICO**: O `ProcessDetailsModal` recebe `process` do KanbanBoard (que chama `/kanban`), não de `/processes/{id}` — sem este enrichment, a atividade não apareceria no modal.

### Técnico
- **Backend modificado**: `backend/routes/processes.py` (latest_activity no GET /{id} + batch enrichment no /kanban), `backend/routes/clients.py` (latest_activity no GET /{id}).
- **Frontend modificado**: `frontend/src/components/kanban/ProcessDetailsModal.jsx` (IIFE agregada + 3º bloco Atividade Recente + fallback all-empty + import `MessageSquare`), `frontend/src/components/ClientDetailsModal.jsx` (IIFE agregada + 3º bloco + fallback all-empty + import `MessageSquare` + `formatDateTime`).
- **FilteredProcessList.js**: Verificado — a coluna de Notas já tem fallback "Sem notas recentes" (do Pacote CZ). Sem alterações necessárias.
- **Validação**: `py_compile` ✓; `flake8 --select=E9,F63,F7,F82` → 0 erros; `esbuild --packages=external` ✓ nos 2 ficheiros frontend.
- **Dependências**: Nenhuma nova — `MessageSquare` já existe em `lucide-react`.

## [2026-07-16] — Pacote CZ: Fix Notes Data Source in Table & Force Observations in Modal

### Corrigido
- **Desfasamento entre notas da tabela e notas reais dos consultores** + **secção de Observações que não aparecia na Modal**. Ambos os bugs resolvidos.

### Bug 1 — Origem das Notas na Tabela de Processos
- **Causa raiz**: As tabelas liam `process.notes` (campo estático) PRIMEIRO, com fallback para `latest_activity_note`/`latest_note`. Como `process.notes` quase sempre tinha valor (mesmo desatualizado), a atividade mais recente nunca aparecia. Além disso, o PACOTE CJ (backend) que deveria sobrescrever `p["notes"]` era **dead code** — filtrava por `action` field que não existe na coleção `activities`.
- **Backend**:
  - **`GET /processes`**: Removido dead code PACOTE CJ. Adicionado `latest_activity_preview` (alias explícito de `latest_note` do batch aggregation PACOTE BT) a cada processo.
  - **`GET /processes/paginated`**: Adicionado batch aggregation PACOTE CZ (mesmo pattern do PACOTE BT) — antes não tinha enrichação de notas nenhuma. Adicionado `latest_note` + `latest_activity_preview`.
  - **`GET /my-clients`** (`my_clients.py`): Removido dead code PACOTE CJ. Adicionado `latest_activity_preview` (alias de `latest_activity_note` do PACOTE CG).
- **Frontend** (fallback chain invertida — atividade mais recente PRIMEIRO):
  - **`FilteredProcessList.js`**: `process.latest_activity_preview || process.latest_activity_note || process.latest_note` (antes era `process.notes || ...`).
  - **`MyClientsPage.js`**: `client.latest_activity_preview || client.latest_activity_note || client.latest_note` (antes era `client.notes || ...`).
  - **`ProcessesPage.js`**: Chain reescrita — agora prioriza `latest_activity_preview` → `latest_note` → `latest_activity_note` → `last_activity.content` → `activities[]` (antes nem tinha `latest_activity_note`/`latest_note`).

### Bug 2 — Secção de Observações não renderizava na Modal
- **Causa raiz (ProcessDetailsModal)**: A secção "Notas da IA" estava: (1) dentro da tab "process" (NÃO era a default — a default era "client"), (2) condicionada a `safeString(process.ai_extracted_notes) && !isEditing` — escondida quando vazia OU em modo de edição.
- **Causa raiz (ClientDetailsModal)**: Ambas as secções ("Observações" e "Notas da IA") eram condicionadas a `client.notas &&` e `client.ai_extracted_notes &&` — completamente escondidas quando os campos estavam vazios.
- **Correção (ProcessDetailsModal)**:
  - Nova **4ª tab "Obs. e IA"** (grid-cols-4), sempre visível.
  - TabsContent incondicional com:
    1. **Notas da IA** (roxo + `Sparkles` + badge "Automático") — sempre renderiza; fallback "Sem notas extraídas pela IA..." se vazio.
    2. **Observações do Consultor** (âmbar + `StickyNote`) — sempre renderiza; editável em modo de edição; fallback "Sem observações manuais..." se vazio.
  - Import `StickyNote` adicionado aos ícones lucide.
- **Correção (ClientDetailsModal)**:
  - Removida a renderização condicional `{client.notas && ...}` e `{client.ai_extracted_notes && ...}`.
  - Ambas as secções agora renderizam **sempre** (wrapper div incondicional), com fallback "Sem observações manuais registadas." / "Sem notas extraídas pela IA..." dentro do `<p>`.
  - Badge "Automático" adicionado ao header das Notas da IA.

### Técnico
- **Backend modificado**: `backend/routes/processes.py` (latest_activity_preview no GET /processes + batch aggregation no GET /paginated + remoção dead code), `backend/routes/my_clients.py` (latest_activity_preview + remoção dead code).
- **Frontend modificado**: `frontend/src/pages/ProcessesPage.js` (notes chain), `frontend/src/pages/FilteredProcessList.js` (notes chain), `frontend/src/pages/MyClientsPage.js` (notes chain), `frontend/src/components/kanban/ProcessDetailsModal.jsx` (4ª tab + import StickyNote), `frontend/src/components/ClientDetailsModal.jsx` (secções incondicionais).
- **Validação**: `py_compile` ✓; `flake8 --select=E9,F63,F7,F82` → 0 erros; `esbuild --packages=external` ✓ nos 5 ficheiros frontend.
- **Dependências**: Nenhuma nova — `StickyNote` já existe em `lucide-react`.

## [2026-07-16] — Pacote CY: Fix Client Onboarding, Timeline & Config Bugs

### Corrigido
- **4 bugs detetados em QA em dev** no fluxo de criação de clientes e configurações. Todos resolvidos com precisão cirúrgica.

### Bug 1 — Email do Portal não era enviado
- **Causa raiz**: O email de boas-vindas com o `portal_access_code` NUNCA era invocado nas rotas de criação (`POST /clients`, `POST /processes/create-client`). O `portal_access_code` era gerado mas o email não era disparado — falha silenciosa sem logs.
- **Correção**:
  - **`backend/routes/clients.py`**: Adicionado `import asyncio` + helper `_send_portal_welcome_email_safe()` (fire-and-forget com try-except aninhado + `logger.error`/`logger.warning` em cada falha). Disparado via `asyncio.create_task()` após `db.clients.insert_one()`. Tenta `task_queue.send_registration_email()` primeiro; se indisponível, envia diretamente via `send_registration_confirmation()`.
  - **`backend/routes/processes.py`**: Adicionado helper `_send_portal_welcome_email_from_process()` (busca/gera `portal_access_code` do cliente, depois envia email). Disparado via `asyncio.create_task()` após `log_history()` na rota `POST /processes/create-client`.
  - **Logs**: `[PORTAL-EMAIL]` prefix em todos os logs (info/warning/error) — falhas de SMTP nunca mais são silenciosas.

### Bug 2 — Timeline a assumir fases fantasma
- **Causa raiz**: `ProcessTimeline.js` recebia `history={process.status_history || activities.filter(...)}` — mas `process.status_history` não existe e `activities` não têm `type`. O prop era SEMPRE `[]`, activando o branch "sem histórico" que marcava `isCompleted: p.order < currentOrder` (index-based — o bug). Fases saltadas apareciam como "Concluídas" com checkmark verde.
- **Causa secundária**: O branch "com histórico" lia `entry.new_status` (campo inexistente) em vez de `entry.new_value` (campo real do `db.history`).
- **Correção**:
  - **`frontend/src/pages/ProcessDetails.js`**: Passa o estado `history` real (já fetched via `getHistory(id)` na linha 1106) em vez da expressão quebrada.
  - **`frontend/src/components/ProcessTimeline.js`**:
    - `buildTimeline` reescrito: constrói `reachedStatuses` (Set) a partir do histórico real (`entry.new_value`), iterando sobre TODAS as fases (`sortedPhases`) em vez do histórico.
    - 4 estados por fase: **Concluída** (alcançada + não atual), **Atual** (atual), **Saltada** (não alcançada + antes da atual), **Pendente** (não alcançada + depois da atual).
    - Datas só aparecem se a fase foi alcançada (registo explícito no histórico) — sem datas inventadas.
    - `TimelineNode`: adicionado `isSkipped` prop (círculo tracejado cinza + label itálico "Saltada").
    - Legenda: adicionado 4º estado "Saltada".

### Bug 3 — Encaminhamento para 'Registos de Clientes'
- **Causa raiz**: `POST /processes/create-client` sempre definia `initial_status = first_status_by_order` (`clientes_espera` — primeira coluna do Kanban ativo). Não havia forma de criar um Lead (status `pre_registo` — a caixa "Registos de Clientes"). Além disso, `lead_status` era sempre `"converted"` (removia o cliente da triagem) e `assign_to_indexer` corria prematuramente.
- **Correção**:
  - **`backend/models/process.py`**: Adicionado `is_lead: Optional[bool] = False` ao `ProcessCreate` model.
  - **`backend/routes/processes.py`** (rota `POST /create-client`):
    - Se `is_lead=True`: `initial_status = "pre_registo"` (vai para Registos de Clientes). `source = "lead"`.
    - Skip `assign_to_indexer()` (pre_registo não deve ser indexado — a auto-atribuição dispara na transição pre_registo → pipeline).
    - `lead_status` mantém-se `"new"` (não `"converted"`) — o cliente continua na triagem.
  - **`frontend/src/pages/StaffDashboard.js`**: `handleCreateLead` passa `is_lead: true` no payload. Toast atualizado para "Registo criado em Registos de Clientes".
  - **`frontend/src/components/CreateProcessModal.jsx`**: Aceita prop `isLead` (default false). Se true, envia `is_lead: true` no payload. Toast diferenciado.

### Bug 4 — Configuração dos Documentos Obrigatórios não gravava
- **Causa raiz**: O SAVE funcionava corretamente (backend gravava no MongoDB). O READ é que estava quebrado — `MandatoryDocumentsSection.fetchConfig()` lia `data.mandatory_documents` (sempre `undefined` porque a API retorna `{config: {...}, fields: [...]}`) em vez de `data.config.mandatory_documents`. O utilizador via uma lista vazia após guardar, pensando que não gravou.
- **Correção**:
  - **`frontend/src/pages/SystemConfigPage.js`** (linha 1810): `data.mandatory_documents` → `(data.config && data.config.mandatory_documents) || data.mandatory_documents || {}`. Agora lê corretamente do nested `config`.
  - **Backend**: Sem alterações necessárias — o save (`replace_one` com full dump) e o merge (`MandatoryDocumentsConfig`) já funcionavam.

### Técnico
- **Backend modificado**: `backend/routes/clients.py` (import asyncio + helper + email send), `backend/routes/processes.py` (helper + email send + is_lead routing), `backend/models/process.py` (campo is_lead).
- **Frontend modificado**: `frontend/src/pages/ProcessDetails.js` (history prop fix), `frontend/src/components/ProcessTimeline.js` (buildTimeline rewrite + isSkipped + legenda), `frontend/src/pages/SystemConfigPage.js` (read path fix), `frontend/src/pages/StaffDashboard.js` (is_lead: true), `frontend/src/components/CreateProcessModal.jsx` (isLead prop).
- **Validação**: `py_compile` ✓; `flake8 --select=E9,F63,F7,F82` → 0 erros; `esbuild --packages=external` ✓ nos 5 ficheiros frontend.
- **Dependências**: Nenhuma nova.

## [2026-07-16] — Pacote CX: Sync UI across Clients and Processes Tables & Modals

### Alterado
- **Nivelamento de UI entre tabelas de Clientes e Processos** + **secção de Notas da IA nos modais**. O Pacote CW funcionou na tabela de Clientes mas falhou na de Processos — este pacote corrige e completa a sincronização visual.

### 1. Tabela de Processos (`ProcessesPage.js`)
- **Nome clicável**: O nome do cliente na tabela (linha 768) era texto plain — agora tem a classe exata `cursor-pointer text-primary hover:underline` e abre o `<ClientDetailsModal />` ao clicar (com `e.stopPropagation()` para não acionar a navegação da row).
- **Bolinhas de notificação inline** ao lado do nome:
  ```jsx
  {process.has_unread_messages && <span className="w-2 h-2 rounded-full bg-blue-500 inline-block ml-2" title="Nova Mensagem"></span>}
  {process.has_new_documents && <span className="w-2 h-2 rounded-full bg-green-500 inline-block ml-2" title="Novo Ficheiro"></span>}
  ```
- **Import + estado + render** do `ClientDetailsModal` adicionados (igual a MyClientsPage e FilteredProcessList).

### 2. Mobile Card View (`FilteredProcessList.js`)
- **Bug corrigido**: A vista de cartão móvel (linha 424) tinha o nome do cliente como texto plain — foi **omitida** no Pacote CW. Agora tem o mesmo `<span>` clicável com a classe exata + bolinhas inline, abrindo o `<ClientDetailsModal />`.

### 3. Popups de Detalhes — Notas da IA
- **`ClientDetailsModal.jsx`**: Nova secção **"Notas da IA"** (linhas 330-341) com formatação distinta — fundo roxo (`bg-purple-50 dark:bg-purple-950/20`), ícone `Sparkles`, texto roxo. Renderiza `client.ai_extracted_notes`. Aparece logo após o bloco "Observações" (que lê `client.notas`).
- **`ProcessDetailsModal.jsx`**: Nova secção **"Notas da IA"** (linhas 859-870) com a mesma formatação roxa + `Sparkles`. Renderiza `process.ai_extracted_notes` (só em modo leitura, não editável). Aparece logo após o bloco "Notas" existente (que lê `process.notes` e é editável).
- **Distinção visual clara**: Notas manuais (Observações) = âmbar + `StickyNote`. Notas da IA = roxo + `Sparkles`. O utilizador distingue instantaneamente a origem.

### Técnico
- **`frontend/src/pages/ProcessesPage.js`**: import ClientDetailsModal (linha 32); estado `clientDetailsModal` (linha 105); nome clicável + bolinhas (linhas 772-785); render do modal (linhas 948-954).
- **`frontend/src/pages/FilteredProcessList.js`**: mobile card nome clicável + bolinhas (linhas 424-437).
- **`frontend/src/components/ClientDetailsModal.jsx`**: import `Sparkles` (linha 52); bloco Notas da IA (linhas 330-341).
- **`frontend/src/components/kanban/ProcessDetailsModal.jsx`**: import `Sparkles` (linha 46); bloco Notas da IA (linhas 859-870).
- **Validação**: `esbuild --packages=external` ✓ nos 4 ficheiros (0 erros).
- **Dependências**: Nenhuma nova — `Sparkles` já existe em `lucide-react`.

## [2026-07-16] — Pacote CW: Trello Mirror Service & Clients Table Final Fixes

### Adicionado
- **`backend/services/trello_service.py`** (NOVO): Serviço de sincronização automática UNIDIRECIONAL (CRM → Trello) para que o Trello funcione como backup estrutural e visual em tempo real. Usa `httpx` (async). Lê `TRELLO_API_KEY`, `TRELLO_TOKEN`, `TRELLO_BOARD_ID` do ambiente. Se faltar config, desliga-se silenciosamente (o CRM funciona sem Trello).
  - **`get_or_create_trello_list(list_name)`**: Procura ou cria uma coluna no quadro Trello. Cache em memória (`_list_cache`). Nome da coluna = `label` do `workflow_statuses` (ex: "Pré-Registo").
  - **`sync_process_to_trello(process, action, new_status)`**: 3 ações:
    - `create`: Cria cartão na lista correta, guarda `trello_card_id` no processo no MongoDB.
    - `move`: Move cartão para a nova lista (usa `trello_card_id` existente).
    - `update`: Atualiza a descrição do cartão com dados úteis extraídos pela IA (NIF, Salário, Valor do Imóvel, Valor a Financiar, etc.).
  - **`_build_card_description(process)`**: Constrói descrição com dados do cliente (NIF, CC, email, telefone), financeiros (salário, valor financiado, capital próprio), imóvel (valor, tipologia, localização), crédito (empréstimo, taxa, prestação, banco), e contagem de campos preenchidos por IA (`field_metadata` source="ai").
  - **Fallbacks inteligentes**: Se `create` mas já tem `trello_card_id` → converte para `move`. Se `move`/`update` mas sem `trello_card_id` → converte para `create`. Nunca rebenta o CRM (try-except global, fire-and-forget).

### Backend — Integração no Kanban (`routes/processes.py`)
- **Import**: `from services.trello_service import sync_process_to_trello` (linha 54).
- **4 pontos de integração** com `asyncio.create_task(...)` (fire-and-forget, não atrasa a UI):
  1. **Criação de processo (cliente)** — linha 910: após `insert_one`, dispara `action="create"`.
  2. **Criação de processo (staff)** — linha 1287: após auto-atribuição de indexador (status pode ser `fila_espera`), dispara `action="create"`.
  3. **Kanban move** — linha 3101: após `update_one` de status, dispara `action="move"` com `new_status`. Constrói `_trello_move_proc = {**process, "status": new_status, "trello_card_id": ...}` para passar o processo atualizado.
  4. **PUT geral (update)** — linhas 4358-4363: após `update_one` + re-fetch, dispara `action="move"` se `data.status` mudou, senão `action="update"`.

### Frontend — Bugs da Tabela Esmagados (`MyClientsPage.js` + `FilteredProcessList.js`)
- **Nome Clicável (100% conforme spec)**:
  - Classe exata `cursor-pointer text-primary hover:underline` em ambas as páginas.
  - Ao clicar, aciona estado local → abre `<ClientDetailsModal />` com `clientId`.
- **Bolinhas de Alerta (inline, formato exato do spec)**:
  ```jsx
  {process.has_unread_messages && <span className="w-2 h-2 rounded-full bg-blue-500 inline-block ml-2" title="Nova Mensagem"></span>}
  {process.has_new_documents && <span className="w-2 h-2 rounded-full bg-green-500 inline-block ml-2" title="Novo Ficheiro"></span>}
  ```
  Aplicadas em ambas as páginas, dentro do `<span>` clicável (a seguir ao nome). Substitui o componente `NotificationDots` anterior para uniformidade visual.
- **Notas na Tabela**: `{process.notes || 'Sem notas recentes'}` — já estava correto, confirmado em ambas as páginas (com fallback `latest_activity_note`/`latest_note`).
- **Filtro de Eliminados (Backend & Frontend)**:
  - **Backend** (`routes/processes.py` + `routes/my_clients.py`): Já implementado (Pacote CP) — `view_mode=deleted` ou `status=eliminado(s)` desliga o filtro padrão de ativos e faz query `is_deleted: True`.
  - **`FilteredProcessList.js`**: Nova entrada `eliminado` no `filterConfig` (ícone `Trash2`). `fetchData` mapeia `filterType === "eliminado"` → `view_mode=deleted`. Acessível via URL `?filter=eliminado`.
  - **`MyClientsPage.js`**: Novo botão "Mostrar Eliminados" (toggle, ícone `Trash2`) que envia `view_mode=deleted` ao backend. Estado persistido em URL param (`view_mode=deleted`). Filtro local atualizado para não excluir terminais quando `showDeleted=true`.

### Técnico
- **Novo ficheiro**: `backend/services/trello_service.py` (~400 linhas).
- **Backend modificado**: `backend/routes/processes.py` (import + 4 pontos de integração).
- **Frontend modificado**: `frontend/src/pages/MyClientsPage.js` (nome clicável, bolinhas inline, toggle eliminados, fetchData + filtro local). `frontend/src/pages/FilteredProcessList.js` (nome clicável, bolinhas inline, filterConfig eliminado, fetchData view_mode=deleted, import Trash2).
- **Validação**: `py_compile` ✓; `flake8 --select=E9,F63,F7,F82` → 0 erros; `esbuild --packages=external` ✓ nos 2 ficheiros frontend.
- **Dependências**: Nenhuma nova — `httpx==0.28.1` já no `requirements.txt`.

## [2026-07-16] — Pacote CV: Robust Omnichannel Bulk Document Scanner

### Alterado
- **`backend/scripts/bulk_ai_document_scan.py` REESCRITO** (substitui o Pacote CU por uma implementação mais robusta e estrita, com regras omnicanal explícitas). O script percorre `db.documents` (is_deleted != True), descarrega o binário do S3 via **boto3 direto**, envia à OpenAI (gpt-4o-mini via `analyze_document_from_base64`), e atualiza o processo + `field_metadata` (source: "ai").

### 1. Conexão e Configuração
- **MongoDB**: `motor_asyncio.AsyncIOMotorClient(MONGO_URL)`, `db = client[DB_NAME]`.
- **S3 (boto3 direto)**: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION` (default `'eu-north-1'`), `AWS_BUCKET_NAME`. Falta de qualquer variável → `sys.exit(1)` com mensagem clara.

### 2. Resiliência Omnicanal do Esquema de Dados
- **Query**: `db.documents.find({"is_deleted": {"$ne": True}})` — todos os documentos não apagados.
- **Resolução de chave S3**: Para cada documento, tenta os campos em ordem: `s3_key`, `file_key`, `key`, `path`, `url`.
- **URL pública S3**: Se o valor contiver `amazonaws.com/`, faz split e agarra apenas o sufixo (chave limpa). Faz `unquote()` para descodificar `%20` etc.
- **Sem chave**: Se nenhuma chave for encontrada → `continue` (status `skipped`).

### 3. Pipeline de Análise
1. **Download S3** (`asyncio.to_thread` para não bloquear event loop): `s3_client.get_object(Bucket, Key)`.
2. **Base64**: `base64.b64encode(content).decode("utf-8")`.
3. **MIME type**: Derivado de `content_type` do documento ou extensão do filename (fallback `application/pdf`).
4. **IA**: `analyze_document_from_base64(base64_content, mime_type, "outro")` de `services.ai_document`.

### 4. Integração com Processos e Rastreabilidade
- **Marca documento**: Se extração bem-sucedida → `db.documents.update_one({"id": doc_id}, {"$set": {"ai_processed": True, "ai_processed_at": ISO, "ai_document_type": tipo}})`.
- **Busca processo**: `db.processes.find_one({"id": process_id})`.
- **Build update**: `build_update_data_from_extraction(extracted_data, tipo_detetado, existing_data)` — mapeia extração → `personal_data`/`financial_data`/`real_estate_data`/`credit_data`.
- **field_metadata**: Para cada campo preenchido, injeta `field_metadata["<group>.<field>"] = {"source": "ai", "updated_at": ISO}`.
- **Merge seguro**: `{**existing_fm, **new_ai_fm}` — não apaga metadata de campos não atualizados (Pacote CS).
- **$set no processo**: Aplica `process_set` com campos + `field_metadata` merged + `updated_at`.

### 5. Gestão de Erros e Rate Limiting
- **Rate limit (429)**: Print de aviso + `await asyncio.sleep(300)` (5 min de "castigo") + `continue` para o próximo documento.
- **S3 404 / NoSuchKey**: Aviso + `continue` (sem pausa — ficheiro inexistente não é erro de API).
- **Sucesso**: `await asyncio.sleep(25)` (travão de segurança entre documentos).
- **Deteção robusta de rate-limit**: 4 camadas — (1) `RateLimitError` custom de `services.ai_document`; (2) `openai.RateLimitError` do SDK; (3) `botocore.exceptions.ClientError` com código Throttling/SlowDown; (4) heurística por mensagem ("429", "rate limit", "too many requests", "quota", "throttle", "tpm", "rpm limit", "limite de pedidos", "tente novamente mais tarde").
- **Safety net**: `try-except` no loop principal apanha qualquer exceção que escape do helper interno — o script nunca rebenta.

### CLI
```
cd backend
python scripts/bulk_ai_document_scan.py --dry-run
python scripts/bulk_ai_document_scan.py --limit 20
python scripts/bulk_ai_document_scan.py --sleep-success 25 --sleep-rate-limit 300
```

### Diferenças vs Pacote CU (substituído)
| Aspecto | Pacote CU | Pacote CV |
|---|---|---|
| Cliente S3 | `s3_service` (wrapper) | **boto3 direto** |
| Coleções pesquisadas | `document_metadata` + `documents` | **`db.documents`** (is_deleted != True) |
| Resolução de chave S3 | só `s3_path` | **omnicanal**: s3_key, file_key, key, path, url + split amazonaws.com |
| Função IA | `analyze_single_document` (bytes) | **`analyze_document_from_base64`** (base64, tipo 'outro') |
| Marcar doc processado | não | **`ai_processed: True`** + `ai_processed_at` + `ai_document_type` |
| Pausa sucesso | 60s | **25s** |
| Pausa rate-limit | 300s | 300s (igual) |
| S3 404 handling | não específico | **NoSuchKey/404 → continue sem pausa** |

### Técnico
- **Ficheiro reescrito**: `backend/scripts/bulk_ai_document_scan.py` (~635 linhas, substitui ~430 do CU).
- **Imports novos**: `boto3`, `botocore.exceptions.ClientError`, `urllib.parse.unquote`, `base64`.
- **Validação**: `py_compile` ✓; `flake8 --select=F,E9` → 0 erros.
- **Dependências**: Nenhuma nova — `boto3==1.42.21`, `botocore==1.42.21` já no `requirements.txt`.

## [2026-07-16] — Pacote CU: Safe Staggered AI Bulk Scanner Script

> ⚠️ **SUBSTITUÍDO pelo Pacote CV** (mesmo ficheiro). Mantido no histórico para referência.

### Adicionado
- **Script `backend/scripts/bulk_ai_document_scan.py`**: Script de background que percorre documentos legados associados a processos ativos e extrai dados com IA, preenchendo campos vazios e marcando proveniência no `field_metadata` (`source: "ai"`). Desenhado para conta de API gratuita — **rate-limit extremamente conservador e imune a falhas**.

### Travões de Segurança (CRÍTICO)
- **Pausa pós-sucesso**: Após cada extração com sucesso, `await asyncio.sleep(60)` (1 minuto) para não estourar o RPM gratuito.
- **Pausa de "castigo"**: Se apanhar erro de rate-limit (429 Too Many Requests ou exceção genérica de rate limit), faz `await asyncio.sleep(300)` (5 minutos) e `continue` para o próximo documento — **não rebenta o script**.
- **Deteção de rate-limit robusta**: Cobre (1) `RateLimitError` custom de `services.ai_document`, (2) `openai.RateLimitError` do SDK, (3) heurística por mensagem ("429", "rate limit", "too many requests", "quota", "throttle", "tpm", "rpm limit").
- **Safety net**: `try-except` no loop principal apanha qualquer `RateLimitError` ou exceção genérica que escape do helper interno — o script nunca rebenta por rate-limit.

### Lógica de Pesquisa
1. **Processos ativos não-terminais**: `is_deleted != True` E `status $nin [concluido, desistencias, desistido, cancelado, arquivado, eliminado]`.
2. **Campos-chave vazios**: Verifica cliente (`dados_pessoais.nif`, `dados_pessoais.documento_id`) e processo (`financial_data.salario_bruto`/`monthly_income`/`valor_financiado`, `real_estate_data.valor_imovel`/`valor_patrimonial`, `credit_data.requested_amount`/`interest_rate`/`monthly_payment`).
3. **Documentos com ficheiro em S3**: Procura em `document_metadata` (s3_path exists) e `documents` (status UPLOADED/RECEIVED/SUBMITTED com s3_path).
4. **Apenas processa** processos que tenham pelo menos 1 campo vazio E documentos associados.

### Respeito por Dados Existentes
- **`manually_edited_fields`**: Campos na lista `manually_edited_fields` do processo **não são sobrescritos** pela IA.
- **`field_metadata[source]="manual"`**: Campos já marcados como manuais (no processo ou no cliente) **não são sobrescritos** — o Consultor tem prioridade sobre a IA.
- **Merge seguro de `field_metadata`**: `{**existing_fm, **new_ai_fm}` — não apaga metadata de campos não atualizados neste request (Pacote CS).
- **`ai_extraction_history`**: Cada extração é registada no array `ai_extraction_history` do processo (doc_id, filename, document_type, fields, analyzed_at, source_collection) para auditoria.

### Atualização da BD
- **Cliente**: `dados_pessoais.*` (NIF, CC, data_nascimento, etc.) + `field_metadata["dados_pessoais.<field>"] = {source:"ai", updated_at, confidence?}`.
- **Processo**: `financial_data.*`, `real_estate_data.*`, `credit_data.*` + `field_metadata["<group>.<field>"] = {source:"ai", ...}`.
- **Separação cliente/processo**: helper `split_metadata_client_process` manda `dados_pessoais.*`/`contacto.*`/`nome` para o cliente; restantes para o processo.

### Reutilização de Serviços Existentes
- **`analyze_single_document`** (`services/ai_document.py`): Já tem tenacity retry em `RateLimitError` com backoff exponencial (2-32s, 5 tentativas) + `MAX_CONCURRENT_ANALYSIS=5`. Este script adiciona uma camada EXTRA de segurança por cima.
- **`build_update_data_from_extraction`** (`services/ai_document.py`): Mapeia extração → formato de update do processo (com validação de NIF, filtragem de placeholders como "YYYY-MM-DD" e "123456789").
- **`s3_service.get_file_content`** (`services/s3_storage.py`): Lê bytes do S3 (síncrono → envolvido em `asyncio.to_thread` para não bloquear o event loop).

### CLI
```
cd backend
python scripts/bulk_ai_document_scan.py --dry-run              # simular
python scripts/bulk_ai_document_scan.py --limit 10             # processar 10 docs
python scripts/bulk_ai_document_scan.py --process-id <uuid>    # processo específico
python scripts/bulk_ai_document_scan.py --sleep-success 60 --sleep-rate-limit 300
```

### Técnico
- **Novo ficheiro**: `backend/scripts/bulk_ai_document_scan.py` (~430 linhas).
- **Bootstrap**: `sys.path.insert(backend/)`, `load_dotenv(backend/.env)`, `AsyncIOMotorClient`, `asyncio.run(_run())` — segue convenção de `seed_qa_ultimate.py` e `backfill_empty_fields.py`.
- **Validação**: `py_compile` ✓; `flake8 --select=E9,F63,F7,F82` → 0 erros.
- **Dependências**: Nenhuma nova — usa `motor`, `python-dotenv`, `openai`, `boto3` (já instalados no backend).

## [2026-07-16] — Pacote CT: AI Field Indicator UI (Frontend)

### Adicionado
- **Componente `AIBadge`** (`frontend/src/components/ui/AIBadge.jsx`): Indicador visual de proveniência de dados. Recebe `source` (`"ai"` | `"client"` | `"manual"`), `updated_at` e `confidence`.
  - `"ai"` → ícone `Sparkles` (roxo) com tooltip "Preenchido pela IA" (+ confiança % + data).
  - `"client"` → ícone `User` (teal) com tooltip "Preenchido pelo Cliente no Portal" (+ data).
  - `"manual"` → **não renderiza nada** (o humano sobrepôs o dado).
- **Helpers exportados**: `getFieldMeta(fieldPath, ...metadataSources)` para ler metadata de múltiplas fontes (process + client) com prioridade; `buildManualMetadata(fieldPaths)` para construir payloads de proveniência manual.

### Frontend — `ProcessDetails.js` (Detalhes do Processo)
- **Leitura de `field_metadata`**: Helper `getFieldMetaFor(path)` que lê de `process.field_metadata` com fallback para `clientData.field_metadata`.
- **AIBadge em 10 campos importantes**: NIF (`dados_pessoais.nif`), CC (`dados_pessoais.documento_id`), Rendimento Mensal (`financial_data.monthly_income`), Rendimento Bruto (`financial_data.rendimento_bruto`), Valor a Financiar (`financial_data.valor_financiado`), Valor do Imóvel (`real_estate_data.valor_imovel`), Valor Patrimonial (`real_estate_data.valor_patrimonial`), Valor do Empréstimo (`credit_data.requested_amount`), Taxa de Juro (`credit_data.interest_rate`), Prestação Mensal (`credit_data.monthly_payment`).
- **Save manual**: `executeSave` envia `field_metadata` com `source="manual"` para os campos do cartão editado (`editingCardId`). Mapeamento `MANUAL_FIELDS_BY_CARD` cobre `personal_identificacao`, `personal_morada`, `financial_rendimentos`, `realestate_caracteristicas`, `credit_dados`. Campos `dados_pessoais.*`/`contacto.*`/`nome` vão para o `PUT /clients`; restantes vão para o `PUT /processes`. O backend (Pacote CS) faz merge seguro.

### Frontend — `ClientDetailPage.js` (Ficha do Cliente)
- **`ContactRow` estendido**: Aceita prop `meta` e renderiza `<AIBadge />` ao lado da label.
- **AIBadge em 6 ContactRows**: Email (`contacto.email`), Telefone (`contacto.telefone`), NIF (`dados_pessoais.nif`), Estado Civil (`dados_pessoais.estado_civil`), Profissão (`dados_pessoais.profissao`), Morada Fiscal (`dados_pessoais.morada_fiscal`).
- **AIBadge em 4 campos do modal de edição**: Nome (`nome`), NIF, Email, Telefone.
- **Inline edit (Email/Telefone)**: `onEdit` envia `field_metadata` com `source="manual"` para o campo editado + atualiza estado local (badge desaparece imediatamente).
- **Modal save (`handleEditSave`)**: Recolhe caminhos alterados (`nome`, `contacto.email`, `contacto.telefone`, `dados_pessoais.nif`) e envia `field_metadata` manual apenas para esses campos. Atualiza estado local para o AIBadge reagir.

### Comportamento
- **IA extrai dado** → badge `Sparkles` roxo aparece ao lado da label.
- **Cliente preenche no Portal** → badge `User` teal aparece (via Pacote CS, injeção automática `source="client"`).
- **Consultor edita e guarda** → frontend envia `source="manual"` → backend faz merge → badge desaparece (o humano sobrepôs o dado).

### Técnico
- **Novo ficheiro**: `frontend/src/components/ui/AIBadge.jsx` (componente + helpers `getFieldMeta`/`buildManualMetadata`/`buildManualMeta`).
- **Frontend** (`frontend/src/pages/ProcessDetails.js`): import AIBadge (linha 118); helper `getFieldMetaFor` (linhas 1850-1854); AIBadge em 10 campos; `MANUAL_FIELDS_BY_CARD` + merge no `executeSave` (linhas 1595-1644).
- **Frontend** (`frontend/src/pages/ClientDetailPage.js`): import AIBadge (linha 24); `ContactRow` com prop `meta` (linha 147, render linha 188-191); 6 call sites com `meta`; inline `onEdit` com `field_metadata` (linhas 489-500, 530-541); `handleEditSave` com `changedPaths` + `buildManualMetadata` (linhas 276-310); 4 AIBadge no modal (linhas 866-907).
- **Validação**: `esbuild --packages=external` ✓ nos 3 ficheiros (0 erros de sintaxe).
- **Dependências**: Nenhuma nova — usa `lucide-react` (Sparkles, User), `@radix-ui/react-tooltip`, `class-variance-authority` (já instalados).

## [2026-07-16] — Pacote CS: Data Provenance Foundation (Backend)

### Adicionado
- **Rastreabilidade de Dados (`field_metadata`)**: Novo objeto `field_metadata` em `clients` e `processes` que rastreia a origem e data de atualização de cada campo. Formato: `{"dados_pessoais.nif": {"source": "ai"|"manual"|"client", "updated_at": "ISO", "confidence": 0.95}}`.

### Backend
- **`PUT /clients/{id}`** (`routes/clients.py`): Aceita `field_metadata` do frontend e faz **merge seguro** (`{**existing, **new}`) — não apaga metadata de campos não atualizados. Adicionado `request: Request` à assinatura.
- **`PUT /processes/{id}`** (`routes/processes.py`): Mesma lógica de merge antes do `$set`.
- **`PUT /portal/me`** (`routes/portal.py`): **Injeção automática** — para cada campo atualizado pelo cliente, injeta `field_metadata[f"contacto.{key}"] = {"source": "client", "updated_at": now}`. O cliente não precisa de enviar `field_metadata`.

### Formato do `field_metadata`
```json
{
  "dados_pessoais.nif": {"source": "ai", "updated_at": "2026-07-16T...", "confidence": 0.95},
  "contacto.email": {"source": "client", "updated_at": "2026-07-16T..."},
  "financial_data.salario_bruto": {"source": "manual", "updated_at": "2026-07-16T..."}
}
```

### Segurança
- **Merge seguro**: `{**existing_metadata, **new_metadata}` — apenas campos enviados neste request são sobrescritos; metadata de campos não atualizados é preservada.
- **Portal automático**: O cliente não envia `field_metadata` — o backend injeta `source="client"` automaticamente.

### Técnico
- **Backend** (`backend/routes/clients.py`): `request: Request` (linha 1496); `field_metadata` merge (linhas 1580-1588).
- **Backend** (`backend/routes/processes.py`): `field_metadata` merge (linhas 4326-4337).
- **Backend** (`backend/routes/portal.py`): injeção automática `source="client"` (linhas 924-944).
- **Validação**: `py_compile` ✓; `flake8 --select=E9,F63,F7,F82` → 0 erros.

## [2026-07-16] — Pacote CR: Hardcode Changelog Time-Diff Logic

### Alterado
- **Filtragem temporal forçada na geração de changelog**: Dupla barreira: (1) código Python filtra a fonte (git `--since`, markdown `_filter_lines_since`) baseado na data do último anúncio em `announcements`; (2) prompt de sistema da IA inclui instrução temporal obrigatória como barreira de segurança extra.

### Backend (`backend/services/changelog_service.py`)
- **`_get_last_changelog_date()`**: Reescrita para procurar em `announcements` (`{"type": "changelog"}`, `sort=[("created_at", -1)]`) primeiro, com fallback para `system_changelogs` (`published_at`).
- **`since_date_str`**: `since_date.strftime("%Y-%m-%d %H:%M")` se existir, `"nunca"` se None.
- **Prompt de sistema**: `system_prompt = CHANGELOG_SYSTEM_PROMPT + "\n\n" + temporal_instruction` onde `temporal_instruction` = "IMPORTANTE: A última nota de atualização foi gerada em {since_date_str}. A tua tarefa é extrair e resumir APENAS as novidades e alterações que tenham ocorrido DEPOIS dessa data. Ignora completamente qualquer ponto do histórico que seja anterior a essa data."
- **Chamada à IA**: Usa `system_prompt` (com instrução temporal) em vez de `CHANGELOG_SYSTEM_PROMPT` (constante estática).

### Segurança
- Não falha se não houver `last_announcement` — `since_date=None` → `since_date_str="nunca"` → a IA resume tudo (primeira geração).

### Técnico
- **Backend** (`backend/services/changelog_service.py`): `_get_last_changelog_date` (linhas 57-105); `since_date_str` (linha 472); `temporal_instruction` + `system_prompt` (linhas 537-547); chamada IA (linha 580).
- **Validação**: `py_compile` ✓; `flake8 --select=E9,F63,F7,F82` → 0 erros.

## [2026-07-16] — Pacote CQ: Robust Portal Lock Logic

### Alterado
- **Bloqueio do portal baseado em Fases do Kanban**: A flag `is_indexed` pode não estar atualizada atempadamente na BD. Substituído por avaliação direta do `status` do processo. O perfil é trancado se o processo avançou para além das fases iniciais (`pre_registo`, `clientes_espera`, `documentacao`, `eliminado`, `desistencias`).

### Backend (`backend/routes/portal.py`)
- **`GET /portal/me`**: Query alterada para `{"status": {"$nin": ["pre_registo", "clientes_espera", "documentacao", "eliminado", "desistencias"]}}`.
- **`PUT /portal/me`**: Mesma query. Lança 403 se o processo estiver numa fase avançada.

### Evolução da regra de bloqueio
| Pacote | Regra | Problema |
|--------|-------|----------|
| Original | Qualquer processo ativo | Bloqueava em pre_registo |
| Pacote CB | `status != "pre_registo"` | Bloqueava em fases intermédias |
| Pacote CF/CI | `is_indexed == True` | Flag pode não estar atualizada |
| **Pacote CQ** | **`status $nin [fases iniciais]`** | ✅ Avalia diretamente o Kanban |

### Técnico
- **Backend** (`backend/routes/portal.py`): `GET /me` (linhas 762-774); `PUT /me` (linhas 849-864).
- **Validação**: `py_compile` ✓; `flake8 --select=E9,F63,F7,F82` → 0 erros.

## [2026-07-16] — Pacote CP: Fix My Clients Table UI & Filters

### Corrigido
- **Filtro Eliminados**: `my_clients.py` agora suporta `view_mode="deleted"` / `status="eliminado"` — remove `is_active` e `INACTIVE_STATUSES`, aplica apenas `is_deleted=True` com filtro de role. `processes.py` já tinha `wants_deleted` implementado.

- **Bolinhas de Notificação**: Confirmadas em `MyClientsPage.js` e `FilteredProcessList.js` — `NotificationDots` renderiza junto ao nome com `has_unread_messages` (azul) e `has_new_documents` (verde).

- **Nome Clicável com Modal**: `MyClientsPage.js` — nome do cliente transformado em `cursor-pointer text-primary hover:underline` com `onClick` que abre `ClientDetailsModal` com `client.client_id || client.id`. `FilteredProcessList.js` já tinha (Pacote CH).

- **Notas na Tabela**: Ambas as tabelas agora lêem `process.notes` primeiro (sobrescrito pelo Pacote CJ com última atividade real), com fallback `latest_activity_note` → `latest_note` → "Sem notas recentes".

### Técnico
- **Backend** (`backend/routes/my_clients.py`): `wants_deleted` (linhas 69-117).
- **Frontend** (`frontend/src/pages/MyClientsPage.js`): import `ClientDetailsModal`; estado `clientDetailsModal`; nome clicável (linhas 530-545); notas lê `notes` primeiro (linhas 603-616); modal no final (linhas 654-660).
- **Frontend** (`frontend/src/pages/FilteredProcessList.js`): notas lê `notes` primeiro (linhas 561-574).
- **Validação**: `py_compile` ✓; `flake8` → 0 erros; `esbuild` → 0 erros.

## [2026-07-16] — Pacote CO v2: Backfill — campos de dropdown/select adicionados

### Corrigido
- **Script de backfill não preenchia campos de dropdown/select**: O script original (Pacote CO) não preenchia ~25 campos, principalmente campos de caixa de seleção. Corrigido: agora preenche TODOS os campos dos modelos.

### Campos de SELECT/DROPDOWN adicionados
- **financial_data**: `tipo_contrato`, `irs_taxa_retencao`, `dependentes`
- **real_estate_data**: `tipologia`, `tipo_imovel`, `finalidade`, `certificado_energetico`, `num_quartos`, `estacionamento`, `arrecadacao`
- **credit_data**: `prazo_meses`, `spread`, `banco`, `tipo_taxa`, `interest_rate`/`taxa_anual`, `admission_year`, `is_ppe`, `is_fpe`

### Outros campos adicionados
- **Clientes**: `nome_pai`, `nome_mae`, `data_validade_cc`
- **financial_data**: `antiguidade_anos`, `renda_mensal`, `prestacao_auto`, `outros_creditos`, `despesas_total`, `valor_entrada`
- **real_estate_data**: `ja_tem_imovel`, `has_property`, `ja_tem_casa_escolhida`, `freguesia`, `area_bruta`, `area_util`, `valor_patrimonial`
- **credit_data**: `monthly_payment`/`prestacao_mensal` (calculada por fórmula de amortização francesa), `requested_amount`, `loan_term_years`, `bank_name`

### Técnico
- **Backend** (`backend/scripts/backfill_empty_fields.py`): v2 — ~25 campos adicionais; `is_empty()` simplificado (0 não é vazio); prestação mensal calculada.
- **Validação**: `py_compile` ✓; `flake8 --select=E9,F63,F7,F82` → 0 erros.

### Regras de Preenchimento
- **Clientes**: `dados_pessoais` (nif, documento_id, telefone, profissao, estado_civil, data_nascimento, naturalidade, nacionalidade, morada_fiscal, sexo) + `contacto` (telefone, telefone_secundario, email_secundario).
- **Processos**: `financial_data` (salario_bruto, salario_liquido, tipo_contrato, empresa, capitais_proprios) + `real_estate_data` (valor_imovel, tipologia, concelho, localidade, tipo_imovel, codigo_postal) + `credit_data` (montante_financiado calculado = valor_imovel - capitais_proprios, prazo_meses, spread, banco, tipo_taxa).

### Segurança
- `is_empty()`: verifica None/vazio/string vazia. Não considera `0` como vazio para valores numéricos.
- `update_one` individual (não `update_many`) para logging granular.
- Contagem de atualizados/ignorados/campos preenchidos + resumo no terminal.

### CLI
```bash
python scripts/backfill_empty_fields.py                # executar
python scripts/backfill_empty_fields.py --dry-run      # simular
python scripts/backfill_empty_fields.py --limit 50     # limitar
```

### Técnico
- **Backend** (`backend/scripts/backfill_empty_fields.py`): 320 linhas; Motor async + dotenv + Faker('pt_PT'); `gerar_nif()` com dígito de controlo; `backfill_clients()` + `backfill_processes()`; `print_summary()`.
- **Validação**: `py_compile` ✓; `flake8 --select=E9,F63,F7,F82` → 0 erros.

## [2026-07-16] — Pacote CK: Registrations Rule & Modal Notes

### Corrigido
- **Clientes avançados apareciam nos Registos**: Clientes com processos em fases avançadas (fora de `pre_registo`, `clientes_espera`, `eliminado`) apareciam na tabela de Registos de Leads. Corrigido: `should_exclude` faz `continue` se o cliente tem um processo que já passou da fase inicial.

- **Modal não mostrava notas**: A modal de detalhes do cliente só lia `client.notas`. Atualizado para usar fallback `notas || notes || 'Sem observações'`.

- **Botão Visitas no Portal**: Confirmado já comentado (Pacote CB) — sem alteração.

### Backend (`backend/routes/clients.py`)
- **`list_registered_clients`**: Bloco `processes_info` substituído com `should_exclude` — se `status not in ["pre_registo", "clientes_espera", "eliminado"]`, `continue` (cliente não aparece nos Registos).

### Frontend (`frontend/src/pages/ClientRegistrationsPage.js`)
- **Modal de detalhes**: `{safeString(detailsDialog.client.notas || detailsDialog.client.notes) || 'Sem observações'}`.

### Técnico
- **Backend** (`backend/routes/clients.py`): `should_exclude` (linhas 543-561).
- **Frontend** (`frontend/src/pages/ClientRegistrationsPage.js`): fallback notas (linhas 916-925).
- **Validação**: `py_compile` ✓; `flake8 --select=E9,F63,F7,F82` → 0 erros; `esbuild --loader=jsx` → 0 erros.

## [2026-07-16] — Pacote CJ: Fetch Latest Activity Note for Lists

### Alterado
- **Campo `notes` sobrescrito com última atividade real**: Em todas as rotas de listagem (`get_processes`, `get_processes_paginated`, `get_my_clients`), o campo `notes` é agora sobrescrito com a última atividade real do consultor (da coleção `activities`, `action` in `["note_added", "comment"]`, mais recente por `created_at`).

### Backend
- **`backend/routes/processes.py`**: `get_processes` (linhas 1790-1797) e `get_processes_paginated` (linhas 1998-2005) — bloco `find_one` em `activities` com `sort=[("created_at", -1)]`.
- **`backend/routes/my_clients.py`**: `get_my_clients` (linhas 303-310) — mesmo bloco.

### Técnico
- **Validação**: `py_compile` ✓; `flake8 --select=E9,F63,F7,F82` → 0 erros.

## [2026-07-16] — Pacote CI: Fix Portal Profile Lock Code

### Alterado
- **Simplificação do código de bloqueio do portal**: O Pacote CF já tinha a query correta (`is_indexed: True`), mas com complexidade desnecessária (projeção de `is_data_confirmed`/`status`, lógica condicional, duas mensagens de erro). Simplificado para o código exato pedido: query minimalista, projeção `{"_id": 0, "id": 1}`, mensagem unificada.

### Backend (`backend/routes/portal.py`)
- **`GET /portal/me`**: `has_process = active_process is not None` (projeção minimalista, sem `is_data_confirmed`/`status`).
- **`PUT /portal/me`**: Mensagem unificada: "Dados trancados. O seu processo já se encontra em análise." (removidas as duas mensagens condicionais).

### Técnico
- **Backend** (`backend/routes/portal.py`): `GET /me` (linhas 757-767); `PUT /me` (linhas 840-851).
- **Validação**: `py_compile` ✓; `flake8 --select=E9,F63,F7,F82` → 0 erros.

## [2026-07-16] — Pacote CH: Reusable Client Details Modal with Observations

### Adicionado
- **Componente `ClientDetailsModal.jsx` reutilizável**: Extraído da modal de detalhes do cliente em `ClientRegistrationsPage.js`. Mostra dados completos do cliente (contactos, dados pessoais, financeiros, 2º titular, metadados) + novo bloco **"Observações"** (`client.notas`) com ícone `StickyNote` e fundo âmbar. Props: `open`, `clientId`, `onClose`, `onNavigateToProcess`.

### Integração
- **`FilteredProcessList.js`**: Nome do cliente transformado em texto clicável (azul/underline) que abre `ClientDetailsModal` com `process.client_id`. `onNavigateToProcess` permite navegar diretamente para o processo.

### Técnico
- **Frontend** (`frontend/src/components/ClientDetailsModal.jsx`): NOVO componente (280 linhas). Fetch via `GET /api/clients/{id}`. Bloco "Observações" com `StickyNote` + `client.notas` + `whitespace-pre-wrap`.
- **Frontend** (`frontend/src/pages/FilteredProcessList.js`): import `ClientDetailsModal`; estado `clientDetailsModal`; nome clicável (`text-blue-600 hover:underline`); modal renderizada no final.
- **Validação**: `esbuild --loader=jsx` → 0 erros.

## [2026-07-16] — Pacote CG: Show Latest Activity Note in Process Lists

### Corrigido
- **Coluna de Notas mostrava campo desatualizado**: As listas de processos (`FilteredProcessList.js` e `MyClientsPage.js`) mostravam `process.notes` (campo estático do processo) em vez da última nota real que o consultor escreveu na timeline. Corrigido: o backend agora injeta `latest_activity_note` (da coleção `activities`) em ambos os endpoints de listagem, e o frontend lê este campo.

### Backend
- **`GET /my-clients` (processes.py)**: Adicionado batch enrichment `latest_activity_note` via aggregation na coleção `activities` (`$match` por `process_id` + `comment` não vazio, `$sort` por `created_at` descendente, `$group` com `$first`). Injetado em `clients_list.append`. Leads ficam com `null`.
- **`GET /my-clients` (my_clients.py)**: Mesma aggregation. Injetado em cada processo do array `processes`.
- **`GET /processes`**: Já tinha `latest_note` (Pacote BT) — mantido para retrocompatibilidade.

### Frontend
- **`FilteredProcessList.js`**: Atualizado para ler `latest_activity_note` primeiro (fallback para `latest_note` do Pacote BT, depois `process.notes`).
- **`MyClientsPage.js`**: Nova coluna "Notas" adicionada entre "Ações Pendentes" e "Última Atualização". Lê `client.latest_activity_note` com fallback.

### Técnico
- **Backend** (`backend/routes/processes.py`): batch enrichment `latest_activity_note` no `GET /my-clients` (linhas 2870-2890); injeção no `clients_list.append` (linhas 2956-2959).
- **Backend** (`backend/routes/my_clients.py`): batch enrichment `latest_activity_note` (linhas 274-301).
- **Frontend** (`frontend/src/pages/FilteredProcessList.js`): lê `latest_activity_note` (linhas 546-552).
- **Frontend** (`frontend/src/pages/MyClientsPage.js`): coluna "Notas" (TableHead linha 506-507; TableCell linhas 591-604).
- **Validação**: `py_compile` ✓; `flake8 --select=E9,F63,F7,F82` → 0 erros; `esbuild --loader=jsx` → 0 erros.

## [2026-07-16] — Pacote CF: Lock Client Portal Profile ONLY if is_indexed

### Corrigido
- **Bloqueio do perfil demasiado agressivo**: O perfil do cliente era bloqueado quando o processo saía do `pre_registo` (Pacote CB), o que impedia clientes em fases intermédias (documentacao, analise, etc.) de editar o perfil. Corrigido: o bloqueio agora acontece **apenas** quando o processo tem `is_indexed == True` (ou seja, a Indexação marcou o processo como indexado). Clientes com processos em `pre_registo`, `clientes_espera`, `documentacao`, `analise`, ou qualquer fase anterior à indexação podem editar o perfil livremente.

### Backend (`backend/routes/portal.py`)
- **`GET /portal/me`**: Query alterada para `{"id": {"$in": process_ids}, "is_deleted": {"$ne": True}, "is_indexed": True}`. `has_process = active_process is not None` (simplificado).
- **`PUT /portal/me`**: Mesma query com `is_indexed: True`. Só lança 403 se o processo estiver indexado.

### Frontend (`frontend/src/pages/ClientPortal.jsx`)
- **Comentário atualizado** para refletir a nova regra (PACOTE CF). Lógica `isLocked = profile?.has_process === true || isDataConfirmed` sem alteração — já obedece ao backend.

### Evolução da regra de bloqueio
| Pacote | Regra de bloqueio |
|--------|------------------|
| Original (pré-BM) | `has_process = True` para qualquer processo ativo |
| Pacote CB | `status != "pre_registo" OR is_data_confirmed` |
| **Pacote CF** | **`is_indexed == True`** (apenas quando a Indexação marca o processo) |

### Técnico
- **Backend** (`backend/routes/portal.py`): `GET /portal/me` (linhas 765-777); `PUT /portal/me` (linhas 850-871).
- **Frontend** (`frontend/src/pages/ClientPortal.jsx`): comentário (linhas 1413-1416).
- **Validação**: `py_compile` ✓; `flake8 --select=E9,F63,F7,F82` → 0 erros; `esbuild --loader=jsx` → 0 erros.

## [2026-07-16] — Pacote CE: Add Restore Button to BackupsPage

### Adicionado
- **Botão "Restaurar Backup" na UI de Backups**: Botão vermelho (`variant="destructive"`) adicionado na barra superior da `BackupsPage.js`, ao lado de "Verificar Integridade". Clique abre `AlertDialog` sério com aviso de operação destrutiva. Se aceito, dispara `POST /api/backup/restore` (Pacote CD — swap atómico).

### Frontend (`frontend/src/pages/BackupsPage.js`)
- **Estado `restoring`**: `useState(false)` — controla loading durante o restauro.
- **`handleRestore()`**: `POST /api/backup/restore` com body `{confirm: "RESTAURAR_PRODUCAO"}`. Sucesso: `toast.success` com estatísticas + `window.location.reload()` após 1.5s. Erro: `toast.error` com detalhe.
- **Botão "Restaurar Backup"**: `variant="destructive"`, ícone `AlertTriangle`, `disabled` quando `restoring || backupInProgress || verifying`.
- **AlertDialog de confirmação**: Título "Atenção! Operação Destrutiva" + descrição exata: "Esta ação vai apagar a base de dados atual e substituí-la pelo último backup guardado no servidor cloud. Todas as ações efetuadas nas últimas horas serão perdidas."
- **Overlay de loading full-screen**: `fixed inset-0 z-50 bg-black/50 backdrop-blur-sm` com `Loader2` e texto "A descarregar e a restaurar a base de dados (isto pode demorar alguns minutos)..."

### Técnico
- **Frontend** (`frontend/src/pages/BackupsPage.js`): estado `restoring` (linha 53); `handleRestore` (linhas 197-230); botão destructive + AlertDialog (linhas 278-317); overlay de loading (linhas 318-329).
- **Validação**: `esbuild --loader=jsx` → 0 erros.

## [2026-07-16] — Pacote CD: Create Emergency Restore Endpoint

### Adicionado
- **Endpoint de restauro de emergência com swap atómico** (`POST /api/backup/restore`): Novo endpoint que restaura a BD de Produção a partir do backup mais recente no S3, usando coleções temporárias e rename atómico para garantir que a BD nunca fica inconsistente (mesmo que o processo falhe a meio). Diferente do endpoint existente `/restore-from-s3` (que faz `delete_many` + `insert_many` diretamente — não atómico).

### Segurança
- **Acesso**: `Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))` — apenas Admin e CEO.
- **Confirmação explícita**: Requer `{"confirm": "RESTAURAR_PRODUCAO"}` no body.
- **Preserva system_config**: A config atual do sistema não é restaurada (ignora `system_config`, `backup_history`, `system.indexes`).

### Fluxo do Swap Atómico
1. **Download S3** → `BytesIO` (memória, não disco)
2. **Extrair JSON** de todas as coleções do ZIP (ignora `backup_history`, `system.indexes`, `system_config`)
3. **`insert_many`** para coleções temporárias `_restore_{collection}`
4. **Swap atómico**: `drop()` coleção real + `rename()` temporária (cada rename é atómico no MongoDB)
5. **Recriar índices**: 16 coleções com índices únicos (`users.email`, `users.id`, `clients.id`, `processes.id`, etc.)
6. **Limpeza**: temporárias órfãs (não swapped) são removidas
7. **Retorno**: estatísticas detalhadas (collections_swapped, total_documents, indexes_created, errors, warnings)

### Técnico
- **Backend** (`backend/routes/backup.py`): endpoint `POST /restore` (linhas 491-839); constantes `_RESTORE_IGNORE_COLLECTIONS` e `_INDEX_DEFINITIONS` (16 coleções); validação de confirmação; swap atómico com `drop()` + `rename()`.
- **Validação**: `py_compile` ✓; `flake8 --select=E9,F63,F7,F82` → 0 erros.

## [2026-07-16] — Pacote CC: Changelog Generation with Date/Time Diff

### Alterado
- **Geração de changelog por IA processa apenas novidades desde a última geração**: Antes, a IA processava sempre as últimas 50 linhas da fonte (git/worklog/CHANGELOG), mesmo que já tivessem sido cobertas numa geração anterior. Agora, antes de ler a fonte, o sistema faz query à coleção `system_changelogs` para obter a data (`published_at`) do último changelog gerado, e filtra apenas as entradas posteriores a essa data.

### Backend (`backend/services/changelog_service.py`)
- **`_get_last_changelog_date()`**: Nova função async. Query à coleção `system_changelogs` para obter `published_at` do último registo. Lida com `datetime` e `string ISO`. Retorna `None` se não houver registo anterior.
- **`_parse_md_date(line)`**: Extrai `datetime` de headers Markdown. Suporta 3 padrões: `## [YYYY-MM-DD]`, `### Date: YYYY-MM-DD`, `## YYYY-MM-DD`.
- **`_filter_lines_since(lines, since_date, max_lines)`**: Heurística de filtragem. Percorre linhas do FIM para o INÍCIO. Quando encontra um header com data `<= since_date`, para. Se `since_date=None` ou não houver datas, usa `max_lines` como fallback (comportamento original).
- **`read_git_log(max_lines, since_date)`**: Se `since_date` fornecido, usa `--since="YYYY-MM-DDTHH:MM:SS"` em vez de `--max-count=N`.
- **`_read_local_file_tail(filepath, max_lines, since_date)`**: Chama `_filter_lines_since` em vez de ler as últimas N linhas diretamente.
- **`_fetch_from_github(filename, max_lines, since_date)`**: Busca o ficheiro completo do GitHub e aplica `_filter_lines_since`.
- **`read_changelog_file` / `read_worklog_file`**: Aceitam `since_date` e passam às funções subordinadas.
- **`generate_changelog_ai`**: Chama `_get_last_changelog_date()` antes de ler a fonte. Passa `since_date` a todas as chamadas de leitura. Log informativo sobre a data de filtragem.

### Lógica de Filtragem por Data
| Fonte | Método de Filtragem | Fallback |
|-------|---------------------|----------|
| Git | `git log --since="{data}"` | `--max-count={N}` se `since_date=None` |
| CHANGELOG.md | Parsing de `## [YYYY-MM-DD]` headers, do FIM para o INÍCIO | Últimas N linhas |
| worklog.md | Parsing de `### Date: YYYY-MM-DD` headers, do FIM para o INÍCIO | Últimas N linhas |

### Técnico
- **Backend** (`backend/services/changelog_service.py`): `_get_last_changelog_date` (linhas 57-85); `_parse_md_date` (linhas 101-110); `_filter_lines_since` (linhas 113-148); `read_git_log` com `--since` (linhas 324-354); `_read_local_file_tail` com `since_date` (linhas 278-286); `_fetch_from_github` com `since_date` (linhas 289-321); `read_changelog_file` / `read_worklog_file` com `since_date` (linhas 357-404); `generate_changelog_ai` com `_get_last_changelog_date` (linhas 447-457).
- **Validação**: `py_compile` ✓; `flake8 --select=E9,F63,F7,F82` → 0 erros.

## [2026-07-16] — Pacote CB: Fix Portal Profile Lock & Hide Visits Tab

### Corrigido
- **Perfil bloqueado prematuramente em pré-registo**: O perfil do cliente era bloqueado assim que o processo era criado em `pre_registo`, antes do cliente ter oportunidade de preencher os dados. Corrigido: o bloqueio (`has_process=True`) agora só acontece quando o processo ativo tem `status != "pre_registo"` OU `is_data_confirmed == True`. Em `pre_registo`, o cliente pode editar o perfil livremente.

### Backend (`backend/routes/portal.py`)
- **`GET /portal/me`**: Query agora projeta `status` além de `is_data_confirmed`. `has_process = (proc_status != "pre_registo") or proc_confirmed`.
- **`PUT /portal/me`**: Mesma regra — `should_lock = (proc_status != "pre_registo") or proc_confirmed`. Só lança 403 se `should_lock` for True. Mensagens mantidas: "Os seus dados encontram-se bloqueados..." (is_data_confirmed) vs "Dados trancados. Processo já em análise." (saiu do pre_registo).

### Frontend (`frontend/src/pages/ClientPortal.jsx`)
- **`isLocked`**: Sem alteração necessária — `profile?.has_process === true || isDataConfirmed` já funciona corretamente com a nova lógica do backend.
- **Botão "As Minhas Visitas"**: Temporariamente comentado (JSX comment). O código da Tab `visitas` mantém-se intacto para reativação futura.

### Técnico
- **Backend** (`backend/routes/portal.py`): `GET /portal/me` (linhas 757-780); `PUT /portal/me` (linhas 853-880).
- **Frontend** (`frontend/src/pages/ClientPortal.jsx`): botão Visitas comentado (linhas 2469-2488).
- **Validação**: `py_compile` ✓; `flake8 --select=E9,F63,F7,F82` → 0 erros; `esbuild --loader=jsx` → 0 erros.

## [2026-07-16] — Pacote CA: Persist Table Filters in URL Params

### Corrigido
- **Filtros perdidos ao navegar para detalhes e Voltar**: Quando o utilizador entrava nos detalhes de um processo e clicava em "Voltar", perdia todos os filtros e a página atual. Corrigido: o estado de filtragem e paginação foi migrado de `useState` para `useSearchParams` (URL params), permitindo que a navegação Back/Forward do browser restaure exatamente a vista pretendida.

### Frontend (`frontend/src/pages/FilteredProcessList.js`)
- **`searchTerm`**: Migrado de `useState("")` para `searchParams.get("search") || ""` (lido do URL).
- **`handleSearchChange(value)`**: Novo handler que usa `setSearchParams` para escrever/remover `search` no URL em tempo real (`replace: true` para não poluir o histórico).
- **Input de pesquisa**: `onChange` agora usa `handleSearchChange` em vez de `setSearchTerm`.
- **`setSearchParams`**: Obtido de `useSearchParams()` (antes era apenas `[searchParams]`, agora `[searchParams, setSearchParams]`).

### Frontend (`frontend/src/pages/ProcessesPage.js`)
- **`indexStatusFilter`**: Migrado de `useState` para `searchParams.get("index_status") || (default do role)`. Default: `'pending'` para indexacao, `'all'` para os restantes.
- **`setIndexStatusFilter`**: Reescrito como `useCallback` que usa `setSearchParams` para escrever/remover `index_status` no URL (`replace: true`).
- **Já estava no URL** (confirmado, sem alteração): `page`, `size`, `view_mode`, `sort`, `order`, `search`.

### Estados persistidos no URL

| Filtro | FilteredProcessList | ProcessesPage |
|--------|-------------------|---------------|
| `search` | ✅ **NOVO** (Pacote CA) | ✅ Já existia |
| `filter` | ✅ Já existia | N/A |
| `view_mode` | ✅ Derivado do `filter` (Pacote BT) | ✅ Já existia |
| `page` | N/A (size: 100 fixo) | ✅ Já existia |
| `size` | N/A | ✅ Já existia |
| `sort` / `order` | N/A | ✅ Já existia |
| `index_status` | N/A | ✅ **NOVO** (Pacote CA) |

### Técnico
- **Frontend** (`frontend/src/pages/FilteredProcessList.js`): `searchTerm` do URL (linha 154); `handleSearchChange` (linhas 157-166); `setSearchParams` (linha 146); `onChange` do input (linha 373).
- **Frontend** (`frontend/src/pages/ProcessesPage.js`): `indexStatusFilter` do URL (linhas 103-117); `setIndexStatusFilter` como `useCallback` (linhas 108-117).
- **Validação**: `esbuild --loader=jsx` → 0 erros nos 2 ficheiros.

## [2026-07-16] — Pacote BZ: Fix Local Filtering causing Uneven Pagination

### Corrigido
- **Tamanhos de página irregulares ao usar filtros**: A tabela de processos apresentava tamanhos de página irregulares porque o Frontend fazia paginação cega e filtrava os resultados localmente com `.filter()`. Corrigido: TODOS os filtros ativos no ecrã (status, search, view_mode, is_indexed) são agora passados como Query Parameters reais ao Backend, que faz a filtragem globalmente e devolve apenas os processos correspondentes.

### Backend (`backend/routes/processes.py`)
- **`GET /processes`**: Novo parâmetro `is_indexed: Optional[bool] = Query(None)`. Quando `true`, filtra `{is_indexed: True}`; quando `false`, filtra processos pendentes (`$or: [{is_indexed: {$ne: True}}, {is_indexed: {$exists: False}}]` — inclui null/undefined para processos antigos sem o campo).

### Frontend (`frontend/src/pages/FilteredProcessList.js`)
- **`fetchData`**: Agora passa `search` (>= 2 chars) e `status` (mapeado do `filterType`: `concluded`→`concluidos`, `dropped`→`desistencias`, `waiting`→`clientes_espera`) como query params.
- **`useEffect`**: Agora depende de `searchTerm` (para que a pesquisa dispare um novo fetch à API em vez de filtrar localmente).
- **`getFilteredProcesses`**: Removidas as `.filter()` locais de `config.filter` e `searchTerm`. Apenas mantém filtragem de `pending_deadlines` (cruzamento com deadlines — exceção legítima, não há endpoint de backend) e ordenação por prioridade (apresentação, não afeta tamanho da página).

### Frontend (`frontend/src/pages/ProcessesPage.js`)
- **`fetchProcesses`**: Agora passa `is_indexed` como query param (`indexStatusFilter='completed'` → `is_indexed=true`; `'pending'` → `is_indexed=false`; `'all'` → não envia).
- **`fetchProcesses` dependency**: Adicionado `indexStatusFilter` ao array de dependências.
- **`useEffect` de sorting**: Removido o `.filter()` local de `indexStatusFilter`. Agora apenas ordena (não filtra). O backend filtra via `is_indexed` query param.

### Técnico
- **Backend** (`backend/routes/processes.py`): parâmetro `is_indexed` (linha 1382); condição no `and_conditions` (linhas 1524-1534).
- **Frontend** (`frontend/src/pages/FilteredProcessList.js`): `search` e `status` como query params (linhas 172-188); `useEffect` depende de `searchTerm` (linha 161); `.filter()` locais removidos (linhas 203-225).
- **Frontend** (`frontend/src/pages/ProcessesPage.js`): `is_indexed` como query param (linhas 303-306); dependency array (linha 337); `.filter()` local removido (linhas 412-424).
- **Validação**: `py_compile` ✓; `flake8 --select=E9,F63,F7,F82` → 0 erros; `esbuild --loader=jsx` → 0 erros.

## [2026-07-16] — Pacote BY: The Ultimate QA Seed Script

### Adicionado
- **Script de seeding definitivo para QA** (`backend/scripts/seed_qa_ultimate.py`, 870 linhas): Gera 18 processos (configurável) com dados 100% realistas e todos os campos preenchidos, cobrindo as 5 regras de negócio:
  1. **4 processos em pré-registo**: Cliente minimalista (apenas nome/email/telefone), `dados_pessoais` vazio, `registration_completed=False`, `lead_status="new"`.
  2. **Diversidade de titulares**: ~25% dos processos ativos são casais com `titular2_data` exaustivo (nome, nif, email, telefone, rendimentos, profissão) e `co_buyers` array preenchido.
  3. **Dados 100% preenchidos**: 8+ processos ativos (em `documentacao`, `analise`, `pre_aprovacao`, `credito_aprovado`, `cpcv`, `escritura`) com `personal_data`, `financial_data` (salário bruto/líquido, despesas, capital próprio, tipo_contrato), `real_estate_data` (morada, valor, tipologia, CPCV, link idealista), e `credit_data` (montante, prazo, spread, euribor, prestação mensal calculada por fórmula de amortização francesa).
  4. **Histórico e notas**: 2-4 atividades/notas por processo ativo (10 notas realistas) + 1 entrada de histórico (status change).
  5. **Atribuições mistas**: Processos atribuídos a consultores, intermediários e indexadores aleatoriamente.

### Funcionalidades do script
- **CLI**: `--clear` (limpeza seletiva de seeds anteriores via `_seed_script`), `--num-processes` (customizar quantidade), `--dry-run` (simulação sem escrever).
- **Workflow statuses**: Garante os 16 estados canónicos do `ProcessStatus` (alinhados com o enum, não com os 7 antigos do `seed_massive_dev_data.py`).
- **Utilizadores dummy**: Cria 2 utilizadores por role (consultor, indexacao, intermediario) se não existirem.
- **NIF válido**: Gera NIFs portugueses com dígito de controlo validado.
- **Faker pt_PT**: Nomes, empresas, moradas e datas realistas em português.

### Uso
```bash
cd backend
python scripts/seed_qa_ultimate.py                    # seed com defaults (18 processos)
python scripts/seed_qa_ultimate.py --clear            # limpar dados seed anteriores
python scripts/seed_qa_ultimate.py --num-processes 25 # customizar quantidade
python scripts/seed_qa_ultimate.py --dry-run          # simular sem escrever
```

### Técnico
- **Backend** (`backend/scripts/seed_qa_ultimate.py`): 870 linhas; bootstrap com Motor async + dotenv + Faker('pt_PT'); catálogos estáticos (nomes, profissões, bancos, concelhos); 10 geradores de dados (cliente, personal_data, financial_data, real_estate_data, credit_data, titular2_data, co_buyer, atividade, historico); `ensure_workflow_statuses` (16 estados); `resolve_users` (cria dummies); `clear_seed_data` (limpeza seletiva); `run_seed` (orquestração).
- **Validação**: `py_compile` ✓; `flake8 --select=E9,F63,F7,F82` → 0 erros.

## [2026-07-16] — Pacote BX: Resize Pipeline Funnel

### Alterado
- **Funil do Pipeline mais compacto no AdminDashboard**: O gráfico de funil (`SafeChartContainer`) foi reduzido de `h-[280px]` para `h-[224px]` (h-56). Padding do `CardHeader` (`pb-2`) e `CardContent` (`pb-3`) também reduzido. `CardDescription` com `text-xs`. Margens internas do `BarChart` ajustadas (`top: 5, bottom: 5`). Poupança total: ~56px de altura vertical.

- **Gráficos do StatisticsPage mais compactos**: Os 5 gráficos (`SafeChartContainer` com `h-[300px]`) foram reduzidos para `h-[260px]` (h-64). Aplicado a: funil de leads, funil de vendas, e 3 gráficos de status. Poupança: 40px por gráfico × 5 = 200px total.

### Classes Tailwind ajustadas
| Ficheiro | Elemento | Antes | Depois |
|----------|----------|-------|--------|
| `AdminDashboard.js` | `SafeChartContainer` | `h-[280px]` | `h-[224px]` |
| `AdminDashboard.js` | Empty state div | `h-[280px]` | `h-[224px]` |
| `AdminDashboard.js` | `CardHeader` | (default) | `pb-2` |
| `AdminDashboard.js` | `CardDescription` | (default) | `text-xs` |
| `AdminDashboard.js` | `CardContent` | (default) | `pb-3` |
| `AdminDashboard.js` | `BarChart` margin | `{ left: 20, right: 20 }` | `{ left: 20, right: 20, top: 5, bottom: 5 }` |
| `StatisticsPage.js` | 5× `SafeChartContainer` | `h-[300px]` | `h-[260px]` |

### Técnico
- **Frontend** (`frontend/src/pages/AdminDashboard.js`): Funil do Pipeline (linhas 368-405).
- **Frontend** (`frontend/src/pages/StatisticsPage.js`): 5 gráficos com `h-[300px]` → `h-[260px]` (substituição global).
- **Validação**: `esbuild --loader=jsx` → 0 erros nos 2 ficheiros.

## [2026-07-16] — Pacote BV: Fix Checklists, RGPD empty state, Backups Date

### Corrigido
- **Checklist de Documentos não refletia alterações**: Quando o utilizador guardava/marcava/removia documentos nos pedidos do portal, a notificação de sucesso aparecia mas os documentos não ficavam refletidos na checklist/painel de documentos. Causa: `PortalDocumentRequests` fazia `fetchDocuments()` (state local) mas não notificava o `UnifiedDocumentsPanel` (componente irmão) para refrescar. Corrigido: adicionado prop `onDocumentsChange` ao `PortalDocumentRequests`, chamado após cada mutação bem-sucedida. No `ProcessDetails.js`, passado `onDocumentsChange={() => setDocumentsRefreshKey(k => k + 1)}` — incrementa a key e força o `UnifiedDocumentsPanel` a remontar e refazer fetch.

- **RGPD página vazia (BUG CRÍTICO)**: A página de Compliance > RGPD estava sempre vazia para todos os utilizadores. Causa raiz: `const accessDenied = <AccessRestricted .../>; if (accessDenied) {...}` — `accessDenied` é um elemento JSX (objeto React), que é **sempre truthy**. A página retornava **sempre** `<AccessRestricted/>` e nunca mostrava o conteúdo. Para admin/ceo/administrativo, `AccessRestricted` retorna `null` → página vazia. Corrigido: substituído por `if (!hasAnyRole(user, RGPD_ALLOWED_ROLES))` (boolean real). Roles alinhados com `ProtectedRoute` do App.js: `["admin", "ceo", "administrativo"]` (antes era `["admin", "staff"]` — "staff" não é um role do sistema).

- **Backups datas não formatavam (apareciam '-')**: As datas em `BackupsPage.js` apareciam como `-` em vez de `dd/MM/yyyy HH:mm`. Causa raiz: `formatDateTime` e `formatDate` em `lib/utils.js` usavam `safeDate` → `safeDateStr` que convertia dashes→slashes mas mantinha o `T` do ISO 8601. Para input `"2025-01-15T14:30:00+00:00"`, produzia `"2025/01/15T14:30:00+00:00"` que é `Invalid Date` em V8/SpiderMonkey → `formatDateTime` retornava `"-"`. Corrigido: `formatDateTime` e `formatDate` agora usam `safeParseISO` (que tenta `parseISO` do date-fns primeiro — lida corretamente com ISO 8601 com `T`). Correção é **global** — afecta todas as páginas que usam `formatDateTime`/`formatDate`, não só BackupsPage.

### Técnico
- **Frontend** (`frontend/src/components/PortalDocumentRequests.js`): prop `onDocumentsChange` (linha 105); 4 chamadas `if (onDocumentsChange) onDocumentsChange()` após mutações (linhas 167, 182, 197, 213).
- **Frontend** (`frontend/src/pages/ProcessDetails.js`): `onDocumentsChange={() => setDocumentsRefreshKey(k => k + 1)}` (linhas 5025-5028).
- **Frontend** (`frontend/src/pages/RGPDAdminPage.js`): substituição do bug `if (accessDenied)` por `if (!hasAnyRole(user, RGPD_ALLOWED_ROLES))` (linhas 1254-1266).
- **Frontend** (`frontend/src/lib/utils.js`): `formatDate` e `formatDateTime` usam `safeParseISO` em vez de `safeDate` (linhas 114-158).
- **Validação**: `esbuild --loader=jsx` → 0 erros nos 4 ficheiros.

## [2026-07-16] — Pacote BU: UI Cleanup (Menus, Emails, Automations)

### Alterado
- **Menus temporariamente ocultos**: Os links de navegação para Minutas, Imóveis, Visitas e Gestão Financeira foram comentados na sidebar do `DashboardLayout.js`. As rotas continuam acessíveis via URL directa — apenas os links na sidebar estão ocultos. Aplicado em 3 grupos: `meuNegocioGroup`, `comunicacoesGroup`, e `consultorNegocioItems`.

- **Select de fases filtra workflows ativos**: No `AutomationPage.js`, o Select do bloco SE (gatilho de automação) agora filtra com `.filter(s => s.is_active !== false)` para mostrar apenas fases ativas. Estados inativos (concluídos, desistências — com `is_active: false` configurado via Pacote BS) não aparecem como gatilho. Usa `!== false` para retrocompatibilidade (estados sem a flag continuam a aparecer).

### UI Emails do Sistema (`SystemConfigPage.js`)
- **Google OAuth — Switch toggle**: Adicionado `<Switch>` no CardHeader de cada cartão de "Contas Partilhadas por Departamento". O Switch reflete o estado do Google OAuth: ligado = conectado, desligado = desconectado. `onCheckedChange`: ligar → `handleGoogleAuth(role)` (inicia OAuth); desligar → `handleDisconnect(role)`. Card com `opacity-75` quando não conectado. `data-testid` para testes.

- **IMAP Recepção — tamanho reduzido**: Bloco C enxutado: `CardHeader pb-4→pb-3`, `CardContent space-y-4→space-y-3`, `gap-4→gap-3`, `space-y-2→space-y-1`. Removida `CardDescription`, wrapper decorativo do ícone, `<p>` da App Password, e `pt-2` do botão. Título encurtado.

- **SMTP Transacional — editável com Lápis**: Novo estado `smtpEditMode` (false por defeito). Botão Lápis (`<Pencil>`) no CardHeader alterna o modo de edição. 3 inputs (Resend API Key, From Email, From Name) e botão Guardar têm `disabled={!smtpEditMode}`. Os dados continuam a ser carregados da BD — apenas a edição está bloqueada por defeito. Ícone `Pencil` já estava importado.

### Técnico
- **Frontend** (`frontend/src/layouts/DashboardLayout.js`): 4 itens comentados em 3 grupos (linhas 283-286, 324-325, 415-418).
- **Frontend** (`frontend/src/pages/AutomationPage.js`): `.filter(s => s.is_active !== false)` no Select de fases (linha 416).
- **Frontend** (`frontend/src/pages/SystemConfigPage.js`): estado `smtpEditMode` (linha 475); Pencil button (linhas 638-647); inputs `disabled={!smtpEditMode}` (linhas 662, 669, 676); Save `disabled` (linha 722); IMAP reduzido (linhas 845-890); Google OAuth Switch (linhas 1074-1098).
- **Validação**: `esbuild --loader=jsx` → 0 erros nos 3 ficheiros.

## [2026-07-16] — Pacote BT: Fix Process List (Badges, Active Filter, Real Notes)

### Corrigido
- **Bolinhas de Notificação não apareciam**: As badges `has_unread_messages` (azul) e `has_new_documents` (verde) não estavam a renderizar na tabela de processos. Causa: as flags podiam chegar como `undefined` (em vez de `false`) quando o backend não as injetava, causando comportamento inesperado na verificação. Corrigido com coerção booleana explícita `Boolean()` no componente `NotificationDots`.

- **Filtro Inativos não funcionava**: Os processos inativos apareciam mesmo com o filtro 'Ativos' ligado. Causa: `fetchData` passava sempre `view_mode='all'` em vez de `'active_only'`. Corrigido com `view_mode` dinâmico conforme o `filterType`: `'active_only'` para filtros de processos em curso; `'historical'` para `concluded`/`dropped`. O backend já respeita `view_mode=active_only` (exclui `INACTIVE_STATUSES`).

- **Notas não liam dados corretos**: A coluna de notas lia `process.notes` (campo direto do processo), não a última nota real do histórico/atividades. Corrigido: o backend agora projeta a última atividade/comentário da coleção `activities` para o campo `latest_note` (batch enrichment com aggregation `$match + $sort + $group`); o frontend lê `latest_note` com fallback para `process.notes`.

### Backend (`backend/routes/processes.py`)
- **`GET /processes`**: Adicionado batch enrichment `latest_note` (linhas 1733-1770). Após paginação, aggregation na coleção `activities` busca o comentário mais recente de cada processo (`$match` por `process_id` + `comment` não vazio; `$sort` por `created_at` descendente; `$group` com `$first`). Injeta `latest_note`, `latest_note_at`, `latest_note_by` em cada processo.

### Frontend (`frontend/src/pages/FilteredProcessList.js`)
- **`NotificationDots`**: Coerção booleana explícita `Boolean(hasUnreadMessages)` / `Boolean(hasNewDocuments)` — `undefined`/`null`/`0`/`""` são tratados como `false` de forma determinística.
- **`fetchData`**: `view_mode` dinâmico — `HISTORICAL_FILTERS = ["concluded", "dropped"]` → `'historical'`; todos os outros filtros → `'active_only'`. Antes era sempre `'all'`.
- **Coluna "Notas do Consultor"**: Lê `process.latest_note || process.notes || ""` (IIFE para lógica limpa). Fallback para `process.notes` mantém retrocompatibilidade.

### Técnico
- **Backend** (`backend/routes/processes.py`): batch enrichment `latest_note` no `GET /processes` (linhas 1733-1770).
- **Frontend** (`frontend/src/pages/FilteredProcessList.js`): `NotificationDots` com `Boolean()` (linhas 38-41); `fetchData` com `view_mode` dinâmico (linhas 158-165); coluna notas lê `latest_note` (linhas 518-534).
- **Validação**: `py_compile` ✓; `flake8 --select=E9,F63,F7,F82` → 0 erros; `esbuild --loader=jsx` → 0 erros.

## [2026-07-16] — Pacote BS: Workflow Status Rules UI (Frontend)

### Adicionado
- **Secção "Automações e Gatilhos do Sistema" no WorkflowEditor**: O admin pode agora configurar visualmente as flags de comportamento de cada fase do workflow, completando o circuito iniciado no Pacote BR (dynamic flags no backend). 4 Switches controlam: `is_active`, `trigger_finance`, `trigger_countdown`, `trigger_deed_reminder`.

### Backend (necessário para persistir as flags)
- **`models/workflow.py`**: Adicionadas 5 flags `Optional[bool] = None` aos modelos `WorkflowStatusCreate`, `WorkflowStatusUpdate`, `WorkflowStatusResponse`: `is_active`, `trigger_finance`, `trigger_countdown`, `trigger_property_check`, `trigger_deed_reminder`. `None` = não configurado (fallback ativo no `move_process_kanban` do Pacote BR).
- **`routes/admin.py`**:
  - `create_workflow_status`: `status_doc` agora inclui as 5 flags (persistidas como `None` se não fornecidas).
  - `update_workflow_status`: `update_data` agora inclui as 5 flags (apenas se `data.flag is not None` — atualização parcial).

### Frontend (`frontend/src/components/WorkflowEditor.js`)
- **`formData` inicial**: Adicionadas as 5 flags (default `null` = fallback).
- **`handleCreateStatus`**: Payload inclui as 5 flags.
- **`handleEditStatus`**: Payload inclui as 5 flags.
- **`openEditDialog`**: Lê as flags do status existente (`status.flag ?? null`).
- **`resetForm`**: Reset flags a `null`.
- **`renderAutomationTriggersSection(prefix)`**: Nova função reutilizável que renderiza a secção "Automações e Gatilhos do Sistema" com 4 Switches (cada um com Label, ícone lucide, descrição e `data-testid`). Inserida em ambos os Diálogos (Criar e Editar) antes do `DialogFooter`.
- **Imports adicionados**: `Activity`, `DollarSign`, `Clock`, `CalendarClock` (lucide-react).

### As 4 Switches
| Switch | Flag | Ícone | Descrição |
|--------|------|-------|-----------|
| Considerar processo Ativo nesta fase | `is_active` | `Activity` (emerald) | Se desligado, o processo fica inativo (sai dos dashboards ativos e liberta slot do indexador) |
| Disparar fecho financeiro e comissões | `trigger_finance` | `DollarSign` (green) | Cria snapshot financeiro (ProcessFinance) ao entrar nesta fase |
| Iniciar contagem decrescente de 90 dias | `trigger_countdown` | `Clock` (blue) | Regista a data de aprovação bancária e inicia o countdown de 90 dias |
| Ativar lembrete de agendamento de escritura | `trigger_deed_reminder` | `CalendarClock` (purple) | Cria lembrete automático 15 dias antes da data da escritura |

### Decisão de UX
- **`checked={formData.flag === true}`**: O switch só aparece ligado quando a flag é `true`. `null` (não configurado) e `false` (explicitamente desligado) aparecem visualmente como desligados. Quando o admin clica pela primeira vez, `null`→`true`; se clicar again, `true`→`false` (explicitamente desligado, override do fallback). O backend distingue `null` (fallback ativo) de `false` (override), pelo que o comportamento é correto.
- **`trigger_property_check` sem switch dedicado**: No backend, esta flag cobre `ch_aprovado`/`fase_escritura`/`escritura_agendada` (verificação de docs do imóvel + alerta CPCV). É uma flag composta que não mapeia 1:1 para uma switch única — optei por não expô-la na UI para evitar confusão. Fica no payload para configuração avançada via API se necessário no futuro.

### Técnico
- **Backend** (`backend/models/workflow.py`): 5 flags `Optional[bool] = None` em Create/Update/Response.
- **Backend** (`backend/routes/admin.py`): persistir flags em `create_workflow_status` (linhas 440-446) e `update_workflow_status` (linhas 489-499).
- **Frontend** (`frontend/src/components/WorkflowEditor.js`): formData (linhas 70-76); payload create (linhas 112-117); payload edit (linhas 143-148); openEditDialog (linhas 218-223); resetForm (linhas 241-246); `renderAutomationTriggersSection` (linhas 256-356); inserção nos Diálogos Criar (linha 585) e Editar (linha 703); imports (linhas 37-40).
- **Validação**: `py_compile` ✓; `flake8 --select=E9,F63,F7,F82` → 0 erros; `esbuild --loader=jsx` → 0 erros.

## [2026-07-16] — Pacote BR: Dynamic Workflow Purpose Flags (Backend)

### Alterado
- **Gatilhos do Kanban agora lêem flags dinâmicas do `workflow_statuses`**: A função `move_process_kanban` (processes.py) deixou de usar strings hardcoded (`new_status == "concluidos"`, `new_status == "fase_bancaria"`, etc.) e passou a ler flags de comportamento configuradas na coleção `workflow_statuses`. O admin pode configurar quais estados disparam cada automação sem alterar código.

### Flags Dinâmicas (PACOTE BR)
- **`trigger_finance`**: cria snapshot financeiro (era: `new_status == "concluidos"`)
- **`trigger_countdown`**: inicia countdown de 90 dias (era: `new_status == "fase_bancaria"`)
- **`trigger_property_check`**: verifica docs do imóvel + alerta CPCV/Escritura (era: `new_status in ["ch_aprovado", "fase_escritura", "escritura_agendada"]`)
- **`trigger_deed_reminder`**: cria lembrete 15 dias antes da escritura (era: `new_status == "escritura_agendada"`)
- **`is_active`**: determina se o processo fica ativo ou inativo (era: `new_status not in ["desistencias", "concluidos"]`)

### Fallback Retrocompatível
- Se a flag não existir no documento `workflow_statuses` (instalações existentes que ainda não migraram), o comportamento hardcoded atual é usado como fallback. Isto garante que nada quebra — à medida que o admin configura as flags, o fallback deixa de ser usado. Ex: `trigger_finance = status_exists.get("trigger_finance")`; se `None`, fallback para `new_status == "concluidos"`.

### Gatilho de Fila de Espera Dinâmico
- O gatilho de fila de espera (libertar slot do indexador) agora dispara em **qualquer estado inativo** (`is_active == False`), não apenas em `["concluidos", "desistencias"]`. Isto é mais correto: se o admin configurar um novo estado terminal com `is_active: False`, o gatilho dispara automaticamente.

### Decisão de Arquitetura
- **Fallback em vez de migração forçada**: As flags não existem ainda no modelo `workflow_statuses` (o seed só define name, label, order, color, is_default, visible_in_portal, portal_label, description). Em vez de forçar uma migração da BD, usei fallback retrocompatível — o sistema funciona imediatamente e à medida que o admin configura as flags (futuro, via WorkflowEditor), o fallback deixa de ser usado.
- **`trigger_countdown and old_status != new_status`**: O countdown original tinha `old_status != "fase_bancaria"` para não disparar se o processo já estava em fase_bancaria. Generalizei para `old_status != new_status` — não disparar se o processo já estava no estado (independente do nome).
- **`trigger_property_check` funde 2 blocos**: Os blocos `if new_status in ["ch_aprovado", "fase_escritura"]` (property check) e `if new_status in ["ch_aprovado", "fase_escritura", "escritura_agendada"]` (CPCV alert) cobriam os mesmos 3 statuses. Fundi-os num só `if trigger_property_check` que faz ambas as verificações.
- **Próximo passo (futuro)**: Expor estas flags no `WorkflowEditor` do frontend para o admin as configurar visualmente.

### Técnico
- **Backend** (`backend/routes/processes.py`): bloco PACOTE BR com leitura das 5 flags + fallback (linhas 2926-2974); substituição dos 5 blocos de gatilhos hardcoded por flags dinâmicas (linhas 3021-3086); gatilho de fila de espera dinâmico `if not is_active` (linhas 3111-3129); remoção da lista fixa `inactive_statuses`.
- **Validação**: `py_compile` ✓; `flake8 --select=E9,F63,F7,F82` → 0 erros.

## [2026-07-16] — Pacote BQ: Acesso Global para a Role de Indexação

### Corrigido
- **Indexacao via literalmente todos os processos no Kanban**: O frontend envia sempre `show_all=true`, e o backend com `show_all=true` não aplicava base filter — indexacao via processos não relevantes para o seu trabalho (ex: processos de outros consultores já atribuídos a outros indexadores). Agora indexacao vê globalmente (across all consultors/mediadores) mas scoped a: (a) processos atribuídos a si (`assigned_indexacao_id == user_id`) OU (b) processos na fila de espera (`status == "fila_espera"`).

### Backend (`backend/routes/processes.py`)
- **`GET /kanban`**: Adicionado bloco PACOTE BQ que aplica o scope para indexacao ANTES do `elif not show_all`. Como é um `if role == UserRole.INDEXACAO` (não `elif`), o scope aplica-se sempre, mesmo com `show_all=true`. Scope: `$or: [assigned_indexacao_id == user_id, status == "fila_espera"]`.
- **`GET /processes`**: Adicionado `{"status": "fila_espera"}` ao `$or` do indexacao (que já tinha `assigned_indexacao_id` + `created_by`). Para consistência com o kanban.
- **`GET /processes/paginated`**: Mesma alteração que `GET /processes`.

### Frontend (`frontend/src/pages/KanbanPage.js`)
- **Verificação**: Os 5 filtros (Consultor, Intermediário, Indexação, Parceiro, Estado de Indexação) já eram renderizados incondicionalmente para todos os roles. Indexacao já via todos os botões de filtro. ✓
- **Verificação**: ProcessesPage `canMarkIndexed` já inclui indexacao, pelo que o "Filtro de Estado de Indexação" já aparecia. ✓
- **Verificação**: `indexStatusFilter` default é 'pending' para indexacao — mostra apenas não-indexados por defeito. ✓
- **Adicionado**: Badge visual teal no KanbanPage para indexacao: "Vista Indexação (atribuídos + fila de espera)" — comunica ao utilizador que está numa vista scoped. `data-testid="kanban-indexacao-scoped-badge"`.

### Decisão de Arquitetura
- **Scope sempre aplicado para indexacao**: O scope (atribuídos + fila_espera) aplica-se sempre, independentemente de `show_all`. Isto porque é o âmbito natural de trabalho da Indexação — não faz sentido indexacao ver processos de outros indexadores ou processos já atribuídos a outros. O `show_all` continua a funcionar para consultores/intermediarios (toggle entre vista pessoal e global).
- **Consistência entre Kanban e listagens**: O scope foi aplicado aos 3 endpoints de listagem (kanban, /processes, /paginated) para que indexacao encontre os mesmos processos em qualquer vista.
- **Filtros funcionam dentro do scope**: Os botões de filtro (Consultor, Intermediário, etc.) agora filtram DENTRO do scope do indexacao. Ex: indexacao pode filtrar por um consultor específico para ver apenas os processos desse consultor que estão atribuídos a si ou na fila.

### Técnico
- **Backend** (`backend/routes/processes.py`): kanban scope (linhas 2098-2116); GET /processes scope (linhas 1481-1488); GET /paginated scope (linhas 1807-1813).
- **Frontend** (`frontend/src/pages/KanbanPage.js`): badge visual para indexacao (linhas 221-229).
- **Validação**: `py_compile` ✓; `flake8 --select=E9,F63,F7,F82` → 0 erros; `esbuild --loader=jsx` → 0 erros.

## [2026-07-16] — Pacote BP: Fix Visibilidade do 2º Titular nas Listas

### Corrigido
- **2º titular não aparecia nas listagens globais**: Clientes que são apenas 2º titular num processo não apareciam em "Os Meus Clientes" / "Processos" se não tivessem um processo principal ativo. Causa raiz: o `process_ids` do 2º titular não era atualizado quando ele era associado como 2º titular, e o `client_ids` do processo não incluía o 2º titular.

### Backend (`backend/routes/processes.py`)
- **`POST /create-client`**: O campo `second_client_id` do `ProcessCreate` era **ignorado** na criação. Agora é lido, validado, injetado no `process_doc` (`second_client_id` + `second_client_name`), e o 2º titular é adicionado ao array `client_ids` do processo. Após a inserção, o `process_ids` do 2º titular é atualizado com `$addToSet`. O `lead_status` do 2º titular NÃO é alterado (pode continuar a ser lead pendente).
- **`PUT /processes/{id}` (update_process)**: Ao adicionar/remover `second_client_id`, agora sincroniza: (a) `client_ids` do processo — remove o 2º titular antigo (se diferente do novo) e adiciona o novo; (b) `process_ids` do 2º titular — `$pull` do antigo e `$addToSet` no novo. Isto garante que queries `{"client_ids": cliente_id}` apanham processos em que o cliente é 1º OU 2º titular.
- **`POST /{process_id}/remove-client`**: Se o cliente removido era o `second_client_id`, limpa `second_client_id`/`second_client_name` do processo para manter consistência (sem isto, o processo ficava com `second_client_id` apontando para um cliente que já não está associado). O `process_ids` do cliente já era removido com `$pull` (existente).

### Sem Alteração (já estava correto)
- **`POST /{process_id}/add-client`**: Já atualizava o `process_ids` do cliente adicionado (`$addToSet`) e o `client_ids` do processo. Sem alteração.
- **`GET /clients/{client_id}`**: Já procurava processos onde o cliente é `second_client_id` (lê diretamente o campo `second_client_id` do processo). Sem alteração.

### Decisão de Arquitetura
- **Sincronização bidirecional**: O `process_ids` do cliente e o `client_ids` do processo são mantidos em sincronia. Quando o 2º titular é adicionado, ambos os arrays são atualizados; quando é removido, ambos são limpos. Isto garante que qualquer query (por `client.process_ids` ou por `process.client_ids`) encontra a associação correta.
- **`lead_status` do 2º titular preservado**: O 2º titular pode continuar a ser um lead pendente (não tem processo próprio como 1º titular). Apenas o 1º titular tem `lead_status` alterado para "converted" na criação do processo.
- **`second_client_id` vs `co_buyers`**: O `second_client_id` é a ligação formal a um cliente existente (com ID na coleção clients). Os `co_buyers` são dados embutidos (dict com name/email/nif/phone) que podem ou não ter `client_id`. A sincronização do `process_ids` aplica-se ao `second_client_id`; os `co_buyers` com `client_id` são sincronizados via `add-client`/`remove-client`.

### Técnico
- **Backend** (`backend/routes/processes.py`): bloco PACOTE BP na criação (linhas 1119-1153 para injeção no process_doc, linhas 1248-1274 para atualização do process_ids do 2º titular); bloco `second_client_id` no PUT reescrito (linhas 4015-4095) com sincronização de client_ids e process_ids; bloco `remove-client` (linhas 5060-5066) com limpeza de second_client_id.
- **Validação**: `py_compile` ✓; `flake8 --select=E9,F63,F7,F82` → 0 erros.

## [2026-07-16] — Pacote BO: Auto-Avanço e Auto-Atribuição no Portal do Cliente

### Adicionado
- **Fecho do circuito de automação no Portal do Cliente**: Quando o cliente carrega os documentos obrigatórios e os submete via Portal, o sistema avança automaticamente o processo de `pre_registo` para o estado seguinte da pipeline e invoca `assign_to_indexer` para o processo cair logo na mesa do Indexador com menos carga. Isto elimina a intervenção manual necessária para tirar o processo do `pre_registo` após o cliente completar o onboarding.

### Backend (`backend/routes/portal.py`)
- **`_trigger_onboarding_check` (modificada)**: Após `check_onboarding_completion`, se onboarding completo (`completed=True`), chama `_auto_advance_from_pre_registo` para o processo recém-criado. Se não completo, chama `_check_and_advance_existing_pre_registo` para verificar processo existente em `pre_registo` (Flow 1 — processo criado pelo formulário público com docs ancorados diretamente).
- **`_check_and_advance_existing_pre_registo` (nova)**: Procura processo do cliente em `pre_registo`, verifica se tem todos os docs obrigatórios via `_has_all_required_documents`, e se sim avança.
- **`_has_all_required_documents` (nova)**: Reutiliza a lógica de validação do `onboarding_service` (`DOCUMENT_REQUIREMENT_MAP`, `REQUIREMENTS_BY_CONTRACT_TYPE`, `CONTRACT_TYPE_NORMALIZE`, `_detect_contract_type`) mas procura docs ancorados AO PROCESSO (com `process_id` definido) em vez de docs órfãos. Cobre o Flow 1 que o `check_onboarding_completion` não detecta.
- **`_auto_advance_from_pre_registo` (nova)**: (a) verifica que processo está em `pre_registo`; (b) calcula próximo estado da pipeline (salto dinâmico, como `mark-indexed`); (c) atualiza status com stealth system user; (d) invoca `assign_to_indexer(process_id)`.

### Silêncio no Histórico (Pacote BJ)
- O auto-avanço usa `stealth_system_user = {"id": "system", "name": "Sistema (Auto-avanço Portal)", "role": "system", "track_history": False}`. O `track_history: False` dispara o `_is_stealth_user` do Pacote BJ, que retorna `True`, e `log_history` retorna imediatamente sem escrever na coleção `history`. Isto garante que o auto-avanço **não gera ruído no histórico** do cliente.
- O `assign_to_indexer` gera os seus próprios logs internos (com `system_user role="admin"`) — esses são ações de sistema legítimas (atribuição de indexador), não do cliente, pelo que são mantidos no histórico.

### Decisão de Arquitetura
- **Dois fluxos cobertos**: Flow 1 (processo criado pelo formulário público em `pre_registo`, docs ancorados diretamente) e Flow 2 (processo criado pelo onboarding_service em `pre_registo`, docs órfãos completos). O `check_onboarding_completion` só detecta o Flow 2 (docs órfãos); o `_check_and_advance_existing_pre_registo` cobre o Flow 1.
- **Salto dinâmico**: O próximo estado é calculado a partir da pipeline `workflow_statuses` ordenada por `order` (mesma lógica do `mark-indexed`), não hardcoded. Isto garante que mudanças na configuração do workflow são respeitadas.
- **`assign_to_indexer` após avanço**: O processo avança primeiro para o estado seguinte (ex: `clientes_espera`), depois `assign_to_indexer` further routeia para `fase_documental` (com indexador) ou `fila_espera` (sem indexador disponível). Se `assign_to_indexer` falhar, o processo fica no estado intermédio (visível nos dashboards) mas sem indexador — o gatilho de fila de espera do `mark-indexed` pode recuperá-lo mais tarde.

### Técnico
- **Backend** (`backend/routes/portal.py`): `_trigger_onboarding_check` modificada (linhas 1791-1835); `_check_and_advance_existing_pre_registo` nova (linhas 1838-1875); `_has_all_required_documents` nova (linhas 1878-1931); `_auto_advance_from_pre_registo` nova (linhas 1934-2031).
- **Validação**: `py_compile` ✓; `flake8 --select=E9,F63,F7,F82` → 0 erros.

## [2026-07-16] — Pacote BN: Evolução do Menu de Registos (Triagem de Entrada)

### Adicionado
- **Sala de Triagem na página de Registos de Clientes**: A página de Registos agora funciona como "Sala de Triagem", mostrando 3 tipos de itens com badges visuais distintas:
  - **Leads pendentes** (sem processo) — Badge laranja "Sem Processo" (existente)
  - **Processos em pré-registo** (cliente ainda a preencher no Portal) — Badge âmbar "Pré-Registo (A preencher Portal)" (NOVO)
  - **Processos prontos para indexação** (sem `assigned_indexacao_id`, na fila de espera) — Badge azul "Pronto para Indexação (Na fila de espera)" (NOVO)

### Backend
- **`GET /clients/registered`** (`routes/clients.py`): Novo parâmetro `triage_mode` (opt-in, default `False`). Quando ativo:
  - Pré-calcula `triage_client_map` buscando processos com `status="pre_registo"` OU `assigned_indexacao_id in [None, ""]` (excluindo eliminados).
  - Alarga a query com `$or` entre "lead sem processo + lead_status pendente" e "cliente com id no triage_client_map".
  - Enriquece cada cliente com `triage_status` (`null` | `"pre_registo"` | `"ready_for_indexing"`).
  - Mantém os filtros existentes (ghost, search, assigned_to_me, cursor pagination).

### Frontend
- **`ClientRegistrationsPage.js`**:
  - `fetchClients` agora envia `triage_mode=true` por defeito (página funciona como Sala de Triagem).
  - Imports `FileInput` e `ClipboardList` adicionados ao lucide-react.
  - Coluna "Estado" com 4 ramos condicionais por prioridade: `pre_registo` → `ready_for_indexing` → `has_process` → `Sem Processo`. Cada badge tem `data-testid` para testes e mostra o `process_number` quando aplicável.

### Decisão de Arquitetura
- **`triage_mode` opt-in (default False)**: O parâmetro é opt-in para não afetar outros callers do endpoint `GET /clients/registered` (ex: ClientRegistrationsAdminPage, ExportClientes). A página de Registos ativa-o explicitamente; os outros callers mantêm o comportamento original (apenas leads pendentes).
- **Prioridade `pre_registo` > `ready_for_indexing`**: Um processo pode estar em `pre_registo` E sem `assigned_indexacao_id` simultaneamente. O `triage_client_map` dá prioridade ao `pre_registo` (estado anterior na pipeline), pelo que a badge âmbar tem precedência sobre a azul. Isto comunica ao utilizador o estágio mais inicial do processo.
- **`triage_status` calculado no backend**: O backend determina o `triage_status` durante o enriquecimento (não no frontend) para garantir consistência e permitir que outros callers (ex: futura API de exportação) usem o mesmo campo.

### Técnico
- **Backend** (`backend/routes/clients.py`): parâmetro `triage_mode` (linha 260); bloco de pré-cálculo de `triage_client_map` (linhas 295-337); bloco de filtro `$or` em triage_mode (linhas 427-452); enriquecimento com `triage_status` (linhas 558-601).
- **Frontend** (`frontend/src/pages/ClientRegistrationsPage.js`): `triage_mode=true` em fetchClients (linha 178); imports `FileInput`/`ClipboardList` (linhas 66-67); 4 ramos de badges na coluna Estado (linhas 502-553).
- **Validação**: `py_compile` ✓; `flake8 --select=E9,F63,F7,F82` → 0 erros; `esbuild --loader=jsx` → 0 erros.

## [2026-07-16] — Pacote BM: Bloqueio do Perfil do Cliente após Indexação

### Adicionado
- **Congelamento de dados do cliente após Indexação**: Quando a Indexação termina o tratamento documental e marca o processo como indexado (`mark-indexed`), o campo `is_data_confirmed: True` é persistido no processo. Isto assinala que os dados foram validados e congelados — o cliente já não pode alterar os seus dados pessoais no Portal.

- **Flag `is_data_confirmed` no `GET /portal/me`**: O Portal do Cliente lê agora esta flag para determinar se os campos do perfil devem ser desativados.

- **Alert específico no Portal do Cliente**: Quando `is_data_confirmed === true`, o `ProfilePanel` mostra um Alert âmbar (ícone `ShieldCheck`) no topo com a mensagem exata: "Os seus dados encontram-se bloqueados para análise da nossa equipa de crédito." — com `role="alert"` e `data-testid="data-confirmed-alert"` para acessibilidade/testes.

- **Defesa no backend (`PUT /portal/me`)**: Quando `is_data_confirmed === true`, o endpoint devolve HTTP 403 com a mesma mensagem específica. Isto garante que mesmo que o frontend seja manipulado, o backend bloqueia a edição.

### Backend
- **`PATCH/POST /processes/{id}/mark-indexed`** (`routes/processes.py`): `update_set` agora inclui `is_data_confirmed: True` + metadados (`data_confirmed_at`, `data_confirmed_by`, `data_confirmed_by_name`). Registo no histórico `DADOS_CONFIRMADOS_INDEXACAO`. Retorno inclui `is_data_confirmed: True`.
- **`GET /portal/me`** (`routes/portal.py`): Query de `active_process` agora projeta `is_data_confirmed`; resposta inclui `"is_data_confirmed": true|false`.
- **`PUT /portal/me`** (`routes/portal.py`): Quando `is_data_confirmed === true`, devolve 403 com mensagem "Os seus dados encontram-se bloqueados para análise da nossa equipa de crédito." (distinta do 403 genérico "Dados trancados. Processo já em análise." para o caso pré-indexação).

### Frontend
- **`ClientPortal.jsx` — `ProfilePanel`**:
  - Import `ShieldCheck` adicionado ao lucide-react.
  - `isDataConfirmed = profile?.is_data_confirmed === true` (lida do `GET /portal/me`).
  - `isLocked = profile?.has_process === true || isDataConfirmed` — bloqueio aplica-se em ambos os casos (pré e pós-indexação). Todos os campos `Field` já usavam `disabled={isLocked}`, pelo que ficam automaticamente desativados.
  - Alert âmbar (ícone `ShieldCheck`) com a mensagem exata pedida — renderizado quando `isDataConfirmed === true`.
  - Banner azul "Processo em Análise" existente agora só aparece quando `isLocked && !isDataConfirmed` (pré-indexação) — evita duplicação visual.

### Decisão de Arquitetura
- **Distinção `has_process` vs `is_data_confirmed`**: São dois estados distintos que merecem mensagens diferentes. `has_process` = cliente tem processo (bloqueio **pré-indexação**, banner azul "Processo em Análise", já existente). `is_data_confirmed` = Indexação validou e congelou os dados (bloqueio **pós-indexação**, Alert âmbar "Dados Bloqueados para Análise", novo). Ambos desativam os campos, mas a mensagem comunica ao cliente o estágio correto do processo.
- **Defesa em profundidade**: O bloqueio é aplicado no frontend (disabled + Alert) E no backend (403 no PUT /portal/me). Mesmo que o frontend seja manipulado, o backend impede a edição.
- **Metadados de auditoria**: `data_confirmed_at`, `data_confirmed_by`, `data_confirmed_by_name` permitem rastrear quem e quando congelou os dados.

### Técnico
- **Backend** (`backend/routes/processes.py`): `update_set` no `mark_process_indexed` (linhas 3282-3291); registo histórico `DADOS_CONFIRMADOS_INDEXACAO` (linhas 3322-3330); `is_data_confirmed: True` no retorno (linhas 3533-3535).
- **Backend** (`backend/routes/portal.py`): `GET /portal/me` projeta e devolve `is_data_confirmed` (linhas 760-772, 797-799); `PUT /portal/me` bloqueia com mensagem específica (linhas 845-865).
- **Frontend** (`frontend/src/pages/ClientPortal.jsx`): import `ShieldCheck` (linha 56); `isDataConfirmed` + `isLocked` estendido (linhas 1413-1418); Alert âmbar (linhas 1477-1502); banner azul condicionado a `!isDataConfirmed` (linha 1505).
- **Validação**: `py_compile` ✓; `flake8 --select=E9,F63,F7,F82` → 0 erros; `esbuild --loader=jsx` → 0 erros.

## [2026-07-16] — Pacote BL: Categoria INDEX forçada e privada

### Adicionado
- **Pasta cofre "Index" para documentos do cliente**: Todos os documentos enviados **diretamente** pelo cliente através do Portal recebem automaticamente `category="Index"`, ignorando qualquer categoria que venha do frontend do portal. Esta categoria é a "pasta cofre" tratada exclusivamente pela equipa de Indexação — os restantes roles não a veem no painel de documentos.

### Backend (forçar categoria)
- **`POST /portal/upload-url`** (`routes/portal.py`): Override da categoria para `"Index"` antes de gerar o `file_key` S3 — garante que a pasta S3 também seja "Index" (consistência com o registo da BD). Bloqueio de `PORTAL_HIDDEN_CATEGORIES` desativado (comentado) porque "Index" é exatamente a categoria a permitir.
- **`POST /portal/confirm-upload`** (`routes/portal.py`): Override da categoria para `"Index"` após ler o payload, antes do bloco de triagem IA. Isto desativa a triagem IA (que só corria para "Outros"/"Auto") — a categoria já está definida. A categoria original é preservada no log para auditoria. O `_create_document_record` e o `update_one` (para docs REQUESTED) usam a categoria forçada.

### Frontend (bloqueio de segurança)
- **`S3FileManager.js`** (filtro granular — onde os ficheiros são listados):
  - Constantes `INDEX_CATEGORY_ID = "Index"` e `INDEX_CATEGORY_ALLOWED_ROLES = ["admin", "ceo", "diretor", "indexacao"]`.
  - `canSeeIndexCategory = hasAnyRole(user, INDEX_CATEGORY_ALLOWED_ROLES)` — flag de permissão.
  - `visibleCategories` — `CATEGORIES` filtrado (exclui "Index" se sem permissão), usado em todos os 3 `CATEGORIES.map` da sidebar.
  - `getCategoryCount("Index")` retorna 0 se sem permissão.
  - `getAllFiles()` — skip da categoria "Index" ao agregar ficheiros se sem permissão.
  - `getFilteredCategoryFiles("Index")` retorna `[]` se sem permissão (defesa contra state/URL manipulada).
  - `useEffect` que reseta `selectedCategory` se for "Index" e o utilizador perder permissão (ex: impersonate terminou).
  - Import de `hasAnyRole` adicionado (só tinha `hasRole`).
- **`UnifiedDocumentsPanel.js`** (defesa em profundidade): flag `canSeeIndexCategory` via `useMemo` com os mesmos roles permitidos. Atributo `data-can-see-index` no div raiz para debugging/testes. O filtro granular fica no `S3FileManager`; o `UnifiedDocumentsPanel` serve como ponto de controlo documentado para futuros componentes.

### Decisão de Arquitetura
- **Scrapers automáticos NÃO afetados**: Os endpoints `_run_financas_scraper` e `_run_seguranca_social_scraper` (documentos obtidos automaticamente das Finanças/Segurança Social em nome do cliente) mantêm as suas categorias específicas (IRS, Segurança Social, etc.). Estes não são "uploads manuais do cliente" e têm categorias significativas que o cliente precisa de ver. O pedido do utilizador foca-se em documentos "enviados diretamente pelo cliente".
- **Valor canónico `"Index"`** (com I maiúsculo): O sistema já usava este valor em `DocumentCategory.INDEX` (`models/enums.py:218`) e `PORTAL_HIDDEN_CATEGORIES` (`portal.py:446`). Mantido para consistência, em vez de `"index"` minúsculo.
- **Defesa em profundidade**: O bloqueio é aplicado em 3 níveis no frontend (getCategoryCount, getAllFiles, getFilteredCategoryFiles) + useEffect guard + UnifiedDocumentsPanel flag, para garantir que documentos "Index" nunca sejam visíveis para roles não autorizados, mesmo em cenários edge (state legacy, URL manipulada, impersonate a terminar).

### Técnico
- **Backend** (`backend/routes/portal.py`): override em `generate_portal_upload_url` (linhas 1387-1402) e `confirm_portal_upload` (linhas 1463-1491); bloqueio `PORTAL_HIDDEN_CATEGORIES` comentado (linhas 1407-1412).
- **Frontend** (`frontend/src/components/S3FileManager.js`): constantes (linhas 153-164); `canSeeIndexCategory` + `visibleCategories` + `useEffect` guard (linhas 284-304); filtros em `getCategoryCount`/`getAllFiles`/`getFilteredCategoryFiles` (linhas 1000-1046); 3 `CATEGORIES.map` → `visibleCategories.map` (linhas 2120, 2589, 2727); import `hasAnyRole` (linha 74).
- **Frontend** (`frontend/src/components/UnifiedDocumentsPanel.js`): `canSeeIndexCategory` via `useMemo` (linhas 35-43); `data-can-see-index` no div raiz (linha 53); docstring atualizada (linhas 9-16).
- **Validação**: `py_compile` ✓; `flake8 --select=E9,F63,F7,F82` → 0 erros; `esbuild --loader=jsx` → 0 erros em ambos os ficheiros frontend.

## [2026-07-16] — Pacote BK: Exclusão do Estado pré_registo dos Dashboards

### Adicionado
- **Exclusão global do estado `pre_registo` dos quadros de trabalho**: Processos em `pre_registo` (cliente ainda a preencher no portal) NÃO aparecem no Kanban, nas listagens tabulares nem em "Os Meus Clientes" — só entram nos quadros de trabalho quando transitam para a primeira fase da pipeline (disparando a dupla auto-atribuição em `services/process_assignment.py`). Isto elimina o ruído gerado por processos que ainda não são leads qualificadas.

- **Helper centralizado `_should_hide_pre_registo(role, status, search)`**: Nova função em `routes/processes.py` que encapsula as regras de exclusão:
  - **Regra 3 (universal)**: `status=="pre_registo"` explícito → nunca excluir (qualquer role pode ver especificamente esse estado).
  - **Regra 1 (admin/CEO/diretor/administrativo)**: excluem na vista normal, MAS vêem pré-registos quando pesquisam (`search` ativo) ou filtram por `status` explícito — mantendo a capacidade de os encontrar através de pesquisa direta.
  - **Regra 2 (consultor/intermediário/indexação/cliente)**: sempre excluem nos quadros de trabalho (nunca veem pré-registos).

- **Constantes `PRE_REGISTO_STATUS` e `PRE_REGISTO_BYPASS_ROLES`**: Centralizam o nome do estado e os roles com privilégios de bypass (admin, CEO, diretor, administrativo).

### Aplicado
- **`GET /processes/kanban`**: Exclusão incondicional (todos os roles) após o bloco `view_mode` — o Kanban é o quadro de trabalho principal e não tem parâmetro de pesquisa, pelo que os pré-registos não devem poluí-lo para ninguém. Admins que precisem inspeccionar pré-registos usam a listagem tabular com `search`.
- **`GET /processes`** (listagem tabular): Exclusão condicional via `_should_hide_pre_registo` — consultores nunca veem; admin vê com `search` ou `status` explícito.
- **`GET /processes/paginated`**: Mesma lógica que `GET /processes`.
- **`GET /my-clients`** (processes.py): Exclusão incondicional após query por role (endpoint sem `search`).
- **`GET /my-clients`** (my_clients.py): Constante local `PRE_REGISTO_STATUS` (evita dependência circular) + exclusão com guard especial para `{"_id": None}` (sem acesso).

### Decisão de Arquitetura
- **Kanban e my-clients sem bypass para admin**: Estes endpoints não têm parâmetro `search`, pelo que a exclusão se aplica a todos os roles. O bypass para admin faz-se através da **listagem tabular** (`GET /processes` com `search`), que é o único endpoint com pesquisa direta. Isto garante que os quadros de trabalho ficam limpos de ruído para toda a equipa, incluindo admins, que mantêm a capacidade de encontrar pré-registos quando precisam.
- **Compatibilidade com `dashboard_statuses()`**: O `models/enums.py` já tinha `dashboard_statuses()` que exclui pré-registos (linha 65-67). As rotas agora alinham-se com esta definição, que já era usada em `routes/stats.py`.

### Técnico
- **Backend** (`backend/routes/processes.py`): constante `PRE_REGISTO_STATUS` + `PRE_REGISTO_BYPASS_ROLES` + helper `_should_hide_pre_registo` (linhas 1259-1302); exclusão aplicada em 4 endpoints (kanban, /processes, /paginated, /my-clients).
- **Backend** (`backend/routes/my_clients.py`): constante local `PRE_REGISTO_STATUS` (linha 31); exclusão com guard `{"_id": None}` no `GET /my-clients` (linhas 114-131).
- **Padrão de injeção**: `{"status": {"$ne": PRE_REGISTO_STATUS}}` adicionado a `$and` (ou combinado com query existente), preservando todos os outros filtros. No `GET /processes` e `/paginated`, a condição é adicionada a `and_conditions` antes da montagem final, garantindo combinação correta com `$and`.
- **Validação**: `py_compile` ✓; `flake8 --select=E9,F63,F7,F82` → 0 erros; teste funcional do helper com 21 casos (consultor/intermediário/indexação/cliente sempre escondem; admin/CEO/diretor/administrativo escondem na vista normal mas vêem com search/status explícito; regra 3 universal do status=pre_registo) — TODOS PASSARAM.

## [2026-07-16] — Pacote BJ: Stealth Mode para o Histórico (Indexação Invisível)

### Adicionado
- **Switch global `track_history` (por utilizador)**: Qualquer utilizador pode agora ser silenciado individualmente no histórico/atividades definindo `track_history: False` no seu documento da coleção `users`. Quando a chave não existe, assume-se `True` (comportamento normal com rasto). Isto permite desligar o rasto de um utilizador específico sem afetar o restante sistema.

- **Helper centralizado `_is_stealth_user(user)`**: Nova função em `services/history.py` que encapsula as regras de stealth mode: (1) `role == "indexacao"` → sempre silencioso; (2) `track_history is False` → silencioso; (3) default → não silencioso. Reutilizável por qualquer rota/serviço (já usado em `routes/activities.py`).

### Corrigido
- **`log_data_changes` não respeitava o stealth mode**: A função `log_data_changes` (que faz diff de dados e chama `log_history` por cada campo alterado) não tinha o early return de stealth mode. Adicionado o mesmo guard no início da função — agora percorre o diff APENAS se o utilizador não for silencioso, evitando trabalho desnecessário e garantindo consistência.

- **`create_activity` inseria diretamente em `db.activities` sem passar pelo stealth mode**: A rota `POST /activities` inseria o comentário diretamente na coleção `activities` antes de chamar `log_history`, pelo que o guard do `log_history` não a cobria. Adicionado guard explícito: utilizador silencioso recebe HTTP 403 com mensagem clara ("O seu perfil está em modo de indexação silenciosa e não pode adicionar comentários ao histórico do processo"). Decisão de UX: seria contraditório silenciar o `log_history("Adicionou comentário")` mas deixar o comentário visível no mural.

### Melhorado
- **`log_history` agora respeita `track_history`**: O guard existente (Pacote D, modo fantasma para `indexacao`) foi generalizado para usar o helper `_is_stealth_user`, cobrindo também o switch global `track_history`. O guard específico do Pacote D (documentos) é mantido como defesa em profundidade (redundante mas intencional).

### Decisão de Arquitetura (Importante)
- **`audit_trail` é INTENCIONALMENTE EXCLUÍDO do stealth mode**: O `audit_trail_service.py` (`log_audit_event`) é um trilho de **compliance** separado — com IP, justificações, retention policy configurável pelo admin e campos críticos (financeiros, status). Silenciar o audit trail seria um risco de segurança/compliance. O stealth mode destina-se ao **histórico visível ao utilizador** (`db.history`, `db.activities`), não ao trilho de auditoria de compliance. Inserções diretas em `db.history` em `routes/admin.py` (ações administrativas: eliminar fases, corrigir duplicados, impersonate, editar/eliminar registos) também NÃO são silenciadas — são ações de gestão de sistema que precisam de rastreabilidade.

### Técnico
- **Backend** (`backend/services/history.py`): novo helper `_is_stealth_user(user)` (linhas 13-44); early return em `log_history` (linhas 58-69) e `log_data_changes` (linhas 120-132) usando o helper; guard do Pacote D mantido como defesa em profundidade.
- **Backend** (`backend/routes/activities.py`): import de `_is_stealth_user`; guard 403 em `create_activity` antes de `db.activities.insert_one`.
- **Regra do `track_history`**: usa `user.get("track_history", True) is False` (strict `is False`) — apenas o literal `False` dispara stealth, NÃO valores falsy como `None` ou `0`, evitando false positives.
- **Validação**: `py_compile` ✓; `flake8 --select=E9,F63,F7,F82` → 0 erros; teste funcional do helper com 13 casos (None, vazio, admin, consultor, indexacao, track_history True/False/None/0, role desconhecido, combinações) — TODOS PASSARAM.

## [2026-07-16] — Pacote BI: Bolinhas de Notificação nas Listas (My Clients / Processes)

### Adicionado
- **Indicadores visuais silenciosos nas listas tabulares de processos (UX)**: As tabelas de "Os Meus Processos" (`FilteredProcessList.js`) e "Os Meus Clientes" (`MyClientsPage.js`) mostram agora pequenas bolinhas junto ao nome do cliente — **azul** para mensagens não lidas do portal e **verde** para novos documentos enviados pelo cliente — exatamente como já acontecia no Kanban. As bolinhas usam `animate-ping` (pulse) para chamar a atenção de forma silenciosa, sem popups nem toasts. Acessibilidade garantida com `title`, `role="img"` e `aria-label`.

### Corrigido (Backend)
- **4 rotas de listagem não devolviam as flags `has_unread_messages` / `has_new_documents`**: Apenas o `GET /processes/kanban` injetava estas flags. Adicionada a **mesma lógica de agregação batch do Kanban** a:
  1. `GET /processes` (paginação offset) — flags injetadas APÓS paginação (eficiência: só busca flags dos processos da página atual)
  2. `GET /processes/paginated` (paginação cursor-based) — flags injetadas após `decrypt_processes_list`
  3. `GET /my-clients` em `processes.py` — flags injetadas no `clients_list` final; leads ficam com `False`
  4. `GET /my-clients` em `my_clients.py` (rota separada) — flags injetadas após o loop de `pending_tasks`; leads ficam com `False`
- **Padrão de agregação**: `portal_messages` com `sender_type=client` + `read_by_staff=False` → `has_unread_messages`; `documents` com `status=uploaded` → `has_new_documents`. Variáveis prefixadas `_bi_` para evitar colisão de nomes.

### Técnico
- **Backend** (`backend/routes/processes.py`): 3 blocos de enriquecimento batch (~25 linhas cada) nos endpoints `GET /processes`, `GET /processes/paginated`, `GET /my-clients`; flags adicionadas ao dicionário final de cada cliente em `clients_list`.
- **Backend** (`backend/routes/my_clients.py`): 1 bloco de enriquecimento batch no endpoint `GET /my-clients`; flags injetadas em cada processo do array `processes`.
- **Frontend** (`frontend/src/pages/FilteredProcessList.js`): novo componente `NotificationDots` (reutilizável) + bolinhas na célula "Cliente" junto ao nome; import `MessageSquare` adicionado.
- **Frontend** (`frontend/src/pages/MyClientsPage.js`): novo componente `NotificationDots` + bolinhas na célula "Cliente" junto ao nome; import `MessageSquare` adicionado.
- **Padrão visual** (consistente com `KanbanCard.jsx`): `relative flex h-2.5 w-2.5` + `animate-ping` + `bg-blue-500` (mensagens) / `bg-emerald-500` (documentos). Componente retorna `null` quando não há sinal (sem ruído visual).
- **Validação**: `py_compile` ✓; `flake8 --select=E9,F63,F7,F82` → 0 erros; `esbuild --loader=jsx` → 0 erros.

## [2026-07-16] — Pacote BH: Ordenação do Histórico (Mais Recentes Primeiro)

### Corrigido
- **Atividades Recentes não ordenadas por data no Detalhe do Processo (UX)**: O cartão "Atividades Recentes" do `ProcessDetails.js` usava `[...activities].reverse()` que apenas inverte a ordem do array tal como vinha do backend — frágil e incorreto caso a ordem de origem mudasse. Substituído por `.sort()` descendente por `created_at` (fallback `timestamp`), com tratamento defensivo de datas inválidas via `safeDate()`: items sem data (ou inválidas) vão para o fim da lista em vez de quebrarem a ordenação com `NaN`. Agora as atividades mais recentes aparecem **sempre no topo**, sem necessidade de scroll.

### Verificado (já estava correto)
- **`UnifiedAuditTrail.js` (tab "Histórico" → "Filme da Lead")**: Já ordenava descendente por data (linha 297) — mantido sem alteração.
- **`ProcessTimeline.js` (timeline visual de fases)**: Ordena ascendente intencionalmente, por representar a progressão esquerda→direita das fases do workflow — mantido sem alteração.

### Técnico
- **Frontend** (`frontend/src/pages/ProcessDetails.js`): linha 176 — adicionado `safeDate` ao import de `../lib/utils`; linhas 2857-2869 — substituído `[...activities].reverse()` por `.sort()` descendente robusto com comentário explicativo `PACOTE BH`.
- **Validação**: `esbuild --loader=jsx` → 0 erros de sintaxe; confirmada exportação de `safeDate` em `lib/utils.js:101`; confirmado que nenhum teste e2e depende da ordem das atividades.

## [2026-06-29] — Pacote AE: Fix 500 no endpoint do Kanban

### Corrigido
- **500 Internal Server Error no `GET /api/processes/kanban` (Bug Crítico)**: O endpoint falhava com 500 quando um documento na coleção `workflow_statuses` tinha campos em falta (`label`, `color`, `order`, `id`, ou `name`). O código usava **bracket notation** (`status["label"]`) que lança `KeyError` se o campo não existir. Corrigido para usar `.get()` com defaults graciosos: `label` → `name.replace("_", " ").title()`, `color` → `#6B7280` (cinza), `order` → `0`, `id` → `name`. Adicionado try/except defensivo que loga o erro real (KeyError ou outro) com `logger.exception` e devolve `HTTPException(500)` com o detalhe da exceção, em vez de 500 genérico sem informação.

### Técnico
- **Backend** (`backend/routes/processes.py`): linhas 2077-2135 — loop `for status in statuses` envolvido em try/except; 5 acessos `status["..."]` trocados por `status.get("...", default)`; 2 handlers de exceção (KeyError → mensagem de configuração; Exception → mensagem genérica com tipo do erro).
- **Validação**: `py_compile` ✓; `flake8 --select=E9,F63,F7,F82` → 0 erros.

## [2026-06-29] — Pacote AD: Simulador Avançado (Taxa Mista, Seguros e Travas)

### Adicionado
- **Modo Básico vs Avançado**: O `SimulatorCH.jsx` foi dividido em duas secções visuais. A simulação rápida (sempre visível) pede apenas Montante, Prazo e Tipo de Taxa. Os campos de Seguro de Vida, Seguro Multiriscos e Comissões Iniciais ficam ocultos num `Accordion` "⚙️ Opções Avançadas" do shadcn (minimizado por defeito).

- **Valores por Defeito de TAEG (Fallbacks Invisíveis)**: Quando as opções avançadas não são tocadas, o simulador injeta fallbacks realistas para calcular a TAEG: Seguro de Vida = **15€/mês**, Multiriscos = **10€/mês**, Comissões = **0€**. Os valores são usados no cálculo mas só aparecem na UI se o cliente abrir o Accordion. Uma nota no Accordion explica os valores por defeito aplicados.

- **Motor da Taxa Mista**: Novo tipo de taxa "Mista" (além de Fixa e Variável). Quando selecionada, mostram-se obrigatoriamente os campos "Prazo da Taxa Fixa (Anos)" e "Taxa Fixa Aplicável (%)". O motor matemático foi refactorado para 2 fases: (1) Fase Fixa — prestação constante com `taxaFixa` sobre o prazo total; (2) Amortização — cálculo do capital em dívida após `prazoTaxaFixa × 12` prestações via valor presente das prestações restantes; (3) Fase Variável — nova prestação com `tan` sobre o capital amortizado durante os anos restantes. O resultado mostra ambas as prestações (Fase 1 e Fase 2) e o capital em dívida no fim da fase fixa.

- **TAEG por Bisseção**: Nova função `calcularTAEG()` que calcula a Taxa Anual de Encargos Efetiva por bisseção (100 iterações) — a taxa que iguala o montante líquido (após comissões) ao valor presente de todas as prestações + seguros. A TAEG é exibida em destaque junto à prestação mensal.

- **Travas de Idade (Maturidade BP)**: O `SimulatorCH` agora aceita a prop `clienteDataNascimento` (passada pelo `ClientPortal` a partir de `data.dados_pessoais.data_nascimento`). A idade é calculada e o slider do Prazo é limitado dinamicamente: **≤ 30 anos → máx 40 anos**, **31-35 anos → máx 37 anos**, **> 35 anos → máx 35 anos**. Se o prazo atual exceder o novo máximo (ex.: cliente envelhece), é ajustado automaticamente. Badge visual mostra a idade e o limite aplicado.

### Técnico
- **Frontend** (`frontend/src/components/portal/SimulatorCH.jsx`): reescrita completa (~550 linhas). Novas funções: `prestacaoFrances()`, `capitalEmDivida()`, `calcularTAEG()` (bisseção), `calcularSimulacao()` (motor 2 fases), `calcularIdade()`, `prazoMaximoPorIdade()`. UI com 3 botões de Tipo de Taxa, painel Taxa Mista (violeta), Accordion de Opções Avançadas, e resultado com TAEG + decomposição (Montante/Total/Juros/Seguros+Comissões).
- **Frontend** (`frontend/src/pages/ClientPortal.jsx`): `<SimulatorCH />` passou a `<SimulatorCH clienteDataNascimento={data?.dados_pessoais?.data_nascimento || data?.client_data?.data_nascimento} />`.
- **Validação**: `esbuild` ✓ em ambos os ficheiros.

## [2026-06-29] — Pacote AC: UX de Simulações e Compliance

### Adicionado
- **Dropdown de Simulações**: Os botões "DSTI" e "Risco" do cabeçalho do processo foram agrupados num único `DropdownMenu` do shadcn chamado "Simulações ▾" (ícone `Sparkles`). Aplicado em ambos os cabeçalhos: `ProcessStickyHeader.js` (sticky) e `ProcessDetails.js` (header principal). Cada item do menu usa `onSelect={(e) => e.preventDefault()}` para permitir que o `DialogTrigger` interno das calculadoras receba o click e abra o modal.

- **Euribor Automática (Backend)**: Novo endpoint `GET /api/public/euribor` que devolve as taxas Euribor reais (1M, 3M, 6M, 12M) com cache diário (24h) em memória. Novo serviço `services/euribor_service.py` com 3 níveis de fallback: (1) cache fresco < 24h, (2) API externa `euribor-rates.eu`, (3) cache antigo mesmo expirado, (4) valores de fallback hardcoded. Lock anti-concorrência para evitar múltiplas buscas simultâneas. A resposta inclui `is_fallback` (bool) e `source` ("cache"|"api"|"cache_stale"|"fallback").

- **Euribor Automática (Simulador CH)**: O `SimulatorCH.jsx` (Portal do Cliente) ganhou um seletor "Tipo de Taxa" (Fixa/Variável). Quando "Taxa Variável" é selecionada, o componente faz `fetch('/api/public/euribor')`, preenche automaticamente a Euribor 12M e calcula `TAN = Euribor + Spread`. O utilizador pode ajustar o spread (default 1.0%). Indicador visual mostra a Euribor carregada e badge "(estimada)" se for fallback.

- **Euribor na Calculadora de Risco**: O `RiskCalculator.js` também consome a Euribor automática quando "Taxa Variável" é selecionada, com campo de spread ajustável e indicação visual da Euribor 12M carregada.

- **Campos de Compliance no Modelo de Processo**: Adicionados 4 campos ao `CreditData` (`backend/models/process.py`): `admission_year` (int — Ano de admissão no emprego), `is_ppe` (bool — Pessoa Politicamente Exposta), `is_fpe` (bool — Pessoa Fiscalmente Exposta), `credit_incidents` (str — incidentes de crédito em texto livre). Validadores Pydantic para coerção de tipos (int/bool/str). Como o `CreditData` tem `extra="allow"` e o `ProcessUpdate` já aceita `credit_data`, os campos são persistidos automaticamente via `PUT /processes/{id}`.

- **Cartão "Compliance & Perfil de Risco"**: Novo cartão na tab "Crédito" dos Detalhes do Processo (`ProcessDetails.js`), minimizado por defeito (`collapsedCards` inicial `{ credit_compliance: true }`). Segue o padrão existente (`CardHeaderWithEdit` + `collapsible` + `read-only-card`). Inclui: Ano de Admissão (input number), PPE (Switch), FPE (Switch), Incidentes de Crédito (Textarea). Aviso visual automático (rose) quando PPE ou FPE estão ativos, com mensagem contextualizada sobre compliance KYC/AML.

### Corrigido
- **RiskCalculator — Tipo de Taxa não atualizava cálculos**: O `onValueChange` do seletor "Tipo de Taxa" chamava apenas `setTipoTaxa` sem recalcular, e a função `calcular()` não lia `tipoTaxa`. Agora o `handleTipoTaxaChange` atualiza o state E, quando "Variável" é selecionada, dispara um `useEffect` que busca a Euribor e preenche `taxaAnual = euribor + spread` instantaneamente.

- **RiskCalculator — Fallback do campo Entrada**: O `valorEntrada` usava `||` que é falsy para `0`, e o `if (clientData.valor_entrada || clientData.capital_proprio)` não preenchia quando ambos eram 0. Corrigido para `??` com default explícito `0`: `clientData.valor_entrada ?? clientData.capital_proprio ?? 0`. Agora lê corretamente o valor dos detalhes do processo e assume 0 (não 1) quando não existe.

### Técnico
- **Backend** (`backend/models/process.py`): 4 campos + 2 validadores adicionados ao `CreditData`.
- **Backend** (`backend/services/euribor_service.py`): novo ficheiro (165 linhas) com `get_euribor_rates()` async + cache módulo-level + lock.
- **Backend** (`backend/routes/public.py`): novo endpoint `GET /public/euribor` (montado em `/api/public/euribor`).
- **Frontend** (`frontend/src/components/ProcessStickyHeader.js`): import `DropdownMenu` + `Sparkles`; 2 botões → 1 dropdown.
- **Frontend** (`frontend/src/pages/ProcessDetails.js`): import `Switch`; 2 botões → 1 dropdown; `collapsedCards` inicial com `credit_compliance: true`; caso `credit_compliance` em `isCardEmpty`; novo cartão Compliance (80 linhas).
- **Frontend** (`frontend/src/components/RiskCalculator.js`): estados `spreadEuribor`/`euriborAuto`/`euriborLoading`; `useEffect` Euribor; `handleTipoTaxaChange`/`handleSpreadChange`; fallback `??` no `valorEntrada`; campo Spread condicional na UI.
- **Frontend** (`frontend/src/components/portal/SimulatorCH.jsx`): import `useEffect` + `TrendingUp`; estados `tipoTaxa`/`euribor12m`/`spread`; `useEffect` Euribor; seletor Fixa/Variável + painel Euribor+Spread na UI.
- **Validação**: `py_compile` ✓; `flake8 --select=E9,F63,F7,F82` → 0 erros; `esbuild` ✓ em todos os ficheiros JSX.

## [2026-06-29] — Pacote AB: Fix F821 no upload de logótipo de empresa

### Corrigido
- **F821 undefined name 'file_key' (CI blocker)**: O endpoint `POST /admin/companies/{id}/logo` em `backend/routes/companies_crud.py` (linha 246) referenciava a variável `file_key` que nunca existia — a variável correta chama-se `s3_key`. Este erro era detetado pelo `flake8 --select=E9,F63,F7,F82` e **falhava o CI** (exit code 1). Em runtime, qualquer upload de logótipo de empresa teria gerado um `NameError` (500 Internal Server Error).

- **Logótipo de empresa não era exibido no frontend**: Para além de corrigir o `NameError`, o campo `logo_url` passou a guardar a **chave S3** (ex.: `companies/{id}/logo_image.png`) na BD. Adicionado o helper `_resolve_logo_url()` que gera um **URL pré-assinado fresco** (validade 7 dias) em tempo de leitura, aplicado nos endpoints `GET /admin/companies` (list) e `GET /admin/companies/{id}`. Isto garante que o frontend recebe sempre um link válido e não expirado para `<img src>`, e suporta tanto chaves S3 como URLs absolutos (configurados manualmente via API).

### Técnico
- **Backend** (`backend/routes/companies_crud.py`): corrigido `logo_url = file_key` → `logo_s3_key = s3_key`; novo helper `_resolve_logo_url(logo_value)` com 3 ramos (None → None, URL http(s) → as-is, chave S3 → pre-signed URL 7 dias); aplicado em `list_companies` e `get_company`; resposta do upload devolve `{logo_url, logo_s3_key}`.
- **Validação**: `py_compile` ✓; `flake8 . --count --select=E9,F63,F7,F82` → **0 erros** (exit 0) em todo o backend.

## [2026-06-29] — Pacote AA: Correção de Erros 401 e 429 no Portal do Cliente

### Corrigido
- **Erros 401 em cascata no Portal do Cliente (Bug Crítico)**: Quando um cliente acedia a `/portal` com um token expirado em `localStorage`, o `ClientPortal.jsx` disparava **5 pedidos simultâneos** (`/portal/status`, `/portal/messages`, `/portal/recommendations`, `/portal/messages/unread`, `/portal/visits`) que todos devolviam 401. Os `useEffect` de `messages`, `recommendations` e `visits` não verificavam `isVerified` — corriam no mount independentemente do estado de autenticação. Adicionado guard `if (!isVerified) return;` aos 3 `useEffect` e às suas dependências. O polling de mensagens (15s) agora também para quando a sessão expira, em vez de continuar a gerar 401s.

- **429 Too Many Requests no login do Portal**: O limite de tentativas de login era demasiado agressivo — **5 tentativas** com lockout de **15 minutos**. Para um código de acesso de 6 caracteres alfanuméricos digitado manualmente, 5 tentativas é insuficiente para utilizadores legítimos. Aumentado para **8 tentativas** com lockout de **10 minutos** (mantém proteção brute-force razoável). A resposta 429 agora inclui `retry_after` (segundos) e `retry_after_minutes` no body, permitindo ao frontend fazer countdown.

- **UX do lockout no login**: O `ClientPortalLogin.jsx` agora mostra um **countdown visual** (formato `Xm Ys`) quando a conta está bloqueada, desabilita o botão de submit durante o lockout e limpa automaticamente o erro quando o tempo expira. Antes, o utilizador via uma mensagem genérica e continuava a tentar, prolongando o lockout. O `detail` da resposta 429 é tratado tanto como objeto (lockout interno do portal) como string (rate limit global do middleware).

### Técnico
- **Frontend** (`frontend/src/pages/ClientPortal.jsx`): 3 `useEffect` ganharam guard `isVerified` + dependência `isVerified` adicionada; comentários explicativos adicionados.
- **Frontend** (`frontend/src/pages/ClientPortalLogin.jsx`): novo estado `lockoutSeconds` + `useEffect` de countdown + ícone `Lock` importado; `canSubmit` agora inclui `!isLockedOut`; bloco de erro distinto (âmbar) para lockout vs erro normal (vermelho).
- **Backend** (`backend/routes/portal.py`): `MAX_LOGIN_ATTEMPTS` 5→8, `LOGIN_LOCKOUT_MINUTES` 15→10; as 2 respostas 429 (lockout ativo + novo lockout) devolvem `detail` como objeto estruturado com `message`, `retry_after`, `retry_after_minutes` + header `Retry-After`.

## [2026-06-25] — Pacote R: Motor de Pesquisa vs Filtros (Fix Crítico)

### Corrigido
- **Pesquisa ignora filtros (Bug Crítico)**: A pesquisa de texto sobrepunha-se aos filtros (status, role, etc.) porque a query era construída com `$or` no nível raiz, que se chocava com outros `$or`. Refatoração completa para usar **`$and`** em todos os filtros — agora a lógica é: `(pesquisa) AND (filtros de role) AND (filtros de status) AND (is_deleted != true)`. Nenhum filtro é anulado por outro.

- **Filtro 'Eliminados' (Soft-Delete Bypass)**: Antes, `status=eliminados` ou `view_mode=deleted` não funcionavam porque `is_deleted: {$ne: True}` era sempre aplicado primeiro, bloqueando os resultados. Agora, quando o utilizador pede `status=eliminados` ou `view_mode=deleted`, o filtro inverte-se para `is_deleted: True`, mostrando apenas os registos eliminados.

- **Expansão dos campos de pesquisa de texto**: A pesquisa só cobria `client_name` e `client_email`. Agora cobre 5 campos com regex case-insensitive:
  - `client_name` (accent-insensitive)
  - `client_email`
  - `client_nif`
  - `client_phone`
  - `process_number` (ref, ex: PROC-001)

### Técnico
- Refatorados 2 endpoints: `GET /api/processes` e `GET /api/processes/paginated`
- Arquitectura: lista `and_conditions = []` → cada filtro adiciona uma condição → montagem final com `$and`
- Otimização: se há apenas 1 condição, não envolve em `$and` desnecessário

## [2026-06-25] — Pacote Q: Limpeza Visual de UI (Remover Gov.pt e Reatribuir)

### Removido
- **Botão "Preencher automaticamente com Autenticação.gov" (Chave Móvel Digital)**: Removido completamente do formulário público (`PublicClientForm.js`):
  - Removido botão de login Gov.pt (botão azul com escudo)
  - Removido banner "Dados verificados pela Autenticação.gov" (estado pós-verificação)
  - Removido `useEffect` de parse do `gov_token` da URL e auto-preenchimento
  - Removido `handleGovAuthLogin` (redirecionamento para login AMA)
  - Removidos estados: `govVerifiedFields`, `govDataLoaded`, `govAuthLoading`
  - Removidos badges "Verificado" (ShieldCheck) nos campos NIF, data de nascimento e campos genéricos
  - Removida lógica de campos bloqueados (disabled/readOnly) por verificação Gov
  - Removido `gov_verified_fields` do payload de submissão
  - Removidos imports `Shield` e `ShieldCheck` do lucide-react
  - Hint do campo `chave_movel_digital` atualizado (removida referência a autenticacao.gov.pt)

- **Botão "Reatribuir Cliente" e Dialog**: Removido completamente do `ProcessDetails.js`:
  - Removido botão "Reatribuir Cliente" (âmbar, ícone Link2) do header de ações
  - Removido Dialog completo de pesquisa e seleção de novo cliente (~130 linhas)
  - Removidos 6 estados: `showReassignDialog`, `reassignSearch`, `reassignResults`, `reassignLoading`, `reassignSaving`, `reassignSelected`
  - Removidas funções: `handleReassignSearch`, `handleReassignClient` + debounce useEffect
  - **Justificação**: Na arquitetura 1 Cliente → N Processos, reatribuir o cliente globalmente é perigoso. O botão "Atribuições" (existente) já cobre as necessidades de gestão por processo.

## [2026-06-25] — Pacote P: Sincronização do Nome do Cliente (Edição Global e Cascata)

### Adicionado
- **Botão "Editar Cliente" na Ficha do Cliente** (Frontend): Botão com ícone de lápis no cabeçalho da `ClientDetailPage` que abre um Modal para editar os dados base da entidade global: Nome, NIF, Email e Telefone. O Modal só envia campos alterados (diff) e atualiza o estado local instantaneamente.

### Corrigido
- **Efeito cascata ao editar cliente** (`PUT /api/clients/{id}`): Antes, alterar o nome do cliente NÃO atualizava o `client_name` nos processos associados, criando dessincronização. Agora, o endpoint propaga automaticamente:
  - `nome` → `client_name`, `personal_data.nome`, `personal_data.name` em todos os processos via `update_many`
  - `dados_pessoais` (NIF, morada, estado civil, profissão, etc.) → `personal_data.*` correspondente nos processos
  - `contacto.telefone` → `client_phone`, `personal_data.telefone`, `personal_data.phone` nos processos
  - Blind indexes (`nif_hash`, `email_hash`) são regenerados quando NIF/email mudam

- **Sincronização inversa ao editar pelo Processo** (`PUT /api/processes/{id}`): Quando o utilizador edita o nome do cliente dentro do cartão de dados pessoais do processo, o sistema agora:
  1. Atualiza o documento do cliente na coleção `clients` (comportamento existente)
  2. **NOVO**: Propaga o novo nome para todos os **restantes processos** do mesmo cliente via `update_many` (cascade sync)

### Segurança
- Sanitização de inputs mantida (nome, NIF, email, telefone)
- Encriptação Fernet preservada em ambos os caminhos de atualização
- Logs detalhados de sincronização para auditoria

## [2026-06-25] — Pacote O: Mural de Atualizações (Gerado por IA)

### Adicionado
- **Mural de Atualizações gerado por IA** — Sistema completo de notas de lançamento automáticas:
  - **Backend**: Nova coleção `system_changelogs` (MongoDB) para guardar notas de atualização geradas por IA
  - **Endpoint público `GET /api/system/changelog`**: Qualquer utilizador autenticado pode consultar as últimas atualizações
  - **Endpoint admin `POST /api/system/changelog/generate-ai`**: Gera notas de atualização por IA (restrito a admin/CEO). Suporta 3 fontes de dados:
    - `git`: Histórico de commits (padrão, com fallback para CHANGELOG.md)
    - `changelog_file`: Ficheiro CHANGELOG.md
    - `worklog`: Ficheiro worklog.md
  - **Serviço `changelog_service.py`**: Lógica de negócio com integração OpenAI GPT-4o-mini, retry com exponential backoff, sanitização anti-prompt-injection, e truncagem de contexto
  - **Modelos Pydantic `changelog.py`**: `ChangelogEntry`, `ChangelogResponse`, `ChangelogGenerateRequest`, `ChangelogGenerateResponse`
  - **Rota `routes/changelog.py`**: 2 endpoints com autenticação e autorização por role
  - **Registo no `server.py`**: Router registado com prefixo `/api`

- **Frontend — Card "📢 Novidades do CRM" na Dashboard**: Card visual com gradiente que mostra a última atualização gerada por IA. Oculta-se automaticamente se não houver dados. Renderiza Markdown de forma segura (DOMPurify + conversor próprio).

- **Frontend — Tab "Atualizações" nas Definições do Sistema**: Secção dedicada para admins com:
  - Seletor de fonte de dados (Git / CHANGELOG.md / worklog.md)
  - Botão "✨ Gerar Notas de Atualização (IA)" com loading state
  - Lista de todos os changelogs publicados com badges de versão e data
  - Estado vazio amigável com ícone e instrução

- **Conversor de Markdown para HTML** (`markdownToHtml`): Função utilitária sem dependências externas que converte Markdown básico em HTML seguro (headers, bold, italic, bullets, line breaks). Output sempre sanitizado por DOMPurify.

- **Funções API no `api.js`**: `getSystemChangelogs()` e `generateChangelogAI()` para comunicação frontend↔backend

### Segurança
- Sanitização de input anti-prompt-injection no `changelog_service.py`
- Truncagem de texto fonte para máximo 8000 caracteres (limite de contexto)
- Renderização HTML sempre via DOMPurify (`sanitizeHtml`)
- Endpoint de geração restrito a roles admin/CEO

## [2026-06-23] — Limpeza técnica: .pyc committed + última query legacy email_config.is_configured

### Corrigido
- **Auto-sync de emails em background não sincronizava utilizadores com config multi-empresa** (`bug` — **CRÍTICO/PRODUÇÃO**): A função `sync_all_user_emails` (`backend/services/email_service.py:2093`) — usada pela sync global de todos os utilizadores — ainda usava a query legacy `db.users.find({"email_config.is_configured": True})` que só encontrava configs flat embebidas em `user.email_config` (campo `is_configured` ao nível de topo). As configs guardadas via o fluxo Perfil > Configuração de Webmail (arquitetura multi-empresa) ficam ANINHADAS em `user.email_config["company:<id>"]` e na coleção canónica `user_email_configs` — pelo que a query legacy nunca as encontrava. Isto era a "limitação conhecida" documentada no hotfix de 2026-06-20 (commit `2f65050`) e no Pacote J (`b7ce96f`), que já tinham corrigido `worker.py` e `scheduled_tasks.py` mas deixado `email_service.py` por corrigir.

  **Fix** — Substituída a query legacy por `get_active_email_configs_for_sync(limit=200)` (de `user_email_config_service.py`), que consulta a coleção canónica `user_email_configs` (uma config por par user+empresa, com credenciais válidas, user ativo). Para cada config devolvida:
  1. Resolve a config canónica via `resolve_email_config_for_sync(user_id, active_company_id=company_id)`
  2. Chama `sync_user_emails(user_id, days=days, resolved_config=resolved)` — o mesmo padrão usado pelo `worker.py` e `scheduled_tasks.py` (Pacote J)

  **Tratamento de edge cases**:
  - Google OAuth pessoal: skip com log debug (legacy também não suportava — paridade com `worker.py`)
  - Config não resolúvel: skip com log debug + contador `skipped_unresolved`
  - Sem configs pessoais mas com roles partilhados: sync só roles partilhados (indexacao, suporte)
  - Roles partilhados: mantidos via `sync_shared_role_emails` (caixa partilhada, não usa configs pessoais)

  **Retorno enriquecido** (superconjunto backward-compatible do retorno anterior):
  - `users_synced` (int): número de configs pessoais sincronizadas
  - `shared_roles_synced` (int): número de roles partilhados sincronizados
  - `skipped_oauth` (int): configs Google OAuth saltadas
  - `skipped_unresolved` (int): configs não resolúveis
  - `total_synced`, `total_errors` (mantidos)
  - `users` (dict): chave composta `user_id|company_id` para distinguir configs do mesmo user em empresas diferentes

  Isto fecha a última pendência técnica do Pacote J — agora **todas** as 3 funções de auto-sync (`worker.py`, `scheduled_tasks.py`, `email_service.py`) usam a coleção canónica `user_email_configs` e suportam configs multi-empresa nested. Zero queries `email_config.is_configured` ativas no backend (apenas 4 comentários "SUBSTITUI a query legacy" para documentação).

### Limpeza
- **Removidos 3 ficheiros `.pyc` committed acidentalmente no Pacote M** (`chore`): Os ficheiros `powercell/backend/routes/__pycache__/{clients,portal,tasks}.cpython-312.pyc` foram commitados por engano no commit `d245b80` (Pacote M). Removidos do index via `git rm --cached` (mantidos no disco localmente) e adicionado ao `.gitignore`:
  - `__pycache__/`
  - `*.py[cod]` (cobre `.pyc`, `.pyo`, `.pyd`)
  - `*$py.class` (Jython)
  - `*.so` (extensões C compiladas)
  - `/powercell/**/__pycache__/` (específico do subdiretório powercell/)

  Isto previne que builds Python voltem a poluir o repo no futuro.

### Notas
- **Sem breaking changes**: o retorno da função é superconjunto do anterior (todos os campos antigos mantidos). Os callers existentes continuam a funcionar.
- **Validação**: `py_compile` + `ast.parse` OK. Sintaxe Python válida.
- **Dev server**: confirmado saudável (HTTP 200) durante toda a sessão.

---

## [2026-06-22] — Pacote L: Proteção de Eliminação — Regra do 2º Titular

### Corrigido
- **Eliminar um cliente que fosse apenas 2º titular destruía processos que ainda tinham 1º titular ativo** (`bug` — **CRÍTICO/QA**): O endpoint `DELETE /api/clients/{id}` (`backend/routes/clients.py`, função `delete_client`) fazia cascata de soft-delete sem distinguir se o cliente era o titular principal (`process.client_id`) ou o 2º titular (`process.second_client_id`). Isto causava perda silenciosa de dados e bloqueava o trabalho do consultor responsável pelo processo.

  **Regra de Proteção implementada — "Regra do 2º Titular"**:
  1. **TITULAR PRINCIPAL** (`process.client_id == client_id`): soft-delete em cascata completo — processo + documentos + tarefas (`is_deleted=True`, `status='eliminado'`). O processo é destruído porque o 1º titular desaparece. Agora também guarda `previous_status` para o endpoint de restore poder recuperar o status original.
  2. **APENAS 2º TITULAR** (`process.second_client_id == client_id` E `process.client_id != client_id`): **NÃO** elimina o processo. Apenas remove a associação (`$unset second_client_id + second_client_data`), mantendo o processo **ATIVO** para o 1º titular. Regista metadados de auditoria (`second_titular_unlinked_at`, `second_titular_unlinked_by`, `second_titular_unlinked_reason`) no documento do processo para rastreabilidade forense.

  **Implementação** — A função `delete_client` foi dividida em 3 fases:
  - **FASE 1** (nova): percorre `processes` onde `second_client_id == client_id` AND `client_id != client_id` AND `is_deleted != True` → desliga a associação e mantém o processo ativo. Conta os desligamentos em `second_titular_unlinks` e ids em `unlinked_process_ids`.
  - **FASE 2** (melhorada): branch do processo por `id == client_id` — mantém o soft-delete + cascata docs/tasks, agora com `previous_status` guardado. Retorna os contadores de 2º titular desligado.
  - **FASE 3** (corrigida): branch legada da coleção `clients` — substituído o `$unset client_id` (que deixava órfãos ativos) por cascata soft-delete REAL dos processos onde `client_id == client_id` (1º titular confirmado): processo + docs + tasks com `is_deleted=True`, `previous_status` guardado. Os 2º titular-only já foram tratados na FASE 1.

  **Retorno da API enriquecido** — Ambas as branches retornam agora:
  - `second_titular_unlinks` (int): número de processos onde o cliente foi desligado como 2º titular
  - `unlinked_process_ids` (list): ids dos processos desligados
  - `cascade_count` + `cascade_process_ids` (apenas FASE 3): processos eliminados em cascata como 1º titular

  Isto permite ao frontend dar feedback claro: *"Cliente movido para o lixo. 2º titular desligado de N processo(s). M processo(s) eliminados em cascata."*

### Notas
- **Mapeamento de schema**: O prompt do utilizador referia `titular_2_id`, mas o campo real no código é `second_client_id` (com dados denormalizados em `second_client_data`), confirmado via `frontend/src/components/SecondTitularCard.jsx` e `backend/routes/processes.py:3462-3477`. A regra foi implementada sobre o campo real.
- **Sem breaking changes**: O retorno da API é superconjunto do anterior (todos os campos antigos mantidos). Os callers existentes continuam a funcionar.
- **Validação**: `py_compile` + `ast.parse` OK. Sintaxe Python válida.

---

## [2026-06-21] — Pacote M: Auto-Login do Portal (Impersonate) + Nomenclatura de Tarefas [PROC-XXX]

### Corrigido
- **"Ver como Cliente" abria o Portal mas o utilizador ficava retido no ecrã de Login** (`bug` — **UX/INTEGRAÇÃO**): O botão "Ver como Cliente" gerava um magic link via `POST /processes/{id}/generate-magic-link` que devolve um URL com short_id no PATH (`/portal/{short_id}`). O frontend do Portal resolvia o short_id mas só extraía o `client_id` — não fazia auto-login (comentário explícito no código: "não carregar dados — o login ainda é obrigatório"). Resultado: staff clicava "Ver como Cliente" e via o ecrã de login em vez da dashboard.

  **Fix em 3 camadas**:
  - **Backend** (`backend/routes/portal.py`): Novo endpoint `GET /portal/impersonate/{process_id}` (protegido por `require_staff`). Gera JWT via `create_client_magic_token`, devolve `{ magic_link: "{frontend_url}/portal?token={JWT}", token, process_id, client_id, client_name, client_email, expires_in_days }`. Filtra `is_deleted != True` (não permite impersonate de eliminados). Log de auditoria `[IMPERSONATE]`. Adicionados imports: `create_client_magic_token`, `PORTAL_TOKEN_VALIDITY_DAYS` de `services.portal_security`; `require_staff` de `services.auth`; `Request` do fastapi.
  - **Frontend — API client** (`frontend/src/services/api.js`): Adicionado `export impersonateClientPortal(processId) → api.get('/portal/impersonate/${processId}')`.
  - **Frontend — Staff UI** (`frontend/src/pages/ProcessDetails.js`): Adicionado botão **"Ver como Cliente"** (teal, default variant) no topo do Popover "Portal do Cliente" que chama `impersonateClientPortal(id)` e abre `res.data.magic_link` em nova aba (`window.open` com `noopener,noreferrer`). Botões "Copiar Link" e "Enviar por Email" mantidos por baixo.
  - **Frontend — Portal UI** (`frontend/src/pages/ClientPortal.jsx`): Adicionado `useEffect` de auto-login que lê `URLSearchParams(window.location.search)` procurando `token` | `magic_link` | `access_token`. Se o token não contém `.` (short_id) → resolve via `/portal/resolve/{short_id}` primeiro; se é JWT → usa diretamente. Guarda token em `localStorage` (`portalToken` + `portal_token`), marca `portalAuthMethod='magic_link_impersonate'`, `portal_verified='true'`, `portalLastActivity`. Limpa o token da URL via `window.history.replaceState` (segurança — não fica no histórico do browser). `setIsVerified(true)` → saltar ecrã de login e ir direto para a dashboard. Idempotente via state `autoLoginAttempted`; tratamento de erro limpa tokens parciais e mostra login; `AbortController` com timeout 15s.

- **Tarefas criadas não identificavam claramente o processo** (`bug` — **UX/NOMENCLATURA**): O endpoint `POST /api/tasks` (`backend/routes/tasks.py`, função `create_task`) só adicionava `[client_name]` como prefixo do título. Não incluía a referência do processo (`PROC-XXX`), pelo que nas listas de tarefas não era possível identificar a que processo diziam respeito.

  **Fix Backend** (`backend/routes/tasks.py`):
  - Estendida a projection do `db.processes.find_one` para incluir `process_ref` + `process_number`.
  - Adicionada lógica: obter `process_ref` (preferir campo directo; fallback formatar `process_number` como `PROC-{N:04d}`; nunca gerar prefixo vazio).
  - **Anti-duplicação**: se o título já contém `[proc-` (case-insensitive) → saltar a prefixação.
  - Formatar `title = "[PROC-012] {title}"`.
  - Comportamento legado preservado: se `process_name` (`client_name`) não estiver no título, adiciona `[client_name]` como segundo prefixo. Resultado final ex: `[PROC-012] [João Silva] Recolher documentos`.
  - O título enriquecido é gravado no documento `task` — é o que aparece em todas as listas, notificações e audit trail.

### Notas
- **Validação**: `py_compile` + `ast.parse` OK nos 2 ficheiros backend. Sintaxe Python válida.
- **Sem breaking changes**: O endpoint `POST /tasks` mantém o mesmo contrato (TaskResponse). O título é apenas enriquecido antes de ser gravado.
- **Segurança**: O token de impersonate tem a mesma validade dos magic links (`PORTAL_TOKEN_VALIDITY_DAYS = 90 dias`). O `require_staff` garante que só staff autenticado pode gerar impersonate links.

---

## [2026-06-20] — Pacote K: Bugfixes de QA (Balcões, Reatribuir, Cliente Ativo, Restore, Mapeamento, Área Pessoal)

### Corrigido
- **1. Lista de Balcões não atualizava após adicionar novo** (`bug` — **UX**): No `SendDocumentationModal.js`, o handler `handleCreateBranch` fazia POST com sucesso mas apenas anexava o novo balcão ao state local manualmente (sem campos completos do backend). Agora chama `loadData()` para re-buscar a lista canónica, garantindo que o novo balcão aparece imediatamente com todos os campos.
- **2. 'Reatribuir Cliente' ao nível do Perfil Global** (`bug` — **UX**): Verificado que NÃO existe botão "Reatribuir Cliente" ao nível do cliente global (ClientsPage, ClientDetailPage, etc.). O botão existe APENAS em `ProcessDetails.js` (nível do processo), que é o comportamento correcto — um cliente pode ter processos geridos por pessoas diferentes. Sem alteração de código necessária; confirmado que o conceito já estava correcto.
- **3a. Cálculo de 'Cliente Ativo' incorrreto** (`bug` — **LÓGICA/BACKEND**): O `clients.py` calculava "cliente ativo" usando a flag `is_active` desnormalizada (que pode dessincronizar do `status` real) e com typos na lista de exclusão (`"concluidos"` em vez de `"concluido"`, `"arquivado"` em vez de `"arquivo"`). Além disso, não verificava `is_deleted`. Nova lógica: um cliente é ativo se tiver pelo menos UM processo onde `is_deleted != True` E `status NOT IN ("concluido", "desistencia", "desistencias", "eliminado")`. Aplicado em ambos os ramos (show_all=True e show_all=False). Adicionado `is_deleted` às projections MongoDB.
- **3b. 'Ver como Cliente' / navegação para primeiro processo usava processo eliminado** (`bug` — **UX**): O `ClientRegistrationsPage.js` navegava para `client.processes[0].id` sem filtrar processos eliminados. Se o primeiro processo estivesse eliminado, o utilizador caía num processo eliminado. Agora usa `processes.find(p => !p.is_deleted && p.status !== "eliminado")` com fallback para `processes[0]`. Aplicado em ambas as ocorrências (lista e dialog de detalhes).
- **4a. Endpoint de Restore quebrado** (`bug` — **CRÍTICO/BACKEND**): O endpoint `POST /api/processes/{id}/restore` existia em `restore.py` mas estava quebrado: (1) NÃO fazia `is_deleted: False` — o processo ficava "restaurado" mas continuava invisível em todas as queries com `{"is_deleted": {"$ne": True}}`; (2) sempre forçava `status: "clientes_espera"` em vez de preservar o original; (3) não restaurava documentos e tarefas em cascade; (4) tinha dead code para `db.deleted_processes` (coleção inexistente); (5) restaurava processos legítimamente concluídos (`is_active: False`). Rewrite completo: unset `is_deleted`, restaura `previous_status` (guardado pelo delete), cascade-restore de documentos/tarefas, log em `process_activities`. Adicionado `previous_status` ao delete endpoint em `processes.py`.
- **4b. Botão Restaurar na lista de Eliminados** (`feature` — **UX**): `ProcessesPage.js` não tinha filtro "Eliminados" nem botão de restaurar. Adicionado: (1) Select com 3 opções (Ativos / Todos / Eliminados) substituindo o Switch antigo; (2) botão "Restaurar" (ícone `RotateCcw`) por linha na vista de Eliminados; (3) badge "Eliminado" vermelho na coluna de status; (4) `restoreProcess` e `deleteProcess` exportados de `api.js`.
- **5. Mapeamento de dados para texto de balcões retornava 'N/A'** (`bug` — **DADOS/BACKEND**): O `_extract_email_variables` em `emails.py` lia paths antigos que não correspondem aos novos cartões do `ProcessDetails.js`. Corrigido: `[VALOR_FINANCIAMENTO]` agora lê `credit_data.requested_amount` (cartão "Dados de Crédito") e `financial_data.valor_financiado`; `[CAPITAIS_PROPRIOS]` agora lê `financial_data.capital_proprio` (singular — nome usado no cartão "Rendimentos"); `[PRAZO_FINANCIAMENTO]` agora lê `credit_data.loan_term_years`.
- **6. Área Pessoal não atualizava ao mudar de perfil + sem toast.success** (`bug` — **UX**): O `ProfilePage.js` usava `toast` do `use-toast` (shadcn) em vez de `sonner` — os toasts de sucesso apareciam cinzentos sem indicador visual. Além disso, o `RichTextEditor` (ReactQuill) não sincronizava visualmente quando o `value` mudava após switch de empresa. Corrigido: (1) import mudou para `sonner`; (2) todos os 13 `toast({...})` convertidos para `toast.success()/error()/warning()`; (3) `handleSaveSignature` agora mostra `toast.success("Assinatura guardada com sucesso")`; (4) adicionado `key={sig-${effectiveCompanyId}}` ao `RichTextEditor` para forçar remount ao mudar de empresa.

### Decisões técnicas
- **Bug 2 (Reatribuir Cliente)**: O QA reportou "remover ao nível do Perfil Global", mas a investigação revelou que o botão NUNCA existiu ao nível do cliente global — apenas em `ProcessDetails.js` (nível do processo). Sem alteração de código; comportamento já estava correcto.
- **Bug 3b (Ver como Cliente)**: O QA referiu "botão 'Ver como Cliente'" mas esse botão não existe literalmente. O botão "Portal do Cliente" em `ProcessDetails.js` já usa o `id` do processo actual (correcto). O bug real estava na navegação "Ver processo" a partir de listas de clientes (`ClientRegistrationsPage.js`), que usava `processes[0]` sem filtrar eliminados. Corrigido esse padrão.
- **Estados terminais para "Cliente Ativo"**: usada a lista do QA (`concluido`, `desistencia`, `eliminado`) + `desistencias` (plural — valor real do enum `ProcessStatus.DESISTENCIAS`). `arquivo` e `perdido` NÃO estão na lista de exclusão (o cliente com processo arquivado/perdido ainda é considerado ativo, per spec do QA).
- **Restore endpoint**: mantido em `restore.py` (onde já estava montado em `/api`), rewrite completo em vez de mover para `processes.py` (evita conflito de routing).

## [2026-06-20] — Pacote J: Refatoração do Auto-Sync de Emails (Background Workers Multi-Empresa)

### Corrigido
- **Auto-sync de emails em background não sincronizava utilizadores com config multi-empresa** (`bug` — **TÉCNICO/PRODUÇÃO**): O `worker.py` (a cada 15 min) e o `scheduled_tasks.py` (a cada hora) usavam a query legacy `db.users.find({"email_config.is_configured": True})` que só encontrava configs **flat** embebidas em `user.email_config`. Como a arquitetura atual guarda as configs na coleção canónica `user_email_configs` (uma por par `user_id`+`company_id`) e aninhadas em `user.email_config["company:<id>"]`, a auto-sync **ignorava completamente** os utilizadores que configuraram o email via o fluxo Perfil > Configuração de Webmail. Apenas a sync **manual** (Pacote anterior) funcionava para esses utilizadores.
  - **Backend** (`backend/services/user_email_config_service.py`): Adicionada nova função `get_active_email_configs_for_sync(limit=100)`. Consulta a coleção canónica `user_email_configs` com filtros: `is_configured: True` AND (tem `encrypted_password` IMAP/SMTP OU tem `google_refresh_token` Google OAuth). Faz uma segunda query batch em `users` para filtrar apenas utilizadores ativos (`is_active != False`). Devolve lista de `{user_id, company_id, email_address, auth_method, user_email}` — o iterador multi-empresa pedido pelo utilizador.
  - **Backend** (`backend/worker.py`): Refatorado o bloco de auto-sync de webmail (linha ~216). Substituída a query legacy por `get_active_email_configs_for_sync(limit=50)`. O loop itera agora sobre pares `(user_id, company_id)`, chama `resolve_email_config_for_sync(user_id, active_company_id=company_id)` para obter a config canónica, e passa-a a `sync_user_emails(resolved_config=resolved)`. Tratamento de erros individual por config (try/except dentro do loop) mantido — falha numa conta não bloqueia as restantes. Detecção de policy violation IMAP mantida (parar iteração em rate limit). Sync de caixas partilhadas via Gmail API (`shared_role_email_configs`) **sem alterações**.
  - **Backend** (`backend/services/scheduled_tasks.py`): Refatorado o bloco "2. Sincronizar caixas pessoais" (linha ~1449) com o mesmo padrão: `get_active_email_configs_for_sync` + loop por `(user_id, company_id)` + `resolve_email_config_for_sync` + `sync_user_emails(resolved_config=resolved)`. Tratamento de policy violation via `_is_policy_violation()` mantido.

### Decisões técnicas
- **OAuth pessoal ainda não suportado na auto-sync**: o `sync_user_emails` só trata IMAP/SMTP (desencripta `encrypted_password` e liga via `imaplib`). Para configs com `auth_method == "google_oauth"`, o worker regista log debug e salta — **não é regressão** (a query legacy também não suportava OAuth pessoal, porque `sync_user_emails` sempre falharia em `encryption_service.decrypt("")`). Implementar `gmail_api_sync_user_to_db(user_id, company_id)` fica para iteracao futura.
- **Limite de 50 configs por ciclo** (worker e scheduled_tasks): mantém o mesmo teto do código anterior para evitar rajadas de ligações IMAP. Cada config tem 3s de delay entre si.
- **Índice composto único** `(user_id, company_id)` em `user_email_configs` (já existente em `db_indexes.py`) garante performance da query.

### Resultado
- A auto-sync em background passa a funcionar para **todos** os utilizadores com config ativa, independentemente de ser flat (legacy), nested multi-empresa, ou guardada via Perfil > Configuração de Webmail.
- Fecha a "limitação conhecida" documentada no hotfix anterior (commit `2f65050e`): a sync manual já funcionava, mas a auto-sync em background ainda usava a query legacy. Agora ambas usam a arquitetura canónica.

## [2026-06-20] — Hotfix: Webmail "Configuração de email não ativa" para utilizadores com config multi-empresa

### Corrigido
- **Sincronização manual do Webmail falhava com "Erro na sincronização: Configuração de email não ativa" para utilizadores que configuraram o email via o fluxo Perfil > Configuração de Webmail** (`bug` — **CRÍTICO/PRODUÇÃO**): O utilizador reportou que, em produção, ao clicar em "Sincronizar" no Webmail aparecia o toast `Erro na sincronização: Configuração de email não ativa`, mesmo tendo a configuração de email pessoal ativa e funcional (envio de email funcionava). Diagnóstico revelou uma divergência entre o `resolve_email_config_for_sync` (canónico) e o `sync_user_emails` (legado):
  - A rota `POST /api/emails/webmail/sync-user` (`backend/routes/emails.py`) usa o resolver canónico `resolve_email_config_for_sync` para validar que a config existe — e este funciona corretamente (suporta multi-empresa, nested `email_config`, e a coleção `user_email_configs`).
  - Contudo, depois de validar, a rota inicia um job em background que chama `sync_user_emails(user_id)` passando **apenas** o `user_id`. O `sync_user_emails` (`backend/services/email_service.py`) **ignorava** o resolver e lia o `user.email_config` embebido **diretamente** (campo `is_configured` ao nível de topo).
  - Ora, as configs guardadas via o fluxo Perfil > Configuração de Webmail (multi-empresa) ficam **aninhadas** em `user.email_config["company:<id>"]` (e na coleção canónica `user_email_configs`), **não** em formato flat ao nível de topo. Por isso, `config.get("is_configured")` devolvia `None` (porque as chaves de topo são `company:default`, `company:power`, etc.) e a função devolvia `{"success": False, "error": "Configuração de email não ativa"}` — exatamente o erro visto pelo utilizador.
  - **Backend** (`backend/services/email_service.py`): Adicionado parâmetro opcional `resolved_config: Optional[Dict[str, Any]] = None` a `sync_user_emails`. Quando fornecido, a função usa **diretamente** essa config (já resolvida pelo resolver canónico) e **não** lê o `user.email_config` embebido. Quando `None`, mantém o comportamento legado (ler `user.email_config` flat) para não quebrar os callers existentes (`worker.py`, `scheduled_tasks.py`, `sync_all_emails`) que ainda operam sobre configs flat.
  - **Backend** (`backend/routes/emails.py`): O handler `webmail_sync_user` agora passa o `resolved` (config já resolvida por `resolve_email_config_for_sync`) ao `sync_user_emails` via `sync_user_emails(user_id, resolved_config=resolved)`. Isto garante que a sync usa a **mesma** config que foi validada — independentemente de ser flat, nested, ou vinda da coleção `user_email_configs`.

### Resultado
- A sincronização manual do Webmail (botão "Sincronizar") passa a funcionar para todos os utilizadores, incluindo os que configuraram o email via o fluxo multi-empresa Perfil > Configuração de Webmail.
- O erro `Erro na sincronização: Configuração de email não ativa` deixa de aparecer para utilizadores com config válida.
- Backward-compatible: os callers existentes (`worker.py`, `scheduled_tasks.py`, `sync_all_emails`) continuam a funcionar sem alterações (não passam `resolved_config`, pelo que caem no caminho legado flat).

### Notas
- **Limitação conhecida NÃO resolvida neste hotfix** (escopo maior, follow-up): as queries do `worker.py` (linha 224) e `scheduled_tasks.py` (linha 1453) usam `{"email_config.is_configured": True}` que **não** encontra utilizadores com config nested/multi-empresa (só encontra flat). Isto afeta a **auto-sync** em background (não a sync manual). Para corrigir, estas queries teriam de ser alargadas para consultar também a coleção `user_email_configs`. Ficado para iteração separada por ser uma mudança mais ampla (envolve reescrever queries MongoDB + iterar resultados de duas fontes).
- Este hotfix resolve o sintoma reportado pelo utilizador (sync manual). A auto-sync em background continuará a não funcionar para configs multi-empresa até o follow-up ser feito.

## [2026-06-20] — Hotfix: Fontes Google render-blocking (ERR_CONNECTION_CLOSED no fonts.gstatic.com)

### Corrigido
- **Erro `net::ERR_CONNECTION_CLOSED` no `fonts.gstatic.com` bloqueava a renderização** (`bug` — **UX/PRODUÇÃO**): O utilizador reportou erro na consola do browser ao carregar a aplicação em produção: `GET https://fonts.gstatic.com/s/jetbrainsmono/...woff2 net::ERR_CONNECTION_CLOSED`. Causa raiz: o `src/index.css` tinha um `@import url('https://fonts.googleapis.com/css2?...')` no topo — e **`@import` em CSS é render-blocking**. O browser bloqueia a parse e renderização do CSS até que o `@import` resolva ou falhe. Quando o CDN da Google (`fonts.gstatic.com`) está inacessível (ad blockers como uBlock Origin, firewall corporativa, ISP com bloqueio de domínios Google, problemas de DNS), a página inteira ficava bloqueada à espera do timeout, e o utilizador via a página lenta/em branco + o erro na consola.
  - **Frontend** (`frontend/src/index.css`): Removido o `@import url(...)` render-blocking do topo do ficheiro. Substituído por um comentário explicativo que documentação que as fontes agora carregam via `<link>` não-bloqueante no HTML.
  - **Frontend** (`frontend/index.html`): Adicionados 5 `<link>` no `<head>` com o padrão **não-bloqueante** recomendado pelo web.dev:
    1. `<link rel="preconnect" href="https://fonts.googleapis.com">` — estabelece ligação TCP/TLS antecipadamente
    2. `<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>` — idem para o CDN de ficheiros
    3. `<link rel="preload" as="style" href="...">` — prioriza o descarregamento da stylesheet
    4. `<link rel="stylesheet" href="..." media="print" onload="this.media='all'">` — **truque da Google/web.dev**: carrega a stylesheet em paralelo mas NÃO bloqueia a renderização (o browser aplica `media="print"` que é inerte, depois o `onload` troca para `media="all'` quando chega)
    5. `<noscript><link rel="stylesheet" ...></noscript>` — fallback para utilizadores sem JavaScript
  - **Frontend** (`frontend/src/index.css`): Melhorados os fallbacks de `font-family` em `body`, `h1-h6`, `.font-mono` e `code`. Antes: `'Inter', sans-serif` (fallback genérico). Agora: `'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif` — usa fontes de sistema nativas (San Francisco no macOS/iOS, Segoe UI no Windows, Roboto no Android/ChromeOS) que são visualmente quase idênticas a Inter/Manrope. Para monoespaçada: `'JetBrains Mono', 'SF Mono', Monaco, 'Cascadia Code', 'Roboto Mono', Consolas, 'Liberation Mono', monospace`.

### Resultado
- A página renderiza **instantaneamente** com fontes de sistema (FOUT — Flash of Unstyled Text mínimo, impercetível porque as fontes de sistema são quase idênticas).
- Quando o CDN da Google responde (na maioria dos casos), o browser troca para Manrope/JetBrains Mono/Inter sem quebra de layout.
- Quando o CDN está inacessível (ad blockers, firewall, DNS), a página **funciona na mesma** com fontes de sistema — sem `ERR_CONNECTION_CLOSED` bloqueante, sem página em branco, sem timeout.
- O erro `net::ERR_CONNECTION_CLOSED` pode ainda aparecer na consola em ambientes restritos, mas **já não bloqueia a renderização** — é apenas um pedido em background que falhou silenciosamente.

## [2026-06-20] — Hotfix: Erro de CORS no Webmail (header X-Active-Company não permitido)

### Corrigido
- **Erro de sincronização CORS no Webmail em produção** (`bug` — **CRÍTICO/PRODUÇÃO**): O utilizador reportou erro `net::ERR_FAILED` com mensagem "Response to preflight request doesn't pass access control check: It does not have HTTP ok status" ao sincronizar emails em `https://www.powercell.pt`. Diagnóstico via simulação de preflight OPTIONS ao backend em produção revelou que o preflight devolvia **HTTP 400** quando o browser pedia o header `X-Active-Company`. Causa raiz: o `WebmailPage.jsx` enviava o header **`X-Active-Company`** (3 ocorrências), mas: (1) o backend lê o header **`X-Company-Id`** (em todo o lado: `services/auth.py:465`, `routes/emails.py`, etc.); (2) a config CORS de produção (`CORS_ALLOW_HEADERS` no `render.yaml`) permite **`X-Company-Id`** mas **NÃO** `X-Active-Company`. Resultado: o browser fazia preflight OPTIONS, o backend respondia 400 (header não permitido), e o browser bloqueava o pedido real com `net::ERR_FAILED` — manifestando-se como "erro de CORS" enganador, quando na verdade era um header desconhecido.
  - **Frontend** (`frontend/src/pages/WebmailPage.jsx`): Substituídas as 3 ocorrências de `"X-Active-Company"` por `"X-Company-Id"` (linhas 465, 609, 637). Isto alinha o `WebmailPage` com: (a) o resto do frontend, que usa `X-Company-Id` via interceptor do `api.js` (linha 149); (b) o backend, que lê `X-Company-Id` em `services/auth.py`; (c) a config CORS de produção. Adicionado comentário explicativo a documentar que **deve** ser `X-Company-Id` (não `X-Active-Company`) para evitar regressão futura.
  - **Backend**: **Sem alterações** — o endpoint `POST /api/emails/webmail/sync-user` já lia o `company_id` do header `X-Company-Id` (via `get_active_company_id_async`) e do query param `company_id`. A config CORS (`render.yaml` `CORS_ALLOW_HEADERS`) já incluía `X-Company-Id`. O bug era exclusivamente do frontend a enviar o nome errado do header.

### Diagnóstico detalhado
1. Verificado o endpoint de debug `GET /api/cors-debug?origin=https://www.powercell.pt` em produção → confirmou que `https://www.powercell.pt` está na lista `explicit_origins` e `would_be_allowed: true`.
2. Simulado preflight OPTIONS **sem** o header problemático → devolveu 200 OK com headers CORS corretos.
3. Simulado preflight OPTIONS **com** `Access-Control-Request-Headers: authorization,x-active-company` → devolveu **HTTP 400** (header não permitido). Isto reproduziu exatamente o erro do browser.
4. Grep ao código revelou a incompatibilidade: frontend `WebmailPage` usava `X-Active-Company` (3 sítios) enquanto tudo o resto (interceptor `api.js`, backend `auth.py`, config CORS) usa `X-Company-Id`.

### Notas
- O erro era **intermitente** dependendo de se o `activeCompanyId` estava definido. Quando estava vazio (sem empresa selecionada), o header não era enviado e o pedido funcionava. Quando o utilizador tinha empresa ativa, o header `X-Active-Company` era enviado e o preflight falhava com 400.
- A linha 859 do `WebmailPage.jsx` já usava `X-Company-Id` corretamente — evidência adicional de que `X-Active-Company` era um typo/legacy.

## [2026-06-18] — Hotfix: Dropdown de Estado do Processo Vazia

### Corrigido
- **Dropdown de estado nos Detalhes do Processo aparecia vazia** (`fix` — **UX CRÍTICO**): O `<Select>` de fase/estado em `ProcessDetails.js` ficava em branco quando a lista dinâmica `workflowStatuses` (vinda de `/admin/workflow-statuses`) estava vazia ou o pedido falhava. O `safeStatusOptions` anterior tinha um `return []` prematuro (`if (!workflowStatuses.length) return [];`) que ignorava totalmente o fallback — mesmo havendo um `process.status` válido, nenhuma opção era renderizada e o `<SelectValue />` aparecia vazio. O `value={status}` (mapeado a `process.status` via estado `status` inicializado em `fetchData`) estava correto, mas sem opções a dropdown mostrava apenas o placeholder. `frontend/src/pages/ProcessDetails.js`.

### Adicionado
- **Baseline estático de estados do workflow** (`feat` — **RESILIÊNCIA**): Criado `frontend/src/utils/workflowStatuses.js` com a constante `KNOWN_PROCESS_STATUSES` — todos os estados conhecidos do backend: os 16 canónicos do enum `ProcessStatus` (`backend/models/enums.py`: `pre_registo`, `clientes_espera`, `documentacao`, `analise`, `pre_aprovacao`, `credito_aprovado`, `pedido_avaliacao`, `avaliacao`, `cpcv`, `minuta`, `escritura`, `concluido`, `arquivo`, `perdido`, `desistencias`, `fila_espera`) + estados legacy de seeds antigos (`triagem`, `aprovado`, `recusado`, `desistido`, `cancelado`, `concluidos`, `fase_documental`, `fase_documental_ii`, `enviado_bruno`, `enviado_luis`, `enviado_bcp_rui`, `entradas_precision`, `fase_bancaria`, `fase_visitas`, `ch_aprovado`, `fase_escritura`, `escritura_agendada`), cada um com `label` (PT-PT), `color` e `order`. Esta lista serve de baseline quando a API devolve vazio, garantindo que a dropdown nunca fica em branco.
- **Helper `buildStatusOptions(workflowStatuses, currentStatus)`** (`feat`): Função partilhada que constrói as opções do `<Select>` de estado com 3 níveis de garantia: (1) se a lista dinâmica da API tiver itens, usa-a (respeita a configuração do admin — label/color/order dele prevalecem); (2) se estiver vazia/falhar, recorre ao baseline estático `KNOWN_PROCESS_STATUSES`; (3) **fallback de segurança** — se o `currentStatus` (process.status) não existir na base escolhida, injeta-o como opção extra com label formatada (underscores → espaços + capitalização) marcada com `_isFallback: true`, exibida como `⚠ {Label} (não configurado)`. O resultado é ordenado por `order`.
- **Helper `formatStatusLabel(statusName)`** (`feat`): Converte nomes técnicos em labels legíveis (ex: `clientes_espera` → `Clientes Espera`, `pre_registo` → `Pre Registo`). Extraído do componente para o utilitário partilhado para reutilização.

### Alterado
- **`safeStatusOptions` agora delega em `buildStatusOptions`** (`refactor`): O `useMemo` em `ProcessDetails.js` passou a chamar `buildStatusOptions(workflowStatuses, status)` em vez de re-implementar a lógica inline. O `formatStatusLabel` local foi removido (agora importado do utilitário). O `getStatusInfo` (usado no badge de estado) continua a usar `workflowStatuses.find(...)` com fallback para `formatStatusLabel`, agora via o import partilhado.

### Notas
- O `<Select>` mantém-se controlado por `value={status}` (estado `status` inicializado de `processData.status` em `fetchData`, atualizado via `onValueChange={setStatus}`). Não há `defaultValue` — o componente é totalmente controlado, pelo que o estado exibido reflete sempre `process.status` (ou o valor em edição).
- A dropdown respeita a configuração do admin quando a API responde com sucesso; o baseline estático só entra em ação quando a API falha/devolve vazio. O fallback final garante que um `process.status` desconhecido (legacy, renomeado, ou de outro ambiente) é sempre visível e selecionável.

## [2026-06-18] — Assinatura de Email por Empresa Ativa + Pré-visualização no Composer

### Corrigido
- **Assinatura de email usava a empresa default em vez da empresa ativa** (`fix` — **FUNCIONALIDADE**): O `send_email` (`backend/services/email_service.py`) resolvia a assinatura pela empresa **default** do utilizador (`users.company`), ignorando a empresa ativa selecionada na sessão. Cada user pode ter uma assinatura diferente por empresa (UCR `user_company_roles.signature`), pelo que trocar de empresa ativa não mudava a assinatura do email enviado. Agora o `send_email` aceita `active_company_id` (lido do header `X-Company-Id` pelo endpoint) e a UCR da empresa ativa passa a ser a **prioridade 1** na resolução. Nova prioridade: (1) UCR empresa ativa → (2) `users.email_signature` (global) → (3) UCR empresa default → (4) UCR de qualquer empresa → (5) `system_smtp.email_signature`. Log inclui agora a origem da assinatura (`sig_source`) e o `active_company_id` para diagnóstico.
- **Endpoint `/send` não passava a empresa ativa ao `send_email`** (`fix`): O `POST /api/emails/send` (`backend/routes/emails.py`) não recebia `Request` nem resolvia o `active_company_id`. Adicionado `request: Request` ao endpoint, resolução via `get_active_company_id_async(request, current_user)` (lê header `X-Company-Id`), e passagem de `active_company_id` ao `send_email`.
- **Endpoint `/send-documentation` não passava a empresa ativa** (`fix`): Aplicada a mesma correção ao `POST /api/emails/send-documentation/{process_id}` e à função `_send_documentation_email_impl` (agora aceita `request: Optional[Request] = None`), propagando o `active_company_id` ao `send_email` (mesmo em `force_system=True`, a assinatura continua a ser resolvida pelo `created_by`+`active_company_id`).
- **Composer do Webmail não enviava o header `X-Company-Id`** (`fix`): O `handleSendEmail` (`frontend/src/pages/WebmailPage.jsx`) usava `fetch` direto sem o header `X-Company-Id` (que o interceptor do axios envia automaticamente). Agora envia `X-Company-Id: {activeCompanyId}` quando disponível, para o backend resolver a assinatura da empresa ativa.
- **Resposta rápida (EmailViewerModal) não enviava o header `X-Company-Id`** (`fix`): O `sendReply` lê agora `activeCompanyId` do `sessionStorage` (igual ao axios) e envia o header `X-Company-Id`.

### Adicionado
- **Pré-visualização da assinatura no composer do Webmail** (`feat` — **UX**): O composer agora mostra a assinatura que será anexada automaticamente no envio (caixa tracejada sob o corpo do email), usando a assinatura resolvida no frontend: prioridade `active_company_signature` (se != null) > `email_signature`. Renderiza o HTML sanitizado via `sanitizeEmailHtml` (DOMPurify). Se não houver assinatura configurada, mostra a dica "Sem assinatura configurada — pode definir a sua em Perfil > Assinatura de Email.". `frontend/src/pages/WebmailPage.jsx`.

### Notas
- A assinatura continua a ser injetada **no backend** (no corpo MIME, antes do envio) — a pré-visualização do composer é meramente informativa e não é enviada no `body` (evita duplicação).
- Emails automáticos do sistema (magic link do portal, notificações, RGPD) continuam a usar `force_system` sem `created_by` → assinatura do sistema (comportamento inalterado).

## [2026-06-18] — Webmail: Seletor de Conta no Composer e Erro 403 ao Enviar

### Corrigido
- **Seletor de conta no composer visível para perfis sem acesso a contas globais** (`fix` — **UX**): O seletor "Conta:" (Precision Crédito / Power Real Estate) aparecia no composer do Webmail para TODOS os utilizadores, incluindo perfis não-admin (consultor, intermediário, administrativo, indexação) que só podem enviar pela conta pessoal. Isto confundia o utilizador ("pede para escolher a conta" mesmo tendo um só perfil) e induzia o envio com `account=power`/`precision`, que o backend rejeita. Agora o seletor só é apresentado a admin/CEO/diretor (`canUseGlobalAccounts = hasAnyRole(user, ['admin','ceo','diretor'])`, alinhado com `can_use_global_accounts` do backend). Para os restantes perfis é mostrada uma nota informativa: "Envio pela sua conta pessoal — configure em Perfil > Configuração de Webmail" (ou "Envio pela conta partilhada de Indexação" para o role indexacao). `frontend/src/pages/WebmailPage.jsx`.
- **Erro 403 ao enviar email sem mensagem útil** (`fix` — **UX CRÍTICO**): O `handleSendEmail` descartava a resposta de erro do backend (`if (!response.ok) throw new Error("Erro ao enviar email")`) e mostrava um toast genérico, escondendo a mensagem acionável do backend: "Configuração de email pessoal não encontrada. Vá ao seu Perfil > Configuração de Webmail para configurar o seu email antes de enviar.". Agora o corpo do erro (`.detail` / `.message` / `.error`) é lido e exibido num toast com duração alargada (8s) para o utilizador saber o que fazer. `frontend/src/pages/WebmailPage.jsx`.
- **Conta enviada no pedido não refletia o perfil** (`fix`): Para perfis sem acesso a contas globais, o pedido enviava `account=power`/`precision` (default derivado do domínio do email). Agora envia `account=personal` (`effectiveAccount`), alinhado com o comportamento do backend que força "personal" para não-admin. `frontend/src/pages/WebmailPage.jsx`.
- **Resposta rápida (EmailViewerModal) sem feedback de erro** (`fix`): O `sendReply` engolia silenciosamente qualquer erro (apenas `console.error`), sem qualquer toast — o utilizador não sabia se a resposta foi enviada ou falhou. Adicionado `import { toast } from "sonner"`, leitura da mensagem de erro do backend, `from_box: "personal"` e `account=personal` no pedido, e toasts de sucesso/erro (duração 8s). `frontend/src/components/EmailViewerModal.js`.

### Notas
- O 403 do endpoint `POST /api/emails/send` para perfis não-admin sem `email_config` configurada é **comportamento pretendido** (isolamento de remetente — ver docstring da rota em `backend/routes/emails.py`). A correção foca-se em: (1) não oferecer contas globais a quem não as pode usar, e (2) tornar a mensagem de erro visível e acionável. O utilizador deve configurar o webmail pessoal em Perfil > Configuração de Webmail.

## [2026-07-17] — Pacote 1: Segurança de Dados, Soft Delete e UI Block

### Removido
- **Integração Trello — Deprecation completa** (`deprecation` — **CLEANUP**): Removida toda a integração do Trello do código. Apagados 5 ficheiros dedicados (`backend/routes/trello.py`, `backend/services/trello.py`, 2 testes, `frontend/src/components/TrelloIntegration.js`). Removidos imports e referências em 16 ficheiros: `server.py` (router + startup init), `config.py` (3 env vars), `models/process.py` (2 campos), `models/system_config.py` (TrelloConfig), `routes/processes.py` (3 sync calls), `routes/admin.py` (member auto-association), `routes/system_config.py` (section + test-connection), `routes/diagnostics.py` (check_trello_service), `services/system_config.py`, `services/task_queue.py`, `worker.py`, `SettingsPage.js`, `DiagnosticsPage.js`, `SystemConfigPage.js`, `ProcessDetails.js`, `api.js`, `UnifiedAuditTrail.js`.

### Corrigido
- **Soft Delete de Processos — Endpoint dedicado** (`fix` — **CRÍTICO**): Adicionado `DELETE /api/processes/{process_id}` que faz soft delete (`is_deleted: True`, `status: "eliminado"`) sem afetar o documento do cliente. Cascade para documentos e tarefas do processo. Registo de atividade no histórico.
- **DELETE /clients/{id} — Cascade delete de processos removido** (`fix` — **CRÍTICO**): Antes, apagar um cliente marcava TODOS os processos associados como eliminados. Agora apenas remove a referência `client_id` dos processos (unset), deixando-os intactos. A independência entre Cliente e Processo é garantida.
- **GET /clients/registered — Filtro is_deleted em falta** (`fix`): Adicionado `is_deleted: {"$ne": True}` na query para não devolver clientes eliminados.
- **GET /clients/me — Filtro is_deleted em falta** (`fix`): Adicionado filtro `is_deleted` na query.
- **Admin hard delete → soft delete** (`fix`): O endpoint `DELETE /admin/client-registrations/{process_id}` usava `delete_one()` (hard delete). Alterado para soft delete com `update_one()`.

### Alterado
- **Cartões de Processo em Read-Only (ProcessDetails)** (`feat` — **UX CRÍTICO**): Os cartões com informações (Contactos, Identificação, Rendimentos, Situação Financeira, Credenciais, Imóvel, Crédito) estão agora em modo de leitura por defeito. Adicionado estado `editingCard` (null por defeito) e componente `CardHeaderWithEdit` com ícone de Lápis no cabeçalho. Só ao clicar no lápis os campos ficam editáveis e aparecem os botões "Cancelar" e "Guardar". Permissões existentes (`canEdit*`, `isViewMode`, `isProcessLocked`) continuam a ser aplicadas. CSS `.read-only-card` torna inputs disabled visualmente limpos (sem borda, fundo transparente).
- **Uniformização de Nomenclatura** (`refactor` — **UX**): Substituído "Co-Proponente"/"Co-Comprador" por "2º Titular / Fiador" em todo o código user-facing: `ProcessDetails.js`, `CPCVModal.js`, `models/process.py`, `models/client.py`, `scripts/seed_completo.py`, e mais 8 ficheiros. Nomes de campos da BD (`co_buyers`, `co_applicants`) mantidos para retro-compatibilidade.

## [2026-07-16] — Correção Definitiva: React Error #31 + /api/clients 422

### Corrigido
- **React Minified Error #31 — Correção Definitiva** (`fix` — **STABILITY**): Os erros Pydantic `[{type, loc, msg, input}]` eram passados diretamente para `toast.error()`, `setError()` e JSX `{error}` em 80+ localizações no frontend, causando crash do React. Criada utilidade `extractErrorMessage()` em `frontend/src/utils/extractErrorMessage.js` que extrai mensagens `.msg` de arrays Pydantic. Aplicada em 55 ficheiros: todas as pages, components, e serviços que usam `toast.error(data.detail || fallback)`, `toast.error(error.response?.data?.detail || fallback)`, e padrões similares. O Axios interceptor (500+) também foi atualizado.
- **GET /api/clients → 422 Validation Error** (`fix` — **CRÍTICO**): Pydantic v2 rejeita strings vazias `""` para parâmetros `bool` e `int`. Quando o frontend enviava `?show_all=` ou `?limit=` (valores vazios), o backend retornava 422. Corrigido: `show_all`, `exclude_deleted`, `deleted_only` alterados de `bool` para `Optional[bool]`; `limit` e `skip` de `int` para `Optional[int]`. Defaults aplicados no corpo da função para valores `None`.
- **getClients() no api.js enviava valores vazios** (`fix`): A função `getClients()` agora filtra parâmetros `null`, `undefined` e `""` antes de enviar o request.

### Adicionado
- **Utilidade `extractErrorMessage()`** (`feat` — `frontend/src/utils/extractErrorMessage.js`): Função que converte qualquer resposta de erro (string, array Pydantic, objeto) numa string segura para uso em `toast.error()`, `setError()` e JSX. Previne React Error #31 permanentemente.

## [2026-07-15] — Correção de 4 Bugs Conhecidos + Sincronização Webmail

### Corrigido
- **Explorador de Ficheiros não mostra ficheiros S3** (`fix` — **CRÍTICO**): O `S3Service` lia apenas variáveis de ambiente na inicialização. Quando o admin configurava S3 via UI (`/configuracoes`), as credenciais eram guardadas na BD mas o serviço nunca as lia. Adicionado método `reconfigure()` ao S3Service e sincronização automática: (1) no startup via `sync_s3_from_db_config()`, (2) em tempo real quando a config de storage é atualizada via UI (`update_config_section`). O `_build_default_config()` agora também lê as variáveis AWS do ambiente.
- **Rota `/definicoes` vs `/configuracoes` no Explorador** (`fix` — **UX**): Quando o S3 não estava configurado, o banner "Ir para Configurações" enviava utilizadores não-admin para `/definicoes` (definições pessoais) em vez de `/configuracoes` (config do sistema). Corrigido: admins veem "Configurar Agora" + "Ir para Configurações" (`/configuracoes`); não-admins veem mensagem "Contacte um administrador".
- **React Minified Error #31 em ProcessDetails** (`fix` — **STABILITY**): Objetos `{value, label}` do backend eram renderizados como React children, causando crash. Adicionados `safeString()` wrappers em 10+ locais no `ProcessDetails.js` e 6+ no `ProcessDetailsModal.jsx`: título do processo, número, tipo, email do cliente, campos de reatribuição, comentários de atividade, deadlines, visitas, tipologia, localização, dados bancários.
- **500 Error em POST /api/documents/portal-requests/{processId}** (`fix`): Adicionada validação de `process_id` vazio (400), logging detalhado do input data no início e no except exterior para debugging post-mortem.

### Alterado
- **Sincronização Webmail — Enviados/Rascunhos/Lixo** (`fix` — **FUNCIONALIDADE**): O `_fetch_all_from_folder_sync` inferia a direção do email comparando `from_email == account.email`, o que é pouco fiável (casing, aliases). Adicionado `em["direction"] = "sent"` explícito após a obtenção de emails da pasta Sent IMAP nas 3 funções de sync: `sync_webmail_emails`, `sync_user_emails`, `sync_shared_role_emails`. Isto garante que emails enviados aparecem na pasta "Enviados" em vez de "Caixa de Entrada".

### Notas
- As funcionalidades "Filtro de documentos já solicitados" e "Multi-seleção de tipos de documento" já estavam implementadas no `PortalDocumentRequests.js` (linhas 128-139 e 292-319). O PRD foi atualizado para refletir isto.
- O PRD foi atualizado para marcar os 4 bugs como corrigidos e as 3 funcionalidades como completas.

## [2026-03-13] — Reestruturação da Área Pessoal: Login Comum + Dados Profissionais por Empresa

### Corrigido
- **Botão "Guardar Dados Profissionais" sem feedback visual** (`fix` — **UX**): Ao carregar no botão, o utilizador não obtinha qualquer indicação de sucesso ou erro. Adicionado estado visual: spinner durante o save → checkmark verde "Guardado!" por 2 segundos após sucesso. Toast agora menciona o nome da empresa ativa.

### Alterado
- **Reestruturação completa da Área Pessoal** (`refactor` — **UX CRÍTICO**): A página foi reorganizada para separar claramente os dados comuns (login) dos dados por empresa (profissionais):
  - **"Informação de Login"** (comum a todos os perfis) — Email (read-only), alteração de password, badge de role e empresa, data de registo. Sem botão de guardar.
  - **"Dados Profissionais"** (por empresa, com badge) — Nome, Telefone e Cargo/Função consolidados num único card com UM botão "Guardar Dados Profissionais". Os campos refletem sempre a empresa selecionada no Modo de Operação (ContextSwitcher).
  - **"Assinatura de Email"** (por empresa) — mantido.
  - **"Sessões Ativas"** (comum) — mantido.
- **Consolidação do campo Telefone** (`refactor`): Removida a duplicação entre "Telefone" (card Informação do Perfil) e "Telefone Profissional" (card Dados Profissionais). Agora existe UM campo "Telefone" nos Dados Profissionais que guarda como `professional_phone` no UCR e `phone` global para retro-compatibilidade.
- **Nome passou para Dados Profissionais** (`refactor`): O campo "Nome" foi movido do card de Informação do Perfil para Dados Profissionais, permitindo que o nome apresentado seja específico por empresa.

### Adicionado
- **Campo `display_name` por empresa no UCR** (`feat` — `backend/routes/auth.py`, `backend/services/auth.py`): Novo campo `display_name` na coleção `user_company_roles` que permite ao utilizador ter um nome de apresentação diferente por empresa. O GET /auth/me faz merge: se `active_company_display_name` existe, sobrepõe o `name` global.
- **`active_company_display_name` na resposta do GET /auth/me** (`feat`): O endpoint agora retorna o campo `active_company_display_name` com a mesma lógica de `null` vs `""` dos outros campos UCR.
- **`display_name` no `update_profile`** (`feat`): O PUT /auth/profile aceita e persiste `display_name` na coleção `user_company_roles`.
- **Projeção MongoDB expandida** (`feat` — `backend/services/auth.py`): `get_user_companies()` agora inclui `display_name` na projeção.

### Notas
- MongoDB é schemaless — o campo `display_name` é automaticamente disponível sem migração
- O campo global `name` (users collection) continua a ser guardado para retro-compatibilidade
- Se `display_name` não está definido no UCR, o sistema usa o `name` global

## [2026-03-12] — Afinação Crítica Multi-Tenant: Reatividade de Contexto, Perfis e Assinaturas

### Corrigido
- **Ecrãs de Área Pessoal e E-mail não atualizam ao trocar de empresa** (`fix` — **CRÍTICO**): Quando o utilizador alterava a empresa no ContextSwitcher, os ecrãs de Área Pessoal (assinatura, cargo, telefone) e E-mail (config IMAP/SMTP) permaneciam com dados da empresa anterior. Causa raiz: o `useEffect` no `ProfilePage.js` dependia apenas de `[user]`, sem `effectiveCompanyId`. O `EmailConfigForm.jsx` dependia apenas de `[companyId]` (prop), sem `effectiveCompanyId` direto do `useAuth()`. E o `switchActiveCompany()` no `AuthContext.js` não recarregava os dados do utilizador após a troca.
- **Assinatura de email era global, não por empresa** (`fix`): O campo `email_signature` estava guardado no documento global do utilizador, fazendo com que a mesma assinatura fosse usada independentemente da empresa ativa. Agora a assinatura é guardada por empresa na coleção `user_company_roles`.

### Alterado
- **Modelo UserCompanyRole expandido com campos por empresa** (`refactor` — `backend/models/user_company_role.py`): Adicionados 3 campos opcionais ao `UserCompanyRoleCreate`, `UserCompanyRoleUpdate` e `UserCompanyRoleResponse`:
  - `signature: Optional[str]` — Assinatura de email HTML/Texto específica para esta empresa
  - `professional_phone: Optional[str]` — Telefone profissional específico para esta empresa
  - `job_title: Optional[str]` — Cargo específico nesta empresa
- **GET /api/auth/me retorna campos específicos da empresa ativa** (`refactor` — `backend/routes/auth.py`): O endpoint agora inclui `active_company_signature`, `active_company_professional_phone` e `active_company_job_title` na resposta, extraídos da associação `user_company_roles` da empresa ativa.
- **PUT /api/auth/profile suporta campos específicos por empresa** (`refactor` — `backend/routes/auth.py`): Os campos `signature`, `professional_phone` e `job_title` são agora guardados na coleção `user_company_roles` para a empresa ativa (determinada pelo header `X-Company-Id`), mantendo o campo global `email_signature` para retro-compatibilidade.
- **`get_user_companies()` retorna campos por empresa** (`refactor` — `backend/services/auth.py`): A projeção MongoDB foi expandida para incluir `signature`, `professional_phone` e `job_title`.
- **Rota de user_company_roles suporta novos campos** (`refactor` — `backend/routes/user_company_roles.py`): Os endpoints `POST` e `PUT` agora aceitam e persistem `signature`, `professional_phone` e `job_title`.

### Adicionado
- **Reatividade do AuthContext à mudança de empresa** (`feat` — `frontend/src/contexts/AuthContext.js`): A função `switchActiveCompany()` agora chama `GET /auth/me` após a troca de empresa, garantindo que os dados do utilizador (incluindo campos específicos da nova empresa) são atualizados no estado global.
- **useEffect com `[user, effectiveCompanyId]` no ProfilePage** (`feat` — `frontend/src/pages/ProfilePage.js`): Os campos da Área Pessoal (assinatura, cargo, telefone profissional) são agora atualizados automaticamente quando a empresa ativa muda. O `effectiveCompanyId` está no array de dependências do useEffect.
- **useEffect com `[companyId, effectiveCompanyId]` no EmailConfigForm** (`feat` — `frontend/src/components/EmailConfigForm.jsx`): A configuração de email é recarregada automaticamente quando o ContextSwitcher muda a empresa ativa.
- **Card "Dados Profissionais" no ProfilePage** (`feat` — `frontend/src/pages/ProfilePage.js`): Nova secção com campos "Cargo / Função" e "Telefone Profissional" específicos para a empresa ativa, com badge a indicar a empresa ativa.
- **Assinatura de email por empresa** (`feat` — `frontend/src/pages/ProfilePage.js`): A secção de assinatura agora mostra a empresa ativa e guarda a assinatura no contexto da empresa, não globalmente.
- **Filtro de templates de email por empresa** (`feat` — `backend/routes/emails.py`): O endpoint `GET /emails/templates` agora filtra templates por `company_id` da empresa ativa, mostrando apenas templates da empresa + templates globais (sem `company_id`). O endpoint `POST /emails/templates` agora associa automaticamente o `company_id` ao template criado.
- **Campo `company_id` no EmailTemplateResponse** (`feat` — `backend/models/email.py`): Adicionado `company_id: Optional[str] = None` ao modelo de resposta.

### Revisão de Fugas de Contexto
- ✅ **Templates de Email**: Filtrados por `company_id` ativo (templates globais sem `company_id` são partilhados)
- ✅ **Notificações Push**: Apenas filtradas por `user_id` (contexto de empresa não aplicável — notificações são pessoais)
- ✅ **Configuração de Email**: Já filtrada por `company_id` via `X-Company-Id` header

### Notas
- MongoDB é schemaless — os novos campos são automaticamente disponíveis sem migração
- Templates existentes sem `company_id` são tratados como globais (visíveis para todas as empresas)
- O campo global `email_signature` no utilizador é mantido para retro-compatibilidade
- A duplicação de `email_signature` (global + por empresa) é temporária — numa futura versão, o campo global pode ser removido

## [2026-06-11] — Atribuição de Registos à Tania Fernandes (Dev)

### Alterado
- **9 processos sem mediador atribuídos à Tania Fernandes** (`ops` — **DEV**): Todos os processos no ambiente de desenvolvimento que não tinham intermediário atribuído foram atribuídos à utilizadora **Tania Fernandes** (ID: `bc2a5a7f-0645-4e38-bdc3-91fd4c2f1c47`, role: `intermediario`, empresa: Precision Crédito). Os 9 processos estavam no estado `clientes_espera` e sem mediador. Atribuição realizada via API `POST /api/processes/{id}/assign?mediador_ids={user_id}` com autenticação admin.

### Processos Atribuídos
| # | Cliente | Estado |
|---|---------|--------|
| 94 | Camila Baptista Lima | clientes_espera |
| 150 | Cristina Reis Silva Carneiro | clientes_espera |
| 102 | Duarte Barbosa Silva | clientes_espera |
| 118 | Fernanda Correia Ribeiro Machado | clientes_espera |
| 130 | Fernanda Silva Correia Antunes | clientes_espera |
| 82 | Isabel Carvalho Costa Soares | clientes_espera |
| 174 | Isabel Vieira Martins Barbosa | clientes_espera |
| 56 | Joana Baptista Soares Cruz | clientes_espera |
| 202 | João Dias Tavares | clientes_espera |

### Notas
- Total de processos no dev: 20
- Processos da Tania após atribuição: 9 (45%)
- Processos de outros intermediários: 11
- Processos sem mediador: 0
- Operação realizada diretamente na BD de dev via API

## [2026-06-10] — Correção CORS Definitiva: Header X-Company-Id em Falta + Fallback Middleware

### Corrigido
- **CORS: Header `X-Company-Id` não estava nos `CORS_ALLOW_HEADERS` do Render** (`fix` — **CAUSA RAIZ REAL**): O erro "Response to preflight request doesn't pass access control check: It does not have HTTP ok status" era causado pelo facto de o Render Dashboard ter um valor personalizado para `CORS_ALLOW_HEADERS` que NÃO incluía `X-Company-Id`. Quando o frontend enviava um pedido preflight com `Access-Control-Request-Headers: ...,X-Company-Id`, o CORSMiddleware retornava HTTP 400 "Disallowed CORS headers" em vez de HTTP 200. O browser interpretava este 400 como falha do preflight. Diagnosticado com:
  ```
  curl -X OPTIONS -H "Access-Control-Request-Headers: Authorization,Content-Type,X-Company-Id" ...
  → HTTP 400 "Disallowed CORS headers"
  ```
- **CORS: Vercel preview URLs podiam falhar sem mecanismo de fallback** (`fix` — **DEFESA EM PROFUNDIDADE**): O `ALLOW_VERCEL_PREVIEWS` podia estar desativado no Render Dashboard (override manual), invalidando o regex do `CORSMiddleware`
- **Handler 422 com headers CORS inválidos** (`fix`): O `validation_exception_handler` usava `Access-Control-Allow-Origin: *` com `credentials=true`, o que é rejeitado pelos browsers

### Adicionado
- **Vercel CORS Fallback Middleware** (`feat` — `server.py`): Middleware outermost que intercepta pedidos preflight OPTIONS de `*.vercel.app` e retorna HTTP 200 com headers CORS correctos, mesmo que o `CORSMiddleware` falhe
- **Endpoint de diagnóstico CORS** (`feat` — `server.py`): `GET /api/cors-debug?origin=URL` para verificar se uma origin seria permitida
- **Proteção de headers obrigatórios em config.py** (`feat`): Os headers `X-Active-Role` e `X-Company-Id` são agora SEMPRE adicionados a `CORS_ALLOW_HEADERS`, mesmo que a variável de ambiente os omita. Isto evita que overrides no Render Dashboard quebrem o CORS
- **CORS_ALLOW_HEADERS e CORS_ALLOW_METHODS explícitos no render.yaml** (`feat`): Variáveis adicionadas ao blueprint do Render para garantir que o Dashboard não usa valores desatualizados

## [2026-06-06] — Correção CORS: Vercel Preview URLs e Headers em Falta

### Corrigido
- **CORS bloqueia Vercel preview URLs** (`fix` — **CRÍTICO**): O frontend deployado em Vercel (branch `dev`) era bloqueado pelo backend no Render com erro CORS "It does not have HTTP ok status". Causas identificadas:
  - `CORS_ORIGINS` no `render.yaml` não incluía `powercell-1.onrender.com` nem qualquer domínio Vercel
  - `ALLOW_VERCEL_PREVIEWS` não estava explicitamente definido no `render.yaml`, podendo ser sobrescrito no dashboard do Render
  - O regex CORS `r"https://[a-z0-9-]+\.vercel\.app"` era demasiado restritivo para subdomínios longos
  - O header `X-Company-Id` (enviado pelo frontend) não estava nos `CORS_ALLOW_HEADERS`

### Alterado
- **render.yaml: CORS_ORIGINS expandido** (`refactor`): Adicionado `powercell-1.onrender.com` à lista de origens explícitas. Adicionada variável `ALLOW_VERCEL_PREVIEWS=true` explicitamente para garantir que o regex CORS cubra qualquer `*.vercel.app`
- **config.py: Regex CORS mais robusto** (`refactor`): Regex atualizado de `r"https://[a-z0-9-]+\.vercel\.app"` para `r"https://[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.vercel\.app(?::\d+)?$"` — suporta subdomínios longos como `power-cell-git-dev-power-precisions-projects.vercel.app` e opcionalmente porta. Adicionado log quando `ALLOW_VERCEL_PREVIEWS` está desativado
- **config.py: CORS_ALLOW_HEADERS atualizado** (`refactor`): Adicionado `X-Company-Id` aos headers permitidos (usado pelo ContextSwitcher multi-empresa no frontend)
- **server.py: Middleware de debug CORS** (`refactor`): Novo middleware que regista no log origins rejeitadas durante preflight OPTIONS, facilitando diagnóstico de problemas CORS em produção. Adicionado log da configuração CORS completa no arranque

## [2026-05-24] — Correções: Timeout IRS e Anexos no Email de Sucesso

### Corrigido
- **Timeout ao descarregar Declaração de IRS do Portal das Finanças** (`fix` — **CRÍTICO**): O scraper falhava com timeout ao navegar pelos menus do Portal das Finanças para aceder à página de IRS. A navegação por menus intermédios era lenta e sujeita a timeouts, especialmente em ambientes com latência (Render). Corrigido com navegação directa para a página de comprovativos:
  - `gov_scraper.py` passo 6: Em vez de procurar o link "IRS" no menu, navega directamente para `https://irs.portaldasfinancas.gov.pt/comprovativo/obterComprovativo.action` com timeout de 90s
  - Fallback encadeado: navegação directa → menu → URL legada, garantindo resiliência
  - `_download_financas_document()` v3: Nova "Estratégia 0" que procura o botão "Obter Comprovativo" e ícones PDF na tabela de comprovativos antes das estratégias anteriores
  - `expect_download()` protegido com try/catch explícito em cada estratégia — erro de download já não crasha o scraper
  - Fallback de emergência com `page.pdf(format='A4')` protegido por try/catch com logging detalhado do erro

- **Email de sucesso enviado sem documentos anexados** (`fix` — **CRÍTICO**): Após o scraper obter com sucesso os documentos das Finanças e Seg. Social, o email de confirmação enviado ao cliente não incluía os PDFs como anexos. O cliente recebia um email a dizer "documentos obtidos com sucesso" mas sem acesso direto aos ficheiros. Corrigido em 3 camadas:
  - `_send_portal_fetch_email()` (portal.py): Adicionado parâmetro `attachments: list = None` — os documentos são anexados apenas no email de status "success"
  - Chamada a `send_email()` do `email_service.py` agora passa `attachments` — suporta tanto Resend API como SMTP directo (MIMEMultipart + MIMEApplication)
  - SMTP fallback (portal.py): Construção da mensagem MIME atualizada para suportar anexos PDF com `MIMEMultipart("mixed")` + iteração sobre os attachments
  - `_run_financas_scraper()` e `_run_seguranca_social_scraper()`: Agora retornam `{"documents": [...]}` com os bytes de cada documento, além do `documents_count`
  - Background tasks (`_run_financas_background`, `_run_seguranca_social_background`): Mapeiam `docs_to_attach = result.get("documents", [])` e passam-nos ao email de sucesso

### Alterado
- **`_download_financas_document()` promovido a v3** (`refactor`): Reorganização das estratégias de download com prioridade explícita:
  - Estratégia 0 (NOVA): Botão "Obter Comprovativo" na página de comprovativos
  - Estratégia 1: Links/botões de download direto (mantida)
  - Estratégia 2: Navegação para sub-página (mantida)
  - Estratégia 3: Fallback page.pdf() com try/catch e logging detalhado
- **Timeout do `expect_download` aumentado para 90s** na Estratégia 0 (comprovativo) — o botão nativo pode demorar a iniciar o download em conexões lentas

## [2026-03-11] — Afinamento de Permissões: Quadro Geral para Indexação

### Alterado
- **Menu 'Quadro Geral' adicionado para role indexação** (`refactor` — **RBAC**): O utilizador com role `indexacao` não tinha acesso ao Quadro Geral (Kanban) no menu lateral, impedindo-o de marcar processos como concluídos diretamente no quadro. Adicionado item `{ label: "Quadro Geral", icon: LayoutGrid, href: "/kanban" }` ao grupo "Listas de Trabalho" da role `indexacao` no `DashboardLayout.js`. O "Registo de Clientes" mantém-se oculto para esta role.

### Notas
- Verificação completa do código: Todos os bugs reportados já estavam resolvidos em sessões anteriores:
  - ✅ CORS/Timeout Scraper: `BackgroundTasks` já implementado nos endpoints `/fetch-financas` e `/fetch-seguranca-social`
  - ✅ Portal do Cliente: Refresh da lista de visitas já forçado após submissão
  - ✅ CRM: Visitas já são clicáveis com `VisitDetailsModal` completo
  - ✅ Botão "Marcar Trabalho Concluído": já visível para `indexacao` E `admin`
  - ✅ "Registo de Clientes": já oculto para role `indexacao`
  - ✅ Excel export: já inclui NIF, Telefone, Consultor Responsável, Indexado

## [2026-03-10] — Correções Críticas: CORS/Timeout Scraper, Visitas, Indexação e Excel

### Corrigido
- **CORS e 502 Bad Gateway no Scraper de Finanças/Seg. Social** (`fix` — **CRÍTICO**): Os endpoints `POST /api/portal/fetch-financas` e `POST /api/portal/fetch-seguranca-social` executavam o scraper Playwright de forma síncrona, causando timeout do Render (30s) e erro 502/CORS:
  - Ambos os endpoints agora usam `BackgroundTasks` do FastAPI
  - Respondem IMEDIATAMENTE com HTTP 200 `{"status": "processing", "message": "A obter documentos em background"}`
  - Execução pesada do `gov_scraper` corre em background via `_run_financas_background()` e `_run_seguranca_social_background()`
  - Novo endpoint `GET /api/portal/scraper-job/{job_id}` para polling do estado pelo frontend
  - Job registado na coleção `portal_scraper_jobs` (MongoDB) com status processing/success/error
  - Notificações WebSocket e email disparadas quando o background task completa
  - Rotas `/api/portal/*` já cobertas pelo middleware CORS global (config.py adiciona www/non-www variants)
- **Portal do Cliente: visita não aparece após submissão** (`fix` — **UX**): Após submeter com sucesso um pedido de visita, o cartão 'As Minhas Visitas' não atualizava sem refresh da página:
  - Refresh da lista de visitas agora forçado imediatamente após submissão com try/catch seguro
  - Antes: `fetch()` sem tratamento de erro podia falhar silenciosamente
- **CRM: visitas do portal não eram clicáveis** (`fix` — **UX**): Na Aba Visitas do ProcessDetailsModal, não existia forma de ver detalhes completos:
  - Cada visita agora é clicável (cursor-pointer + hover)
  - Adicionado `VisitDetailsModal` com: Foto do Imóvel, Preço, Tipologia, Morada completa, URL do anúncio, Comentários, Data agendada, Consultor, Badge "Pedido pelo Cliente via Portal"

### Alterado
- **Botão 'Marcar Trabalho Concluído' agora visível para admin** (`refactor` — **Permissões**): A lógica de visibilidade foi alterada de `role === 'indexacao'` para `role === 'indexacao' || role === 'admin'`, permitindo testes administrativos do fluxo de indexação sem necessidade de trocar de role.
- **Menu 'Registos de Clientes' removido para role indexação** (`refactor` — **RBAC**): O item "Registos de Clientes" foi removido do menu da role `indexacao` no DashboardLayout — este perfil não necessita de acesso a registos de clientes, apenas a "Os Meus Processos" e "Documentos Pendentes".

### Adicionado
- **Colunas extra na Exportação Excel** (`feat` — **FRONTEND**): O KanbanPage export enriquecido com 4 novas colunas:
  - `NIF` — NIF do cliente (`p.client_nif || p.personal_data?.nif`)
  - `Telefone` — Telefone do cliente (`p.client_phone || p.contacto?.telefone`)
  - `Consultor Responsável` — Nome do consultor (renomeado de "Consultor" para clareza)
  - `Indexado` — Estado de indexação (`p.is_indexed ? 'Sim' : 'Não'`)
  - Colunas anteriores mantidas: Processo, Cliente, Fase, Valor

## [2026-03-09] — Melhorias Operacionais: Indexação, Exportação Excel e Fix Portal Visitas

### Adicionado
- **Estado de Conclusão da Indexação** (`feat` — **BACKEND + FRONTEND**): Novo campo `is_indexed` (booleano, default false) no modelo de Processos que permite ao perfil de Indexação marcar o tratamento documental como concluído:
  - Modelo: Adicionado `is_indexed` ao `ProcessUpdate` e `ProcessResponse` em `backend/models/process.py`
  - Backend: Novo endpoint `PATCH /processes/{id}/mark-indexed` — apenas role `indexacao` pode marcar; quando `is_indexed` passa a `true`, dispara automaticamente uma notificação (email + in-app + WebSocket) para todos os utilizadores atribuídos ao processo com a mensagem: "A Indexação concluiu o tratamento documental do processo [Ref] — [Nome Cliente]"
  - Frontend KanbanCard: Badge "✅ Indexado" (verde) visível quando `is_indexed=true`
  - Frontend ProcessDetailsModal: Badge "✅ Indexado" na tab Processo + botão "Marcar Trabalho Concluído" (verde) visível apenas para role `indexacao` quando o processo ainda não está indexado
  - Registo no histórico: `INDEXACAO_CONCLUIDA` com detalhes de quem marcou e quando
- **Exportação para Excel** (`feat` — **FRONTEND**): Botão "Exportar Excel" na barra de filtros do Kanban que exporta todos os processos visíveis (após filtros) para um ficheiro `.xlsx`:
  - Biblioteca SheetJS (`xlsx`) instalada no frontend com importação dinâmica (lazy loading)
  - Colunas exportadas: Nome do Cliente, Nº Processo, Fase/Status, Valor Imóvel, Consultor, Intermediário, Prioridade, Indexado, Atualizado
  - Larguras de coluna otimizadas e nome de ficheiro com data: `PowerCell_Processos_YYYY-MM-DD.xlsx`
  - Botão com estado de loading (spinner) durante a exportação

### Corrigido
- **Portal de Visitas: frontend fica a pensar infinitamente** (`fix` — **CRÍTICO**): O endpoint `POST /portal/visits/request` invocava o scraper do Idealista de forma síncrona (5-15s), bloqueando a resposta ao cliente. O portal ficava com loading infinito e a visita não se associava ao processo:
  - Backend: Reescrito com `BackgroundTasks` do FastAPI — o endpoint agora: (1) Procura o processo ativo do cliente e guarda o `_id` como `process_id` na visita; (2) Cria a visita na BD IMEDIATAMENTE com status `solicitada` e `scraper_status: "pending"`; (3) Coloca a execução do scraper em `BackgroundTask` (que atualizará a visita na BD depois de extrair foto/preço); (4) Devolve status 200 IMEDIATAMENTE para libertar o frontend
  - Nova função `_background_visit_scraper_and_notify()`: Executa em background após o 200 — invoca o scraper, atualiza a visita com dados extraídos, notifica a equipa atribuída e faz broadcast WebSocket
  - Frontend: Botão "Pedir Visita" agora mostra "A enviar..." em vez de "A extrair dados..." — mensagem de sucesso atualizada para refletir o processamento assíncrono
  - `try/catch/finally` já existia no ClientPortal.jsx — confirmado que `setIsLoading(false)` e limpeza do URL estão corretos no `finally`

## [2026-03-08] — Correções Críticas: Sidebar, Edição Retroativa e Sincronização Financeira

### Corrigido
- **Sidebar recolhe indevidamente ao navegar para páginas de detalhe** (`fix` — **UX CRÍTICO**): Ao abrir `/processo/:id` ou `/cliente/:id`, os submenus laterais (O Meu Negócio, Visão Global, etc.) colapsavam porque `computedOpenSections` não incluía as rotas de detalhe na correspondência. Corrigido em `DashboardLayout.js`:
  - Adicionadas rotas de detalhe (`/processo`, `/imovel`, `/cliente`) aos arrays de correspondência de secções
  - Lógica de sincronização de `openSections` alterada de substituição total para apenas expansão — ao navegar para uma rota filha, a secção abre-se automaticamente; mas o utilizador pode fechar manualmente sem que a navegação a reabra
  - Container principal recebeu `min-w-0` e `max-w-full` para evitar que conteúdo largo "empurre" a sidebar no desktop
- **Processos concluídos bloqueiam edição para admin/CEO** (`fix` — **UX CRÍTICO**): Os inputs e o botão "Guardar Alterações" estavam desativados para processos em estado terminal (Concluído/Escritura), mesmo para admin e CEO. Corrigido em `ProcessDetails.js`:
  - `isProcessLocked` agora exclui roles `admin` e `ceo` — estes podem editar processos concluídos
  - `isViewMode` e todas as verificações `!isProcessLocked` passam a permitir interação para admin/CEO
  - Adicionado banner informativo azul (com ícone Shield) que avisa que o processo está em estado terminal mas o utilizador pode editar retroativamente

### Adicionado
- **Sincronização Financeira Retroativa** (`feat` — **BACKEND CRÍTICO**): Quando um admin/CEO edita um processo concluído/escritura, o backend agora garante que o snapshot financeiro (`ProcessFinance`) existe e está atualizado com os novos valores:
  - Nova função `_ensure_finance_snapshot()` em `processes.py`: se não existe snapshot → cria novo; se já existe → recalcula comissões com base nos novos valores e configurações atuais da empresa
  - PUT `/processes/{id}` permite edição de processos terminais por admin/CEO (antes retornava 403)
  - Após cada update por admin/CEO em processo com status `concluidos`/`escritura`/`escritura_agendada`, o sistema chama `_ensure_finance_snapshot()` automaticamente
  - Proteção contra falhas: erro no snapshot não impede a atualização do processo

## [2026-03-07] — Módulo Financeiro: Modelo de Distribuição Pool Global

### Adicionado
- **Enum `DistributionModel` no modelo FinanceConfig** (`feat` — `backend/models/finance.py`): Novo enum com valores `individual_split` (cada consultor recebe a comissão dos seus processos — modelo tradicional) e `global_pool` (todas as comissões do mês são somadas e divididas igualmente pelos consultores ativos). Campo `distribution_model` adicionado a `FinanceConfig`, `FinanceConfigCreate`, `FinanceConfigUpdate` e `FinanceConfigResponse` com default `individual_split` para retro-compatibilidade.
- **Endpoint GET /finance/pool-distribution** (`feat` — `backend/routes/finance.py`): Novo endpoint que calcula a distribuição do Pool Global para um mês/ano. Lógica: (1) soma `expected_commission` de todos os ProcessFinances com status `paid` ou `invoiced` no período, filtrando por `company_id` → `total_pool`; (2) conta utilizadores ativos com role `consultor` ou `intermediario` na empresa (incluindo `additional_roles`) → `total_consultants`; (3) retorna `pool_per_consultant = total_pool / total_consultants` com proteção de divisão por zero. Inclui lista de consultores e breakdown imobiliária/crédito.
- **Seletor de Modelo de Distribuição no HonorariosDialog** (`feat` — `frontend/src/pages/FinanceDashboard.js`): Dois botões toggle no modal de Configuração de Honorários — "Individual" (roxo) e "Pool Global" (verde-esmeralda) — com aviso contextual explicando o modelo Pool. Estado persistido no campo `distribution_model` da FinanceConfig via API.
- **Aba "Distribuição" no Dashboard Financeiro** (`feat` — `frontend/src/pages/FinanceDashboard.js`): Nova tab condicional que aparece apenas quando o modelo de distribuição é `global_pool`. Contém o componente `PoolDistributionPanel` com: seletor de mês/ano, 3 KPI cards (Total Faturado no Mês, Consultores Ativos, Valor por Consultor), breakdown imobiliária/crédito, e grid de avatares dos consultores no Pool.
- **Função `getPoolDistribution` no api.js** (`feat` — `frontend/src/services/api.js`): Nova função API que consome o endpoint `/finance/pool-distribution` com parâmetros `month`, `year` e `company_id`.

### Alterado
- **FinanceConfig Create/Update incluem distribution_model** (`refactor`): Os endpoints `POST /finance/configs` e `PUT /finance/configs/{config_id}` agora aceitam e persistem o campo `distribution_model`. O `create_finance_config` inclui o campo no documento MongoDB. O `update_finance_config_by_id` suporta atualização do modelo via `FinanceConfigUpdate`.
- **fetchAllData no FinanceDashboard** (`refactor`): A função de carregamento de dados agora faz 6 requests em paralelo (adicionado `getFinanceConfigs`) para determinar o `distributionModel` ativo e renderizar condicionalmente a aba "Distribuição".

## [2026-03-06] — Fase 1: Refatoração Arquitetural — Separação Cliente ↔ Processo (Atualização)

### Adicionado
- **Endpoint de migração Fase 1 via API REST** (`feat` — `backend/routes/admin_process_migration.py`): Novos endpoints para executar e monitorizar a migração de separação Cliente ↔ Processo diretamente no painel de administração:
  - `GET /api/admin/process-migration/status` — Estado actual da migração (processos com/sem client_id, backups, dados financeiros nos clientes)
  - `POST /api/admin/process-migration/dry-run` — Simulação sem modificar a BD
  - `POST /api/admin/process-migration/run` — Executar migração (com backup automático)
  - `POST /api/admin/process-migration/rollback` — Reverter migração usando backups
- **Tab "Migração" no Painel de Administração** (`feat` — `frontend/src/components/admin/ProcessMigrationTab.js`): Nova tab no SystemAdminPanel (secção "Técnico", apenas admin) com:
  - Diagrama visual Cliente → Processo (relação 1:N)
  - Estatísticas em tempo real (total clientes, processos, com/sem client_id)
  - Estado dos backups (clients_legacy, processes_legacy)
  - Botão de simulação (dry-run) com confirmação
  - Botão de execução com dupla confirmação (escrever "MIGRAR")
  - Botão de rollback com dupla confirmação (escrever "REVERTER")
  - Auto-refresh durante migração em execução
  - Relatório da última execução (clientes processados, criados, processos migrados, erros)
- **Funções de API no frontend** (`feat` — `frontend/src/services/api.js`): Adicionadas `getProcessMigrationStatus`, `dryRunProcessMigration`, `runProcessMigration`, `rollbackProcessMigration`

### Alterado
- **server.py**: Registo da nova rota `admin_process_migration_router`

## [2026-03-06] — Fase 1: Refatoração Arquitetural — Separação Cliente ↔ Processo

### Alterado
- **Refatoração arquitetural: Separação estrita da entidade Cliente da entidade Processo** (`refactor` — **CRÍTICO**): Os dados pessoais/fiscais do Cliente foram separados dos dados de negócio do Processo. Antes, os dados estavam misturados — o Cliente tinha dados financeiros e o Processo duplicava dados pessoais. Agora:
  - **Cliente**: Entidade pessoa/fiscal — contém APENAS dados pessoais (nome, NIF, email, telefone, estado civil, profissão, morada fiscal, etc.) e de contacto. Removidos `dados_financeiros`, `co_buyers` e `co_applicants` do modelo.
  - **Processo**: Entidade de negócio/dossier — contém dados de negócio (financial_data, real_estate_data, credit_data), atribuições (consultor, mediador), e campos de negócio ao nível raiz (`property_value`, `loan_value`, `bank_assigned`, `honorarios`, `comissao_banco`). `client_id` passa a ser OBRIGATÓRIO.
  - `ClientFinancialData` foi removido. Dados financeiros pertencem exclusivamente ao Processo.
  - `compra_tipo` e `menor_35_anos` marcados como `[DEPRECATED]` no ClientPersonalData (campos de negócio — migrar para Processo na Fase 2).
  - `ProcessType` expandido com novos tipos: `CREDITO_PESSOAL`, `SEGUROS`, `OUTRO`.
  - `ProcessStatusEnum` adicionado ao modelo de processo (centralizado).
  - Novo `ClientResponse` schema (sem dados financeiros).
  - Novo `ProcessResponse` com campos de negócio ao nível raiz (`property_value`, `loan_value`, `bank_assigned`, `honorarios`, `comissao_banco`).
  - `ProcessUpdate` suporta atualização dos campos de negócio ao nível raiz.
  - `ProcessCreate` requer `client_id` obrigatório.

### Adicionado
- **Script de Migração Segura** (`feat` — `backend/scripts/migrate_clients_to_processes.py`): Script standalone para migrar dados existentes do MongoDB para a nova arquitetura:
  - Dry-run por defeito (usa `--apply` para executar de verdade)
  - Deduplicação de clientes por NIF/Email/Nome (chave única)
  - Extração de dados pessoais dos processos para criar/encontrar clientes
  - Adição de `client_id` obrigatório a todos os processos
  - Campos de negócio extraídos para o nível raiz (`property_value`, `loan_value`, `bank_assigned`, `honorarios`)
  - Backup automático das coleções originais (`clients_legacy`, `processes_legacy`)
  - Validação de integridade pós-migração
  - Rollback disponível (`--rollback`)
  - Criação de índices (`client_id`, `nif_hash`, `email`)

### Notas
- **Fase 1 apenas**: Modelos e migração. Rotas do backend e frontend NÃO foram alterados — compatibilidade backward é mantida.
- **Fase 2 (futura)**: Adaptar rotas do backend para usar a nova separação. Remover campos deprecados. Atualizar frontend.
- **Fase 3 (futura)**: Remover `personal_data` do Processo (usar apenas referência ao Cliente via `client_id`).

## [2026-03-05] — KILL SWITCH: DISABLE_EMAIL_SYNC (variável existente no Render)

### Corrigido
- **KILL SWITCH usa agora `DISABLE_EMAIL_SYNC` (variável que JÁ EXISTE no Render dev)** (`fix` — **CRÍTICO**): Todos os guards foram alterados de `ENABLE_EMAIL_SYNC` (opt-in) para `DISABLE_EMAIL_SYNC` (opt-out). O Render dev já tem `DISABLE_EMAIL_SYNC=true` configurado. Em produção, a variável NÃO existe → sync corre normalmente.
- **8 pontos de proteção com `DISABLE_EMAIL_SYNC`** (`fix`):
  - **`server.py` startup**: Se `DISABLE_EMAIL_SYNC=true`, email_sync_task NÃO é criado
  - **`scheduled_tasks.py` `run_email_auto_sync()`**: return imediato se `DISABLE_EMAIL_SYNC=true`
  - **`scheduled_tasks.py` `auto_sync_emails()`**: return mock se `DISABLE_EMAIL_SYNC=true`
  - **`email_service.py` `sync_webmail_emails()`**: return mock se `DISABLE_EMAIL_SYNC=true`
  - **`email_service.py` `sync_user_emails()`**: return mock se `DISABLE_EMAIL_SYNC=true`
  - **`email_service.py` `sync_shared_role_emails()`**: return mock se `DISABLE_EMAIL_SYNC=true`
  - **`email_service.py` `sync_all_user_emails()`**: return mock se `DISABLE_EMAIL_SYNC=true`
  - **`worker.py`**: webmail sync saltado se `DISABLE_EMAIL_SYNC=true`

### Notas
- **Render dev**: Já tem `DISABLE_EMAIL_SYNC=true` — zero ligações IMAP.
- **Produção**: NÃO definir `DISABLE_EMAIL_SYNC` — o sync corre normalmente.
- Commit anterior: `cd42b1b` (ENABLE_EMAIL_SYNC), este commit migra para DISABLE_EMAIL_SYNC.

## [2026-03-05] — KILL SWITCH DEFINITIVO: ENABLE_EMAIL_SYNC + ensure_libmagic REMOVIDO

### Corrigido
- **Render DEV: Webmail Sync continua a correr apesar de guards ENVIRONMENT** (`fix` — **CRÍTICO**): Os guards baseados em `ENVIRONMENT != 'production'` deviam funcionar (Render dev tem `ENVIRONMENT=dev`), mas o Render está a correr **código antigo** porque o deploy crasha antes de aplicar os novos commits. Criada variável dedicada `ENABLE_EMAIL_SYNC` — opt-in explícito que NÃO existe em nenhum ambiente por defeito. Sem `ENABLE_EMAIL_SYNC=true` → **zero ligações IMAP, sempre**.
- **Render DEV: OOM causado por `ensure_libmagic()` no arranque** (`fix` — **CAUSA RAIZ**): A função `ensure_libmagic()` no topo de `server.py` executava `apt-get update && apt-get install -y libmagic1` em CADA arranque. Apagada completamente. `libmagic1` já instalado no Dockerfile.
- **8 pontos de proteção com `ENABLE_EMAIL_SYNC`** (`fix`):
  - **`server.py` startup**: `email_sync_task` só criado se `ENABLE_EMAIL_SYNC=true`
  - **`scheduled_tasks.py` `run_email_auto_sync()`**: return imediato se `ENABLE_EMAIL_SYNC != true`
  - **`scheduled_tasks.py` `auto_sync_emails()`**: return mock se `ENABLE_EMAIL_SYNC != true`
  - **`email_service.py` `sync_webmail_emails()`**: return mock se `ENABLE_EMAIL_SYNC != true`
  - **`email_service.py` `sync_user_emails()`**: return mock se `ENABLE_EMAIL_SYNC != true`
  - **`email_service.py` `sync_shared_role_emails()`**: return mock se `ENABLE_EMAIL_SYNC != true`
  - **`email_service.py` `sync_all_user_emails()`**: return mock se `ENABLE_EMAIL_SYNC != true`
  - **`worker.py`**: webmail sync só executa se `ENABLE_EMAIL_SYNC=true`

### Notas
- **Para ativar o Email Sync em produção**: Adicionar `ENABLE_EMAIL_SYNC=true` às variáveis de ambiente do Render (ambiente de produção apenas).
- **NÃO adicionar** `ENABLE_EMAIL_SYNC` ao ambiente de dev — por defeito, o sync fica desativado.
- Commits: `1d6a9bc`, `1d2aef9`, `0bf8c78`

### Corrigido
- **Render DEV: OOM persistente apesar de kill switches baseados em ENVIRONMENT** (`fix` — **CRÍTICO**): Os kill switches anteriores baseados em `os.environ.get('ENVIRONMENT', 'dev')` falharam porque: (1) O Dockerfile define `APP_ENV=production` (não `ENVIRONMENT`), e se `ENVIRONMENT=production` estiver configurado no Render, o bypass é ultrapassado e o loop arranca; (2) As variáveis de ambiente podem ter valores inesperados em diferentes ambientes de deploy. Aplicada solução de "Força Bruta": o código fonte foi diretamente comentado/amputado, independente de qualquer variável de ambiente.
- **`server.py`: `asyncio.create_task(run_email_auto_sync())` COMENTADO** (`fix` — **BRUTE FORCE**): A criação da tarefa de email sync no startup do FastAPI foi comentada. O loop IMAP de polling NÃO arranca mais, independentemente de variáveis de ambiente. Log de aviso adicionado: `🛑 EMERGENCY BYPASS: Email Auto-Sync task creation COMMENTED OUT`.
- **`scheduled_tasks.py`: `run_email_auto_sync()` → return forçado na 1ª linha** (`fix` — **BRUTE FORCE**): Mesmo que a função seja chamada por outro path, retorna imediatamente com log `🛑 BRUTE FORCE KILL SWITCH: Webmail Sync desativado no código fonte.`.
- **`scheduled_tasks.py`: `auto_sync_emails()` → return forçado na 1ª linha** (`fix` — **BRUTE FORCE**): O método `auto_sync_emails()` da classe `ScheduledTasksService` retorna imediatamente com `{"success": True, "error": "BRUTE FORCE BYPASS", "total_synced": 0}`.
- **`email_service.py`: `sync_webmail_emails()` → return forçado na 1ª linha** (`fix` — **BRUTE FORCE**): A função principal de sincronização IMAP retorna imediatamente com `{"success": True, "error": "BRUTE FORCE BYPASS", "total_synced": 0}`. Qualquer chamada direta ou indireta é bloqueada.
- **`worker.py`: `scheduler_loop()` e `run_scheduled_tasks()` → return forçado na 1ª linha** (`fix` — **BRUTE FORCE**): O scheduler do worker (que faz IMAP polling a cada 20min) e as tarefas agendadas retornam imediatamente, impedindo qualquer execução.

### Notas
- **6 pontos de kill** aplicados em 4 ficheiros (`server.py`, `scheduled_tasks.py`, `email_service.py`, `worker.py`).
- Cada kill switch é **incondicional** — não depende de variáveis de ambiente.
- O código original é preservado mas inalcançável (comentado ou após `return`).
- Para reativar em PRODUÇÃO: (1) Descomentar o bloco `try/except` em `server.py`, (2) Remover as 3-4 linhas de "BRUTE FORCE KILL SWITCH" em cada função.
- Commit: `468fb3f`

## [2026-07-14] — Modelo On-Demand em Dev (Fix OOM no Render)

### Corrigido
- **Render crash por OOM (Ran out of memory — 512MB)** (`fix` — **CRÍTICO**): O serviço de sincronização de emails em background consumia ~200MB de RAM persistente (ThreadPoolExecutor + ligações IMAP), excedendo os 512MB do Render free tier e causando crashes constantes no deploy. Em ambiente de desenvolvimento (`ENVIRONMENT=dev/development/local/preview`), o auto-sync de emails NÃO arranca mais no startup.
- **Background sync desativado em dev** (`fix`): `server.py` agora verifica `ENVIRONMENT` antes de criar a tarefa `run_email_auto_sync()`. O `worker.py` também salta a sincronização webmail em dev. Em produção (`ENVIRONMENT=production`), o comportamento mantém-se (sync a cada 15min).
- **Logs desnecessários em dev** (`fix`): O worker loga "Webmail sync DESATIVADO em dev" apenas uma vez por hora (não a cada minuto).

### Adicionado
- **Auto-sync ao abrir o Webmail** (`feat` — On-Demand): Quando o utilizador navega para a página de Webmail, a sincronização IMAP é disparada automaticamente (uma vez por visita à página). Isto substitui o polling contínuo em dev, garantindo emails frescos sem consumo de RAM persistente.
- **Modelo On-Demand para dev** (`feat` — Arquitetura): Em vez de sincronizar continuamente em background (modelo Push), o ambiente de dev usa o modelo Pull — sincroniza apenas quando o utilizador abre o Webmail ou clica "Sincronizar". Os endpoints `POST /api/emails/webmail/sync-user` (pessoal) e `POST /api/emails/webmail/sync` (global) já existiam e continuam disponíveis em ambos os ambientes.

## [2026-07-14] — Proteção contra Rate Limiting IMAP (Policy Violation)

### Corrigido
- **IP do Render bloqueado pelo servidor Webmail (IMAP policy violation)** (`fix` — **CRÍTICO**): O servidor de email estava a bloquear o IP do Render com o erro `* BYE Service temporarily refused connection from IP because a policy violation has occurred`, seguido de `LOGIN Failed`. Causa raiz: o sistema de sincronização automática corria a cada 3 minutos e abria ligações IMAP em rajada para todas as contas de utilizadores (Tiago, Carina, Andrea, etc.) sem qualquer delay, disparando as firewalls de rate limiting do provedor de email.
- **Intervalo de polling demasiado agressivo (3 minutos)** (`fix`): O `run_email_auto_sync` no `server.py` corria a cada 180s, criando ~20 ciclos de sync por hora. Cada ciclo abria ligações IMAP para todas as contas configuradas sem qualquer espaçamento. Alterado para 900s (15 minutos).
- **Sem delay entre contas IMAP** (`fix`): O loop de sincronização iterava sobre todas as contas de email sem qualquer pausa, abrindo múltiplas ligações IMAP em simultâneo. Agora adicionado `await asyncio.sleep(3)` entre cada conta.
- **Erros de policy violation inundavam os logs como ERROR** (`fix`): Erros de rate limiting eram logados como `logger.error()`, criando dezenas de entradas repetitivas por ciclo. Agora são logados como `logger.warning()` com mensagem clara e truncada.
- **Ligações IMAP vazadas em caso de erro** (`fix`): `_fetch_all_from_folder_sync()` não chamava `mail.logout()` em caso de exceção durante o fetch, vazando ligações IMAP. Agora `mail.logout()` está num bloco `finally`.
- **Sincronização continuava após policy violation** (`fix`): Mesmo quando o servidor IMAP bloqueava o IP, o loop continuava a tentar as contas restantes, agravando o bloqueio. Agora o loop para imediatamente (`break`) ao detetar policy violation.

### Adicionado
- **Detecção de policy violation no IMAP** (`feat` — Resiliência): Keywords detetadas: `policy violation`, `temporarily refused`, `too many`, `rate limit`, `connection limit`, `abuse`, `blocked`. Aplicada em 3 camadas: `_fetch_all_from_folder_sync`, `sync_webmail_emails` / `sync_user_emails`, e `auto_sync_emails`.
- **Jitter aleatório no intervalo de sync** (`feat` — Anti-thundering-herd): O loop `run_email_auto_sync` adiciona 0-60s de variação aleatória ao intervalo de 15 minutos, para evitar que múltiplas instâncias sincronizem simultaneamente após deploy.
- **Delay de 3s entre fases de sync** (`feat`): Pausas de 3 segundos entre sync global → pessoal → partilhado em `auto_sync_emails()`.
- **Worker: intervalo de webmail sync aumentado para 20 minutos** (`feat`): O worker ARQ agora sincroniza webmail a cada 1200s (20 min) em vez de 900s, para evitar sobreposição com o scheduler do FastAPI (15 min).

## [2026-07-14] — Resiliência a 503 no Portal do Cliente (Cold Start Render)

### Corrigido
- **Erro 503 ao obter documentos do Portal das Finanças** (`fix` — **Resiliência**): O endpoint `POST /api/portal/fetch-financas` retornava 503 (Service Unavailable) em duas situações: (1) Render free tier cold start — o servidor adormece após inatividade e a primeira request recebe 503 do proxy antes da app estar pronta; (2) Falha do scraper Playwright/Chromium (timeout, falta de memória). O erro era apresentado de forma genérica ao utilizador, sem retry automático nem mensagem útil.
- **Parse de JSON falhava quando o 503 vinha do proxy Render** (`fix`): O proxy do Render retorna HTML no 503 (não JSON), o que causava erro de parsing no `res.json()` e crashava o fluxo. Adicionado parsing seguro com try/catch e mensagem específica para 503 do proxy vs 503 da app.
- **Credenciais pedidas mesmo com scraper indisponível** (`fix` — UX): O utilizador podia introduzir NIF e password, esperar pelo scraper, e só depois receber erro 503. Agora o sistema verifica a disponibilidade do scraper antes de mostrar o dialog de credenciais.

### Adicionado
- **`fetchWithRetry()` — Retry automático para 503** (`feat` — Resiliência): Nova utilidade que faz retry automático até 2 vezes (com delays de 3s e 6s) quando recebe HTTP 503 ou erro de rede. Isto cobre a maioria dos cold starts do Render (tipicamente 5-15s para acordar).
- **Verificação prévia de disponibilidade do scraper** (`feat` — UX): Ao carregar a página de documentos, o sistema consulta `GET /portal/scraper-status` para verificar se o Playwright/Chromium está disponível. Se não estiver, mostra aviso amarelo a guiar o utilizador para upload manual.
- **Re-verificação ao clicar no botão** (`feat` — UX): Se o scraper estava indisponível no carregamento da página, ao clicar em "Obter IRS" o sistema re-verifica — o servidor pode ter acordado entretanto.
- **Mensagens de erro específicas** (`feat` — UX): Erros 503 mostram mensagem distinta (servidor a iniciar vs scraper indisponível), 401 mostra "credenciais incorretas", e erros genéricos têm fallback adequado.
- **Spinner nos botões de auto-fetch durante verificação** (`feat` — UX): Botões mostram Loader2 spinner enquanto verificam disponibilidade do scraper.

### Corrigido
- **Console warning: "Collapsible is changing from uncontrolled to controlled"** (`fix` — **Console Spam**): O componente Radix `Collapsible` na sidebar do DashboardLayout recebia `open={openSections[group.id]}` que era `undefined` quando o grupo ainda não tinha sido interagido. O Radix trata `undefined` como uncontrolled e `true/false` como controlled, causando o warning repetido no console. Corrigido com `!!openSections[group.id]` para garantir que `open` é sempre `boolean`, nunca `undefined`. Isto elimina dezenas de warnings repetidos do Radix Collapsible por cada render.
- **Bug: Nova Pasta criada sempre na raiz do bucket S3** (`fix` — **UX CRÍTICO**): Quando o utilizador navegava para uma subpasta no Explorador de Ficheiros e criava uma "Nova Pasta", ela era criada na raiz do bucket S3 (fora de "Documentação Clientes/"), ignorando a pasta actual. Causa: os endpoints `POST /api/admin/s3-create-folder` e `POST /api/admin/s3-upload` não prefixavam o caminho com o base path do explorador quando `folder_path` estava vazio ou não continha o prefixo "Documentação Clientes". Corrigido com a função `_resolve_explorer_path()` que normaliza todos os caminhos relativamente ao base path, consistente com a lógica já existente no `GET /api/admin/s3-folder-contents`.
- **Upload na raiz também ia para o bucket root** (`fix`): O mesmo bug afetava o upload de ficheiros quando o utilizador estava na raiz do explorador. Agora também usa `_resolve_explorer_path()`.

### Adicionado
- **Permissões granulares para Rascunhos** (`feat` — Permissões): Adicionadas duas novas capabilities ao sistema de permissões:
  - `DRAFT_VIEW` — Aceder à página de Rascunhos (ver e consultar)
  - `DRAFT_MANAGE` — Criar, editar e eliminar rascunhos
  - Ambas estão na categoria "Comunicações" do gestor de permissões
  - **Diretor** e **Administrativo** têm ambas as capabilities ativas por padrão
  - **Consultor**, **Intermediário** e **Indexação** têm ambas desativadas por padrão (disponíveis para ativação pelo admin)
  - Admin e CEO mantêm bypass total (Super Admin)
- **Acesso à página de Rascunhos via capability** (`feat` — RBAC): A rota `/rascunhos` passou de verificação por cargo hardcoded (`allowedRoles: ["admin", "ceo", "administrativo"]`) para verificação por capability granular (`requiredCapability: "DRAFT_VIEW"`). Isto permite ao administrador controlar quem acede aos Rascunhos diretamente no gestor de permissões, sem depender de cargo.
- **Sidebar respeita capability DRAFT_VIEW** (`feat` — UX): O link "Rascunhos" na sidebar agora só aparece se o utilizador tiver a capability `DRAFT_VIEW`. O grupo "Gestão e Operações" é automaticamente ocultado se ficar sem items após a filtragem.
- **`ProtectedRoute` suporta `requiredCapability`** (`feat` — Infraestrutura): O componente `ProtectedRoute` no `App.js` agora aceita a prop `requiredCapability` além de `allowedRoles`, permitindo verificação granular de acesso por capability.
- **Mapeamento legado de Rascunhos** (`feat` — Compatibilidade): Adicionado `"rascunhos"` a `AVAILABLE_PAGES` e `"view_drafts"`/`"manage_drafts"` a `AVAILABLE_ACTIONS` no serviço de permissões legado, com mapeamento para `DRAFT_VIEW`/`DRAFT_MANAGE` no `ACTION_TO_CAPABILITY_MAP`.

### Corrigido
- **Bug visual: campos ocultos no Gestor de Permissões** (`fix` — UX): Quando todos os accordions de categorias eram expandidos na página de permissões, a lista ficava demasiado grande sem scroll adequado, cortando os campos do fundo. Corrigido alterando o `ScrollArea` de `max-h-[65vh]` para `h-[65vh]` com `overflow-hidden` no container pai, e adicionado `pb-10` ao conteúdo interno para garantir que a última opção nunca fica colada ou escondida atrás de bordas.
- **Mismatch de acesso: Diretor via Sidebar vs Rota** (`fix` — RBAC): O Diretor via o link "Rascunhos" na sidebar mas era redirecionado ao clicar porque a rota só permitia `["admin", "ceo", "administrativo"]`. Agora ambos usam a mesma verificação de capability `DRAFT_VIEW`.

## [2026-03-04] — Limpeza RBAC: Remoção de "mediador", Validação de Cargos e Correção de Build

### Corrigido
- **Build error: `</div>` extra em SystemConfigPage.js** (`fix` — **BUILD BLOCKER**): O ficheiro `SystemConfigPage.js` tinha um `</div>` orfão na linha 3030 que causava erro "Unterminated regular expression" no esbuild/Vercel, impedindo o build. O `</div>` não correspondia a nenhuma tag de abertura — removido.
- **package-lock.json misturado com Yarn** (`fix`): Removido `package-lock.json` do frontend para eliminar o warning do Yarn sobre lock files misturados.

### Alterado
- **Role "mediador" removida do sistema** (`refactor` — RBAC): O role "mediador" não existe como cargo de utilizador — era um alias legacy de "intermediario". Removido de todas as roleLabels, roleColors, filterByAnyRole arrays, STAFF_ROLES, allowedRoles e ContextSwitcher em 15+ ficheiros. O role "intermediario" passa a ser o único cargo de intermediário de crédito. As referências a "mediador" no contexto de processos (assigned_mediador_id, mediador_name, mediadorFilter) foram mantidas pois referem-se ao intermediário de crédito no processo de negócio, não ao cargo de utilizador.
- **Indexação agora tem acesso à Visão Global** (`refactor` — RBAC): O role "indexação" passou a ver o grupo "Visão Global" (Todos os Clientes, Todos os Processos) na Sidebar, além das Listas de Trabalho habituais.
- **Validação: cargo principal ≠ cargo adicional** (`feat` — RBAC): Adicionada validação nos formulários de criação e edição de utilizadores que impede selecionar o mesmo cargo como principal e como adicional (ex: consultor + consultor). Inclui: (1) filtro automático nos checkboxes de cargos adicionais (o cargo principal já não aparece como opção), (2) aviso visual vermelho se houver duplicado, (3) bloqueio no submit com toast de erro descritivo.

## [2026-07-07] — Correção de TypeError no PUT /processes/:id

### Corrigido
- **TypeError em PUT /processes/:id — dict merge com sub-campos não-dict** (`fix` — **CRÍTICO**): O endpoint `PUT /processes/:id` crashava com `TypeError` ao fazer merge `{**existing, **incoming}` quando um sub-campo do MongoDB (ex: `personal_data`, `financial_data`) estava armazenado como tipo não-dict (string, lista, etc.). O fallback `or {}` não protege contra valores truthy não-dict (ex: string `"null"` → `{**"null", **dict}` → TypeError). Corrigido substituindo todos os `process.get("field") or {}` por `isinstance(field, dict)` checks em 7 sub-campos: `personal_data`, `financial_data`, `real_estate_data`, `credit_data`, `titular2_data`, `vendedor` (cliente e staff paths).
- **Shallow copy em encrypt_sensitive_data** (`fix`): `encrypt_sensitive_data()` usava `data.copy()` (shallow) em vez de `copy.deepcopy(data)`, causando mutação silenciosa dos dicts aninhados do `update_data` original quando blind indexes e encriptação eram adicionados in-place. Corrigido para `copy.deepcopy()`, consistente com `decrypt_sensitive_data()`.
- **Try/except em falta na primeira desencriptação do PUT** (`fix`): A primeira chamada `decrypt_sensitive_data(process)` no PUT endpoint não tinha try/except — se `deepcopy` ou a desencriptação falhasse com TypeError, o erro subia sem contexto. Adicionado try/except com mensagem de erro descritiva.

## [2026-07-06] — Correções de Bugs e Funcionalidades Pendentes (Ronda 3)

### Corrigido
- **Build error: duplicate safeString import** (`fix` — **BUILD BLOCKER**): `safeString` era importado simultaneamente de `DashboardShared` e de `utils/safeString` em 3 ficheiros (ProcessDetails.js, ProcessSummaryCard.js, ProcessStickyHeader.js), causando `ERROR: The symbol "safeString" has already been declared` e impedindo o build. Corrigido removendo `safeString` dos imports de `DashboardShared` em todos os ficheiros — todos usam agora exclusivamente a versão robusta de `utils/safeString.js` que lida corretamente com objetos `{value, label}` e previne React Error #31.

## [2026-07-06] — Correções de Bugs e Funcionalidades Pendentes (Ronda 2)

### Corrigido
- **Flake8 F821: Form import em falta** (`fix`): O endpoint `POST /api/admin/s3-upload` em `admin_storage.py` usava `Form(...)` sem importar `Form` do FastAPI, causando falha no CI.
- **React Minified Error #31 em ProcessDetails** (`fix`): Criada utilidade partilhada `safeString()` e `safeStringArray()` em `utils/safeString.js`. Aplicado a `consultor_names`, `mediador_names`, campos de co-buyers e co-applicants em ProcessDetails.js e ProcessSummaryCard.js. Previne crash quando o MongoDB devolve objetos `{value, label}` em vez de strings.
- **500 error em POST /api/documents/portal-requests/{processId}** (`fix`): (1) Adicionado `{"category.label": category}` ao `$or` na verificação de duplicados — agora deteta categorias armazenadas como objetos `{label, value}`. (2) Adicionado filtro `"source": {"$in": ["admin_request", "client_portal"]}` para evitar falsos conflitos com documentos `auto_default`. (3) Removido `.copy()` desnecessário no insert MongoDB.
- **File Explorer: navegação para não-admins** (`fix`): Botão "Ir para Configurações" no S3NotConfiguredBanner agora redireciona para `/definicoes` (pessoal) em vez de `/configuracoes` (admin-only) quando o utilizador não é admin. Botão "Configurar Agora" escondido para não-admins que não podem guardar a config.
- **Webmail: eliminação permanente vs soft-delete** (`fix`): (1) Backend: `DELETE /api/emails/{id}` agora faz soft-delete (marca `is_archived=True` em vez de remover da BD). (2) Novo endpoint `DELETE /api/emails/{id}/permanent` para eliminação permanente de emails no Lixo. (3) Frontend: ao eliminar emails na pasta Lixo, chama endpoint permanente com confirmação mais forte; nas restantes pastas, faz soft-delete com mensagem "movido para o Lixo".

### Adicionado
- **RGPD "Não Solicitado" no Portal do Cliente** (`feat`): Adicionado card cinza "RGPD Não Solicitado" quando o estado é `none` — o cliente agora vê sempre o estado RGPD (assinado/pendente/não solicitado), em vez de não ver nada quando o RGPD ainda não foi pedido.
- **Utilitário safeString partilhado** (`feat`): `frontend/src/utils/safeString.js` com `safeString(val, fallback)` e `safeStringArray(arr, fallback)`. Extrai strings de objetos `{value, label}` de forma segura, evitando React Error #31 em toda a aplicação.

## [2026-07-05] — Correções de Bugs e Funcionalidades Pendentes

### Corrigido
- **F821 — `Form` não importado em `admin_storage.py`** (`fix` — **CI BLOCKER**): O endpoint `POST /api/admin/s3-upload` usava `Form("")` na linha 785 sem importar `Form` do FastAPI. Isto causava falha no flake8 (F821 undefined name 'Form') e bloqueava o pipeline CI/CD. Adicionado `Form` ao import: `from fastapi import APIRouter, Depends, HTTPException, Query, Body, UploadFile, File, Form`.
- **React Minified Error #31 em ProcessDetails e componentes relacionados** (`fix` — **CRÍTICO**): Objetos `{value, label}` do backend eram renderizados diretamente como React children, causando crash da aplicação. Corrigido em 3 ficheiros:
  - **DashboardShared.js**: Adicionados helpers `safeString()` e `safeNumber()` exportados para uso global.
  - **ProcessDetails.js** (25+ correções): Wrapping de `process.client_name`, `process.process_number`, labels, dados de co-buyers/applicants, `.toLocaleString()`, `.replace()`, metadata e AI conflicts com `safeString()`/`safeNumber()`.
  - **ProcessStickyHeader.js** (12+ correções): Wrapping de client name, phone, email, NIF, rendimento, employment_type, consultor/mediador names.
  - **ProcessSummaryCard.js** (7+ correções): Wrapping de client info, formatCurrency, real estate data, interest rate.
- **Rota /definicoes corrigida no sidebar** (`fix`): "Definições Gerais" no sidebar apontava para `/configuracoes` (SystemConfigPage) em vez de `/definicoes` (SettingsPage com Perfil, Segurança, Notificações, Sistema). Corrigido para `/definicoes`. Adicionado novo item "Configuração do Sistema" no menu apontando para `/configuracoes`.
- **500 error em POST /api/documents/portal-requests/{processId}** (`fix`): Adicionado `try/except` à volta da query de verificação de duplicados no MongoDB (previne crash se a query `$or` falhar). Adicionado `model_validator` no Pydantic `DocumentRequestCreate` para coagir automaticamente objetos `{value, label}` em strings antes da validação.

### Adicionado
- **Contadores de pastas no Webmail** (`feat`): O endpoint `/api/emails/webmail-stats` agora retorna `folder_counts` com contadores para todas as pastas (inbox, sent, starred, drafts, trash). O WebmailPage mostra badges com contadores para todas as pastas na sidebar, não apenas para a Inbox.
- **Endpoints S3 para o Explorador de Ficheiros** (`feat`): Adicionados 5 novos endpoints no backend (`admin_storage.py`):
  - `POST /api/admin/s3-rename` — Renomear ficheiros e pastas (copy + delete para ficheiros, recursivo para pastas)
  - `POST /api/admin/s3-delete` — Eliminar ficheiros e pastas (com recursão para pastas, paginação para pastas grandes)
  - `POST /api/admin/s3-create-folder` — Criar pastas (cria marcador `.keep` vazio)
  - `POST /api/admin/s3-upload` — Upload de ficheiros para qualquer pasta S3
  - `GET /api/admin/s3-download` — Download de ficheiros (streaming response com Content-Disposition)
  - Frontend atualizado: upload usa `/api/admin/s3-upload`, download usa `/api/admin/s3-download`
  - Acesso: Consultores/intermediários podem ver e descarregar; Operações de escrita restritas a admin/CEO/diretor/administrativo.

### Verificado (já implementado)
- **RGPD assinado no portal**: O portal do cliente já mostra card verde "RGPD Assinado" com data, e card amarelo "RGPD Pendente" quando aguarda assinatura.
- **Filtro de documentos já solicitados**: Ao solicitar documentos, categorias já pedidas (REQUESTED/PENDING/UPLOADED/SUBMITTED) são filtradas da lista de seleção.
- **Multi-seleção de documentos**: O dialog permite selecionar múltiplas categorias simultaneamente com checkboxes, criando um pedido por categoria.
- **Pastas do Webmail (Enviados, Rascunhos, Lixo)**: O backend suporta todas as pastas (inbox, sent, drafts, starred, trash, custom) com isolamento por utilizador. O frontend mostra contadores de pastas e permite navegar entre elas.
- **Explorador de Ficheiros para consultores/intermediários**: O endpoint `/api/admin/s3-folder-contents` permite acesso a consultores, mediadores, intermediários e indexação (leitura e download). Operações de escrita restritas a admin/CEO/diretor/administrativo.

## [2026-07-04] — Atualização de Documentação e Issues Conhecidos

### Alterado
- **Documentação atualizada** (`docs`): README.md, CHANGELOG.md e PRD.md atualizados para refletir o estado atual do sistema:
  - Perfis de utilizador atualizados (consultores/intermediários têm acesso ao Explorador de Ficheiros)
  - Rotas documentadas (`/definicoes` vs `/configuracoes` vs `/ficheiros`)
  - Issues conhecidos documentados (explorador vazio, rota /definicoes, React #31, 500 portal-requests)
  - Estado do RGPD no portal documentado (card assinado/pendente)
  - Pastas do webmail documentadas (inbox, sent, starred, drafts, trash + custom)
  - Explorador de Ficheiros documentado na secção de Documentos

### Problemas Conhecidos — RESOLVIDOS em [2026-07-06]
- ~~**Explorador de Ficheiros não mostra ficheiros**~~: ✅ Resolvido — O endpoint já suporta consultores/intermediários. Se não mostra ficheiros, verificar configuração S3 (Base Path e credenciais). UI mostra mensagens mais úteis e navegação role-aware.
- ~~**Rota /definicoes incorreta**~~: ✅ Resolvido — "Definições Gerais" agora aponta para `/definicoes` (SettingsPage). "Configuração do Sistema" é item separado apontando para `/configuracoes`.
- ~~**React Minified Error #31**~~: ✅ Resolvido — Adicionados helpers `safeString()`/`safeNumber()` em DashboardShared.js e aplicados em ProcessDetails, ProcessStickyHeader, ProcessSummaryCard.
- ~~**500 Internal Server Error em POST /api/documents/portal-requests/{processId}**~~: ✅ Resolvido — Model validator e error handling adicionados. Duplicate check melhorado com `category.label` e filtro por source.

### Funcionalidades Pendentes — RESOLVIDAS em [2026-07-06]
- ~~**Filtro de documentos já solicitados**~~: ✅ Já implementado — categorias já pedidas são filtradas da lista de seleção.
- ~~**Multi-seleção de documentos**~~: ✅ Já implementado — dialog com checkboxes, cria um pedido por categoria.
- ~~**Pastas do Webmail (Enviados, Rascunhos, Lixo)**~~: ✅ Já implementado com folder_counts e navegação. Soft-delete implementado, emails movem para Lixo em vez de eliminação permanente.

## [2026-07-03] — Correções de CSP, Impersonate e Gestão de Fases

### Adicionado
- **Menu "Estados do Workflow" no sidebar** (`feat`): A página `/workflow-estados` existia mas não tinha item no menu lateral, tornando-a inacessível. Adicionado ao grupo "Configurações de Sistema" (visível apenas para admin) com ícone Activity. Permite criar, editar, eliminar e reordenar fases do processo.

### Corrigido
- **CSP — vercel.live iframe bloqueado** (`fix`): Adicionado `frame-src 'self' https://vercel.live` ao CSP do portal e das páginas administrativas para permitir o iframe de feedback da Vercel em preview deployments.
- **CSP — wss: WebSocket bloqueado** (`fix`): Adicionado `wss:` ao `connect-src` de ambos os CSPs. As notificações em tempo real via WebSocket estavam bloqueadas pelo Content Security Policy.
- **CSP — páginas non-portal demasiado restritivas** (`fix`): O CSP das páginas administrativas (non-portal) bloqueava inline scripts, Google Fonts, API calls ao render.com, Sentry e blob workers. Atualizado para permitir `unsafe-inline`/`eval` em script-src, Google Fonts em style-src/font-src, `https:` em connect-src e `blob:` em worker-src.
- **stop-impersonate retorna 400** (`fix`): Quando o access token era renovado automaticamente (a cada ~2h), os metadados de impersonate eram perdidos — o frontend continuava a mostrar o banner "A ver como..." mas o backend não reconhecia o modo. Corrigido em 3 pontos: (1) Backend `/auth/refresh` preserva metadados de impersonate do token antigo ao criar o novo, (2) Frontend passa o token atual no header Authorization durante refresh, (3) Frontend `stopImpersonating()` trata erro 400 com restauração automática do token original.
- **React error #31 `{value, label}` na Gestão de Formulários** (`fix`): O backend envia opções em dois formatos (strings e objetos `{value, label}`). O componente `FormManagementPage.js` renderizava objetos diretamente como React children em 7 locais. Adicionadas helpers `optStr()` e `optVal()` para normalizar ambos os formatos em toda a página.

## [2026-06-29] — Portal do Cliente: UX & Lógica — Redesenho Completo

### Alterado
- **Layout responsivo 2 colunas** (`refactor`): Desktop usa grid `lg:grid-cols-5` — coluna esquerda (3/5) para estado/stepper/consultor, coluna direita (2/5) para documentos. Mobile empilha verticalmente. Container passou de `max-w-lg` para `max-w-6xl`.
- **Stepper vertical em desktop** (`refactor`): Em desktop, o stepper é agora uma timeline vertical com linhas conectoras, labels e descrições. Em mobile mantém horizontal compacto.
- **Documentos dinâmicos** (`refactor`): A lista de documentos pendentes vem do backend (docs com status REQUESTED/PENDING). Cada item tem o seu próprio botão de upload com a categoria correta. O upload envia `category` e `document_id` ao backend, eliminando o hardcoded `category: 'Outros'`.
- **Confirm-upload atualiza docs REQUESTED** (`refactor`): Se o cliente faz upload de um doc que o admin solicitou (com `document_id`), o registo existente é atualizado para `status: UPLOADED` em vez de criar um duplicado. Sem `document_id`, cria registo novo.
- **Status dos documentos** (`feat`): Uploads do portal ficam com `status: "UPLOADED"` na BD. Docs solicitados são query com `status: REQUESTED/PENDING`.

### Adicionado
- **DOCUMENT_CATEGORY_MAP** (`feat`): Dicionário de 13 categorias (Cartao_Cidadao, IRS, Recibo_Vencimento, etc.) com label e icon. Usado pelo backend para normalizar labels dos documentos.
- **Cores dinâmicas do stepper** (`feat`): Função `stepColor()` mapeia cores do workflow (yellow/blue/orange/green/red/purple) para classes Tailwind completas.
- **Helper `_get_consultor_info()`** (`feat`): Extraído do endpoint status para função reutilizável. Verifica consultor e mediador.

## [2026-06-29] - Portal do Cliente: Remover Domínio Hardcoded

### Corrigido
- **Links do portal gerados com domínio hardcoded `app.powercell.pt`** (`fix`): Os endpoints `POST /processes/{id}/generate-magic-link` e `POST /processes/{id}/generate-magic-link/send` construíam URLs com `os.environ.get("FRONTEND_URL", "https://app.powercell.pt")`. Como `FRONTEND_URL` não estava configurada no backend (Render), o fallback era sempre usado — gerando links para um domínio inativo. Removido completamente o domínio hardcoded.
- **Função `_get_frontend_url(request)`** (`feat`): Nova função helper que determina a URL base do frontend dinamicamente: (1) Extrai do header `Referer`/`Origin` da request do staff (sempre o domínio correto), (2) Fallback para env var `FRONTEND_URL` (sem hardcoded), (3) Log de warning se não for possível determinar. Ambos os endpoints de magic link agora recebem `request: Request` e usam esta função.
- **CSP do portal bloqueava Google Fonts** (`fix`): Adicionados `https://fonts.googleapis.com` a `style-src` e `https://fonts.gstatic.com` a `font-src` no `vercel.json` para a rota `/portal(.*)`.

## [2026-06-29] - Portal do Cliente: Página em Branco — Bug Crítico

### Corrigido
- **Página do portal renderiza em branco (ecrã vazio)** (`fix` — **CRÍTICO**): O `ClientPortal.jsx` construiu URLs da API como `${BACKEND_URL}/portal/resolve/...` onde `BACKEND_URL` era `https://powercell.onrender.com` (definido pelo `vite.config.js` em build-time). Faltava o prefixo `/api`. Todas as chamadas (resolve + status + upload) iam para `https://powercell.onrender.com/portal/...` (404) em vez de `https://powercell.onrender.com/api/portal/...`. O fallback `|| 'https://powercell.onrender.com/api'` era código morto porque o Vite substitui `process.env.REACT_APP_BACKEND_URL` em build-time — o `||` nunca era avaliado. Corrigido para anexar `/api` diretamente: `(process.env.REACT_APP_BACKEND_URL || '...') + '/api'`, igual ao padrão usado em `api.js`.

## [2026-06-29] - Portal do Cliente: Correção Completa (iframe + loading + email)

### Corrigido
- **Portal não carrega dados (nem por URL directo)** (`fix`): O frame-busting no `index.html` e no `ClientPortal.jsx` causava o erro `chrome-error://chromewebdata/` SEMPRE (mesmo em URL directo) porque: (1) o script no `index.html` executava `window.open()` que falhava e deixava a página em estado quebrado; (2) o `useEffect` de frame-busting no React definia `error` e `loading=false` sem nunca carregar os dados. Solução: removido todo o frame-busting agressivo e substituído por `IframeDetector` — componente React que detecta iframe via `window.self !== window.top` e mostra botão "Abrir no Browser" com `<a target="_blank">` (não dispara erro cross-origin).
- **`window.history.replaceState` causava race condition** (`fix`): Removido `replaceState` do fluxo de resolve. O token JWT resolvido fica guardado apenas em `sessionStorage`. Em refresh/re-render, o `sessionStorage` é verificado primeiro para evitar re-resolve desnecessário.
- **`send_email()` com argumentos errados — 500 error** (`fix`): O endpoint `POST /processes/{id}/generate-magic-link/send` chamava `send_email(to_email=..., body=html_body)`. Corrigido para `send_email(account_name="power", to_emails=[...], body=text_body, body_html=html_body)`.
- **Timeouts em fetches sem abort** (`fix`): Adicionados `AbortController` com timeouts (15s resolve, 20s status) para evitar requests pendentes indefinidamente.

### Alterado
- **Frame-busting removido do `index.html`** (`change`): Removido script inline que tentava `window.top.location.href` e `window.open()`. O iframe é agora tratado exclusivamente pelo componente React `IframeDetector` que é não-intrusivo.
- **`ClientPortal.jsx` usa `useRef` para token estável** (`change`): O token JWT é guardado em `useRef` em vez de depender de `rawToken` da URL (que mudava com `replaceState` e causava re-execução do `useEffect`).

## [2026-06-28] - Links Curtos para Portal do Cliente

### Adicionado
- **Magic Links curtos (short_id)** (`feat`): Os links do portal passaram de ~280 caracteres (JWT na URL) para ~50 caracteres. Exemplo: `https://app.powercell.pt/portal/xK9mQ2pL`. Um `short_id` de 8 caracteres é gerado e guardado na coleção `portal_tokens` da MongoDB. O frontend detecta automaticamente se é short_id ou JWT e resolve via API.
- **Endpoint `GET /portal/resolve/{short_id}`** (`feat`): Resolve um short_id para o JWT completo. Valida formato, verifica existência na BD, e valida que o JWT não expirou. Retorna o JWT para o frontend usar nas restantes rotas autenticadas.
- **Endpoint `POST /processes/{id}/generate-magic-link/send`** (`feat`): Gera Magic Link e envia por email ao cliente. O email HTML contém um botão "Aceder ao meu Portal" com o link curto, mais instrução para copiar o link. Resolve o bug em que este endpoint não existia (frontend fazia 404).

### Alterado
- **`POST /processes/{id}/generate-magic-link`**: Agora devolve `magic_link` com short_id (URL curta) em vez do JWT completo na URL. Continua a devolver o `token` JWT para debug.
- **`ClientPortal.jsx`**: Detecta automaticamente se o token na URL é um short_id (sem `.`) ou JWT (com `.`). Se for short_id, chama `/portal/resolve/{short_id}` para obter o JWT antes de carregar os dados. Links JWT antigos continuam a funcionar (backward compatibility).

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

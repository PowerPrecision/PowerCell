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
- **2026-07-15**: Corrigidos 4 bugs conhecidos: (1) Explorador de Ficheiros S3 — S3Service não lia config da BD, adicionado `reconfigure()` + `sync_s3_from_db_config()` no startup e em tempo real; (2) Rota `/definicoes` vs `/configuracoes` no banner do explorador; (3) React Error #31 em ProcessDetails e ProcessDetailsModal — 16+ safeString() wrappers; (4) 500 em portal-requests — validação + logging melhorado. Funcionalidades completadas: Sincronização Webmail Enviados/Rascunhos/Lixo (direction="sent" explícito no sync). Confirmed: Filtro de docs já solicitados e Multi-seleção já estavam implementados.
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

## Issues Conhecidos e Bugs (2026-06-29 — ATUALIZADO)

### Bugs Corrigidos ✅
1. **✅ Explorador de Ficheiros não mostra ficheiros** (corrigido 2026-07-15): O `S3Service` lia apenas variáveis de ambiente na inicialização. Adicionado `reconfigure()` + `sync_s3_from_db_config()` no startup e sincronização em tempo real quando config é guardada via UI.
2. **✅ Rota /definicoes incorreta para "Definições Gerais"** (corrigido 2026-07-15): Banner do Explorador de Ficheiros agora navega corretamente: admins → `/configuracoes`, não-admins → mensagem "Contacte um administrador".
3. **✅ React Minified Error #31** (corrigido 2026-07-15): Adicionados 16+ `safeString()` wrappers em `ProcessDetails.js` e `ProcessDetailsModal.jsx` para evitar renderização de objetos `{value, label}` como React children.
4. **✅ 500 Internal Server Error em POST /api/documents/portal-requests/{processId}** (corrigido 2026-07-15): Adicionada validação de process_id vazio (400) e logging detalhado para debugging.
5. **✅ Erros 401 em cascata no Portal do Cliente** (corrigido 2026-06-29, Pacote AA): Os `useEffect` de `messages`, `recommendations` e `visits` no `ClientPortal.jsx` disparavam no mount sem verificar `isVerified`, gerando 5×401 quando o token estava expirado. Adicionado guard `isVerified` aos 3 `useEffect` + paragem do polling de mensagens quando a sessão expira.
6. **✅ 429 Too Many Requests no login do Portal** (corrigido 2026-06-29, Pacote AA): Limite de login demasiado agressivo (5 tentativas / 15 min lockout). Ajustado para 8 tentativas / 10 min. Resposta 429 agora inclui `retry_after` (segundos) no body. Frontend mostra countdown visual e desabilita o botão durante o lockout.
7. **✅ F821 undefined name 'file_key' no upload de logótipo** (corrigido 2026-06-29, Pacote AB): `backend/routes/companies_crud.py` linha 246 referenciava `file_key` (variável inexistente) em vez de `s3_key`. Falhava o CI (`flake8 --select=E9,F63,F7,F82`) e geraria `NameError` em runtime. Adicionado helper `_resolve_logo_url()` que gera URL pré-assinado S3 (7 dias) em tempo de leitura nos endpoints GET.

### Funcionalidades do Pacote AC (2026-06-29)
- **Dropdown "Simulações"**: Botões DSTI + Risco agrupados num `DropdownMenu` no cabeçalho do processo (sticky + principal).
- **Euribor Automática**: Endpoint `GET /api/public/euribor` (cache 24h) + integração no `SimulatorCH` (Portal do Cliente) e `RiskCalculator` (CRM). Seletor Fixa/Variável + spread ajustável.
- **Campos de Compliance**: `admission_year`, `is_ppe`, `is_fpe`, `credit_incidents` no modelo `CreditData`.
- **Cartão "Compliance & Perfil de Risco"**: Novo cartão minimizado por defeito na tab Crédito dos Detalhes do Processo, com aviso visual automático para PPE/FPE.
- **Fix RiskCalculator**: `tipoTaxa` agora atualiza cálculos instantaneamente; fallback do campo Entrada corrigido (0 em vez de 1, lê do processo).

### Funcionalidades do Pacote AD (2026-06-29)
- **Simulador Avançado (SimulatorCH)**: Motor de nível bancário com 4 melhorias:
  - **Modo Básico vs Avançado**: Simulação rápida (Montante/Prazo/TipoTaxa) sempre visível; Seguros e Comissões num `Accordion` "⚙️ Opções Avançadas" minimizado.
  - **TAEG com fallbacks invisíveis**: Seguro Vida 15€/mês, Multiriscos 10€/mês, Comissões 0€ aplicados por defeito no cálculo da TAEG (só visíveis se o Accordion for aberto). TAEG calculada por bisseção (100 iterações).
  - **Motor da Taxa Mista**: 2 fases — Fase 1 (taxa fixa, prestação constante) → amortização do capital (valor presente das prestações restantes) → Fase 2 (taxa variável sobre capital amortizado). Campos "Prazo da Taxa Fixa" e "Taxa Fixa Aplicável" obrigatórios.
  - **Travas de Idade BP**: `SimulatorCH` recebe `clienteDataNascimento` do `ClientPortal`; slider do Prazo limitado dinamicamente (≤30→40, 31-35→37, >35→35 anos) com badge visual.

### Correções do Pacote AE (2026-06-29)
- **✅ 500 no endpoint do Kanban** (corrigido 2026-06-29, Pacote AE): `GET /api/processes/kanban` falhava com `KeyError` quando um documento em `workflow_statuses` tinha campos em falta (`label`/`color`/`order`/`id`/`name`). Corrigido com `.get()` + defaults graciosos + try/except defensivo que loga e devolve o erro real.

### Funcionalidades Completadas ✅
1. **✅ Filtro de documentos já solicitados** (já implementado): O `PortalDocumentRequests.js` filtra automaticamente categorias já solicitadas da lista de seleção (linhas 128-139, `availableCategories`).
2. **✅ Multi-seleção de tipos de documento** (já implementado): O `PortalDocumentRequests.js` permite selecionar múltiplas categorias com checkboxes e cria pedidos em batch (linhas 292-319, `newDoc.categories`).
3. **✅ Pastas do Webmail - Enviados/Rascunhos/Lixo** (corrigido 2026-07-15): Adicionado `direction="sent"` explícito nas 3 funções de sync IMAP (`sync_webmail_emails`, `sync_user_emails`, `sync_shared_role_emails`). O frontend já definia as 5 pastas e o backend já sincroniza Drafts/Trash — o problema era que emails enviados apareciam na Inbox por causa da inferência pouco fiável de `direction`.

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

## Correções 2026-09-01 (3) — Config UIs (Checklist/IMAP) + Motor de Tarefas Automáticas

- **Checklist UI**: `MandatoryDocumentsSection.js` reescrito com sub-componente reutilizável `DocumentChecklist`, gerindo duas listas independentes — **Obrigatórios** (badge vermelho) e **Opcionais** (badge âmbar) — cada uma com o seu próprio formulário de adicionar/remover. Um único botão "Guardar Checklist" grava ambas via `PATCH /api/system-config/mandatory_documents` (`{enabled, documents, optional_documents}`); backend já suportava a estrutura (sessão anterior), sem necessidade de alterações.
- **IMAP na configuração de email**: descoberto durante testes que `frontend/src/pages/systemConfig/CompanyEmailConfigSection.js` e `SharedEmailConfigSection.js` (mencionados no pedido) eram **código morto** — nunca importados em nenhuma rota. A UI real e alcançável é: (a) `components/admin/CompaniesAdminTab.jsx` (Organização > Empresas) para o modelo `Company` (`smtp_*`/agora `imap_email/imap_password/imap_host/imap_port`, adicionados em ronda anterior ao backend mas sem UI); (b) `pages/EmailAccountsPage.js` (`/contas-email`, card "Contas Partilhadas") para `SharedEmailConfigCreate`, com um novo toggle "Configuração manual IMAP/SMTP (alternativa ao Google)" por departamento (Indexação/Suporte/Comercial/Administração), campos SMTP primeiro depois IMAP (host/porta/user/password) via `PUT /api/admin/shared-email/{role}`. As secções em `systemConfig/` também foram actualizadas (para consistência/possível reutilização futura), mas a correção funcional real está nos dois ficheiros acima.
- Backend: `models/company_email_config.py` ganhou `imap_user`/`imap_password` (encriptado via `encryption_service`, persistido em `companies_api_mutate.py`); `models/shared_email_config.py::SharedEmailConfigResponse` passou a expor `imap_server/imap_port/smtp_server/smtp_port` (não-secretos) para pré-preencher o formulário de edição.
- **Motor de Tarefas Automáticas**: `services/process_assignment.py::_create_post_indexing_tasks`, chamada dentro de `dual_auto_assign_on_pre_registo_transition` logo após a notificação de atribuição. Para cada consultor/mediador recém-atribuído pós-indexação, cria 2 `Task`: "Analisar documentação inicial" (Alta) e "Agendar contacto inicial com o cliente" (Média). `models/task.py` ganhou campo `priority` opcional (`TaskCreate`/`TaskUpdate`/`TaskResponse`), persistido em `run_create_task`. Sem entradas de histórico (evita duplicar ruído com o registo de auto-atribuição já existente); tarefas continuam a ser criadas mesmo quando o actor é "indexacao" (não fazem parte da Auditoria Stealth, que só se aplica ao histórico do processo).
- Testado: suite completa 1183 passed / 6 skipped (novos testes unitários para os 3 modelos + 2 testes de integração para o motor de tarefas + `tests/test_iteration4_features.py` E2E contra a app live). `testing_agent_v3_fork` (iteration_4 + iteration_5): Feature 1 e Feature 3 passaram à primeira; Features 2a/2b falharam na 1ª ronda por apontarem a componentes mortos — corrigido ao localizar a UI real e re-testado com 100% de sucesso na 2ª ronda. Commit `32a1663a`.

## Correções 2026-09-01 (2) — Ajustes cirúrgicos pós-produção (5 pontos)

- **Bug Frontend (Pesquisa Rápida)**: `GlobalSearchModal.jsx::handleSelect` — resultados do tipo "Cliente" navegavam incorretamente para `/clientes?cliente=id` (rota morta, query param nunca lido) ou para o processo associado. Corrigido para navegar sempre para `/cliente/{id}` (rota real, `ClientDetailPage.js`). Adicionados `data-testid="global-search-input"` e `data-testid="global-search-result-{type}-{id}"`.
- **Bug Backend (email de acesso ao portal "perdido")**: investigação aprofundada (reprodução real via `POST /api/public/client-registration` e `POST /api/clients`, com inspeção de `backend.out.log`) mostrou que o trigger **já existe e dispara correctamente** em ambos os fluxos de criação de cliente — `client_crud.py::run_create_client` (Pacote CY, `_send_portal_welcome_email_safe`) e `public_registration.py::run_public_client_registration` (magic-link + fallback de confirmação). A remoção de `onboarding_service.py` (sessão anterior) não continha nenhuma lógica de email. Nenhuma alteração de código foi necessária; confirmado independentemente por `testing_agent_v3_fork` (ver `test_reports/iteration_3.json`). Os emails aparecem como `[EMAIL SIMULATED]` neste ambiente por falta de fornecedor SMTP real configurado (limitação de ambiente já documentada, não é bug).
- **Script de limpeza**: `cleanup_prod_test_data.py` — query expandida com `$or` para também considerar `clients.nome` e `processes.client_name` (antes só e-mail).
- **Novo script**: `backend/scripts/delete_process_by_id.py` — apaga em cascata um processo específico (por `id`, via CLI) e os documentos anexados. Modo `dry-run` por defeito, `--execute` para eliminação real.
- **Schemas IMAP**: `models/company.py` (`CompanyCreate`/`CompanyUpdate`/`CompanyResponse`) ganharam `imap_email`, `imap_password` (só create/update), `imap_host`, `imap_port` — espelhando os campos SMTP já existentes, para suportar Webmail do CRM. `run_create_company` actualizado para persistir os novos campos (update já era genérico via `model_dump`). Sem UI de administração nesta ronda (fora de âmbito, pedido explícito do utilizador).
- Testado: suite completa 1178 passed / 6 skipped (unit) + 67 passed (integration); `testing_agent_v3_fork` confirmou os 2 bugs (routing OK, email trigger já funcional) com 100%/100% de sucesso, 0 action items. Commit `ba9ad1c7`.

## Correções 2026-09-01 — Hotfixes (500/404) + Implementação Backend do Onboarding

- **Bug 500**: `GET /processes/{id}` falhava com `ResponseValidationError` quando `updated_at`/`created_at` era um BSON Date nativo (raiz: `soft_delete_process` sem `.isoformat()`). Fix: `ProcessResponse` usa `Optional[datetime]` + `@field_serializer`.
- **Bug 404**: `portal-messages/unread` — causa raiz era CORS desatualizado em `backend/.env` (preview URL antigo) vs. domínio novo em `frontend/.env`. Corrigido.
- **Onboarding backend**: `onboarding_service.py` (morto) removido; Auditoria Stealth propagada a `dual_auto_assign_on_pre_registo_transition`; notificação (email+in-app) ao consultor/mediador recém-atribuído; checklist dividida em Obrigatórios (CC, Extratos, Mapa de Responsabilidades) e Opcionais (Recibos, IRS, Declaração Patronal) via `SystemConfig.mandatory_documents.optional_documents` (configurável, sem hardcode). Sem UI de administração nesta ronda (backlog).
- Testado por `testing_agent_v3_fork`: 1176 passed, 0 falhas, 0 action items. Commit `245cc4a5`.
- **Backlog remanescente**: UI de administração da checklist no SystemConfigPage; tarefas automáticas para consultor/intermediário (regras por definir).

## Correções 2026-08-31 (2) — Reatividade UI (React Query) + Observabilidade Auto-Fulfill

- **Backend**: `_auto_fulfill_portal_request` (`services/document_upload.py`) regista `logger.warning` estruturado quando `fulfill_portal_requests_on_staff_upload` devolve `reason=weak_match` ou `reason=no_match` (visibilidade sobre falhas silenciosas do motor de correspondência automática). 4 testes novos em `test_portal_fulfill_observability.py`.
- **Frontend**: `queryKeys.portalRequests.byProcess(processId)` (novo em `lib/queryClient.js`) + `usePortalRequestsQuery` hook. `PortalDocumentRequests.js` migrado de fetch local para React Query; `S3FileManager.js` (`executeUpload`/`executeUploadWithResolutions`) invalida essa query após upload bem-sucedido — o consultor vê o estado mudar para "Recebido" sem F5.
- **Limitação conhecida**: validação end-to-end completa da transição automática bloqueada em preview por falta de credenciais AWS/S3 (upload devolve 503); wiring confirmada correta por revisão de código e pelos testes de observabilidade.
- Suite completa: 1135 passed. Commit `58f0496f`.

## Correções 2026-08-31 — Estabilização de Ambiente + Testes Documentos

- **Ambiente do pod (fork) estava sem `.env` (backend/frontend) e com dezenas de dependências de `requirements.txt` não instaladas** — `pip install -r requirements.txt` anterior tinha abortado em `numpy==2.5.1` (exige Python ≥3.12; pod usa 3.11). Corrigido: `numpy==2.4.6` em `requirements.txt`, instaladas todas as dependências em falta (thefuzz, bleach, sentry-sdk, slowapi, python-magic+libmagic1, playwright, pandas, etc.), `.env` reconstruídos (DB local estava vazia, sem risco de dados PII órfãos). Backend/frontend confirmados operacionais (`/api/health` 200).
- **Suite pytest de documentos**: `test_documents.py`, `test_documents_integration.py`, `test_document_extraction_helpers.py`, `test_document_portal_fulfill.py`, `test_document_titular_match.py` → 55/55 passed, 0 regressões.
- **Suite completa** (`tests/unit` + `tests/integration` + raiz, conforme `pytest.ini`): 1162 passed, 6 skipped, 0 falhas.
- **Novos testes para `_auto_fulfill_portal_request`** (`services/document_upload.py` → `services/document_portal_fulfill.py`) em `tests/unit/test_document_portal_fulfill.py::TestAutoFulfillPortalRequest`: fluxo de sucesso (status→RECEIVED + associação `document_id`), fallback de normalização de nome de ficheiro (regressão do bug `cartao_cidadao_joao.pdf` vs alias `cartao_cidadao`), e caso sem pedidos pendentes.
- Commits: `d6c94a48` (testes + fix numpy), `25a5ece7` (worklog).

## Correções 2026-01

### Portal das Finanças & Segurança Social Direta — Scrapers (Bug `selector_desatualizado`)
- **`backend/requirements.txt`**: `playwright-stealth` 1.0.6 → **2.0.3** (a versão antiga falhava no Render por causa de `pkg_resources` em Python ≥ 3.12, daí o warning "não instalado")
- **`backend/services/gov_scraper.py`**:
  - `FINANCAS_AUTH_URL` actualizado para `https://www.acesso.gov.pt/v2/loginForm?partID=PFIN&path=/geral/dashboard&selectedAuthMethod=N` (a URL `/unauthlogin` foi descontinuada)
  - Novos seletores Radix-UI para o portal acesso.gov.pt v2 (`button[role='tab']:has-text('NIF')`, `input[name='username']`, `button[type='submit']`)
  - `SEG_SOCIAL_URL` actualizado para `https://app.seg-social.pt/sso/login` (`/ptss/` redirecionava para a homepage pública)
  - Adicionado clique automático no `#toogleAuth` da SSD para expandir o formulário (que vem colapsado)
  - `_apply_stealth()` migrado para a API `Stealth().apply_stealth_async(context)` da v2.x, com fallback automático para a API v1.x
- Selectors validados localmente contra os portais reais ✅

### Cartão "Contactos" do Processo não guardava
- **`frontend/src/pages/ProcessDetails.js`**:
  - Ao carregar o processo, contactos do Cliente (`cData.contacto.email/telefone`) são agora sincronizados para `process.client_email/client_phone` quando o processo ainda não os tem
  - No save, deixou de enviar `contacto: { email: "", telefone: "" }` para o `/clients/{id}` — antes apagava os contactos válidos do Cliente (merge `{**existing, **incoming}`)
  - Corrigido bug onde `prev.phone || prev.telefone` (referência ao process) era usado em vez de `pd.phone || pd.telefone` (personal_data)

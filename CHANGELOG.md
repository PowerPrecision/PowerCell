# Changelog

Todas as mudanças notáveis neste projeto serão documentadas neste arquivo.
O formato é baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.0.0/).

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

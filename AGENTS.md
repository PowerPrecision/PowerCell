# AGENTS.md

## Cursor Cloud specific instructions

This repository is the **PowerCell** product (see `README.md` / `ARCHITECTURE.md`): a credit-process CRM made of a FastAPI backend (`backend/`) + React/Vite SPA (`frontend/`) + MongoDB.

The update script already installs all dependencies (frontend yarn deps and the backend Python venv at `backend/.venv`). System packages (`mongodb-org`, `libmagic1`, `python3.12-venv`) are baked into the VM image — do NOT reinstall them.

### Services & how to run them

| Service | Dir | Command | Port | Notes |
|---|---|---|---|---|
| MongoDB | — | `mongod --dbpath ~/data/db --bind_ip 127.0.0.1 --port 27017` | 27017 | No systemd; start manually. Required by the backend. |
| Backend (FastAPI) | `backend/` | `.venv/bin/uvicorn server:app --host 0.0.0.0 --port 8001` | 8001 | See env overrides below. Health: `GET /health`. |
| Frontend (React/Vite) | `frontend/` | `yarn dev` | 3000 | Vite, `strictPort`. `frontend/.env` sets `REACT_APP_BACKEND_URL=http://localhost:8001`. |

### Non-obvious gotchas

- **MongoDB Atlas is unreachable** from this environment (egress-restricted DNS). The committed `backend/.env` points `MONGO_URL` at Atlas — for local dev you MUST override it to a local Mongo. `backend/database.py` auto-disables TLS for `mongodb://localhost`. Start the backend with:
  `MONGO_URL="mongodb://localhost:27017" DB_NAME="PowerCell_dev" ENVIRONMENT="dev" .venv/bin/uvicorn server:app --host 0.0.0.0 --port 8001`
- **Seed users:** `cd backend && MONGO_URL="mongodb://localhost:27017" DB_NAME="PowerCell_dev" SEED_ADMIN_PASSWORD="Admin123!" SEED_DEFAULT_PASSWORD="PowerPrecision2026!" .venv/bin/python seed.py`. Login is `POST /api/auth/login-v2`. The `admin@sistema.pt` account has the hardcoded password **`admin`** (not the env var); `geral@powerealestate.pt` uses `SEED_ADMIN_PASSWORD`.
- **Backend tests:** `pytest.ini` declares an `env =` block but `pytest-env` is NOT installed, so those vars are ignored. Pass env explicitly and use `--no-cov` for speed, e.g.:
  `cd backend && MONGO_URL="mongodb://localhost:27017" DB_NAME="test_db_precision" JWT_SECRET="test_secret_key_123456789012345678" CORS_ORIGINS="http://localhost:3000" TESTING="true" ENVIRONMENT="dev" .venv/bin/python -m pytest tests/unit --no-cov -q`
- **tests/unit = SEM MongoDB vivo:** o job `backend-fast` do CI corre `pytest tests/unit/` SEM serviço de Mongo (por design — é o job rápido; só `backend-full` e `e2e-smoke` têm Mongo). Testes unitários que exercitem serviços com persistência têm de **mockar a camada `db`**: usar a fixture `fake_async_db` (`tests/unit/conftest.py` — `FakeAsyncDatabase`/`FakeAsyncCollection` in-memory, acesso por atributo como o `DatabaseProxy` real) com `patch.object(modulo_do_servico, "db", fake_async_db)`. Testes que precisem de I/O real de Mongo vivem em `tests/integration/` (marcador `integration` já declarado no `pytest.ini`). Regressão de referência (2026-09-02): os testes IMAP de company/shared-email config faziam I/O real e rebentavam o `backend-fast` com `ServerSelectionTimeoutError`.
- Optional integrations (Redis/ARQ worker, S3, OpenAI/Gemini, email/IMAP, Sentry) all degrade gracefully and are not needed to run the app. The ARQ worker (`backend/worker.py`) only runs when `ENVIRONMENT=production`.
- **Credentials in `backend/.env` are DEV-only** (owner clarification): production does not use this file — it injects secrets via the platform's secret manager. So the values present here are not production secrets; no need to treat them as a production leak or block on rotating them. Use `.env.example` as the template for required vars.
- **Documentos IA (S3FileManager):** botões **Analisar IA** / **Renomear IA** só para `effectiveRole` ∈ `MANAGEMENT_ROLES` (`admin`, `ceo`, `diretor` — “gestor” no produto). Backend: `require_roles([ADMIN, CEO, DIRETOR])` em `/documents/ai-analyze`, `/rename-smart`, `/rename-all-smart`. Docs com `document_metadata.ai_analyzed` aparecem com badge **IA** e são saltados em re-análise. Renomear IA faz `categorize-all` antes de `rename-all-smart` para gerar nomes legíveis.
- **Onboarding público (após Jul 2026):** registo **não** cria processo. Cria cliente + `titular2_data` no cliente + pedidos `mandatory_checklist` (SystemConfig) por `client_id`. Processo é criado só quando a checklist está completa (`onboarding_mandatory_config`). Na criação copia `titular2_data` → processo. Uploads portal sem processo → orphans Index. Pós-Index: **sempre** dual-assign consultor+intermediário. IA: `document_titular_match` compara com titular1/2 já no processo; `needs_user_choice` só se ambíguo.
- **UI titular ambíguo:** ProcessDetails recebe `titular_matches` / `needs_titular_choice` do `ai-analyze`; dialog “Este documento é de quem?” (Titular 1 / 2 / Ignorar). Apply usa `target_titular` em `/documents/ai-apply-suggestions` → `titular2_data.*` quando 2º titular.
- **Portal docs enviados:** upload do **cliente** (`portal/confirm-upload`) marca REQUESTED→RECEIVED. Upload da **equipa** no CRM (`document_upload` / `confirm-upload` + pós `auto_categorize`) chama `document_portal_fulfill` para o mesmo efeito no portal do cliente (match por categoria/label).
- **O `file_key` que o cliente do Portal envia NÃO é de confiança (Incidente P0, Set 2026).** `portal/confirm-upload` aceitava o `file_key` do CORPO do pedido e validava-o só com `s3_service.file_exists()`: um titular autenticado enviava `backups/dump-2026-09-01.zip` e recebia na resposta (`temporary_url`) um URL pré-assinado para o descarregar — no mesmo bucket vivem os documentos de TODAS as redes, os `backups/*.zip` e os `companies/*`. Pior: o registo criado em `db.documents` com esse `s3_path` fazia o `/portal/download-url` (esse, bem guardado) autorizar a chave para sempre. As duas guardas do Épico 9 (`assert_path_within_document_root` + `assert_s3_file_belongs_to_process`) existiam e descreviam o ataque na própria docstring, mas estavam ligadas só ao CRM — **o Portal, a única superfície externa, ficou fora da parede; cada camada validava, a combinação não** (mesma forma do placebo `build_company_scope_condition` do Lote 4). Hoje `portal_upload_ops.assert_portal_file_key_e_do_cliente` é o ponto único, ligado aos DOIS caminhos: escrita **e** leitura (na leitura não é zelo — é o que neutraliza os registos que a janela vulnerável já deixou na colecção). Três detalhes que não se podem perder: (1) a guarda corre **antes** do `file_exists`, senão o código de resposta (403 vs 400) vira **oráculo** do conteúdo do bucket; (2) sem dono (`_dono_do_prefixo_s3` devolve `None`) recusa-se — o degradado de `assert_s3_file_belongs_to_process` com nome vazio aceita toda a raiz `Documentação Clientes/`, o que no CRM é um incómodo e no Portal era a fuga; (3) a guarda da **raiz** parece redundante (a de posse deriva prefixos que já começam por ela, e apagá-la não matava nenhum teste) mas o trabalho dela é outro — defende de um `s3_folder` **envenenado** que aponte para fora da árvore de documentos. `temporary_url` saiu da resposta de propósito (o `ClientPortal.jsx` nunca o leu) e os três endpoints ganharam `@limiter.limit` — no Portal o `sub` do JWT é o `process_id`, logo o limite é por processo. **Não** acrescentar rejeição de `..`: as chaves S3 são opacas e a assinatura fica presa à chave exacta — seria um placebo. Cobertura: `tests/unit/test_portal_upload_path_traversal.py` (os testes de `TestAExploracao` são o ataque, escritos para morder primeiro).
- **Toasts BG:** sticky em `TasksContext` (`duration: Infinity`); **não** fazer `toast.dismiss` quando a tarefa sai de `/tasks/active` — o Toaster está fora do `BrowserRouter` e deve sobreviver a mudanças de página (só o utilizador fecha com X). `visibleToasts={8}`.
- **ProcessDetails writes (TanStack):** load via `useProcessFullData` / `useProcessQuery`; gravações via `useProcessMutations` (`updateProcess` / `updateClient` / assign / activities / deadlines). **Nunca** enviar `documents` / `onedrive_links` / arrays vazios no PUT — `sanitizeProcessUpdatePayload` em `pages/processDetails/processUpdatePayload.js` (allow `labels:[]` só no save org). Optimistic merge nested. Dialog atribuições: `ProcessAssignDialog`. Ainda híbrido: RGPD / AI analyze-apply / magic-link usam `fetch` pontual.
- **Frontend UX/UI norms → ver `FRONTEND_GUIDELINES.md`** (Progressive Disclosure, layout 2/3+1/3, eliminação de cartões redundantes para metadados simples, `Dialog`/`Sheet` para formulários secundários, `EmptyState`/`PageHeader` canónicos, regra ESLint de cores, utilitários centralizados). Ler antes de tocar em `ProcessDetails`, dashboards ou qualquer página densa.
- **ESLint `no-restricted-syntax` (Dark Mode safe colors):** `frontend/eslint.config.js` bloqueia (nível `warn`; **CI usa `--quiet`**, i.e. só falha em `error`) classes Tailwind de cor cruas (`bg-gray-500`, `text-blue-600`, `border-red-500`, etc.) em `className`/`class`/`cn()`/`clsx()`/`classnames()`/`cva()`. Código novo usa sempre tokens semânticos do Shadcn (`bg-primary`, `text-muted-foreground`, `bg-destructive`, `border-border`, …). Código legado (~2700 avisos) fica como aviso — não bloqueia CI, não copiar padrão para ficheiros novos.
- **ProcessDetails redesign (Progressive Disclosure, PR #597–#601):** `PageHeader` partilhado com `titleBadge` (Status) + ações à direita; grid `grid-cols-1 lg:grid-cols-3` — 2/3 esquerda = Tabs (Resumo/Documentos/Histórico), 1/3 direita = `ClientContextCard` + `AssignmentContextCard` (consultor/mediador + prazos + Prioridade como `DropdownMenu`+`Badge`, botão "Gerir" → `ProcessAssignDialog`) + Tarefas + Imóveis Compatíveis. Separador Histórico (`HistoryTab.jsx`) consolida timeline de fases + "Atividades Recentes" (`ScrollArea` `h-[500px]`) + formulário "Registar Atividade" atrás de um `Dialog` + "Filme da Lead". `ProcessStickyHeader` removido (substituído pelo novo cabeçalho + cartões de contexto).
- **Atribuição: campos CANÓNICOS (bugfix cartão em branco):** quem grava uma atribuição tem de escrever o conjunto completo — consultor: `assigned_consultor_id` + `assigned_consultor_ids` + `consultor_id` + `consultor_name` + `consultor_names` (+ `consultant_id`, legado, que `process_list_filters` usa em "Os Meus Processos"); mediador: `assigned_mediador_id` + `assigned_mediador_ids` + `mediador_name` + `mediador_names` (+ `mediador_id`). O `AssignmentContextCard` lê `consultor_names` → `assigned_consultor_ids` → `assigned_consultor_id` (`resolveAssignedNames`); a `dual_auto_assign_on_pre_registo_transition` gravava só `consultant_id` e o cartão ficava **em branco** apesar de a atribuição correr bem e a Timeline mostrá-la. Referência da forma correcta: `client_assign.py`. O `run_mark_indexed_side_effects` difunde um **segundo** delta (`broadcast_assignment_delta`) DEPOIS da atribuição — o primeiro broadcast corre antes e só leva o estado; `ProcessDetails` funde-o com `utils/processDelta.applyProcessDelta`. Cobertura: `tests/integration/test_e2e_financial_realtime.py`.
- **Event-Driven (Redis Pub/Sub → WebSocket):** tarefas pesadas publicam `task_started`/`task_progress`/`task_completed`/`task_failed` no canal `powercell_system_events` (`services/redis_pubsub.py`, `redis.asyncio` sobre `REDIS_URL` — **não** `redis_cache.py`, que é Upstash **REST** e não suporta SUBSCRIBE). `websocket_manager.route_system_event` encaminha **só** para as ligações do `user_id` do envelope; envelope sem `user_id` é **descartado**, nunca difundido (tenant-safety fail-closed). O listener arranca em **TODOS** os workers (`server.py` startup, deliberadamente FORA do guard `_is_primary_worker`) — sem isso um evento do worker A não chega a um socket do worker B. **Emissores = 3 pontos de estrangulamento**, não código espalhado: `TaskLogService.create_task/update_task`, `BackgroundJobService.*` e `routes/ai_bulk/jobs.py::{create,update,finish}_background_job_db` — todos via `services/task_events.py` (payload único). Falhas nunca propagam: Redis em baixo → entrega in-process + `publish_event` devolve `False`; a tarefa segue. Frontend: `hooks/useTaskEvents.js` (subscrição) + `utils/taskEvents.js` (merge puro, testado); **o polling é FALLBACK, não foi apagado** — `TasksContext`/`useBackgroundJobsQuery`/`TasksPanel` param o intervalo quando `isConnected` e retomam-no quando o WS cai.
- **Testes e `from database import db` ao nível do módulo (ordem de import):** um serviço que faça `from database import db` no topo fica com a SUA referência ao proxy. `patch("database.db", fake)` só o apanha se esse módulo **ainda não tiver sido importado** — logo o teste passa ou falha conforme a ORDEM em que o pytest recolhe os ficheiros. Foi o que aconteceu com `task_log_service` na bateria financeira: bastava um teste unitário importar `task_log_service`/`task_queue`/`scheduled_tasks` antes (ex.: `test_task_extraction_helpers.py`) para o `create_task` escrever no proxy real, a excepção ser engolida e a bateria ficar sem eventos — verde isolada, vermelha na suite completa do CI. **Regra:** patchar SEMPRE `patch.object(modulo, "db", fake)` para cada módulo da cadeia, além de `patch("database.db", fake)` (que só cobre os `from database import db` feitos DENTRO de funções). `_emit_event_safe` loga agora a `warning` e não a `debug` — um Redis em baixo não chega lá (o `publish_event` trata disso), por isso uma excepção nesse ponto é sempre inesperada e não pode ficar invisível.
- **Webmail Pro & Live Sync (Épico 5):** o `new_email` já existia (`services/email_realtime.py`) mas entregava pelo **ConnectionManager em memória** — com vários workers, um email sincronizado no worker A nunca chegava a um socket no worker B (`is_user_connected` respondia `False` e o evento morria em silêncio). Passa por `redis_pubsub.publish_event` (canal `powercell_system_events`, um envelope POR destinatário); o nome na rede continua **`new_email`**, não `email_received` — o dispatcher do frontend já o escuta e um segundo nome obrigaria ambos os lados a conhecer os dois. `notify_new_email` **não** filtra por `is_user_connected`: quem sabe se há socket é o worker dono da ligação. Frontend: `utils/webmailRealtime.js` (puro, testado) insere a linha na cache do React Query — sem GET — quando o email pertence à lista aberta (1ª página, sem pesquisa, mesma pasta/caixa); fora disso invalida com `refetchType: "none"`. O polling de contagens em `WebmailPage` **para** quando `isConnected` e retoma se o WS cair. **Threading (RFC 5322):** o CRM lia `Message-ID`/`In-Reply-To` do IMAP (Smart Threading) mas **enviava sem eles** — cada resposta nascia órfã. `services/email_threading.py` (puro) + `send_email(in_reply_to=, references=)` gera `Message-ID` próprio e propaga a cadeia; `EmailSendRequest` → `build_pending_send_record` → `execute_pending_email_send` transportam-nos (o envio real acontece depois da janela de undo, noutro job). Agrupamento em conversas: `utils/emailThreads.js` (`threadKey`: raiz de `references` → `in_reply_to` → `message_id` → assunto normalizado), **por página** (30 emails) — uma conversa que atravesse a paginação aparece como dois grupos. `send_email` só arquiva em `db.emails` quando há `process_id` (sem processo, o email volta pelo sync da pasta Enviados) — não "corrigir" sem pensar em duplicados. Cobertura: `tests/integration/test_e2e_webmail_realtime.py`, `tests/unit/test_email_threading.py`, `utils/{emailThreads,webmailRealtime}.test.js`.
- **Motor de Simulação Financeira (DSTI & Cenários):** validar a indexação (`mark-indexed`/`set-indexed` ON) de um processo de **crédito** com documentos financeiros indexados dispara, em background, `services/financial_engine.trigger_financial_engine_after_indexing`. Cadeia: detecção (tipos derivados de `document_ai_analyze.DOCUMENT_TYPE_FOLDERS` → pasta `Financeiros`) → extracção (cache `document_metadata.extracted_data`, só depois `ai_document.analyze_document_from_base64`) → `ClientDataAggregator` → `financial_simulator` (puro: sistema francês + TAEG + DSTI via `dsti_service`, Euribor via `euribor_service`) → `financial_proposal_pdf` → S3 `Propostas/` + `document_metadata` (`ai_subcategory: "Proposta Financeira"`). **Parâmetros em `SystemConfig.financial_simulator`** (spreads, índice Euribor, prémio de taxa fixa, período fixo da mista); prazo/LTV/validade vêm de `credit_services` e o limite DSTI de `dsti_analysis.critical_risk_threshold` — **não duplicar**. Falha (IRS ilegível, S3 em baixo) → `flag_manual_review`: `process.financial_simulation.status = "needs_manual_review"` + atividade de sistema + TaskLog FAILED; a indexação **nunca** é revertida. A resposta do endpoint traz `financial_engine: {triggered, reason, task_id, documents}` — é o que alimenta o toast `utils/financialEngineFeedback.js` e o `TasksPanel` (que já mostra background jobs dentro do processo).
- **Calculadoras (`/calculadoras`):** `CalculatorsPage.js` → `components/calculators/MortgageSimulator.jsx` (Capital/Prazo/Taxa, toggle `Switch` "Incluir Seguros" com Progressive Disclosure para Seguro de Vida/Multirriscos) + acesso rápido a DSTI/Risco (dialogs existentes). Motor de cálculo puro em `utils/mortgageCalculations.js` (`calcularPrestacaoMensal` / `calcularTAEG` / `simularCreditoHabitacao`), extraído de `components/portal/SimulatorCH.jsx` (Portal do Cliente) — reutilizar este utilitário em vez de duplicar a matemática.
- **Config de email: escrever e ler TÊM de usar a mesma chave (incidente 2026-09-21).** O `user.email_config` pode ser ANINHADO. O envio (`email_documentation` → `resolve_email_config_for_sync` → `_extract_role_email_config`) lê por esta ordem: `email_config["company:<id>"]` → `email_config[<papel UCR>]` → `email_config["default"]`. O papel vem de `resolve_active_ucr_role` (lê o UCR na BD; **nunca** `None`). O guardar e o testar em `users_api_email_config.py` resolviam o papel de outra maneira — só usavam `X-Active-Role` quando este DIFERIA do papel base, caindo em `"default"` no caso comum. Sem empresa activa, escrevia-se em `"default"` e lia-se de `[<papel>]`: uma sub-config antiga sombreava a password acabada de guardar, o botão **Testar dava verde** (testava `default`) e o envio falhava com `535 Incorrect authentication data` — e voltar a gravar não resolvia. **Regra: qualquer handler que leia ou escreva config de email resolve o papel com `resolve_active_ucr_role`, a mesma função do envio.** Cobertura: `tests/unit/test_email_config_write_read_key.py` (inclui guarda sobre o código-fonte dos handlers).
- **Conta de envio: `email_config_resolver.resolve_sending_account` é o ponto ÚNICO.** Devolve `(EmailAccount | None, source)` seguindo perfil activo (`resolve_active_ucr_role` + `resolve_email_config_for_sync`) → Caixa Geral → nenhuma. `email_documentation` (send-documentation) e o envio de teste usam-na; **não reconstruir esta cadeia em linha** — foi tê-la duplicada que produziu o incidente de 2026-09-21. O `source` devolvido (`profile:<config_source>` / `caixa_geral`) vai nas respostas de erro de propósito: sem ele, diagnosticar um envio falhado obriga a ler os logs do servidor.
- **Dois testes de email, e fazem coisas diferentes:** `POST /users/me/email-config/test` faz `login()` em IMAP **e** SMTP (`gmail_oauth.test_imap_connection`, `success = imap_ok and smtp_ok`) — prova credenciais, nada mais. `POST /users/me/email-config/send-test` envia um email REAL para o próprio utilizador pelo `send_email` de produção — prova a entrega. Relay recusado, política de remetente, tamanho de anexo e rate limits só falham DEPOIS do login, e era essa a lacuna. O envio de teste não leva `process_id` de propósito (o `send_email` só arquiva em `db.emails` quando há processo, e um teste não tem de poluir o histórico). Cobertura: `tests/unit/test_email_send_test.py`.
- **`fetch` cru perde o `X-Company-Id` — e isso muda a conta de email usada (incidente 2026-09-21, 3ª instância).** O interceptor que injecta `X-Company-Id` / `X-Active-Role` vive no cliente **Axios** (`services/api.js`). Um `fetch` cru só leva o que lhe escreverem à mão. Sem `X-Company-Id`, o `get_active_company_id_async` cai em `user.company`, que é o **NOME** da empresa e não o id — a procura da config de email por `company_id` falha, cai numa sub-config antiga e o envio sai com a password errada (`535`). Sintoma que o denunciou: o **email de teste funcionava** (vai por Axios, do `EmailConfigForm`) e o **envio para balcões falhava** (ia por `fetch`, do `SendDocumentationModal`), com a mesma conta. **Regra: qualquer chamada que dependa de contexto de empresa/papel vai pelo `api` do Axios, nunca por `fetch`.** Cobertura: `src/components/sendDocumentation.test.js`.
- **UCR / headers (Pacote FN):** `X-Company-Id` é o **company_id** canónico, nunca `user.company` (nome). `AuthContext` resolve via `resolveCompanyIdFromUser` e faz `syncAuthContextHeaders` — o interceptor Axios prefere este snapshot ao `sessionStorage`. Backend (`_find_ucr`) casa `company_id` **ou** `company_name` (case-insensitive). Se o JWT já tem o cargo e o user pertence à empresa, `get_effective_role_async` honra o header (não esvaziar `/processes/me` com fallback silencioso).
- **Os Meus Processos (`/processos`):** `GET /processes/me` (`process_list_filters`, `mine_only`) filtra por atribuição + empresa (id ou nome). `ProcessesPage` **não** escreve `"all"` em `sessionStorage.activeRole` (não é um UCR). Dependências do fetch têm de ser estáveis (`useMemo` em `assignedUserIdsFilter`) — arrays novos em cada render = loop infinito, sobretudo com lista vazia. `/lista-processos` = `GET /processes?show_all=true`. `/meus-clientes` é **Os Meus Clientes** (`MyClientsPage`), não processos.
- **URL do backend no frontend: importar de `utils/apiBaseUrl.js`, nunca repetir o literal (Set 2026).** Seis módulos tinham `process.env.REACT_APP_BACKEND_URL || "https://powercell.onrender.com"` e o `define` do `vite.config.js` aplicava o mesmo fallback em QUALQUER modo — um build de dev sem a variável falava com a **API de produção**, em silêncio. A regra vive agora num ponto único (`resolveApiBaseUrl` runtime, `resolveBuildTimeBackendUrl` build, importado pelo `vite.config.js`): host local ou modo ≠ production sem variável → `http://localhost:8001`. Código novo importa `BACKEND_URL`/`API_BASE_URL`. Cobertura: `src/utils/apiBaseUrl.test.js`.
- **O pacote `backend` NÃO existe em runtime.** A app corre com `backend/` na raiz do `sys.path` (`from config import ...`, `from database import db`). Um `from backend.config import ...` levanta `ModuleNotFoundError` — e se estiver dentro de um `try/except` mudo, falha para sempre sem ninguém dar por isso: foi o que manteve o CORS do bucket S3 de **todos** os ambientes com a lista hardcoded de produção. Qualquer `except` à volta de um import tem de registar o motivo.
- **Scripts de seed abortam contra produção.** `scripts/env_guard.py::require_non_production_db(nome)` é a PRIMEIRA instrução do `__main__` dos 8 scripts de mock data. Bloqueia por `ENVIRONMENT`/`APP_ENV` de produção ou `DB_NAME` com "prod"; escape `ALLOW_SEED_IN_PRODUCTION=true`; ambiente sem variáveis (CI) não é bloqueado. Um script de seed novo tem de o chamar — `tests/unit/test_scripts_env_guard.py` verifica por AST.
- **Testes do frontend: Vitest + jsdom + React Testing Library (Épico 6).** `yarn test` (uma vez), `test:watch`, `test:coverage`; o CI corre `yarn test` e falha o pipeline. A configuração vive no bloco `test` do `vite.config.js`, não num `vitest.config.js` à parte, para herdar o alias `@`, o `define` do process.env e o **loader JSX para ficheiros `.js`** (há JSX dentro de `.js` neste projecto). Os testes antigos importam `describe`/`it` de `node:test`: um alias para `src/test/nodeTestShim.js` traduz isso para a API do Vitest — sem ele registavam-se no corredor do Node e o Vitest não via nada, **sem falhar**. Código novo importa de `vitest`. `src/test/setup.js` liga o jest-dom, faz `cleanup()` e preenche `matchMedia`/`ResizeObserver`/`scrollIntoView` que o jsdom não traz. O corredor `node --test` foi REMOVIDO — dois motores de teste é o padrão dos dois caminhos.
- **Webmail: Página/Contentor + componentes de apresentação (Épico 6).** `WebmailPage.jsx` (3288 → 2237 linhas) detém estado, hooks, efeitos e handlers; a UI vive em `components/webmail/` (`FolderNavigation`, `EmailList`, `EmailThreadViewer`, `EmailComposer`, `webmailFormatters`). **Nada de `set*` dentro de um componente de apresentação** — ele diz o que aconteceu (`onSelectFolder(id)`) e o contentor decide o que isso implica. O agrupamento em conversas, o `useNewEmailRealtime` e a suspensão do polling ficam no contentor: o tempo real do Épico 5 não atravessa a fronteira. Props explícitas com contrato em JSDoc, nunca `{...props}`. Regras completas em `FRONTEND_GUIDELINES.md` § 20.
- **`react/jsx-no-undef` é bloqueante.** O `no-undef` não cobre JSX e esta regra estava desligada: um `<Loader2 />` sem import passava no CI e só rebentava no clique do utilizador. Activada no Épico 6, apanhou logo mais 15 casos reais no código existente. Um componente novo que use um ícone tem de o importar — o build não protesta, o eslint agora sim.
- **Dependências novas do frontend TÊM de instalar em Node 20.** O CI corre Node 20 e o frontend é construído na Vercel e como static site no Render — nenhum deles fixa a versão no repositório. Uma devDependency que exija Node ≥22 não parte só o CI: parte o `yarn install` do DEPLOY. Aconteceu no Épico 6 (`@testing-library/jest-dom@7` e `jsdom@30` exigem ≥22; localmente há Node 22 e passou despercebido). Versões fixadas por isso: `jest-dom@6.9.1` e `jsdom@^26`. Antes de acrescentar uma dependência, verificar `npm view <pkg> engines.node`; para provar, correr o install com um Node 20 avulso (`curl -sSL https://nodejs.org/dist/v20.20.2/node-v20.20.2-linux-x64.tar.xz | tar xJ`) sobre uma cópia de `package.json` + `yarn.lock`.
- **A página do Webmail tem teste de integração** (`pages/__tests__/WebmailPage.test.jsx`). Falseia só quatro fronteiras — `DashboardLayout`, `AuthContext`, `useWebmailEmails`/`useNewEmailRealtime` e o `fetch` — e ainda o `ui/resizable` (o `react-resizable-panels` mede elementos e no jsdom tudo tem dimensão zero). O estado, os handlers e os componentes extraídos são os REAIS. Foi o primeiro destes testes que apanhou a página a rebentar no arranque: um `useCallback` declarado ANTES daquele de que depende, com a dependência na lista — um `const` na zona morta temporal, avaliado no próprio render. Nem o eslint, nem o build, nem os 70 testes de componente viram; nada montava a página. **Um componente extraído de uma página só está coberto quando a página também é montada num teste.**
- **A pasta `skills/` NÃO é código do produto.** `skills/{ASR,LLM,TTS,VLM,…}/` são pacotes de documentação de fornecedor (`SKILL.md` + exemplos `.ts`) para o `z-ai-web-dev-sdk` — TypeScript, SDK não instalado, zero referências no `backend/` ou no `frontend/src/`. Não são importáveis. O motor de voz que corre a sério é `services/voice_transcription.py` + `services/voice_extraction.py`, em Python, sobre o cliente OpenAI já existente (`ai_document.get_openai_client`).
- **Nota de voz do consultor (Épico 7):** `POST /api/processes/{id}/voice-notes` valida, arquiva o áudio no S3 (`Notas de Voz/`), cria um `TaskLog` do tipo `VOICE_NOTE` e **devolve** — transcrição, extracção, escrita na timeline e criação de tarefas correm em `spawn_background_task` (`voice_note_engine.run_voice_note_pipeline`). O tempo real vem dos eventos `task_*` do Épico 4 (sem nome de evento novo); o `result_data` do evento terminal leva `{voice_note_id, activity_id, task_ids, aviso}`. O resumo entra em `db.activities` com `origin="voice_note"` e autor = o consultor (não "Sistema"); as tarefas nascem por `task_api_crud.run_create_task` — **nunca** `db.tasks.insert_one` directo, senão perdem o prefixo `[PROC-012]`, o histórico e a notificação. Falha do LLM ≠ falha da nota: a transcrição entra na timeline à mesma (`status: "partial"`). `update_progress` sozinho não muda o estado — sem `status=PROCESSING` explícito, `resolve_event_type` emite `task_started` em cada actualização e a barra de progresso nunca anda.
- **Motores de IA de voz: dev simula, sempre.** `VOICE_ASR_PROVIDER`/`VOICE_LLM_PROVIDER` (`openai`|`mock`); **sem variável, só produção COM chave usa o motor real** — ter chave no `.env` local não é autorização para a usar, e um valor desconhecido cai no simulado (falha fechada). Modelo do LLM pelo painel de admin (`voice_note_extraction`), nunca no código. Datas relativas: `voice_extraction.resolver_data_relativa` devolve `None` para o que não souber resolver — uma tarefa com prazo errado é pior do que uma sem prazo. Cobertura: `tests/unit/test_voice_extraction.py`, `test_voice_note_providers.py`, `tests/integration/test_e2e_ai_consultant.py`, `utils/voiceNote.test.js`, `VoiceNoteRecorder.test.jsx`, `HistoryTab.voiceNote.test.jsx`.
- **Extrair de ficheiros grandes: medir a superfície de props ANTES de cortar (Épico 8).** Um bloco de JSX grande não é, por si, candidato a extracção — decide o número de símbolos do CONTENTOR que usa. ≤10 extrair; 10–25 só se agrupáveis em famílias coesas (`dragHandlers`, `fileActions`); >25 não extrair sem redesenhar. As ~230 linhas de cola do separador Resumo do `ProcessDetails` usam **55** e só passam props aos separadores já extraídos: ficaram onde estão, de propósito. Ordem obrigatória: teste que monta o ecrã → medir → cortar do menor risco ao maior (um commit por peça) → teste de componente → mutação. Regras completas em `FRONTEND_GUIDELINES.md` § 22.
- **`ProcessDetails` tem teste de integração** (`pages/__tests__/ProcessDetails.test.jsx`). Falseia só `DashboardLayout`, `AuthContext`, `useWebSocket`, `useProcessFullData`, `useProcessMutations`, `useProcessPortalMessages`, `useTaskEvents` e o `fetch`; separadores, cartões de contexto e o gravador de notas de voz são os REAIS. Apanhou no primeiro arranque um bug que estava em produção: **revisitar um processo dentro do `staleTime` (60 s) deixava a página presa no esqueleto**. O efeito que limpa o estado ao mudar de processo está declarado DEPOIS do que hidrata o formulário — na montagem corriam ambos, hidratar e desfazer. Na primeira visita a query resolvia a seguir e `dataUpdatedAt` mudava; numa revisita, o TanStack serve a cache no primeiro render, `refetchOnMount: true` não dispara (não está stale) e nada volta a hidratar. **Na montagem não há nada a limpar** — o efeito distingue agora montagem de mudança de processo. Não "simplificar" essa guarda.
- **`S3FileManager`: tudo pelo cliente Axios, zero `fetch` (Épico 8).** Eram 25 chamadas `fetch`, nenhuma com `X-Company-Id` e três com `X-Active-Role` escrito à mão — quarta instância do incidente de 2026-09-21. Hoje passam por funções de `services/api.js` (`getProcessS3Files`, `uploadProcessS3File`, `getS3FileContent`, `aiAnalyzeS3Documents`, …). Três detalhes que não se podem perder: (1) o ramo do **403 honra `skipErrorToast`** (antes só valia nos 500+) porque a listagem precisa do aviso LOCALIZADO do PACOTE 11 e não de um toast global por cima; (2) `responseType: "blob"` faz o corpo de ERRO vir também como Blob — `readBlobErrorBody` lê-o como texto, senão a lista de campos em falta da geração de minutas desaparece em silêncio; (3) o conteúdo dos ficheiros continua a vir pelo **proxy do backend**, que é o que evita o CORS do bucket — nunca reintroduzir URL pré-assinado. Guarda: `components/s3FileManagerTransport.test.js` (ignora comentários de propósito, senão a explicação da regra fá-lo-ia ficar vermelho).
- **Extracção de dados por documento (Épico 9): a IA propõe, o utilizador dispõe.** `POST /api/processes/{id}/documents/extract` recebe o **caminho S3** de um ficheiro já arquivado (`routes/document_extraction.py` → `services/document_vision_extract.py`), lê-o e devolve os dados comparados com a ficha — **não escreve nada**. Quem escreve continua a ser `/documents/ai-apply-suggestions`, depois de o consultor confirmar no `AIReviewDialog`. O diálogo abre SEMPRE, mesmo sem conflitos: "sem conflitos" significa que a ficha está vazia e que TUDO o que a IA leu vai entrar. **Não há motor novo** — `services/vision_extraction.py` não existe de propósito: o motor é o `ai_document.analyze_with_vision` (+ `convert_pdf_to_image`, `resize_image_base64`, `get_document_tool_definition`) e o diálogo é o `AIReviewDialog`, que ganhou `newValues`/`sourceDocument` opcionais em vez de um `VLMReviewDialog` paralelo. A análise NÃO foi duplicada: `run_ai_analyze_documents` e a extracção por ficheiro partilham `document_ai_analyze.run_analysis_on_documents`; só muda a origem dos bytes. `skip_analyzed=False` nesse caminho salta E não marca `ai_analyzed` — marcar sem ter aplicado nada à ficha esconderia o documento da análise em lote para sempre. **Duas guardas de caminho, não uma:** `assert_path_within_document_root` (backups e logótipos vivem no mesmo bucket) E `assert_s3_file_belongs_to_process` (o processo do vizinho). Formato não suportado é recusado ANTES do S3 — um `.docx` seguiria para uma chamada paga e voltaria vazio. Cobertura: `tests/unit/test_vision_extraction.py`, `tests/integration/test_e2e_vlm_extraction.py`, `utils/documentExtraction.test.js`, `AIReviewDialog.extraccao.test.jsx`, `S3FileManager.extraccao.test.jsx`.
- **Modelo de IA: nunca fixo no código.** `ai_document.AI_MODEL` é a OMISSÃO, não o modelo em uso. Quem manda é o painel de admin (tarefa `document_analysis`), lido por `ai_document.resolve_ai_model()` → `ai_document_analyzer.resolve_document_analysis_model()` (import tardio: o analyzer importa deste módulo e um import no topo fecharia o ciclo). `call_openai_api` aceita o modelo já resolvido; `analyze_with_text`/`analyze_with_vision` resolvem uma vez e reportam o modelo REAL. Um `"model": AI_MODEL` numa chamada não parte nada — apenas ignora o que o administrador configurou —, por isso há uma guarda sobre o código-fonte (`test_nenhuma_chamada_usa_a_constante_fixa`).
- **Caderneta Predial tinha mapeador mas não tinha esquema.** `build_update_data_from_extraction` sabia traduzir caderneta → ficha, mas `get_document_tool_definition` não tinha ramo: a IA caía no genérico, devolvia texto livre e o mapeador não encontrava nada — extracção "com sucesso", ficha vazia. Os nomes dos campos do esquema **não são livres**: `artigo_matricial`, `valor_patrimonial_tributario`, `area_bruta`, `localizacao`, `tipologia` têm de casar EXACTAMENTE com o `field_mapping` do mapeador. O prompt distingue o VPT do preço de compra, que é a confusão que o modelo comete sozinho.
- **A IA nunca grava sem confirmação — TAMBÉM na análise em lote (Missão de Limpeza, ponto 1).** `commitAIExtractedData` abria o diálogo de revisão quando havia conflitos e, quando NÃO havia, chamava `persistAISuggestions` → `POST /ai-apply-suggestions` directamente. E "sem conflitos" não é o caso benigno: um conflito só existe quando a ficha JÁ TEM outro valor, logo **ficha vazia = zero conflitos = tudo entra sem ninguém ver**. Hoje o lote passa pelo mesmo `prepararRevisaoDaExtraccao` do Épico 9, o diálogo abre SEMPRE e só `handleConfirmAIReview` grava. O lote também deixou de pré-preencher o formulário antes da revisão (mostrava uma ficha já alterada por baixo de um diálogo ainda não aceite). Um `targetTitular` explícito vence a dedução dos `titularMatches` — o consultor já respondeu "este documento é de quem?" num diálogo anterior. Guarda: `pages/processDetails/aiWriteGuard.test.js` afirma sobre o CÓDIGO-FONTE que `persistAISuggestions` só é invocado de um sítio.
- **Assinatura de email: só a do próprio, no contexto certo (Missão de Limpeza, ponto 2).** `email_service.resolve_email_signature` (extraída do `send_email`, testável). A cadeia tinha cinco níveis e os dois últimos não eram do utilizador: **`ucr_any`** (assinatura de QUALQUER empresa dele — um email da Power saía assinado pela Precision) e **`system_fallback`** (a assinatura do sistema, o bloco HTML que aparecia a quem nunca configurou nada). Hoje: UCR da empresa activa → `users.email_signature` → UCR da empresa por omissão **só quando não há empresa activa** (com empresa activa escolhida, a de outra empresa é fuga, não fallback). Sem assinatura configurada, o email sai SEM assinatura. `system_smtp` é o único caso que usa a do sistema. Cobertura: `tests/unit/test_email_signature_fallback.py` (inclui guarda sobre o código-fonte que ignora comentários).
- **Contas de email por perfil: `"default"` pedido explicitamente é uma resposta (Missão de Limpeza, ponto 3).** `_non_default_company_id` descarta `"default"` por desenho — trata-o como "não sei". Mas o `EmailAccountsCard` renderiza um separador por perfil e um perfil sem empresa pede `company_id=default` **sem** header `X-Company-Id` (só o envia quando difere de "default"). O pedido caía em `get_active_company_id_async` → `user["company"]`: o separador pedia "default" e recebia as contas de outra empresa. `users_api_email_config.resolve_accounts_company_id` honra o pedido explícito e só usa o contexto da sessão quando o cliente não diz nada. Corrigido nos **três** sítios (listar, `run_save_my_email_config`, `run_add_my_email_account`) — ao gravar o defeito era o mesmo ao contrário: uma conta criada no separador "default" ia para a empresa activa e desaparecia de onde foi criada. Cobertura: `tests/unit/test_email_accounts_company_scope.py`.
- **RGPD do 2.º titular: "presente mas vazio" não é "presente" (Missão de Limpeza, ponto 4).** O PDF saía em branco por TRÊS instâncias da mesma confusão. (1) `_titular_fallback_data` usava `fallback.setdefault("nif", ...)` sobre o `titular2_data` — mas o formulário público grava as chaves PRESENTES E VAZIAS (`{"nif": ""}`) e `setdefault` só escreve quando a chave FALTA, logo os dados do cliente ligado nunca chegavam ao documento. (2) Os renderers faziam `consent_data.get("contribuinte", personal_data.get("nif",""))` — `dict.get(k, default)` só devolve o default com a chave ausente, portanto um `""` submetido vencia o dado real. (3) `{{CODIGO_POSTAL}}`, `{{TIPO_DOCUMENTO}}` e `{{NUMERO_DOCUMENTO}}` não tinham fallback nenhum e o `documento_id` recolhido nunca era usado. Helpers canónicos em `rgpd_service`: `_esta_vazio` / `_preencher_se_vazio` / `primeiro_preenchido` / `partes_do_documento` — **usar estes, nunca `.get(k, fallback)` para dados de formulário**. `process["client_name"]` só entra na cadeia do 1.º titular: no 2.º seria o documento legal a identificar a pessoa errada. Cobertura: `tests/unit/test_rgpd_titular2_prefill.py`.
- **Pedidos do Portal na aba Documentos do CRM: duas causas, não uma (Missão de Limpeza, ponto 5).** (a) O registo público cria os pedidos por `client_id`, antes de existir processo; só `onboarding_mandatory_config` os ancora depois — `client_assign` e `process_create` **não**, pelo que um processo criado pela Sala de Triagem deixava-os órfãos. (b) Mesmo ancorados, a consulta filtrava por uma ALLOW-LIST de `source` que não conhecia `mandatory_checklist` / `mandatory_checklist_optional`. Hoje: `PORTAL_REQUEST_SOURCES` (constante — **uma origem nova TEM de entrar aqui**) + `build_portal_requests_query`, que junta um ramo por `process_id` e outro pelos clientes do processo (`clientes_do_processo`: titular 1, titular 2, `client_ids`). O ramo do cliente exige `process_id` ausente de propósito: sem isso, um pedido do MESMO cliente noutro processo entrava nesta lista. Cobertura: `tests/unit/test_portal_requests_crm_listing.py`.
- **Apagar no CRM tem de retirar do Portal (Missão de Limpeza, ponto 6).** `document_delete` apagava do S3 e do `document_metadata` e **nunca tocava em `db.documents`** — onde o Portal guarda o pedido com `status: RECEIVED`, `s3_path` e `attached_files`. O cliente continuava a ver um documento inexistente, e um pedido apagado por estar ERRADO continuava a contar como satisfeito (o processo avançava com base nele). `services/document_portal_revoke.py` é a operação INVERSA do `document_portal_fulfill`: `rebuild_after_removal` (pura) tira o ficheiro de `attached_files`, reaponta os campos de topo para o que sobra e devolve o pedido a `REQUESTED` **só quando a contagem desce abaixo do `expected_count`** (mesma regra de `document_portal_counts`). Nunca bloqueia: quando corre, o ficheiro JÁ saiu do S3 — levantar aqui mostraria um erro sobre uma operação bem sucedida. Ligada aos DOIS caminhos de eliminação; a em massa passou também a limpar `document_metadata`, que só a individual limpava. Cobertura: `tests/unit/test_portal_revoke_on_delete.py` (inclui guardas de que a ligação existe — sem elas o serviço seria código morto).
- **Perfil do Portal deriva do `form_config` (Lote 3, ponto 7).** O formulário interno é CONFIGURÁVEL; o do Portal era uma lista escrita à mão em `ClientPortal.jsx` com um allowlist igualmente à mão em `portal_profile.py`. Divergiram: faltavam `codigo_postal` e `niss`, não havia sinalização de obrigatórios, e `if key in PROFILE_UPDATABLE_PERSONAL_FIELDS` descartava em SILÊNCIO — o cliente gravava, lia "Perfil atualizado com sucesso!" e o valor não existia. Hoje `services/portal_profile_schema.py` deriva do mesmo `form_config` (via `public_form_config.load_merged_form_fields`, extraída para ser partilhada) **o que se mostra E o que se aceita gravar** — há um teste a afirmar que são o mesmo conjunto. O `GET /portal/me` devolve `form_schema`; o `PUT` devolve `rejected_fields` e regista-os. **O NIF NUNCA é editável pelo cliente** (`PORTAL_LOCKED_FIELDS`, regra de negócio confirmada): continua oculto na leitura e fora do esquema na escrita — o componente da UI não o trata como caso especial, o que é a forma certa de a regra não se perder. As listas antigas ficam como RECURSO para quando a configuração não está acessível; a validação é sobre `dados_pessoais` (o `contacto` traz sempre os extras do Portal e um esquema vazio parecia válido). Frontend: `components/portal/PortalProfileFields.jsx` (apresentação, divulgação progressiva: obrigatórios à vista, restantes atrás de "Preencher mais detalhes") + `utils/portalProfile.js` (`hidratarFormulario` / `construirPayload` / `obrigatoriosEmFalta`, puros). Cobertura: `tests/unit/test_portal_profile_schema.py`, `PortalProfileFields.test.jsx`, `utils/portalProfile.test.js`.
- **`assigned_to` das tarefas: SEMPRE lista (Lote 4, ponto 12).** `workflow_engine` gravava o valor cru resolvido do processo — um ESCALAR ou `None` — enquanto `task_api_crud` e `process_assignment` gravam lista. `enrich_task` faz `{"id": {"$in": task["assigned_to"]}}` e o Mongo responde `$in needs an array`; como `run_list_tasks` enriquece num ciclo **sem `try`**, UMA tarefa de automação fazia a listagem INTEIRA devolver 500. `task_assignment_hygiene.normalizar_assigned_to` desarma à leitura **e** o motor de automação passou a gravar lista (guarda sobre o código-fonte da origem: normalizar trata o que já existe, deixar de produzir impede que volte).
- **Mudar a atribuição de um processo LIMPA as tarefas de quem saiu (Lote 4, ponto 12).** `_create_post_indexing_tasks` cria tarefas de arranque e nada lhes voltava a tocar: tirar o consultor deixava as tarefas dele num processo sem ninguém atribuído. **Opção A:** tarefa criada pelo SISTEMA e por tocar (`created_by` do sistema **e** não concluída **e** `updated_at == created_at`) é apagada; tudo o resto fica, perde a atribuição e leva `assignment_orphaned` — nunca apagar trabalho humano em silêncio. Só fica órfã quando NINGUÉM sobra. O diff é sobre o ANTES/DEPOIS reais do documento (`ids_atribuidos_do_processo`), ligado aos DOIS caminhos (`/assign` e `/unassign-me`). Cobertura: `tests/unit/test_task_assignment_hygiene.py`.
- **Criar utilizador cria os UCRs no mesmo acto, e a empresa é OBRIGATÓRIA (Lote 4, ponto 11).** `run_create_user` nunca criava UCR e o formulário nem enviava `company`: a conta ficava invisível ao ContextSwitcher, à config de email por empresa e ao isolamento por rede. Hoje `services/user_company_bootstrap.py` (`normalizar_acessos` / `assert_acessos_obrigatorios` / `criar_acessos_iniciais`) e, se os UCRs falharem, **a conta é desfeita**. Excepção: `parceiro` (conta fantasma). `completar_nomes_das_empresas` corre ANTES de se montar o documento — `users.company` é o NOME e `_find_ucr` casa por ele; lá escrever o `company_id` é a confusão id/nome de 2026-09-21. Cobertura: `tests/unit/test_user_company_bootstrap.py`.
- **`TasksPanel` JÁ É um cartão: usar `asCard={false}` ao embuti-lo (Lote 4, ponto 13).** Tem `CardHeader`, `CardTitle "Tarefas"`, contagem e `ScrollArea` próprios; o `ProcessDetails` embrulhava-o noutro `Card` com o MESMO título e outro `ScrollArea`, e passava `compact={false}` a desligar o modo compacto que já existia. Em `compact`, filtros e data de criação **não são renderizados** (esconder por CSS deixa-os acessíveis ao teclado e aos leitores de ecrã). O selector de responsáveis mostra a equipa do processo primeiro e o resto atrás de "Fora da equipa do processo"; quando a equipa não se confirma, isso é DITO — antes caía para todo o staff com um `console.warn`.
- **Mutação que não mata: distinguir mutação perdida de TESTE FRACO.** Segunda ocorrência no projecto. No Épico 9 a mutação não chegou ao sítio; no ponto 13, `const Moldura = Card` atravessou porque o `data-testid` estava preso à FLAG e não à moldura real. Regra: quando um marcador de teste e o comportamento derivam da mesma condição escrita duas vezes, podem divergir — derivar do que foi de facto escolhido (`Moldura === Card`), não da flag.
- **`src/test/setup.js` preenche a API de Pointer Capture.** O `Select` do Radix chama `hasPointerCapture` ao abrir e o jsdom não a implementa: sem o stub, o clique morre em silêncio e o teste falha a dizer que "não encontrou a opção" — pista que aponta para o sítio errado.
- **Monitor de Sinais Vitais: o estado dos jobs é PERSISTIDO, nunca lido da memória local (Lote 4, ponto 14).** Não há agendador (nem APScheduler nem Celery): são laços `asyncio` à mão em DOIS processos do `render.yaml` — web (`background_job_monitor` em todos os workers; backup/CDC/`email_auto_sync` só em produção E no worker primário) e worker (`scheduled_tasks` 1h, `lead_matching` 30min, `webmail_worker_sync` 10min). O `last_runs` do `worker.py` é um dicionário LOCAL DE UMA FUNÇÃO: morre no reinício e a API nunca o vê; com `UVICORN_WORKERS=2` um pedido no worker secundário não vê as tarefas do primário. Um endpoint que lesse o estado local responderia sobre o processo que calhasse atender o pedido — **um monitor que mente com ar de autoridade é pior do que não ter monitor**. `services/job_heartbeat.py` + colecção `job_heartbeats`: ÚLTIMO batimento por job + `run_count`/`failure_count` (não é histórico). O envelope `heartbeat()` embrulha o TRABALHO (não corre ao lado dele) e **re-levanta** a excepção do ciclo — observa, não intercepta; falhar a GRAVAR o batimento nunca propaga. A lista vem de `JOBS_DECLARADOS`, não da colecção: senão o job que nunca arrancou era o único invisível (guarda nos dois sentidos). Limiar de atraso = **2× o intervalo**. **`desactivado` ≠ em baixo**: em dev quase tudo está desligado por kill switch e um painel a gritar vermelho ensina toda a gente a ignorá-lo. Endpoint `GET /api/automations` é READ-ONLY (o disparo teria de atravessar a fronteira de processos). Cobertura: `tests/unit/test_job_heartbeat.py`, `EngineStatusPanel.test.jsx`.
- **Perfil `indexacao` não deixa rasto — e o PERFIL ACTIVO conta (Lote 4).** `history._is_stealth_user` é o ponto único. Olhava só para `user["role"]` (papel do JWT): quem entra COMO Indexação tem `effective_role == "indexacao"` e um papel base diferente, e deixava rasto — o caso mais provável, porque é assim que o produto quer que se troque de chapéu. A regra ACRESCENTA (quem é indexador de base continua silencioso com outro perfil activo). **Nunca reconstruir a regra à mão:** `document_portal_request` tinha uma cópia inline em três sítios que ignorava `track_history=False`; `restore_api_document` e `voice_note_engine` não tinham guarda nenhuma. NÃO são fuga: os escritores em `admin_*` (endpoints `require_roles([ADMIN, CEO])`) e o `temp_link_api_public` (`created_by: None`, é o cliente). O **`audit_trail_service` fica EXCLUÍDO de propósito** — é conformidade com IP e retenção, e há um teste a afirmá-lo para ninguém o "corrigir". Cobertura: `tests/unit/test_stealth_indexacao.py`.
- **A contagem de testes do Vitest denuncia ficheiros que nem foram recolhidos.** Uma declaração duplicada em `services/api.js` fez a bateria cair de 707 para 684 testes PASSADOS, **sem uma única falha**: os ficheiros que importavam o módulo partido não chegaram a ser recolhidos. O ESLint apanhou o erro; a contagem é que o denunciou. Comparar o total entre execuções distingue "tudo passa" de "metade nem correu".
- **Atribuição: `set` e `clear` derivam da MESMA constante (Lote 5, ponto 4).** `build_clear_consultor_fields` limpava quatro dos seis campos canónicos — `consultor_id` e `consultant_id` ficavam com o valor antigo. Duas consequências: (1) `ids_atribuidos_do_processo` lê-os todos, logo o diff "equipa antes − depois" dava VAZIO e a limpeza de tarefas órfãs do Lote 4 nunca corria; (2) `process_list_filters` usa `consultant_id` em "Os Meus Processos" — **o consultor removido continuava a ver o processo**. Hoje `CONSULTOR_ID_FIELDS`/`MEDIADOR_ID_FIELDS` alimentam `_build_assignee_fields`, e há um teste a afirmar que o `set` e o `clear` tocam no mesmo conjunto. **Os testes desta área usam SEMPRE os construtores de produção** — o meu teste do Lote 4 passou por construir os documentos à mão, com os campos já coerentes.
- **Inventariar os sítios que LISTAM, não só a condição (Lote 5, ponto 1).** O Kanban tem um construtor SEPARADO (`build_kanban_query`) que não passa pelo `build_process_list_query` nem pelo `run_get_processes*`: ficou fora do isolamento do Lote 4 e um utilizador de uma empresa isolada via o quadro inteiro. Um ponto único para a CONDIÇÃO não chega — `tests/unit/test_kanban_files_isolation.py` é também o inventário das superfícies, com um teste por cada. O Explorador global de ficheiros (`/ficheiros`) fica em `FILE_VIEW_ROLES`/`FILE_OPS_ROLES` = **[ADMIN, CEO]** (o bucket é por pasta de cliente, não há `network_id` num prefixo S3); os ficheiros do processo continuam por `/documents/*`.
- **Notificações: o filtro é por `user_id`, nunca por processo nem por cargo (Lote 5, ponto 3).** As notificações têm destinatário e `run_get_notifications` ignorava-o: filtrava por visibilidade de PROCESSO e isentava admin/ceo/diretor (`query = {}`), pelo que a gestão recebia tudo o que existia na colecção e um consultor via as do mediador do mesmo processo. `{"process_id": None}` mandava os avisos sem processo para toda a gente. Hoje `build_notifications_query` filtra só por `user_id` (fail-closed sem utilizador) e a contagem segue o mesmo âmbito. `run_mark_notification_read` recebe o utilizador e devolve **404** (não 403) para a notificação de outro — distinguir "não existe" de "não é tua" confirmaria o id. Cobertura: `tests/unit/test_notifications_scope.py`.
- **Assinatura de email: a global não atravessa empresas (Lote 5, ponto 5).** O `ProfileRoleTab` grava nos DOIS sítios (UCR da empresa activa **e** `users.email_signature`) e lê só o primeiro: a global escrita ao gravar a da Power saía nos emails da Precision — o `ucr_any` do Lote 1 pela porta do campo global. Regra: **com empresa activa, a global só vale se o utilizador nunca tiver configurado assinatura por empresa** (aí é mesmo a única dele). `/auth/me` devolve `email_signature_effective` / `email_signature_source` resolvidos pela MESMA função do envio — duplicar a cadeia na UI recriaria o problema com outro nome.
- **Trocar de perfil limpa a cache do TanStack (Lote 5, ponto 6).** `switchActiveCompany` faz `window.location.reload()`; `switchActiveRole` não tocava na cache — os headers mudavam para o pedido seguinte e o TanStack não fazia nenhum (nada estava stale). `queryClient.clear()` e **não** `invalidateQueries()`: invalidar continua a MOSTRAR os dados do âmbito anterior enquanto o novo pedido não chega. A limpeza vem DEPOIS de gravar o perfil novo, para o refetch partir com os headers certos.
- **Campo de Rede: autocomplete, nunca texto livre (Lote 5, ponto 2).** `grupo_power` em vez de `grupo_power_precision` não dá erro — cria uma rede nova de uma empresa só e o isolamento quebra AO CONTRÁRIO (esconde dados de quem os devia ver). `CompanyNetworkField` usa `<datalist>` (nativo, acessível, permite criar uma rede nova) e **avisa do efeito**: "junta-se a N empresas" vs "rede nova". É o aviso, não a lista, que apanha a gralha. O valor é aparado no `onChange`: um espaço à direita é outra rede e a diferença é invisível.
- **`App.rotasMenu.test.js`: admin e CEO vêm do fall-through, não de um `if`.** O guarda do Lote 3 só iterava diretor/consultor/intermediário; para admin/ceo o extractor devolvia lista vazia e, como não estavam no ciclo, a lacuna era invisível. Cobertos desde o Lote 5, e o extractor lê três formas de declarar um item: `if (userRole === "x")`, `[...].includes(userRole)` e o **spread condicional** dentro de um grupo partilhado (`...(["admin","ceo"].includes(userRole) ? [{…}] : [])`), com contraprova nos dois sentidos.
- **Isolamento multi-tenant: a rede vive na EMPRESA, o carimbo vive no DOCUMENTO (Lote 4, ponto 10).** Não havia filtro de tenant nenhum nas listagens e pesquisas (`search_api_*`, `client_list_filters`, `my_clients_api_helpers`, `task_api_crud`: zero ocorrências de `compan`) e o Ctrl+K devolvia clientes de outra empresa com o NIF já desencriptado. O único filtro que existia era um **placebo**: `build_company_scope_condition` inclui `{"company_id": {"$exists": False}}` e `build_staff_process_doc` não escrevia campo de empresa NENHUM — todo o processo do CRM casava com o filtro de qualquer empresa. Hoje: `companies.network_id` (empresa sem rede = **ilha de uma só**; uma empresa nova NUNCA herda a rede de omissão), `services/tenant_network.py` como **ponto único** (`resolve_tenant_scope` / `build_network_scope_condition` / `resolve_tenant_stamp`) e carimbo na escrita (`build_staff_process_doc(tenant=…)`). O âmbito é do UTILIZADOR (a empresa activa é uma vista; a rede é a fronteira de segurança). `TENANT_DEFAULT_NETWORK_ID` diz a que rede pertence a pilha por carimbar — definida em produção, por definir em dev/CI (comportamento anterior + `warning`). **"Por carimbar" exige ausência de TODAS as marcas** (`network_id` **e** `company_id`/`company`/`company_name`): olhar só para a rede deixa a fuga entrar pela cláusula que a evita. `build_network_scope_condition` **nunca devolve `None`** — um âmbito fechado sem ramos devolve uma condição impossível; `None` seria "sem filtro". Migração: `scripts/backfill_network_id.py` (`--empresas` obrigatória, `--documentos` opcional) — `rede_consensual` recusa-se a adivinhar quando há mais do que uma candidata, porque um carimbo errado é permanente. Cobertura: `tests/unit/test_tenant_network_isolation.py`.
- **Guardas sobre o código-fonte: usar `tests/unit/helpers_fonte.py`.** `codigo_sem_comentarios` / `codigo_da_funcao_sem_comentarios` (tokenize + `ast`, não regex — um literal com `#` truncaria código a meio). Uma guarda que leia os comentários proíbe a explicação do defeito que previne, e a saída óbvia quando fica vermelha é apagar a explicação. `ast.unparse` normaliza as aspas: comparar literais sem elas. **Toda a guarda sobre o código-fonte precisa da CONTRAPROVA ao lado** ("o sítio certo chama mesmo X") — sem ela, apagar a chamada satisfaz o guarda.
- **Menu e rotas têm de concordar (Lote 3, ponto 8).** `DashboardLayout` mostrava "Os Meus Clientes" ao perfil Diretora (o grupo "O Meu Negócio" é explicitamente dela) e a rota `/meus-clientes` não tinha `diretor` nas `allowedRoles` — `ProtectedRoute` devolvia ao Dashboard. Não é "não tens acesso", é o produto a contradizer-se, e não dá erro em lado nenhum. Guarda: `src/App.rotasMenu.test.js` cruza as duas listas por perfil e diz qual divergiu. **Um item de menu novo exige o papel na rota, e vice-versa.**
- **Hooks correm antes do early return (Lote 3, ponto 9).** `ProcessDetails` sabia que o processo tinha sido eliminado (`setNotFound`) e mostrava "Processo não encontrado" — mas isso é um `return` no RENDER, e `useProcessPortalMessages(id, …)` (linha ~276) corre sempre. O hook continuava a interrogar `/portal-messages/unread` de 30 em 30 s. A defesa interna dele só cobria o intervalo: o efeito de `isActive`, o `refresh()` do WebSocket e o `fetchMessages` ignoravam-na, e o guard é um `useRef` que reinicia em cada montagem. Hoje o hook aceita `enabled` e a página passa `!notFound && !accessDenied` — `notFound`/`accessDenied` foram MOVIDOS para antes da chamada do hook de propósito. **Quem sabe que o recurso desapareceu é a página; desligar à nascença é mais seguro do que cada caminho defender-se depois.** Cobertura: `hooks/__tests__/useProcessPortalMessages.enabled.test.jsx`.
- **Testes de componente:** consultar por papel e nome acessível (`getByRole("button", { name: "Limpar pasta" })`), nunca por classe CSS; um botão sem nome acessível é um bug de acessibilidade e um teste impossível. Quem usa `Tooltip` tem de ser montado dentro de um `<TooltipProvider>`. **Um teste que possa passar sem provar nada é pior do que não existir** — nada de `if (mock.calls.length) expect(...)`.
- **Email NUNCA bloqueia um pedido HTTP (incidente CI 2026-09-21).** `send_email` chamava `smtplib.SMTP_SSL(..., timeout=30)` — síncrono — directamente de uma corotina: com o servidor de email inacessível, o event loop do worker INTEIRO parava 30s. E o `/public/client-registration` fazia **três** envios awaited em série (convite do Portal, email de registo, notificação ao staff) → até 90s de espera num formulário público, por emails que o próprio código já tratava como não-fatais. Hoje: os transportes (SMTP e Resend, ambos síncronos) correm por `asyncio.to_thread`, e os envios cujo resultado o utilizador não precisa vão por `spawn_background_task` (`services/background_tasks.py` — referência forte; `asyncio.create_task` puro pode ser recolhido pelo GC). Um envio awaited só se justifica quando o utilizador espera pelo resultado (botão "Enviar Email de Teste", `send-documentation`). Cobertura: `tests/unit/test_email_nao_bloqueia_event_loop.py`, `tests/integration/test_public_registration_smtp_pendurado.py`.
- **Em dev/CI o host SMTP tem de ser tão falso como as credenciais.** O workflow definia `POWER_EMAIL`/`POWER_PASSWORD` falsos mas NÃO o host, pelo que `get_email_accounts` caía no default hardcoded (`webmail2.hcpro.pt`) e a suite marcava um servidor de email REAL — a origem da intermitência (o mesmo commit falhava e passava conforme o servidor respondesse). `POWER_SMTP_SERVER`/`PRECISION_SMTP_SERVER=127.0.0.1` e `SMTP_CONNECT_TIMEOUT=5` no job Full. `SMTP_CONNECT_TIMEOUT` é lido a cada envio (default 30; valor inválido cai no default — nunca desligar o timeout).
- **Suite completa local:** só corre com Mongo vivo. Sem `mongod`, a fixture `_setup_test_data` (session, autouse) pendura ~30s por timeout e, com `--timeout`, vira erro de setup que derruba a recolha inteira. Binário avulso: `curl -sSL https://fastdl.mongodb.org/linux/mongodb-linux-x86_64-ubuntu2204-7.0.14.tgz | tar xz && ./bin/mongod --dbpath <dir> --port 27017 --fork --logpath <log>` — com ele, o comando exacto do job Full corre em ~22s.
- CI (`.github/workflows/main.yml`): frontend (ESLint `--quiet` blocking + Vite build), backend (flake8 + pytest on **Python 3.12** — required by `numpy==2.5.1`), security (bandit + pip-audit), and **E2E smoke** (Playwright `e2e/smoke.spec.js` against local mongo + uvicorn + `yarn dev`).
- **Frontend E2E (Playwright)**: smoke runs in CI. Full suite locally: `cd frontend && npx playwright install chromium`, then `PLAYWRIGHT_BASE_URL=http://localhost:3000 yarn playwright test --project=chromium` (with backend on `:8001`). Use `PLAYWRIGHT_SKIP_WEBSERVER=1` if Vite is already running. Specs that need data (e.g. `e2e/undo-delete.spec.js`) provision via API and clean up after.

### Route thinning (documents / processes / emails / portal / admin / admin_storage / clients / finance / properties / chat / diagnostics / leads / form_config / system_config / admin_process_migration / rgpd / auth / visits / tasks / backup / shared_email / temp_links / google_auth / public / stats / admin_ai / ai / ai_analysis / my_clients / onedrive / scraper / templates / users / async_jobs / ai_bulk / admin_migration / companies_crud / minutas / user_company_roles / deadlines / search / restore / match / gov_auth / companies / alerts / storage / portal_settings / automation / announcements / changelog / portal_admin / push_notifications / activities / audit / user_branches / ai_agent)

Fat FastAPI routers are being split into thin `@router` stubs + `backend/services/*` modules. Prefer editing the service, not stuffing logic back into the route file.

| Area | Route file | Services pattern | Notes |
|---|---|---|---|
| Processes | `routes/processes.py` (~664) | `services/process_*.py` | Mostly done |
| Documents | `routes/documents.py` (~1072; was ~4623) | `services/document_*.py` | Thin stubs only — see map |
| Emails | `routes/emails.py` (~654; **done**) | `services/email_*.py` (see map) | Keep static paths before `/{email_id}`; do **not** collide with existing `email_service.py` / `email_draft_service.py` |
| Portal | `routes/portal.py` (~221; **done**) | `services/portal_*.py` (see map) | Do **not** collide with existing `portal_security` / `portal_magic_link` / `portal_documents_notify`. Portal `DOCUMENT_CATEGORY_MAP` includes `Financeiros` (separate from `document_constants`) |
| Admin | `routes/admin.py` (~655; **done**) | `services/admin_*.py` (see map) | Do **not** collide with existing **route** modules `admin_ai` / `admin_storage` / `admin_encryption` / `admin_migration` / `admin_process_migration` |
| Admin storage | `routes/admin_storage.py` (**done**) | `services/admin_s3_*.py` (see map) | Sibling of `admin.py`. **Never** create `services/admin_storage.py` (collides with the route module name). Do **not** overwrite `s3_storage.py` / `storage_service.py`. Preserve `client-s3-mappings` aliases. |
| Clients | `routes/clients.py` (~210; **done**) | `services/client_*.py` (see map) | Keep static paths (`/me`, `/registered`, `/search`, `""`, `/find-or-create`) before `/{client_id}`; do **not** collide with existing `client_match.py` / `process_clients_nm.py` / `process_my_clients.py` |
| Finance | `routes/finance.py` (~280; **done**) | `services/finance_*.py` (see map) | Keep `/finance/processes/summary` before `/{finance_id}`; do **not** collide with existing `process_finance.py` — use `finance_process_records.py` for `process_finances` CRUD |
| Properties | `routes/properties.py` (~245; **done**) | `services/property_*.py` (see map) | Keep static paths (`/stats`, `/by-process/{id}`) before `/{property_id}`; do **not** collide with existing `property_scraper.py` / `alerts.py` / `scraper.py` / `gov_scraper.py` |
| Chat | `routes/chat.py` (~250; **done**) | `services/chat_*.py` (see map) | No prior `chat_*` services; WS notify via `websocket_manager` stays inside services |
| Diagnostics | `routes/diagnostics.py` (~150; **done**) | `services/diagnostics_*.py` (see map) | Do **not** collide with existing `process_kanban_diagnose.py` — use `diagnostics_*` prefix |
| Leads | `routes/leads.py` (~140; **done**) | `services/lead_*.py` (see map) | Keep static paths (`/by-status`, `/consultores`, `/extract-url`, `/extract-html`, `/from-url`, `""`) before `/{lead_id}`; prefer `lead_*` (not `leads_*`) |
| Form config | `routes/form_config.py` (**done**) | `services/form_config_*.py` (see map) | Re-exports `DEFAULT_FORM_CONFIG` / `DEFAULT_STEP_CONFIG` for `routes.public` |
| Admin process migration | `routes/admin_process_migration.py` (**done**) | `services/admin_proc_migration_*.py` (see map) | **Never** create `services/admin_process_migration.py` (collides with the route module name) |
| System config | `routes/system_config.py` (**done**) | `services/system_config_*.py` (see map) | **Never** overwrite existing `services/system_config.py` (core load/save/cache). Use `system_config_api` / `_connections` / `_admin_ops` / `_system_emails` |
| RGPD | `routes/rgpd.py` (~230; **done**) | `services/rgpd_*.py` (see map) | Keep `/admin/all`, `/admin/template*`, `/admin/minuta-template*`, `/admin/stats/summary` before `/admin/{request_id}`; do **not** overwrite existing `rgpd_service.py` / `gdpr.py` — use `rgpd_helpers` / `rgpd_request` / `rgpd_public` / `rgpd_admin_list` / `rgpd_templates` / `rgpd_minutas` |
| Auth | `routes/auth.py` (~150; **done**) | `services/auth_*_handlers.py` (see map) | **Never** overwrite existing `services/auth.py` (JWT/bcrypt/`get_current_user`). Preserve deprecated `/login` (410) + `/login-v2` + cookie-ready `Response` signatures. Re-export `get_current_user` for `routes.storage` |
| Visits | `routes/visits.py` (~90; **done**) | `services/visit_*.py` (see map) | Keep `/kanban` before `/{visit_id}`; prefer `visit_*` (not `visits_*`); do **not** collide with `portal_client_visits.py` |
| Tasks | `routes/tasks.py` (~130; **done**) | `services/task_api_*.py` (see map) | Keep `/active`, `/my-tasks` before `/{task_id}`; **never** overwrite `task_queue.py` / `task_log_service.py` / `scheduled_tasks.py` — use `task_api_*` |
| Shared email | `routes/shared_email.py` (~110; **done**) | `services/shared_email_*.py` (see map) | Keep static `/google/callback` **before** `/{role}`; prefer `shared_email_*` |
| Temp links | `routes/temp_links.py` (~110; **done**) | `services/temp_link_api_*.py` (see map) | **Never** overwrite `temp_link_service.py` — use `temp_link_api_*`; keep `/public/{token}*` |
| Google auth | `routes/google_auth.py` (~60; **done**) | `services/google_auth_*.py` (see map) | **Never** overwrite `gmail_oauth.py` / `gmail_api_service.py` — use `google_auth_*` |
| Public | `routes/public.py` (~51; **done**) | `services/public_*.py` (see map) | Preserve rate limits on stubs; **never** overwrite `euribor_service.py`; form defaults from `form_config_defaults` (not via routes — circular import) |
| Stats | `routes/stats.py` (~47; **done**) | `services/stats_*.py` (see map) | Do **not** collide with `analytics_service.py`; `/health` (no auth) is the monitoring endpoint |
| Admin AI | `routes/admin_ai.py` (**done**) | `services/admin_ai_{config,models,tasks,cache,usage}.py` | **Never** create `services/admin_ai.py`; do **not** overwrite `admin_ai_data.py` / `ai_usage_tracker.py` |
| AI | `routes/ai.py` (**done**) | `services/ai_api_*.py` (see map) | **Never** overwrite `ai_document.py` / analyzers / `ai_usage_tracker.py` — use `ai_api_*` |
| AI analysis | `routes/ai_analysis.py` (**done**) | `services/ai_analysis_api_*.py` (see map) | **Never** overwrite analyzers; executive summary + cross-ref audit |
| My clients | `routes/my_clients.py` (**done**) | `services/my_clients_api_*.py` (see map) | **Never** overwrite `process_my_clients.py` (GET `/processes/my-clients`); list may reuse its enrichment maps |
| OneDrive | `routes/onedrive.py` (**done**) | `services/onedrive_*.py` (see map) | **Never** overwrite `services/onedrive.py` (Graph OAuth core) |
| Scraper | `routes/scraper.py` (**done**) | `services/scraper_api_*.py` (see map) | **Never** overwrite `scraper.py` / `gov_scraper.py` / `property_scraper.py` |
| Templates | `routes/templates.py` (**done**) | `services/templates_api_*.py` (see map) | **Never** overwrite `template_generator.py` |
| Users | `routes/users.py` (**done**) | `services/users_api_*.py` (see map) | **Never** overwrite `auth.py`; keep `/me/email-config*` before `/{user_id}`; admin CRUD stays in admin |
| Async jobs | `routes/async_jobs.py` (**done**) | `services/async_jobs_api_*.py` (see map) | Preserve rate limits; keep `/health` + `/session/*` + `/analyze` before `/{job_id}` |

**`email_*` thinning (complete):**

| Service | Responsibility |
|---|---|
| `email_template_vars.py` | `_extract_email_variables`, `_build_professional_email_html` |
| `email_enrich.py` | `enrich_email` (client_name / created_by_name) |
| `email_labels_folders.py` | Labels/folders CRUD + `validate_hex_color` + move-to-folder |
| `email_documentation.py` | document-recipients, preview-template, preview/send-documentation |
| `email_mailbox_ops.py` | Attachments upload/download/preview + mark/unmark + per-email labels |
| `email_templates_drafts.py` | Reply templates, unread notifications, auto-drafts |
| `email_webmail.py` | Webmail list/stats/sync, accounts, test-connection, jobs |
| `email_process_crud.py` | Search/timeline, process emails/sync, send, CRUD, monitored (`_sync_status` lives here) |

Unit helpers: `backend/tests/unit/test_email_extraction_helpers.py`.

**`portal_*` thinning (complete):**

| Service | Responsibility |
|---|---|
| `portal_assigned_users.py` | `get_all_assigned_user_ids` (also used by `process_portal_messages`) |
| `portal_doc_categories.py` | Portal category map / hidden / default pending (used by `process_create`) |
| `portal_profile.py` | GET/PUT `/me` + profile field allowlists |
| `portal_status_helpers.py` | contact / RGPD / team helpers for `/status` |
| `portal_onboarding_advance.py` | Pacote BO auto-advance after portal uploads |
| `portal_auth.py` | login / verify / resolve / impersonate / authenticate |
| `portal_status.py` | GET `/status` orchestration |
| `portal_upload_ops.py` | upload-url / confirm-upload / download-url |
| `portal_client_messages.py` | client messages (+ notify) |
| `portal_gov_fetch.py` | Finanças/SS scrapers, MFA, jobs |
| `portal_recommendations.py` | Smart Match recommendations |
| `portal_client_visits.py` | visit request + list |

Unit helpers: `backend/tests/unit/test_portal_extraction_helpers.py`.

**`admin_*` thinning (complete):**

| Service | Responsibility |
|---|---|
| `admin_helpers.py` | `_safe_float`, `_audit_log` |
| `admin_permissions.py` | permissions + capabilities |
| `admin_workflow.py` | workflow statuses + S3 CORS diagnostic |
| `admin_users.py` | user CRUD, impersonate, notif prefs, user email-config |
| `admin_process_ops.py` | fix-duplicates, migrate numbers, sync process emails |
| `admin_ai_data.py` | AI training + AI import logs |
| `admin_observability.py` | system logs, jobs health, client registrations, audit, team performance |
| `admin_dev_ops.py` | DB indexes, sync-database, seed (`_sync_in_progress` lives here) |

Unit helpers: `backend/tests/unit/test_admin_extraction_helpers.py`.

**`admin_s3_*` thinning (complete) — sibling of `routes/admin_storage.py`:**

| Service | Responsibility |
|---|---|
| `admin_s3_client_mappings.py` | `run_auto_map_client_s3_folders` (aliases stay as route stubs → process `run_*`) |
| `admin_s3_user_mappings.py` | user ↔ S3 folder list/get/update |
| `admin_s3_process_mappings.py` | process ↔ S3 list/update/fix-missing/batch + `_clean_s3_folder` |
| `admin_s3_explorer.py` | `_resolve_explorer_path`, folder contents, rename/delete/create/upload/download + request models |

**Never** create `services/admin_storage.py` (name collision with `routes/admin_storage.py` called out in the admin thinning notes). Do **not** overwrite `s3_storage.py` / `storage_service.py`.

Unit helpers: `backend/tests/unit/test_admin_storage_extraction_helpers.py`.

**`client_*` thinning (complete):**

| Service | Responsibility |
|---|---|
| `client_portal_email.py` | `_send_portal_welcome_email_safe` (fire-and-forget portal welcome) |
| `client_me.py` | GET `/me` assigned clients/processes |
| `client_registered.py` | GET `/registered` (Registo / Sala de Triagem) |
| `client_assign.py` | POST `/{id}/assign` (+ auto process create) |
| `client_list_search.py` | GET `/search` + GET `` list |
| `client_crud.py` | GET/POST/PUT client get/create/update |
| `client_process_ops.py` | link/unlink/create-process + GET processes |
| `client_portal_access.py` | POST resend-portal-access |
| `client_find_or_create.py` | POST `/find-or-create` |
| `client_delete.py` | DELETE client (soft delete + 2º titular rule) |

Unit helpers: `backend/tests/unit/test_client_extraction_helpers.py`.

**`finance_*` thinning (complete):**

| Service | Responsibility |
|---|---|
| `finance_helpers.py` | Shared helpers + `DashboardFinanceConfigUpdate` + `FINANCE_READ_ROLES` / defaults |
| `finance_dashboard.py` | GET/PUT `/finance/config`, summary, monthly, performance |
| `finance_commissions.py` | `_calc_commissions_data`, commissions + CSV export |
| `finance_configs.py` | Multi-company `finance_configs` CRUD + `_doc_to_config_response` |
| `finance_pool.py` | Pool distribution + CSV export |
| `finance_process_records.py` | `process_finances` summary/CRUD/status/delete (not `process_finance.py`) |

Unit helpers: `backend/tests/unit/test_finance_extraction_helpers.py`.

**`property_*` thinning (complete):**

| Service | Responsibility |
|---|---|
| `property_helpers.py` | `get_next_reference` (IMO-NNN) — shared by CRUD + excel import |
| `property_list.py` | GET `` list, `/stats`, `/by-process/{id}` |
| `property_crud.py` | POST/GET/PATCH/DELETE property + status (uses `alerts.check_and_notify_matches_for_new_property`) |
| `property_engagement.py` | interested clients, register-visit, photo add/remove |
| `property_excel_import.py` | bulk excel import + `_process_excel_import` + jobs + template |
| `property_documents.py` | property document upload / list / delete (S3) |

Unit helpers: `backend/tests/unit/test_property_extraction_helpers.py`.

**`chat_*` thinning (complete):**

| Service | Responsibility |
|---|---|
| `chat_helpers.py` | `_block_parceiro` / `block_parceiro`, `MAX_ATTACHMENT_SIZE`, `ALLOWED_ATTACHMENT_TYPES` |
| `chat_conversations.py` | GET `/conversations` |
| `chat_messages.py` | messages get/send/upload/react/edit/delete + POST `/search` |
| `chat_groups.py` | groups CRUD + leave |
| `chat_presence.py` | typing, unread-count, online-users, chat users directory |

Unit helpers: `backend/tests/unit/test_chat_extraction_helpers.py`.

**`diagnostics_*` thinning (complete):**

| Service | Responsibility |
|---|---|
| `diagnostics_helpers.py` | `datetime_to_str`, `ServiceStatus`, `SystemDiagnostics`, TTL migration models |
| `diagnostics_checks.py` | email / storage / AI / backup / notifications health checkers |
| `diagnostics_system.py` | GET ``, `/service/{name}`, `/quick-check` |
| `diagnostics_security.py` | encryption status, PII compliance, OpenAI privacy test-api |
| `diagnostics_ttl.py` | POST `/migrate-ttl-fields` + GET `/ttl-status` |

Unit helpers: `backend/tests/unit/test_diagnostics_extraction_helpers.py`.

**`lead_*` thinning (complete):**

| Service | Responsibility |
|---|---|
| `lead_helpers.py` | `_log_system_error`, `_parse_plain_text` |
| `lead_list.py` | GET `` list, `/by-status`, `/consultores` |
| `lead_extract.py` | POST `/extract-url`, `/extract-html`, `/from-url` |
| `lead_crud.py` | POST create + PATCH/status/refresh + DELETE |
| `lead_associate.py` | POST `/{id}/associate-client` |

Unit helpers: `backend/tests/unit/test_lead_extraction_helpers.py`.

**`form_config_*` thinning (complete):**

| Service | Responsibility |
|---|---|
| `form_config_defaults.py` | `DEFAULT_FORM_CONFIG`, `DEFAULT_STEP_CONFIG` |
| `form_config_fields.py` | GET/PUT `/fields`, custom-field CRUD, `/reset` + request models |
| `form_config_templates.py` | System templates + templates list/preview/save/activate/duplicate/delete |

Unit helpers: `backend/tests/unit/test_form_config_extraction_helpers.py`.

**`admin_proc_migration_*` thinning (complete) — sibling of `routes/admin_process_migration.py`:**

| Service | Responsibility |
|---|---|
| `admin_proc_migration_helpers.py` | `generate_client_key`, `extract_personal_from_process`, migration state helpers, `run_migration_task` |
| `admin_proc_migration_api.py` | status / dry-run / run / rollback / reset `run_*` handlers |

**Never** create `services/admin_process_migration.py` (name collision with the route module).

Unit helpers: `backend/tests/unit/test_admin_proc_migration_extraction_helpers.py`.

**`system_config_*` thinning (complete):**

| Service | Responsibility |
|---|---|
| `system_config.py` | **Existing core** — load/save/cache, `update_config_section`, companies list (**do not overwrite**) |
| `system_config_api.py` | `CONFIG_FIELDS`, `mask_sensitive`, get/update/fields/companies/export-permission |
| `system_config_connections.py` | POST `/test-connection/{service}` |
| `system_config_admin_ops.py` | complete-setup, storage-info, reset-cache, reveal-secrets |
| `system_config_system_emails.py` | system-emails CRUD + test + request models |

Unit helpers: `backend/tests/unit/test_system_config_extraction_helpers.py`.

**`rgpd_*` thinning (complete):**

| Service | Responsibility |
|---|---|
| `rgpd_helpers.py` | `_add_process_activity`, `_get_rgpd_or_404`, `_frontend_base_url_from_request` |
| `rgpd_request.py` | POST `/request` + `/admin/{id}/resend` (calls `rgpd_service.create_rgpd_request` / `send_rgpd_email`) |
| `rgpd_public.py` | validate / sign / status / data / list-by-process (calls `validate_token` / `sign_rgpd` / `get_rgpd_by_process`) |
| `rgpd_admin_list.py` | `/admin/all`, `/admin/{id}` CRUD, `/admin/stats/summary` |
| `rgpd_templates.py` | RGPD template CRUD + `_get_active_rgpd_template` + defaults |
| `rgpd_minutas.py` | Minuta template CRUD + `_get_active_minuta_template` + defaults |

Do **not** overwrite `rgpd_service.py` (PDF/email/token core) or `gdpr.py`. `rgpd_service` now imports active-template helpers from `rgpd_templates` / `rgpd_minutas` (routes still re-export for back-compat).

Unit helpers: `backend/tests/unit/test_rgpd_extraction_helpers.py`.

**`auth_*_handlers` thinning (complete) — do not overwrite `services/auth.py`:**

| Service | Responsibility |
|---|---|
| `auth_register_handlers.py` | POST `/register` |
| `auth_login_handlers.py` | deprecated POST `/login` (410) + POST `/login-v2` |
| `auth_profile_handlers.py` | GET `/me`, GET/PUT `/preferences`, PUT `/profile` (multi-empresa merge) |
| `auth_sessions_handlers.py` | POST `/refresh`, `/logout`, GET/DELETE `/sessions` |
| `auth_password_handlers.py` | POST `/change-password`, `/validate-password` |

Unit helpers: `backend/tests/unit/test_auth_extraction_helpers.py`.

**`visit_*` thinning (complete):**

| Service | Responsibility |
|---|---|
| `visit_helpers.py` | Calendar create/remove, portal status sync, background scraper |
| `visit_list_create.py` | GET `` list + POST create (scraper task + history) |
| `visit_kanban_get.py` | GET `/kanban` + GET `/{id}` |
| `visit_update_cancel.py` | PATCH update + DELETE cancel (calendar/portal sync) |

Do **not** collide with existing `portal_client_visits.py` (portal request/list). Prefer `visit_*` (not `visits_*`).

Unit helpers: `backend/tests/unit/test_visit_extraction_helpers.py`.

**`task_api_*` thinning (complete):**

| Service | Responsibility |
|---|---|
| `task_api_helpers.py` | `_block_parceiro` / `block_parceiro`, `get_user_names`, `enrich_task` |
| `task_api_crud.py` | Staff task create/list/my-tasks/get/update/complete/reopen/delete |
| `task_api_background.py` | GET `/active` + acknowledge/cancel for `background_jobs` |

**Never** overwrite `task_queue.py` / `task_log_service.py` / `scheduled_tasks.py` — thinning uses `task_api_*` prefix.

Unit helpers: `backend/tests/unit/test_task_extraction_helpers.py`.

**`backup_*` thinning (complete) — do **not** overwrite `services/backup.py` (core engine):**

| Service | Responsibility |
|---|---|
| `backup_ops.py` | statistics / history / verify / config / status |
| `backup_trigger.py` | POST `/trigger` + `/run-now` (+ `BackupRequest`) |
| `backup_restore.py` | POST `/restore-from-s3` + emergency `/restore` (atomic swap) |

Unit helpers: `backend/tests/unit/test_backup_extraction_helpers.py`.

**`public_*` thinning (complete) — do **not** overwrite `services/euribor_service.py`:**

| Service | Responsibility |
|---|---|
| `public_registration.py` | POST `/client-registration` (sanitize, RGPD encrypt, Pacote D process + magic link) |
| `public_health.py` | GET `/public/health` |
| `public_form_config.py` | GET `/form-config` (defaults from `form_config_defaults`, not via routes — avoids circular import) |
| `public_euribor.py` | GET `/euribor` wrapper → `euribor_service.get_euribor_rates` |

Preserve `@limiter.limit` on route stubs (`5/hour` registration, `30/minute` health, `60/minute` form-config). Form-config defaults are the same objects re-exported by `routes.form_config`.

Unit helpers: `backend/tests/unit/test_public_extraction_helpers.py`.

**`stats_*` thinning (complete) — do **not** collide with `analytics_service.py`:**

| Service | Responsibility |
|---|---|
| `stats_overview.py` | GET `/stats` (role-scoped KPI + Redis cache) |
| `stats_leads.py` | GET `/stats/leads` |
| `stats_conversion.py` | GET `/stats/conversion` |
| `stats_communications.py` | GET `/stats/communications` (portal + unread emails feed) |
| `stats_health.py` | GET `/health` (monitoring; Redis status) |
| `stats_branches.py` | GET `/stats/branches` (Pacote S bank/branch pipeline + status constants) |

Unit helpers: `backend/tests/unit/test_stats_extraction_helpers.py`.

**`shared_email_*` thinning (complete):**

| Service | Responsibility |
|---|---|
| `shared_email_helpers.py` | `ALLOWED_ROLES`, `_require_admin`, `_get_google_config`, `_build_redirect_uri` |
| `shared_email_crud.py` | list / get / upsert / delete shared role email configs |
| `shared_email_google.py` | `/google/callback` + `/{role}/google/login` + disconnect |
| `shared_email_sync.py` | POST `/{role}/sync` via `gmail_api_sync_to_db` |

Keep static `/google/callback` **before** `/{role}`. Unit helpers: `backend/tests/unit/test_shared_email_extraction_helpers.py`.

**`temp_link_api_*` thinning (complete) — do **not** overwrite `temp_link_service.py`:**

| Service | Responsibility |
|---|---|
| `temp_link_api_staff.py` | create / list-by-process / cancel / delete (auth) |
| `temp_link_api_public.py` | `/public/{token}` info/upload/download/download-all/files |

**Never** overwrite `temp_link_service.py` (core `TempLinkService`). Unit helpers: `backend/tests/unit/test_temp_link_extraction_helpers.py`.

**`google_auth_*` thinning (complete) — do **not** overwrite `gmail_oauth.py`:**

| Service | Responsibility |
|---|---|
| `google_auth_helpers.py` | `_get_google_config`, `_build_redirect_uri`, `_resolve_user` (Bearer + `?token=`) |
| `google_auth_oauth.py` | GET `/login` + `/callback` |
| `google_auth_status.py` | GET `/status` + DELETE `/disconnect` (per-role) |

**Never** overwrite `gmail_oauth.py` / `gmail_api_service.py`. Unit helpers: `backend/tests/unit/test_google_auth_extraction_helpers.py`.

**`admin_ai_*` thinning (complete) — sibling of `routes/admin_ai.py`:**

| Service | Responsibility |
|---|---|
| `admin_ai_config.py` | GET/PUT `/ai-config` + report recipients/config |
| `admin_ai_models.py` | AI models CRUD |
| `admin_ai_tasks.py` | AI tasks CRUD |
| `admin_ai_cache.py` | GET/PUT `/cache-settings` |
| `admin_ai_usage.py` | usage summary/by-task/by-model/trend/logs + weekly report |

**Never** create `services/admin_ai.py` (route module name). Do **not** overwrite `admin_ai_data.py` (training/import logs) or `ai_usage_tracker.py`. Unit helpers: `backend/tests/unit/test_admin_ai_extraction_helpers.py`.

**`ai_api_*` thinning (complete) — sibling of `routes/ai.py`:**

| Service | Responsibility |
|---|---|
| `ai_api_helpers.py` | `VALID_DOCUMENT_TYPES`, `map_extracted_data` |
| `ai_api_analyze.py` | sync analyze + OneDrive/S3 analyze + supported-documents |
| `ai_api_reset.py` | POST `/reset-client-data` |
| `ai_api_async.py` | async analyze + background worker |
| `ai_api_bulk.py` | bulk analysis async + background worker |

**Never** overwrite `ai_document.py` / `ai_document_analyzer.py` / `ai_page_analyzer.py` / `ai_usage_tracker.py` / `ai_improvement_agent.py`. Unit helpers: `backend/tests/unit/test_ai_api_extraction_helpers.py`.

**`ai_analysis_api_*` thinning (complete) — sibling of `routes/ai_analysis.py`:**

| Service | Responsibility |
|---|---|
| `ai_analysis_api_helpers.py` | locks, flatten/format/sanitize/build_context, `SYSTEM_PROMPT`, model constants |
| `ai_analysis_api_get.py` | GET `/processes/{id}/analyze` |
| `ai_analysis_api_generate.py` | POST `/processes/{id}/analyze` (OpenAI call + persist) |

**Never** overwrite `ai_document_analyzer.py` / `ai_page_analyzer.py` / `ai_document.py`. Unit helpers: `backend/tests/unit/test_ai_analysis_api_extraction_helpers.py`.

**`my_clients_api_*` thinning (complete) — do **not** overwrite `process_my_clients.py`:**

| Service | Responsibility |
|---|---|
| `my_clients_api_helpers.py` | status constants, process/stats query builders, lead row format |
| `my_clients_api_list.py` | GET `` (list + leads + enrichment; reuses `process_my_clients` maps) |
| `my_clients_api_stats.py` | GET `/stats` |

Unit helpers: `backend/tests/unit/test_my_clients_extraction_helpers.py`.

**`onedrive_*` thinning (complete) — do **not** overwrite `onedrive.py`:**

| Service | Responsibility |
|---|---|
| `onedrive_url_validation.py` | folder/link URL prefix checks |
| `onedrive_status.py` | GET `/status` |
| `onedrive_folder_url.py` | process folder URL get/save/delete |
| `onedrive_checklist.py` | checklist generate/get |
| `onedrive_files.py` | list client files by name (S3) |
| `onedrive_links.py` | process link CRUD + `LinkCreate`/`LinkUpdate` |

Unit helpers: `backend/tests/unit/test_onedrive_extraction_helpers.py`.

**`scraper_api_*` thinning (complete) — do **not** overwrite core scrapers:**

| Service | Responsibility |
|---|---|
| `scraper_api_models.py` | request/response models, friendly errors, site list, HTML source detect |
| `scraper_api_scrape.py` | `/single`, `/scrape`, `/crawl` |
| `scraper_api_ai.py` | supported-sites, analyze-with-ai, extract-html |
| `scraper_api_cache.py` | cache stats/clear/refresh |

Unit helpers: `backend/tests/unit/test_scraper_extraction_helpers.py`.

**`templates_api_*` thinning (complete) — do **not** overwrite `template_generator.py`:**

| Service | Responsibility |
|---|---|
| `templates_api_helpers.py` | roles, `DocumentRequestData`, error/download helpers |
| `templates_api_named.py` | webmail + named generate/download + document-request |
| `templates_api_checklist.py` | document checklist + document-types |
| `templates_api_generic.py` | available / generate / download / validate |

Unit helpers: `backend/tests/unit/test_templates_extraction_helpers.py`.

**`users_api_*` thinning (complete) — do **not** overwrite `auth.py`:**

| Service | Responsibility |
|---|---|
| `users_api_helpers.py` | `FORCED_SHARED_ROLES` |
| `users_api_list.py` | GET `` + GET `/{user_id}` |
| `users_api_email_config.py` | GET/POST `/me/email-config` + test |

Unit helpers: `backend/tests/unit/test_users_extraction_helpers.py`.

**`async_jobs_api_*` thinning (complete):**

| Service | Responsibility |
|---|---|
| `async_jobs_api_models.py` | Pydantic models + `ARQ_AVAILABLE` import guard |
| `async_jobs_api_analyze.py` | POST `/analyze` + GET `/{job_id}` |
| `async_jobs_api_session.py` | session start/analyze/status/finish |
| `async_jobs_api_health.py` | GET `/health` |

Unit helpers: `backend/tests/unit/test_async_jobs_extraction_helpers.py`.

**`ai_bulk_*` thinning (complete) — leave `routes/ai_bulk/` package helpers in place:**

| Service | Responsibility |
|---|---|
| `ai_bulk_models.py` | Pydantic request/response models |
| `ai_bulk_helpers.py` | `read_file_with_limit`, `update_client_data`, `log_import_*` |
| `ai_bulk_sessions.py` | import-session + aggregated session start/finish/status |
| `ai_bulk_analyze.py` | `/analyze-single` + aggregated `/analyze` |
| `ai_bulk_clients.py` | suggest/check/list/diagnose + analyzed-documents |
| `ai_bulk_cache_ops.py` | nif/duplicate cache + pending-reviews |
| `ai_bulk_import_errors.py` | get/resolve import errors (name avoids `routes.ai_bulk.import_errors`) |

Package `routes/ai_bulk/` (cache/jobs/matching/utils/constants/background_jobs) stays; `from routes.ai_bulk import router` still uses the sibling stub via importlib. Unit helpers: `backend/tests/unit/test_ai_bulk_extraction_helpers.py`.

**`admin_migration_api_*` thinning (complete) — never create `services/admin_migration.py`:**

| Service | Responsibility |
|---|---|
| `admin_migration_api_helpers.py` | `is_encrypted`, `pct`, `build_client_encryption_updates` |
| `admin_migration_api_task.py` | Background bulk `run_migration_task` |
| `admin_migration_api_status.py` | GET `/status` |
| `admin_migration_api_run.py` | POST `/run` + `/run-single/{client_id}` |

Unit helpers: `backend/tests/unit/test_admin_migration_extraction_helpers.py`.

**`companies_crud_api_*` thinning (complete):**

| Service | Responsibility |
|---|---|
| `companies_crud_api_helpers.py` | `resolve_logo_url` (S3 presign) |
| `companies_crud_api_list.py` | list / available / get |
| `companies_crud_api_mutate.py` | create / update / delete (+ UCR reassignment) |
| `companies_crud_api_logo.py` | POST `/{company_id}/logo` |

Keep `/available` before `/{company_id}`. Unit helpers: `backend/tests/unit/test_companies_crud_extraction_helpers.py`.

**`minutas_api_*` thinning (complete) — do not overwrite `rgpd_minutas.py`:**

| Service | Responsibility |
|---|---|
| `minutas_api_models.py` | `MinutaCreate` / `MinutaUpdate` |
| `minutas_api_crud.py` | list / create / get / update / delete |
| `minutas_api_import.py` | POST `/import` (docx/pdf/txt) |

Keep `/import` before `/{minuta_id}`. Unit helpers: `backend/tests/unit/test_minutas_extraction_helpers.py`.

**`user_company_roles_api_*` thinning (complete):**

| Service | Responsibility |
|---|---|
| `user_company_roles_api_crud.py` | list / get / create / update / delete |
| `user_company_roles_api_migrate.py` | `/migrate` + `/migrate-email-configs` |
| `user_company_roles_api_active.py` | `/set-active-company` |

Keep static `/migrate*`, `/set-active-company` before `/{role_id}`. Unit helpers: `backend/tests/unit/test_user_company_roles_extraction_helpers.py`.

**`deadlines_api_*` thinning (complete):**

| Service | Responsibility |
|---|---|
| `deadlines_api_crud.py` | create / update / delete |
| `deadlines_api_list.py` | list + `/my-deadlines` (role-scoped) |
| `deadlines_api_calendar.py` | `/calendar` enrichment |

Keep `/my-deadlines` and `/calendar` before `/{deadline_id}`. Unit helpers: `backend/tests/unit/test_deadlines_extraction_helpers.py`.

**`search_api_*` thinning (complete) — do **not** overwrite `utils/search_filters.py`:**

| Service | Responsibility |
|---|---|
| `search_api_helpers.py` | `normalize_text` |
| `search_api_global.py` | GET `/global` (processes + clients + tasks) |
| `search_api_processes.py` | GET `/processes` |
| `search_api_suggestions.py` | GET `/suggestions` |

Unit helpers: `backend/tests/unit/test_search_extraction_helpers.py`.

**`restore_api_*` thinning (complete) — do **not** overwrite `backup_restore.py`:**

| Service | Responsibility |
|---|---|
| `restore_api_helpers.py` | `TERMINAL_STATUSES` |
| `restore_api_process.py` | POST `/processes/{id}/restore` (+ cascade) |
| `restore_api_document.py` | POST `/documents/{id}/restore` (main + trash) |
| `restore_api_task.py` | POST `/tasks/{id}/restore` |
| `restore_api_list.py` | GET `/deleted/items` |

Unit helpers: `backend/tests/unit/test_restore_extraction_helpers.py`.

**`match_api_*` thinning (complete) — do **not** overwrite `client_match.py`:**

| Service | Responsibility |
|---|---|
| `match_api_smart.py` | GET `/process/{process_id}` (smart match + scoring) |
| `match_api_client.py` | `/client/{id}/all|properties|leads|summary` wrappers |
| `match_api_property.py` | `/property/{id}/clients` + `/lead/{id}/clients` wrappers |

Keep `/process/{id}` before `/client/...` / `/property/...` / `/lead/...`. Unit helpers: `backend/tests/unit/test_match_extraction_helpers.py`.

**`websocket_api_*` thinning (complete) — do **not** overwrite `websocket_manager.py`:**

| Service | Responsibility |
|---|---|
| `websocket_api_helpers.py` | JWT verify + disconnect detection |
| `websocket_api_notifications.py` | `/ws/notifications` loop (ping, read, rooms, locks) |
| `websocket_api_status.py` | GET `/ws/status` |

Unit helpers: `backend/tests/unit/test_websocket_extraction_helpers.py`.

**`gdpr_api_*` thinning (complete) — do **not** overwrite `gdpr.py`:**

| Service | Responsibility |
|---|---|
| `gdpr_api_models.py` | `AnonymizeRequest` / `BatchAnonymizeRequest` |
| `gdpr_api_read.py` | statistics / eligible / audit / config |
| `gdpr_api_mutate.py` | anonymize / batch / export |

Unit helpers: `backend/tests/unit/test_gdpr_extraction_helpers.py`.

**`annotations_api_*` thinning (complete) — do **not** overwrite `annotation_service.py`:**

| Service | Responsibility |
|---|---|
| `annotations_api_list.py` | document / process list + stats |
| `annotations_api_crud.py` | create / update / delete / resolve |

Keep `/document` and `/process/{id}/stats` before `/{annotation_id}`. Unit helpers: `backend/tests/unit/test_annotations_extraction_helpers.py`.

**`ai_import_logs_api_*` thinning (complete) — do **not** overwrite `admin_ai_data.py`:**

| Service | Responsibility |
|---|---|
| `ai_import_logs_api_helpers.py` | create / update / finalize (used by bulk/analyzer) |
| `ai_import_logs_api_list.py` | list + `/stats` |
| `ai_import_logs_api_detail.py` | get / delete |

Route re-exports helpers for back-compat (`routes.ai_import_logs`). Keep `/stats` before `/{log_id}`. Unit helpers: `backend/tests/unit/test_ai_import_logs_extraction_helpers.py`.

**`task_logs_api_*` thinning (complete) — do **not** overwrite `task_log_service.py`:**

| Service | Responsibility |
|---|---|
| `task_logs_api_list.py` | `/active` + list |
| `task_logs_api_actions.py` | get / acknowledge / cancel / delete |

Keep `/active` and list `""` before `/{task_id}`. Unit helpers: `backend/tests/unit/test_task_logs_extraction_helpers.py`.

**`admin_encryption_api_*` thinning (complete) — never create `services/admin_encryption.py`:**

| Service | Responsibility |
|---|---|
| `admin_encryption_api_status.py` | GET `/status` |
| `admin_encryption_api_migrate.py` | `/migrate` + `/migrate-sync` |
| `admin_encryption_api_verify.py` | `/verify/{id}` + `/encrypt-process/{id}` |

Unit helpers: `backend/tests/unit/test_admin_encryption_extraction_helpers.py`.

**`gov_auth_api_*` thinning (complete):**

| Service | Responsibility |
|---|---|
| `gov_auth_api_helpers.py` | Mock citizen, JWT create, env config |
| `gov_auth_api_login.py` | Start CMD / AMA OAuth redirect |
| `gov_auth_api_callback.py` | OAuth callback → frontend with gov_token |
| `gov_auth_api_verify.py` | Decode/verify temporary gov_token |

Unit helpers: `backend/tests/unit/test_gov_auth_extraction_helpers.py`.

**`companies_api_*` thinning (complete) — company email configs (distinct from `companies_crud_api_*`):**

| Service | Responsibility |
|---|---|
| `companies_api_list.py` | List configs / available companies / get one |
| `companies_api_mutate.py` | Create / update / delete email config |

Keep `/available-companies` before `/{company_name}`. Unit helpers: `backend/tests/unit/test_companies_extraction_helpers.py`.

**`alerts_api_*` thinning (complete) — do **not** overwrite `services/alerts.py`:**

| Service | Responsibility |
|---|---|
| `alerts_api_process.py` | Process alerts, age, pre-approval, docs, deed reminder |
| `alerts_api_notifications.py` | List notifications + mark read |

Unit helpers: `backend/tests/unit/test_alerts_extraction_helpers.py`.

**`storage_api_*` thinning (complete) — do **not** overwrite `s3_storage.py` / `storage_service.py`:**

| Service | Responsibility |
|---|---|
| `storage_api_status.py` | Provider status (S3 / OneDrive) |
| `storage_api_folder.py` | Process folder URL get/save/delete |
| `storage_api_checklist.py` | Document checklist generate/get |

Unit helpers: `backend/tests/unit/test_storage_extraction_helpers.py`.

**`portal_settings_api_*` thinning (complete) — careful vs `portal_*`:**

| Service | Responsibility |
|---|---|
| `portal_settings_api_helpers.py` | Defaults, `render_welcome_message`, get doc |
| `portal_settings_api_crud.py` | Get / update / reset welcome template |
| `portal_settings_api_preview.py` | Preview rendered welcome |

Route re-exports helpers for back-compat (`routes.portal_settings` → `portal_status`). Unit helpers: `backend/tests/unit/test_portal_settings_extraction_helpers.py`.

**`automation_api_*` thinning (complete):**

| Service | Responsibility |
|---|---|
| `automation_api_rules.py` | Rule models + CRUD |
| `automation_api_meta.py` | Triggers / actions catalogs |
| `automation_api_engine.py` | GET `/api/automations` — telemetria do motor (leitura) |

Unit helpers: `backend/tests/unit/test_automation_extraction_helpers.py`.

**`announcements_api_*` thinning (complete):**

| Service | Responsibility |
|---|---|
| `announcements_api_crud.py` | List / create / delete |
| `announcements_api_interactions.py` | Like / read / readers |

Keep `/readers/{id}` before `/{announcement_id}`. Unit helpers: `backend/tests/unit/test_announcements_extraction_helpers.py`.

**`changelog_api_*` thinning (complete) — do **not** overwrite `changelog_service.py`:**

| Service | Responsibility |
|---|---|
| `changelog_api_list.py` | List published changelogs |
| `changelog_api_diagnose.py` | Diagnose AI generation readiness |
| `changelog_api_generate.py` | Generate changelog via IA |

Unit helpers: `backend/tests/unit/test_changelog_extraction_helpers.py`.

**`portal_admin_api_*` thinning (complete):**

| Service | Responsibility |
|---|---|
| `portal_admin_api_impersonate.py` | Staff “Ver como Cliente” impersonation |

Unit helpers: `backend/tests/unit/test_portal_admin_extraction_helpers.py`.

**`push_notifications_api_*` thinning (complete) — do **not** overwrite `push_notifications.py` (VAPID):**

| Service | Responsibility |
|---|---|
| `push_notifications_api_subscribe.py` | Subscribe / unsubscribe / unsubscribe-all + models |
| `push_notifications_api_status.py` | Subscription status |

Unit helpers: `backend/tests/unit/test_push_notifications_extraction_helpers.py`.

**`activities_api_*` thinning (complete):**

| Service | Responsibility |
|---|---|
| `activities_api_crud.py` | Create / list / delete (stealth guard preserved) |
| `activities_api_history.py` | Process history list |

Unit helpers: `backend/tests/unit/test_activities_extraction_helpers.py`.

**`audit_api_*` thinning (complete) — do **not** overwrite `audit_trail_service.py`:**

| Service | Responsibility |
|---|---|
| `audit_api_trail.py` | List trail + stats |
| `audit_api_export.py` | CSV export |
| `audit_api_cleanup.py` | Retention cleanup |

Unit helpers: `backend/tests/unit/test_audit_extraction_helpers.py`.

**`user_branches_api_*` thinning (complete):**

| Service | Responsibility |
|---|---|
| `user_branches_api_crud.py` | Custom branch create / list / delete |

Unit helpers: `backend/tests/unit/test_user_branches_extraction_helpers.py`.

**`ai_agent_api` thinning (complete):**

| Service | Responsibility |
|---|---|
| `ai_agent_api.py` | analyze-all / analyze-single / suggestions / alerts / stats |

Do **not** overwrite `ai_improvement_agent.py`. Unit helpers: `backend/tests/unit/test_ai_agent_extraction_helpers.py`.

**Fat route thinning: complete.** All substantive FastAPI route modules now use thin stubs + `run_*` services. Large line counts on already-thinned stubs (`documents`, `emails`, `admin`, `processes`) are many thin endpoint declarations — edit the matching `services/*` modules, not the route file.

**Route thinning status:** complete for practical purposes (only intentional leftover: `routes/ai_bulk/*` package helpers). Do not reopen fat route files to stuff logic back in. Merged via PR #565 into `dev`.

### Active feature plan (branch `cursor/multi-profile-ai-visits-toasts-0b1c`)

| Item | Status | Notes |
|---|---|---|
| Visitas URL/IA | **done** | `scraper_status` completed/error; preview PT→EN; poll pending; nav Visitas restored |
| Toasts BG | **done** | sticky loading → morph green/red; **never auto-dismiss on nav**; dismiss via X; max 5 loading |
| Multi-perfil webmail | **done** | `effectiveRole`/company gates; forced-shared uses effective role; OAuth prefers company key |
| IA documentos | **done (canonical + UI)** | Analisar/Renomear IA; `MANAGEMENT_ROLES`; `ai_analyzed`; dialog titular 1/2 se ambíguo |
| Portal fulfill staff upload | **done** | `document_portal_fulfill` no upload CRM + auto-cat |
| ProcessDetails mutations | **done (writes)** | `useProcessMutations` + `sanitizeProcessUpdatePayload`; load já era `useProcessFullData` |
| Pacote FN — `/processes/me` + UCR | **done** | Loop fetch parado; `X-Company-Id` = id; match UCR por nome; header honrado se JWT+empresa válidos |

Optional follow-ups: Gemini-only admin picks on OpenAI analyzer client; portal visitas tab / consultor RBAC for unassigned pedidos; orphan AI paths left intentionally; ProcessDetails ainda híbrido (RGPD / magic-link / AI fetch pontual); mais extracção de tabs do monolito.

### Frontend UX Audit + Calculadoras (PRs #590–#602, `FRONTEND_UX_AUDIT.md`) — done

| Fase / Item | Status | Notes |
|---|---|---|
| Fase 1 — código morto | **done** | Remoção de componentes/rotas/imports não usados (#592) |
| Fase 2 — notificações unificadas | **done** | Sistema único `sonner`; sem libs de toast paralelas (#592) |
| Fase 3 — lógica duplicada centralizada | **done** | `formatCurrency`, `validateNIF`, helpers repetidos → `utils/` (#592) |
| Fase 4–5 — componentes partilhados + ConsultorDashboard | **done** | `StatCard`/`StatusBadge`/`Spinner`/`EmptyState`/`PageHeader` canónicos em `components/shared/`; migração de Dashboards/RGPD/Finance; remove double padding; `ConsultorDashboard` redesenhado em 3 zonas (foco, funil, tabs) (#594) |
| Fase 6 — ESLint `no-restricted-syntax` (cores Tailwind cruas) | **done** | Ver bullet em "Non-obvious gotchas"; regra `warn`, gate CI só em `error` (#596) |
| ProcessDetails Progressive Disclosure | **done** | Ver bullet em "Non-obvious gotchas" — `PageHeader` + grid 2/3+1/3 + `ClientContextCard`/`AssignmentContextCard`/`HistoryTab` (#597, #599) |
| Prioridade → `AssignmentContextCard` | **done** | Deixa de ter `Card` isolado no Resumo; vive como `DropdownMenu`+`Badge` (#601) |
| Calculadora de Prestações (`/calculadoras`) | **done** | Ver bullet em "Non-obvious gotchas" — `MortgageSimulator.jsx` + `mortgageCalculations.js` (#601) |

Norma de referência para todo este pacote: `FRONTEND_GUIDELINES.md` (criado em #601/#602, consolida Progressive Disclosure + regra ESLint + utilitários centralizados — ler antes de editar UI densa).

#### 1) Multi-perfil → webmail / email config — **done**

**Product:** IMAP/SMTP from company; user sets email+password; multi-profile ⇒ usually different companies ⇒ different emails.

**Fixed:** gates use `effectiveRole`; forced-shared uses effective role; OAuth prefers `company:<id>`.

#### 2) IA em documentos → atualizar ficha — **done (canonical path)**

**Canonical only:** ProcessDetails → S3 “Analisar com IA” → `/documents/ai-analyze` → apply-suggestions. No duplicate UI.

**Fixed:** model from admin config; compare/apply use `monthly_income` / `employer_name`.

**UI (S3FileManager):** Analisar/Renomear IA visíveis; RBAC gestão; badge + skip `ai_analyzed`; Renomear categoriza antes de renomear.

**Titular 1 vs 2:** se `needs_titular_choice`, dialog em ProcessDetails; apply com `target_titular` → `titular2_data` quando aplicável.

**Gaps left:** conflict UX still split; OpenAI client may not call Gemini ids; orphan `/api/ai/analyze-document*` and upload OCR `data_suggestions` untouched.

#### 3) Toasts de tarefas em background — **done**

Sticky `toast.loading` (id `bg-task-*`, `duration: Infinity`) → morph success/error; **não** auto-dismiss quando a tarefa sai de `/tasks/active` (sobrevive a mudança de página); dismiss só via X. Cap loading 5; `visibleToasts={8}`.

#### 4) Gestor de visitas + IA URL — **done (CRM path)**

`_run_scraper_for_visit` sets completed/error; VisitsPage normalizes preview + polls; DashboardLayout Visitas nav restored. Portal tab / consultor RBAC for unassigned portal requests still optional.

Owner clarified: email is per **company** (IMAP/SMTP from company; user sets email+password). Multiple profiles ⇒ usually different companies ⇒ different emails.

**`document_*` service map (keep `@router` names stable — rate-limit / integration tests scrape handler names in `routes/documents.py`):**

| Service | Responsibility |
|---|---|
| `document_constants.py` | Error strings, HTTP response docs, `DOCUMENT_CATEGORY_MAP` |
| `document_filenames.py` | `normalize_filename`, `generate_smart_filename`, log sanitize |
| `document_process_resolve.py` | Flexible process/client ID resolve + S3 path ownership checks |
| `document_expiring_dashboard.py` | Expiring-docs dashboard query/grouping |
| `document_portal_request.py` | Portal request CRUD (staff → client) |
| `document_portal_fulfill.py` | Staff CRM upload → REQUESTED/PENDING → RECEIVED (portal checklist) |
| `document_titular_match.py` | Match IA extract vs titular1/2; `needs_user_choice` se ambíguo |
| `document_auto_categorize.py` | Background IA categorize + OCR entities (**re-exported** from `routes.documents` for tests) |
| `document_upload_conflict.py` | Pre-upload filename conflict check |
| `document_direct_upload.py` | Pre-signed URL generate + confirm-upload |
| `document_upload.py` | Multipart upload pipeline (MIME validate, convert, IA triage, S3, history) |
| `document_move.py` | Move/rename conflict check + move-to-category |
| `document_ai_analyze.py` | Multi-doc IA analyze + organize-after-analysis + titular_matches / apply `target_titular` |
| `document_delete.py` | Delete + bulk-delete with cross-process scope guard |
| `document_proxy.py` | S3 download proxy (StreamingResponse) |
| `document_bulk_download.py` | Multi-file ZIP download |
| `document_categorize.py` | On-demand categorize one / all |
| `document_rename_smart.py` | Smart rename one / all |
| `document_s3_paths.py` | Path variation helpers (underscore/space) |
| `document_queries.py` | Process docs list, metadata, search, categories |
| `document_expiry_crud.py` | Manual expiry CRUD + upcoming/calendar + DOCUMENT_TYPES |
| `document_misc.py` | check-file, init-folders, download URLs, employer NIF |
| `document_ocr_data.py` | OCR status, data suggestions, resolve/confirm conflicts |

**Gotchas**
- After changing route modules without `--reload`, restart uvicorn (cloud agents often run without reload).
- `auto_categorize_document_background` must remain importable as `from routes.documents import auto_categorize_document_background`.
- Motor `insert_one` mutates dicts with ObjectId `_id` — strip before JSON responses (portal create already does).
- Unit helpers: `backend/tests/unit/test_document_extraction_helpers.py`.

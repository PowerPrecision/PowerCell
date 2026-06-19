# Changelog

Todas as mudanças notáveis neste projeto serão documentadas neste arquivo.
O formato é baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.0.0/).

## [2026-06-18] — Pacote A: Script Massivo de Mock Data (100+ Clientes e Portal)

### Adicionado
- **Script de injeção de dados massivo para testar o CRM e o Portal do Cliente ao limite em DEV** (`feat`): `backend/scripts/seed_massive_dev_data.py`. Gera ~120 clientes principais + processos + 2ºs titulares + documentos/mensagens do Portal + tarefas + histórico, com dados portugueses realistas (Faker `pt_PT` + NIF válido com check digit).
  - **Clientes (120+)**: perfil COMPLETO — NIF válido (9 dígitos, check digit correto), morada completa, data de nascimento, estado civil, dependentes, profissão, vínculo laboral, contactos (email/telefone primário e secundário), código de acesso ao Portal, dados financeiros completos (salário, outros rendimentos, IRS com taxa de retenção e escalão, despesas, capitais próprios, dependentes, outros créditos).
  - **Processos (1 por cliente)**: dados do Imóvel simulado completos (valor, financiamento pretendido, tipologia, concelho, freguesia, área, certificado energético, datas CPCV/escritura) + dados de crédito completos (montante, prazo, taxa, spread, euribor, prestação mensal, banco). Atribuições a consultor/indexador/intermediário reais (ou dummies criados se não existirem).
  - **2º Titular (~30%)**: em ~30% dos processos é criado um SEGUNDO cliente completo e associado via `second_client_id` + `titular2_data` (denormalizado) + `second_client_name`, com dados financeiros próprios.
  - **Distribuição de estados** conforme percentagens pedidas: `pre_registo` 10%, `clientes_espera` 15%, `triagem` 15%, `intermediario` 30%, `aprovado` 10%, `concluido` 10%, `desistencia` 5%, `eliminado` (`is_deleted=True`) 5%. Os estados são upserted em `workflow_statuses` para garantirem visibilidade no Kanban (passível de desligar com `--no-ensure-statuses`).
  - **Portal — Documentos**: 3-5 registos em `documents` por processo, mistura de `REQUESTED` (pedidos pelo consultor, `source=admin_request`) e `UPLOADED` (carregados pelo cliente, `source=client_portal`), com categorias válidas do Portal (`Cartao_Cidadao`, `IRS`, `Recibo_Vencimento`, etc.).
  - **Portal — Mensagens**: 2-4 mensagens em `portal_messages` por processo simulando conversa consultor ↔ cliente (`sender_type=staff/client`, `read_by_client`/`read_by_staff`).
  - **Tarefas**: 5-10 por processo, distribuídas entre completadas (passado), pendentes (futuro) e atrasadas (`is_overdue=True`), com `due_date`, `completed_at`, `days_until_due`.
  - **Histórico/Atividades**: 4-6 registos em `history` (audit log: criação, mudanças de estado, validação de documentos, etc.) + 1-2 em `activities` (comentários) por processo, datas aleatórias nos últimos 60 dias (timeline coerente).
  - **Execução segura**: usa `MONGO_URL`/`DB_NAME` do `backend/.env`; por defeito **adiciona** aos existentes (não limpa); `--clear` remove apenas dados deste script (`_seed_script=seed_massive_dev_data`); inserções em batches via `asyncio.gather` + `insert_many` (batch configurável com `--batch-size`, default 50) para não rebentar com a memória; todos os docs marcados com `_seed_data`/`_seed_script` para cleanup fácil.
  - **Auto-detecção de empresa ativa**: `company_id`/`company_name` resolvido por ordem de prioridade — `user_company_roles` (is_default) → `user_company_roles` (mais comum) → `company_email_configs` → `users.company` (mais comum) → fallback "Power Real Estate". Override com `--company-id`/`--company-name`.
  - **CLI flexível**: `--num-clients`, `--clear`, `--no-ensure-statuses`, `--company-id`, `--company-name`, `--batch-size`, `--skip-docs`, `--skip-messages`, `--skip-tasks`, `--skip-history`.

### Notas
- **Bug corrigido no gerador de NIF**: o `seed_realistic_data.py` (existente) gerava NIFs de **10 dígitos** (off-by-one: 1 + 8 aleatórios + 1 check = 10), que falham o `validate_nif` do `models/client.py` (exige 9). O novo script gera NIFs de **9 dígitos** corretos (1 + 7 aleatórios + 1 check), verificados contra o algoritmo oficial e contra o validador do modelo. Nota: o `seed_realistic_data.py` continua com o bug (não foi alterado neste commit) — os NIFs inválidos só causam problema se passarem por validação Pydantic; como o seed insere direto no MongoDB (schemaless), ficam armazenados como strings inválidas.
- O script **não encripta** dados sensíveis (NIF/email em claro) — consistente com o `seed_realistic_data.py` existente. As funções `decrypt_client_data`/`decrypt_sensitive_data` do backend têm fallback para dados em claro, pelo que os clientes/processos seeded são lidos corretamente. Destinado a **DEV apenas**.
- Os estados `triagem`, `intermediario`, `aprovado`, `desistencia` (pedidos pelo user) não são valores do `ProcessStatus` canónico (que tem `analise`, `credito_aprovado`, `desistencias`), mas o sistema suporta workflow statuses customizáveis via `workflow_statuses` — o script faz upsert destes para garantirem visibilidade no Kanban. Se preferir mapear para os canónicos, edite `STATUS_PLAN` no topo do script.

## [2026-06-18] — Hotfix: Cliente 404 ao Abrir Página + Desaparecimento da Lista de Ativos

### Corrigido
- **404 ao abrir a página do cliente após marcar um processo como desistência** (`fix` — **CRÍTICO**): O `GET /api/clients/{id}` devolvia 404 quando o `id` não correspondia a um documento na coleção `clients`. Isto acontecia porque a lista de clientes é construída a partir de PROCESSOS (não da coleção `clients`), e o `id` devolvido era `proc.client_id or proc.id` — quando o `client_id` estava vazio (processo órfão), a lista devolvia o **id do processo** como id do cliente, e o `GET /clients/{process_id}` não encontrava nada → 404. Adicionado fallback no `GET /clients/{id}`: se o documento do cliente não existir, procura processos por `id` ou `client_id` e constrói uma resposta sintética de cliente a partir dos dados do processo (marcada com `_synthetic: true`). No caminho sintético, procura também outros processos com o mesmo `client_id` para listar todos os processos do cliente. `backend/routes/clients.py`.
- **DELETE /clients/{id} criava processos órfãos (causa raiz do 404)** (`fix` — **CAUSA RAIZ**): O `DELETE /clients/{id}` fazia `$unset: {"client_id": ""}` em todos os processos associados ao cliente — removendo a referência `client_id` dos processos. Isto "órfão" os processos: a lista de clientes passava a devolver o id do processo (fallback `proc.client_id or proc.id`), e o `GET /clients/{process_id}` devolvia 404. Agora o DELETE **mantém a referência `client_id`** nos processos (apenas atualiza `updated_at`) — o cliente fica soft-deleted (`is_deleted: True`) mas os processos continuam ligados a ele. O `GET /clients/{id}` não filtra `is_deleted`, pelo que a página abre normalmente. Para desvincular um processo específico, continua a existir `DELETE /clients/{id}/unlink-process/{process_id}`. `backend/routes/clients.py`.
- **Mudar status via dropdown não atualizava `is_active` do processo** (`fix` — **CONSISTÊNCIA**): O `PUT /api/processes/{id}` (usado pela dropdown de estado nos Detalhes do Processo) atualizava o `status` mas NÃO o `is_active`. Só o endpoint de move (kanban drag-and-drop) atualizava `is_active`. Resultado: um processo mudado para "desistencias" via dropdown ficava com `is_active: True` (desatualizado), causando inconsistência nos filtros da lista de clientes ativos (`active_processes_count` usa `is_active AND status not in terminal`). Agora o PUT também sincroniza `is_active` com o novo estado: terminais (`desistencias`, `concluidos`, `concluido`, `arquivo`, `arquivado`, `perdido`, `eliminado`, `eliminados`) → `is_active: False`; restantes → `is_active: True`. `backend/routes/processes.py`.
- **`active_processes_count` não excluía processos "eliminado"** (`fix`): A lista de status terminais usada para contar processos ativos (`["desistencias", "concluidos", "arquivado", "perdido", "concluido"]`) não incluía `"eliminado"`/`"eliminados"` nem `"arquivo"` (só `"arquivado"`). Um processo eliminado podia ser contado como ativo se `is_active` fosse True. Alinhada a lista com todos os terminais canónicos e legacy. `backend/routes/clients.py`.

### Notas
- **Cenário do user**: cliente com 2 processos, um marcado como desistência. O cliente desaparecia da lista de ativos e a página dava 404. Com estas correções: (1) o 404 deixa de ocorrer (fallback para dados do processo), (2) a causa raiz (unset do client_id no DELETE) é eliminada, (3) o `is_active` fica consistente entre kanban e dropdown, (4) a contagem de processos ativos exclui todos os terminais. Se o cliente tiver um processo ativo (não-terminal), continua a aparecer na lista de ativos.
- O `DELETE /clients/{id}/unlink-process/{process_id}` (desvincular um processo específico) continua a fazer `$unset` do `client_id` — é o mecanismo intencional para desvincular. O que foi removido é o unset automático em CASCATA quando se apaga o cliente.
- O flag `_synthetic: true` na resposta do GET é informativo; o frontend pode usá-lo para mostrar um aviso ("cliente sem documento próprio — dados derivados do processo") mas funciona sem alterações de frontend.

## [2026-06-18] — Hotfix: Tarefas (e Chat) Desapareceram dos Detalhes do Processo

### Corrigido
- **Card de Tarefas desapareceu dos Detalhes do Processo para consultor, intermediário, administrativo e diretor** (`fix` — **REGRESSÃO DE PERMISSÕES CRÍTICO**): O `canManageTasks` em `ProcessDetails.js` avalia `userActions.length > 0 ? userActions.includes("manage_tasks") : roleFallback`. Como o `/auth/me` corre `sync_permissions_with_role_defaults` em cada pedido e popula `permissions.actions`, `userActions.length > 0` é **sempre true** para staff — pelo que a primeira via executa e exige a action `manage_tasks`. Ora, os `DEFAULT_PERMISSIONS_BY_ROLE` em `backend/services/permissions.py` **não incluíam `manage_tasks`** nos defaults de `diretor`, `consultor`, `intermediario` e `administrativo` (só `admin`/`ceo` via `AVAILABLE_ACTIONS.copy()` e `indexacao` explicitamente). Resultado: estes roles perdiam o card de Tarefas (e o de Chat, mesmo problema com `use_chat`) nos Detalhes do Processo, mesmo sendo staff que deve gerir tarefas. `backend/services/permissions.py`.
- **Chat do processo também desaparecido para os mesmos roles** (`fix`): O `canUseChat` segue o mesmo padrão e `use_chat` também não estava nos defaults de `diretor`/`consultor`/`intermediario`/`administrativo`. Corrigido em conjunto.

### Alterado
- **Defaults de permissões alinhados com o fallback por role do frontend** (`fix`): Adicionado `manage_tasks` e `use_chat` aos `DEFAULT_PERMISSIONS_BY_ROLE` de `diretor`, `consultor`, `intermediario` e `administrativo`. Adicionado também `assign_process_users` ao `diretor` (alinhado com `canAssignUsers` que já o permitia via fallback de role para admin/ceo/diretor). Isto garante que estes roles vêem e gerem Tarefas e Chat nos Detalhes do Processo. A propagação é **automática**: o `/auth/me` faz `sync_permissions_with_role_defaults` (merge `set(defaults + user_perms)`) em cada pedido e persiste se houver diferença — pelo que os utilizadores existentes recebem as novas actions no próximo login/refresh, sem necessidade de script de migração. `backend/services/permissions.py`.

### Notas
- `admin` e `ceo` continuam com todas as actions (via `AVAILABLE_ACTIONS.copy()`); `indexacao` já tinha `manage_tasks`/`use_chat`/`assign_process_users` (mantido); `cliente` e `parceiro` continuam sem actions (sem acesso a staff).
- A semântica de permissões customizadas é preservada: se um admin remover `manage_tasks` das permissões de um consultor via UI de Permissões, o consultor perde o card (comportamento pretendido). A correção foca-se nos **defaults** — garante que um consultor "fresco" (sem customizações) vê as Tarefas e o Chat.
- O `canManageTasks`/`canUseChat` do frontend não foi alterado: a correção é toda no backend (defaults), que é o sítio certo para definir "o que cada role pode fazer por defeito".

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

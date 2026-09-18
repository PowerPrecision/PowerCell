# Frontend Guidelines — PowerCell CRM

Normas de UX/UI e convenções técnicas para o frontend (React 19 + Vite + Tailwind CSS 4 + Shadcn UI). Ler em conjunto com `ARCHITECTURE.md` (padrões gerais) e `AGENTS.md` (notas operacionais para agentes).

---

## 1. Progressive Disclosure — norma absoluta

**Regra**: nunca mostrar tudo de uma vez numa página densa. Esconder complexidade secundária atrás de separadores, dialogs/sheets ou accordions, e mostrar só os dados/ações críticos por defeito.

Aplicações concretas já em produção:

| Onde | Como |
|---|---|
| `ProcessDetails` — separador Resumo | Dados críticos + Observações (`observations`) + Timeline compacta (últimos eventos); o filme completo continua no separador Histórico |
| `ProcessDetails` — separador Histórico | Timeline de fases + Atividades + "Filme da Lead" (auditoria unificada) — histórico completo, fora do fluxo de edição |
| `HistoryTab.jsx` — "Registar Atividade" | Formulário só aparece dentro de um `Dialog`, aberto por um botão de destaque ("➕ Registar Atividade"); nunca inline permanentemente |
| `S3FileManager` — Opções Avançadas | Accordion, fechado por defeito |
| Calculadoras (`MortgageSimulator.jsx`) | Campos de Seguro de Vida / Multirriscos só aparecem depois de o `Switch` "Incluir Seguros" ser ativado |

Ao adicionar uma nova secção a uma página já densa, a pergunta a fazer é: **"isto precisa de estar sempre visível, ou pode viver num separador/dialog?"**

---

## 2. Layout 2/3 (Tabs) + 1/3 (Context Cards)

Padrão para páginas de detalhe densas (ex: `ProcessDetails`):

```
grid grid-cols-1 lg:grid-cols-3 gap-6
├── lg:col-span-2 → Tabs (Resumo / Documentos / Histórico) — ação e exploração
└── (1 coluna)     → Contexto fixo, sempre visível independentemente do separador ativo:
                      ClientContextCard, AssignmentContextCard, TasksPanel, etc.
```

A coluna direita (1/3) é para **contexto de apoio à decisão** — quem está atribuído, prazos críticos, dados do cliente — nunca para formulários de edição extensos.

---

## 3. Eliminação de cartões redundantes para metadados simples

Metadados de uma única linha (ex: Prioridade, Etiquetas) **não** justificam um `Card` isolado no fluxo principal — ocupam espaço vertical desproporcional ao valor que trazem.

**Regra**: metadados simples (1 valor, poucas opções) vivem como um `Select` compacto, `Badge` ou `DropdownMenu` + `Badge`, integrados num cartão de contexto já existente (coluna direita) ou no `PageHeader` (ao lado de outro badge, ex: Status).

**Exemplo aplicado**: a Prioridade do processo deixou de ter um `Card` próprio no separador Resumo — passou a um `DropdownMenu` + `Badge` compacto dentro do `AssignmentContextCard` (coluna direita), ver `components/processDetails/AssignmentContextCard.jsx`.

---

## 4. Ocultação de formulários secundários em Modais/Sheets

Formulários que não são a ação principal da página (ex: registar uma nota, pedir RGPD, atribuir utilizadores) vivem em `Dialog` ou `Sheet` (Shadcn), acionados por um botão explícito — nunca ocupam espaço permanente no layout principal.

Listas potencialmente longas (atividades, histórico, notificações) vivem dentro de um `ScrollArea` com altura fixa (ex: `h-[500px]`), para impedir que a página estique infinitamente à medida que o histórico cresce. Ver `HistoryTab.jsx`.

---

## 5. Uso global de `EmptyState` e `PageHeader`

- **`components/shared/PageHeader.jsx`**: título canónico de página (ícone + título + badge inline + descrição + ações). Uma página não deve duplicar o título já mostrado pelo `PageHeader` no `title` do `DashboardLayout`, a não ser que o header fixo precise de um label curto.
- **`components/ui/EmptyState.jsx`**: placeholder canónico para listas/painéis vazios (ícone + título + mensagem + ação opcional). Preferir sempre a `EmptyState` a mensagens de "sem resultados" ad-hoc.

---

## 6. Tecnologia — regras técnicas

### Toasts — `sonner` exclusivo

- Único sistema de toasts da aplicação (não misturar com outras bibliotecas de notificação inline).
- `<Toaster />` (`components/ui/sonner.jsx`, montado em `App.js`) **tem sempre** `closeButton` ativo — o utilizador deve poder fechar qualquer toast manualmente, mesmo os "sticky" (`duration: Infinity`) usados para tarefas em background (`TasksContext`).
- Toasts de tarefas em background nunca são fechados programaticamente ao navegar de página (`toast.dismiss` proibido nesse fluxo) — só o X do utilizador fecha.

### ESLint `no-restricted-syntax` — Dark Mode safe colors

`eslint.config.js` bloqueia (nível `warn`, mas **errors-only via `--quiet` é o gate do CI**) o uso de classes Tailwind de cor cruas (`bg-gray-200`, `text-blue-600`, `border-red-500`, etc.) em `className`/`class` e em chamadas `cn()`/`clsx()`/`classnames()`/`cva()`. Motivo: cores cruas têm luminosidade fixa e não respondem à classe `.dark` como os tokens semânticos do Shadcn.

**Em código novo, usar sempre os tokens semânticos**: `bg-primary`, `bg-secondary`, `bg-accent`, `bg-muted`, `bg-destructive`, `text-foreground`, `text-muted-foreground`, `border-border`, etc. Código legado com cores cruas fica como aviso (warning) — não bloqueia o CI, mas não deve ser copiado para ficheiros novos.

### Centralização de utilitários

Evitar reimplementar helpers que já existem centralizados — encontrar 2+ cópias locais quase idênticas é sinal de que devem ser extraídas para `utils/`.

| Utilitário | Ficheiro | Nota |
|---|---|---|
| `formatCurrency(value, options)` | `utils/formatCurrency.js` | Única fonte de verdade para formatação de euros (`Intl.NumberFormat` pt-PT); export nomeado e default |
| `validateNIF(nif, options)` | `utils/validateNIF.js` | Inclui checksum (módulo 11) — não validar NIF sem checksum em formulários novos; `allowCompanyNIF` para contra-partes que podem ser pessoa colectiva |
| `simularCreditoHabitacao(...)` / `calcularPrestacaoMensal(...)` / `calcularTAEG(...)` | `utils/mortgageCalculations.js` | Motor de cálculo do sistema francês de amortização — extraído de `components/portal/SimulatorCH.jsx`, reutilizado em `components/calculators/MortgageSimulator.jsx` (Calculadoras do CRM) |

### Refresh token — single-flight obrigatório (fix Set 2026)

O backend roda o refresh token (**single-use**: `POST /auth/refresh` revoga
o token antigo). **Nunca** fazer pedidos directos a `/auth/refresh` a partir
de componentes ou contexts — usar sempre `getRefreshedToken()` (export de
`services/api.js`), a promessa single-flight partilhada por todos os
mecanismos (timer preventivo do `AuthContext`, interceptor Axios reativo a
401, fetch-guard de `sessionExpiry.js`). Dois refreshes concorrentes com o
mesmo token fazem o segundo receber 401 e disparar `forceSessionExpired()`
(logout inesperado). Novos mecanismos de renovação devem converger nesta
função, não criar a própria chamada.

---

## 7. Checklist antes de dar uma feature por terminada

- [ ] Nenhum `Card` isolado só para 1-2 campos de metadados simples.
- [ ] Formulários secundários estão em `Dialog`/`Sheet`, não inline permanentemente.
- [ ] Listas longas estão dentro de `ScrollArea` com altura máxima.
- [ ] Sem classes Tailwind de cor cruas em código novo (`yarn eslint . --quiet` sem erros).
- [ ] Valores monetários usam `formatCurrency`; NIFs usam `validateNIF`.
- [ ] `yarn lint`/`yarn eslint . --quiet` e `yarn build` correm sem erros.

---

## 8. Padrões consolidados (Pacote DD)

### Calculadoras vivem em Sheets globais

Ferramentas transversais que não pertencem ao fluxo de um processo específico (ex: Calculadora de Prestações) vivem num `Sheet` global aberto a partir do `TopNav` (cabeçalho superior do `DashboardLayout`), **não** numa rota dedicada com link na sidebar. Isto reduz a poluição da navegação lateral e torna a ferramenta acessível a partir de qualquer ecrã com um único clique num ícone discreto.

- **Ícone no TopNav**: `Button` `variant="ghost"` `size="icon"` com ícone `Calculator`, posicionado antes do `TasksDropdown`/`NotificationsDropdown`.
- **Sheet**: `side="right"` com `w-full sm:max-w-lg overflow-y-auto`, contendo o componente da calculadora.
- A rota e o link na sidebar anteriores (ex: `/calculadoras`) são removidos — a página `CalculatorsPage` fica comentada no `App.js` para referência futura, mas não é lazy-loaded nem navegável.

### Listas devem ter `max-height` + `ScrollArea`

Listas que podem crescer indefinidamente (tarefas, atividades, histórico, co-titulares) **devem** estar dentro de um `ScrollArea` do Shadcn com altura máxima explícita. Isto impede que a página estique infinitamente e mantém o layout previsível.

```jsx
<ScrollArea className="h-fit max-h-[400px]">
  <TasksPanel ... />
</ScrollArea>
```

Use `h-fit max-h-[Npx]` (não `h-[Npx]` fixo) para que listas curtas não ocupem espaço desnecessário.

### Metadados curtos embutem-se no header (sem fallbacks de "N/A")

Metadados curtos (etiquetas, prioridade, tipo de processo) vivem como `Badge` compactos no `PageHeader` (na `description` ou como `titleBadge`), **não** em `Card`s isolados no corpo da página. Ver `components/shared/PageHeader.jsx`.

- **Etiquetas**: `<Badge variant="secondary">` inline na `description` do `PageHeader`, a seguir ao tipo de processo / número.
- **Sem fallbacks "N/A"**: se um valor condicional (ex: DSTI automático) não for calculável, **oculta o elemento** (`return null`) em vez de mostrar "N/A". O "N/A" entre botões de ação é ruído visual. Ver `AutoDSTIBadge.js` (modo `compact` retorna `null` quando `!is_calculable`).

### Sem cartões de UI duplicados

Quando dois cartões mostram conceitos relacionados (ex: "2º Titular" que gere `titular2_data` e "2º Titular / Fiador" que mostra `co_buyers`/`co_applicants`), **consolide** num único cartão. A secção secundária (co-buyers/co-applicants, que são read-only) vive dentro do cartão principal, preservando a lógica de gravação deste. Ver `SecondTitularCard.jsx` — a secção `CoBuyersSection` foi movida para dentro do cartão principal.

### Toasts de background sempre com `closeButton`

Os toasts sticky de tarefas em background (`TasksContext`, `duration: Infinity`) **devem** incluir `closeButton: true` na chamada `toast.loading`/`toast.success`/`toast.error`. O `<Toaster />` global já tem `closeButton`, mas toasts individuais com `duration: Infinity` devem reforçar a opção para garantir que o botão X aparece.

```jsx
toast.loading(task.title, {
  id,
  description: task.progress_message || "Em curso…",
  duration: Infinity,
  closeButton: true,  // PACOTE DD — garantir botão de fechar
});
```

---

## 9. Portal do Cliente e Documentos Legais (Pacote DE)

### Portal do Cliente — sempre lógica de "append" em arrays de documentos

O Portal do Cliente **nunca** substitui ficheiros previamente carregados pelo cliente. Cada categoria de documento (Recibos de Vencimento, Extratos Bancários, IRS, Identificação, etc.) mantém um array `attached_files` que cresce com cada upload — o cliente pode enviar ficheiros faseados (1 hoje, 2 amanhã) sem perder os anteriores.

- **Backend**: `run_confirm_portal_upload` (`services/portal_upload_ops.py`) faz `$set` (status → RECEIVED) + `$push` (novo `file_entry` para `attached_files`). Os campos top-level (`filename`, `s3_path`) são atualizados para refletir o upload mais recente (backward compat), mas o array `attached_files` preserva o histórico completo. O mesmo padrão aplica-se a `fulfill_portal_requests_on_staff_upload` (`document_portal_fulfill.py`).
- **Frontend**: o input de ficheiro tem `multiple={true}` e está **sempre visível** (o botão não se esconde após o primeiro upload — muda o label para "➕ Adicionar ficheiros"). A lista de ficheiros anexados é mostrada numa `ScrollArea` com `Badge`s (filename + tamanho + botão de download por ficheiro).
- **Presigned URLs**: o upload usa o padrão presigned S3 (client → S3 direto, backend nunca recebe bytes). **Não** usar `List[UploadFile]` — seria uma regressão arquitetural.

### Documentos legais gerados — sempre pré-preenchidos do backend

Documentos legais gerados pelo sistema (RGPD, Minuta, CPCV) **devem** vir pré-preenchidos com os dados reais do cliente/processo quando o staff os descarrega para assinatura manual. O backend é a única fonte de verdade para os dados — o frontend não pré-preenche nada.

- **RGPD PDF**: `GET /api/rgpd/pdf/{process_id}` gera um PDF com o template ativo do RGPD, substituindo os placeholders (`{{NOME}}`, `{{CONTRIBUINTE}}`, `{{MORADA}}`, etc.) pelos dados desencriptados do cliente. Usa `reportlab` (já instalado) e reutiliza `_get_rendered_rgpd_text` + `_generate_rgpd_pdf_bytes` de `services/rgpd_service.py`.
- **Frontend**: o botão de RGPD no `PageHeader` do `ProcessDetails` é um `DropdownMenu` com 2 opções: "Solicitar Consentimento" (envia email com link) e "Descarregar PDF (Assinatura Manual)" (download do PDF pré-preenchido). O download usa o padrão blob (`responseType: "blob"` + `createObjectURL` + `link.click()`).

---

## 10. Área Pessoal — separação User (Global) vs Role/Perfil (Pacote DF)

A Área Pessoal (`ProfilePage`) segue uma separação estrita entre o que pertence à **pessoa** (global) e o que pertence a cada **perfil/role** (local por `user_company_role`). Isto evita perfis fantasma e a falsa noção de "conta principal".

### Renderização de perfis 100% dinâmica

As abas/secções de perfil são geradas **exclusivamente** a partir de `user.companies` (a lista de UCRs reais vindas do backend). **Nunca** hardcodear roles (`VALID_ROLES`, `additional_roles` sem validação) — isso produz perfis fantasma (ex: "Mediador" aparece mesmo sem o role).

```jsx
// PACOTE DF — Tabs dinâmicas baseadas em UCRs reais
const ucrTabs = useMemo(() => {
  return (user?.companies || [])
    .filter(c => c.role && c.company_id && c.company_id !== "default")
    .map(c => ({
      value: `${c.role}__${c.company_id}`,
      label: `${ROLE_LABELS[c.role] || c.role} @ ${c.company_name}`,
      Icon: ROLE_ICONS[c.role],
      companyId: c.company_id,
    }));
}, [user?.companies]);
```

Usar `ROLE_LABELS` e `ROLE_ICONS` de `utils/roleUtils.js` (não reimplementar localmente). Filtrar `company_id === "default"` — é um fallback sintético que não corresponde a nenhum UCR real.

### Estrutura: "Conta Global" + uma aba por perfil

- **Aba "Conta Global"** (sempre presente): contém APENAS cartões transversais à pessoa — Informação de Login (email, password) e Sessões Ativas. Sem `active_company_name` badge (já visível no `ContextSwitcher`).
- **Uma aba por UCR** (gerada dinamicamente): contém os cartões de perfil — Dados Profissionais, Assinatura de Email, Configuração de Webmail. Cada aba faz scoping via `X-Company-Id` header override (`api.put(url, data, { headers: { "X-Company-Id": companyId } })`).

### Sem "conta principal"

O conceito de "conta principal" foi removido. Não existe "Principal (Padrão)" como company_id sintético. O que existe é `is_default: true` num UCR (a empresa padrão do utilizador), mostrado como badge "Padrão" no `ContextSwitcher` — não como uma categoria separada de "conta".

### Settings sempre pré-preenchidas do backend

As settings de cada perfil (assinatura, webmail, preferências) são lidas do backend já scoped pelo UCR ativo (via `X-Company-Id`). O frontend não pré-preenche nem mistura contextos — cada aba carrega e guarda os seus dados de forma isolada. Ver `components/ProfileRoleTab.jsx`.

### Pacote DM — gravação isolada + assinatura Rich Text + perfil Mediador

- **Interceptor `api.js`**: nunca sobrescrever `X-Company-Id` / `X-Active-Role` se o pedido já os definiu. Sem isto, gravar IMAP/SMTP numa tab de perfil que não é a empresa activa global escrevia no UCR errado.
- **EmailConfigForm**: POST/GET/test enviam `company_id` no body, na query e no header da tab (`ProfileRoleTab.companyId`).
- **Assinatura**: renderizar com `RichTextViewer` / `dangerouslySetInnerHTML` + `sanitizeEmailHtml` (DOMPurify). Permitir `data:image`, `cid:` e `https` nas imagens. Se o HTML estiver gravado como entidades (`&lt;p&gt;`), `unescapeHtmlIfNeeded` recupera o markup.
- **Perfil Mediador**: não existe. `normalizeRole('mediador')` → `intermediario`. Tabs e o `ContextSwitcher` filtram `REMOVED_ROLES`. A dropbox extra de empresa no Diretor está oculta — a empresa vem do perfil no Header.
- **Impersonate**: o menu lateral usa o `user.role` impersonado. Abas de Administração (`showAdminButton`, Dashboard Executivo) escondem-se se o impersonado não for admin/CEO.
- **Rascunhos no Dashboard**: `getDraftNavigationTarget` — emails → `/webmail?folder=drafts&id=`, pré-registo → `/registos-clientes?clientId=`, processos → `/processo/:id` (nunca ProcessDetails para rascunhos de email).

### Pacote FN — headers UCR e Os Meus Processos

- **`X-Company-Id` é um id.** `AuthContext` guarda `activeCompanyId` via `resolveCompanyIdFromUser` (`utils/userProfiles.js`). Nunca persistir `user.company` (nome de exibição, ex. `Precision Crédito`) — o interceptor envia esse valor e o UCR deixa de bater.
- **Fonte dos headers:** `syncAuthContextHeaders({ role, companyId })` no AuthContext. O interceptor em `api.js` prefere este snapshot ao `sessionStorage`. Continua a **não sobrescrever** headers já definidos no pedido (tabs da Área Pessoal).
- **Não escrever `"all"` em `sessionStorage.activeRole`.** Esse sentinel não é um UCR. O cargo activo é do `ContextSwitcher`. `GET /processes/me` já filtra por atribuição (`mine_only`).
- **`ProcessesPage`:** dependências do `fetchProcesses` estáveis. `assignedUserIdsFilter` vem de `useMemo` sobre o query param — um array novo em cada render relança o efeito e, com lista vazia, entra em loop de `GET /processes/me`.
- Rotas: `/processos` = Os Meus Processos; `/lista-processos` = visão global; `/meus-clientes` = Os Meus Clientes.

---

## 11. Listagens — contextos Cliente vs Processo + Query Keys (Pacotes FK/FL/FJ)

**Regra**: filtros de **Cliente** e de **Processo** não se misturam na UI nem nas query keys. A query string da página é a fonte de verdade (partilhável, back/forward).

| Página | Componente de filtros | Params de URL | Não incluir |
|--------|----------------------|---------------|-------------|
| `/clientes` | `ClientFilters.jsx` | `search`, `fonte`, `tipo`, `status` (ficha: `active` / `inactive` / `deleted`) | `assigned_user_ids`, fase de workflow, `is_indexed` |
| `/processos`, `/lista-processos` | `ProcessFilters.jsx` | `search`, `status` (fase), `process_type`, `assigned_user_ids`, `assigned_logic` (`OR`/`AND`) | `fonte` / `tipo` da ficha de cliente |

- Dropdown «Atribuído a»: `useAssignmentUsersQuery` → `queryKeys.users.forAssignment()` → `GET /users?for_assignment=true`.
- Admin de organização: **sempre** `queryKeys.orgAdmin.companies(search)` / `.users()` / `.ucrs()` / `.ucrByUser(id)`. Proibido arrays literais (`['org-admin-companies']`) ou constantes locais (`USERS_QUERY_KEY`) — partem invalidações parciais.
- Invalidar Kanban com `queryKeys.processes.kanbanAll()`, nunca `['processes']` inteiro (apagaria detalhe/listas/`my-clients`).
- Código novo de cor: tokens Shadcn (`bg-primary`, `text-muted-foreground`, …), não classes Tailwind cruas.

---

## 12. Extração de cartões de páginas densas — pasta `components/<pagina>/` (Refactor UX — Fev 2026)

**Regra**: quando uma página composta por múltiplos cartões independentes (cada um com o seu próprio fetch/estado) ultrapassa ~400-500 linhas, extrair cada cartão para um componente próprio numa pasta `components/<nomeDaPagina>/`, mantendo a página original apenas como wrapper (guarda de permissões + layout + import dos cartões). Cada cartão extraído deve continuar autossuficiente (o seu próprio `useQuery`/`useState`), sem introduzir estado partilhado global que não existia antes. Helpers usados por mais de um cartão (ex: um `fetch` comum) vivem num ficheiro utilitário na mesma pasta (`<pagina>Api.js`), nunca duplicados.

**Exemplo aplicado**: `pages/EmailAccountsPage.js` (950 linhas, 3 cartões de configuração de email) foi dividido em `components/emailAccounts/{SystemSmtpCard,IndexationImapCard,SharedEmailCard}.jsx` + `emailAccountsApi.js` (helper `fetchSystemConfig` partilhado pelos dois primeiros cartões). A página ficou com ~75 linhas (guarda de role admin/ceo + grid de layout), sem qualquer alteração de lógica ou comportamento.

## 13. Badges de prioridade — campo explícito vence heurística derivada

Quando uma entidade tem um campo de prioridade explícito (`task.priority`, definido manualmente ou por um motor automático) **e** uma heurística derivada de outro campo (ex: prazo/`due_date`), o badge deve dar sempre prioridade ao valor explícito; a heurística só serve de *fallback* quando o campo explícito está vazio. Cores fixas por nível: Alta/High → vermelho (`variant="destructive"`), Média/Medium → amarelo/`outline` com classes `bg-yellow-100 text-yellow-700`, Baixa/Low → cinzento/`outline` com `bg-slate-100 text-slate-600`. Ver `getPriorityBadge` em `components/TasksPanel.js`.

## 14. Perfis fantasma e Webmail unificado (Pacote 8)

### Perfis do menu = UCRs reais, ponto final

`buildUserProfileItems` (`utils/userProfiles.js`) devolve **exclusivamente** os UCRs reais (`user.companies`) quando existem — **nunca** mesclar `additional_roles` ou o role primário de login nesses casos: eram a causa dos "perfis fantasma" (2 perfis activos, 3 opções no menu). O fallback legado (role primário + `additional_roles`) só existe para utilizadores **sem qualquer UCR**. O backend já filtra `is_deleted`/`is_active` na origem (ver `ARCHITECTURE.md` — "Filtro estrito de UCRs válidos"), pelo que qualquer perfil recebido é válido por construção.

### Webmail — seletor de caixas unificado, sem troca de perfil

- O `WebmailPage` carrega as contas com `GET /users/me/email-accounts?scope=all` (todas as empresas) — a lista de caixas **não** depende de `companyId`/`effectiveRole`, nem refaz fetch quando o perfil global muda.
- As opções do seletor vêm de `buildMailboxOptions` (`utils/webmailMailbox.js`): labels com sufixo da empresa (`Caixa Pessoal (a@x.pt · Empresa)`), Caixa Geral marcada pelo backend (`is_caixa_geral`) e Caixa de Indexação quando `has_shared_indexacao` (cargo indexacao em **qualquer** perfil). O valor seleccionado flui para o param `mailbox` da API — nunca filtrar caixas no frontend por role activo.
- Abrir ficheiros/anexos: **sempre** novo separador — `window.open("", "_blank")` síncrono no gesto de clique (antes de qualquer `await`, senão o popup blocker come o pedido), navegação para o blob URL quando o fetch resolve, `URL.revokeObjectURL` adiado (~60s) para o separador ter tempo de renderizar. Ver `handleDownloadAttachment` no `WebmailPage`.
- Abrir o email em novo separador: link nativo `/webmail?folder=<pasta>&mailbox=<caixa>&id=<id>` — a página honra `?mailbox=` (selecciona a caixa) e `?id=` (abre o painel de leitura; `?folder=drafts&id=` continua a abrir o compositor — Pacote DM).







## 15. Undo Send e Toggle "Indexado" (Pacote 9)

### Envio de email = toast "Email a ser enviado..." com Desfazer

O backend (Pacote 9) agenda o envio real após a janela de undo (`POST /api/emails/send` devolve `{queued: true, send_id, undo_window_seconds}` em vez de enviar de imediato). O frontend NUNCA assume envio imediato na resposta OK:

- **Parse da resposta com `parseSendResponse`** (`utils/webmailSendQueue.js` — helpers puros, testáveis com `node --test`): normaliza `queued`/`send_id`/`undo_window_ms` e tolera respostas legacy/inválidas (devolve `queued: false` → caminho de envio imediato).
- **UX canónica (Gmail-like)**: ao clicar "Enviar", o composer **fecha**; surge `toast.success("Email a ser enviado...", { duration: undoWindowMs, action: { label: "Desfazer", onClick: cancelSend } })`. O botão "Desfazer" chama `POST /api/emails/{send_id}/cancel-send` (mesmos headers de contexto: `Authorization` + `X-Company-Id`/`X-Active-Role` via `webmailHeaders()`).
- **Undo repõe o modo de edição**: antes do fetch de envio, guardar um snapshot (`buildComposerSnapshot`) do `composerData` + `uploadAttachments`; no cancel, repor o snapshot (ou o `draft` devolvido pelo backend, convertido com `draftToComposerFields`), reabrir o composer (`setComposerOpen(true)`) e `toast.success("Envio cancelado — pode continuar a editar o rascunho.")`. Os anexos temp continuam válidos (o backend só os move no envio real).
- **Após a janela (sem undo)**: `setTimeout` ligeiramente depois da janela confirma visualmente ("Email enviado com sucesso") e faz `handleRefresh()` (invalidação `queryKeys.emails.webmailAll()`).
- Padrão aplicado nos DOIS pontos de envio do Webmail: `WebmailPage.jsx::handleSendEmail` (composer) e `EmailViewerModal.js::sendReply` (resposta rápida — no undo, reabre a caixa de resposta com o texto intacto).
- Nunca duplicar a lógica de undo inline: extrair sempre para `utils/` (puro, sem JSX) e testar com `node --test`.

### Toggle "Indexado" no header dos Detalhes do Processo

- Switch shadcn (`components/ui/switch`) + `Label` no bloco `actions` do `PageHeader`, com `data-testid="indexed-toggle"`; `checked={!!process?.is_indexed}`.
- **Visibilidade**: apenas perfis de gestão/indexação — `INDEX_TOGGLE_ROLES = ["indexacao", "admin", "ceo"]` (a mesma regra do backend `assert_mark_indexed_permission`), avaliada com `effectiveRole` (perfil ACTIVO) e fallback `hasAnyRole(user, ...)` (padrão do Kanban — ver `ProcessDetailsModal`). Não usar apenas `user.role` (primário do JWT): multi-perfis ficariam sem o toggle.
- **Acção**: `setProcessIndexed(processId, isIndexed)` (`services/api.js`) → `POST /processes/{id}/set-indexed {"is_indexed": bool}`. Optimistic update local (`setProcess`) + rollback em erro + `fetchData()` (invalida o bundle de queries do processo). O ON notifica a equipa (fluxo canónico do mark-indexed no backend); o OFF reverte o flag sem mexer na fase.
- Estado ocupado: `indexToggleBusy` desactiva o Switch e troca o label por um `Loader2` spinner — feedback imediato, sem cliques duplos.

## 16. Prevenção de duplicados, badge de email falhado e monitor "Processos em Segundo Plano" (Pacote 10)

### Erro 409 de cliente duplicado — alerta visual BLOQUEANTE

O backend devolve `409` com `detail` ESTRUTURADO (`{message, existing_client_id, existing_client_name, matched_fields}`). O contrato no frontend:

- **Nunca** fazer parse ad-hoc do 409 nos componentes: usar `utils/duplicateClient.js` (`parseDuplicateClientError(err)` → `{message, existing_client_id, existing_client_name, matched_fields}` | null; `isDuplicateClientError`; `duplicateFieldLabel`). Reconhece também o 400 legacy (string "Já existe um cliente…") para robustez de rollout.
- **Banner bloqueante partilhado**: `components/shared/DuplicateClientAlert.jsx` (banner vermelho `role="alert"` com ícone `AlertTriangle`, nome do cliente existente, campo(s) em conflito e acção "Usar cliente existente" quando aplicável). Nunca desenhar o alerta inline duplicado — sempre este componente.
- **Integração canónica** (CreateClientModal, CreateProcessModal, SecondTitularCard):
  1. chamar `createClient(payload, { skipErrorToast: true })` — o 409 é tratado pelo FORMULÁRIO (banner persistente), não pelo toast genérico do interceptor (evita dupla notificação);
  2. no catch: `const dup = parseDuplicateClientError(err); if (dup) { setDuplicateError(dup); return; }` — só erros não-duplicados vão para toast;
  3. **bloquear a submissão** enquanto `duplicateError` está activo (`canSubmit`/`disabled` — impede clique-clique-clique); alterar NIF/Email **limpa o estado** (onChange);
  4. acção "Usar cliente existente": selecciona `{id, nome}` sintético via `handleSelectExistingClient`/`handleSelectClient` + `setClientMode('existing')` e limpa o erro. Em `clientOnly` o banner NÃO oferece a acção (não há processo).
- `services/api.js`: o interceptor de response deriva `errorMessage` com `extractErrorMessage` (o detail pode ser OBJECTO — passar objectos ao `description` do sonner rebenta o render); o ramo 400+ respeita `config.skipErrorToast` (mesma flag dos 500+); `createClient(data, config)` aceita config axios.

### Indicador de "Email de acesso não entregue"

- **Detalhes do Processo**: o card `ProcessAlerts` (GET `/alerts/process/{id}`) renderiza o novo alerta `portal_email_undelivered` (priority `critical`) automaticamente — ícone `MailWarning` no mapa `alertIcons`. NÃO reinventar badge no header quando o alerta já vive no card.
- **Listas de clientes**: pílula vermelha `MailWarning + "Email de acesso não entregue"` condicionada a `client.portal_email_delivery?.status === "failed"` (campo novo devolvido pelo GET /clients; MyClientsPage usa acesso defensivo — a vista agregada pode não incluir o campo). Cores canónicas de erro: `bg-red-50 dark:bg-red-950/30 text-red-700 dark:text-red-300 border-red-300 dark:border-red-800`. O `title` do badge mostra o erro da entrega.

### Widget global "Processos em Segundo Plano" (topbar)

- **Não criar widgets novos**: o `TasksDropdown` (Sheet ao lado das notificações) É o monitor global — renomeado e evoluído. Fonte única: `TasksContext` (polling 5s/30s + circuit breaker sobre `GET /tasks/active`, que agora agrega task_logs + background_jobs no backend).
- Grupos do painel: **Em Execução** (pending/processing, spinner), **Falhadas recentes** (failed !ack — grupo próprio vermelho, o sinal de "precisa de atenção"), **Concluídas** (completed !ack). O trigger troca o ícone: `Loader2` (a executar) → `AlertTriangle` vermelho (só falhadas) → `Activity`.
- `failedCount` derivado no `TasksContext` (novo campo do contexto) — não recalcular nos consumidores.
- Novos task_types visíveis sem alteração do frontend: `EMAIL_SEND` (fila Undo Send + email de acesso ao Portal) e `DOCUMENT_UPLOAD` (upload confirmado) — os ícones/labels já estavam mapeados em `TaskTypeIcons`/`TaskTypeLabels`.
- Acknowledge/Cancel do frontend continuam a chamar `/tasks/{id}/acknowledge` e `/tasks/{id}/cancel` — o backend roteia por prefixo `task_` (task_logs) vs uuid (background_jobs); zero mudanças nos consumidores.

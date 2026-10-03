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

### O `file_key` do upload é do SERVIDOR, e a resposta do `confirm-upload` não traz URL (Incidente P0, Set 2026)

O upload do Portal é presigned (client → S3 directo) e **isso mantém-se**, mas o contrato mudou em dois pontos que o frontend tem de respeitar:

- **O `file_key` a enviar no `confirm-upload` é, sem excepção, o que veio no `upload-url`.** O `confirm-upload` valida-o agora contra o prefixo S3 do processo/cliente e devolve **403** a qualquer outro. Não construir, derivar, concatenar nem "corrigir" a chave no cliente — um `file_key` calculado no browser é indistinguível de um ataque e vai ser recusado. O `ClientPortal.jsx` já faz o correcto (`const { upload_url, file_key } = await urlRes.json()` e devolve esse `file_key` tal e qual).
- **A resposta do `confirm-upload` já não traz `temporary_url`.** Era um URL pré-assinado de *leitura* devolvido no mesmo pedido que nomeava a chave — a carga útil de uma vulnerabilidade de path traversal. O campo nunca foi lido pelo Portal (o `doUpload` devolve só `{ success, filename }`), pelo que nada quebrou; **não o reintroduzir**. Se um ecrã precisar de mostrar o ficheiro logo após o upload, o caminho é `GET /portal/download-url?file_key=…`, que verifica a posse antes de assinar.

Os três endpoints do Portal passaram também a ter limite de pedidos (`20/minute` nos de upload, `60/minute` no download). Um lote grande de ficheiros pode por isso apanhar **429** — o tratamento de erro do upload tem de mostrar o `detail` da resposta em vez de assumir falha de rede, e nunca fazer *retry* imediato em ciclo (é o comportamento que o limite existe para travar). Detalhes e diagnóstico completo em `ARCHITECTURE.md` → "Incidente P0 — o `file_key` do Portal do Cliente não era de confiança".

### O `confirm-upload` do Portal pode agora recusar o ficheiro (quarentena, Set 2026)

Os bytes passaram a ser validados **depois** de chegarem ao S3 (`HEAD` + `Range` de 2 KB → magic bytes). O upload pré-assinado mantém-se exactamente como está, mas o passo 3 do fluxo deixou de ser uma formalidade e o tratamento de erro tem de acompanhar:

- **400** — o ficheiro foi recusado e **já foi apagado do S3**. O `detail` traz a razão em português (formato não permitido, demasiado grande, vazio) e é o que se mostra ao cliente. Não vale a pena repetir o pedido: o objecto já não existe. Reenviar significa recomeçar do passo 1 (`/upload-url`).
- **503** — não foi possível **verificar** o ficheiro (S3 em baixo). O objecto **continua lá** e a confirmação pode ser repetida tal e qual. É o único caso em que faz sentido oferecer "tentar novamente" sobre o mesmo `file_key`.
- **429** — limite de pedidos (ver acima). Mostrar o `detail`, nunca fazer *retry* imediato em ciclo.

Distinguir 400 de 503 no `catch` é o que separa "o teu ficheiro não serve" de "tenta outra vez dentro de um minuto" — e dizer a primeira coisa quando a verdade é a segunda faz o cliente desistir de um upload que estava bom.

#### O que NÃO se faz com o evento `portal_message`

**Não inserir o payload na lista de mensagens.** O servidor trunca o conteúdo a 200 caracteres (`content[:200]`): inserido como registo, uma mensagem longa fica truncada no ecrã **para sempre**, até um refetch acidental. O evento é um **sinal** — quem tem a verdade é o `GET /portal/messages`.

É deliberadamente diferente do `utils/webmailRealtime.js`, que insere a linha **sem** GET. Lá o evento transporta o registo completo; aqui não. A diferença está no payload, não na preferência — e é por isso que está escrita nos dois sítios.

**Não filtrar o eco por `sender_type`.** O cliente recebe a sua própria mensagem de volta (o `portal_client_messages` difunde sem `exclude_user_id`, ao contrário do caminho do staff). O reflexo de ignorar `sender_type === "client"` parece certo e está errado: um processo pode ter **dois titulares** com magic links próprios, ambos `client`, e esse filtro fazia o titular 2 deixar de ver as mensagens do titular 1 — com o polling parado, silenciosamente. A desduplicação é por **id da mensagem**: a minha já está na lista (o POST refez o fetch), a do meu co-titular não.

O `file_size` e o `content_type` que o cliente envia no `confirm-upload` continuam a ser aceites no corpo por retrocompatibilidade, mas **são ignorados**: o que fica gravado é o que o S3 e os magic bytes dizem. Não construir UI que assuma que o tipo declarado é o que ficou (um `.pdf` que é na verdade um PNG aparecerá como `image/png` na lista de documentos, e está correcto).

### O Portal tem WebSocket próprio: `/api/ws/portal` (Set 2026)

**Ligado** desde a iteração `ws-portal-ui`: `hooks/usePortalRealtime.js` (a ligação) + `utils/portalRealtime.js` (a decisão, pura e testada), consumidos pelo `ClientPortal`. Estas são as regras do contrato, e nenhuma é negociável do lado do cliente:

- **Endpoint próprio.** `/api/ws/portal?token=<magic token do Portal>` — **não** o `/api/ws/notifications` da equipa, que recusa tokens de Portal com o código de fecho `4002`. O token é o mesmo que o Portal já usa nas chamadas REST (`getPortalToken()`).
- **Não enviar `join_process_room`.** A sala é derivada do token **no servidor** e um pedido de sala é ignorado e registado como sondagem. Não há nada a subscrever: a ligação já está na sala do processo do cliente.
- **A única mensagem a enviar é `{"type":"ping"}`**, de 30 em 30s — é ela que renova a presença. Tudo o mais é descartado em silêncio.
- **Dois eventos, e só dois:** `portal_message` (mensagem do consultor) e `portal_gov_progress` (`{process_id, source, estado, documents_count}` no sucesso; `{process_id, source, estado:"falhou", motivo}` na falha, onde `motivo` ∈ `credenciais_invalidas` / `confirmacao_necessaria` / `confirmacao_expirada` / `confirmacao_incorreta` / `indisponivel`). Qualquer outro evento da sala do processo é retido no servidor por uma lista de permissão — **não** escrever handlers para eventos internos (`process_updated`, `document_uploaded`, …): eles nunca chegam, e um handler para eles é código morto que sugere que chegam.
- **Códigos de fecho:** `4001` sessão expirada (pedir novo magic link), `4002` acesso inválido. Em ambos, **não** reconectar em ciclo.
- **O polling FICA como recurso** — a regra do Épico 10: para quando `isConnected`, retoma quando o WS cai. Apagá-lo deixa o Portal sem mensagens quando o WebSocket não liga.

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

## 17. UX Masterclass — dropdowns dinâmicas, tipografia de email, navegação e soft-delete (Pacote 11)

### Dropdown de estado: 100% dinâmica (Strict No-Hardcoding)

- `utils/workflowStatuses.js` — a lista estática `KNOWN_PROCESS_STATUSES` foi **REMOVIDA**. `buildStatusOptions(workflowStatuses, currentStatus)` usa apenas a lista da API `/admin/workflow-statuses`; quando o `status` actual não vem na lista (API falhou / fase removida pelo admin), injecta-o como opção única `_isFallback` com `formatStatusLabel` — **nunca** acrescentar fases cravadas em código a um select/badge/dropdown. `formatStatusLabel` continua disponível para labels.
- Fonte única de verdade: a colecção `workflow_statuses` (a mesma do Kanban). Se um agrupamento semântico for preciso no futuro (ex.: funnels de dashboard), expor do backend (flags na colecção), nunca listas frontend.

### EmailViewerModal — tipografia do corpo (prose)

- O corpo do email (HTML sanitizado OU texto simples) renderiza SEMPRE no div `.email-content` dentro do container `prose prose-sm dark:prose-invert`. Os estilos vivem em `src/index.css` (secção "PACOTE 11"): parágrafos com `margin`, `line-height 1.7`, listas/headings/tables/blockquote/pre formatados, `word-break`.
- Texto simples é convertido em `<p>` reais por `buildPlainTextEmailHtml` (bloco `\n\n` → parágrafo; `\n` → `<br/>`; escape de HTML) — o `<pre>` denso monospace está PROIBIDO para corpos de email. Sanitização de HTML continua a cargo de `utils/sanitize.js::sanitizeEmailHtml`.

### Navegação e ficha de processos

- **Nome do cliente clicável**: no `ProcessDetails` (header, `PageHeader` description) e no `ClientContextCard` (ContactLine "Titular") o nome navega para `/cliente/:id` (react-router `Link`). O ID resolve por `clientData?.id || clientId || process?.client_id`. ContactLine ganhou props `internalLink`/`title` — links externos (mailto/tel) mantêm `<a>`.
- **Aviso de permissões de Documentos LOCALIZADO à tab**: o `S3FileManager` captura o 403 do `GET /documents/client/{id}/files` (guard `assert_can_view_process_documents`) num estado `permissionDenied` e renderiza um Card âmbar próprio (`data-testid="s3-file-manager-permission-denied"`) com "Tentar novamente" — SEM toast global e SEM bloquear a vista do processo. O guard 403 do processo em si (página inteira) mantém-se — é de processo, não de documentos.
- **Dicionário de enums `fonte`**: usar `utils/fonteLabels.js::formatFonteLabel(fonte)` (nunca mostrar `client.fonte` cru). Mapeia os valores técnicos do backend (`staff_created`, `public_form`, `auto_created`, `segundo_titular`, ...) e legados (Manual/Website/trello/...) para PT-PT; valores desconhecidos são humanizados. Aplicado em ClientsPage (badge + Excel), MyClientsPage (Excel), ClientDetailPage e ClientDetailsModal.
- **Cards de contas Webmail clicáveis** (`EmailAccountsCard.jsx`): o `<li>` tem `role="button"`, `tabIndex`, handler Enter/Espaço e `onClick → openEdit(account)` (Caixa Geral excluída); botões internos usam `e.stopPropagation()` para não disparar a edição ao remover/definir principal.

### Protecção Soft-Delete + Banner de Restauro (ProcessDetails e ClientDetailPage)

- Derivar SEMPRE um flag de eliminação e usá-lo em TODOS os inputs/botões de edição: `isDeletedProcess` (`process.is_deleted || process.deleted || status eliminado(s)`) em ProcessDetails; `isDeletedClient` em ClientDetailPage. Em ProcessDetails força `isViewMode` (read-only sem excepção de role) e alimenta `isInactiveProcess` (botões de acção disabled). Em ClientDetailPage desactiva o botão "Editar Cliente", as `ContactRow` inline (`editable={!isDeletedClient}`), os inputs do modal e o Guardar (com guard extra no `handleEditSave` — nunca gravar num registo eliminado).
- **Banner de restauro no topo** (vermelho, `role="alert"`, ícone `Trash2` + botão `RotateCcw "Restaurar"` com spinner próprio): ProcessDetails → `restoreProcess(id)` (api.js, já existia); ClientDetailPage → `restoreClient(id)` (NOVO em api.js → `POST /clients/{id}/restore`). Após sucesso: toast + refetch (`fetchData()`/`fetchClientData()`). O banner de estado terminal (âmbar) do ProcessDetails fica oculto quando o de eliminado está visível (evita dupla advertência).

## 18. Bug Squash & UX Polish — unmount, undo send, duplicados e webmail (Pacote 12)

### Fetches internos + cleanup (anti-ecrã-branco)

- Todo fetch interno de página que faz setState depois de `await` DEVE aceitar `AbortSignal` (ou guard `isMountedRef`), e o effect dono cria `AbortController` com `return () => controller.abort()`. setState só quando `!signal?.aborted`. Padrão de referência: `ProcessDetails.js::fetchRgpdStatus` (effect `[id]`) e `VisitasTab.jsx::fetchVisitasProperties`. Abortos são silenciados no `catch` (não são erros do utilizador). Chamadas pontuais de refresh continuam a funcionar sem signal.

### Soft-delete do CLIENTE também bloqueia edição de processos

- `ProcessDetails.js` deriva `isDeletedClient` (bundle do cliente: `is_deleted`/`deleted`/status eliminado) e dobra-o em `isViewMode` E `isInactiveProcess` — um processo ACTIVO cujo cliente está eliminado deixa de ser editável (espelho do `isDeletedProcess`).
- `kanban/ProcessDetailsModal.jsx`: `isDeletedRecord` (processo OU cliente) desabilita o botão Editar (com `title` explicativo) e `handleSave` faz early-return com `toast.error` PT antes de qualquer `updateClient`/`updateProcess`. Regra: **nunca gravar num registo eliminado**, independentemente da permissão.

### Undo Send — toast de sucesso condicional

- O timer pós-janela de undo (confirmação "enviado com sucesso" + limpeza de anexos + refresh) vive num `useRef` (`sendConfirmTimerRef`) e é SEMPRE cancelado (`clearTimeout`) no sucesso do Desfazer. Um envio desfeito nunca mostra toast de sucesso nem apaga o snapshot de anexos restaurado. Padrão duplicado: `WebmailPage.jsx` (handleSend/cancelSend) e `EmailViewerModal.js` (cancelReplySend).

### 409 de duplicados — headline granular NIF vs Email

- `utils/duplicateClient.js::parseDuplicateClientError` constrói a mensagem do utilizador a partir de `matched_fields` + `existing_client_name` ("Já existe um cliente com este NIF: X" / "…este Email: X" / "…este NIF e este Email: X") — NUNCA propagar a string genérica do backend ("NIF ou Email"). O banner bloqueante `DuplicateClientAlert` mantém a sub-linha por campo e a acção "Usar cliente existente".

### Webmail — BCC, assinatura e chips de anexos

- Compositor (`WebmailPage.jsx`): campo **BCC** collapsible espelhando exactamente o padrão do CC (estado `bcc_emails` string; expande automaticamente quando há valor); payload constrói `bccList` como o `ccList`; o draft do cancel-send restaura o BCC via `utils/webmailSendQueue.js::draftToComposerFields`.
- Chips de anexos: ler `file.filename || file.file_name` e `file.size ?? file.file_size` (contrato real da resposta do `POST /emails/attachments/upload`).
- Pré-preenchimento: `/webmail?compose=new&to=<email>&process_id=<id>` abre o compositor com prefill UMA única vez (guard: `compose === "new" && !draftIdFromUrl`; não colide com o effect de abrir rascunhos). Usado pelo botão "+ Novo" da tab Emails (`processDetails/tabs/EmailsTab.jsx`) — destinatário = email do cliente, processo associado (tag `[Proc-{id}]` + histórico).

### Tab Emails — semântica estrita

- O backend filtra ESTRITAMENTE por `process_id` (emails não associados deixaram de ser agregados por endereço de participante). Subtítulo/UI da tab deve reflectir apenas "emails associados a este processo" — não documentar lógica de participante.

### Vista rápida de cliente (ClientRegistrationsPage)

- O detailsDialog da lista de registos NÃO tem botão "Adicionar Processo" (removido no P12 — o fluxo de criação fica no botão de linha "Criar Processo", que pré-selecciona o cliente). Não reintroduzir ações de criação dentro de quick-views.

## 19. URL do backend e testes unitários no CI (Set 2026)

### URL do backend — importar, nunca repetir

```js
// ❌ ERRADO — repete o literal e, sem a variável, fala com PRODUÇÃO a partir de dev
const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || "https://powercell.onrender.com";

// ✅ CORRECTO — ponto único, com a regra dev/prod já aplicada
import { BACKEND_URL, API_BASE_URL } from "@/utils/apiBaseUrl"; // ou caminho relativo
```

- `BACKEND_URL` → raiz do backend; `API_BASE_URL` → `BACKEND_URL + "/api"` (o que a maioria dos módulos quer).
- Um host local sem `REACT_APP_BACKEND_URL` resolve para `http://localhost:8001` — **nunca** para produção. A regra completa está em `ARCHITECTURE.md` › "Isolamento dev/prod".
- Em dev, definir `REACT_APP_BACKEND_URL` em `frontend/.env` (ver `.env.example`). O `vite build` anuncia sempre o URL embebido no bundle; se aparecer um aviso `⚠️ REACT_APP_BACKEND_URL não definido`, a variável está em falta no ambiente.
- Os módulos que ainda lêem `process.env.REACT_APP_BACKEND_URL` directamente continuam a funcionar (o Vite injecta o valor já resolvido), mas código novo usa o import.

### Testes unitários — `yarn test` e bloqueantes no CI

- `yarn test` corre todos os `src/**/*.test.js(x)` com `node --test`, sem dependências extra. `yarn test <filtro>` limita por substring do caminho (ex.: `yarn test utils`).
- A enumeração dos ficheiros vive em `scripts/run-unit-tests.mjs` — os globs do `node --test` só existem no Node 22 e o CI corre Node 20.
- **O job "Frontend CI" corre `yarn test` e falha o pipeline.** Até Set 2026 nenhum job corria estes testes: existiam ~240 e uma regressão em `src/utils` passava despercebida até produção.
- Assertivas em **`node:assert/strict`** com `describe`/`it` importados de `node:test`. Não usar a API `expect(...)` do Jest: o projecto não tem Jest nem Vitest instalados — três ficheiros escritos assim (`pages/processDetails/*.test.js`) nunca chegaram a correr e só foram recuperados quando convertidos.
- Imports em ficheiros de teste levam **extensão explícita** (`from "./x.js"`): o ESM puro do Node não resolve extensões omitidas, ao contrário do bundler.

## 20. Vitest + React Testing Library e a divisão do Webmail (Épico 6, Set 2026)

### Motor de testes

- `yarn test` (uma vez), `yarn test:watch`, `yarn test:coverage`. O CI corre `yarn test` e falha o pipeline.
- Configuração em `vite.config.js`, bloco `test`. Vive lá e não num `vitest.config.js` separado para herdar o que os testes precisam e o build já define: o alias `@`, o `define` do `process.env` e o **loader JSX para ficheiros `.js`** (este projecto tem JSX dentro de `.js`, herança do CRA).
- Os testes antigos de utilitários continuam a importar `describe`/`it` de `node:test`: um alias (`src/test/nodeTestShim.js`) traduz isso para a API do Vitest. **Código novo importa directamente de `vitest`.**
- `src/test/setup.js` liga os matchers do `jest-dom`, faz `cleanup()` entre testes e preenche o que o jsdom não traz (`matchMedia`, `ResizeObserver`, `scrollIntoView`).

### Escrever um teste de componente

```jsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
```

- Consultar por **papel e nome acessível** (`getByRole("button", { name: "Limpar pasta" })`), não por classe CSS. Um botão sem nome acessível é um bug de acessibilidade **e** um teste impossível de escrever — dar-lhe `aria-label`.
- Componentes que usam `Tooltip` têm de ser montados dentro de um `<TooltipProvider>`; os testes do Webmail fazem-no num `wrapper`.
- **Um teste que possa passar sem provar nada é pior do que não existir.** Nada de `if (mock.calls.length) expect(...)`. Se o alvo é difícil de encontrar, o problema está no componente.
- Confirmar que o teste tem dentes: partir de propósito o que ele afirma e ver vermelho.

### Página/Contentor vs componentes de apresentação

O `WebmailPage.jsx` é o **Contentor**: detém o estado, os hooks (`useWebmailEmails`, `useNewEmailRealtime`), os efeitos e os handlers. Os componentes em `components/webmail/` são de **apresentação**:

| Componente | Responsabilidade |
| --- | --- |
| `FolderNavigation.jsx` | Caixas, pastas, marcadores e pastas personalizadas |
| `EmailList.jsx` | Lista de conversas (recebe as threads JÁ agrupadas) |
| `EmailThreadViewer.jsx` | Leitura da mensagem (recebe o HTML JÁ sanitizado) |
| `EmailComposer.jsx` | Compositor (controlado: `onFieldChange(campo, valor)`) |
| `webmailFormatters.js` | Data, tamanho de ficheiro e ícone de anexo |

Regras para quem continuar o trabalho:

1. **Props explícitas, nunca `{...props}`.** O contrato está em JSDoc no topo de cada componente.
2. **Nada de `set*` dentro de um componente de apresentação.** O componente diz o que aconteceu (`onSelectFolder(id)`); o contentor decide o que isso implica. Um `onClick` com quatro setters encadeados é lógica de página disfarçada de UI.
3. **O tempo real não atravessa a fronteira.** O agrupamento em conversas, o WebSocket e a suspensão do polling ficam no contentor — os componentes só vêem o resultado.
4. **Canalização de DOM fica no componente.** O `input` escondido do upload, o clique na zona e o arrastar-largar vivem no `EmailComposer`; o contentor recebe `File[]`.
5. Ao extrair, limpar os imports que ficam órfãos na página e confirmar com `npx eslint <ficheiro>` (o `--quiet` não mostra `no-unused-vars`, que é aviso).

### `react/jsx-no-undef` é bloqueante

Um componente ou ícone usado em JSX sem import **não** era apanhado: o `no-undef` não cobre JSX e a regra estava desligada. A regra é agora `error` — foi activada depois de um `<Loader2 />` sem import passar no CI e só rebentar no clique de transferir um anexo. Apanhou logo mais 15 casos reais no código existente.

## 21. Nota de voz do consultor (Épico 7, Set 2026)

**Onde vive.** Botão **Nota de voz** no separador *Histórico* do processo,
ao lado de *Registar Atividade*. Progressive Disclosure: o ecrã normal tem
um botão; o gravador só existe dentro do `Dialog`.

**Três peças, três responsabilidades.**

| Ficheiro | O que faz | O que NÃO faz |
|---|---|---|
| `utils/voiceNote.js` | Decisões puras: formato a pedir, limites, validação, cronómetro, mensagens | Tocar no browser |
| `hooks/useAudioRecorder.js` | `getUserMedia`, `MediaRecorder`, libertar o microfone | Decidir formatos ou validar |
| `components/processDetails/VoiceNoteRecorder.jsx` | Renderizar os estados e entregar o ficheiro por `onEnviar(File)` | Chamar a API, saber o que é um processo |

O estado (diálogo aberto, upload em curso, tarefa em curso) e a chamada à
API vivem no contentor `ProcessDetails`. O componente diz o que aconteceu;
o contentor decide o que isso implica — a mesma regra do § 20.

**Os quatro estados visíveis:** repouso → *A gravar...* (cronómetro, com
aviso a 30 s do limite) → pré-escuta (`<audio controls>`, enviar ou
descartar) → *A enviar...*; e, depois do upload, *A processar Inteligência
Artificial...*, ligado aos eventos `task_*` e não a um temporizador.

**Gravar pode simplesmente não ser possível.** Safari antigo sem
`MediaRecorder`, permissão recusada, browser sem formato compatível, página
fora de HTTPS. Em qualquer destes casos o componente **oferece o upload de
ficheiro** e explica porquê — nunca mostra um botão que não faz nada.

**O microfone é sempre libertado.** Cada faixa do `MediaStream` é parada ao
terminar, ao cancelar e ao desmontar. Sem isso, o indicador de gravação do
browser fica aceso depois de o diálogo fechar e o utilizador julga — com
razão — que continua a ser ouvido. Há dois testes só sobre isto.

**A URL de pré-escuta é revogada.** `URL.createObjectURL` sem
`revokeObjectURL` deixa o áudio inteiro em memória até ao refresh.

**Upload pelo `api` do Axios, nunca por `fetch`.** Regra geral do projecto
(incidente 2026-09-21): só o interceptor injecta o token e os cabeçalhos de
empresa/papel.

**O evento é filtrado antes de invalidar.** `eNotaDeVozDoProcesso(payload,
id)` exige `task_type === "VOICE_NOTE"` **e** o `process_id` desta página.
Sem o filtro, qualquer tarefa de fundo do CRM (importação Excel, análise em
massa, geração de PDF) recarregaria a página de detalhes do processo.

**Limites iguais aos do backend** (25 MB, 5 minutos): rejeitar cedo poupa ao
consultor um upload de 20 MB para receber um 413 no fim.

**Testar APIs de media:** falsear `MediaRecorder`, `getUserMedia` e
`createObjectURL` — os três — e deixar o hook e o componente reais. Falsear
o hook deixaria a integração por testar, que é precisamente onde estão os
bugs.

## 22. Extrair de ficheiros grandes: medir antes de cortar (Épico 8, Set 2026)

**A regra.** Um bloco de JSX grande não é, por si, candidato a extracção. O
que decide é **quantos símbolos do contentor ele usa**. Antes de mover uma
linha, conta-os:

```bash
# Identificadores do bloco que são declarações do contentor
python3 - <<'PY'
import re
linhas = open("pages/ProcessDetails.js").read().split("\n")
corpo = "\n".join(linhas[:INICIO_DO_JSX])
declarados = set(re.findall(r"const\s+(\w+)\s*=", corpo))
for a, b in re.findall(r"const\s+\[\s*(\w+)\s*,\s*(\w+)\s*\]", corpo):
    declarados |= {a, b}
bloco = "\n".join(linhas[INICIO:FIM])
print(sorted(set(re.findall(r"\b([a-zA-Z_]\w*)\b", bloco)) & declarados))
PY
```

**O limiar, por experiência deste épico:**

| Símbolos | Decisão |
|---|---|
| ≤ 10 | Extrair. Contrato legível, JSDoc cabe num parágrafo. |
| 10 – 25 | Extrair **se** os símbolos formarem famílias coesas que se possam agrupar (`dragHandlers`, `fileActions`). |
| > 25 | Não extrair sem redesenhar. Um componente com 50 props não é um contrato, é um borrão. |

**O caso a não repetir:** as ~230 linhas de cola do separador Resumo do
`ProcessDetails` usam **55** símbolos do contentor e não fazem nada além de
passar props aos separadores que já estão extraídos. Envolvê-las produziria
prop-drilling com nome novo. Ficaram onde estão, e está escrito porquê.

**Ordem de trabalho, sem excepção:**
1. Teste que monta o ecrã inteiro (só fronteiras de rede/sessão falsas);
2. medir as superfícies;
3. cortar do menor risco para o maior, **um commit por peça**, com a suite
   verde entre cada;
4. teste de componente para cada peça extraída;
5. mutação, para provar que os testes novos têm dentes.

**Porque é que o passo 1 não é opcional.** Neste épico, o teste da página
montada apanhou, no primeiro arranque, um bug que estava em produção
(revisitar um processo dentro de 60 s deixava a página presa no esqueleto)
e, minutos depois, uma extracção que apanhara a `TabsList` errada — a
exterior, de Resumo/Documentos/Histórico, porque a classe
`grid w-full grid-cols-3` casa com duas listas diferentes. Seis testes
ficaram vermelhos de imediato; sem eles, os separadores de topo chegavam a
produção trocados.

**O que muda de dono na extracção.** Um `set*` do contentor dentro da UI é
sinal de fronteira mal posta: `setTitularChoiceDialog(prev => …)` que
reconstruía a lista de escolhas passou a `onChoose(indice, escolha)`; o
`toast.success` do "Confirmar Todos" passou para o contentor, que é quem
sabe que há alterações por gravar.

**Armadilhas de JSDoc.** Documentação errada é pior do que nenhuma. Neste
épico escrevi duas vezes contratos que não correspondiam ao código
(`onResolve(indice, decisao)` quando a assinatura é `(accao, nomeProprio)`;
`filename` quando o campo é `original_filename`). Ambas foram apanhadas por
testes — escrever o teste a partir da JSDoc, e não do código, é o que as
expõe.

**Ícones deixam de vir de borla.** `react/jsx-no-undef` (§ 21 e AGENTS.md)
apanha o que a extracção destapa: dentro de um ficheiro de 4000 linhas, um
`<AlertCircle />` herdava o import de um vizinho; sozinho num ficheiro novo,
falha logo.

---

## 23. A IA propõe, o utilizador dispõe (Épico 9, Set 2026)

Sempre que um modelo lê dados **pessoais ou financeiros** de um documento e
esses dados se destinam à ficha de um cliente, vale uma regra sem excepções:

> **Nada é escrito — nem no formulário, nem na base de dados — antes de um
> clique explícito de confirmação.**

Não é uma norma de UX, é de segurança de dados: um modelo de visão que leia
mal um dígito de um NIF ou uma casa decimal de um vencimento produz um erro
plausível, que ninguém detecta a olho, num campo que alimenta decisões de
crédito.

### O padrão

1. **O componente que lê não grava.** `S3FileManager` chama o endpoint de
   extracção e entrega o resultado ao contentor por callback
   (`onDocumentDataExtracted`). Se alguma vez chamar `ai-apply-suggestions`,
   a regra caiu — há um teste a prová-lo.
2. **A decisão vive numa função pura.**
   `utils/documentExtraction.prepararRevisaoDaExtraccao` separa o que foi
   lido em conflitos e campos a preencher. Dentro de um componente de 2900
   linhas esta decisão não se testa; fora dele, testa-se com 17 casos.
3. **O diálogo abre sempre.** Mesmo sem conflitos — "sem conflitos" quer
   dizer que a ficha está vazia e que **tudo** vai entrar. Mostrar só os
   conflitos faria o consultor confirmar às cegas o resto.
4. **Fechar não é confirmar.** Desistir descarta o que estava pendente.
   Guardá-lo faria a confirmação seguinte escrever dados de um documento já
   rejeitado.

### Estender um diálogo existente em vez de criar outro

`AIReviewDialog` já fazia o lado-a-lado "Actual ↔ Extraído" para a análise
em lote. Ganhou duas props **opcionais** — `newValues` e `sourceDocument` —
e o caminho antigo continuou a funcionar sem uma linha alterada (os seus 17
testes ficaram intactos). Criar um `VLMReviewDialog` paralelo teria dado
dois diálogos a fazer o mesmo, que é o que `AGENTS.md` proíbe em "Canonical
only. No duplicate UI".

Quando um diálogo novo parecer inevitável, a pergunta certa é: **que props
opcionais faltam ao que já existe?**

### Só oferecer o botão quando a acção é possível

A extracção aceita imagens e PDF. Um `.docx` com botão seguiria para uma
chamada **paga** e voltaria vazio. O `podeExtrairDados(nome)` decide pela
extensão e o botão simplesmente não aparece — dizer que não dá depois de
gastar dinheiro é a pior das ordens.

O mesmo vale para o papel: é uma ferramenta de gestão e olha para o
`effectiveRole` (perfil activo), nunca para o papel base (§ 20, AGENTS.md).

### Botões só de ícone precisam de `aria-label`

Os três botões de extracção (vista de lista, grelha "Todos", grelha por
categoria) levam `aria-label={`Extrair dados de ${file.name}`}`. Sem ele
não há nome acessível — é um bug de acessibilidade e um teste impossível
(§ 20). Com ele, o teste consulta por papel e nome, como deve.

## 24. A UI nunca é uma segunda verdade (Lote 5, P0, Set 2026)

Duas interceções críticas, o mesmo padrão: um ecrã que sabe mais do que o
motor lhe disse, ou que não diz o que sabe.

### 24.1 O silêncio não é um desfecho

Uma operação que o utilizador lançou **tem** de acabar em palavras. A análise
em lote de documentos tinha um quarto caminho — não abria o diálogo, não dava
erro, não dava aviso — e ficava indistinguível da aplicação avariada.

Regras:

- **`{}` é truthy.** `if (resposta.dados)` não prova que há dados. Quando o
  que interessa é haver CONTEÚDO, conta-se: `Object.keys(x).length > 0`.
- **Um `if` que decide se o utilizador vê alguma coisa precisa de `else`.**
  Um `return` sem mensagem, dentro de um componente grande, é invisível na
  revisão e invisível em produção.
- **Uma voz por evento.** Se o componente filho já celebrou, o pai não tem
  como desdizer: o verde fica no ecrã por cima do diálogo que não abriu.
  Quem sabe o desfecho é quem anuncia.
- **A decisão vive num módulo puro**, não no componente: `sucesso` / `aviso` /
  `erro` é testável (`utils/analiseEmLoteFeedback.js`), e um teste afirma que
  não há um quarto valor possível.

### 24.2 Contagens: dizer o que se está a contar

`documents_count` contava os documentos ENVIADOS e a UI lia-o como
"processados". Com a IA em baixo, "3 documento(s) processado(s)" era
literalmente falso. **Um número no ecrã tem de nomear o que mede**; quando
há dois números (enviados vs. lidos), a resposta traz os dois.

### 24.3 Mapeamentos: o motor manda, o alias é recurso

As fases vêm de `workflow_statuses` e são configuráveis. Um mapa de nomes
antigos cravado no frontend **só** se aplica quando o motor não conhece o
original **e** conhece o destino. Aplicá-lo sempre faz o ecrã reescrever uma
fase que existe mesmo — e nada dá erro.

Corolários:

- **Aplicar a normalização aos DOIS lados ou a nenhum.** Normalizar o estado
  actual e o histórico, mas não a lista de fases, garante que um dia deixam
  de casar.
- **`?.campo || 0` não distingue "zero" de "não existe".** Use-se `null` para
  o desconhecido: com 0, tudo o que vem depois parece futuro.
- **Um agrupamento que o motor não sabe fazer não se inventa.** Derivar
  macro-fases da `order` seria outra mentira, com ar automático. Os grupos
  ficam como classificação conhecida e o que não couber é DITO ("Outras
  fases"), nunca deitado fora. Há um teste a afirmar que a soma do gráfico é
  o total de itens.

### 24.4 Quando o texto procurado existe em dois sítios, a asserção nomeia o sítio

Terceira ocorrência do padrão "mutação perdida ≠ teste fraco". Um
`expect(cartão).toHaveTextContent("CPCV")` passava com a fase actual já
reescrita, porque "CPCV" também era etiqueta de um nó da timeline. A
asserção tem de apontar ao elemento cujo conteúdo a regra decide
(`data-testid="fase-actual"`), não ao contentor que por acaso o inclui.

## 25. Etiquetas e texto livre (Lote 5, Secção B, Set 2026)

### 25.1 Vários escritores, um leitor: juntar, não escolher

Quando o mesmo conceito tem mais do que um campo na base de dados —
porque foi crescendo — o leitor não pode escolher um. O texto livre do
processo vivia em `observation_notes`, `notes`/`observations` e
`ai_extracted_notes`, e o Resumo lia o primeiro "se não estiver vazio".
Bastava uma nota nova para o que tinha sido escrito noutro ecrã
desaparecer.

- **Juntar, deduplicar pelo valor normalizado, marcar a origem.** Nada
  desaparece, e quem lê sabe de onde veio cada coisa.
- **Marcar só as origens que surpreendem.** O caso normal não leva
  crachá; se tudo for marcado, nada está marcado.
- **Um campo escalar não se pré-preenche com o conteúdo de outro.** O
  modal do Kanban semeava a textarea de `notes` com a última nota do
  feed: gravar copiava a nota de outra pessoa, sem autor nem data.

### 25.2 Derivar em vez de guardar

A cor de uma etiqueta deriva do seu texto (hash → paleta de tokens
semânticos). A alternativa era uma colecção de definições de etiqueta ou
mudar o campo para objectos, migrando dados e projecções — para garantir
uma coisa que a derivação garante de graça: "VIP" é da mesma cor em todos
os ecrãs porque é a mesma palavra, não porque alguém a configurou igual
em dois sítios.

A paleta usa tokens do Shadcn (`bg-primary/10`, `bg-destructive/10`, …) e
nunca cores Tailwind cruas — há um teste a afirmá-lo, porque a regra
ESLint do PACOTE 11 é `warn` e o CI só falha em `error`.

### 25.3 Normalizar à escrita, espelhar no cliente

"VIP", "vip" e " VIP " são a mesma etiqueta para quem segmenta e três
para a base de dados. A normalização vive na escrita, no backend, em
**todos** os caminhos — e o frontend espelha-a, senão o editor aceita o
que a API recusa.

### 25.4 Um filtro novo liga-se em todos os sítios que LISTAM

O Kanban tem construtor de query separado do das listagens. Foi assim que
ficou de fora do isolamento por rede duas vezes. Um filtro novo precisa
de um inventário de superfícies e de um teste por cada, **nos dois
sentidos**: com o filtro filtra, sem o filtro não ganha ramo nenhum. Um
ramo sempre presente esconde os registos sem valor — que costumam ser a
maioria.

E o filtro vai no URL: partilhar um link já filtrado é metade da
utilidade da segmentação.

### 25.5 Perguntar só o que tem significado

O selector AND/OR só aparece com duas ou mais etiquetas escolhidas.
"Corresponder a todas" de uma só etiqueta é a mesma coisa que "qualquer
uma": a escolha não muda nada e só dá ao utilizador uma decisão a tomar
sem consequência.

## 26. Contexto de empresa/perfil e transporte (Lote 5, Secção B, Set 2026)

### 26.1 Quinta instância: `fetch` cru continua a aparecer

O Kanban chamava `/processes/kanban` por `fetch` em três sítios, com
`Authorization` e mais nada. O interceptor que injecta `X-Company-Id` e
`X-Active-Role` vive no cliente **Axios**; um `fetch` só leva o que lhe
escreverem à mão.

**Qualquer chamada que dependa de contexto de empresa ou de perfil vai
pelo `api` do Axios.** Não é uma preferência de estilo — é a diferença
entre o backend responder sobre o perfil activo ou sobre o papel base.
Os sintomas desta família são sempre os mesmos: funciona para quem tem
um perfil só, e falha silenciosamente para quem tem vários.

Quando um endpoint ganha uma função em `services/api.js`, o
`URLSearchParams` passa **intacto** — um `Object.fromEntries` perde as
chaves repetidas, e filtros multi-valor (etiquetas, ids atribuídos)
passam a ver só a última.

### 26.2 Um componente que se esconde não serve de fonte

O `ContextSwitcher` resolvia o nome da empresa activa, mas devolve
`null` quando não há nada para alternar — ou seja, exactamente para quem
tem uma empresa só. Reutilizar lógica de um componente com regras de
visibilidade próprias é reutilizar também o seu silêncio: a lógica sobe
para `utils/`, o componente fica com a apresentação.

### 26.3 Um id nunca aparece no ecrã como se fosse nome

`getDistinctCompanies` faz `company_name || company_id` — um UCR sem
nome mostra o identificador em bruto. Numa dropdown passa por um nome
estranho; num rótulo permanente é a confusão id/nome de 2026-09-21 à
vista todos os dias. **Vale mais não mostrar nada do que mostrar um
identificador**, e melhor ainda cair para outro campo que seja
comprovadamente um nome.

### 26.4 Quem perde o trabalho também é avisado

Reatribuir uma tarefa notificava quem entrava e não quem saía. A pessoa
anterior ficava com ela na lista até ao refresh seguinte, sem saber que
deixou de ser dela. **Uma transferência tem dois lados** — e o registo no
histórico tem de dizer o que mudou (o responsável), não repetir o título
da tarefa, senão reatribuir e renomear ficam indistinguíveis.

## 27. Listagens que crescem, e erros que se disfarçam (Lote 5, Set 2026)

### 27.1 A ordem dos ramos é parte da correção

Acrescentar um ramo de erro **depois** do estado vazio não corrige nada:

```jsx
{lista.length === 0 ? <Vazio/> : erro ? <Erro/> : <Lista/>}   // continua a mentir
{erro ? <Erro/> : lista.length === 0 ? <Vazio/> : <Lista/>}   // certo
```

Uma leitura falhada quase sempre devolve zero itens, por isso o estado
vazio à frente engole o erro. É o defeito do "VLM no Escuro" escrito
noutra forma — e escrevi-o mal à primeira, num ecrã onde o estava
precisamente a corrigir.

### 27.2 Ações destrutivas pedem confirmação, e dizem o que se perde

Apagar uma regra de negócio fazia-se com um clique. A confirmação diz o
NOME do que vai desaparecer e a consequência ("as automações que
dependem dela param"), não um "Tem a certeza?" genérico.

### 27.3 Paginação: o total é do âmbito, e a página fora do intervalo é um caso

- **Mostrar sempre o total** ("1–25 de 132"). Sem ele, o utilizador não
  distingue "são estes" de "são os primeiros" — que era o defeito do
  tecto silencioso de 200.
- **O total é o do âmbito do utilizador**, nunca o da coleção: um total
  global diz a uma rede quantos registos a outra tem.
- **Apertar a pesquisa estando numa página alta** devolve uma lista
  vazia que parece "não há resultados". Reiniciar a página a cada
  mudança de filtro, e `calcularPaginacao` devolve `foraDoIntervalo`
  para quem precise de reagir.
- **`placeholderData: (anterior) => anterior`** ao mudar de página —
  sem isso a tabela pisca toda para o esqueleto a cada clique.

### 27.4 Filtrar no cliente o que o servidor já filtrou esconde resultados

A pesquisa de utilizadores era `users.filter(...)` sobre a página
inteira trazida de uma vez. Ao passar a pesquisa para o servidor, o
filtro em memória tem de SAIR: aplicado por cima de uma lista já
paginada, esconde correspondências que o servidor colocou noutra página.

E uma pesquisa de pessoas procura por **empresa** também, não só por
nome e email — é assim que um administrador procura alguém.

### 27.5 `invalidateQueries` casa por PREFIXO, `setQueryData` por chave EXACTA

A diferença entre as duas parece trivia de biblioteca e produz um
**placebo**. O separador Utilizadores lia
`usersPaginated(pesquisa, pagina)` = `['org-admin','users','paginated',…]`
e escrevia em `users()` = `['org-admin','users']`:

```js
queryClient.invalidateQueries({ queryKey: users() });  // casa em prefixo → FUNCIONAVA
queryClient.setQueryData(users(), updater);            // chave exacta → entrada FANTASMA
```

Foi a metade que funcionava que escondeu a outra. Consequências, todas
invisíveis sem montar a tabela: clicar "Eliminar" não retirava a linha, o
"Desfazer" não repunha nada (só o `clearTimeout` salvava o registo), e um
erro do servidor deixava a linha desaparecida.

**Regras:**

- **Quem escreve na cache de uma listagem paginada usa `setQueriesData`
  com o PREFIXO** (`usersPaginatedAll()`), não `setQueryData` com uma
  chave montada à mão: a lista pode estar aberta na página 3 e com
  pesquisa activa, e há uma entrada por combinação.
- **A chave-prefixo existe como função própria** e a paginada deriva
  dela. Duas listas de segmentos escritas à mão divergem, e a divergência
  não dá erro.
- **A forma do que está em cache não é um array.** A página é
  `{utilizadores, total}`; tratá-la como array foi metade do defeito. A
  transformação vive em helpers PUROS
  (`removerUtilizadorDaPagina` / `reporUtilizadorNaPagina`), que é o que
  permite testar a idempotência e o chão do total sem montar nada.
- **O `total` desce com a linha.** Retirar a linha e deixar o total
  mostra "1–1 de 2" — uma contagem que contradiz o ecrã.

### 27.6 Um separador só está coberto quando alguém o MONTA

O `UsersAccessAdminTab` tem 789 linhas e nenhum teste o montava; o único
que o mencionava lia o **código-fonte** para verificar a forma da chave.
Um erro de render chegou a produção sem o CI dar um pio, e o defeito do
27.5 viveu meses num ecrã que ninguém renderizava num teste. É a mesma
regra do `WebmailPage` e do `ProcessDetails`, e vale para separadores de
painéis de administração exactamente como para páginas.

O primeiro teste de um ecrã destes é o mais estúpido possível — montar e
sobreviver — seguido de uma tabela de **formas que os dados reais tomam**
(registo sem id, relação sem nome de empresa, empresa sem id, chaves
repetidas, total incoerente, payload aninhado em vez de array). Essa
tabela escreve-se a ler os normalizadores e a perguntar, por cada `||`,
o que acontece quando nenhum dos lados existe.

### 27.7 Chaves de cache iguais exigem VALORES iguais

O erro de produção que fechou este lote:

```js
// CompaniesAdminTab   companies(pesquisa, pagina) → {empresas, total}
// UsersAccessAdminTab companies("")               → array
// e companies(s, p) = [...companiesAll(), s ?? '', p ?? 1]
//   logo companies("") === companies("", 1) — A MESMA CHAVE
```

Os dois separadores vivem no mesmo `SystemAdminPanel`, logo no mesmo
`QueryClient`. Quem monta primeiro decide a forma; o segundo recebe a do
outro. `TypeError: companies is not iterable`.

**Regras:**

- **Perguntas diferentes, chaves diferentes.** "Todas as empresas para um
  selector" e "página N da lista de empresas" não são a mesma pergunta,
  mesmo que a fonte seja o mesmo endpoint. A chave do selector
  (`companiesSelector()`) **desce** de `companiesAll()` para a invalidação
  por prefixo do CRUD continuar a alcançá-la.
- **Uma chave com argumentos por omissão colide com a explícita.**
  `companies("")` e `companies("", 1)` são iguais porque `page ?? 1`. Uma
  chave com omissões é uma armadilha para quem a chama com menos
  argumentos do que o autor imaginou.
- **`|| []` não protege contra isto**, e a razão é contra-intuitiva: um
  objecto é *truthy*, logo `companies || []` devolve o objecto. Medido:
  com a colisão presente e o `|| []` no sítio, o erro passa a
  `(companies || []).filter is not a function` — **muda de sítio em vez de
  desaparecer**. Só `Array.isArray` distingue, e o consumidor seguinte sem
  guarda volta a rebentar. **A correcção é a chave; a guarda é segunda
  linha de defesa e não substitui a correcção.**
- **Só um teste que monte os DOIS componentes na MESMA cache reproduz
  isto.** Os testes que montam um componente sozinho, com um
  `QueryClient` próprio, passam com o defeito presente — os meus passaram.

### 27.8 Ler uma configuração e escrevê-la têm de usar o MESMO âmbito

O ecrã dos limiares de SLA (`SlaThresholdsSection`) é deliberadamente
**global** e di-lo no cartão, porque o leitor
(`services/stats_sla._limiares`) chama `get_system_config()` sem
`company_id`. O `SystemConfig` aceita âmbito por empresa e o modelo até o
prometia na docstring — mas a promessa não estava cumprida do lado da
leitura.

Construir aqui um selector de empresa faria o administrador editar a Power
e o painel continuar a usar a global: é o incidente de 2026-09-21 outra
vez, com outro nome. **Enquanto o leitor for global, o ecrã é global e
diz-o.** A diferença está em `TECHNICAL_DEBT.md` D-12, não escondida.

Corolário para formulários de configuração: **um erro de LEITURA nunca se
apresenta como "está nas omissões"**. Se o GET falhou, diz-se, e avisa-se
que guardar escreve por cima de valores que o utilizador não viu.

### 27.9 Um separador escolhe UMA secção — registo positivo, nunca lista de exclusão

O `SystemConfigPage` decidia o conteúdo com uma lista NEGATIVA:

```jsx
{activeTab === "portal" && <PortalSettingsSection/>}            // lado positivo
{activeTab !== "portal" && activeTab !== "maintenance" && …      // lado negativo
  && <ConfigSection section={fields[activeTab]} …/>}
```

A mesma informação em dois sítios. Acrescentei um separador só no lado
positivo e o cartão genérico passou a renderizar-se **a par** do dedicado,
com `section` a `undefined` → `section.title` → `TypeError` → **ecrã em
branco**. É a forma do "Menu e rotas têm de concordar": divergem e não dá
erro em lado nenhum.

**Regras:**

- **Registo positivo** (`SECCOES_DEDICADAS`, chave → componente) como ponto
  único. Um separador é dedicado **ou** genérico, nunca os dois, e
  acrescentar um obriga a decidir.
- **Props uniformes** para todas as secções do registo (`token`, `user`).
  Quem não os usa ignora-os, e uniformizar evita um terceiro sítio com a
  lista de quem precisa de quê.
- **O separador vem do URL** (`searchParams.get("tab")`), logo um favorito
  antigo pede secções que já não existem: o desconhecido **diz-se**, em vez
  de cair no genérico (o mesmo crash por uma porta controlada por quem
  visita) ou de deixar a área vazia sem explicação.
- **Só a PÁGINA montada apanha isto.** O teste da secção nova passava com o
  defeito presente — montava a folha. Acrescentar um separador a uma página
  exige um teste que monte a página.

### 27.10 Ler o endpoint antes de escrever o ecrã

Três defeitos numa só entrega, todos da mesma raiz: construí o ecrã dos SLAs
contra um contrato **suposto**.

| Suposto | Real |
|---|---|
| `GET /system-config` devolve a configuração | devolve `{config, fields}` |
| `PATCH /system-config/{secção}` aceita qualquer chave | valida contra `CONFIG_FIELDS` + `EXTRA_SECTIONS` → 400 |

O primeiro é o pior dos dois, porque **parece funcionar**: `res.data.dashboard_slas`
dava `undefined`, o formulário caía nas omissões e o ecrã mostrava 7/15/30
fossem quais fossem os valores gravados.

**Regras:**

- **Ler o handler**, não inferir a resposta do nome do endpoint.
- **O mock do teste usa a forma REAL.** Um mock com a forma inventada é pior
  do que nenhum: faz a bateria verde sobre um ecrã que não lê nada. Terceira
  ocorrência no projecto (a primeira foi o `/portal/status`).
- **Os valores do fixture têm de ser DIFERENTES das omissões.** Com
  `{novo: 7}` — que é a omissão — um erro no caminho de leitura é
  indistinguível de uma leitura correcta. Foi a mutação que o denunciou:
  apontar a leitura para a chave errada matava **um** teste; com valores
  afastados, mata três.

## 28. Edição inline e navegação contígua (Lote 5, Secção B, Set 2026)

### 28.1 Um controlo dentro de uma linha clicável começa por travar o clique

A linha da tabela de processos navega para os Detalhes no seu `onClick`.
Qualquer controlo posto dentro dela — dropdown, checkbox, botão — tem de
fazer `stopPropagation`, ou abrir o controlo leva o utilizador embora
antes de ele chegar a usá-lo. É um defeito que não dá erro nenhum: só
parece que "o dropdown não funciona".

```jsx
<div onClick={(e) => e.stopPropagation()} onKeyDown={(e) => e.stopPropagation()}>
  <Select …/>
</div>
```

O `onKeyDown` também, e pela mesma razão: quem navega por teclado abre o
dropdown com Enter, e o Enter subiria para a linha.

### 28.2 Editar em linha usa o endpoint oficial, não um atalho

Um controlo pequeno convida a um endpoint pequeno. Não. A gravação
inline chama exactamente o que a página de Detalhes chama — é lá que
vivem o histórico, a auditoria, as automações e as regras de silêncio
por perfil. Um endpoint "leve" só para a listagem seria uma porta das
traseiras a todos eles, e ninguém daria por isso durante meses.

### 28.3 A permissão de um controlo inline espelha o backend — e num campo só

Mostrar um controlo a quem o servidor vai recusar com 403 é prometer uma
acção que não existe. Mas a resposta certa quando o frontend e o backend
resolvem a permissão por campos DIFERENTES não é exigir os dois: é
**corrigir a divergência**.

Foi o que aconteceu aqui. A edição inline nasceu a exigir o perfil
activo **e** o papel base do JWT, porque o `PUT /processes/{id}` decidia
pelo segundo. Assim que o backend passou a seguir `get_effective_role`
como o resto do produto, a dupla condição deixou de ser prudência e
passou a **esconder uma acção legítima** — a de quem é indexador numa
empresa e consultor noutra. Uma permissão espelha-se num sítio só.

A lição: uma condição defensiva montada por cima de uma divergência tem
de ser removida quando a divergência desaparece. Ficar lá "por
segurança" é código morto que mente ao utilizador.

### 28.4 Uma actualização optimista desfaz-se quando o servidor recusa

Deixar o valor novo no ecrã depois de um erro é a pior das saídas: o
utilizador sai convencido de que gravou. O valor anterior guarda-se
ANTES de mutar o estado e repõe-se no `catch`.

### 28.5 Uma seta que pode apontar para o sítio errado não se desenha

Nas setas Anterior/Seguinte dos Detalhes, a ausência de contexto de
navegação (o processo foi aberto por pesquisa global, por link, por
notificação) resolve-se **escondendo o controlo**, não adivinhando.
Adivinhar aqui é pior do que não oferecer: não dá erro, não deixa rasto,
e o utilizador só percebe depois de editar a ficha errada.

Já um vizinho que *existe* mas está do outro lado da página desenha-se
**desactivado**, não ausente — esconder o botão fá-lo-ia saltar de sítio
no primeiro e no último processo, e perder o alvo do rato a meio de uma
revisão de 40 processos é o atrito que a funcionalidade veio remover.

### 28.6 Estado que atravessa páginas: `state` do router, sessão, e só depois a rede

Por esta ordem, e nunca ao contrário:

1. `location.state` — o que a página de origem sabe, de graça.
2. `sessionStorage` — a mesma coisa, a sobreviver a um F5. Sobrevive ao
   refresh e **não** sobrevive a um separador novo, que é exactamente o
   comportamento certo.
3. Um pedido ao servidor — só para o que nenhuma das duas pode saber.

O `state` manda sobre a sessão: uma sessão velha de outra listagem não
pode sequestrar a navegação da listagem de onde o utilizador acabou de
vir. E toda a leitura/escrita de `sessionStorage` vai dentro de
`try/catch`: janela privada, quota cheia e cookies bloqueados são
normais, e um controlo de conveniência nunca pode impedir a página de
abrir.

### 28.7 Filtros de vários valores viajam em `URLSearchParams`, nunca num objecto

`labels` é `List[str]` no backend. Um `{labels: ["VIP","Urgente"]}`
serializado por omissão dá `labels=VIP,Urgente` e o servidor procura uma
etiqueta chamada "VIP,Urgente" — zero resultados, zero erros. É o mesmo
defeito que o `Object.fromEntries` ia introduzindo no Kanban. Constrói-se
o `URLSearchParams` com `append` por valor e passa-se **intacto**.

## 29. Formulários que o cliente preenche sozinho (Ponto 9, Set 2026)

### 29.1 "Obrigatório" tem UMA fonte, e é a que bloqueia

Um formulário com uma lista de campos obrigatórios para validar e outra
para a barra de progresso vai divergir — não é uma hipótese, é uma
questão de tempo. E quando diverge, a barra exige coisas que o botão
deixa passar, ou promete um avanço que o botão recusa. A fonte é a
configuração que o `validateStep` lê; tudo o resto deriva dela.

### 29.2 Esconder um campo que continua a bloquear é pior do que mostrá-lo

Divulgação progressiva num formulário público só funciona se o que fica
escondido for mesmo opcional. Caso contrário o cliente carrega em
"Próximo", recebe um erro sobre um campo que não está a ver, e não tem
como o encontrar. Por isso a divisão deriva da MESMA flag que bloqueia,
e não de uma lista de "campos que me parecem secundários".

### 29.3 Um passo sem obrigatórios mostra tudo

Se a divisão fosse cega, um passo em que todos os campos são opcionais
abria visualmente vazio, com a totalidade atrás de um botão. Um ecrã em
branco assusta mais do que uma lista longa: não há nada a esconder
quando não há nada a exigir.

### 29.4 Quem retomou um rascunho vê o que escreveu

O painel de campos adicionais abre já aberto quando algum dos campos lá
dentro tem valor. Esconder o que o cliente escreveu na sessão anterior
lê-se como trabalho perdido.

### 29.5 O convite diz o que se ganha, nunca o que falta

Nada de "obrigatório", "em falta", "tem de", "erro". O rótulo diz o que
aqueles campos servem, e o corpo diz, por palavras, que se pode
continuar sem eles. Há um teste a varrer as palavras proibidas — porque
copy é comportamento, e regride tão facilmente como código.

## 30. Separadores que representam um âmbito de dados (Ponto 8, Set 2026)

### 30.1 Um separador solitário nunca se desenha

Se só há uma opção, não há escolha — há uma linha de ecrã desperdiçada e
um controlo que não faz nada. Mostra-se o rótulo (saber onde se está não
é ruído) e a barra desaparece. A regra vive num módulo puro, testada nos
dois sentidos, e não num `length > 1` dentro do JSX.

### 30.2 O âmbito do separador viaja em cada pedido

Um separador que mude só o que está no ecrã, sem mudar o que se pede ao
servidor, é uma ilusão. O identificador do âmbito vai como **parâmetro**
de cada chamada — e não como header, nem como estado global — para que a
autorização do lado do servidor tenha alguma coisa em que pegar.

### 30.3 A lista de separadores vem de quem autoriza

Derivá-la do contexto do cliente (o utilizador em sessão) parece
equivalente e não é: o cliente pode mostrar um separador que o servidor
recusa, e o utilizador fica com uma caixa vazia sem explicação. A lista
vem do mesmo sítio que decide o 404.

### 30.4 Um âmbito pedido que já não existe cai no primeiro

URLs antigos e sessões guardadas sobrevivem a acessos revogados.
Insistir no identificador pedido dá um erro do servidor onde devia haver
uma caixa; cair no primeiro âmbito válido é o comportamento que o
utilizador espera.

### 30.5 Uma operação de fundo não merece um painel

Sincronizar, importar, recalcular: usa-se uma vez por sessão e o
resultado interessa mais do que o botão. Uma linha de estado no
cabeçalho ("Actualizado há 5 min") com um ícone ao lado substitui um
painel permanente — e o estado "ainda não correu" não se pinta de
alarme, porque é o estado normal ao abrir a página.

### 30.6 Prop que deixou de ser usada sai do contrato

Quando o comportamento muda de componente, as props que o serviam saem
do que ficou para trás — da assinatura, do JSDoc e dos testes. Uma prop
morta é um contrato que mente, e o próximo a ler acredita nele.

## 31. Eventos de tempo real: o que o cliente pode e não pode assumir (Épico 10, Set 2026)

Até ao Épico 10, um evento de processo chegava por `manager.broadcast()` — a
**todos** os sockets ligados. O `useKanbanRealtime` inseria o cartão que lhe
chegasse, e por isso um processo da Power aparecia, com o nome do cliente, no
quadro de quem estava na Domus. O filtro passou a existir no servidor
(`services/realtime_audience.py`); estas regras existem para que o cliente não
volte a depender de não haver filtro nenhum.

**31.1 — Um evento que chega já foi autorizado; um evento que não chega não é
um erro.** O servidor entrega a quem a audiência do processo alcança. Um
quadro que receba menos eventos do que antes está correcto, não partido. Nunca
compensar uma ausência com um pedido extra "para o caso de".

**31.2 — O tempo real não é a fonte da verdade, é um atalho.** O delta traz
campos leves (`client_name`, `status`, `updated_at`), nunca o processo. Quem
precisa do processo pede-o ao HTTP, que reverifica as permissões a cada
pedido. Não alargar o payload de um evento para evitar um `GET`: seria pôr
dados de negócio a atravessar um canal que não faz query nenhuma.

**31.3 — Ignorar o eco do próprio utilizador é responsabilidade do cliente.**
O `PROCESS_MOVED` deixou de excluir o autor no servidor (a audiência inclui-o,
naturalmente). O `useKanbanRealtime` já faz `if (payload.user_id === userId)
return;` porque a actualização optimista tratou do assunto. Quem escrever um
handler novo tem de fazer o mesmo — caso contrário o cartão salta duas vezes.

**31.4 — `event_id` serve para desduplicar.** Cada envelope traz um `id`, e o
cliente pode recebê-lo duas vezes numa reconexão. Handlers de inserção têm de
ser idempotentes (procurar antes de inserir), como os do Kanban já são.

**31.5 — O polling continua a ser o recurso, e ainda não foi cortado.** As
Fases 1 e 2 arrumaram a entrega; a Fase 3 é que suspende os intervalos. O
padrão é o do Webmail e do `TasksContext`: parar quando `isConnected` e
retomar quando o WS cai — nunca apagar o intervalo.

**31.6 — Um indicador de presença mente com vários workers.** `is_online` vem
de `manager.is_user_connected`, que só conhece o worker que atendeu o pedido.
Não construir funcionalidade em cima dele (atribuir só a quem está online, por
exemplo) enquanto não houver um registo de presença partilhado.

## 32. Uploads: o `Content-Type` e a predefinição da instância (Set 2026)

**32.1 — Omitir o `Content-Type` num upload NÃO é limpá-lo.** A instância
Axios declara `application/json` por omissão, e o `transformRequest` do Axios
converte um `FormData` em JSON quando vê esse cabeçalho: o ficheiro vira `{}` e
o servidor devolve 422 `Field required` em TODOS os campos do formulário. Três
funções tinham este defeito e nenhuma parecia errada.

**32.2 — Não escrever `Content-Type` nenhum em chamadas com FormData.** O
interceptor de `utils/formDataTransport.js` anula-o. Escrever
`"multipart/form-data"` à mão funciona por acidente (o Axios limpa-o lá
dentro), e um acidente não é uma regra.

**32.3 — Passar um objecto com `multipart/form-data` é outra coisa, e é
legítima.** O Axios converte o objecto em FormData. `createTempLink` usa-o de
propósito; o interceptor não lhe toca porque, nesse momento, `config.data`
ainda não é FormData.

**32.4 — Duas funções para o mesmo endpoint é uma a mais.** `uploadClientS3File`
duplicava `uploadProcessS3File`, nunca teve chamador e guardava o defeito
enquanto a irmã era corrigida. Antes de acrescentar um helper de API, procurar
o endpoint no ficheiro.

**32.5 — Um teste de transporte vale contra um servidor a sério.** 
`services/__tests__/formDataTransport.test.js` corre em `// @vitest-environment
node`, levanta um `http.createServer` e lê os bytes que chegam. Um duplo do
adaptador do Axios teria "confirmado" o comportamento errado, porque o defeito
está no `transformRequest` — antes do adaptador.

## 33. Explorador de Ficheiros: o que a UI pode e não pode assumir (Épico 10, Set 2026)

**33.1 — A lista que chega já vem filtrada.** O servidor devolve só as pastas da
rede de quem pede (`services/s3_explorer_scope.py`). A UI não filtra, não conta
"quantas faltam" e não oferece um "ver tudo" — não há tudo para ver.

**33.2 — 404 não é "erro", é "não é sua".** Uma pasta de outra rede responde
404, como se não existisse. Mostrar "sem permissões" nesse caso confirmaria que
a pasta existe, e o nome da pasta é o nome do cliente. A mensagem é *"Pasta não
encontrada"*, igual à de uma pasta que de facto não existe — a indistinção é
intencional.

**33.3 — 403 continua a existir e significa outra coisa:** o perfil não entra na
página. Os dois ramos são distintos no `catch` e têm de continuar a sê-lo.

**33.4 — Renomear é uma operação de dados, não de cosmética.** O servidor move
os objectos no S3 **e** reaponta o mapeamento do processo, os metadados dos
documentos e os pedidos do Portal. A resposta traz `relink` com as contagens;
se aparecer `relink.erro`, os ficheiros moveram-se e as ligações ficaram
partidas — vale a pena dizê-lo ao utilizador em vez de celebrar sucesso.

**33.5 — O menu e a rota têm de concordar.** A lista de papéis do item
"Ficheiros" no `DashboardLayout` e as `allowedRoles` da rota em `App.js` são
lidas e cruzadas por `App.rotasMenu.test.js`. Abrir um sem o outro dá um item de
menu que redirecciona — o produto a contradizer-se, sem erro em lado nenhum.

---

## 34. Nomes de fases do workflow no frontend (Épico 10, Set 2026)

As fases do processo são **configuráveis pelo administrador**. O frontend não
tem autoridade sobre elas — tem, hoje, três listas que fingem o contrário.

**34.1 — Uma lista de nomes de fases no frontend é dívida, não configuração.**
Existem três: `ALIASES_LEGADOS` (`utils/processTimeline.js`), `MACRO_FASES`
(`utils/funilDeFases.js`) e os literais `'concluidos'` / `'desistencias'`
espalhados pelo `KanbanBoard`, `KanbanColumn`, `KanbanCard` e
`useKanbanCompletedQuery`. Nenhuma cresce: quem lê fases novas é o motor.
**Código novo não acrescenta a nenhuma delas.**

**34.2 — A regra do alias, quando for preciso aplicá-la.** Um nome antigo só
vence quando o motor **não** conhece o nome gravado **e** conhece o destino.
Nunca ao contrário — basta o admin criar uma fase com o nome antigo para a
tradução passar a reescrever processos correctos. Está escrita no cabeçalho do
`processTimeline.js` e vale para toda a gente.

**34.3 — `ALIASES_LEGADOS` tem agora um gémeo em Python.**
`services/workflow_status_coverage.py` porta a mesma tabela para a medição de
produção, e `tests/unit/test_workflow_status_coverage.py` lê o ficheiro JS e
exige que os dois sejam o mesmo conjunto. **Editar um obriga a editar o
outro** — até a Parte 2, que muda a fonte para a base de dados e mata a
duplicação.

**34.4 — Uma fase que nenhum grupo cobre aparece; não desaparece.** É a regra
do `agruparEmFunil` e mantém-se: o que não couber vai para "Outras fases", com
o nome, em vez de ser deitado fora em silêncio. Um agrupamento que perde
processos mente com ar de relatório.

**34.5 — Terminal não se decide por lista.** Uma fase é terminal quando o
motor diz `is_active: false`. Um `status === 'concluidos'` num componente é a
mesma dívida do 34.1 com outra forma.

---

## 35. A coluna de reconciliação do Kanban (Épico 10, Parte 3)

O quadro deixou de perder cartões. Os processos cujo `status` gravado o
motor não reconhece deixam de desaparecer e passam a juntar-se numa coluna
própria — `reconciliacao: true` no objecto da coluna.

**35.1 — Não é uma fase; é uma caixa de entrada.** Vem no fim, não mostra
número de passo, e **não aceita cartões**: `onDragOver` e `onDrop` são
ignorados quando `column.reconciliacao === true`. Largar lá um cartão seria
pedir ao servidor um estado que não existe — ele responde **400 "Estado
inválido"** e o utilizador leva um erro por uma acção que a UI lhe deixou
fazer. Os cartões só **saem** dela, para uma fase a sério, e é isso que
reconcilia o processo.

**35.2 — A comparação é estrita (`=== true`).** `reconciliacao` ausente não
é `false`: uma coluna normal nunca pode cair neste ramo por omissão.

**35.3 — Esconder a coluna não é esconder o problema.** Só `ADMIN`/`CEO` a
recebem, mas `total_desconhecidos` vem na resposta do `/kanban` para toda a
gente. Se alguma vez for preciso mostrar o número a outros perfis, o dado já
lá está — o que não pode acontecer é o número deixar de existir.

**35.4 — `status_resolvido_de` diz que o cartão está ali por tradução.** Um
processo gravado como `escriturado` aparece na coluna `concluidos` com
`status_resolvido_de: "escriturado"`, e o `status` continua `escriturado`. A
resolução é de leitura; o campo existe para a UI poder dizê-lo e para um
diagnóstico não ter de refazer a conta.

**35.5 — Continua a valer a regra 34.1.** Os literais `'concluidos'` /
`'desistencias'` que ainda existem no `KanbanBoard`, `KanbanColumn`,
`KanbanCard` e `useKanbanCompletedQuery` **não cresceram** nesta parte e
continuam a ser dívida. Código novo não lhes acrescenta nada.

---

## 36. O grupo do funil é uma lista fechada (Épico 10, Parte 2)

**36.1 — Cinco grupos, `<Select>`, nunca `<Input>`.** `novo`, `analise`,
`aprovado`, `concluido`, `perdido`. Texto livre criaria um grupo novo com
uma gralha (`aprovdo`) e o funil partia-se em silêncio: os processos dessa
fase saíam do grupo certo e apareciam num grupo de um só, com ar de
categoria legítima. O backend recusa ao gravar; a UI tem de recusar antes,
senão o utilizador só descobre no submit.

**36.2 — "Sem grupo" é uma opção, e tem de existir.** Obrigar a escolher é
obrigar a inventar. Uma fase sem grupo cai em «Outras fases», com o nome à
vista — nunca desaparece. Atenção ao detalhe do Radix: `<SelectItem>` não
aceita `value=""`, por isso a opção usa uma chave interna
(`__sem_grupo__`) que é traduzida para `""` **antes** do payload. Se
escapasse, o backend recusava-a pelo enum.

**36.3 — A lista de fases saiu do `funilDeFases.js`.** Ficaram as
etiquetas e as cores dos grupos. Quem classifica é `macro_fase`, vindo do
motor com as `workflow_statuses`. O `CLASSIFICACAO_DE_RECURSO` só socorre
uma fase que o motor ainda não classificou, perde sempre para ele, e **não
cresce** — uma fase nova classifica-se na UI, não neste ficheiro.

**36.4 — `statuses` de um grupo é o que caiu lá, não o que foi declarado.**
Mudou de significado na Parte 2. É o que serve para clicar num segmento do
funil e filtrar a lista.

**36.5 — As duas listas do frontend e o enum do backend são cruzados por
testes.** `workflowEditorMacroFase.test.js` compara o `<Select>` com o
`MACRO_FASES` do funil; do lado do Python, `test_macro_fase.py` lê os dois
ficheiros JS e compara-os com o enum. Mexer numa obriga a mexer nas outras.

## 37. Páginas de BI: quem agrega é o servidor (Dashboard, Set 2026)

**37.1 — Uma página de estatísticas não puxa a colecção para contar.** O
`StatisticsPage` faz `getProcesses()` sem filtro e conta em JavaScript. Com
12.450 processos em produção, isso é a base de dados inteira pela rede para
desenhar um gráfico de barras — e o risco de desempenho do BI não está no
Mongo, está aqui. Contagens, médias e distribuições vêm de um endpoint que
as calcula numa agregação; a página recebe números, não registos.

**37.2 — Nunca agrupar pelo valor CRU de `status`. FEITO.** Estas três linhas
estavam no `StatisticsPage` e foram removidas na Camada 2:

```javascript
filteredProcesses.filter(p => !['concluidos', 'desistencias'].includes(p.status))
filteredProcesses.filter(p => p.status === 'concluidos')
acc[p.status] = (acc[p.status] || 0) + 1        // agrupava pelo valor cru
```

Eram listas cravadas de nomes de fases — exactamente o que o Épico 10 implodiu
no backend — e o agrupamento pelo valor cru punha os 205 processos em
`cpcv`/`escriturado` e as 12 gralhas `"Concluidos "` em barras próprias. O
quadro resolvia-os para a coluna certa e o gráfico não: **duas verdades sobre
os mesmos dados no mesmo produto**.

Hoje a página consome `GET /stats/funil` e `GET /stats/sla`, onde a ponte com o
motor de workflow garante que uma barra conta o mesmo que uma coluna. As
transformações que restam são apresentação e vivem em `utils/statsFunil.js`,
puras e testadas. **Nada neste ficheiro pode voltar a saber nomes de fases** —
quem sabe isso é o motor, no servidor.

**37.2.1 — Dois campos que a página lia errados, e ninguém viu.** O filtro por
utilizador comparava `p.assigned_consultor` (os canónicos são
`assigned_consultor_id` / `consultor_id` / `consultant_id`) e o gráfico de
prioridades contava `p.priority === 'high'` (o campo é `prioridade` e os valores
são `baixa`/`media`/`alta`). Nenhum dos dois dava erro: um esvaziava todos os
gráficos ao escolher um utilizador, o outro mostrava zero desde sempre. **Um
campo que não existe lê-se como `undefined` e compara-se em silêncio** — é por
isto que o filtro passou para o servidor, onde a condição canónica já existe e
está testada.

A guarda de listas cravadas do Épico 10 varre `backend/services/` e por isso
não apanhou nada disto. Quem apanhou foi o teste de integração da página
(`pages/__tests__/StatisticsPage.test.jsx`), que afirma por COMPORTAMENTO que
`getProcesses` não é chamado.

**37.3 — Um número estimado tem de se ver que é estimado.** O relógio de
fases só começa a contar no dia em que o carimbo entrar; os processos
anteriores levam uma estimativa marcada com `fase_desde_estimado`. Um gráfico
que misture medido com estimado sem o dizer é pior do que um gráfico vazio —
a resposta do servidor traz as duas amostras separadas e a UI tem de as
distinguir (nota de rodapé, cor diferente, o que for), nunca somá-las em
silêncio.

### 27.11 Um registo só é ponto único se TODAS as superfícies derivarem dele

O `SystemConfigPage` decide o conteúdo por um registo positivo
(`SECCOES_DEDICADAS`, § 27.9) — e mesmo assim o separador "Limiares de SLA"
desapareceu num ecrã estreito. A navegação estava escrita à mão em **três**
sítios: a barra lateral (`hidden lg:block`), o `<Select>` do telemóvel e a
fila de chips ao lado dele. O separador entrou só no primeiro.

Não era overflow. A fila de chips já tinha `overflow-x-auto`; um item que
não é **renderizado** não se alcança com scroll nenhum. O diagnóstico
natural ("o Radix Tabs não lida com o overflow") aponta para o sítio
errado — e ali não há Tabs do Radix nenhum.

**Regra:** uma lista de itens de navegação vive num array exportado e as
superfícies (desktop, dropdown, chips) fazem `map` sobre ele. Acrescentar um
item é acrescentar uma linha; esquecer uma superfície deixa de ser possível.

**Corolário para o teste:** no jsdom as media queries do Tailwind não se
aplicam, pelo que TODAS as navegações existem na árvore ao mesmo tempo — é
exactamente isso que permite afirmar, num só teste, que cada item tem o
botão da barra lateral **e** o chip do ecrã estreito. Um teste que verifique
só uma delas volta a deixar passar este defeito.

### 27.12 `overflow-x-auto` com a barra escondida é uma porta sem maçaneta

A fila de chips rolava com `style={{scrollbarWidth: "none"}}`. Num telemóvel
não havia nada a indicar que houvesse mais separadores à direita, e num rato
sem eixo horizontal não havia como chegar lá. `flex-wrap` mostra tudo em
qualquer largura e não precisa de afordância.

Esconder a barra de rolagem é uma decisão de estética que custa
descobribilidade: só se faz quando existe outra pista de que há mais
conteúdo (um gradiente na margem, setas).

### 27.13 O limite de altura de um `ScrollArea` vai no VIEWPORT

O `ScrollArea` do Radix tem `overflow-hidden` na `Root` e `h-full` no
`Viewport`. Um `maxHeight` na Root — o reflexo natural, e o que o
`TasksPanel` fazia — deixa a Root em altura **auto**, pelo que o `h-full` do
viewport resolve para a altura do conteúdo: o viewport nunca transborda, o
Radix não desenha barra nenhuma, e a Root **corta** o excedente com o seu
`overflow-hidden`.

O resultado não é uma lista com elevador: é uma lista **truncada**, com
itens que não se conseguem alcançar. Para "As minhas tarefas" do Dashboard
isso significava tarefas invisíveis.

Usar `viewportStyle`/`viewportClassName` (o wrapper em `components/ui/`
aceita-os) para o limite, ou uma altura DEFINIDA (`className="h-[280px]"`,
que é o que os restantes usos já faziam e por isso funcionavam). O jsdom não
faz layout, pelo que o teste afirma o CONTRATO — o limite chega ao viewport
e não à root — e não o scroll.

### 27.14 Um `ErrorBoundary` fica preso até alguém o repor

Um error boundary do React mantém o estado de erro até ser remontado ou
reposto à mão. O desta app só se repunha no clique de "Tentar novamente", e
vive **dentro** do `element` de cada rota: a partir do primeiro crash, toda
a navegação para aquela rota mostrava o ecrã de erro — de um recurso que já
não era o aberto, e mesmo depois de a causa desaparecer.

Em produção apareceu como uma assimetria que não se explicava pelo código
da página: as setas Anterior/Seguinte funcionavam e o "Voltar" do browser
dava ecrã em branco. A app declarava **duas** rotas para os detalhes do
processo (`/processo/:id` e `/process/:id`), cada uma com o seu `element` e
portanto com o seu boundary — um ficava latido e o outro não.

**Regra:** um boundary por rota recebe `resetKey` com o contexto (o
pathname) e repõe-se quando ele muda, com o `retryCount` a zero — mudar de
sítio é uma tentativa nova, e o limite de tentativas existe para travar um
ciclo de re-render, não para condenar uma rota durante a sessão.

Isto **não esconde o erro**: ele foi registado e volta a acontecer se a
causa persistir. O que deixa de acontecer é o ecrã ficar quebrado depois de
a causa desaparecer — que é a diferença entre um relato reproduzível e "às
vezes fica branco".

### 27.15 O snapshot dos cabeçalhos não pode ficar um commit atrasado

O interceptor do Axios lê `X-Company-Id`/`X-Active-Role` de um snapshot em
memória (`authContextHeaders`) e **prefere-o** ao storage. Quem o escreve é
`syncAuthContextHeaders`, e isso acontecia apenas num `useEffect` — ou seja,
depois do commit.

`switchActiveRole` chama `queryClient.clear()` de forma **síncrona**, e o
`clear()` faz as queries activas voltar a pedir imediatamente. Esses pedidos
saíam com a empresa **anterior**, e os dados que voltavam ficavam em cache
como se fossem os do âmbito novo. Um utilizador da Domus via a caixa geral e
as tarefas da Power, e nada repetia o pedido depois de o estado convergir.

**Regra:** numa troca de âmbito, o snapshot é escrito no mesmo tick, antes
de invalidar ou esvaziar. O efeito continua a reconciliar (arranque,
`/auth/me`); o que não pode é ser o único a escrever.

**Como se prova:** afirmando a ORDEM, não o estado final. O teste anterior
verificava `sessionStorage.getItem("activeRole")` com o comentário "se a
cache fosse limpa primeiro, o refetch partia com os headers antigos" — a
premissa certa e a asserção no sítio errado, porque o storage não é o que o
interceptor lê primeiro. Provava que a escrita acontecera e concluía que os
cabeçalhos estavam certos.

### 27.16 Um parâmetro de âmbito no URL sobrevive ao `reload()`

`switchActiveCompany` termina em `window.location.reload()`, que recarrega o
**mesmo URL**. O Webmail põe a empresa em `?company_id=` (para o separador
sobreviver a um F5 e para um link levar alguém à caixa certa) e o parâmetro
do URL vence a empresa activa — e deve vencer, é o que faz um link
funcionar. Quem estivesse em `/webmail?company_id=<power>` e trocasse para a
Domus voltava a cair na caixa da Power.

Reescrever o parâmetro antes do reload, não removê-lo: quem trocou de
empresa quer ver a caixa da nova, e o resto do URL (pasta, pesquisa)
continua a valer.

### 27.17 Três estados precisam de três condições, não de duas e um `else`

`WebmailCompanyTabs` decidia com `deveMostrarSeparadores(empresas)`
(`length > 1`) e punha o rótulo da empresa única no **`else`**. O
complemento de "mais do que uma" inclui o **zero**: com a lista ainda a
carregar — ou com o pedido falhado, ou com um utilizador sem UCR nenhum —
o `else` disparava e desenhava o ícone de empresa com o nome **em branco**.

No ecrã, "a carregar" e "uma empresa" ficam indistinguíveis. Um estado de
carregamento nunca pode cair no ramo de um estado de dados.

**Num teste o efeito é pior, e é assíncrono:** `findByTestId` resolve
assim que o elemento existe — e ele já existia, vazio. O
`toHaveTextContent` que vem a seguir corre contra esse vazio. Passa numa
máquina rápida, falha num CI carregado. Foi verde três vezes localmente e
vermelho no CI.

**A saída não é esperar melhor no teste.** Um `waitFor` à volta da
asserção mascara o defeito: o ecrã continua a mostrar um rótulo vazio a
utilizadores reais. A correcção é **o elemento só existir quando tem o que
dizer** — e aí a presença dele passa a ser, ela própria, a afirmação.

```js
// ✗ duas condições para três estados
{mostrarSeparadores ? <Tabs …/> : <span>{rotulo(empresas?.[0])}</span>}

// ✓ cada estado com a sua condição, e a do meio é POSITIVA
{mostrarSeparadores ? <Tabs …/>
 : mostrarNome ? <span>{rotulo(empresas[0])}</span>
 : <span className="min-w-0" />}
```

**A contraprova que acompanha a regra:** as duas condições nunca podem ser
verdadeiras ao mesmo tempo, para qualquer lista — é essa exclusividade que
o `else` encadeado assume.

**E quem prova a regra é o teste de COMPONENTE.** O teste da página passa
de qualquer forma numa máquina rápida; é o teste que monta o componente com
a lista vazia que afirma que o rótulo não existe.

### 27.18 Uma cascata de fallbacks esconde um contrato inventado

As duas listagens de processos mostravam a coluna "Notas do Consultor"
com uma cascata que começava assim:

```js
// ❌ ERRADO — os três primeiros campos não existem no backend
const noteText =
  process.latest_activity_preview ||
  process.latest_activity_note ||
  process.latest_note ||
  "";
```

`latest_activity_preview`, `latest_note` e `latest_activity_note` têm
**zero** ocorrências em `backend/`. Na `FilteredProcessList`, onde a
cascata só lia esses três, a coluna dizia "Sem notas recentes" em TODOS
os processos, sempre. Na `ProcessesPage` havia mais sete ramos por baixo
e o sexto chegava a `process.notes` — **foi essa metade a funcionar que
escondeu a outra**, exactamente como o `run_get_my_tasks` escondeu o
`run_get_tasks`.

Duas regras saem daqui:

1. **Um `||` encadeado sobre campos de um endpoint é uma hipótese, não
   um contrato.** Se não se sabe qual dos nomes vem, não se sabe se
   algum vem. Ler a projecção do backend **antes** (§ 27.10) e escrever
   um só nome.
2. **A cascata é o próprio disfarce.** Com um campo só, "está vazio"
   nota-se no primeiro processo. Com sete, o ecrã mostra *alguma coisa*
   e ninguém pergunta de onde vem.

Hoje a regra vive num ponto único e puro (`notaMaisRecenteDoConsultor`,
derivado de `resolveProcessObservationNotes` — os mesmos campos, a mesma
ordem que o cartão do Resumo), e o contrato tem guarda **do lado do
backend**, que é o único que o pode afirmar:
`tests/unit/test_projeccao_das_notas_do_consultor.py`, com contraprova de
que os nomes inventados continuam a não existir.

### 27.19 Uma UI removida por regra de negócio precisa de um teste da AUSÊNCIA

O separador Histórico passou a ser uma trilha de auditoria só de leitura
(Ponto 9): sem diálogo de "Registar Atividade", sem caixa de texto, sem
gravador. Apagar o código não chega — **uma UI removida volta com a
mesma facilidade com que saiu**, e é a regressão mais fácil de não dar
por ela: não parte nada, não dá erro, apenas repõe um botão que alguém
achou que faltava.

`HistoryTab.soLeitura.test.jsx` afirma a ausência pelo papel e pelo nome
acessível (não por `data-testid`, senão o mesmo botão com outro
identificador passava), e inclui duas coisas que a tornam honesta:

* uma contraprova de que a ausência **não depende de quem chama** — o
  separador recebe `handleSendComment`/`newComment` e continua a não
  desenhar nada;
* uma contraprova de que "só de leitura" não virou "vazio": a timeline
  e a tabela de auditoria continuam lá.

E a ausência **explica-se no ecrã** (`historico-so-leitura`: "Registo
automático — as notas escrevem-se no Resumo"). Sem isso, quem procurar o
botão conclui que a página está partida em vez de perceber que o sítio
mudou — é a mesma razão pela qual um 403 esperado não se mostra como
"Sem documentação".

**Uma funcionalidade que estorva uma regra nova muda-se de sítio, não se
apaga.** O botão de nota de voz saiu do Histórico para o cartão de
Observações, no Resumo, e o teste da ligação mudou-se com ele: uma nota
ditada é uma nota, e o sítio das notas passou a ser um só.

## 27.20 — `fetch` cru numa página com contexto de empresa (5.ª instância)

`ClientRegistrationsPage` fazia as três chamadas por `fetch` cru. O
interceptor que injecta `X-Company-Id` / `X-Active-Role` vive no cliente
**Axios** (`services/api.js`); um `fetch` só leva o que lhe escreverem à
mão, e ali só ia a `Authorization`.

Enquanto o backend não filtrava por rede, isso não se notava. No momento
em que `/clients/registered` passou a resolver a rede do utilizador, um
`fetch` cru passaria a devolver **a lista errada, em silêncio** — sem
erro, sem aviso, com ar de estar a funcionar.

**Regra (a mesma desde 2026-09-21, agora pela quinta vez):** qualquer
chamada que dependa de contexto de empresa/perfil vai pelo `api` do
Axios. E o corolário que esta instância acrescenta: **quando se põe um
filtro de tenant num endpoint, verifica-se no mesmo lote quem o chama** —
um endpoint que passa a filtrar e um chamador que não manda os
cabeçalhos produzem uma lista vazia ou errada que ninguém liga à
alteração do backend.

## 27.21 — Um painel de operação diz QUAL caminho aconteceu, não só que correu

`EngineStatusPanel` ganhou botões «Forçar Execução» (Lote 2, ponto 1). O
motor vive em DOIS processos do `render.yaml`, e o botão faz coisas
diferentes conforme o job:

* job da **Aplicação** → corre no processo que serve o pedido;
* job do **Processador** → fica um PEDIDO na fila, reclamado no ciclo
  seguinte (até 1 minuto).

**A mensagem vem do SERVIDOR.** Escrevê-la no frontend obrigaria a UI a
saber em que processo vive cada job — uma segunda cópia dessa regra, a
divergir da do backend sem dar erro. E a UI tem de **distinguir os dois**:
dizer "correu" a um pedido que só foi entregue é o painel a mentir, que é
exactamente o motivo por que ele era read-only antes.

Três regras que vieram deste componente:

1. **Quem pode ser accionado é decisão do servidor** (`pode_forcar`), e o
   motivo de não poder vai à vista (`motivo_sem_forcar`). Um botão em
   falta sem explicação manda o utilizador procurar o que não existe. Uma
   lista de "quem se pode forçar" no frontend divergiria da do backend —
   e aí o botão aparece para um job que o servidor recusa.
2. **O estado "a carregar" guarda a CHAVE, não um booleano.** Com um
   booleano, clicar num job desativava o botão de todos.
3. **Recarregar o estado depois de accionar, inclusive quando FALHA.** Sem
   isso o painel continua a dizer «Nunca correu» a seguir ao clique e o
   utilizador conclui que o botão não faz nada; e um pedido registado
   antes da falha continua a ser informação.

O teste legado que afirmava «não oferece nenhuma acção sobre o motor» foi
**INVERTIDO, não apagado**: continua a valer que um job sem autorização do
servidor não mostra botão nenhum.

## 27.22 — Uma regra de negócio não vive num `executeSave`

A sincronização «Créditos Ativos → Contas Bancárias» estava dentro do
`executeSave` do `pages/ProcessDetails.js`. Corria quando um humano
carregava em Gravar naquela página, e só então: a IA, o
`ai-apply-suggestions`, o motor financeiro e qualquer importação passavam
todos ao lado, e a lista ficava incompleta **sem dar erro nenhum**.

**Regra:** uma transformação que tenha de valer para TODOS os escritores
de um campo vive no backend, no caminho da escrita — não no handler de
gravação de um ecrã. O ecrã é um dos escritores, não o escritor.

O bloco antigo tem um detalhe que vale guardar: mutava `financialData` em
sítio **e** chamava `setFinancialData`. Era a MUTAÇÃO que o fazia
funcionar — o `setState` é assíncrono e não chegaria a tempo do payload —
pelo que o código parecia idiomático e dependia do contrário. Quando se
encontra um par assim, a pergunta não é qual dos dois tirar: é porque é
que a regra está ali.

## 27.23 — Mostrar uma sugestão da IA não é gravá-la

O preenchimento em linha (Lote 3, ponto 1) substitui o diálogo sobreposto
de resultados: a sugestão aparece NO campo, com fundo amarelado e
aprovar/rejeitar ao lado.

**A regra que isto não pode quebrar:** o input desenha o valor sugerido
enquanto ele está PENDENTE — é esse o ponto de o preenchimento ser em
linha —, mas o que vai no payload é só o que foi APROVADO. São duas
funções diferentes em `utils/sugestoesEmLinha.js` (`valorAMostrar` e
`valoresAprovados`) e a separação é deliberada: se a gravação voltar a
partir do `extractedData`, **a interface fica exactamente igual e a regra
de ouro desaparece sem deixar rasto**.

Três regras do mecanismo:
1. **«Aprovar todas» nunca reabre o que já foi rejeitado.** Reabrir
   gravava o que o consultor acabou de recusar, em silêncio.
2. **Um campo rejeitado não volta a pendente.** Ele já respondeu; repor a
   pergunta a cada render faz o ecrã perguntar para sempre.
3. **O destaque é temporário.** Amarelo enquanto pende (é um pedido de
   atenção), verde um instante quando é aprovado, nada quando é rejeitado
   (o valor voltou a ser o da ficha — destacá-lo dizia o contrário). Um
   destaque permanente deixa de ser um destaque.

E cada botão leva o NOME DO CAMPO no nome acessível: com dez sugestões no
ecrã, dez botões «Aprovar» são indistinguíveis para quem usa leitor de
ecrã — e impossíveis de consultar num teste.

## 27.24 — Um badge de confiança tem de olhar para o VALOR

`getConfidenceIndicator` decidia só pelo número da IA. O input do NIF tem
`placeholder="9 dígitos"`: com o campo vazio o browser desenha esse texto,
e ao lado dele aparecia «IA 100%».

**É o badge que faz o placeholder parecer um dado.** Sem ele, um campo
vazio lê-se como um campo vazio.

**Regra:** um indicador de proveniência ou de confiança recusa-se a
aparecer quando (a) o valor está vazio, (b) o valor é igual ao texto do
placeholder — a IA que lê um formulário EM BRANCO devolve o texto de ajuda
como se fosse o valor, e é um modo de falha real da extracção por visão —
ou (c) o valor falha a validação que o próprio campo já corre.

Os placeholders e os validadores vivem num ponto único
(`utils/aiConfidence.js`). Escritos ao lado de cada `placeholder=`
divergiriam dele em silêncio, e a divergência fazia o indicador voltar a
aprovar o placeholder.

## 27.25 — Um `ErrorBoundary` que não muda de estado não trata o erro

`LazyChunkErrorBoundary` devolvia `{ hasError: false }` para tudo o que não
fosse um erro de chunk. Isso **não é deixar passar** — é dizer ao React que
tratou. O React volta a renderizar os mesmos filhos, eles levantam outra
vez e, sem fronteira a assumir a falha, **desmonta a árvore inteira**: ecrã
branco.

Aparecia no Voltar do browser porque as rotas têm fronteira própria; o que
chega à fronteira de cima é o que vive FORA delas — contextos, layout,
router — e é isso que uma navegação para trás volta a montar de uma vez.

**Três regras:**
1. **Toda a fronteira renderiza algo.** Nunca `null`, nunca os filhos que
   acabaram de levantar.
2. **A classificação de erros é por sinais ESPECÍFICOS.**
   `includes("Unexpected token")` apanha qualquer `JSON.parse` falhado;
   `includes("Script error")` apanha o erro opaco de outra origem. Uma
   sub-cadeia larga transforma um defeito de dados num recarregamento, e o
   erro real nunca chega ao Sentry. As rejeitadas ficam listadas **com o
   motivo** (`utils/chunkErrors.js`), senão alguém volta a acrescentá-las.
3. **Efeitos secundários não vivem em `getDerivedStateFromError`.** Corre
   na fase de render, pode correr duas vezes em StrictMode e pode correr
   num render descartado. Vão para `componentDidCatch`.

E ao recarregar: `location.assign` e não `replace` — o `replace` apaga a
entrada do histórico e com ela o sítio onde o utilizador estava, ou seja, a
correcção do ecrã branco estragava o Voltar. O cache-busting substitui o
`_t` em vez de o acumular (`?_t=1&_t=2&_t=3` era o que acontecia) e
desiste à segunda: recarregar em ciclo é pior do que mostrar o erro, porque
o utilizador não chega a ler o que aconteceu.

## 27.26 — Uma modal densa: cabeçalho, corpo com scroll, rodapé fixo

`DialogContent` tem `max-h-[90vh] overflow-y-auto` na GRELHA inteira: o
rodapé rola com o conteúdo e, num ecrã baixo, sai de vista. E
`overflow-y:auto` com `overflow-x:visible` faz o CSS promover o eixo X
também a `auto` — qualquer filho mais largo do que a modal cria barra
horizontal e **empurra o botão da direita para fora**.

**Regra para qualquer modal com mais de um ecrã de conteúdo:**
`overflow-hidden flex flex-col` no `DialogContent`, `shrink-0` no cabeçalho
e no rodapé, e `flex-1 min-h-0 overflow-y-auto overflow-x-hidden` no corpo.
O `min-h-0` não é decorativo: sem ele um filho flex recusa-se a encolher
abaixo do seu conteúdo e o `overflow-y` nunca dispara.

No rodapé, `flex-wrap`: num ecrã estreito os botões passam a duas linhas em
vez de um deles sair do ecrã.

## 27.27 — `position: sticky` sem `top` não cola

O valor inicial de `top` é `auto`, e um elemento `sticky` com `top: auto`
**não tem limiar onde colar**: comporta-se como `static`. A classe
`sticky` sozinha não dá erro, não dá aviso do Tailwind e o ecrã parece
normal — só não cola.

```jsx
// ERRADO — e foi o cabeçalho do CRM durante meses
<header className="sticky z-50 h-14" style={isImpersonating ? { top: '48px' } : {}}>

// CERTO — o `top` nos DOIS ramos, por classe
<header className={classesDoCabecalhoFixo({ isImpersonating })}>
```

Três regras:

1. **As classes de posição vivem num ponto único** (`utils/stickyHeader.js`),
   com teste a exigir um `top-*` em **cada** ramo. Era ter `top` só num
   deles que fazia a impersonação ser o único caso funcional.
2. **Classes Tailwind LITERAIS, nunca compostas.** `z-${CAMADA}` não
   existe como texto no ficheiro, o Tailwind não gera a regra e o
   resultado é o mesmo nada que o `top` em falta produzia.
3. **Uma barra fixa fica ABAIXO da gaveta lateral e do seu fundo.** Com
   camadas iguais decide a ordem no DOM, e o cabeçalho vem depois: em
   ecrã estreito tapava o logótipo e o botão de fechar da gaveta.

O jsdom não calcula posicionamento: um `sticky` que cola e um que não
cola renderizam igual. Não há teste de render que apanhe isto — o que se
afirma é a REGRA (no módulo puro) e a LIGAÇÃO (guarda sobre a fonte do
layout).

## 27.28 — Um filtro que vai nos parâmetros TEM de ir na chave de cache

O filtro de etiquetas do Kanban não fazia nada. O fetcher lia
`filters.labels` e montava `params.append('labels', …)`; o hook
destruturava uma lista FIXA de opções, descartava-as e reconstruía um
objecto novo para o `queryFn`. E, por não entrarem na chave, mudar o
filtro **não provocava sequer um pedido**.

```js
// ERRADO — duas listas escritas à mão, em quatro sítios
const { token, consultorFilter = 'all', … } = options;   // sem labels
const filters = { consultor, mediador, … };              // sem labels
useQuery({ queryKey: keys.kanban(filters),               // sem labels
           queryFn: () => fetch(token, { consultorFilter, … }) });  // sem labels

// CERTO — um objecto canónico, e dele saem os DOIS lados
const filters = normalizarFiltros(options);
useQuery({ queryKey: keys.kanban(filters),
           queryFn: () => fetch(token, filters) });
```

O teste é da FORMA e não do filtro: flipar **cada** campo e exigir que
os parâmetros E a chave mudem, com a contraprova de que filtros iguais
dão a mesma chave (senão um valor aleatório passava e destruía a cache a
cada render). Cuidado com `|| 30` sobre um `completedDays` que pode ser
`0`: "sem limite" é falsy e virava "30 dias" em silêncio.

## 27.29 — Um gate de UI lê o papel EFECTIVO, o mesmo que o backend lê

`require_roles` decide pelo cargo efectivo (UCR + `X-Active-Role`). Um
botão escondido por `user.role` dá as duas respostas erradas: a Direção
a trabalhar a partir de um perfil base de consultor não vê o botão, e um
admin de base a agir como consultor vê-o e leva 403.

```jsx
const papelActivo = (effectiveRole || user?.role || "").toLowerCase();
const podeEliminar = MANAGEMENT_ROLES.includes(papelActivo);
```

O teste tem de usar um utilizador cujo `role` do JWT DIFIRA do perfil
activo — com os dois iguais, passa com o defeito presente.

## 27.30 — Uma etiqueta bonita não pode fazer duas coisas parecerem uma

O chip do grupo de empresas mostra `grupo_power_precision` como
"Power Precision". Mas `grupo_power` em vez de `grupo_power_precision`
não dá erro nenhum: cria uma rede nova de uma empresa só e o isolamento
quebra AO CONTRÁRIO (esconde dados de quem os devia ver). Se dois slugs
distintos no mesmo ecrã derem o mesmo rótulo, mostram-se os dois CRUS —
a etiqueta embeleza, nunca unifica.

Duas consequências a manter:

- **"Sem grupo" tem aparência própria.** Uma empresa sem `network_id` é
  uma ILHA; desenhá-la como as outras fazia o estado mais consequente do
  ecrã passar por um campo em branco.
- **Nada de contagens sobre uma PÁGINA.** "Esta rede tem uma empresa só"
  é falso para toda a rede cujas empresas estejam partidas entre páginas,
  e um aviso errado sobre a fronteira de isolamento é pior do que aviso
  nenhum.

## 27.31 — Uma confirmação destrutiva diz o que ARRASTA

Eliminar um registo da Pool faz soft delete em cascata (processo,
documentos, tarefas) quando o cliente é 1.º titular, e apenas DESLIGA a
associação quando é 2.º — o processo do 1.º fica activo. O diálogo
escreve as duas coisas. Um "Tem a certeza?" sem dizer o que arrasta é um
aviso que não informa.

E a mensagem de erro é a DO SERVIDOR: um "Erro ao eliminar" genérico
esconde a diferença entre 403 (permissão) e 404 (já não existe), que é
exactamente o que quem está no ecrã precisa de saber.

## 27.32 — Navegação Próximo/Anterior: o mecanismo é um só

A Pool navega entre CLIENTES e os Detalhes entre PROCESSOS, e é o mesmo
`ProcessNavigator` com os rótulos parametrizados — "Processo anterior"
num diálogo de cliente seria mentira para um leitor de ecrã, e uma
segunda cópia do componente divergiria. As regras que se mantêm:

- **um lado sem vizinho é um botão DESACTIVADO, não ausente** (o controlo
  não pode saltar de sítio a meio de uma revisão);
- **sem contexto, sem setas**: quem chega por notificação (`?clientId=`)
  não veio de listagem nenhuma, e inventar-lhe uma vizinhança promete uma
  ordem que não existe;
- **o total é o da lista EM MÃO.** A Pool pede `limit=100` sem paginação:
  dizer "12 / 243" prometia um 101.º que a seta nunca alcança.

## 27.33 — Uma etiqueta que explica uma regra muda COM a regra

O `Sub35Badge` prometia, no `title`, «Titular com menos de 36 anos». Com
a regra estrita do Lote 5 — o apoio exige que **todos** os compradores
cumpram o requisito — esse texto passou a prometer menos do que a
condição exige, e é o texto que o consultor lê antes de falar com o
cliente. A diferença entre «o titular» e «todos os titulares» é a
diferença entre uma oportunidade e uma isenção de IMT recusada pela
Autoridade Tributária em cima da escritura.

Duas regras:

- **o texto da explicação vive ao lado do componente, num ponto único**
  (`EXPLICACAO_SUB35`), e o teste afirma o seu CONTEÚDO, não só a sua
  presença. Um `toBeTruthy()` sobre o `title` não distingue uma
  explicação certa de uma desactualizada;
- **quem decide continua a ser o servidor.** O componente nunca recalcula
  a regra para a "confirmar" — duas contas da mesma regra divergem no dia
  de um aniversário. Ele lê a flag e explica-a.

## 27.34 — Um botão que não pode diz-se, não desaparece

O registo canónico de capacidades (`models/permissions.ROLE_CAPABILITY_DEFAULTS`)
já dizia que o perfil `indexacao` não cria processos. O ecrã é que não o
consultava: o botão "Novo Processo" aparecia a todos e quem não podia descobria
pelo erro.

**A regra:** `BotaoComPermissao` com `modo="cadeado"` (omissão) — o botão fica
VISÍVEL, desactivado, com cadeado e um tooltip que DIZ o motivo. `modo="ocultar"`
reserva-se para acções cuja mera existência revela algo (gestão, eliminação em
massa) e para barras onde um botão morto é só ruído.

Porque é que a omissão é o cadeado e não a ocultação: um ecrã que muda de forma
a cada perfil é impossível de apoiar ao telefone, e esconder ensina menos do que
explicar. Um cadeado sem motivo, por outro lado, manda o utilizador perguntar a
alguém — por isso `motivoDoBloqueio` nunca devolve vazio.

**Três detalhes do componente que não se podem perder:**

1. **O tooltip traz o seu próprio `TooltipProvider`.** Não há provider global
   neste projecto; um componente que dependa de o chamador o ter funciona numa
   página e falha noutra — sem erro, só sem tooltip.
2. **O `disabled` vai no botão**, não um `pointer-events: none` no contentor:
   um contentor sem eventos tira o tooltip E o foco do teclado.
3. **Um `<button disabled>` não emite eventos de rato**, logo o `TooltipTrigger`
   envolve-o num `<span>` — sem isso o tooltip nunca abriria.

## 27.35 — Capacidades: registo POSITIVO, pelo papel EFECTIVO, e sem contrato não se esconde

O gate antigo da Pool era `userRole !== "indexacao"`. Dois defeitos numa linha:

* **lista de EXCLUSÃO** — um perfil novo sem direito a criar processos passava a
  ver o botão, porque a exclusão não o conhece;
* **papel do JWT** — quem tem perfil base de indexação a agir COMO consultor não
  via o botão, embora a rota (que lê o papel EFECTIVO) o deixe passar. É a forma
  do `history._is_stealth_user` e do botão de eliminar cliente: duas noções de
  papel no mesmo caminho dão as duas respostas erradas.

Hoje: `podeFazer(user, CAPACIDADE, effectiveRole)` (`utils/capacidades.js`), com
as capacidades a vir do `/auth/me` em **`capabilities_por_papel`** — um mapa por
cargo, porque o perfil activo muda sem recarregar a sessão. **Nunca duplicar a
tabela de defaults no frontend:** uma cópia divergiria em silêncio.

**E a decisão que parece ao contrário: sem contrato, deixa-se passar.** Uma
sessão anterior ao deploy não tem `capabilities_por_papel`; falhar fechado aí
esconderia TODOS os botões a TODOS os utilizadores, um ecrã sem botões não
produz erro nenhum e parece que a aplicação está partida. A parede é o
`exigir_capacidade` do servidor, que falha FECHADO. `capacidadesDoPapel` devolve
`null` para "não sei" e `{}` para "sei que não tem nenhuma" — tratá-los como o
mesmo era o erro.

## 27.36 — Arrastar ficheiros: três armadilhas, um módulo

`utils/dropzone.js` (puro) + `components/shared/Dropzone.jsx`.

1. **`onDragLeave` dispara ao passar sobre um FILHO.** Uma zona que só faça
   `setDragOver(false)` no leave pisca enquanto o rato atravessa o conteúdo, e
   com o realce apagado o utilizador larga sem saber se vai acertar. Conta-se
   entradas e saídas (`arrastoEntrou`/`arrastoSaiu`).
2. **O arrasto do SISTEMA e o arrasto INTERNO são eventos diferentes com o
   mesmo nome.** No separador Documentos, arrastar entre categorias MOVE; do
   Finder, ENVIA. `eArrastoDeFicheiros` distingue-os pelo `dataTransfer.types`
   conter `"Files"` — sem esta guarda, ligar o upload por arrasto partia o mover
   que já existia.
3. **O botão filtra tipos e o arrasto não.** O `<input>` tem `accept`; o caminho
   do `drop` não passa por ele, e largar um `.exe` ia direito ao upload. A lista
   de tipos é UMA constante por superfície, usada pelo `accept` E pelo filtro do
   arrasto — em dois sítios divergiriam, e a divergência tem uma forma concreta:
   o botão recusa e o arrasto deixa passar.

**A ordem dos callbacks é significativa:** `onFicheiros` ANTES de
`onRecusados`. Ao contrário, um largar MISTO apagava o aviso — quem trata os
aceites limpa o estado do envio anterior, e esse "limpar" apagava a recusa
acabada de escrever. Com esta ordem, um largar limpo também limpa um aviso
antigo.

**E a mensagem de recusa NOMEIA os ficheiros.** No Portal ela vive em estado
PRÓPRIO e não no `result`: a forma do `result` serve o resumo do lote e os
crachás de sucesso, e nenhum ramo do render mostrava uma mensagem de falha —
escrever lá era escrever para ninguém.

## 27.37 — O nome que se MOSTRA nunca é o que se USA para operar

Desde que a identidade documental deriva do ID, a pasta de um cliente novo
chama-se `11111111-…`. O backend resolve o nome real e envia-o em
`display_name`; `utils/pastaS3.js` é o ponto único do lado do ecrã.

`path` e `name` continuam a ser a autoridade de TODAS as operações (entrar,
renomear, apagar, descarregar). Mostrar uma coisa e operar noutra é a forma
discreta de uma parede não valer nada.

**Três regras:**

* **o nome cru fica à vista** quando foi substituído — quem precisa do uuid (um
  log, um pedido de suporte) não pode perdê-lo;
* **a pesquisa casa contra os dois** (visível e cru), senão o uuid deixa de ser
  pesquisável no dia em que o nome passa a aparecer;
* **duas fichas na mesma pasta não escolhem um nome** — mostra-se o nome cru e
  um crachá com a contagem. Escolher um faria a colisão parecer resolvida.

## 27.38 — A forma de uma lista do servidor normaliza-se UMA vez, não em cada leitor

O `KanbanBoard` lia `column.processes.filter(...)` em quatro sítios **sem**
guarda e com `|| []` em dois. Os dois protegidos eram os do arrasto, que só
correm depois de um movimento local — a metade rara estava defendida e a normal
não. Uma coluna sem a chave `processes` dava `Cannot read properties of undefined
(reading 'filter')`: ecrã em branco na página de entrada do sistema.

E não era hipotético: a fusão das duas consultas do quadro substitui a coluna
**inteira** pela da consulta de concluídos, pelo que a forma da coluna fundida
passa a ser a que o OUTRO endpoint devolver.

**A regra:** quando uma resposta do servidor atravessa vários leitores, a forma
garante-se num ponto único à entrada (`utils/kanbanColunas.js`) e ninguém a
seguir volta a perguntar. Seis cópias da mesma guarda divergem sem dar erro, e
foi assim que quatro delas ficaram sem ela.

**Dois corolários:**

* **`Array.isArray`, nunca `|| []`.** Um objecto é *truthy*, logo `x || []`
  devolve o objecto e o erro muda de sítio em vez de desaparecer (§ 27.7).
* **Um contador DERIVA da lista.** O `count` vem calculado do servidor, mas
  depois do arrasto optimista e do filtro em memória deixa de corresponder ao
  ecrã. Um contador que contradiz a coluna é o rodapé a discordar da lista.

## 27.39 — O nome acessível de um botão bloqueado DIZ qual é a acção

O `BotaoComPermissao` (§ 27.34) montava o `aria-label` com
`typeof children === "string" ? children : "Acção"`. **`children` quase nunca é
uma string:** o padrão desta casa é ícone + rótulo, logo um array. O resultado era
que todos os botões bloqueados do sistema se anunciavam como
«Acção — sem permissão» — um leitor de ecrã não distinguia «Novo Processo» de
«Exportar Excel», e `getByRole("button", { name: /exportar/i })` não encontrava
nada.

As duas consequências são a mesma regra: **um botão sem nome acessível é um bug
de acessibilidade e um teste impossível.** O rótulo sai do TEXTO dos filhos
(`textoDosFilhos` percorre a árvore); o recuo genérico fica só para um botão sem
texto nenhum, e tem contraprova.

## 27.40 — A mesma acção em dois sítios do ecrã tem de ter a mesma regra

O Kanban tem dois botões «Exportar Excel»: o da página e o do cabeçalho do
quadro. O fecho dos botões fantasma (Lote 6) gatiu o primeiro e **não viu** o
segundo — que não tinha gate nenhum e exporta NIF, telefone e email. Um perfil
sem a capacidade via um cadeado ao lado de um botão a funcionar.

É o «menu e rotas têm de concordar» (§ 27.9) aplicado a botões: a mesma acção
desenhada em dois sítios diverge sem dar erro. **Ao gatir uma acção, inventariar
TODOS os sítios que a desenham** — e o teste afirma sobre `getAllByRole`, nunca
sobre `getByRole`, senão prova metade.

O papel desce por **prop** (página → contentor → apresentação) e não de um
`useAuth` no componente de apresentação: o cabeçalho apresenta, quem conhece o
contexto é o contentor (§ 20). E é sempre o papel **EFECTIVO**, porque o gate do
outro sítio também é — dois gates com noções de papel diferentes dão as duas
respostas erradas.

## 27.41 — Um nome no ecrã sem ligação é texto morto

O calendário geral recebia `client_name` em cada evento e mostrava-o num
parágrafo do painel do dia. O utilizador lia o nome do cliente, abria a pesquisa
e procurava-o à mão — o ecrã sabia a resposta e não a dava.

**A regra:** quando o ecrã mostra o nome de uma entidade que tem ficha, mostra
também o caminho para ela. E separa-se em duas peças, como o `nomeVisivel` do
Explorador (§ 27.37): **o que se MOSTRA** (`etiquetaDoCliente`) e **para onde se
VAI** (`rotaDaFicha`).

**Três corolários:**

* **Sem destino não se desenha a ligação.** `rotaDaFicha` devolve `null` e quem
  recebe `null` renderiza texto — um link que não leva a lado nenhum é pior do
  que nenhum link.
* **Um recuo do servidor não é um nome.** O backend escreve `"Evento Geral"` e
  `"Ausência"` em `client_name` quando não há processo; mostrá-los punha «Evento
  Geral» onde devia estar o nome de uma pessoa. Os recuos conhecidos vivem numa
  lista de exclusão no utilitário, não em cada ecrã.
* **A ligação fica FORA do botão da linha.** Um `<button>` dentro de outro
  `<button>` é HTML inválido e o clique interior deixa de ser alcançável pelo
  teclado.

## 27.42 — Num ecrã de equipa, o rótulo responde «de quem é», não «quem trata»

O chip do calendário mostrava `[Responsável] Título`. Com doze «Escritura» num
dia, o prefixo do responsável não distingue nada: a pergunta de quem olha para
uma agenda de equipa é de QUEM é o evento.

**A regra:** o rótulo muda com a vista. Em vista de equipa o cliente vem primeiro
(`Cliente · Título`); na agenda pessoal fica só o título, porque o utilizador já
sabe que é dele e o cliente aparece no painel do dia — repeti-lo gasta a largura
da célula. E **não se repete o nome quando o título já o contém** («Escritura Ana
Martins» não vira «Ana Martins · Escritura Ana Martins»).

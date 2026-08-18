# Frontend Guidelines — PowerCell CRM

Normas de UX/UI e convenções técnicas para o frontend (React 19 + Vite + Tailwind CSS 4 + Shadcn UI). Ler em conjunto com `ARCHITECTURE.md` (padrões gerais) e `AGENTS.md` (notas operacionais para agentes).

---

## 1. Progressive Disclosure — norma absoluta

**Regra**: nunca mostrar tudo de uma vez numa página densa. Esconder complexidade secundária atrás de separadores, dialogs/sheets ou accordions, e mostrar só os dados/ações críticos por defeito.

Aplicações concretas já em produção:

| Onde | Como |
|---|---|
| `ProcessDetails` — separador Resumo | Só dados críticos do processo (dados do cliente, financeiros, imóvel, crédito) — **sem** atividades/histórico |
| `ProcessDetails` — separador Histórico | Timeline + Atividades + "Filme da Lead" (auditoria unificada) — tudo o que é cronológico, fora do fluxo de edição |
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





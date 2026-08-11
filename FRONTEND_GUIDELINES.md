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


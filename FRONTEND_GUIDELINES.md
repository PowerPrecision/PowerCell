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

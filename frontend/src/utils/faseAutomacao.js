/**
 * Automação ao ENTRAR numa fase (Bloco 3, ponto 12) — regras puras do editor.
 *
 * O servidor guarda duas coisas por fase, cada uma com TRÊS estados:
 *   • `null`  → não configurado: herda o por-omissão (que só existe para a
 *               saída da Index);
 *   • `[]`    → configurado como «nada»;
 *   • lista   → configurado.
 * `null` e `[]` são respostas diferentes e o editor mostra a diferença: um
 * interruptor «Personalizar» por secção. Desligá-lo envia `null` (volta a
 * herdar); ligá-lo sem nada dentro envia `[]`.
 *
 * Os valores numéricos vivem em TEXTO no estado (estado numérico num
 * `<input>` faz reaparecer o `0` a cada tecla) e convertem-se no fim.
 */

/** Tem de coincidir com `models/workflow.py`. */
export const MAXIMO_DE_MODELOS_POR_FASE = 20;
export const MAXIMO_DE_DIAS = 365;
export const MAXIMO_DO_TITULO = 120;

export const PAPEIS_ATRIBUIVEIS = [
  { value: "consultor", label: "Consultor" },
  { value: "intermediario", label: "Intermediário" },
];

export const PRIORIDADES = ["Alta", "Média", "Baixa"];

export const RESPONSAVEIS = [
  { value: "todos", label: "Consultor e intermediário" },
  { value: "consultor", label: "Só o consultor" },
  { value: "intermediario", label: "Só o intermediário" },
];

export const DESCRICAO_DA_OMISSAO =
  "Sem personalização, a saída da Index atribui consultor e intermediário e cria duas tarefas de arranque; as restantes fases não fazem nada.";

export const automacaoVazia = () => ({ papeis: null, modelos: null });

export const modeloVazio = () => ({
  id: undefined,
  title: "",
  priority: "Média",
  due_in_days: "",
  assigned_role: "todos",
});

const validosOu = (valor, permitidos, omissao) =>
  permitidos.includes(valor) ? valor : omissao;

/** Do que o servidor devolve para o estado do formulário. */
export const automacaoDaFase = (fase) => {
  const papeis = Array.isArray(fase?.auto_assign_roles)
    ? fase.auto_assign_roles.filter((p) => PAPEIS_ATRIBUIVEIS.some((o) => o.value === p))
    : null;
  const modelos = Array.isArray(fase?.task_templates)
    ? fase.task_templates.map((m) => ({
        id: m?.id,
        title: typeof m?.title === "string" ? m.title : "",
        priority: validosOu(m?.priority, PRIORIDADES, "Média"),
        due_in_days:
          Number.isInteger(m?.due_in_days) && m.due_in_days >= 0 ? String(m.due_in_days) : "",
        assigned_role: validosOu(
          m?.assigned_role, RESPONSAVEIS.map((r) => r.value), "todos",
        ),
      }))
    : null;
  return { papeis, modelos };
};

/** Mensagens a mostrar antes de gravar (lista vazia = pode gravar). */
export const errosDaAutomacao = (estado) => {
  const erros = [];
  const modelos = Array.isArray(estado?.modelos) ? estado.modelos : [];
  if (modelos.length > MAXIMO_DE_MODELOS_POR_FASE) {
    erros.push(`No máximo ${MAXIMO_DE_MODELOS_POR_FASE} tarefas por fase.`);
  }
  modelos.forEach((m, i) => {
    const n = i + 1;
    if (!String(m.title || "").trim()) {
      erros.push(`Tarefa ${n}: o título não pode ficar vazio.`);
    } else if (String(m.title).length > MAXIMO_DO_TITULO) {
      erros.push(`Tarefa ${n}: o título tem mais de ${MAXIMO_DO_TITULO} caracteres.`);
    }
    const dias = String(m.due_in_days ?? "").trim();
    if (dias !== "" && !(/^\d+$/.test(dias) && Number(dias) <= MAXIMO_DE_DIAS)) {
      erros.push(`Tarefa ${n}: o prazo é um número de dias entre 0 e ${MAXIMO_DE_DIAS}.`);
    }
  });
  return erros;
};

/**
 * Do formulário para o servidor. Devolve SEMPRE as duas chaves: `null` é a
 * instrução de voltar a herdar, e deixar a chave de fora não toca em nada.
 */
export const payloadDaAutomacao = (estado) => ({
  auto_assign_roles: Array.isArray(estado?.papeis) ? [...estado.papeis] : null,
  task_templates: Array.isArray(estado?.modelos)
    ? estado.modelos.map((m) => {
        const dias = String(m.due_in_days ?? "").trim();
        return {
          ...(m.id ? { id: m.id } : {}),
          title: String(m.title || "").trim(),
          priority: m.priority,
          due_in_days: dias === "" ? null : Number(dias),
          assigned_role: m.assigned_role,
        };
      })
    : null,
});

/** Para a criação: o que é `null` não se envia (a fase nasce a herdar). */
export const payloadDaAutomacaoNaCriacao = (estado) => {
  const { auto_assign_roles, task_templates } = payloadDaAutomacao(estado);
  return {
    ...(auto_assign_roles !== null ? { auto_assign_roles } : {}),
    ...(task_templates !== null ? { task_templates } : {}),
  };
};

/** Um resumo curto para a lista de fases. */
export const resumoDaAutomacao = (fase) => {
  const { papeis, modelos } = automacaoDaFase(fase);
  if (papeis === null && modelos === null) return null;
  const partes = [];
  if (papeis !== null) {
    partes.push(papeis.length ? `atribui ${papeis.join(" + ")}` : "não atribui");
  }
  if (modelos !== null) {
    partes.push(
      modelos.length === 1 ? "1 tarefa" : modelos.length ? `${modelos.length} tarefas` : "sem tarefas",
    );
  }
  return partes.join(" · ");
};

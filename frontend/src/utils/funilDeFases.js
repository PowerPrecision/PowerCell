/**
 * funilDeFases — o funil do dashboard como VISTA do motor de workflow.
 *
 * O DEFEITO QUE ISTO FECHA (Lote 5, P0 — "UI de Fases Mentirosa")
 *   `FUNNEL_MACRO` vivia dentro do `ConsultorDashboard`: quatro grupos
 *   com os nomes das fases escritos à mão, e a contagem era
 *   `list.filter((p) => statusSet.has(p.status)).length` por grupo.
 *
 *   1. Um processo numa fase que nenhum grupo listasse não contava para
 *      lado nenhum. As fases são CONFIGURÁVEIS pelo admin e nenhuma das
 *      que ele crie entra nestas listas: a soma das colunas ficava
 *      abaixo do total de processos, sem nada no ecrã a dizê-lo. Um
 *      consultor com processos numa fase nova via o funil a dizer que
 *      não tinha trabalho.
 *   2. `escritura` estava em DOIS grupos ("Aprovado" e "Concluído").
 *
 * A REGRA
 *   O funil agrupa, não decide o que existe. Nenhum processo pode
 *   desaparecer dele e nenhum pode ser contado duas vezes. O que não
 *   couber nos grupos conhecidos cai num grupo "Outras fases" — que só
 *   aparece quando tem conteúdo, para não ser ruído permanente.
 *
 * PORQUE É QUE OS GRUPOS CONTINUAM A SER UMA LISTA
 *   O motor não tem campo de macro-fase: `workflow_statuses` sabe
 *   `order`, `label` e `color`, não "isto é análise". Inventar o
 *   agrupamento a partir da ordem seria outra mentira, só que com ar
 *   automático. Os grupos ficam como CLASSIFICAÇÃO CONHECIDA; o que a
 *   classificação não cobre é dito, em vez de ser deitado fora.
 *
 * @module utils/funilDeFases
 */

/** Macro-fases conhecidas. Uma fase pertence no MÁXIMO a um grupo. */
export const MACRO_FASES = [
  {
    key: "novo",
    label: "Novo",
    statuses: ["clientes_espera", "fase_documental", "fase_documental_ii", "documentacao"],
    color: "hsl(var(--chart-4))",
  },
  {
    key: "analise",
    label: "Em Análise",
    statuses: [
      "enviado_bruno", "enviado_luis", "enviado_bcp_rui", "entradas_precision",
      "fase_bancaria", "fase_visitas", "analise", "pre_aprovacao",
    ],
    color: "hsl(var(--chart-1))",
  },
  {
    key: "aprovado",
    label: "Aprovado",
    statuses: [
      "ch_aprovado", "fase_escritura", "escritura_agendada",
      "credito_aprovado", "pedido_avaliacao", "avaliacao", "cpcv", "minuta",
      "aprovado",
    ],
    color: "hsl(var(--chart-2))",
  },
  {
    key: "concluido",
    label: "Concluído",
    // `escritura` estava TAMBÉM em "Aprovado": o mesmo processo era
    // contado conforme a ordem de iteração. Fica aqui, que é o desfecho.
    statuses: ["concluidos", "concluido", "escritura"],
    color: "hsl(var(--chart-3))",
  },
];

const CHAVE_OUTRAS = "outras";
const SEM_ESTADO = "__sem_estado__";

/**
 * Agrupa processos pelas macro-fases, sem perder nenhum.
 *
 * @param {Array} [processos] - `[{status}]`.
 * @param {Array} [fasesDoMotor] - `workflow_statuses`, para dar nome às
 *   fases que caem em "Outras". Opcional: sem ela usa o nome técnico.
 * @returns {Array<{key, name, value, color, statuses}>}
 */
export function agruparEmFunil(processos, fasesDoMotor) {
  const lista = Array.isArray(processos) ? processos : [];

  const grupoDaFase = new Map();
  for (const grupo of MACRO_FASES) {
    for (const fase of grupo.statuses) {
      // Primeiro grupo a declarar a fase fica com ela — e há um teste a
      // afirmar que nenhuma é declarada duas vezes.
      if (!grupoDaFase.has(fase)) grupoDaFase.set(fase, grupo.key);
    }
  }

  const contagens = new Map(MACRO_FASES.map((g) => [g.key, 0]));
  const fasesForaDeGrupo = new Set();
  let foraDeGrupo = 0;

  for (const processo of lista) {
    const estado = processo?.status || SEM_ESTADO;
    const chave = grupoDaFase.get(estado);
    if (chave) {
      contagens.set(chave, contagens.get(chave) + 1);
    } else {
      foraDeGrupo += 1;
      if (estado !== SEM_ESTADO) fasesForaDeGrupo.add(estado);
    }
  }

  const funil = MACRO_FASES.map((grupo) => ({
    key: grupo.key,
    name: grupo.label,
    value: contagens.get(grupo.key),
    color: grupo.color,
    statuses: grupo.statuses,
  }));

  if (foraDeGrupo === 0) return funil;

  const etiquetas = new Map(
    (Array.isArray(fasesDoMotor) ? fasesDoMotor : [])
      .filter((f) => f && f.name)
      .map((f) => [f.name, f.label || f.name]),
  );
  const nomes = [...fasesForaDeGrupo].map((f) => etiquetas.get(f) || f);
  const sufixo = nomes.length > 0 ? ` (${nomes.slice(0, 3).join(", ")}${nomes.length > 3 ? "…" : ""})` : "";

  funil.push({
    key: CHAVE_OUTRAS,
    name: `Outras fases${sufixo}`,
    value: foraDeGrupo,
    color: "hsl(var(--muted-foreground))",
    statuses: [...fasesForaDeGrupo],
  });
  return funil;
}

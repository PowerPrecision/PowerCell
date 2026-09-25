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
 * O MOTOR PASSOU A TER O CAMPO (Épico 10, Parte 2)
 *   `workflow_statuses.macro_fase` — enum fechado
 *   (`novo|analise|aprovado|concluido|perdido`), editável pelo
 *   administrador no WorkflowEditor. A lista de fases SAIU deste
 *   ficheiro: aqui ficam só as etiquetas e as cores dos cinco grupos.
 *
 *   O mapa `CLASSIFICACAO_DE_RECURSO` sobrevive como RECURSO para uma
 *   fase que o motor ainda não classificou, e perde sempre para ele —
 *   a mesma regra dos aliases da timeline. Não cresce: uma fase nova
 *   classifica-se na UI.
 *
 *   O que continua sem grupo aparece em "Outras fases", com o nome à
 *   vista. `null` é uma resposta; inventar um grupo seria pior.
 *
 * @module utils/funilDeFases
 */

/**
 * Os grupos do funil, pela ordem em que o negócio acontece.
 *
 * A LISTA DE FASES SAIU DAQUI (Épico 10, Parte 2). Cada grupo tem só
 * identidade visual — quem diz a que grupo pertence uma fase é o MOTOR,
 * pelo campo `macro_fase` que o administrador edita no WorkflowEditor.
 */
export const MACRO_FASES = [
  { key: "novo", label: "Novo", color: "hsl(var(--chart-4))" },
  { key: "analise", label: "Em Análise", color: "hsl(var(--chart-1))" },
  { key: "aprovado", label: "Aprovado", color: "hsl(var(--chart-2))" },
  { key: "concluido", label: "Concluído", color: "hsl(var(--chart-3))" },
  { key: "perdido", label: "Perdido", color: "hsl(var(--chart-5))" },
];

/**
 * Classificação de RECURSO, para uma fase que o motor ainda não
 * classificou — instalação que não correu o backfill, ou fase criada
 * antes dele. Perde SEMPRE para o `macro_fase` do motor, e não cresce:
 * uma fase nova classifica-se na UI, não aqui.
 */
const CLASSIFICACAO_DE_RECURSO = {
  clientes_espera: "novo",
  fase_documental: "novo",
  fase_documental_ii: "novo",
  documentacao: "novo",
  enviado_bruno: "analise",
  enviado_luis: "analise",
  enviado_bcp_rui: "analise",
  entradas_precision: "analise",
  fase_bancaria: "analise",
  fase_visitas: "analise",
  analise: "analise",
  pre_aprovacao: "analise",
  renegociacao: "analise",
  pausa_cliente: "analise",
  ch_aprovado: "aprovado",
  fase_escritura: "aprovado",
  escritura_agendada: "aprovado",
  credito_aprovado: "aprovado",
  pedido_avaliacao: "aprovado",
  avaliacao: "aprovado",
  cpcv: "aprovado",
  minuta: "aprovado",
  aprovado: "aprovado",
  concluidos: "concluido",
  concluido: "concluido",
  escritura: "concluido",
  desistencias: "perdido",
  desistencia: "perdido",
  desistido: "perdido",
  cancelado: "perdido",
  perdido: "perdido",
  arquivo: "perdido",
};

const CHAVES_VALIDAS = new Set(MACRO_FASES.map((g) => g.key));

/**
 * A que grupo pertence uma fase. O motor ganha sempre.
 *
 * Um `macro_fase` fora do enum é ignorado — o backend já o recusa ao
 * gravar, mas um documento antigo pode trazê-lo, e um grupo inventado
 * partiria o funil com ar de categoria legítima.
 */
function grupoDoEstado(estado, fasesDoMotor) {
  const doMotor = (Array.isArray(fasesDoMotor) ? fasesDoMotor : []).find(
    (f) => f && f.name === estado,
  );
  const declarada = doMotor?.macro_fase;
  if (declarada && CHAVES_VALIDAS.has(declarada)) return declarada;
  return CLASSIFICACAO_DE_RECURSO[estado] || null;
}

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

  const contagens = new Map(MACRO_FASES.map((g) => [g.key, 0]));
  const fasesPorGrupo = new Map(MACRO_FASES.map((g) => [g.key, new Set()]));
  const fasesForaDeGrupo = new Set();
  let foraDeGrupo = 0;

  // Memoiza por ESTADO: uma lista de 1000 processos tem dezenas de
  // estados distintos, e `grupoDoEstado` percorre as fases do motor.
  const cache = new Map();

  for (const processo of lista) {
    const estado = processo?.status || SEM_ESTADO;
    if (!cache.has(estado)) {
      cache.set(estado, estado === SEM_ESTADO ? null : grupoDoEstado(estado, fasesDoMotor));
    }
    const chave = cache.get(estado);
    if (chave) {
      contagens.set(chave, contagens.get(chave) + 1);
      fasesPorGrupo.get(chave).add(estado);
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
    statuses: [...fasesPorGrupo.get(grupo.key)],
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

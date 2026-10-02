/**
 * Os filtros do Kanban: UM ponto para os parâmetros E para a chave de
 * cache (Lote 4, ponto 1).
 *
 * O DEFEITO QUE ISTO FECHA — o filtro de etiquetas do Kanban não fazia
 * absolutamente nada.
 *
 * `useKanbanQuery` e `useKanbanCompletedQuery` tinham, cada um, um
 * `fetchX(token, filters)` que lê `filters.labels` e monta
 * `params.append('labels', …)`. Mas os dois hooks fazem isto:
 *
 *     const { token, consultorFilter = 'all', … } = options;   // sem labels
 *     const filters = { consultor, mediador, …, viewMode };    // sem labels
 *     useQuery({
 *       queryKey: queryKeys.processes.kanban(filters),          // sem labels
 *       queryFn: () => fetchKanbanData(token, { consultorFilter, … }),
 *     });                                                      // sem labels
 *
 * O `KanbanBoard` passa `labels` nas opções, o hook destrutura uma lista
 * FIXA, descarta-as e reconstrói um objecto novo para o `queryFn`. A
 * canalização está cortada ao meio: o fetcher sabe enviar e nunca
 * recebe. E há um segundo defeito por cima, do mesmo corte: como as
 * etiquetas também não entram na **chave**, mudar o filtro não invalida
 * nada — o React Query serve a mesma cache e não há nem pedido. Não há
 * filtragem local de etiquetas em sítio nenhum, logo o efeito era zero.
 *
 * A LIÇÃO, e a razão de este módulo existir: **um filtro que vai nos
 * parâmetros tem de ir na chave de cache.** São duas listas escritas à
 * mão em quatro sítios, e duas listas escritas à mão divergem — foi o
 * que aconteceu aqui e é a forma dos campos canónicos de atribuição do
 * Lote 5 noutro eixo. Aqui ambas derivam de `normalizarFiltros`, e há um
 * teste a flipar CADA filtro e a exigir que os parâmetros E a chave
 * mudem.
 */

/** Um filtro de atribuição desligado. `none` = "sem ninguém atribuído". */
const TODOS = "all";

/**
 * A forma canónica dos filtros do quadro.
 *
 * Tudo o que o servidor sabe filtrar entra aqui. Um filtro que fique
 * fora deste objecto é um filtro que não chega ao servidor — não há
 * outro caminho.
 */
export function normalizarFiltros(opcoes = {}) {
  const etiquetas = (Array.isArray(opcoes.labels) ? opcoes.labels : [])
    .map((e) => String(e || "").trim())
    .filter(Boolean);

  return {
    consultor: opcoes.consultorFilter || TODOS,
    mediador: opcoes.mediadorFilter || TODOS,
    indexacao: opcoes.indexacaoFilter || TODOS,
    parceiro: opcoes.parceiroFilter || TODOS,
    // `completedDays` pode ser 0 ("sem limite"), que é falsy: `|| 30`
    // transformaria "sem limite" em "30 dias" em silêncio.
    completedDays:
      opcoes.completedDays === undefined || opcoes.completedDays === null
        ? 30
        : opcoes.completedDays,
    labels: etiquetas,
    labelsLogic: opcoes.labelsLogic === "AND" ? "AND" : "OR",
    sub35: opcoes.sub35 === true,
    viewMode: "all",
  };
}

/**
 * `URLSearchParams` para `GET /kanban`, a partir dos filtros canónicos.
 */
export function parametrosDoKanban(filtros) {
  const f = filtros || {};
  const params = new URLSearchParams();

  // view_mode=all: processos activos + concluídos/desistências.
  params.append("view_mode", f.viewMode || "all");
  // Visão global: o âmbito por cargo e por Rede é decidido no servidor.
  params.append("show_all", "true");

  if (f.completedDays !== undefined && f.completedDays !== null) {
    params.append("completed_days", String(f.completedDays));
  }

  for (const [chave, valor] of [
    ["consultor_id", f.consultor],
    ["mediador_id", f.mediador],
    ["indexacao_id", f.indexacao],
    ["parceiro_id", f.parceiro],
  ]) {
    if (valor && valor !== TODOS) params.append(chave, valor);
  }

  // Ponto 15 — etiquetas. O Kanban tem construtor de query SEPARADO no
  // backend (foi assim que ficou de fora do isolamento no Lote 4), por
  // isso o filtro tem de ser ligado de propósito.
  for (const etiqueta of f.labels || []) {
    params.append("labels", etiqueta);
  }
  // A lógica E/OU só faz diferença com mais do que uma etiqueta.
  if ((f.labels || []).length > 1 && f.labelsLogic === "AND") {
    params.append("labels_logic", "AND");
  }

  // Ponto 1 — Sub35. Só `true` é enviado: o servidor recusa o `false`
  // de propósito (ver `services/sub35.py`).
  if (f.sub35 === true) params.append("sub35", "true");

  return params;
}

/**
 * A chave de cache — DERIVADA dos mesmos filtros.
 *
 * Não é um alias inútil: é o ponto onde se garante que a chave e os
 * parâmetros não podem divergir. Tudo o que `parametrosDoKanban` lê está
 * neste objecto, por construção.
 */
export function chaveDeFiltros(filtros) {
  const f = normalizarFiltros({
    consultorFilter: filtros?.consultor,
    mediadorFilter: filtros?.mediador,
    indexacaoFilter: filtros?.indexacao,
    parceiroFilter: filtros?.parceiro,
    completedDays: filtros?.completedDays,
    labels: filtros?.labels,
    labelsLogic: filtros?.labelsLogic,
    sub35: filtros?.sub35,
  });
  return f;
}

/** Os nomes dos filtros, para quem precise de os enumerar (testes). */
export const CAMPOS_DE_FILTRO = [
  "consultor",
  "mediador",
  "indexacao",
  "parceiro",
  "completedDays",
  "labels",
  "labelsLogic",
  "sub35",
];

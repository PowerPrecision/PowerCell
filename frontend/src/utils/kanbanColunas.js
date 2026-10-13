/**
 * A forma de uma coluna do Kanban — normalizada UMA vez (Lote 7, D-20).
 *
 * O DEFEITO QUE O TESTE DE PÁGINA APANHOU
 * =======================================
 * `KanbanBoard` lia `column.processes.filter(...)` em quatro sítios SEM
 * guarda (`filteredColumns`, o achatamento dos cartões, a contagem
 * visível, e o `KanbanColumn`) e COM guarda (`|| []`) em dois — os dois
 * que só correm depois de um arrasto (`optimisticColumns` devolve
 * `columns` intacto quando não há movimentos locais). Era a metade raríssima
 * a estar protegida e a normal a não estar: uma coluna sem a chave
 * `processes` dava `Cannot read properties of undefined (reading 'filter')`
 * e ecrã em branco no quadro, que é a página de entrada do sistema.
 *
 * E há um caminho real que o produz: o merge das duas consultas substitui
 * a coluna INTEIRA pela da consulta de concluídos
 * (`completedMap.get(col.name)`). A partir desse momento a forma da coluna
 * é a que o OUTRO endpoint devolver — duas respostas, uma só suposição.
 *
 * A saída não é um sétimo `|| []`: é um ponto único. Seis cópias de uma
 * guarda divergem sem dar erro, e foi exactamente assim que quatro delas
 * ficaram sem ela.
 *
 * `count` DERIVA da lista e não se acredita no servidor
 * ====================================================
 * O `count` vem calculado do backend, mas depois do arrasto optimista e do
 * filtro em memória deixa de corresponder ao que está no ecrã. Um
 * contador que contradiz a coluna é a forma do rodapé a discordar da
 * lista — logo deriva-se sempre do comprimento.
 */

/** Uma coluna com a forma garantida: `processes` é sempre um array. */
export function normalizarColuna(coluna) {
  if (!coluna || typeof coluna !== "object") return null;
  // `Array.isArray` e não `|| []`: um objecto é truthy, logo `x || []`
  // devolve o objecto e o erro muda de sítio em vez de desaparecer (é a
  // lição da colisão de chaves de cache do painel de admin).
  const processes = Array.isArray(coluna.processes) ? coluna.processes : [];
  return { ...coluna, processes, count: processes.length };
}

/** A lista de colunas normalizada. Entrada inválida → lista vazia. */
export function normalizarColunas(colunas) {
  if (!Array.isArray(colunas)) return [];
  return colunas.map(normalizarColuna).filter(Boolean);
}

/**
 * Funde as colunas activas com as de concluídos, pelo nome.
 *
 * A substituição é da coluna INTEIRA (é o que o quadro já fazia, e é
 * deliberado: o período de concluídos é um filtro só daquela consulta),
 * mas a saída passa pela normalização — senão a forma da coluna fundida
 * é a que o outro endpoint decidir.
 */
export function fundirColunasDeConcluidos(activas, concluidas) {
  const normalizadasActivas = normalizarColunas(activas);
  if (normalizadasActivas.length === 0) return normalizadasActivas;

  const porNome = new Map(
    normalizarColunas(concluidas).map((col) => [col.name, col]),
  );
  return normalizadasActivas.map((col) => porNome.get(col.name) ?? col);
}

/** O total de cartões realmente visíveis, somado das colunas já filtradas. */
export function contarCartoes(colunas) {
  return normalizarColunas(colunas).reduce(
    (acumulado, col) => acumulado + col.processes.length,
    0,
  );
}

/**
 * As colunas que vêm da consulta SEPARADA de concluídos (ver
 * `fundirColunasDeConcluidos`). Até essa consulta responder, o `count` delas
 * é o da consulta activa — que não as carrega — e «zero» não quer dizer
 * «vazia».
 */
export const COLUNAS_DE_CONCLUIDOS = Object.freeze(["concluidos", "desistencias"]);

/**
 * Que colunas se recolhem sozinhas ao primeiro olhar (uma coluna vazia ocupa
 * 320 px para nada).
 *
 * POR QUE «DECIDIR UMA VEZ POR COLUNA» E NÃO «SE NINGUÉM RECOLHEU AINDA»
 *   O efeito anterior só corria com `collapsedColumns.size === 0` e excluía
 *   `concluidos`/`desistencias` por nome («os utilizadores precisam de as
 *   ver»). A exclusão fazia todo o sentido enquanto o quadro mostrava
 *   cartões de OUTRAS redes (cartões-fantasma que o detalhe recusa): uma
 *   coluna «com conteúdo» que na verdade não tinha nada. Com as listagens
 *   limpas, uma coluna vazia é vazia — também estas duas.
 *
 *   A decisão é por coluna e uma só vez: o utilizador que reabrir uma coluna
 *   vazia não a vê voltar a fechar-se, e uma coluna que fique vazia a meio de
 *   um arrasto não desaparece debaixo do rato.
 *
 * AS DE CONCLUÍDOS ESPERAM PELA SUA CONSULTA
 *   Sem `concluidosProntos` o `count` 0 é só «ainda não carregou»: recolhê-las
 *   aí fechava Concluídos para sempre (a decisão não se repete) com cartões
 *   por chegar.
 *
 * @param {Array} colunas - as colunas já fundidas
 * @param {{jaDecididas?: Set<string>, concluidosProntos?: boolean}} [opcoes]
 * @returns {{recolher: string[], decididas: string[]}}
 */
export function planearAutoRecolha(
  colunas,
  { jaDecididas = new Set(), concluidosProntos = false } = {},
) {
  const recolher = [];
  const decididas = [];
  for (const coluna of normalizarColunas(colunas)) {
    if (jaDecididas.has(coluna.id)) continue;
    if (COLUNAS_DE_CONCLUIDOS.includes(coluna.name) && !concluidosProntos) continue;
    decididas.push(coluna.id);
    if (coluna.processes.length === 0) recolher.push(coluna.id);
  }
  return { recolher, decididas };
}

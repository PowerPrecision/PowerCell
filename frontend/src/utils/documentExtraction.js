/**
 * Preparação da revisão de uma extracção por documento (Épico 9).
 *
 * PURO, E DE PROPÓSITO: é aqui que vive a decisão que a regra de ouro do
 * épico protege — "a IA nunca escreve dados pessoais ou financeiros sem
 * confirmação do utilizador". Dentro de um componente de 2900 linhas essa
 * decisão não se consegue testar; aqui consegue-se.
 *
 * O que a função faz é separar o que a IA leu em duas listas:
 *   - **conflitos**: a ficha já tem um valor diferente → o consultor
 *     escolhe;
 *   - **valores novos**: a ficha está vazia → não há nada a escolher, mas
 *     TÊM de estar à vista, porque vão ser gravados na mesma. Era este o
 *     buraco: sem conflitos, o caminho em lote gravava sozinho.
 */

/**
 * @typedef {Object} ConflitoIA
 * @property {string} field
 * @property {any} existing_value
 * @property {any} new_value
 */

/**
 * @typedef {Object} RevisaoPendente
 * @property {Object} extractedData - Tudo o que a IA leu.
 * @property {ConflitoIA[]} conflicts - Campos por decidir.
 * @property {{field: string, value: any}[]} newValues - Campos a preencher.
 * @property {string} sourceDocument - Ficheiro de onde vieram os dados.
 * @property {"titular1"|"titular2"} targetTitular - A quem pertencem.
 */

/**
 * Transforma a resposta da extracção no estado da revisão.
 *
 * @param {Object} resposta
 * @param {Object} [resposta.extractedData]
 * @param {ConflitoIA[]} [resposta.conflicts]
 * @param {string} [resposta.sourceDocument]
 * @param {Array} [resposta.titularMatches]
 * @returns {RevisaoPendente|null} `null` quando não há nada para rever —
 *   abrir um diálogo vazio é pior do que dizer que a leitura não deu.
 */
export function prepararRevisaoDaExtraccao({
  extractedData,
  conflicts,
  sourceDocument,
  titularMatches,
} = {}) {
  if (!extractedData || typeof extractedData !== "object") return null;

  const campos = Object.entries(extractedData);
  if (campos.length === 0) return null;

  const listaConflitos = Array.isArray(conflicts) ? conflicts : [];
  const camposEmConflito = new Set(
    listaConflitos.map((conflito) => conflito?.field).filter(Boolean),
  );

  const valoresNovos = campos
    .filter(([campo]) => !camposEmConflito.has(campo))
    .map(([campo, valor]) => ({ field: campo, value: valor }));

  // O agregado do processo é quem diz se o documento é do 1.º ou do 2.º
  // titular. Sem ele, titular 1 — nunca adivinhar o 2.º, que escreveria
  // dados na pessoa errada.
  const agregado = (Array.isArray(titularMatches) ? titularMatches : []).find(
    (match) => match?.scope === "process_aggregate",
  );

  return {
    extractedData,
    conflicts: listaConflitos,
    newValues: valoresNovos,
    sourceDocument: sourceDocument || "",
    targetTitular: agregado?.match === "titular2" ? "titular2" : "titular1",
  };
}

/**
 * Regista no estado da revisão a decisão tomada sobre um conflito.
 *
 * PORQUE É PRECISO: ao confirmar, o contentor aplica `extractedData` à
 * ficha. Sem isto, escolher "fica o valor existente" removia o conflito da
 * lista mas deixava o valor da IA em `extractedData` — e a confirmação
 * escrevia-o na mesma, por cima da decisão do consultor. O pior tipo de
 * defeito: a interface diz que respeitou a escolha e o que fica gravado é
 * o contrário.
 *
 * @param {RevisaoPendente|null} revisao
 * @param {string} campo
 * @param {any} valorEscolhido
 * @returns {RevisaoPendente|null} Nova revisão; a original não é mutada.
 */
export function aplicarDecisaoNaRevisao(revisao, campo, valorEscolhido) {
  if (!revisao || !campo) return revisao;

  const conflitosRestantes = revisao.conflicts.filter(
    (conflito) => conflito?.field !== campo,
  );

  return {
    ...revisao,
    extractedData: { ...revisao.extractedData, [campo]: valorEscolhido },
    conflicts: conflitosRestantes,
  };
}

/**
 * Apagar um campo opcional: o que «apagar» quer dizer no ecrã.
 *
 * O PROBLEMA
 *   Os formulários de edição (Dados do Processo, Ficha de Cliente…) descartavam
 *   os campos VAZIOS antes de enviar (`if (value === "") delete …`, `x || undefined`).
 *   O servidor nunca recebia o pedido de limpeza: o toast dizia «sucesso» e o
 *   valor antigo voltava no refetch. Corrigiu-se primeiro para o email/telefone
 *   (`contactosAGravar`); isto generaliza a regra a qualquer campo.
 *
 * A REGRA (a mesma do servidor — `backend/services/campos_limpaveis.py`)
 *   Chave presente e vazia (`""`, `null`, espaços) = «apaga». Chave ausente =
 *   «não alterei». O ecrã só consegue distinguir os dois casos COMPARANDO com o
 *   que foi carregado: um campo vazio que já nasceu vazio não é um pedido, um que
 *   tinha valor e agora está vazio é. Por isso só se envia vazio para os campos
 *   que o utilizador de facto limpou (`camposLimpos`) — nunca «todos os que
 *   estão vazios», que apagaria o que este formulário nunca mostrou.
 *
 * O «0» É UM VALOR
 *   `parseFloat(x) || null` e `valor || ""` tratam 0 como vazio: 0 dependentes,
 *   0 € de renda ou 0 % de taxa eram gravados como «apagado» e mostrados como
 *   campo vazio. `numeroOuNulo` e `valorDoCampo` distinguem.
 */

/** `undefined`, `null` e texto só com espaços: o campo está vazio. `0` e `false` não. */
export const estaVazio = (valor) =>
  valor === undefined ||
  valor === null ||
  (typeof valor === "string" && valor.trim() === "");

/**
 * Nomes alternativos do MESMO dado, em `dados_pessoais` / `personal_data`.
 * Espelha `ALIASES_PESSOAIS` do servidor (há um teste que compara os dois).
 */
export const ALIASES_PESSOAIS = Object.freeze({
  morada_fiscal: ["morada", "address"],
  data_nascimento: ["birth_date"],
  birth_date: ["data_nascimento"],
  estado_civil: ["marital_status"],
  nacionalidade: ["nationality"],
});

/**
 * Nomes alternativos em `financial_data` que a hidratação usa como recurso do
 * campo canónico. Espelha `ALIASES_FINANCEIROS` do servidor.
 */
export const ALIASES_FINANCEIROS = Object.freeze({
  monthly_income: ["rendimento_mensal", "salario_liquido"],
  rendimento_bruto: ["salario_bruto"],
  capital_proprio: ["other_income"],
  nr_dependentes: ["number_of_dependents"],
  employer_name: ["empresa", "entidade_patronal"],
  employment_type: ["tipo_contrato"],
  employment_duration: ["antiguidade_emprego"],
});

/**
 * Campos que `camposLimpos` nunca devolve num formulário de dados pessoais:
 * o nome é obrigatório e os contactos têm o seu próprio caminho
 * (`contactosAGravar`). Os índices cegos derivam do valor.
 */
export const FORA_DA_LIMPEZA_PESSOAL = Object.freeze([
  "nome", "name", "nome_completo",
  "email", "telefone", "phone", "telefone_secundario", "email_secundario",
]);

/**
 * Os campos que TINHAM valor em `base` e agora estão vazios em `atual`.
 *
 * @param {object|null|undefined} base - o que foi carregado do servidor
 * @param {object|null|undefined} atual - o que o formulário tem agora
 * @param {{ignorar?: string[]}} [opcoes]
 * @returns {string[]}
 */
export function camposLimpos(base, atual, { ignorar = [] } = {}) {
  if (!base || typeof base !== "object") return [];
  const fora = new Set(ignorar);
  const hoje = atual && typeof atual === "object" ? atual : {};
  return Object.keys(base).filter(
    (chave) =>
      !fora.has(chave) &&
      !chave.endsWith("_hash") &&
      !estaVazio(base[chave]) &&
      estaVazio(hoje[chave]),
  );
}

/**
 * Preenche o campo canónico com o primeiro alternativo que tenha valor.
 *
 * É o «recurso» que a hidratação sempre fez (monthly_income ← salario_liquido…),
 * mas feito UMA vez, sobre o estado, em vez de em cada `value={a || b || ""}`
 * do JSX — onde apagar o canónico fazia o alternativo voltar a aparecer no input.
 */
export function preencherCanonicosComAliases(secao, tabela) {
  const saida = { ...(secao || {}) };
  for (const [canonico, aliases] of Object.entries(tabela)) {
    if (!estaVazio(saida[canonico])) continue;
    const alias = aliases.find((a) => !estaVazio(saida[a]));
    if (alias) saida[canonico] = saida[alias];
  }
  return saida;
}

/**
 * Um campo canónico apagado leva consigo os nomes alternativos: sem isso o
 * servidor recebia o canónico vazio E o alternativo antigo, e a hidratação
 * seguinte voltava a promover o alternativo.
 *
 * @param {object} payload - secção já limpa (valores finais a enviar)
 * @param {string[]} limpos - campos canónicos que o utilizador apagou
 * @param {Record<string,string[]>} tabela
 * @param {*} valorVazio - `""` (pessoais) ou `null` (financeiro/imóvel/crédito)
 * @param {object} [base] - o que foi carregado: só se limpam os alternativos que tinham valor
 */
export function limparAliasesDosCampos(payload, limpos, tabela, valorVazio, base) {
  for (const campo of limpos) {
    for (const alias of tabela[campo] || []) {
      // Só os que o servidor TEM: criar `address: ""` numa ficha que nunca o teve é ruído.
      if (!estaVazio(base?.[alias])) payload[alias] = valorVazio;
    }
  }
  return payload;
}

/**
 * Número de um `<input type="number">`: `""` → `null`, `"0"` → `0`.
 * (`parseFloat(x) || null` fazia do 0 um campo apagado.)
 */
export function numeroOuNulo(texto, { inteiro = false } = {}) {
  if (estaVazio(texto)) return null;
  const n = inteiro ? parseInt(texto, 10) : parseFloat(texto);
  return Number.isNaN(n) ? null : n;
}

/** O que mostrar num input: `0` mostra-se, só o vazio fica em branco. */
export const valorDoCampo = (valor) => (estaVazio(valor) ? "" : valor);

/**
 * Alterações a enviar de um formulário simples (campos de texto).
 *
 * Só entram os campos que MUDARAM: com valor novo vai o valor; apagado vai `""`
 * (nunca `undefined`, que o JSON descarta e o servidor lê como «não alterei»).
 *
 * @returns {{definidos: Record<string,string>, limpos: string[]}}
 */
export function alteracoesDeTexto(original, atual, chaves) {
  const definidos = {};
  const limpos = [];
  for (const chave of chaves) {
    const antes = original?.[chave];
    const agora = atual?.[chave];
    const novo = typeof agora === "string" ? agora.trim() : agora;
    if ((estaVazio(antes) && estaVazio(novo)) || antes === novo) continue;
    if (estaVazio(novo)) {
      definidos[chave] = "";
      limpos.push(chave);
    } else {
      definidos[chave] = novo;
    }
  }
  return { definidos, limpos };
}

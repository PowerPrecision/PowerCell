/**
 * Pacote DR — pré-preenchimento das calculadoras a partir do processo ativo.
 *
 * Quando o utilizador está em `/processo/:id` ou `/process/:id`, o hub do
 * Header lê o processo (TanStack Query / GET) e mapeia montante, prazo,
 * spread/TAN e rendimentos para os campos das calculadoras.
 */

const PROCESS_PATH_RE = /^\/process(?:o)?\/([^/]+)/;

/**
 * Extrai o ID do processo a partir do pathname do React Router.
 * @param {string} pathname
 * @returns {string|null}
 */
export function getProcessIdFromPath(pathname) {
  if (!pathname || typeof pathname !== "string") return null;
  const match = pathname.match(PROCESS_PATH_RE);
  return match?.[1] || null;
}

function positiveNumber(value) {
  const n = Number(value);
  return Number.isFinite(n) && n > 0 ? n : undefined;
}

/**
 * Constrói o payload de pré-preenchimento a partir do documento do processo.
 *
 * @param {object|null|undefined} process
 * @returns {{
 *   mortgage: { capital?: number, prazoAnos?: number, taxaJuro?: number },
 *   dsti: object,
 *   risk: object,
 *   hasContext: boolean,
 * }}
 */
export function extractCalculatorPrefill(process) {
  const empty = {
    mortgage: {},
    dsti: {},
    risk: {},
    hasContext: false,
  };
  if (!process || typeof process !== "object") return empty;

  const credit = process.credit_data || {};
  const financial = process.financial_data || {};
  const realEstate = process.real_estate_data || {};
  const personal = process.personal_data || {};

  const capital = positiveNumber(
    credit.requested_amount ?? credit.valor_emprestimo ?? financial.valor_financiamento,
  );
  const prazoAnos = positiveNumber(
    credit.loan_term_years ?? credit.prazo_anos ?? financial.prazo_pretendido,
  );
  const taxaJuro = positiveNumber(
    credit.interest_rate ?? credit.taxa_anual ?? credit.spread,
  );
  const spread = positiveNumber(credit.spread);
  const monthlyIncome =
    financial.monthly_income ?? financial.salario_liquido ?? financial.rendimento_mensal;
  const valorImovel = realEstate.valor_imovel ?? realEstate.valor ?? process.property_value;
  const valorEntrada = financial.valor_entrada ?? financial.capital_proprio;
  const monthlyPayment = credit.monthly_payment;

  const mortgage = {};
  if (capital != null) mortgage.capital = capital;
  if (prazoAnos != null) mortgage.prazoAnos = prazoAnos;
  if (taxaJuro != null) mortgage.taxaJuro = taxaJuro;

  const dsti = {
    rendimento_bruto: financial.rendimento_bruto,
    rendimento_mensal: monthlyIncome,
    salario_liquido: financial.salario_liquido,
    renda_habitacao_atual: financial.renda_habitacao_atual,
    rendimento_co_titular: financial.rendimento_co_titular,
    prestacao_nova: monthlyPayment,
  };

  const risk = {
    rendimento_mensal: monthlyIncome,
    salario_liquido: financial.salario_liquido,
    valor_imovel: valorImovel,
    valor_entrada: valorEntrada,
    capital_proprio: financial.capital_proprio,
    idade: personal.idade,
    data_nascimento: personal.data_nascimento || personal.birth_date,
    prazo_anos: prazoAnos,
    taxa_anual: taxaJuro,
    interest_rate: taxaJuro,
    spread,
  };

  const hasContext = Boolean(
    capital || prazoAnos || taxaJuro || monthlyIncome || valorImovel,
  );

  return { mortgage, dsti, risk, hasContext };
}

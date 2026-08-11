/**
 * mortgageCalculations — motor de cálculo financeiro para Crédito Habitação.
 *
 * PORQUÊ: esta lógica já existia embutida no `SimulatorCH.jsx` (Portal do
 * Cliente), misturada com JSX e estilos. Para reutilizar o mesmo motor
 * matemático na Calculadora de Prestações do CRM (`MortgageSimulator.jsx`,
 * em `components/calculators/`) sem duplicar código, extrai-se para um
 * utilitário puro — sem estado, sem imports de UI.
 *
 * MOTOR MATEMÁTICO — Sistema Francês de Amortização:
 *   PMT = (M * r) / (1 - (1 + r)^(-n))
 *
 * onde M = capital, r = taxa mensal (taxa anual / 12 / 100), n = nº de meses.
 */

/**
 * Calcula a prestação mensal do sistema francês (capital + juros, sem seguros).
 *
 * @param {number} capital    - Capital emprestado (€)
 * @param {number} taxaAnual  - Taxa anual nominal em percentagem (ex: 3.5)
 * @param {number} numMeses   - Número total de prestações
 * @returns {number} Prestação mensal (€), 0 se os parâmetros forem inválidos
 */
export function calcularPrestacaoMensal(capital, taxaAnual, numMeses) {
  const m = Number(capital) || 0;
  const n = Number(numMeses) || 0;
  if (m <= 0 || n <= 0) return 0;

  const r = (Number(taxaAnual) || 0) / 100 / 12;
  if (r === 0) return m / n;

  const fator = Math.pow(1 + r, -n);
  return (m * r) / (1 - fator);
}

/**
 * Calcula a TAEG (Taxa Anual de Encargos Efetiva) por bisseção.
 *
 * A TAEG é a taxa anual que iguala o montante líquido recebido pelo cliente
 * (capital - comissões) ao valor presente de todas as prestações + seguros.
 *
 * @param {number} capitalLiquido  - Capital - comissões iniciais (o que o cliente recebe)
 * @param {number} prestacaoBase   - Prestação mensal (só capital + juros)
 * @param {number} segurosMensal   - Total de seguros mensais (vida + multirriscos)
 * @param {number} numMeses        - Número total de prestações
 * @returns {number} TAEG em percentagem (ex: 4.12), 0 se inválido
 */
export function calcularTAEG(capitalLiquido, prestacaoBase, segurosMensal, numMeses) {
  const capital = Number(capitalLiquido) || 0;
  const n = Number(numMeses) || 0;
  if (capital <= 0 || n <= 0) return 0;

  const fluxoMensal = (Number(prestacaoBase) || 0) + (Number(segurosMensal) || 0);

  // Bisseção: encontrar a taxa mensal i tal que
  // capitalLiquido = fluxoMensal * (1 - (1+i)^-n) / i
  let lo = 0.000001; // 0.0001% mensal
  let hi = 0.1; // 10% mensal (120% anual) — limite superior generoso
  let mid = 0;

  for (let iter = 0; iter < 100; iter++) {
    mid = (lo + hi) / 2;
    const vp = (fluxoMensal * (1 - Math.pow(1 + mid, -n))) / mid;
    if (vp > capital) {
      lo = mid; // taxa demasiado baixa → VP alto → subir taxa
    } else {
      hi = mid; // taxa demasiado alta → VP baixo → baixar taxa
    }
    if (hi - lo < 0.0000001) break;
  }

  return mid * 12 * 100;
}

/**
 * Simulação completa de um Crédito Habitação (sistema francês, taxa única).
 *
 * @param {Object} params
 * @param {number} params.capital           - Montante do empréstimo (€)
 * @param {number} params.prazoAnos         - Prazo em anos
 * @param {number} params.taxaJuro          - Taxa de juro anual / TAN (%) — já inclui spread se variável
 * @param {boolean} [params.incluirSeguros] - Se true, soma seguros à prestação e à TAEG
 * @param {number} [params.seguroVida]      - Seguro de vida mensal (€)
 * @param {number} [params.seguroMultirriscos] - Seguro multirriscos mensal (€)
 * @param {number} [params.comissoesIniciais] - Comissões/encargos iniciais (€), usados só na TAEG
 * @returns {{
 *   numMeses: number,
 *   prestacaoBase: number,
 *   segurosMensal: number,
 *   prestacaoTotal: number,
 *   totalPago: number,
 *   totalJuros: number,
 *   taeg: number,
 * }|null} null se `capital`/`prazoAnos` forem inválidos
 */
export function simularCreditoHabitacao({
  capital,
  prazoAnos,
  taxaJuro,
  incluirSeguros = false,
  seguroVida = 0,
  seguroMultirriscos = 0,
  comissoesIniciais = 0,
}) {
  const m = Number(capital) || 0;
  const numMeses = (Number(prazoAnos) || 0) * 12;
  if (m <= 0 || numMeses <= 0) return null;

  const prestacaoBase = calcularPrestacaoMensal(m, taxaJuro, numMeses);
  const segurosMensal = incluirSeguros
    ? (Number(seguroVida) || 0) + (Number(seguroMultirriscos) || 0)
    : 0;
  const prestacaoTotal = prestacaoBase + segurosMensal;

  const comissoes = Number(comissoesIniciais) || 0;
  const totalPago = prestacaoTotal * numMeses + comissoes;
  const totalJuros = prestacaoBase * numMeses - m;

  const capitalLiquido = m - comissoes;
  const taeg = calcularTAEG(capitalLiquido, prestacaoBase, segurosMensal, numMeses);

  return {
    numMeses,
    prestacaoBase,
    segurosMensal,
    prestacaoTotal,
    totalPago,
    totalJuros,
    taeg,
  };
}

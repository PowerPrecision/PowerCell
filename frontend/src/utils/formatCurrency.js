/**
 * Formatação centralizada de valores monetários em Euros (pt-PT).
 *
 * PORQUÊ: antes desta função existirem 7 implementações locais quase idênticas
 * (`FinanceDashboard`, `FinanceTab`, `BranchPerformancePage`, `FilteredProcessList`,
 * `ProcessSummaryCard`, `ProcessDetailsModal`) + 18 ficheiros com `Intl.NumberFormat`
 * inline, cada uma com um fallback e número de casas decimais diferente. Esta função
 * é a única fonte de verdade para "como é que um valor em euros aparece no ecrã".
 *
 * @param {number|string|null|undefined} value - Valor a formatar (aceita string numérica)
 * @param {Object} [options]
 * @param {string} [options.fallback="—"] - Texto a mostrar quando o valor é nulo/inválido
 * @param {number} [options.minimumFractionDigits=2] - Casas decimais mínimas
 * @param {number} [options.maximumFractionDigits=2] - Casas decimais máximas
 * @returns {string} Valor formatado, ex: "1.234,50 €"
 */
export function formatCurrency(value, options = {}) {
  const {
    fallback = "—",
    minimumFractionDigits = 2,
    maximumFractionDigits = 2,
  } = options;

  const numericValue = typeof value === "string" ? Number(value) : value;

  if (numericValue == null || Number.isNaN(numericValue)) {
    return fallback;
  }

  return new Intl.NumberFormat("pt-PT", {
    style: "currency",
    currency: "EUR",
    minimumFractionDigits,
    maximumFractionDigits,
  }).format(numericValue);
}

export default formatCurrency;

/**
 * Constantes e helpers puros partilhados pela página ProcessDetails.
 * Extraídos do mega-ficheiro para reduzir o tamanho e permitir reutilização.
 */

export const statusColors = {
  yellow: "bg-yellow-100 text-yellow-800 border-yellow-200",
  blue: "bg-blue-100 text-blue-800 border-blue-200",
  orange: "bg-orange-100 text-orange-800 border-orange-200",
  green: "bg-emerald-100 text-emerald-800 border-emerald-200",
  red: "bg-red-100 text-red-800 border-red-200",
  purple: "bg-purple-100 text-purple-800 border-purple-200",
};

export const BANK_LIST = [
  "ABANCA", "BBVA", "BEST", "BIG", "BPI", "CGD", "Crédito Agrícola",
  "CTT", "Millennium bcp", "Novo Banco", "Popular", "Santander Totta", "Outro",
];

/** Cores dos bancos portugueses para badges */
export const BANK_COLORS = {
  "ABANCA": "bg-red-500 text-white",
  "BBVA": "bg-blue-600 text-white",
  "BEST": "bg-green-600 text-white",
  "BIG": "bg-orange-500 text-white",
  "BPI": "bg-yellow-400 text-yellow-900",
  "CGD": "bg-red-600 text-white",
  "Crédito Agrícola": "bg-green-500 text-white",
  "Credito Agricola": "bg-green-500 text-white",
  "CTT": "bg-red-400 text-white",
  "Millennium bcp": "bg-red-500 text-white",
  "Millennium": "bg-red-500 text-white",
  "bcp": "bg-red-500 text-white",
  "Novo Banco": "bg-gray-700 text-white",
  "NovoBanco": "bg-gray-700 text-white",
  "Popular": "bg-blue-500 text-white",
  "Santander Totta": "bg-red-600 text-white",
  "Santander": "bg-red-600 text-white",
  "Bankinter": "bg-blue-800 text-white",
  "ActivoBank": "bg-teal-500 text-white",
  "Eurobic": "bg-red-500 text-white",
  "BIC": "bg-red-500 text-white",
  "Caixa Geral": "bg-red-600 text-white",
};

/** Obtém a classe CSS de cor para um banco (match exacto ou parcial). */
export const getBankColor = (bankName) => {
  if (!bankName) return "bg-gray-200 text-gray-800";

  // Garantir que bankName é uma string (pode vir como objecto {value, label})
  const name = typeof bankName === "string"
    ? bankName
    : (bankName?.label || bankName?.value || String(bankName));

  if (BANK_COLORS[name]) {
    return BANK_COLORS[name];
  }

  const bankLower = name.toLowerCase();
  for (const [bank, color] of Object.entries(BANK_COLORS)) {
    if (bankLower.includes(bank.toLowerCase()) || bank.toLowerCase().includes(bankLower)) {
      return color;
    }
  }

  return "bg-gray-200 text-gray-800";
};

export const typeLabels = {
  credito: "Crédito",
  imobiliaria: "Imobiliária",
  ambos: "Crédito + Imobiliária",
};

export const LABEL_PRESETS = [
  "Urgente",
  "Refinanciamento",
  "Primeira Habitação",
  "Investimento",
  "Documentação Pendente",
  "Aguarda Banco",
  "Aguarda Cliente",
  "Jovem",
];

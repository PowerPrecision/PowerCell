import { clsx } from "clsx";
import { twMerge } from "tailwind-merge"
import { parseISO, format } from "date-fns";

export function cn(...inputs) {
  return twMerge(clsx(inputs));
}

/**
 * Normaliza uma string de data para formato compatível com Safari/iOS.
 * Safari não consegue fazer parse de 'YYYY-MM-DD HH:mm:ss' — precisa de
 * 'YYYY/MM/DD HH:mm:ss' ou 'YYYY-MM-DDTHH:mm:ss'.
 *
 * Retorna a string normalizada, ou undefined se a data for inválida.
 *
 * ⚠️ NOTA IMPORTANTE: Retorna undefined (NÃO null) para datas inválidas.
 * Isto é intencional: new Date(null) = 01/01/1970 (epoch!), enquanto
 * new Date(undefined) = Invalid Date (NaN). Todos os call sites que fazem
 * new Date(safeDateStr(x)) devem verificar isNaN() antes de usar o resultado.
 * Para formatação segura, use formatDate(x), formatDateTime(x), ou safeFormat().
 */
export const safeDateStr = (dateString) => {
  if (!dateString) return undefined;
  if (typeof dateString !== "string") {
    // Pode já ser um Date object
    if (dateString instanceof Date) return isNaN(dateString.getTime()) ? undefined : dateString;
    return undefined;
  }
  // Substituir dash por slash na parte da data (antes do T ou espaço)
  // Isto converte '2025-03-15 14:30:00' → '2025/03/15T14:30:00'
  // e '2025-03-15T14:30:00' → '2025/03/15T14:30:00'
  const normalized = dateString
    .replace(/(\d{4})-(\d{2})-(\d{2})/, "$1/$2/$3")
    .replace(" ", "T"); // garante formato ISO
  // Verificar se o resultado é uma data válida antes de retornar
  try {
    const testDate = new Date(normalized);
    if (isNaN(testDate.getTime())) return undefined;
  } catch {
    return undefined;
  }
  return normalized;
};

/**
 * Faz parseISO de forma segura — retorna null em vez de crashar com
 * "Invalid time value" quando a data é inválida.
 *
 * NOTA: NÃO usa safeDateStr() antes de parseISO, porque safeDateStr
 * converte traços em barras (para compatibilidade Safari/new Date),
 * mas parseISO do date-fns exige formato ISO 8601 com traços.
 * A conversão de barras fazia com que parseISO retornasse Invalid Date,
 * causando "Data inválida" no chat e noutros componentes.
 *
 * Estratégia:
 * 1. Tenta parseISO directamente (funciona com ISO 8601: 2025-03-15T14:30:00+00:00)
 * 2. Se falhar, tenta new Date(safeDateStr()) como fallback para Safari
 */
export const safeParseISO = (dateString) => {
  if (!dateString) return null;
  if (dateString instanceof Date) {
    return isNaN(dateString.getTime()) ? null : dateString;
  }
  if (typeof dateString !== "string") return null;
  try {
    // Tentar parseISO directamente com a string original (formato ISO 8601)
    const parsed = parseISO(dateString);
    if (!isNaN(parsed.getTime())) return parsed;
  } catch {
    // parseISO falhou, tentar fallback
  }
  try {
    // Fallback: normalizar para Safari e usar new Date()
    const normalized = safeDateStr(dateString);
    if (!normalized) return null;
    const d = new Date(normalized);
    return isNaN(d.getTime()) ? null : d;
  } catch {
    return null;
  }
};

/**
 * Formata uma data com date-fns de forma segura — nunca crasha.
 * Retorna fallback (default "-") se a data for inválida.
 */
export const safeFormat = (dateString, formatStr, { locale } = {}) => {
  try {
    const parsed = safeParseISO(dateString);
    if (!parsed) return "-";
    return format(parsed, formatStr, { locale });
  } catch {
    return "-";
  }
};

/**
 * Cria um Date de forma segura em Safari/iOS.
 * Retorna null se a data for inválida.
 */
export const safeDate = (dateString) => {
  if (!dateString) return null;
  if (dateString instanceof Date) {
    return isNaN(dateString.getTime()) ? null : dateString;
  }
  try {
    const d = new Date(safeDateStr(dateString));
    return isNaN(d.getTime()) ? null : d;
  } catch {
    return null;
  }
};

/**
 * Formata uma data para exibição (dd/MM/yyyy) — seguro em Safari/iOS.
 * PACOTE BV (Fix 3): usa safeParseISO em vez de safeDate para lidar corretamente
 * com strings ISO 8601 com 'T' (ex: 2025-01-15T14:30:00+00:00). Antes,
 * safeDateStr convertia dashes→slashes mas mantinha o 'T', produzindo
 * '2025/01/15T14:30:00+00:00' que é Invalid Date em V8/SpiderMonkey.
 */
export const formatDate = (dateString) => {
  if (!dateString) return "-";
  try {
    const d = safeParseISO(dateString);
    if (!d) return "-";
    return new Intl.DateTimeFormat("pt-PT", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
    }).format(d);
  } catch {
    return "-";
  }
};

/**
 * Formata uma data+hora para exibição (dd/MM/yyyy HH:mm) — seguro em Safari/iOS.
 * PACOTE BV (Fix 3): usa safeParseISO em vez de safeDate para lidar corretamente
 * com strings ISO 8601 com 'T' (ex: 2025-01-15T14:30:00+00:00). Antes,
 * safeDateStr convertia dashes→slashes mas mantinha o 'T', produzindo
 * '2025/01/15T14:30:00+00:00' que é Invalid Date — todas as datas apareciam '-'.
 */
export const formatDateTime = (dateString) => {
  if (!dateString) return "-";
  try {
    const d = safeParseISO(dateString);
    if (!d) return "-";
    return new Intl.DateTimeFormat("pt-PT", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    }).format(d);
  } catch {
    return "-";
  }
};

/**
 * formatSafeDate — Função de formatação de datas 100% segura para Safari/iOS.
 *
 * Safari falha ao fazer parsing de strings de data com espaço em vez de 'T'
 * (ex: '2025-03-15 14:30:00'). Esta função normaliza a string antes de
 * criar o objeto Date, evitando o erro React "Invalid time value".
 *
 * @param {string|Date|null|undefined} dateString — A data a formatar
 * @returns {string} — Data formatada em pt-PT ou texto de fallback
 */
export const formatSafeDate = (dateString) => {
  if (!dateString) return 'Data indisponível';

  // Normalização para o Safari: Substituir espaços por 'T' e garantir compatibilidade ISO
  let safeString = dateString;
  if (typeof dateString === 'string') {
    safeString = dateString.replace(' ', 'T');
  }

  const d = new Date(safeString);
  return isNaN(d.getTime()) ? 'Data inválida' : d.toLocaleString('pt-PT');
};
